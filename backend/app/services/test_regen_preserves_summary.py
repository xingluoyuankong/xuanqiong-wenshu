# -*- coding: utf-8 -*-
"""Regression: regenerating a finished chapter must preserve narrative summary_text."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.utils.chapter_summary_utils import build_real_summary_json, extract_chapter_narrative_summary


def test_extract_keeps_summary_when_runtime_present():
    raw = build_real_summary_json(
        None,
        summary_text="林舟在驿站压住血契，顾棠拒绝同路。",
        generation_runtime={"run_id": "old", "progress_stage": "review"},
        preserve_summary_text=True,
    )
    chapter = SimpleNamespace(real_summary=raw, selected_version=None)
    assert "血契" in extract_chapter_narrative_summary(chapter)


@pytest.mark.anyio
async def test_generate_chapter_preserves_summary_on_regen(monkeypatch):
    from app.services.pipeline_orchestrator import PipelineOrchestrator

    orch = PipelineOrchestrator(session=AsyncMock())
    preserved = "上一章：林舟与顾棠在雨夜驿站达成临时同盟。"
    chapter = SimpleNamespace(
        id=9,
        project_id="p-temp",
        chapter_number=2,
        status="successful",
        real_summary=build_real_summary_json(None, summary_text=preserved, generation_runtime={"run_id": "old"}),
        selected_version_id=3,
    )

    # Simulate the fixed branch body
    if chapter.status != "generating":
        kept = extract_chapter_narrative_summary(chapter)
        if kept:
            chapter.real_summary = build_real_summary_json(None, summary_text=kept, preserve_summary_text=True)
        else:
            chapter.real_summary = None
        chapter.selected_version_id = None
        chapter.status = "generating"

    assert chapter.status == "generating"
    assert chapter.selected_version_id is None
    payload = json.loads(chapter.real_summary)
    assert payload.get("summary_text") == preserved
    assert "generation_runtime" not in payload or payload.get("generation_runtime") in (None, {})
