"""Real writer/worker regression: an executed approval must persist continuation intent."""
from functools import wraps
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.agent.executor import build_agent_plan
from app.agent.jobs import AgentJobService
from app.agent.registry import DEFAULT_TOOL_REGISTRY
from app.agent.schemas import AgentPlanRequest
from app.agent.test_worker import _factory
from app.agent.worker import AgentWorker,handle_agent_execution_job
from app.agent.write_executor import execute_approved_write
from app.models import User,NovelProject
from app.models.agent import AgentApproval,AgentJob
from app.services.agent_runtime import AgentRuntimeService


async def pending_chain(tmp_path,monkeypatch, *, two_writes=False, parallel_writes=False):
    engine,factory=await _factory(tmp_path)
    calls=[]
    tools=['chapter.generate','statistics.project'] + (['chapter.rewrite','project.context'] if two_writes else [])
    async with factory() as session:
        user=User(username='continue-owner',email='continue-owner@example.com',hashed_password='x',is_active=True)
        session.add(user);await session.flush()
        project=NovelProject(id='continue-project',user_id=user.id,title='Continuation')
        session.add(project);await session.flush()
        runtime=AgentRuntimeService(session)
        arguments={'chapter.generate':{'chapter_number':1}}
        if two_writes:
            from app.models import Chapter,ChapterVersion
            chapter=Chapter(project_id=project.id,chapter_number=1)
            session.add(chapter);await session.flush()
            version=ChapterVersion(chapter_id=chapter.id,content='原始版本。',status='selected')
            session.add(version);await session.flush();chapter.selected_version_id=version.id
            arguments['chapter.rewrite']={'chapter_number':1,'source_version_id':version.id,'instruction':'整理'}
        chat=await runtime.create_session(user_id=user.id,project_id=project.id)
        run=await runtime.create_run(session_id=chat.id,user_id=user.id,project_id=project.id,
            context={'goal':'生成候选后查看统计','context_refs':[], 'requested_tools':tools, 'tool_arguments':arguments})
        source=await AgentJobService(session).create_job(run_id=run.id,user_id=user.id,project_id=project.id,
            kind='agent_execution',idempotency_key=f'{run.id}:agent_execution',payload={'run_id':run.id,'phase':'planning'})
        run_id,user_id,source_id=run.id,user.id,source.id
    class Planner:
        async def plan(self,**kwargs):
            calls.append('planner')
            plan=build_agent_plan(AgentPlanRequest(goal=kwargs['goal'],project_id=kwargs['project_id'],tools=tools),user_id=kwargs['user_id'])
            for i in range(1,len(plan.steps)):
                plan.steps[i].depends_on=[] if parallel_writes and i==2 else [i]
            return SimpleNamespace(plan=plan,visible_summary='生成后统计',provider_called=False,fallback_reason=None)
    async def stream(self,**kwargs):
        calls.append('writer')
        ledger=kwargs['attempt_ledger'];attempt=ledger.begin(role='writer',provider_ref='fixture',model_ref='fixture')
        ledger.finish(attempt.attempt_id,output='候选正文。')
        yield '候选正文。'
    original=DEFAULT_TOOL_REGISTRY.get_handler('statistics.project')
    @wraps(original)
    async def statistics(**kwargs):
        calls.append('statistics');return await original(**kwargs)
    monkeypatch.setattr('app.agent.execution.AgentOrchestrator',lambda *args,**kwargs:Planner())
    monkeypatch.setattr('app.agent.execution.launch_visible_response',lambda **kwargs:None)
    monkeypatch.setattr('app.agent.write_executor.LLMService.stream_visible_response',stream)
    monkeypatch.setattr('app.agent.write_executor._ARTIFACT_ROOT',tmp_path/'artifacts')
    monkeypatch.setitem(DEFAULT_TOOL_REGISTRY._handlers,'statistics.project',statistics)
    worker=AgentWorker(factory,worker_id='initial',handlers={'agent_execution':handle_agent_execution_job})
    assert await worker.poll_once()
    async with factory() as session:
        approval=(await session.execute(select(AgentApproval).where(AgentApproval.run_id==run_id,AgentApproval.tool_name=='chapter.generate'))).scalar_one()
        assert approval.status=='pending'
        approval_id=approval.id
    return SimpleNamespace(engine=engine,factory=factory,run_id=run_id,user_id=user_id,source_id=source_id,approval_id=approval_id,calls=calls)


