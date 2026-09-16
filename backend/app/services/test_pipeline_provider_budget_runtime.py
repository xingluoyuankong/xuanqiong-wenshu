"""Regression coverage for chapter-level Provider budget runtime summaries."""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from app.services.generation_call_service import GenerationCallPolicy
from app.services import pipeline_orchestrator as pipeline_module
from app.services.pipeline_orchestrator import PipelineOrchestrator


class _Session:
    async def commit(self):
        return None

    async def refresh(self, _chapter):
        return None


class _Chapter:
    chapter_number = 1

    def __init__(self, run_id: str = "provider-budget-run"):
        self.real_summary = json.dumps({"generation_runtime": {"run_id": run_id, "events": []}})


@pytest.mark.asyncio
async def test_generation_call_policy_tracks_logical_and_provider_attempt_totals():
    orchestrator = object.__new__(PipelineOrchestrator)
    orchestrator._begin_provider_budget_ledger(
        generation_run_id="provider-budget-run",
        project_id="project-1",
        chapter_number=1,
    )

    policy = orchestrator._track_generation_call_policy(
        GenerationCallPolicy(retry_attempts=2, response_format=None),
        role="draft_candidate_1",
    )
    assert policy.attempt_ledger is not None
    assert policy.attempt_ledger.run_id == "provider-budget-run"
    assert policy.attempt_role == "draft_candidate_1"

    first = policy.attempt_ledger.begin(
        role=policy.attempt_role,
        provider_ref="private-provider-reference",
        model_ref="private-model-reference",
    )
    policy.attempt_ledger.fail(first.attempt_id, category="TIMEOUT")
    second = policy.attempt_ledger.begin(
        role=policy.attempt_role,
        provider_ref="private-provider-reference",
        model_ref="private-model-reference",
        retry_index=1,
    )
    policy.attempt_ledger.finish(second.attempt_id, output="正文不会进入运行态摘要")

    summary = orchestrator._provider_budget_summary()
    assert summary["scope"] == "generation_call_service_direct_only"
    assert summary["logical_call_count"] == 1
    assert summary["provider_attempt_count"] == 2
    assert summary["succeeded_attempt_count"] == 1
    assert summary["failed_attempt_count"] == 1
    assert summary["cancelled_attempt_count"] == 0
    assert summary["retry_attempt_count"] == 1
    assert summary["fallback_attempt_count"] == 0
    assert summary["remaining_attempt_count"] == 62
    assert summary["latest_error_category"] == "TIMEOUT"
    assert summary["error_categories"] == {"TIMEOUT": 1}
    assert summary["roles"]["draft_candidate_1"] == {
        "logical_calls": 1,
        "provider_attempts": 2,
        "succeeded": 1,
        "failed": 1,
        "running": 0,
        "cancelled": 0,
    }
    serialized = json.dumps(summary, ensure_ascii=False)
    assert "private-provider-reference" not in serialized
    assert "private-model-reference" not in serialized
    assert "正文不会进入运行态摘要" not in serialized


@pytest.mark.asyncio
async def test_provider_budget_context_isolated_between_concurrent_chapters():
    async def collect(run_id: str, role: str):
        orchestrator = object.__new__(PipelineOrchestrator)
        orchestrator._begin_provider_budget_ledger(
            generation_run_id=run_id,
            project_id="project-1",
            chapter_number=1,
        )
        policy = orchestrator._track_generation_call_policy(
            GenerationCallPolicy(response_format=None), role=role
        )
        await asyncio.sleep(0)
        attempt = policy.attempt_ledger.begin(
            role=policy.attempt_role,
            provider_ref="fixture",
            model_ref="fixture",
        )
        policy.attempt_ledger.finish(attempt.attempt_id, output="fixture")
        return policy.attempt_ledger.run_id, orchestrator._provider_budget_summary()

    left, right = await asyncio.gather(
        collect("run-left", "draft_candidate_1"),
        collect("run-right", "continuation"),
    )

    assert left[0] == "run-left"
    assert right[0] == "run-right"
    assert left[1]["roles"] == {
        "draft_candidate_1": {
            "logical_calls": 1,
            "provider_attempts": 1,
            "succeeded": 1,
            "failed": 0,
            "running": 0,
            "cancelled": 0,
        }
    }
    assert right[1]["roles"] == {
        "continuation": {
            "logical_calls": 1,
            "provider_attempts": 1,
            "succeeded": 1,
            "failed": 0,
            "running": 0,
            "cancelled": 0,
        }
    }


@pytest.mark.asyncio
async def test_continuation_policy_carries_active_chapter_ledger(monkeypatch):
    orchestrator = object.__new__(PipelineOrchestrator)
    orchestrator.llm_service = object()
    orchestrator._begin_provider_budget_ledger(
        generation_run_id="continuation-budget-run",
        project_id="project-1",
        chapter_number=1,
    )
    observed = {}

    async def fake_call_generation_text(**kwargs):
        policy = kwargs["policy"]
        observed["policy"] = policy
        attempt = policy.attempt_ledger.begin(
            role=policy.attempt_role,
            provider_ref="fixture",
            model_ref="fixture",
        )
        policy.attempt_ledger.finish(attempt.attempt_id, output="续写正文")
        return SimpleNamespace(text="续写正文")

    monkeypatch.setattr(pipeline_module, "call_generation_text", fake_call_generation_text)
    result = await orchestrator._call_continuation_generation(
        writer_prompt="writer",
        conversation_history=[{"role": "user", "content": "continue"}],
        user_id=7,
        remaining_to_floor=300,
        minimum_increment=100,
        round_number=2,
    )

    assert result.text == "续写正文"
    assert observed["policy"].attempt_role == "continuation"
    assert observed["policy"].attempt_ledger.run_id == "continuation-budget-run"
    summary = orchestrator._provider_budget_summary()
    assert summary["logical_call_count"] == 1
    assert summary["provider_attempt_count"] == 1
    assert summary["roles"]["continuation"]["succeeded"] == 1


@pytest.mark.asyncio
async def test_runtime_snapshot_contains_only_compact_provider_budget_summary():
    received = []

    async def callback(event):
        received.append(event)

    orchestrator = object.__new__(PipelineOrchestrator)
    orchestrator.session = _Session()
    orchestrator._runtime_event_callback = callback
    orchestrator._begin_provider_budget_ledger(
        generation_run_id="runtime-budget-run",
        project_id="project-1",
        chapter_number=1,
    )
    policy = orchestrator._track_generation_call_policy(
        GenerationCallPolicy(response_format=None), role="chapter_mission"
    )
    attempt = policy.attempt_ledger.begin(
        role=policy.attempt_role,
        provider_ref="private-provider",
        model_ref="private-model",
    )
    policy.attempt_ledger.finish(attempt.attempt_id, output="private-output")
    chapter = _Chapter("runtime-budget-run")

    summary = orchestrator._provider_budget_summary()
    await orchestrator._update_generation_runtime(
        chapter,
        generation_run_id="runtime-budget-run",
        stage="waiting_for_confirm",
        message="候选已完成",
        progress_percent=97,
        extra={"provider_budget": summary},
    )

    runtime = json.loads(chapter.real_summary)["generation_runtime"]
    assert runtime["provider_budget"]["provider_attempt_count"] == 1
    assert runtime["provider_budget"]["roles"]["chapter_mission"]["logical_calls"] == 1
    serialized = json.dumps(runtime, ensure_ascii=False)
    assert "private-provider" not in serialized
    assert "private-model" not in serialized
    assert "private-output" not in serialized
    assert received[0]["payload"]["metadata"]["provider_budget"]["provider_attempt_count"] == 1
