import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app.db.base import Base
from app.models.clue_tracker import StoryClue
from app.models.foreshadowing import Foreshadowing
from app.models.memory_layer import CausalChain, CharacterState, TimelineEvent
from app.models.knowledge_graph import CharacterNode, EventEdge
from app.models.novel import BlueprintCharacter, BlueprintRelationship, Chapter, ChapterOutline, NovelBlueprint, NovelProject
from app.models.project_memory import ProjectMemory
from app.models.user import User
from app.services.foreshadowing_service import ForeshadowingService
from app.services.knowledge_graph_service import KnowledgeGraphService
from app.services.longform_context_service import LongformContextService
from app.services.memory_layer_service import MemoryLayerService
from app.services.novel_service import (
    _infer_total_chapters_for_cast,
    _normalize_blueprint_characters_for_storage,
    _normalize_blueprint_relationships_for_storage,
    _target_character_count,
)


@pytest.mark.asyncio
async def test_longform_context_package_classifies_due_hooks_and_cast_slots(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'longform.db'}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as session:
            session.add(User(id=1, username="tester", email="tester@example.com", hashed_password="hash"))
            session.add(NovelProject(id="p-long", user_id=1, title="长篇", initial_prompt="百万字", status="draft"))
            session.add(
                NovelBlueprint(
                    project_id="p-long",
                    title="长篇",
                    world_setting={
                        "novel_outline": [{"title": "终局卷", "expected_chapter_range": "1-220章"}],
                        "volume_plan": [{"title": "远航卷", "chapter_range": "1-120章"}],
                    },
                )
            )
            session.add(ChapterOutline(project_id="p-long", chapter_number=3, title="账册显影", summary="林七必须查清旧账册真相。"))
            session.add(BlueprintCharacter(project_id="p-long", name="林七", identity="主角", position=0))
            session.add(BlueprintCharacter(project_id="p-long", name="沈舟", identity="核心盟友", position=1))
            session.add(Chapter(project_id="p-long", chapter_number=1, status="successful", word_count=1200))
            await session.flush()
            chapter = (await session.execute(select(Chapter).where(Chapter.project_id == "p-long"))).scalar_one()
            session.add(
                Foreshadowing(
                    project_id="p-long",
                    chapter_id=chapter.id,
                    chapter_number=1,
                    content="旧账册边角有盐渍编号",
                    type="setup",
                    status="planted",
                    keywords=["账册", "盐渍编号"],
                    name="盐渍编号",
                    target_reveal_chapter=3,
                    importance="major",
                )
            )
            session.add(
                StoryClue(
                    project_id="p-long",
                    name="潮雾账册",
                    clue_type="plot_hook",
                    description="账册会指向旧码头",
                    planted_chapter=1,
                    resolution_chapter=3,
                    status="active",
                )
            )
            session.add(
                CharacterState(
                    project_id="p-long",
                    character_id=1,
                    character_name="林七",
                    chapter_number=2,
                    location="旧档案馆",
                    emotion="警惕",
                    health_status="injured",
                    current_goals=["查明账册来源"],
                )
            )
            session.add(
                TimelineEvent(
                    project_id="p-long",
                    chapter_number=2,
                    event_title="林七拿到账册残页",
                    event_description="盐渍编号第一次被注意到。",
                    involved_characters=["林七", "沈舟"],
                    importance=8,
                )
            )
            session.add(ProjectMemory(project_id="p-long", global_summary="林七正在追查潮雾账册。", last_updated_chapter=2))
            await session.commit()

        async with session_factory() as session:
            result = await session.execute(
                select(NovelProject)
                .options(
                    selectinload(NovelProject.blueprint),
                    selectinload(NovelProject.outlines),
                    selectinload(NovelProject.chapters),
                )
                .where(NovelProject.id == "p-long")
            )
            project = result.scalar_one()
            outline = next(item for item in project.outlines if item.chapter_number == 3)
            package = await LongformContextService(session).build_context_package(
                project=project,
                outline=outline,
                chapter_number=3,
                writing_notes="强调回收",
                chapter_mission={"character_focus": ["林七"], "scene_list": [{"goal": "查账册", "characters": ["林七"]}]},
                allowed_new_characters=[],
            )

            assert package.cast_plan.target_character_count >= 40
            assert package.cast_plan.planned_character_count == 2
            assert package.foreshadowing_task.must_resolve
            assert "旧账册边角有盐渍编号" in package.prompt_text
            assert "无论篇幅长短" in package.prompt_text

            missing_gate = LongformContextService.evaluate_continuity_quality(
                content="林七只在旧档案馆徘徊，没有碰那本旧账。",
                package=package,
                chapter_mission={},
            )
            assert missing_gate.passed is False
            assert any(item["code"] == "due_foreshadowing_not_visible" for item in missing_gate.blockers)

            weak_payoff_gate = LongformContextService.evaluate_continuity_quality(
                content="林七终于看见潮雾账册上的盐渍编号，却只是把它放回桌角，转身继续沉默。",
                package=package,
                chapter_mission={},
            )
            assert weak_payoff_gate.passed is True
            assert any(item["code"] == "due_foreshadowing_payoff_weak" for item in weak_payoff_gate.warnings)
            assert any(item["code"] == "strengthen_payoff_patch" for item in weak_payoff_gate.patch_suggestions)

            resolved_gate = LongformContextService.evaluate_continuity_quality(
                content="林七终于看懂潮雾账册上的盐渍编号，原来它指向旧码头的真相。",
                package=package,
                chapter_mission={},
            )
            assert resolved_gate.metrics["unresolved_due_count"] == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_foreshadowing_auto_resolve_records_resolution(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'foreshadowing.db'}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as session:
            session.add(User(id=1, username="tester", email="tester@example.com", hashed_password="hash"))
            session.add(NovelProject(id="p-foo", user_id=1, title="伏笔", initial_prompt="测试", status="draft"))
            session.add(Chapter(project_id="p-foo", chapter_number=1, status="successful", word_count=100))
            session.add(Chapter(project_id="p-foo", chapter_number=3, status="successful", word_count=100))
            await session.flush()
            chapters = (await session.execute(select(Chapter).where(Chapter.project_id == "p-foo"))).scalars().all()
            first = next(ch for ch in chapters if ch.chapter_number == 1)
            third = next(ch for ch in chapters if ch.chapter_number == 3)
            session.add(
                Foreshadowing(
                    project_id="p-foo",
                    chapter_id=first.id,
                    chapter_number=1,
                    content="青铜铃会在真相揭开时响起",
                    type="setup",
                    status="planted",
                    keywords=["青铜铃", "真相"],
                    name="青铜铃",
                    target_reveal_chapter=3,
                )
            )
            await session.commit()

        async with session_factory() as session:
            service = ForeshadowingService(session)
            chapters = (await session.execute(select(Chapter).where(Chapter.project_id == "p-foo"))).scalars().all()
            third = next(ch for ch in chapters if ch.chapter_number == 3)
            result = await service.auto_resolve_from_chapter(
                project_id="p-foo",
                chapter_id=third.id,
                chapter_number=3,
                chapter_content="青铜铃终于响起，原来它指向的真相就是旧案的证人。",
            )
            await session.commit()

            assert result["resolved"] == 1
            updated = (await session.execute(select(Foreshadowing).where(Foreshadowing.project_id == "p-foo"))).scalar_one()
            assert updated.status == "resolved"
            assert updated.resolved_chapter_number == 3
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_foreshadowing_auto_resolve_accepts_due_paraphrased_payoff(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'foreshadowing_paraphrase.db'}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as session:
            session.add(User(id=1, username="tester", email="tester@example.com", hashed_password="hash"))
            session.add(NovelProject(id="p-payoff", user_id=1, title="Payoff", initial_prompt="test", status="draft"))
            session.add(Chapter(project_id="p-payoff", chapter_number=2, status="successful", word_count=100))
            session.add(Chapter(project_id="p-payoff", chapter_number=6, status="successful", word_count=100))
            await session.flush()
            chapters = (await session.execute(select(Chapter).where(Chapter.project_id == "p-payoff"))).scalars().all()
            second = next(ch for ch in chapters if ch.chapter_number == 2)
            sixth = next(ch for ch in chapters if ch.chapter_number == 6)
            session.add(
                Foreshadowing(
                    project_id="p-payoff",
                    chapter_id=second.id,
                    chapter_number=2,
                    content="The half-seal hidden in the ledger will matter later",
                    type="setup",
                    status="planted",
                    keywords=["half-seal ledger"],
                    name="half-seal",
                    target_reveal_chapter=6,
                )
            )
            await session.commit()

        async with session_factory() as session:
            service = ForeshadowingService(session)
            sixth = (await session.execute(
                select(Chapter).where(Chapter.project_id == "p-payoff", Chapter.chapter_number == 6)
            )).scalar_one()
            result = await service.auto_resolve_from_chapter(
                project_id="p-payoff",
                chapter_id=sixth.id,
                chapter_number=6,
                chapter_content=(
                    "Lin Qi found the ledger mark again. The half-seal was the key: "
                    "it proved the archive door had been opened from inside."
                ),
            )
            await session.commit()

            updated = (await session.execute(select(Foreshadowing).where(Foreshadowing.project_id == "p-payoff"))).scalar_one()
            assert result["resolved"] == 1
            assert updated.status == "resolved"
            assert updated.resolved_chapter_number == 6
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_memory_update_writes_causal_chains_into_longform_context(tmp_path):
    class FakeMemoryLLM:
        def __init__(self):
            self.responses = [
                {
                    "character_states": [
                        {
                            "character_name": "Lin Qi",
                            "location": "archive cellar",
                            "emotion": "alert",
                            "emotion_intensity": 8,
                            "health_status": "healthy",
                            "new_knowledge": ["the ledger code is traceable"],
                            "goal_progress": [{"goal": "hide the code", "progress": "temporarily escaped"}],
                        }
                    ]
                },
                {
                    "events": [
                        {
                            "event_title": "Ledger code stolen",
                            "event_description": "Lin Qi copies the code before the archive closes.",
                            "event_type": "major",
                            "story_time": "night",
                            "involved_characters": ["Lin Qi"],
                            "location": "archive cellar",
                            "importance": 8,
                            "is_turning_point": True,
                        }
                    ]
                },
                {
                    "causal_chains": [
                        {
                            "cause_description": "Lin Qi steals the ledger code from the archive.",
                            "cause_chapter": 4,
                            "effect_description": "The archivist can trace the missing code and pressure Lin Qi next chapter.",
                            "effect_chapter": None,
                            "cause_type": "action",
                            "effect_type": "plot_pressure",
                            "involved_characters": ["Lin Qi", "Archivist"],
                            "importance": 9,
                            "status": "pending",
                            "resolution_description": None,
                        }
                    ]
                },
            ]

        async def get_llm_response(self, **kwargs):
            return json.dumps(self.responses.pop(0), ensure_ascii=False)

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'memory-causal.db'}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as session:
            session.add(User(id=1, username="tester", email="tester@example.com", hashed_password="hash"))
            session.add(NovelProject(id="p-causal", user_id=1, title="Causal", initial_prompt="test", status="draft"))
            session.add(NovelBlueprint(project_id="p-causal", title="Causal", world_setting={"novel_outline": []}))
            session.add(ChapterOutline(project_id="p-causal", chapter_number=5, title="Pressure", summary="The archive reacts."))
            await session.commit()

        async with session_factory() as session:
            service = MemoryLayerService(session, FakeMemoryLLM(), object())
            result = await service.update_memory_after_chapter(
                project_id="p-causal",
                chapter_number=4,
                chapter_content="Lin Qi copies the ledger code. The archivist notices the missing trace.",
                character_names=[],
                user_id=1,
            )
            assert result["character_states_updated"] == 1
            assert result["timeline_events_added"] == 1
            assert result["causal_chains_added"] == 1
            assert result["dynamic_characters_created"] == 1
            assert result["dynamic_character_names"] == ["Lin Qi"]

            chain = (await session.execute(select(CausalChain).where(CausalChain.project_id == "p-causal"))).scalar_one()
            assert chain.status == "pending"
            assert "ledger code" in chain.cause_description
            dynamic_character = (
                await session.execute(
                    select(BlueprintCharacter).where(
                        BlueprintCharacter.project_id == "p-causal",
                        BlueprintCharacter.name == "Lin Qi",
                    )
                )
            ).scalar_one()
            assert dynamic_character.extra["auto_created_from_memory"] is True
            assert dynamic_character.extra["first_appearance_chapter"] == 4

            loaded = await session.execute(
                select(NovelProject)
                .options(
                    selectinload(NovelProject.blueprint),
                    selectinload(NovelProject.outlines),
                    selectinload(NovelProject.chapters),
                )
                .where(NovelProject.id == "p-causal")
            )
            project = loaded.scalar_one()
            outline = next(item for item in project.outlines if item.chapter_number == 5)
            package = await LongformContextService(session).build_context_package(
                project=project,
                outline=outline,
                chapter_number=5,
            )

            assert package.timeline_digest["causal_chains"]
            assert "trace the missing code" in package.timeline_digest["causal_chains"][0]["effect"]
            assert "trace the missing code" in package.prompt_text
    finally:
        await engine.dispose()


