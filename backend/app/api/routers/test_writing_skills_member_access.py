from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi import HTTPException

from app.api.routers import writing_skills
from app.models import NovelProject, ProjectMember, User
from app.models.project_member import ProjectMemberRole
from app.schemas.user import UserInDB


@dataclass(frozen=True)
class Fixture:
    owner: User
    editor: User
    viewer: User
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


async def _seed(task_session) -> Fixture:
    owner = User(id=97301, username="skills-owner", email="skills-owner@example.com", hashed_password="x", is_active=True)
    editor = User(id=97302, username="skills-editor", email="skills-editor@example.com", hashed_password="x", is_active=True)
    viewer = User(id=97303, username="skills-viewer", email="skills-viewer@example.com", hashed_password="x", is_active=True)
    outsider = User(id=97304, username="skills-outsider", email="skills-outsider@example.com", hashed_password="x", is_active=True)
    project = NovelProject(id="writing-skills-member-project", user_id=owner.id, title="写作技能成员项目")
    task_session.add_all(
        [
            owner,
            editor,
            viewer,
            outsider,
            project,
            ProjectMember(project_id=project.id, user_id=owner.id, role=ProjectMemberRole.owner.value),
            ProjectMember(project_id=project.id, user_id=editor.id, role=ProjectMemberRole.editor.value),
            ProjectMember(project_id=project.id, user_id=viewer.id, role=ProjectMemberRole.viewer.value),
        ]
    )
    await task_session.commit()
    return Fixture(owner, editor, viewer, outsider, project)


@pytest.mark.asyncio
@pytest.mark.parametrize("actor_kind", ["viewer", "outsider"])
async def test_project_scoped_skill_execution_rejects_viewer_and_nonmember(task_session, monkeypatch, actor_kind: str):
    fixture = await _seed(task_session)
    called = False

    class UnexpectedService:
        def __init__(self, _session):
            nonlocal called
            called = True

    monkeypatch.setattr(writing_skills, "WritingSkillsService", UnexpectedService)

    with pytest.raises(HTTPException) as denied:
        await writing_skills.execute_skill(
            "outline-polish",
            writing_skills.ExecuteSkillRequest(
                prompt="优化冲突推进",
                project_id=fixture.project.id,
                chapter_number=1,
            ),
            session=task_session,
            current_user=_principal(getattr(fixture, actor_kind)),
        )

    assert denied.value.status_code == 403
    assert called is False


@pytest.mark.asyncio
async def test_editor_can_execute_project_scoped_skill(task_session, monkeypatch):
    fixture = await _seed(task_session)
    captured: dict[str, object] = {}

    class FakeService:
        def __init__(self, _session):
            pass

        async def execute_skill(self, **kwargs):
            captured.update(kwargs)
            return {"mode": "fixture", "suggestion": "补强冲突推进"}

    monkeypatch.setattr(writing_skills, "WritingSkillsService", FakeService)

    result = await writing_skills.execute_skill(
        "outline-polish",
        writing_skills.ExecuteSkillRequest(
            prompt="优化冲突推进",
            project_id=fixture.project.id,
            chapter_number=1,
        ),
        session=task_session,
        current_user=_principal(fixture.editor),
    )

    assert result == {"mode": "fixture", "suggestion": "补强冲突推进"}
    assert captured == {
        "skill_id": "outline-polish",
        "prompt": "优化冲突推进",
        "project_id": fixture.project.id,
        "chapter_number": 1,
        "user_id": fixture.editor.id,
    }
