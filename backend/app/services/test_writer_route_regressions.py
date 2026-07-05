import json
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


def test_outline_json_schemas_require_execution_fields():
    rewrite_schema = writer._outline_item_json_schema()
    batch_schema = writer._outline_batch_json_schema()

    assert "chapter_role" in rewrite_schema["required"]
    assert "continuity_notes" in rewrite_schema["required"]
    assert "foreshadowing_tasks" in rewrite_schema["required"]
    assert "cast_delta" in rewrite_schema["required"]
    assert "chapters" in batch_schema["required"]
    assert "chapter_number" in batch_schema["properties"]["chapters"]["items"]["required"]


def test_completed_chapter_review_context_keeps_previous_anchors_and_ledgers():
    chapters = [
        types.SimpleNamespace(
            chapter_number=1,
            title="Chapter 1",
            summary="The protagonist finds the first clue.",
            real_summary='{"generation_runtime":{"progress_stage":"waiting_for_confirm"}}',
            content="opening one\n" + "middle one " * 20 + "\nending anchor one",
            word_count=1200,
            generation_status="successful",
            character_focus=["Lin Qi"],
            cast_delta={"new": ["Lin Qi"]},
            continuity_notes=["the clue is still hidden"],
            foreshadowing_tasks={"plant": ["salt mark"]},
        ),
        types.SimpleNamespace(
            chapter_number=2,
            title="Chapter 2",
            summary="The clue is contested by a rival.",
            real_summary="The rival learns only half of the truth.",
            content="opening two\n" + "middle two " * 20 + "\nending anchor two",
            word_count=1800,
            generation_status="successful",
            character_focus=["Lin Qi", "Rival"],
            cast_delta={"returning": ["Lin Qi"], "new": ["Rival"]},
            continuity_notes=["the rival has partial knowledge"],
            foreshadowing_tasks={"reinforce": ["salt mark"], "payoff": []},
        ),
        types.SimpleNamespace(
            chapter_number=3,
            title="Chapter 3",
            summary="The door handle turns before the call ends.",
            real_summary="The incoming visitor must be handled next.",
            content="opening three\n" + "middle three " * 20 + "\nending anchor three",
            word_count=2100,
            generation_status="waiting_for_confirm",
            character_focus=["Lin Qi", "Archivist"],
            cast_delta={"returning": ["Lin Qi"], "new": ["Archivist"]},
            continuity_notes=["the door handle is the next scene handoff"],
            foreshadowing_tasks={"payoff": ["door handle"], "avoid_forgetting": ["salt mark"]},
        ),
        types.SimpleNamespace(chapter_number=4, title="Current", summary="Current chapter"),
    ]

    context = writer._build_completed_chapter_review_context(chapters, 4, limit=2)

    assert [item["chapter_number"] for item in context] == [2, 3]
    assert context[0]["real_summary"] == "The rival learns only half of the truth."
    assert "ending anchor three" in context[1]["ending_anchor"]
    assert context[1]["foreshadowing_tasks"]["payoff"] == ["door handle"]
    assert context[1]["cast_delta"]["new"] == ["Archivist"]
    assert all("generation_runtime" not in item["real_summary"] for item in context)


