from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).with_name("audit_t06_standardized_rate.py")


def _module():
    spec = importlib.util.spec_from_file_location("audit_t06_standardized_rate", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _summary(tmp_path: Path, name: str, *, model: str = "model-a", contract_suffix: str = "a", status: str = "passed", retry: bool = False, retry_field: bool = True, blocked: bool = False) -> Path:
    module = _module()
    missions = ["m-01"]
    fingerprint = {
        "schema_version": 2,
        "record_count": 1,
        "mission_ids": missions,
        "mission_contract_sha256": f"mission-{contract_suffix}",
        "generation_request_contract_sha256": f"request-{contract_suffix}",
        "scorer_sha256": f"scorer-{contract_suffix}",
        "comparison_contract_sha256": f"comparison-{contract_suffix}",
    }
    retry_events = [{"attempt": 1, "error_type": "LiveProviderBlocked", "retryable": True}] if retry else []
    call = {"mission_id": "m-01", "attempts": 2 if retry else 1}
    if retry_field:
        call["retry_events"] = retry_events
    payload = {
        "status": status,
        "record_count": 1,
        "records": [{"mission_id": "m-01", "score": 1}],
        "provider": {"provider_host": "provider.example", "model": model},
        "probe": {"ready": not blocked, "status_code": 503 if blocked else 200, "model_listed": not blocked},
        "comparison_fingerprint": fingerprint,
        "live_calls": [call],
        "live_failures": ([{"mission_id": "m-01", "error_type": "LiveProviderBlocked", "error": "redacted"}] if blocked else []),
    }
    path = tmp_path / name / "rescore-summary.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert module._sha256_file(path)
    return path


def test_same_contract_cohort_emits_observed_retry_rate(tmp_path):
    first = _summary(tmp_path, "one", retry=True)
    second = _summary(tmp_path, "two", retry=False)
    result = _module().audit_summaries([first, second], min_batches=2, min_calls=2)
    assert result["status"] == "observed"
    assert result["rates"]["degrade_rate"] == 0.5
    assert result["rates"]["retry_event_rate"] == 0.5
    assert result["cohort"]["eligible_live_call_count"] == 2


def test_missing_retry_events_is_excluded_without_zero_backfill(tmp_path):
    valid = _summary(tmp_path, "valid")
    missing = _summary(tmp_path, "missing", retry_field=False)
    result = _module().audit_summaries([valid, missing], min_batches=1, min_calls=1)
    assert result["status"] == "observed"
    assert result["rates"]["degrade_rate"] == 0.0
    assert result["cohort"]["eligible_batch_count"] == 1
    excluded = next(item for item in result["batches"] if "missing_retry_events" in item["reasons"])
    assert excluded["eligible"] is False


def test_mixed_model_or_contract_is_insufficient_and_has_no_rate(tmp_path):
    first = _summary(tmp_path, "one")
    second = _summary(tmp_path, "two", model="model-b")
    result = _module().audit_summaries([first, second], min_batches=1, min_calls=1)
    assert result["status"] == "insufficient"
    assert result["rates"]["degrade_rate"] is None
    assert result["checks"]["single_model_provider_contract"] is False


def test_provider_block_is_excluded_and_not_code_failure(tmp_path):
    blocked = _summary(tmp_path, "blocked", status="failed", blocked=True)
    result = _module().audit_summaries([blocked], min_batches=1, min_calls=1)
    assert result["status"] == "blocked"
    assert result["rates"]["degrade_rate"] is None
    assert result["cohort"]["excluded_provider_blocked_batch_count"] == 1
    assert result["checks"]["provider_blocks_are_not_code_failures"] is True
    assert "code_failure" not in result["batches"][0]["reasons"]


def test_contract_mismatch_is_not_silently_merged(tmp_path):
    first = _summary(tmp_path, "one")
    second = _summary(tmp_path, "two", contract_suffix="b")
    result = _module().audit_summaries([first, second], min_batches=1, min_calls=1)
    assert result["status"] == "insufficient"
    assert result["rates"]["degrade_rate"] is None
    assert result["cohort"]["eligible_batch_count"] == 2
    assert result["checks"]["single_model_provider_contract"] is False


def test_manifest_locks_paths_and_expected_contract(tmp_path):
    first = _summary(tmp_path, "one")
    second = _summary(tmp_path, "two")
    contract = _module()._contract_from_payload(json.loads(first.read_text(encoding="utf-8")))
    expected = _module()._contract_json(contract)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "summaries": [str(first), str(second)],
        "expected_contract": expected,
        "min_batches": 2,
        "min_calls": 2,
    }), encoding="utf-8")
    paths, expected_contract, min_batches, min_calls = _module()._load_manifest(manifest)
    result = _module().audit_summaries(paths, expected_contract=expected_contract, min_batches=min_batches, min_calls=min_calls)
    assert result["status"] == "observed"
    assert result["input_contract"]["reproducible"] is True
    assert result["input_contract"]["summary_sha256"] == [
        _module()._sha256_file(first), _module()._sha256_file(second)
    ]


def test_provider_ready_but_final_failure_still_has_no_numeric_rate(tmp_path):
    failed = _summary(tmp_path, "failed", status="failed")
    payload = json.loads(failed.read_text(encoding="utf-8"))
    payload["live_failures"] = [{"mission_id": "m-01", "error_type": "RuntimeError", "error": "redacted"}]
    failed.write_text(json.dumps(payload), encoding="utf-8")
    result = _module().audit_summaries([failed], min_batches=1, min_calls=1)
    assert result["status"] == "insufficient"
    assert result["rates"]["degrade_rate"] is None
    assert result["batches"][0]["provider_blocked"] is False

