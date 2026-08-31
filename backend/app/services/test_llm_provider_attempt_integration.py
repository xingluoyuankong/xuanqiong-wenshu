from __future__ import annotations

import pytest

from app.agent.provider_attempt import ProviderAttemptLedger
from app.services.llm_service import LLMService
from app.services.generation_call_service import GenerationCallPolicy, call_generation_text


class _FakeClient:
    def __init__(self, *, api_key=None, base_url=None):
        self.api_key = api_key
        self.base_url = base_url

    async def stream_chat(self, **_kwargs):
        if getattr(self, "empty", False):
            if False:
                yield {}
            return
        yield {"content": "流式", "finish_reason": None}
        yield {"content": "回答", "finish_reason": "stop"}

    async def chat(self, **_kwargs):
        return {"content": "兜底回答", "finish_reason": "stop"}


@pytest.mark.asyncio
async def test_llm_visible_stream_records_attempt_through_service(monkeypatch):
    monkeypatch.setattr("app.services.llm_service.LLMClient", _FakeClient)
    service = LLMService(object())
    monkeypatch.setattr(
        service,
        "_resolve_llm_config",
        lambda _user_id, **_kwargs: _async_value({"api_key": "fixture", "base_url": "https://provider.fixture", "model": "fixture-model"}),
    )
    ledger = ProviderAttemptLedger(run_id="run-response")
    result = []
    async for delta in service.stream_visible_response(
        system_prompt="system",
        user_prompt="user",
        user_id=1,
        attempt_ledger=ledger,
        attempt_role="response",
    ):
        result.append(delta)
    assert "".join(result) == "流式回答"
    attempts = ledger.snapshot()["provider_attempts"]
    assert len(attempts) == 1
    assert attempts[0]["role"] == "response"
    assert attempts[0]["status"] == "succeeded"
    assert attempts[0]["first_token_at"]
    assert attempts[0]["output_digest"]


@pytest.mark.asyncio
async def test_llm_collect_records_empty_stream_and_non_stream_fallback(monkeypatch):
    class EmptyStreamClient(_FakeClient):
        async def stream_chat(self, **_kwargs):
            if False:
                yield {}
            return

    monkeypatch.setattr("app.services.llm_service.LLMClient", EmptyStreamClient)
    service = LLMService(object())
    monkeypatch.setattr(
        service,
        "_resolve_llm_config",
        lambda _user_id, **_kwargs: _async_value({"api_key": "fixture", "base_url": "https://provider.fixture", "model": "fixture-model"}),
    )
    ledger = ProviderAttemptLedger(run_id="run-fallback")
    result = await service.get_llm_response(
        "system",
        [{"role": "user", "content": "user"}],
        user_id=1,
        response_format=None,
        retry_same_model_once=False,
        attempt_ledger=ledger,
        attempt_role="quality",
    )
    assert result == "兜底回答"
    attempts = ledger.snapshot()["provider_attempts"]
    assert len(attempts) == 2
    assert attempts[0]["role"] == "quality"
    assert attempts[0]["error_category"] == "EMPTY_STREAM"
    assert attempts[1]["role"] == "quality.fallback"
    assert attempts[1]["status"] == "succeeded"
    assert attempts[1]["fallback_from_attempt"] == 1


async def _async_value(value):
    return value


@pytest.mark.asyncio
async def test_quality_generation_policy_propagates_attempt_ledger_and_role():
    observed = {}

    class QualityLLM:
        async def get_llm_response(self, **kwargs):
            observed.update(kwargs)
            ledger = kwargs["attempt_ledger"]
            attempt = ledger.begin(role=kwargs["attempt_role"], provider_ref="quality-fixture", model_ref="quality-model")
            ledger.mark_first_token(attempt.attempt_id)
            ledger.finish(attempt.attempt_id, output="quality-result")
            return "quality-result"

    result = await call_generation_text(
        llm_service=QualityLLM(),
        system_prompt="quality",
        conversation_history=[{"role": "user", "content": "inspect"}],
        temperature=0.2,
        user_id=1,
        timeout=10,
        policy=GenerationCallPolicy(retry_attempts=1, response_format=None, stage_label="quality-check", attempt_role="quality"),
    )
    assert result.text == "quality-result"
    assert observed["attempt_role"] == "quality"
    assert result.provider_attempts["provider_attempts"][0]["role"] == "quality"
    assert result.provider_attempts["provider_attempts"][0]["status"] == "succeeded"
