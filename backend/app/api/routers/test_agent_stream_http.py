from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.routers import agent as agent_router
from app.core.dependencies import get_current_user
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
