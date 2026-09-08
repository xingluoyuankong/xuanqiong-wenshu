from __future__ import annotations

import argparse
import csv
import json
import re
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
VALID_LABELS = {"true", "false", "na"}
IDENTITY_COLUMNS = ("source_version_id", "source_chapter_id", "content_sha256")
ANNOTATION_DIR = "output/quality-annotation-bundle-t18-exemption-20260823"
MERGED_RESULT_NAMES = ("adjudicated-annotations.json", "merged-annotations.json")


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def _read_reviewer_csv(path: Path) -> tuple[dict[str, dict[str, str]], list[str]]:
    errors: list[str] = []
    if not path.is_file():
        return {}, [f"missing file: {path.name}"]
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except (OSError, csv.Error, UnicodeError) as exc:
        return {}, [f"cannot read {path.name}: {exc}"]

    result: dict[str, dict[str, str]] = {}
    for index, row in enumerate(rows, start=2):
        sample_id = str(row.get("sample_id") or "").strip()
        if not sample_id:
            errors.append(f"{path.name}:{index}: sample_id is required")
            continue
        if sample_id in result:
            errors.append(f"{path.name}:{index}: duplicate sample_id {sample_id}")
            continue
        result[sample_id] = row
        if not str(row.get("reviewer_id") or "").strip():
            errors.append(f"{path.name}:{index}: reviewer_id is required")
        for column in IDENTITY_COLUMNS:
            if not str(row.get(column) or "").strip():
                errors.append(f"{path.name}:{index}: {column} is required")
        for label in CORE_LABELS:
            value = str(row.get(label) or "").strip().lower()
            if value not in VALID_LABELS:
                errors.append(f"{path.name}:{index}: {label} must be true/false/na")

    reviewers = {str(row.get("reviewer_id") or "").strip() for row in result.values()}
    if len(reviewers) != 1 or not next(iter(reviewers), ""):
        errors.append(f"{path.name}: exactly one non-empty reviewer_id is required")
    return result, errors


def _find_merged_result(annotation_dir: Path) -> Path | None:
    for name in MERGED_RESULT_NAMES:
        candidate = annotation_dir / name
        if candidate.is_file():
            return candidate
    return None


def _validate_merged_result(
    path: Path,
    reviewer_a: dict[str, dict[str, str]],
    reviewer_b: dict[str, dict[str, str]],
    *,
    allow_unresolved: bool = False,
) -> list[str]:
    errors: list[str] = []
    try:
        payload = load(path)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [f"{path.name}: cannot read JSON: {exc}"]

    if payload.get("schema_version") != 1:
        errors.append(f"{path.name}: schema_version must be 1")
    source_files = payload.get("source_files")
    expected_source_files = ["reviewer-a-template.csv", "reviewer-b-template.csv"]
    if source_files != expected_source_files:
        errors.append(f"{path.name}: source_files must identify both reviewer templates")
    if payload.get("valid") is not True:
        errors.append(f"{path.name}: valid must be true")
    if payload.get("errors") not in ([], None):
        errors.append(f"{path.name}: errors must be empty")
    if set(reviewer_a) != set(reviewer_b):
        errors.append("reviewer CSV sample_id sets do not match")

    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        return errors + [f"{path.name}: rows must be a non-empty list"]
    if payload.get("sample_count") != len(rows):
        errors.append(f"{path.name}: sample_count does not match rows")
    if len(rows) != len(reviewer_a):
        errors.append(f"{path.name}: row count does not match reviewer CSVs")

    seen: set[str] = set()
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            errors.append(f"{path.name}: row {index} must be an object")
            continue
        sample_id = str(row.get("sample_id") or "").strip()
        if not sample_id or sample_id in seen:
            errors.append(f"{path.name}: row {index} has missing or duplicate sample_id")
            continue
        seen.add(sample_id)
        if sample_id not in reviewer_a or sample_id not in reviewer_b:
            errors.append(f"{path.name}: unknown sample_id {sample_id}")
            continue
        expected_a, expected_b = reviewer_a[sample_id], reviewer_b[sample_id]
        if str(row.get("reviewer_a") or "").strip() != str(expected_a.get("reviewer_id") or "").strip():
            errors.append(f"{path.name}: {sample_id} reviewer_a does not match CSV")
        if str(row.get("reviewer_b") or "").strip() != str(expected_b.get("reviewer_id") or "").strip():
            errors.append(f"{path.name}: {sample_id} reviewer_b does not match CSV")
        if str(row.get("reviewer_a") or "").strip() == str(row.get("reviewer_b") or "").strip():
            errors.append(f"{path.name}: {sample_id} reviewers must be distinct")
        identity = row.get("identity")
        if not isinstance(identity, dict):
            errors.append(f"{path.name}: {sample_id} identity must be an object")
        else:
            for column in IDENTITY_COLUMNS:
                expected = str(expected_a.get(column) or "").strip()
                if str(identity.get(column) or "").strip() != expected or str(expected_b.get(column) or "").strip() != expected:
                    errors.append(f"{path.name}: {sample_id} {column} does not match CSVs")
        for label in CORE_LABELS:
            value = str(row.get(label) or "").strip().lower()
            if value not in VALID_LABELS and not (allow_unresolved and value == "adjudicate"):
                errors.append(f"{path.name}: {sample_id} {label} is unresolved or invalid")
    if seen != set(reviewer_a):
        errors.append(f"{path.name}: merged rows do not cover reviewer CSVs exactly")
    errors.extend(_label_provenance_errors(path, payload, reviewer_a, reviewer_b, allow_unresolved=allow_unresolved))
    return errors


