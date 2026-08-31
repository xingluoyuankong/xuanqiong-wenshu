"""Merge two completed T-18 human-review CSVs without manufacturing agreement.

A disagreement remains the literal value ``adjudicate``.  It is resolved only
by the separate adjudication tool and a human-entered decision file.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

CORE_LABELS = (
    "human_overall_accept",
    "human_ending_pressure",
    "human_dialogue_changes_state",
    "human_late_reversal",
    "human_speaker_distinct",
    "human_balance_acceptable",
    "human_scene_transition_clear",
    "human_static_description_excessive",
)
VALID = {"true", "false", "na"}
IDENTITY_COLUMNS = ("source_version_id", "source_chapter_id", "content_sha256")
REQUIRED_COLUMNS = {"sample_id", "reviewer_id", *IDENTITY_COLUMNS, *CORE_LABELS}


def _read(path: Path) -> tuple[dict[str, dict[str, str]], list[str]]:
    errors: list[str] = []
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = {str(field or "").strip() for field in (reader.fieldnames or [])}
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        return {}, [f"cannot read {path}: {type(exc).__name__}"]
    missing = sorted(REQUIRED_COLUMNS - fieldnames)
    if missing:
        errors.append(f"{path.name}: missing required columns: {missing}")
    result: dict[str, dict[str, str]] = {}
    for line_number, row in enumerate(rows, start=2):
        sample_id = str(row.get("sample_id") or "").strip()
        if not sample_id or sample_id in result:
            errors.append(f"{path.name}:{line_number}: duplicate or missing sample_id {sample_id!r}")
            continue
        result[sample_id] = row
    if not result:
        errors.append(f"{path.name}: at least one annotation row is required")
    return result, errors


def _single_reviewer(rows: dict[str, dict[str, str]], path: Path, errors: list[str], role: str) -> str:
    reviewer_ids = {str(row.get("reviewer_id") or "").strip() for row in rows.values()}
    if len(reviewer_ids) != 1:
        errors.append(f"{role} reviewer file must contain exactly one non-empty reviewer_id")
        return ""
    reviewer_id = next(iter(reviewer_ids), "")
    if not reviewer_id:
        errors.append(f"{role} reviewer file must contain exactly one non-empty reviewer_id")
    return reviewer_id


def merge(first: Path, second: Path) -> dict[str, Any]:
    left, left_errors = _read(first)
    right, right_errors = _read(second)
    errors = [*left_errors, *right_errors]
    if set(left) != set(right):
        errors.append("annotation sample_id sets do not match")
    reviewer_a = _single_reviewer(left, first, errors, "first")
    reviewer_b = _single_reviewer(right, second, errors, "second")
    if reviewer_a and reviewer_b and reviewer_a == reviewer_b:
        errors.append("reviewer_id must be distinct between reviewer files")
    rows: list[dict[str, Any]] = []
    agreement: dict[str, dict[str, int]] = {
        label: {"agree": 0, "disagree": 0, "unlabeled": 0} for label in CORE_LABELS
    }
    for sample_id in sorted(set(left) & set(right)):
        a, b = left[sample_id], right[sample_id]
        identity: dict[str, str] = {}
        for column in IDENTITY_COLUMNS:
            left_value = str(a.get(column) or "").strip()
            right_value = str(b.get(column) or "").strip()
            if not left_value or not right_value:
                errors.append(f"{sample_id}: {column} must be present in both reviewer files")
            elif left_value != right_value:
                errors.append(f"{sample_id}: {column} does not match between reviewer files")
            identity[column] = left_value or right_value
        merged: dict[str, Any] = {
            "sample_id": sample_id,
            "identity": identity,
            "reviewer_a": reviewer_a,
            "reviewer_b": reviewer_b,
            "review_notes_a": str(a.get("review_notes") or "").strip() or None,
            "review_notes_b": str(b.get("review_notes") or "").strip() or None,
        }
        for label in CORE_LABELS:
            va = str(a.get(label) or "").strip().lower()
            vb = str(b.get(label) or "").strip().lower()
            if va not in VALID or vb not in VALID:
                errors.append(f"{sample_id}: {label} must be true/false/na for both reviewers")
            if not va or not vb:
                agreement[label]["unlabeled"] += 1
            elif va == vb:
                agreement[label]["agree"] += 1
            else:
                agreement[label]["disagree"] += 1
            merged[f"{label}_a"] = va or None
            merged[f"{label}_b"] = vb or None
            merged[label] = va if va == vb and va in VALID else "adjudicate"
        rows.append(merged)
    complete_agreement_rows = sum(all(row[label] in VALID for label in CORE_LABELS) for row in rows)
    unresolved_decision_count = sum(
        1 for row in rows for label in CORE_LABELS if row.get(label) == "adjudicate"
    )
    return {
        "schema_version": 1,
        "evidence_kind": "two_reviewer_merge",
        "source_files": [first.name, second.name],
        "reviewers": {"reviewer_a": reviewer_a or None, "reviewer_b": reviewer_b or None},
        "sample_count": len(rows),
        "complete_agreement_row_count": complete_agreement_rows,
        "unresolved_adjudication_count": unresolved_decision_count,
        "valid": not errors,
        "errors": errors,
        "agreement": agreement,
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="合并两名完整人工审阅 CSV；分歧保留为 adjudicate。")
    parser.add_argument("first", type=Path)
    parser.add_argument("second", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    payload = merge(args.first, args.second)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("sample_count", "complete_agreement_row_count", "unresolved_adjudication_count", "valid", "errors")}, ensure_ascii=False))
    return 0 if payload["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
