from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

import pytest


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
    (bundle / "manifest.json").write_text(json.dumps({
        "schema_version": 1, "content_emitted": False, "selected_count": 1,
        "samples": [{"sample_id": "Q001", "source_version_id": 1,
                     "source_chapter_id": 1, "content_sha256": "a" * 64}],
    }), encoding="utf-8")
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


def _complete_bundle(tmp_path):
    _, bundle = _setup(tmp_path)
    _write_reviewer(bundle / "reviewer-a-template.csv", "reviewer-a")
    _write_reviewer(bundle / "reviewer-b-template.csv", "reviewer-b")
    _write_merge(bundle)
    return bundle


@pytest.mark.parametrize("damage", [
    "missing", "invalid_json", "not_object", "wrong_schema", "invalid_samples",
    "empty_samples", "wrong_count", "boolean_count", "duplicate_sample",
    "unknown_sample", "missing_sample", "wrong_version", "wrong_chapter",
    "wrong_hash", "invalid_hash", "invalid_version", "huge_version", "boolean_schema",
])
def test_manifest_scope_and_identity_are_required(tmp_path, damage):
    bundle = _complete_bundle(tmp_path)
    path = bundle / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if damage == "missing":
        path.unlink()
    elif damage == "invalid_json":
        path.write_text("{", encoding="utf-8")
    else:
        if damage == "not_object": manifest = []
        elif damage == "wrong_schema": manifest["schema_version"] = 2
        elif damage == "boolean_schema": manifest["schema_version"] = True
        elif damage == "invalid_samples": manifest["samples"] = {}
        elif damage == "empty_samples": manifest.update(samples=[], selected_count=0)
        elif damage == "wrong_count": manifest["selected_count"] = 2
        elif damage == "boolean_count": manifest["selected_count"] = True
        elif damage == "duplicate_sample":
            manifest["samples"].append(dict(manifest["samples"][0]))
            manifest["selected_count"] = 2
        elif damage == "unknown_sample": manifest["samples"][0]["sample_id"] = "T18-other"
        elif damage == "missing_sample":
            manifest["samples"].append({**manifest["samples"][0], "sample_id": "Q002"})
            manifest["selected_count"] = 2
        elif damage == "wrong_version": manifest["samples"][0]["source_version_id"] = 2
        elif damage == "wrong_chapter": manifest["samples"][0]["source_chapter_id"] = 2
        elif damage == "wrong_hash": manifest["samples"][0]["content_sha256"] = "b" * 64
        elif damage == "invalid_hash": manifest["samples"][0]["content_sha256"] = "not-a-digest"
        elif damage == "invalid_version": manifest["samples"][0]["source_version_id"] = 0
        elif damage == "huge_version": manifest["samples"][0]["source_version_id"] = "9" * 5000
        path.write_text(json.dumps(manifest), encoding="utf-8")
    result = load().audit(tmp_path)
    assert result["completion_eligible"] is False
    assert any("manifest" in error for error in result["human_quality_labels_validation"]["errors"])


@pytest.mark.parametrize("reviewed, merged", [("false", "true"), ("true", "false"), ("na", "true")])
def test_merge_must_preserve_unanimous_reviewer_labels(tmp_path, reviewed, merged):
    bundle = _complete_bundle(tmp_path)
    _write_reviewer(bundle / "reviewer-a-template.csv", "reviewer-a", reviewed)
    _write_reviewer(bundle / "reviewer-b-template.csv", "reviewer-b", reviewed)
    _write_merge(bundle, merged)
    result = load().audit(tmp_path)
    assert result["completion_eligible"] is False
    assert any("unanimous" in error for error in result["human_quality_labels_validation"]["errors"])


