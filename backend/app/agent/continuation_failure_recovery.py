"""Evidence-based recovery of stage-eight continuation failure/ACK orphans.

Only expired running Jobs with one unambiguous failed frozen-plan read are
settled. No Run is revived, no tool is invoked, and incomplete evidence is left
untouched. A detached proof is revalidated under locks before a lease-fenced CAS.
The entrypoint owns its transaction and expects a clean worker polling session.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import logging
from typing import Any

from sqlalchemy import String, cast, inspect, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.agent import AgentApproval, AgentJob, AgentRun, AgentRunStep, AgentSession
from ..models.agent_catalog import AgentCapabilityDefinition, AgentCapabilityExecution
from ..services.agent_execution_service import _digest
from .continuation import AgentContinuationService, ContinuationConflict, validate_intent_payload
from .continuation_plan import ContinuationPlanError
from .approval_snapshot_integrity import ApprovalSnapshotIntegrityError
from .run_context_integrity import RunContextIntegrityError
from ..services.agent_context_service import AgentContextIntegrityError
from ..services.agent_plan_service import AgentPlanIntegrityError
from .retry_policy import classify_error
from .continuation_scan import ContinuationScanCursor, scan_candidates


logger = logging.getLogger(__name__)


class ContinuationRecoveryRejected(ValueError):
    """Incomplete, stale or ambiguous evidence; never a reason to execute work."""


@dataclass(frozen=True)
class _RecoveryProof:
    job_id: str
    run_id: str
    user_id: int
    lease_owner: str
    lease_generation: int
    lease_expires_at: datetime
    error_type: str
    terminal_status: str
    fingerprint: str
    run_state_version: int
    run_lease_owner: str | None
    run_lease_expires_at: datetime | None
    step_id: str
    step_status: str
    step_lease_generation: int
    step_error_type: str
    fact_id: str
    fact_status: str
    fact_lease_generation: int | None
    fact_error_type: str
    sqlite_job_lease_text: str | None
    sqlite_run_lease_text: str | None


def _recovery_scan_limit(limit: int) -> int:
    if type(limit) is not int or limit <= 0:
        return 0
    return min(max(limit * 4, limit), 200)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def _instant(value: Any) -> datetime:
    if not isinstance(value, datetime):
        raise ContinuationRecoveryRejected('timestamp')
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _time(value: Any) -> datetime:
    # Runtime lifecycle chronology crosses rows with different storage precision.
    # Compare those relations at the persisted second boundary only.
    return _instant(value).replace(microsecond=0)


def _stored_at_or_after(previous: Any, current: Any) -> bool:
    return _time(previous) <= _time(current)


def _require(condition: bool, field: str) -> None:
    if not condition:
        raise ContinuationRecoveryRejected(field)


def _same(actual: Any, expected: Any, field: str) -> None:
    # JSON comparison is intentionally strict about bool/int and list shape.
    _require(_canonical(actual) == _canonical(expected), field)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'),
                      allow_nan=False, default=lambda obj: obj.isoformat() if isinstance(obj, datetime) else dict(obj))


def _lease_equals(session, column, value, sqlite_text):
    # Preserve SQLite's actual stored representation in the immutable proof.
    # Do not normalize with strftime (which would discard microseconds).
    if session.get_bind().dialect.name == 'sqlite':
        return cast(column, String) == sqlite_text if sqlite_text is not None else column.is_(None)
    return column == value


def _row(row: Any) -> dict:
    return {column.key: getattr(row, column.key) for column in inspect(row).mapper.column_attrs}


def _scope(row: Any, run: AgentRun) -> None:
    for field in ('run_id', 'user_id', 'project_id', 'correlation_id', 'transaction_id'):
        if hasattr(type(row), field):
            _same(getattr(row, field), run.id if field == 'run_id' else getattr(run, field), f'scope.{field}')


async def _get(session, model, key):
    if not isinstance(key, str) or not key.strip():
        raise ContinuationRecoveryRejected('row locator')
    return (await session.execute(select(model).where(model.id == key)
            .execution_options(populate_existing=True).with_for_update())).scalar_one_or_none()


async def _failure_proof(session: AsyncSession, job: AgentJob, run: AgentRun) -> _RecoveryProof:
    timestamp = _now()
    _require(run.status == 'failed' and run.current_phase == 'continuation_error', 'run.state')
    _require(run.cancel_requested_at is None and run.finished_at is not None, 'run.terminal')
    _require(run.lease_owner is None or (run.lease_expires_at is not None and _instant(run.lease_expires_at) <= timestamp), 'run.live_lease')
    _require(type(run.user_id) is int and run.user_id > 0, 'run.user_id')
    for field in ('id', 'session_id', 'correlation_id', 'transaction_id'):
        _require(isinstance(getattr(run, field), str) and bool(getattr(run, field).strip()), f'run.{field}')
    _require(job.kind == 'agent_continuation' and job.status == 'running', 'job.state')
    _require(isinstance(job.lease_owner, str) and bool(job.lease_owner.strip()), 'job.owner')
    _require(type(job.lease_generation) is int and job.lease_generation > 0, 'job.generation')
    _require(job.lease_expires_at is not None and _instant(job.lease_expires_at) <= timestamp, 'job.expiry')
    _require(job.cancel_requested_at is None and job.finished_at is None, 'job.cancel_or_finished')
    _require(job.attempt_count > 0 and job.max_attempts > 0 and job.started_at is not None, 'job.attempt')
    _scope(job, run)
    payload = validate_intent_payload(job.payload_json)
    _require(payload.get('outcome') == 'executed', 'payload.outcome')
    chat = await _get(session, AgentSession, run.session_id)
    _require(chat is not None and chat.user_id == run.user_id and chat.project_id == run.project_id, 'session.scope')
    approval = await _get(session, AgentApproval, payload.get('approval_id'))
    _require(approval is not None and approval.status == 'executed', 'approval.state')
    _scope(approval, run)
    service = AgentContinuationService(session)
    loaded = await service.load(run, approval, source_job_id=payload['source_job_id'])
    _require(loaded is not None, 'frozen_plan')
    _same(payload, {**loaded.plan.to_payload(), 'return_phase': payload['return_phase']}, 'payload.frozen_plan')
    _require(loaded.source.status == 'succeeded' and loaded.source.cancel_requested_at is None, 'source.ack')
    _same(job.idempotency_key, f'continuation:v1:{loaded.revision.id}:{approval.id}:executed', 'job.idempotency')

    # Failed steps erase their lease_owner. A second still-running continuation
    # makes attribution ambiguous, so do not infer an owner from timestamps alone.
    running = list((await session.execute(select(AgentJob).where(
        AgentJob.run_id == run.id, AgentJob.kind == 'agent_continuation', AgentJob.status == 'running'
    ).with_for_update().execution_options(populate_existing=True))).scalars())
    _require([item.id for item in running] == [job.id], 'ambiguous.running_jobs')
    steps = list((await session.execute(select(AgentRunStep).where(AgentRunStep.run_id == run.id)
        .order_by(AgentRunStep.step_order).with_for_update().execution_options(populate_existing=True))).scalars())
    failed = [step for step in steps if step.status == 'failed']
    _require(len(failed) == 1, 'ambiguous.failed_steps')
    step = failed[0]
    _scope(step, run)
    frozen = next((s for s in loaded.plan.steps if s.order == step.step_order), None)
    _require(frozen is not None and frozen.risk_level in {'read', 'suggest'}, 'failed_read.plan')
    _same(step.tool_name, frozen.tool_name, 'step.tool')
    _same(step.idempotency_key, f'{run.id}:step:{frozen.order}:{frozen.tool_name}', 'step.idempotency')
    _require(isinstance(step.input_json, dict), 'step.input')
    expected_input = {'goal': loaded.revision.plan_json['goal'], 'tool_arguments': dict(frozen.arguments)}
    _same(step.input_json.get('goal'), expected_input['goal'], 'step.goal')
    _same(step.input_json.get('tool_arguments'), expected_input['tool_arguments'], 'step.arguments')
    _require(step.lease_owner is None and step.lease_expires_at is None, 'step.lease')
    _require(type(step.lease_generation) is int and step.lease_generation > 0 and step.attempt_count > 0, 'step.generation')
    _require(isinstance(step.error_type, str) and 0 < len(step.error_type) <= 160, 'step.error_type')
    _require(_stored_at_or_after(job.started_at, step.started_at) and _stored_at_or_after(step.started_at, step.finished_at) and _stored_at_or_after(step.finished_at, run.finished_at), 'step.time')
    by_order = {s.step_order:s for s in steps}
    for order in frozen.depends_on:
        dependency = by_order.get(order)
        _require(dependency is not None and dependency.status == 'completed', 'step.dependencies')
        _scope(dependency, run)

    facts = list((await session.execute(select(AgentCapabilityExecution).where(
        AgentCapabilityExecution.run_id == run.id, AgentCapabilityExecution.step_id == step.id
    ).with_for_update().execution_options(populate_existing=True))).scalars())
    _require(len(facts) == 1, 'read_fact.count')
    fact = facts[0]
    _scope(fact, run)  # fact has no user/project columns; the scoped step/snapshot bind them
    _require(fact.status == 'failed', 'fact.status')
    _same(fact.snapshot_id, loaded.capability_snapshot.id, 'fact.snapshot')
    _same(fact.capability_id, frozen.tool_name, 'fact.capability')
    _same(fact.idempotency_key, f'{run.id}:capability:{step.id}', 'fact.idempotency')
    _same(fact.error_type, step.error_type, 'fact.error')
    _same(fact.lease_generation, step.lease_generation, 'fact.generation')
    _require(fact.attempt > 0 and fact.attempt <= step.attempt_count, 'fact.attempt')
    _same(fact.input_json, expected_input, 'fact.input')
    _same(fact.input_digest, _digest(expected_input), 'fact.input_digest')
    _require(_stored_at_or_after(step.started_at, fact.started_at) and _stored_at_or_after(fact.started_at, fact.finished_at) and _stored_at_or_after(fact.finished_at, run.finished_at), 'fact.time')
    _require(job.error_type is None or job.error_type == fact.error_type, 'job.error_type')
    capability = await _get(session, AgentCapabilityDefinition, fact.capability_definition_id)
    _require(capability is not None, 'fact.definition')
    _same(capability.catalog_release_id, loaded.capability_snapshot.catalog_release_id, 'definition.catalog')
    _same(capability.capability_id, frozen.tool_name, 'definition.capability')
    _same(fact.provider_release_id, capability.provider_release_id, 'fact.provider')
    _same(fact.resolved_version, capability.version, 'fact.version')

    retry = classify_error(fact.error_type, attempt_count=job.attempt_count, max_attempts=job.max_attempts)
    _require(not retry.retryable or job.attempt_count >= job.max_attempts, 'failure.retry_budget')
    material = [_row(r) for r in (job, run, chat, approval, loaded.source,
        loaded.revision, loaded.context_snapshot, loaded.capability_snapshot, capability, fact)]
    material.extend(_row(s) for s in steps)
    job_lease_text = run_lease_text = None
    if session.get_bind().dialect.name == 'sqlite':
        job_lease_text = (await session.execute(select(cast(AgentJob.lease_expires_at, String)).where(AgentJob.id == job.id))).scalar_one()
        run_lease_text = (await session.execute(select(cast(AgentRun.lease_expires_at, String)).where(AgentRun.id == run.id))).scalar_one()
    return _RecoveryProof(job.id, run.id, run.user_id, job.lease_owner, job.lease_generation,
        job.lease_expires_at, fact.error_type, 'dead_letter' if retry.retryable else 'failed',
        sha256(_canonical(material).encode('utf-8')).hexdigest(),
        run.state_version, run.lease_owner, run.lease_expires_at,
        step.id, step.status, step.lease_generation, step.error_type,
        fact.id, fact.status, fact.lease_generation, fact.error_type,
        job_lease_text, run_lease_text)


async def _cas_update_job(session: AsyncSession, *, proof: _RecoveryProof) -> AgentJob | None:
    timestamp = _now()
    changed = await session.execute(update(AgentJob).where(
        AgentJob.id == proof.job_id, AgentJob.run_id == proof.run_id, AgentJob.user_id == proof.user_id,
        AgentJob.kind == 'agent_continuation', AgentJob.status == 'running',
        AgentJob.lease_owner == proof.lease_owner, AgentJob.lease_generation == proof.lease_generation,
        _lease_equals(session, AgentJob.lease_expires_at, proof.lease_expires_at, proof.sqlite_job_lease_text), AgentJob.lease_expires_at <= timestamp,
        AgentJob.cancel_requested_at.is_(None), AgentJob.finished_at.is_(None),
        AgentJob.run_id.in_(select(AgentRun.id).where(
            AgentRun.id == proof.run_id, AgentRun.user_id == proof.user_id,
            AgentRun.status == 'failed', AgentRun.current_phase == 'continuation_error',
            AgentRun.state_version == proof.run_state_version,
            AgentRun.lease_owner == proof.run_lease_owner,
            _lease_equals(session, AgentRun.lease_expires_at, proof.run_lease_expires_at, proof.sqlite_run_lease_text),
            AgentRun.cancel_requested_at.is_(None),
        )),
        AgentJob.run_id.in_(select(AgentRunStep.run_id).where(
            AgentRunStep.id == proof.step_id, AgentRunStep.run_id == proof.run_id,
            AgentRunStep.status == proof.step_status,
            AgentRunStep.lease_generation == proof.step_lease_generation,
            AgentRunStep.error_type == proof.step_error_type,
            AgentRunStep.lease_owner.is_(None), AgentRunStep.lease_expires_at.is_(None),
        )),
        AgentJob.run_id.in_(select(AgentCapabilityExecution.run_id).where(
            AgentCapabilityExecution.id == proof.fact_id,
            AgentCapabilityExecution.run_id == proof.run_id,
            AgentCapabilityExecution.status == proof.fact_status,
            AgentCapabilityExecution.lease_generation == proof.fact_lease_generation,
            AgentCapabilityExecution.error_type == proof.fact_error_type,
        )),
    ).values(status=proof.terminal_status, error_type=proof.error_type,
        error_detail='Recovered expired continuation from verified failed read proof',
        finished_at=timestamp, lease_owner=None, lease_expires_at=None)
        .execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        await session.rollback()
        return None
    await session.commit()
    return await session.get(AgentJob, proof.job_id, populate_existing=True)


async def _cas_mark_failed(session: AsyncSession, *, proof: _RecoveryProof) -> AgentJob | None:
    # Acquire the Run fence first. The no-op update is also an optimistic CAS
    # against a changed terminal state/version or a newly acquired live lease.
    changed = await session.execute(update(AgentRun).where(
        AgentRun.id == proof.run_id, AgentRun.user_id == proof.user_id,
        AgentRun.status == 'failed', AgentRun.current_phase == 'continuation_error',
        AgentRun.state_version == proof.run_state_version,
        AgentRun.lease_owner == proof.run_lease_owner,
        _lease_equals(session, AgentRun.lease_expires_at, proof.run_lease_expires_at, proof.sqlite_run_lease_text),
        AgentRun.cancel_requested_at.is_(None),
    ).values(state_version=AgentRun.state_version, updated_at=AgentRun.updated_at)
        .execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        await session.rollback()
        return None
    run = await _get(session, AgentRun, proof.run_id)
    job = await _get(session, AgentJob, proof.job_id)
    if job is None or run is None:
        await session.rollback()
        return None
    current = await _failure_proof(session, job, run)
    if current != proof:
        await session.rollback()
        return None
    # The proof passed above is immutable. The helper receives that original
    # proof, never a refreshed owner/generation, so a late claimant cannot be
    # rebound into the recovery transaction.
    return await _cas_update_job(session, proof=proof)


_PROOF_ERRORS = (ContinuationRecoveryRejected, ContinuationConflict, ContinuationPlanError,
    ApprovalSnapshotIntegrityError, RunContextIntegrityError, AgentContextIntegrityError,
    AgentPlanIntegrityError, AttributeError, KeyError, TypeError, ValueError)


async def recover_failed_continuations(session: AsyncSession, limit: int = 50, *, scan_cursor: ContinuationScanCursor | None = None) -> list[AgentJob]:
    """Return durably settled Jobs; leave unproven/live/cancelled rows untouched.

    Owns its transactions, for a clean worker polling session only. Infrastructure
    failures propagate after rollback rather than being misclassified as poison.
    """
    if type(limit) is not int or limit <= 0:
        return []
    if session.new or session.dirty or session.deleted:
        raise ValueError('recovery requires a clean polling session')
    # The live worker supplies a rotating cursor so unproven rows do not
    # permanently monopolize a bounded maintenance page.
    scan_limit = _recovery_scan_limit(limit)
    cursor_before = scan_cursor.last_id if scan_cursor is not None else None
    query = select(AgentJob.id, AgentJob.run_id).join(
        AgentRun, AgentRun.id == AgentJob.run_id).where(
        AgentJob.kind == 'agent_continuation', AgentJob.status == 'running',
        AgentJob.lease_expires_at.is_not(None), AgentJob.lease_expires_at <= _now(),
        AgentJob.cancel_requested_at.is_(None), AgentRun.status == 'failed',
        AgentRun.current_phase == 'continuation_error', AgentRun.cancel_requested_at.is_(None)
    ).order_by(AgentJob.created_at, AgentJob.id)
    candidates = await scan_candidates(session, query, limit=scan_limit, cursor=scan_cursor)
    await session.rollback()
    recovered_ids = []
    last_examined = None
    for job_id, run_id in candidates:
        if len(recovered_ids) >= limit:
            break
        last_examined = job_id
        try:
            run = await _get(session, AgentRun, run_id)
            job = await _get(session, AgentJob, job_id)
            if run is None or job is None:
                await session.rollback()
                continue
            proof = await _failure_proof(session, job, run)
            # End the observation transaction before claiming the proof. No ORM
            # object survives as authoritative evidence across this boundary.
            await session.rollback()
            settled = await _cas_mark_failed(session, proof=proof)
            if settled is not None:
                recovered_ids.append(settled.id)
                # A successful CAS has committed; never include persisted input
                # or error_detail in operator logs.
                logger.info('continuation_failure_recovered', extra={
                    'job_id': settled.id, 'run_id': proof.run_id,
                    'job_status': settled.status, 'lease_generation': proof.lease_generation,
                })
            await session.rollback()
        except _PROOF_ERRORS as exc:
            await session.rollback()
            logger.debug('continuation_recovery_skipped', extra={
                'job_id': job_id, 'run_id': run_id, 'reason_code': type(exc).__name__,
            })
        except BaseException:
            await session.rollback()
            if scan_cursor is not None:
                scan_cursor.last_id = cursor_before
            raise
    if scan_cursor is not None:
        scan_cursor.last_id = last_examined if last_examined is not None else None
    if not recovered_ids:
        return []
    rows = list((await session.execute(select(AgentJob).where(AgentJob.id.in_(recovered_ids))
        .execution_options(populate_existing=True))).scalars())
    by_id = {row.id:row for row in rows}
    return [by_id[key] for key in recovered_ids]
