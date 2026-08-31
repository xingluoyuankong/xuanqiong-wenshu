"""Classify durable Agent job failures without embedding Provider secrets."""
from __future__ import annotations

from dataclasses import dataclass

RETRYABLE_ERROR_TYPES = frozenset({
    "ProviderTimeout",
    "ProviderUnavailable",
    "LeaseExpired",
    "TemporaryDatabaseError",
    "WorkerCancelled",
})

NON_RETRYABLE_ERROR_TYPES = frozenset({
    "UnknownJobKind",
    "InvalidPayload",
    "AgentScopeViolation",
    "AgentConflict",
})

@dataclass(frozen=True)
class RetryDecision:
    retryable: bool
    reason: str
    delay_seconds: int


def classify_error(error_type: str, *, attempt_count: int, max_attempts: int) -> RetryDecision:
    normalized = str(error_type or "UnknownError")[:160]
    if normalized in NON_RETRYABLE_ERROR_TYPES:
        return RetryDecision(False, "non_retryable_error", 0)
    retryable = normalized in RETRYABLE_ERROR_TYPES
    if not retryable:
        return RetryDecision(False, "unclassified_error_requires_review", 0)
    if int(attempt_count) >= int(max_attempts):
        return RetryDecision(True, "retry_budget_exhausted", 0)
    return RetryDecision(True, "transient_error", min(300, 2 ** max(0, int(attempt_count) - 1)))
