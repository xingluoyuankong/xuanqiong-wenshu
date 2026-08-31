"""Initial durable Agent Run Command Worker.

The worker is intentionally small and provider-agnostic.  It only applies the
existing lifecycle commands (pause/resume/cancel); Provider execution remains
owned by the existing Agent execution worker.  The worker can therefore be
validated entirely with SQLite and does not claim to prove a Provider success
path.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..models.agent import AgentRun, AgentRunCommand
from ..services.agent_runtime import (
    AgentConflict,
    AgentRuntimeError,
    AgentRuntimeService,
)
from .command_recovery import (
    COMMAND_APPLYING,
    COMMAND_APPLIED,
    COMMAND_REJECTED,
    CommandLeaseConflict,
    AgentCommandRecovery,
)
from .jobs import AgentJobService
from .runner import cancel_visible_response, is_visible_response_active

CommandApplier = Callable[[AgentRunCommand, AsyncSession, str], Awaitable[AgentRunCommand]]


def _is_event_sequence_conflict(exc: IntegrityError) -> bool:
    message = str(getattr(exc, "orig", exc)).lower()
    return "agent_events" in message and ("sequence" in message or "uq_agent_event" in message)


async def apply_claimed_command(
    command: AgentRunCommand,
    session: AsyncSession,
    *,
    lease_owner: str,
    max_retries: int = 3,
) -> AgentRunCommand:
    """Apply one command already moved to ``applying`` by this worker.

    The Run mutation, lifecycle event, terminal command state and applied event
    are committed together.  Rejections are expected business outcomes and
    use ``rejected``; unexpected exceptions are left to ``CommandWorker`` so it
    can persist ``failed`` after rolling back partial ORM changes.
    """
    owner = str(lease_owner or "").strip()[:128]
    if not owner:
        raise CommandLeaseConflict("lease_owner is required")
    command_id = str(command.id)
    claimed_generation = int(command.lease_generation or 0)
    last_conflict: IntegrityError | None = None

    for _attempt in range(max(1, int(max_retries))):
        stored = (
            await session.execute(
                select(AgentRunCommand).where(
                    AgentRunCommand.id == command_id,
                    AgentRunCommand.status == COMMAND_APPLYING,
                    AgentRunCommand.lease_owner == owner,
                    AgentRunCommand.lease_generation == claimed_generation,
                )
            )
        ).scalar_one_or_none()
        if stored is None:
            raise CommandLeaseConflict("command is not owned by this worker")
        run = (
            await session.execute(
                select(AgentRun).where(
                    AgentRun.id == stored.run_id,
                    AgentRun.user_id == stored.user_id,
                )
            )
        ).scalar_one_or_none()
        if run is None:
            raise AgentConflict("agent run not found for command")
        runtime = AgentRuntimeService(session)
        try:
            expected = stored.expected_state_version
            if expected is not None and int(run.state_version or 0) != int(expected):
                stored.status = COMMAND_REJECTED
                stored.error_type = "AgentStateVersionConflict"
                stored.error_detail = (
                    f"expected state_version={expected}, current={run.state_version}"
                )[:1000]
                stored.applied_at = runtime._now()
                stored.finished_at = stored.applied_at
                await runtime._append_event_uncommitted(
                    run_id=run.id,
                    user_id=stored.user_id,
                    event_type="run_command_rejected",
                    summary="Agent 运行控制请求的状态版本已过期",
                    data={
                        "command_id": stored.id,
                        "command_type": stored.command_type,
                        "phase": "run_control",
                        "error_type": stored.error_type,
                    },
                )
            else:
                if stored.command_type == "pause":
                    run = await runtime._apply_pause_run(
                        run_id=run.id,
                        user_id=stored.user_id,
                        commit=False,
                    )
                elif stored.command_type == "resume":
                    run = await runtime._apply_resume_run(
                        run_id=run.id,
                        user_id=stored.user_id,
                        commit=False,
                    )
                elif stored.command_type == "cancel":
                    run = await runtime._apply_cancel_run(
                        run_id=run.id,
                        user_id=stored.user_id,
                        reason=stored.reason,
                        commit=False,
                    )
                else:
                    raise AgentConflict("unsupported Agent Run command")
                stored.status = COMMAND_APPLIED
                stored.applied_at = runtime._now()
                stored.finished_at = stored.applied_at
                stored.error_type = None
                stored.error_detail = None
                stored.result_json = {
                    "run_status": run.status,
                    "state_version": int(run.state_version or 0),
                }
                await runtime._append_event_uncommitted(
                    run_id=run.id,
                    user_id=stored.user_id,
                    event_type="run_command_applied",
                    summary="Agent 运行控制请求已应用",
                    data={
                        "command_id": stored.id,
                        "command_type": stored.command_type,
                        "phase": run.current_phase or "run_control",
                        "status": stored.status,
                    },
                )
            stored.lease_owner = None
            stored.lease_expires_at = None
            await session.commit()
            refreshed = (
                await session.execute(
                    select(AgentRunCommand).where(AgentRunCommand.id == command_id)
                )
            ).scalar_one()
            return refreshed
        except AgentRuntimeError:
            # Lifecycle precondition failures are normal command rejections.
            # Roll back first so a partially populated identity map cannot leak
            # a mutation into the rejection transaction.
            await session.rollback()
            stored = (
                await session.execute(
                    select(AgentRunCommand).where(
                        AgentRunCommand.id == command_id,
                        AgentRunCommand.status == COMMAND_APPLYING,
                        AgentRunCommand.lease_owner == owner,
                    )
                )
            ).scalar_one_or_none()
            if stored is None:
                raise CommandLeaseConflict("command is not owned after rejection rollback")
            stored.status = COMMAND_REJECTED
            stored.error_type = "AgentCommandRejected"
            stored.error_detail = "lifecycle precondition rejected the command"
            stored.applied_at = runtime._now()
            stored.finished_at = stored.applied_at
            await runtime._append_event_uncommitted(
                run_id=stored.run_id,
                user_id=stored.user_id,
                event_type="run_command_rejected",
                summary="Agent 运行控制请求未在当前状态应用",
                data={
                    "command_id": stored.id,
                    "command_type": stored.command_type,
                    "phase": "run_control",
                    "error_type": stored.error_type,
                },
            )
            stored.lease_owner = None
            stored.lease_expires_at = None
            await session.commit()
            return stored
        except IntegrityError as exc:
            await session.rollback()
            if not _is_event_sequence_conflict(exc):
                raise
            last_conflict = exc
            continue
    raise AgentConflict("unable to allocate a unique Agent command event sequence") from last_conflict


async def _apply_cancel_side_effects(command: AgentRunCommand, session: AsyncSession) -> None:
    """Fan out a queued cancel command to durable Jobs and visible response."""
    runtime = AgentRuntimeService(session)
    try:
        await AgentJobService(session).request_cancel_for_run(
            run_id=command.run_id,
            user_id=command.user_id,
            reason=command.reason or "user_requested",
        )
    except Exception as exc:
        try:
            await runtime.append_event(
                run_id=command.run_id,
                user_id=command.user_id,
                event_type="cancellation_side_effect_failed",
                summary="Command Worker 取消 Job 时发生异常",
                data={"error_type": type(exc).__name__, "phase": "cancelling"},
            )
        except Exception:
            pass
    cancel_visible_response(command.run_id)
    await runtime.finalize_cancellation(
        run_id=command.run_id,
        user_id=command.user_id,
        visible_response_active=is_visible_response_active(command.run_id),
    )


class CommandWorker:
    """Poll, lease and apply durable Run commands."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        worker_id: str,
        lease_seconds: int = 120,
        poll_interval: float = 0.25,
        applier: CommandApplier | None = None,
    ) -> None:
        owner = str(worker_id or "").strip()[:128]
        if not owner:
            raise ValueError("worker_id is required")
        self.session_factory = session_factory
        self.worker_id = owner
        self.lease_seconds = max(1, min(int(lease_seconds), 3600))
        self.poll_interval = max(0.01, min(float(poll_interval), 60.0))
        self.applier = applier or self._default_applier

    async def _default_applier(
        self,
        command: AgentRunCommand,
        session: AsyncSession,
        worker_id: str,
    ) -> AgentRunCommand:
        return await apply_claimed_command(
            command,
            session,
            lease_owner=worker_id,
        )

    async def _heartbeat(self, command_id: str, lease_generation: int) -> None:
        while True:
            await asyncio.sleep(max(1.0, min(30.0, self.lease_seconds / 3)))
            try:
                async with self.session_factory() as session:
                    await AgentCommandRecovery(
                        session,
                        lease_seconds=self.lease_seconds,
                    ).heartbeat(
                        command_id=command_id,
                        lease_owner=self.worker_id,
                        lease_generation=lease_generation,
                    )
            except Exception:
                return

    async def poll_once(self) -> bool:
        """Recover expired leases, then claim and process at most one command."""
        heartbeat_task: asyncio.Task[None] | None = None
        async with self.session_factory() as session:
            recovery = AgentCommandRecovery(session, lease_seconds=self.lease_seconds)
            await recovery.recover_stale_commands()
            command = await recovery.claim_next(lease_owner=self.worker_id)
            if command is None:
                return False
            command_id = str(command.id)
            command_generation = int(command.lease_generation or 0)
            heartbeat_task = asyncio.create_task(
                self._heartbeat(command_id, command_generation)
            )
            try:
                applied_command = await self.applier(command, session, self.worker_id)
                if applied_command.command_type == "cancel" and applied_command.status == COMMAND_APPLIED:
                    await _apply_cancel_side_effects(applied_command, session)
            except asyncio.CancelledError:
                await session.rollback()
                try:
                    await recovery.fail(
                        command_id=command_id,
                        lease_owner=self.worker_id,
                        error_type="WorkerCancelled",
                        detail="command worker task cancelled",
                        lease_generation=command_generation,
                    )
                except Exception:
                    pass
                raise
            except Exception as exc:
                await session.rollback()
                try:
                    await recovery.fail(
                        command_id=command_id,
                        lease_owner=self.worker_id,
                        error_type=type(exc).__name__,
                        detail=str(exc),
                        lease_generation=command_generation,
                    )
                except Exception:
                    # If the lease was lost, recovery will safely return the
                    # applying row to requested on the next worker pass.
                    pass
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


# Naming parallel to the existing AgentWorker is useful to callers migrating
# from the generic worker entry point.
AgentCommandWorker = CommandWorker


__all__ = [
    "CommandWorker",
    "AgentCommandWorker",
    "CommandApplier",
    "apply_claimed_command",
]
