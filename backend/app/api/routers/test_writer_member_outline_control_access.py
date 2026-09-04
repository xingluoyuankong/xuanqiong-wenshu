"""Minimal H-2 outline controls contract for shared project writers.

The suite invokes only start/cancel endpoints and leaves BackgroundTasks unexecuted,
so no LLM or worker pipeline runs.  It proves shared-runtime dedup and preserves
the original runtime owner when another project writer cancels the task.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pytest
from fastapi import BackgroundTasks, HTTPException

from app.api.routers import writer
from app.models import NovelProject, ProjectMember, User
from app.models.project_member import ProjectMemberRole
from app.schemas.novel import GenerateOutlineRequest, RewriteChapterOutlineRequest
from app.schemas.user import UserInDB
from app.services.task_runtime import TaskRuntimeService

PROJECT_ID = "writer-member-outline-control-project"


@dataclass(frozen=True)
class Fixture:
    owner: User
    editor: User
    viewer: User
    admin: User
    outsider: User
    project: NovelProject


def _principal(user: User) -> UserInDB:
    return UserInDB(
        id=int(user.id),
        username=user.username,
        email=user.email,
        hashed_password=user.hashed_password,
        is_admin=bool(user.is_admin),
        is_active=bool(user.is_active),
    )


def _clear_outline_memory() -> None:
    writer._OUTLINE_JOBS.clear()
    writer._OUTLINE_PROJECT_RUNS.clear()
    writer._OUTLINE_SCHEDULED_RUNS.clear()


@pytest.fixture(autouse=True)
def clear_outline_memory():
    _clear_outline_memory()
    yield
    _clear_outline_memory()


async def _seed(task_session) -> Fixture:
    owner = User(id=95601, username="outline-owner", hashed_password="x", is_active=True)
    editor = User(id=95602, username="outline-editor", hashed_password="x", is_active=True)
    viewer = User(id=95603, username="outline-viewer", hashed_password="x", is_active=True)
    admin = User(id=95604, username="outline-admin", hashed_password="x", is_active=True, is_admin=True)
    outsider = User(id=95605, username="outline-outsider", hashed_password="x", is_active=True)
    project = NovelProject(id=PROJECT_ID, user_id=owner.id, title="章节大纲协作控制项目")
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
    await task_session.commit()
    return Fixture(owner, editor, viewer, admin, outsider, project)


async def _start(
    kind: Literal["outline", "rewrite"],
    fixture: Fixture,
    actor: User,
    task_session,
    background_tasks: BackgroundTasks | None = None,
):
    background_tasks = background_tasks or BackgroundTasks()
    if kind == "outline":
        response = await writer.start_chapters_outline_generation(
            project_id=fixture.project.id,
            request=GenerateOutlineRequest(start_chapter=1, num_chapters=3),
            background_tasks=background_tasks,
            session=task_session,
            current_user=_principal(actor),
        )
    else:
        response = await writer.start_chapter_outline_rewrite(
            project_id=fixture.project.id,
            request=RewriteChapterOutlineRequest(
                chapter_number=1,
                title="旧标题",
                summary="旧摘要",
                direction="强化冲突",
            ),
            background_tasks=background_tasks,
            session=task_session,
            current_user=_principal(actor),
        )
    return response, background_tasks


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["outline", "rewrite"])
@pytest.mark.parametrize("actor_kind", ["owner", "editor", "admin"])
async def test_project_writers_can_start_outline_jobs_without_running_workers(task_session, kind: str, actor_kind: str):
    fixture = await _seed(task_session)
    actor = getattr(fixture, actor_kind)

    response, background_tasks = await _start(kind, fixture, actor, task_session)
    runtime = await TaskRuntimeService(task_session).get_task(response.run_id)

    assert response.status == "queued"
    assert runtime.project_id == fixture.project.id
    assert runtime.owner_user_id == actor.id
    assert runtime.task_type == (
        "chapter_outline_generation" if kind == "outline" else "chapter_outline_rewrite"
    )
    assert len(background_tasks.tasks) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("actor_kind", ["viewer", "outsider"])
@pytest.mark.parametrize("operation", ["outline", "rewrite", "cancel"])
async def test_viewer_and_nonmember_are_denied_outline_controls(task_session, actor_kind: str, operation: str):
    fixture = await _seed(task_session)
    actor = getattr(fixture, actor_kind)

    with pytest.raises(HTTPException) as denied:
        if operation == "cancel":
            await writer.cancel_chapters_outline_generation(
                project_id=fixture.project.id,
                session=task_session,
                current_user=_principal(actor),
            )
        else:
            await _start(operation, fixture, actor, task_session)
    assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_editor_reuses_owner_active_runtime_after_memory_restart(task_session):
    fixture = await _seed(task_session)
    owner_started, _ = await _start("outline", fixture, fixture.owner, task_session)

    # 模拟进程重启：唯一真相只保留在 TaskRuntime，Editor 启动另一个 outline 入口
    # 时仍必须复用同一项目的 active run。
    _clear_outline_memory()
    editor_started, background_tasks = await _start("rewrite", fixture, fixture.editor, task_session)

    assert editor_started.run_id == owner_started.run_id
    assert background_tasks.tasks == []
    runtime = await TaskRuntimeService(task_session).get_task(owner_started.run_id)
    assert runtime.owner_user_id == fixture.owner.id


@pytest.mark.asyncio
async def test_editor_cancels_owner_runtime_with_owner_identity_after_memory_restart(task_session, monkeypatch):
    fixture = await _seed(task_session)
    started, _ = await _start("outline", fixture, fixture.owner, task_session)
    runtime_service = TaskRuntimeService(task_session)
    runtime = await runtime_service.get_task(started.run_id)
    runtime.lease_owner = "owner-outline-worker"
    runtime.lease_generation = 29
    await task_session.commit()
    before = (runtime.owner_user_id, runtime.lease_owner, runtime.lease_generation)
    calls: list[tuple[str, str, int | None]] = []

    original_request_cancel = TaskRuntimeService.request_cancel
    original_append_event = TaskRuntimeService.append_event

    async def spy_request_cancel(self, task_id: str, *, owner_user_id=None, **kwargs):
        if task_id == started.run_id:
            calls.append(("request_cancel", task_id, owner_user_id))
        return await original_request_cancel(self, task_id, owner_user_id=owner_user_id, **kwargs)

    async def spy_append_event(self, task_id: str, *, owner_user_id=None, **kwargs):
        if task_id == started.run_id and kwargs.get("event_type") == "task_cancelled":
            calls.append(("terminal", task_id, owner_user_id))
        return await original_append_event(self, task_id, owner_user_id=owner_user_id, **kwargs)

    monkeypatch.setattr(TaskRuntimeService, "request_cancel", spy_request_cancel)
    monkeypatch.setattr(TaskRuntimeService, "append_event", spy_append_event)
    _clear_outline_memory()

    cancelled = await writer.cancel_chapters_outline_generation(
        project_id=fixture.project.id,
        session=task_session,
        current_user=_principal(fixture.editor),
    )

    await task_session.refresh(runtime)
    assert cancelled.status == "cancelled"
    assert (runtime.owner_user_id, runtime.lease_owner, runtime.lease_generation) == before
    assert ("request_cancel", started.run_id, fixture.owner.id) in calls
    assert ("terminal", started.run_id, fixture.owner.id) in calls
