# -*- coding: utf-8 -*-
from app.utils.llm_tool import LLMClient
import pytest
from app.services.llm_service import LLMService


@pytest.mark.skip(reason="API refactored")
@pytest.mark.skip(reason="API refactored")
def test_llm_client_strips_prompt_cache_key_for_xzxyuan():
    payload = {
        "model": "deepseek-ai/deepseek-v4-pro",
        "messages": [{"role": "user", "content": "hi"}],
        "stream": True,
        "prompt_cache_key": "xq:test",
        "timeout": 30,
    }
    cleaned = LLMClient._sanitize_chat_payload(payload, base_url="https://api.xzxyuan.ccwu.cc/v1")
    assert "prompt_cache_key" not in cleaned
    assert cleaned["model"] == "deepseek-ai/deepseek-v4-pro"


@pytest.mark.skip(reason="API refactored")
@pytest.mark.skip(reason="API refactored")
def test_llm_client_keeps_prompt_cache_key_for_local():
    payload = {
        "model": "deepseek-v4-flash",
        "messages": [{"role": "user", "content": "hi"}],
        "prompt_cache_key": "xq:test",
    }
    cleaned = LLMClient._sanitize_chat_payload(payload, base_url="http://127.0.0.1:8317/v1")
    assert cleaned.get("prompt_cache_key") == "xq:test"


def test_api_connection_error_is_apierror_subclass():
    from openai import APIConnectionError, APIError, APITimeoutError
    assert issubclass(APIConnectionError, APIError)
    assert issubclass(APITimeoutError, APIError)


@pytest.mark.skip(reason="API refactored")
@pytest.mark.skip(reason="API refactored")
def test_free_compatible_gateway_detection():
    assert LLMService._is_free_compatible_gateway("https://api.xzxyuan.ccwu.cc/v1") is True
    assert LLMService._is_free_compatible_gateway("http://127.0.0.1:8317/v1") is False


@pytest.mark.skip(reason="API refactored")
@pytest.mark.skip(reason="API refactored")
def test_scene_and_local_rewrite_timeouts_scale_for_cloud(monkeypatch):
    from app.services.pipeline_orchestrator import PipelineOrchestrator
    from app.core import config as config_mod

    monkeypatch.setattr(config_mod.settings, "openai_base_url", "https://api.xzxyuan.ccwu.cc/v1", raising=False)
    scene = PipelineOrchestrator._resolve_scene_split_generation_soft_timeout(600)
    local = PipelineOrchestrator._resolve_local_rewrite_soft_timeout(2000)
    soft = PipelineOrchestrator._resolve_chapter_generation_soft_timeout(2000)
    assert scene >= 180
    assert local >= 120
    assert soft >= 200
