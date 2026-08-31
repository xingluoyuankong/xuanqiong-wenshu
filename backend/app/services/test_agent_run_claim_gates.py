from __future__ import annotations

from datetime import timedelta

import pytest

from app.agent.jobs import AgentJobConflict, AgentJobService
from app.models import User
from app.services.agent_runtime import AgentConflict, AgentRuntimeService


async def _user(session, user_id: int, name: str) -> User:
    user = User(id=user_id, username=name, email=f"{name}@example.com", hashed_password="x", is_active=True)
    session.add(user)
    await session.flush()
    return user


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "phase"),
    [
        ("paused", "user"),
        ("awaiting_approval", "awaiting_approval"),
        ("cancelling", "cancelling"),
        ("completed", "summary"),
        ("failed", "error"),
        ("cancelled", "cancelled"),
    ],
)
async def test_run_claim_is_blocked_by_non_executable_status(task_session, status: str, phase: str) -> None:
    user = await _user(task_session, 1950 + len(status), f"run-claim-{status}")
    runtime = AgentRuntimeService(task_session)
    session = await runtime.create_session(user_id=user.id)
    run = await runtime.create_run(session_id=session.id, user_id=user.id)
    await runtime.update_run(run_id=run.id, user_id=user.id, status=status, phase=phase)

    with pytest.raises(AgentConflict, match="run lease"):
        await runtime.claim_run(run_id=run.id, user_id=user.id, lease_owner="gate-worker")


@pytest.mark.asyncio
async def test_recovery_ready_run_can_be_claimed_and_preserves_version(task_session) -> None:
    user = await _user(task_session, 1960, "run-claim-recovery")
    runtime = AgentRuntimeService(task_session)
    session = await runtime.create_session(user_id=user.id)
    run = await runtime.create_run(session_id=session.id, user_id=user.id)
    await runtime.update_run(run_id=run.id, user_id=user.id, status="running", phase="tool_execution")
    run.lease_owner = "expired-worker"
    run.lease_expires_at = runtime._now() - timedelta(seconds=1)
    await task_session.commit()
    before = await runtime.get_run(run.id, user.id)
    before_version = int(before.state_version or 0)
    recovered_ids = await runtime.reconcile_stale_runs()
    assert recovered_ids == [run.id]
    recovery = await runtime.get_run(run.id, user.id)
    assert recovery.status == "paused"
    assert recovery.current_phase == "recovery_ready"
    assert recovery.pause_reason == "lease_expired"
    assert recovery.resume_target_status == "running"
    assert recovery.state_version == before_version + 1

    claimed = await runtime.claim_run(run_id=run.id, user_id=user.id, lease_owner="replacement-worker")
    assert claimed.lease_owner == "replacement-worker"


@pytest.mark.asyncio
async def test_job_and_run_claim_gates_share_recovery_ready_semantics(task_session) -> None:
    user = await _user(task_session, 1970, "claim-gate-alignment")
    runtime = AgentRuntimeService(task_session)
    session = await runtime.create_session(user_id=user.id)
    run = await runtime.create_run(session_id=session.id, user_id=user.id)
    await runtime.update_run(run_id=run.id, user_id=user.id, status="running", phase="tool_execution")
    jobs = AgentJobService(task_session)
    job = await jobs.create_job(
        run_id=run.id,
        user_id=user.id,
        project_id=None,
        kind="visible_response",
        idempotency_key="claim-alignment",
    )
    await runtime.update_run(run_id=run.id, user_id=user.id, status="paused", phase="recovery_ready")
    claimed_run = await runtime.claim_run(run_id=run.id, user_id=user.id, lease_owner="run-worker")
    assert claimed_run.lease_owner == "run-worker"
    claimed_job = await jobs.claim_job(job_id=job.id, user_id=user.id, lease_owner="job-worker")
    assert claimed_job.status == "running"

    await runtime.update_run(run_id=run.id, user_id=user.id, status="paused", phase="user", pause_reason="user")
    with pytest.raises(AgentJobConflict, match="not claimable"):
        await jobs.claim_job(job_id=job.id, user_id=user.id, lease_owner="another-worker")

@pytest.mark.asyncio
async def test_run_lease_generation_fences_old_owner_after_same_owner_reclaim(task_session):
    user = await _user(task_session, 1988, "run-generation-fence")
    runtime = AgentRuntimeService(task_session)
    session = await runtime.create_session(user_id=user.id)
    run = await runtime.create_run(session_id=session.id, user_id=user.id)
    first = await runtime.claim_run(run_id=run.id, user_id=user.id, lease_owner="reused-owner", lease_seconds=60)
    first_generation = int(first.lease_generation or 0)
    first.lease_expires_at = runtime._now() - __import__("datetime").timedelta(seconds=1)
    await task_session.commit()
    second = await runtime.claim_run(run_id=run.id, user_id=user.id, lease_owner="reused-owner", lease_seconds=60, lease_generation=first_generation)
    assert second.lease_generation == first_generation + 1
    with pytest.raises(AgentConflict, match="generation"):
        await runtime.release_run(run_id=run.id, user_id=user.id, lease_owner="reused-owner", lease_generation=first_generation)
