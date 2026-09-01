from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.routers import agent as agent_router
from app.core.dependencies import get_current_user
from app.db.session import get_session
from app.main import app
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


@pytest.mark.asyncio
async def test_agent_stream_http_honors_last_event_id_and_preserves_sse_headers(task_session, monkeypatch):
    user = await _user(task_session, 1310, "stream-http-owner")
    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=user.id)
    run = await runtime.create_run(session_id=agent_session.id, user_id=user.id)
    first = await runtime.append_event(
        run_id=run.id, user_id=user.id, event_type="run_started", summary="first", data={"phase": "observe"}
    )
    second = await runtime.append_work_trace_delta(
        run_id=run.id,
        user_id=user.id,
        trace_id="trace-http",
        phase="act",
        kind="tool",
        message="HTTP 层回放公开轨迹",
        progress=50,
    )
    await runtime.update_run(run_id=run.id, user_id=user.id, status="completed", progress=100)
    terminal = await runtime.append_event(
        run_id=run.id, user_id=user.id, event_type="run_completed", summary="done", data={"phase": "finish"}
    )

    monkeypatch.setattr(agent_router, "AsyncSessionLocal", async_sessionmaker(task_session.bind, expire_on_commit=False))

    async def override_current_user():
        return SimpleNamespace(id=user.id)

    app.dependency_overrides[get_current_user] = override_current_user
    try:
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)
        async with httpx.AsyncClient(transport=transport, base_url="http://agent-http") as client:
            response = await client.get(
                f"/api/agent/sessions/{agent_session.id}/runs/{run.id}/stream?after_sequence=0",
                headers={"Last-Event-ID": str(first.sequence)},
            )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["cache-control"] == "no-cache"
        assert response.headers["x-accel-buffering"] == "no"
        assert f"id: {first.sequence}" not in response.text
        assert f"id: {second.sequence}" in response.text
        assert f"id: {terminal.sequence}" in response.text
        assert "event: work_trace_delta" in response.text
        assert "HTTP 层回放公开轨迹" in response.text
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_agent_stream_http_returns_scope_error_before_streaming_response(task_session, monkeypatch):
    user = await _user(task_session, 1311, "stream-http-scope-owner")
    runtime = AgentRuntimeService(task_session)
    first_session = await runtime.create_session(user_id=user.id)
    second_session = await runtime.create_session(user_id=user.id)
    run = await runtime.create_run(session_id=second_session.id, user_id=user.id)

    monkeypatch.setattr(agent_router, "AsyncSessionLocal", async_sessionmaker(task_session.bind, expire_on_commit=False))

    async def override_current_user():
        return SimpleNamespace(id=user.id)

    app.dependency_overrides[get_current_user] = override_current_user
    try:
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)
        async with httpx.AsyncClient(transport=transport, base_url="http://agent-http") as client:
            response = await client.get(
                f"/api/agent/sessions/{first_session.id}/runs/{run.id}/stream"
            )

        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "AGENT_SCOPE_VIOLATION"
        assert response.headers.get("content-type", "").startswith("application/json")
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_agent_stream_http_rejects_unknown_run_without_opening_sse(task_session, monkeypatch):
    user = await _user(task_session, 1312, "stream-http-missing-owner")
    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=user.id)

    monkeypatch.setattr(agent_router, "AsyncSessionLocal", async_sessionmaker(task_session.bind, expire_on_commit=False))

    async def override_current_user():
        return SimpleNamespace(id=user.id)

    app.dependency_overrides[get_current_user] = override_current_user
    try:
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)
        async with httpx.AsyncClient(transport=transport, base_url="http://agent-http") as client:
            response = await client.get(
                f"/api/agent/sessions/{agent_session.id}/runs/missing-run/stream"
            )

        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "AGENT_NOT_FOUND"
    finally:
        app.dependency_overrides.pop(get_current_user, None)
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("last_event_id", "expected_sequences"),
    [
        ("", [1, 2]),
        ("   ", [1, 2]),
        ("bad-header", [1, 2]),
        ("-1", [1, 2]),
        ("+10", [1, 2]),
        ("2_147_483_648", [1, 2]),
        ("0", [1, 2]),
    ],
)
async def test_agent_stream_http_normalizes_invalid_last_event_id(
    task_session, monkeypatch, last_event_id: str, expected_sequences: list[int]
):
    user = await _user(task_session, 1330 + len(expected_sequences), f"stream-http-cursor-{len(expected_sequences)}")
    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=user.id)
    run = await runtime.create_run(session_id=agent_session.id, user_id=user.id)
    await runtime.append_event(
        run_id=run.id, user_id=user.id, event_type="run_started", summary="first", data={"phase": "observe"}
    )
    await runtime.update_run(run_id=run.id, user_id=user.id, status="completed", progress=100)
    await runtime.append_event(
        run_id=run.id, user_id=user.id, event_type="run_completed", summary="done", data={"phase": "finish"}
    )

    monkeypatch.setattr(agent_router, "AsyncSessionLocal", async_sessionmaker(task_session.bind, expire_on_commit=False))

    async def override_current_user():
        return SimpleNamespace(id=user.id)

    app.dependency_overrides[get_current_user] = override_current_user
    try:
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)
        async with httpx.AsyncClient(transport=transport, base_url="http://agent-http") as client:
            response = await client.get(
                f"/api/agent/sessions/{agent_session.id}/runs/{run.id}/stream?after_sequence=0",
                headers={"Last-Event-ID": last_event_id},
            )

        assert response.status_code == 200
        emitted = [
            int(line.removeprefix("id: "))
            for line in response.text.splitlines()
            if line.startswith("id: ")
        ]
        assert emitted == expected_sequences
    finally:
        app.dependency_overrides.pop(get_current_user, None)
