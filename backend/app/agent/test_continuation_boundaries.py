"""Continuation lifecycle boundaries exercised against the real durable worker."""
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from app.agent.continuation import AgentContinuationService, now
from app.agent.continuation_worker import handle_agent_continuation_job
from app.agent.jobs import AgentJobService
from app.agent.test_continuation_worker import pending_chain, approve_write
from app.agent.worker import AgentWorker
from app.models.agent import AgentJob, AgentRun, AgentRunStep
from app.models.agent_catalog import AgentCapabilityExecution
from app.services.agent_runtime import AgentRuntimeService


async def intent(session, f):
    return (await session.execute(select(AgentJob).where(
        AgentJob.run_id == f.run_id, AgentJob.kind == 'agent_continuation'
    ))).scalar_one()


@pytest.mark.asyncio
@pytest.mark.parametrize('poison', [[], ['bad'], {'approval_id': []}, {'approval_id': {}}, {'approval_id': 'missing'}])
async def test_activation_poison_does_not_block_healthy_intent(tmp_path, monkeypatch, poison):
    f = await pending_chain(tmp_path, monkeypatch)
    try:
        await approve_write(f)
        async with f.factory() as session:
            good = await intent(session, f)
            bad = AgentJob(id=str(uuid4()), run_id=f.run_id, user_id=f.user_id,
                project_id=good.project_id, correlation_id=good.correlation_id,
                transaction_id=good.transaction_id, kind='agent_continuation',
                status='blocked', idempotency_key='poison', payload_json=poison,
                result_json={}, available_at=now(), created_at=now()-timedelta(days=1))
            session.add(bad)
            bad_id, good_id = bad.id, good.id
            await session.commit()
        async with f.factory() as session:
            assert await AgentContinuationService(session).activate_ready(quarantine_invalid=True) == 1
            assert (await session.get(AgentJob, bad_id)).status == 'failed'
            assert (await session.get(AgentJob, good_id)).status == 'queued'
        worker = AgentWorker(f.factory, worker_id='healthy', handlers={'agent_continuation': handle_agent_continuation_job})
        assert await worker.poll_once()
        assert f.calls == ['planner', 'writer', 'statistics']
    finally:
        await f.engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('invalid_marker', ['generation', 'job', 'revision', 'orders', 'cancelled_source'])
async def test_source_ack_recovery_requires_exact_handoff(tmp_path, monkeypatch, invalid_marker):
    f = await pending_chain(tmp_path, monkeypatch)
    try:
        async with f.factory() as session:
            source = await session.get(AgentJob, f.source_id)
            source.status = 'running'
            source.lease_owner = 'expired-source'
            source.lease_expires_at = now()-timedelta(seconds=1)
            run = await session.get(AgentRun, f.run_id)
            context = dict(run.context_json)
            marker = dict(context['approval_wait_handoff'])
            if invalid_marker == 'generation': marker['lease_generation'] += 1
            elif invalid_marker == 'job': marker['job_id'] = 'other-job'
            elif invalid_marker == 'revision': marker['plan_revision_id'] = 'other-plan'
            elif invalid_marker == 'orders': marker['step_orders'] = [{'bad': 1}]
            else: source.cancel_requested_at = now()
            context['approval_wait_handoff'] = marker
            run.context_json = context
            await session.commit()
        await approve_write(f)
        async with f.factory() as session:
            assert await AgentContinuationService(session).activate_ready(quarantine_invalid=True) == 0
            assert (await session.get(AgentJob, f.source_id)).status == 'running'
        assert f.calls == ['planner', 'writer']
    finally:
        await f.engine.dispose()


