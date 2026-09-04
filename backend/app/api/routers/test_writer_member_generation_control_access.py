"""H-2 generation-control member access contracts.

Generation may be started by every project writer, and its newly claimed runtime
belongs to the actor that started it.  Control of an existing owner-created run
uses the original execution identity even when an Editor makes the request.
The tests stub only the runtime/worker boundary; no background task or LLM runs.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import BackgroundTasks, HTTPException

from app.api.routers import writer
from app.models import Chapter, ChapterOutline, NovelProject, ProjectMember, User
from app.models.project_member import ProjectMemberRole
from app.models.task_runtime import TaskRuntime
from app.schemas.novel import CancelChapterRequest, GenerateChapterRequest, ResumeChapterGenerationRequest
from app.schemas.user import UserInDB

PROJECT_ID = "writer-member-generation-control-project"


@dataclass(frozen=True)
class Fixture:
    owner: User
    editor: User
    viewer: User
    admin: User
    outsider: User
    project: NovelProject
    generation_chapter: Chapter
    cancel_chapter: Chapter
    resume_chapter: Chapter
    owner_cancel_task: TaskRuntime
    owner_resume_task: TaskRuntime


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
    owner = User(id=95401, username="writer-control-owner", hashed_password="x", is_active=True)
    editor = User(id=95402, username="writer-control-editor", hashed_password="x", is_active=True)
    viewer = User(id=95403, username="writer-control-viewer", hashed_password="x", is_active=True)
    admin = User(id=95404, username="writer-control-admin", hashed_password="x", is_active=True, is_admin=True)
    outsider = User(id=95405, username="writer-control-outsider", hashed_password="x", is_active=True)
    project = NovelProject(id=PROJECT_ID, user_id=owner.id, title="协作运行控制项目")
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

    generation_chapter = Chapter(project_id=PROJECT_ID, chapter_number=1, status="not_generated")
    cancel_chapter = Chapter(
        project_id=PROJECT_ID,
        chapter_number=2,
        status="generating",
        real_summary=writer._build_generation_runtime_state(run_id="owner-cancel-run"),
    )
    resume_chapter = Chapter(
        project_id=PROJECT_ID,
        chapter_number=3,
        status="failed",
        real_summary=writer._build_generation_runtime_state(run_id="owner-resume-run"),
    )
    task_session.add_all([
        generation_chapter,
        cancel_chapter,
        resume_chapter,
        ChapterOutline(project_id=PROJECT_ID, chapter_number=1, title="生成大纲", summary="用于生成权限合同。"),
    ])
    await task_session.flush()

    owner_cancel_task = TaskRuntime(
        task_id="owner-cancel-run",
        owner_user_id=owner.id,
        project_id=PROJECT_ID,
        chapter_id=str(cancel_chapter.id),
        task_type="chapter_generation",
        status="running",
        stage="drafting",
        progress=42.0,
        message="Owner worker 正在写作",
        lease_owner="owner-worker-cancel",
        lease_generation=17,
        payload={"run_id": "owner-cancel-run"},
    )
    owner_resume_task = TaskRuntime(
        task_id="owner-resume-run",
        owner_user_id=owner.id,
        project_id=PROJECT_ID,
        chapter_id=str(resume_chapter.id),
        task_type="chapter_generation",
        status="stale",
        stage="checkpoint",
        progress=58.0,
        message="Owner worker 等待恢复",
        lease_owner="owner-worker-resume",
        lease_generation=23,
        payload={"run_id": "owner-resume-run", "generation_execution": {"writing_notes": "fixture", "flow_config": {}}},
    )
    task_session.add_all([owner_cancel_task, owner_resume_task])
    await task_session.commit()
    return Fixture(
        owner,
        editor,
        viewer,
        admin,
        outsider,
        project,
        generation_chapter,
        cancel_chapter,
        resume_chapter,
        owner_cancel_task,
        owner_resume_task,
    )


async def _fake_project_schema(*_args: Any, **kwargs: Any) -> SimpleNamespace:
    return SimpleNamespace(generation_runtime=kwargs.get("generation_runtime"))


def _install_generation_boundary(monkeypatch, claims: list[dict[str, Any]]) -> None:
    async def fake_claim(*_args: Any, **kwargs: Any) -> str:
        claims.append(kwargs)
        return "editor-generation-run"

    async def fake_plan(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"checkpoint": "stub"}

    async def fake_persist(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(writer, "_try_claim_chapter_generation", fake_claim)
    monkeypatch.setattr(writer, "_register_longform_generation_plan", fake_plan)
    monkeypatch.setattr(writer, "_persist_generation_execution_spec", fake_persist)
    monkeypatch.setattr(writer, "_load_project_schema", _fake_project_schema)


def _install_owner_runtime_boundary(monkeypatch, fixture: Fixture, calls: list[tuple[str, str, int | None]]) -> None:
    class RecordingRuntimeService:
        def __init__(self, _session: Any):
            pass

        async def request_cancel(self, task_id: str, *, owner_user_id: int | None = None, **_kwargs: Any) -> TaskRuntime:
            calls.append(("cancel", task_id, owner_user_id))
            return fixture.owner_cancel_task

        async def get_task(self, task_id: str, owner_user_id: int | None = None) -> TaskRuntime:
            calls.append(("get", task_id, owner_user_id))
            return fixture.owner_resume_task

        async def retry(self, task_id: str, *, owner_user_id: int | None = None, **_kwargs: Any) -> TaskRuntime:
            calls.append(("retry", task_id, owner_user_id))
            return fixture.owner_resume_task

    async def noop_mark_failed(*_args: Any, **_kwargs: Any) -> None:
        return None

    def fake_restore(*_args: Any, **_kwargs: Any) -> tuple[str, dict[str, Any]]:
        return "fixture checkpoint", {"longform_runtime": {"checkpoint": "stub"}}

    monkeypatch.setattr(writer, "TaskRuntimeService", RecordingRuntimeService)
    monkeypatch.setattr(writer, "_mark_busy_chapter_failed", noop_mark_failed)
    monkeypatch.setattr(writer, "_restore_generation_execution_spec", fake_restore)
    monkeypatch.setattr(writer, "_load_project_schema", _fake_project_schema)


@pytest.mark.asyncio
@pytest.mark.parametrize("actor_kind", ["owner", "editor", "admin"])
async def test_project_writers_claim_new_generation_runtime_as_their_actor(task_session, monkeypatch, actor_kind: str):
    fixture = await _seed(task_session)
    claims: list[dict[str, Any]] = []
    _install_generation_boundary(monkeypatch, claims)
    background_tasks = BackgroundTasks()
    actor = getattr(fixture, actor_kind)

    await writer.generate_chapter(
        project_id=fixture.project.id,
        request=GenerateChapterRequest(chapter_number=fixture.generation_chapter.chapter_number),
        background_tasks=background_tasks,
        session=task_session,
        current_user=_principal(actor),
    )

    assert claims == [{
        "chapter_id": fixture.generation_chapter.id,
        "chapter_number": fixture.generation_chapter.chapter_number,
        "execution_owner_id": actor.id,
        "generation_timeout_seconds": pytest.approx(claims[0]["generation_timeout_seconds"]),
    }]
    assert len(background_tasks.tasks) == 1
    assert background_tasks.tasks[0].func is writer._schedule_generate_task
    assert background_tasks.tasks[0].args[2] == actor.id


@pytest.mark.asyncio
@pytest.mark.parametrize("actor_kind", ["viewer", "outsider"])
@pytest.mark.parametrize("operation", ["generate", "cancel", "resume"])
async def test_viewer_and_nonmember_are_denied_generation_controls(task_session, actor_kind: str, operation: str):
    fixture = await _seed(task_session)
    actor = _principal(getattr(fixture, actor_kind))

    with pytest.raises(HTTPException) as denied:
        if operation == "generate":
            await writer.generate_chapter(
                project_id=fixture.project.id,
                request=GenerateChapterRequest(chapter_number=1),
                background_tasks=BackgroundTasks(),
                session=task_session,
                current_user=actor,
            )
        elif operation == "cancel":
            await writer.cancel_chapter_generation(
                project_id=fixture.project.id,
                request=CancelChapterRequest(chapter_number=2),
                session=task_session,
                current_user=actor,
            )
        else:
            await writer.resume_chapter_generation(
                project_id=fixture.project.id,
                request=ResumeChapterGenerationRequest(run_id=fixture.owner_resume_task.task_id),
                background_tasks=BackgroundTasks(),
                session=task_session,
                current_user=actor,
            )
    assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_editor_cancel_uses_owner_execution_identity_without_mutating_owner_run(task_session, monkeypatch):
    fixture = await _seed(task_session)
    before = (fixture.owner_cancel_task.owner_user_id, fixture.owner_cancel_task.lease_owner, fixture.owner_cancel_task.lease_generation)
    calls: list[tuple[str, str, int | None]] = []
    _install_owner_runtime_boundary(monkeypatch, fixture, calls)

    await writer.cancel_chapter_generation(
        project_id=fixture.project.id,
        request=CancelChapterRequest(chapter_number=fixture.cancel_chapter.chapter_number),
        session=task_session,
        current_user=_principal(fixture.editor),
    )

    await task_session.refresh(fixture.owner_cancel_task)
    assert (fixture.owner_cancel_task.owner_user_id, fixture.owner_cancel_task.lease_owner, fixture.owner_cancel_task.lease_generation) == before
    assert ("cancel", fixture.owner_cancel_task.task_id, fixture.owner.id) in calls


@pytest.mark.asyncio
async def test_editor_resume_uses_owner_execution_identity_and_owner_worker_schedule(task_session, monkeypatch):
    fixture = await _seed(task_session)
    before = (fixture.owner_resume_task.owner_user_id, fixture.owner_resume_task.lease_owner, fixture.owner_resume_task.lease_generation)
    calls: list[tuple[str, str, int | None]] = []
    _install_owner_runtime_boundary(monkeypatch, fixture, calls)
    background_tasks = BackgroundTasks()

    await writer.resume_chapter_generation(
        project_id=fixture.project.id,
        request=ResumeChapterGenerationRequest(run_id=fixture.owner_resume_task.task_id),
        background_tasks=background_tasks,
        session=task_session,
        current_user=_principal(fixture.editor),
    )

    await task_session.refresh(fixture.owner_resume_task)
    assert (fixture.owner_resume_task.owner_user_id, fixture.owner_resume_task.lease_owner, fixture.owner_resume_task.lease_generation) == before
    assert ("retry", fixture.owner_resume_task.task_id, fixture.owner.id) in calls
    assert len(background_tasks.tasks) == 1
    assert background_tasks.tasks[0].func is writer._schedule_generate_task
    assert background_tasks.tasks[0].args[2] == fixture.owner.id

