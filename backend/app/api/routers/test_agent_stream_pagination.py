from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.routers import agent as agent_router
from app.api.routers.agent import stream_agent_events
from app.models import User
from app.models.agent import AgentEventRecord
from app.services.agent_runtime import AgentRuntimeService


class _Request:
    def __init__(self):
        self.headers: dict[str, str] = {}
        self.checks = 0

    async def is_disconnected(self) -> bool:
        self.checks += 1
        return False


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
@pytest.mark.parametrize("event_count", [499, 500, 501, 1000])
async def test_terminal_stream_paginates_exact_boundaries_without_loss_or_duplicates(
    task_session, monkeypatch, event_count: int
):
    user = await _user(task_session, 1320 + event_count, f"stream-page-{event_count}")
    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=user.id)
    run = await runtime.create_run(session_id=agent_session.id, user_id=user.id)

    now = datetime.now(timezone.utc)
    task_session.add_all(
        [
            AgentEventRecord(
                id=str(uuid4()),
                run_id=run.id,
                correlation_id=run.correlation_id,
                transaction_id=run.transaction_id,
                user_id=user.id,
                event_type="progress_update",
                sequence=sequence,
                summary=f"event-{sequence}",
                data_json={"phase": "act", "progress": sequence % 101},
                created_at=now,
            )
            for sequence in range(1, event_count + 1)
        ]
    )
    run.event_sequence = event_count
    run.status = "completed"
    run.progress = 100
    await task_session.commit()

    calls: list[int] = []
    factory = async_sessionmaker(task_session.bind, expire_on_commit=False)
    original_list_events = AgentRuntimeService.list_events

    async def capture_list_events(self, *, run_id, user_id, after_sequence=0, limit=500):
        calls.append(after_sequence)
        return await original_list_events(
            self,
            run_id=run_id,
            user_id=user_id,
            after_sequence=after_sequence,
            limit=limit,
        )

    monkeypatch.setattr(agent_router, "AsyncSessionLocal", factory)
    monkeypatch.setattr(AgentRuntimeService, "list_events", capture_list_events)

    response = await stream_agent_events(
        agent_session.id,
        run.id,
        _Request(),
        after_sequence=0,
        current_user=SimpleNamespace(id=user.id),
    )
    chunks = [chunk async for chunk in response.body_iterator]
    body = "".join(chunk.decode() if isinstance(chunk, bytes) else chunk for chunk in chunks)

    emitted = [
        int(line.removeprefix("id: "))
        for line in body.splitlines()
        if line.startswith("id: ")
    ]
    assert emitted == list(range(1, event_count + 1))
    assert len(emitted) == len(set(emitted)) == event_count
    assert calls == list(range(0, event_count, 500)) + ([event_count] if event_count % 500 == 0 else [])