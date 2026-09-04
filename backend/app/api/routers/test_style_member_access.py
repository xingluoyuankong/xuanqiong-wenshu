from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from app.api.routers import style as style_router
from app.core.dependencies import get_current_user
from app.db.session import get_session
from app.main import app
from app.models import NovelProject, ProjectMember, ProjectMemberRole, User


class _FakeStyleRAGService:
    cleared_projects: list[str] = []

    def __init__(self, *_args, **_kwargs):
        pass

    async def get_style_summary(self, project_id: str, _user_id: int):
        return {
            "has_style": False,
            "summary": {"project_id": project_id},
            "source": None,
        }

    async def clear_style_for_project(self, project_id: str):
        self.cleared_projects.append(project_id)


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
def http_client(task_session, monkeypatch):
    current_user = {"user": None}
    _FakeStyleRAGService.cleared_projects = []
    monkeypatch.setattr(style_router, "StyleRAGService", _FakeStyleRAGService)

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
        async with httpx.AsyncClient(transport=transport, base_url="http://style-member-access") as client:
            return await client.request(method, url, **kwargs)

    yield request
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_current_user, None)


async def _project_with_members(task_session, suffix: str):
    owner = await _user(task_session, 9411, f"style-owner-{suffix}")
    viewer = await _user(task_session, 9412, f"style-viewer-{suffix}")
    editor = await _user(task_session, 9413, f"style-editor-{suffix}")
    outsider = await _user(task_session, 9414, f"style-outsider-{suffix}")
    project = NovelProject(id=f"style-member-{suffix}", user_id=owner.id, title="文风成员权限")
    task_session.add_all(
        [
            project,
            ProjectMember(project_id=project.id, user_id=viewer.id, role=ProjectMemberRole.viewer.value),
            ProjectMember(project_id=project.id, user_id=editor.id, role=ProjectMemberRole.editor.value),
        ]
    )
    await task_session.commit()
    return owner, viewer, editor, outsider, project


@pytest.mark.asyncio
async def test_style_routes_allow_viewer_read_and_reject_nonmember(task_session, http_client):
    _owner, viewer, _editor, outsider, project = await _project_with_members(task_session, "read")

    viewer_read = await http_client("GET", f"/api/projects/{project.id}/style", user=viewer)
    assert viewer_read.status_code == 200
    assert viewer_read.json()["summary"] == {"project_id": project.id}

    outsider_read = await http_client("GET", f"/api/projects/{project.id}/style", user=outsider)
    assert outsider_read.status_code == 403


@pytest.mark.asyncio
async def test_style_routes_reject_viewer_write_and_allow_editor_write(task_session, http_client):
    _owner, viewer, editor, outsider, project = await _project_with_members(task_session, "write")

    viewer_write = await http_client("DELETE", f"/api/projects/{project.id}/style", user=viewer)
    assert viewer_write.status_code == 403

    outsider_write = await http_client("DELETE", f"/api/projects/{project.id}/style", user=outsider)
    assert outsider_write.status_code == 403

    editor_write = await http_client("DELETE", f"/api/projects/{project.id}/style", user=editor)
    assert editor_write.status_code == 200
    assert editor_write.json()["success"] is True
    assert _FakeStyleRAGService.cleared_projects == [project.id]
