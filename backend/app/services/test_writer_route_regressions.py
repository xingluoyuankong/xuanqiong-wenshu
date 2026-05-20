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


def test_rewritten_outline_metadata_preserves_existing_story_ledgers():
    metadata = writer._build_rewritten_outline_metadata(
        parsed_payload={
            "title": "夜审残页",
            "summary": (
                "林七接住上一章门外脚步声带来的压力，决定在密室里逼问沈舟残页的来历。"
                "沈舟拒绝交代，并用旧案反过来威胁林七，迫使林七暴露半枚印章。"
                "审问中顾棠突然回归，带来账册被调包的证据，局势转向更危险的追查。"
                "章尾沈舟说出真正的送信人就在门外，给下一章留下直接危机。"
            ),
            "character_focus": ["林七", "沈舟", "顾棠"],
            "cast_delta": {"returning": ["顾棠"], "new": [], "exit_or_absent": [], "faction_roles": ["沈舟:旧案势力"]},
            "continuity_notes": ["承接上一章门外脚步声", "把半枚印章风险递给下一章"],
            "foreshadowing_tasks": {"payoff": ["门外脚步声"], "reinforce": ["半枚印章"], "plant": [], "avoid_forgetting": ["旧案账册"]},
            "chapter_role": "用审问推进旧案账册主线，并把送信人危机压到下一章。",
            "suspense_hook": "真正的送信人就在门外。",
            "conflict_escalation": ["沈舟用旧案反制", "顾棠带来账册调包证据"],
            "emotional_progression": "压迫转为被反制，再转成短暂掌握主动。",
        },
        existing_metadata={
            "narrative_phase": "追查升级",
            "foreshadowing": {"plant": ["半枚印章"], "payoff": []},
            "outline_quality": {"accepted_by_executability_gate": True},
        },
        chapter_no=3,
        title="夜审残页",
        summary=(
            "林七接住上一章门外脚步声带来的压力，决定在密室里逼问沈舟残页的来历。"
            "沈舟拒绝交代，并用旧案反过来威胁林七，迫使林七暴露半枚印章。"
            "顾棠突然回归，带来账册被调包的证据，林七意识到追查目标已经从残页转向送信人。"
            "章尾沈舟抛出钩子：真正的送信人就在门外，危机会继续压到下一章。"
        ),
        direction="加强连续性",
    )

    assert metadata["narrative_phase"] == "追查升级"
    assert metadata["character_focus"] == ["林七", "沈舟", "顾棠"]
    assert metadata["cast_delta"]["returning"] == ["顾棠"]
    assert metadata["foreshadowing"]["plant"] == ["半枚印章"]
    assert metadata["foreshadowing_tasks"]["payoff"] == ["门外脚步声"]
    assert metadata["outline_quality"]["accepted_by_executability_gate"] is True
    assert metadata["outline_quality"]["rewrite_executability_gate_passed"] is True
    assert metadata["last_rewrite"]["direction"] == "加强连续性"
