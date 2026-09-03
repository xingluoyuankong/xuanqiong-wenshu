from __future__ import annotations

import pytest

from app.services.llm_service import LLMService


class FakeClient:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    async def stream_chat(self, **kwargs):
        yield {"content": "可见第一段", "reasoning_content": "不得泄漏的内部推理", "finish_reason": None}
        yield {"content": "可见第二段", "reasoning_content": "仍不得泄漏", "finish_reason": "stop"}


@pytest.mark.asyncio
async def test_agent_visible_stream_yields_content_but_never_reasoning(monkeypatch, task_session):
    service = LLMService(task_session)

    async def resolved(*args, **kwargs):
        return {"api_key": "test-key", "base_url": "https://example.test/v1", "model": "test-model"}

    async def cooldown(*args, **kwargs):
        return None

    monkeypatch.setattr(service, "_resolve_llm_config", resolved)
    monkeypatch.setattr(service, "_wait_for_provider_cooldown", cooldown)
    monkeypatch.setattr("app.services.llm_service.LLMClient", FakeClient)

    content = [chunk async for chunk in service.stream_visible_response(
        system_prompt="safe system", user_prompt="safe user", user_id=1, timeout=10
    )]

    assert content == ["可见第一段", "可见第二段"]
    assert not any("内部推理" in chunk or "不得泄漏" in chunk for chunk in content)

@pytest.mark.asyncio
async def test_stream_agent_response_parts_preserves_content_reasoning_and_finish_reason(monkeypatch, task_session):
    service = LLMService(task_session)

    async def resolved(*args, **kwargs):
        return {"api_key": "test-key", "base_url": "https://example.test/v1", "model": "test-model"}

    async def cooldown(*args, **kwargs):
        return None

    monkeypatch.setattr(service, "_resolve_llm_config", resolved)
    monkeypatch.setattr(service, "_wait_for_provider_cooldown", cooldown)
    monkeypatch.setattr("app.services.llm_service.LLMClient", FakeClient)

    parts = [part async for part in service.stream_agent_response_parts(
        system_prompt="safe system", user_prompt="safe user", user_id=1, timeout=10
    )]

    assert parts == [
        {
            "content": "可见第一段",
            "reasoning_content": "不得泄漏的内部推理",
            "finish_reason": None,
        },
        {
            "content": "可见第二段",
            "reasoning_content": "仍不得泄漏",
            "finish_reason": "stop",
        },
    ]
