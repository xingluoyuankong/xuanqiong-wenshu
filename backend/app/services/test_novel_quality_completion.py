from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path


def load():
    path = Path(__file__).resolve().parents[2] / "scripts/audit_novel_quality_completion.py"
    spec = importlib.util.spec_from_file_location("completion_audit", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_reviewer(path: Path, reviewer: str, value: str | None = "true") -> None:
    module = load()
    row = {
        "sample_id": "Q001",
        "source_version_id": "1",
        "source_chapter_id": "1",
        "content_sha256": "a" * 64,
        "reviewer_id": reviewer,
        **{label: value or "" for label in module.CORE_LABELS},
    }
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=row.keys())
        writer.writeheader()
        writer.writerow(row)


def _setup(tmp_path: Path) -> tuple[Path, Path]:
    output = tmp_path / "output"
    bundle = output / "quality-annotation-bundle-t18-exemption-20260823"
    bundle.mkdir(parents=True)
    (output / "novel-quality-task-matrix-consistency-20260823.json").write_text(
        json.dumps({"status": "valid", "task_count": 39, "t_count": 26, "e_count": 12}),
        encoding="utf-8",
    )
    (output / "novel-quality-gap-register-20260823.json").write_text(
        json.dumps({"hard_gaps": []}),
        encoding="utf-8",
    )
    return output, bundle


def _write_merge(bundle: Path, value: str = "true") -> None:
    module = load()
    row = {
        "sample_id": "Q001",
        "identity": {
            "source_version_id": "1",
            "source_chapter_id": "1",
            "content_sha256": "a" * 64,
        },
        "reviewer_a": "reviewer-a",
        "reviewer_b": "reviewer-b",
        **{label: value for label in module.CORE_LABELS},
    }
    payload = {
        "schema_version": 1,
        "source_files": ["reviewer-a-template.csv", "reviewer-b-template.csv"],
        "valid": True,
        "errors": [],
        "sample_count": 1,
        "rows": [row],
    }
    (bundle / "merged-annotations.json").write_text(json.dumps(payload), encoding="utf-8")


def test_completion_audit_stays_ineligible_while_hard_gaps_exist(tmp_path):
    _, bundle = _setup(tmp_path)
    _write_reviewer(bundle / "reviewer-a-template.csv", "reviewer-a", None)
    _write_reviewer(bundle / "reviewer-b-template.csv", "reviewer-b", None)
    result = load().audit(tmp_path)
    assert result["completion_eligible"] is False
    assert "human_quality_labels" in result["blockers"]


def test_blank_reviewer_a_and_b_are_ineligible(tmp_path):
    _, bundle = _setup(tmp_path)
    _write_reviewer(bundle / "reviewer-a-template.csv", "reviewer-a", None)
    _write_reviewer(bundle / "reviewer-b-template.csv", "reviewer-b", None)
    result = load().audit(tmp_path)
    assert result["completion_eligible"] is False
    assert result["human_quality_labels_validation"]["valid"] is False


def test_only_reviewer_a_complete_is_ineligible(tmp_path):
    _, bundle = _setup(tmp_path)
    _write_reviewer(bundle / "reviewer-a-template.csv", "reviewer-a")
    _write_reviewer(bundle / "reviewer-b-template.csv", "reviewer-b", None)
    result = load().audit(tmp_path)
    assert result["completion_eligible"] is False
    assert "human_quality_labels" in result["blockers"]


def test_complete_reviewers_without_merge_or_with_unresolved_adjudication_are_ineligible(tmp_path):
    _, bundle = _setup(tmp_path)
    _write_reviewer(bundle / "reviewer-a-template.csv", "reviewer-a")
    _write_reviewer(bundle / "reviewer-b-template.csv", "reviewer-b")
    missing_merge = load().audit(tmp_path)
    assert missing_merge["completion_eligible"] is False
    assert "merged/adjudicated result is missing" in missing_merge["human_quality_labels_validation"]["errors"]

    unresolved = {
        "schema_version": 1,
        "valid": True,
        "errors": [],
        "sample_count": 1,
        "rows": [{
            "sample_id": "Q001",
            "identity": {"source_version_id": "1", "source_chapter_id": "1", "content_sha256": "a" * 64},
            "reviewer_a": "reviewer-a",
            "reviewer_b": "reviewer-b",
            **{label: "adjudicate" if label == "human_overall_accept" else "true" for label in load().CORE_LABELS},
        }],
    }
    (bundle / "merged-annotations.json").write_text(json.dumps(unresolved), encoding="utf-8")
    result = load().audit(tmp_path)
    assert result["completion_eligible"] is False
    assert any("unresolved or invalid" in error for error in result["human_quality_labels_validation"]["errors"])


def test_complete_reviewers_and_legal_resolved_merge_clear_human_blocker(tmp_path):
    _, bundle = _setup(tmp_path)
    _write_reviewer(bundle / "reviewer-a-template.csv", "reviewer-a")
    _write_reviewer(bundle / "reviewer-b-template.csv", "reviewer-b")
    _write_merge(bundle)
    result = load().audit(tmp_path)
    assert result["human_quality_labels_validation"]["valid"] is True
    assert "human_quality_labels" not in result["blockers"]
    assert result["completion_eligible"] is True


def test_merge_with_wrong_source_files_is_rejected(tmp_path):
    _, bundle = _setup(tmp_path)
    _write_reviewer(bundle / "reviewer-a-template.csv", "reviewer-a")
    _write_reviewer(bundle / "reviewer-b-template.csv", "reviewer-b")
    _write_merge(bundle)
    path = bundle / "merged-annotations.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["source_files"] = ["unrelated-a.csv", "unrelated-b.csv"]
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = load().audit(tmp_path)
    assert result["completion_eligible"] is False
    assert any("source_files" in error for error in result["human_quality_labels_validation"]["errors"])
