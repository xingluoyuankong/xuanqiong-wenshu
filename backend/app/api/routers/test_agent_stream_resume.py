from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.routers import agent as agent_router
from app.api.routers.agent import resolve_agent_stream_cursor, stream_agent_events
from app.models import User
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


class _Request:
    def __init__(self, *, last_event_id: str | None = None, disconnected_after: int = 0):
        self.headers = {} if last_event_id is None else {"last-event-id": last_event_id}
        self._checks = 0
        self._disconnected_after = disconnected_after

    async def is_disconnected(self) -> bool:
        self._checks += 1
        return self._checks > self._disconnected_after


@pytest.mark.parametrize(
    ("header", "query", "expected"),
    [
        ("10", 3, 10),
        (" 10 ", 3, 10),
        (None, 3, 3),
        ("", 3, 3),
        ("not-a-sequence", 3, 3),
        ("-1", 3, 3),
        ("not-a-sequence", -4, 0),
    ],
)
def test_resolve_agent_stream_cursor_prefers_valid_header_and_falls_back(
    header: str | None, query: int, expected: int
):
    assert resolve_agent_stream_cursor(header, query) == expected


@pytest.mark.asyncio
async def test_stream_uses_last_event_id_before_after_sequence_and_replays_persisted_events(
    task_session, monkeypatch
):
    user = await _user(task_session, 1301, "stream-resume-owner")
    service = AgentRuntimeService(task_session)
    agent_session = await service.create_session(user_id=user.id)
    run = await service.create_run(session_id=agent_session.id, user_id=user.id)
    first = await service.append_event(
        run_id=run.id, user_id=user.id, event_type="run_started", summary="first", data={"phase": "observe"}
    )
    second = await service.append_work_trace_delta(
        run_id=run.id,
        user_id=user.id,
        trace_id="trace-1301",
        phase="act",
        kind="tool",
        message="读取持久化章节索引",
        progress=32,
        capability_id="content.search",
    )
    await service.update_run(run_id=run.id, user_id=user.id, status="completed", progress=100)
    terminal = await service.append_event(
        run_id=run.id, user_id=user.id, event_type="run_completed", summary="done", data={"phase": "finish"}
    )

    captured: list[int] = []
    original_list_events = AgentRuntimeService.list_events

    async def capture_list_events(self, *, run_id, user_id, after_sequence=0, limit=500):
        captured.append(after_sequence)
        return await original_list_events(
            self, run_id=run_id, user_id=user_id, after_sequence=after_sequence, limit=limit
        )

    session_factory = async_sessionmaker(task_session.bind, expire_on_commit=False)

    class _SessionContext:
        def __init__(self):
            self.session = session_factory()

        async def __aenter__(self):
            return self.session

        async def __aexit__(self, exc_type, exc, tb):
            await self.session.close()
            return False

    monkeypatch.setattr(agent_router, "AsyncSessionLocal", _SessionContext)
    monkeypatch.setattr(AgentRuntimeService, "list_events", capture_list_events)

    response = await stream_agent_events(
        agent_session.id,
        run.id,
        _Request(last_event_id=str(first.sequence), disconnected_after=10),
        after_sequence=0,
        current_user=SimpleNamespace(id=user.id),
    )
    chunks = [chunk async for chunk in response.body_iterator]
    body = "".join(chunk.decode() if isinstance(chunk, bytes) else chunk for chunk in chunks)

    assert captured == [first.sequence]
    assert f"id: {second.sequence}" in body
    assert f"id: {terminal.sequence}" in body
    assert "event: work_trace_delta" in body
    assert "读取持久化章节索引" in body
    assert f"id: {first.sequence}" not in body


@pytest.mark.asyncio
async def test_stream_closes_after_terminal_batch_without_second_poll(task_session, monkeypatch):
    user = await _user(task_session, 1302, "stream-terminal-owner")
    service = AgentRuntimeService(task_session)
    agent_session = await service.create_session(user_id=user.id)
    run = await service.create_run(session_id=agent_session.id, user_id=user.id)
    event = await service.append_event(
        run_id=run.id, user_id=user.id, event_type="run_started", summary="terminal event", data={"phase": "finish"}
    )
    await service.update_run(run_id=run.id, user_id=user.id, status="completed", progress=100)

    poll_count = 0
    original_list_events = AgentRuntimeService.list_events

    async def count_list_events(self, *, run_id, user_id, after_sequence=0, limit=500):
        nonlocal poll_count
        poll_count += 1
        return await original_list_events(
            self, run_id=run_id, user_id=user_id, after_sequence=after_sequence, limit=limit
        )

    class _SessionContext:
        async def __aenter__(self):
            return task_session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(agent_router, "AsyncSessionLocal", lambda: _SessionContext())
    monkeypatch.setattr(AgentRuntimeService, "list_events", count_list_events)

    response = await stream_agent_events(
        agent_session.id,
        run.id,
        _Request(disconnected_after=10),
        after_sequence=0,
        current_user=SimpleNamespace(id=user.id),
    )
    chunks = [chunk async for chunk in response.body_iterator]

    assert poll_count == 1
    assert len(chunks) == 1
    assert f"id: {event.sequence}" in chunks[0]


