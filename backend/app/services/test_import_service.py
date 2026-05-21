import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.clue_tracker import StoryClue
from app.models.foreshadowing import Foreshadowing
from app.models.novel import BlueprintCharacter, Chapter, NovelProject
from app.models.project_memory import ChapterSnapshot, ProjectMemory
from app.models.user import User
from app.schemas.novel import Blueprint
from app.services.import_service import ImportService


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