@pytest.mark.asyncio
async def test_real_writer_persists_intent_with_executed_approval(tmp_path,monkeypatch):
    f=await pending_chain(tmp_path,monkeypatch)
    try:
        async with f.factory() as session:
            runtime=AgentRuntimeService(session)
            await runtime.decide_approval(approval_id=f.approval_id,user_id=f.user_id,approved=True)
            artifact=await execute_approved_write(approval_id=f.approval_id,user_id=f.user_id,session=session)
            artifact_id=artifact.id
        async with f.factory() as session:
            approval=await AgentRuntimeService(session).get_approval(approval_id=f.approval_id,user_id=f.user_id)
            jobs=list((await session.execute(select(AgentJob).where(AgentJob.run_id==f.run_id,AgentJob.kind=='agent_continuation'))).scalars())
            assert len(jobs)==1
            assert approval.status=='executed'
            assert jobs[0].status=='blocked'
            assert jobs[0].payload_json['approval_id']==approval.id
            assert jobs[0].payload_json['source_job_id']==f.source_id
            assert jobs[0].payload_json['outcome']=='executed'
            assert '正文' not in str(jobs[0].payload_json)
            assert f.calls==['planner','writer']
    finally:await f.engine.dispose()

@pytest.mark.asyncio
async def test_fresh_worker_replays_original_plan_once_after_approved_write(tmp_path,monkeypatch):
    from app.agent.worker import handle_agent_continuation_job
    from app.models import ChapterVersion
    f=await pending_chain(tmp_path,monkeypatch)
    try:
        async with f.factory() as session:
            runtime=AgentRuntimeService(session)
            await runtime.decide_approval(approval_id=f.approval_id,user_id=f.user_id,approved=True)
            artifact=await execute_approved_write(approval_id=f.approval_id,user_id=f.user_id,session=session)
            artifact_id=artifact.id
        # New worker object and DB session: no in-memory continuation callback.
        worker=AgentWorker(f.factory,worker_id='replacement',handlers={'agent_continuation':handle_agent_continuation_job})
        assert await worker.poll_once()
        assert f.calls==['planner','writer','statistics']
        assert await worker.poll_once() is False
        async with f.factory() as session:
            runtime=AgentRuntimeService(session)
            run=await runtime.get_run(f.run_id,f.user_id)
            steps=await runtime.list_steps(run_id=f.run_id,user_id=f.user_id)
            assert [step.status for step in steps]==['completed','completed']
            assert [step.attempt_count for step in steps]==[1,1]
            assert run.status=='paused'
            assert run.current_phase in {'candidate_ready','quality_blocked'}
            assert list((await session.execute(select(ChapterVersion))).scalars())==[]
            jobs=await AgentJobService(session).list_jobs(user_id=f.user_id)
            assert len(jobs)==2 and all(job.status=='succeeded' for job in jobs)
            from app.models.agent import AgentArtifactRef
            artifacts=list((await session.execute(select(AgentArtifactRef).where(AgentArtifactRef.run_id==f.run_id))).scalars())
            assert len(artifacts)==1 and artifacts[0].id==artifact_id
            assert artifacts[0].metadata_json['status']=='candidate'
    finally:await f.engine.dispose()


@pytest.mark.asyncio
async def test_intent_failure_rolls_back_terminal_completion(tmp_path,monkeypatch):
    from app.agent.continuation import AgentContinuationService
    from app.models.agent_catalog import AgentCapabilityExecution
    f=await pending_chain(tmp_path,monkeypatch)
    try:
        async def fail_intent(self,*args,**kwargs):raise RuntimeError('injected intent persistence failure')
        monkeypatch.setattr(AgentContinuationService,'_persist_intent',fail_intent)
        async with f.factory() as session:
            await AgentRuntimeService(session).decide_approval(approval_id=f.approval_id,user_id=f.user_id,approved=True)
            with pytest.raises(Exception,match='candidate writer execution failed'):
                await execute_approved_write(approval_id=f.approval_id,user_id=f.user_id,session=session)
        async with f.factory() as session:
            runtime=AgentRuntimeService(session)
            approval=await runtime.get_approval(approval_id=f.approval_id,user_id=f.user_id)
            steps=await runtime.list_steps(run_id=f.run_id,user_id=f.user_id)
            facts=list((await session.execute(select(AgentCapabilityExecution).where(AgentCapabilityExecution.run_id==f.run_id))).scalars())
            jobs=await AgentJobService(session).list_jobs(user_id=f.user_id)
            assert approval.status!='executed'
            assert steps[0].status!='completed'
            assert all(fact.status!='completed' for fact in facts)
            assert not any(job.kind=='agent_continuation' for job in jobs)
    finally:await f.engine.dispose()

