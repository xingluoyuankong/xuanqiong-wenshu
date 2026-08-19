import asyncio
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import pytest
from fastapi import HTTPException

from app.api.routers.optimizer import _build_continuity_contract, _continuity_guard_failure, _optimizer_response_schema
from app.services.generation_call_service import (
    GenerationCallPolicy,
    build_response_format_payload,
    call_generation_json,
    call_generation_text,
    classify_provider_error,
    estimate_generation_token_count,
    parse_llm_json_value,
    resolve_retry_delay_seconds,
    validate_json_schema_subset,
)
from app.services.llm_service import LLMService


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
        policy=GenerationCallPolicy(stage_label="蓝图生成", retry_attempts=2, backoff_base_seconds=0.01),
        progress_callback=progress_callback,
    )

    assert result.text == "ok"
    assert len(llm.calls) == 2
    assert result.provider_error_type == "provider_jitter"
    assert result.estimated_total_tokens > 0
    assert stages == [("generating", "蓝图生成遇到上游抖动，正在进行第 1/1 次重试")]


@pytest.mark.anyio
async def test_call_generation_text_reduces_max_tokens_after_provider_token_limit_rejection():
    stages = []

    async def progress_callback(stage: str, message: str):
        stages.append((stage, message))

    token_limit_error = HTTPException(
        status_code=400,
        detail={"message": "max_tokens is too high for this model output token limit"},
    )
    llm = _FakeLLMService([token_limit_error, "ok"])

    result = await call_generation_text(
        llm_service=llm,
        system_prompt="system",
        conversation_history=[{"role": "user", "content": "long chapter"}],
        temperature=0.3,
        user_id=1,
        timeout=30.0,
        policy=GenerationCallPolicy(
            stage_label="正文首稿生成",
            retry_attempts=2,
            max_tokens=24000,
            backoff_base_seconds=0.01,
        ),
        progress_callback=progress_callback,
    )

    assert result.text == "ok"
    assert len(llm.calls) == 2
    assert llm.calls[0]["max_tokens"] == 24000
    assert 12000 <= llm.calls[1]["max_tokens"] < 24000
    assert result.provider_error_type == "output_token_limit"
    assert result.effective_max_tokens == llm.calls[1]["max_tokens"]
    assert result.estimated_output_tokens > 0
    assert stages and stages[0][0] == "generating"


@pytest.mark.anyio
async def test_call_generation_text_does_not_retry_timeout_by_default():
    stages = []

    class SlowLLMService(_FakeLLMService):
        async def get_llm_response(self, **kwargs):
            self.calls.append(kwargs)
            await asyncio.sleep(1)
            return "late"

    async def progress_callback(stage: str, message: str):
        stages.append((stage, message))

    llm = SlowLLMService([])

    with pytest.raises(HTTPException) as exc_info:
        await call_generation_text(
            llm_service=llm,
            system_prompt="system",
            conversation_history=[{"role": "user", "content": "long chapter"}],
            temperature=0.3,
            user_id=1,
            timeout=1.0,
            policy=GenerationCallPolicy(
                stage_label="长章正文候选",
                progress_stage="generate_variants",
                retry_attempts=2,
                response_format=None,
                max_tokens=20000,
                heartbeat_interval_seconds=0.01,
                soft_timeout_seconds=0.03,
                backoff_base_seconds=0.01,
            ),
            progress_callback=progress_callback,
        )

    assert exc_info.value.status_code == 504
    assert len(llm.calls) == 1
    assert llm.calls[0]["max_tokens"] == 20000
    assert not any("重试" in message for _, message in stages)


