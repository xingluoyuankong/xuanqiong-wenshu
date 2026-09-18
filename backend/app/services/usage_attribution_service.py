# -*- coding: utf-8 -*-
"""LLM 调用归因上下文与自动记账（US-010 budget closure）。

问题：此前 ``TokenBudgetService`` 只在手工 API 端点被调用，生成链路从不记账，
导致预算数字与真实消耗无关。本模块把记账下沉到 LLM 出口，并用 ContextVar
承载归因键（project/chapter/run/stage/module），使调用方无需逐处传参。

设计要点：
- ``usage_scope`` 用 contextvars，天然随 asyncio 任务隔离 —— 并发的候选版本
  任务各自持有自己的 scope，不会串味。
- Provider 未返回 usage 时退化为本地估算，并置 ``is_estimated=True``，
  绝不把估算值伪装成实际值。
- 记账失败**永不阻断生成**（与既有 usage_service 的处理一致）。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class UsageScope:
    project_id: Optional[str] = None
    chapter_id: Optional[int] = None
    run_id: Optional[str] = None
    stage: Optional[str] = None
    module: str = "content"


_USAGE_SCOPE: ContextVar[Optional[UsageScope]] = ContextVar("llm_usage_scope", default=None)


def current_usage_scope() -> Optional[UsageScope]:
    return _USAGE_SCOPE.get()


def update_usage_scope_chapter(chapter_id: Optional[int]) -> None:
    """在已建立的 scope 内回填 chapter_id（供 impl 取得章节后调用）。

    直接改对象字段（不重设 ContextVar），因此对持有同一对象的后续调用即时生效。
    """
    scope = _USAGE_SCOPE.get()
    if scope is not None and chapter_id is not None:
        scope.chapter_id = chapter_id


@asynccontextmanager
async def usage_scope(
    *,
    project_id: Optional[str],
    chapter_id: Optional[int] = None,
    run_id: Optional[str] = None,
    stage: Optional[str] = None,
    module: str = "content",
) -> AsyncIterator[UsageScope]:
    """在块内建立归因上下文；退出时无副作用。"""
    scope = UsageScope(
        project_id=project_id,
        chapter_id=chapter_id,
        run_id=run_id,
        stage=stage,
        module=module,
    )
    token = _USAGE_SCOPE.set(scope)
    try:
        yield scope
    finally:
        _USAGE_SCOPE.reset(token)


def estimate_tokens(text: str) -> int:
    """粗略估算 token 数。

    中文约 1.5 char/token，英文约 4 char/token；这里取保守混合口径。
    仅用于 Provider 未返回 usage 时的降级路径，结果会被标记 estimated。
    """
    if not text:
        return 0
    ascii_chars = sum(1 for ch in text if ord(ch) < 128)
    non_ascii = len(text) - ascii_chars
    return int(ascii_chars / 4) + int(non_ascii / 1.5) + 1


def extract_usage_tokens(usage: Any) -> Optional[Dict[str, int]]:
    """从 Provider usage 对象/字典中取出 prompt/completion tokens。

    返回 None 表示无法解析（调用方应走估算路径）。
    """
    if usage is None:
        return None

    def _get(name: str) -> Optional[int]:
        if isinstance(usage, dict):
            value = usage.get(name)
        else:
            value = getattr(usage, name, None)
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    prompt = _get("prompt_tokens")
    completion = _get("completion_tokens")
    if prompt is None and completion is None:
        return None
    prompt = prompt or 0
    completion = completion or 0
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
    }


def estimate_cost(model_name: Optional[str], prompt_tokens: int, completion_tokens: int) -> float:
    """按模型单价把 token 换算为成本（人民币）。

    诚实说明：本项目**没有**中央价格表，以下是内置的保守缺省单价，仅用于
    在没有外部定价配置时给出量级正确的数字。若要精确结算，应替换为
    真实定价配置。返回值为元。
    """
    # 缺省：输入 ¥0.001/1K tokens，输出 ¥0.002/1K tokens（量级参考）
    rate_in = 0.001 / 1000
    rate_out = 0.002 / 1000
    return round(prompt_tokens * rate_in + completion_tokens * rate_out, 8)


async def record_llm_usage(
    session: Any,
    *,
    model_name: Optional[str],
    usage: Any,
    prompt_text: str = "",
    completion_text: str = "",
    attempt_index: Optional[int] = None,
) -> None:
    """把一次**成功的物理调用**记入预算账本。

    仅在归类上下文存在（有 project_id）且拿到内容时写入。
    失败只记 warning，绝不抛出。
    """
    scope = current_usage_scope()
    if scope is None or not scope.project_id:
        return

    parsed = extract_usage_tokens(usage)
    is_estimated = parsed is None
    if parsed is None:
        prompt_tokens = estimate_tokens(prompt_text)
        completion_tokens = estimate_tokens(completion_text)
    else:
        prompt_tokens = parsed["prompt_tokens"]
        completion_tokens = parsed["completion_tokens"]

    if prompt_tokens == 0 and completion_tokens == 0:
        return

    try:
        from .token_budget_service import TokenBudgetService

        service = TokenBudgetService(session)
        await service.record_usage(
            project_id=scope.project_id,
            module=scope.module,
            tokens_used=prompt_tokens + completion_tokens,
            cost=estimate_cost(model_name, prompt_tokens, completion_tokens),
            model_name=model_name,
            chapter_id=scope.chapter_id,
            operation_type="generation",
            description=f"auto-recorded (stage={scope.stage or 'unknown'})",
            run_id=scope.run_id,
            stage=scope.stage,
            attempt_index=attempt_index,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            is_estimated=is_estimated,
        )
    except Exception as exc:  # noqa: BLE001 - 记账失败不得阻断生成
        logger.warning(
            "自动记账失败（不影响生成）：project=%s run=%s stage=%s error=%s",
            scope.project_id,
            scope.run_id,
            scope.stage,
            exc,
        )
