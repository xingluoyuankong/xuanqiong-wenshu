"""Public Job projections and bounded read queries, owned by the API layer.

This module never claims, recovers, replays or modifies a durable Job. Legacy
JSON keys remain present but private payloads and lease identities are withheld.
"""
from __future__ import annotations

from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...agent.schemas import AgentJobRead
from ...models.agent import AgentJob, AgentRun

TERMINAL_RUN_STATUSES = frozenset({"completed", "succeeded", "failed", "cancelled", "dead_letter"})
TERMINAL_JOB_STATUSES = TERMINAL_RUN_STATUSES
_RECOVERY_MARKER = "Recovered expired continuation from verified failed read proof"
_ERROR_CODES = frozenset({
    "ContinuationConflict", "ContinuationPlanError", "ContinuationRecoveryRejected",
    "RunContextIntegrityError", "ApprovalSnapshotIntegrityError", "AgentContextIntegrityError",
    "AgentPlanIntegrityError", "RuntimeError", "ValueError", "TypeError", "KeyError",
    "AttributeError", "TimeoutError", "ConnectionError", "OSError", "AgentConflict",
    "AgentJobError", "ProviderTimeout", "ProviderUnavailable", "RateLimitError",
    "LeaseExpiredRecovery", "LeaseExpired", "DependencyNotCompleted", "ToolContractViolation",
})


class PublicAgentJobRead(AgentJobRead):
    terminal_status: str | None = None
    recovery_status: Literal["not_recorded", "continuation_completed", "failure_reconciled"] = "not_recorded"


def public_job(row: AgentJob) -> PublicAgentJobRead:
    # Never serialize the ORM row first: even malformed private JSON must not
    # enter validation, error messages or the response body.
    fields = {name: getattr(row, name) for name in (
        "id", "run_id", "correlation_id", "transaction_id", "user_id", "project_id",
        "kind", "status", "attempt_count", "max_attempts", "available_at",
        "lease_expires_at", "lease_generation", "cancel_requested_at", "created_at",
        "started_at", "finished_at",
    )}
    result = row.result_json if isinstance(row.result_json, dict) else {}
    safe_result = {}
    recovery = "not_recorded"
    if row.kind == "visible_response":
        # This is a public correlation handle, not response content. Only
        # expose it when it self-binds to this Job; never pass arbitrary IDs.
        if result.get("visible_response_job_id") == row.id:
            safe_result["visible_response_job_id"] = row.id
    if row.kind == "agent_continuation":
        if row.status in {"succeeded", "completed"}:
            for key in ("continuation_completed", "pending_approval", "continuation_acknowledged"):
                if type(result.get(key)) is bool:
                    safe_result[key] = result[key]
            if safe_result.get("continuation_completed") is True:
                recovery = "continuation_completed"
        if (row.status in {"failed", "dead_letter"} and row.error_detail == _RECOVERY_MARKER
                and row.finished_at is not None and row.lease_owner is None and row.lease_expires_at is None):
            # A recorded recovery marker, not a new evaluation of write proof.
            recovery = "failure_reconciled"
    code = row.error_type if row.error_type in _ERROR_CODES else ("AgentJobError" if row.error_type else None)
    return PublicAgentJobRead(**fields, idempotency_key="", payload_json={}, result_json=safe_result,
        error_type=code, error_detail=None, lease_owner=None, cancel_reason=None,
        terminal_status=row.status if row.status in TERMINAL_JOB_STATUSES else None, recovery_status=recovery)


def scoped_job_query(*, user_id: int, project_id: str | None = None,
                     run_id: str | None = None, status: str | None = None, kind: str | None = None):
    query = select(AgentJob).join(AgentRun, AgentRun.id == AgentJob.run_id).where(
        AgentJob.user_id == user_id, AgentRun.user_id == user_id,
        AgentJob.correlation_id == AgentRun.correlation_id,
        AgentJob.transaction_id.is_not_distinct_from(AgentRun.transaction_id),
        AgentJob.project_id.is_not_distinct_from(AgentRun.project_id),
    )
    if project_id is not None:
        query = query.where(AgentJob.project_id == project_id)
    if run_id is not None:
        query = query.where(AgentJob.run_id == run_id)
    if status is not None:
        query = query.where(AgentJob.status == status)
    if kind is not None:
        query = query.where(AgentJob.kind == kind)
    return query


async def public_state_jobs(session: AsyncSession, state: dict) -> dict:
    rows = list((await session.execute(scoped_job_query(user_id=state["user_id"], run_id=state["run_id"])
        .order_by(AgentJob.created_at.asc(), AgentJob.id.asc()))).scalars())
    jobs = [public_job(row) for row in rows]
    state = dict(state)
    state["jobs"] = [job.model_dump(include={"id", "kind", "status", "attempt_count", "max_attempts",
        "error_type", "terminal_status", "recovery_status", "result_json", "finished_at"}) for job in jobs]
    state["blocked_reason"] = next((job.error_type for job in reversed(jobs)
        if job.status in {"failed", "dead_letter"} and job.error_type), None)
    return state
