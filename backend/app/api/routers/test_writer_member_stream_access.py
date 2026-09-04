"""H-1 SSE contracts for project-member chapter runtime replay."""
from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi import HTTPException

from app.api.routers import writer
from app.models import Chapter, NovelProject, ProjectMember, User
from app.models.project_member import ProjectMemberRole
from app.models.task_runtime import TaskRuntime, TaskRuntimeEvent
from app.schemas.user import UserInDB

PROJECT_ID = "writer-stream-member-project"
OTHER_PROJECT_ID = "writer-stream-other-project"


@dataclass(frozen=True)
class Fixture:
    owner: User
    editor: User
    viewer: User
    outsider: User
    project: NovelProject
    chapter: Chapter
    second_chapter: Chapter
    other_project: NovelProject
    other_chapter: Chapter
    task: TaskRuntime
    first_event: TaskRuntimeEvent
    terminal_event: TaskRuntimeEvent


class _Request:
    async def is_disconnected(self) -> bool:
        return False


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_args):
        return False


def _principal(user: User) -> UserInDB:
    return UserInDB(
        id=int(user.id),
        username=user.username,
        email=user.email,
        hashed_password=user.hashed_password,
        is_active=bool(user.is_active),
        is_admin=bool(user.is_admin),
    )


async def _collect(response) -> str:
    chunks: list[str] = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk))
    return "".join(chunks)


async def _first_frame_then_close(response) -> str:
    iterator = response.body_iterator
    try:
        chunk = await anext(iterator)
        return chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk)
    finally:
        await iterator.aclose()


async def _seed(task_session) -> Fixture:
    owner = User(id=95201, username="writer-stream-owner", hashed_password="x", is_active=True)
    editor = User(id=95202, username="writer-stream-editor", hashed_password="x", is_active=True)
    viewer = User(id=95203, username="writer-stream-viewer", hashed_password="x", is_active=True)
    outsider = User(id=95204, username="writer-stream-outsider", hashed_password="x", is_active=True)
    project = NovelProject(id=PROJECT_ID, user_id=owner.id, title="成员 SSE 项目")
    other_project = NovelProject(id=OTHER_PROJECT_ID, user_id=owner.id, title="其他项目")
    task_session.add_all([
        owner,
        editor,
        viewer,
        outsider,
        project,
        other_project,
        ProjectMember(project_id=PROJECT_ID, user_id=owner.id, role=ProjectMemberRole.owner.value),
        ProjectMember(project_id=PROJECT_ID, user_id=editor.id, role=ProjectMemberRole.editor.value),
        ProjectMember(project_id=PROJECT_ID, user_id=viewer.id, role=ProjectMemberRole.viewer.value),
    ])
    await task_session.flush()

    chapter = Chapter(project_id=PROJECT_ID, chapter_number=1, status="generating")
    second_chapter = Chapter(project_id=PROJECT_ID, chapter_number=2, status="generating")
    other_chapter = Chapter(project_id=OTHER_PROJECT_ID, chapter_number=1, status="generating")
    task_session.add_all([chapter, second_chapter, other_chapter])
    await task_session.flush()

    task = TaskRuntime(
        task_id="writer-stream-member-task",
        owner_user_id=owner.id,
        project_id=PROJECT_ID,
        chapter_id=str(chapter.id),
        task_type="chapter_generation",
        status="succeeded",
        stage="completed",
        progress=100.0,
        message="Owner 章节生成完成",
        lease_owner="owner-worker",
        lease_generation=4,
        payload={"run_id": "writer-stream-member-task", "project_id": PROJECT_ID, "chapter_id": str(chapter.id)},
    )
    task_session.add(task)
    await task_session.flush()
    first_event = TaskRuntimeEvent(
        task_id=task.task_id,
        event_type="content_delta",
        status="running",
        stage="writing",
        progress=66.0,
        message="成员可见正文片段",
        payload={"delta": "共享片段"},
        idempotency_key="writer-stream-first",
    )
    terminal_event = TaskRuntimeEvent(
        task_id=task.task_id,
        event_type="task_completed",
        status="succeeded",
        stage="completed",
        progress=100.0,
        message="成员可见完成事件",
        payload={"word_count": 1200},
        idempotency_key="writer-stream-terminal",
    )
    task_session.add_all([first_event, terminal_event])
    await task_session.commit()
    await task_session.refresh(first_event)
    await task_session.refresh(terminal_event)
    return Fixture(owner, editor, viewer, outsider, project, chapter, second_chapter, other_project, other_chapter, task, first_event, terminal_event)


