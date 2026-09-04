from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select

from app.core.dependencies import get_current_user
from app.db.session import get_session
from app.main import app
from app.models import NovelProject, ProjectMember, ProjectMemberRole, User


async def _user(session, user_id: int, username: str, *, is_admin: bool = False) -> User:
    user = User(
        id=user_id,
        username=username,
        email=f"{username}@example.com",
        hashed_password="not-used-in-route-test",
        is_admin=is_admin,
        is_active=True,
    )
    session.add(user)
    await session.flush()
    return user


@pytest.fixture
def http_client(task_session):
    current_user = {"user": None}

    async def override_session():
        yield task_session

    async def override_current_user():
        return current_user["user"]

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = override_current_user
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)

    async def request(method: str, url: str, *, user: User, **kwargs):
        current_user["user"] = SimpleNamespace(
            id=user.id,
            is_admin=bool(user.is_admin),
            is_active=bool(user.is_active),
        )
        async with httpx.AsyncClient(transport=transport, base_url="http://project-members") as client:
            return await client.request(method, url, **kwargs)

    yield request
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_project_members_http_owner_can_list_add_update_remove_and_restore(task_session, http_client):
    owner = await _user(task_session, 5101, "members-owner")
    target = await _user(task_session, 5102, "members-target")
    project = NovelProject(id="project-members-http", user_id=owner.id, title="成员管理 HTTP")
    task_session.add_all(
        [
            project,
            ProjectMember(
                project_id=project.id,
                user_id=target.id,
                role=ProjectMemberRole.viewer.value,
            ),
        ]
    )
    await task_session.commit()

    listed = await http_client("GET", f"/api/projects/{project.id}/members", user=owner)
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    assert listed.json()["members"][0]["user_id"] == target.id
    assert listed.json()["members"][0]["role"] == "viewer"

    added = await http_client(
        "POST",
        f"/api/projects/{project.id}/members",
        user=owner,
        json={"user_id": target.id, "role": "editor"},
    )
    assert added.status_code == 200
    assert added.json()["user_id"] == target.id
    assert added.json()["role"] == "editor"
    assert added.json()["deleted_at"] is None

    updated = await http_client(
        "PATCH",
        f"/api/projects/{project.id}/members/{target.id}",
        user=owner,
        json={"role": "viewer"},
    )
    assert updated.status_code == 200
    assert updated.json()["role"] == "viewer"

    removed = await http_client(
        "DELETE",
        f"/api/projects/{project.id}/members/{target.id}",
        user=owner,
    )
    assert removed.status_code == 200
    assert removed.json()["deleted_at"] is not None
    assert datetime.fromisoformat(removed.json()["deleted_at"].replace("Z", "+00:00"))

    hidden = await http_client("GET", f"/api/projects/{project.id}/members", user=owner)
    assert hidden.status_code == 200
    assert hidden.json()["count"] == 0

    restored = await http_client(
        "POST",
        f"/api/projects/{project.id}/members",
        user=owner,
        json={"user_id": target.id, "role": "editor"},
    )
    assert restored.status_code == 200
    assert restored.json()["user_id"] == target.id
    assert restored.json()["role"] == "editor"
    assert restored.json()["deleted_at"] is None

    persisted = (
        await task_session.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project.id,
                ProjectMember.user_id == target.id,
            )
        )
    ).scalar_one()
    assert persisted.deleted_at is None
    assert persisted.role == "editor"


