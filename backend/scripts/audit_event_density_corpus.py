"""Read-only redacted calibration for event-density thresholds."""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
import sys
from statistics import quantiles
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from app.services.pipeline_orchestrator import PipelineOrchestrator


def percentile(values: list[float], fraction: float) -> float | None:
    if not values: return None
    if len(values) == 1: return round(float(values[0]), 4)
    points = quantiles(values, n=100, method="inclusive")
    index = max(0, min(98, int(fraction * 100) - 1))
    return round(float(points[index]), 4)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    conn = sqlite3.connect(f"file:{args.database.resolve()}?mode=ro", uri=True)
    rows = conn.execute("SELECT content FROM chapter_versions WHERE content IS NOT NULL").fetchall()
    metrics: list[dict[str, Any]] = []
    for (content,) in rows:
        text = str(content or "")
        word_count = PipelineOrchestrator._count_words(text)
        if word_count < 800: continue
        result = PipelineOrchestrator._evaluate_event_density(text, word_count=word_count)
        metrics.append({
            "word_count": word_count,
            "event_density_per_1000": float(result.get("event_density_per_1000") or 0),
            "progression_unit_rate": float(result.get("progression_unit_rate") or 0),
            "max_plain_unit_run_ratio": float(result.get("max_plain_unit_run_ratio") or 0),
            "event_density_passed": result.get("event_density_passed"),
        })
    density = [item["event_density_per_1000"] for item in metrics]
    progression = [item["progression_unit_rate"] for item in metrics]
    plain_run = [item["max_plain_unit_run_ratio"] for item in metrics]
    payload = {
        "source_rows": len(rows),
        "eligible_rows": len(metrics),
        "pass_rate": round(sum(item["event_density_passed"] is True for item in metrics) / len(metrics), 4) if metrics else None,
        "event_density_per_1000": {"p05": percentile(density, 0.05), "p50": percentile(density, 0.50), "p95": percentile(density, 0.95)},
        "progression_unit_rate": {"p05": percentile(progression, 0.05), "p50": percentile(progression, 0.50), "p95": percentile(progression, 0.95)},
        "max_plain_unit_run_ratio": {"p05": percentile(plain_run, 0.05), "p50": percentile(plain_run, 0.50), "p95": percentile(plain_run, 0.95)},
    }
    encoded=json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output: args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(encoded, encoding="utf-8")
    print(encoded)
    return 0


if __name__ == "__main__": raise SystemExit(main())
