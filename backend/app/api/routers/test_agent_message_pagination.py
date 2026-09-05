from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.agent.schemas import AgentSessionCreateRequest
from app.api.routers.agent import get_agent_session, list_agent_session_messages
from app.models import NovelProject, ProjectMember, User
from app.models.project_member import ProjectMemberRole
from app.services.agent_runtime import AgentRuntimeService


async def _user(session, user_id: int, name: str) -> User:
    user = User(id=user_id, username=name, email=f"{name}@example.com", hashed_password="x", is_active=True)
    session.add(user)
    await session.flush()
    return user


@pytest.mark.asyncio
async def test_session_messages_page_returns_latest_history_in_order_and_cursor(task_session):
    owner = await _user(task_session, 98301, "message-page-owner")
    runtime = AgentRuntimeService(task_session)
    session = await runtime.create_session(user_id=owner.id, title="分页会话")
    for index in range(1, 7):
        await runtime.append_message(session_id=session.id, user_id=owner.id, role="user", content=f"消息 {index}")

    page = await list_agent_session_messages(
        session.id,
        limit=3,
        before_sequence=None,
        session=task_session,
        current_user=SimpleNamespace(id=owner.id),
    )
    assert [item.sequence for item in page.items] == [4, 5, 6]
    assert page.has_more is True
    assert page.next_cursor == 4

    older = await list_agent_session_messages(
        session.id,
        limit=3,
        before_sequence=page.next_cursor,
        session=task_session,
        current_user=SimpleNamespace(id=owner.id),
    )
    assert [item.sequence for item in older.items] == [1, 2, 3]
    assert older.has_more is False
    assert older.next_cursor is None


@pytest.mark.asyncio
async def test_session_messages_page_clamps_limit_and_keeps_empty_tail(task_session):
    owner = await _user(task_session, 98302, "message-page-empty")
    runtime = AgentRuntimeService(task_session)
    session = await runtime.create_session(user_id=owner.id, title="空尾页")
    for index in range(1, 4):
        await runtime.append_message(session_id=session.id, user_id=owner.id, role="assistant", content=f"回复 {index}")

    page = await list_agent_session_messages(
        session.id,
        limit=999,
        before_sequence=1,
        session=task_session,
        current_user=SimpleNamespace(id=owner.id),
    )
    assert page.items == []
    assert page.has_more is False
    assert page.next_cursor is None


@pytest.mark.asyncio
async def test_session_messages_page_reuses_member_scope_and_legacy_detail_shape(task_session):
    owner = await _user(task_session, 98303, "message-page-project-owner")
    editor = await _user(task_session, 98304, "message-page-project-editor")
    outsider = await _user(task_session, 98305, "message-page-project-outsider")
    project = NovelProject(id="message-page-project", user_id=owner.id, title="消息分页项目")
    task_session.add_all([
        project,
        ProjectMember(project_id=project.id, user_id=owner.id, role=ProjectMemberRole.owner.value),
        ProjectMember(project_id=project.id, user_id=editor.id, role=ProjectMemberRole.editor.value),
    ])
    await task_session.flush()
    runtime = AgentRuntimeService(task_session)
    session = await runtime.create_session(user_id=owner.id, project_id=project.id, title="共享会话")
    await runtime.append_message(session_id=session.id, user_id=owner.id, role="user", content="共享消息")

    member_page = await list_agent_session_messages(
        session.id,
        limit=60,
        before_sequence=None,
        session=task_session,
        current_user=SimpleNamespace(id=editor.id),
    )
    assert [item.content for item in member_page.items] == ["共享消息"]

    legacy = await get_agent_session(session.id, session=task_session, current_user=SimpleNamespace(id=owner.id))
    assert isinstance(legacy.messages, list)
    assert isinstance(legacy.runs, list)

    with pytest.raises(HTTPException) as error:
        await list_agent_session_messages(
            session.id,
            limit=60,
            before_sequence=None,
            session=task_session,
            current_user=SimpleNamespace(id=outsider.id),
        )
    assert error.value.status_code == 403

