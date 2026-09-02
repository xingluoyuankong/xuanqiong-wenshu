"""Durable Agent job contract and worker-safe state transitions.

This module persists execution intent and leases. It intentionally does not
start a worker process; N-12 first establishes the database contract that a
future worker can safely claim.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import and_, case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.agent import AgentJob, AgentRun
from ..agent.state_machine import CLAIMABLE_RUN_STATUSES as STATE_CLAIMABLE_RUN_STATUSES, RECOVERY_READY_PHASE
from .retry_policy import RETRYABLE_ERROR_TYPES, classify_error

TERMINAL_JOB_STATUSES = {"succeeded", "failed", "cancelled", "dead_letter"}
# A queued Job may advance its parent Run only while the Run is in one of the
# actively executable states.  In particular, paused/awaiting_approval/
# cancelling/terminal Runs are durable gates, not worker hints.
CLAIMABLE_RUN_STATUSES = set(STATE_CLAIMABLE_RUN_STATUSES)
# A stale-run sweeper uses paused + recovery_ready as an explicit recovery
# marker. It is the only paused state that may reclaim an already persisted
# Job; ordinary user pauses and approval waits remain hard claim gates.
JOB_APPLYABLE_RUN_STATUSES = {"created", "planning", "running", "awaiting_approval", "completed"}


def _claimable_run_condition():
    return or_(
        AgentRun.status.in_(CLAIMABLE_RUN_STATUSES),
        (AgentRun.status == "paused") & (AgentRun.current_phase == RECOVERY_READY_PHASE),
    )


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def _clean(value: Any) -> Any:
    forbidden = {"thought", "reasoning", "chain_of_thought", "private_reasoning", "system_prompt", "provider_secret", "api_key", "authorization"}
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items() if str(k).lower() not in forbidden}
    if isinstance(value, list):
        return [_clean(item) for item in value[:200]]
    if isinstance(value, str):
        return value[:12000]
    return value


class AgentJobError(Exception):
    pass


class AgentJobNotFound(AgentJobError):
    pass


class AgentJobConflict(AgentJobError):
    pass


class AgentJobService:
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _now() -> datetime:
        return _now()

    async def _get(self, job_id: str, user_id: int) -> AgentJob:
        job = (await self.session.execute(
            select(AgentJob)
            .where(AgentJob.id == job_id, AgentJob.user_id == user_id)
            .execution_options(populate_existing=True)
        )).scalar_one_or_none()
        if job is None:
            raise AgentJobNotFound("agent job not found")
        return job

    async def create_job(
        self,
        *,
        run_id: str,
        user_id: int,
        project_id: str | None,
        kind: str,
        idempotency_key: str,
        payload: dict[str, Any] | None = None,
        max_attempts: int = 3,
        available_at: datetime | None = None,
        commit: bool = True,
    ) -> AgentJob:
        run = (await self.session.execute(select(AgentRun).where(AgentRun.id == run_id, AgentRun.user_id == user_id))).scalar_one_or_none()
        if run is None:
            raise AgentJobNotFound("agent run not found")
        if run.project_id != project_id:
            raise AgentJobConflict("job project does not match run project")
        existing = (await self.session.execute(select(AgentJob).where(AgentJob.run_id == run_id, AgentJob.idempotency_key == idempotency_key))).scalar_one_or_none()
        if existing is not None:
            return existing
        if run.cancel_requested_at is not None or run.status not in CLAIMABLE_RUN_STATUSES:
            raise AgentJobConflict("run is not accepting new jobs")
        job = AgentJob(
            id=str(uuid4()), run_id=run_id, correlation_id=run.correlation_id, transaction_id=run.transaction_id, user_id=user_id, project_id=project_id,
            kind=str(kind).strip()[:80], status="queued", idempotency_key=str(idempotency_key)[:255],
            payload_json=_clean(payload or {}), result_json={}, max_attempts=max(1, min(int(max_attempts), 10)),
            available_at=available_at or _now(),
        )
        if not job.kind or not job.idempotency_key:
            raise AgentJobConflict("job kind and idempotency_key are required")
        self.session.add(job)
        if commit:
            await self.session.commit()
            await self.session.refresh(job)
        return job

    async def get_job(self, *, job_id: str, user_id: int) -> AgentJob:
        return await self._get(job_id, user_id)

    async def claim_job(
        self,
        *,
        job_id: str,
        user_id: int,
        lease_owner: str,
        lease_seconds: int = 120,
        lease_generation: int | None = None,
    ) -> AgentJob:
        owner = str(lease_owner or "").strip()[:128]
        if not owner:
            raise AgentJobConflict("lease_owner is required")
        now = _now()
        expires = now + timedelta(seconds=max(1, min(int(lease_seconds), 3600)))
        result = await self.session.execute(
            update(AgentJob)
            .execution_options(synchronize_session=False)
            .where(
                AgentJob.id == job_id,
                AgentJob.user_id == user_id,
                AgentJob.cancel_requested_at.is_(None),
                or_(lease_generation is None, AgentJob.lease_generation == int(lease_generation or 0)),
                AgentJob.run_id.in_(
                    select(AgentRun.id).where(
                        _claimable_run_condition(),
                        AgentRun.cancel_requested_at.is_(None),
                    )
                ),
                or_(
                    AgentJob.status == "queued",
                    (AgentJob.status == "running")
                    & AgentJob.lease_expires_at.is_not(None)
                    & (AgentJob.lease_expires_at <= now),
                ),
                AgentJob.available_at <= now,
            )
            .values(
                status="running",
                lease_owner=owner,
                lease_expires_at=expires,
                lease_generation=case(
                    (
                        and_(AgentJob.lease_owner == owner, AgentJob.lease_expires_at > now),
                        AgentJob.lease_generation,
                    ),
                    else_=AgentJob.lease_generation + 1,
                ),
                attempt_count=AgentJob.attempt_count + 1,
                started_at=func.coalesce(AgentJob.started_at, now),
            )
        )
        if result.rowcount != 1:
            raise AgentJobConflict("job is not claimable")
        await self.session.commit()
        job = await self._get(job_id, user_id)
        await self.session.refresh(job)
        return job

    async def claim_next_job(self, *, lease_owner: str, lease_seconds: int = 120) -> AgentJob | None:
        """Atomically claim one globally queued job for an internal worker.

        This method deliberately has no user-facing authorization surface; the
        worker is still required to execute only the persisted, project-scoped
        payload. A conditional UPDATE is the claim fence, so two workers may
        observe the same candidate but only one receives a running lease.
        """
        owner = str(lease_owner or "").strip()[:128]
        if not owner:
            raise AgentJobConflict("lease_owner is required")
        now = _now()
        candidate = (await self.session.execute(
            select(AgentJob.id, AgentJob.user_id)
            .join(AgentRun, AgentRun.id == AgentJob.run_id)
            .where(
                AgentJob.cancel_requested_at.is_(None),
                _claimable_run_condition(),
                AgentRun.cancel_requested_at.is_(None),
                AgentJob.available_at <= now,
                or_(
                    AgentJob.status == "queued",
                    (AgentJob.status == "running") & AgentJob.lease_expires_at.is_not(None) & (AgentJob.lease_expires_at <= now),
                ),
            )
            .order_by(AgentJob.available_at.asc(), AgentJob.created_at.asc(), AgentJob.id.asc())
            .limit(1)
        )).first()
        if candidate is None:
            return None
        job_id, user_id = candidate
        try:
            return await self.claim_job(job_id=str(job_id), user_id=int(user_id), lease_owner=owner, lease_seconds=lease_seconds)
        except AgentJobConflict:
            # Another worker won the conditional claim; polling can continue.
            return None

    async def heartbeat(self, *, job_id: str, user_id: int, lease_owner: str, lease_seconds: int = 120, lease_generation: int | None = None) -> AgentJob:
        now = _now(); expires = now + timedelta(seconds=max(1, min(int(lease_seconds), 3600)))
        result = await self.session.execute(update(AgentJob).execution_options(synchronize_session=False).where(
            AgentJob.id == job_id,
            AgentJob.user_id == user_id,
            AgentJob.status == "running",
            AgentJob.lease_owner == str(lease_owner)[:128],
            or_(lease_generation is None, AgentJob.lease_generation == int(lease_generation or 0)),
            AgentJob.cancel_requested_at.is_(None),
            AgentJob.run_id.in_(
                select(AgentRun.id).where(
                    _claimable_run_condition(),
                    AgentRun.cancel_requested_at.is_(None),
                )
            ),
        ).values(lease_expires_at=expires))
        if result.rowcount != 1:
            raise AgentJobConflict("job heartbeat lease is not owned")
        await self.session.commit()
        return await self._get(job_id, user_id)

    async def request_cancel_for_run(self, *, run_id: str, user_id: int, reason: str | None = None) -> int:
        """Cancel every queued/running Job belonging to one Run.

        The row-count result lets the caller converge the parent Run without
        relying on a copied job id in mutable Run context.
        """
        now = _now()
        changed = await self.session.execute(
            update(AgentJob)
            .execution_options(synchronize_session="fetch")
            .where(
                AgentJob.run_id == run_id,
                AgentJob.user_id == user_id,
                AgentJob.status.in_({"queued", "running"}),
            )
            .values(
                cancel_requested_at=now,
                cancel_reason=(reason or "user_requested")[:255],
                status="cancelled",
                lease_owner=None,
                lease_expires_at=None,
                finished_at=now,
            )
        )
        await self.session.commit()
        return int(changed.rowcount or 0)


    async def request_cancel(self, *, job_id: str, user_id: int, reason: str | None = None) -> AgentJob:
        job = await self._get(job_id, user_id)
        await self.request_cancel_for_run(
            run_id=job.run_id,
            user_id=user_id,
            reason=reason,
        )
        return await self._get(job_id, user_id)

    async def complete(self, *, job_id: str, user_id: int, lease_owner: str, result: dict[str, Any] | None = None, lease_generation: int | None = None) -> AgentJob:
        owner = str(lease_owner or "")[:128]
        if not owner:
            raise AgentJobConflict("lease_owner is required")
        now = _now()
        changed = await self.session.execute(
            update(AgentJob)
            .execution_options(synchronize_session=False)
            .where(
                AgentJob.id == job_id,
                AgentJob.user_id == user_id,
                AgentJob.status == "running",
                AgentJob.lease_owner == owner,
                or_(lease_generation is None, AgentJob.lease_generation == int(lease_generation or 0)),
                AgentJob.cancel_requested_at.is_(None),
                AgentJob.run_id.in_(
                    select(AgentRun.id).where(
                        AgentRun.status.in_(JOB_APPLYABLE_RUN_STATUSES),
                        AgentRun.cancel_requested_at.is_(None),
                    )
                ),
            )
            .values(
                status="succeeded",
                result_json=_clean(result or {}),
                error_type=None,
                error_detail=None,
                finished_at=now,
                lease_owner=None,
                lease_expires_at=None,
            )
        )
        if changed.rowcount != 1:
            raise AgentJobConflict("job completion lost its lease or run is no longer active")
        await self.session.commit()
        return await self._get(job_id, user_id)

    async def defer(self, *, job_id: str, user_id: int, lease_owner: str, reason: str = "run_paused", lease_generation: int | None = None) -> AgentJob:
        """Return a claimed Job to the queue without consuming another attempt."""
        owner = str(lease_owner or "")[:128]
        if not owner:
            raise AgentJobConflict("lease_owner is required")
        changed = await self.session.execute(
            update(AgentJob)
            .execution_options(synchronize_session=False)
            .where(
                AgentJob.id == job_id,
                AgentJob.user_id == user_id,
                AgentJob.status == "running",
                AgentJob.lease_owner == owner,
                or_(lease_generation is None, AgentJob.lease_generation == int(lease_generation or 0)),
                AgentJob.cancel_requested_at.is_(None),
            )
            .values(
                status="queued",
                available_at=_now(),
                lease_owner=None,
                lease_expires_at=None,
                error_type="RunPaused",
                error_detail=str(reason or "run_paused")[:1000],
                finished_at=None,
            )
        )
        if changed.rowcount != 1:
            raise AgentJobConflict("job cannot be deferred by this worker")
        await self.session.commit()
        return await self._get(job_id, user_id)

    async def fail(self, *, job_id: str, user_id: int, lease_owner: str, error_type: str, detail: str | None = None, retryable: bool | None = None, lease_generation: int | None = None) -> AgentJob:
        job = await self._get(job_id, user_id)
        owner = str(lease_owner or "")[:128]
        if job.status != "running" or job.lease_owner != owner:
            raise AgentJobConflict("job is not owned by this worker")
        if lease_generation is not None and int(job.lease_generation or 0) != int(lease_generation):
            raise AgentJobConflict("job lease generation is stale")
        decision = classify_error(str(error_type), attempt_count=job.attempt_count, max_attempts=job.max_attempts)
        retry = decision.retryable if retryable is None else bool(retryable)
        now = _now()
        next_status = "queued" if retry and job.attempt_count < job.max_attempts and job.cancel_requested_at is None else ("dead_letter" if retry else "failed")
        values: dict[str, Any] = {
            "error_type": str(error_type)[:160],
            "error_detail": str(detail or "")[:1000] or None,
            "lease_owner": None,
            "lease_expires_at": None,
        }
        if next_status == "queued":
            values.update(status="queued", available_at=now + timedelta(seconds=decision.delay_seconds), finished_at=None)
        else:
            values.update(status=next_status, finished_at=now)
        changed = await self.session.execute(
            update(AgentJob)
            .execution_options(synchronize_session=False)
            .where(
                AgentJob.id == job_id,
                AgentJob.user_id == user_id,
                AgentJob.status == "running",
                AgentJob.lease_owner == owner,
                or_(lease_generation is None, AgentJob.lease_generation == int(lease_generation or 0)),
                AgentJob.cancel_requested_at.is_(None),
            )
            .values(**values)
        )
        if changed.rowcount != 1:
            raise AgentJobConflict("job failure lost its lease or cancellation won")
        await self.session.commit()
        return await self._get(job_id, user_id)

    async def reconcile_completed_handoff_jobs(self) -> list[AgentJob]:
        """Settle expired worker acknowledgements after durable terminal handoffs.

        A worker can persist a downstream handoff and then die before acknowledging
        its current Job.  A terminal Run must not leave that predecessor permanently
        ``running``.  Every branch below requires durable, Run-local proof before it
        marks a Job successful; it never infers success merely from a terminal phase.
        """
        now = _now()
        settled: list[AgentJob] = []

        visible_candidates = list((await self.session.execute(
            select(AgentJob, AgentRun)
            .join(AgentRun, AgentRun.id == AgentJob.run_id)
            .where(
                AgentJob.kind == "visible_response",
                AgentJob.status == "running",
                AgentJob.lease_expires_at.is_not(None),
                AgentJob.lease_expires_at <= now,
                AgentJob.cancel_requested_at.is_(None),
                AgentRun.status == "completed",
            )
        )).all())
        for job, run in visible_candidates:
            marker = str((run.context_json or {}).get("visible_response_final_message_id") or "").strip()
            if not marker:
                continue
            changed = await self.session.execute(
                update(AgentJob)
                .where(
                    AgentJob.id == job.id,
                    AgentJob.status == "running",
                    AgentJob.lease_expires_at.is_not(None),
                    AgentJob.lease_expires_at <= now,
                    AgentJob.cancel_requested_at.is_(None),
                )
                .values(
                    status="succeeded",
                    result_json={"visible_response_job_id": job.id},
                    error_type=None,
                    error_detail=None,
                    finished_at=now,
                    lease_owner=None,
                    lease_expires_at=None,
                )
            )
            if changed.rowcount == 1:
                settled.append(job)

        execution_candidates = list((await self.session.execute(
            select(AgentJob, AgentRun)
            .join(AgentRun, AgentRun.id == AgentJob.run_id)
            .where(
                AgentJob.kind == "agent_execution",
                AgentJob.status == "running",
                AgentJob.lease_expires_at.is_not(None),
                AgentJob.lease_expires_at <= now,
                AgentJob.cancel_requested_at.is_(None),
                AgentRun.status == "completed",
            )
        )).all())
        for job, run in execution_candidates:
            context = dict(run.context_json or {})
            execution_job_id = str(context.get("execution_job_id") or "").strip()
            visible_response_job_id = str(context.get("visible_response_job_id") or "").strip()
            if execution_job_id != job.id or not visible_response_job_id:
                continue
            visible_response_succeeded = (await self.session.execute(
                select(AgentJob.id).where(
                    AgentJob.id == visible_response_job_id,
                    AgentJob.run_id == run.id,
                    AgentJob.user_id == job.user_id,
                    AgentJob.kind == "visible_response",
                    AgentJob.status == "succeeded",
                )
            )).scalar_one_or_none()
            if visible_response_succeeded is None:
                continue
            changed = await self.session.execute(
                update(AgentJob)
                .where(
                    AgentJob.id == job.id,
                    AgentJob.status == "running",
                    AgentJob.lease_expires_at.is_not(None),
                    AgentJob.lease_expires_at <= now,
                    AgentJob.cancel_requested_at.is_(None),
                )
                .values(
                    status="succeeded",
                    result_json={
                        "status": "assistant_queued",
                        "visible_response_job_id": visible_response_job_id,
                        "reconciled_after_handoff": True,
                    },
                    error_type=None,
                    error_detail=None,
                    finished_at=now,
                    lease_owner=None,
                    lease_expires_at=None,
                )
            )
            if changed.rowcount == 1:
                settled.append(job)

        if settled:
            await self.session.commit()
            for job in settled:
                await self.session.refresh(job)
        return settled

    async def reconcile_completed_visible_response_jobs(self) -> list[AgentJob]:
        """Backward-compatible name for terminal Job handoff reconciliation."""
        return await self.reconcile_completed_handoff_jobs()

    async def list_dead_letters(self, *, limit: int = 100) -> list[AgentJob]:
        stmt = (
            select(AgentJob)
            .where(AgentJob.status == "dead_letter")
            .order_by(AgentJob.finished_at.desc().nullslast(), AgentJob.created_at.desc())
            .limit(min(max(1, int(limit)), 200))
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def replay_dead_letter(
        self,
        *,
        job_id: str,
        operator_id: int,
        reason: str | None = None,
    ) -> AgentJob:
        """Requeue one DLQ job without erasing its failure history.

        Replaying is an operator action: the existing row keeps its attempt
        count and error fields, while the next claim becomes a new attempt.
        The durable run event is the audit record; repeated calls are safe once
        the job is no longer dead-lettered.
        """
        job = (await self.session.execute(select(AgentJob).where(AgentJob.id == job_id))).scalar_one_or_none()
        if job is None:
            raise AgentJobNotFound("agent job not found")
        if job.status != "dead_letter":
            return job
        run = (await self.session.execute(select(AgentRun).where(AgentRun.id == job.run_id))).scalar_one()
        if run.status in {"completed", "failed", "cancelled"}:
            raise AgentJobConflict("terminal run cannot replay")
        job.status = "queued"
        job.available_at = self._now()
        job.lease_owner = None
        job.lease_expires_at = None
        job.cancel_requested_at = None
        job.cancel_reason = None
        job.finished_at = None
        detail = (reason or "operator_replay")[:255]
        job.error_detail = f"replayed_by={int(operator_id)}; reason={detail}"[:1000]
        from ..services.agent_runtime import AgentRuntimeService
        try:
            await AgentRuntimeService(self.session).append_event(
                run_id=job.run_id,
                user_id=job.user_id,
                event_type="job_replayed",
                summary="管理员已将 Agent Job 从死信队列重新排队",
                data={
                    "job_id": job.id,
                    "attempt_count": job.attempt_count,
                    "operator_id": int(operator_id),
                },
                commit=False,
            )
            await self.session.commit()
        except Exception:
            # Requeue and its audit event are one durable state transition.
            # A failed event append must not leave an untracked queued Job.
            await self.session.rollback()
            raise
        await self.session.refresh(job)
        return job
    async def list_jobs(self, *, user_id: int, project_id: str | None = None, status: str | None = None, limit: int = 100) -> list[AgentJob]:
        stmt = select(AgentJob).where(AgentJob.user_id == user_id)
        if project_id is not None: stmt = stmt.where(AgentJob.project_id == project_id)
        if status is not None: stmt = stmt.where(AgentJob.status == status)
        stmt = stmt.order_by(AgentJob.created_at.desc()).limit(min(max(1, int(limit)), 200))
        return list((await self.session.execute(stmt)).scalars().all())
