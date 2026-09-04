"""Task-runtime project-member route regression contracts."""
from __future__ import annotations

from dataclasses import dataclass

import httpx
import pytest

from app.api.routers import task_runtime
from app.core.security import hash_password
from app.core.dependencies import get_current_user, get_session
from app.db import session as db_session
from app.db.base import Base
from app.main import app
from app.models import NovelProject, ProjectMember, User
from app.models.project_member import ProjectMemberRole
from app.models.task_runtime import TaskRuntime, TaskRuntimeEvent

PASSWORD = "TaskRuntimeMember123!"
PROJECT_ID = "task-runtime-member-project"
OTHER_PROJECT_ID = "task-runtime-other-project"


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
    project_task: TaskRuntime
    other_task: TaskRuntime
    projectless_task: TaskRuntime


async def _seed(session) -> Fixture:
    owner = User(id=99101, username="task-route-owner", email="task-route-owner@example.com", hashed_password=hash_password(PASSWORD), is_active=True)
    editor = User(id=99102, username="task-route-editor", email="task-route-editor@example.com", hashed_password=hash_password(PASSWORD), is_active=True)
    viewer = User(id=99103, username="task-route-viewer", email="task-route-viewer@example.com", hashed_password=hash_password(PASSWORD), is_active=True)
    admin = User(id=99104, username="task-route-admin", email="task-route-admin@example.com", hashed_password=hash_password(PASSWORD), is_active=True, is_admin=True)
    outsider = User(id=99105, username="task-route-outsider", email="task-route-outsider@example.com", hashed_password=hash_password(PASSWORD), is_active=True)
    project = NovelProject(id=PROJECT_ID, user_id=owner.id, title="任务成员项目")
    other_project = NovelProject(id=OTHER_PROJECT_ID, user_id=outsider.id, title="其他任务项目")
    session.add_all([
        owner, editor, viewer, admin, outsider, project, other_project,
        ProjectMember(project_id=PROJECT_ID, user_id=owner.id, role=ProjectMemberRole.owner.value),
        ProjectMember(project_id=PROJECT_ID, user_id=editor.id, role=ProjectMemberRole.editor.value),
        ProjectMember(project_id=PROJECT_ID, user_id=viewer.id, role=ProjectMemberRole.viewer.value),
    ])
    await session.flush()

    project_task = TaskRuntime(
        task_id="task-route-shared-run",
        owner_user_id=owner.id,
        project_id=PROJECT_ID,
        chapter_id="chapter-1",
        task_type="chapter_generation",
        status="queued",
        stage="queued",
        progress=45.0,
        message="待成员重试",
        max_retries=3,
        payload={"project_id": PROJECT_ID},
    )
    other_task = TaskRuntime(
        task_id="task-route-other-run",
        owner_user_id=outsider.id,
        project_id=OTHER_PROJECT_ID,
        task_type="chapter_generation",
        status="succeeded",
        stage="completed",
        progress=100.0,
        payload={"project_id": OTHER_PROJECT_ID},
    )
    projectless_task = TaskRuntime(
        task_id="task-route-projectless-run",
        owner_user_id=owner.id,
        project_id=None,
        task_type="projectless_job",
        status="succeeded",
        stage="completed",
        progress=100.0,
        payload={},
    )
    session.add_all([project_task, other_task, projectless_task])
    await session.flush()
    session.add_all([
        TaskRuntimeEvent(
            task_id=project_task.task_id,
            event_type="task_failed",
            status="failed",
            stage="failed",
            progress=45.0,
            message="成员可见事件",
            payload={"channel": "terminal"},
        ),
        TaskRuntimeEvent(
            task_id=other_task.task_id,
            event_type="task_completed",
            status="succeeded",
            stage="completed",
            progress=100.0,
            message="其他项目事件",
        ),
    ])
    await session.commit()
    await session.refresh(project_task)
    await session.refresh(other_task)
    await session.refresh(projectless_task)
    return Fixture(owner, editor, viewer, admin, outsider, project_task, other_task, projectless_task)


