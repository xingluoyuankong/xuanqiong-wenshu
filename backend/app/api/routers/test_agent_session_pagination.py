from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.routers import agent
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
