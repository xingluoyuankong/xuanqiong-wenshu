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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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

    class _Repo:
        async def get_by_id(self, project_id):
            assert project_id == "p1"
            return project

    class _NovelService:
        repo = _Repo()

        async def ensure_project_owner(self, project_id, user_id):
            raise AssertionError("worker must not apply legacy project-owner filtering")

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


@pytest.mark.asyncio
async def test_superseded_generation_run_cannot_append_late_versions(task_session):
    """旧 run 只可作为诊断字段存在，绝不可授权迟到版本写入。"""
    from fastapi import HTTPException
    from sqlalchemy import select

    from app.models import Chapter, ChapterVersion, NovelProject, User
    from app.services.novel_service import NovelService

    owner = User(
        id=98190,
        username="late-run-owner",
        email="late-run-owner@example.com",
        hashed_password="fixture",
        is_active=True,
    )
    project = NovelProject(id="superseded-run-project", user_id=owner.id, title="迟到 run 回归")
    chapter = Chapter(
        project_id=project.id,
        chapter_number=1,
        status=ChapterGenerationStatus.GENERATING.value,
        real_summary=json.dumps(
            {
                "generation_runtime": {
                    "run_id": "fresh-run",
                    "superseded_run_id": "old-run",
                    "cancel_requested": False,
                }
            },
            ensure_ascii=False,
        ),
    )
    task_session.add_all([owner, project, chapter])
    await task_session.commit()

    service = NovelService(task_session)
    with pytest.raises(HTTPException) as rejected:
        await service.append_chapter_versions(
            chapter,
            ["旧 worker 的迟到正文不得写入。"],
            expected_generation_run_id="old-run",
        )

    assert rejected.value.status_code == 409
    versions = await task_session.execute(
        select(ChapterVersion).where(ChapterVersion.chapter_id == chapter.id)
    )
    assert versions.scalars().all() == []
    await task_session.refresh(chapter)
    assert chapter.status == ChapterGenerationStatus.GENERATING.value


@pytest.mark.asyncio
async def test_current_generation_run_can_append_versions_after_rebind(task_session):
    """精确 fencing 不应阻断重新绑定后的当前 run。"""
    from app.models import Chapter, NovelProject, User
    from app.services.novel_service import NovelService

    owner = User(
        id=98191,
        username="fresh-run-owner",
        email="fresh-run-owner@example.com",
        hashed_password="fixture",
        is_active=True,
    )
    project = NovelProject(id="fresh-run-project", user_id=owner.id, title="当前 run 回归")
    chapter = Chapter(
        project_id=project.id,
        chapter_number=1,
        status=ChapterGenerationStatus.GENERATING.value,
        real_summary=json.dumps(
            {"generation_runtime": {"run_id": "fresh-run", "superseded_run_id": "old-run"}},
            ensure_ascii=False,
        ),
    )
    task_session.add_all([owner, project, chapter])
    await task_session.commit()

    versions = await NovelService(task_session).append_chapter_versions(
        chapter,
        ["当前 run 的正文可以正常落库。"],
        expected_generation_run_id="fresh-run",
    )

    assert len(versions) == 1
    assert versions[0].content == "当前 run 的正文可以正常落库。"
    assert chapter.status == ChapterGenerationStatus.WAITING_FOR_CONFIRM.value
