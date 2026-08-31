"""Durable capability-execution facts for the Agent read-tool execution path."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any

from ..models.agent import AgentApproval, AgentRun, AgentRunStep
from ..models.agent_catalog import AgentCapabilityExecution, AgentRunCapabilitySnapshot
from ..repositories.agent_catalog_repository import AgentCatalogRepository


class AgentCapabilityExecutionConflict(RuntimeError):
    """Raised when an execution tries to cross immutable Run/Snapshot boundaries."""


class AgentCapabilityHandlerIdentityMismatch(AgentCapabilityExecutionConflict):
    """Raised when the approved runtime handler differs from the frozen Catalog handler."""


def _digest(payload: dict[str, Any]) -> str:
    return sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


class AgentExecutionService:
    """Writes started/completed/failed facts for a resolved read capability call."""

    def __init__(self, session):
        self.session = session
        self.repository = AgentCatalogRepository(session)

    async def get_run_snapshot(self, run_id: str) -> AgentRunCapabilitySnapshot | None:
        return await self.repository.get_run_snapshot(run_id)

    async def begin_read_execution(
        self,
        *,
        run: AgentRun,
        step: AgentRunStep | None,
        snapshot: AgentRunCapabilitySnapshot,
        capability_id: str,
        arguments: dict[str, Any],
        lease_generation: int,
        idempotency_key: str,
    ) -> AgentCapabilityExecution:
        capability = await self.repository.get_capability_for_snapshot(
            snapshot=snapshot, capability_id=capability_id
        )
        if capability is None:
            raise AgentCapabilityExecutionConflict(
                "capability is absent from the Run relational resolver snapshot"
            )
        existing = await self.repository.get_execution_by_idempotency(
            run_id=run.id, idempotency_key=idempotency_key
        )
        if existing is not None:
            if existing.capability_id != capability_id or existing.step_id != (step.id if step is not None else None):
                raise AgentCapabilityExecutionConflict("execution idempotency key conflicts with a different capability")
            if existing.status in {"started", "completed"}:
                return existing
            existing.status = "started"
            existing.attempt += 1
            existing.error_type = None
            existing.error_detail = None
            existing.finished_at = None
            existing.duration_ms = None
            existing.input_json = dict(arguments)
            existing.input_digest = _digest(dict(arguments))
            existing.lease_generation = lease_generation
            await self.session.commit()
            await self.session.refresh(existing)
            return existing

        execution = await self.repository.create_execution(
            run=run,
            step=step,
            snapshot=snapshot,
            capability=capability,
            idempotency_key=idempotency_key,
            input_payload=dict(arguments),
            input_digest=_digest(dict(arguments)),
            lease_generation=lease_generation,
        )
        await self.session.commit()
        await self.session.refresh(execution)
        return execution

    async def begin_write_execution(
        self,
        *,
        run: AgentRun,
        approval: AgentApproval,
        step: AgentRunStep | None,
        arguments: dict[str, Any],
        lease_generation: int,
        actual_handler_identity: str,
    ) -> AgentCapabilityExecution | None:
        """Start one approved write fact and bind it to the frozen Run handler.

        Legacy Runs predate relational resolver snapshots and deliberately return
        ``None``; they retain the prior approval/write compatibility path. Every
        new relational Run must resolve both the capability and its exact handler.
        """
        snapshot = await self.get_run_snapshot(run.id)
        if snapshot is None:
            return None
        payload = {**dict(arguments), "_approval_id": approval.id}
        execution = await self.begin_read_execution(
            run=run,
            step=step,
            snapshot=snapshot,
            capability_id=approval.tool_name,
            arguments=payload,
            lease_generation=lease_generation,
            idempotency_key=f"{run.id}:capability:approval:{approval.id}",
        )
        capability = await self.repository.get_capability_for_snapshot(
            snapshot=snapshot, capability_id=approval.tool_name
        )
        expected = str(capability.handler_identity or "").strip() if capability is not None else ""
        actual = str(actual_handler_identity or "").strip()
        if expected and expected == actual:
            return execution
        mismatch = AgentCapabilityHandlerIdentityMismatch(
            "frozen capability handler identity does not match the runtime handler"
            f" (expected={expected or '<missing>'}, actual={actual or '<missing>'})"
        )
        await self.fail_read_execution(
            execution=execution,
            lease_generation=lease_generation,
            error=mismatch,
        )
        raise mismatch

    async def complete_write_execution(
        self,
        *,
        execution: AgentCapabilityExecution,
        lease_generation: int,
        output: dict[str, Any],
    ) -> AgentCapabilityExecution:
        return await self.complete_read_execution(
            execution=execution, lease_generation=lease_generation, output=output
        )

    async def fail_write_execution(
        self,
        *,
        execution: AgentCapabilityExecution,
        lease_generation: int,
        error: Exception,
    ) -> AgentCapabilityExecution:
        return await self.fail_read_execution(
            execution=execution, lease_generation=lease_generation, error=error
        )

    async def complete_read_execution(
        self,
        *,
        execution: AgentCapabilityExecution,
        lease_generation: int,
        output: dict[str, Any],
    ) -> AgentCapabilityExecution:
        if execution.lease_generation != lease_generation:
            raise AgentCapabilityExecutionConflict("execution lease generation is stale")
        if execution.status == "completed":
            return execution
        if execution.status != "started":
            raise AgentCapabilityExecutionConflict("only a started execution can complete")
        now = datetime.now(timezone.utc)
        execution.status = "completed"
        execution.output_json = dict(output)
        execution.output_digest = _digest(dict(output))
        execution.finished_at = now
        execution.duration_ms = max(0, int((now - execution.started_at.replace(tzinfo=timezone.utc) if execution.started_at.tzinfo is None else now - execution.started_at).total_seconds() * 1000))
        await self.session.commit()
        await self.session.refresh(execution)
        return execution

    async def fail_read_execution(
        self,
        *,
        execution: AgentCapabilityExecution,
        lease_generation: int,
        error: Exception,
    ) -> AgentCapabilityExecution:
        if execution.lease_generation != lease_generation:
            raise AgentCapabilityExecutionConflict("execution lease generation is stale")
        if execution.status == "completed":
            raise AgentCapabilityExecutionConflict("completed execution cannot be failed")
        now = datetime.now(timezone.utc)
        execution.status = "failed"
        execution.error_type = type(error).__name__
        execution.error_detail = str(error)[:1000]
        execution.finished_at = now
        execution.duration_ms = max(0, int((now - execution.started_at.replace(tzinfo=timezone.utc) if execution.started_at.tzinfo is None else now - execution.started_at).total_seconds() * 1000))
        await self.session.commit()
        await self.session.refresh(execution)
        return execution
