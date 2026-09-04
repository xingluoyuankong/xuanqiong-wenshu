"""Project-member contracts for the generic TaskRuntime HTTP router."""
from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api.routers import task_runtime
from app.models import NovelProject, ProjectMember, TaskRuntime, TaskRuntimeEvent, User
from app.models.project_member import ProjectMemberRole
from app.schemas.task_runtime import (
    TaskRuntimeCreate,
    TaskRuntimeEventCreate,
    TaskRuntimeEventType,
    TaskRuntimeStatus,
)
from app.schemas.user import UserInDB
from app.services.task_runtime import TaskRuntimeService

PROJECT_ID = "task-runtime-member-router-project"


@dataclass(frozen=True)
class Fixture:
    owner: User
    editor: User
    viewer: User
    admin: User
    outsider: User
    project: NovelProject
    owner_task: TaskRuntime
    projectless_task: TaskRuntime


def _principal(user: User) -> UserInDB:
    return UserInDB(
        id=int(user.id),
        username=user.username,
        email=user.email,
        hashed_password=user.hashed_password,
        is_admin=bool(user.is_admin),
        is_active=bool(user.is_active),
    )


async def _seed(task_session) -> Fixture:
    owner = User(id=98301, username="runtime-router-owner", hashed_password="x", is_active=True)
    editor = User(id=98302, username="runtime-router-editor", hashed_password="x", is_active=True)
    viewer = User(id=98303, username="runtime-router-viewer", hashed_password="x", is_active=True)
    admin = User(id=98304, username="runtime-router-admin", hashed_password="x", is_active=True, is_admin=True)
    outsider = User(id=98305, username="runtime-router-outsider", hashed_password="x", is_active=True)
    project = NovelProject(id=PROJECT_ID, user_id=owner.id, title="TaskRuntime 协作路由项目")
    task_session.add_all([
        owner,
        editor,
        viewer,
        admin,
        outsider,
        project,
        ProjectMember(project_id=PROJECT_ID, user_id=owner.id, role=ProjectMemberRole.owner.value),
        ProjectMember(project_id=PROJECT_ID, user_id=editor.id, role=ProjectMemberRole.editor.value),
        ProjectMember(project_id=PROJECT_ID, user_id=viewer.id, role=ProjectMemberRole.viewer.value),
    ])
    await task_session.flush()
    runtime = TaskRuntimeService(task_session)
    owner_task = await runtime.create_task(
        task_id="runtime-router-owner-task",
        task_type="chapter_generation",
        owner_user_id=owner.id,
        project_id=PROJECT_ID,
        payload={"run_id": "runtime-router-owner-task"},
    )
    projectless_task = await runtime.create_task(
        task_id="runtime-router-projectless-task",
        task_type="maintenance",
        owner_user_id=owner.id,
    )
    return Fixture(owner, editor, viewer, admin, outsider, project, owner_task, projectless_task)


@pytest.mark.asyncio
async def test_project_member_can_create_and_read_shared_runtime(task_session):
    fixture = await _seed(task_session)
    editor = _principal(fixture.editor)

    created = await task_runtime.create_task(
        TaskRuntimeCreate(task_type="outline_generation", project_id=PROJECT_ID),
        session=task_session,
        current_user=editor,
    )
    assert created.project_id == PROJECT_ID
    assert created.owner_user_id == fixture.editor.id

    for actor in (fixture.editor, fixture.viewer, fixture.admin):
        readable = await task_runtime.get_task(
            fixture.owner_task.task_id,
            session=task_session,
            current_user=_principal(actor),
        )
        assert readable.owner_user_id == fixture.owner.id

    with pytest.raises(HTTPException) as denied:
        await task_runtime.get_task(
            fixture.owner_task.task_id,
            session=task_session,
            current_user=_principal(fixture.outsider),
        )
    assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_project_task_list_and_events_are_member_readable_but_projectless_stays_private(task_session):
    fixture = await _seed(task_session)
    runtime = TaskRuntimeService(task_session)
    await runtime.append_event(
        fixture.owner_task.task_id,
        event_type=TaskRuntimeEventType.PROGRESS.value,
        status=TaskRuntimeStatus.RUNNING.value,
        stage="writing",
        progress=55,
        message="共享项目进度",
        owner_user_id=fixture.owner.id,
    )

    listed = await task_runtime.list_tasks(
        project_id=PROJECT_ID,
        session=task_session,
        current_user=_principal(fixture.viewer),
    )
    assert {task.task_id for task in listed} == {fixture.owner_task.task_id}

    events = await task_runtime.list_task_events(
        fixture.owner_task.task_id,
        session=task_session,
        current_user=_principal(fixture.viewer),
    )
    assert any(event.message == "共享项目进度" for event in events)

    with pytest.raises(HTTPException) as denied:
        await task_runtime.get_task(
            fixture.projectless_task.task_id,
            session=task_session,
            current_user=_principal(fixture.viewer),
        )
    assert denied.value.status_code == 404


@pytest.mark.asyncio
async def test_editor_cancels_owner_task_using_original_runtime_owner(task_session):
    fixture = await _seed(task_session)
    runtime = TaskRuntimeService(task_session)
    task = await runtime.get_task(fixture.owner_task.task_id)
    task.lease_owner = "owner-runtime-worker"
    task.lease_generation = 12
    await task_session.commit()
    before = (task.owner_user_id, task.lease_owner, task.lease_generation)

    cancelled = await task_runtime.cancel_task(
        fixture.owner_task.task_id,
        session=task_session,
        current_user=_principal(fixture.editor),
    )
    await task_session.refresh(task)

    assert cancelled.status == TaskRuntimeStatus.CANCELLING.value
    assert (task.owner_user_id, task.lease_owner, task.lease_generation) == before

    with pytest.raises(HTTPException) as denied:
        await task_runtime.cancel_task(
            fixture.owner_task.task_id,
            session=task_session,
            current_user=_principal(fixture.viewer),
        )
    assert denied.value.status_code == 403


class _ConnectedRequest:
    async def is_disconnected(self) -> bool:
        return False


@pytest.mark.asyncio
async def test_project_member_task_stream_replays_terminal_events(monkeypatch, task_session):
    fixture = await _seed(task_session)
    runtime = TaskRuntimeService(task_session)
    await runtime.append_event(
        fixture.owner_task.task_id,
        event_type=TaskRuntimeEventType.TASK_COMPLETED.value,
        status=TaskRuntimeStatus.SUCCEEDED.value,
        stage="completed",
        progress=100,
        message="共享任务完成",
        owner_user_id=fixture.owner.id,
    )
    monkeypatch.setattr(task_runtime, "AsyncSessionLocal", lambda: _SessionContext(task_session))

    response = await task_runtime.stream_task_events(
        fixture.owner_task.task_id,
        request=_ConnectedRequest(),
        session=task_session,
        current_user=_principal(fixture.viewer),
    )
    chunks = [chunk async for chunk in response.body_iterator]
    body = "".join(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk for chunk in chunks)

    assert "event: task_completed" in body
    assert "共享任务完成" in body


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_args):
        return False
