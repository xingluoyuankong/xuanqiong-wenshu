# -*- coding: utf-8 -*-
"""Minimal async integration coverage for PipelineOrchestrator.generate_chapter continuation."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.schemas.novel import ChapterGenerationStatus
from app.services.longform_context_service import ContinuityQualityGate
from app.services.generation_call_service import GenerationCallPolicy
from app.services.pipeline_orchestrator import PipelineConfig, PipelineOrchestrator


class _Session:
    async def refresh(self, _instance):
        return None

    async def commit(self):
        return None

    async def flush(self):
        return None

    def expire_all(self):
        return None


class _NovelService:
    def __init__(self, project, outline, chapter):
        self.repo = SimpleNamespace(get_by_id=AsyncMock(return_value=project))
        self._outline = outline
        self._chapter = chapter
        self.append_calls = []

    async def get_outline(self, project_id, chapter_number):
        assert (project_id, chapter_number) == ("project-1", 1)
        return self._outline

    async def get_or_create_chapter(self, project_id, chapter_number):
        assert (project_id, chapter_number) == ("project-1", 1)
        return self._chapter

    async def append_chapter_versions(self, chapter, contents, metadata, **kwargs):
        self.append_calls.append((chapter, list(contents), list(metadata), kwargs))
        return [
            SimpleNamespace(id=index + 101, content=content, metadata=item)
            for index, (content, item) in enumerate(zip(contents, metadata))
        ]


def _distinct_segment(marker: str, offset: int) -> str:
    return marker + "。" + "".join(f"情节{offset + index:03d}推进。" for index in range(28))



def _build_boundary_orchestrator(monkeypatch, continuation_handler):
    run_id = "continuation-boundary-run"
    chapter = SimpleNamespace(
        id=12,
        project_id="project-1",
        chapter_number=1,
        status=ChapterGenerationStatus.GENERATING.value,
        real_summary=json.dumps({"generation_runtime": {"run_id": run_id, "events": []}}, ensure_ascii=False),
        selected_version_id=None,
        selected_version=None,
    )
    outline = SimpleNamespace(chapter_number=1, title="雨夜旧港", summary="林七在旧港追查账册。")
    project = SimpleNamespace(outlines=[outline], chapters=[], id="project-1")
    novel_service = _NovelService(project, outline, chapter)
    orchestrator = object.__new__(PipelineOrchestrator)
    orchestrator.session = _Session()
    orchestrator.novel_service = novel_service
    orchestrator.prompt_service = SimpleNamespace(get_prompt=AsyncMock(return_value="小说作者"))
    orchestrator.llm_service = object()
    orchestrator.context_builder = SimpleNamespace(
        analyze_character_scope=lambda **_kwargs: {
            "all_names": ["林七"], "introduced_characters": ["林七"], "planned_characters": [],
        },
        build_visibility_context=lambda **_kwargs: {
            "writer_blueprint": {"characters": [{"name": "林七"}]},
            "forbidden_characters": ["顾临"],
            "introduced_characters": ["林七"],
            "macro_continuity_context": "前章结尾的雨声仍未停。",
        },
    )
    orchestrator.longform_context_service = SimpleNamespace(
        build_context_package=AsyncMock(return_value=None),
        evaluate_continuity_quality=lambda **_kwargs: ContinuityQualityGate(passed=True, metrics={"continuity": "ok"}),
    )
    config = PipelineConfig(
        preset="basic", version_count=1, target_word_count=1000, min_word_count=100,
        enable_rag=False, enable_multi_round_fallback=True, multi_round_max_rounds=2,
        multi_round_min_increment=100,
    )
    continuation_calls = []
    runtime_events = []

    async def generate_initial(**_kwargs):
        return {"index": 0, "content": _distinct_segment("首轮边界正文", 0)[:260], "metadata": {"timings": {}}}

    async def generate_continuation(**kwargs):
        continuation_calls.append(kwargs)
        return await continuation_handler(chapter, kwargs)

    async def runtime_callback(event):
        runtime_events.append(event)

    monkeypatch.setattr(orchestrator, "_resolve_config", AsyncMock(return_value=config))
    monkeypatch.setattr(orchestrator, "_ensure_provider_ready", AsyncMock(return_value={}))
    monkeypatch.setattr(orchestrator, "_check_token_budget_before_generation", AsyncMock(return_value=None))
    monkeypatch.setattr(orchestrator, "_collect_history_context", AsyncMock(return_value={
        "completed_summaries": [], "previous_summary": "前章摘要", "previous_tail": "雨声未停。",
        "recent_track": "旧港线", "plot_arc_digest": "账册去向未明。",
    }))
    monkeypatch.setattr(orchestrator, "_get_writer_blueprint", AsyncMock(return_value={"characters": [{"name": "林七"}]}))
    monkeypatch.setattr(orchestrator, "_generate_chapter_mission", AsyncMock(return_value={
        "allowed_new_characters": [],
        "scene_list": [{"scene": "旧港追查", "goal": "找到账册", "conflict": "潮水封路", "turn": "发现假账册", "outcome": "追踪船灯"}],
        "continuity_anchor": {"inherit_from_previous": ["雨声未停"]},
    }))
    monkeypatch.setattr(orchestrator, "_get_project_memory_text", AsyncMock(return_value=None))
    monkeypatch.setattr(orchestrator, "_get_style_context", AsyncMock(return_value="冷峻短句"))
    monkeypatch.setattr(orchestrator, "_build_story_guidance_context", AsyncMock(return_value=None))
    monkeypatch.setattr(orchestrator, "_build_stable_retry_config", lambda _config: None)
    monkeypatch.setattr(orchestrator, "_generate_single_version", generate_initial)
    monkeypatch.setattr(orchestrator, "_call_continuation_generation", generate_continuation)
    monkeypatch.setattr(orchestrator, "_apply_deterministic_cleanup", lambda *, content, **_kwargs: (content, {"changed": False}))
    monkeypatch.setattr(orchestrator, "_evaluate_structural_quality_gate_for_content", lambda *, review_summaries, **_kwargs: (review_summaries, {"passed": True, "quality_issue_codes": [], "quality_issue_labels": [], "blockers": []}))
    monkeypatch.setattr(orchestrator, "_score_story_quality_candidate", lambda **_kwargs: {"quality_metric_snapshot": {}, "violations": []})
    monkeypatch.setattr(orchestrator, "_attach_quality_gate_status_to_guard", lambda guard, _gate: guard)
    monkeypatch.setattr(orchestrator, "_record_generation_token_budget_usage", AsyncMock(return_value={"record_count": 0, "total_tokens": 0, "estimated_cost": 0.0}))
    return orchestrator, chapter, novel_service, config, continuation_calls, runtime_events, runtime_callback, run_id


@pytest.mark.asyncio
async def test_generate_chapter_runs_stateful_two_round_continuation_and_persists_candidate(monkeypatch):
    run_id = "continuation-integration-run"
    chapter = SimpleNamespace(
        id=11,
        project_id="project-1",
        chapter_number=1,
        status=ChapterGenerationStatus.GENERATING.value,
        real_summary=json.dumps({"generation_runtime": {"run_id": run_id, "events": []}}, ensure_ascii=False),
        selected_version_id=None,
        selected_version=None,
    )
    outline = SimpleNamespace(chapter_number=1, title="雨夜旧港", summary="林七在旧港追查账册。")
    project = SimpleNamespace(outlines=[outline], chapters=[], id="project-1")
    novel_service = _NovelService(project, outline, chapter)
    orchestrator = object.__new__(PipelineOrchestrator)
    orchestrator.session = _Session()
    orchestrator.novel_service = novel_service
    orchestrator.prompt_service = SimpleNamespace(get_prompt=AsyncMock(return_value="小说作者"))
    orchestrator.llm_service = object()
    orchestrator.context_builder = SimpleNamespace(
        analyze_character_scope=lambda **_kwargs: {
            "all_names": ["林七"], "introduced_characters": ["林七"], "planned_characters": [],
        },
        build_visibility_context=lambda **_kwargs: {
            "writer_blueprint": {"characters": [{"name": "林七"}]},
            "forbidden_characters": ["顾临"],
            "introduced_characters": ["林七"],
            "macro_continuity_context": "前章结尾的雨声仍未停。",
        },
    )
    orchestrator.longform_context_service = SimpleNamespace(
        build_context_package=AsyncMock(return_value=None),
        evaluate_continuity_quality=lambda **_kwargs: ContinuityQualityGate(passed=True, metrics={"continuity": "ok"}),
    )
    config = PipelineConfig(
        preset="basic",
        version_count=1,
        target_word_count=1000,
        min_word_count=100,
        enable_rag=False,
        enable_multi_round_fallback=True,
        multi_round_max_rounds=2,
        multi_round_min_increment=100,
    )
    histories = []
    runtime_events = []

    async def generate_initial(**_kwargs):
        return {"index": 0, "content": _distinct_segment("首轮正文", 0)[:260], "metadata": {"timings": {}}}

    async def generate_continuation(**kwargs):
        histories.append(kwargs["conversation_history"])
        marker = "续写第一轮" if kwargs["round_number"] == 1 else "续写第二轮"
        offset = 100 if kwargs["round_number"] == 1 else 200
        return SimpleNamespace(text=_distinct_segment(marker, offset))

    async def runtime_callback(event):
        runtime_events.append(event)

    monkeypatch.setattr(orchestrator, "_resolve_config", AsyncMock(return_value=config))
    monkeypatch.setattr(orchestrator, "_ensure_provider_ready", AsyncMock(return_value={}))
    monkeypatch.setattr(orchestrator, "_check_token_budget_before_generation", AsyncMock(return_value=None))
    monkeypatch.setattr(orchestrator, "_collect_history_context", AsyncMock(return_value={
        "completed_summaries": [], "previous_summary": "前章摘要", "previous_tail": "雨声未停。",
        "recent_track": "旧港线", "plot_arc_digest": "账册去向未明。",
    }))
    monkeypatch.setattr(orchestrator, "_get_writer_blueprint", AsyncMock(return_value={"characters": [{"name": "林七"}]}))
    monkeypatch.setattr(orchestrator, "_generate_chapter_mission", AsyncMock(return_value={
        "allowed_new_characters": [],
        "scene_list": [{"scene": "旧港追查", "goal": "找到账册", "conflict": "潮水封路", "turn": "发现假账册", "outcome": "追踪船灯"}],
        "continuity_anchor": {"inherit_from_previous": ["雨声未停"]},
    }))
    monkeypatch.setattr(orchestrator, "_get_project_memory_text", AsyncMock(return_value=None))
    monkeypatch.setattr(orchestrator, "_get_style_context", AsyncMock(return_value="冷峻短句"))
    monkeypatch.setattr(orchestrator, "_build_story_guidance_context", AsyncMock(return_value=None))
    monkeypatch.setattr(orchestrator, "_build_stable_retry_config", lambda _config: None)
    monkeypatch.setattr(orchestrator, "_generate_single_version", generate_initial)
    monkeypatch.setattr(orchestrator, "_call_continuation_generation", generate_continuation)
    monkeypatch.setattr(orchestrator, "_apply_deterministic_cleanup", lambda *, content, **_kwargs: (content, {"changed": False}))
    monkeypatch.setattr(orchestrator, "_evaluate_structural_quality_gate_for_content", lambda *, review_summaries, **_kwargs: (review_summaries, {"passed": True, "quality_issue_codes": [], "quality_issue_labels": [], "blockers": []}))
    monkeypatch.setattr(orchestrator, "_score_story_quality_candidate", lambda **_kwargs: {"quality_metric_snapshot": {}, "violations": []})
    monkeypatch.setattr(orchestrator, "_attach_quality_gate_status_to_guard", lambda guard, _gate: guard)
    monkeypatch.setattr(orchestrator, "_record_generation_token_budget_usage", AsyncMock(return_value={"record_count": 0, "total_tokens": 0, "estimated_cost": 0.0}))

    result = await orchestrator.generate_chapter(
        project_id="project-1",
        chapter_number=1,
        user_id=7,
        writing_notes="完整写前要求：保持林七视角。",
        flow_config={},
        generation_run_id=run_id,
        runtime_event_callback=runtime_callback,
    )

    assert len(histories) == 2
    full_prompt = histories[0][0]["content"]
    assert "完整写前要求：保持林七视角。" in full_prompt
    assert histories[0][1]["role"] == "assistant"
    assert all(item["content"] != full_prompt for item in histories[1])
    assert histories[1][0]["role"] == "assistant"
    assert "续写第一轮" in histories[1][0]["content"]

    persisted_contents = novel_service.append_calls[0][1]
    assert len(persisted_contents) == 1
    assert "首轮正文" in persisted_contents[0]
    assert "续写第一轮" in persisted_contents[0]
    assert "续写第二轮" in persisted_contents[0]
    assert result["variants"][0]["content"] == persisted_contents[0]

    continuation = result["runtime_metadata"]["continuation"]
    assert continuation["rounds"] == 2
    assert continuation["stateful_context"] is True
    assert continuation["full_prompt_rounds"] == 1
    assert continuation["compact_context_rounds"] == 1
    assert continuation["stop_reason"] == "continuation_floor_reached"
    assert [attempt["accepted"] for attempt in continuation["attempts"]] == [True, True]
    assert any(event["event_type"] == "continuation" for event in runtime_events)
    assert any(event["payload"].get("metrics", {}).get("round") == 2 for event in runtime_events)

@pytest.mark.asyncio
async def test_generate_chapter_stops_on_low_continuation_increment_and_persists_original(monkeypatch):
    async def short_output(_chapter, _kwargs):
        return SimpleNamespace(text="短")

    orchestrator, _chapter, novel_service, _config, calls, events, callback, run_id = _build_boundary_orchestrator(monkeypatch, short_output)
    result = await orchestrator.generate_chapter(
        project_id="project-1", chapter_number=1, user_id=7, flow_config={},
        generation_run_id=run_id, runtime_event_callback=callback,
    )

    continuation = result["runtime_metadata"]["continuation"]
    assert len(calls) == 1
    assert continuation["stop_reason"] == "low_increment"
    assert continuation["attempts"][0]["accepted"] is False
    assert "短" not in novel_service.append_calls[0][1][0]
    assert any(event["payload"].get("metrics", {}).get("stop_reason") == "low_increment" for event in events)


@pytest.mark.asyncio
async def test_generate_chapter_provider_error_keeps_existing_draft_and_records_degradation(monkeypatch):
    async def provider_error(_chapter, _kwargs):
        raise RuntimeError("provider connection dropped")

    orchestrator, _chapter, novel_service, _config, calls, _events, callback, run_id = _build_boundary_orchestrator(monkeypatch, provider_error)
    result = await orchestrator.generate_chapter(
        project_id="project-1", chapter_number=1, user_id=7, flow_config={},
        generation_run_id=run_id, runtime_event_callback=callback,
    )

    continuation = result["runtime_metadata"]["continuation"]
    assert len(calls) == 1
    assert continuation["stop_reason"] == "provider_error"
    assert continuation["attempts"][0]["accepted"] is False
    assert "首轮边界正文" in novel_service.append_calls[0][1][0]
    assert "provider connection dropped" in str(result["runtime_metadata"]["degraded_stages"])


@pytest.mark.asyncio
async def test_generate_chapter_cancellation_after_continuation_call_aborts_without_persisting(monkeypatch):
    async def cancellation_during_call(chapter, _kwargs):
        payload = json.loads(chapter.real_summary)
        payload["generation_runtime"]["cancel_requested"] = True
        chapter.real_summary = json.dumps(payload, ensure_ascii=False)
        return SimpleNamespace(text=_distinct_segment("不应采纳", 900))

    orchestrator, _chapter, novel_service, _config, calls, _events, callback, run_id = _build_boundary_orchestrator(monkeypatch, cancellation_during_call)
    with pytest.raises(HTTPException) as exc_info:
        await orchestrator.generate_chapter(
            project_id="project-1", chapter_number=1, user_id=7, flow_config={},
            generation_run_id=run_id, runtime_event_callback=callback,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "GENERATION_CANCELLED"
    assert len(calls) == 1
    assert novel_service.append_calls == []

@pytest.mark.asyncio
async def test_generate_chapter_reuses_structural_gate_when_enrichment_and_cleanup_are_noops(monkeypatch):
    async def reach_floor(_chapter, _kwargs):
        return SimpleNamespace(text=_distinct_segment("补足正文", 300))

    orchestrator, _chapter, _novel_service, config, _calls, _events, callback, run_id = _build_boundary_orchestrator(monkeypatch, reach_floor)
    config.enable_enrichment = True
    config.multi_round_max_rounds = 1
    gate_calls = []

    def evaluate_gate(*, review_summaries, content, story_guard_key="story_progression_guard", **_kwargs):
        gate_calls.append(content)
        summaries = dict(review_summaries)
        summaries[story_guard_key] = {"word_count": len(content), "score": 88}
        return summaries, {"passed": True, "quality_issue_codes": [], "quality_issue_labels": [], "blockers": []}

    async def enrichment_noop(content, **_kwargs):
        return content, None

    monkeypatch.setattr(orchestrator, "_evaluate_structural_quality_gate_for_content", evaluate_gate)
    monkeypatch.setattr(orchestrator, "_run_enrichment", enrichment_noop)
    result = await orchestrator.generate_chapter(
        project_id="project-1", chapter_number=1, user_id=7, flow_config={},
        generation_run_id=run_id, runtime_event_callback=callback,
    )

    assert len(gate_calls) == 1
    final_gate = result["runtime_metadata"]["quality_gates"]["structural_gate_final"]
    assert final_gate["reused_from"] == "pre_enrichment_structural_gate"
    assert result["review_summaries"]["story_progression_guard"]["word_count"] == len(gate_calls[0])


@pytest.mark.asyncio
async def test_generate_chapter_recomputes_structural_gate_when_final_cleanup_changes_whitespace(monkeypatch):
    async def reach_floor(_chapter, _kwargs):
        return SimpleNamespace(text=_distinct_segment("补足正文", 400))

    orchestrator, _chapter, _novel_service, config, _calls, _events, callback, run_id = _build_boundary_orchestrator(monkeypatch, reach_floor)
    config.enable_enrichment = True
    config.multi_round_max_rounds = 1
    gate_calls = []
    cleanup_calls = []

    def evaluate_gate(*, review_summaries, content, story_guard_key="story_progression_guard", **_kwargs):
        gate_calls.append(content)
        summaries = dict(review_summaries)
        summaries[story_guard_key] = {"word_count": len(content), "score": 88}
        return summaries, {"passed": True, "quality_issue_codes": [], "quality_issue_labels": [], "blockers": []}

    async def enrichment_noop(content, **_kwargs):
        return content, None

    def cleanup(*, content, **_kwargs):
        cleanup_calls.append(content)
        if len(cleanup_calls) == 2:
            return content.replace("\n\n", "\n \n", 1), {"changed": True}
        return content, {"changed": False}

    monkeypatch.setattr(orchestrator, "_evaluate_structural_quality_gate_for_content", evaluate_gate)
    monkeypatch.setattr(orchestrator, "_run_enrichment", enrichment_noop)
    monkeypatch.setattr(orchestrator, "_apply_deterministic_cleanup", cleanup)
    result = await orchestrator.generate_chapter(
        project_id="project-1", chapter_number=1, user_id=7, flow_config={},
        generation_run_id=run_id, runtime_event_callback=callback,
    )

    assert len(gate_calls) == 2
    assert gate_calls[0] != gate_calls[1]
    assert result["runtime_metadata"]["quality_gates"]["structural_gate_final"].get("reused_from") is None


@pytest.mark.asyncio
async def test_generate_chapter_exposes_shared_provider_budget_in_final_runtime(monkeypatch):
    async def continuation_with_budget(_chapter, _kwargs):
        policy = orchestrator._track_generation_call_policy(
            GenerationCallPolicy(response_format=None), role="continuation"
        )
        attempt = policy.attempt_ledger.begin(
            role=policy.attempt_role,
            provider_ref="fixture-provider",
            model_ref="fixture-model",
        )
        policy.attempt_ledger.finish(attempt.attempt_id, output="续写预算正文")
        return SimpleNamespace(text=_distinct_segment("预算续写正文", 700))

    orchestrator, chapter, _novel_service, _config, _calls, runtime_events, callback, run_id = _build_boundary_orchestrator(
        monkeypatch, continuation_with_budget
    )

    async def initial_with_budget(**_kwargs):
        policy = orchestrator._track_generation_call_policy(
            GenerationCallPolicy(response_format=None), role="draft_candidate_1"
        )
        first = policy.attempt_ledger.begin(
            role=policy.attempt_role,
            provider_ref="fixture-provider",
            model_ref="fixture-model",
        )
        policy.attempt_ledger.fail(first.attempt_id, category="TIMEOUT")
        second = policy.attempt_ledger.begin(
            role=policy.attempt_role,
            provider_ref="fixture-provider",
            model_ref="fixture-model",
            retry_index=1,
        )
        policy.attempt_ledger.finish(second.attempt_id, output="初稿预算正文")
        return {
            "index": 0,
            "content": _distinct_segment("预算首稿正文", 0)[:260],
            "metadata": {"timings": {}},
        }

    monkeypatch.setattr(orchestrator, "_generate_single_version", initial_with_budget)
    result = await orchestrator.generate_chapter(
        project_id="project-1",
        chapter_number=1,
        user_id=7,
        flow_config={},
        generation_run_id=run_id,
        runtime_event_callback=callback,
    )

    budget = result["runtime_metadata"]["provider_budget"]
    assert budget["scope"] == "generation_call_service_direct_only"
    assert budget["logical_call_count"] == 3
    assert budget["provider_attempt_count"] == 4
    assert budget["failed_attempt_count"] == 1
    assert budget["roles"]["draft_candidate_1"]["provider_attempts"] == 2
    assert budget["roles"]["continuation"]["provider_attempts"] >= 1

    runtime_budget = json.loads(chapter.real_summary)["generation_runtime"]["provider_budget"]
    assert runtime_budget["provider_attempt_count"] == budget["provider_attempt_count"]
    final_event = runtime_events[-1]
    assert final_event["payload"]["metadata"]["provider_budget"]["logical_call_count"] == 3
    assert final_event["payload"]["metrics"]["provider_attempt_count"] == budget["provider_attempt_count"]