@pytest.mark.asyncio
async def test_agent_stream_http_maps_preflight_database_failure_to_retryable_503(task_session, monkeypatch):
    class BrokenSession:
        async def __aenter__(self):
            raise SQLAlchemyError("driver secret should not be returned")

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(agent_router, "AsyncSessionLocal", lambda: BrokenSession())

    async def override_current_user():
        return SimpleNamespace(id=1313)

    app.dependency_overrides[get_current_user] = override_current_user
    try:
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)
        async with httpx.AsyncClient(transport=transport, base_url="http://agent-http") as client:
            response = await client.get(
                "/api/agent/sessions/session-missing-from-broken-db/runs/run-missing-from-broken-db/stream"
            )

        assert response.status_code == 503
        detail = response.json()["detail"]
        assert detail["code"] == "AGENT_EVENT_LEDGER_UNAVAILABLE"
        assert "driver secret" not in response.text
        assert response.headers.get("content-type", "").startswith("application/json")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

@pytest.mark.asyncio
async def test_agent_stream_emits_redacted_retryable_error_when_ledger_fails_during_poll(task_session, monkeypatch):
    user = await _user(task_session, 1314, "stream-ledger-error-owner")
    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=user.id)
    run = await runtime.create_run(session_id=agent_session.id, user_id=user.id)

    monkeypatch.setattr(agent_router, "AsyncSessionLocal", async_sessionmaker(task_session.bind, expire_on_commit=False))

    async def broken_list_events(self, *, run_id, user_id, after_sequence=0, limit=500):
        raise SQLAlchemyError("raw database driver details")

    monkeypatch.setattr(AgentRuntimeService, "list_events", broken_list_events)

    async def is_disconnected():
        return False

    response = await agent_router.stream_agent_events(
        agent_session.id,
        run.id,
        SimpleNamespace(headers={}, is_disconnected=is_disconnected),
        after_sequence=7,
        current_user=SimpleNamespace(id=user.id),
    )
    body = "".join(
        [
            chunk.decode() if isinstance(chunk, bytes) else chunk
            async for chunk in response.body_iterator
        ]
    )

    assert "event: stream_error" in body
    assert "AGENT_EVENT_LEDGER_UNAVAILABLE" in body
    assert '"retryable": true' in body
    assert '"cursor": 7' in body
    assert "raw database driver details" not in body


@pytest.mark.asyncio
async def test_agent_event_ledger_http_routes_map_database_failures_to_redacted_503(task_session, monkeypatch):
    user = await _user(task_session, 1315, "event-ledger-http-owner")
    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=user.id)
    run = await runtime.create_run(session_id=agent_session.id, user_id=user.id)

    async def override_session():
        yield task_session

    async def override_current_user():
        return SimpleNamespace(id=user.id)

    async def broken_list_events(self, *, run_id, user_id, after_sequence=0, limit=500):
        raise SQLAlchemyError("raw database password=should-not-leak")

    monkeypatch.setattr(AgentRuntimeService, "list_events", broken_list_events)
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = override_current_user
    try:
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)
        async with httpx.AsyncClient(transport=transport, base_url="http://agent-http") as client:
            events_response = await client.get(
                f"/api/agent/sessions/{agent_session.id}/runs/{run.id}/events"
            )
            activity_response = await client.get(f"/api/agent/runs/{run.id}/activity")

        for response in (events_response, activity_response):
            assert response.status_code == 503
            detail = response.json()["detail"]
            assert detail["code"] == "AGENT_EVENT_LEDGER_UNAVAILABLE"
            assert detail["message"] == "Agent 事件账本暂时不可用，请稍后重连。"
            assert isinstance(detail.get("request_id"), str) and detail["request_id"]
            assert "password=should-not-leak" not in response.text
            assert response.headers.get("content-type", "").startswith("application/json")
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_agent_event_ledger_endpoints_require_current_user_before_accessing_storage():
    local_app = FastAPI()
    local_app.include_router(agent_router.router)

    async def reject_user():
        raise HTTPException(status_code=401, detail={"code": "AUTH_REQUIRED"})

    local_app.dependency_overrides[get_current_user] = reject_user
    transport = httpx.ASGITransport(app=local_app, raise_app_exceptions=True)
    async with httpx.AsyncClient(transport=transport, base_url="http://agent-auth") as client:
        events_response = await client.get("/api/agent/sessions/session-1/runs/run-1/events")
        activity_response = await client.get("/api/agent/runs/run-1/activity")
        stream_response = await client.get("/api/agent/sessions/session-1/runs/run-1/stream")

    for response in (events_response, activity_response, stream_response):
        assert response.status_code == 401
        assert response.json()["detail"] == {"code": "AUTH_REQUIRED"}
