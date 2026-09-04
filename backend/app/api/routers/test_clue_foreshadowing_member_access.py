from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from app.core.dependencies import get_current_user
from app.db.session import get_session
from app.main import app
from app.models import Chapter, NovelProject, ProjectMember, ProjectMemberRole, User


async def _user(session, user_id: int, username: str) -> User:
    user = User(
        id=user_id,
        username=username,
        email=f"{username}@example.com",
        hashed_password="not-used-in-route-test",
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
        async with httpx.AsyncClient(transport=transport, base_url="http://clue-foreshadowing-member-access") as client:
            return await client.request(method, url, **kwargs)

    yield request
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_current_user, None)


async def _project_with_members(task_session, suffix: str):
    owner = await _user(task_session, 7101, f"clue-owner-{suffix}")
    viewer = await _user(task_session, 7102, f"clue-viewer-{suffix}")
    editor = await _user(task_session, 7103, f"clue-editor-{suffix}")
    outsider = await _user(task_session, 7104, f"clue-outsider-{suffix}")
    project = NovelProject(id=f"clue-member-{suffix}", user_id=owner.id, title="成员权限线索与伏笔")
    chapter = Chapter(project_id=project.id, chapter_number=1, status="not_generated")
    task_session.add_all(
        [
            project,
            chapter,
            ProjectMember(project_id=project.id, user_id=viewer.id, role=ProjectMemberRole.viewer.value),
            ProjectMember(project_id=project.id, user_id=editor.id, role=ProjectMemberRole.editor.value),
        ]
    )
    await task_session.commit()
    await task_session.refresh(chapter)
    return owner, viewer, editor, outsider, project, chapter


@pytest.mark.asyncio
async def test_clue_and_foreshadowing_routes_allow_viewer_read_and_reject_nonmember(task_session, http_client):
    _owner, viewer, _editor, outsider, project, _chapter = await _project_with_members(task_session, "read")

    viewer_clues = await http_client("GET", f"/api/projects/{project.id}/clues", user=viewer)
    assert viewer_clues.status_code == 200
    assert viewer_clues.json() == []

    viewer_foreshadowings = await http_client("GET", f"/api/projects/{project.id}/foreshadowings", user=viewer)
    assert viewer_foreshadowings.status_code == 200
    assert viewer_foreshadowings.json()["total"] == 0

    outsider_clues = await http_client("GET", f"/api/projects/{project.id}/clues", user=outsider)
    assert outsider_clues.status_code == 403

    outsider_foreshadowings = await http_client("GET", f"/api/projects/{project.id}/foreshadowings", user=outsider)
    assert outsider_foreshadowings.status_code == 403


@pytest.mark.asyncio
async def test_clue_and_foreshadowing_routes_reject_viewer_write_and_allow_editor_write(task_session, http_client):
    _owner, viewer, editor, outsider, project, chapter = await _project_with_members(task_session, "write")

    clue_payload = {
        "name": "盐痕账册",
        "clue_type": "key_evidence",
        "description": "账册边缘留有盐痕编号。",
    }
    foreshadowing_payload = {
        "chapter_id": chapter.id,
        "chapter_number": chapter.chapter_number,
        "content": "主角在账册边缘发现盐痕编号。",
        "type": "mystery",
        "keywords": ["盐痕", "账册"],
    }

    viewer_clue = await http_client("POST", f"/api/projects/{project.id}/clues", user=viewer, json=clue_payload)
    assert viewer_clue.status_code == 403
    viewer_foreshadowing = await http_client(
        "POST", f"/api/projects/{project.id}/foreshadowings", user=viewer, json=foreshadowing_payload
    )
    assert viewer_foreshadowing.status_code == 403

    outsider_clue = await http_client("POST", f"/api/projects/{project.id}/clues", user=outsider, json=clue_payload)
    assert outsider_clue.status_code == 403
    outsider_foreshadowing = await http_client(
        "POST", f"/api/projects/{project.id}/foreshadowings", user=outsider, json=foreshadowing_payload
    )
    assert outsider_foreshadowing.status_code == 403

    editor_clue = await http_client("POST", f"/api/projects/{project.id}/clues", user=editor, json=clue_payload)
    assert editor_clue.status_code == 200
    assert editor_clue.json()["name"] == clue_payload["name"]

    editor_foreshadowing = await http_client(
        "POST", f"/api/projects/{project.id}/foreshadowings", user=editor, json=foreshadowing_payload
    )
    assert editor_foreshadowing.status_code == 200
    assert editor_foreshadowing.json()["content"] == foreshadowing_payload["content"]
