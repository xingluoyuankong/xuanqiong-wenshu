"""Bounded, redacted Provider attempt provenance for Agent runs.

The ledger is JSON-serializable so it can live in the existing Run context until
a dedicated relational ProviderAttempt table is introduced. It is idempotent by
attempt_id and never stores prompts, headers, credentials, or raw provider text.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
from typing import Any

ERROR_CATEGORIES = {
    "AUTHENTICATION", "RATE_LIMIT", "TRANSIENT_5XX", "NETWORK_DISCONNECT",
    "TIMEOUT", "EMPTY_STREAM", "INVALID_RESPONSE", "CANCELLED",
    "BUDGET_EXHAUSTED", "POLICY_REJECTED", "UNKNOWN",
}

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _ref(value: Any, limit: int = 200) -> str | None:
    text = str(value or "").strip()
    return text[:limit] or None

def classify_provider_error(error: BaseException | None, *, http_status: int | None = None) -> str:
    status = int(http_status or getattr(error, "status_code", 0) or 0)
    if status == 401 or status == 403: return "AUTHENTICATION"
    if status == 429: return "RATE_LIMIT"
    if status >= 500: return "TRANSIENT_5XX"
    name = type(error).__name__.lower() if error is not None else ""
    if "cancel" in name: return "CANCELLED"
    if "timeout" in name: return "TIMEOUT"
    if any(token in name for token in ("connection", "connect", "protocol", "readerror", "remotedisconnect")): return "NETWORK_DISCONNECT"
    if "invalid" in name or "json" in name: return "INVALID_RESPONSE"
    return "UNKNOWN"

@dataclass
class ProviderAttemptRecord:
    attempt_id: str
    attempt: int
    role: str
    provider_ref: str | None
    model_ref: str | None
    status: str
    started_at: str
    first_token_at: str | None = None
    finished_at: str | None = None
    error_category: str | None = None
    http_status: int | None = None
    retry_index: int = 0
    fallback_from_attempt: int | None = None
    cancel_observed: bool = False
    output_digest: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

class ProviderAttemptLedger:
    """Small idempotent ledger suitable for safe Run context persistence."""
    def __init__(self, *, run_id: str, max_attempts: int = 16) -> None:
        self.run_id = str(run_id)[:128]
        self.max_attempts = max(1, min(int(max_attempts), 64))
        self._records: dict[str, ProviderAttemptRecord] = {}

    @classmethod
    def from_snapshot(cls, *, run_id: str, snapshot: Any, max_attempts: int = 16) -> "ProviderAttemptLedger":
        """Rehydrate bounded persisted history before a durable Job retry appends."""
        ledger = cls(run_id=run_id, max_attempts=max_attempts)
        raw = snapshot if isinstance(snapshot, dict) else {}
        records = raw.get("provider_attempts") if isinstance(raw.get("provider_attempts"), list) else []
        valid_statuses = {"running", "succeeded", "failed"}
        for index, item in enumerate(records[:ledger.max_attempts], start=1):
            if not isinstance(item, dict):
                continue
            try:
                attempt = int(item.get("attempt") or index)
            except (TypeError, ValueError):
                attempt = index
            if attempt < 1 or attempt > ledger.max_attempts:
                attempt = index
            status = str(item.get("status") or "unknown").strip().lower()
            if status not in valid_statuses:
                status = "failed"
            # A persisted running attempt belongs to the worker that was
            # interrupted before this retry. Rehydrate it as a closed failure
            # so the Provider timeline cannot retain a permanent running state.
            interrupted = status == "running"
            if interrupted:
                status = "failed"
            key = f"{ledger.run_id}:restored:{attempt}:{index}"
            ledger._records[key] = ProviderAttemptRecord(
                attempt_id=key,
                attempt=attempt,
                role=_ref(item.get("role"), 80) or "unknown",
                provider_ref=_ref(item.get("provider_ref")),
                model_ref=_ref(item.get("model_ref")),
                status=status,
                started_at=_ref(item.get("started_at"), 64) or _now(),
                first_token_at=_ref(item.get("first_token_at"), 64),
                finished_at=(_ref(item.get("finished_at"), 64) or (_now() if interrupted else None)),
                error_category=("NETWORK_DISCONNECT" if interrupted else _ref(item.get("error_category"), 40)),
                http_status=int(item["http_status"]) if isinstance(item.get("http_status"), int) else None,
                retry_index=max(0, int(item.get("retry_index") or 0)),
                fallback_from_attempt=int(item["fallback_from_attempt"]) if isinstance(item.get("fallback_from_attempt"), int) else None,
                cancel_observed=bool(item.get("cancel_observed")),
                output_digest=_ref(item.get("output_digest"), 128),
            )
        return ledger

    def begin(self, *, role: str, provider_ref: Any, model_ref: Any, retry_index: int = 0, fallback_from_attempt: int | None = None, attempt_id: str | None = None) -> ProviderAttemptRecord:
        if len(self._records) >= self.max_attempts and not attempt_id: raise ValueError("provider attempt budget exhausted")
        number = len(self._records) + 1
        key = attempt_id or f"{self.run_id}:{role}:{number}"
        if key in self._records: return self._records[key]
        record = ProviderAttemptRecord(key, number, _ref(role, 80) or "unknown", _ref(provider_ref), _ref(model_ref), "running", _now(), retry_index=max(0, int(retry_index)), fallback_from_attempt=fallback_from_attempt)
        self._records[key] = record
        return record

    def mark_first_token(self, attempt_id: str) -> ProviderAttemptRecord:
        record = self._records[attempt_id]
        if record.first_token_at is None: record.first_token_at = _now()
        return record

    def finish(self, attempt_id: str, *, status: str = "succeeded", output: str | None = None) -> ProviderAttemptRecord:
        record = self._records[attempt_id]
        record.status = status
        record.finished_at = record.finished_at or _now()
        if output is not None: record.output_digest = hashlib.sha256(output.encode("utf-8")).hexdigest()
        return record

    def fail(self, attempt_id: str, error: BaseException | None = None, *, http_status: int | None = None, category: str | None = None, output: str | None = None) -> ProviderAttemptRecord:
        record = self._records[attempt_id]
        record.status = "failed"
        record.finished_at = record.finished_at or _now()
        record.http_status = int(http_status) if http_status is not None else record.http_status
        record.error_category = category if category in ERROR_CATEGORIES else classify_provider_error(error, http_status=http_status)
        record.cancel_observed = record.error_category == "CANCELLED"
        if output and not record.output_digest:
            record.output_digest = hashlib.sha256(output.encode("utf-8")).hexdigest()
        return record

    def cancel(self, attempt_id: str) -> ProviderAttemptRecord:
        return self.fail(attempt_id, category="CANCELLED")

    def latest_attempt_number(self) -> int | None:
        return max((record.attempt for record in self._records.values()), default=None)

    def snapshot(self) -> dict[str, Any]:
        records = [item.to_dict() for item in sorted(self._records.values(), key=lambda item: item.attempt)]
        selected = next((item.attempt for item in reversed(self._records.values()) if item.status == "succeeded"), None)
        return {"provider_attempts": records, "selected_provider_attempt": selected, "fallback_used": any(item.fallback_from_attempt is not None for item in self._records.values())}
