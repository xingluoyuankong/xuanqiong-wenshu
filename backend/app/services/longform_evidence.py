"""Redacted, deterministic evidence helpers for long-form generation smoke runs."""
from __future__ import annotations

import hashlib
import re
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1
_FORBIDDEN_KEYS = {
    "content", "content_delta", "prose", "text", "正文", "assembled_text",
    "provider_response", "response", "prompt", "chapter_mission",
    "book_context", "volume_context", "chapter_context",
}
_TERMINAL_EVENTS = {"task_completed", "task_failed", "task_cancelled", "task_stale"}


def _sha256_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_error_code(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text[:96]


def _safe_segment_fingerprint(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    # Runtime writes SHA-1 today; accept SHA-256 too for forward compatibility.
    if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", text):
        return text
    # A corrupted checkpoint must not turn an arbitrary field into report text.
    return _sha256_text(text)


def _walk_forbidden(value: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, nested in value.items():
            key_text = str(key)
            if key_text in _FORBIDDEN_KEYS and not path.endswith(".event_type_counts"):
                found.append(f"{path}.{key_text}")
            found.extend(_walk_forbidden(nested, f"{path}.{key_text}"))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, nested in enumerate(value):
            found.extend(_walk_forbidden(nested, f"{path}[{index}]"))
    return found


def build_longform_failure_evidence(
    *,
    source_db: str | Path,
    task: Mapping[str, Any] | None,
    runtime: Mapping[str, Any] | None,
    events: Sequence[Mapping[str, Any]] = (),
    content: Any = None,
    failure: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Project runtime state into a report that never contains prose or provider payloads."""
    task = task if isinstance(task, Mapping) else {}
    runtime = runtime if isinstance(runtime, Mapping) else {}
    failure = failure if isinstance(failure, Mapping) else {}
    event_rows = [item for item in events if isinstance(item, Mapping)]
    plan = runtime.get("plan") if isinstance(runtime.get("plan"), Mapping) else {}
    checkpoint = runtime.get("checkpoint") if isinstance(runtime.get("checkpoint"), Mapping) else {}
    segment_rows = checkpoint.get("completed_segments")
    segment_rows = segment_rows if isinstance(segment_rows, list) else []

    safe_segments = []
    for item in segment_rows:
        if not isinstance(item, Mapping):
            continue
        safe_segments.append({
            "index": _safe_int(item.get("index")),
            "word_count": _safe_int(item.get("word_count")),
            "char_count": _safe_int(item.get("char_count")),
            "target_words": _safe_int(item.get("target_words")),
            "token_usage": _safe_int(item.get("token_usage")),
            "fingerprint": _safe_segment_fingerprint(item.get("fingerprint")),
        })

    content_text = str(content) if content is not None else ""
    assembled_text = checkpoint.get("assembled_text")
    if not content_text and assembled_text is not None:
        content_text = str(assembled_text)

    event_counts = Counter(str(item.get("event_type") or "unknown") for item in event_rows)
    terminal_events = [item for item in event_rows if str(item.get("event_type") or "") in _TERMINAL_EVENTS]
    error_code = _safe_error_code(failure.get("error_code") or task.get("error_code"))
    error_class = _safe_error_code(failure.get("error_class"))
    normalized_reason = _safe_error_code(failure.get("normalized_reason"))

    report: dict[str, Any] = {
        "kind": "t25_real_longform_failure_audit",
        "schema_version": SCHEMA_VERSION,
        "source_db": Path(str(source_db)).name,
        "redaction": {
            "content_emitted": False,
            "assembled_text_emitted": False,
            "content_delta_emitted": False,
            "provider_response_emitted": False,
            "content_sha256": _sha256_text(content_text),
            "content_chars": len(content_text),
        },
        "task": {
            "task_id": _safe_error_code(task.get("task_id")),
            "status": _safe_error_code(task.get("status")),
            "stage": _safe_error_code(task.get("stage")),
            "progress": _safe_float(task.get("progress")),
            "attempt": _safe_int(task.get("attempt"), 1),
            "retry_count": _safe_int(task.get("retry_count")),
            "elapsed_ms": _safe_int(task.get("elapsed_ms")),
        },
        "plan": {
            "target_word_count": _safe_int(plan.get("target_word_count")),
            "min_word_count": _safe_int(plan.get("min_word_count")),
            "segment_word_limit": _safe_int(plan.get("segment_word_limit")),
            "segment_count": _safe_int(len(plan.get("segments") or [])) if isinstance(plan.get("segments"), list) else _safe_int(runtime.get("segment_count")),
            "plan_key_sha256": _sha256_text(plan.get("plan_key")),
        },
        "checkpoint": {
            "present": bool(checkpoint),
            "next_segment_index": _safe_int(checkpoint.get("next_segment_index")),
            "completed_segment_count": len(safe_segments),
            "used_words": _safe_int(checkpoint.get("used_words")),
            "total_tokens": _safe_int(checkpoint.get("total_tokens")),
            "assembled_text_sha256": _sha256_text(assembled_text),
            "assembled_text_chars": len(str(assembled_text or "")),
            "segments": safe_segments,
        },
        "failure": {
            "error_code": error_code,
            "error_class": error_class,
            "retryable": failure.get("retryable") if isinstance(failure.get("retryable"), bool) else None,
            "normalized_reason": normalized_reason,
        },
        "events": {
            "event_count": len(event_rows),
            "content_delta_count": event_counts.get("content_delta", 0),
            "event_type_counts": dict(sorted(event_counts.items())),
            "terminal_event_present": bool(terminal_events),
            "failure_event_present": any(str(item.get("event_type") or "") == "task_failed" for item in event_rows),
        },
        "validation": {},
        "limitations": [
            "Failure evidence is a runtime/contract diagnostic, not a literary-quality judgment.",
            "Hashes and counts cannot replace human labels, Provider provenance, or T-16 before/after comparability.",
        ],
    }
    forbidden = _walk_forbidden(report)
    errors = validate_longform_failure_evidence(report)
    report["validation"] = {"valid": not errors, "forbidden_key_paths": forbidden, "errors": errors}
    return report


def validate_longform_failure_evidence(payload: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, Mapping):
        return ["root must be an object"]
    if payload.get("kind") != "t25_real_longform_failure_audit":
        errors.append("invalid kind")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append("unsupported schema_version")
    forbidden = _walk_forbidden(payload)
    if forbidden:
        errors.append("forbidden prose-bearing keys present")
    redaction = payload.get("redaction") if isinstance(payload.get("redaction"), Mapping) else {}
    for key in ("content_emitted", "assembled_text_emitted", "content_delta_emitted", "provider_response_emitted"):
        if redaction.get(key) is not False:
            errors.append(f"redaction.{key} must be false")
    checkpoint = payload.get("checkpoint") if isinstance(payload.get("checkpoint"), Mapping) else {}
    plan = payload.get("plan") if isinstance(payload.get("plan"), Mapping) else {}
    segments = checkpoint.get("segments") if isinstance(checkpoint.get("segments"), list) else []
    if checkpoint.get("completed_segment_count") != len(segments):
        errors.append("completed_segment_count does not match segments")
    if _safe_int(checkpoint.get("next_segment_index")) < _safe_int(checkpoint.get("completed_segment_count")):
        errors.append("next_segment_index precedes completed segments")
    if _safe_int(plan.get("segment_count")) and _safe_int(checkpoint.get("next_segment_index")) > _safe_int(plan.get("segment_count")):
        errors.append("next_segment_index exceeds segment_count")
    events = payload.get("events") if isinstance(payload.get("events"), Mapping) else {}
    event_counts = events.get("event_type_counts") if isinstance(events.get("event_type_counts"), Mapping) else {}
    if sum(_safe_int(value) for value in event_counts.values()) != _safe_int(events.get("event_count")):
        errors.append("event_type_counts does not match event_count")
    return errors
