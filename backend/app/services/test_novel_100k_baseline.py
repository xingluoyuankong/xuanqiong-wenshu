from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.novel import Chapter, ChapterVersion, NovelBlueprint, NovelProject
from app.models.user import User
from app.services.novel_benchmark_service import CountingPolicy, NovelBaselineError, NovelBenchmarkService


@pytest.mark.asyncio
async def test_build_baseline_uses_selected_versions_counts_visible_text_and_volume_plan(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'baseline.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with factory() as session:
            session.add(User(id=1, username="baseline", email="baseline@example.com", hashed_password="hash"))
            session.add(NovelProject(id="p-baseline", user_id=1, title="十万字基线", status="draft"))
            session.add(NovelBlueprint(project_id="p-baseline", world_setting={"volume_plan": [{"title": "第一卷", "chapter_range": "1-2章"}, {"title": "第二卷", "chapter_range": "3-4章"}]}))
            first = Chapter(project_id="p-baseline", chapter_number=1, status="successful")
            second = Chapter(project_id="p-baseline", chapter_number=2, status="successful")
            third = Chapter(project_id="p-baseline", chapter_number=3, status="not_generated")
            session.add_all([first, second, third])
            await session.flush()
            first_old = ChapterVersion(chapter_id=first.id, content="旧版本不应统计", status="candidate")
            first_selected = ChapterVersion(chapter_id=first.id, content="甲 乙\n丙\u200b", status="candidate")
            second_selected = ChapterVersion(chapter_id=second.id, content="丁", status="candidate")
            session.add_all([first_old, first_selected, second_selected])
            await session.flush()
            first.selected_version_id = first_selected.id
            second.selected_version_id = second_selected.id
            await session.commit()

        async with factory() as session:
            service = NovelBenchmarkService(session)
            baseline = await service.build_baseline("p-baseline")
            repeated = await service.build_baseline("p-baseline")

        assert baseline.text_units == 4
        assert baseline.chapter_count == 3
        assert baseline.selected_chapter_count == 2
        assert baseline.missing_selected_version_count == 1
        assert baseline.empty_selected_content_count == 0
        assert baseline.chapter_coverage_ratio == pytest.approx(2 / 3)
        assert [item.text_units for item in baseline.chapter_distribution] == [3, 1, 0]
        assert baseline.chapter_distribution[2].status == "missing_selected_version"
        assert len(baseline.volume_distribution) == 2
        assert baseline.volume_distribution[0].text_units == 4
        assert baseline.volume_distribution[1].chapter_count == 1
        assert baseline.content_digest == repeated.content_digest
        assert baseline.counting_policy["version"] == "zh-visible-v1"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_build_baseline_rejects_unknown_project(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'missing.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with factory() as session:
            with pytest.raises(NovelBaselineError, match="novel project not found"):
                await NovelBenchmarkService(session).build_baseline("missing")
    finally:
        await engine.dispose()


def test_counting_policy_can_preserve_whitespace_when_requested():
    assert CountingPolicy().count("甲 乙\n丙\u200b") == 3
    assert CountingPolicy(include_whitespace=True).count("甲 乙\n丙\u200b") == 5
