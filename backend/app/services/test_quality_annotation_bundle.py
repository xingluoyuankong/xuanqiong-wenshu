from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from scripts.export_quality_annotation_bundle import export_bundle, main, validate_labels


def _db(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE chapter_versions (id INTEGER, chapter_id INTEGER, content TEXT, metadata TEXT, created_at TEXT)")
    connection.executemany(
        "INSERT INTO chapter_versions VALUES (?, ?, ?, ?, ?)",
        [
            (1, 1, "SECRET_PROSE_A", json.dumps({"quality_metrics": {"ending_pressure_passed": True, "dialogue_changes_state": True}}), "2026-01-01"),
            (2, 2, "SECRET_PROSE_B", json.dumps({"quality_metrics": {"ending_pressure_passed": False}, "quality_gate": {"blockers": [{"code": "ending_pressure_missing"}]}}), "2026-01-02"),
        ],
    )
    connection.commit(); connection.close()


def test_annotation_bundle_is_redacted_by_default_and_stratifies(tmp_path):
    database = tmp_path / "novel.db"; _db(database)
    output = tmp_path / "bundle"
    manifest = export_bundle(database, output, sample_size=2)
    assert manifest["content_emitted"] is False
    assert manifest["selected_count"] == 2
    assert "SECRET_PROSE" not in "\n".join(path.read_text(encoding="utf-8") for path in output.iterdir())
    readme = (output / "README.md").read_text(encoding="utf-8")
    assert "--validate-labels" in readme
    assert "merge_quality_annotations.py" in readme
    assert database.name in readme
    labels = list(csv.DictReader((output / "labels.csv").open(encoding="utf-8")))
    assert {row["bucket"] for row in labels} == {"clean_pass", "blocker"}


def test_annotation_bundle_requires_explicit_content_path_and_validates_labels(tmp_path):
    database = tmp_path / "novel.db"; _db(database)
    output = tmp_path / "bundle"
    try:
        export_bundle(database, output, include_content=True)
    except ValueError as exc:
        assert "content-output" in str(exc)
    else:
        raise AssertionError("content export must require explicit path")
    export_bundle(database, output, include_content=True, content_output=tmp_path / "private.jsonl")
    assert "SECRET_PROSE_A" in (tmp_path / "private.jsonl").read_text(encoding="utf-8")
    labels_file = output / "labels.csv"
    rows = list(csv.DictReader(labels_file.open(encoding="utf-8")))
    rows[0]["human_overall_accept"] = "maybe"; rows[0]["reviewer_id"] = "r1"
    with labels_file.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys()); writer.writeheader(); writer.writerows(rows)
    result = validate_labels(labels_file)
    assert result["valid"] is False
    assert "true/false/na" in result["errors"][0]

def test_annotation_validator_binds_rows_to_manifest_identity(tmp_path):
    database = tmp_path / "novel.db"; _db(database)
    output = tmp_path / "bundle"
    export_bundle(database, output, sample_size=2)
    labels_file = output / "labels.csv"
    rows = list(csv.DictReader(labels_file.open(encoding="utf-8")))
    rows[0]["content_sha256"] = "b" * 64
    with labels_file.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys()); writer.writeheader(); writer.writerows(rows)
    result = validate_labels(labels_file, output / "manifest.json")
    assert result["valid"] is False
    assert any("content_sha256 does not match manifest" in error for error in result["errors"])


def test_annotation_validator_rejects_duplicate_or_missing_sample_ids(tmp_path):
    labels = tmp_path / "labels.csv"
    labels.write_text("sample_id,human_overall_accept,reviewer_id\nQ001,true,reviewer-a\nQ001,,\n", encoding="utf-8")
    result = validate_labels(labels)
    assert result["valid"] is False
    assert any("duplicate sample_id" in error for error in result["errors"])


def test_annotation_validator_cli_does_not_require_database_or_output_dir(tmp_path):
    labels = tmp_path / "labels.csv"
    labels.write_text(
        "sample_id,human_overall_accept,reviewer_id\nQ001,true,reviewer-a\n",
        encoding="utf-8",
    )
    assert main(["--validate-labels", str(labels)]) == 0



def test_annotation_validator_require_complete_rejects_blank_template_and_accepts_complete_rows(tmp_path):
    labels = tmp_path / "labels.csv"
    headers = ["sample_id", *[
        "human_overall_accept", "human_ending_pressure", "human_dialogue_changes_state",
        "human_late_reversal", "human_speaker_distinct", "human_balance_acceptable",
        "human_scene_transition_clear", "human_static_description_excessive",
    ], "reviewer_id"]
    labels.write_text(",".join(headers) + "\nQ001,,,,,,,,,\n", encoding="utf-8")
    blank = validate_labels(labels, require_complete=True)
    assert blank["valid"] is False
    assert any("complete labels required" in error for error in blank["errors"])
    rows = list(csv.DictReader(labels.open(encoding="utf-8")))
    for key in headers[1:-1]: rows[0][key] = "na"
    rows[0]["reviewer_id"] = "reviewer-a"
    with labels.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers); writer.writeheader(); writer.writerows(rows)
    complete = validate_labels(labels, require_complete=True)
    assert complete["valid"] is True
    assert complete["complete_labeled_row_count"] == 1


def test_annotation_validator_cli_require_complete_flag_rejects_blank_rows(tmp_path):
    labels = tmp_path / "labels.csv"
    labels.write_text("sample_id,human_overall_accept,reviewer_id\nQ001,,\n", encoding="utf-8")
    assert main(["--validate-labels", str(labels), "--require-complete"]) == 1
