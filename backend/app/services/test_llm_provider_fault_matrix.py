from __future__ import annotations

import asyncio

import httpx
import pytest

from app.agent.provider_attempt import ProviderAttemptLedger
from app.services import llm_service as llm_module
from app.services.llm_service import LLMService


async def _config(_user_id, **_kwargs):
    return {"api_key": "fixture", "base_url": "https://provider.fixture", "model": "fixture-model"}


class _ErrorStreamClient:
    mode = "rate"

    def __init__(self, **_kwargs):
        pass

    async def stream_chat(self, **_kwargs):
        if self.mode == "rate":
            raise _RateLimitFixture("rate limit fixture")
        if self.mode == "server":
            raise _ServerFixture("503 fixture")
        if self.mode == "timeout":
            raise asyncio.TimeoutError("timeout fixture")
        if self.mode == "disconnect":
            raise httpx.ReadError("disconnect fixture")
        if self.mode == "cancel":
            raise asyncio.CancelledError()
        if False:
            yield {}

    async def chat(self, **_kwargs):
        return {"content": "fallback", "finish_reason": "stop"}


class _RateLimitFixture(Exception):
    status_code = 429


class _ServerFixture(Exception):
    status_code = 503


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "exception_name", "category"),
    [
        ("rate", "RateLimitError", "RATE_LIMIT"),
        ("timeout", "APITimeoutError", "TIMEOUT"),
        ("disconnect", "APIConnectionError", "NETWORK_DISCONNECT"),
    ],
)
async def test_llm_service_stream_failures_leave_classified_attempt(monkeypatch, mode, exception_name, category):
    _ErrorStreamClient.mode = mode
    monkeypatch.setattr(llm_module, "LLMClient", _ErrorStreamClient)
    if mode == "rate":
        monkeypatch.setattr(llm_module, "RateLimitError", _RateLimitFixture)
    if mode == "timeout":
        monkeypatch.setattr(llm_module, "APITimeoutError", asyncio.TimeoutError)
    if mode == "disconnect":
        monkeypatch.setattr(llm_module, "APIConnectionError", httpx.ReadError)
    monkeypatch.setattr(llm_module.asyncio, "sleep", _no_sleep)
    service = LLMService(object())
    monkeypatch.setattr(service, "_resolve_llm_config", _config)
    ledger = ProviderAttemptLedger(run_id=f"run-{mode}")
    if mode == "rate":
        with pytest.raises(Exception):
            await service.get_llm_response(
                "system",
                [{"role": "user", "content": "user"}],
                user_id=1,
                response_format=None,
                retry_same_model_once=False,
                allow_non_stream_fallback=False,
                attempt_ledger=ledger,
                attempt_role="quality",
            )
    else:
        result = await service.get_llm_response(
            "system",
            [{"role": "user", "content": "user"}],
            user_id=1,
            response_format=None,
            retry_same_model_once=False,
            allow_non_stream_fallback=True,
            attempt_ledger=ledger,
            attempt_role="quality",
        )
        assert result == "fallback"
    attempts = ledger.snapshot()["provider_attempts"]
    assert attempts[0]["error_category"] == category
    assert attempts[0]["role"] == "quality"
    if mode != "rate":
        assert attempts[1]["role"] == "quality.fallback"
        assert attempts[1]["fallback_from_attempt"] == attempts[0]["attempt"]


@pytest.mark.asyncio
async def test_llm_service_503_records_failed_primary_and_linked_fallback(monkeypatch):
    _ErrorStreamClient.mode = "server"
    monkeypatch.setattr(llm_module, "LLMClient", _ErrorStreamClient)
    monkeypatch.setattr(llm_module, "InternalServerError", _ServerFixture)
    monkeypatch.setattr(llm_module.asyncio, "sleep", _no_sleep)
    service = LLMService(object())
    monkeypatch.setattr(service, "_resolve_llm_config", _config)
    ledger = ProviderAttemptLedger(run_id="run-503")
    result = await service.get_llm_response(
        "system",
        [{"role": "user", "content": "user"}],
        user_id=1,
        response_format=None,
        retry_same_model_once=False,
        attempt_ledger=ledger,
        attempt_role="planner",
    )
    assert result == "fallback"
    attempts = ledger.snapshot()["provider_attempts"]
    assert len(attempts) == 2
    assert attempts[0]["error_category"] == "TRANSIENT_5XX"
    assert attempts[1]["role"] == "planner.fallback"
    assert attempts[1]["fallback_from_attempt"] == attempts[0]["attempt"]
    assert attempts[1]["status"] == "succeeded"


