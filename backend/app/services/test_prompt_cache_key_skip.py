from types import SimpleNamespace

import pytest

from app.services.llm_service import LLMService
from app.utils.llm_tool import ChatMessage, LLMClient


def test_prompt_cache_key_is_removed_only_for_unsupported_gateway():
    payload = {"model": "m", "messages": [], "prompt_cache_key": "project:p1"}
    unsupported = LLMClient._sanitize_chat_payload(
        payload, base_url="https://api.xzxyuan.ccwu.cc/v1"
    )
    local = LLMClient._sanitize_chat_payload(
        payload, base_url="http://127.0.0.1:8317/v1"
    )
    assert "prompt_cache_key" not in unsupported
    assert local["prompt_cache_key"] == "project:p1"
    assert LLMService._is_free_compatible_gateway("https://api.xzxyuan.ccwu.cc/v1") is True
    assert LLMService._is_free_compatible_gateway("http://127.0.0.1:8317/v1") is False


@pytest.mark.asyncio
async def test_formal_stream_and_non_stream_requests_both_use_payload_sanitizer():
    calls = []

    class _Stream:
        def __init__(self, chunks):
            self.chunks = chunks

        def __aiter__(self):
            return self._iterate()

        async def _iterate(self):
            for chunk in self.chunks:
                yield chunk

    class _Completions:
        async def create(self, **payload):
            calls.append(payload)
            if payload["stream"]:
                return _Stream([
                    SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                delta=SimpleNamespace(content="正文", reasoning_content=None),
                                finish_reason="stop",
                            )
                        ]
                    )
                ])
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="非流式正文"),
                        finish_reason="stop",
                    )
                ]
            )

    client = object.__new__(LLMClient)
    client._base_url = "https://api.xzxyuan.ccwu.cc/v1"
    client._client = SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))
    messages = [ChatMessage(role="user", content="test")]

    streamed = [
        part
        async for part in client.stream_chat(
            messages=messages,
            model="m",
            prompt_cache_key="project:p1:writer",
            top_p=None,
        )
    ]
    non_streamed = await client.chat(
        messages=messages,
        model="m",
        prompt_cache_key="project:p1:writer",
        top_p=None,
    )

    assert streamed[0]["content"] == "正文"
    assert non_streamed["content"] == "非流式正文"
    assert len(calls) == 2
    assert all("prompt_cache_key" not in payload for payload in calls)
    assert all(value is not None for payload in calls for value in payload.values())


@pytest.mark.asyncio
async def test_low_level_calls_use_project_deepseek_default(monkeypatch):
    calls = []

    class _Stream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    class _Completions:
        async def create(self, **payload):
            calls.append(payload)
            if payload["stream"]:
                return _Stream()
            return SimpleNamespace(choices=[])

    monkeypatch.delenv("OPENAI_MODEL_NAME", raising=False)
    monkeypatch.delenv("MODEL", raising=False)
    # 隔离测试默认值，避免当前工作区 .env 的生产模型改变低层默认模型断言。
    monkeypatch.setattr(
        "app.utils.llm_tool.get_settings",
        lambda: SimpleNamespace(openai_model_name="deepseek-v4-flash-free"),
    )
    client = object.__new__(LLMClient)
    client._base_url = "https://api.example.test/v1"
    client._client = SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))
    messages = [ChatMessage(role="user", content="test")]

    streamed = [part async for part in client.stream_chat(messages=messages)]
    non_streamed = await client.chat(messages=messages)

    assert streamed == []
    assert non_streamed == {"content": "", "finish_reason": None}
    assert [payload["model"] for payload in calls] == [
        "deepseek-v4-flash-free",
        "deepseek-v4-flash-free",
    ]
