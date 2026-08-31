"""Redacted corpus calibration for dialogue state marker semantic categories."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.pipeline_orchestrator import PipelineOrchestrator

CATEGORY_MARKERS = {
    "revelation": ("发现", "意识到", "暴露", "泄露", "承认", "消息", "名单"),
    "choice": ("决定", "选择", "让步", "改口", "交换", "条件", "代价", "退路"),
    "external_pressure": ("威胁", "压迫", "危险", "风险", "失控", "打断", "逼问", "反制", "翻脸"),
}


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


def _hit_categories(text: str) -> dict[str, bool]:
    value = str(text or "")
    return {category: any(marker in value for marker in markers) for category, markers in CATEGORY_MARKERS.items()}


def audit_database(database: Path) -> dict[str, Any]:
    connection = sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True)
    try:
        rows = connection.execute("SELECT content, metadata FROM chapter_versions WHERE content IS NOT NULL").fetchall()
    finally:
        connection.close()

    observations: list[dict[str, Any]] = []
    for content, raw_metadata in rows:
        text = str(content or "")
        if PipelineOrchestrator._count_words(text) < 800:
            continue
        metadata = _decode(raw_metadata)
        mission = metadata.get("chapter_mission") if isinstance(metadata.get("chapter_mission"), dict) else None
        expected = PipelineOrchestrator._chapter_mission_expects_dialogue(mission) if mission is not None else None
        dialogue_markers = sum(text.count(mark) for mark in ("“", "”", '"', "「", "」"))
        categories = _hit_categories(text)
        observations.append({"expected_dialogue": expected, "dialogue_markers": dialogue_markers, **categories})

    category_counts = Counter()
    for item in observations:
        for category in CATEGORY_MARKERS:
            if item[category]:
                category_counts[category] += 1

    declared = [item for item in observations if item["expected_dialogue"] is True]
    undeclared = [item for item in observations if item["expected_dialogue"] is False]
    with_dialogue = [item for item in observations if item["dialogue_markers"] > 0]

    def rates(rows_to_measure: list[dict[str, Any]]) -> dict[str, float | None]:
        return {
            category: round(sum(item[category] for item in rows_to_measure) / len(rows_to_measure), 4) if rows_to_measure else None
            for category in CATEGORY_MARKERS
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_rows": len(rows),
        "eligible_rows": len(observations),
        "dialogue_rows": len(with_dialogue),
        "expected_dialogue_true_rows": len(declared),
        "expected_dialogue_false_rows": len(undeclared),
        "category_marker_counts": dict(sorted(category_counts.items())),
        "category_hit_rates": {
            "all_eligible": rates(observations),
            "declared_dialogue": rates(declared),
            "undeclared_dialogue": rates(undeclared),
            "dialogue_rows_only": rates(with_dialogue),
        },
        "total_marker_nonzero_rate": round(sum(PipelineOrchestrator._count_dialogue_state_change_markers(str(content or "")) > 0 for content, _ in rows if PipelineOrchestrator._count_words(str(content or "")) >= 800) / len(observations), 4) if observations else None,
        "redaction": {"content_emitted": False, "marker_examples_emitted": False},
        "limitations": [
            "分类是对现有确定性词表的脱敏覆盖统计，不是人工语义真值。",
            "expected_dialogue_false_rows 为 0 时，未声明分支不能据此调阈值。",
            "命中率高不等于对话真正改变局势，仍需人工标签或真实行为对照。",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = audit_database(args.database)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("source_rows", "eligible_rows", "expected_dialogue_true_rows", "expected_dialogue_false_rows", "category_marker_counts", "category_hit_rates")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())