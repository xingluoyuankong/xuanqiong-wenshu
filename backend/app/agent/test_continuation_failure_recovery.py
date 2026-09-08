"""Stage-nine orphan continuation recovery contract tests."""
from datetime import timedelta

import pytest
from sqlalchemy import select, update

from app.agent.continuation import AgentContinuationService, now
from app.agent.jobs import AgentJobService
from app.agent.test_continuation_worker import pending_chain, approve_write
from app.agent.worker import handle_agent_continuation_job
from app.models.agent import AgentJob, AgentRun, AgentRunStep
from app.models.agent_catalog import AgentCapabilityExecution


_HISTORICAL_SEED = None


async def create_orphan(tmp_path, monkeypatch):
    """Construct the stage-eight persisted state, not the new atomic failure path.

    Cache only a closed SQLite backup and immutable artifact bytes; every test
    gets its own database and sessions. The original seed uses real runtime and
    execution-fact services and intentionally omits JobService.fail.
    """
    global _HISTORICAL_SEED
    import sqlite3
    from types import SimpleNamespace
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from app.services.agent_execution_service import AgentExecutionService
    from app.services.agent_runtime import AgentRuntimeService
    if _HISTORICAL_SEED is not None:
        data, metadata, artifacts = _HISTORICAL_SEED
        (tmp_path / 'worker.sqlite').write_bytes(data)
        (tmp_path / 'artifacts').mkdir()
        for name, content in artifacts.items():
            (tmp_path / 'artifacts' / name).write_bytes(content)
        monkeypatch.setattr('app.agent.write_executor._ARTIFACT_ROOT', tmp_path / 'artifacts')
        engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'worker.sqlite').as_posix()}")
        f = SimpleNamespace(engine=engine, factory=async_sessionmaker(engine, expire_on_commit=False), **metadata)
        return f, f.job_id
    f = await pending_chain(tmp_path, monkeypatch)
    await approve_write(f)
    try:
        async with f.factory() as session:
            assert await AgentContinuationService(session).activate_ready() == 1
            job = await AgentJobService(session).claim_next_job(lease_owner='orphan-worker', lease_seconds=120)
            job_id = job.id
            runtime = AgentRuntimeService(session)
            owner = f'continuation:{job.id}:{job.lease_generation}'[:128]
            run = await runtime.claim_run(run_id=f.run_id, user_id=f.user_id, lease_owner=owner)
            steps = await runtime.list_steps(run_id=f.run_id, user_id=f.user_id)
            step = await runtime.claim_step(step_id=steps[1].id, user_id=f.user_id, lease_owner=owner)
            facts = AgentExecutionService(session)
            snapshot = await facts.get_run_snapshot(f.run_id)
            fact = await facts.begin_read_execution(run=run, step=step, snapshot=snapshot,
                capability_id=step.tool_name, arguments={'goal':run.context_json['goal'], 'tool_arguments':{}},
                lease_generation=step.lease_generation, idempotency_key=f'{run.id}:capability:{step.id}')
            await runtime.fail_step(step_id=step.id, user_id=f.user_id, error_type='RuntimeError',
                lease_owner=owner, lease_generation=step.lease_generation, commit=False)
            await facts.fail_read_execution(execution=fact, lease_generation=step.lease_generation,
                error=RuntimeError('orphan read failure'), commit=False)
            await runtime.update_run(run_id=f.run_id, user_id=f.user_id,
                status='failed', phase='continuation_error', commit=False)
            await session.commit()
            await runtime.release_run(run_id=f.run_id, user_id=f.user_id,
                lease_owner=owner, lease_generation=run.lease_generation)
            orphan = await session.get(AgentJob, job_id, populate_existing=True)
            assert orphan.status == 'running'
            orphan.lease_expires_at = now() - timedelta(seconds=1)
            await session.commit()
        backup = tmp_path / 'stage8-seed.sqlite'
        with sqlite3.connect(tmp_path / 'worker.sqlite') as source, sqlite3.connect(backup) as target:
            source.backup(target)
        metadata = {key:getattr(f,key) for key in ('run_id','user_id','source_id','approval_id')}
        metadata['job_id'] = job_id
        _HISTORICAL_SEED = (backup.read_bytes(), metadata,
            {p.name:p.read_bytes() for p in (tmp_path/'artifacts').iterdir() if p.is_file()})
        return f, job_id
    except BaseException:
        await f.engine.dispose()
        raise