@pytest.mark.parametrize("value", ["false", "na"])
def test_completed_consistent_negative_or_na_labels_are_not_rewritten(tmp_path, value):
    bundle = _complete_bundle(tmp_path)
    _write_reviewer(bundle / "reviewer-a-template.csv", "reviewer-a", value)
    _write_reviewer(bundle / "reviewer-b-template.csv", "reviewer-b", value)
    _write_merge(bundle, value)
    assert load().audit(tmp_path)["completion_eligible"] is True


def _adjudicated_bundle(tmp_path):
    from scripts.merge_quality_annotations import merge
    from scripts.adjudicate_quality_annotations import apply_adjudication, create_template
    bundle = _complete_bundle(tmp_path)
    a, b = bundle / "reviewer-a-template.csv", bundle / "reviewer-b-template.csv"
    _write_reviewer(b, "reviewer-b", "false")
    merged = bundle / "merged-annotations.json"
    merged.write_text(json.dumps(merge(a, b)), encoding="utf-8")
    decisions = bundle / "adjudication-decisions.csv"
    create_template(merged, decisions)
    with decisions.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row.update(adjudicated_value="true", adjudicator_id="fixture-adjudicator", adjudication_rationale="Synthetic regression fixture, not actual human review.")
    with decisions.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    payload = apply_adjudication(merged, decisions)
    assert payload["valid"] is True
    (bundle / "adjudicated-annotations.json").write_text(json.dumps(payload), encoding="utf-8")
    return bundle


def test_valid_adjudication_is_checked_without_deleting_source_merge(tmp_path):
    bundle = _adjudicated_bundle(tmp_path)
    result = load().audit(tmp_path)
    assert (bundle / "merged-annotations.json").is_file()
    assert result["completion_eligible"] is True, result


def test_disagreement_resolved_without_adjudication_is_rejected(tmp_path):
    bundle = _complete_bundle(tmp_path)
    _write_reviewer(bundle / "reviewer-b-template.csv", "reviewer-b", "false")
    result = load().audit(tmp_path)
    assert result["completion_eligible"] is False
    assert any("adjudication" in error for error in result["human_quality_labels_validation"]["errors"])


def test_invalid_adjudication_is_not_ignored_in_favor_of_good_merge(tmp_path):
    bundle = _complete_bundle(tmp_path)
    (bundle / "adjudicated-annotations.json").write_text(json.dumps({"valid": False}), encoding="utf-8")
    assert load().audit(tmp_path)["completion_eligible"] is False


@pytest.mark.parametrize("damage", ["missing_source", "changed_source_bytes", "wrong_source_hash", "missing_decisions", "external_decisions", "changed_decision", "changed_final_label", "changed_rationale"])
def test_adjudication_must_match_source_merge_and_decision_file(tmp_path, damage):
    bundle = _adjudicated_bundle(tmp_path)
    source, decisions = bundle / "merged-annotations.json", bundle / "adjudication-decisions.csv"
    selected = bundle / "adjudicated-annotations.json"
    payload = json.loads(selected.read_text(encoding="utf-8"))
    if damage == "missing_source": source.unlink()
    elif damage == "changed_source_bytes": source.write_text(source.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    elif damage == "wrong_source_hash": payload["adjudication"]["source_merged_sha256"] = "0" * 64
    elif damage == "missing_decisions": decisions.unlink()
    elif damage == "external_decisions": payload["adjudication"]["decision_file"] = "../outside.csv"
    elif damage == "changed_decision": decisions.write_text(decisions.read_text(encoding="utf-8").replace(",true,fixture-adjudicator", ",false,fixture-adjudicator"), encoding="utf-8")
    elif damage == "changed_final_label": payload["rows"][0]["human_overall_accept"] = "false"
    elif damage == "changed_rationale": payload["adjudication"]["decisions"][0]["adjudication_rationale"] = "invented"
    selected.write_text(json.dumps(payload), encoding="utf-8")
    result = load().audit(tmp_path)
    assert result["completion_eligible"] is False
    assert any("adjudication" in error for error in result["human_quality_labels_validation"]["errors"])
