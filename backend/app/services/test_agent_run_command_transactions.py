from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models import AgentEventRecord, User
from app.services.agent_runtime import AgentRuntimeService


async def _user(session, user_id: int, name: str) -> User:
    user = User(
        id=user_id,
        username=name,
        email=f"{name}@example.com",
        hashed_password="x",
        is_active=True,
    )
    session.add(user)
    await session.flush()
    return user


@pytest.mark.asyncio
async def test_request_command_persists_command_and_requested_event_in_one_commit(task_session, monkeypatch):
    user = await _user(task_session, 1901, "command-transaction-request")
    runtime = AgentRuntimeService(task_session)
    session = await runtime.create_session(user_id=user.id)
    run = await runtime.create_run(session_id=session.id, user_id=user.id)
    await runtime.update_run(run_id=run.id, user_id=user.id, status="running")

    original_commit = task_session.commit
    commits = 0

    async def counting_commit():
        nonlocal commits
        commits += 1
        await original_commit()

    monkeypatch.setattr(task_session, "commit", counting_commit)
    command = await runtime.request_run_command(
        run_id=run.id,
        user_id=user.id,
        command_type="pause",
        idempotency_key="request-transaction-1901",
        expected_state_version=int(run.state_version or 0),
    )

    assert commits == 1
    assert command.status == "requested"
    events = await runtime.list_events(run_id=run.id, user_id=user.id)
    assert [(event.event_type, event.sequence) for event in events] == [
        ("run_command_requested", 1),
    ]


@pytest.mark.asyncio
async def test_apply_command_persists_run_and_lifecycle_events_in_one_commit(task_session, monkeypatch):
    user = await _user(task_session, 1902, "command-transaction-apply")
    runtime = AgentRuntimeService(task_session)
    session = await runtime.create_session(user_id=user.id)
    run = await runtime.create_run(session_id=session.id, user_id=user.id)
    await runtime.update_run(run_id=run.id, user_id=user.id, status="running")
    command = await runtime.request_run_command(
        run_id=run.id,
        user_id=user.id,
        command_type="pause",
        idempotency_key="apply-transaction-1902",
        expected_state_version=int(run.state_version or 0),
    )

    original_commit = task_session.commit
    commits = 0

    async def counting_commit():
        nonlocal commits
        commits += 1
        await original_commit()

    monkeypatch.setattr(task_session, "commit", counting_commit)
    applied = await runtime.apply_run_command(command_id=command.id, user_id=user.id)

    assert commits == 1
    assert applied.status == "applied"
    saved = await runtime.get_run(run.id, user.id)
    assert saved.status == "paused"
    events = await runtime.list_events(run_id=run.id, user_id=user.id)
    assert [event.event_type for event in events] == [
        "run_command_requested",
        "run_paused",
        "run_command_applied",
    ]


@pytest.mark.asyncio
async def test_apply_command_retries_the_whole_transaction_after_event_sequence_conflict(task_session, monkeypatch):
    user = await _user(task_session, 1903, "command-transaction-retry")
    runtime = AgentRuntimeService(task_session)
    session = await runtime.create_session(user_id=user.id)
    run = await runtime.create_run(session_id=session.id, user_id=user.id)
    await runtime.update_run(run_id=run.id, user_id=user.id, status="running")
    command = await runtime.request_run_command(
        run_id=run.id,
        user_id=user.id,
        command_type="pause",
        idempotency_key="retry-transaction-1903",
        expected_state_version=int(run.state_version or 0),
    )
    run_id = run.id
    user_id = user.id
    command_id = command.id
    original_commit = task_session.commit
    commits = 0

    async def conflict_once():
        nonlocal commits
        commits += 1
        if commits == 1:
            raise IntegrityError(
                "INSERT INTO agent_events",
                {},
                Exception("UNIQUE constraint failed: agent_events.run_id, agent_events.sequence"),
            )
        await original_commit()

    monkeypatch.setattr(task_session, "commit", conflict_once)
    applied = await runtime.apply_run_command(command_id=command_id, user_id=user_id)

    assert commits == 2
    assert applied.status == "applied"
    saved = await runtime.get_run(run_id, user_id)
    assert saved.status == "paused"
    events = await runtime.list_events(run_id=run_id, user_id=user_id)
    assert [event.event_type for event in events] == [
        "run_command_requested",
        "run_paused",
        "run_command_applied",
    ]
    assert await task_session.scalar(
        select(func.count(AgentEventRecord.id)).where(
            AgentEventRecord.run_id == run_id,
        )
    ) == 3