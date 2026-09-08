"""Waiting approval is not a terminal dependency failure: real worker checkpoints."""
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.agent.executor import build_agent_plan
from app.agent.jobs import AgentJobService
from app.agent.schemas import AgentPlanRequest
from app.agent.test_worker import _factory
from app.agent.worker import AgentWorker, handle_agent_execution_job
from app.models import User, NovelProject
from app.models.agent import AgentApproval, AgentRunStep
from app.models.agent_plan import PlanRevision
from app.services.agent_runtime import AgentRuntimeService


@pytest.mark.asyncio
@pytest.mark.parametrize('chain', [False, True])
async def test_worker_leaves_approval_dependents_pending_without_failure_or_replan(tmp_path, monkeypatch, chain):
    engine, factory = await _factory(tmp_path)
    tools = ['chapter.generate', 'statistics.project'] + (['project.context'] if chain else [])
    calls = []
    try:
        async with factory() as session:
            user = User(username='waiting-owner',email='waiting-owner@example.com',hashed_password='x',is_active=True)
            session.add(user);await session.flush()
            project = NovelProject(id='waiting-project',user_id=user.id,title='Approval dependency')
            session.add(project);await session.flush()
            runtime = AgentRuntimeService(session)
            chat = await runtime.create_session(user_id=user.id, project_id=project.id)
            run = await runtime.create_run(session_id=chat.id,user_id=user.id,project_id=project.id,
                context={'goal':'生成候选后查看统计','context_refs':[], 'requested_tools':tools,
                         'tool_arguments':{'chapter.generate':{'chapter_number':1}}})
            job = await AgentJobService(session).create_job(run_id=run.id,user_id=user.id,project_id=project.id,kind='agent_execution',idempotency_key=f'{run.id}:agent_execution')
        class Planner:
            async def plan(self, **kwargs):
                calls.append('planner')
                plan = build_agent_plan(AgentPlanRequest(goal=kwargs['goal'], project_id=kwargs['project_id'], tools=tools),user_id=kwargs['user_id'])
                for i in range(1, len(plan.steps)): plan.steps[i].depends_on=[i]
                return SimpleNamespace(plan=plan,visible_summary='先生成再读取',provider_called=True,fallback_reason=None)
        async def read(**kwargs): calls.append(kwargs['tool_name']);return {'ok':True}
        monkeypatch.setattr('app.agent.execution.AgentOrchestrator',lambda *args,**kwargs:Planner())
        monkeypatch.setattr('app.agent.execution.execute_read_tool',read)
        monkeypatch.setattr('app.agent.execution.launch_visible_response',lambda **kwargs:None)
        worker = AgentWorker(factory,worker_id='dependency-worker',handlers={'agent_execution':handle_agent_execution_job})
        assert await worker.poll_once()
        assert calls == ['planner']
        async with factory() as session:
            runtime = AgentRuntimeService(session)
            stored = await runtime.get_run(run.id,user.id)
            steps = await runtime.list_steps(run_id=run.id,user_id=user.id)
            assert [step.status for step in steps] == ['awaiting_approval'] + ['pending'] * (len(tools)-1)
            assert all(step.error_type is None and step.finished_at is None for step in steps)
            assert stored.status == 'awaiting_approval'
            jobs = await AgentJobService(session).list_jobs(user_id=user.id)
            assert len(jobs)==1 and jobs[0].status=='succeeded'
            assert len((await session.execute(select(AgentApproval).where(AgentApproval.run_id==run.id))).scalars().all()) == 1
            events = await runtime.list_events(run_id=run.id,user_id=user.id)
            assert not any(event.event_type=='plan_step_failed' for event in events)
            blocked = [event for event in events if event.event_type=='plan_step_blocked']
            assert len(blocked)==len(tools)-1
            assert all(event.data_json['reason']=='dependency_waiting' for event in blocked)
            revisions = (await session.execute(select(PlanRevision).where(PlanRevision.run_id==run.id))).scalars().all()
            assert len(revisions)==1
            assert [item['depends_on'] for item in revisions[0].plan_json['steps']] == [[],[1]] + ([[2]] if chain else [])
    finally: await engine.dispose()

@pytest.mark.parametrize('event_type,reason', [('plan_step_blocked','dependency_waiting'), ('plan_step_cancelled','dependency_cancelled')])
def test_dependency_event_metadata_is_visible_but_private_payload_is_not(event_type, reason):
    from app.services.agent_runtime import _visible_event_data
    result = _visible_event_data(event_type, {'step': 2, 'tool_name': 'statistics.project',
        'reason': reason, 'dependencies': [1], 'phase': 'planning',
        'reasoning': 'PRIVATE_SENTINEL', 'arguments': {'secret': 'PRIVATE_SENTINEL'}})
    assert result == {'step': 2, 'tool_name': 'statistics.project', 'reason': reason,
                      'dependencies': [1], 'phase': 'planning'}
    assert 'PRIVATE_SENTINEL' not in str(result)
