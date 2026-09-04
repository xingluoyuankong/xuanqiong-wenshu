"""Member-access regression contract for the first novels.py gate sweep."""
from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

from app.api.routers import novels
from app.models import Chapter, ChapterVersion, NovelProject, ProjectMember, User
from app.models.project_member import ProjectMemberRole
from app.schemas.novel import ConverseRequest
from app.schemas.user import UserInDB

PROJECT_ID = "novels-member-access-project"
OTHER_PROJECT_ID = "novels-member-access-other-project"


@dataclass(frozen=True)
class Fixture:
    owner: User
    editor: User
    viewer: User
    admin: User
    outsider: User
    project: NovelProject
    other_project: NovelProject
    chapter: Chapter
    version: ChapterVersion


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
    owner = User(id=96101, username="novels-owner", email="novels-owner@example.com", hashed_password="x", is_active=True)
    editor = User(id=96102, username="novels-editor", email="novels-editor@example.com", hashed_password="x", is_active=True)
    viewer = User(id=96103, username="novels-viewer", email="novels-viewer@example.com", hashed_password="x", is_active=True)
    admin = User(id=96104, username="novels-admin", email="novels-admin@example.com", hashed_password="x", is_active=True, is_admin=True)
    outsider = User(id=96105, username="novels-outsider", email="novels-outsider@example.com", hashed_password="x", is_active=True)
    project = NovelProject(id=PROJECT_ID, user_id=owner.id, title="成员访问项目")
    other_project = NovelProject(id=OTHER_PROJECT_ID, user_id=outsider.id, title="隔离项目")
    session.add_all(
        [
            owner,
            editor,
            viewer,
            admin,
            outsider,
            project,
            other_project,
            ProjectMember(project_id=PROJECT_ID, user_id=owner.id, role=ProjectMemberRole.owner.value),
            ProjectMember(project_id=PROJECT_ID, user_id=editor.id, role=ProjectMemberRole.editor.value),
            ProjectMember(project_id=PROJECT_ID, user_id=viewer.id, role=ProjectMemberRole.viewer.value),
        ]
    )
    await session.flush()

    chapter = Chapter(
        project_id=PROJECT_ID,
        chapter_number=1,
        status="successful",
        real_summary="成员读取章节摘要",
    )
    session.add(chapter)
    await session.flush()
    version = ChapterVersion(
        chapter_id=chapter.id,
        version_label="selected-v1",
        provider="fixture",
        content="成员可读取的章节正文。",
        content_hash="novels-member-access-v1",
        status="selected",
        metadata_={
            "quality_metrics": {"score": 912, "word_count": 13},
            "quality_gate": {"blockers": [], "warnings": []},
        },
    )
    session.add(version)
    await session.flush()
    chapter.selected_version_id = version.id
    await session.commit()
    return Fixture(owner, editor, viewer, admin, outsider, project, other_project, chapter, version)


@pytest.mark.asyncio
@pytest.mark.parametrize("actor_kind", ["owner", "editor", "viewer", "admin"])
async def test_quality_trend_is_readable_by_all_project_readers(task_session, actor_kind: str):
    fixture = await _seed(task_session)

    payload = await novels.get_quality_trend(
        fixture.project.id,
        session=task_session,
        current_user=_principal(getattr(fixture, actor_kind)),
    )

    assert payload["project_id"] == PROJECT_ID
    assert payload["chapter_count"] == 1
    assert payload["chapters"][0]["score"] == 912


@pytest.mark.asyncio
async def test_quality_trend_keeps_cross_project_and_missing_project_isolation(task_session):
    fixture = await _seed(task_session)

    with pytest.raises(HTTPException) as denied:
        await novels.get_quality_trend(
            fixture.project.id,
            session=task_session,
            current_user=_principal(fixture.outsider),
        )
    assert denied.value.status_code == 403

    with pytest.raises(HTTPException) as missing:
        await novels.get_quality_trend(
            "novels-member-access-missing",
            session=task_session,
            current_user=_principal(fixture.owner),
        )
    assert missing.value.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("actor_kind", ["owner", "editor", "viewer", "admin"])
async def test_chapter_detail_is_readable_by_all_project_readers(task_session, actor_kind: str):
    fixture = await _seed(task_session)

    response = await novels.get_chapter(
        fixture.project.id,
        fixture.chapter.chapter_number,
        session=task_session,
        current_user=_principal(getattr(fixture, actor_kind)),
    )

    assert response.chapter_number == 1
    assert response.content == "成员可读取的章节正文。"
    assert response.selected_version_id == fixture.version.id


@pytest.mark.asyncio
async def test_chapter_detail_rejects_nonmember_and_wrong_chapter_without_leak(task_session):
    fixture = await _seed(task_session)

    with pytest.raises(HTTPException) as denied:
        await novels.get_chapter(
            fixture.project.id,
            fixture.chapter.chapter_number,
            session=task_session,
            current_user=_principal(fixture.outsider),
        )
    assert denied.value.status_code == 403

    with pytest.raises(HTTPException) as missing:
        await novels.get_chapter(
            fixture.project.id,
            99,
            session=task_session,
            current_user=_principal(fixture.editor),
        )
    assert missing.value.status_code == 404