async def approve_write(f):
    async with f.factory() as session:
        await AgentRuntimeService(session).decide_approval(approval_id=f.approval_id,user_id=f.user_id,approved=True)
        await execute_approved_write(approval_id=f.approval_id,user_id=f.user_id,session=session)


@pytest.mark.asyncio
async def test_user_pause_blocks_continuation_until_explicit_resume(tmp_path,monkeypatch):
    from app.agent.worker import handle_agent_continuation_job
    f=await pending_chain(tmp_path,monkeypatch)
    try:
        await approve_write(f)
        async with f.factory() as session:
            await AgentRuntimeService(session).update_run(run_id=f.run_id,user_id=f.user_id,status='paused',phase='user_paused',pause_reason='user_requested',resume_target_status='running')
        worker=AgentWorker(f.factory,worker_id='paused-worker',handlers={'agent_continuation':handle_agent_continuation_job})
        assert await worker.poll_once() is False
        assert f.calls==['planner','writer']
        async with f.factory() as session:
            await AgentRuntimeService(session).update_run(run_id=f.run_id,user_id=f.user_id,status='running',phase='resumed')
        assert await worker.poll_once()
        assert f.calls==['planner','writer','statistics']
    finally:await f.engine.dispose()


@pytest.mark.asyncio
async def test_cancelled_run_never_activates_blocked_intent(tmp_path,monkeypatch):
    from app.agent.worker import handle_agent_continuation_job
    f=await pending_chain(tmp_path,monkeypatch)
    try:
        await approve_write(f)
        async with f.factory() as session:
            runtime=AgentRuntimeService(session)
            await runtime.update_run(run_id=f.run_id,user_id=f.user_id,status='cancelling',phase='cancel')
            await runtime.update_run(run_id=f.run_id,user_id=f.user_id,status='cancelled',phase='cancelled')
        worker=AgentWorker(f.factory,worker_id='cancel-worker',handlers={'agent_continuation':handle_agent_continuation_job})
        assert await worker.poll_once() is False
        async with f.factory() as session:
            jobs=await AgentJobService(session).list_jobs(user_id=f.user_id)
            assert next(job for job in jobs if job.kind=='agent_continuation').status=='cancelled'
            assert (await AgentRuntimeService(session).get_run(f.run_id,f.user_id)).status=='cancelled'
        assert f.calls==['planner','writer']
    finally:await f.engine.dispose()


@pytest.mark.asyncio
async def test_source_ack_and_live_run_lease_gate_continuation(tmp_path,monkeypatch):
    from datetime import timedelta
    from app.agent.continuation import now
    from app.agent.worker import handle_agent_continuation_job
    f=await pending_chain(tmp_path,monkeypatch)
    try:
        async with f.factory() as session:
            # Simulate terminal write racing the source's final worker ACK.
            source=await session.get(AgentJob,f.source_id)
            source.status='running';source.lease_owner='source';source.lease_expires_at=now()+timedelta(seconds=120)
            await session.commit()
        await approve_write(f)
        worker=AgentWorker(f.factory,worker_id='ack-worker',handlers={'agent_continuation':handle_agent_continuation_job})
        # Direct activation avoids claiming the deliberately live source fixture.
        from app.agent.continuation import AgentContinuationService
        async with f.factory() as session:
            assert await AgentContinuationService(session).activate_ready()==0
            source=await session.get(AgentJob,f.source_id);source.status='succeeded';source.lease_owner=None;source.lease_expires_at=None
            run=await AgentRuntimeService(session).get_run(f.run_id,f.user_id)
            run.lease_owner='source';run.lease_expires_at=now()+timedelta(seconds=120)
            await session.commit()
        async with f.factory() as session:
            assert await AgentContinuationService(session).activate_ready()==0
            run=await AgentRuntimeService(session).get_run(f.run_id,f.user_id);run.lease_owner=None;run.lease_expires_at=None;await session.commit()
        assert await worker.poll_once()
        assert f.calls==['planner','writer','statistics']
    finally:await f.engine.dispose()


