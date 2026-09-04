"""Regression coverage for collaborative access to legacy blueprint routes."""
from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, HTTPException

from app.api.routers import novels
from app.models import NovelProject, ProjectMember, User
from app.models.project_member import ProjectMemberRole
from app.schemas.novel import Blueprint, BlueprintPatch, NovelSectionType
from app.schemas.user import UserInDB
from app.services.novel_service import NovelService
from app.schemas.task_runtime import TaskRuntimeStatus

PROJECT_ID = "blueprint-member-project"


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


async def _seed(session) -> Fixture:
    owner = User(id=97101, username="blueprint-owner", email="blueprint-owner@example.com", hashed_password="x", is_active=True)
    editor = User(id=97102, username="blueprint-editor", email="blueprint-editor@example.com", hashed_password="x", is_active=True)
    viewer = User(id=97103, username="blueprint-viewer", email="blueprint-viewer@example.com", hashed_password="x", is_active=True)
    admin = User(id=97104, username="blueprint-admin", email="blueprint-admin@example.com", hashed_password="x", is_active=True, is_admin=True)
    outsider = User(id=97105, username="blueprint-outsider", email="blueprint-outsider@example.com", hashed_password="x", is_active=True)
    project = NovelProject(id=PROJECT_ID, user_id=owner.id, title="蓝图成员项目", initial_prompt="玄穹故事")
    session.add_all(
        [
            owner,
            editor,
            viewer,
            admin,
            outsider,
            project,
            ProjectMember(project_id=PROJECT_ID, user_id=owner.id, role=ProjectMemberRole.owner.value),
            ProjectMember(project_id=PROJECT_ID, user_id=editor.id, role=ProjectMemberRole.editor.value),
            ProjectMember(project_id=PROJECT_ID, user_id=viewer.id, role=ProjectMemberRole.viewer.value),
        ]
    )
    await session.commit()
    return Fixture(owner, editor, viewer, admin, outsider, project)


class _FakeTaskRuntimeService:
    created: list[dict] = []
    cancelled: list[dict] = []

    def __init__(self, _session):
        pass

    async def create_task(self, **kwargs):
        self.created.append(kwargs)
        return SimpleNamespace(task_id=kwargs["task_id"], status=TaskRuntimeStatus.QUEUED.value)

    async def request_cancel(self, task_id, *, owner_user_id=None, **kwargs):
        self.cancelled.append({"task_id": task_id, "owner_user_id": owner_user_id, **kwargs})
        return SimpleNamespace(task_id=task_id, status=TaskRuntimeStatus.CANCELLED.value)


class _FakeNovelService:
    calls: list[tuple] = []

    def __init__(self, _session):
        pass

    async def replace_blueprint(self, project_id, blueprint):
        self.calls.append(("replace", project_id, blueprint.title))

    async def patch_blueprint(self, project_id, update_data):
        self.calls.append(("patch", project_id, update_data))

    async def get_project_schema(self, project_id, user_id):
        self.calls.append(("schema", project_id, user_id))
        return {"id": project_id, "user_id": user_id}

    async def ensure_project_owner(self, *_args, **_kwargs):
        raise AssertionError("legacy owner gate must not be called")


@pytest.mark.asyncio
@pytest.mark.parametrize("actor_kind", ["owner", "editor", "admin"])
async def test_blueprint_start_is_project_write_access(task_session, monkeypatch, actor_kind):
    fixture = await _seed(task_session)
    _FakeTaskRuntimeService.created = []
    monkeypatch.setattr(novels, "TaskRuntimeService", _FakeTaskRuntimeService)
    monkeypatch.setattr(novels, "_load_latest_blueprint_job", _async_none)
    monkeypatch.setattr(novels, "_persist_blueprint_job_state", _async_noop)
    monkeypatch.setattr(novels, "_schedule_blueprint_recovery", _async_noop)

    response = await novels.start_blueprint_generation(
        PROJECT_ID,
        BackgroundTasks(),
        payload=None,
        session=task_session,
        current_user=_principal(getattr(fixture, actor_kind)),
    )

    assert response.status == "queued"
    assert _FakeTaskRuntimeService.created[-1]["owner_user_id"] == getattr(fixture, actor_kind).id
    assert _FakeTaskRuntimeService.created[-1]["project_id"] == PROJECT_ID


@pytest.mark.asyncio
async def test_blueprint_start_recovery_preserves_persisted_execution_owner(task_session, monkeypatch):
    fixture = await _seed(task_session)
    captured: list[int] = []

    async def load_job(*_args, **_kwargs):
        return {
            "run_id": "owner-active-run",
            "project_id": PROJECT_ID,
            "user_id": fixture.owner.id,
            "status": "generating",
            "progress_stage": "generating",
            "progress_message": "fixture",
            "force_stage": "novel_outline",
        }

    async def schedule(*args, **kwargs):
        captured.append(kwargs.get("user_id", args[2] if len(args) > 2 else -1))

    monkeypatch.setattr(novels, "_load_latest_blueprint_job", load_job)
    monkeypatch.setattr(novels, "_schedule_persisted_blueprint_recovery_if_needed", schedule)

    response = await novels.start_blueprint_generation(
        PROJECT_ID,
        BackgroundTasks(),
        payload={"force_stage": "novel_outline"},
        session=task_session,
        current_user=_principal(fixture.editor),
    )

    assert response.run_id == "owner-active-run"
    assert captured == [fixture.owner.id]


