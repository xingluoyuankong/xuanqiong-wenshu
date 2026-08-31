from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


def _load_module():
    script = Path(__file__).resolve().parents[2] / "scripts" / "audit_quality_bench_comparability.py"
    spec = importlib.util.spec_from_file_location("quality_bench_comparability_test", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _summary(path: Path, *, scorer: str, generated_at: str) -> None:
    payload = {
        "generated_at": generated_at,
        "generation_started_at": generated_at,
        "record_count": 2,
        "comparison_fingerprint": {
            "schema_version": 2,
            "record_count": 2,
            "mission_ids": ["m1", "m2"],
            "mission_contract_sha256": "mission",
            "generation_request_contract_sha256": "request",
            "scorer_sha256": scorer,
            "comparison_contract_sha256": "comparison-" + scorer,
        },
        "provider": {"provider_host": "provider.test", "model": "model-a"},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    payload["status"] = "passed"
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_strict_audit_finds_only_scorer_changed_pair(tmp_path):
    _summary(tmp_path / "a" / "rescore-summary.json", scorer="old", generated_at="2026-08-20T00:00:00Z")
    _summary(tmp_path / "b" / "rescore-summary.json", scorer="new", generated_at="2026-08-22T00:00:00Z")
    payload = _load_module().audit(tmp_path)
    assert payload["candidate_pair_count"] == 1
    assert payload["comparable_pair_count"] == 0
    assert payload["non_comparable_candidate_pair_count"] == 1
    assert payload["complete_fingerprint_count"] == 2
    assert payload["candidate_pairs"][0]["mission_ids"] == ["m1", "m2"]


def test_strict_audit_rejects_missing_request_contract(tmp_path):
    _summary(tmp_path / "a" / "rescore-summary.json", scorer="old", generated_at="2026-08-20T00:00:00Z")
    data = json.loads((tmp_path / "a" / "rescore-summary.json").read_text(encoding="utf-8"))
    data["comparison_fingerprint"]["generation_request_contract_sha256"] = None
    (tmp_path / "a" / "rescore-summary.json").write_text(json.dumps(data), encoding="utf-8")
    payload = _load_module().audit(tmp_path)
    assert payload["candidate_pair_count"] == 0
    assert payload["complete_fingerprint_count"] == 0


def test_strict_audit_positive_contract_break_is_detectable(monkeypatch, tmp_path):
    _summary(tmp_path / "a" / "rescore-summary.json", scorer="old", generated_at="2026-08-20T00:00:00Z")
    _summary(tmp_path / "b" / "rescore-summary.json", scorer="new", generated_at="2026-08-22T00:00:00Z")
    module = _load_module()
    original = module._strict_group_key
    monkeypatch.setattr(module, "_strict_group_key", lambda item: None)
    payload = module.audit(tmp_path)
    assert payload["candidate_pair_count"] == 0
    monkeypatch.setattr(module, "_strict_group_key", original)
    assert module.audit(tmp_path)["candidate_pair_count"] == 1

def test_strict_audit_counts_same_scorer_pair_as_comparable(tmp_path):
    _summary(tmp_path / "a" / "rescore-summary.json", scorer="same", generated_at="2026-08-20T00:00:00Z")
    _summary(tmp_path / "b" / "rescore-summary.json", scorer="same", generated_at="2026-08-22T00:00:00Z")
    payload = _load_module().audit(tmp_path)
    assert payload["candidate_pair_count"] == 0
    assert payload["comparable_pair_count"] == 1
    assert payload["non_comparable_candidate_pair_count"] == 0
    assert payload["comparable_pairs"][0]["mission_ids"] == ["m1", "m2"]


def test_strict_audit_rejects_same_scorer_with_different_comparison_contract(tmp_path):
    _summary(tmp_path / "a" / "rescore-summary.json", scorer="same", generated_at="2026-08-20T00:00:00Z")
    _summary(tmp_path / "b" / "rescore-summary.json", scorer="same", generated_at="2026-08-22T00:00:00Z")
    path = tmp_path / "b" / "rescore-summary.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["comparison_fingerprint"]["comparison_contract_sha256"] = "different-contract"
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = _load_module().audit(tmp_path)
    assert result["candidate_pair_count"] == 1
    assert result["comparable_pair_count"] == 0
    assert result["non_comparable_candidate_pair_count"] == 1


@pytest.mark.parametrize("generation_started_at", [None, ""])
def test_strict_audit_uses_legacy_generated_at_when_generation_started_at_is_missing(tmp_path, generation_started_at):
    _summary(tmp_path / "a" / "rescore-summary.json", scorer="same", generated_at="2026-08-20T00:00:00Z")
    _summary(tmp_path / "b" / "rescore-summary.json", scorer="same", generated_at="2026-08-22T00:00:00Z")
    for path in (tmp_path / "a" / "rescore-summary.json", tmp_path / "b" / "rescore-summary.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        if generation_started_at is None:
            data.pop("generation_started_at", None)
        else:
            data["generation_started_at"] = generation_started_at
        path.write_text(json.dumps(data), encoding="utf-8")

    result = _load_module().audit(tmp_path)

    assert result["candidate_pair_count"] == 0
    assert result["comparable_pair_count"] == 1
    assert result["ambiguous_time_pair_count"] == 0


def test_strict_audit_reports_equal_legacy_generated_at_as_ambiguous(tmp_path):
    _summary(tmp_path / "a" / "rescore-summary.json", scorer="same", generated_at="2026-08-20T00:00:00Z")
    _summary(tmp_path / "b" / "rescore-summary.json", scorer="same", generated_at="2026-08-20T00:00:00Z")
    for path in (tmp_path / "a" / "rescore-summary.json", tmp_path / "b" / "rescore-summary.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        data.pop("generation_started_at", None)
        path.write_text(json.dumps(data), encoding="utf-8")

    result = _load_module().audit(tmp_path)

    assert result["candidate_pair_count"] == 0
    assert result["comparable_pair_count"] == 0
    assert result["ambiguous_time_pair_count"] == 1
    assert result["ambiguous_time_pairs"][0]["reason"] == "missing_or_equal_generated_at"


def test_strict_audit_reads_generation_started_at_from_live_status(tmp_path):
    _summary(tmp_path / "a" / "rescore-summary.json", scorer="same", generated_at="2026-08-20T00:00:00Z")
    _summary(tmp_path / "b" / "rescore-summary.json", scorer="same", generated_at="2026-08-22T00:00:00Z")
    for path, started_at in (
        (tmp_path / "a", "2026-08-20T00:01:00Z"),
        (tmp_path / "b", "2026-08-22T00:01:00Z"),
    ):
        payload = json.loads((path / "rescore-summary.json").read_text(encoding="utf-8"))
        payload.pop("generation_started_at", None)
        (path / "rescore-summary.json").write_text(json.dumps(payload), encoding="utf-8")
        (path / "live-status.json").write_text(json.dumps({"generation_started_at": started_at}), encoding="utf-8")

    result = _load_module().audit(tmp_path)

    assert result["candidate_pair_count"] == 0
    assert result["comparable_pair_count"] == 1
    assert result["ambiguous_time_pair_count"] == 0
