import pytest
from fastapi import HTTPException

from app.services.generation_call_service import classify_provider_error, is_retryable_http_exception


def test_model_not_found_503_is_not_retryable():
    exc = HTTPException(
        status_code=503,
        detail={
            "code": "PROVIDER_MODEL_UNAVAILABLE",
            "message": "No available channel for model __test__",
            "retryable": False,
        },
    )
    assert classify_provider_error(exc) == "model_unavailable"
    assert is_retryable_http_exception(exc) is False


def test_raw_no_available_channel_text_is_classified():
    exc = HTTPException(status_code=503, detail="model_not_found: no available channel")
    assert classify_provider_error(exc) == "model_unavailable"
    assert is_retryable_http_exception(exc) is False


@pytest.mark.asyncio
async def test_llm_service_model_unavailable_does_not_retry(monkeypatch):
    import httpx
    from openai import InternalServerError
    from unittest.mock import MagicMock
    from app.services.llm_service import LLMService
    from app.utils.llm_tool import ChatMessage

    service = LLMService.__new__(LLMService)
    calls = 0

    async def stream_chat(**kwargs):
        nonlocal calls
        calls += 1
        response = httpx.Response(
            503,
            request=httpx.Request("POST", "https://provider.test"),
            json={"error": {"code": "model_not_found", "message": "No available channel"}},
        )
        raise InternalServerError("No available channel", response=response, body=response.json())
        yield  # pragma: no cover

    client = MagicMock()
    client.stream_chat = stream_chat
    monkeypatch.setattr(service, "_wait_for_provider_cooldown", lambda key: _noop())
    monkeypatch.setattr(service, "_register_provider_cooldown", lambda key, seconds: None)

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await service._stream_single_model(
            client=client,
            chat_messages=[ChatMessage(role="user", content="probe")],
            model_name="__missing__",
            provider_key="provider:test",
            temperature=0.1,
            user_id=1,
            timeout=10,
            response_format=None,
            retry_same_model_once=True,
            usage_sink={},
        )
    assert calls == 1
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["code"] == "PROVIDER_MODEL_UNAVAILABLE"
    assert exc_info.value.detail["retryable"] is False


async def _noop():
    return None