@pytest.mark.asyncio
async def test_exhausted_transient_read_failure_converges_dead_letter(tmp_path, monkeypatch):
    f = await pending_chain(tmp_path, monkeypatch)
    try:
        await approve_write(f)
        async with f.factory() as session:
            job = await intent(session, f)
            job.max_attempts = 1
            await session.commit()
        class ProviderTimeout(Exception): pass
        async def fail(**kwargs): raise ProviderTimeout('exhausted fixture')
        monkeypatch.setattr('app.agent.continuation_worker.execute_read_tool', fail)
        worker = AgentWorker(f.factory, worker_id='last-attempt', handlers={'agent_continuation': handle_agent_continuation_job})
        assert await worker.poll_once()
        async with f.factory() as session:
            job = await intent(session, f)
            steps = await AgentRuntimeService(session).list_steps(run_id=f.run_id, user_id=f.user_id)
            fact = (await session.execute(select(AgentCapabilityExecution).where(
                AgentCapabilityExecution.step_id == steps[1].id))).scalar_one()
            run = await session.get(AgentRun, f.run_id)
            assert (job.status, steps[1].status, fact.status, run.status) == ('dead_letter', 'failed', 'failed', 'failed')
            assert steps[0].status == 'completed'
            assert run.lease_owner is None and steps[1].lease_owner is None
    finally:
        await f.engine.dispose()


@pytest.mark.asyncio
async def test_read_result_after_run_lease_takeover_is_not_committed(tmp_path, monkeypatch):
    f = await pending_chain(tmp_path, monkeypatch)
    try:
        await approve_write(f)
        async def steal(**kwargs):
            async with f.factory() as other:
                await other.execute(update(AgentRun).where(AgentRun.id == f.run_id).values(
                    lease_owner='replacement-owner', lease_generation=AgentRun.lease_generation+1,
                    lease_expires_at=now()+timedelta(seconds=120)))
                await other.commit()
            return {'stale_result': True}
        monkeypatch.setattr('app.agent.continuation_worker.execute_read_tool', steal)
        worker = AgentWorker(f.factory, worker_id='stale-reader', handlers={'agent_continuation': handle_agent_continuation_job})
        assert await worker.poll_once()
        async with f.factory() as session:
            steps = await AgentRuntimeService(session).list_steps(run_id=f.run_id, user_id=f.user_id)
            fact = (await session.execute(select(AgentCapabilityExecution).where(
                AgentCapabilityExecution.step_id == steps[1].id))).scalar_one()
            assert steps[1].status != 'completed'
            assert fact.status != 'completed'
            run = await session.get(AgentRun, f.run_id)
            assert run.lease_owner == 'replacement-owner' and run.status == 'running'
    finally:
        await f.engine.dispose()

@pytest.mark.asyncio
@pytest.mark.parametrize('field,value', [
    ('step_output', []), ('step_output', None), ('step_output', {'artifact_id': []}),
    ('execution_output', []), ('execution_output', None),
    ('source_id', []), ('return_phase', {}),
])
async def test_structural_proof_poison_is_quarantined_and_polling_continues(tmp_path, monkeypatch, field, value):
    f = await pending_chain(tmp_path, monkeypatch)
    try:
        await approve_write(f)
        async with f.factory() as session:
            job = await intent(session, f)
            bad_id = job.id
            steps = await AgentRuntimeService(session).list_steps(run_id=f.run_id, user_id=f.user_id)
            if field == 'step_output': steps[0].output_json = value
            elif field == 'execution_output':
                fact = (await session.execute(select(AgentCapabilityExecution).where(
                    AgentCapabilityExecution.step_id == steps[0].id))).scalar_one()
                fact.output_json = value
            else:
                key = 'source_job_id' if field == 'source_id' else field
                job.payload_json = {**job.payload_json, key: value}
            await session.commit()
            runtime = AgentRuntimeService(session)
            run = await session.get(AgentRun, f.run_id)
            healthy = await runtime.create_run(session_id=run.session_id, user_id=f.user_id,
                project_id=run.project_id, context={})
            good = await AgentJobService(session).create_job(run_id=healthy.id, user_id=f.user_id,
                project_id=healthy.project_id, kind='healthy_probe', idempotency_key='healthy', payload={})
            good_id = good.id
        calls = []
        async def healthy_handler(job, session):
            calls.append(job.id)
            return {'ok': True}
        worker = AgentWorker(f.factory, worker_id='poison-check', handlers={
            'agent_continuation': handle_agent_continuation_job, 'healthy_probe': healthy_handler})
        assert await worker.poll_once()
        assert calls == [good_id]
        async with f.factory() as session:
            bad = await session.get(AgentJob, bad_id)
            assert bad.status == 'failed' and bad.error_type == 'ContinuationConflict'
            assert (await session.get(AgentJob, good_id)).status == 'succeeded'
    finally:
        await f.engine.dispose()


