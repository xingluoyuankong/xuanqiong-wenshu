from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import select

from app.api.routers.writer import _assert_finalize_selection_current, edit_chapter_content_fast
from app.models.novel import Chapter, ChapterVersion, NovelProject
from app.models.user import User
from app.schemas.novel import EditChapterRequest


async def _seed_chapter(task_session):
    user = User(
        id=911,
        username="version-editor",
        email="version-editor@example.com",
        hashed_password="not-used",
        is_active=True,
    )
    project = NovelProject(id="immutable-version-project", user_id=user.id, title="版本测试")
    task_session.add_all([user, project])
    await task_session.flush()
    chapter = Chapter(
        project_id=project.id,
        chapter_number=1,
        status="successful",
        revision=1,
        word_count=4,
    )
    task_session.add(chapter)
    await task_session.flush()
    original = ChapterVersion(
        chapter_id=chapter.id,
        content="旧版正文",
        version_label="generated",
        content_hash=hashlib.sha256("旧版正文".encode("utf-8")).hexdigest(),
    )
    task_session.add(original)
    await task_session.flush()
    chapter.selected_version_id = original.id
    await task_session.commit()
    return user, project, chapter, original


@pytest.mark.anyio
async def test_manual_edit_creates_child_version_without_mutating_parent(task_session, monkeypatch):
    user, project, chapter, original = await _seed_chapter(task_session)

    async def fake_schema(_self, _project_id, _chapter_number):
        return SimpleNamespace(selected_version_id=chapter.selected_version_id)

    monkeypatch.setattr(
        "app.services.novel_service.NovelService.get_chapter_schema_for_admin",
        fake_schema,
    )
    await edit_chapter_content_fast(
        project.id,
        EditChapterRequest(chapter_number=1, content="新版正文", base_revision=1),
        BackgroundTasks(),
        session=task_session,
        current_user=SimpleNamespace(id=user.id),
    )

    versions = list((await task_session.execute(
        select(ChapterVersion).where(ChapterVersion.chapter_id == chapter.id).order_by(ChapterVersion.id)
    )).scalars().all())
    await task_session.refresh(chapter)
    await task_session.refresh(original)

    assert len(versions) == 2
    assert original.content == "旧版正文"
    edited = versions[-1]
    assert edited.content == "新版正文"
    assert edited.parent_version_id == original.id
    assert edited.content_hash == hashlib.sha256("新版正文".encode("utf-8")).hexdigest()
    assert chapter.selected_version_id == edited.id
    assert chapter.revision == 2


@pytest.mark.anyio
async def test_manual_edit_rejects_stale_base_revision_without_creating_version(task_session, monkeypatch):
    user, project, chapter, _original = await _seed_chapter(task_session)

    async def fake_schema(_self, _project_id, _chapter_number):
        return SimpleNamespace(selected_version_id=chapter.selected_version_id)

    monkeypatch.setattr(
        "app.services.novel_service.NovelService.get_chapter_schema_for_admin",
        fake_schema,
    )
    with pytest.raises(HTTPException) as error:
        await edit_chapter_content_fast(
            project.id,
            EditChapterRequest(chapter_number=1, content="过期编辑", base_revision=9),
            BackgroundTasks(),
            session=task_session,
            current_user=SimpleNamespace(id=user.id),
        )

    assert error.value.status_code == 409
    assert error.value.detail["code"] == "CHAPTER_REVISION_CONFLICT"
    assert error.value.detail["current_revision"] == 1
    count = len(list((await task_session.execute(
        select(ChapterVersion).where(ChapterVersion.chapter_id == chapter.id)
    )).scalars().all()))
    assert count == 1


@pytest.mark.anyio
async def test_finalize_selection_guard_rejects_superseded_version(task_session):
    _user, project, chapter, original = await _seed_chapter(task_session)
    replacement = ChapterVersion(
        chapter_id=chapter.id,
        content="替代正文",
        version_label="manual_edit",
        parent_version_id=original.id,
    )
    task_session.add(replacement)
    await task_session.flush()
    chapter.selected_version_id = replacement.id
    await task_session.commit()

    with pytest.raises(Exception, match="superseded"):
        await _assert_finalize_selection_current(
            task_session,
            project_id=project.id,
            chapter_number=chapter.chapter_number,
            selected_version_id=original.id,
        )