@pytest.mark.asyncio
async def test_project_members_http_admin_can_manage_and_editor_viewer_cannot(task_session, http_client):
    owner = await _user(task_session, 5201, "matrix-owner")
    admin = await _user(task_session, 5202, "matrix-admin", is_admin=True)
    editor = await _user(task_session, 5203, "matrix-editor")
    viewer = await _user(task_session, 5204, "matrix-viewer")
    outsider = await _user(task_session, 5205, "matrix-outsider")
    target = await _user(task_session, 5206, "matrix-target")
    project = NovelProject(id="project-members-matrix", user_id=owner.id, title="成员矩阵")
    task_session.add_all(
        [
            project,
            ProjectMember(project_id=project.id, user_id=owner.id, role="owner"),
            ProjectMember(project_id=project.id, user_id=editor.id, role="editor"),
            ProjectMember(project_id=project.id, user_id=viewer.id, role="viewer"),
        ]
    )
    await task_session.commit()

    admin_list = await http_client("GET", f"/api/projects/{project.id}/members", user=admin)
    assert admin_list.status_code == 200
    assert {item["user_id"] for item in admin_list.json()["members"]} == {
        owner.id,
        editor.id,
        viewer.id,
    }

    admin_add = await http_client(
        "POST",
        f"/api/projects/{project.id}/members",
        user=admin,
        json={"user_id": target.id, "role": "viewer"},
    )
    assert admin_add.status_code == 200

    for actor in (editor, viewer):
        response = await http_client("GET", f"/api/projects/{project.id}/members", user=actor)
        assert response.status_code == 200
        assert response.json()["can_manage"] is False
        assert response.json()["access_role"] == ("editor" if actor.id == editor.id else "viewer")
        response = await http_client(
            "POST",
            f"/api/projects/{project.id}/members",
            user=actor,
            json={"user_id": target.id, "role": "editor"},
        )
        assert response.status_code == 403
        response = await http_client(
            "PATCH",
            f"/api/projects/{project.id}/members/{target.id}",
            user=actor,
            json={"role": "viewer"},
        )
        assert response.status_code == 403
        response = await http_client(
            "DELETE",
            f"/api/projects/{project.id}/members/{target.id}",
            user=actor,
        )
        assert response.status_code == 403

    outsider_list = await http_client("GET", f"/api/projects/{project.id}/members", user=outsider)
    assert outsider_list.status_code == 403
    for method, url, kwargs in (
        ("POST", f"/api/projects/{project.id}/members", {"json": {"user_id": target.id, "role": "editor"}}),
        ("PATCH", f"/api/projects/{project.id}/members/{target.id}", {"json": {"role": "viewer"}}),
        ("DELETE", f"/api/projects/{project.id}/members/{target.id}", {}),
    ):
        response = await http_client(method, url, user=outsider, **kwargs)
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_project_members_http_validates_role_and_target_and_preserves_legacy_owner(task_session, http_client):
    owner = await _user(task_session, 5301, "legacy-http-owner")
    inactive = await _user(task_session, 5302, "inactive-http-target")
    inactive.is_active = False
    project = NovelProject(id="project-members-validation", user_id=owner.id, title="验证")
    task_session.add(project)
    await task_session.commit()

    invalid_role = await http_client(
        "POST",
        f"/api/projects/{project.id}/members",
        user=owner,
        json={"user_id": inactive.id, "role": "administrator"},
    )
    assert invalid_role.status_code == 422

    inactive_target = await http_client(
        "POST",
        f"/api/projects/{project.id}/members",
        user=owner,
        json={"user_id": inactive.id, "role": "viewer"},
    )
    assert inactive_target.status_code == 404

    missing_target = await http_client(
        "POST",
        f"/api/projects/{project.id}/members",
        user=owner,
        json={"user_id": 5399, "role": "viewer"},
    )
    assert missing_target.status_code == 404

    missing_member = await http_client(
        "DELETE",
        f"/api/projects/{project.id}/members/{inactive.id}",
        user=owner,
    )
    assert missing_member.status_code == 404


@pytest.mark.asyncio
async def test_project_members_http_cannot_transfer_or_demote_owner(task_session, http_client):
    owner = await _user(task_session, 5201, "immutable-owner")
    target = await _user(task_session, 5202, "immutable-target")
    project = NovelProject(id="project-members-owner-immutable", user_id=owner.id, title="Owner immutable HTTP")
    task_session.add_all([
        project,
        ProjectMember(project_id=project.id, user_id=owner.id, role=ProjectMemberRole.owner.value),
    ])
    await task_session.commit()

    transfer = await http_client(
        "POST",
        f"/api/projects/{project.id}/members",
        user=owner,
        json={"user_id": target.id, "role": "owner"},
    )
    assert transfer.status_code == 422

    demote = await http_client(
        "PATCH",
        f"/api/projects/{project.id}/members/{owner.id}",
        user=owner,
        json={"role": "viewer"},
    )
    assert demote.status_code == 422

    remove = await http_client(
        "DELETE",
        f"/api/projects/{project.id}/members/{owner.id}",
        user=owner,
    )
    assert remove.status_code == 422