@pytest.mark.asyncio
async def test_recover_expired_failed_continuation_with_exact_failure_proof(tmp_path, monkeypatch):
    from app.agent.continuation_failure_recovery import recover_failed_continuations
    f, job_id = await create_orphan(tmp_path, monkeypatch)
    try:
        async with f.factory() as session:
            recovered = await recover_failed_continuations(session)
            assert [job.id for job in recovered] == [job_id]
            job = await session.get(AgentJob, job_id)
            assert job.status == 'failed'
            assert job.error_type == 'RuntimeError'
            assert job.lease_owner is None and job.lease_expires_at is None
            assert job.finished_at is not None
    finally:
        await f.engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation', ['active_lease', 'cancelled', 'run_scope', 'missing_fact', 'error_mismatch'])
async def test_recovery_refuses_ambiguous_or_live_evidence(tmp_path, monkeypatch, mutation):
    from app.agent.continuation_failure_recovery import recover_failed_continuations
    f, job_id = await create_orphan(tmp_path, monkeypatch)
    try:
        async with f.factory() as session:
            job = await session.get(AgentJob, job_id)
            run = await session.get(AgentRun, f.run_id)
            step = (await session.execute(select(AgentRunStep).where(
                AgentRunStep.run_id == f.run_id, AgentRunStep.step_order == 2))).scalar_one()
            fact = (await session.execute(select(AgentCapabilityExecution).where(
                AgentCapabilityExecution.step_id == step.id))).scalar_one()
            if mutation == 'active_lease':
                job.lease_expires_at = now() + timedelta(seconds=120)
            elif mutation == 'cancelled':
                job.cancel_requested_at = now()
            elif mutation == 'run_scope':
                job.project_id = 'other-project'
            elif mutation == 'missing_fact':
                fact.status = 'started'
            else:
                fact.error_type = 'DifferentError'
            await session.commit()
            assert await recover_failed_continuations(session) == []
            job = await session.get(AgentJob, job_id, populate_existing=True)
            assert job.status == 'running'
    finally:
        await f.engine.dispose()


@pytest.mark.asyncio
async def test_recovery_cas_loses_to_lease_generation_interleaving(tmp_path, monkeypatch):
    from app.agent import continuation_failure_recovery as module
    from app.agent.continuation_failure_recovery import recover_failed_continuations
    f, job_id = await create_orphan(tmp_path, monkeypatch)
    try:
        original = module._cas_mark_failed
        raced = []
        async def interleave(session, *, proof):
            job_id = proof.job_id
            async with f.factory() as competitor:
                await competitor.execute(update(AgentJob).where(AgentJob.id == job_id).values(
                    lease_generation=AgentJob.lease_generation + 1,
                    lease_owner='replacement-worker',
                    lease_expires_at=now() + timedelta(seconds=120)))
                await competitor.commit()
            raced.append(True)
            return await original(session, proof=proof)
        monkeypatch.setattr(module, '_cas_mark_failed', interleave)
        async with f.factory() as session:
            assert await recover_failed_continuations(session) == []
            job = await session.get(AgentJob, job_id, populate_existing=True)
            assert raced == [True]
            assert job.status == 'running'
            assert job.lease_owner == 'replacement-worker'
            assert job.lease_generation == 2
    finally:
        await f.engine.dispose()


