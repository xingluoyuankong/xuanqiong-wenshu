from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from app.api.routers import outline
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
        async with httpx.AsyncClient(transport=transport, base_url="http://research-outline-member-access") as client:
            return await client.request(method, url, **kwargs)

    yield request
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_current_user, None)


class _NoopLLMService:
    def __init__(self, _session):
        pass


class _OutlineEvolutionService:
    def __init__(self, _session, _llm_service):
        pass

    async def select_alternative(self, *, project_id: str, selected_option_id: int, user_id: int):
        return SimpleNamespace(
            title=f"成员编辑后的大纲-{selected_option_id}",
            summary=f"项目 {project_id} 由用户 {user_id} 更新",
        )


@pytest.fixture
def outline_write_service(monkeypatch):
    monkeypatch.setattr(outline, "LLMService", _NoopLLMService)
    monkeypatch.setattr(outline, "OutlineEvolutionService", _OutlineEvolutionService)


@pytest.mark.asyncio
async def test_research_routes_apply_member_read_write_matrix(task_session, http_client):
    owner = await _user(task_session, 8101, "research-access-owner")
    viewer = await _user(task_session, 8102, "research-access-viewer")
    editor = await _user(task_session, 8103, "research-access-editor")
    outsider = await _user(task_session, 8104, "research-access-outsider")
    project = NovelProject(id="research-member-access", user_id=owner.id, title="研究成员权限")
    task_session.add_all(
        [
            project,
            ProjectMember(project_id=project.id, user_id=viewer.id, role=ProjectMemberRole.viewer.value),
            ProjectMember(project_id=project.id, user_id=editor.id, role=ProjectMemberRole.editor.value),
        ]
    )
    await task_session.commit()

    viewer_read = await http_client("GET", f"/api/projects/{project.id}/research/config", user=viewer)
    assert viewer_read.status_code == 200
    assert viewer_read.json()["project_id"] == project.id

    outsider_read = await http_client("GET", f"/api/projects/{project.id}/research/config", user=outsider)
    assert outsider_read.status_code == 403

    payload = {"mode": "auto", "enabled": True, "max_parallel_queries": 3}
    viewer_write = await http_client("PUT", f"/api/projects/{project.id}/research/config", user=viewer, json=payload)
    assert viewer_write.status_code == 403

    outsider_write = await http_client("PUT", f"/api/projects/{project.id}/research/config", user=outsider, json=payload)
    assert outsider_write.status_code == 403

    editor_write = await http_client("PUT", f"/api/projects/{project.id}/research/config", user=editor, json=payload)
    assert editor_write.status_code == 200
    assert editor_write.json()["max_parallel_queries"] == payload["max_parallel_queries"]


@pytest.mark.asyncio
async def test_outline_routes_apply_member_read_write_matrix(task_session, http_client, outline_write_service):
    owner = await _user(task_session, 8201, "outline-access-owner")
    viewer = await _user(task_session, 8202, "outline-access-viewer")
    editor = await _user(task_session, 8203, "outline-access-editor")
    outsider = await _user(task_session, 8204, "outline-access-outsider")
    project = NovelProject(id="outline-member-access", user_id=owner.id, title="大纲成员权限")
    task_session.add_all(
        [
            project,
            ProjectMember(project_id=project.id, user_id=viewer.id, role=ProjectMemberRole.viewer.value),
            ProjectMember(project_id=project.id, user_id=editor.id, role=ProjectMemberRole.editor.value),
        ]
    )
    await task_session.commit()

    viewer_read = await http_client("GET", f"/api/novels/{project.id}/outline/structure", user=viewer)
    assert viewer_read.status_code == 200
    assert viewer_read.json()["project_id"] == project.id

    outsider_read = await http_client("GET", f"/api/novels/{project.id}/outline/structure", user=outsider)
    assert outsider_read.status_code == 403

    payload = {"option_id": 7, "chapter_number": 1}
    viewer_write = await http_client("POST", f"/api/novels/{project.id}/outline/next", user=viewer, json=payload)
    assert viewer_write.status_code == 403

    outsider_write = await http_client("POST", f"/api/novels/{project.id}/outline/next", user=outsider, json=payload)
    assert outsider_write.status_code == 403

    editor_write = await http_client("POST", f"/api/novels/{project.id}/outline/next", user=editor, json=payload)
    assert editor_write.status_code == 200
    assert editor_write.json()["updated_outline"]["title"] == "成员编辑后的大纲-7"
