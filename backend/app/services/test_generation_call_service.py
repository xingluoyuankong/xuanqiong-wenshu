import pytest
from fastapi import HTTPException

from app.api.routers.optimizer import _build_continuity_contract, _continuity_guard_failure
from app.services.generation_call_service import (
    GenerationCallPolicy,
    call_generation_json,
    call_generation_text,
)


class _FakeLLMService:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def get_llm_response(self, **kwargs):
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.mark.anyio
async def test_call_generation_json_repairs_malformed_json_once():
    llm = _FakeLLMService(
        [
            "不是 JSON",
            '{"title": "暗潮入城", "summary": "主角追查线索，发现盟友隐瞒关键消息，章尾留下追兵逼近的钩子。"}',
        ]
    )

    result = await call_generation_json(
        llm_service=llm,
        system_prompt="system",
        conversation_history=[{"role": "user", "content": "rewrite"}],
        temperature=0.3,
        user_id=1,
        timeout=30.0,
        policy=GenerationCallPolicy(stage_label="章节大纲重写", json_repair_attempts=1),
    )

    assert result.data["title"] == "暗潮入城"
    assert len(llm.calls) == 2
    assert "上一条回复不是可解析的 JSON 对象" in llm.calls[1]["conversation_history"][-1]["content"]


@pytest.mark.anyio
async def test_call_generation_text_retries_retryable_http_exception():
    stages = []

    async def progress_callback(stage: str, message: str):
        stages.append((stage, message))

    retryable = HTTPException(status_code=503, detail={"retryable": True, "message": "overloaded"})
    llm = _FakeLLMService([retryable, "ok"])

    result = await call_generation_text(
        llm_service=llm,
        system_prompt="system",
        conversation_history=[{"role": "user", "content": "hello"}],
        temperature=0.3,
        user_id=1,
        timeout=30.0,
        policy=GenerationCallPolicy(stage_label="蓝图生成", retry_attempts=2),
        progress_callback=progress_callback,
    )

    assert result.text == "ok"
    assert len(llm.calls) == 2
    assert stages == [("generating", "蓝图生成遇到上游抖动，正在进行第 1/1 次重试")]


def test_continuity_guard_rejects_over_shrunk_optimization():
    original = "第一段。" * 700
    optimized = "只剩一个片段。" * 20

    reason = _continuity_guard_failure(original, optimized)

    assert reason is not None
    assert "shrank" in reason or "lost too much" in reason


def test_continuity_contract_includes_neighboring_outlines_and_hard_rules():
    class Obj:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    project = Obj(
        outlines=[
            Obj(chapter_number=1, title="旧局", summary="上一章钩子"),
            Obj(chapter_number=2, title="暗潮", summary="本章冲突"),
            Obj(chapter_number=3, title="追兵", summary="下一章承接"),
        ],
        chapters=[],
    )
    request = Obj(chapter_number=2, dimension="rhythm")

    contract = _build_continuity_contract(project, request, "开头" + "正文" * 200 + "结尾")

    assert contract["mode"] == "local_window_with_anchors_return_full_chapter"
    assert [item["chapter_number"] for item in contract["nearby_outlines"]] == [1, 2, 3]
    assert any("局部改动" in rule for rule in contract["hard_rules"])
    assert any("完整章节正文" in rule for rule in contract["hard_rules"])
