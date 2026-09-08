"""Real durable worker regression for strict context reads before planning."""
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from app.agent.executor import build_agent_plan
from app.agent.jobs import AgentJobService
from app.agent.schemas import AgentPlanRequest
from app.agent.test_worker import _factory
from app.agent.worker import AgentWorker, handle_agent_execution_job
from app.models.agent import AgentRun, AgentRunStep, AgentArtifactRef
from app.models.agent_catalog import AgentCapabilityExecution
from app.models.agent_context import ContextSnapshot, ContextSnapshotRef
from app.models.agent_plan import PlanRevision
from app.models.novel import NovelProject
from app.models.user import User
from app.services.agent_context_service import AgentContextService
from app.services.agent_runtime import AgentRuntimeService


async def setup_run(factory, *, legacy=False, replan_context=False):
    async with factory() as session:
        user=User(username='strict-worker',email='strict-worker@example.com',hashed_password='x',is_active=True)
        session.add(user);await session.flush()
        project=NovelProject(id=uuid4().hex,user_id=user.id,title='Strict worker')
        session.add(project);await session.flush()
        runtime=AgentRuntimeService(session)
        chat=await runtime.create_session(user_id=user.id,project_id=project.id)
        context={'goal':'读取项目','context_refs':[{'kind':'project','project_id':project.id}],'requested_tools':['project.context']}
        if legacy:
            run=AgentRun(id=str(uuid4()),session_id=chat.id,user_id=user.id,project_id=project.id,
                         correlation_id=str(uuid4()),transaction_id=str(uuid4()),status='created',context_json=context)
            session.add(run);await session.commit()
        else:
            run=await runtime.create_run(session_id=chat.id,user_id=user.id,project_id=project.id,context=context)
        if replan_context:
            snapshot=await AgentContextService(session).create_snapshot(run=run,session=chat,context_json=context,refs=context['context_refs'],context_kind='replan_context')
            updated=dict(run.context_json);updated['relational_context_snapshot_id']=snapshot.id;updated['relational_context_snapshot_key']=snapshot.snapshot_id
            await runtime.set_run_context(run_id=run.id,user_id=user.id,context=updated)
        job=await AgentJobService(session).create_job(run_id=run.id,user_id=user.id,project_id=project.id,kind='agent_execution',idempotency_key=f'{run.id}:execution')
        return run.id,user.id,job.id


def fake_edges(monkeypatch):
    calls=[]
    class Planner:
        async def plan(self,**kwargs):
            calls.append('planner')
            return SimpleNamespace(plan=build_agent_plan(AgentPlanRequest(goal=kwargs['goal'],project_id=kwargs['project_id'],tools=['project.context']),user_id=kwargs['user_id']),visible_summary='计划',provider_called=False,fallback_reason=None)
    async def read(**kwargs):calls.append('read');return {'ok':True}
    monkeypatch.setattr('app.agent.execution.AgentOrchestrator',lambda *args,**kwargs:Planner())
    monkeypatch.setattr('app.agent.execution.execute_read_tool',read)
    monkeypatch.setattr('app.agent.execution.launch_visible_response',lambda **kwargs:None)
    return calls


@pytest.mark.asyncio
@pytest.mark.parametrize('damage',['missing-row','digest','ref-digest','id','key','user','session','project','correlation','transaction','drop-locators','null-key','refs-drift','invalid-json'])
async def test_worker_rejects_damaged_modern_context_before_planner(tmp_path,monkeypatch,damage):
    engine,factory=await _factory(tmp_path)
    calls=fake_edges(monkeypatch)
    try:
        run_id,user_id,job_id=await setup_run(factory)
        async with factory() as session:
            run=await AgentRuntimeService(session).get_run(run_id,user_id)
            snapshot=await AgentContextService(session).get_run_snapshot(run_id=run_id,snapshot_id=run.context_json['relational_context_snapshot_key'])
            context=deepcopy(run.context_json)
            if damage=='missing-row':await session.delete(snapshot)
            elif damage=='digest':await session.execute(update(ContextSnapshot).where(ContextSnapshot.id==snapshot.id).values(digest='f'*64))
            elif damage=='ref-digest':await session.execute(update(ContextSnapshotRef).where(ContextSnapshotRef.id==snapshot.refs[0].id).values(digest='f'*64))
            elif damage in ('user','session','project','correlation','transaction'):
                column={'user':'user_id','session':'session_id','project':'project_id','correlation':'correlation_id','transaction':'transaction_id'}[damage]
                await session.execute(update(ContextSnapshot).where(ContextSnapshot.id==snapshot.id).values(**{column:user_id+100 if damage=='user' else str(uuid4())}))
            else:
                if damage=='id':context['relational_context_snapshot_id']=str(uuid4())
                elif damage=='key':context['relational_context_snapshot_key']=str(uuid4())
                elif damage=='null-key':context['relational_context_snapshot_key']=None
                elif damage=='drop-locators':
                    context.pop('relational_context_snapshot_id');context.pop('relational_context_snapshot_key')
                elif damage=='refs-drift':context['context_refs']=[]
                elif damage=='invalid-json':context=[]
                run.context_json=context
            await session.commit()
        worker=AgentWorker(factory,worker_id='strict-worker',handlers={'agent_execution':handle_agent_execution_job})
        assert await worker.poll_once()
        assert calls==[]
        async with factory() as session:
            job=await AgentJobService(session).get_job(job_id=job_id,user_id=user_id)
            run=await AgentRuntimeService(session).get_run(run_id,user_id)
            assert job.status=='failed'
            assert job.error_type=='RunContextIntegrityError'
            assert run.status=='failed'
            for model in (AgentRunStep,AgentArtifactRef,AgentCapabilityExecution,PlanRevision):
                assert (await session.execute(select(model).where(model.run_id==run_id))).scalars().all()==[]
            assert [item.kind for item in await AgentJobService(session).list_jobs(user_id=user_id)]==['agent_execution']
    finally:await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('kind',['initial','replan-context','legacy'])
async def test_worker_keeps_real_initial_replan_and_legacy_context(tmp_path,monkeypatch,kind):
    engine,factory=await _factory(tmp_path)
    calls=fake_edges(monkeypatch)
    try:
        run_id,user_id,job_id=await setup_run(factory,legacy=kind=='legacy',replan_context=kind=='replan-context')
        worker=AgentWorker(factory,worker_id='strict-worker',handlers={'agent_execution':handle_agent_execution_job})
        assert await worker.poll_once()
        assert calls==['planner','read']
        async with factory() as session:
            job=await AgentJobService(session).get_job(job_id=job_id,user_id=user_id)
            assert job.status=='succeeded'
            assert len(await AgentRuntimeService(session).list_steps(run_id=run_id,user_id=user_id))==1
    finally:await engine.dispose()
