"""Generate and apply human adjudication decisions for a T-18 reviewer merge.

This module never chooses a label.  It only verifies that a human supplied one
for every disagreement emitted by ``merge_quality_annotations.py``.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

try:  # Package import for pytest/module use; direct import for `python scripts/...`.
    from scripts.merge_quality_annotations import CORE_LABELS, VALID
except ModuleNotFoundError:  # pragma: no cover - exercised by CLI smoke command.
    from merge_quality_annotations import CORE_LABELS, VALID

DECISION_COLUMNS = (
    "sample_id",
    "label",
    "reviewer_a_value",
    "reviewer_b_value",
    "adjudicated_value",
    "adjudicator_id",
    "adjudication_rationale",
)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path}: JSON root must be an object")
    return value


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _conflicts(merged: dict[str, Any]) -> list[dict[str, str]]:
    if merged.get("schema_version") != 1 or merged.get("valid") is not True:
        raise ValueError("merged input must be a valid schema_version 1 reviewer merge")
    rows = merged.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("merged input must contain at least one row")
    conflicts: list[dict[str, str]] = []
    for row_index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"merged row {row_index} must be an object")
        sample_id = str(row.get("sample_id") or "").strip()
        if not sample_id:
            raise ValueError(f"merged row {row_index} has no sample_id")
        for label in CORE_LABELS:
            if row.get(label) == "adjudicate":
                a = str(row.get(f"{label}_a") or "").strip().lower()
                b = str(row.get(f"{label}_b") or "").strip().lower()
                if a not in VALID or b not in VALID or a == b:
                    raise ValueError(f"{sample_id}: invalid disagreement source for {label}")
                conflicts.append({
                    "sample_id": sample_id,
                    "label": label,
                    "reviewer_a_value": a,
                    "reviewer_b_value": b,
                })
    return conflicts


def create_template(merged_file: Path, output_file: Path) -> dict[str, Any]:
    merged = _load_json(merged_file)
    conflicts = _conflicts(merged)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DECISION_COLUMNS)
        writer.writeheader()
        writer.writerows(conflicts)
    return {
        "merged_sha256": _digest(merged_file),
        "conflict_count": len(conflicts),
        "template_file": output_file.name,
        "status": "no_adjudication_needed" if not conflicts else "human_decisions_required",
    }


def _read_decisions(path: Path) -> tuple[dict[tuple[str, str], dict[str, str]], list[str], str | None]:
    errors: list[str] = []
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = {str(field or "").strip() for field in (reader.fieldnames or [])}
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        return {}, [f"cannot read decision CSV: {type(exc).__name__}"], None
    missing = sorted(set(DECISION_COLUMNS) - fieldnames)
    if missing:
        errors.append(f"decision CSV missing required columns: {missing}")
    decisions: dict[tuple[str, str], dict[str, str]] = {}
    adjudicator_ids: set[str] = set()
    for line_number, row in enumerate(rows, start=2):
        sample_id = str(row.get("sample_id") or "").strip()
        label = str(row.get("label") or "").strip()
        key = (sample_id, label)
        if not sample_id or label not in CORE_LABELS:
            errors.append(f"line {line_number}: sample_id and known label are required")
            continue
        if key in decisions:
            errors.append(f"line {line_number}: duplicate decision for {sample_id}/{label}")
            continue
        value = str(row.get("adjudicated_value") or "").strip().lower()
        if value not in VALID:
            errors.append(f"line {line_number}: adjudicated_value must be true/false/na")
        adjudicator_id = str(row.get("adjudicator_id") or "").strip()
        if not adjudicator_id:
            errors.append(f"line {line_number}: adjudicator_id is required")
        else:
            adjudicator_ids.add(adjudicator_id)
        if not str(row.get("adjudication_rationale") or "").strip():
            errors.append(f"line {line_number}: adjudication_rationale is required")
        decisions[key] = {column: str(row.get(column) or "").strip() for column in DECISION_COLUMNS}
    if len(adjudicator_ids) != 1:
        errors.append("decision CSV must contain exactly one non-empty adjudicator_id")
    return decisions, errors, next(iter(adjudicator_ids), None)


def apply_adjudication(merged_file: Path, decisions_file: Path) -> dict[str, Any]:
    merged = _load_json(merged_file)
    conflicts = _conflicts(merged)
    expected = {(item["sample_id"], item["label"]): item for item in conflicts}
    decisions, errors, adjudicator_id = _read_decisions(decisions_file)
    if set(decisions) != set(expected):
        missing = sorted(set(expected) - set(decisions))
        unexpected = sorted(set(decisions) - set(expected))
        if missing:
            errors.append(f"decision CSV is missing conflicts: {missing}")
        if unexpected:
            errors.append(f"decision CSV contains non-conflicts: {unexpected}")
    for key, expected_row in expected.items():
        decision = decisions.get(key)
        if decision is None:
            continue
        for column in ("reviewer_a_value", "reviewer_b_value"):
            if decision.get(column, "").lower() != expected_row[column]:
                errors.append(f"{key[0]}/{key[1]}: {column} does not match merged input")
    rows = json.loads(json.dumps(merged["rows"], ensure_ascii=False))
    applied: list[dict[str, str]] = []
    for row in rows:
        sample_id = str(row.get("sample_id") or "").strip()
        for label in CORE_LABELS:
            if row.get(label) != "adjudicate":
                continue
            decision = decisions.get((sample_id, label))
            if decision is None:
                continue
            value = decision["adjudicated_value"].lower()
            row[label] = value
            applied.append({
                "sample_id": sample_id,
                "label": label,
                "reviewer_a_value": decision["reviewer_a_value"].lower(),
                "reviewer_b_value": decision["reviewer_b_value"].lower(),
                "adjudicated_value": value,
                "adjudicator_id": decision["adjudicator_id"],
                "adjudication_rationale": decision["adjudication_rationale"],
            })
    output = {
        **{key: value for key, value in merged.items() if key != "rows"},
        "evidence_kind": "two_reviewer_merge_with_human_adjudication",
        "valid": not errors,
        "errors": errors,
        "rows": rows,
        "adjudication": {
            "status": "completed" if not errors else "invalid",
            "adjudicator_id": adjudicator_id,
            "source_merged_sha256": _digest(merged_file),
            "decision_file": decisions_file.name,
            "decision_count": len(applied),
            "decision_value_counts": dict(sorted(Counter(item["adjudicated_value"] for item in applied).items())),
            "decisions": applied,
        },
    }
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成或应用 T-18 人工仲裁决议；不自动裁决。")
    subparsers = parser.add_subparsers(dest="command", required=True)
    template = subparsers.add_parser("template", help="根据 merge JSON 生成待人工填写的仲裁 CSV")
    template.add_argument("merged", type=Path)
    template.add_argument("--output", type=Path, required=True)
    apply = subparsers.add_parser("apply", help="验证人工仲裁 CSV 并生成 adjudicated JSON")
    apply.add_argument("merged", type=Path)
    apply.add_argument("decisions", type=Path)
    apply.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "template":
        payload = create_template(args.merged, args.output)
        print(json.dumps(payload, ensure_ascii=False))
        return 0
    payload = apply_adjudication(args.merged, args.decisions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("valid", "errors")}, ensure_ascii=False))
    return 0 if payload["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