@pytest.mark.asyncio
async def test_modified_frozen_intent_is_rejected_before_read(tmp_path,monkeypatch):
    from app.agent.continuation import AgentContinuationService,ContinuationConflict
    f=await pending_chain(tmp_path,monkeypatch)
    try:
        await approve_write(f)
        async with f.factory() as session:
            job=(await session.execute(select(AgentJob).where(AgentJob.run_id==f.run_id,AgentJob.kind=='agent_continuation'))).scalar_one()
            job.payload_json={**job.payload_json,'plan_revision_digest':'f'*64};await session.commit()
        async with f.factory() as session:
            with pytest.raises(ContinuationConflict,match='frozen payload'):
                await AgentContinuationService(session).activate_ready()
        assert f.calls==['planner','writer']
    finally:await f.engine.dispose()

@pytest.mark.asyncio
async def test_rejected_approval_atomically_stops_dependents_and_persists_outcome(tmp_path,monkeypatch):
    from app.agent.worker import handle_agent_continuation_job
    f=await pending_chain(tmp_path,monkeypatch)
    try:
        async with f.factory() as session:
            await AgentRuntimeService(session).decide_approval(approval_id=f.approval_id,user_id=f.user_id,approved=False,reason='stop')
        async with f.factory() as session:
            runtime=AgentRuntimeService(session)
            assert (await runtime.get_run(f.run_id,f.user_id)).status=='cancelled'
            assert [step.status for step in await runtime.list_steps(run_id=f.run_id,user_id=f.user_id)]==['cancelled','cancelled']
            jobs=await AgentJobService(session).list_jobs(user_id=f.user_id)
            outcomes=[job for job in jobs if job.kind=='agent_continuation']
            assert len(outcomes)==1
            outcome=outcomes[0]
            assert outcome.status=='cancelled' and outcome.payload_json['outcome']=='rejected'
        worker=AgentWorker(f.factory,worker_id='reject-worker',handlers={'agent_continuation':handle_agent_continuation_job})
        assert not await worker.poll_once()
        assert f.calls==['planner']
    finally:await f.engine.dispose()


@pytest.mark.asyncio
async def test_failed_writer_records_terminal_intent_without_read(tmp_path,monkeypatch):
    f=await pending_chain(tmp_path,monkeypatch)
    try:
        async def broken_stream(self,**kwargs):
            if False:yield ''
            raise RuntimeError('writer fixture failed')
        monkeypatch.setattr('app.agent.write_executor.LLMService.stream_visible_response',broken_stream)
        async with f.factory() as session:
            await AgentRuntimeService(session).decide_approval(approval_id=f.approval_id,user_id=f.user_id,approved=True)
            with pytest.raises(Exception,match='candidate writer execution failed'):
                await execute_approved_write(approval_id=f.approval_id,user_id=f.user_id,session=session)
        async with f.factory() as session:
            runtime=AgentRuntimeService(session)
            assert (await runtime.get_run(f.run_id,f.user_id)).status=='failed'
            assert (await runtime.get_approval(approval_id=f.approval_id,user_id=f.user_id)).status=='execution_failed'
            jobs=await AgentJobService(session).list_jobs(user_id=f.user_id)
            outcomes=[job for job in jobs if job.kind=='agent_continuation']
            assert len(outcomes)==1
            outcome=outcomes[0]
            assert outcome.status=='cancelled' and outcome.payload_json['outcome']=='execution_failed'
            assert all(step.status in {'failed','cancelled'} for step in await runtime.list_steps(run_id=f.run_id,user_id=f.user_id))
        assert f.calls==['planner']
    finally:await f.engine.dispose()

