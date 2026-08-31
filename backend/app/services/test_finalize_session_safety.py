# -*- coding: utf-8 -*-
import asyncio
import inspect

import pytest
from fastapi import HTTPException

from app.services.finalize_service import FinalizeService
from app.services.llm_service import LLMService


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_finalize_and_memory_updates_do_not_fan_out_session_work():
    from app.services.memory_layer_service import MemoryLayerService

    finalize_source = inspect.getsource(FinalizeService)
    memory_source = inspect.getsource(MemoryLayerService.update_memory_after_chapter)
    assert "asyncio.gather(" not in finalize_source
    assert "asyncio.gather(" not in memory_source
    assert memory_source.index("extract_character_states_from_chapter") < memory_source.index("extract_timeline_events_from_chapter")
    assert memory_source.index("extract_timeline_events_from_chapter") < memory_source.index("extract_causal_chains_from_chapter")


def test_llm_service_uses_locked_and_unlocked_config_resolution():
    source = inspect.getsource(LLMService)
    assert "self._session_lock = asyncio.Lock()" in source
    assert "async def _resolve_llm_config_unlocked" in source
    assert "Prefer dedicated short-lived sessions" in source
    service = LLMService(session=object())
    assert isinstance(service._session_lock, asyncio.Lock)


@pytest.mark.asyncio
async def test_llm_config_resolution_is_serialized_per_service():
    service = LLMService(session=object())
    events = []

    async def fake_resolve(*_args, **_kwargs):
        events.append("start")
        await asyncio.sleep(0.01)
        events.append("end")
        return {"model": "test"}

    service._resolve_llm_config_unlocked = fake_resolve
    await asyncio.gather(service._resolve_llm_config(1), service._resolve_llm_config(1))
    assert events == ["start", "end", "start", "end"]


def test_finalize_fallbacks_preserve_existing_ledger_and_character_state():
    svc = FinalizeService.__new__(FinalizeService)
    old_plot = {
        "unresolved_hooks": ["血契三日反噬"],
        "main_conflicts": ["夜雨令归属"],
        "character_arcs": ["林舟·血线蔓延"],
    }
    plot = svc._fallback_plot_arcs(
        chapter_text="林舟在驿站压住血契，顾棠用药。",
        chapter_number=2,
        old_plot_arcs=old_plot,
    )
    assert plot["update_source"] == "local_fallback"
    assert plot["last_updated_chapter"] == 2
    assert "血契三日反噬" in plot["unresolved_hooks"]
    assert any("第2章已定稿" in str(item) for item in plot["unresolved_hooks"])
    assert plot["main_conflicts"] == ["夜雨令归属"]

    state = svc._local_fallback_character_state(
        chapter_text="顾棠带林舟躲进破屋，血契发热，决定东街寻刻令者。",
        old_state="林舟：\n├──物品: 夜雨令",
    )
    assert "夜雨令" in state
    assert "本章本地回退" in state
    assert "东街" in state or "破屋" in state or "血契" in state
    assert len(state) <= 2500


def test_finalize_rolls_back_before_running_provider_stages():
    source = inspect.getsource(FinalizeService.finalize_chapter)
    assert source.index("await self._rollback()") < source.index("await self._update_global_summary")


def test_structured_output_detection_accepts_provider_wording_variants():
    from app.services.generation_call_service import _looks_like_structured_output_unsupported

    for detail in (
        "Model DeepSeek-V4-Flash does not support JSON schema output mode",
        "response_format json_schema is not supported by this model",
    ):
        assert _looks_like_structured_output_unsupported(HTTPException(status_code=400, detail=detail))


def test_json_schema_capability_cache_is_model_scoped():
    from app.services.generation_call_service import (
        GenerationCallPolicy,
        _downgrade_schema_policy,
        build_response_format_payload,
        clear_json_schema_capability_cache,
        is_json_schema_unsupported,
        mark_json_schema_unsupported,
    )

    clear_json_schema_capability_cache()
    try:
        assert is_json_schema_unsupported(model="DeepSeek-V4-Flash")
        assert not is_json_schema_unsupported(model="gpt-4o-mini")
        mark_json_schema_unsupported(model=None, detail="Model gpt-4o-mini-custom does not support JSON schema output mode")
        assert is_json_schema_unsupported(model="gpt-4o-mini-custom")
        assert not is_json_schema_unsupported(model=None)
        policy = _downgrade_schema_policy(GenerationCallPolicy(json_schema={"type": "object"}))
        assert policy.json_schema is None
        assert build_response_format_payload(policy) == "json_object"
    finally:
        clear_json_schema_capability_cache()
