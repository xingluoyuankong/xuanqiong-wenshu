import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app.db.base import Base
from app.models.clue_tracker import StoryClue
from app.models.foreshadowing import Foreshadowing
from app.models.memory_layer import CharacterState, TimelineEvent
from app.models.novel import BlueprintCharacter, Chapter, ChapterOutline, NovelBlueprint, NovelProject
from app.models.project_memory import ProjectMemory
from app.models.user import User
from app.services.foreshadowing_service import ForeshadowingService
from app.services.longform_context_service import LongformContextService
from app.services.novel_service import _normalize_blueprint_characters_for_storage, _target_character_count


@pytest.mark.anyio
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

            missing_gate = LongformContextService.evaluate_continuity_quality(
                content="林七只在旧档案馆徘徊，没有碰那本旧账。",
                package=package,
                chapter_mission={},
            )
            assert missing_gate.passed is False
            assert any(item["code"] == "due_foreshadowing_not_visible" for item in missing_gate.blockers)

            resolved_gate = LongformContextService.evaluate_continuity_quality(
                content="林七终于看懂潮雾账册上的盐渍编号，原来它指向旧码头的真相。",
                package=package,
                chapter_mission={},
            )
            assert resolved_gate.metrics["unresolved_due_count"] == 0
    finally:
        await engine.dispose()


@pytest.mark.anyio
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
