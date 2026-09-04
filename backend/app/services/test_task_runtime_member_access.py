from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.models import NovelProject, ProjectMember, ProjectMemberRole, User
from app.repositories.novel_repository import NovelRepository
from app.services.task_runtime import TaskRuntimeService


@pytest.mark.asyncio
async def test_create_task_authorizes_member_actor_and_preserves_execution_owner(task_session):
    owner = User(id=8101, username="runtime-owner", hashed_password="x", is_admin=False, is_active=True)
    editor = User(id=8102, username="runtime-editor", hashed_password="x", is_admin=False, is_active=True)
    project = NovelProject(id="runtime-member-project", user_id=owner.id, title="Runtime member project")
    task_session.add_all(
        [
            owner,
            editor,
            project,
            ProjectMember(
                project_id=project.id,
                user_id=editor.id,
                role=ProjectMemberRole.editor.value,
            ),
        ]
    )
    await task_session.commit()

    task = await TaskRuntimeService(task_session).create_task(
        task_id="runtime-member-task",
        task_type="chapter_generation",
        project_id=project.id,
        actor_user_id=editor.id,
        execution_owner_id=owner.id,
    )

    assert task.project_id == project.id
    assert task.owner_user_id == owner.id


@pytest.mark.asyncio
async def test_create_task_rejects_non_member_actor_but_keeps_projectless_compatibility(task_session):
    owner = User(id=8111, username="runtime-owner-2", hashed_password="x", is_admin=False, is_active=True)
    outsider = User(id=8112, username="runtime-outsider", hashed_password="x", is_admin=False, is_active=True)
    project = NovelProject(id="runtime-member-project-2", user_id=owner.id, title="Runtime member project 2")
    task_session.add_all([owner, outsider, project])
    await task_session.commit()

    with pytest.raises(HTTPException) as denied:
        await TaskRuntimeService(task_session).create_task(
            task_id="runtime-outsider-task",
            task_type="chapter_generation",
            project_id=project.id,
            actor_user_id=outsider.id,
            execution_owner_id=outsider.id,
        )
    assert denied.value.status_code == 403

    projectless = await TaskRuntimeService(task_session).create_task(
        task_id="runtime-projectless-task",
        task_type="maintenance",
        actor_user_id=outsider.id,
        execution_owner_id=outsider.id,
    )
    assert projectless.project_id is None
    assert projectless.owner_user_id == outsider.id


@pytest.mark.asyncio
async def test_list_by_user_returns_owner_and_active_member_projects_only(task_session):
    owner = User(id=8121, username="list-owner", hashed_password="x", is_admin=False, is_active=True)
    member = User(id=8122, username="list-member", hashed_password="x", is_admin=False, is_active=True)
    outsider = User(id=8123, username="list-outsider", hashed_password="x", is_admin=False, is_active=True)
    owner_project = NovelProject(id="list-owner-project", user_id=owner.id, title="Owner project")
    member_project = NovelProject(id="list-member-project", user_id=owner.id, title="Member project")
    deleted_project = NovelProject(id="list-deleted-project", user_id=owner.id, title="Deleted membership project")
    hidden_project = NovelProject(id="list-hidden-project", user_id=owner.id, title="Hidden project")
    task_session.add_all(
        [
            owner,
            member,
            outsider,
            owner_project,
            member_project,
            deleted_project,
            hidden_project,
            ProjectMember(
                project_id=member_project.id,
                user_id=member.id,
                role=ProjectMemberRole.viewer.value,
            ),
            ProjectMember(
                project_id=deleted_project.id,
                user_id=member.id,
                role=ProjectMemberRole.editor.value,
                deleted_at=datetime.now(timezone.utc),
            ),
        ]
    )
    await task_session.commit()

    visible = await NovelRepository(task_session).list_by_user(member.id)

    assert {project.id for project in visible} == {member_project.id}
    assert owner_project.id not in {project.id for project in visible}
    assert deleted_project.id not in {project.id for project in visible}
    assert hidden_project.id not in {project.id for project in visible}
    assert await NovelRepository(task_session).list_by_user(outsider.id) == []
