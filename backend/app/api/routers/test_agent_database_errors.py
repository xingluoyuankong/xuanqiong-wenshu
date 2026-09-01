from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.agent.context_refs import ResolvedAgentContext
from app.agent.schemas import AgentMessageCreateRequest, AgentSessionCreateRequest
from app.api.routers import agent as agent_router
from app.core.dependencies import get_current_user
from app.db.session import get_session
from app.main import app
from app.services.agent_runtime import AgentRuntimeService


CURRENT_USER = SimpleNamespace(id=1971)


def _assert_ledger_503(error: pytest.ExceptionInfo[HTTPException]) -> None:
    assert error.value.status_code == 503
    assert error.value.detail["code"] == "AGENT_EVENT_LEDGER_UNAVAILABLE"
    assert "database driver" not in str(error.value.detail)


@pytest.mark.asyncio
async def test_agent_session_and_message_routes_map_sqlalchemy_failures_to_ledger_503(task_session, monkeypatch):
    async def broken_session(*args, **kwargs):
        raise SQLAlchemyError("database driver password=redacted")

    monkeypatch.setattr(AgentRuntimeService, "create_session", broken_session)
    with pytest.raises(HTTPException) as create_error:
        await agent_router.create_agent_session(
            AgentSessionCreateRequest(title="db failure"),
            session=task_session,
            current_user=CURRENT_USER,
        )
    _assert_ledger_503(create_error)

    monkeypatch.setattr(AgentRuntimeService, "list_sessions", broken_session)
    with pytest.raises(HTTPException) as list_error:
        await agent_router.list_agent_sessions(session=task_session, current_user=CURRENT_USER)
    _assert_ledger_503(list_error)

    monkeypatch.setattr(AgentRuntimeService, "get_session", broken_session)
    with pytest.raises(HTTPException) as get_error:
        await agent_router.get_agent_session("session-db-failure", session=task_session, current_user=CURRENT_USER)
    _assert_ledger_503(get_error)

    with pytest.raises(HTTPException) as message_error:
        await agent_router.post_agent_message(
            "session-db-failure",
            AgentMessageCreateRequest(content="trigger database failure"),
            session=task_session,
            current_user=CURRENT_USER,
        )
    _assert_ledger_503(message_error)


@pytest.mark.asyncio
async def test_agent_message_database_failure_rolls_back_started_transaction(monkeypatch):
    session = SimpleNamespace(rollback=AsyncMock())
    resolved = SimpleNamespace(refs=[], canonical_refs=lambda: [])

    async def load_session(*args, **kwargs):
        return SimpleNamespace(id="session-rollback", project_id=None)

    async def broken_append_message(*args, **kwargs):
        raise SQLAlchemyError("database driver password=must-not-leak")

    monkeypatch.setattr(AgentRuntimeService, "get_session", load_session)
    monkeypatch.setattr(AgentRuntimeService, "append_message", broken_append_message)
    async def resolve_context(**kwargs):
        return resolved

    monkeypatch.setattr(agent_router, "resolve_agent_context_refs", resolve_context)

    with pytest.raises(HTTPException) as error:
        await agent_router.post_agent_message(
            "session-rollback",
            AgentMessageCreateRequest(content="rollback this transaction"),
            session=session,
            current_user=CURRENT_USER,
        )

    _assert_ledger_503(error)
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_agent_database_failure_http_response_has_request_id_and_redacts_driver_text(task_session, monkeypatch):
    async def override_session():
        yield task_session

    async def override_current_user():
        return CURRENT_USER

    async def broken_create_session(*args, **kwargs):
        raise SQLAlchemyError("database driver password=must-not-leak")

    monkeypatch.setattr(AgentRuntimeService, "create_session", broken_create_session)
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = override_current_user
    try:
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)
        async with httpx.AsyncClient(transport=transport, base_url="http://agent-db-error") as client:
            response = await client.post("/api/agent/sessions", json={"title": "db error"})

        assert response.status_code == 503
        detail = response.json()["detail"]
        assert detail["code"] == "AGENT_EVENT_LEDGER_UNAVAILABLE"
        assert isinstance(detail.get("request_id"), str) and detail["request_id"]
        assert response.headers.get("x-request-id") == detail["request_id"]
        assert "password=must-not-leak" not in response.text
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(get_current_user, None)
