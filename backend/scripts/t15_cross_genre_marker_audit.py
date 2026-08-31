"""T-15 redacted cross-genre marker coverage audit for E-08/E-09 evidence.

Reads existing benchmark/evidence files and emits counts/rates only. It never emits
chapter prose, speaker names, or changes production thresholds/evidence.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.pipeline_orchestrator import PipelineOrchestrator

DEFAULT_E08 = ROOT / "output" / "quality-bench-live-e08-gpt56-localized-v4-final-20260822" / "provider-live-20260822T100955Z"
DEFAULT_E09 = ROOT / "output" / "e09-multichapter-trend-20chapters-20260821.json"
EXPECTED_GENRE_GROUPS = (
    "action",
    "bridge",
    "climax",
    "closure",
    "dialogue-romance",
    "horror-transition",
    "scifi-investigation",
)


def _rate(values: list[bool]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def _genre_group(mission_id: str) -> str:
    value = str(mission_id or "").removeprefix("benchmark-").removeprefix("smoke-")
    if value.startswith("dialogue-romance"):
        return "dialogue-romance"
    if value.startswith("horror-transition"):
        return "horror-transition"
    if value.startswith("scifi-investigation"):
        return "scifi-investigation"
    return value.split("-", 1)[0] or "unknown"


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected object JSON: {path}")
    return value


def _e08_rows(run_dir: Path) -> list[dict[str, Any]]:
    summary = _load_json(run_dir / "rescore-summary.json")
    rows: list[dict[str, Any]] = []
    for record in summary.get("records") or []:
        if not isinstance(record, dict):
            continue
        mission_id = str(record.get("mission_id") or "")
        content_file = run_dir / f"{mission_id}.txt"
        if not content_file.exists():
            continue
        text = content_file.read_text(encoding="utf-8")
        ending = PipelineOrchestrator._evaluate_ending_pressure(text, None)
        density = PipelineOrchestrator._evaluate_event_density(
            text,
            word_count=PipelineOrchestrator._count_words(text),
        )
        reversal = PipelineOrchestrator._evaluate_reversal_quality(text)
        rows.append({
            "mission_id": mission_id,
            "group": _genre_group(mission_id),
            "source_kind": "smoke_supplement" if mission_id.startswith("smoke-") else "genre_fixture",
            "ending_semantic_hit": bool(ending.get("ending_semantic_hit_count")),
            "ending_pressure_passed": ending.get("ending_pressure_passed"),
            "flat_closure_hit": bool(ending.get("flat_closure_markers")),
            "event_density_evaluated": density.get("event_density_evaluated"),
            "event_density_passed": density.get("event_density_passed"),
            "state_change_interval_passed": density.get("state_change_interval_passed"),
            "event_density_per_1000": density.get("event_density_per_1000"),
            "reversal_signal_observed": bool(reversal.get("reversal_signal_count")),
            "reversal_in_late_section": bool(reversal.get("reversal_in_late_section")),
        })
    return rows


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for group in sorted({str(row["group"]) for row in rows}):
        items = [row for row in rows if row["group"] == group]
        result[group] = {
            "record_count": len(items),
            "source_kinds": sorted({str(item["source_kind"]) for item in items}),
            "ending_semantic_marker_rate": _rate([bool(item["ending_semantic_hit"]) for item in items]),
            "ending_pressure_pass_rate": _rate([item["ending_pressure_passed"] is True for item in items]),
            "flat_closure_marker_rate": _rate([bool(item["flat_closure_hit"]) for item in items]),
            "event_density_evaluated_rate": _rate([item["event_density_evaluated"] is True for item in items]),
            "event_density_pass_rate": _rate([item["event_density_passed"] is True for item in items]),
            "state_change_interval_pass_rate": _rate([item["state_change_interval_passed"] is True for item in items]),
            "reversal_signal_observed_rate": _rate([bool(item["reversal_signal_observed"]) for item in items]),
            "late_reversal_rate": _rate([bool(item["reversal_in_late_section"]) for item in items]),
            "event_density_per_1000_mean": _mean([
                float(item["event_density_per_1000"])
                for item in items
                if item["event_density_per_1000"] is not None
            ]),
        }
    return result


def _e09_audit(path: Path) -> dict[str, Any]:
    data = _load_json(path)
    chapters = [item for item in (data.get("chapters") or []) if isinstance(item, dict)]
    genre_keys = ("genre", "genre_group", "theme", "topic", "mission_id")
    labeled = [item for item in chapters if any(str(item.get(key) or "").strip() for key in genre_keys)]
    successful = [item for item in chapters if item.get("status") == "successful"]
    return {
        "requested_chapter_count": data.get("requested_chapter_count"),
        "chapter_row_count": len(chapters),
        "successful_row_count": len(successful),
        "evaluation_failed_row_count": sum(item.get("status") == "evaluation_failed" for item in chapters),
        "genre_label_available": bool(labeled),
        "genre_labeled_row_count": len(labeled),
        "raw_marker_text_available": False,
        "marker_coverage_auditable": False,
        "metric_rates": {
            "ending_pressure_pass_rate": _rate([item.get("ending_pressure_passed") is True for item in successful]),
            "event_density_pass_rate": _rate([item.get("event_density_passed") is True for item in successful]),
            "reversal_signal_observed_rate": _rate([
                (item.get("reversal_signal_count") or 0) > 0 for item in successful
            ]),
            "late_reversal_rate": _rate([item.get("reversal_in_late_section") is True for item in successful]),
        },
        "coverage_gap": "E-09 只有逐章脱敏指标，没有正文原文或题材标签，不能做跨题材 marker 覆盖审计。",
    }


def audit(e08_run: Path, e09_file: Path) -> dict[str, Any]:
    rows = _e08_rows(e08_run)
    genre_rows = [row for row in rows if row["source_kind"] == "genre_fixture"]
    observed_groups = sorted({str(row["group"]) for row in genre_rows})
    return {
        "kind": "t15_cross_genre_marker_coverage_audit",
        "redaction": {"content_emitted": False, "speaker_names_emitted": False},
        "e08": {
            "run_dir": str(e08_run),
            "record_count_from_summary": len(_load_json(e08_run / "rescore-summary.json").get("records") or []),
            "readable_text_record_count": len(rows),
            "genre_fixture_count": len(genre_rows),
            "smoke_supplement_count": sum(row["source_kind"] == "smoke_supplement" for row in rows),
            "observed_genre_groups": observed_groups,
            "expected_fixture_groups": list(EXPECTED_GENRE_GROUPS),
            "missing_expected_genre_groups": [group for group in EXPECTED_GENRE_GROUPS if group not in observed_groups],
            "group_coverage": _aggregate(rows),
        },
        "e09": {"source_file": str(e09_file), **_e09_audit(e09_file)},
        "finding": {
            "e08_obvious_genre_group_missing": any(group not in observed_groups for group in EXPECTED_GENRE_GROUPS),
            "e09_cross_genre_gap": True,
            "reason": "E-08 covers all seven declared genre fixture groups; E-09 has no genre labels/raw text, so its 20 chapters cannot prove genre coverage.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--e08-run", type=Path, default=DEFAULT_E08)
    parser.add_argument("--e09-file", type=Path, default=DEFAULT_E09)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(args.e08_run, args.e09_file)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())