@pytest.mark.asyncio
async def test_invalid_intent_is_quarantined_without_crashing_worker_loop(tmp_path,monkeypatch):
    from app.agent.worker import handle_agent_continuation_job
    f=await pending_chain(tmp_path,monkeypatch)
    try:
        await approve_write(f)
        async with f.factory() as session:
            job=(await session.execute(select(AgentJob).where(AgentJob.run_id==f.run_id,AgentJob.kind=='agent_continuation'))).scalar_one()
            job.payload_json={**job.payload_json,'plan_revision_digest':'f'*64};await session.commit()
        worker=AgentWorker(f.factory,worker_id='quarantine',handlers={'agent_continuation':handle_agent_continuation_job})
        assert await worker.poll_once() is False
        async with f.factory() as session:
            jobs=await AgentJobService(session).list_jobs(user_id=f.user_id)
            intent=next(job for job in jobs if job.kind=='agent_continuation')
            assert intent.status=='failed' and intent.error_type=='ContinuationConflict'
        assert f.calls==['planner','writer']
    finally:await f.engine.dispose()


@pytest.mark.asyncio
async def test_corrupt_candidate_file_prevents_continuation(tmp_path,monkeypatch):
    from app.agent.continuation import AgentContinuationService
    f=await pending_chain(tmp_path,monkeypatch)
    try:
        await approve_write(f)
        files=list((tmp_path/'artifacts').glob('*.md'));assert len(files)==1
        files[0].write_text('changed candidate bytes',encoding='utf8')
        async with f.factory() as session:
            with pytest.raises(Exception,match='integrity|proof'):
                await AgentContinuationService(session).activate_ready()
        assert f.calls==['planner','writer']
    finally:await f.engine.dispose()


@pytest.mark.asyncio
async def test_continuation_read_failure_converges_job_step_and_run(tmp_path,monkeypatch):
    from app.agent.worker import handle_agent_continuation_job
    from app.models.agent_catalog import AgentCapabilityExecution
    f=await pending_chain(tmp_path,monkeypatch)
    try:
        await approve_write(f)
        async def fail_read(**kwargs):raise RuntimeError('read leaf failure')
        monkeypatch.setattr('app.agent.continuation_worker.execute_read_tool',fail_read)
        worker=AgentWorker(f.factory,worker_id='failure-worker',handlers={'agent_continuation':handle_agent_continuation_job})
        assert await worker.poll_once()
        async with f.factory() as session:
            runtime=AgentRuntimeService(session)
            assert (await runtime.get_run(f.run_id,f.user_id)).status=='failed'
            steps=await runtime.list_steps(run_id=f.run_id,user_id=f.user_id)
            assert steps[1].status=='failed'
            facts=list((await session.execute(select(AgentCapabilityExecution).where(AgentCapabilityExecution.run_id==f.run_id,AgentCapabilityExecution.step_id==steps[1].id))).scalars())
            assert len(facts)==1 and facts[0].status=='failed'
            jobs=await AgentJobService(session).list_jobs(user_id=f.user_id)
            assert next(job for job in jobs if job.kind=='agent_continuation').status=='failed'
    finally:await f.engine.dispose()

@pytest.mark.asyncio
@pytest.mark.parametrize('has_handoff',[True,False])
async def test_expired_source_ack_recovery_requires_durable_handoff(tmp_path,monkeypatch,has_handoff):
    from datetime import timedelta
    from app.agent.continuation import AgentContinuationService,now
    from app.agent.worker import handle_agent_continuation_job
    f=await pending_chain(tmp_path,monkeypatch)
    try:
        async with f.factory() as session:
            source=await session.get(AgentJob,f.source_id)
            source.status='running';source.lease_owner='lost-worker';source.lease_expires_at=now()-timedelta(seconds=1)
            source.result_json={}
            if not has_handoff:
                run=await AgentRuntimeService(session).get_run(f.run_id,f.user_id)
                context=dict(run.context_json);context.pop('approval_wait_handoff',None);run.context_json=context
            await session.commit()
        await approve_write(f)
        async with f.factory() as session:
            activated=await AgentContinuationService(session).activate_ready()
            assert activated==(1 if has_handoff else 0)
            source=await session.get(AgentJob,f.source_id,populate_existing=True)
            assert source.status==('succeeded' if has_handoff else 'running')
        if has_handoff:
            worker=AgentWorker(f.factory,worker_id='recovered',handlers={'agent_continuation':handle_agent_continuation_job})
            assert await worker.poll_once()
            assert f.calls==['planner','writer','statistics']
        else:assert f.calls==['planner','writer']
    finally:await f.engine.dispose()


