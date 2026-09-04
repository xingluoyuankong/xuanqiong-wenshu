"""真实 HTTP/JWT Writer 成员验收的隔离回归测试。

测试通过 FastAPI ASGITransport 走真实路由、真实 JWT 登录和隔离会话，
不覆盖主 SQLite；生成类后台任务只在脚本中使用确定性桩，本文件聚焦
成员读取、项目成员接口、状态接口和 SSE cursor replay/隔离合同。
"""
from __future__ import annotations

from dataclasses import dataclass
import httpx
import pytest
from app.api.routers import writer
from app.core.dependencies import get_session
from app.db.base import Base
from app.db import session as db_session
from app.core.security import hash_password
from app.main import app
from app.models import Chapter, ChapterOutline, ChapterVersion, NovelProject, ProjectMember, User
from app.models.project_member import ProjectMemberRole
from app.models.task_runtime import TaskRuntime, TaskRuntimeEvent


PROJECT_ID = "http-member-acceptance-project"
OTHER_PROJECT_ID = "http-member-acceptance-other-project"
PASSWORD = "WriterAcceptance123!"


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_args):
        return False


@dataclass(frozen=True)
class Fixture:
    owner: User
    editor: User
    viewer: User
    admin: User
    outsider: User
    project: NovelProject
    other_project: NovelProject
    chapter: Chapter
    other_chapter: Chapter
    first_event: TaskRuntimeEvent
    terminal_event: TaskRuntimeEvent
    selected_version: ChapterVersion


async def _seed(session) -> Fixture:
    owner = User(id=98101, username="http-accept-owner", email="http-accept-owner@example.com", hashed_password=hash_password(PASSWORD), is_active=True)
    editor = User(id=98102, username="http-accept-editor", email="http-accept-editor@example.com", hashed_password=hash_password(PASSWORD), is_active=True)
    viewer = User(id=98103, username="http-accept-viewer", email="http-accept-viewer@example.com", hashed_password=hash_password(PASSWORD), is_active=True)
    admin = User(id=98104, username="http-accept-admin", email="http-accept-admin@example.com", hashed_password=hash_password(PASSWORD), is_active=True, is_admin=True)
    outsider = User(id=98105, username="http-accept-outsider", email="http-accept-outsider@example.com", hashed_password=hash_password(PASSWORD), is_active=True)
    project = NovelProject(id=PROJECT_ID, user_id=owner.id, title="HTTP JWT 成员验收项目")
    other_project = NovelProject(id=OTHER_PROJECT_ID, user_id=outsider.id, title="HTTP JWT 隔离项目")
    session.add_all([
        owner, editor, viewer, admin, outsider, project, other_project,
        ProjectMember(project_id=PROJECT_ID, user_id=owner.id, role=ProjectMemberRole.owner.value),
        ProjectMember(project_id=PROJECT_ID, user_id=editor.id, role=ProjectMemberRole.editor.value),
        ProjectMember(project_id=PROJECT_ID, user_id=viewer.id, role=ProjectMemberRole.viewer.value),
        ChapterOutline(project_id=PROJECT_ID, chapter_number=1, title="第一章", summary="成员 HTTP 验收大纲"),
    ])
    await session.flush()

    chapter = Chapter(project_id=PROJECT_ID, chapter_number=1, status="successful", real_summary="HTTP 验收已完成")
    other_chapter = Chapter(project_id=OTHER_PROJECT_ID, chapter_number=1, status="successful", real_summary="隔离项目正文")
    session.add_all([chapter, other_chapter])
    await session.flush()
    selected_version = ChapterVersion(
        chapter_id=chapter.id,
        version_label="http-v1",
        provider="fixture",
        content="HTTP JWT 成员验收正文。",
        content_hash="http-member-acceptance-v1",
        status="selected",
    )
    session.add(selected_version)
    await session.flush()
    chapter.selected_version_id = selected_version.id

    task = TaskRuntime(
        task_id="http-member-acceptance-run",
        owner_user_id=owner.id,
        project_id=PROJECT_ID,
        chapter_id=str(chapter.id),
        task_type="chapter_generation",
        status="succeeded",
        stage="completed",
        progress=100.0,
        message="HTTP 成员验收完成",
        lease_owner="fixture-worker",
        lease_generation=3,
        payload={"run_id": "http-member-acceptance-run", "project_id": PROJECT_ID, "chapter_id": str(chapter.id)},
    )
    other_task = TaskRuntime(
        task_id="http-member-acceptance-other-run",
        owner_user_id=outsider.id,
        project_id=OTHER_PROJECT_ID,
        chapter_id=str(other_chapter.id),
        task_type="chapter_generation",
        status="succeeded",
        stage="completed",
        progress=100.0,
        message="隔离任务",
        payload={"run_id": "http-member-acceptance-other-run", "project_id": OTHER_PROJECT_ID, "chapter_id": str(other_chapter.id)},
    )
    session.add_all([task, other_task])
    await session.flush()
    first_event = TaskRuntimeEvent(
        task_id=task.task_id,
        event_type="content_delta",
        status="running",
        stage="writing",
        progress=65.0,
        message="HTTP 成员可见片段",
        payload={"delta": "共享片段"},
        idempotency_key="http-member-acceptance-first",
    )
    terminal_event = TaskRuntimeEvent(
        task_id=task.task_id,
        event_type="task_completed",
        status="succeeded",
        stage="completed",
        progress=100.0,
        message="HTTP 成员可见终态",
        payload={"word_count": 1200},
        idempotency_key="http-member-acceptance-terminal",
    )
    session.add_all([first_event, terminal_event])
    await session.commit()
    await session.refresh(first_event)
    await session.refresh(terminal_event)
    return Fixture(owner, editor, viewer, admin, outsider, project, other_project, chapter, other_chapter, first_event, terminal_event, selected_version)


