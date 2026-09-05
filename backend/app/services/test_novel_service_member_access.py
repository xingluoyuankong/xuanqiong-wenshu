from __future__ import annotations

import ast
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from fastapi import HTTPException

from app.models import NovelProject, ProjectMember, ProjectMemberRole, TaskRuntime, TaskRuntimeEvent, User
from app.schemas.novel import NovelSectionType
from app.services.novel_service import NovelService


pytestmark = pytest.mark.asyncio


async def _seed_project_access(task_session):
    owner = User(id=9401, username="novel-service-owner", hashed_password="x", is_active=True)
    editor = User(id=9402, username="novel-service-editor", hashed_password="x", is_active=True)
    viewer = User(id=9403, username="novel-service-viewer", hashed_password="x", is_active=True)
    outsider = User(id=9404, username="novel-service-outsider", hashed_password="x", is_active=True)
    project = NovelProject(
        id="novel-service-member-project",
        user_id=owner.id,
        title="NovelService member semantics",
        initial_prompt="seed",
    )
    task_session.add_all(
        [
            owner,
            editor,
            viewer,
            outsider,
            project,
            ProjectMember(
                project_id=project.id,
                user_id=editor.id,
                role=ProjectMemberRole.editor.value,
            ),
            ProjectMember(
                project_id=project.id,
                user_id=viewer.id,
                role=ProjectMemberRole.viewer.value,
            ),
        ]
    )
    await task_session.commit()
    return owner, editor, viewer, outsider, project


def _owner_gate_callers() -> list[str]:
    source = __import__("inspect").getsource(NovelService)
    tree = ast.parse(source)
    callers: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        if node.name == "ensure_project_owner":
            continue
        if any(
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "ensure_project_owner"
            for call in ast.walk(node)
        ):
            callers.append(node.name)
    return callers


async def test_ensure_project_owner_inventory_keeps_only_delete_owner_gate():
    assert _owner_gate_callers() == ["delete_projects"]


async def test_member_read_helpers_do_not_reenter_legacy_owner_gate(task_session, monkeypatch):
    _owner, editor, _viewer, outsider, project = await _seed_project_access(task_session)
    service = NovelService(task_session)

    async def fail_if_legacy_owner_gate_is_used(*_args, **_kwargs):
        raise AssertionError("member read path must not call ensure_project_owner")

    monkeypatch.setattr(service, "ensure_project_owner", fail_if_legacy_owner_gate_is_used)
    monkeypatch.setattr(service, "_serialize_project", AsyncMock(return_value="serialized-project"))
    monkeypatch.setattr(
        service,
        "_build_section_response",
        lambda _project, section: ("section", section),
    )
    monkeypatch.setattr(
        service,
        "_build_chapter_schema",
        lambda _project, chapter_number, **_kwargs: ("chapter", chapter_number),
    )

    assert await service.get_project_schema(project.id, editor.id) == "serialized-project"
    assert await service.get_section_data(project.id, editor.id, NovelSectionType.OVERVIEW) == (
        "section",
        NovelSectionType.OVERVIEW,
    )
    assert await service.get_chapter_schema(project.id, editor.id, 1) == ("chapter", 1)

    with pytest.raises(HTTPException) as denied:
        await service.get_project_schema(project.id, outsider.id)
    assert denied.value.status_code == 403


async def test_list_projects_for_user_uses_member_visible_repository_scope(task_session):
    _owner, editor, _viewer, outsider, project = await _seed_project_access(task_session)
    service = NovelService(task_session)

    summaries = await service.list_projects_for_user(editor.id)
    assert [summary.id for summary in summaries] == [project.id]
    assert await service.list_projects_for_user(outsider.id) == []


async def test_delete_projects_preserves_true_owner_only_compatibility(task_session, monkeypatch):
    owner, editor, _viewer, _outsider, project = await _seed_project_access(task_session)
    service = NovelService(task_session)
    service._vector_store.delete_by_project = AsyncMock()

    with pytest.raises(HTTPException) as denied:
        await service.delete_projects([project.id], editor.id)
    assert denied.value.status_code == 403

    runtime = TaskRuntime(
        task_id="delete-project-runtime-task",
        owner_user_id=owner.id,
        project_id=project.id,
        task_type="chapter_generation",
        status="cancelling",
    )
    task_session.add(runtime)
    await task_session.flush()
    task_session.add(
        TaskRuntimeEvent(
            task_id=runtime.task_id,
            event_type="task_cancel_requested",
            status="cancelling",
            message="fixture",
        )
    )
    await task_session.commit()

    await service.delete_projects([project.id], owner.id)
    service._vector_store.delete_by_project.assert_awaited_once_with(project.id)
    assert await service.repo.get_by_id(project.id) is None
    assert await task_session.get(TaskRuntime, runtime.task_id) is None
    assert (await task_session.execute(select(TaskRuntimeEvent).where(TaskRuntimeEvent.task_id == runtime.task_id))).scalars().all() == []