@pytest.mark.asyncio
async def test_transient_continuation_failure_retries_read_not_writer(tmp_path,monkeypatch):
    from app.agent.worker import handle_agent_continuation_job
    from app.agent.continuation import now
    from app.models.agent_catalog import AgentCapabilityExecution
    f=await pending_chain(tmp_path,monkeypatch)
    try:
        await approve_write(f)
        import app.agent.continuation_worker as module
        original=module.execute_read_tool
        class ProviderTimeout(Exception):pass
        attempts=[]
        async def once(**kwargs):
            attempts.append(1)
            if len(attempts)==1:raise ProviderTimeout('retry fixture')
            return await original(**kwargs)
        monkeypatch.setattr(module,'execute_read_tool',once)
        worker=AgentWorker(f.factory,worker_id='retry-worker',handlers={'agent_continuation':handle_agent_continuation_job})
        assert await worker.poll_once()
        async with f.factory() as session:
            job=(await session.execute(select(AgentJob).where(AgentJob.run_id==f.run_id,AgentJob.kind=='agent_continuation'))).scalar_one()
            assert job.status=='queued';job.available_at=now();await session.commit()
        assert await worker.poll_once()
        assert attempts==[1,1] and f.calls==['planner','writer','statistics']
        async with f.factory() as session:
            run=await AgentRuntimeService(session).get_run(f.run_id,f.user_id);assert run.status=='paused'
            facts=list((await session.execute(select(AgentCapabilityExecution).where(AgentCapabilityExecution.run_id==f.run_id,AgentCapabilityExecution.capability_id=='statistics.project'))).scalars())
            assert len(facts)==1 and facts[0].status=='completed' and facts[0].attempt==2
    finally:await f.engine.dispose()

@pytest.mark.asyncio
async def test_expired_read_checkpoint_and_fact_reclaim_use_new_generation(tmp_path,monkeypatch):
    from datetime import timedelta
    from app.agent.continuation import AgentContinuationService,now
    from app.agent.worker import handle_agent_continuation_job
    from app.models.agent_catalog import AgentCapabilityExecution
    from app.services.agent_execution_service import AgentExecutionService
    f=await pending_chain(tmp_path,monkeypatch)
    try:
        await approve_write(f)
        async with f.factory() as session:
            await AgentContinuationService(session).activate_ready()
            runtime=AgentRuntimeService(session)
            run=await runtime.get_run(f.run_id,f.user_id)
            steps=await runtime.list_steps(run_id=f.run_id,user_id=f.user_id)
            step=await runtime.claim_step(step_id=steps[1].id,user_id=f.user_id,lease_owner='dead-reader',lease_seconds=1)
            facts=AgentExecutionService(session);snapshot=await facts.get_run_snapshot(run.id)
            fact=await facts.begin_read_execution(run=run,step=step,snapshot=snapshot,capability_id=step.tool_name,
                arguments={'goal':run.context_json['goal'],'tool_arguments':{}},lease_generation=step.lease_generation,
                idempotency_key=f'{run.id}:capability:{step.id}')
            old_generation=step.lease_generation
            step.lease_expires_at=now()-timedelta(seconds=1);await session.commit()
        failures=[]
        async def capture_handler(job,session):
            try:return await handle_agent_continuation_job(job,session)
            except Exception:
                import traceback
                failures.append(traceback.format_exc())
                raise
        worker=AgentWorker(f.factory,worker_id='read-reclaimer',handlers={'agent_continuation':capture_handler})
        assert await worker.poll_once()
        assert not failures, '\n'.join(failures)
        async with f.factory() as session:
            runtime=AgentRuntimeService(session);steps=await runtime.list_steps(run_id=f.run_id,user_id=f.user_id)
            assert steps[1].status=='completed' and steps[1].lease_generation>old_generation
            fact=(await session.execute(select(AgentCapabilityExecution).where(AgentCapabilityExecution.run_id==f.run_id,AgentCapabilityExecution.step_id==steps[1].id))).scalar_one()
            assert fact.status=='completed' and fact.lease_generation==steps[1].lease_generation
            assert fact.attempt==2
        assert f.calls==['planner','writer','statistics']
    finally:await f.engine.dispose()