@pytest.fixture
async def http_jwt_client(task_session, monkeypatch):
    # backend/conftest 创建内存库时可能尚未加载 app.models 的全部模型；
    # 在本专用验收 fixture 内补齐元数据，避免状态 schema 查询缺表。
    connection = await task_session.connection()
    await connection.run_sync(Base.metadata.create_all)
    table_check = await connection.exec_driver_sql(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'novel_conversations'"
    )
    assert table_check.first() == (1,)
    fixture = await _seed(task_session)
    monkeypatch.setattr(writer, "AsyncSessionLocal", lambda: _SessionContext(task_session))

    async def override_session():
        yield task_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[db_session.get_session] = override_session
    # A few legacy Writer projections intentionally use AsyncSessionLocal rather
    # than Depends(get_session); bind that boundary to the same isolated DB.
    writer.AsyncSessionLocal = lambda: _SessionContext(task_session)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)
    async with httpx.AsyncClient(transport=transport, base_url="http://writer-member-http") as client:
        tokens: dict[str, str] = {}
        for user in (fixture.owner, fixture.editor, fixture.viewer, fixture.admin, fixture.outsider):
            response = await client.post("/api/auth/login", data={"username": user.username, "password": PASSWORD})
            assert response.status_code == 200, response.text
            tokens[user.username] = response.json()["access_token"]

        def headers(user: User) -> dict[str, str]:
            return {"Authorization": f"Bearer {tokens[user.username]}"}

        yield client, fixture, headers

    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(db_session.get_session, None)


@pytest.mark.asyncio
async def test_real_http_jwt_member_read_status_members_and_sse_replay(http_jwt_client):
    client, fixture, headers = http_jwt_client
    project_id = fixture.project.id

    for user in (fixture.owner, fixture.editor, fixture.viewer, fixture.admin):
        response = await client.get(f"/api/projects/{project_id}/members", headers=headers(user))
        assert response.status_code == 200, response.text
        payload = response.json()
        assert {item["user_id"] for item in payload["members"]} == {fixture.owner.id, fixture.editor.id, fixture.viewer.id}
        assert payload["access_role"] in {"owner", "editor", "viewer", "admin"}

    outsider_members = await client.get(f"/api/projects/{project_id}/members", headers=headers(fixture.outsider))
    assert outsider_members.status_code == 403

    for user in (fixture.owner, fixture.editor, fixture.viewer, fixture.admin):
        for suffix in (
            f"chapters/{fixture.chapter.chapter_number}/status",
            "chapters/outline/status",
            "chapters/rewrite-outline/status",
        ):
            response = await client.get(f"/api/writer/novels/{project_id}/{suffix}", headers=headers(user))
            assert response.status_code == 200, (user.username, suffix, response.text)

    outsider_status = await client.get(
        f"/api/writer/novels/{project_id}/chapters/1/status",
        headers=headers(fixture.outsider),
    )
    assert outsider_status.status_code == 403

    stream = await client.get(
        f"/api/writer/novels/{project_id}/chapters/1/stream",
        headers=headers(fixture.viewer),
        params={"after_event_id": 0},
    )
    assert stream.status_code == 200, stream.text
    assert f"id: {fixture.first_event.event_id}" in stream.text
    assert "event: content_delta" in stream.text
    assert "HTTP 成员可见片段" in stream.text
    assert f"id: {fixture.terminal_event.event_id}" in stream.text
    assert "event: task_completed" in stream.text

    replay = await client.get(
        f"/api/writer/novels/{project_id}/chapters/1/stream",
        headers=headers(fixture.editor),
        params={"after_event_id": fixture.first_event.event_id},
    )
    assert replay.status_code == 200, replay.text
    assert f"id: {fixture.first_event.event_id}" not in replay.text
    assert "HTTP 成员可见片段" not in replay.text
    assert f"id: {fixture.terminal_event.event_id}" in replay.text
    assert "event: task_completed" in replay.text

    isolated = await client.get(
        f"/api/writer/novels/{fixture.other_project.id}/chapters/1/stream",
        headers=headers(fixture.outsider),
        params={"after_event_id": 0},
    )
    assert isolated.status_code == 200, isolated.text
    assert "HTTP 成员可见片段" not in isolated.text

    outsider_stream = await client.get(
        f"/api/writer/novels/{project_id}/chapters/1/stream",
        headers=headers(fixture.outsider),
        params={"after_event_id": 0},
    )
    assert outsider_stream.status_code == 403


@pytest.mark.asyncio
async def test_real_http_jwt_uses_actual_bearer_identity_not_client_override(http_jwt_client):
    client, fixture, headers = http_jwt_client
    response = await client.get(
        f"/api/projects/{fixture.project.id}/members",
        headers=headers(fixture.viewer),
    )
    assert response.status_code == 200
    assert response.json()["access_role"] == "viewer"

    tampered = dict(headers(fixture.viewer))
    tampered["Authorization"] = headers(fixture.outsider)["Authorization"]
    response = await client.get(f"/api/projects/{fixture.project.id}/members", headers=tampered)
    assert response.status_code == 403