@pytest.mark.asyncio
async def test_append_work_trace_delta_persists_public_projection_only(task_session):
    user = await _user(task_session, 1304, "work-trace-owner")
    service = AgentRuntimeService(task_session)
    agent_session = await service.create_session(user_id=user.id)
    run = await service.create_run(session_id=agent_session.id, user_id=user.id)

    event = await service.append_work_trace_delta(
        run_id=run.id,
        user_id=user.id,
        trace_id="trace-1304",
        phase="persist",
        kind="result",
        message="已写入可回放事件账本",
        progress=88,
        action_id="action.persist",
        capability_id="event.append",
        result_ref="event:pending",
    )

    assert event.event_type == "work_trace_delta"
    assert event.sequence == 1
    assert event.data_json == {
        "trace_id": "trace-1304",
        "phase": "persist",
        "action_id": "action.persist",
        "kind": "result",
        "message": "已写入可回放事件账本",
        "progress": 88.0,
        "capability_id": "event.append",
        "result_ref": "event:pending",
    }
    assert "run_id" not in event.data_json
    assert "private_reasoning" not in event.data_json

    replayed = await service.list_events(run_id=run.id, user_id=user.id, after_sequence=0)
    assert [(item.sequence, item.event_type) for item in replayed] == [(1, "work_trace_delta")]

    with pytest.raises(ValidationError):
        await service.append_work_trace_delta(
            run_id=run.id,
            user_id=user.id,
            trace_id="trace-1304-private",
            phase="act",
            kind="status",
            message="system_prompt: hidden",
        )


@pytest.mark.asyncio
async def test_stream_invalid_last_event_id_falls_back_to_query_cursor(task_session, monkeypatch):
    user = await _user(task_session, 1305, "stream-invalid-header-owner")
    service = AgentRuntimeService(task_session)
    agent_session = await service.create_session(user_id=user.id)
    run = await service.create_run(session_id=agent_session.id, user_id=user.id)
    first = await service.append_event(
        run_id=run.id, user_id=user.id, event_type="run_started", summary="first", data={"phase": "observe"}
    )
    second = await service.append_work_trace_delta(
        run_id=run.id,
        user_id=user.id,
        trace_id="trace-1305",
        phase="act",
        kind="status",
        message="query cursor fallback",
    )
    await service.update_run(run_id=run.id, user_id=user.id, status="completed", progress=100)

    captured: list[int] = []
    original_list_events = AgentRuntimeService.list_events

    async def capture_list_events(self, *, run_id, user_id, after_sequence=0, limit=500):
        captured.append(after_sequence)
        return await original_list_events(
            self, run_id=run_id, user_id=user_id, after_sequence=after_sequence, limit=limit
        )

    class _SessionContext:
        async def __aenter__(self):
            return task_session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(agent_router, "AsyncSessionLocal", lambda: _SessionContext())
    monkeypatch.setattr(AgentRuntimeService, "list_events", capture_list_events)

    response = await stream_agent_events(
        agent_session.id,
        run.id,
        _Request(last_event_id="bad-header", disconnected_after=10),
        after_sequence=first.sequence,
        current_user=SimpleNamespace(id=user.id),
    )
    body = "".join(
        [
            chunk.decode() if isinstance(chunk, bytes) else chunk
            async for chunk in response.body_iterator
        ]
    )

    assert captured == [first.sequence]
    assert f"id: {first.sequence}" not in body
    assert f"id: {second.sequence}" in body


@pytest.mark.asyncio
async def test_stream_does_not_poll_when_client_is_already_disconnected(task_session, monkeypatch):
    user = await _user(task_session, 1303, "stream-disconnected-owner")
    service = AgentRuntimeService(task_session)
    agent_session = await service.create_session(user_id=user.id)
    run = await service.create_run(session_id=agent_session.id, user_id=user.id)

    class _SessionContext:
        async def __aenter__(self):
            raise AssertionError("disconnected stream must not open a database session")

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(agent_router, "AsyncSessionLocal", lambda: _SessionContext())

    response = await stream_agent_events(
        agent_session.id,
        run.id,
        _Request(disconnected_after=-1),
        after_sequence=0,
        current_user=SimpleNamespace(id=user.id),
    )
    assert [chunk async for chunk in response.body_iterator] == []

@pytest.mark.asyncio
async def test_stream_scope_mismatch_is_rejected_before_sse_headers(task_session, monkeypatch):
    from fastapi import HTTPException

    user = await _user(task_session, 1306, "stream-scope-owner")
    service = AgentRuntimeService(task_session)
    first_session = await service.create_session(user_id=user.id)
    second_session = await service.create_session(user_id=user.id)
    run = await service.create_run(session_id=second_session.id, user_id=user.id)

    class _SessionContext:
        async def __aenter__(self):
            return task_session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(agent_router, "AsyncSessionLocal", lambda: _SessionContext())

    with pytest.raises(HTTPException) as error:
        await stream_agent_events(
            first_session.id,
            run.id,
            _Request(disconnected_after=10),
            after_sequence=0,
            current_user=SimpleNamespace(id=user.id),
        )

    assert error.value.status_code == 403
    assert error.value.detail["code"] == "AGENT_SCOPE_VIOLATION"


