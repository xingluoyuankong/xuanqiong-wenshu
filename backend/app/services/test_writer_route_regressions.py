import types

import pytest
from fastapi import BackgroundTasks

from app.api.routers import writer
from app.schemas.novel import AdvancedGenerateRequest, FlowConfig, GenerateChapterRequest


class _DummySession:
    async def refresh(self, _obj):
        return None


class _DummyNovelService:
    def __init__(self, session):
        self.session = session

    async def ensure_project_owner(self, project_id, user_id):
        return types.SimpleNamespace(id=project_id, user_id=user_id)

    async def get_outline(self, project_id, chapter_number):
        return types.SimpleNamespace(project_id=project_id, chapter_number=chapter_number)

    async def get_or_create_chapter(self, project_id, chapter_number):
        return types.SimpleNamespace(
            id=11,
            project_id=project_id,
            chapter_number=chapter_number,
            status="not_generated",
            updated_at=None,
            created_at=None,
            real_summary="",
        )


@pytest.mark.anyio
async def test_generate_chapter_route_uses_request_chapter_number_when_claiming(monkeypatch):
    claimed: dict[str, int] = {}

    async def fake_try_claim(session, *, chapter_id, chapter_number):
        claimed["chapter_id"] = chapter_id
        claimed["chapter_number"] = chapter_number
        return "run-generate"

    async def fake_load_project_schema(service, project_id, user_id, generation_runtime=None):
        return {
            "project_id": project_id,
            "user_id": user_id,
            "generation_runtime": generation_runtime or {},
        }

    monkeypatch.setattr(writer, "NovelService", _DummyNovelService)
    monkeypatch.setattr(writer, "_try_claim_chapter_generation", fake_try_claim)
    monkeypatch.setattr(writer, "_load_project_schema", fake_load_project_schema)
    monkeypatch.setattr(writer, "build_chapter_progress_snapshot", lambda *args, **kwargs: {"progress_stage": "queued"})

    response = await writer.generate_chapter(
        project_id="project-1",
        request=GenerateChapterRequest(
            chapter_number=7,
            target_word_count=700,
            min_word_count=350,
        ),
        background_tasks=BackgroundTasks(),
        session=_DummySession(),
        current_user=types.SimpleNamespace(id=101),
    )

    assert claimed == {"chapter_id": 11, "chapter_number": 7}
    assert response["generation_runtime"]["target_word_count"] == 700
    assert response["generation_runtime"]["min_word_count"] == 350


@pytest.mark.anyio
async def test_advanced_generate_route_uses_request_chapter_number_when_claiming(monkeypatch):
    claimed: dict[str, int] = {}

    async def fake_try_claim(session, *, chapter_id, chapter_number):
        claimed["chapter_id"] = chapter_id
        claimed["chapter_number"] = chapter_number
        return "run-advanced"

    async def fake_load_project_schema(service, project_id, user_id, generation_runtime=None):
        return {
            "project_id": project_id,
            "user_id": user_id,
            "generation_runtime": generation_runtime or {},
        }

    monkeypatch.setattr(writer, "NovelService", _DummyNovelService)
    monkeypatch.setattr(writer, "_try_claim_chapter_generation", fake_try_claim)
    monkeypatch.setattr(writer, "_load_project_schema", fake_load_project_schema)
    monkeypatch.setattr(writer, "build_chapter_progress_snapshot", lambda *args, **kwargs: {"progress_stage": "queued"})

    response = await writer.advanced_generate_chapter(
        request=AdvancedGenerateRequest(
            project_id="project-2",
            chapter_number=9,
            writing_notes="加强压迫感",
            flow_config=FlowConfig(target_word_count=900, min_word_count=700, preset="ultimate"),
        ),
        background_tasks=BackgroundTasks(),
        session=_DummySession(),
        current_user=types.SimpleNamespace(id=202),
    )

    assert claimed == {"chapter_id": 11, "chapter_number": 9}
    assert response["generation_runtime"]["target_word_count"] == 900
    assert response["generation_runtime"]["min_word_count"] == 700
    assert response["generation_runtime"]["advanced_background_mode"] is True
