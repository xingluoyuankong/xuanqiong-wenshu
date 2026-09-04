from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.routers import optimizer
from app.models import Chapter, ChapterVersion, NovelProject, ProjectMember, User
from app.models.project_member import ProjectMemberRole
from app.schemas.user import UserInDB


@dataclass(frozen=True)
class Fixture:
    owner: User
    editor: User
    viewer: User
    outsider: User
    project: NovelProject
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


async def _seed(task_session) -> Fixture:
    owner = User(id=97201, username="optimizer-owner", email="optimizer-owner@example.com", hashed_password="x", is_active=True)
    editor = User(id=97202, username="optimizer-editor", email="optimizer-editor@example.com", hashed_password="x", is_active=True)
    viewer = User(id=97203, username="optimizer-viewer", email="optimizer-viewer@example.com", hashed_password="x", is_active=True)
    outsider = User(id=97204, username="optimizer-outsider", email="optimizer-outsider@example.com", hashed_password="x", is_active=True)
    project = NovelProject(id="optimizer-member-project", user_id=owner.id, title="优化器成员项目")
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
    await task_session.flush()
    chapter = Chapter(project_id=project.id, chapter_number=1, status="successful", word_count=18)
    task_session.add(chapter)
    await task_session.flush()
    version = ChapterVersion(
        chapter_id=chapter.id,
        version_label="selected-v1",
        provider="fixture",
        content="原始章节内容，保留连续性锚点。",
        status="selected",
        metadata_={"source": "fixture"},
    )
    task_session.add(version)
    await task_session.flush()
    chapter.selected_version_id = version.id
    await task_session.commit()
    return Fixture(owner, editor, viewer, outsider, project, chapter, version)


@pytest.mark.asyncio
@pytest.mark.parametrize("actor_kind", ["viewer", "outsider"])
async def test_optimizer_write_routes_reject_readonly_and_nonmember_before_mutation(task_session, actor_kind: str):
    fixture = await _seed(task_session)
    actor = _principal(getattr(fixture, actor_kind))

    with pytest.raises(HTTPException) as denied:
        await optimizer.apply_optimization(
            request=optimizer.ApplyOptimizationRequest(
                project_id=fixture.project.id,
                chapter_number=1,
                optimized_content="不应写入的内容",
            ),
            session=task_session,
            current_user=actor,
        )

    assert denied.value.status_code == 403
    refreshed = await task_session.get(ChapterVersion, fixture.version.id)
    assert refreshed is not None
    assert refreshed.content == "原始章节内容，保留连续性锚点。"


@pytest.mark.asyncio
async def test_editor_can_apply_optimization_to_shared_project(task_session):
    fixture = await _seed(task_session)

    response = await optimizer.apply_optimization(
        request=optimizer.ApplyOptimizationRequest(
            project_id=fixture.project.id,
            chapter_number=1,
            optimized_content="编辑成员写入的优化章节，保留连续性锚点。",
        ),
        session=task_session,
        current_user=_principal(fixture.editor),
    )

    assert response.status == "success"
    assert response.chapter.content == "编辑成员写入的优化章节，保留连续性锚点。"
    assert response.chapter.selected_version_id != fixture.version.id


@pytest.mark.asyncio
async def test_editor_can_run_optimizer_on_shared_project(task_session, monkeypatch):
    fixture = await _seed(task_session)

    class FakePromptService:
        def __init__(self, _session):
            pass

        async def get_prompt(self, _name):
            return "fixture optimizer prompt"

    class FakeLLMService:
        def __init__(self, _session):
            pass

        @staticmethod
        def daily_limit_scope(_key):
            from contextlib import nullcontext
            return nullcontext()

    class FakeContextPackage:
        def to_optimizer_payload(self):
            return {"continuity": "fixture"}

    class FakeLongformContextService:
        def __init__(self, _session):
            pass

        async def build_context_package(self, **_kwargs):
            return FakeContextPackage()

    class FakeResult:
        data = {
            "optimized_content": "原始章节内容，保留连续性锚点，并补充推进。主角沿着石阶前行，发现密信中的线索指向城门后的旧塔，新的冲突正在逼近。雨声压过远处的钟鸣，他必须在天亮前做出选择，并把这条线索带回同伴身边。",
            "optimization_notes": "fixture optimizer",
        }

    async def fake_call_generation_json(**_kwargs):
        return FakeResult()

    monkeypatch.setattr(optimizer, "PromptService", FakePromptService)
    monkeypatch.setattr(optimizer, "LLMService", FakeLLMService)
    monkeypatch.setattr(optimizer, "LongformContextService", FakeLongformContextService)
    monkeypatch.setattr(optimizer, "call_generation_json", fake_call_generation_json)

    response = await optimizer.optimize_chapter(
        optimizer.OptimizeRequest(
            project_id=fixture.project.id,
            chapter_number=1,
            dimension="rhythm",
        ),
        session=task_session,
        current_user=_principal(fixture.editor),
    )

    assert response.dimension == "rhythm"
    assert response.optimized_content.startswith("原始章节内容")
    assert response.optimization_notes == "fixture optimizer"