@pytest.fixture
async def task_runtime_http(task_session, monkeypatch):
    connection = await task_session.connection()
    await connection.run_sync(Base.metadata.create_all)
    fixture = await _seed(task_session)

    async def override_session():
        yield task_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[db_session.get_session] = override_session
    monkeypatch.setattr(task_runtime, "AsyncSessionLocal", lambda: _SessionContext(task_session))

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)
    async with httpx.AsyncClient(transport=transport, base_url="http://task-runtime-route") as client:
        tokens = {}
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
async def test_member_task_runtime_read_list_detail_events_and_sse_are_project_scoped(task_runtime_http):
    client, fixture, headers = task_runtime_http

    listed = await client.get(
        "/api/task-runtime/tasks",
        params={"project_id": PROJECT_ID},
        headers=headers(fixture.viewer),
    )
    assert listed.status_code == 200, listed.text
    assert {item["task_id"] for item in listed.json()} == {fixture.project_task.task_id}

    detail = await client.get(
        f"/api/task-runtime/tasks/{fixture.project_task.task_id}",
        headers=headers(fixture.viewer),
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["owner_user_id"] == fixture.owner.id

    events = await client.get(
        f"/api/task-runtime/tasks/{fixture.project_task.task_id}/events",
        headers=headers(fixture.viewer),
    )
    assert events.status_code == 200, events.text
    assert events.json()[0]["message"] == "成员可见事件"

    close_task = await client.post(
        f"/api/task-runtime/tasks/{fixture.project_task.task_id}/cancel",
        headers=headers(fixture.owner),
    )
    assert close_task.status_code == 200, close_task.text
    assert close_task.json()["status"] == "cancelled"

    stream = await client.get(
        f"/api/task-runtime/tasks/{fixture.project_task.task_id}/stream",
        headers=headers(fixture.viewer),
    )
    assert stream.status_code == 200, stream.text
    assert "成员可见事件" in stream.text

    outsider_list = await client.get(
        "/api/task-runtime/tasks",
        params={"project_id": PROJECT_ID},
        headers=headers(fixture.outsider),
    )
    assert outsider_list.status_code == 403

    outsider_detail = await client.get(
        f"/api/task-runtime/tasks/{fixture.project_task.task_id}",
        headers=headers(fixture.outsider),
    )
    assert outsider_detail.status_code == 403

    missing = await client.get(
        "/api/task-runtime/tasks/task-route-missing",
        headers=headers(fixture.viewer),
    )
    assert missing.status_code == 404

    cross_project = await client.get(
        "/api/task-runtime/tasks",
        params={"project_id": OTHER_PROJECT_ID},
        headers=headers(fixture.editor),
    )
    assert cross_project.status_code == 403


@pytest.mark.asyncio
async def test_member_task_runtime_create_and_controls_separate_actor_from_execution_owner(task_runtime_http):
    client, fixture, headers = task_runtime_http

    created = await client.post(
        "/api/task-runtime/tasks",
        headers=headers(fixture.editor),
        json={"task_type": "member_created_job", "project_id": PROJECT_ID, "payload": {"source": "editor"}},
    )
    assert created.status_code == 201, created.text
    assert created.json()["owner_user_id"] == fixture.editor.id
    assert created.json()["project_id"] == PROJECT_ID

    cancelled = await client.post(
        f"/api/task-runtime/tasks/{fixture.project_task.task_id}/cancel",
        headers=headers(fixture.editor),
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"

    viewer_cancel = await client.post(
        f"/api/task-runtime/tasks/{fixture.other_task.task_id}/cancel",
        headers=headers(fixture.viewer),
    )
    assert viewer_cancel.status_code == 403

    viewer_create = await client.post(
        "/api/task-runtime/tasks",
        headers=headers(fixture.viewer),
        json={"task_type": "viewer_job", "project_id": PROJECT_ID},
    )
    assert viewer_create.status_code == 403

    projectless_owner = await client.get(
        f"/api/task-runtime/tasks/{fixture.projectless_task.task_id}",
        headers=headers(fixture.owner),
    )
    assert projectless_owner.status_code == 200
    projectless_editor = await client.get(
        f"/api/task-runtime/tasks/{fixture.projectless_task.task_id}",
        headers=headers(fixture.editor),
    )
    assert projectless_editor.status_code == 404