def test_single_chapter_evaluation_input_uses_cross_chapter_quality_context():
    class DumpableWorld:
        def model_dump(self):
            return {"city": "Qingdu", "rule": "salt marks track debt"}

    project_schema = types.SimpleNamespace(
        blueprint=types.SimpleNamespace(
            title="Salt Archive",
            genre="mystery fantasy",
            style="dense scene-driven prose",
            tone="tense",
            one_sentence_summary="A clerk follows salt marks through a rigged archive.",
            full_synopsis="The story tracks a widening conspiracy across the archive city.",
            world_setting=DumpableWorld(),
            characters=[
                {
                    "name": "Lin Qi",
                    "role": "protagonist",
                    "personality": "careful but stubborn",
                    "motivation": "prove the ledger was swapped",
                    "faction": "Archive Office",
                },
                {"name": "Rival", "role": "pressure actor"},
            ],
            foreshadowing_system=[{"setup": "salt mark", "payoff_window": "chapter 4"}],
            chapter_outline=[
                types.SimpleNamespace(
                    chapter_number=2,
                    title="Door Handle",
                    summary="A visitor arrives before the call ends.",
                    chapter_role="force the protagonist to act before ready",
                    conflict_escalation=["visitor blocks escape", "ledger changes hands"],
                    character_focus=["Lin Qi", "Archivist"],
                    cast_delta={"returning": ["Lin Qi"], "new": ["Archivist"]},
                    continuity_notes=["inherit the door handle from chapter 1"],
                    foreshadowing_tasks={"payoff": ["door handle"], "avoid_forgetting": ["salt mark"]},
                    payoff_window="now",
                )
            ],
        ),
        chapters=[
            types.SimpleNamespace(
                chapter_number=1,
                title="Salt Mark",
                summary="Lin Qi finds the first mark.",
                real_summary="The rival only knows half the ledger secret.",
                content="opening\n" + "archive pressure " * 30 + "\nending door handle turns",
                word_count=1600,
                generation_status="successful",
                character_focus=["Lin Qi", "Rival"],
                cast_delta={"new": ["Lin Qi", "Rival"]},
                continuity_notes=["door handle must continue"],
                foreshadowing_tasks={"plant": ["salt mark"]},
            ),
            types.SimpleNamespace(chapter_number=2, title="Door Handle"),
        ],
    )
    chapter = types.SimpleNamespace(chapter_number=2, title="Door Handle", generation_status="waiting_for_confirm")
    version = types.SimpleNamespace(
        id=17,
        version_label="candidate-a",
        word_count=5200,
        content="Lin Qi kept one hand on the ledger.\n" + "He argues, acts, pays a price. " * 220,
        metadata={"quality_gate": {"event_density": "ok"}},
    )

    payload = json.loads(writer._build_single_chapter_evaluation_input(project_schema, chapter, version, 2))

    assert payload["review_mode"] == "single_version_cross_chapter_quality_review"
    assert "completed_chapters" in payload
    assert "ending door handle turns" in payload["completed_chapters"][0]["ending_anchor"]
    assert payload["current_chapter_outline"]["foreshadowing_tasks"]["payoff"] == ["door handle"]
    assert payload["novel_blueprint"]["world_setting"]["rule"] == "salt marks track debt"
    assert payload["novel_blueprint"]["characters"][0]["name"] == "Lin Qi"
    assert any("local anchored patches" in rule for rule in payload["review_rules"])
    assert payload["content_to_evaluate"]["version"]["metadata"]["quality_gate"]["event_density"] == "ok"


def test_outline_generation_goal_allows_short_story_targets():
    effective_chapters, chapter_target = writer._resolve_outline_generation_goal(
        start_chapter=1,
        num_chapters=2,
        target_total_chapters=2,
        target_total_words=1800,
        chapter_word_target=None,
    )

    assert effective_chapters == 2
    assert chapter_target == 900

    with pytest.raises(writer.HTTPException) as exc_info:
        writer._resolve_outline_generation_goal(
            start_chapter=1,
            num_chapters=1,
            target_total_chapters=1,
            target_total_words=999,
            chapter_word_target=None,
        )
    assert exc_info.value.status_code == 400
    assert "1000" in str(exc_info.value.detail)


def test_failed_runtime_can_keep_confirm_actions_for_blocked_candidates():
    chapter = types.SimpleNamespace(
        real_summary=json.dumps({"generation_runtime": {"run_id": "run-1", "events": []}}, ensure_ascii=False),
        chapter_number=4,
    )

    payload = json.loads(
        writer._build_failed_generation_runtime_state(
            chapter,
            run_id="run-1",
            reason="质量门拦截，但候选稿已保存。",
            allowed_actions=["refresh_status", "confirm_version", "review_versions", "retry_generation", "view_error"],
            stage="evaluation_failed",
        )
    )

    runtime = payload["generation_runtime"]
    assert runtime["progress_stage"] == "evaluation_failed"
    assert "confirm_version" in runtime["allowed_actions"]
    assert "review_versions" in runtime["allowed_actions"]


def test_failed_runtime_defaults_to_failed_stage_without_explicit_stage():
    chapter = types.SimpleNamespace(
        real_summary=json.dumps({"generation_runtime": {"run_id": "run-2", "events": []}}, ensure_ascii=False),
        chapter_number=5,
    )

    payload = json.loads(
        writer._build_failed_generation_runtime_state(
            chapter,
            run_id="run-2",
            reason="生成超时，未产出任何候选版本。",
        )
    )

    runtime = payload["generation_runtime"]
    assert runtime["progress_stage"] == "failed"
    assert runtime["allowed_actions"] == ["refresh_status", "retry_generation"]