class _FakeExportService:
    calls: list[tuple[str, str]] = []

    def __init__(self, _session):
        pass

    async def export_novel_as_txt(self, project_id: str) -> str:
        self.calls.append(("txt", project_id))
        return "成员导出 TXT"

    async def preflight_export(self, project_id: str) -> dict[str, Any]:
        self.calls.append(("preflight", project_id))
        return {"ready": True, "project_id": project_id, "issues": []}

    async def export_novel_as_docx(self, project_id: str) -> bytes:
        self.calls.append(("docx", project_id))
        return b"fixture-docx"


@pytest.mark.asyncio
@pytest.mark.parametrize("route_name", ["txt", "preflight", "docx"])
@pytest.mark.parametrize("actor_kind", ["owner", "editor", "viewer", "admin"])
async def test_export_and_preflight_are_readable_by_all_project_readers(
    task_session, monkeypatch, route_name: str, actor_kind: str
):
    fixture = await _seed(task_session)
    _FakeExportService.calls = []
    monkeypatch.setattr(novels, "ExportService", _FakeExportService)
    actor = _principal(getattr(fixture, actor_kind))

    if route_name == "txt":
        response = await novels.export_novel_as_txt(fixture.project.id, session=task_session, current_user=actor)
        assert response.media_type == "text/plain; charset=utf-8"
        assert response.body == "成员导出 TXT".encode()
    elif route_name == "preflight":
        response = await novels.preflight_export_novel(fixture.project.id, session=task_session, current_user=actor)
        assert response == {"ready": True, "project_id": PROJECT_ID, "issues": []}
    else:
        response = await novels.export_novel_as_docx(fixture.project.id, session=task_session, current_user=actor)
        assert response.media_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        assert response.body == b"fixture-docx"

    assert (route_name, PROJECT_ID) in _FakeExportService.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("route_name", ["txt", "preflight", "docx"])
async def test_export_and_preflight_reject_nonmember_before_downstream_access(
    task_session, monkeypatch, route_name: str
):
    fixture = await _seed(task_session)
    _FakeExportService.calls = []
    monkeypatch.setattr(novels, "ExportService", _FakeExportService)
    actor = _principal(fixture.outsider)

    with pytest.raises(HTTPException) as denied:
        if route_name == "txt":
            await novels.export_novel_as_txt(fixture.project.id, session=task_session, current_user=actor)
        elif route_name == "preflight":
            await novels.preflight_export_novel(fixture.project.id, session=task_session, current_user=actor)
        else:
            await novels.export_novel_as_docx(fixture.project.id, session=task_session, current_user=actor)

    assert denied.value.status_code == 403
    assert _FakeExportService.calls == []


class _FakeNovelService:
    appended: list[tuple[str, str, str]] = []

    def __init__(self, _session):
        pass

    async def list_conversations(self, project_id: str):
        return []

    async def append_conversation(self, project_id: str, role: str, content: str, metadata=None):
        self.appended.append((project_id, role, content))


class _FakePromptService:
    def __init__(self, _session):
        pass

    async def get_prompt(self, _name: str):
        return "fixture concept prompt"


class _FakeLLMService:
    def __init__(self, _session):
        pass

    @staticmethod
    def daily_limit_scope(_key: str):
        return nullcontext()


@pytest.mark.asyncio
@pytest.mark.parametrize("actor_kind", ["owner", "editor", "admin"])
async def test_concept_conversation_is_writable_by_project_writers(task_session, monkeypatch, actor_kind: str):
    fixture = await _seed(task_session)
    _FakeNovelService.appended = []
    monkeypatch.setattr(novels, "NovelService", _FakeNovelService)
    monkeypatch.setattr(novels, "PromptService", _FakePromptService)
    monkeypatch.setattr(novels, "LLMService", _FakeLLMService)

    async def fake_call_generation_text(**_kwargs):
        return SimpleNamespace(
            text='{"ai_message":"继续补充冲突。","ui_control":{"type":"text_input","placeholder":"继续"},"conversation_state":{},"is_complete":false}'
        )

    monkeypatch.setattr(novels, "call_generation_text", fake_call_generation_text)
    response = await novels.converse_with_concept(
        fixture.project.id,
        ConverseRequest(user_input={"text": "主角要面对什么冲突？"}, conversation_state={}),
        session=task_session,
        current_user=_principal(getattr(fixture, actor_kind)),
    )

    assert response.ai_message == "继续补充冲突。"
    assert [role for _, role, _ in _FakeNovelService.appended] == ["user", "assistant"]
    assert all(project_id == PROJECT_ID for project_id, _, _ in _FakeNovelService.appended)


@pytest.mark.asyncio
@pytest.mark.parametrize("actor_kind", ["viewer", "outsider"])
async def test_readonly_or_nonmember_cannot_start_concept_conversation(
    task_session, monkeypatch, actor_kind: str
):
    fixture = await _seed(task_session)
    _FakeNovelService.appended = []
    monkeypatch.setattr(novels, "NovelService", _FakeNovelService)

    with pytest.raises(HTTPException) as denied:
        await novels.converse_with_concept(
            fixture.project.id,
            ConverseRequest(user_input={"text": "越界请求"}, conversation_state={}),
            session=task_session,
            current_user=_principal(getattr(fixture, actor_kind)),
        )

    assert denied.value.status_code == 403
    assert _FakeNovelService.appended == []

