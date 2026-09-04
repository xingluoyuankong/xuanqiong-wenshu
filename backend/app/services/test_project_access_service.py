from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import inspect, select

from app.models import NovelProject, ProjectMember, User
from app.services.project_access_service import ProjectAccessService


@pytest.mark.asyncio
async def test_project_member_model_exposes_roles_soft_delete_and_indexes(task_session):
    table = ProjectMember.__table__
    assert {"owner", "editor", "viewer"} == {role.value for role in ProjectMemberRole}
    assert {"id", "project_id", "user_id", "role", "created_at", "updated_at", "deleted_at"} <= set(table.columns.keys())
    assert any(
        constraint.name == "uq_project_member_project_user"
        and {column.name for column in constraint.columns} == {"project_id", "user_id"}
        for constraint in table.constraints
    )
    index_columns = {
        index.name: tuple(column.name for column in index.columns)
        for index in table.indexes
    }
    assert any(columns == ("project_id",) for columns in index_columns.values())
    assert any(columns == ("user_id",) for columns in index_columns.values())


@pytest.mark.asyncio
async def test_access_service_supports_admin_owner_member_roles_and_soft_delete(task_session):
    owner = User(id=101, username="owner-101", hashed_password="x", is_admin=False, is_active=True)
    editor = User(id=102, username="editor-102", hashed_password="x", is_admin=False, is_active=True)
    viewer = User(id=103, username="viewer-103", hashed_password="x", is_admin=False, is_active=True)
    admin = User(id=104, username="admin-104", hashed_password="x", is_admin=True, is_active=True)
    outsider = User(id=105, username="outsider-105", hashed_password="x", is_admin=False, is_active=True)
    project = NovelProject(id="project-access-1", user_id=owner.id, title="Access test")
    task_session.add_all(
        [
            owner,
            editor,
            viewer,
            admin,
            outsider,
            project,
            ProjectMember(project_id=project.id, user_id=editor.id, role=ProjectMemberRole.editor.value),
            ProjectMember(project_id=project.id, user_id=viewer.id, role=ProjectMemberRole.viewer.value),
        ]
    )
    await task_session.commit()

    service = ProjectAccessService(task_session)
    assert service.is_admin(admin) is True
    assert service.is_admin(viewer) is False
    assert await service.can_read_project(project.id, owner) is True
    assert await service.can_write_project(project.id, owner) is True
    assert await service.can_read_project(project.id, editor) is True
    assert await service.can_write_project(project.id, editor) is True
    assert await service.can_read_project(project.id, viewer) is True
    assert await service.can_write_project(project.id, viewer) is False
    assert await service.can_read_project(project.id, admin) is True
    assert await service.can_write_project(project.id, admin) is True
    assert await service.can_read_project(project.id, outsider) is False
    assert await service.can_write_project(project.id, outsider) is False

    member = await service.require_member(project.id, editor)
    assert member is not None
    assert member.role == ProjectMemberRole.editor.value

    deleted_viewer = (await task_session.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == viewer.id,
        )
    )).scalar_one()
    deleted_viewer.deleted_at = datetime.now(timezone.utc)
    await task_session.commit()
    assert await service.can_read_project(project.id, viewer) is False
    assert await service.can_write_project(project.id, viewer) is False


@pytest.mark.asyncio
async def test_access_service_preserves_legacy_owner_fallback_and_raises_clear_errors(task_session):
    owner = User(id=201, username="legacy-owner", hashed_password="x", is_admin=False, is_active=True)
    outsider = User(id=202, username="legacy-outsider", hashed_password="x", is_admin=False, is_active=True)
    task_session.add_all([
        owner,
        outsider,
        NovelProject(id="legacy-owner-project", user_id=owner.id, title="Legacy project"),
    ])
    await task_session.commit()
    service = ProjectAccessService(task_session)

    assert await service.can_read_project("legacy-owner-project", owner) is True
    assert await service.can_write_project("legacy-owner-project", owner) is True
    with pytest.raises(HTTPException) as denied:
        await service.require_member("legacy-owner-project", outsider)
    assert denied.value.status_code == 403

    with pytest.raises(HTTPException) as missing:
        await service.require_member("missing-project", owner)
    assert missing.value.status_code == 404


@pytest.mark.asyncio
async def test_access_service_does_not_treat_inactive_member_as_access(task_session):
    owner = User(id=301, username="inactive-owner", hashed_password="x", is_admin=False, is_active=True)
    member = User(id=302, username="inactive-member", hashed_password="x", is_admin=False, is_active=False)
    project = NovelProject(id="inactive-member-project", user_id=owner.id, title="Inactive member")
    task_session.add_all([
        owner,
        member,
        project,
        ProjectMember(project_id=project.id, user_id=member.id, role=ProjectMemberRole.editor.value),
    ])
    await task_session.commit()
    service = ProjectAccessService(task_session)
    assert await service.can_read_project(project.id, member) is False
    assert await service.can_write_project(project.id, member) is False


# Imported at the bottom intentionally: the first red run must fail before the model is implemented.
from app.models.project_member import ProjectMemberRole



@pytest.mark.asyncio
async def test_access_service_keeps_owner_immutable(task_session):
    owner = User(id=401, username="owner-immutable", hashed_password="x", is_admin=False, is_active=True)
    editor = User(id=402, username="editor-immutable", hashed_password="x", is_admin=False, is_active=True)
    project = NovelProject(id="owner-immutable-project", user_id=owner.id, title="Owner immutable")
    task_session.add_all([owner, editor, project, ProjectMember(
        project_id=project.id, user_id=owner.id, role=ProjectMemberRole.owner.value
    )])
    await task_session.commit()
    service = ProjectAccessService(task_session)

    with pytest.raises(HTTPException) as transfer:
        await service.add_or_restore_member(project.id, editor.id, ProjectMemberRole.owner, owner)
    assert transfer.value.status_code == 422

    with pytest.raises(HTTPException) as remove:
        await service.remove_member(project.id, owner.id, owner)
    assert remove.value.status_code == 422

    with pytest.raises(HTTPException) as demote:
        await service.add_or_restore_member(project.id, owner.id, ProjectMemberRole.viewer, owner)
    assert demote.value.status_code == 422