def test_longform_character_targets_scale_for_million_word_projects():
    assert _target_character_count(12) == 8
    assert _target_character_count(80) >= 26
    assert _target_character_count(200) >= 40

    characters = _normalize_blueprint_characters_for_storage(
        [{"name": "林七", "identity": "主角"}],
        total_chapters=200,
        blueprint_title="百万字长篇",
        genre="玄幻",
    )

    assert len(characters) >= 40
    assert characters[0]["extra"]["cast_tier"] == "protagonist"
    assert "knowledge_boundary" in characters[0]["extra"]
    assert any(item["extra"].get("cast_tier") in {"stage_support", "faction_member"} for item in characters)
    assert not any("补强角色位" in (item.get("identity") or "") for item in characters)
    assert not any((item.get("name") or "").startswith("线索持有者") for item in characters)


def test_length_contract_controls_cast_scale_before_generated_outline_ranges():
    total = _infer_total_chapters_for_cast(
        world_setting={"system_blueprint": {"length_contract": {"target_chapter_count": 12}}},
        novel_outline=[{"expected_chapter_range": "346-390章"}],
        fallback=390,
    )

    assert total == 12

    characters = _normalize_blueprint_characters_for_storage(
        [{"name": "沈文朝", "identity": "主角"}],
        total_chapters=total,
        blueprint_title="潮印迷城",
        genre="东方玄幻",
    )

    assert len(characters) == 8
    assert {item["name"] for item in characters[1:]}
    assert not any("补强角色位" in (item.get("identity") or "") for item in characters)


