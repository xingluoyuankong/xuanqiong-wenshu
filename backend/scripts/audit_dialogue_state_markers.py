"""Read-only redacted audit for dialogue state-change marker coverage."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from statistics import quantiles
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.pipeline_orchestrator import PipelineOrchestrator


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return round(float(values[0]), 4)
    points = quantiles(values, n=100, method="inclusive")
    index = max(0, min(98, int(fraction * 100) - 1))
    return round(float(points[index]), 4)


def _decode(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def audit_database(database: Path) -> dict[str, Any]:
    connection = sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True)
    try:
        rows = connection.execute("SELECT content, metadata FROM chapter_versions WHERE content IS NOT NULL").fetchall()
    finally:
        connection.close()
    observations: list[dict[str, Any]] = []
    for content, raw_metadata in rows:
        text = str(content or "")
        word_count = PipelineOrchestrator._count_words(text)
        if word_count < 800:
            continue
        metadata = _decode(raw_metadata)
        mission = metadata.get("chapter_mission") if isinstance(metadata.get("chapter_mission"), dict) else None
        dialogue_markers = text.count("“") + text.count("”") + text.count("\"") + text.count("「") + text.count("」")
        marker_count = PipelineOrchestrator._count_dialogue_state_change_markers(text)
        expected = PipelineOrchestrator._chapter_mission_expects_dialogue(mission) if mission is not None else None
        observations.append({
            "word_count": word_count,
            "dialogue_markers": dialogue_markers,
            "state_change_markers": marker_count,
            "expected_dialogue": expected,
            "has_quality_metrics": isinstance(metadata.get("quality_metrics"), dict),
        })
    counts = [float(item["state_change_markers"]) for item in observations]
    with_dialogue = [item for item in observations if item["dialogue_markers"] > 0]
    expected_rows = [item for item in observations if item["expected_dialogue"] is not None]
    expected_true = [item for item in expected_rows if item["expected_dialogue"] is True]
    expected_false = [item for item in expected_rows if item["expected_dialogue"] is False]
    return {
        "source_rows": len(rows),
        "eligible_rows": len(observations),
        "quality_metric_rows": sum(item["has_quality_metrics"] for item in observations),
        "dialogue_rows": len(with_dialogue),
        "expected_dialogue_observed_rows": len(expected_rows),
        "expected_dialogue_true_rows": len(expected_true),
        "expected_dialogue_false_rows": len(expected_false),
        "marker_zero_rows": sum(item["state_change_markers"] == 0 for item in observations),
        "marker_nonzero_rows": sum(item["state_change_markers"] > 0 for item in observations),
        "marker_nonzero_rate_among_dialogue": round(sum(item["state_change_markers"] > 0 for item in with_dialogue) / len(with_dialogue), 4) if with_dialogue else None,
        "state_change_markers": {"p05": percentile(counts, 0.05), "p50": percentile(counts, 0.50), "p95": percentile(counts, 0.95), "max": max(counts) if counts else None},
        "expected_dialogue_marker_nonzero_rate": {
            "true": round(sum(item["state_change_markers"] > 0 for item in expected_true) / len(expected_true), 4) if expected_true else None,
            "false": round(sum(item["state_change_markers"] > 0 for item in expected_false) / len(expected_false), 4) if expected_false else None,
        },
        "method": "word_count>=800; content never emitted; expected_dialogue read from chapter_mission only when present",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    payload = audit_database(args.database)
    encoded = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
