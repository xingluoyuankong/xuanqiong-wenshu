"""H-2 contract tests for project-member Writer mutations.

The contract keeps the durable TaskRuntime execution identity with the original
creator while allowing Owner, Editor, and Admin actors to make project-scoped
writer changes.  It deliberately uses local version/edit/outline paths and
never invokes an LLM.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import func, select

from app.api.routers import writer
from app.models import (
    Chapter,
    ChapterOutline,
    ChapterVersion,
    NovelProject,
    ProjectMember,
    User,
)
from app.models.project_member import ProjectMemberRole
from app.models.task_runtime import TaskRuntime
from app.schemas.novel import EditChapterRequest, SelectVersionRequest, UpdateChapterOutlineRequest
from app.schemas.user import UserInDB

PROJECT_ID = "writer-member-write-project"


@dataclass(frozen=True)
class Fixture:
    owner: User
    editor: User
    viewer: User
    admin: User
    outsider: User
    project: NovelProject
    chapter: Chapter
    selected_version: ChapterVersion
    candidate_version: ChapterVersion
    outline: ChapterOutline
    task: TaskRuntime


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
    owner = User(id=95201, username="writer-write-owner", hashed_password="x", is_active=True)
    editor = User(id=95202, username="writer-write-editor", hashed_password="x", is_active=True)
    viewer = User(id=95203, username="writer-write-viewer", hashed_password="x", is_active=True)
    admin = User(id=95204, username="writer-write-admin", hashed_password="x", is_active=True, is_admin=True)
    outsider = User(id=95205, username="writer-write-outsider", hashed_password="x", is_active=True)
    project = NovelProject(id=PROJECT_ID, user_id=owner.id, title="协作写入项目")
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

    chapter = Chapter(
        project_id=PROJECT_ID,
        chapter_number=1,
        status="successful",
        real_summary="Owner 创建的章节。",
    )
    outline = ChapterOutline(
        project_id=PROJECT_ID,
        chapter_number=1,
        title="Owner 大纲标题",
        summary="Owner 大纲摘要",
    )
    task_session.add_all([chapter, outline])
    await task_session.flush()

    selected_version = ChapterVersion(
        chapter_id=chapter.id,
        version_label="owner-selected",
        provider="fixture",
        content="Owner 选择的原始正文。",
        content_hash="writer-member-write-selected",
        status="selected",
    )
    candidate_version = ChapterVersion(
        chapter_id=chapter.id,
        version_label="owner-candidate",
        provider="fixture",
        content="Owner 创建的候选正文。",
        content_hash="writer-member-write-candidate",
        status="candidate",
    )
    task_session.add_all([selected_version, candidate_version])
    await task_session.flush()
    chapter.selected_version_id = selected_version.id

    task = TaskRuntime(
        task_id="writer-member-write-owner-run",
        owner_user_id=owner.id,
        project_id=PROJECT_ID,
        chapter_id=str(chapter.id),
        task_type="chapter_generation",
        status="running",
        stage="drafting",
        progress=61.0,
        message="Owner worker 正在写作",
        lease_owner="owner-worker",
        lease_generation=19,
        payload={"run_id": "writer-member-write-owner-run"},
    )
    task_session.add(task)
    await task_session.commit()
    return Fixture(
        owner,
        editor,
        viewer,
        admin,
        outsider,
        project,
        chapter,
        selected_version,
        candidate_version,
        outline,
        task,
    )


async def _invoke_write_operation(task_session, fixture: Fixture, actor: User, operation: str):
    if operation == "select":
        return await writer.select_chapter_version(
            project_id=fixture.project.id,
            request=SelectVersionRequest(
                chapter_number=fixture.chapter.chapter_number,
                version_id=fixture.candidate_version.id,
            ),
            background_tasks=BackgroundTasks(),
            session=task_session,
            current_user=_principal(actor),
        )
    if operation == "edit":
        return await writer.edit_chapter_content(
            project_id=fixture.project.id,
            request=EditChapterRequest(
                chapter_number=fixture.chapter.chapter_number,
                content=f"{actor.username} 的协作正文",
                base_revision=1,
            ),
            background_tasks=BackgroundTasks(),
            session=task_session,
            current_user=_principal(actor),
        )
    if operation == "outline":
        return await writer.update_chapter_outline(
            project_id=fixture.project.id,
            request=UpdateChapterOutlineRequest(
                chapter_number=fixture.chapter.chapter_number,
                title=f"{actor.username} 的协作大纲",
                summary=f"{actor.username} 更新的章节摘要",
            ),
            session=task_session,
            current_user=_principal(actor),
        )
    raise AssertionError(f"unknown operation: {operation}")


@pytest.mark.asyncio
@pytest.mark.parametrize("actor_kind", ["owner", "editor", "admin"])
@pytest.mark.parametrize("operation", ["select", "edit", "outline"])
async def test_project_writers_can_mutate_shared_writer_resources_without_reassigning_owner_runtime(
    task_session,
    actor_kind: str,
    operation: str,
):
    fixture = await _seed(task_session)
    actor = getattr(fixture, actor_kind)
    execution_identity = (
        fixture.task.owner_user_id,
        fixture.task.lease_owner,
        fixture.task.lease_generation,
    )

    await _invoke_write_operation(task_session, fixture, actor, operation)

    await task_session.refresh(fixture.chapter)
    await task_session.refresh(fixture.outline)
    await task_session.refresh(fixture.task)
    assert (
        fixture.task.owner_user_id,
        fixture.task.lease_owner,
        fixture.task.lease_generation,
    ) == execution_identity

    if operation == "select":
        assert fixture.chapter.selected_version_id == fixture.candidate_version.id
    elif operation == "edit":
        created = await task_session.scalar(
            select(ChapterVersion)
            .where(ChapterVersion.chapter_id == fixture.chapter.id)
            .order_by(ChapterVersion.id.desc())
        )
        assert created is not None
        assert created.content == f"{actor.username} 的协作正文"
        assert fixture.chapter.selected_version_id == created.id
    else:
        assert fixture.outline.title == f"{actor.username} 的协作大纲"
        assert fixture.outline.summary == f"{actor.username} 更新的章节摘要"


@pytest.mark.asyncio
@pytest.mark.parametrize("actor_kind", ["viewer", "outsider"])
@pytest.mark.parametrize("operation", ["select", "edit", "outline"])
async def test_viewer_and_nonmember_get_403_without_mutating_shared_writer_resources(
    task_session,
    actor_kind: str,
    operation: str,
):
    fixture = await _seed(task_session)
    actor = getattr(fixture, actor_kind)
    original = {
        "selected_version_id": fixture.chapter.selected_version_id,
        "outline": (fixture.outline.title, fixture.outline.summary),
        "version_count": await task_session.scalar(
            select(func.count()).select_from(ChapterVersion).where(ChapterVersion.chapter_id == fixture.chapter.id)
        ),
        "execution_identity": (
            fixture.task.owner_user_id,
            fixture.task.lease_owner,
            fixture.task.lease_generation,
        ),
    }

    with pytest.raises(HTTPException) as denied:
        await _invoke_write_operation(task_session, fixture, actor, operation)
    assert denied.value.status_code == 403

    await task_session.refresh(fixture.chapter)
    await task_session.refresh(fixture.outline)
    await task_session.refresh(fixture.task)
    assert fixture.chapter.selected_version_id == original["selected_version_id"]
    assert (fixture.outline.title, fixture.outline.summary) == original["outline"]
    assert await task_session.scalar(
        select(func.count()).select_from(ChapterVersion).where(ChapterVersion.chapter_id == fixture.chapter.id)
    ) == original["version_count"]
    assert (
        fixture.task.owner_user_id,
        fixture.task.lease_owner,
        fixture.task.lease_generation,
    ) == original["execution_identity"]
