from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.merge_quality_annotations import CORE_LABELS, merge


def _write(path: Path, reviewer: str, value: str = "true"):
    row = {"sample_id": "Q001", "source_version_id": "1", "source_chapter_id": "1", "content_sha256": "a" * 64, "reviewer_id": reviewer, **{label: value for label in CORE_LABELS}}
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=row.keys()); writer.writeheader(); writer.writerow(row)


def test_annotation_merge_requires_matching_distinct_reviewers_and_reports_agreement(tmp_path):
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    _write(a, "r1", "true"); _write(b, "r2", "true")
    result = merge(a, b)
    assert result["valid"] is True
    assert result["complete_agreement_row_count"] == 1
    assert result["agreement"]["human_overall_accept"] == {"agree": 1, "disagree": 0, "unlabeled": 0}
    assert result["rows"][0]["human_overall_accept"] == "true"
    assert result["rows"][0]["identity"]["content_sha256"] == "a" * 64


def test_annotation_merge_rejects_same_sample_id_with_different_content_hash(tmp_path):
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    _write(a, "r1"); _write(b, "r2")
    rows = list(csv.DictReader(b.open(encoding="utf-8")))
    rows[0]["content_sha256"] = "b" * 64
    with b.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader(); writer.writerows(rows)

    result = merge(a, b)

    assert result["valid"] is False
    assert any("content_sha256 does not match" in error for error in result["errors"])


def test_annotation_merge_rejects_mixed_reviewer_ids_within_one_file(tmp_path):
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    fields = ["sample_id", "source_version_id", "source_chapter_id", "content_sha256", "reviewer_id", *CORE_LABELS]
    rows_a = [
        {"sample_id": "Q001", "source_version_id": "1", "source_chapter_id": "1", "content_sha256": "a" * 64, "reviewer_id": "r1", **{label: "true" for label in CORE_LABELS}},
        {"sample_id": "Q002", "source_version_id": "2", "source_chapter_id": "2", "content_sha256": "b" * 64, "reviewer_id": "r3", **{label: "true" for label in CORE_LABELS}},
    ]
    rows_b = [
        {"sample_id": "Q001", "source_version_id": "1", "source_chapter_id": "1", "content_sha256": "a" * 64, "reviewer_id": "r2", **{label: "true" for label in CORE_LABELS}},
        {"sample_id": "Q002", "source_version_id": "2", "source_chapter_id": "2", "content_sha256": "b" * 64, "reviewer_id": "r2", **{label: "true" for label in CORE_LABELS}},
    ]
    for path, rows in ((a, rows_a), (b, rows_b)):
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)

    result = merge(a, b)

    assert result["valid"] is False
    assert any("first reviewer file must contain exactly one" in error for error in result["errors"])


def test_annotation_merge_rejects_misaligned_samples_and_marks_disagreement(tmp_path):
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    _write(a, "r1", "true"); _write(b, "r1", "false")
    result = merge(a, b)
    assert result["valid"] is False
    assert any("distinct" in error for error in result["errors"])
    assert result["agreement"]["human_overall_accept"]["disagree"] == 1
    assert result["rows"][0]["human_overall_accept"] == "adjudicate"
