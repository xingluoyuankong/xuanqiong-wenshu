from __future__ import annotations

import inspect
import json

import pytest

from app.services.pipeline_orchestrator import PipelineOrchestrator


class _Session:
    async def refresh(self, _chapter):
        return None

    async def commit(self):
        return None


class _Chapter:
    chapter_number = 1

    def __init__(self):
        self.real_summary = json.dumps({"generation_runtime": {"run_id": "run-callback", "events": []}})


def test_generate_chapter_accepts_runtime_event_callback_contract():
    signature = inspect.signature(PipelineOrchestrator.generate_chapter)
    assert "runtime_event_callback" in signature.parameters


@pytest.mark.asyncio
async def test_runtime_update_forwards_persisted_event_to_worker_callback():
    received = []

    async def callback(event):
        received.append(event)

    orchestrator = object.__new__(PipelineOrchestrator)
    orchestrator.session = _Session()
    orchestrator._runtime_event_callback = callback
    chapter = _Chapter()

    await orchestrator._update_generation_runtime(
        chapter, generation_run_id="run-callback", stage="generate_variants",
        message="候选生成中", progress_percent=62, event_kind="progress",
        title="候选生成", summary="候选正文正在生成", extra={"candidate_count": 3},
    )

    assert len(received) == 1
    assert received[0]["event_type"] == "progress"
    assert received[0]["stage"] == "generate_variants"
    assert received[0]["progress"] == 62
    assert received[0]["payload"]["metadata"]["candidate_count"] == 3


@pytest.mark.asyncio
async def test_runtime_event_callback_failure_does_not_abort_generation_update():
    async def broken_callback(_event):
        raise RuntimeError("event mirror unavailable")

    orchestrator = object.__new__(PipelineOrchestrator)
    orchestrator.session = _Session()
    orchestrator._runtime_event_callback = broken_callback
    chapter = _Chapter()

    await orchestrator._update_generation_runtime(
        chapter, generation_run_id="run-callback", stage="review",
        message="评审中", progress_percent=72, event_kind="progress",
    )

    runtime = json.loads(chapter.real_summary)["generation_runtime"]
    assert runtime["progress_stage"] == "review"
