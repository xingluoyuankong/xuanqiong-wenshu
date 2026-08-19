# -*- coding: utf-8 -*-
"""Regression: generate_chapter rebinds fresh generation_run_id so retries are not false-cancelled."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.novel import ChapterGenerationStatus
from app.services.pipeline_orchestrator import PipelineOrchestrator


def _chapter(run_id: str | None = "old-run", status: str = "generating"):
    runtime = {
        "generation_runtime": {
            "run_id": run_id,
            "cancel_requested": False,
            "progress_stage": "review",
            "events": [{"stage": "review"}],
        }
    }
    return SimpleNamespace(
        id=1,
        project_id="p1",
        chapter_number=2,
        status=status,
        real_summary=json.dumps(runtime, ensure_ascii=False),
        selected_version_id=None,
    )


@pytest.mark.anyio
async def test_rebind_generation_run_overwrites_stale_run_id():
    orch = PipelineOrchestrator(session=AsyncMock())
    orch.session.refresh = AsyncMock()
    orch.session.commit = AsyncMock()
    orch.session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: None))
    chapter = _chapter("stale-run")

    await orch._rebind_generation_run_if_needed(
        chapter,
        generation_run_id="fresh-run",
        stage="pre_mission_context",
    )

    payload = json.loads(chapter.real_summary)
    runtime = payload["generation_runtime"]
    assert runtime["run_id"] == "fresh-run"
    assert runtime["cancel_requested"] is False
    assert runtime.get("superseded_run_id") == "stale-run"
    assert chapter.status == ChapterGenerationStatus.GENERATING.value
    orch.session.commit.assert_awaited()


@pytest.mark.anyio
async def test_rebind_is_noop_when_run_already_active():
    orch = PipelineOrchestrator(session=AsyncMock())
    orch.session.refresh = AsyncMock()
    orch.session.commit = AsyncMock()
    orch.session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: None))
    chapter = _chapter("same-run")
    before = chapter.real_summary

    await orch._rebind_generation_run_if_needed(
        chapter,
        generation_run_id="same-run",
        stage="pre_mission_context",
    )

    assert chapter.real_summary == before
    orch.session.commit.assert_not_awaited()


@pytest.mark.anyio
async def test_assert_generation_active_passes_after_rebind():
    orch = PipelineOrchestrator(session=AsyncMock())
    orch.session.refresh = AsyncMock()
    orch.session.commit = AsyncMock()
    orch.session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: None))
    chapter = _chapter("old")
    await orch._rebind_generation_run_if_needed(chapter, generation_run_id="new")
    # should not raise
    await orch._assert_generation_active(
        chapter,
        generation_run_id="new",
        stage="pre_mission_context",
    )


@pytest.mark.anyio
async def test_formal_generate_chapter_entry_rebinds_before_runtime_updates():
    orch = PipelineOrchestrator(session=AsyncMock())
    chapter = _chapter("stale-run", status="failed")
    project = SimpleNamespace(outlines=[])
    outline = SimpleNamespace(chapter_number=2, title="章", summary="摘要")
    config = SimpleNamespace(
        preset="basic",
        target_word_count=500,
        min_word_count=300,
        enable_memory=False,
    )

    class _StopPipeline(Exception):
        pass

    class _NovelService:
        async def ensure_project_owner(self, project_id, user_id):
            return project

        async def get_outline(self, project_id, chapter_number):
            return outline

        async def get_or_create_chapter(self, project_id, chapter_number):
            return chapter

    async def stop_at_first_runtime_update(*_args, **_kwargs):
        raise _StopPipeline

    orch.novel_service = _NovelService()
    orch._resolve_config = AsyncMock(return_value=config)
    orch._ensure_provider_ready = AsyncMock(return_value={})
    orch._check_token_budget_before_generation = AsyncMock(return_value=None)
    orch._update_generation_runtime = stop_at_first_runtime_update

    with pytest.raises(_StopPipeline):
        await orch.generate_chapter(
            project_id="p1",
            chapter_number=2,
            user_id=1,
            flow_config={},
            generation_run_id="fresh-run",
        )

    runtime = json.loads(chapter.real_summary)["generation_runtime"]
    assert runtime["run_id"] == "fresh-run"
    assert runtime["superseded_run_id"] == "stale-run"
    assert chapter.status == ChapterGenerationStatus.GENERATING.value
