"""Minimal H-2 finalize access contract for collaborative Writer projects."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from fastapi import BackgroundTasks, HTTPException

from app.api.routers import writer
from app.models import BlueprintCharacter, Chapter, ChapterVersion, NovelProject, ProjectMember, User
from app.models.project_member import ProjectMemberRole
from app.schemas.novel import FinalizeChapterRequest
from app.schemas.user import UserInDB

PROJECT_ID = "writer-member-finalize-project"
CHAPTER_NUMBER = 7


@dataclass(frozen=True)
class Fixture:
    owner: User
    editor: User
    admin: User
    viewer: User
    outsider: User
    project: NovelProject
    chapter: Chapter
    selected_version: ChapterVersion


def _principal(user: User) -> UserInDB:
    return UserInDB(
        id=int(user.id), username=user.username, email=user.email,
        hashed_password=user.hashed_password, is_admin=bool(user.is_admin),
        is_active=bool(user.is_active),
    )


async def _seed(session) -> Fixture:
    owner = User(id=95401, username="finalize-owner", hashed_password="x", is_active=True)
    editor = User(id=95402, username="finalize-editor", hashed_password="x", is_active=True)
    admin = User(id=95405, username="finalize-admin", hashed_password="x", is_active=True, is_admin=True)
    viewer = User(id=95403, username="finalize-viewer", hashed_password="x", is_active=True)
    outsider = User(id=95404, username="finalize-outsider", hashed_password="x", is_active=True)
    project = NovelProject(id=PROJECT_ID, user_id=owner.id, title="协作定稿项目")
    session.add_all([
        owner, editor, admin, viewer, outsider, project,
        ProjectMember(project_id=PROJECT_ID, user_id=owner.id, role=ProjectMemberRole.owner.value),
        ProjectMember(project_id=PROJECT_ID, user_id=editor.id, role=ProjectMemberRole.editor.value),
        ProjectMember(project_id=PROJECT_ID, user_id=viewer.id, role=ProjectMemberRole.viewer.value),
        BlueprintCharacter(project_id=PROJECT_ID, name="兰舟", position=1),
        BlueprintCharacter(project_id=PROJECT_ID, name="闻雪", position=2),
    ])
    await session.flush()
    chapter = Chapter(project_id=PROJECT_ID, chapter_number=CHAPTER_NUMBER, status="successful")
    session.add(chapter)
    await session.flush()
    selected_version = ChapterVersion(
        chapter_id=chapter.id, version_label="owner-selected", provider="fixture",
        content="协作定稿正文。", content_hash="writer-member-finalize-selected", status="selected",
    )
    session.add(selected_version)
    await session.flush()
    chapter.selected_version_id = selected_version.id
    await session.commit()
    return Fixture(owner, editor, admin, viewer, outsider, project, chapter, selected_version)


def _request(fixture: Fixture) -> FinalizeChapterRequest:
    return FinalizeChapterRequest(
        project_id=fixture.project.id,
        selected_version_id=fixture.selected_version.id,
        async_finalize=False,
        skip_vector_update=True,
    )


def _install_pipeline_fakes(monkeypatch, calls: dict[str, dict[str, Any]]) -> None:
    class FakeFinalizeService:
        def __init__(self, *_args: Any, **_kwargs: Any):
            pass

        async def finalize_chapter(self, **kwargs: Any) -> dict[str, Any]:
            calls["finalize"] = kwargs
            return {"success": True, "updates": {}}

    class FakeMemoryLayerService:
        def __init__(self, *_args: Any, **_kwargs: Any):
            pass

        async def update_memory_after_chapter(self, **kwargs: Any) -> dict[str, Any]:
            calls["memory"] = kwargs
            return {"success": True, "dynamic_character_names": [], "dynamic_characters_created": 0}

    class FakeForeshadowingService:
        def __init__(self, *_args: Any, **_kwargs: Any):
            pass

        async def auto_resolve_from_chapter(self, **_kwargs: Any) -> dict[str, Any]:
            return {"resolved": 0, "reinforced": 0, "resolution_ids": [], "unresolved_due_ids": []}

        async def auto_collect_from_chapter(self, **_kwargs: Any) -> dict[str, Any]:
            return {"created": 0}

        async def check_and_create_reminders(self, **_kwargs: Any) -> list[Any]:
            return []

    class FakeClueTrackerService:
        def __init__(self, *_args: Any, **_kwargs: Any):
            pass

        async def sync_from_foreshadowings(self, _project_id: str) -> dict[str, Any]:
            return {"success": True}

    class FakeKnowledgeGraphService:
        def __init__(self, *_args: Any, **_kwargs: Any):
            pass

        async def sync_from_story_memory(self, _project_id: str) -> dict[str, Any]:
            return {"success": True}

    class FakeCacheService:
        async def delete(self, _key: str) -> None:
            return None

    monkeypatch.setattr(writer, "LLMService", lambda _session: object())
    monkeypatch.setattr(writer, "PromptService", lambda _session: object())
    monkeypatch.setattr(writer, "FinalizeService", FakeFinalizeService)
    monkeypatch.setattr(writer, "MemoryLayerService", FakeMemoryLayerService)
    monkeypatch.setattr(writer, "ForeshadowingService", FakeForeshadowingService)
    monkeypatch.setattr(writer, "ClueTrackerService", FakeClueTrackerService)
    monkeypatch.setattr(writer, "KnowledgeGraphService", FakeKnowledgeGraphService)
    monkeypatch.setattr(writer, "CacheService", FakeCacheService)


@pytest.mark.asyncio
@pytest.mark.parametrize("actor_kind", ["owner", "editor", "admin"])
async def test_project_writers_can_finalize_shared_selected_version_and_read_project_characters(task_session, monkeypatch, actor_kind: str):
    fixture = await _seed(task_session)
    actor = getattr(fixture, actor_kind)
    calls: dict[str, dict[str, Any]] = {}
    _install_pipeline_fakes(monkeypatch, calls)

    response = await writer.finalize_chapter(
        CHAPTER_NUMBER, _request(fixture), BackgroundTasks(), task_session, _principal(actor)
    )

    assert response.result["finalize"]["success"] is True
    assert calls["finalize"]["user_id"] == actor.id
    assert calls["memory"]["user_id"] == actor.id
    assert calls["memory"]["character_names"] == ["兰舟", "闻雪"]


@pytest.mark.asyncio
@pytest.mark.parametrize("actor_kind", ["viewer", "outsider"])
async def test_viewer_and_nonmember_receive_403_from_finalize_entry(task_session, actor_kind: str):
    fixture = await _seed(task_session)

    with pytest.raises(HTTPException) as denied:
        await writer.finalize_chapter(
            CHAPTER_NUMBER,
            _request(fixture),
            BackgroundTasks(),
            task_session,
            _principal(getattr(fixture, actor_kind)),
        )

    assert denied.value.status_code == 403

