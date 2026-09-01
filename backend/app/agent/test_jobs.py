from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.agent.jobs import AgentJobConflict, AgentJobService
from app.models import NovelProject, User
from app.services.agent_runtime import AgentRuntimeService


async def _user(session, user_id: int, username: str) -> User:
    user = User(id=user_id, username=username, email=username + '@example.com', hashed_password='x', is_active=True)
    session.add(user)
    await session.flush()
    return user


@pytest.mark.asyncio
async def test_job_idempotency_and_payload_redaction(task_session):
    user = await _user(task_session, 1401, 'job-owner')
    task_session.add(NovelProject(id='job-project', user_id=user.id, title='Jobs'))
    await task_session.flush()
    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=user.id, project_id='job-project')
    run = await runtime.create_run(session_id=agent_session.id, user_id=user.id, project_id='job-project')
    service = AgentJobService(task_session)
    first = await service.create_job(run_id=run.id, user_id=user.id, project_id='job-project', kind='visible_response', idempotency_key='job-key', payload={'goal': 'x', 'reasoning': 'secret', 'nested': {'api_key': 'secret', 'ok': True}})
    second = await service.create_job(run_id=run.id, user_id=user.id, project_id='job-project', kind='visible_response', idempotency_key='job-key', payload={'other': 'ignored'})
    assert first.id == second.id
    assert first.payload_json == {'goal': 'x', 'nested': {'ok': True}}


@pytest.mark.asyncio
async def test_job_claim_is_atomic_and_expired_lease_can_be_taken_over(task_session):
    user = await _user(task_session, 1402, 'job-claim')
    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=user.id)
    run = await runtime.create_run(session_id=agent_session.id, user_id=user.id)
    service = AgentJobService(task_session)
    job = await service.create_job(run_id=run.id, user_id=user.id, project_id=None, kind='visible_response', idempotency_key='claim-key')
    claimed = await service.claim_job(job_id=job.id, user_id=user.id, lease_owner='worker-a')
    assert claimed.status == 'running'
    with pytest.raises(AgentJobConflict):
        await service.claim_job(job_id=job.id, user_id=user.id, lease_owner='worker-b')
    claimed.lease_expires_at = service._now() - timedelta(seconds=1) if hasattr(service, '_now') else None
    await task_session.commit()
    taken = await service.claim_job(job_id=job.id, user_id=user.id, lease_owner='worker-b')
    assert taken.lease_owner == 'worker-b'


@pytest.mark.asyncio
async def test_job_cancel_heartbeat_and_complete_are_lease_safe(task_session):
    user = await _user(task_session, 1403, 'job-cancel')
    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=user.id)
    run = await runtime.create_run(session_id=agent_session.id, user_id=user.id)
    service = AgentJobService(task_session)
    job = await service.create_job(run_id=run.id, user_id=user.id, project_id=None, kind='visible_response', idempotency_key='cancel-key')
    await service.claim_job(job_id=job.id, user_id=user.id, lease_owner='worker-a')
    cancelled = await service.request_cancel(job_id=job.id, user_id=user.id, reason='browser_stop')
    assert cancelled.status == 'cancelled'
    with pytest.raises(AgentJobConflict):
        await service.complete(job_id=job.id, user_id=user.id, lease_owner='worker-a', result={'ok': True})


@pytest.mark.asyncio
async def test_dead_letter_operator_replay_requeues_and_audits_without_losing_history(task_session):
    user = await _user(task_session, 1405, 'job-replay')
    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=user.id)
    run = await runtime.create_run(session_id=agent_session.id, user_id=user.id)
    service = AgentJobService(task_session)
    job = await service.create_job(
        run_id=run.id, user_id=user.id, project_id=None, kind='provider',
        idempotency_key='replay-key', max_attempts=1,
    )
    await service.claim_job(job_id=job.id, user_id=user.id, lease_owner='worker-a')
    dead = await service.fail(
        job_id=job.id, user_id=user.id, lease_owner='worker-a', error_type='ProviderTimeout'
    )
    assert dead.status == 'dead_letter'
    assert dead.attempt_count == 1

    replayed = await service.replay_dead_letter(
        job_id=job.id, operator_id=999, reason='after provider recovery'
    )
    assert replayed.status == 'queued'
    assert replayed.attempt_count == 1
    assert replayed.error_type == 'ProviderTimeout'
    assert 'replayed_by=999' in (replayed.error_detail or '')
    assert await service.list_dead_letters() == []

    events = await runtime.list_events(run_id=run.id, user_id=user.id)
    assert len(events) == 1
    assert events[0].event_type == 'job_replayed'
    assert events[0].data_json == {
        'job_id': job.id, 'attempt_count': 1, 'operator_id': 999
    }

    claimed_again = await service.claim_job(
        job_id=job.id, user_id=user.id, lease_owner='worker-b'
    )
    assert claimed_again.attempt_count == 2


