from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from app.api.routers import analytics_enhanced
from app.core.dependencies import get_current_user
from app.db.session import get_session
from app.main import app
from app.models import NovelProject, ProjectMember, ProjectMemberRole, User


class _CacheStub:
    async def delete(self, _key: str) -> bool:
        return True


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
        async with httpx.AsyncClient(transport=transport, base_url="http://knowledge-analytics-member-access") as client:
            return await client.request(method, url, **kwargs)

    yield request
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_viewer_reads_knowledge_graph_and_analytics_but_cannot_mutate(
    task_session,
    http_client,
    monkeypatch,
):
    owner = await _user(task_session, 7101, "knowledge-analytics-owner")
    viewer = await _user(task_session, 7102, "knowledge-analytics-viewer")
    project = NovelProject(id="knowledge-analytics-viewer", user_id=owner.id, title="成员分析读取")
    task_session.add_all(
        [
            project,
            ProjectMember(project_id=project.id, user_id=viewer.id, role=ProjectMemberRole.viewer.value),
        ]
    )
    await task_session.commit()
    monkeypatch.setattr(analytics_enhanced, "CacheService", _CacheStub)

    graph = await http_client("GET", f"/api/projects/{project.id}/knowledge-graph/nodes", user=viewer)
    assert graph.status_code == 200
    assert graph.json() == []

    emotion_curve = await http_client("GET", f"/api/analytics/{project.id}/emotion-curve", user=viewer)
    assert emotion_curve.status_code == 200
    assert emotion_curve.json()["project_id"] == project.id
    assert emotion_curve.json()["total_chapters"] == 0

    enhanced_curve = await http_client(
        "GET",
        f"/api/analytics/projects/{project.id}/emotion-curve-enhanced?use_cache=false",
        user=viewer,
    )
    assert enhanced_curve.status_code == 200
    assert enhanced_curve.json() == []

    graph_write = await http_client(
        "POST",
        f"/api/projects/{project.id}/knowledge-graph/nodes",
        user=viewer,
        json={"name": "Viewer 不可写"},
    )
    assert graph_write.status_code == 403

    cache_write = await http_client(
        "POST",
        f"/api/analytics/projects/{project.id}/invalidate-cache",
        user=viewer,
    )
    assert cache_write.status_code == 403


@pytest.mark.asyncio
async def test_editor_mutates_graph_and_analysis_cache_while_nonmember_is_denied(
    task_session,
    http_client,
    monkeypatch,
):
    owner = await _user(task_session, 7201, "knowledge-analytics-owner-2")
    editor = await _user(task_session, 7202, "knowledge-analytics-editor")
    outsider = await _user(task_session, 7203, "knowledge-analytics-outsider")
    project = NovelProject(id="knowledge-analytics-editor", user_id=owner.id, title="成员分析写入")
    task_session.add_all(
        [
            project,
            ProjectMember(project_id=project.id, user_id=editor.id, role=ProjectMemberRole.editor.value),
        ]
    )
    await task_session.commit()
    monkeypatch.setattr(analytics_enhanced, "CacheService", _CacheStub)

    editor_graph_write = await http_client(
        "POST",
        f"/api/projects/{project.id}/knowledge-graph/nodes",
        user=editor,
        json={"name": "Editor 可写"},
    )
    assert editor_graph_write.status_code == 200
    assert editor_graph_write.json()["name"] == "Editor 可写"

    editor_cache_write = await http_client(
        "POST",
        f"/api/analytics/projects/{project.id}/invalidate-cache",
        user=editor,
    )
    assert editor_cache_write.status_code == 200
    assert editor_cache_write.json()["project_id"] == project.id

    outsider_graph = await http_client("GET", f"/api/projects/{project.id}/knowledge-graph/nodes", user=outsider)
    assert outsider_graph.status_code == 403

    outsider_analytics = await http_client("GET", f"/api/analytics/{project.id}/foreshadowing", user=outsider)
    assert outsider_analytics.status_code == 403

    outsider_enhanced = await http_client(
        "GET",
        f"/api/analytics/projects/{project.id}/emotion-curve-enhanced?use_cache=false",
        user=outsider,
    )
    assert outsider_enhanced.status_code == 403
