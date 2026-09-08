"""Lease SET ordering regressions: compile current services, not copied SQL."""
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.dialects import mysql, sqlite
from app.agent.jobs import AgentJobService, AgentJobConflict
from app.services.agent_runtime import AgentRuntimeService, AgentConflict
from app.models import User


class CaptureSession:
    async def execute(self, statement):
        self.statement = statement
        return SimpleNamespace(rowcount=0)


@pytest.mark.asyncio
@pytest.mark.parametrize('dialect', [mysql.dialect(), sqlite.dialect()], ids=['mysql','sqlite'])
@pytest.mark.parametrize('kind', ['job', 'run'])
@pytest.mark.parametrize('generation', [None, 0, 7])
async def test_claim_compiled_set_order_and_explicit_generation(dialect, kind, generation):
    session = CaptureSession()
    with pytest.raises((AgentJobConflict, AgentConflict)):
        if kind == 'job':
            await AgentJobService(session).claim_job(job_id='job', user_id=1,
                lease_owner='owner', lease_generation=generation)
        else:
            await AgentRuntimeService(session).claim_run(run_id='run', user_id=1,
                lease_owner='owner', lease_generation=generation)
    sql = str(session.statement.compile(dialect=dialect, compile_kwargs={'literal_binds': True}))
    assignments = sql.split(' SET ', 1)[1].split(' WHERE ', 1)[0]
    assert assignments.index('lease_generation=CASE') < assignments.index('lease_owner=')
    assert assignments.index('lease_generation=CASE') < assignments.index('lease_expires_at=')
    predicate = sql.split(' WHERE ', 1)[1]
    expected = f'agent_{kind}s.lease_generation = {generation}'
    if generation is not None:
        assert expected in predicate
    else:
        assert f'agent_{kind}s.lease_generation =' not in predicate


async def lease_fixture(session):
    token = uuid4().hex
    user = User(username='lease-'+token, email=token+'@example.com', hashed_password='x', is_active=True)
    session.add(user)
    await session.flush()
    uid = user.id
    runtime = AgentRuntimeService(session)
    chat = await runtime.create_session(user_id=uid)
    run = await runtime.create_run(session_id=chat.id, user_id=uid)
    job = await AgentJobService(session).create_job(run_id=run.id, user_id=uid,
        project_id=None, kind='visible_response', idempotency_key=token)
    return uid, run.id, job.id


@pytest.mark.asyncio
@pytest.mark.parametrize('owner', ['first', 'replacement'])
async def test_job_generation_zero_reclaim_and_stale_completion(task_session, owner):
    uid, rid, jid = await lease_fixture(task_session)
    jobs = AgentJobService(task_session)
    first = await jobs.claim_job(job_id=jid, user_id=uid, lease_owner='first', lease_generation=0)
    assert first.lease_generation == 1
    first.lease_expires_at = jobs._now() - timedelta(seconds=2)
    await task_session.commit()
    with pytest.raises(AgentJobConflict):
        await jobs.claim_job(job_id=jid, user_id=uid, lease_owner=owner, lease_generation=0)
    await task_session.rollback()
    second = await jobs.claim_job(job_id=jid, user_id=uid, lease_owner=owner, lease_generation=1)
    assert second.lease_generation == 2
    with pytest.raises(AgentJobConflict):
        await jobs.complete(job_id=jid, user_id=uid, lease_owner=owner, lease_generation=1, result={'stale': True})
    await task_session.rollback()
    current = await jobs.get_job(job_id=jid, user_id=uid)
    assert current.status == 'running' and current.result_json == {}
    assert current.lease_generation == 2


@pytest.mark.asyncio
async def test_run_renewal_reclaim_and_identity_map_refresh(task_session):
    uid, rid, jid = await lease_fixture(task_session)
    runtime = AgentRuntimeService(task_session)
    first = await runtime.claim_run(run_id=rid, user_id=uid, lease_owner='same', lease_generation=0)
    assert first.lease_generation == 1
    renewed = await runtime.claim_run(run_id=rid, user_id=uid, lease_owner='same', lease_generation=1)
    assert renewed is first and renewed.lease_generation == 1
    renewed.lease_expires_at = runtime._now() - timedelta(seconds=2)
    await task_session.commit()
    reclaimed = await runtime.claim_run(run_id=rid, user_id=uid, lease_owner='same', lease_generation=1)
    assert reclaimed.lease_generation == 2
    with pytest.raises(AgentConflict):
        await runtime.claim_run(run_id=rid, user_id=uid, lease_owner='same', lease_generation=1)
    await task_session.rollback()


@pytest.mark.asyncio
async def test_job_active_lease_still_rejects_duplicate_claim(task_session):
    uid, rid, jid = await lease_fixture(task_session)
    jobs = AgentJobService(task_session)
    first = await jobs.claim_job(job_id=jid, user_id=uid, lease_owner='same', lease_generation=0)
    assert first.lease_generation == 1
    with pytest.raises(AgentJobConflict):
        await jobs.claim_job(job_id=jid, user_id=uid, lease_owner='same', lease_generation=1)
    await task_session.rollback()
    current = await jobs.get_job(job_id=jid, user_id=uid)
    assert current.lease_generation == 1 and current.attempt_count == 1
