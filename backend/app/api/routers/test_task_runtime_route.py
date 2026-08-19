from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.routers.task_runtime import create_task
from app.models import NovelProject, User
from app.schemas.task_runtime import TaskRuntimeCreate, TaskRuntimeEventRead
from app.services.task_runtime import TaskRuntimeService


async def _add_user(session, user_id: int, username: str) -> User:
    user = User(
        id=user_id,
        username=username,
        email=f"{username}@example.com",
        hashed_password="not-used-in-router-test",
        is_active=True,
    )
    session.add(user)
    await session.flush()
    return user


@pytest.mark.anyio
async def test_create_task_accepts_project_owned_by_current_user(task_session):
    user = await _add_user(task_session, 101, "task-owner")
    task_session.add(NovelProject(id="owned-project", user_id=user.id, title="Owned"))
    await task_session.flush()

    task = await create_task(
        TaskRuntimeCreate(task_type="chapter", project_id="owned-project"),
        session=task_session,
        current_user=SimpleNamespace(id=user.id),
    )

    assert task.project_id == "owned-project"
    assert task.owner_user_id == user.id


@pytest.mark.anyio
async def test_create_task_rejects_project_owned_by_another_user(task_session):
    owner = await _add_user(task_session, 102, "other-owner")
    current_user = await _add_user(task_session, 103, "current-owner")
    task_session.add(NovelProject(id="foreign-project", user_id=owner.id, title="Foreign"))
    await task_session.flush()

    with pytest.raises(HTTPException) as error:
        await create_task(
            TaskRuntimeCreate(task_type="chapter", project_id="foreign-project"),
            session=task_session,
            current_user=SimpleNamespace(id=current_user.id),
        )

    assert error.value.status_code == 404
    assert error.value.detail["code"] == "PROJECT_NOT_FOUND"


@pytest.mark.anyio
async def test_create_task_without_project_remains_available(task_session):
    user = await _add_user(task_session, 104, "generic-owner")

    task = await create_task(
        TaskRuntimeCreate(task_type="maintenance"),
        session=task_session,
        current_user=SimpleNamespace(id=user.id),
    )

    assert task.project_id is None
    assert task.owner_user_id == user.id


@pytest.mark.anyio
async def test_event_response_projects_stable_channel_and_sequence(task_session):
    service = TaskRuntimeService(task_session)
    task = await service.create_task(task_type="chapter", owner_user_id=105)
    await service.append_event(
        task.task_id,
        event_type="content_delta",
        payload={"text": "正文片段"},
        owner_user_id=105,
    )
    event = (await service.list_events(task.task_id, owner_user_id=105))[-1]

    response = TaskRuntimeEventRead.model_validate(event)

    assert response.channel == "content"
    assert response.event_sequence == event.event_id