@pytest.mark.asyncio
async def test_recovery_limit_is_deterministic(tmp_path, monkeypatch):
    from app.agent.continuation_failure_recovery import recover_failed_continuations
    f, job_id = await create_orphan(tmp_path, monkeypatch)
    try:
        async with f.factory() as session:
            assert await recover_failed_continuations(session, limit=0) == []
            assert (await session.get(AgentJob, job_id)).status == 'running'
    finally:
        await f.engine.dispose()

async def evidence_rows(session, f, job_id):
    from app.models.agent import AgentApproval
    from app.models.agent_context import ContextSnapshot
    from app.models.agent_plan import PlanRevision
    from app.models.agent_catalog import AgentRunCapabilitySnapshot, AgentCapabilityDefinition
    run = await session.get(AgentRun, f.run_id)
    job = await session.get(AgentJob, job_id)
    step = (await session.execute(select(AgentRunStep).where(
        AgentRunStep.run_id == f.run_id, AgentRunStep.step_order == 2))).scalar_one()
    fact = (await session.execute(select(AgentCapabilityExecution).where(
        AgentCapabilityExecution.step_id == step.id))).scalar_one()
    return {'job':job, 'run':run, 'step':step, 'fact':fact,
        'source':await session.get(AgentJob,f.source_id),
        'approval':await session.get(AgentApproval,f.approval_id),
        'plan':await session.get(PlanRevision,run.context_json['relational_plan_revision_id']),
        'context':await session.get(ContextSnapshot,run.context_json['relational_context_snapshot_id']),
        'snapshot':await session.get(AgentRunCapabilitySnapshot,fact.snapshot_id),
        'definition':await session.get(AgentCapabilityDefinition,fact.capability_definition_id)}


@pytest.mark.asyncio
@pytest.mark.parametrize('entity,field,value', [
    ('job','user_id',999), ('job','project_id','other'), ('job','correlation_id','other'),
    ('job','transaction_id','other'), ('job','lease_owner',''), ('job','lease_generation',0),
    ('job','finished_at','now'), ('job','error_type','OtherError'), ('job','payload_json',[]),
    ('job','idempotency_key','wrong'), ('job','lease_expires_at',None),
    ('run','status','completed'), ('run','current_phase','other'), ('run','cancel_requested_at','now'),
    ('run','finished_at',None), ('run','context_json',[]),
    ('step','user_id',999), ('step','transaction_id','other'), ('step','correlation_id','other'),
    ('step','tool_name','project.context'), ('step','status','completed'), ('step','input_json',{}),
    ('step','idempotency_key','wrong'), ('step','lease_owner','other'), ('step','lease_generation',0),
    ('step','error_type',None), ('step','finished_at',None),
    ('fact','transaction_id','other'), ('fact','correlation_id','other'), ('fact','capability_id','other'),
    ('fact','input_json',{}), ('fact','input_digest','0'*64), ('fact','snapshot_id','missing'),
    ('fact','idempotency_key','wrong'), ('fact','lease_generation',999), ('fact','finished_at',None),
    ('fact','error_type','DifferentError'), ('fact','provider_release_id','wrong'),
    ('fact','resolved_version','other'), ('fact','capability_definition_id',None),
    ('plan','digest','0'*64), ('plan','user_id',999), ('plan','transaction_id','other'),
    ('context','digest','0'*64), ('context','project_id','other'),
    ('snapshot','digest','0'*64), ('snapshot','transaction_id','other'),
    ('approval','status','execution_failed'), ('approval','transaction_id','other'),
    ('source','status','running'), ('source','cancel_requested_at','now'),
])
async def test_incomplete_or_mismatched_proof_is_unchanged(tmp_path,monkeypatch,entity,field,value):
    from app.agent.continuation_failure_recovery import recover_failed_continuations
    f,job_id=await create_orphan(tmp_path,monkeypatch)
    try:
        async with f.factory() as session:
            rows=await evidence_rows(session,f,job_id)
            row=rows[entity]
            replacement=now() if value=='now' else value
            await session.execute(update(type(row)).where(type(row).id==row.id)
                .values(**{field:replacement}).execution_options(synchronize_session=False))
            await session.commit()
        async with f.factory() as session:
            assert await recover_failed_continuations(session)==[]
            assert (await session.get(AgentJob,job_id)).status=='running'
    finally: await f.engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('entity,field,value', [
    ('job','lease_owner','new-owner'), ('job','lease_generation',2),
    ('job','lease_expires_at','past'), ('job','cancel_requested_at','now'),
    ('job','transaction_id','other'), ('job','payload_json',{}),
    ('run','status','running'), ('run','current_phase','other'),
    ('run','cancel_requested_at','now'), ('run','lease_generation',999),
    ('step','status','completed'), ('step','lease_generation',999), ('step','error_type','other'),
    ('fact','status','completed'), ('fact','lease_generation',999), ('fact','error_type','other'),
    ('fact','input_digest','0'*64), ('plan','digest','0'*64),
])
async def test_cas_never_rebinds_to_changed_proof(tmp_path,monkeypatch,entity,field,value):
    from app.agent import continuation_failure_recovery as module
    f,job_id=await create_orphan(tmp_path,monkeypatch)
    try:
        # Real cross-session interleaving between the detached first proof and
        # Run-lock acquisition. No lock is held by the observer at this boundary.
        original=module._cas_mark_failed
        calls=[]
        async def interleave(session,*,proof):
            async with f.factory() as other:
                rows=await evidence_rows(other,f,job_id)
                row=rows[entity]
                replacement=now() if value=='now' else now()-timedelta(seconds=60) if value=='past' else value
                await other.execute(update(type(row)).where(type(row).id==row.id)
                    .values(**{field:replacement}).execution_options(synchronize_session=False))
                await other.commit()
            calls.append(proof)
            return await original(session,proof=proof)
        monkeypatch.setattr(module,'_cas_mark_failed',interleave)
        async with f.factory() as session:
            assert await module.recover_failed_continuations(session)==[]
            assert len(calls)==1
            assert (await session.get(AgentJob,job_id)).status=='running'
    finally: await f.engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('exhausted',[False,True])
