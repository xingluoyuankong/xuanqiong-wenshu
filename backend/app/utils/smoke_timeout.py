"""Shared timeout normalization for real ASGI smoke polling."""
from __future__ import annotations

from typing import Any, Mapping

SMOKE_MIN_TIMEOUT_SECONDS = 15 * 60
SMOKE_MAX_TIMEOUT_SECONDS = 4 * 60 * 60


def coerce_smoke_timeout_seconds(value: Any) -> int:
    try:
        seconds = int(float(value or 0))
    except (TypeError, ValueError):
        return 0
    return max(0, min(SMOKE_MAX_TIMEOUT_SECONDS, seconds))


def resolve_smoke_poll_timeout_seconds(
    submitted_payload: Mapping[str, Any] | None,
    *,
    requested_timeout_seconds: Any = 0,
    fallback_timeout_seconds: Any = 0,
) -> int:
    """Mirror the backend budget for polling without weakening the backend gate."""
    requested = coerce_smoke_timeout_seconds(requested_timeout_seconds)
    if requested:
        return max(SMOKE_MIN_TIMEOUT_SECONDS, requested)

    runtime = submitted_payload.get("generation_runtime") if isinstance(submitted_payload, Mapping) else None
    normalized = runtime.get("timeout_seconds") if isinstance(runtime, Mapping) else None
    normalized = coerce_smoke_timeout_seconds(normalized)
    fallback = coerce_smoke_timeout_seconds(fallback_timeout_seconds)
    return max(SMOKE_MIN_TIMEOUT_SECONDS, normalized or fallback or SMOKE_MAX_TIMEOUT_SECONDS)


__all__ = [
    "SMOKE_MIN_TIMEOUT_SECONDS",
    "SMOKE_MAX_TIMEOUT_SECONDS",
    "coerce_smoke_timeout_seconds",
    "resolve_smoke_poll_timeout_seconds",
]
