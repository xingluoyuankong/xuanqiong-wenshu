from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException

from app.api.routers import agent
from app.core.security import create_access_token
from app.db.session import get_session
from app.main import app
from app.agent.schemas import AgentMessagePageRead, AgentSessionRunPageRead
from app.models import AgentMessage, AgentRun, NovelProject, ProjectMember, User
from app.models.project_member import ProjectMemberRole
from app.services.agent_runtime import AgentRuntimeService


async def _user(session, user_id: int, name: str) -> User:
    user = User(id=user_id, username=name, email=f"{name}@example.com", hashed_password="x", is_active=True)
    session.add(user)
    await session.flush()
    return user


@pytest.mark.asyncio
async def test_session_message_page_returns_latest_messages_then_older_cursor_pages(task_session):
    owner = await _user(task_session, 99401, "session-page-owner")
    project = NovelProject(id="session-page-project", user_id=owner.id, title="Session page")
    task_session.add(project)
    await task_session.flush()
    runtime = AgentRuntimeService(task_session)
    session = await runtime.create_session(user_id=owner.id, project_id=project.id)
    for index in range(1, 6):
        await runtime.append_message(session_id=session.id, user_id=owner.id, role="user", content=f"消息 {index}")

    page = await agent.list_agent_session_messages(
        session.id, limit=3, session=task_session, current_user=SimpleNamespace(id=owner.id)
    )
    assert isinstance(page, AgentMessagePageRead)
    assert [item.sequence for item in page.items] == [3, 4, 5]
    assert page.total == 5
    assert page.has_more is True
    assert page.next_cursor == 3

    older = await agent.list_agent_session_messages(
        session.id,
        limit=3,
        before_sequence=page.next_cursor,
        session=task_session,
        current_user=SimpleNamespace(id=owner.id),
    )
    assert [item.sequence for item in older.items] == [1, 2]
    assert older.has_more is False
    assert older.next_cursor is None


@pytest.mark.asyncio
async def test_session_run_page_uses_created_at_and_id_cursor_and_old_detail_flags(task_session):
    owner = await _user(task_session, 99402, "session-run-owner")
    project = NovelProject(id="session-run-project", user_id=owner.id, title="Session runs")
    task_session.add(project)
    await task_session.flush()
    runtime = AgentRuntimeService(task_session)
    session = await runtime.create_session(user_id=owner.id, project_id=project.id)
    runs = []
    base = datetime(2026, 9, 5, 1, 0, tzinfo=timezone.utc)
    for index in range(3):
        run = await runtime.create_run(session_id=session.id, user_id=owner.id, project_id=project.id, commit=False)
        run.id = f"session-run-{index + 1}"
        run.created_at = base + timedelta(seconds=index)
        runs.append(run)
    await task_session.commit()

    page = await agent.list_agent_session_runs(
        session.id, limit=2, session=task_session, current_user=SimpleNamespace(id=owner.id)
    )
    assert isinstance(page, AgentSessionRunPageRead)
    assert [item.id for item in page.items] == ["session-run-2", "session-run-3"]
    assert page.has_more is True
    assert page.next_before_id == "session-run-2"
    assert page.next_before_created_at is not None

    older = await agent.list_agent_session_runs(
        session.id,
        limit=2,
        before_created_at=page.next_before_created_at,
        before_id=page.next_before_id,
        session=task_session,
        current_user=SimpleNamespace(id=owner.id),
    )
    assert [item.id for item in older.items] == ["session-run-1"]
    assert older.has_more is False

    detail = await agent.get_agent_session(
        session.id,
        include_messages=False,
        include_runs=False,
        session=task_session,
        current_user=SimpleNamespace(id=owner.id),
    )
    assert detail.messages == []
    assert detail.runs == []


