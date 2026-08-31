from __future__ import annotations

import pytest
from sqlalchemy import select

from app.agent.jobs import AgentJobService
from app.api.routers.agent import cancel_agent_run
from app.models import AgentEventRecord, AgentJob, AgentRun, User
from app.services.agent_runtime import AgentRuntimeService
from types import SimpleNamespace


async def _user(session, user_id: int) -> User:
    user = User(
        id=user_id,
        username=f"cancel-{user_id}",
        email=f"cancel-{user_id}@example.com",
        hashed_password="x",
        is_active=True,
    )
    session.add(user)
    await session.flush()
    return user


@pytest.mark.asyncio
async def test_cancel_converges_after_outstanding_job_is_cancelled(task_session):
    user = await _user(task_session, 2601)
    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=user.id)
    run = await runtime.create_run(session_id=agent_session.id, user_id=user.id)
    await runtime.update_run(run_id=run.id, user_id=user.id, status="running")
    job = await AgentJobService(task_session).create_job(
        run_id=run.id, user_id=user.id, project_id=None, kind="agent_execution", idempotency_key="cancel-job-2601"
    )

    result = await cancel_agent_run(run.id, session=task_session, current_user=SimpleNamespace(id=user.id))

    assert result.status == "cancelled"
    saved_job = (await task_session.execute(select(AgentJob).where(AgentJob.id == job.id))).scalar_one()
    assert saved_job.status == "cancelled"
    events = list((await task_session.execute(
        select(AgentEventRecord).where(AgentEventRecord.run_id == run.id).order_by(AgentEventRecord.sequence.asc())
    )).scalars().all())
    event_types = [event.event_type for event in events]
    assert "run_cancelling" in event_types
    assert event_types[-1] == "run_cancelled"
    assert event_types.index("run_cancelling") < event_types.index("run_cancelled")


@pytest.mark.asyncio
async def test_cancel_marks_pending_approval_and_blocks_late_completion(task_session):
    user = await _user(task_session, 2602)
    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=user.id)
    run = await runtime.create_run(session_id=agent_session.id, user_id=user.id)
    await runtime.update_run(run_id=run.id, user_id=user.id, status="running")
    approval = await runtime.request_approval(
        run_id=run.id, user_id=user.id, tool_name="chapter.generate", project_id=None, arguments={"chapter_number": 1}
    )

    result = await cancel_agent_run(run.id, session=task_session, current_user=SimpleNamespace(id=user.id))

    assert result.status == "cancelled"
    saved_approval = await runtime.get_approval(approval_id=approval.id, user_id=user.id)
    assert saved_approval.status == "cancelled"
    with pytest.raises(Exception):
        await runtime.update_run(run_id=run.id, user_id=user.id, status="completed", progress=100)
