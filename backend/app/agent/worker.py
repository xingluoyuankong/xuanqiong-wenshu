"""Testable durable Agent worker loop.

N-12 exposes the worker boundary without starting it from FastAPI. Production
startup integration is intentionally deferred until multi-instance fault
injection and deployment policy are complete.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from datetime import timedelta
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .continuation import AgentContinuationService
from .continuation_scan import ContinuationScanCursor
from .continuation_worker import handle_agent_continuation_job
from .execution import execute_agent_execution_job
from .jobs import AgentJobService
from .runner import _run_visible_response
from ..services.agent_runtime import AgentRuntimeService
from ..models.agent import AgentJob, AgentRun, AgentRunStep

AgentJobHandler = Callable[[AgentJob, AsyncSession], Awaitable[dict[str, Any]]]


async def handle_visible_response_job(job: AgentJob, session: AsyncSession) -> dict[str, Any]:
    payload = dict(job.payload_json or {})
    goal = str(payload.get("goal") or "").strip()
    tool_results = payload.get("tool_results") if isinstance(payload.get("tool_results"), list) else []
    if not goal:
        raise ValueError("visible response job has no goal")
    # A worker process owns the job lease; runner performs only the Provider
    # response and event append, without claiming/completing the job again.
    run = (await session.execute(select(AgentRun).where(AgentRun.id == job.run_id, AgentRun.user_id == job.user_id))).scalar_one()
    if run.status == "paused" and run.current_phase == "recovery_ready":
        # A stale-run sweeper deliberately pauses the run before a replacement
        # worker can continue it. Only this durable recovery marker permits an
        # automatic resume; awaiting-approval and user-paused runs stay paused.
        runtime = AgentRuntimeService(session)
        await runtime.update_run(
            run_id=run.id,
            user_id=run.user_id,
            status="running",
            phase="recovered",
            progress=min(85.0, max(0.0, float(run.progress))),
        )
        await runtime.append_event(
            run_id=run.id,
            user_id=run.user_id,
            event_type="run_resumed",
            summary="独立 Worker 已从过期租约恢复 Agent 运行",
            data={"phase": "recovered"},
        )
        await session.refresh(run)
    await _run_visible_response(
        run_id=job.run_id,
        session_id=run.session_id,
        user_id=job.user_id,
        goal=goal,
        tool_results=tool_results,
        job_id=job.id,
        manage_job=False,
        worker_id=f"worker:{job.lease_owner or 'unknown'}",
    )
    await session.refresh(run)
    if run.status != "completed":
        raise RuntimeError(f"visible response run ended as {run.status}")
    return {"visible_response_job_id": job.id}


async def handle_agent_execution_job(job: AgentJob, session: AsyncSession) -> dict[str, Any]:
    """Execute the persisted planning/read/suggest phase for one Run."""
    try:
        return await execute_agent_execution_job(job, session)
    except Exception as exc:
        runtime = AgentRuntimeService(session)
        try:
            run = await runtime.get_run(job.run_id, job.user_id)
            if run.status not in {"completed", "failed", "cancelled"}:
                await runtime.update_run(
                    run_id=run.id,
                    user_id=run.user_id,
                    status="failed",
                    phase="execution_error",
                )
                await runtime.append_event(
                    run_id=run.id,
                    user_id=run.user_id,
                    event_type="run_failed",
                    summary="Agent 执行任务失败",
                    data={"error_type": type(exc).__name__, "phase": "execution_error"},
                )
        except Exception:
            pass
        raise


class AgentWorker:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        worker_id: str,
        handlers: dict[str, AgentJobHandler],
        lease_seconds: int = 120,
        poll_interval: float = 0.25,
    ) -> None:
        owner = str(worker_id or '').strip()[:128]
        if not owner:
            raise ValueError('worker_id is required')
        self.session_factory = session_factory
        self.worker_id = owner
        self.handlers = dict(handlers)
        self._activation_scan_cursor = ContinuationScanCursor()
        self._failure_scan_cursor = ContinuationScanCursor()
        self.lease_seconds = max(1, min(int(lease_seconds), 3600))
        self.poll_interval = max(0.01, min(float(poll_interval), 60.0))

    async def _heartbeat(self, job_id: str, user_id: int, lease_generation: int) -> None:
        while True:
            await asyncio.sleep(max(1.0, min(30.0, self.lease_seconds / 3)))
            try:
                async with self.session_factory() as session:
                    await AgentJobService(session).heartbeat(
                        job_id=job_id,
                        user_id=user_id,
                        lease_owner=self.worker_id,
                        lease_generation=lease_generation,
                        lease_seconds=self.lease_seconds,
                    )
                    job=await session.get(AgentJob,job_id)
                    if job is not None and job.kind=='agent_continuation':
                        owner=f'continuation:{job_id}:{lease_generation}'[:128]
                        expires=AgentRuntimeService._now()+timedelta(seconds=120)
                        changed=await session.execute(update(AgentRun).where(AgentRun.id==job.run_id,AgentRun.user_id==user_id,
                            AgentRun.lease_owner==owner,AgentRun.status=='running',AgentRun.cancel_requested_at.is_(None))
                            .values(lease_expires_at=expires))
                        if changed.rowcount==1:
                            await session.execute(update(AgentRunStep).where(AgentRunStep.run_id==job.run_id,
                                AgentRunStep.status=='running',AgentRunStep.lease_owner==owner).values(lease_expires_at=expires))
                            await session.commit()
            except Exception:
                return

    async def poll_once(self) -> bool:
        """Claim and process at most one job; return whether work was found."""
        heartbeat_task: asyncio.Task[None] | None = None
        async with self.session_factory() as session:
            service = AgentJobService(session)
            if await service.reconcile_completed_handoff_jobs():
                return True
            if "agent_continuation" in self.handlers:
                from .continuation_failure_recovery import recover_failed_continuations
                if await recover_failed_continuations(session, scan_cursor=self._failure_scan_cursor):
                    return True
                await AgentContinuationService(session).activate_ready(quarantine_invalid=True, scan_cursor=self._activation_scan_cursor)
            job = await service.claim_next_job(lease_owner=self.worker_id, lease_seconds=self.lease_seconds)
            if job is None:
                return False
            job_generation = int(job.lease_generation or 0)
            job_id, job_user_id, job_kind = job.id, job.user_id, job.kind
            handler = self.handlers.get(job_kind)
            if handler is None:
                await service.fail(
                    job_id=job_id,
                    user_id=job_user_id,
                    lease_owner=self.worker_id,
                    lease_generation=job_generation,
                    error_type='UnknownJobKind',
                    detail=f'no handler registered for {job_kind}',
                    retryable=False,
                )
                return True
            heartbeat_task = asyncio.create_task(self._heartbeat(job_id, job_user_id, job_generation))
            try:
                result = await handler(job, session)
                if job_kind == "agent_continuation" and result.get("continuation_failed"):
                    persisted = await service.get_job(job_id=job_id, user_id=job_user_id)
                    expected_status = result.get("continuation_job_status")
                    if expected_status not in {"queued", "failed", "dead_letter"} or persisted.status != expected_status:
                        raise RuntimeError("continuation failure returned without durable acknowledgement")
                    return True
                if job_kind == "agent_continuation" and (result.get("continuation_acknowledged") or result.get("continuation_deferred")):
                    persisted = await service.get_job(job_id=job_id, user_id=job_user_id)
                    expected_status = "succeeded" if result.get("continuation_acknowledged") else "queued"
                    if persisted.status != expected_status:
                        raise RuntimeError("continuation handler returned without durable acknowledgement")
                    return True
                await service.complete(
                    job_id=job_id,
                    user_id=job_user_id,
                    lease_owner=self.worker_id,
                    lease_generation=job_generation,
                    result=result,
                )
            except asyncio.CancelledError:
                try:
                    await service.fail(
                        job_id=job_id,
                        user_id=job_user_id,
                        lease_owner=self.worker_id,
                        lease_generation=job_generation,
                        error_type='WorkerCancelled',
                        detail='worker task cancelled',
                        retryable=True,
                    )
                except Exception:
                    pass
                raise
            except Exception as exc:
                await service.fail(
                    job_id=job_id,
                    user_id=job_user_id,
                    lease_owner=self.worker_id,
                    lease_generation=job_generation,
                    error_type=type(exc).__name__,
                    detail='durable worker handler failed',
                )
            finally:
                if heartbeat_task is not None:
                    heartbeat_task.cancel()
                    await asyncio.gather(heartbeat_task, return_exceptions=True)
            return True

    async def run_forever(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            worked = await self.poll_once()
            if not worked:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=self.poll_interval)
                except asyncio.TimeoutError:
                    pass
