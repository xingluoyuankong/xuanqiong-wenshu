"""Redacted historical-vs-current scorer comparison; never emits chapter prose."""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import sqlite3
import subprocess
import sys
import types
from collections import Counter
from pathlib import Path
from statistics import quantiles
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OLD_COMMIT = "3e6406070af5a391deed7427198258691dd85ece^"


def _load_old_class() -> type:
    source = subprocess.check_output(
        ["git", "show", f"{OLD_COMMIT}:backend/app/services/pipeline_orchestrator.py"],
        cwd=ROOT.parent,
        text=True,
        encoding="utf-8",
    )
    module_name = "app.services._legacy_historical_scorer_probe"
    module = types.ModuleType(module_name)
    module.__package__ = "app.services"
    module.__file__ = f"<git:{OLD_COMMIT}>"
    sys.modules[module_name] = module
    try:
        exec(compile(source, module.__file__, "exec"), module.__dict__)
        return module.PipelineOrchestrator
    finally:
        sys.modules.pop(module_name, None)


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


def _config(metadata: dict[str, Any]) -> tuple[int, int]:
    mission = metadata.get("chapter_mission") if isinstance(metadata.get("chapter_mission"), dict) else {}
    contract = mission.get("chapter_draft_contract") if isinstance(mission.get("chapter_draft_contract"), dict) else {}
    metrics = metadata.get("quality_metrics") if isinstance(metadata.get("quality_metrics"), dict) else {}
    target = contract.get("target_word_count", metrics.get("target_word_count", 0))
    minimum = contract.get("min_word_count", metrics.get("min_word_count", 0))
    try:
        return max(0, int(target or 0)), max(0, int(minimum or 0))
    except (TypeError, ValueError):
        return 0, 0


def _call(scorer: type, *, content: str, metadata: dict[str, Any]) -> dict[str, Any]:
    mission = metadata.get("chapter_mission") if isinstance(metadata.get("chapter_mission"), dict) else None
    guardrail = metadata.get("guardrail") if isinstance(metadata.get("guardrail"), dict) else {}
    violations = guardrail.get("violations") if isinstance(guardrail.get("violations"), list) else []
    target, minimum = _config(metadata)
    fn = scorer._score_story_quality_candidate
    kwargs: dict[str, Any] = {"content": content, "violations": violations, "chapter_mission": mission}
    parameters = inspect.signature(fn).parameters
    if "target_word_count" in parameters:
        kwargs["target_word_count"] = target
    if "min_word_count" in parameters:
        kwargs["min_word_count"] = minimum
    return fn(**kwargs)


def _percentiles(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"p05": None, "p50": None, "p95": None}
    if len(values) == 1:
        return {"p05": values[0], "p50": values[0], "p95": values[0]}
    points = quantiles(values, n=20, method="inclusive")
    return {"p05": round(points[0], 4), "p50": round(points[9], 4), "p95": round(points[18], 4)}


def audit(database: Path) -> dict[str, Any]:
    from app.services.pipeline_orchestrator import PipelineOrchestrator

    old = _load_old_class()
    connection = sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True)
    try:
        rows = connection.execute("SELECT id, content, metadata FROM chapter_versions WHERE content IS NOT NULL ORDER BY id").fetchall()
    finally:
        connection.close()
    comparable: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    code_delta: Counter[str] = Counter()
    for version_id, content, raw_metadata in rows:
        metadata = _decode(raw_metadata)
        try:
            before = _call(old, content=str(content or ""), metadata=metadata)
            after = _call(PipelineOrchestrator, content=str(content or ""), metadata=metadata)
            old_codes = set(before.get("quality_issue_codes") or [])
            new_codes = set(after.get("quality_issue_codes") or [])
            for code in sorted(new_codes - old_codes): code_delta[f"added:{code}"] += 1
            for code in sorted(old_codes - new_codes): code_delta[f"removed:{code}"] += 1
            comparable.append({
                "version_id": int(version_id),
                "content_sha256": hashlib.sha256(str(content or "").encode("utf-8")).hexdigest(),
                "target_word_count": _config(metadata)[0],
                "min_word_count": _config(metadata)[1],
                "old_score": before.get("score"),
                "current_score": after.get("score"),
                "score_delta": (after.get("score") - before.get("score")) if isinstance(after.get("score"), (int, float)) and isinstance(before.get("score"), (int, float)) else None,
                "old_issue_codes": sorted(old_codes),
                "current_issue_codes": sorted(new_codes),
            })
        except Exception as exc:
            failures.append({"version_id": int(version_id), "error_type": type(exc).__name__, "error": str(exc)[:240]})
    deltas = [float(item["score_delta"]) for item in comparable if isinstance(item.get("score_delta"), (int, float))]
    old_scores = [float(item["old_score"]) for item in comparable if isinstance(item.get("old_score"), (int, float))]
    current_scores = [float(item["current_score"]) for item in comparable if isinstance(item.get("current_score"), (int, float))]
    return {
        "kind": "historical_scorer_behavior_delta_not_quality_ground_truth",
        "database": database.name,
        "old_commit": OLD_COMMIT,
        "source_rows": len(rows),
        "comparable_rows": len(comparable),
        "failed_rows": failures,
        "old_score": {"average": round(sum(old_scores) / len(old_scores), 4) if old_scores else None, **_percentiles(old_scores)},
        "current_score": {"average": round(sum(current_scores) / len(current_scores), 4) if current_scores else None, **_percentiles(current_scores)},
        "score_delta": {"average": round(sum(deltas) / len(deltas), 4) if deltas else None, **_percentiles(deltas)},
        "issue_code_delta_counts": dict(sorted(code_delta.items())),
        "rows": comparable,
        "limitations": [
            "这是同一历史正文的评分器行为差异，不是改前/改后真实生成质量对照。",
            "没有人工标签，不代表质量提升、误杀率或用户偏好。",
            "正文只通过 content_sha256 关联，未写入输出。",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    payload = audit(args.database)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("source_rows", "comparable_rows", "failed_rows", "old_score", "current_score", "score_delta", "issue_code_delta_counts")}, ensure_ascii=False, indent=2))
    return 0 if not payload["failed_rows"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
