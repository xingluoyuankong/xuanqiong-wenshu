# AIMETA P=蓝图任务metrics可观测|R=retry_count_degraded_merge|NR=完整蓝图生成|E=test_blueprint_job_metrics|X=test|A=回归|D=pytest|S=none|RD=./README.ai
from __future__ import annotations

import asyncio
from typing import Any, Dict

import pytest

from app.api.routers import novels as novels_router


def test_normalize_blueprint_job_payload_defaults_metrics():
    payload = novels_router._normalize_blueprint_job_payload(
        {
            "run_id": "r1",
            "project_id": "p1",
            "status": "generating",
            "progress_stage": "generating",
            "progress_message": "working",
        }
    )
    assert payload["metrics"]["retry_count"] == 0
    assert payload["metrics"]["llm_call_count"] == 0
    assert payload["metrics"]["degraded"] is False
    assert payload["metrics"]["retry_events"] == []


@pytest.mark.asyncio
async def test_set_blueprint_job_state_merges_retry_metrics(monkeypatch):
    run_id = "run-metrics-1"
    novels_router._BLUEPRINT_JOBS[run_id] = {
        "run_id": run_id,
        "project_id": "p-metrics",
        "user_id": 1,
        "status": "generating",
        "progress_stage": "generating",
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

    monkeypatch.setattr(novels_router, "_persist_blueprint_job_state", fake_persist)

    await novels_router._set_blueprint_job_state(
        run_id,
        metrics={
            "retry_count": 1,
            "llm_call_count": 2,
            "degraded": True,
            "last_retry_reason": "provider_jitter",
            "last_retry_stage": "蓝图生成",
            "retry_events": [{"stage": "蓝图生成", "reason": "provider_jitter"}],
            "stage_attempts": {"蓝图生成": 1},
        },
    )
    await novels_router._set_blueprint_job_state(
        run_id,
        metrics={
            "retry_count": 2,
            "llm_call_count": 3,
            "degraded": True,
            "retry_events": [{"stage": "章节大纲", "reason": "json_repair"}],
            "stage_attempts": {"章节大纲": 1},
        },
    )

    metrics = novels_router._BLUEPRINT_JOBS[run_id]["metrics"]
    assert metrics["retry_count"] == 2
    assert metrics["llm_call_count"] == 3
    assert metrics["degraded"] is True
    assert len(metrics["retry_events"]) == 2
    assert metrics["stage_attempts"]["蓝图生成"] == 1
    assert metrics["stage_attempts"]["章节大纲"] == 1
    assert persisted, "should persist metrics updates"

    # cleanup
    novels_router._BLUEPRINT_JOBS.pop(run_id, None)


def test_serialize_blueprint_job_includes_metrics():
    response = novels_router._serialize_blueprint_job(
        {
            "run_id": "r2",
            "project_id": "p2",
            "status": "generating",
            "progress_stage": "generating",
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
