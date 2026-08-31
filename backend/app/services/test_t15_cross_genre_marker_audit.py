import json
from pathlib import Path

from app.scripts_t15_loader import load_t15_module


def _write_e08(tmp_path: Path):
    run = tmp_path / "e08"
    run.mkdir()
    records = []
    for mission_id in ("benchmark-action-3000", "benchmark-dialogue-romance-1500", "smoke-opening"):
        records.append({"mission_id": mission_id, "event_density_passed": True})
        (run / f"{mission_id}.txt").write_text(
            "她逼问对方，证据暴露，门外脚步逼近。" * 80,
            encoding="utf-8",
        )
    (run / "rescore-summary.json").write_text(json.dumps({"records": records}), encoding="utf-8")
    return run


def _write_e09(tmp_path: Path):
    path = tmp_path / "e09.json"
    path.write_text(json.dumps({
        "requested_chapter_count": 2,
        "chapters": [
            {"chapter_number": 1, "status": "successful", "ending_pressure_passed": True, "event_density_passed": True, "reversal_signal_count": 1, "reversal_in_late_section": True},
            {"chapter_number": 2, "status": "evaluation_failed"},
        ],
    }), encoding="utf-8")
    return path


def test_t15_audit_classifies_genre_groups_without_emitting_text(tmp_path):
    module = load_t15_module()
    report = module.audit(_write_e08(tmp_path), _write_e09(tmp_path))
    assert report["e08"]["observed_genre_groups"] == ["action", "dialogue-romance"]
    assert report["e08"]["missing_expected_genre_groups"]
    assert report["e08"]["group_coverage"]["action"]["ending_pressure_pass_rate"] == 1.0
    assert report["redaction"]["content_emitted"] is False
    assert "她逼问" not in json.dumps(report, ensure_ascii=False)


def test_t15_audit_marks_e09_genre_and_marker_coverage_as_unavailable(tmp_path):
    module = load_t15_module()
    report = module.audit(_write_e08(tmp_path), _write_e09(tmp_path))
    e09 = report["e09"]
    assert e09["chapter_row_count"] == 2
    assert e09["evaluation_failed_row_count"] == 1
    assert e09["genre_label_available"] is False
    assert e09["raw_marker_text_available"] is False
    assert e09["marker_coverage_auditable"] is False


def test_t15_audit_does_not_treat_smoke_as_a_genre_fixture(tmp_path):
    module = load_t15_module()
    report = module.audit(_write_e08(tmp_path), _write_e09(tmp_path))
    assert report["e08"]["genre_fixture_count"] == 2
    assert report["e08"]["smoke_supplement_count"] == 1