@pytest.mark.anyio
async def test_call_generation_text_retries_timeout_only_when_explicitly_enabled():
    class SlowThenFastLLMService(_FakeLLMService):
        async def get_llm_response(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                await asyncio.sleep(1)
            return "ok"

    llm = SlowThenFastLLMService([])
    result = await call_generation_text(
        llm_service=llm,
        system_prompt="system",
        conversation_history=[{"role": "user", "content": "long chapter"}],
        temperature=0.3,
        user_id=1,
        timeout=1.0,
        policy=GenerationCallPolicy(
            stage_label="长章正文候选",
            retry_attempts=2,
            retry_on_timeout=True,
            response_format=None,
            max_tokens=20000,
            heartbeat_interval_seconds=None,
            soft_timeout_seconds=0.03,
            backoff_base_seconds=0.01,
        ),
    )

    assert result.text == "ok"
    assert len(llm.calls) == 2
    assert 12000 <= llm.calls[1]["max_tokens"] < 20000


def test_estimate_generation_token_count_handles_cjk_and_ascii():
    assert estimate_generation_token_count("") == 0
    assert estimate_generation_token_count("hello world " * 10) >= 20
    assert estimate_generation_token_count("玄穹文枢正在生成更长的章节") >= 8


def test_deepseek_free_model_capability_is_narrowly_scoped():
    assert LLMService.is_deepseek_free_model("deepseek-v4-flash-free") is True
    assert LLMService.is_deepseek_free_model("deepseek-v4-flash-0731") is False
    assert LLMService.is_deepseek_free_model("glm-5.2") is False


def test_retry_delay_respects_retry_after_and_cap():
    exc = HTTPException(
        status_code=429,
        detail={"retryable": True, "retry_after_seconds": 30},
    )
    policy = GenerationCallPolicy(stage_label="provider", backoff_max_seconds=8)

    assert resolve_retry_delay_seconds(exc, 1, policy) == 8


def test_retry_delay_accepts_http_date_retry_after_header():
    retry_after = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=45), usegmt=True)
    exc = HTTPException(
        status_code=429,
        detail={"retryable": True},
        headers={"Retry-After": retry_after},
    )
    policy = GenerationCallPolicy(stage_label="provider", backoff_max_seconds=8)

    assert 0 < resolve_retry_delay_seconds(exc, 1, policy) <= 8


def test_build_response_format_payload_prefers_json_schema():
    schema = {
        "type": "object",
        "required": ["title"],
        "properties": {"title": {"type": "string"}},
    }
    policy = GenerationCallPolicy(
        stage_label="章节任务",
        response_format="json_object",
        json_schema=schema,
        json_schema_name="chapter_mission",
    )

    payload = build_response_format_payload(policy)

    assert payload["type"] == "json_schema"
    assert payload["json_schema"]["name"] == "chapter_mission"
    assert payload["json_schema"]["schema"] == schema
    assert payload["json_schema"]["strict"] is True


@pytest.mark.anyio
async def test_call_generation_text_passes_prompt_cache_key_when_configured():
    llm = _FakeLLMService(["ok"])

    result = await call_generation_text(
        llm_service=llm,
        system_prompt="stable story bible prefix",
        conversation_history=[{"role": "user", "content": "chapter task"}],
        temperature=0.3,
        user_id=1,
        timeout=30.0,
        policy=GenerationCallPolicy(
            stage_label="chapter draft",
            response_format=None,
            prompt_cache_key="project:p1:writer",
        ),
    )

    assert result.text == "ok"
    assert llm.calls[0]["prompt_cache_key"] == "project:p1:writer"


@pytest.mark.anyio
async def test_call_generation_json_uses_schema_and_repairs_local_schema_failure():
    llm = _FakeLLMService(
        [
            '{"summary": "缺标题"}',
            '{"title": "暗潮入城", "summary": "主角追查线索。"}',
        ]
    )
    schema = {
        "type": "object",
        "required": ["title", "summary"],
        "properties": {
            "title": {"type": "string"},
            "summary": {"type": "string"},
        },
    }

    result = await call_generation_json(
        llm_service=llm,
        system_prompt="system",
        conversation_history=[{"role": "user", "content": "outline"}],
        temperature=0.3,
        user_id=1,
        timeout=30.0,
        policy=GenerationCallPolicy(
            stage_label="章节大纲",
            json_schema=schema,
            json_schema_name="chapter_outline",
            json_repair_attempts=1,
        ),
    )

    assert result.data["title"] == "暗潮入城"
    assert result.schema_validated is True
    assert llm.calls[0]["response_format"]["type"] == "json_schema"
    assert "必须满足本地 schema" in llm.calls[1]["conversation_history"][-1]["content"]


@pytest.mark.anyio
async def test_call_generation_text_downgrades_schema_when_provider_rejects_structured_outputs():
    stages = []

    async def progress_callback(stage: str, message: str):
        stages.append((stage, message))

    unsupported = HTTPException(
        status_code=400,
        detail={"message": "response_format json_schema is not supported by this model"},
    )
    llm = _FakeLLMService([unsupported, '{"title": "ok"}'])

    result = await call_generation_text(
        llm_service=llm,
        system_prompt="system",
        conversation_history=[{"role": "user", "content": "outline"}],
        temperature=0.3,
        user_id=1,
        timeout=30.0,
        policy=GenerationCallPolicy(
            stage_label="蓝图结构化输出",
            retry_attempts=2,
            backoff_base_seconds=0.01,
            json_schema={
                "type": "object",
                "required": ["title"],
                "properties": {"title": {"type": "string"}},
            },
        ),
        progress_callback=progress_callback,
    )

    assert result.text == '{"title": "ok"}'
    assert llm.calls[0]["response_format"]["type"] == "json_schema"
    assert llm.calls[1]["response_format"] == "json_object"
    assert stages == [("generating", "蓝图结构化输出 的结构化 schema 被当前 Provider 拒绝，已回退到 JSON 模式重试")]


