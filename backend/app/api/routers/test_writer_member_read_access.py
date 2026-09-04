"""H-1 contract tests for project-member read access to Writer runtime state.

These tests intentionally describe the target UI-004-B read contract. They
expose the legacy owner-scoped Writer paths until the H-1 implementation lands.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi import HTTPException

from app.api.routers import writer
from app.models import Chapter, ChapterVersion, NovelProject, ProjectMember, User
from app.models.project_member import ProjectMemberRole
from app.models.task_runtime import TaskRuntime, TaskRuntimeEvent
from app.schemas.user import UserInDB

PROJECT_ID = "writer-member-read-project"
OTHER_PROJECT_ID = "writer-member-read-other-project"


@dataclass(frozen=True)
class Fixture:
    owner: User
    editor: User
    viewer: User
    admin: User
    outsider: User
    project: NovelProject
    chapter: Chapter
    second_chapter: Chapter
    other_chapter: Chapter
    task: TaskRuntime
    other_task: TaskRuntime


def _principal(user: User) -> UserInDB:
    return UserInDB(
        id=int(user.id),
        username=user.username,
        email=user.email,
        hashed_password=user.hashed_password,
        is_admin=bool(user.is_admin),
        is_active=bool(user.is_active),
    )


@pytest.fixture(autouse=True)
def _clear_writer_runtime_memory():
    writer._OUTLINE_JOBS.clear()
    writer._OUTLINE_PROJECT_RUNS.clear()
    yield
    writer._OUTLINE_JOBS.clear()
    writer._OUTLINE_PROJECT_RUNS.clear()


async def _seed(task_session) -> Fixture:
    owner = User(id=95101, username="writer-read-owner", hashed_password="x", is_active=True)
    editor = User(id=95102, username="writer-read-editor", hashed_password="x", is_active=True)
    viewer = User(id=95103, username="writer-read-viewer", hashed_password="x", is_active=True)
    admin = User(id=95104, username="writer-read-admin", hashed_password="x", is_active=True, is_admin=True)
    outsider = User(id=95105, username="writer-read-outsider", hashed_password="x", is_active=True)
    project = NovelProject(id=PROJECT_ID, user_id=owner.id, title="协作读取项目")
    other_project = NovelProject(id=OTHER_PROJECT_ID, user_id=outsider.id, title="隔离项目")
    task_session.add_all([
        owner, editor, viewer, admin, outsider, project, other_project,
        ProjectMember(project_id=PROJECT_ID, user_id=owner.id, role=ProjectMemberRole.owner.value),
        ProjectMember(project_id=PROJECT_ID, user_id=editor.id, role=ProjectMemberRole.editor.value),
        ProjectMember(project_id=PROJECT_ID, user_id=viewer.id, role=ProjectMemberRole.viewer.value),
    ])
    await task_session.flush()

    chapter = Chapter(project_id=PROJECT_ID, chapter_number=1, status="generating", real_summary="Owner 发起的章节生成")
    second_chapter = Chapter(project_id=PROJECT_ID, chapter_number=2, status="generating", real_summary="同项目第二章节")
    other_chapter = Chapter(project_id=OTHER_PROJECT_ID, chapter_number=1, status="generating", real_summary="隔离章节")
    task_session.add_all([chapter, second_chapter, other_chapter])
    await task_session.flush()
    selected = ChapterVersion(
        chapter_id=chapter.id, version_label="owner-v1", provider="fixture",
        content="Owner 创建的章节正文。", content_hash="writer-member-read-selected", status="selected",
    )
    task_session.add(selected)
    await task_session.flush()
    chapter.selected_version_id = selected.id

    task = TaskRuntime(
        task_id="writer-member-read-task", owner_user_id=owner.id, project_id=PROJECT_ID,
        chapter_id=str(chapter.id), task_type="chapter_outline_generation", status="running",
        stage="outline_context", progress=45.0, message="Owner 创建的大纲运行中",
        lease_owner="owner-worker", lease_generation=7,
        payload={"run_id": "writer-member-read-task", "request": {"start_chapter": 1, "num_chapters": 3}},
    )
    other_task = TaskRuntime(
        task_id="writer-member-read-other-task", owner_user_id=outsider.id, project_id=OTHER_PROJECT_ID,
        chapter_id=str(other_chapter.id), task_type="chapter_outline_generation", status="running",
        stage="outline_context", progress=55.0, message="隔离项目运行中",
        lease_owner="outsider-worker", lease_generation=11,
        payload={"run_id": "writer-member-read-other-task", "request": {"start_chapter": 1, "num_chapters": 2}},
    )
    task_session.add_all([task, other_task])
    await task_session.flush()
    task_session.add_all([
        TaskRuntimeEvent(task_id=task.task_id, event_type="stage_changed", status="running", stage="outline_context", progress=45.0, message="共享项目事件", idempotency_key="writer-read-shared-event"),
        TaskRuntimeEvent(task_id=other_task.task_id, event_type="stage_changed", status="running", stage="outline_context", progress=55.0, message="隔离项目事件", idempotency_key="writer-read-other-event"),
    ])
    await task_session.commit()
    return Fixture(owner, editor, viewer, admin, outsider, project, chapter, second_chapter, other_chapter, task, other_task)


@pytest.mark.asyncio
@pytest.mark.parametrize("member_kind", ["owner", "editor", "viewer", "admin"])
async def test_project_readers_can_read_owner_created_chapter_status(task_session, member_kind: str):
    fixture = await _seed(task_session)

    status = await writer.get_chapter_generation_status(
        project_id=fixture.project.id,
        chapter_number=fixture.chapter.chapter_number,
        session=task_session,
        current_user=_principal(getattr(fixture, member_kind)),
    )

    assert status.chapter_number == fixture.chapter.chapter_number
    assert status.generation_status == "generating"
    assert status.selected_version_id == fixture.chapter.selected_version_id
    assert status.content == "Owner 创建的章节正文。"


@pytest.mark.asyncio
@pytest.mark.parametrize("member_kind", ["owner", "editor", "viewer", "admin"])
async def test_project_readers_can_rebuild_owner_created_outline_runtime_without_mutating_lease(task_session, member_kind: str):
    fixture = await _seed(task_session)
    before = (fixture.task.owner_user_id, fixture.task.lease_owner, fixture.task.lease_generation)

    status = await writer.get_chapters_outline_generation_status(
        project_id=fixture.project.id,
        session=task_session,
        current_user=_principal(getattr(fixture, member_kind)),
    )

    await task_session.refresh(fixture.task)
    assert status.run_id == fixture.task.task_id
    assert status.progress_stage == "outline_context"
    assert "共享项目事件" in "\n".join(event.get("message") or "" for event in status.events)
    assert (fixture.task.owner_user_id, fixture.task.lease_owner, fixture.task.lease_generation) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["chapter_status", "outline_status", "rewrite_outline_status"])
async def test_nonmember_is_rejected_from_project_runtime_read_contract(task_session, operation: str):
    fixture = await _seed(task_session)
    outsider = _principal(fixture.outsider)

    with pytest.raises(HTTPException) as denied:
        if operation == "chapter_status":
            await writer.get_chapter_generation_status(project_id=fixture.project.id, chapter_number=1, session=task_session, current_user=outsider)
        elif operation == "outline_status":
            await writer.get_chapters_outline_generation_status(project_id=fixture.project.id, session=task_session, current_user=outsider)
        else:
            await writer.get_chapter_outline_rewrite_status(project_id=fixture.project.id, session=task_session, current_user=outsider)
    assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_project_runtime_lookup_remains_bound_to_project_and_chapter(task_session):
    fixture = await _seed(task_session)

    shared = await writer._find_chapter_runtime_task(
        task_session, project_id=fixture.project.id, chapter_number=1, chapter_id=fixture.chapter.id,
        owner_user_id=fixture.owner.id, run_id=fixture.task.task_id,
    )
    cross_project = await writer._find_chapter_runtime_task(
        task_session, project_id=fixture.project.id, chapter_number=1, chapter_id=fixture.chapter.id,
        owner_user_id=fixture.owner.id, run_id=fixture.other_task.task_id,
    )
    cross_chapter = await writer._find_chapter_runtime_task(
        task_session, project_id=fixture.project.id, chapter_number=fixture.second_chapter.chapter_number,
        chapter_id=fixture.second_chapter.id, owner_user_id=fixture.owner.id, run_id=fixture.task.task_id,
    )

    assert shared is not None and shared.task_id == fixture.task.task_id
    assert cross_project is None
    assert cross_chapter is None


