from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
_REPAIR_FIELDS = {
    "repair_attempted",
    "revision_diagnostics",
    "issue_codes_before",
    "issue_codes_after",
    "passed_after_repair",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _issue_codes(value: Any) -> tuple[list[str] | None, str | None]:
    if not isinstance(value, list):
        return None, "issue_codes_missing_or_not_list"
    if any(not isinstance(code, str) or not code.strip() for code in value):
        return None, "issue_codes_contain_invalid_value"
    return sorted(set(value)), None


def _diagnostics_present(entry: dict[str, Any]) -> bool:
    if "revision_diagnostics" not in entry:
        return False
    diagnostics = entry.get("revision_diagnostics")
    if isinstance(diagnostics, list):
        return bool(diagnostics)
    if isinstance(diagnostics, dict):
        return bool(diagnostics)
    return False


def _provider_blocked(payload: dict[str, Any], probes: list[dict[str, Any]]) -> bool:
    statuses = [payload.get("status")]
    statuses.extend(probe.get("status") for probe in probes)
    for status in statuses:
        if isinstance(status, str) and "provider" in status.lower() and "block" in status.lower():
            return True
    return any(probe.get("provider_blocked") is True for probe in probes)


def _probes(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("probes")
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    single = payload.get("probe")
    if isinstance(single, dict):
        return [single]
    return []


def _repair_entries(probe: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    entries: list[tuple[str, dict[str, Any]]] = []
    versions = probe.get("versions")
    if isinstance(versions, list):
        for version_index, version in enumerate(versions):
            if not isinstance(version, dict):
                continue
            summaries = version.get("repair_summaries")
            if isinstance(summaries, list):
                for summary_index, summary in enumerate(summaries):
                    if isinstance(summary, dict):
                        entries.append((f"version_{version_index}_repair_{summary_index}", summary))
    summaries = probe.get("repair_summaries")
    if isinstance(summaries, list):
        for summary_index, summary in enumerate(summaries):
            if isinstance(summary, dict):
                entries.append((f"repair_{summary_index}", summary))
    singular = probe.get("repair_summary")
    if isinstance(singular, dict):
        entries.append(("repair_summary", singular))
    if any(field in probe for field in _REPAIR_FIELDS):
        entries.append(("probe_repair", probe))
    return entries


def _audit_item(probe: dict[str, Any], locator: str, entry: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    gate = _as_bool(probe.get("quality_gate_entered"))
    if gate is None:
        gate = _as_bool(entry.get("quality_gate_entered"))
    if gate is not True:
        reasons.append("quality_gate_not_entered_or_missing")

    attempted = _as_bool(entry.get("repair_attempted"))
    if attempted is not True:
        reasons.append("repair_not_attempted_or_missing")

    diagnostics_present = _diagnostics_present(entry)
    if not diagnostics_present:
        reasons.append("revision_diagnostics_missing_or_empty")

    before, before_error = _issue_codes(entry.get("issue_codes_before"))
    after, after_error = _issue_codes(entry.get("issue_codes_after"))
    if before_error:
        reasons.append(f"before_{before_error}")
    if after_error:
        reasons.append(f"after_{after_error}")

    strict_subset = bool(before is not None and after is not None and set(after) < set(before))
    declared = entry.get("strict_subset_improvement")
    if declared is not None:
        if not isinstance(declared, bool):
            reasons.append("strict_subset_declaration_invalid")
        elif declared != strict_subset:
            reasons.append("strict_subset_declaration_mismatch")
    if not strict_subset:
        reasons.append("strict_subset_improvement_not_proven")

    passed = _as_bool(entry.get("passed_after_repair"))
    if passed is not True:
        reasons.append("passed_after_repair_false_or_missing")

    outcome = entry.get("repair_outcome")
    outcome_value = outcome.strip().lower() if isinstance(outcome, str) else None
    if outcome_value == "unchanged":
        reasons.append("repair_outcome_unchanged")

    return {
        "locator": locator,
        "quality_gate_entered": gate,
        "repair_attempted": attempted,
        "revision_diagnostics_present": diagnostics_present,
        "issue_codes_before": before,
        "issue_codes_after": after,
        "strict_subset_improvement": strict_subset,
        "passed_after_repair": passed,
        "repair_outcome": outcome_value,
        "failure_reasons": sorted(set(reasons)),
        "gain_evidence_valid": not reasons,
    }


def audit_payload(payload: Any, *, source_sha256: str | None = None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "kind": "e11_repair_gain_audit",
            "schema_version": SCHEMA_VERSION,
            "generated_at": _utc_now(),
            "status": "insufficient",
            "gain_claimed": False,
            "checks": {"input_object": False, "provider_blocked": False, "evidence_complete": False},
            "counts": {},
            "items": [],
            "limitations": ["Input audit JSON is not an object; no repair gain is claimed."],
        }

    probes = _probes(payload)
    provider_blocked = _provider_blocked(payload, probes)
    items: list[dict[str, Any]] = []
    for probe_index, probe in enumerate(probes):
        for locator, entry in _repair_entries(probe):
            items.append(_audit_item(probe, f"probe_{probe_index}_{locator}", entry))

    attempted_count = sum(item["repair_attempted"] is True for item in items)
    diagnostics_count = sum(item["revision_diagnostics_present"] for item in items)
    strict_count = sum(item["strict_subset_improvement"] for item in items)
    passed_count = sum(item["passed_after_repair"] is True for item in items)
    unchanged_count = sum(item["repair_outcome"] == "unchanged" for item in items)
    valid_count = sum(item["gain_evidence_valid"] for item in items)
    evidence_complete = bool(items) and valid_count == len(items)

    checks = {
        "input_object": True,
        "task_is_e11_t22": payload.get("task") in (None, "E-11/T-22"),
        "provider_blocked": provider_blocked,
        "quality_gate_entered_for_all_items": bool(items) and all(item["quality_gate_entered"] is True for item in items),
        "repair_attempted_for_all_items": bool(items) and all(item["repair_attempted"] is True for item in items),
        "revision_diagnostics_for_all_items": bool(items) and all(item["revision_diagnostics_present"] for item in items),
        "before_after_issue_codes_for_all_items": bool(items)
        and all(item["issue_codes_before"] is not None and item["issue_codes_after"] is not None for item in items),
        "strict_subset_improvement_for_all_items": bool(items) and all(item["strict_subset_improvement"] for item in items),
        "passed_after_repair_for_all_items": bool(items) and all(item["passed_after_repair"] is True for item in items),
        "no_unchanged_outcome": unchanged_count == 0,
        "evidence_complete": evidence_complete,
    }

    if provider_blocked:
        status = "blocked"
        limitation = "Provider blocked before a quality-gate repair evidence cohort; no gain is claimed."
    elif not items:
        status = "insufficient"
        limitation = "No explicit repair evidence entries were found; no gain is claimed."
    elif evidence_complete:
        status = "observed"
        limitation = "Gain is observed only from complete redacted gate, diagnostics, issue-code and pass evidence."
    else:
        status = "insufficient"
        limitation = "Required redacted repair evidence is missing, unchanged, rejected, or lacks strict-subset/pass proof; no gain is claimed."

    return {
        "kind": "e11_repair_gain_audit",
        "schema_version": SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "source_sha256": source_sha256,
        "status": status,
        "gain_claimed": status == "observed",
        "checks": checks,
        "counts": {
            "probe_count": len(probes),
            "repair_entry_count": len(items),
            "repair_attempted_count": attempted_count,
            "diagnostics_present_count": diagnostics_count,
            "strict_subset_improvement_count": strict_count,
            "passed_after_repair_count": passed_count,
            "unchanged_outcome_count": unchanged_count,
            "valid_gain_evidence_count": valid_count,
        },
        "items": items,
        "limitations": [limitation, "Input is treated as redacted metadata; this audit does not call a Provider or read/output正文。"],
    }


def audit(path: str | Path) -> dict[str, Any]:
    source = Path(path).resolve()
    try:
        raw = source.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return audit_payload({"invalid_input": type(exc).__name__})
    return audit_payload(payload, source_sha256=hashlib.sha256(raw).hexdigest())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit redacted E-11/T-22 repair-gain evidence without calling a Provider.")
    parser.add_argument("audit_json", nargs="?", type=Path)
    parser.add_argument("--input", dest="input_path", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    source = args.input_path or args.audit_json
    if source is None:
        parser.error("one audit JSON input is required")
    result = audit(source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "gain_claimed": result["gain_claimed"], "counts": result["counts"]}, ensure_ascii=False))
    return 0 if result["status"] == "observed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
