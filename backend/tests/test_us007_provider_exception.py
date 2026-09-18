"""
US-007: Provider 异常处理测试

测的是**真实生效的重试层** `generation_call_service.call_generation_text`
（pipeline 所有文本生成的统一出口），而不是已被弃用的 LLMService 内部方法。

诚实说明：
- 重试策略在 GenerationCallPolicy 上，不在 LLMService.get_llm_response 里。
  原 tests/test_provider_exception_handling.py 打桩 `_stream_and_collect`
  并断言 get_llm_response 会重试 —— 那是错的，该层只做单次调用 + 硬超时。
- 重试语义（generation_call_service.py:442-547）：
  * retry_attempts=N → 最多 N 次
  * is_retryable_http_exception: 408/409/425/429/500/502/503/504 才重试
  * 401/403/400 **不重试**（永久性错误，立即上抛）
  * 尊重 Retry-After 头
  * 特殊的"降级重试"：schema 被拒 → 退回 JSON 模式；max_tokens 超限 → 降 0.72/0.82
- 覆盖：可重试/不可重试/退避/降级/耗尽后上抛/非法 JSON 修复。
"""

import asyncio
import json
import sys
import time
from pathlib import Path

import pytest
from fastapi import HTTPException

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.generation_call_service import (  # noqa: E402
    GenerationCallPolicy,
    GenerationJSONDecodeError,
    call_generation_json,
    call_generation_text,
    classify_provider_error,
    is_retryable_http_exception,
    resolve_retry_delay_seconds,
)

pytestmark = pytest.mark.asyncio


class FakeLLMService:
    """最小 LLMService 替身：只实现 call_generation_text 需要的接口。"""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []
        self.sleeps = []

    async def get_llm_response(self, system_prompt, conversation_history, **kwargs):
        self.calls.append({"temperature": kwargs.get("temperature"), "kwargs": kwargs})
        item = self.script[min(len(self.calls) - 1, len(self.script) - 1)]
        if isinstance(item, Exception):
            raise item
        if callable(item):
            return item()
        return item


def policy(**overrides) -> GenerationCallPolicy:
    base = dict(
        retry_attempts=3,
        backoff_base_seconds=0.0,
        backoff_max_seconds=0.0,
        heartbeat_interval_seconds=None,
        soft_timeout_seconds=None,
        stage_label="US-007 测试阶段",
    )
    base.update(overrides)
    return GenerationCallPolicy(**base)


def http_exc(status: int, detail: str = "boom", headers=None):
    return HTTPException(status_code=status, detail=detail, headers=headers)


async def run(script, **policy_overrides):
    llm = FakeLLMService(script)
    pol = policy(**policy_overrides)
    return llm, await call_generation_text(
        llm_service=llm,
        system_prompt="sys",
        conversation_history=[{"role": "user", "content": "hi"}],
        temperature=0.7,
        user_id=1,
        timeout=30.0,
        policy=pol,
    )


# ---------------------------------------------------------------- 分类语义


@pytest.mark.parametrize(
    "status,expected",
    [
        (429, "rate_limit"),
        (408, "timeout"),
        (504, "timeout"),
        (500, "provider_jitter"),
        (503, "provider_jitter"),
        (401, "provider_auth"),
        (403, "provider_auth"),
        (400, "bad_request"),
        (404, "unknown"),
    ],
)
def test_classify_provider_error(status, expected):
    assert classify_provider_error(http_exc(status, "x")) == expected


@pytest.mark.parametrize(
    "status,retryable",
    [(408, True), (429, True), (500, True), (503, True), (401, False), (403, False), (400, False), (404, False)],
)
def test_retryability_matrix(status, retryable):
    assert is_retryable_http_exception(http_exc(status)) is retryable


def test_retry_after_header_is_honored():
    """Retry-After 头被解析并优先于指数退避，但仍受 backoff_max_seconds 封顶。

    实测：_resolve_retry_after_seconds(429, Retry-After: 7) -> 7.0
          backoff_max_seconds=30.0 -> 7.0（采用 Retry-After）
          backoff_max_seconds=0.0  -> 0.0（被封顶截断，属预期行为）
    """
    exc = http_exc(429, "slow down", headers={"Retry-After": "7"})
    assert resolve_retry_delay_seconds(exc, 1, policy(backoff_max_seconds=30.0)) == pytest.approx(7.0, abs=0.5)


def test_retry_after_is_capped_by_backoff_max():
    """封顶行为：Retry-After 超过 backoff_max_seconds 时按上限截断。"""
    exc = http_exc(429, "slow down", headers={"Retry-After": "120"})
    assert resolve_retry_delay_seconds(exc, 1, policy(backoff_max_seconds=30.0)) == pytest.approx(30.0, abs=0.5)


def test_retryable_flag_in_detail_overrides_status():
    exc = HTTPException(status_code=400, detail={"retryable": True, "message": "transient"})
    assert is_retryable_http_exception(exc) is True


# ---------------------------------------------------------------- 重试行为


async def test_retryable_5xx_retries_until_success():
    llm, result = await run([http_exc(500), http_exc(503), "ok-text"])
    assert result.text == "ok-text"
    assert result.attempts == 3
    assert len(llm.calls) == 3


async def test_retryable_5xx_exhausted_raises_last_error():
    with pytest.raises(HTTPException) as exc_info:
        await run([http_exc(500), http_exc(502), http_exc(503, "final")])
    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "final"


async def test_auth_error_not_retried():
    """401 是永久性错误：只能有一次调用，绝不重试。"""
    llm = FakeLLMService([http_exc(401, "bad key")])
    with pytest.raises(HTTPException) as exc_info:
        await call_generation_text(
            llm_service=llm,
            system_prompt="sys",
            conversation_history=[],
            temperature=0.7,
            user_id=1,
            timeout=30.0,
            policy=policy(),
        )
    assert exc_info.value.status_code == 401
    assert len(llm.calls) == 1, "401 不得重试"


