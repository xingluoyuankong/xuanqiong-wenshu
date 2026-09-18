"""
US-010: 预算闭包 —— LLM 出口自动记账 + 逻辑调用/物理尝试归因

此前 TokenBudgetService 只被手工 API 端点调用，生成链路引用数为 0，
导致预算数字与真实消耗无关。本测试验证新接入的自动记账链路：

  LLMClient 保留 usage -> LLMService 出口调用 record_llm_usage
    -> ContextVar 归因 (project/chapter/run/stage) -> token_usages 落库

并验证 US-010 的核心语义：逻辑调用 vs 物理尝试可区分。
"""

import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.usage_attribution_service import (  # noqa: E402
    current_usage_scope,
    estimate_tokens,
    extract_usage_tokens,
    record_llm_usage,
    update_usage_scope_chapter,
    usage_scope,
)

pytestmark = pytest.mark.asyncio


# ------------------------------------------------------------ token 解析


def test_extract_usage_from_object():
    class Usage:
        prompt_tokens = 100
        completion_tokens = 50

    assert extract_usage_tokens(Usage()) == {
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "total_tokens": 150,
    }


def test_extract_usage_from_dict():
    assert extract_usage_tokens({"prompt_tokens": 7, "completion_tokens": 3}) == {
        "prompt_tokens": 7,
        "completion_tokens": 3,
        "total_tokens": 10,
    }


def test_extract_usage_returns_none_when_absent():
    """Provider 没返回 usage 时必须明确返回 None，让上层走估算，而不是伪装成 0。"""
    assert extract_usage_tokens(None) is None
    assert extract_usage_tokens({}) is None


def test_estimate_tokens_chinese_and_ascii():
    assert estimate_tokens("") == 0
    zh = estimate_tokens("中文十个字左右")
    en = estimate_tokens("hello world this is a test")
    assert zh > 0 and en > 0


# ------------------------------------------------------------ 归因上下文


async def test_scope_is_isolated_between_tasks():
    """ContextVar 必须随 asyncio 任务隔离：并发候选任务不能串味。"""
    import asyncio

    seen = {}

    async def worker(name, pid):
        async with usage_scope(project_id=pid, run_id=name, stage="draft"):
            await asyncio.sleep(0.01)
            seen[name] = current_usage_scope().project_id

    await asyncio.gather(worker("a", "proj-A"), worker("b", "proj-B"))
    assert seen == {"a": "proj-A", "b": "proj-B"}


async def test_scope_cleared_after_block():
    assert current_usage_scope() is None
    async with usage_scope(project_id="p", run_id="r", stage="draft"):
        assert current_usage_scope().project_id == "p"
    assert current_usage_scope() is None


async def test_chapter_id_backfill():
    async with usage_scope(project_id="p", run_id="r", stage="draft") as scope:
        assert scope.chapter_id is None
        update_usage_scope_chapter(42)
        assert current_usage_scope().chapter_id == 42


# ------------------------------------------------------------ 自动记账


class RecordingService:
    """记录 record_usage 调用的替身。"""

    calls = []

    def __init__(self, session):
        pass

    async def record_usage(self, **kwargs):
        RecordingService.calls.append(kwargs)
        return kwargs


@pytest.fixture(autouse=True)
def _patch_service(monkeypatch):
    RecordingService.calls = []
    import app.services.token_budget_service as mod

    monkeypatch.setattr(mod, "TokenBudgetService", RecordingService)
    yield


async def test_no_record_without_scope():
    """没有归因上下文（如后台维护调用）不得记账。"""
    await record_llm_usage(None, model_name="m", usage={"prompt_tokens": 10, "completion_tokens": 5})
    assert RecordingService.calls == []


async def test_records_provider_reported_usage():
    async with usage_scope(project_id="p1", run_id="run-1", stage="draft", module="content"):
        update_usage_scope_chapter(7)
        await record_llm_usage(
            None,
            model_name="GLM-5.3-Flash",
            usage={"prompt_tokens": 200, "completion_tokens": 100},
            prompt_text="irrelevant",
            completion_text="irrelevant",
        )
    assert len(RecordingService.calls) == 1
    call = RecordingService.calls[0]
    assert call["project_id"] == "p1"
    assert call["run_id"] == "run-1"
    assert call["stage"] == "draft"
    assert call["chapter_id"] == 7
    assert call["prompt_tokens"] == 200
    assert call["completion_tokens"] == 100
    assert call["tokens_used"] == 300
    assert call["is_estimated"] is False, "Provider 实际值不得标记为估算"


async def test_records_physical_attempt_index():
    async with usage_scope(project_id="p-attempt", run_id="run-attempt", stage="draft"):
        await record_llm_usage(
            None,
            model_name="m",
            usage={"prompt_tokens": 4, "completion_tokens": 6},
            attempt_index=2,
        )
    assert RecordingService.calls[-1]["attempt_index"] == 2


async def test_falls_back_to_estimate_and_flags_it():
    """Provider 未返回 usage 时必须估算，并如实标记 is_estimated=True。"""
    async with usage_scope(project_id="p2", run_id="run-2", stage="self_critique"):
        await record_llm_usage(
            None,
            model_name="m",
            usage=None,
            prompt_text="这是一个提示词" * 10,
            completion_text="这是生成内容" * 20,
        )
    assert len(RecordingService.calls) == 1
    call = RecordingService.calls[0]
    assert call["is_estimated"] is True, "估算值必须被标记，不得冒充实际值"
    assert call["tokens_used"] > 0
    assert call["stage"] == "self_critique"


async def test_recording_failure_does_not_propagate():
    """记账失败绝不能中断生成 —— 这是硬要求。"""
    import app.services.token_budget_service as mod

    class BoomService:
        def __init__(self, session):
            pass

        async def record_usage(self, **kwargs):
            raise RuntimeError("db down")

    original = mod.TokenBudgetService
    mod.TokenBudgetService = BoomService
    try:
        async with usage_scope(project_id="p3", run_id="run-3", stage="draft"):
            # 不应抛出
            await record_llm_usage(None, model_name="m", usage={"prompt_tokens": 1, "completion_tokens": 1})
    finally:
        mod.TokenBudgetService = original