@pytest.mark.asyncio
@pytest.mark.parametrize("actor_kind", ["viewer", "outsider"])
async def test_blueprint_start_denies_read_only_and_nonmember(task_session, monkeypatch, actor_kind):
    fixture = await _seed(task_session)
    monkeypatch.setattr(novels, "TaskRuntimeService", _FakeTaskRuntimeService)

    with pytest.raises(HTTPException) as denied:
        await novels.start_blueprint_generation(
            PROJECT_ID,
            BackgroundTasks(),
            payload=None,
            session=task_session,
            current_user=_principal(getattr(fixture, actor_kind)),
        )
    assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_blueprint_status_is_project_read_access(task_session, monkeypatch):
    fixture = await _seed(task_session)
    monkeypatch.setattr(novels, "_load_latest_blueprint_job", _async_none)

    response = await novels.get_blueprint_generation_status(
        PROJECT_ID,
        BackgroundTasks(),
        session=task_session,
        current_user=_principal(fixture.viewer),
    )

    assert response.status == "idle"


@pytest.mark.asyncio
async def test_blueprint_cancel_uses_persisted_execution_owner(task_session, monkeypatch):
    fixture = await _seed(task_session)
    _FakeTaskRuntimeService.cancelled = []
    monkeypatch.setattr(novels, "TaskRuntimeService", _FakeTaskRuntimeService)
    monkeypatch.setattr(novels, "AsyncSessionLocal", lambda: _SessionContext(task_session))
    monkeypatch.setattr(novels, "_load_latest_blueprint_job", _async_job)
    monkeypatch.setattr(novels, "_blueprint_runtime_task", _async_runtime)
    monkeypatch.setattr(novels, "_persist_blueprint_job_state", _async_noop)

    response = await novels.cancel_blueprint_generation(
        PROJECT_ID,
        session=task_session,
        current_user=_principal(fixture.editor),
    )

    assert response.status in {"cancelled", "cancelling"}
    assert _FakeTaskRuntimeService.cancelled[-1]["owner_user_id"] == fixture.owner.id


@pytest.mark.asyncio
@pytest.mark.parametrize("route_name", ["save", "patch"])
async def test_blueprint_mutations_are_project_write_access(task_session, monkeypatch, route_name):
    fixture = await _seed(task_session)
    _FakeNovelService.calls = []
    monkeypatch.setattr(novels, "NovelService", _FakeNovelService)

    if route_name == "save":
        result = await novels.save_blueprint(
            PROJECT_ID,
            blueprint_data=Blueprint(title="成员保存蓝图"),
            session=task_session,
            current_user=_principal(fixture.editor),
        )
    else:
        result = await novels.patch_blueprint(
            PROJECT_ID,
            payload=BlueprintPatch(one_sentence_summary="成员局部更新"),
            session=task_session,
            current_user=_principal(fixture.editor),
        )

    assert result["id"] == PROJECT_ID
    assert _FakeNovelService.calls[0][0] == route_name if route_name == "patch" else _FakeNovelService.calls[0][0] == "replace"


@pytest.mark.asyncio
@pytest.mark.parametrize("route_name", ["save", "patch"])
@pytest.mark.parametrize("actor_kind", ["viewer", "outsider"])
async def test_blueprint_mutations_deny_read_only_and_nonmember(task_session, monkeypatch, route_name, actor_kind):
    fixture = await _seed(task_session)
    monkeypatch.setattr(novels, "NovelService", _FakeNovelService)

    with pytest.raises(HTTPException) as denied:
        if route_name == "save":
            await novels.save_blueprint(
                PROJECT_ID,
                blueprint_data=Blueprint(title="越权蓝图"),
                session=task_session,
                current_user=_principal(getattr(fixture, actor_kind)),
            )
        else:
            await novels.patch_blueprint(
                PROJECT_ID,
                payload=BlueprintPatch(one_sentence_summary="越权更新"),
                session=task_session,
                current_user=_principal(getattr(fixture, actor_kind)),
            )
    assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_service_section_and_chapter_readers_use_member_access(task_session, monkeypatch):
    fixture = await _seed(task_session)
    service = NovelService(task_session)
    monkeypatch.setattr(service, "_build_section_response", lambda *_args: {"section": "world_setting"})
    monkeypatch.setattr(service, "_build_chapter_schema", lambda *_args, **_kwargs: {"chapter_number": 1})

    section = await service.get_section_data(PROJECT_ID, fixture.editor.id, NovelSectionType.WORLD_SETTING)
    chapter = await service.get_chapter_schema(PROJECT_ID, fixture.editor.id, 1)

    assert section == {"section": "world_setting"}
    assert chapter == {"chapter_number": 1}


async def _async_none(*_args, **_kwargs):
    return None


async def _async_noop(*_args, **_kwargs):
    return None


async def _async_job(*_args, **_kwargs):
    return {
        "run_id": "blueprint-owner-run",
        "project_id": PROJECT_ID,
        "user_id": 97101,
        "status": "generating",
        "progress_stage": "generating",
        "progress_message": "fixture",
    }


async def _async_runtime(*_args, **_kwargs):
    return SimpleNamespace(status=TaskRuntimeStatus.QUEUED.value)


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_args):
        return False
