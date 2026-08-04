# -*- coding: utf-8 -*-
import pytest

from app.services.llm_service import LLMService


class _FakeStreamClient:
    def __init__(self, parts):
        self._parts = parts

    async def stream_chat(self, **kwargs):
        for part in self._parts:
            yield part


async def _async_noop(*_a, **_k):
    return None


@pytest.mark.anyio
async def test_stream_single_model_falls_back_to_reasoning_content():
    service = object.__new__(LLMService)
    service._wait_for_provider_cooldown = _async_noop
    client = _FakeStreamClient(
        [
            {"content": "", "reasoning_content": "先想一步。", "finish_reason": None},
            {"content": "", "reasoning_content": "最终答案：今天天气很好。", "finish_reason": "stop"},
        ]
    )
    text, finish = await service._stream_single_model(
        client=client,
        chat_messages=[],
        model_name="deepseek-ai/DeepSeek-V4-Pro",
        provider_key="test",
        temperature=0.2,
        user_id=1,
        timeout=30,
        response_format=None,
        max_tokens=64,
        top_p=None,
        prompt_cache_key=None,
        retry_same_model_once=False,
    )
    assert "今天天气很好" in text
    assert finish == "stop"


@pytest.mark.anyio
async def test_stream_single_model_prefers_content_when_present():
    service = object.__new__(LLMService)
    service._wait_for_provider_cooldown = _async_noop
    client = _FakeStreamClient(
        [
            {"content": "正文结果", "reasoning_content": "不该覆盖", "finish_reason": "stop"},
        ]
    )
    text, finish = await service._stream_single_model(
        client=client,
        chat_messages=[],
        model_name="m",
        provider_key="test",
        temperature=0.2,
        user_id=1,
        timeout=30,
        response_format=None,
        max_tokens=64,
        top_p=None,
        prompt_cache_key=None,
        retry_same_model_once=False,
    )
    assert text == "正文结果"
    assert finish == "stop"