@pytest.mark.asyncio
async def test_session_detail_http_defaults_keep_legacy_payload_and_flags_are_independent(task_session):
    owner = await _user(task_session, 99409, "session-detail-contract-owner")
    project = NovelProject(id="session-detail-contract-project", user_id=owner.id, title="Detail contract")
    task_session.add(project)
    await task_session.flush()
    runtime = AgentRuntimeService(task_session)
    session = await runtime.create_session(user_id=owner.id, project_id=project.id)
    await runtime.append_message(session_id=session.id, user_id=owner.id, role="user", content="合同消息 1")
    await runtime.append_message(session_id=session.id, user_id=owner.id, role="assistant", content="合同消息 2")
    run = await runtime.create_run(session_id=session.id, user_id=owner.id, project_id=project.id)

    async def override_session():
        yield task_session

    app.dependency_overrides[get_session] = override_session
    try:
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)
        async with httpx.AsyncClient(transport=transport, base_url="http://agent-session-detail-contract") as client:
            headers = {"Authorization": f"Bearer {create_access_token(str(owner.id))}"}

            legacy = await client.get(f"/api/agent/sessions/{session.id}", headers=headers)
            assert legacy.status_code == 200
            legacy_payload = legacy.json()
            assert [item["content"] for item in legacy_payload["messages"]] == ["合同消息 1", "合同消息 2"]
            assert [item["id"] for item in legacy_payload["runs"]] == [run.id]

            compact = await client.get(
                f"/api/agent/sessions/{session.id}?include_messages=false&include_runs=false",
                headers=headers,
            )
            assert compact.status_code == 200
            assert compact.json()["messages"] == []
            assert compact.json()["runs"] == []

            messages_only = await client.get(
                f"/api/agent/sessions/{session.id}?include_runs=false",
                headers=headers,
            )
            assert messages_only.status_code == 200
            assert len(messages_only.json()["messages"]) == 2
            assert messages_only.json()["runs"] == []

            runs_only = await client.get(
                f"/api/agent/sessions/{session.id}?include_messages=false",
                headers=headers,
            )
            assert runs_only.status_code == 200
            assert runs_only.json()["messages"] == []
            assert [item["id"] for item in runs_only.json()["runs"]] == [run.id]
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.mark.asyncio
async def test_legacy_detail_message_limit_and_run_unbounded_risk_are_visible_against_pages(task_session):
    owner = await _user(task_session, 99410, "session-detail-long-owner")
    runtime = AgentRuntimeService(task_session)
    session = await runtime.create_session(user_id=owner.id)
    task_session.add_all([
        AgentMessage(
            id=str(uuid4()),
            session_id=session.id,
            user_id=owner.id,
            role="user",
            content=f"长消息 {sequence}",
            sequence=sequence,
        )
        for sequence in range(1, 202)
    ])
    task_session.add_all([
        AgentRun(
            id=str(uuid4()),
            session_id=session.id,
            user_id=owner.id,
            project_id=None,
            correlation_id=str(uuid4()),
            transaction_id=str(uuid4()),
            status="created",
            context_json={},
        )
        for _ in range(101)
    ])
    await task_session.commit()

    detail = await agent.get_agent_session(
        session.id,
        session=task_session,
        current_user=SimpleNamespace(id=owner.id),
    )
    # The compatibility detail path retains the service's historical 200-row
    # message bound, while its direct Run query currently has no row bound.
    assert len(detail.messages) == 200
    assert [item.sequence for item in detail.messages] == list(range(1, 201))
    assert len(detail.runs) == 101

    page = await agent.list_agent_session_messages(
        session.id,
        limit=60,
        session=task_session,
        current_user=SimpleNamespace(id=owner.id),
    )
    assert page.total == 201
    assert [item.sequence for item in page.items] == list(range(142, 202))
    assert page.has_more is True
    assert page.next_cursor == 142


@pytest.mark.asyncio
async def test_session_pages_keep_member_read_scope_and_projectless_privacy(task_session):
    owner = await _user(task_session, 99403, "session-scope-owner")
    viewer = await _user(task_session, 99404, "session-scope-viewer")
    outsider = await _user(task_session, 99405, "session-scope-outsider")
    project = NovelProject(id="session-scope-project", user_id=owner.id, title="Scope")
    task_session.add_all([
        project,
        ProjectMember(project_id=project.id, user_id=owner.id, role=ProjectMemberRole.owner.value),
        ProjectMember(project_id=project.id, user_id=viewer.id, role=ProjectMemberRole.viewer.value),
    ])
    await task_session.flush()
    runtime = AgentRuntimeService(task_session)
    shared = await runtime.create_session(user_id=owner.id, project_id=project.id)
    await runtime.append_message(session_id=shared.id, user_id=owner.id, role="assistant", content="共享消息")

    page = await agent.list_agent_session_messages(
        shared.id, session=task_session, current_user=SimpleNamespace(id=viewer.id)
    )
    assert page.items[0].content == "共享消息"
    with pytest.raises(HTTPException) as denied:
        await agent.list_agent_session_messages(
            shared.id, session=task_session, current_user=SimpleNamespace(id=outsider.id)
        )
    assert denied.value.status_code == 403

    private = await runtime.create_session(user_id=owner.id)
    await runtime.append_message(session_id=private.id, user_id=owner.id, role="user", content="私有消息")
    with pytest.raises(HTTPException) as private_denied:
        await agent.list_agent_session_messages(
            private.id, session=task_session, current_user=SimpleNamespace(id=outsider.id)
        )
    assert private_denied.value.status_code == 404


