# -*- coding: utf-8 -*-
from app.services.llm_service import LLMService, _PROMPT_CACHE_KEY_UNSUPPORTED_BASES


def test_xzxyuan_prompt_cache_key_pre_unsupported():
    assert LLMService._is_prompt_cache_key_unsupported("https://api.xzxyuan.ccwu.cc/v1") is True
    assert LLMService._is_prompt_cache_key_unsupported("http://127.0.0.1:8317/v1") is False


def test_mark_prompt_cache_key_unsupported_persists():
    _PROMPT_CACHE_KEY_UNSUPPORTED_BASES.discard("https://example-gateway.test/v1")
    assert LLMService._is_prompt_cache_key_unsupported("https://example-gateway.test/v1") is False
    LLMService._mark_prompt_cache_key_unsupported("https://example-gateway.test/v1")
    assert LLMService._is_prompt_cache_key_unsupported("https://example-gateway.test/v1") is True
    _PROMPT_CACHE_KEY_UNSUPPORTED_BASES.discard("https://example-gateway.test/v1")