def _manifest_errors(
    annotation_dir: Path,
    reviewer_a: dict[str, dict[str, str]],
    reviewer_b: dict[str, dict[str, str]],
) -> list[str]:
    path = annotation_dir / "manifest.json"
    try:
        manifest = load(path)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [f"manifest.json: invalid or missing manifest: {type(exc).__name__}"]
    errors = []
    if type(manifest.get("schema_version")) is not int or manifest.get("schema_version") != 1:
        errors.append("manifest.json: schema_version must be 1")
    if manifest.get("content_emitted") is not False:
        errors.append("manifest.json: content_emitted must be false")
    raw_samples = manifest.get("samples")
    if not isinstance(raw_samples, list) or not raw_samples:
        return errors + ["manifest.json: samples must be a non-empty list"]
    count = manifest.get("selected_count")
    if type(count) is not int or count != len(raw_samples):
        errors.append("manifest.json: selected_count must match sample rows")
    samples = {}
    for sample in raw_samples:
        if not isinstance(sample, dict):
            errors.append("manifest.json: sample must be an object")
            continue
        sample_id = sample.get("sample_id")
        if not isinstance(sample_id, str) or not sample_id.strip() or sample_id.strip() in samples:
            errors.append("manifest.json: missing or duplicate sample_id")
            continue
        sample_id = sample_id.strip()
        samples[sample_id] = sample
        for column in ("source_version_id", "source_chapter_id"):
            value = str(sample.get(column) or "")
            if not value.isascii() or not value.isdecimal() or not value.lstrip("0"):
                errors.append(f"manifest.json: {sample_id} {column} must be a positive integer")
        if re.fullmatch(r"[0-9a-fA-F]{64}", str(sample.get("content_sha256") or "")) is None:
            errors.append(f"manifest.json: {sample_id} content_sha256 must be a SHA256 digest")
    for filename, rows in (("reviewer-a-template.csv", reviewer_a), ("reviewer-b-template.csv", reviewer_b)):
        if set(rows) != set(samples):
            errors.append(f"manifest.json: {filename} sample_id set must match manifest exactly")
        for sample_id in set(rows) & set(samples):
            for column in IDENTITY_COLUMNS:
                if str(rows[sample_id].get(column) or "").strip() != str(samples[sample_id].get(column) or "").strip():
                    errors.append(f"manifest.json: {filename} {sample_id} {column} differs from manifest")
    return errors


def _adjudication_errors(
    path: Path,
    payload: dict[str, Any],
    reviewer_a: dict[str, dict[str, str]],
    reviewer_b: dict[str, dict[str, str]],
) -> list[str]:
    """Replay the existing adjudication contract against its preserved inputs."""
    metadata = payload.get("adjudication")
    if not isinstance(metadata, dict):
        return ["adjudication metadata is required"]
    source = path.parent / "merged-annotations.json"
    source_errors = _validate_merged_result(source, reviewer_a, reviewer_b, allow_unresolved=True)
    if source_errors:
        return [f"adjudication source merge invalid: {error}" for error in source_errors]
    name = metadata.get("decision_file")
    if not isinstance(name, str) or not name or name in {".", ".."} or any(c in name for c in ("/", "\\", ":")):
        return ["adjudication decision_file must be a local filename"]
    try:
        decision_file = path.parent / name
        if decision_file.resolve().parent != path.parent.resolve() or not decision_file.is_file():
            return ["adjudication decision file is missing or outside its bundle"]
        try:
            from scripts.adjudicate_quality_annotations import apply_adjudication
        except ModuleNotFoundError:
            from adjudicate_quality_annotations import apply_adjudication
        expected = apply_adjudication(source, decision_file)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return [f"adjudication input validation failed: {type(exc).__name__}"]
    if expected.get("valid") is not True:
        return [f"adjudication decisions invalid: {error}" for error in expected.get("errors", ["invalid decision input"])]
    return [f"adjudication {field} differs from verified source merge/decision file"
            for field in ("evidence_kind", "source_files", "sample_count", "rows", "adjudication")
            if payload.get(field) != expected.get(field)]