def test_legacy_supplemental_characters_are_cleaned_from_saved_blueprints():
    raw_characters = [
        {"name": "沈文朝", "identity": "主角"},
        {"name": "季阿七", "identity": "核心盟友"},
    ] + [
        {
            "name": f"线索持有者{index}",
            "identity": f"补强角色位{index}",
            "extra": {"is_supplemental": True},
        }
        for index in range(3, 15)
    ]

    characters = _normalize_blueprint_characters_for_storage(
        raw_characters,
        total_chapters=12,
        blueprint_title="潮印迷城",
        genre="东方玄幻",
    )

    assert len(characters) == 8
    assert not any((item.get("name") or "").startswith("线索持有者") for item in characters)
    assert not any("补强角色位" in (item.get("identity") or "") for item in characters)

    relationships = _normalize_blueprint_relationships_for_storage(
        [
            {"character_from": "沈文朝", "character_to": "季阿七", "description": "互相试探后合作"},
            {"character_from": "沈文朝", "character_to": "线索持有者13", "description": "旧占位角色残留关系"},
        ],
        characters=characters,
        total_chapters=12,
        blueprint_title="潮印迷城",
    )

    assert relationships
    assert all("线索持有者13" not in {item["character_from"], item["character_to"]} for item in relationships)


@pytest.mark.asyncio
async def test_knowledge_graph_sync_backfills_blueprint_relationship_edges(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'knowledge-graph.db'}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as session:
            session.add(User(id=1, username="tester", email="tester@example.com", hashed_password="hash"))
            session.add(NovelProject(id="p-kg", user_id=1, title="图谱", initial_prompt="测试", status="draft"))
            session.add(BlueprintCharacter(project_id="p-kg", name="林七", identity="主角", position=0))
            session.add(BlueprintCharacter(project_id="p-kg", name="沈舟", identity="盟友", position=1))
            stale_a = CharacterNode(project_id="p-kg", name="线索持有者13", role_type="补强角色位13")
            stale_b = CharacterNode(project_id="p-kg", name="旧日盟友14", role_type="补强角色位14")
            session.add_all([stale_a, stale_b])
            await session.flush()
            session.add(
                EventEdge(
                    project_id="p-kg",
                    source_node_id=stale_a.id,
                    target_node_id=stale_b.id,
                    event_type="relationship",
                    description="旧占位关系",
                )
            )
            session.add(
                BlueprintRelationship(
                    project_id="p-kg",
                    character_from="林七",
                    character_to="沈舟",
                    description='林七与沈舟围绕旧账册形成互信。\n[[XUANQIONG_WENSHU_RELATIONSHIP_META]]\n{"relationship_type":"alliance","importance":4,"tension":"medium"}',
                    position=0,
                )
            )
            await session.commit()

        async with session_factory() as session:
            result = await KnowledgeGraphService(session).sync_from_story_memory("p-kg")
            assert result["created_nodes"] == 2
            assert result["created_edges"] == 1
            assert result["removed_nodes"] == 2
            assert result["removed_edges"] == 1

            remaining_nodes = (await session.execute(select(CharacterNode).where(CharacterNode.project_id == "p-kg"))).scalars().all()
            assert {node.name for node in remaining_nodes} == {"林七", "沈舟"}

            edge = (await session.execute(select(EventEdge).where(EventEdge.project_id == "p-kg"))).scalar_one()
            assert edge.event_type == "alliance"
            assert edge.importance == 4
            assert edge.extra["source"] == "blueprint_relationship"
    finally:
        await engine.dispose()
