import io

import pytest
from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.clue_tracker import StoryClue
from app.models.foreshadowing import Foreshadowing
from app.models.memory_layer import TimelineEvent
from app.models.novel import BlueprintCharacter, BlueprintRelationship, Chapter, ChapterOutline, ChapterVersion, NovelBlueprint, NovelProject
from app.models.project_memory import ChapterSnapshot, ProjectMemory
from app.models.user import User
from app.schemas.novel import Blueprint
from app.services.import_service import ImportService
from app.services.export_service import ExportService
from app.services.novel_service import NovelService
from app.services.novel_service import _extract_marker_payload


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_import_ledger_rebuild_persists_foreshadowings_and_clues(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'import-ledgers.db'}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as session:
            session.add(User(id=1, username="tester", email="tester@example.com", hashed_password="hash"))
            session.add(NovelProject(id="p-import", user_id=1, title="Imported", initial_prompt="old file", status="draft"))
            session.add(BlueprintCharacter(project_id="p-import", name="Lin Qi", identity="lead", goals="Find the ledger"))
            session.add(Chapter(project_id="p-import", chapter_number=1, status="successful", word_count=1200))
            session.add(Chapter(project_id="p-import", chapter_number=2, status="successful", word_count=1300))
            session.add(Chapter(project_id="p-import", chapter_number=3, status="successful", word_count=1400))
            await session.commit()

        blueprint = Blueprint(
            title="Imported",
            one_sentence_summary="A ledger secret crosses three chapters.",
            full_synopsis="Lin Qi follows a hidden salt-code from setup to payoff.",
            characters=[{"name": "Lin Qi", "goal": "Find the ledger"}],
            foreshadowing_system=[
                {
                    "name": "Salt-code ledger",
                    "plant": "The first page of the ledger carries an unexplained salt-code.",
                    "payoff": "The archive later proves the salt-code marks the missing heir.",
                    "planted_chapter": 1,
                    "resolution_chapter": 3,
                    "target_reveal_chapter": 3,
                    "owner": "Lin Qi",
                    "type": "setup",
                    "importance": "major",
                    "keywords": ["ledger", "salt-code"],
                },
                {
                    "name": "Future seal",
                    "plant": "A sealed emblem is mentioned but not explained yet.",
                    "planted_chapter": 2,
                    "target_reveal_chapter": 8,
                    "owner": "Lin Qi",
                    "type": "mystery",
                    "importance": "minor",
                },
            ],
        )

        async with session_factory() as session:
            metrics = await ImportService(session)._rebuild_import_ledgers(
                "p-import",
                blueprint,
                [
                    ("Chapter 1", "Lin Qi notices a salt-code in the ledger."),
                    ("Chapter 2", "The clue changes hands."),
                    ("Chapter 3", "The archive explains the salt-code."),
                ],
                filename="old.txt",
            )

            assert metrics["snapshot_count"] == 3
            assert metrics["foreshadowing_count"] == 2
            assert metrics["clue_tracker"]["created"] == 2

            foreshadowings = (
                await session.execute(
                    select(Foreshadowing)
                    .where(Foreshadowing.project_id == "p-import")
                    .order_by(Foreshadowing.chapter_number.asc(), Foreshadowing.id.asc())
                )
            ).scalars().all()
            assert [item.name for item in foreshadowings] == ["Salt-code ledger", "Future seal"]
            foreshadowing = foreshadowings[0]
            assert foreshadowing.chapter_number == 1
            assert foreshadowing.target_reveal_chapter == 3
            assert foreshadowing.status == "revealed"
            assert foreshadowing.related_characters == ["Lin Qi"]
            assert foreshadowings[1].chapter_number == 2
            assert foreshadowings[1].target_reveal_chapter == 8
            assert foreshadowings[1].status == "planted"

            clues = (
                await session.execute(
                    select(StoryClue)
                    .where(StoryClue.project_id == "p-import")
                    .order_by(StoryClue.planted_chapter.asc(), StoryClue.id.asc())
                )
            ).scalars().all()
            assert [item.name for item in clues] == ["Salt-code ledger", "Future seal"]
            assert clues[0].planted_chapter == 1
            assert clues[0].resolution_chapter == 3
            assert clues[0].status == "resolved"
            assert clues[1].planted_chapter == 2
            assert clues[1].resolution_chapter is None
            assert clues[1].status == "active"

            snapshot_count = (
                await session.execute(select(ChapterSnapshot).where(ChapterSnapshot.project_id == "p-import"))
            ).scalars().all()
            assert len(snapshot_count) == 3

            memory = (await session.execute(select(ProjectMemory).where(ProjectMemory.project_id == "p-import"))).scalar_one()
            assert memory.extra["import_ledger_rebuild"]["foreshadowing_count"] == 2
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_formal_export_import_roundtrip_restores_project_and_ledgers(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'formal-roundtrip.db'}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            session.add(User(id=11, username="roundtrip-owner", email="roundtrip@example.com", hashed_password="hash"))
            await session.commit()
            novel = NovelService(session)
            project = await novel.create_project(11, "往返长篇", "保留初始设定")
            await novel.replace_blueprint(
                project.id,
                Blueprint(
                    title="往返长篇", genre="玄幻", style="冷峻", tone="紧张",
                    one_sentence_summary="主角追查失落的星图。", full_synopsis="三章内完成一次线索埋设与回收。",
                    world_setting={"core_rules": "星图只能被守门人读取"},
                    characters=[{"name": "沈砚", "identity": "守门人", "goals": "找回星图", "personality": "克制"},
                                {"name": "陆衡", "identity": "追猎者", "goals": "夺取星图"}],
                    relationships=[{"character_from": "沈砚", "character_to": "陆衡", "description": "互相追猎", "relationship_type": "敌对"}],
                    chapter_outline=[
                        {"chapter_number": 1, "title": "星图初现", "summary": "发现星图。", "continuity_notes": ["留下银印"]},
                        {"chapter_number": 2, "title": "雨夜追踪", "summary": "追踪敌人。"},
                    ],
                    foreshadowing_system=[{"name": "银印", "plant": "沈砚发现银印", "payoff": "银印打开星门", "planted_chapter": 1, "resolution_chapter": 2}],
                ),
            )
            chapters = []
            for number, content in ((1, "沈砚在废墟中发现银印。"), (2, "银印打开星门，陆衡现身。")):
                chapter = await novel.get_or_create_chapter(project.id, number)
                await novel.replace_chapter_versions(
                    chapter,
                    [content, f"候选版本{number}"],
                    metadata=[{"source": "roundtrip-test", "summary": f"摘要{number}"}, {"candidate": True}],
                )
                await novel.select_chapter_version(chapter, 0)
                chapters.append(chapter)
            session.add_all([
                Foreshadowing(project_id=project.id, chapter_id=chapters[0].id, chapter_number=1,
                              content="银印隐藏着星门坐标", type="setup", keywords=["银印"], status="revealed",
                              resolved_chapter_id=chapters[1].id, resolved_chapter_number=2, name="银印正式伏笔",
                              target_reveal_chapter=2, reveal_method="打开星门", related_characters=["沈砚"], importance="major"),
                TimelineEvent(project_id=project.id, chapter_number=1, story_time="第一夜", event_type="major",
                              event_title="发现银印", event_description="沈砚找到银印", involved_characters=["沈砚"],
                              location="废墟", importance=8, is_turning_point=True, extra={"source": "seed"}),
            ])
            await session.commit()
            exported = await ExportService(session).export_novel_as_txt(project.id)

        async with session_factory() as session:
            monkeypatch.setattr(ImportService, "_filter_characters_only", lambda self, user_id, potential, highlights: _async_empty())
            imported_id = await ImportService(session).import_novel_from_file(
                11, UploadFile(filename="formal-roundtrip.txt", file=io.BytesIO(exported.encode("utf-8")))
            )
            imported = await session.get(NovelProject, imported_id)
            assert imported.title == "往返长篇"
            blueprint = await session.get(NovelBlueprint, imported_id)
            assert blueprint.full_synopsis == "三章内完成一次线索埋设与回收。"
            characters = (await session.execute(select(BlueprintCharacter).where(BlueprintCharacter.project_id == imported_id).order_by(BlueprintCharacter.position))).scalars().all()
            imported_character_names = [item.name for item in characters]
            assert imported_character_names[:2] == ["沈砚", "陆衡"]
            assert all(name in imported_character_names for name in ("沈砚", "陆衡"))
            assert characters[0].identity == "守门人"
            assert characters[0].goals == "找回星图"
            relationships = (await session.execute(select(BlueprintRelationship).where(BlueprintRelationship.project_id == imported_id))).scalars().all()
            primary_relationship = next(
                item for item in relationships
                if item.character_from == "沈砚" and item.character_to == "陆衡"
            )
            clean_description, relation_meta = _extract_marker_payload(primary_relationship.description)
            assert clean_description == "互相追猎"
            assert relation_meta["relationship_type"] == "敌对"
            chapters = (await session.execute(select(Chapter).where(Chapter.project_id == imported_id).order_by(Chapter.chapter_number))).scalars().all()
            assert [item.status for item in chapters] == ["successful", "successful"]
            versions = (await session.execute(select(ChapterVersion).where(ChapterVersion.chapter_id.in_([item.id for item in chapters])))).scalars().all()
            assert {item.content for item in versions} == {"沈砚在废墟中发现银印。", "银印打开星门，陆衡现身。", "候选版本1", "候选版本2"}
            assert all(item.metadata.get("source") == "file_import" for item in versions if item.content.startswith("沈砚") or item.content.startswith("银印打开"))
            refreshed_chapters = (await session.execute(select(Chapter).where(Chapter.project_id == imported_id).order_by(Chapter.chapter_number))).scalars().all()
            assert [item.selected_version.content for item in refreshed_chapters] == ["沈砚在废墟中发现银印。", "银印打开星门，陆衡现身。"]
            foreshadowings = (await session.execute(select(Foreshadowing).where(Foreshadowing.project_id == imported_id))).scalars().all()
            assert [item.name for item in foreshadowings] == ["银印正式伏笔"]
            assert foreshadowings[0].resolved_chapter_number == 2
            timelines = (await session.execute(select(TimelineEvent).where(TimelineEvent.project_id == imported_id))).scalars().all()
            assert [(item.event_title, item.location) for item in timelines] == [("发现银印", "废墟")]
            snapshots = (await session.execute(select(ChapterSnapshot).where(ChapterSnapshot.project_id == imported_id))).scalars().all()
            assert len(snapshots) == 2
            memory = (await session.execute(select(ProjectMemory).where(ProjectMemory.project_id == imported_id))).scalar_one()
            assert memory.extra["import_ledger_rebuild"]["foreshadowing_count"] == 1
    finally:
        await engine.dispose()


async def _async_empty():
    return []