@pytest.mark.asyncio
async def test_llm_service_cancel_records_cancelled_attempt(monkeypatch):
    _ErrorStreamClient.mode = "cancel"
    monkeypatch.setattr(llm_module, "LLMClient", _ErrorStreamClient)
    service = LLMService(object())
    monkeypatch.setattr(service, "_resolve_llm_config", _config)
    ledger = ProviderAttemptLedger(run_id="run-cancel")
    with pytest.raises(asyncio.CancelledError):
        async for _ in service.stream_visible_response(
            system_prompt="system",
            user_prompt="user",
            user_id=1,
            attempt_ledger=ledger,
            attempt_role="response",
        ):
            pass
    attempt = ledger.snapshot()["provider_attempts"][0]
    assert attempt["error_category"] == "CANCELLED"
    assert attempt["cancel_observed"] is True


async def _no_sleep(_seconds):
    return None


@pytest.mark.asyncio
async def test_llm_service_retry_creates_second_attempt_with_retry_index(monkeypatch):
    class RetryClient(_ErrorStreamClient):
        calls = 0
        async def stream_chat(self, **_kwargs):
            type(self).calls += 1
            if type(self).calls == 1:
                raise _ServerFixture("retry fixture")
            yield {"content": "retry-success", "finish_reason": "stop"}

    monkeypatch.setattr(llm_module, "LLMClient", RetryClient)
    monkeypatch.setattr(llm_module, "InternalServerError", _ServerFixture)
    monkeypatch.setattr(llm_module.asyncio, "sleep", _no_sleep)
    service = LLMService(object())
    monkeypatch.setattr(service, "_resolve_llm_config", _config)
    ledger = ProviderAttemptLedger(run_id="run-retry")
    result = await service.get_llm_response(
        "system", [{"role": "user", "content": "user"}], user_id=1, response_format=None,
        retry_same_model_once=True, allow_non_stream_fallback=False, attempt_ledger=ledger, attempt_role="writer"
    )
    assert result == "retry-success"
    attempts = ledger.snapshot()["provider_attempts"]
    assert len(attempts) == 2
    assert attempts[0]["error_category"] == "TRANSIENT_5XX"
    assert attempts[1]["retry_index"] == 1
    assert attempts[1]["status"] == "succeeded"


@pytest.mark.asyncio
async def test_llm_service_all_failed_keeps_primary_and_fallback_attempts(monkeypatch):
    class AllFailedClient(_ErrorStreamClient):
        async def stream_chat(self, **_kwargs):
            raise httpx.ReadError("primary disconnected")
            if False:
                yield {}

        async def chat(self, **_kwargs):
            raise httpx.ReadError("fallback disconnected")

    monkeypatch.setattr(llm_module, "LLMClient", AllFailedClient)
    monkeypatch.setattr(llm_module.asyncio, "sleep", _no_sleep)
    service = LLMService(object())
    monkeypatch.setattr(service, "_resolve_llm_config", _config)
    ledger = ProviderAttemptLedger(run_id="run-all-failed")
    with pytest.raises(Exception):
        await service.get_llm_response(
            "system", [{"role": "user", "content": "user"}], user_id=1, response_format=None,
            retry_same_model_once=False, attempt_ledger=ledger, attempt_role="response"
        )
    attempts = ledger.snapshot()["provider_attempts"]
    assert len(attempts) == 2
    assert attempts[0]["error_category"] == "NETWORK_DISCONNECT"
    assert attempts[1]["role"] == "response.fallback"
    assert attempts[1]["fallback_from_attempt"] == attempts[0]["attempt"]
    assert attempts[1]["error_category"] == "NETWORK_DISCONNECT"

