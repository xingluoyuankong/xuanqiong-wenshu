"""Durable recovery and lease helpers for Agent Run commands.

This module is the first Command Worker boundary.  It deliberately reuses the
existing ``AgentRunCommand`` row instead of introducing a second queue table:
``requested`` is available work, ``applying`` is an owned lease, and terminal
states are ``applied``, ``rejected`` and ``failed``.

The existing API/runtime still applies commands inline.  This module is
additive: callers may use it for commands that remain requested, while the
legacy runtime keeps its current request/apply behavior unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.agent import AgentRunCommand
from ..services.agent_runtime import AgentRuntimeService

COMMAND_REQUESTED = "requested"
COMMAND_APPLYING = "applying"
COMMAND_APPLIED = "applied"
COMMAND_REJECTED = "rejected"
COMMAND_FAILED = "failed"
COMMAND_STATUSES = {
    COMMAND_REQUESTED,
    COMMAND_APPLYING,
    COMMAND_APPLIED,
    COMMAND_REJECTED,
    COMMAND_FAILED,
}
COMMAND_TERMINAL_STATUSES = {
    COMMAND_APPLIED,
    COMMAND_REJECTED,
    COMMAND_FAILED,
}


class CommandRecoveryError(Exception):
    """Base error for command lease/recovery operations."""


class CommandLeaseConflict(CommandRecoveryError):
    """The command is not available to the requested worker."""


@dataclass(frozen=True)
class CommandLease:
    """The observable lease fence returned by a successful claim."""

    command_id: str
    owner: str
    expires_at: datetime
    attempt_count: int


def _now() -> datetime:
    # The project stores SQLite DateTime values as naive UTC values.  Match the
    # existing AgentRuntime/AgentJob helpers so comparisons remain consistent.
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def _owner(value: str) -> str:
    normalized = str(value or "").strip()[:128]
    if not normalized:
        raise CommandLeaseConflict("lease_owner is required")
    return normalized


def _lease_seconds(value: int) -> int:
    return max(1, min(int(value), 3600))


def _lease_expired_or_free(now: datetime):
    return or_(
        AgentRunCommand.lease_owner.is_(None),
        AgentRunCommand.lease_expires_at.is_(None),
        AgentRunCommand.lease_expires_at <= now,
    )


class AgentCommandRecovery:
    """Persistence operations for claiming and recovering Run commands.

    All transitions use conditional SQL updates.  The row returned by a
    preceding SELECT is only a scheduling hint; the UPDATE is the ownership
    fence that decides the winner when several workers poll concurrently.
    """

    def __init__(self, session: AsyncSession, *, lease_seconds: int = 120) -> None:
        self.session = session
        self.lease_seconds = _lease_seconds(lease_seconds)

    @staticmethod
    def now() -> datetime:
        return _now()

    async def get(self, *, command_id: str) -> AgentRunCommand | None:
        return (
            await self.session.execute(
                select(AgentRunCommand)
                .where(AgentRunCommand.id == command_id)
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()

    async def claim(
        self,
        *,
        command_id: str,
        lease_owner: str,
        lease_seconds: int | None = None,
    ) -> AgentRunCommand:
        """Claim one requested command and move it to ``applying``."""
        owner = _owner(lease_owner)
        now = _now()
        expires_at = now + timedelta(seconds=_lease_seconds(lease_seconds or self.lease_seconds))
        changed = await self.session.execute(
            update(AgentRunCommand)
            .execution_options(synchronize_session=False)
            .where(
                AgentRunCommand.id == command_id,
                AgentRunCommand.status == COMMAND_REQUESTED,
                _lease_expired_or_free(now),
            )
            .values(
                status=COMMAND_APPLYING,
                lease_owner=owner,
                lease_expires_at=expires_at,
                lease_generation=AgentRunCommand.lease_generation + 1,
                attempt_count=AgentRunCommand.attempt_count + 1,
                started_at=func.coalesce(AgentRunCommand.started_at, now),
                finished_at=None,
                applied_at=None,
                error_type=None,
                error_detail=None,
            )
        )
        if changed.rowcount != 1:
            raise CommandLeaseConflict("command is not claimable")
        await self.session.commit()
        command = await self.get(command_id=command_id)
        if command is None:
            raise CommandRecoveryError("claimed command disappeared")
        return command

    async def claim_next(
        self,
        *,
        lease_owner: str,
        lease_seconds: int | None = None,
    ) -> AgentRunCommand | None:
        """Atomically claim the oldest available requested command."""
        owner = _owner(lease_owner)
        now = _now()
        candidate = (
            await self.session.execute(
                select(AgentRunCommand.id)
                .where(
                    AgentRunCommand.status == COMMAND_REQUESTED,
                    _lease_expired_or_free(now),
                )
                .order_by(
                    AgentRunCommand.requested_at.asc(),
                    AgentRunCommand.id.asc(),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if candidate is None:
            return None
        try:
            return await self.claim(
                command_id=str(candidate),
                lease_owner=owner,
                lease_seconds=lease_seconds,
            )
        except CommandLeaseConflict:
            # Another worker won the conditional UPDATE.  A later poll will
            # retry without exposing a duplicate command execution.
            return None

    async def heartbeat(
        self,
        *,
        command_id: str,
        lease_owner: str,
        lease_seconds: int | None = None,
        lease_generation: int | None = None,
    ) -> AgentRunCommand:
        """Extend an active applying lease without changing command state."""
        owner = _owner(lease_owner)
        now = _now()
        expires_at = now + timedelta(seconds=_lease_seconds(lease_seconds or self.lease_seconds))
        changed = await self.session.execute(
            update(AgentRunCommand)
            .execution_options(synchronize_session=False)
            .where(
                AgentRunCommand.id == command_id,
                AgentRunCommand.status == COMMAND_APPLYING,
                AgentRunCommand.lease_owner == owner,
                or_(lease_generation is None, AgentRunCommand.lease_generation == int(lease_generation or 0)),
                AgentRunCommand.lease_expires_at.is_not(None),
                AgentRunCommand.lease_expires_at > now,
            )
            .values(lease_expires_at=expires_at)
        )
        if changed.rowcount != 1:
            raise CommandLeaseConflict("command lease is not active")
        await self.session.commit()
        command = await self.get(command_id=command_id)
        if command is None:
            raise CommandRecoveryError("heartbeated command disappeared")
        return command

    async def recover_stale_commands(
        self,
        *,
        now: datetime | None = None,
        limit: int = 100,
    ) -> list[AgentRunCommand]:
        """Return expired ``applying`` commands to ``requested``.

        Recovery preserves ``attempt_count`` and records a durable event in the
        same transaction as the lease release.  A replacement worker then
        claims the command as a new attempt.  Commands with a live lease are
        left untouched.
        """
        recovery_now = now or _now()
        candidates = list(
            (
                await self.session.execute(
                    select(AgentRunCommand)
                    .where(
                        AgentRunCommand.status == COMMAND_APPLYING,
                        AgentRunCommand.lease_expires_at.is_not(None),
                        AgentRunCommand.lease_expires_at <= recovery_now,
                    )
                    .order_by(
                        AgentRunCommand.lease_expires_at.asc(),
                        AgentRunCommand.requested_at.asc(),
                        AgentRunCommand.id.asc(),
                    )
                    .limit(max(1, min(int(limit), 200)))
                )
            )
            .scalars()
            .all()
        )
        recovered: list[AgentRunCommand] = []
        for candidate in candidates:
            # Recheck the lease in the UPDATE: a heartbeat or another
            # recovery pass may have won after the candidate SELECT.
            changed = await self.session.execute(
                update(AgentRunCommand)
                .execution_options(synchronize_session=False)
                .where(
                    AgentRunCommand.id == candidate.id,
                    AgentRunCommand.status == COMMAND_APPLYING,
                    AgentRunCommand.lease_expires_at.is_not(None),
                    AgentRunCommand.lease_expires_at <= recovery_now,
                )
                .values(
                    status=COMMAND_REQUESTED,
                    lease_owner=None,
                    lease_expires_at=None,
                    finished_at=None,
                    applied_at=None,
                    error_type="CommandLeaseExpired",
                    error_detail="command lease expired; returned to requested for retry",
                    result_json={
                        **dict(candidate.result_json or {}),
                        "recovered_at": recovery_now.isoformat(),
                        "recovery_count": int((candidate.result_json or {}).get("recovery_count", 0)) + 1,
                    },
                )
            )
            if changed.rowcount != 1:
                continue
            runtime = AgentRuntimeService(self.session)
            await runtime._append_event_uncommitted(
                run_id=candidate.run_id,
                user_id=candidate.user_id,
                event_type="command_recovered",
                summary="Agent 运行控制命令租约已过期，已返回队列等待恢复",
                data={
                    "command_id": candidate.id,
                    "command_type": candidate.command_type,
                    "phase": "command_recovery",
                },
            )
            await self.session.commit()
            refreshed = await self.get(command_id=candidate.id)
            if refreshed is not None:
                recovered.append(refreshed)
        return recovered

    async def fail(
        self,
        *,
        command_id: str,
        lease_owner: str,
        error_type: str,
        detail: str | None = None,
        lease_generation: int | None = None,
    ) -> AgentRunCommand:
        """Durably finish an owned command as ``failed``."""
        owner = _owner(lease_owner)
        now = _now()
        command = await self.get(command_id=command_id)
        if command is None:
            raise CommandRecoveryError("agent run command not found")
        changed = await self.session.execute(
            update(AgentRunCommand)
            .where(
                AgentRunCommand.id == command_id,
                AgentRunCommand.status == COMMAND_APPLYING,
                AgentRunCommand.lease_owner == owner,
                or_(lease_generation is None, AgentRunCommand.lease_generation == int(lease_generation or 0)),
            )
            .values(
                status=COMMAND_FAILED,
                lease_owner=None,
                lease_expires_at=None,
                finished_at=now,
                error_type=str(error_type)[:160],
                error_detail=str(detail or "")[:1000] or None,
            )
        )
        if changed.rowcount != 1:
            raise CommandLeaseConflict("command failure lost its lease")
        runtime = AgentRuntimeService(self.session)
        await runtime._append_event_uncommitted(
            run_id=command.run_id,
            user_id=command.user_id,
            event_type="run_command_failed",
            summary="Agent 运行控制命令执行失败",
            data={
                "command_id": command.id,
                "command_type": command.command_type,
                "phase": "run_control",
                "error_type": str(error_type)[:160],
            },
        )
        await self.session.commit()
        refreshed = await self.get(command_id=command_id)
        if refreshed is None:
            raise CommandRecoveryError("failed command disappeared")
        return refreshed

    async def release(self, *, command_id: str, lease_owner: str, lease_generation: int | None = None) -> AgentRunCommand:
        """Release an owned lease without consuming another attempt."""
        owner = _owner(lease_owner)
        changed = await self.session.execute(
            update(AgentRunCommand)
            .where(
                AgentRunCommand.id == command_id,
                AgentRunCommand.status == COMMAND_APPLYING,
                AgentRunCommand.lease_owner == owner,
                or_(lease_generation is None, AgentRunCommand.lease_generation == int(lease_generation or 0)),
            )
            .values(
                status=COMMAND_REQUESTED,
                lease_owner=None,
                lease_expires_at=None,
                finished_at=None,
                error_type=None,
                error_detail=None,
            )
        )
        if changed.rowcount != 1:
            raise CommandLeaseConflict("command lease cannot be released")
        await self.session.commit()
        command = await self.get(command_id=command_id)
        if command is None:
            raise CommandRecoveryError("released command disappeared")
        return command


# Short alias used by callers that do not need the longer service name.
CommandRecovery = AgentCommandRecovery


__all__ = [
    "AgentCommandRecovery",
    "CommandRecovery",
    "CommandLease",
    "CommandRecoveryError",
    "CommandLeaseConflict",
    "COMMAND_REQUESTED",
    "COMMAND_APPLYING",
    "COMMAND_APPLIED",
    "COMMAND_REJECTED",
    "COMMAND_FAILED",
    "COMMAND_STATUSES",
    "COMMAND_TERMINAL_STATUSES",
]

