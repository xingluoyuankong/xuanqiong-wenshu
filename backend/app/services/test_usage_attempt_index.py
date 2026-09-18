import httpx
import pytest
from unittest.mock import MagicMock
from openai import RateLimitError

from app.services.llm_service import LLMService
from app.utils.llm_tool import ChatMessage


@pytest.mark.asyncio
async def test_provider_retry_records_successful_physical_attempt_index_two(monkeypatch):
    service = LLMService.__new__(LLMService)
    calls = 0

    async def stream_chat(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RateLimitError(
                "rate limited",
                response=httpx.Response(429, request=httpx.Request("POST", "https://provider.test")),
                body=None,
            )
        yield {"usage": {"prompt_tokens": 10, "completion_tokens": 5}}
        yield {"content": "retry success", "finish_reason": "stop"}

    client = MagicMock()
    client.stream_chat = stream_chat
    monkeypatch.setattr(service, "_wait_for_provider_cooldown", lambda key: _async_noop())
    monkeypatch.setattr(service, "_compute_rate_limit_backoff_seconds", lambda exc, retry_index: 0.0)
    monkeypatch.setattr(service, "_register_provider_cooldown", lambda key, seconds: None)

    usage_sink = {}
    text, finish = await service._stream_single_model(
        client=client,
        chat_messages=[ChatMessage(role="user", content="hello")],
        model_name="GLM-5.3-Flash",
        provider_key="provider:test",
        temperature=0.2,
        user_id=1,
        timeout=30,
        response_format=None,
        retry_same_model_once=True,
        usage_sink=usage_sink,
    )

    assert calls == 2
    assert text == "retry success"
    assert finish == "stop"
    assert usage_sink["attempt_index"] == 2
    assert usage_sink["usage"]["prompt_tokens"] == 10


async def _async_noop():
    return None
