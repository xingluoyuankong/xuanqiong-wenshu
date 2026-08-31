"""Read-only structural gate for the corrected T-16 acceptance model.

This audit never calls a provider and never reads prose.  It only validates
that one fixed generation input manifest was scored by two different
production scorers and then evaluated by the same independent frozen
evaluator.  A successful result means the evidence is structurally eligible
for T-16 acceptance review; it does not prove a quality gain.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
REQUIRED_SUMMARY_FINGERPRINT = (
    "schema_version",
    "mission_contract_sha256",
    "generation_request_contract_sha256",
    "scorer_sha256",
)


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _record_ids(records: Any) -> list[str]:
    if not isinstance(records, list):
        return []
    return [_text(item.get("mission_id")) for item in records if isinstance(item, dict)]


def _input_records(payload: dict[str, Any]) -> list[dict[str, str]]:
    records = payload.get("records")
    if not isinstance(records, list):
        return []
    result: list[dict[str, str]] = []
    for item in records:
        if not isinstance(item, dict):
            continue
        result.append({
            "mission_id": _text(item.get("mission_id")),
            "input_content_sha256": _text(item.get("input_content_sha256")),
        })
    return result


def _evaluator_records(payload: dict[str, Any]) -> list[dict[str, str]]:
    records = payload.get("records")
    if not isinstance(records, list):
        return []
    result: list[dict[str, str]] = []
    for item in records:
        if not isinstance(item, dict):
            continue
        result.append({
            "mission_id": _text(item.get("mission_id")),
            "input_content_sha256": _text(item.get("input_content_sha256")),
        })
    return result


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _summary_metadata(payload: dict[str, Any] | None) -> dict[str, Any]:
    fingerprint = payload.get("comparison_fingerprint") if isinstance(payload, dict) else {}
    if not isinstance(fingerprint, dict):
        fingerprint = {}
    provider = payload.get("provider") if isinstance(payload, dict) else {}
    if not isinstance(provider, dict):
        provider = {}
    records = payload.get("records") if isinstance(payload, dict) else []
    if not isinstance(records, list):
        records = []
    return {
        "status": _text(payload.get("status")) if isinstance(payload, dict) else "",
        "record_count": payload.get("record_count") if isinstance(payload, dict) else 0,
        "schema_version": fingerprint.get("schema_version"),
        "mission_ids": [str(item) for item in (fingerprint.get("mission_ids") or [])]
        if isinstance(fingerprint.get("mission_ids"), list)
        else [],
        "record_ids": _record_ids(records),
        "mission_contract_sha256": _text(fingerprint.get("mission_contract_sha256")),
        "generation_request_contract_sha256": _text(fingerprint.get("generation_request_contract_sha256")),
        "scorer_sha256": _text(fingerprint.get("scorer_sha256")),
        "input_manifest_sha256": _text(payload.get("input_manifest_sha256")) if isinstance(payload, dict) else "",
        "provider_host": _text(provider.get("provider_host")),
        "model": _text(provider.get("model")),
    }


def _check(name: str, passed: bool, reason: str) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "reason": reason}


def audit(
    input_manifest_path: Path,
    before_summary_path: Path,
    after_summary_path: Path,
    before_evaluator_path: Path,
    after_evaluator_path: Path,
) -> dict[str, Any]:
    """Validate corrected T-16 evidence without scoring or contacting a provider."""
    paths = {
        "input_manifest": input_manifest_path.resolve(),
        "before_summary": before_summary_path.resolve(),
        "after_summary": after_summary_path.resolve(),
        "before_evaluator": before_evaluator_path.resolve(),
        "after_evaluator": after_evaluator_path.resolve(),
    }
    manifest = _load_json(paths["input_manifest"])
    before_summary = _load_json(paths["before_summary"])
    after_summary = _load_json(paths["after_summary"])
    before_evaluator = _load_json(paths["before_evaluator"])
    after_evaluator = _load_json(paths["after_evaluator"])

    blockers: list[str] = []
    checks: list[dict[str, Any]] = []

    manifest_valid = (
        isinstance(manifest, dict)
        and manifest.get("kind") == "t16_fixed_generation_input_manifest"
        and manifest.get("schema_version") == SCHEMA_VERSION
        and bool(_text(manifest.get("generation_batch_id")))
        and bool(_text(manifest.get("mission_contract_sha256")))
        and bool(_text(manifest.get("generation_request_contract_sha256")))
        and isinstance(manifest.get("provider"), dict)
        and bool(_text((manifest.get("provider") or {}).get("provider_host")))
        and bool(_text((manifest.get("provider") or {}).get("model")))
        and bool(_input_records(manifest))
        and all(item["mission_id"] and item["input_content_sha256"] for item in _input_records(manifest))
    )
    checks.append(_check("fixed_input_manifest", manifest_valid, "固定生成输入 manifest 必须完整且为受支持 schema"))
    if not manifest_valid:
        blockers.append("invalid_fixed_input_manifest")

    manifest_hash = ""
    if paths["input_manifest"].is_file():
        try:
            manifest_hash = _sha256_file(paths["input_manifest"])
        except OSError:
            manifest_hash = ""
    input_records = _input_records(manifest or {})
    input_ids = [item["mission_id"] for item in input_records]
    input_hashes = [item["input_content_sha256"] for item in input_records]
    input_provider = (manifest or {}).get("provider") if isinstance(manifest, dict) else {}
    if not isinstance(input_provider, dict):
        input_provider = {}

    before = _summary_metadata(before_summary)
    after = _summary_metadata(after_summary)
    summaries_valid = all(
        payload is not None
        and metadata["status"] == "passed"
        and metadata["record_count"] == len(input_ids)
        and metadata["record_ids"] == input_ids
        and metadata["mission_ids"] == input_ids
        and metadata["input_manifest_sha256"] == manifest_hash
        and metadata["schema_version"]
        and all(metadata.get(key) for key in REQUIRED_SUMMARY_FINGERPRINT if key != "schema_version")
        for payload, metadata in ((before_summary, before), (after_summary, after))
    )
    checks.append(_check("production_summaries", summaries_valid, "改前/改后 production summary 必须是同一固定输入的完整成功批次"))
    if not summaries_valid:
        blockers.append("invalid_production_summaries")

    fixed_request = (
        before["mission_contract_sha256"] == after["mission_contract_sha256"] == _text((manifest or {}).get("mission_contract_sha256"))
        and before["generation_request_contract_sha256"]
        == after["generation_request_contract_sha256"]
        == _text((manifest or {}).get("generation_request_contract_sha256"))
        and before["provider_host"] == after["provider_host"] == _text(input_provider.get("provider_host"))
        and before["model"] == after["model"] == _text(input_provider.get("model"))
    )
    checks.append(_check("fixed_generation_request", fixed_request, "任务、生成请求契约、Provider 与模型必须完全一致"))
    if not fixed_request:
        blockers.append("fixed_generation_request_mismatch")

    scorer_changed = bool(before["scorer_sha256"] and after["scorer_sha256"] and before["scorer_sha256"] != after["scorer_sha256"])
    checks.append(_check("production_scorer_changed", scorer_changed, "production scorer 改前/改后 SHA 必须不同"))
    if not scorer_changed:
        blockers.append("production_scorer_not_changed")

    evaluator_meta: list[dict[str, Any]] = []
    for payload in (before_evaluator, after_evaluator):
        evaluator = payload.get("evaluator") if isinstance(payload, dict) else {}
        if not isinstance(evaluator, dict):
            evaluator = {}
        evaluator_meta.append({
            "kind": payload.get("kind") if isinstance(payload, dict) else "",
            "schema_version": payload.get("schema_version") if isinstance(payload, dict) else None,
            "status": _text(payload.get("status")) if isinstance(payload, dict) else "",
            "frozen": evaluator.get("frozen") is True,
            "evaluator_sha256": _text(evaluator.get("evaluator_sha256")),
            "contract_sha256": _text(evaluator.get("contract_sha256")),
            "input_manifest_sha256": _text(payload.get("input_manifest_sha256")) if isinstance(payload, dict) else "",
            "production_scorer_sha256": _text(payload.get("production_scorer_sha256")) if isinstance(payload, dict) else "",
            "record_count": payload.get("record_count") if isinstance(payload, dict) else 0,
            "records": _evaluator_records(payload or {}),
            "aggregate_score": (payload.get("aggregate") or {}).get("average_score")
            if isinstance(payload, dict) and isinstance(payload.get("aggregate"), dict)
            else None,
        })
    evaluator_ready = all(
        payload is not None
        and item["kind"] == "t16_frozen_evaluator_report"
        and item["schema_version"] == SCHEMA_VERSION
        and item["status"] == "passed"
        and item["frozen"]
        and item["evaluator_sha256"]
        and item["contract_sha256"]
        and item["input_manifest_sha256"] == manifest_hash
        and item["record_count"] == len(input_ids)
        and item["records"] == input_records
        and _is_number(item["aggregate_score"])
        for payload, item in ((before_evaluator, evaluator_meta[0]), (after_evaluator, evaluator_meta[1]))
    )
    checks.append(_check("frozen_evaluator_reports", evaluator_ready, "两份 evaluator 报告必须完整覆盖同一固定输入"))
    if not evaluator_ready:
        blockers.append("invalid_frozen_evaluator_reports")

    same_evaluator = (
        evaluator_meta[0]["evaluator_sha256"] == evaluator_meta[1]["evaluator_sha256"]
        and evaluator_meta[0]["contract_sha256"] == evaluator_meta[1]["contract_sha256"]
        and evaluator_meta[0]["evaluator_sha256"] not in {"", before["scorer_sha256"], after["scorer_sha256"]}
    )
    checks.append(_check("independent_frozen_evaluator", same_evaluator, "改前/改后必须由同一且独立于 production scorer 的冻结 evaluator 评分"))
    if not same_evaluator:
        blockers.append("evaluator_not_same_and_independent")

    evaluator_scorer_binding = (
        evaluator_meta[0]["production_scorer_sha256"] == before["scorer_sha256"]
        and evaluator_meta[1]["production_scorer_sha256"] == after["scorer_sha256"]
    )
    checks.append(_check("evaluator_scorer_binding", evaluator_scorer_binding, "冻结 evaluator 报告必须明确绑定对应 production scorer 版本"))
    if not evaluator_scorer_binding:
        blockers.append("evaluator_scorer_binding_mismatch")

    evidence_ready = not blockers
    return {
        "kind": "t16_corrected_acceptance_audit",
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "eligible_for_t16_acceptance_review" if evidence_ready else "blocked",
        "acceptance_ready": evidence_ready,
        "quality_gain_proven": False,
        "provider_calls": False,
        "artifacts": {key: str(value) for key, value in paths.items()},
        "checks": checks,
        "blockers": sorted(set(blockers)),
        "evidence": {
            "input_manifest_sha256": manifest_hash,
            "mission_ids": input_ids,
            "record_count": len(input_ids),
            "before_scorer_sha256": before["scorer_sha256"],
            "after_scorer_sha256": after["scorer_sha256"],
            "evaluator_sha256": evaluator_meta[0]["evaluator_sha256"],
            "evaluator_contract_sha256": evaluator_meta[0]["contract_sha256"],
            "evaluator_before_average_score": None,
            "evaluator_after_average_score": None,
            "evaluator_average_score_delta": None,
        },
        "limitations": [
            "本报告只证明 corrected T-16 证据接口结构就绪，不证明质量提升。",
            "本审计不读取正文、不计算或输出 before/after 收益，不调用 Provider。",
            "仍须由项目验收规则结合独立 evaluator 的真实结果、人工真值和预注册阈值判定 T-16。",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit corrected T-16 evidence without provider calls.")
    parser.add_argument("--input-manifest", type=Path, required=True)
    parser.add_argument("--before-summary", type=Path, required=True)
    parser.add_argument("--after-summary", type=Path, required=True)
    parser.add_argument("--before-evaluator", type=Path, required=True)
    parser.add_argument("--after-evaluator", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    payload = audit(
        args.input_manifest,
        args.before_summary,
        args.after_summary,
        args.before_evaluator,
        args.after_evaluator,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("status", "acceptance_ready", "quality_gain_proven", "provider_calls", "blockers")}, ensure_ascii=False))
    return 0 if payload["acceptance_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
