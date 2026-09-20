#!/usr/bin/env python3
"""Report generation pipeline p50/p95 latency from persisted logs."""
from __future__ import annotations
import argparse
import ast
import glob
import json
import re
from pathlib import Path
from statistics import median
from typing import Any

TOTAL_RE = re.compile(r"Pipeline total duration: .*? duration_ms=(?P<duration>[0-9.]+) stages=(?P<stages>\{.*\})")

def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * p
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    weight = rank - low
    return ordered[low] + (ordered[high] - ordered[low]) * weight

def stats(values: list[float]) -> dict[str, Any]:
    return {
        "count": len(values),
        "min_ms": round(min(values), 2) if values else None,
        "p50_ms": round(median(values), 2) if values else None,
        "p95_ms": round(percentile(values, 0.95), 2) if values else None,
        "max_ms": round(max(values), 2) if values else None,
    }

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--glob",
        action="append",
        dest="globs",
        help="Log glob; repeat for multiple roots. Defaults to backend/logs and deployed service logs.",
    )
    parser.add_argument("--output", default="-")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    globs = args.globs or ["backend/logs/**/*.log", "logs/**/*.log"]
    files = sorted({path for pattern in globs for path in root.glob(pattern)})
    totals: list[float] = []
    stages: dict[str, list[float]] = {}
    source_files: set[str] = set()
    parse_errors: list[str] = []
    for path in files:
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            parse_errors.append(f"{path}:{type(exc).__name__}")
            continue
        for line in lines:
            match = TOTAL_RE.search(line)
            if not match:
                continue
            try:
                duration = float(match.group("duration"))
                stage_payload = ast.literal_eval(match.group("stages"))
                if not isinstance(stage_payload, dict):
                    raise ValueError("stages is not a dict")
            except Exception as exc:  # noqa: BLE001
                parse_errors.append(f"{path}:{type(exc).__name__}")
                continue
            totals.append(duration)
            source_files.add(str(path.relative_to(root)))
            for stage, value in stage_payload.items():
                if isinstance(value, (int, float)):
                    stages.setdefault(str(stage), []).append(float(value))
    result = {
        "report_type": "generation_latency_summary",
        "globs": globs,
        "source_file_count": len(source_files),
        "source_files": sorted(source_files),
        "total_pipeline": stats(totals),
        "stages": {stage: stats(values) for stage, values in sorted(stages.items())},
        "parse_errors": parse_errors,
        "status": "PASS" if totals and not parse_errors else ("EMPTY" if not totals else "PARTIAL"),
    }
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output == "-":
        print(rendered, end="")
    else:
        (root / args.output).write_text(rendered, encoding="utf-8")
    return 0 if result["status"] == "PASS" else 10

if __name__ == "__main__":
    raise SystemExit(main())