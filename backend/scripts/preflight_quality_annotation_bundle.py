"""Machine-only preflight for T-18 human annotation materials.

The report distinguishes templates from completed human evidence.  It does not
infer labels, invent reviewer identities, or turn a blank template into a
review result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:  # Package import for pytest/module use; direct import for `python scripts/...`.
    from scripts.export_quality_annotation_bundle import CORE_LABELS, IDENTITY_COLUMNS, validate_labels
    from scripts.merge_quality_annotations import merge
except ModuleNotFoundError:  # pragma: no cover - exercised by CLI smoke command.
    from export_quality_annotation_bundle import CORE_LABELS, IDENTITY_COLUMNS, validate_labels
    from merge_quality_annotations import merge

REVIEWER_FILES = ("reviewer-a-template.csv", "reviewer-b-template.csv")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, [f"cannot read {path.name}: {type(exc).__name__}"]
    return (value, []) if isinstance(value, dict) else (None, [f"{path.name}: JSON root must be an object"])


def _manifest_report(path: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[str]]:
    manifest, errors = _read_json(path)
    samples: dict[str, dict[str, Any]] = {}
    details: dict[str, Any] = {"path": path.name, "exists": path.is_file(), "sha256": _sha256(path) if path.is_file() else None}
    if manifest is None:
        return details, samples, errors
    details.update({
        "schema_version": manifest.get("schema_version"),
        "content_emitted": manifest.get("content_emitted"),
        "selected_count": manifest.get("selected_count"),
    })
    if manifest.get("content_emitted") is not False:
        errors.append("manifest content_emitted must be false for the redacted T-18 review bundle")
    raw_samples = manifest.get("samples")
    if not isinstance(raw_samples, list) or not raw_samples:
        errors.append("manifest samples must be a non-empty list")
    else:
        for index, sample in enumerate(raw_samples, start=1):
            if not isinstance(sample, dict):
                errors.append(f"manifest sample {index} must be an object")
                continue
            sample_id = str(sample.get("sample_id") or "").strip()
            if not sample_id or sample_id in samples:
                errors.append(f"manifest sample {index} has missing or duplicate sample_id")
                continue
            for column in IDENTITY_COLUMNS:
                if not str(sample.get(column) or "").strip():
                    errors.append(f"manifest {sample_id}: {column} is required")
            samples[sample_id] = sample
        if manifest.get("selected_count") != len(samples):
            errors.append("manifest selected_count does not match usable sample rows")
    details["sample_count"] = len(samples)
    details["valid"] = not errors
    details["errors"] = errors
    return details, samples, errors


def _file_report(path: Path, manifest_path: Path) -> dict[str, Any]:
    exists = path.is_file()
    basic = validate_labels(path, manifest_path) if exists else {
        "row_count": 0, "labeled_row_count": 0, "complete_labeled_row_count": 0,
        "reviewer_ids": [], "valid": False, "errors": [f"missing file: {path.name}"],
    }
    completion = validate_labels(
        path,
        manifest_path,
        require_complete=True,
        require_single_reviewer=True,
    ) if exists else basic
    is_blank_template = exists and basic["valid"] and basic["labeled_row_count"] == 0 and not basic["reviewer_ids"]
    if is_blank_template:
        state = "blank_template"
    elif completion["valid"]:
        state = "complete_human_candidate"
    else:
        state = "incomplete_or_invalid"
    return {
        "path": path.name,
        "exists": exists,
        "sha256": _sha256(path) if exists else None,
        "state": state,
        "basic_validation": basic,
        "completion_validation": completion,
        "template_is_not_human_result": is_blank_template,
    }


def _existing_adjudication(bundle: Path) -> dict[str, Any]:
    path = bundle / "adjudicated-annotations.json"
    if not path.is_file():
        return {"exists": False, "state": "not_present"}
    payload, errors = _read_json(path)
    if payload is not None:
        rows = payload.get("rows")
        unresolved = sum(
            1 for row in rows if isinstance(row, dict) for label in CORE_LABELS if row.get(label) == "adjudicate"
        ) if isinstance(rows, list) else None
        if payload.get("valid") is not True:
            errors.append("adjudicated-annotations.json valid must be true")
        if unresolved not in (0,):
            errors.append("adjudicated-annotations.json still has unresolved adjudicate values")
    return {
        "exists": True,
        "path": path.name,
        "sha256": _sha256(path),
        "state": "valid_candidate" if not errors else "invalid",
        "unresolved_adjudication_count": unresolved if payload is not None else None,
        "errors": errors,
    }


def preflight(bundle: Path) -> dict[str, Any]:
    manifest_path = bundle / "manifest.json"
    manifest, samples, manifest_errors = _manifest_report(manifest_path)
    reviewers = {name: _file_report(bundle / name, manifest_path) for name in REVIEWER_FILES}
    completed = all(item["completion_validation"]["valid"] for item in reviewers.values())
    reviewer_ids = [item["completion_validation"].get("reviewer_ids", []) for item in reviewers.values()]
    reviewers_distinct = completed and all(len(ids) == 1 for ids in reviewer_ids) and reviewer_ids[0][0] != reviewer_ids[1][0]
    merge_result: dict[str, Any] | None = None
    merge_error: str | None = None
    if completed and reviewers_distinct:
        try:
            merge_result = merge(bundle / REVIEWER_FILES[0], bundle / REVIEWER_FILES[1])
        except (OSError, ValueError) as exc:
            merge_error = f"merge failed: {type(exc).__name__}: {exc}"
    adjudication = _existing_adjudication(bundle)
    blank_templates = all(item["state"] == "blank_template" for item in reviewers.values())
    if manifest_errors:
        evidence_state = "bundle_contract_invalid"
        human_result_present = False
    elif blank_templates:
        evidence_state = "templates_only_not_human_result"
        human_result_present = False
    elif not completed or not reviewers_distinct:
        evidence_state = "reviewer_inputs_incomplete_or_invalid"
        human_result_present = False
    elif merge_error or merge_result is None or not merge_result["valid"]:
        evidence_state = "merge_invalid"
        human_result_present = False
    elif merge_result["unresolved_adjudication_count"]:
        if adjudication["state"] == "valid_candidate":
            evidence_state = "human_annotation_evidence_ready_after_adjudication"
            human_result_present = True
        else:
            evidence_state = "human_adjudication_required"
            human_result_present = False
    else:
        evidence_state = "human_annotation_evidence_ready_two_reviewer_consensus"
        human_result_present = True
    next_actions: list[str]
    if evidence_state == "templates_only_not_human_result":
        next_actions = [
            "两名真实审阅人各自独立填写 reviewer-a-template.csv 与 reviewer-b-template.csv；不得互看结果。",
            "分别执行 CSV 完整性校验，再执行 merge_quality_annotations.py。",
            "如 merge JSON 出现 adjudicate，执行 adjudicate_quality_annotations.py template 生成仲裁表，由真实仲裁人填写后 apply。",
        ]
    elif evidence_state == "human_adjudication_required":
        next_actions = ["生成并填写仲裁决议 CSV；脚本不自动选边或补值。"]
    elif human_result_present:
        next_actions = ["将结果交给上层 T-18 完成性审计；本预检只证明标注材料链完整。"]
    else:
        next_actions = ["修复报告中的 CSV、manifest 或 merge 契约错误后重新运行预检。"]
    return {
        "schema_version": 1,
        "report_kind": "t18_machine_precheck",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "bundle": str(bundle),
        "manifest": manifest,
        "reviewer_files": reviewers,
        "merge_preview": None if merge_result is None else {
            key: merge_result[key] for key in (
                "valid", "errors", "sample_count", "complete_agreement_row_count", "unresolved_adjudication_count", "agreement",
            )
        },
        "merge_error": merge_error,
        "adjudication_artifact": adjudication,
        "evidence_state": evidence_state,
        "human_result_present": human_result_present,
        "template_is_not_human_result": not human_result_present,
        "machine_precheck_limit": "本报告只验证文件契约与人工填写痕迹；不判定小说质量，也不把模板、机器标签或空白字段视为人工审阅。",
        "next_actions": next_actions,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="T-18 双人工审阅材料机器预检查。")
    parser.add_argument("bundle", type=Path, help="T-18 标注包目录")
    parser.add_argument("--output", type=Path, help="JSON 报告位置；省略时打印到标准输出")
    args = parser.parse_args(argv)
    payload = preflight(args.bundle)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("evidence_state", "human_result_present", "next_actions")}, ensure_ascii=False))
    return 0 if payload["evidence_state"] != "bundle_contract_invalid" else 1


if __name__ == "__main__":
    raise SystemExit(main())

