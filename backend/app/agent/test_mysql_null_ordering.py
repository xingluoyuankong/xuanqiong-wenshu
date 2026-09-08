"""Use real service statements to check MySQL-compatible NULL placement."""
from datetime import datetime, timezone, timedelta
from uuid import uuid4
import pytest
from sqlalchemy.dialects import mysql
from app.models import User
from app.models.agent import AgentApproval
from app.agent.jobs import AgentJobService
from app.services.agent_runtime import AgentRuntimeService
from app.agent.state_projection import AgentStateProjectionService


async def scope(session):
    token=uuid4().hex
    user=User(username='null-sort-'+token,email=token+'@example.com',hashed_password='x',is_active=True)
    session.add(user);await session.flush();uid=user.id
    runtime=AgentRuntimeService(session)
    chat=await runtime.create_session(user_id=uid)
    run=await runtime.create_run(session_id=chat.id,user_id=uid)
    return runtime,uid,run


@pytest.mark.asyncio
@pytest.mark.parametrize('entry',['list','readable','projection','dead_letters'])
async def test_real_service_queries_do_not_emit_unsupported_mysql_nulls_syntax(task_session,monkeypatch,entry):
    runtime,uid,run=await scope(task_session)
    original=task_session.execute
    checked=[]
    async def inspect_and_execute(statement,*args,**kwargs):
        sql=str(statement.compile(dialect=mysql.dialect()))
        assert 'NULLS FIRST' not in sql and 'NULLS LAST' not in sql
        checked.append(sql)
        return await original(statement,*args,**kwargs)
    monkeypatch.setattr(task_session,'execute',inspect_and_execute)
    if entry=='list': await runtime.list_approvals(run_id=run.id,user_id=uid)
    elif entry=='readable': await runtime.list_approvals_readable(run_id=run.id,user_id=uid)
    elif entry=='projection': await AgentStateProjectionService(task_session).get_run_state(run_id=run.id,user_id=uid)
    else: await AgentJobService(task_session).list_dead_letters()
    assert any('ORDER BY' in sql and ' IS NULL' in sql for sql in checked)


@pytest.mark.asyncio
async def test_approvals_null_decisions_first_and_dead_letters_null_finished_last(task_session):
    runtime,uid,run=await scope(task_session)
    instant=datetime(2026,9,7,tzinfo=timezone.utc)
    approvals=[]
    for label,decision in [('later',instant+timedelta(seconds=2)),('pending',None),('earlier',instant)]:
        row=AgentApproval(id=str(uuid4()),run_id=run.id,user_id=uid,correlation_id=run.correlation_id,
            transaction_id=run.transaction_id,tool_name='chapter.generate',status='pending' if decision is None else 'approved',decision_at=decision,request_json={})
        task_session.add(row);approvals.append(row)
    await task_session.commit()
    expected=[approvals[1].id,approvals[2].id,approvals[0].id]
    assert [x.id for x in await runtime.list_approvals(run_id=run.id,user_id=uid)]==expected
    assert [x.id for x in await runtime.list_approvals_readable(run_id=run.id,user_id=uid)]==expected
    projection=await AgentStateProjectionService(task_session).get_run_state(run_id=run.id,user_id=uid)
    assert [x['id'] for x in projection['approvals']]==expected
    jobs=AgentJobService(task_session);rows=[]
    for i,finished in enumerate([instant,None,instant+timedelta(seconds=2)]):
        job=await jobs.create_job(run_id=run.id,user_id=uid,project_id=None,kind='visible_response',idempotency_key=f'null-sort-{i}')
        job.status='dead_letter';job.finished_at=finished;rows.append(job)
    await task_session.commit()
    assert [x.id for x in await jobs.list_dead_letters()]==[rows[2].id,rows[0].id,rows[1].id]
