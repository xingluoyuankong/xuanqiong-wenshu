from __future__ import annotations

import pytest

from app.services.novel_context_snapshot_service import ContextSelectionRequest, ContextSnapshotBuilder, ContextSnapshotSelectionError


def _records():
    return [
        {"project_id": "p", "ref_type": "project", "ref_key": "p", "reason_code": "current_scope", "summary": "项目"},
        {"project_id": "p", "ref_type": "chapter", "ref_key": "chapter:10", "chapter_number": 10, "text_units": 100, "reason_code": "recent_continuity"},
        {"project_id": "p", "ref_type": "quality", "ref_key": "finding:1", "chapter_number": 9, "text_units": 20, "reason_code": "quality_blocker", "conflict": True},
    ]


def test_builder_selects_with_budget_and_digest_is_reproducible():
    request = ContextSelectionRequest(project_id="p", target_chapter=10, max_text_units=110)
    builder = ContextSnapshotBuilder(request)
    first = builder.build(_records(), snapshot_id="snap-1")
    second = builder.build(_records(), snapshot_id="snap-1")
    assert first.estimated_text_units == 100
    assert [item.ref_key for item in first.selected] == ["p", "chapter:10"]
    assert first.compressed or first.excluded
    assert first.digest == second.digest
    assert len(first.conflicts) == 0


def test_builder_rejects_cross_project_and_future_records():
    builder = ContextSnapshotBuilder(ContextSelectionRequest(project_id="p", target_chapter=10))
    with pytest.raises(ContextSnapshotSelectionError, match="another project"):
        builder.build(_records() + [{"project_id": "other", "ref_type": "chapter", "ref_key": "other:1"}], snapshot_id="snap")
    with pytest.raises(ContextSnapshotSelectionError, match="future chapter"):
        builder.build(_records() + [{"project_id": "p", "ref_type": "chapter", "ref_key": "chapter:11", "chapter_number": 11}], snapshot_id="snap")


def test_builder_rejects_future_explicit_reference_even_if_not_selected():
    with pytest.raises(ContextSnapshotSelectionError, match="future chapter"):
        ContextSnapshotBuilder(ContextSelectionRequest(project_id="p", target_chapter=10, explicit_refs=({"project_id": "p", "chapter_number": 11, "ref_key": "chapter:11"},))).build([], snapshot_id="snap")
