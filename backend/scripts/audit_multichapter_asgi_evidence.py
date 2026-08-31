"""Redacted consistency audit for real multi-chapter ASGI evidence."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_FORBIDDEN_KEYS = {
    "content", "prose", "正文", "text",
    "content_delta", "assembled_text", "provider_response",
    "prompt", "chapter_mission", "book_context", "volume_context", "chapter_context",
}

_TERMINAL_SUCCESS = {"successful", "waiting_for_confirm"}
_TERMINAL_REJECTED = {"failed", "evaluation_failed", "cancelled"}

def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("evidence root must be an object")
    return value


def _walk_forbidden(value: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key) in _FORBIDDEN_KEYS:
                found.append(f"{path}.{key}")
            found.extend(_walk_forbidden(nested, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            found.extend(_walk_forbidden(nested, f"{path}[{index}]"))
    return found


def audit(path: Path) -> dict[str, Any]:
    payload = _load(path)
    chapters = payload.get("chapters") if isinstance(payload.get("chapters"), list) else []
    attempts = payload.get("attempt_results") if isinstance(payload.get("attempt_results"), list) else chapters
    requested = int(payload.get("requested_chapter_count") or 0)
    attempted = int(payload.get("attempted_count") or 0)
    successful = int(payload.get("successful_count") or 0)
    rejected = int(payload.get("rejected_count") or 0)
    status_counts = Counter(str(item.get("status") or "unknown") for item in attempts if isinstance(item, dict))
    calculated_success = sum(status in _TERMINAL_SUCCESS for status in status_counts.elements())
    calculated_rejected = sum(status in _TERMINAL_REJECTED for status in status_counts.elements())
    rate = round(successful / attempted, 4) if attempted else 0.0
    report_rate = float(payload.get("pass_rate") or 0.0)
    distribution_ns = {
        str(key): value.get("n")
        for key, value in (payload.get("distributions") or {}).items()
        if isinstance(value, dict)
    }
    errors: list[str] = []
    if requested <= 0:
        errors.append("requested_chapter_count must be positive")
    if attempted != len(attempts):
        errors.append("attempted_count does not match attempt_results")
    if len(chapters) != int(payload.get("chapter_count") or 0):
        errors.append("chapter_count does not match chapters")
    if successful + rejected != attempted:
        errors.append("successful_count + rejected_count does not equal attempted_count")
    if calculated_success != successful:
        errors.append("successful_count does not match terminal attempt statuses")
    if calculated_rejected != rejected:
        errors.append("rejected_count does not match terminal attempt statuses")
    if abs(rate - report_rate) > 0.0001:
        errors.append("pass_rate does not match counts")
    if any(value not in (None, successful) for value in distribution_ns.values()):
        errors.append("distribution n must equal successful_count or be null")
    semantics = payload.get("word_count_semantics")
    if semantics is not None and not isinstance(semantics, dict):
        errors.append("word_count_semantics must be an object when present")
    for item in attempts:
        if not isinstance(item, dict):
            continue
        if "content_char_count" in item and item.get("word_count_unit") != "content_char_count_legacy_api_field":
            errors.append("attempt word_count_unit does not declare content character semantics")
            break
    for item in chapters:
        if not isinstance(item, dict):
            continue
        if "quality_metric_word_count" in item and item.get("word_count_unit") != "quality_metric_word_count":
            errors.append("chapter word_count_unit does not declare quality metric semantics")
            break
    verified_exemption_attempts = 0
    for item in attempts:
        if not isinstance(item, dict):
            continue
        exemptions = item.get("exemptions")
        applied = item.get("critique_exemption_applied")
        if isinstance(exemptions, list) and isinstance(applied, list) and exemptions != applied:
            errors.append("critique_exemption_applied does not match exemptions")
        if not isinstance(exemptions, list) or not exemptions:
            continue
        score = item.get("self_critique_final_score")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or score < 75:
            errors.append("non-empty exemptions require self_critique_final_score >= 75")
        else:
            verified_exemption_attempts += 1
    forbidden_paths = _walk_forbidden(payload)
    if forbidden_paths:
        errors.append("prose-bearing keys present")
    return {
        "kind": "real_multichapter_asgi_evidence_consistency_audit",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_file": str(path.resolve()),
        "requested_chapter_count": requested,
        "attempted_count": attempted,
        "successful_count": successful,
        "rejected_count": rejected,
        "pass_rate": rate,
        "status_counts": dict(sorted(status_counts.items())),
        "distribution_sample_sizes": distribution_ns,
        "verified_exemption_attempts": verified_exemption_attempts,
        "word_count_semantics": semantics or {},
        "forbidden_key_paths": forbidden_paths,
        "valid": not errors,
        "errors": errors,
        "limitations": [
            "只验证脱敏证据内部一致性，不判断正文文学质量。",
            "放行率不等于人工质量接受率，也不替代 T-16 前后对照或 T-18 真值。",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.evidence)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("valid", "attempted_count", "successful_count", "rejected_count", "pass_rate", "errors")}, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