def test_classify_provider_error_for_runtime_logs():
    assert classify_provider_error(HTTPException(status_code=429, detail={"message": "rate limit"})) == "rate_limit"
    assert classify_provider_error(HTTPException(status_code=504, detail={"message": "timeout"})) == "timeout"
    assert classify_provider_error(HTTPException(status_code=400, detail={"message": "max_tokens too high"})) == "output_token_limit"


def test_validate_json_schema_subset_rejects_bool_for_numeric_contract_fields():
    schema = {
        "type": "object",
        "required": ["word_budget", "score"],
        "properties": {
            "word_budget": {"type": "integer"},
            "score": {"type": "number"},
        },
    }

    errors = validate_json_schema_subset({"word_budget": True, "score": False}, schema)

    assert "$.word_budget must be integer" in errors
    assert "$.score must be number" in errors


def test_optimizer_response_schema_requires_content_and_notes():
    schema = _optimizer_response_schema()

    assert schema["required"] == ["optimized_content", "optimization_notes"]
    assert not validate_json_schema_subset({"optimized_content": "正文", "optimization_notes": "局部补丁"}, schema)
    assert "$.optimization_notes is required" in validate_json_schema_subset({"optimized_content": "正文"}, schema)


def test_parse_llm_json_value_extracts_array_payload_from_wrapped_text():
    data, normalized = parse_llm_json_value(
        "蓝图如下：\n```json\n[{\"chapter_number\": 1, \"chapter_function\": \"buildup\"}]\n```"
    )

    assert data == [{"chapter_number": 1, "chapter_function": "buildup"}]
    assert normalized.startswith("[")


def test_continuity_guard_rejects_over_shrunk_optimization():
    original = "第一段。" * 700
    optimized = "只剩一个片段。" * 20

    reason = _continuity_guard_failure(original, optimized)

    assert reason is not None
    assert "shrank" in reason or "lost too much" in reason


def test_continuity_guard_rejects_optimizer_when_both_anchors_disappear():
    original = (
        "林七攥着半枚印章站在旧码头门前，上一章留下的脚步声已经逼到背后。"
        + "他必须在沈舟开口前判断谁在撒谎。"
        + "审问推进了整整一夜，账册、盐渍编号、顾棠的回归都把旧案推向更深处。" * 16
        + "章尾沈舟忽然说，真正的送信人就在门外，林七听见门栓被人从外侧推开。"
    )
    optimized = (
        "远山在风里显得苍白，主角独自思考命运。"
        + "黄昏像很长的梦，所有事情都变得朦胧而诗意。" * 40
        + "他决定明天再继续。"
    )

    reason = _continuity_guard_failure(original, optimized)

    assert reason == "optimized content lost both opening and ending continuity anchors"


def test_continuity_guard_rejects_optimizer_when_critical_motifs_disappear():
    original = (
        "雨城水楼的茶气很稳，沈砚把账页一册册排开。" * 20
        + "沈砚在水楼账册里闻到药渣味，惊蛰后三日的空账指向旧南渠。"
        + "顾栖川提醒他：有些账见了地，才真会死人。"
        + "他把封签重新压好，知道这一夜不会轻易结束。" * 20
    )
    optimized = (
        "雨城水楼的茶气很稳，沈砚把账页一册册排开。" * 20
        + "沈砚在水楼里看见旧账有异，顾栖川提醒他继续追查。"
        + "雨声落在檐下，事情还没有结束。"
        + "他把封签重新压好，知道这一夜不会轻易结束。" * 20
    )

    reason = _continuity_guard_failure(original, optimized)

    assert reason is not None
    assert "critical continuity motifs" in reason
    assert "old_south_canal" in reason
    assert "medicine_trace" in reason


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
    assert contract["required_motif_groups"] == []
    assert any("局部改动" in rule for rule in contract["hard_rules"])
    assert any("完整章节正文" in rule for rule in contract["hard_rules"])