@pytest.mark.asyncio
@pytest.mark.parametrize("member_kind", ["viewer", "editor"])
async def test_project_members_replay_owner_chapter_terminal_stream(task_session, monkeypatch, member_kind: str):
    fixture = await _seed(task_session)
    monkeypatch.setattr(writer, "AsyncSessionLocal", lambda: _SessionContext(task_session))

    response = await writer.stream_chapter_progress(
        project_id=fixture.project.id,
        chapter_number=fixture.chapter.chapter_number,
        request=_Request(),
        after_event_id=0,
        last_event_id=None,
        session=task_session,
        current_user=_principal(getattr(fixture, member_kind)),
    )
    body = await _collect(response)

    assert f"id: {fixture.first_event.event_id}" in body
    assert "event: content_delta" in body
    assert "成员可见正文片段" in body
    assert f"id: {fixture.terminal_event.event_id}" in body
    assert "event: task_completed" in body
    assert "成员可见完成事件" in body


@pytest.mark.asyncio
@pytest.mark.parametrize("cursor_kind", ["after", "last_event_id"])
async def test_member_cursor_replays_only_events_after_requested_cursor(task_session, monkeypatch, cursor_kind: str):
    fixture = await _seed(task_session)
    monkeypatch.setattr(writer, "AsyncSessionLocal", lambda: _SessionContext(task_session))
    kwargs = {"after_event_id": fixture.first_event.event_id, "last_event_id": None} if cursor_kind == "after" else {"after_event_id": 0, "last_event_id": fixture.first_event.event_id}

    response = await writer.stream_chapter_progress(
        project_id=fixture.project.id,
        chapter_number=fixture.chapter.chapter_number,
        request=_Request(),
        session=task_session,
        current_user=_principal(fixture.viewer),
        **kwargs,
    )
    body = await _collect(response)

    assert f"id: {fixture.first_event.event_id}" not in body
    assert "成员可见正文片段" not in body
    assert f"id: {fixture.terminal_event.event_id}" in body
    assert "成员可见完成事件" in body


@pytest.mark.asyncio
async def test_nonmember_is_rejected_before_stream_is_created(task_session, monkeypatch):
    fixture = await _seed(task_session)
    monkeypatch.setattr(writer, "AsyncSessionLocal", lambda: _SessionContext(task_session))

    with pytest.raises(HTTPException) as denied:
        await writer.stream_chapter_progress(
            project_id=fixture.project.id,
            chapter_number=fixture.chapter.chapter_number,
            request=_Request(),
            after_event_id=0,
            last_event_id=None,
            session=task_session,
            current_user=_principal(fixture.outsider),
        )
    assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_stream_task_lookup_does_not_reuse_project_task_for_wrong_project_or_chapter(task_session, monkeypatch):
    fixture = await _seed(task_session)
    monkeypatch.setattr(writer, "AsyncSessionLocal", lambda: _SessionContext(task_session))

    wrong_chapter = await writer._find_chapter_runtime_task(
        task_session,
        project_id=fixture.project.id,
        chapter_number=fixture.second_chapter.chapter_number,
        chapter_id=fixture.second_chapter.id,
        owner_user_id=None,
        run_id=fixture.task.task_id,
    )
    wrong_project = await writer._find_chapter_runtime_task(
        task_session,
        project_id=fixture.other_project.id,
        chapter_number=fixture.other_chapter.chapter_number,
        chapter_id=fixture.other_chapter.id,
        owner_user_id=None,
        run_id=fixture.task.task_id,
    )
    response = await writer.stream_chapter_progress(
        project_id=fixture.project.id,
        chapter_number=fixture.second_chapter.chapter_number,
        request=_Request(),
        after_event_id=0,
        last_event_id=None,
        session=task_session,
        current_user=_principal(fixture.viewer),
    )
    fallback_frame = await _first_frame_then_close(response)

    assert wrong_chapter is None
    assert wrong_project is None
    assert "成员可见正文片段" not in fallback_frame
    assert "event: status_update" in fallback_frame
