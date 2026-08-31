"""Redacted calibration for T-09 static/action paragraph detection.

The report contains counts and percentiles only; chapter prose is never emitted or stored.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.pipeline_orchestrator import PipelineOrchestrator


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * weight, 4)


def summarize(db_path: Path) -> dict:
    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute("SELECT id, content FROM chapter_versions WHERE content IS NOT NULL").fetchall()
    finally:
        connection.close()

    static_rates: list[float] = []
    max_runs: list[float] = []
    static_counts: list[float] = []
    eligible_paragraphs = 0
    action_paragraphs = 0
    ambient_only_paragraphs = 0
    version_summaries = []

    for version_id, content in rows:
        paragraphs = [line for line in str(content or "").splitlines() if line.strip()]
        eligible = ["".join(line.split()) for line in paragraphs if len("".join(line.split())) >= 100]
        runs = PipelineOrchestrator._estimate_static_description_runs(paragraphs)
        eligible_count = len(eligible)
        static_count = int(runs.get("static_paragraph_count") or 0)
        eligible_paragraphs += eligible_count
        static_counts.append(float(static_count))
        max_runs.append(float(runs.get("max_static_run") or 0))
        if eligible_count:
            static_rates.append(round(static_count / eligible_count, 4))
        for paragraph in eligible:
            has_action = PipelineOrchestrator._paragraph_has_character_action(paragraph)
            if has_action:
                action_paragraphs += 1
            elif any(marker in paragraph for marker in PipelineOrchestrator.AMBIENT_MOTION_MARKERS):
                ambient_only_paragraphs += 1
        version_summaries.append({
            "version_id": int(version_id),
            "word_count": PipelineOrchestrator._count_words(str(content or "")),
            "eligible_paragraph_count": eligible_count,
            "static_paragraph_count": static_count,
            "max_static_run": int(runs.get("max_static_run") or 0),
        })

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_path": str(db_path),
        "redaction": {"content_emitted": False, "version_detail_emitted": False},
        "ground_truth": {"available": False, "precision": None, "recall": None},
        "record_count": len(rows),
        "eligible_paragraph_count": eligible_paragraphs,
        "character_action_paragraph_count": action_paragraphs,
        "ambient_only_static_paragraph_count": ambient_only_paragraphs,
        "static_rate": {
            "p05": percentile(static_rates, 0.05),
            "p50": percentile(static_rates, 0.50),
            "p95": percentile(static_rates, 0.95),
            "mean": round(mean(static_rates), 4) if static_rates else None,
        },
        "static_paragraph_count": {
            "p05": percentile(static_counts, 0.05),
            "p50": percentile(static_counts, 0.50),
            "p95": percentile(static_counts, 0.95),
        },
        "max_static_run": {
            "p05": percentile(max_runs, 0.05),
            "p50": percentile(max_runs, 0.50),
            "p95": percentile(max_runs, 0.95),
        },
        "interpretation": "无人工主体动作标注，统计只能校准分布，不能证明精确率/召回率。",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=BACKEND_ROOT / "storage" / "xuanqiong_wenshu.db")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = summarize(args.db)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())