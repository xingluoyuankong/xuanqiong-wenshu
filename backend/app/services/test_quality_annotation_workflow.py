from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.adjudicate_quality_annotations import apply_adjudication, create_template
from scripts.export_quality_annotation_bundle import CORE_LABELS, validate_labels
from scripts.merge_quality_annotations import merge
from scripts.preflight_quality_annotation_bundle import preflight


def _manifest(bundle: Path) -> Path:
    payload = {
        "schema_version": 1,
        "content_emitted": False,
        "selected_count": 1,
        "samples": [{
            "sample_id": "T18-01",
            "source_version_id": 7,
            "source_chapter_id": 11,
            "content_sha256": "a" * 64,
        }],
    }
    path = bundle / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _reviewer(path: Path, reviewer_id: str = "", *, overall: str = "", ending: str = "") -> None:
    fields = ["sample_id", "source_version_id", "source_chapter_id", "content_sha256", *CORE_LABELS, "reviewer_id", "review_notes"]
    row = {
        "sample_id": "T18-01",
        "source_version_id": "7",
        "source_chapter_id": "11",
        "content_sha256": "a" * 64,
        "reviewer_id": reviewer_id,
        "review_notes": "抽象依据",
        **{label: "true" for label in CORE_LABELS},
    }
    if not reviewer_id:
        for label in CORE_LABELS:
            row[label] = ""
        row["review_notes"] = ""
    else:
        row["human_overall_accept"] = overall or "true"
        row["human_ending_pressure"] = ending or "true"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow(row)


def test_preflight_marks_blank_templates_as_not_human_result(tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    _manifest(bundle)
    _reviewer(bundle / "reviewer-a-template.csv")
    _reviewer(bundle / "reviewer-b-template.csv")

    result = preflight(bundle)

    assert result["evidence_state"] == "templates_only_not_human_result"
    assert result["human_result_present"] is False
    assert result["template_is_not_human_result"] is True
    assert result["reviewer_files"]["reviewer-a-template.csv"]["state"] == "blank_template"


def test_completed_csv_requires_a_single_reviewer_identity(tmp_path):
    labels = tmp_path / "labels.csv"
    _reviewer(labels, "reviewer-a")
    result = validate_labels(labels, require_complete=True, require_single_reviewer=True)
    assert result["valid"] is True
    assert result["reviewer_ids"] == ["reviewer-a"]

    rows = list(csv.DictReader(labels.open(encoding="utf-8")))
    rows.append({**rows[0], "sample_id": "T18-02", "reviewer_id": "reviewer-other"})
    with labels.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    invalid = validate_labels(labels, require_complete=True, require_single_reviewer=True)
    assert invalid["valid"] is False
    assert any("exactly one non-empty reviewer_id" in error for error in invalid["errors"])


def test_adjudication_template_and_apply_preserve_disagreement_provenance(tmp_path):
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    _reviewer(a, "reviewer-a", overall="true", ending="true")
    _reviewer(b, "reviewer-b", overall="false", ending="true")
    merged_payload = merge(a, b)
    assert merged_payload["valid"] is True
    assert merged_payload["unresolved_adjudication_count"] == 1
    merged = tmp_path / "merged.json"
    merged.write_text(json.dumps(merged_payload), encoding="utf-8")

    decisions = tmp_path / "decisions.csv"
    template = create_template(merged, decisions)
    assert template["status"] == "human_decisions_required"
    decision_rows = list(csv.DictReader(decisions.open(encoding="utf-8")))
    assert decision_rows == [{
        "sample_id": "T18-01",
        "label": "human_overall_accept",
        "reviewer_a_value": "true",
        "reviewer_b_value": "false",
        "adjudicated_value": "",
        "adjudicator_id": "",
        "adjudication_rationale": "",
    }]
    decision_rows[0].update({
        "adjudicated_value": "true",
        "adjudicator_id": "adjudicator-1",
        "adjudication_rationale": "章节仍具备继续阅读的基本完成度。",
    })
    with decisions.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=decision_rows[0].keys())
        writer.writeheader()
        writer.writerows(decision_rows)

    adjudicated = apply_adjudication(merged, decisions)

    assert adjudicated["valid"] is True
    assert adjudicated["rows"][0]["human_overall_accept"] == "true"
    assert adjudicated["adjudication"]["decision_count"] == 1
    assert adjudicated["adjudication"]["decisions"][0]["reviewer_b_value"] == "false"


def test_preflight_requires_human_adjudication_for_real_disagreement(tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    _manifest(bundle)
    _reviewer(bundle / "reviewer-a-template.csv", "reviewer-a", overall="true")
    _reviewer(bundle / "reviewer-b-template.csv", "reviewer-b", overall="false")

    result = preflight(bundle)

    assert result["evidence_state"] == "human_adjudication_required"
    assert result["human_result_present"] is False
    assert result["merge_preview"]["unresolved_adjudication_count"] == 1