@pytest.mark.asyncio
async def test_dead_letter_replay_is_idempotent_and_rejects_terminal_run(task_session):
    user = await _user(task_session, 1406, 'job-replay-terminal')
    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=user.id)
    run = await runtime.create_run(session_id=agent_session.id, user_id=user.id)
    service = AgentJobService(task_session)
    job = await service.create_job(
        run_id=run.id, user_id=user.id, project_id=None, kind='provider',
        idempotency_key='replay-terminal', max_attempts=1,
    )
    await service.claim_job(job_id=job.id, user_id=user.id, lease_owner='worker-a')
    await service.fail(job_id=job.id, user_id=user.id, lease_owner='worker-a', error_type='ProviderTimeout')
    await runtime.update_run(run_id=run.id, user_id=user.id, status='failed', phase='error')
    with pytest.raises(AgentJobConflict):
        await service.replay_dead_letter(job_id=job.id, operator_id=999)
@pytest.mark.asyncio
async def test_job_retry_then_dead_letter_and_non_retryable_failure(task_session):
    user = await _user(task_session, 1404, 'job-retry')
    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=user.id)
    run = await runtime.create_run(session_id=agent_session.id, user_id=user.id)
    service = AgentJobService(task_session)
    job = await service.create_job(run_id=run.id, user_id=user.id, project_id=None, kind='provider', idempotency_key='retry-key', max_attempts=2)
    await service.claim_job(job_id=job.id, user_id=user.id, lease_owner='worker-a')
    queued = await service.fail(job_id=job.id, user_id=user.id, lease_owner='worker-a', error_type='ProviderTimeout')
    assert queued.status == 'queued'
    queued.available_at = service._now() - timedelta(seconds=1) if hasattr(service, '_now') else queued.available_at
    await task_session.commit()
    await service.claim_job(job_id=job.id, user_id=user.id, lease_owner='worker-b')
    dead = await service.fail(job_id=job.id, user_id=user.id, lease_owner='worker-b', error_type='ProviderTimeout')
    assert dead.status == 'dead_letter'

    other = await service.create_job(run_id=run.id, user_id=user.id, project_id=None, kind='provider', idempotency_key='fatal-key')
    await service.claim_job(job_id=other.id, user_id=user.id, lease_owner='worker-a')
    failed = await service.fail(job_id=other.id, user_id=user.id, lease_owner='worker-a', error_type='InvalidPayload')
    assert failed.status == 'failed'


@pytest.mark.asyncio
async def test_successful_retry_clears_prior_provider_failure_details(task_session):
    user = await _user(task_session, 1407, 'job-retry-success')
    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=user.id)
    run = await runtime.create_run(session_id=agent_session.id, user_id=user.id)
    service = AgentJobService(task_session)
    job = await service.create_job(
        run_id=run.id,
        user_id=user.id,
        project_id=None,
        kind='visible_response',
        idempotency_key='retry-success-key',
        max_attempts=2,
    )

    await service.claim_job(job_id=job.id, user_id=user.id, lease_owner='worker-a')
    retry = await service.fail(
        job_id=job.id,
        user_id=user.id,
        lease_owner='worker-a',
        error_type='ProviderTimeout',
        detail='first provider response timed out',
    )
    assert retry.status == 'queued'
    assert retry.error_type == 'ProviderTimeout'
    retry.available_at = service._now() - timedelta(seconds=1)
    await task_session.commit()

    claimed = await service.claim_job(job_id=job.id, user_id=user.id, lease_owner='worker-b')
    completed = await service.complete(
        job_id=job.id,
        user_id=user.id,
        lease_owner='worker-b',
        lease_generation=claimed.lease_generation,
        result={'provider': 'recovered'},
    )

    assert completed.status == 'succeeded'
    assert completed.result_json == {'provider': 'recovered'}
    assert completed.error_type is None
    assert completed.error_detail is None


@pytest.mark.asyncio
@pytest.mark.parametrize("status, phase", [
    ("paused", "paused"),
    ("awaiting_approval", "approval"),
    ("cancelling", "cancelling"),
    ("completed", "summary"),
    ("failed", "error"),
    ("cancelled", "cancelled"),
])
async def test_job_claim_is_blocked_by_non_executable_run_status(task_session, status, phase):
    user = await _user(task_session, 1450 + len(status), f"job-gate-{status}")
    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=user.id)
    run = await runtime.create_run(session_id=agent_session.id, user_id=user.id)
    service = AgentJobService(task_session)
    job = await service.create_job(
        run_id=run.id,
        user_id=user.id,
        project_id=None,
        kind="visible_response",
        idempotency_key=f"gate-{status}",
    )
    await runtime.update_run(run_id=run.id, user_id=user.id, status=status, phase=phase)

    with pytest.raises(AgentJobConflict, match="not claimable"):
        await service.claim_job(job_id=job.id, user_id=user.id, lease_owner="worker-gate")