def _label_provenance_errors(
    path: Path,
    payload: dict[str, Any],
    reviewer_a: dict[str, dict[str, str]],
    reviewer_b: dict[str, dict[str, str]],
    *,
    allow_unresolved: bool = False,
) -> list[str]:
    errors = []
    for row in payload["rows"]:
        if not isinstance(row, dict):
            continue
        sample_id = str(row.get("sample_id") or "").strip()
        if sample_id not in reviewer_a or sample_id not in reviewer_b:
            continue
        for label in CORE_LABELS:
            a = str(reviewer_a[sample_id].get(label) or "").strip().lower()
            b = str(reviewer_b[sample_id].get(label) or "").strip().lower()
            value = str(row.get(label) or "").strip().lower()
            for suffix, original in (("a", a), ("b", b)):
                field = f"{label}_{suffix}"
                if field in row and str(row[field] or "").strip().lower() != original:
                    errors.append(f"{path.name}: {sample_id} {field} differs from reviewer CSV")
            if a == b and value != a:
                errors.append(f"{path.name}: {sample_id} {label} must preserve unanimous reviewer value")
            elif a != b:
                if allow_unresolved:
                    if value != "adjudicate":
                        errors.append(f"{path.name}: {sample_id} {label} source disagreement must remain adjudicate")
                elif path.name != "adjudicated-annotations.json":
                    errors.append(f"{path.name}: {sample_id} {label} requires verified adjudication")
    if not allow_unresolved and path.name == "adjudicated-annotations.json":
        errors.extend(_adjudication_errors(path, payload, reviewer_a, reviewer_b))
    return errors



def _annotation_errors(root: Path) -> list[str]:
    annotation_dir = root / ANNOTATION_DIR
    reviewer_a, errors_a = _read_reviewer_csv(annotation_dir / "reviewer-a-template.csv")
    reviewer_b, errors_b = _read_reviewer_csv(annotation_dir / "reviewer-b-template.csv")
    errors = errors_a + errors_b + _manifest_errors(annotation_dir, reviewer_a, reviewer_b)
    if reviewer_a and reviewer_b:
        if set(reviewer_a) != set(reviewer_b):
            errors.append("reviewer CSV sample_id sets do not match")
        if {row.get("reviewer_id", "").strip() for row in reviewer_a.values()} & {row.get("reviewer_id", "").strip() for row in reviewer_b.values()}:
            errors.append("reviewer_id must be distinct between reviewer CSVs")
        merged = _find_merged_result(annotation_dir)
        if merged is None:
            errors.append("merged/adjudicated result is missing")
        else:
            errors.extend(_validate_merged_result(merged, reviewer_a, reviewer_b))
    else:
        errors.append("both reviewer CSVs must be complete before merge validation")
    return errors


def audit(root: Path) -> dict[str, Any]:
    matrix = load(root / "output/novel-quality-task-matrix-consistency-20260823.json")
    gap = load(root / "output/novel-quality-gap-register-20260823.json")
    blockers: list[str] = []
    if matrix.get("status") != "valid":
        blockers.append("task_matrix_invalid")
    hard = gap.get("hard_gaps") if isinstance(gap.get("hard_gaps"), list) else []
    for item in hard:
        if item.get("status") != "completed":
            blockers.append(str(item.get("item") or "unknown_hard_gap"))
    annotation_errors = _annotation_errors(root)
    if annotation_errors:
        blockers.append("human_quality_labels")
    return {
        "audit_date": "2026-08-23",
        "goal_status": "active",
        "completion_eligible": not blockers,
        "blockers": sorted(set(blockers)),
        "human_quality_labels_validation": {
            "valid": not annotation_errors,
            "errors": annotation_errors,
        },
        "matrix": {
            "status": matrix.get("status"),
            "task_count": matrix.get("task_count"),
            "t_count": matrix.get("t_count", matrix.get("t_task_count")),
            "e_count": matrix.get("e_count", matrix.get("e_task_count")),
        },
        "hard_gap_count": len(hard),
        "policy": "Never mark complete while blockers are present; audit guard is not a substitute for human truth or real provider gain.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
