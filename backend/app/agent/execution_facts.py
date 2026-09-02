from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.agent import AgentRun
from ..models.novel import NovelProject
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

    @staticmethod
    def _provider_attempt_summary(context: Mapping[str, Any]) -> dict[str, Any]:
        """Project a legacy Provider-attempt snapshot without exposing its payload."""
        total = succeeded = failed = fallback = first_token = digests = selected = 0
        last_error_category: str | None = None
        latest_attempt_at: str | None = None
        latest_attempt_time: datetime | None = None
        latest_attempt_sequence = 0
        sequence = 0

        def parse_time(value: Any) -> datetime | None:
            raw = str(value or '').strip()
            if not raw:
                return None
            try:
                parsed = datetime.fromisoformat(raw.replace('Z', '+00:00'))
            except ValueError:
                return None
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)

        for key, snapshot in context.items():
            if not str(key).endswith('_provider_attempts') or not isinstance(snapshot, Mapping):
                continue
            attempts = snapshot.get('provider_attempts')
            if not isinstance(attempts, list):
                continue
            valid_selected = snapshot.get('selected_provider_attempt')
            if isinstance(valid_selected, int) and valid_selected >= 1:
                selected += 1
            for item in attempts[:64]:
                if not isinstance(item, Mapping):
                    continue
                sequence += 1
                total += 1
                status = str(item.get('status') or '').strip().lower()
                if status == 'succeeded':
                    succeeded += 1
                elif status == 'failed':
                    failed += 1
                    category = str(item.get('error_category') or '').strip()[:40]
                    if category:
                        # Preserve the established ledger order for this label; the
                        # attempt list is the durable retry chronology, while timestamps
                        # remain optional on legacy snapshots.
                        last_error_category = category
                if item.get('fallback_from_attempt') is not None:
                    fallback += 1
                first_token_at = str(item.get('first_token_at') or '').strip()[:64]
                if first_token_at:
                    first_token += 1
                if str(item.get('output_digest') or '').strip():
                    digests += 1
                attempt_at_raw = (
                    str(item.get('finished_at') or '').strip()
                    or str(item.get('first_token_at') or '').strip()
                    or str(item.get('started_at') or '').strip()
                )[:64]
                attempt_time = parse_time(attempt_at_raw)
                if attempt_at_raw and (
                    (attempt_time is not None and (latest_attempt_time is None or attempt_time >= latest_attempt_time))
                    or (attempt_time is None and latest_attempt_time is None and sequence >= latest_attempt_sequence)
                ):
                    latest_attempt_time = attempt_time or latest_attempt_time
                    latest_attempt_sequence = sequence
                    latest_attempt_at = attempt_at_raw
        return {
            'attempt_count': total,
            'succeeded_attempts': succeeded,
            'failed_attempts': failed,
            'fallback_attempts': fallback,
            'first_token_attempts': first_token,
            'digest_attempts': digests,
            'selected_attempts': selected,
            'last_error_category': last_error_category,
            'latest_attempt_at': latest_attempt_at,
        }

    async def provider_usage_summary(
        self,
        *,
        run_id: str,
        user_id: int,
    ) -> dict[str, Any]:
        """Aggregate persisted Provider attempt metadata for one user-owned Run."""
        run = (await self.session.execute(
            select(AgentRun).where(AgentRun.id == run_id, AgentRun.user_id == user_id),
        )).scalar_one_or_none()
        if run is None:
            raise AgentExecutionFactNotFound('Agent Run 不存在或不属于当前用户')

        context = run.context_json if isinstance(run.context_json, Mapping) else {}
        summary = self._provider_attempt_summary(context)
        return {
            'run_id': run.id,
            'total_attempts': summary['attempt_count'],
            'succeeded_attempts': summary['succeeded_attempts'],
            'failed_attempts': summary['failed_attempts'],
            'fallback_attempts': summary['fallback_attempts'],
            'first_token_attempts': summary['first_token_attempts'],
            'digest_attempts': summary['digest_attempts'],
            'selected_attempts': summary['selected_attempts'],
            'last_error_category': summary['last_error_category'],
            'latest_first_token_at': summary['latest_attempt_at'],
        }

    async def project_provider_usage_summary(
        self,
        *,
        project_id: str,
        user_id: int,
        since: datetime | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Aggregate a bounded, user-scoped window of Provider attempt facts for one project."""
        project = (await self.session.execute(
            select(NovelProject).where(NovelProject.id == project_id, NovelProject.user_id == user_id),
        )).scalar_one_or_none()
        if project is None:
            raise AgentExecutionFactNotFound('小说项目不存在或不属于当前用户')

        bounded_limit = min(max(int(limit), 1), 100)
        query = (
            select(AgentRun)
            .where(AgentRun.project_id == project.id, AgentRun.user_id == user_id)
            .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
            .limit(bounded_limit)
        )
        if since is not None:
            query = (
                select(AgentRun)
                .where(
                    AgentRun.project_id == project.id,
                    AgentRun.user_id == user_id,
                    AgentRun.created_at >= since,
                )
                .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
                .limit(bounded_limit)
            )
        runs = (await self.session.execute(query)).scalars().all()

        aggregate = {
            'project_id': project.id,
            'run_count': len(runs),
            'attempt_count': 0,
            'succeeded_attempts': 0,
            'failed_attempts': 0,
            'fallback_attempts': 0,
            'first_token_attempts': 0,
            'digest_attempts': 0,
            'selected_attempts': 0,
            'last_error_category': None,
            'latest_attempt_at': None,
            'runs': [],
        }
        for run in runs:
            context = run.context_json if isinstance(run.context_json, Mapping) else {}
            run_summary = self._provider_attempt_summary(context)
            for field in (
                'attempt_count',
                'succeeded_attempts',
                'failed_attempts',
                'fallback_attempts',
                'first_token_attempts',
                'digest_attempts',
                'selected_attempts',
            ):
                aggregate[field] += run_summary[field]
            if aggregate['last_error_category'] is None and run_summary['last_error_category']:
                aggregate['last_error_category'] = run_summary['last_error_category']
            attempt_at = run_summary['latest_attempt_at']
            if attempt_at and (aggregate['latest_attempt_at'] is None or attempt_at > aggregate['latest_attempt_at']):
                aggregate['latest_attempt_at'] = attempt_at
            aggregate['runs'].append({
                'run_id': run.id,
                'status': run.status,
                'attempt_count': run_summary['attempt_count'],
                'failed_attempts': run_summary['failed_attempts'],
                'fallback_attempts': run_summary['fallback_attempts'],
                'last_error_category': run_summary['last_error_category'],
                'latest_attempt_at': attempt_at,
            })
        return aggregate
