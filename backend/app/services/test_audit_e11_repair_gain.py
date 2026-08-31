from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "audit_e11_repair_gain.py"


def _module():
    spec = importlib.util.spec_from_file_location("audit_e11_repair_gain", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _payload(*, before=None, after=None, diagnostics=None, passed=True, outcome="improved", gate=True, attempted=True):
    before = ["ending_pressure_missing", "static_description_risk"] if before is None else before
    after = ["static_description_risk"] if after is None else after
    entry = {
        "repair_attempted": attempted,
        "revision_diagnostics": [{"strategy": "redacted", "changed": True}],
        "issue_codes_before": before,
        "issue_codes_after": after,
        "passed_after_repair": passed,
        "repair_outcome": outcome,
    }
    if diagnostics is None:
        diagnostics = entry["revision_diagnostics"]
    entry["revision_diagnostics"] = diagnostics
    return {"task": "E-11/T-22", "status": "real_repair_triggered", "probes": [{"quality_gate_entered": gate, "versions": [{"repair_summaries": [entry]}]}]}


def test_complete_redacted_strict_subset_and_pass_is_observed():
    result = _module().audit_payload(_payload())
    assert result["status"] == "observed"
    assert result["gain_claimed"] is True
    assert result["checks"]["evidence_complete"] is True
    assert result["counts"]["strict_subset_improvement_count"] == 1
    assert result["counts"]["passed_after_repair_count"] == 1


def test_existing_triggered_schema_is_insufficient_not_gain():
    source = Path(__file__).resolve().parents[2] / "output" / "e11-t22-real-repair-triggered-audit-20260823.json"
    result = _module().audit(source)
    assert result["status"] == "insufficient"
    assert result["gain_claimed"] is False
    assert result["checks"]["revision_diagnostics_for_all_items"] is False
    assert result["counts"]["unchanged_outcome_count"] == 2


def test_provider_blocked_is_blocked_and_never_claims_gain():
    result = _module().audit_payload({
        "task": "E-11/T-22",
        "status": "provider_blocked_before_quality_gate",
        "probe": {"quality_gate_entered": False, "repair_entered": False, "revision_diagnostics_persisted": False},
    })
    assert result["status"] == "blocked"
    assert result["gain_claimed"] is False
    assert result["checks"]["provider_blocked"] is True


@pytest.mark.parametrize(
    "changes,expected_reason",
    [
        ({"diagnostics": []}, "revision_diagnostics_missing_or_empty"),
        ({"after": ["ending_pressure_missing", "static_description_risk"]}, "strict_subset_improvement_not_proven"),
        ({"passed": False}, "passed_after_repair_false_or_missing"),
        ({"outcome": "unchanged"}, "repair_outcome_unchanged"),
        ({"gate": False}, "quality_gate_not_entered_or_missing"),
    ],
)
def test_missing_or_negative_gain_evidence_is_insufficient(changes, expected_reason):
    result = _module().audit_payload(_payload(**changes))
    assert result["status"] == "insufficient"
    assert result["gain_claimed"] is False
    assert expected_reason in result["items"][0]["failure_reasons"]


def test_declared_strict_subset_mismatch_is_rejected():
    payload = _payload()
    payload["probes"][0]["versions"][0]["repair_summaries"][0]["strict_subset_improvement"] = False
    result = _module().audit_payload(payload)
    assert result["status"] == "insufficient"
    assert "strict_subset_declaration_mismatch" in result["items"][0]["failure_reasons"]


def test_singular_blocked_schema_is_adapted_without_repair_entry():
    source = Path(__file__).resolve().parents[2] / "output" / "e11-t22-real-repair-diagnostics-probe-blocked-20260823-late-run.json"
    result = _module().audit(source)
    assert result["status"] == "blocked"
    assert result["counts"]["repair_entry_count"] == 0


def test_audit_does_not_expose_revision_diagnostics_payload():
    payload = _payload()
    payload["probes"][0]["versions"][0]["repair_summaries"][0]["revision_diagnostics"] = [{"content": "secret body"}]
    result = _module().audit_payload(payload)
    assert "secret body" not in str(result)
