"""Strict, redacted comparability audit for T-16 benchmark evidence."""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REQUIRED_FINGERPRINT_KEYS = (
    "schema_version",
    "record_count",
    "mission_ids",
    "mission_contract_sha256",
    "generation_request_contract_sha256",
    "scorer_sha256",
    "comparison_contract_sha256",
)


def _parse_timestamp(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except ValueError:
        return ""


def _load_summary(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def _fingerprint_record(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    fingerprint = payload.get("comparison_fingerprint")
    if not isinstance(fingerprint, dict):
        fingerprint = {}
    provider = payload.get("provider") if isinstance(payload.get("provider"), dict) else {}
    mission_ids = fingerprint.get("mission_ids")
    if not isinstance(mission_ids, list):
        mission_ids = []
    missing = [key for key in REQUIRED_FINGERPRINT_KEYS if not fingerprint.get(key)]
    # Prefer an explicit generation start timestamp.  For legacy summaries
    # that predate this field, use the live status timestamp and finally the
    # summary generation timestamp; never fall back when the field is present
    # but empty/equal, because that is an ambiguous provenance signal.
    if "generation_started_at" in payload:
        generation_started_at = _parse_timestamp(payload.get("generation_started_at"))
    else:
        generation_started_at = ""
        status_path = path.parent / "live-status.json"
        status_payload = _load_summary(status_path) if status_path.is_file() else None
        if isinstance(status_payload, dict):
            generation_started_at = _parse_timestamp(status_payload.get("generation_started_at"))
        if not generation_started_at:
            generation_started_at = _parse_timestamp(payload.get("generated_at"))
    # Legacy summaries predate generation_started_at. Their generated_at is
    # the only available temporal evidence, so keep compatibility without
    # falling back to filesystem ordering.
    if not generation_started_at:
        generation_started_at = _parse_timestamp(payload.get("generated_at"))
    return {
        "summary_path": str(path.resolve()),
        "generated_at": _parse_timestamp(payload.get("generated_at")),
        "generation_started_at": generation_started_at,
        "status": str(payload.get("status") or "unknown"),
        "record_count": int(payload.get("record_count") or 0),
        "mission_ids": [str(item) for item in mission_ids],
        "schema_version": fingerprint.get("schema_version"),
        "mission_contract_sha256": fingerprint.get("mission_contract_sha256"),
        "generation_request_contract_sha256": fingerprint.get("generation_request_contract_sha256"),
        "scorer_sha256": fingerprint.get("scorer_sha256"),
        "comparison_contract_sha256": fingerprint.get("comparison_contract_sha256"),
        "provider_host": str(provider.get("provider_host") or ""),
        "model": str(provider.get("model") or ""),
        "missing_fingerprint_keys": missing,
    }


def _strict_group_key(item: dict[str, Any]) -> tuple[Any, ...] | None:
    if item["missing_fingerprint_keys"]:
        return None
    return (
        item["schema_version"],
        item["record_count"],
        tuple(item["mission_ids"]),
        item["mission_contract_sha256"],
        item["generation_request_contract_sha256"],
        item["provider_host"],
        item["model"],
    )


def _order_temporal_pair(
    left: dict[str, Any], right: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Return (earlier, later) only when the report timestamps prove order.

    File/directory names are not provenance.  Falling back to path ordering can
    label an after batch as the before batch, or manufacture a before/after
    relation for two reports with no trustworthy timestamp.
    """
    left_at = str(left.get("generation_started_at") or "")
    right_at = str(right.get("generation_started_at") or "")
    if not left_at or not right_at or left_at == right_at:
        return None
    return (left, right) if left_at < right_at else (right, left)


def audit(root: Path) -> dict[str, Any]:
    summaries = sorted(root.rglob("rescore-summary.json"))
    items: list[dict[str, Any]] = []
    reason_counts: Counter[str] = Counter()
    for path in summaries:
        payload = _load_summary(path)
        if payload is None:
            reason_counts["invalid_json"] += 1
            continue
        item = _fingerprint_record(path, payload)
        if item["missing_fingerprint_keys"]:
            reason_counts["missing_or_incomplete_fingerprint"] += 1
        elif item["generation_request_contract_sha256"] is None:
            reason_counts["missing_generation_request_contract"] += 1
        else:
            reason_counts["complete_fingerprint"] += 1
        items.append(item)

    groups: defaultdict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        if item["status"] != "passed" or not item["provider_host"] or not item["model"]:
            continue
        key = _strict_group_key(item)
        if key is not None:
            groups[key].append(item)

    candidate_pairs: list[dict[str, Any]] = []
    comparable_pairs: list[dict[str, Any]] = []
    ambiguous_time_pairs: list[dict[str, Any]] = []
    same_contract_groups: list[dict[str, Any]] = []
    for key, members in groups.items():
        scorer_hashes = sorted({str(item["scorer_sha256"]) for item in members})
        group = {
            "record_count": key[1],
            "mission_ids": list(key[2]),
            "mission_contract_sha256": key[3],
            "generation_request_contract_sha256": key[4],
            "provider_host": key[5],
            "model": key[6],
            "member_count": len(members),
            "scorer_sha256s": scorer_hashes,
            "summary_paths": [item["summary_path"] for item in members],
        }
        same_contract_groups.append(group)
        if len(members) < 2:
            continue
        for index, left in enumerate(members):
            for right in members[index + 1:]:
                ordered = _order_temporal_pair(left, right)
                if ordered is None:
                    ambiguous_time_pairs.append({
                        "summary_paths": sorted((left["summary_path"], right["summary_path"])),
                        "generation_started_at": [left["generation_started_at"], right["generation_started_at"]],
                        "record_count": key[1],
                        "mission_ids": list(key[2]),
                        "provider_host": key[5],
                        "model": key[6],
                        "reason": "missing_or_equal_generated_at",
                    })
                    continue
                before, after = ordered
                if (
                    before["scorer_sha256"] == after["scorer_sha256"]
                    and before["comparison_contract_sha256"] == after["comparison_contract_sha256"]
                ):
                    comparable_pairs.append({
                        "before_or_earlier": before["summary_path"],
                        "after_or_later": after["summary_path"],
                        "generated_at": [before["generated_at"], after["generated_at"]],
                        "generation_started_at": [before["generation_started_at"], after["generation_started_at"]],
                        "scorer_sha256": before["scorer_sha256"],
                        "record_count": key[1],
                        "mission_ids": list(key[2]),
                        "mission_contract_sha256": key[3],
                        "generation_request_contract_sha256": key[4],
                        "provider_host": key[5],
                        "model": key[6],
                    })
                    continue
                candidate_pairs.append({
                    "before_or_earlier": before["summary_path"],
                    "after_or_later": after["summary_path"],
                    "before_generated_at": before["generated_at"],
                    "after_generated_at": after["generated_at"],
                    "before_generation_started_at": before["generation_started_at"],
                    "after_generation_started_at": after["generation_started_at"],
                    "scorer_sha256_before_or_earlier": before["scorer_sha256"],
                    "scorer_sha256_after_or_later": after["scorer_sha256"],
                    "record_count": key[1],
                    "mission_ids": list(key[2]),
                    "mission_contract_sha256": key[3],
                    "generation_request_contract_sha256": key[4],
                    "provider_host": key[5],
                    "model": key[6],
                })

    return {
        "kind": "strict_t16_benchmark_comparability_audit",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": str(root.resolve()),
        "summary_file_count": len(summaries),
        "audited_summary_count": len(items),
        "complete_fingerprint_count": sum(1 for item in items if not item["missing_fingerprint_keys"] and item["generation_request_contract_sha256"] is not None),
        "same_contract_group_count": len(same_contract_groups),
        "candidate_pair_count": len(candidate_pairs),
        "comparable_pair_count": len(comparable_pairs),
        "non_comparable_candidate_pair_count": len(candidate_pairs),
        "ambiguous_time_pair_count": len(ambiguous_time_pairs),
        "candidate_pairs": candidate_pairs,
        "comparable_pairs": comparable_pairs,
        "ambiguous_time_pairs": ambiguous_time_pairs,
        "same_contract_groups": same_contract_groups,
        "reason_counts": dict(sorted(reason_counts.items())),
        "limitations": [
            "该审计只证明请求/任务/评分器指纹的可比性，不证明人工质量提升。",
            "candidate_pair_count 只是时间顺序且评分器不同的候选数；必须同时检查 comparable_pair_count。",
            "缺失或相同 generation_started_at 的同条件报告只记录为 ambiguous_time_pairs，不得按重评分时间或文件路径推断 before/after。",
            "comparable_pair_count=0 时，不能用相似任务、评分器重算或不同 prompt 批次替代 T-16 改前生成批次。",
            "报告不读取或输出正文内容。",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = audit(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("summary_file_count", "complete_fingerprint_count", "same_contract_group_count", "candidate_pair_count", "comparable_pair_count", "non_comparable_candidate_pair_count", "reason_counts")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