@pytest.mark.asyncio
async def test_source_ack_recovery_cas_rejects_renewed_source(tmp_path, monkeypatch):
    f = await pending_chain(tmp_path, monkeypatch)
    try:
        async with f.factory() as session:
            source = await session.get(AgentJob, f.source_id)
            source.status = 'running'; source.lease_owner = 'expired'
            source.lease_expires_at = now()-timedelta(seconds=1)
            await session.commit()
        await approve_write(f)
        original = AgentContinuationService.verify_write_proof
        calls = []
        async def renew(self, *args, **kwargs):
            result = await original(self, *args, **kwargs)
            if not calls:
                calls.append(1)
                # Deterministic interleaving at the proof/CAS boundary; no time sleeps.
                await self.session.execute(update(AgentJob).where(AgentJob.id == f.source_id).values(
                    lease_generation=AgentJob.lease_generation+1, lease_owner='new-owner',
                    lease_expires_at=now()+timedelta(seconds=120)).execution_options(synchronize_session=False))
            return result
        monkeypatch.setattr(AgentContinuationService, 'verify_write_proof', renew)
        async with f.factory() as session:
            assert await AgentContinuationService(session).activate_ready() == 0
            assert (await session.get(AgentJob, f.source_id)).status == 'running'
        assert calls == [1]
    finally:
        await f.engine.dispose()

@pytest.mark.asyncio
async def test_bound_initial_source_survives_latest_execution_pointer_change(tmp_path, monkeypatch):
    f = await pending_chain(tmp_path, monkeypatch)
    try:
        async with f.factory() as session:
            run = await session.get(AgentRun, f.run_id)
            run.context_json = {**run.context_json, 'execution_job_id': 'later-execution-pointer'}
            await session.commit()
        await approve_write(f)
        async with f.factory() as session:
            job = await intent(session, f)
            assert job.payload_json['source_job_id'] == f.source_id
            assert await AgentContinuationService(session).activate_ready() == 1
        worker = AgentWorker(f.factory, worker_id='bound-source', handlers={'agent_continuation': handle_agent_continuation_job})
        assert await worker.poll_once()
        assert f.calls == ['planner', 'writer', 'statistics']
    finally:
        await f.engine.dispose()


@pytest.mark.parametrize('replan', [False, True])
def test_plan_source_binding_checks_checkpoint_not_latest_pointer(replan):
    from app.agent.test_continuation_plan import case
    from app.agent.continuation_plan import load_continuation_plan, ContinuationPlanError
    f = case(replan=replan)
    f['approval_step'].input_json['approval_source_job_id'] = f['source_job'].id
    f['run'].context_json['execution_job_id'] = 'latest-pointer'
    assert load_continuation_plan(**f).to_payload()['source_job_id'] == f['source_job'].id
    f['approval_step'].input_json['approval_source_job_id'] = 'wrong-source'
    with pytest.raises(ContinuationPlanError):
        load_continuation_plan(**f)


