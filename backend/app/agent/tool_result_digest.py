"""Bounded, redacted tool-result context for Planner/reply synthesis.

Durable Step output remains the audit source of truth.  This module creates a
small, deterministic digest for the next planning/reply phase so a model can
reason about actual results without receiving raw provider payloads, long prose,
prompts, secrets, or internal fields.
"""
from __future__ import annotations

import json
from typing import Any

_FORBIDDEN = {
    "thought",
    "reasoning",
    "chain_of_thought",
    "private_reasoning",
    "system_prompt",
    "provider_secret",
    "api_key",
    "authorization",
    "token",
    "password",
    "secret",
}
_PROSE_KEYS = {
    "content",
    "chapter_content",
    "full_text",
    "raw_text",
    "prompt",
    "system_message",
    "user_message",
    "response",
    "raw_response",
}
_MAX_DEPTH = 5
_MAX_ITEMS = 12
_MAX_KEYS = 24
_MAX_STRING = 360
_MAX_PER_TOOL = 1800
_MAX_TOTAL = 6000


def _key(value: Any) -> str:
    return str(value or "").strip().lower()


def _digest(value: Any, *, depth: int = 0) -> Any:
    if depth >= _MAX_DEPTH:
        return "[truncated-depth]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        compact = " ".join(value.replace("\x00", " ").split())
        return compact[:_MAX_STRING] + ("…" if len(compact) > _MAX_STRING else "")
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for raw_key, raw_value in list(value.items())[:_MAX_KEYS]:
            name = str(raw_key)
            normalized = _key(name)
            if normalized in _FORBIDDEN:
                continue
            if normalized in _PROSE_KEYS:
                result[name] = "[omitted-prose]"
                continue
            result[name] = _digest(raw_value, depth=depth + 1)
        return result
    if isinstance(value, (list, tuple, set)):
        rows = list(value)
        return [_digest(item, depth=depth + 1) for item in rows[:_MAX_ITEMS]]
    return str(value)[:_MAX_STRING]


def digest_tool_result(item: dict[str, Any]) -> dict[str, Any]:
    """Produce a stable safe digest for one persisted tool result."""
    tool_name = str(item.get("tool_name") or "unknown")[:120]
    raw_result = item.get("result") if isinstance(item.get("result"), dict) else {}
    summary = _digest(raw_result)
    if not isinstance(summary, dict):
        summary = {"value": summary}
    encoded = json.dumps(summary, ensure_ascii=False, separators=(",", ":"))
    if len(encoded) > _MAX_PER_TOOL:
        summary = {"result_keys": sorted(str(key) for key in raw_result.keys())[:_MAX_KEYS], "note": "[digest-truncated]"}
    return {
        "tool_name": tool_name,
        "result_keys": sorted(str(key) for key in raw_result.keys())[:_MAX_KEYS],
        "summary": summary,
    }


def build_tool_result_digests(results: list[dict[str, Any]] | Any) -> list[dict[str, Any]]:
    """Return a bounded ordered digest list with no raw provider payload escape."""
    if not isinstance(results, list):
        return []
    digests = [digest_tool_result(item) for item in results if isinstance(item, dict)]
    encoded = json.dumps(digests, ensure_ascii=False, separators=(",", ":"))
    while digests and len(encoded) > _MAX_TOTAL:
        digests.pop()
        encoded = json.dumps(digests, ensure_ascii=False, separators=(",", ":"))
    return digests


def tool_result_digest_context(results: list[dict[str, Any]] | Any) -> str:
    """Serialize the digest as a bounded model-context payload."""
    return json.dumps(build_tool_result_digests(results), ensure_ascii=False, separators=(",", ":"))[:_MAX_TOTAL]
