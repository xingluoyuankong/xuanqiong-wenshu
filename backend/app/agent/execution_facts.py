from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.agent import AgentRun
from ..models.agent_catalog import AgentCapabilityExecution


class AgentExecutionFactNotFound(LookupError):
    """Raised when a Run is absent or belongs to another user."""


def _timestamp(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _safe_fact(row: AgentCapabilityExecution) -> dict[str, Any]:
    """Serialize execution metadata without copying either JSON payload."""
    return {
        'execution_id': row.execution_id,
        'run_id': row.run_id,
        'step_id': row.step_id,
        'action_id': f'step:{row.step_id}' if row.step_id else None,
        'result_ref': f'execution:{row.execution_id}',
        'tool_name': row.capability_id,
        'status': row.status,
        'attempt': row.attempt,
        'started_at': _timestamp(row.started_at),
        'finished_at': _timestamp(row.finished_at),
        'duration_ms': row.duration_ms,
        'error_type': row.error_type,
        'output_digest': row.output_digest,
        'has_output': bool(row.output_json) if isinstance(row.output_json, Mapping) else False,
    }


class AgentExecutionFactService:
    """Read-only, user-scoped projection of durable capability executions."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_for_run(
        self,
        *,
        run_id: str,
        user_id: int,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        run = (await self.session.execute(
            select(AgentRun).where(AgentRun.id == run_id, AgentRun.user_id == user_id),
        )).scalar_one_or_none()
        if run is None:
            raise AgentExecutionFactNotFound('Agent Run 不存在或不属于当前用户')

        bounded_limit = min(max(int(limit), 1), 500)
        rows = (await self.session.execute(
            select(AgentCapabilityExecution)
            .where(
                AgentCapabilityExecution.run_id == run.id,
                AgentCapabilityExecution.correlation_id == run.correlation_id,
            )
            .order_by(
                AgentCapabilityExecution.started_at.asc(),
                AgentCapabilityExecution.execution_id.asc(),
            )
            .limit(bounded_limit),
        )).scalars().all()
        return [_safe_fact(row) for row in rows]