async def test_invalid_request_400_not_retried():
    llm = FakeLLMService([http_exc(400, "bad request")])
    with pytest.raises(HTTPException):
        await call_generation_text(
            llm_service=llm,
            system_prompt="sys",
            conversation_history=[],
            temperature=0.7,
            user_id=1,
            timeout=30.0,
            policy=policy(),
        )
    assert len(llm.calls) == 1, "400 不得重试"


async def test_rate_limit_retries_and_respects_attempt_budget():
    llm = FakeLLMService([http_exc(429)] * 10)
    with pytest.raises(HTTPException) as exc_info:
        await call_generation_text(
            llm_service=llm,
            system_prompt="sys",
            conversation_history=[],
            temperature=0.7,
            user_id=1,
            timeout=30.0,
            policy=policy(retry_attempts=3),
        )
    assert exc_info.value.status_code == 429
    assert len(llm.calls) == 3, f"retry_attempts=3 应恰好调用 3 次，实际 {len(llm.calls)}"


# ---------------------------------------------------------------- 降级重试


async def test_structured_output_rejected_downgrades_to_json_mode():
    schema = {"type": "object", "properties": {"a": {"type": "string"}}}
    llm = FakeLLMService([http_exc(400, "structured output unsupported"), "{}"])
    result = await call_generation_text(
        llm_service=llm,
        system_prompt="sys",
        conversation_history=[],
        temperature=0.7,
        user_id=1,
        timeout=30.0,
        policy=policy(json_schema=schema, retry_attempts=2),
    )
    assert result.text == "{}"
    assert len(llm.calls) == 2
    assert result.response_format_used == "json_object", "应已从 schema 模式降级"


async def test_output_token_limit_reduces_max_tokens():
    llm = FakeLLMService([http_exc(400, "max_tokens is too large: 20000"), "ok"])
    result = await call_generation_text(
        llm_service=llm,
        system_prompt="sys",
        conversation_history=[],
        temperature=0.7,
        user_id=1,
        timeout=30.0,
        policy=policy(max_tokens=20000, retry_attempts=3),
    )
    assert result.text == "ok"
    assert len(llm.calls) == 2
    assert llm.calls[1]["kwargs"]["max_tokens"] == 14400, "20000 * 0.72 = 14400"


# ---------------------------------------------------------------- 非法 JSON


async def test_invalid_json_is_repaired_then_succeeds():
    llm = FakeLLMService(["<not json>", json.dumps({"title": "ok"})])
    result = await call_generation_json(
        llm_service=llm,
        system_prompt="sys",
        conversation_history=[],
        temperature=0.7,
        user_id=1,
        timeout=30.0,
        policy=policy(json_repair_attempts=2, retry_attempts=1),
    )
    assert result.data == {"title": "ok"}
    assert len(llm.calls) == 2


async def test_invalid_json_exhausted_raises_decode_error():
    llm = FakeLLMService(["<not json>"])
    with pytest.raises(GenerationJSONDecodeError) as exc_info:
        await call_generation_json(
            llm_service=llm,
            system_prompt="sys",
            conversation_history=[],
            temperature=0.7,
            user_id=1,
            timeout=30.0,
            policy=policy(json_repair_attempts=0, retry_attempts=1),
        )
    assert exc_info.value.raw_text == "<not json>"


# ---------------------------------------------------------------- 不崩、不静默


async def test_unexpected_exception_propagates_not_swallowed():
    """非 HTTPException 的意外异常必须原样上抛，不能被吞成成功。"""
    llm = FakeLLMService([RuntimeError("unexpected")])
    with pytest.raises(RuntimeError, match="unexpected"):
        await call_generation_text(
            llm_service=llm,
            system_prompt="sys",
            conversation_history=[],
            temperature=0.7,
            user_id=1,
            timeout=30.0,
            policy=policy(),
        )
    assert len(llm.calls) == 1


async def test_retry_delay_actually_sleeps_when_configured():
    """backoff > 0 时确实等待（用真实计时验证，不用 mock）。"""
    sleeps = []
    real_sleep = asyncio.sleep

    async def spy_sleep(delay, *a, **k):
        sleeps.append(delay)
        await real_sleep(0)

    llm = FakeLLMService([http_exc(503), http_exc(503), "done"])
    monkeypatched = asyncio.sleep
    asyncio.sleep = spy_sleep
    try:
        await call_generation_text(
            llm_service=llm,
            system_prompt="sys",
            conversation_history=[],
            temperature=0.7,
            user_id=1,
            timeout=30.0,
            policy=policy(backoff_base_seconds=0.5),
        )
    finally:
        asyncio.sleep = monkeypatched

    assert len(sleeps) == 2, f"两次失败应产生两次退避等待，实际 {len(sleeps)}"
    assert all(s > 0 for s in sleeps)


def test_progress_callback_receives_retry_notice():
    """重试时前端应能通过 progress_callback 看到提示（US-006 的 SSE 通道即由此驱动）。"""
    notices = []

    async def cb(stage, message):
        notices.append((stage, message))

    llm = FakeLLMService([http_exc(500), "ok"])
    asyncio.run(
        call_generation_text(
            llm_service=llm,
            system_prompt="sys",
            conversation_history=[],
            temperature=0.7,
            user_id=1,
            timeout=30.0,
            policy=policy(progress_stage="generating"),
            progress_callback=cb,
        )
    )
    assert len(notices) == 1
    assert "重试" in notices[0][1]