async def test_transient_history_is_dead_letter_only_if_budget_exhausted(tmp_path,monkeypatch,exhausted):
    from app.agent.continuation_failure_recovery import recover_failed_continuations
    f,job_id=await create_orphan(tmp_path,monkeypatch)
    try:
        async with f.factory() as session:
            rows=await evidence_rows(session,f,job_id)
            rows['step'].error_type=rows['fact'].error_type='ProviderTimeout'
            rows['job'].max_attempts=1 if exhausted else 3
            await session.commit()
            recovered=await recover_failed_continuations(session)
            assert len(recovered)==int(exhausted)
            job=await session.get(AgentJob,job_id,populate_existing=True)
            assert job.status==('dead_letter' if exhausted else 'running')
            assert job.attempt_count==1
            assert (await session.get(AgentRun,f.run_id)).status=='failed'
    finally: await f.engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('entity',['job','run'])
async def test_subsecond_live_lease_is_not_rounded_into_expiry(tmp_path,monkeypatch,entity):
    from app.agent import continuation_failure_recovery as module
    f,job_id=await create_orphan(tmp_path,monkeypatch)
    try:
        moment=now()
        monkeypatch.setattr(module,'_now',lambda:moment)
        async with f.factory() as session:
            rows=await evidence_rows(session,f,job_id)
            rows[entity].lease_owner='live-owner'
            rows[entity].lease_expires_at=moment+timedelta(microseconds=500000)
            await session.commit()
            assert await module.recover_failed_continuations(session)==[]
            assert (await session.get(AgentJob,job_id)).status=='running'
    finally: await f.engine.dispose()


