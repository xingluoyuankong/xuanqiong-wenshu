from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


def _load_module():
    script = Path(__file__).resolve().parents[2] / "scripts" / "audit_t16_corrected_acceptance.py"
    spec = importlib.util.spec_from_file_location("t16_corrected_acceptance_test", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_evidence(tmp_path: Path, *, scorer_before: str = "old", scorer_after: str = "new") -> dict[str, Path]:
    missions = [
        {"mission_id": "m1", "input_content_sha256": "content-1"},
        {"mission_id": "m2", "input_content_sha256": "content-2"},
    ]
    manifest = {
        "kind": "t16_fixed_generation_input_manifest",
        "schema_version": 1,
        "generation_batch_id": "fixed-batch-001",
        "mission_contract_sha256": "mission-contract",
        "generation_request_contract_sha256": "request-contract",
        "provider": {"provider_host": "provider.test", "model": "model-a"},
        "records": missions,
    }
    input_path = tmp_path / "input-manifest.json"
    input_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    input_hash = hashlib.sha256(input_path.read_bytes()).hexdigest()

    def summary(scorer: str) -> dict:
        return {
            "status": "passed",
            "record_count": 2,
            "input_manifest_sha256": input_hash,
            "provider": {"provider_host": "provider.test", "model": "model-a"},
            "comparison_fingerprint": {
                "schema_version": 2,
                "mission_contract_sha256": "mission-contract",
                "generation_request_contract_sha256": "request-contract",
                "scorer_sha256": scorer,
                "mission_ids": ["m1", "m2"],
            },
            "records": [{"mission_id": "m1"}, {"mission_id": "m2"}],
        }

    def evaluator(production_scorer: str) -> dict:
        return {
            "kind": "t16_frozen_evaluator_report",
            "schema_version": 1,
            "status": "passed",
            "input_manifest_sha256": input_hash,
            "production_scorer_sha256": production_scorer,
            "evaluator": {
                "name": "frozen-human-proxy-evaluator",
                "version": "2026-08-23",
                "evaluator_sha256": "frozen-evaluator",
                "contract_sha256": "frozen-evaluator-contract",
                "frozen": True,
            },
            "record_count": 2,
            "records": missions,
            "aggregate": {"average_score": 80.0},
        }

    paths = {
        "input": input_path,
        "before": tmp_path / "before-summary.json",
        "after": tmp_path / "after-summary.json",
        "before_eval": tmp_path / "before-evaluator.json",
        "after_eval": tmp_path / "after-evaluator.json",
    }
    paths["before"].write_text(json.dumps(summary(scorer_before)), encoding="utf-8")
    paths["after"].write_text(json.dumps(summary(scorer_after)), encoding="utf-8")
    paths["before_eval"].write_text(json.dumps(evaluator(scorer_before)), encoding="utf-8")
    paths["after_eval"].write_text(json.dumps(evaluator(scorer_after)), encoding="utf-8")
    return paths


def _audit(paths: dict[str, Path]):
    return _load_module().audit(
        paths["input"], paths["before"], paths["after"], paths["before_eval"], paths["after_eval"]
    )


def test_corrected_acceptance_requires_fixed_input_and_independent_frozen_evaluator(tmp_path):
    payload = _audit(_write_evidence(tmp_path))
    assert payload["status"] == "eligible_for_t16_acceptance_review"
    assert payload["acceptance_ready"] is True
    assert payload["quality_gain_proven"] is False
    assert payload["provider_calls"] is False
    assert payload["evidence"]["evaluator_average_score_delta"] is None
    assert payload["blockers"] == []


def test_same_production_scorer_is_rejected(tmp_path):
    payload = _audit(_write_evidence(tmp_path, scorer_before="same", scorer_after="same"))
    assert payload["acceptance_ready"] is False
    assert "production_scorer_not_changed" in payload["blockers"]


def test_changed_generation_request_is_rejected(tmp_path):
    paths = _write_evidence(tmp_path)
    data = json.loads(paths["after"].read_text(encoding="utf-8"))
    data["comparison_fingerprint"]["generation_request_contract_sha256"] = "changed-request"
    paths["after"].write_text(json.dumps(data), encoding="utf-8")
    payload = _audit(paths)
    assert payload["acceptance_ready"] is False
    assert "fixed_generation_request_mismatch" in payload["blockers"]


def test_different_frozen_evaluators_are_rejected(tmp_path):
    paths = _write_evidence(tmp_path)
    data = json.loads(paths["after_eval"].read_text(encoding="utf-8"))
    data["evaluator"]["evaluator_sha256"] = "different-evaluator"
    paths["after_eval"].write_text(json.dumps(data), encoding="utf-8")
    payload = _audit(paths)
    assert payload["acceptance_ready"] is False
    assert "evaluator_not_same_and_independent" in payload["blockers"]


def test_evaluator_must_bind_to_corresponding_production_scorer(tmp_path):
    paths = _write_evidence(tmp_path)
    data = json.loads(paths["before_eval"].read_text(encoding="utf-8"))
    data["production_scorer_sha256"] = "unrelated"
    paths["before_eval"].write_text(json.dumps(data), encoding="utf-8")
    payload = _audit(paths)
    assert payload["acceptance_ready"] is False
    assert "evaluator_scorer_binding_mismatch" in payload["blockers"]


def test_missing_or_mismatched_input_content_is_rejected(tmp_path):
    paths = _write_evidence(tmp_path)
    data = json.loads(paths["after_eval"].read_text(encoding="utf-8"))
    data["records"][1]["input_content_sha256"] = "different-content"
    paths["after_eval"].write_text(json.dumps(data), encoding="utf-8")
    payload = _audit(paths)
    assert payload["acceptance_ready"] is False
    assert "invalid_frozen_evaluator_reports" in payload["blockers"]
