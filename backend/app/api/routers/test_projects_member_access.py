from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from app.core.dependencies import get_current_user
from app.db.session import get_session
from app.main import app
from app.models import NovelProject, ProjectMember, ProjectMemberRole, User


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
    current_user = {"user": None}

    async def override_session():
        yield task_session

    async def override_current_user():
        return current_user["user"]

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = override_current_user
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)

    async def request(method: str, url: str, *, user: User, **kwargs):
        current_user["user"] = SimpleNamespace(
            id=user.id,
            is_admin=bool(user.is_admin),
            is_active=bool(user.is_active),
        )
        async with httpx.AsyncClient(transport=transport, base_url="http://projects-member-access") as client:
            return await client.request(method, url, **kwargs)

    yield request
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_projects_routes_allow_viewer_read_and_reject_nonmember(task_session, http_client):
    owner = await _user(task_session, 6101, "projects-access-owner")
    viewer = await _user(task_session, 6102, "projects-access-viewer")
    outsider = await _user(task_session, 6103, "projects-access-outsider")
    project = NovelProject(id="projects-member-read", user_id=owner.id, title="成员读取项目资源")
    task_session.add_all(
        [
            project,
            ProjectMember(project_id=project.id, user_id=viewer.id, role=ProjectMemberRole.viewer.value),
        ]
    )
    await task_session.commit()

    viewer_read = await http_client("GET", f"/api/projects/{project.id}/memory", user=viewer)
    assert viewer_read.status_code == 200
    assert viewer_read.json() == {"project_id": project.id, "memory": None}

    outsider_read = await http_client("GET", f"/api/projects/{project.id}/memory", user=outsider)
    assert outsider_read.status_code == 403


@pytest.mark.asyncio
async def test_projects_routes_reject_viewer_write_and_allow_editor_write(task_session, http_client):
    owner = await _user(task_session, 6201, "projects-write-owner")
    viewer = await _user(task_session, 6202, "projects-write-viewer")
    editor = await _user(task_session, 6203, "projects-write-editor")
    outsider = await _user(task_session, 6204, "projects-write-outsider")
    project = NovelProject(id="projects-member-write", user_id=owner.id, title="成员写入项目资源")
    task_session.add_all(
        [
            project,
            ProjectMember(project_id=project.id, user_id=viewer.id, role=ProjectMemberRole.viewer.value),
            ProjectMember(project_id=project.id, user_id=editor.id, role=ProjectMemberRole.editor.value),
        ]
    )
    await task_session.commit()

    payload = {"global_summary": "Editor 已更新项目记忆"}
    viewer_write = await http_client("PUT", f"/api/projects/{project.id}/memory", user=viewer, json=payload)
    assert viewer_write.status_code == 403

    outsider_write = await http_client("PUT", f"/api/projects/{project.id}/memory", user=outsider, json=payload)
    assert outsider_write.status_code == 403

    editor_write = await http_client("PUT", f"/api/projects/{project.id}/memory", user=editor, json=payload)
    assert editor_write.status_code == 200
    assert editor_write.json()["memory"]["global_summary"] == payload["global_summary"]
