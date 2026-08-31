"""Read-only, redacted quality-trend audit for persisted chapter-version metadata."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.pipeline_orchestrator import PipelineOrchestrator


def _decode_json_object(raw: Any) -> dict[str, Any]:
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _backfill_story_progression_guard(
    metrics: dict[str, Any], metadata: dict[str, Any]
) -> dict[str, Any]:
    """Mirror the trend API's read-only story-guard backfill contract.

    Historical rows often keep the complete guard beside a compact
    ``quality_metrics`` snapshot. Fill only absent top-level metric keys;
    never mutate the stored snapshot and never copy the two nested snapshots
    whose contents are intentionally handled by their owning fields.
    """
    result = dict(metrics or {})
    story_guard = metadata.get("story_progression_guard")
    if not isinstance(story_guard, dict):
        return result
    excluded = {"quality_metric_snapshot", "quality_issue_summary"}
    for key, value in story_guard.items():
        if key in excluded or key in result:
            continue
        result[key] = value
    # Mirror the API's T-08/T-15 legacy nested-field flattening so the audit
    # cannot report a different observability contract than the trend endpoint.
    nested_sources = {
        "static_description_runs": ("static_paragraph_count", "max_static_run"),
        "ending_pressure": (
            "ending_pressure_passed",
            "ending_semantic_hit_count",
            "ending_weak_hit_count",
            "flat_closure_markers",
            "ending_core_chars",
            "ending_core_semantic_hit_count",
            "ending_core_weak_hit_count",
            "ending_core_deflating",
        ),
    }
    for source_key, target_keys in nested_sources.items():
        nested = result.get(source_key)
        if not isinstance(nested, dict):
            continue
        for key in target_keys:
            if result.get(key) is None and key in nested:
                result[key] = nested.get(key)
    return result


def audit_metadata_rows(rows: list[Any]) -> dict[str, Any]:
    """Aggregate redacted trend metadata using the API's selected-row semantics."""
    blocker_counts: Counter[str] = Counter()
    warning_counts: Counter[str] = Counter()
    issue_counts: Counter[str] = Counter()
    mission_quality_counts: Counter[str] = Counter()
    exemption_counts: Counter[str] = Counter()
    gate_source_counts: Counter[str] = Counter()
    runtime_gate_chapters: set[str] = set()
    observed = 0
    gate_rows = 0
    mission_rows = 0
    first_chapter_inherit_violations = 0
    continuity_observed_rows = 0
    continuity_missing_rows = 0
    continuity_late_rows = 0
    for raw_row in rows:
        chapter_id = None
        chapter_number = 1
        version_id = None
        selected_version_id = None
        has_selection_context = False
        if isinstance(raw_row, dict) and ("metadata" in raw_row or "real_summary" in raw_row):
            metadata = _decode_json_object(raw_row.get("metadata"))
            real_summary = _decode_json_object(raw_row.get("real_summary"))
            chapter_id = raw_row.get("chapter_id")
            chapter_number = int(raw_row.get("chapter_number") or 1)
            has_selection_context = "version_id" in raw_row and "selected_version_id" in raw_row
            version_id = raw_row.get("version_id")
            selected_version_id = raw_row.get("selected_version_id")
            content = raw_row.get("content")
        else:
            content = None
            metadata = _decode_json_object(raw_row)
            real_summary = {}

        # E-09: trend API reads one selected version per chapter.  Ignore
        # non-selected candidates when the caller supplies selection context;
        # rows without that context remain compatible with fixture callers.
        if has_selection_context and version_id is not None:
            if selected_version_id is None or str(version_id) != str(selected_version_id):
                continue

        raw_metrics = metadata.get("quality_metrics")
        metrics = _backfill_story_progression_guard(
            raw_metrics if isinstance(raw_metrics, dict) else {}, metadata
        )
        chapter_mission = metadata.get("chapter_mission")
        if metrics.get("mission_quality_codes") is None and isinstance(chapter_mission, dict):
            target_word_count = int(metrics.get("target_word_count") or 0)
            mission_quality = PipelineOrchestrator._evaluate_mission_quality(
                chapter_mission,
                target_word_count,
                chapter_number=max(1, chapter_number),
            )
            metrics["mission_quality_codes"] = list(
                mission_quality.get("mission_quality_codes") or []
            )
        continuity_keys = (
            "continuity_inherit_missing",
            "continuity_inherit_late",
            "continuity_inherit_hit_count",
            "inherit_hit_count",
            "continuity_inherit_total_hit_count",
            "continuity_inherit_match_mode",
        )
        if content is not None and isinstance(chapter_mission, dict):
            if any(metrics.get(key) is None for key in continuity_keys):
                continuity = PipelineOrchestrator._evaluate_continuity_inherit(
                    str(content), chapter_mission
                )
                for key in continuity_keys:
                    if metrics.get(key) is None and key in continuity:
                        metrics[key] = continuity.get(key)
        if metrics:
            observed += 1
            for code in metrics.get("quality_issue_codes") or []:
                issue_counts[str(code)] += 1
            if "mission_quality_codes" in metrics:
                mission_rows += 1
                mission_codes = [str(code) for code in metrics.get("mission_quality_codes") or []]
                for code in mission_codes:
                    mission_quality_counts[code] += 1
                if chapter_number == 1 and "mission_inherit_empty" in mission_codes:
                    first_chapter_inherit_violations += 1
        inherit_anchors = []
        if isinstance(chapter_mission, dict):
            continuity_anchor = chapter_mission.get("continuity_anchor")
            if isinstance(continuity_anchor, dict):
                inherit_anchors = [
                    item for item in (continuity_anchor.get("inherit_from_previous") or [])
                    if str(item).strip()
                ]
        if inherit_anchors and metrics.get("continuity_inherit_missing") is not None:
            continuity_observed_rows += 1
            continuity_missing_rows += int(bool(metrics.get("continuity_inherit_missing")))
            continuity_late_rows += int(bool(metrics.get("continuity_inherit_late")))

        gate = metadata.get("quality_gate")
        gate_source = "version_metadata" if isinstance(gate, dict) and gate else ""
        if not isinstance(gate, dict) or not gate:
            runtime = real_summary.get("generation_runtime") or {}
            candidate = runtime.get("quality_gate") if isinstance(runtime, dict) else None
            gate = candidate if isinstance(candidate, dict) else {}
            if gate:
                gate_source = "chapter_runtime"
        if not isinstance(gate, dict) or not gate:
            continue
        if gate_source == "chapter_runtime" and chapter_id is not None:
            runtime_key = str(chapter_id)
            if runtime_key in runtime_gate_chapters:
                continue
            runtime_gate_chapters.add(runtime_key)
        gate_rows += 1
        gate_source_counts[gate_source or "unknown"] += 1
        for item in gate.get("blockers") or []:
            if isinstance(item, dict) and item.get("code"):
                blocker_counts[str(item["code"])] += 1
        for item in gate.get("warnings") or []:
            if isinstance(item, dict) and item.get("code"):
                warning_counts[str(item["code"])] += 1
        for code in gate.get("exemptions") or []:
            exemption_counts[str(code)] += 1
    return {
        "quality_metric_rows": observed,
        "mission_quality_rows": mission_rows,
        "first_chapter_mission_inherit_violations": first_chapter_inherit_violations,
        "continuity_observed_rows": continuity_observed_rows,
        "continuity_missing_rows": continuity_missing_rows,
        "continuity_late_rows": continuity_late_rows,
        "gate_rows": gate_rows,
        "gate_source_counts": dict(sorted(gate_source_counts.items())),
        "blocker_counts": dict(sorted(blocker_counts.items())),
        "warning_counts": dict(sorted(warning_counts.items())),
        "quality_issue_counts": dict(sorted(issue_counts.items())),
        "mission_quality_counts": dict(sorted(mission_quality_counts.items())),
        "exemption_counts": dict(sorted(exemption_counts.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    connection = sqlite3.connect(f"file:{args.database.resolve()}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "SELECT chapters.id, chapters.chapter_number, chapters.selected_version_id, "
            "chapter_versions.id, chapter_versions.metadata, chapter_versions.content, chapters.real_summary "
            "FROM chapters LEFT JOIN chapter_versions "
            "ON chapters.selected_version_id = chapter_versions.id "
            "WHERE chapter_versions.metadata IS NOT NULL OR chapters.real_summary IS NOT NULL"
        ).fetchall()
    finally:
        connection.close()
    payload: dict[str, Any] = {
        "trend_chapter_rows": len(rows),
        "version_metadata_rows": sum(1 for _, _, _, _, raw, _, _ in rows if raw is not None),
        **audit_metadata_rows([
            {
                "chapter_id": chapter_id,
                "chapter_number": chapter_number,
                "selected_version_id": selected_version_id,
                "version_id": version_id,
                "metadata": raw,
                "content": content,
                "real_summary": summary,
            }
            for chapter_id, chapter_number, selected_version_id, version_id, raw, content, summary in rows
        ]),
    }
    encoded = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