@pytest.mark.asyncio
@pytest.mark.parametrize('late_operation', ['fail', 'complete'])
async def test_stale_writer_session_cannot_overwrite_terminal_approval(tmp_path, monkeypatch, late_operation):
    from app.agent.continuation import ContinuationConflict
    from app.models.agent import AgentApproval, AgentArtifactRef
    f = await pending_chain(tmp_path, monkeypatch)
    stale_session = f.factory()
    stale = {}
    original = AgentContinuationService.complete_write
    async def snapshot_and_complete(self, **kwargs):
        for key, model in [('approval', AgentApproval), ('step', AgentRunStep),
                           ('execution', AgentCapabilityExecution), ('artifact', AgentArtifactRef)]:
            stale[key] = await stale_session.get(model, kwargs[key].id)
        stale['lease_owner'] = kwargs['lease_owner']
        stale['lease_generation'] = kwargs['lease_generation']
        stale['candidate_phase'] = kwargs['candidate_phase']
        await stale_session.commit()
        return await original(self, **kwargs)
    monkeypatch.setattr(AgentContinuationService, 'complete_write', snapshot_and_complete)
    try:
        await approve_write(f)
        assert stale['approval'].status == 'executing'
        service = AgentContinuationService(stale_session)
        with pytest.raises(ContinuationConflict):
            if late_operation == 'complete':
                await original(service, **stale)
            else:
                await service.fail_write(approval=stale['approval'], step=stale['step'],
                    execution=stale['execution'], error=RuntimeError('late failure'),
                    lease_owner=stale['lease_owner'], lease_generation=stale['lease_generation'])
        async with f.factory() as session:
            approval = await session.get(AgentApproval, f.approval_id)
            steps = await AgentRuntimeService(session).list_steps(run_id=f.run_id, user_id=f.user_id)
            facts = list((await session.execute(select(AgentCapabilityExecution).where(
                AgentCapabilityExecution.run_id == f.run_id))).scalars())
            assert approval.status == 'executed'
            assert steps[0].status == 'completed' and facts[0].status == 'completed'
            assert (await intent(session, f)).status == 'blocked'
    finally:
        await stale_session.close()
        await f.engine.dispose()

@pytest.mark.asyncio
async def test_parallel_executing_approval_keeps_step_lease_and_source(tmp_path, monkeypatch):
    from app.models.agent import AgentApproval
    from app.agent.write_executor import execute_approved_write, LLMService
    f = await pending_chain(tmp_path, monkeypatch, two_writes=True, parallel_writes=True)
    observed = []
    try:
        await approve_write(f)
        original_stream = LLMService.stream_visible_response
        async def interleave(self, **kwargs):
            worker = AgentWorker(f.factory, worker_id='parallel-approval', handlers={
                'agent_continuation': handle_agent_continuation_job})
            assert await worker.poll_once()
            async with f.factory() as observer:
                steps = await AgentRuntimeService(observer).list_steps(run_id=f.run_id, user_id=f.user_id)
                observed.append((steps[2].status, steps[2].input_json['approval_source_job_id'], steps[2].lease_owner))
            async for chunk in original_stream(self, **kwargs):
                yield chunk
        monkeypatch.setattr(LLMService, 'stream_visible_response', interleave)
        async with f.factory() as session:
            approval = (await session.execute(select(AgentApproval).where(
                AgentApproval.run_id==f.run_id, AgentApproval.tool_name=='chapter.rewrite'))).scalar_one()
            await AgentRuntimeService(session).decide_approval(approval_id=approval.id, user_id=f.user_id, approved=True)
            await execute_approved_write(approval_id=approval.id, user_id=f.user_id, session=session)
        assert len(observed)==1
        assert observed[0][0]=='running' and observed[0][1]==f.source_id and observed[0][2]
        async with f.factory() as session:
            jobs=list((await session.execute(select(AgentJob).where(
                AgentJob.run_id==f.run_id, AgentJob.kind=='agent_continuation'))).scalars())
            assert len(jobs)==2 and {j.payload_json['source_job_id'] for j in jobs}=={f.source_id}
        worker = AgentWorker(f.factory, worker_id='finish-parallel', handlers={'agent_continuation': handle_agent_continuation_job})
        assert await worker.poll_once()
        async with f.factory() as session:
            steps=await AgentRuntimeService(session).list_steps(run_id=f.run_id,user_id=f.user_id)
            assert all(s.status=='completed' for s in steps)
        assert f.calls.count('writer')==2 and f.calls.count('planner')==1 and f.calls.count('statistics')==1
    finally:
        await f.engine.dispose()
