"""Audit a reproducible, same-contract T-06 retry/degrade observation cohort.

This tool deliberately does not scan the whole output tree.  Callers must pass
an explicit list of ``rescore-summary.json`` files (or a manifest containing
that list).  A batch is eligible only when its live calls, retry schema,
provider probe, and complete comparison fingerprint are all present.  Final
provider blocks are reported and excluded from the denominator; they are not
classified as code failures and never produce a numeric rate.

The observed degrade rate is explicitly defined as:

    calls_with_retry_events / eligible_live_calls

``retry_event_rate`` is also emitted for diagnostic purposes.  Neither metric
is emitted as a number until one single model/provider/mission/contract cohort
meets the requested batch and call minimums.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


FINGERPRINT_KEYS = (
    "schema_version",
    "record_count",
    "mission_ids",
    "mission_contract_sha256",
    "generation_request_contract_sha256",
    "scorer_sha256",
    "comparison_contract_sha256",
)

CONTRACT_KEYS = (
    "schema_version",
    "mission_ids",
    "mission_contract_sha256",
    "generation_request_contract_sha256",
    "scorer_sha256",
    "comparison_contract_sha256",
    "provider_host",
    "model",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any] | None:
    return value if isinstance(value, list) else None


def _normalise_mission_ids(value: Any) -> tuple[str, ...] | None:
    values = _as_list(value)
    if values is None or not values or any(not isinstance(item, str) or not item for item in values):
        return None
    result = tuple(sorted(values))
    return result if len(set(result)) == len(result) else None


def _provider_blocked(payload: dict[str, Any]) -> bool:
    probe = _as_dict(payload.get("probe"))
    if probe and probe.get("ready") is False:
        return True
    for failure in _as_list(payload.get("live_failures")) or []:
        if not isinstance(failure, dict):
            continue
        error_type = str(failure.get("error_type") or "").lower()
        error_text = str(failure.get("error") or "").lower()
        if (
            "provider" in error_type
            or "transport" in error_type
            or "provider" in error_text
            or "http " in error_text
            or "sse" in error_text
        ):
            return True
    return False


def _resolve_summary_path(path: Path, *, base_dir: Path | None = None) -> Path:
    candidate = path if path.is_absolute() else ((base_dir or Path.cwd()) / path)
    candidate = candidate.resolve()
    if candidate.is_dir():
        candidate = (candidate / "rescore-summary.json").resolve()
    return candidate


def _load_manifest(path: Path) -> tuple[list[Path], dict[str, Any], int, int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("manifest must be a JSON object")
    raw_summaries = payload.get("summaries")
    if not isinstance(raw_summaries, list) or not raw_summaries:
        raise ValueError("manifest.summaries must be a non-empty list")
    summaries = [_resolve_summary_path(Path(str(item)), base_dir=path.parent) for item in raw_summaries]
    expected = payload.get("expected_contract")
    if expected is None:
        expected = {}
    if not isinstance(expected, dict):
        raise ValueError("manifest.expected_contract must be an object")
    return (
        summaries,
        expected,
        int(payload.get("min_batches", 2)),
        int(payload.get("min_calls", 20)),
    )


def _expected_contract(value: dict[str, Any]) -> tuple[Any, ...] | None:
    if not value:
        return None
    missing = [key for key in CONTRACT_KEYS if key not in value]
    if missing:
        raise ValueError(f"expected_contract missing keys: {', '.join(missing)}")
    mission_ids = _normalise_mission_ids(value.get("mission_ids"))
    if mission_ids is None:
        raise ValueError("expected_contract.mission_ids must be a non-empty unique string list")
    return (
        value.get("schema_version"),
        mission_ids,
        str(value.get("mission_contract_sha256")),
        str(value.get("generation_request_contract_sha256")),
        str(value.get("scorer_sha256")),
        str(value.get("comparison_contract_sha256")),
        str(value.get("provider_host")),
        str(value.get("model")),
    )


def _contract_from_payload(payload: dict[str, Any]) -> tuple[Any, ...] | None:
    fingerprint = _as_dict(payload.get("comparison_fingerprint"))
    provider = _as_dict(payload.get("provider"))
    mission_ids = _normalise_mission_ids(fingerprint.get("mission_ids"))
    if mission_ids is None:
        return None
    return (
        fingerprint.get("schema_version"),
        mission_ids,
        fingerprint.get("mission_contract_sha256"),
        fingerprint.get("generation_request_contract_sha256"),
        fingerprint.get("scorer_sha256"),
        fingerprint.get("comparison_contract_sha256"),
        str(provider.get("provider_host") or ""),
        str(provider.get("model") or ""),
    )


def _contract_json(key: tuple[Any, ...] | None) -> dict[str, Any] | None:
    if key is None:
        return None
    return {
        "schema_version": key[0],
        "mission_ids": list(key[1]),
        "mission_contract_sha256": key[2],
        "generation_request_contract_sha256": key[3],
        "scorer_sha256": key[4],
        "comparison_contract_sha256": key[5],
        "provider_host": key[6],
        "model": key[7],
    }


def _validate_batch(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    status = str(payload.get("status") or "unknown")
    blocked = _provider_blocked(payload)
    fingerprint = _as_dict(payload.get("comparison_fingerprint"))
    provider = _as_dict(payload.get("provider"))
    probe = _as_dict(payload.get("probe"))
    calls = _as_list(payload.get("live_calls"))
    records = _as_list(payload.get("records"))
    live_failures = _as_list(payload.get("live_failures")) or []
    contract = _contract_from_payload(payload)

    if blocked:
        reasons.append("provider_blocked")
    if status != "passed":
        reasons.append("non_passed_summary")
    if live_failures:
        reasons.append("final_provider_or_runtime_failure")
    if not provider.get("provider_host") or not provider.get("model"):
        reasons.append("missing_provider_identity")
    if not probe or probe.get("ready") is not True or probe.get("status_code") != 200 or probe.get("model_listed") is not True:
        reasons.append("provider_probe_not_ready")
    if contract is None or any(not fingerprint.get(key) for key in FINGERPRINT_KEYS):
        reasons.append("incomplete_comparison_fingerprint")
    if calls is None:
        reasons.append("live_calls_missing")
        calls = []
    if records is None:
        reasons.append("records_missing")
        records = []
    declared_count = payload.get("record_count")
    if not isinstance(declared_count, int) or declared_count < 1:
        reasons.append("invalid_record_count")
        declared_count = 0
    if fingerprint.get("record_count") != declared_count:
        reasons.append("fingerprint_record_count_mismatch")
    mission_ids = _normalise_mission_ids(fingerprint.get("mission_ids"))
    if mission_ids is None or len(mission_ids) != declared_count:
        reasons.append("fingerprint_mission_ids_mismatch")
    call_ids: list[str] = []
    record_ids: list[str] = []
    retry_call_count = 0
    retry_event_count = 0
    for call in calls:
        if not isinstance(call, dict):
            reasons.append("invalid_live_call")
            continue
        mission_id = call.get("mission_id")
        if not isinstance(mission_id, str) or not mission_id:
            reasons.append("live_call_mission_id_missing")
        else:
            call_ids.append(mission_id)
        attempts = call.get("attempts")
        if not isinstance(attempts, int) or attempts < 1:
            reasons.append("invalid_attempts")
        retry_events = call.get("retry_events")
        if not isinstance(retry_events, list):
            reasons.append("missing_retry_events")
            continue
        if retry_events:
            retry_call_count += 1
        retry_event_count += len(retry_events)
        if isinstance(attempts, int) and attempts != len(retry_events) + 1:
            reasons.append("attempt_retry_events_mismatch")
    for record in records:
        if not isinstance(record, dict):
            reasons.append("invalid_record")
            continue
        mission_id = record.get("mission_id")
        if isinstance(mission_id, str) and mission_id:
            record_ids.append(mission_id)
        else:
            reasons.append("record_mission_id_missing")
    if declared_count != len(calls) or declared_count != len(records):
        reasons.append("record_call_count_mismatch")
    if sorted(call_ids) != sorted(record_ids) or (mission_ids and sorted(call_ids) != list(mission_ids)):
        reasons.append("mission_set_mismatch")
    unique_reasons = list(dict.fromkeys(reasons))
    eligible = not unique_reasons
    return {
        "summary": str(path),
        "summary_sha256": _sha256_file(path) if path.is_file() else None,
        "status": status,
        "eligible": eligible,
        "reasons": unique_reasons,
        "provider_blocked": blocked,
        "contract": _contract_json(contract),
        "record_count": declared_count,
        "live_call_count": len(calls),
        "retry_call_count": retry_call_count,
        "retry_event_count": retry_event_count,
        "live_failure_count": len(live_failures),
    }


def audit_summaries(
    summary_paths: Iterable[Path],
    *,
    expected_contract: dict[str, Any] | None = None,
    min_batches: int = 2,
    min_calls: int = 20,
) -> dict[str, Any]:
    """Return a redacted T-06 cohort audit without silently manufacturing a rate."""
    paths = [Path(path).resolve() for path in summary_paths]
    unique_paths = list(dict.fromkeys(paths))
    if len(unique_paths) != len(paths):
        raise ValueError("duplicate summary paths are not allowed")
    if min_batches < 1 or min_calls < 1:
        raise ValueError("min_batches and min_calls must be positive")

    expected_key = _expected_contract(expected_contract or {})
    entries: list[dict[str, Any]] = []
    for path in unique_paths:
        if not path.is_file():
            entries.append({
                "summary": str(path),
                "summary_sha256": None,
                "status": "missing",
                "eligible": False,
                "reasons": ["summary_missing"],
                "provider_blocked": False,
                "contract": None,
                "record_count": 0,
                "live_call_count": 0,
                "retry_call_count": 0,
                "retry_event_count": 0,
                "live_failure_count": 0,
            })
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            entries.append({
                "summary": str(path),
                "summary_sha256": _sha256_file(path),
                "status": "invalid",
                "eligible": False,
                "reasons": ["invalid_json"],
                "provider_blocked": False,
                "contract": None,
                "record_count": 0,
                "live_call_count": 0,
                "retry_call_count": 0,
                "retry_event_count": 0,
                "live_failure_count": 0,
            })
            continue
        if not isinstance(payload, dict):
            entries.append({
                "summary": str(path),
                "summary_sha256": _sha256_file(path),
                "status": "invalid",
                "eligible": False,
                "reasons": ["summary_not_object"],
                "provider_blocked": False,
                "contract": None,
                "record_count": 0,
                "live_call_count": 0,
                "retry_call_count": 0,
                "retry_event_count": 0,
                "live_failure_count": 0,
            })
            continue
        entry = _validate_batch(path, payload)
        if expected_key is not None:
            actual_key = _contract_from_payload(payload)
            if actual_key != expected_key:
                entry["eligible"] = False
                entry["reasons"] = list(dict.fromkeys([*entry["reasons"], "expected_contract_mismatch"]))
        entries.append(entry)

    eligible = [entry for entry in entries if entry["eligible"]]
    contract_keys = {
        tuple(
            [
                entry["contract"][key] if key != "mission_ids" else tuple(entry["contract"][key])
                for key in CONTRACT_KEYS
            ]
        )
        for entry in eligible
    }
    mixed_contract = len(contract_keys) > 1
    total_calls = sum(int(entry["live_call_count"]) for entry in eligible)
    retry_calls = sum(int(entry["retry_call_count"]) for entry in eligible)
    retry_events = sum(int(entry["retry_event_count"]) for entry in eligible)
    meets_minimum = (
        not mixed_contract
        and len(eligible) >= min_batches
        and total_calls >= min_calls
    )
    if meets_minimum:
        status = "observed"
        degrade_rate: float | None = round(retry_calls / total_calls, 6)
        retry_event_rate: float | None = round(retry_events / total_calls, 6)
    elif entries and all(entry.get("provider_blocked") for entry in entries):
        status = "blocked"
        degrade_rate = None
        retry_event_rate = None
    else:
        status = "insufficient"
        degrade_rate = None
        retry_event_rate = None

    reason_counts = Counter(reason for entry in entries for reason in entry["reasons"])
    inferred_contract = None
    if len(contract_keys) == 1:
        inferred_contract = _contract_json(next(iter(contract_keys)))
    return {
        "kind": "t06_standardized_retry_degrade_rate_audit",
        "schema_version": 1,
        "generated_at": _utc_now(),
        "status": status,
        "input_contract": {
            "summary_paths": [str(path) for path in unique_paths],
            "summary_sha256": [entry["summary_sha256"] for entry in entries],
            "expected_contract": _contract_json(expected_key),
            "inferred_contract": inferred_contract,
            "min_batches": min_batches,
            "min_calls": min_calls,
            "reproducible": True,
        },
        "checks": {
            "all_calls_have_retry_events": not any("missing_retry_events" in entry["reasons"] for entry in entries),
            "single_model_provider_contract": not mixed_contract and len(contract_keys) <= 1,
            "provider_blocks_excluded": True,
            "provider_blocks_are_not_code_failures": True,
            "minimum_sample_met": meets_minimum,
        },
        "cohort": {
            "eligible_batch_count": len(eligible),
            "eligible_live_call_count": total_calls,
            "calls_with_retry_events": retry_calls,
            "retry_event_count": retry_events,
            "excluded_batch_count": len(entries) - len(eligible),
            "excluded_provider_blocked_batch_count": sum(1 for entry in entries if entry.get("provider_blocked")),
        },
        "rates": {
            "definition": "degrade_rate = calls_with_retry_events / eligible_live_calls; final provider blocks are excluded",
            "degrade_rate": degrade_rate,
            "retry_event_rate": retry_event_rate,
            "final_provider_failure_rate": None,
        },
        "reason_counts": dict(sorted(reason_counts.items())),
        "batches": entries,
        "limitations": [
            "数值只描述通过同一模型/Provider、mission 集合和完整契约指纹的显式输入 cohort，不代表代码失败率。",
            "缺 retry_events、Provider 阻断、非 passed 批次和契约混杂输入均不进入分母。",
            "insufficient/blocked 状态的 rate 保持 null，不用失败计数或缺失字段回填。",
            "本报告不读取或输出正文、Prompt、密钥，也不替代人工质量真值。",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit standardized T-06 retry/degrade observations.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--summary", action="append", type=Path, help="explicit summary file or run directory; repeatable")
    source.add_argument("--manifest", type=Path, help="JSON manifest with summaries/expected_contract/thresholds")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--min-batches", type=int, default=2)
    parser.add_argument("--min-calls", type=int, default=20)
    args = parser.parse_args(argv)

    if args.manifest:
        paths, expected, manifest_min_batches, manifest_min_calls = _load_manifest(args.manifest.resolve())
        min_batches = manifest_min_batches
        min_calls = manifest_min_calls
    else:
        paths = [_resolve_summary_path(path) for path in args.summary]
        expected = {}
        min_batches = args.min_batches
        min_calls = args.min_calls
    payload = audit_summaries(
        paths,
        expected_contract=expected,
        min_batches=min_batches,
        min_calls=min_calls,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": payload["status"],
        "eligible_batch_count": payload["cohort"]["eligible_batch_count"],
        "eligible_live_call_count": payload["cohort"]["eligible_live_call_count"],
        "degrade_rate": payload["rates"]["degrade_rate"],
        "reason_counts": payload["reason_counts"],
    }, ensure_ascii=False))
    return 0 if payload["status"] == "observed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
