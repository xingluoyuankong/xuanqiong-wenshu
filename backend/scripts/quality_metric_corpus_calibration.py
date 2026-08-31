"""Redacted corpus calibration for E-02..E-05 quality observables."""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
from app.services.pipeline_orchestrator import PipelineOrchestrator


def _decode_metadata(raw: object) -> dict:
    """Decode optional version metadata without letting one bad row stop calibration."""
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _load_content_rows(db_path: Path) -> list[tuple[object, object]]:
    """Read content plus optional metadata, falling back for legacy test databases."""
    con = sqlite3.connect(db_path)
    try:
        try:
            return con.execute(
                "SELECT content, metadata FROM chapter_versions WHERE content IS NOT NULL"
            ).fetchall()
        except sqlite3.OperationalError as exc:
            if "no such column" not in str(exc).lower():
                raise
            return [
                (content, None)
                for (content,) in con.execute(
                    "SELECT content FROM chapter_versions WHERE content IS NOT NULL"
                ).fetchall()
            ]
    finally:
        con.close()


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower), 4)


def summarize(values: list[float]) -> dict:
    return {"p05": percentile(values, .05), "p50": percentile(values, .50), "p95": percentile(values, .95)}


def run(db_path: Path) -> dict:
    rows = _load_content_rows(db_path)
    reversal_counts: list[float] = []
    late_reversal: list[float] = []
    dialogue_ratios: list[float] = []
    action_ratios: list[float] = []
    description_ratios: list[float] = []
    speaker_counts: list[float] = []
    dominant_ratios: list[float] = []
    hard_cut_counts: list[float] = []
    summary_cut_counts: list[float] = []
    speaker_observed = 0
    transition_warning = 0
    for content, raw_metadata in rows:
        text = str(content or "")
        paragraphs = [item for item in text.splitlines() if item.strip()]
        word_count = PipelineOrchestrator._count_words(text)
        metadata = _decode_metadata(raw_metadata)
        chapter_mission = metadata.get("chapter_mission")
        focus_character_names = PipelineOrchestrator._collect_focus_character_names(
            chapter_mission if isinstance(chapter_mission, dict) else None
        )
        reversal = PipelineOrchestrator._evaluate_reversal_quality(text)
        balance = PipelineOrchestrator._evaluate_content_balance(
            paragraphs,
            word_count=word_count,
            character_names=focus_character_names,
        )
        speaker = PipelineOrchestrator._evaluate_dialogue_speaker_distribution(text)
        transition = PipelineOrchestrator._evaluate_scene_transition_clarity(paragraphs)
        reversal_counts.append(float(reversal.get("reversal_signal_count") or 0))
        late_reversal.append(1.0 if reversal.get("reversal_in_late_section") else 0.0)
        dialogue_ratios.append(float(balance.get("dialogue_ratio") or 0))
        action_ratios.append(float(balance.get("action_ratio") or 0))
        description_ratios.append(float(balance.get("description_ratio") or 0))
        speaker_counts.append(float(speaker.get("speaker_count") or 0))
        if speaker.get("speaker_count"):
            speaker_observed += 1
            dominant_ratios.append(float(speaker.get("dominant_speaker_ratio") or 0))
        hard_cut_counts.append(float(transition.get("hard_scene_cut_count") or 0))
        summary_cut_counts.append(float(transition.get("summary_scene_cut_count") or 0))
        if transition.get("scene_transition_warning"):
            transition_warning += 1
    n = len(rows)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "record_count": n,
        "redaction": {"content_emitted": False, "speaker_names_emitted": False},
        "E02_reversal": {"signal_count": summarize(reversal_counts), "late_section_rate": round(sum(late_reversal) / n, 4) if n else None},
        "E03_speaker_distribution": {"speaker_count": summarize(speaker_counts), "dominant_speaker_ratio": summarize(dominant_ratios), "speaker_observed_rate": round(speaker_observed / n, 4) if n else None},
        "E04_content_balance": {"dialogue_ratio": summarize(dialogue_ratios), "action_ratio": summarize(action_ratios), "description_ratio": summarize(description_ratios)},
        "E05_scene_transition": {"hard_cut_count": summarize(hard_cut_counts), "summary_cut_count": summarize(summary_cut_counts), "warning_rate": round(transition_warning / n, 4) if n else None},
        "limitations": ["版本没有人工标签，分布不等于质量真值。", "场景任务书未与历史版本可靠关联，E-05 只校准正文观测字段。"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=BACKEND_ROOT / "storage" / "xuanqiong_wenshu.db")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = run(args.db)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())