@pytest.mark.asyncio
async def test_write_read_write_chain_requires_second_approval_and_original_plan(tmp_path,monkeypatch):
    from app.agent.worker import handle_agent_continuation_job
    from app.models import ChapterVersion
    f=await pending_chain(tmp_path,monkeypatch,two_writes=True)
    try:
        await approve_write(f)
        worker=AgentWorker(f.factory,worker_id='multi-writer',handlers={'agent_continuation':handle_agent_continuation_job})
        assert await worker.poll_once()
        async with f.factory() as session:
            runtime=AgentRuntimeService(session)
            run=await runtime.get_run(f.run_id,f.user_id)
            assert run.status=='awaiting_approval'
            assert run.context_json['execution_job_id']==f.source_id
            approval=(await session.execute(select(AgentApproval).where(AgentApproval.run_id==f.run_id,AgentApproval.tool_name=='chapter.rewrite'))).scalar_one()
            assert approval.status=='pending'
            steps=await runtime.list_steps(run_id=f.run_id,user_id=f.user_id)
            assert [step.status for step in steps]==['completed','completed','awaiting_approval','pending']
            continuation_id=run.context_json['continuation_job_id']
            assert steps[2].input_json['approval_source_job_id']==continuation_id
            await runtime.decide_approval(approval_id=approval.id,user_id=f.user_id,approved=True)
            await execute_approved_write(approval_id=approval.id,user_id=f.user_id,session=session)
        assert await worker.poll_once()
        async with f.factory() as session:
            runtime=AgentRuntimeService(session)
            assert all(step.status=='completed' for step in await runtime.list_steps(run_id=f.run_id,user_id=f.user_id))
            assert (await runtime.get_run(f.run_id,f.user_id)).status=='paused'
            assert len(list((await session.execute(select(ChapterVersion))).scalars()))==1
            assert len([job for job in await AgentJobService(session).list_jobs(user_id=f.user_id) if job.kind=='agent_continuation'])==2
        assert f.calls==['planner','writer','statistics','writer']
    finally:await f.engine.dispose()

@pytest.mark.asyncio
async def test_two_workers_claim_one_continuation_without_duplicate_read(tmp_path,monkeypatch):
    import asyncio
    from app.agent.worker import handle_agent_continuation_job
    f=await pending_chain(tmp_path,monkeypatch)
    try:
        await approve_write(f)
        workers=[AgentWorker(f.factory,worker_id=f'concurrent-{i}',handlers={'agent_continuation':handle_agent_continuation_job}) for i in range(2)]
        outcomes=await asyncio.gather(*(worker.poll_once() for worker in workers))
        assert outcomes.count(True)==1
        assert f.calls==['planner','writer','statistics']
        async with f.factory() as session:
            steps=await AgentRuntimeService(session).list_steps(run_id=f.run_id,user_id=f.user_id)
            assert steps[1].status=='completed' and steps[1].attempt_count==1
    finally:await f.engine.dispose()


@pytest.mark.asyncio
async def test_retry_after_read_commit_reuses_checkpoint_before_final_ack(tmp_path,monkeypatch):
    from app.agent.continuation import AgentContinuationService,now
    from app.agent.worker import handle_agent_continuation_job
    f=await pending_chain(tmp_path,monkeypatch)
    try:
        await approve_write(f)
        original=AgentContinuationService._lock
        faults=[]
        class ProviderTimeout(Exception):pass
        async def fail_before_ack(self,run_id,user_id):
            run=await original(self,run_id,user_id)
            steps=await self.runtime.list_steps(run_id=run_id,user_id=user_id)
            if not faults and run.current_phase=='continuation' and all(step.status=='completed' for step in steps):
                faults.append(1);raise ProviderTimeout('crash before final acknowledgement')
            return run
        monkeypatch.setattr(AgentContinuationService,'_lock',fail_before_ack)
        worker=AgentWorker(f.factory,worker_id='ack-retry',handlers={'agent_continuation':handle_agent_continuation_job})
        assert await worker.poll_once()
        async with f.factory() as session:
            job=(await session.execute(select(AgentJob).where(AgentJob.run_id==f.run_id,AgentJob.kind=='agent_continuation'))).scalar_one()
            assert job.status=='queued';job.available_at=now();await session.commit()
        assert await worker.poll_once()
        assert faults==[1] and f.calls==['planner','writer','statistics']
        async with f.factory() as session:
            steps=await AgentRuntimeService(session).list_steps(run_id=f.run_id,user_id=f.user_id)
            assert all(step.status=='completed' and step.attempt_count==1 for step in steps)
    finally:await f.engine.dispose()