@pytest.mark.asyncio
async def test_recovery_is_idempotent_and_only_changes_job(tmp_path,monkeypatch):
    from app.agent.continuation_failure_recovery import recover_failed_continuations,_row
    f,job_id=await create_orphan(tmp_path,monkeypatch)
    try:
        async with f.factory() as session:
            rows=await evidence_rows(session,f,job_id)
            before={key:_row(row) for key,row in rows.items() if key!='job'}
            assert [r.id for r in await recover_failed_continuations(session)]==[job_id]
            assert await recover_failed_continuations(session)==[]
        async with f.factory() as session:
            rows=await evidence_rows(session,f,job_id)
            assert {key:_row(row) for key,row in rows.items() if key!='job'}==before
            assert rows['job'].attempt_count==1
    finally: await f.engine.dispose()

@pytest.mark.asyncio
@pytest.mark.parametrize('entity,field,value', [
    ('job','lease_owner','replacement-worker'),
    ('job','lease_generation',2),
    ('run','lease_owner','replacement-run-owner'),
    ('run','state_version',999),
    ('step','status','completed'),
    ('step','lease_generation',999),
    ('step','error_type','OtherError'),
    ('fact','status','completed'),
    ('fact','lease_generation',999),
    ('fact','error_type','OtherError'),
])
async def test_final_cas_rejects_mutation_after_proof(tmp_path, monkeypatch, entity, field, value):
    from app.agent import continuation_failure_recovery as module
    f, job_id = await create_orphan(tmp_path, monkeypatch)
    try:
        original = module._cas_update_job
        entered = []
        async def interleave(session, *, proof):
            # Run write lock is already held here. Exercise final SQL predicates
            # with an in-transaction fault, not a blocked second SQLite writer.
            rows = await evidence_rows(session, f, job_id)
            row = rows[entity]
            await session.execute(update(type(row)).where(type(row).id == row.id)
                .values(**{field: value}).execution_options(synchronize_session=False))
            entered.append(proof)
            return await original(session, proof=proof)
        monkeypatch.setattr(module, '_cas_update_job', interleave)
        async with f.factory() as session:
            assert await module.recover_failed_continuations(session) == []
            assert len(entered) == 1
            job = await session.get(AgentJob, job_id, populate_existing=True)
            assert job.status == 'running'
    finally:
        await f.engine.dispose()


@pytest.mark.asyncio
async def test_recovery_accepts_historical_sqlite_second_precision_lease(tmp_path, monkeypatch):
    from app.agent.continuation_failure_recovery import recover_failed_continuations
    from sqlalchemy import text
    f, job_id = await create_orphan(tmp_path, monkeypatch)
    try:
        async with f.factory() as session:
            job = await session.get(AgentJob, job_id)
            run = await session.get(AgentRun, f.run_id)
            value = '2026-09-06 22:10:47'
            await session.execute(text('UPDATE agent_jobs SET lease_expires_at=:value WHERE id=:id'), {'value': value, 'id': job_id})
            await session.execute(text('UPDATE agent_runs SET lease_expires_at=:value WHERE id=:id'), {'value': value, 'id': f.run_id})
            await session.commit()
            recovered = await recover_failed_continuations(session)
            assert [item.id for item in recovered] == [job_id]
            assert (await session.get(AgentJob, job_id)).status == 'failed'
    finally:
        await f.engine.dispose()

@pytest.mark.parametrize('current,expected', [
    ('2026-09-06T22:43:17', True),
    ('2026-09-06T22:43:16', False),
])
def test_storage_second_precision_preserves_same_second_order(current, expected):
    from datetime import datetime
    from app.agent.continuation_failure_recovery import _stored_at_or_after
    step_started = datetime.fromisoformat('2026-09-06T22:43:17.498064')
    fact_started = datetime.fromisoformat(current)
    assert _stored_at_or_after(step_started, fact_started) is expected


def test_recovery_scan_window_is_wider_than_return_budget():
    from app.agent.continuation_failure_recovery import _recovery_scan_limit
    assert _recovery_scan_limit(1) == 4
    assert _recovery_scan_limit(50) == 200
    assert _recovery_scan_limit(200) == 200
    assert _recovery_scan_limit(0) == 0