@pytest.mark.asyncio
async def test_session_message_page_http_uses_real_jwt_for_long_history_member_scope(task_session):
    owner = await _user(task_session, 99406, "session-http-owner")
    viewer = await _user(task_session, 99407, "session-http-viewer")
    outsider = await _user(task_session, 99408, "session-http-outsider")
    project = NovelProject(id="session-http-project", user_id=owner.id, title="HTTP session page")
    task_session.add_all([
        project,
        ProjectMember(project_id=project.id, user_id=owner.id, role=ProjectMemberRole.owner.value),
        ProjectMember(project_id=project.id, user_id=viewer.id, role=ProjectMemberRole.viewer.value),
    ])
    await task_session.commit()

    runtime = AgentRuntimeService(task_session)
    shared = await runtime.create_session(user_id=owner.id, project_id=project.id)
    for index in range(1, 126):
        await runtime.append_message(
            session_id=shared.id,
            user_id=owner.id,
            role="assistant" if index % 2 == 0 else "user",
            content=f"长历史消息 {index}",
        )
    private = await runtime.create_session(user_id=owner.id)
    await runtime.append_message(session_id=private.id, user_id=owner.id, role="user", content="projectless 私有消息")

    async def override_session():
        yield task_session

    app.dependency_overrides[get_session] = override_session
    try:
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)
        async with httpx.AsyncClient(transport=transport, base_url="http://agent-session-http") as client:
            viewer_headers = {"Authorization": f"Bearer {create_access_token(str(viewer.id))}"}
            outsider_headers = {"Authorization": f"Bearer {create_access_token(str(outsider.id))}"}

            newest = await client.get(
                f"/api/agent/sessions/{shared.id}/messages?limit=60",
                headers=viewer_headers,
            )
            assert newest.status_code == 200
            newest_payload = newest.json()
            assert [item["sequence"] for item in newest_payload["items"]] == list(range(66, 126))
            assert newest_payload["total"] == 125
            assert newest_payload["next_cursor"] == 66
            assert newest_payload["has_more"] is True

            older = await client.get(
                f"/api/agent/sessions/{shared.id}/messages?limit=60&before_sequence=66",
                headers=viewer_headers,
            )
            assert older.status_code == 200
            older_payload = older.json()
            assert [item["sequence"] for item in older_payload["items"]] == list(range(6, 66))
            assert older_payload["has_more"] is True
            assert older_payload["next_cursor"] == 6

            oldest = await client.get(
                f"/api/agent/sessions/{shared.id}/messages?limit=60&before_sequence=6",
                headers=viewer_headers,
            )
            assert oldest.status_code == 200
            oldest_payload = oldest.json()
            assert [item["sequence"] for item in oldest_payload["items"]] == list(range(1, 6))
            assert oldest_payload["has_more"] is False
            assert oldest_payload["next_cursor"] is None

            denied_shared = await client.get(
                f"/api/agent/sessions/{shared.id}/messages?limit=60",
                headers=outsider_headers,
            )
            assert denied_shared.status_code == 403
            assert denied_shared.json()["detail"]["code"] == "HTTP_403"

            denied_private = await client.get(
                f"/api/agent/sessions/{private.id}/messages?limit=60",
                headers=outsider_headers,
            )
            assert denied_private.status_code == 404
            assert denied_private.json()["detail"]["code"] == "AGENT_NOT_FOUND"
    finally:
        app.dependency_overrides.pop(get_session, None)
