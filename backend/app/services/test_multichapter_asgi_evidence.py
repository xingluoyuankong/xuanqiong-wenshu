from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_module():
    script = Path(__file__).resolve().parents[2] / "scripts" / "audit_multichapter_asgi_evidence.py"
    spec = importlib.util.spec_from_file_location("multichapter_asgi_evidence_test", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(path: Path, *, bad: bool = False) -> None:
    payload = {
        "requested_chapter_count": 2,
        "chapter_count": 2,
        "attempted_count": 2,
        "successful_count": 1,
        "rejected_count": 1,
        "pass_rate": 0.5,
        "attempt_results": [
            {"chapter_number": 1, "status": "successful", "content_char_count": 1200, "word_count_unit": "content_char_count_legacy_api_field"},
            {"chapter_number": 2, "status": "evaluation_failed", "content_char_count": 900, "word_count_unit": "content_char_count_legacy_api_field"},
        ],
        "chapters": [
            {"chapter_number": 1, "quality_metric_word_count": 1100, "word_count_unit": "quality_metric_word_count"},
            {"chapter_number": 2, "quality_metric_word_count": 800, "word_count_unit": "quality_metric_word_count"},
        ],
        "word_count_semantics": {
            "attempt_results.content_char_count": "persisted content character count",
            "chapters.quality_metric_word_count": "quality metric word count",
        },
        "distributions": {"score": {"n": 1}},
    }
    if bad:
        payload["chapters"][0]["content"] = "secret prose"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_multichapter_evidence_audit_accepts_consistent_redacted_report(tmp_path):
    path = tmp_path / "evidence.json"
    _write(path)
    result = _load_module().audit(path)
    assert result["valid"] is True
    assert result["pass_rate"] == 0.5
    assert result["distribution_sample_sizes"] == {"score": 1}


def test_multichapter_evidence_audit_rejects_prose_key(tmp_path):
    path = tmp_path / "bad.json"
    _write(path, bad=True)
    result = _load_module().audit(path)
    assert result["valid"] is False
    assert result["forbidden_key_paths"]


def test_multichapter_evidence_audit_rejects_runtime_prose_fields(tmp_path):
    path = tmp_path / "runtime-leak.json"
    _write(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["attempt_results"][0]["content_delta"] = "secret delta"
    payload["chapters"][0]["assembled_text"] = "secret assembled"
    payload["chapters"][1]["provider_response"] = "secret provider response"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    result = _load_module().audit(path)

    assert result["valid"] is False
    assert "prose-bearing keys present" in result["errors"]
    assert any("content_delta" in item for item in result["forbidden_key_paths"])
    assert any("assembled_text" in item for item in result["forbidden_key_paths"])
    assert any("provider_response" in item for item in result["forbidden_key_paths"])


def test_multichapter_evidence_audit_rejects_count_mismatch(tmp_path):
    path = tmp_path / "mismatch.json"
    _write(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["pass_rate"] = 1.0
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = _load_module().audit(path)
    assert result["valid"] is False
    assert "pass_rate does not match counts" in result["errors"]


def test_multichapter_evidence_audit_rejects_mislabeled_word_count_units(tmp_path):
    path = tmp_path / "unit-mismatch.json"
    _write(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["attempt_results"][0]["word_count_unit"] = "quality_metric_word_count"
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = _load_module().audit(path)
    assert result["valid"] is False
    assert "attempt word_count_unit does not declare content character semantics" in result["errors"]


def test_multichapter_evidence_audit_verifies_t18_exemption_score(tmp_path):
    path = tmp_path / "t18.json"
    _write(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["attempt_results"][1].update(
        {
            "exemptions": ["ending_pressure_missing"],
            "critique_exemption_applied": ["ending_pressure_missing"],
            "self_critique_final_score": 77.1,
        }
    )
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    result = _load_module().audit(path)

    assert result["valid"] is True
    assert result["verified_exemption_attempts"] == 1


def test_multichapter_evidence_audit_rejects_unproven_t18_exemption(tmp_path):
    path = tmp_path / "t18-invalid.json"
    _write(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["attempt_results"][1].update(
        {
            "exemptions": ["ending_pressure_missing"],
            "critique_exemption_applied": ["ending_pressure_missing"],
            "self_critique_final_score": 74.9,
        }
    )
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    result = _load_module().audit(path)

    assert result["valid"] is False
    assert "non-empty exemptions require self_critique_final_score >= 75" in result["errors"]
