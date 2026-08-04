# AIMETA P=大纲任务metrics可观测|R=retry_count_degraded_merge|NR=不改大纲正文|E=test_outline_job_metrics|X=test|A=回归|D=pytest|S=none|RD=./README.ai
from __future__ import annotations

from typing import Any, Dict

import pytest

from app.api.routers import writer as writer_router


def test_normalize_outline_job_payload_defaults_metrics():
    payload = writer_router._normalize_outline_job_payload(
        {
            "run_id": "r1",
            "project_id": "p1",
            "status": "generating",
            "progress_stage": "outline_chapter_skeleton",
            "progress_message": "working",
        }
    )
    assert payload["metrics"]["retry_count"] == 0
    assert payload["metrics"]["llm_call_count"] == 0
    assert payload["metrics"]["degraded"] is False
    assert payload["metrics"]["retry_events"] == []


@pytest.mark.anyio
async def test_set_outline_job_state_merges_retry_metrics(monkeypatch):
    run_id = "run-outline-metrics-1"
    writer_router._OUTLINE_JOBS[run_id] = {
        "run_id": run_id,
        "project_id": "p-metrics",
        "user_id": 1,
        "status": "generating",
        "progress_stage": "outline_chapter_skeleton",
        "progress_message": "working",
        "metrics": {
            "retry_count": 0,
            "llm_call_count": 0,
            "degraded": False,
            "retry_events": [],
            "stage_attempts": {},
        },
    }

    persisted = []

    async def fake_persist(job: Dict[str, Any]) -> None:
        persisted.append(dict(job.get("metrics") or {}))

    monkeypatch.setattr(writer_router, "_persist_outline_job_state", fake_persist)

    await writer_router._set_outline_job_state(
        run_id,
        metrics={
            "retry_count": 1,
            "llm_call_count": 2,
            "degraded": True,
            "last_retry_reason": "provider_jitter",
            "last_retry_stage": "章节大纲批量生成",
            "retry_events": [{"stage": "章节大纲批量生成", "reason": "provider_jitter"}],
            "stage_attempts": {"章节大纲批量生成": 1},
        },
    )
    await writer_router._set_outline_job_state(
        run_id,
        metrics={
            "retry_count": 2,
            "llm_call_count": 3,
            "degraded": True,
            "retry_events": [{"stage": "章节大纲重写", "reason": "json_repair"}],
            "stage_attempts": {"章节大纲重写": 1},
        },
    )

    metrics = writer_router._OUTLINE_JOBS[run_id]["metrics"]
    assert metrics["retry_count"] == 2
    assert metrics["llm_call_count"] == 3
    assert metrics["degraded"] is True
    assert len(metrics["retry_events"]) == 2
    assert metrics["stage_attempts"]["章节大纲批量生成"] == 1
    assert metrics["stage_attempts"]["章节大纲重写"] == 1
    assert persisted, "should persist metrics updates"

    writer_router._OUTLINE_JOBS.pop(run_id, None)


def test_serialize_outline_job_includes_metrics():
    response = writer_router._serialize_outline_job(
        {
            "run_id": "r2",
            "project_id": "p2",
            "status": "generating",
            "progress_stage": "outline_chapter_skeleton",
            "progress_message": "retrying",
            "metrics": {
                "retry_count": 1,
                "llm_call_count": 2,
                "degraded": True,
                "last_retry_reason": "provider_jitter",
                "retry_events": [{"reason": "provider_jitter"}],
            },
        }
    )
    assert response.metrics["retry_count"] == 1
    assert response.metrics["degraded"] is True
    assert response.metrics["llm_call_count"] == 2


@pytest.mark.anyio
async def test_outline_start_job_includes_default_metrics(monkeypatch):
    from fastapi import BackgroundTasks

    from app.schemas.novel import GenerateOutlineRequest
    from app.schemas.user import UserInDB

    class _FakeNovelService:
        def __init__(self, session):
            self.session = session

        async def ensure_project_owner(self, project_id, user_id):
            return object()

    monkeypatch.setattr(writer_router, "NovelService", _FakeNovelService)

    async def fake_load_active(*_args, **_kwargs):
        return None

    async def fake_upsert(*_args, **_kwargs):
        return None

    monkeypatch.setattr(writer_router, "_load_active_outline_job_from_db", fake_load_active)
    monkeypatch.setattr(writer_router, "_upsert_outline_job_record", fake_upsert)

    current_user = UserInDB(id=7, username="tester", email=None, hashed_password="x")
    request = GenerateOutlineRequest(start_chapter=2, num_chapters=4, target_total_chapters=80)
    background_tasks = BackgroundTasks()

    started = await writer_router.start_chapters_outline_generation(
        project_id="project-metrics",
        request=request,
        background_tasks=background_tasks,
        session=object(),
        current_user=current_user,
    )
    assert started.metrics["retry_count"] == 0
    assert started.metrics["llm_call_count"] == 0
    assert started.metrics["degraded"] is False
