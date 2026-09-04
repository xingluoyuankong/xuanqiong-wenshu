from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from app.core.dependencies import get_current_user
from app.db.session import get_session
from app.main import app
from app.models import NovelProject, ProjectMember, ProjectMemberRole, User
from app.services.agent_runtime import AgentRuntimeService


async def _user(session, user_id: int, username: str) -> User:
    user = User(
        id=user_id,
        username=username,
        email=f"{username}@example.com",
        hashed_password="not-used-in-route-test",
        is_active=True,
    )
    session.add(user)
    await session.flush()
    return user


@pytest.fixture
def http_client(task_session):
    principal = {"user": None}

    async def override_session():
        yield task_session

    async def override_current_user():
        return principal["user"]

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = override_current_user
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)

    async def request(method: str, url: str, *, user: User, **kwargs):
        principal["user"] = SimpleNamespace(
            id=user.id,
            is_admin=bool(user.is_admin),
            is_active=bool(user.is_active),
        )
        async with httpx.AsyncClient(transport=transport, base_url="http://agent-member-http") as client:
            return await client.request(method, url, **kwargs)

    yield request
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_agent_http_allows_member_read_projection_and_rejects_outsider(task_session, http_client):
    owner = await _user(task_session, 7101, "agent-http-owner")
    viewer = await _user(task_session, 7102, "agent-http-viewer")
    outsider = await _user(task_session, 7103, "agent-http-outsider")
    project = NovelProject(id="agent-http-member-project", user_id=owner.id, title="Agent HTTP members")
    task_session.add_all([
        project,
        ProjectMember(project_id=project.id, user_id=owner.id, role=ProjectMemberRole.owner.value),
        ProjectMember(project_id=project.id, user_id=viewer.id, role=ProjectMemberRole.viewer.value),
    ])
    await task_session.commit()

    runtime = AgentRuntimeService(task_session)
    session = await runtime.create_session(user_id=owner.id, project_id=project.id)
    run = await runtime.create_run(session_id=session.id, user_id=owner.id, project_id=project.id)
    await runtime.append_assistant_reasoning_chunk(
        run_id=run.id,
        user_id=owner.id,
        chunk_index=0,
        content="member-readable reasoning",
    )
    await runtime.append_public_work_summary(
        run_id=run.id,
        user_id=owner.id,
        summary={"action_id": "member-read", "phase": "planning", "current_action": "读取上下文"},
    )

    for suffix in ("reasoning", "activity", "state"):
        response = await http_client("GET", f"/api/agent/runs/{run.id}/{suffix}", user=viewer)
        assert response.status_code == 200
        if suffix == "state":
            assert response.json()["user_id"] == owner.id
            assert response.json()["allowed_commands"] == []

    reasoning = await http_client("GET", f"/api/agent/runs/{run.id}/reasoning", user=viewer)
    assert reasoning.json()["items"][0]["content"] == "member-readable reasoning"

    for suffix in ("reasoning", "activity", "state"):
        response = await http_client("GET", f"/api/agent/runs/{run.id}/{suffix}", user=outsider)
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_agent_http_enforces_viewer_editor_project_write_matrix(task_session, http_client):
    owner = await _user(task_session, 7201, "agent-http-write-owner")
    viewer = await _user(task_session, 7202, "agent-http-write-viewer")
    editor = await _user(task_session, 7203, "agent-http-write-editor")
    project = NovelProject(id="agent-http-write-project", user_id=owner.id, title="Agent HTTP writes")
    task_session.add_all([
        project,
        ProjectMember(project_id=project.id, user_id=owner.id, role=ProjectMemberRole.owner.value),
        ProjectMember(project_id=project.id, user_id=viewer.id, role=ProjectMemberRole.viewer.value),
        ProjectMember(project_id=project.id, user_id=editor.id, role=ProjectMemberRole.editor.value),
    ])
    await task_session.commit()

    viewer_create = await http_client(
        "POST", "/api/agent/sessions", user=viewer, json={"project_id": project.id, "title": "viewer write"}
    )
    assert viewer_create.status_code == 403

    editor_create = await http_client(
        "POST", "/api/agent/sessions", user=editor, json={"project_id": project.id, "title": "editor write"}
    )
    assert editor_create.status_code == 201
    assert editor_create.json()["project_id"] == project.id
    assert editor_create.json()["user_id"] == editor.id
