# AIMETA P=multi_chapter_continuity_production|R=ch1-5_finalize_history_longform|NR=prod_db|E=test_multi_chapter_continuity_production|X=test|A=proof|D=pytest|S=tmpdb|RD=./README.ai
"""Production multi-chapter continuity proof on temp DB only. Never touches protected ch12/13."""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app.db.base import Base
from app.models.clue_tracker import StoryClue
from app.models.foreshadowing import Foreshadowing
from app.models.knowledge_graph import CharacterNode, EventEdge
from app.models.memory_layer import CharacterState, TimelineEvent
from app.models.novel import BlueprintCharacter, Chapter, ChapterOutline, ChapterVersion, NovelBlueprint, NovelProject
from app.models.project_memory import ChapterSnapshot, ProjectMemory
from app.models.user import User
from app.services.finalize_service import FinalizeService
from app.services.longform_context_service import LongformContextService
from app.services.pipeline_orchestrator import PipelineOrchestrator
from app.utils.chapter_summary_utils import extract_narrative_summary, parse_real_summary_payload


PROJECT_ID = "p-multi-cont-prod"
USER_ID = 1

CHAPTER_BEATS: List[Dict[str, Any]] = [
    {
        "n": 1,
        "title": "\u96e8\u591c\u593a\u4ee4",
        "summary": "\u7b2c1\u7ae0\u6458\u8981\uff1a\u6797\u821f\u5728\u4eac\u57ce\u57ce\u95e8\u593a\u56de\u591c\u96e8\u4ee4\uff0c\u8840\u5951\u521d\u73b0\u3002",
        "content": "\u6797\u821f\u5728\u66b4\u96e8\u57ce\u95e8\u593a\u56de\u591c\u96e8\u4ee4\uff0c\u8840\u5951\u5728\u638c\u5fc3\u707c\u70e7\uff0c\u987e\u68e0\u88ab\u8feb\u540c\u884c\u3002",
        "global": "\u5168\u4e66\uff1a\u6797\u821f\u79bb\u4eac\u5728\u5373\uff0c\u591c\u96e8\u4ee4\u5728\u624b\uff0c\u8840\u5951\u672a\u89e3\u3002",
        "hook": "\u8840\u5951\u4e09\u65e5\u53cd\u566c",
        "clue": "\u591c\u96e8\u4ee4\u80cc\u9762\u65e7\u4eac\u706b\u5370",
        "event": "\u593a\u56de\u591c\u96e8\u4ee4",
        "location": "\u4eac\u57ce\u57ce\u95e8",
    },
    {
        "n": 2,
        "title": "\u9a7f\u7ad9\u53cd\u566c",
        "summary": "\u7b2c2\u7ae0\u6458\u8981\uff1a\u5b98\u9053\u9a7f\u7ad9\u8840\u5951\u53cd\u566c\uff0c\u987e\u68e0\u7528\u836f\u538b\u4f4f\u707c\u70e7\u3002",
        "content": "\u6797\u821f\u5728\u5b98\u9053\u9a7f\u7ad9\u538b\u4f4f\u8840\u5951\u707c\u70e7\uff0c\u987e\u68e0\u9012\u6765\u6b62\u8840\u836f\uff0c\u706b\u5370\u7ebf\u7d22\u52a0\u6df1\u3002",
        "global": "\u5168\u4e66\uff1a\u6797\u821f\u4e0e\u987e\u68e0\u5728\u9a7f\u7ad9\u7a33\u4f4f\u8840\u5951\uff0c\u65e7\u4eac\u706b\u5370\u6307\u5411\u66f4\u6df1\u5c42\u52bf\u529b\u3002",
        "hook": "\u9a7f\u7ad9\u836f\u65b9\u6765\u6e90\u4e0d\u660e",
        "clue": "\u6b62\u8840\u836f\u4e0a\u6709\u519b\u76d1\u6697\u7eb9",
        "event": "\u8840\u5951\u53cd\u566c\u88ab\u538b\u5236",
        "location": "\u5b98\u9053\u9a7f\u7ad9",
    },
    {
        "n": 3,
        "title": "\u65e7\u4eac\u706b\u5370",
        "summary": "\u7b2c3\u7ae0\u6458\u8981\uff1a\u4e24\u4eba\u8ffd\u67e5\u706b\u5370\u6765\u6e90\uff0c\u53d1\u73b0\u519b\u76d1\u65e7\u6863\u6709\u8bb0\u5f55\u3002",
        "content": "\u6797\u821f\u5bf9\u7167\u65e7\u4eac\u706b\u5370\uff0c\u987e\u68e0\u7ffb\u51fa\u519b\u76d1\u65e7\u6863\uff0c\u786e\u8ba4\u4ee4\u724c\u66fe\u5c5e\u7981\u536b\u53f8\u3002",
        "global": "\u5168\u4e66\uff1a\u591c\u96e8\u4ee4\u5c5e\u7981\u536b\u53f8\u65e7\u7269\uff0c\u519b\u76d1\u65e7\u6863\u628a\u6797\u821f\u63a8\u5165\u66f4\u5927\u9634\u8c0b\u3002",
        "hook": "\u7981\u536b\u53f8\u65e7\u6863\u7f3a\u53e3",
        "clue": "\u7981\u536b\u53f8\u4ee4\u724c\u7f16\u53f7\u7f3a\u5931\u4e00\u9875",
        "event": "\u786e\u8ba4\u591c\u96e8\u4ee4\u5c5e\u7981\u536b\u53f8",
        "location": "\u519b\u76d1\u65e7\u6863\u5e93",
    },
    {
        "n": 4,
        "title": "\u7981\u536b\u65e7\u6028",
        "summary": "\u7b2c4\u7ae0\u6458\u8981\uff1a\u7981\u536b\u65e7\u4eba\u73b0\u8eab\u7d22\u4ee4\uff0c\u987e\u68e0\u8eab\u4efd\u66b4\u9732\u4e00\u534a\u3002",
        "content": "\u7981\u536b\u65e7\u4eba\u622a\u6740\u7d22\u4ee4\uff0c\u987e\u68e0\u4eae\u51fa\u534a\u679a\u7981\u536b\u4fe1\u7269\uff0c\u8eab\u4efd\u88c2\u75d5\u6269\u5927\u3002",
        "global": "\u5168\u4e66\uff1a\u987e\u68e0\u7275\u8fde\u7981\u536b\u65e7\u90e8\uff0c\u591c\u96e8\u4ee4\u6210\u4e3a\u591a\u65b9\u4e89\u593a\u7684\u94a5\u5319\u3002",
        "hook": "\u987e\u68e0\u53e6\u4e00\u534a\u8eab\u4efd",
        "clue": "\u534a\u679a\u7981\u536b\u4fe1\u7269",
        "event": "\u7981\u536b\u65e7\u4eba\u622a\u6740\u7d22\u4ee4",
        "location": "\u57ce\u5916\u5bc6\u6797",
    },
    {
        "n": 5,
        "title": "\u591c\u96e8\u5206\u9014",
        "summary": "\u7b2c5\u7ae0\u6458\u8981\uff1a\u6797\u821f\u51b3\u5b9a\u5165\u65e7\u4eac\u67e5\u6863\uff0c\u987e\u68e0\u6682\u7559\u7275\u5236\u8ffd\u6740\u3002",
        "content": "\u6797\u821f\u51b3\u610f\u5165\u65e7\u4eac\u67e5\u7981\u536b\u65e7\u6863\uff0c\u987e\u68e0\u7559\u4e0b\u7275\u5236\u8ffd\u6740\uff0c\u4e24\u4eba\u5206\u9014\u3002",
        "global": "\u5168\u4e66\uff1a\u4e3b\u7ebf\u5206\u9014\uff0c\u6797\u821f\u5165\u65e7\u4eac\uff0c\u987e\u68e0\u7275\u5236\u8ffd\u6740\uff0c\u591c\u96e8\u4ee4\u4e0e\u8840\u5951\u53cc\u7ebf\u5e76\u884c\u3002",
        "hook": "\u65e7\u4eac\u7981\u536b\u65e7\u6863\u771f\u76f8",
        "clue": "\u65e7\u4eac\u67e5\u6863\u8def\u7ebf\u56fe",
        "event": "\u4e3b\u7ebf\u5206\u9014\u5165\u65e7\u4eac",
        "location": "\u5206\u5c94\u5b98\u9053",
    },
    {
        "n": 6,
        "title": "旧京验档",
        "summary": "第6章摘要：林舟潜入旧京档库，补上禁卫司令牌缺失那一页。",
        "content": "林舟潜入旧京档库，比对夜雨令编号，补上禁卫司旧档缺失的一页，血契灼烧再起。",
        "global": "全书：林舟在旧京补全禁卫司档案缺页，夜雨令来历指向宫中旧案。",
        "hook": "宫中旧案主使未明",
        "clue": "补回的档案缺页",
        "event": "补全禁卫司旧档缺页",
        "location": "旧京档库",
    },
    {
        "n": 7,
        "title": "顾棠断线",
        "summary": "第7章摘要：顾棠牵制追杀失手被俘，半枚禁卫信物落入军监。",
        "content": "顾棠牵制追杀时失手被俘，半枚禁卫信物被军监取走，止血药方来源随之断线。",
        "global": "全书：顾棠落入军监，半枚信物易手，林舟在旧京失去接应。",
        "hook": "军监为何要信物",
        "clue": "军监扣下的半枚信物",
        "event": "顾棠被军监俘获",
        "location": "军监诏狱",
    },
    {
        "n": 8,
        "title": "血契三日",
        "summary": "第8章摘要：血契三日反噬到期，林舟以档案缺页换得压制之法。",
        "content": "血契三日反噬到期，林舟用旧档缺页与旧禁卫做交换，换来压制血契的法门。",
        "global": "全书：林舟暂压血契，代价是旧档缺页外流，夜雨令行踪暴露。",
        "hook": "缺页外流的后果",
        "clue": "外流缺页的抄本",
        "event": "以缺页换压制之法",
        "location": "旧京废祠",
    },
    {
        "n": 9,
        "title": "诏狱夺人",
        "summary": "第9章摘要：林舟夜袭诏狱救出顾棠，取回半枚禁卫信物。",
        "content": "林舟夜袭军监诏狱救出顾棠，取回半枚禁卫信物，两人确认宫中旧案主使身份。",
        "global": "全书：顾棠脱困，信物归位，宫中旧案主使已可指名。",
        "hook": "主使仍在宫中掌权",
        "clue": "主使的宫中印记",
        "event": "夜袭诏狱救出顾棠",
        "location": "军监诏狱",
    },
    {
        "n": 10,
        "title": "夜雨归令",
        "summary": "第10章摘要：两人合璧信物与夜雨令，直指宫中旧案主使。",
        "content": "顾棠合璧半枚信物与夜雨令，火印与旧档缺页对齐，宫中旧案主使浮出水面。",
        "global": "全书：夜雨令与禁卫信物合璧，宫中旧案主使浮出，主线进入正面对决。",
        "hook": "正面对决前的布局",
        "clue": "合璧后的完整火印",
        "event": "信物与夜雨令合璧",
        "location": "旧京城楼",
    },
]


def _beat(n: int) -> Dict[str, Any]:
    return next(item for item in CHAPTER_BEATS if item["n"] == n)


def _make_orchestrator(memory_text: str = "") -> PipelineOrchestrator:
    class DummyCache:
        def is_available(self):
            return False

        async def get(self, key):
            return None

        async def set(self, key, value, expire=None):
            return None

    orchestrator = PipelineOrchestrator.__new__(PipelineOrchestrator)
    orchestrator.cache_service = DummyCache()
    orchestrator._make_cache_key = lambda *args, **kwargs: "k"
    orchestrator._cache_get = DummyCache().get
    orchestrator._cache_set = DummyCache().set
    orchestrator._truncate_text = lambda text, limit=220: (text or "")[:limit]
    orchestrator._extract_tail_excerpt = lambda text, limit=500: (text or "")[-limit:]
    orchestrator._build_recent_chapter_track = lambda chapters: list(chapters or [])
    orchestrator._format_plot_arc_digest = lambda arcs: str(arcs or "")

    async def _get_project_memory_text(project_id):
        return memory_text

    orchestrator._get_project_memory_text = _get_project_memory_text
    return orchestrator


def _chapter_mirror(chapter: Chapter, content: str) -> SimpleNamespace:
    return SimpleNamespace(
        chapter_number=chapter.chapter_number,
        updated_at=getattr(chapter, "updated_at", None),
        selected_version_id=chapter.selected_version_id,
        real_summary=chapter.real_summary,
        selected_version=SimpleNamespace(content=content),
    )


async def _seed_project(session) -> None:
    session.add(User(id=USER_ID, username="multi-cont", email="multi@example.com", hashed_password="hash"))
    session.add(
        NovelProject(
            id=PROJECT_ID,
            user_id=USER_ID,
            title="\u591a\u7ae0\u8fde\u7eed\u6027\u751f\u4ea7\u8bc1\u660e",
            initial_prompt="short+long continuity",
            status="draft",
        )
    )
    session.add(
        NovelBlueprint(
            project_id=PROJECT_ID,
            title="\u591a\u7ae0\u8fde\u7eed\u6027\u751f\u4ea7\u8bc1\u660e",
            world_setting={
                "novel_outline": [{"title": "\u5377\u4e00", "expected_chapter_range": "1-10"}],
                "volume_plan": [{"title": "\u591c\u96e8\u7ebf", "chapter_range": "1-10"}],
            },
        )
    )
    session.add(BlueprintCharacter(project_id=PROJECT_ID, name="\u6797\u821f", identity="\u4e3b\u89d2", position=0))
    session.add(BlueprintCharacter(project_id=PROJECT_ID, name="\u987e\u68e0", identity="\u76df\u53cb", position=1))
    for beat in CHAPTER_BEATS:
        session.add(
            ChapterOutline(
                project_id=PROJECT_ID,
                chapter_number=beat["n"],
                title=beat["title"],
                summary="\u5927\u7eb2\uff1a" + beat["title"],
            )
        )
        session.add(
            Chapter(
                project_id=PROJECT_ID,
                chapter_number=beat["n"],
                status="pending" if beat["n"] > 1 else "waiting_for_confirm",
                real_summary=None,
                word_count=0,
            )
        )
    await session.flush()


async def _prepare_chapter_for_finalize(session, chapter_number: int):
    beat = _beat(chapter_number)
    chapter = (
        await session.execute(
            select(Chapter).where(Chapter.project_id == PROJECT_ID, Chapter.chapter_number == chapter_number)
        )
    ).scalar_one()
    chapter.real_summary = json.dumps(
        {
            "generation_runtime": {
                "run_id": f"run-ch{chapter_number}",
                "progress_stage": "waiting_for_confirm",
                "progress_percent": 97,
            }
        },
        ensure_ascii=False,
    )
    chapter.status = "waiting_for_confirm"
    content = (beat["content"] + "\u3002") * 8
    version = ChapterVersion(chapter_id=chapter.id, content=content, version_label=f"v-ch{chapter_number}")
    session.add(version)
    await session.flush()
    chapter.selected_version_id = version.id
    chapter.word_count = len(content)
    await session.flush()
    return chapter, content


async def _seed_longform_artifacts_for_chapter(session, chapter_number: int, chapter_id: int) -> None:
    beat = _beat(chapter_number)
    session.add(
        Foreshadowing(
            project_id=PROJECT_ID,
            chapter_id=chapter_id,
            chapter_number=chapter_number,
            content=beat["hook"],
            type="setup",
            status="planted",
            keywords=[beat["hook"][:6], "\u591c\u96e8\u4ee4"],
            name=f"hook-ch{chapter_number}",
            target_reveal_chapter=min(chapter_number + 1, 5),
            importance="major",
        )
    )
    session.add(
        StoryClue(
            project_id=PROJECT_ID,
            name=f"clue-ch{chapter_number}",
            clue_type="plot_hook",
            description=beat["clue"],
            planted_chapter=chapter_number,
            resolution_chapter=min(chapter_number + 2, 5),
            status="active",
            importance=5,
        )
    )
    session.add(
        CharacterState(
            project_id=PROJECT_ID,
            character_id=1,
            character_name="\u6797\u821f",
            chapter_number=chapter_number,
            location=beat["location"],
            emotion="\u7d27\u7ef7",
            health_status="injured" if chapter_number < 4 else "stable",
            current_goals=["\u63a8\u8fdb" + beat["title"]],
        )
    )
    session.add(
        TimelineEvent(
            project_id=PROJECT_ID,
            chapter_number=chapter_number,
            event_title=beat["event"],
            event_description=beat["content"],
            involved_characters=["\u6797\u821f", "\u987e\u68e0"],
            importance=7 + min(chapter_number, 2),
            location=beat["location"],
        )
    )
    existing_nodes = {
        node.name: node
        for node in (await session.execute(select(CharacterNode).where(CharacterNode.project_id == PROJECT_ID))).scalars().all()
    }
    if "\u6797\u821f" not in existing_nodes:
        source = CharacterNode(project_id=PROJECT_ID, name="\u6797\u821f", role_type="\u4e3b\u89d2", location=beat["location"], status="injured")
        session.add(source)
        await session.flush()
        existing_nodes["\u6797\u821f"] = source
    if "\u987e\u68e0" not in existing_nodes:
        target = CharacterNode(project_id=PROJECT_ID, name="\u987e\u68e0", role_type="\u76df\u53cb")
        session.add(target)
        await session.flush()
        existing_nodes["\u987e\u68e0"] = target
    session.add(
        EventEdge(
            project_id=PROJECT_ID,
            source_node_id=existing_nodes["\u6797\u821f"].id,
            target_node_id=existing_nodes["\u987e\u68e0"].id,
            chapter_number=chapter_number,
            event_type="causality",
            description=f"{beat['event']} -> \u987e\u68e0\u534f\u540c",
            causality=beat["hook"],
        )
    )
    await session.flush()


async def _finalize_one(session, monkeypatch, chapter_number: int, chapter_text: str) -> Dict[str, Any]:
    beat = _beat(chapter_number)
    service = FinalizeService(session, object())

    async def fake_summary(*_a, **_k):
        return beat["global"]

    async def fake_state(*_a, **_k):
        return f"\u6797\u821f\uff1a{beat['location']}; \u987e\u68e0\uff1a\u534f\u540c"

    async def fake_plot(*_a, **_k):
        return {
            "unresolved_hooks": [beat["hook"]],
            "main_conflicts": ["\u591c\u96e8\u4ee4\u5f52\u5c5e", "\u8840\u5951\u53cd\u566c"],
            "character_arcs": [{"character": "\u6797\u821f", "current_stage": beat["title"]}],
        }

    async def fake_chapter_summary(*_a, **_k):
        return beat["summary"]

    monkeypatch.setattr(service, "_update_global_summary", fake_summary)
    monkeypatch.setattr(service, "_update_character_state", fake_state)
    monkeypatch.setattr(service, "_update_plot_arcs", fake_plot)
    monkeypatch.setattr(service, "_generate_chapter_summary", fake_chapter_summary)
    return await service.finalize_chapter(PROJECT_ID, chapter_number, chapter_text, USER_ID, skip_vector_update=True)


async def _load_outlines_map(session) -> Dict[int, SimpleNamespace]:
    rows = (await session.execute(select(ChapterOutline).where(ChapterOutline.project_id == PROJECT_ID))).scalars().all()
    return {
        row.chapter_number: SimpleNamespace(chapter_number=row.chapter_number, title=row.title, summary=row.summary)
        for row in rows
    }


async def _collect_history_for(session, target_chapter: int, memory_text: str) -> Dict[str, Any]:
    prior_chapters = (
        await session.execute(
            select(Chapter)
            .where(Chapter.project_id == PROJECT_ID, Chapter.chapter_number < target_chapter)
            .order_by(Chapter.chapter_number.asc())
        )
    ).scalars().all()
    mirrors = []
    for chapter in prior_chapters:
        version = None
        if chapter.selected_version_id:
            version = (
                await session.execute(select(ChapterVersion).where(ChapterVersion.id == chapter.selected_version_id))
            ).scalar_one_or_none()
        mirrors.append(_chapter_mirror(chapter, version.content if version else ""))
    orchestrator = _make_orchestrator(memory_text=memory_text)
    return await orchestrator._collect_history_context(
        project_id=PROJECT_ID,
        chapter_number=target_chapter,
        outlines_map=await _load_outlines_map(session),
        chapters=mirrors,
        user_id=USER_ID,
    )


async def _build_package(session, target_chapter: int):
    project = (
        await session.execute(
            select(NovelProject)
            .options(selectinload(NovelProject.blueprint), selectinload(NovelProject.outlines), selectinload(NovelProject.chapters))
            .where(NovelProject.id == PROJECT_ID)
        )
    ).scalar_one()
    outline = next(item for item in project.outlines if item.chapter_number == target_chapter)
    return await LongformContextService(session).build_context_package(
        project=project,
        outline=outline,
        chapter_number=target_chapter,
        writing_notes=f"ch{target_chapter-1}->ch{target_chapter}",
        chapter_mission={
            "chapter_number": target_chapter,
            "character_focus": ["\u6797\u821f", "\u987e\u68e0"],
            "scene_list": [{"goal": _beat(target_chapter)["title"], "characters": ["\u6797\u821f", "\u987e\u68e0"], "location": _beat(target_chapter)["location"]}],
        },
        allowed_new_characters=[],
    )


@pytest.mark.asyncio
async def test_production_multi_chapter_short_and_long_continuity_chain(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'multi-chapter-continuity.db'}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            await _seed_project(session)
            await session.commit()
            seen_summaries: List[str] = []
            last_global = ""
            # 连续 1→9 章逐章定稿并校验下一章上下文，第 10 章在循环后单独收口，
            # 覆盖目标要求的“正式路径连续生成至少 10 章”。
            for n in range(1, 10):
                chapter, content = await _prepare_chapter_for_finalize(session, n)
                await session.commit()
                pre_summary = extract_narrative_summary(chapter.real_summary, outline_summary=_beat(n)["title"])
                assert "generation_runtime" not in pre_summary
                result = await _finalize_one(session, monkeypatch, n, content)
                assert result["success"] is True, result
                assert result["updates"].get("chapter_real_summary") in {"updated", "unchanged"}
                await session.refresh(chapter)
                narrative = extract_narrative_summary(chapter.real_summary)
                assert narrative == _beat(n)["summary"]
                payload = parse_real_summary_payload(chapter.real_summary)
                assert payload.get("summary_text") == _beat(n)["summary"]
                assert isinstance(payload.get("generation_runtime"), dict)
                seen_summaries.append(narrative)
                memory = (await session.execute(select(ProjectMemory).where(ProjectMemory.project_id == PROJECT_ID))).scalar_one()
                assert memory.global_summary == _beat(n)["global"]
                assert memory.last_updated_chapter == n
                last_global = memory.global_summary or ""
                snapshots = list(
                    (
                        await session.execute(
                            select(ChapterSnapshot)
                            .where(ChapterSnapshot.project_id == PROJECT_ID, ChapterSnapshot.chapter_number == n)
                            .order_by(ChapterSnapshot.id.desc())
                        )
                    ).scalars()
                )
                assert snapshots and snapshots[0].chapter_summary == _beat(n)["summary"]
                await _seed_longform_artifacts_for_chapter(session, n, chapter.id)
                await session.commit()
                next_n = n + 1
                history = await _collect_history_for(session, next_n, memory_text=last_global)
                assert "generation_runtime" not in history["previous_summary"]
                assert history["previous_summary"] == _beat(n)["summary"]
                for prior in seen_summaries:
                    assert any(prior == item or prior in str(item) for item in history.get("completed_summaries", []))
                package = await _build_package(session, next_n)
                assert package.chapter_number == next_n
                assert last_global in (package.memory_digest.get("global_summary") or "")
                assert package.memory_digest.get("last_updated_chapter") == n
                recent_snap_summaries = [str(item.get("chapter_summary") or "") for item in (package.memory_digest.get("recent_snapshots") or [])]
                assert any(_beat(n)["summary"] in text for text in recent_snap_summaries)
                recent_events = package.timeline_digest.get("recent_events") or []
                assert any(_beat(n)["event"] in str(ev.get("title") or "") or _beat(n)["event"] in str(ev.get("description") or "") for ev in recent_events)
                edges = package.knowledge_digest.get("recent_event_edges") or []
                assert any(str(n) == str(edge.get("chapter_number")) or _beat(n)["event"] in str(edge.get("description") or "") for edge in edges)
                assert package.foreshadowing_task.must_resolve or package.foreshadowing_task.active_clues or package.foreshadowing_task.should_reinforce or package.foreshadowing_task.avoid_forgetting
                assert "\u6797\u821f" in package.prompt_text
                assert _beat(n)["hook"] in package.prompt_text or _beat(n)["clue"] in package.prompt_text or "\u591c\u96e8\u4ee4" in package.prompt_text
                gate = LongformContextService.evaluate_continuity_quality(
                    content=_beat(next_n)["content"],
                    package=package,
                    chapter_mission={"chapter_number": next_n, "character_focus": ["\u6797\u821f", "\u987e\u68e0"]},
                    chapter_number=next_n,
                )
                assert gate.metrics.get("longform_context_missing") is not True
                assert gate.metrics.get("continuity_degraded") is not True

            # 第 10 章收口：定稿后校验全书记忆、历史摘要链与快照覆盖到第 10 章。
            final_n = CHAPTER_BEATS[-1]["n"]
            assert final_n == 10
            chapter_last, content_last = await _prepare_chapter_for_finalize(session, final_n)
            await session.commit()
            result_last = await _finalize_one(session, monkeypatch, final_n, content_last)
            assert result_last["success"] is True
            await session.refresh(chapter_last)
            assert extract_narrative_summary(chapter_last.real_summary) == _beat(final_n)["summary"]
            await _seed_longform_artifacts_for_chapter(session, final_n, chapter_last.id)
            await session.commit()
            history_next = await _collect_history_for(session, final_n + 1, memory_text=_beat(final_n)["global"])
            assert history_next["previous_summary"] == _beat(final_n)["summary"]
            # 全部 10 章摘要都必须留在历史链里，任何一章丢失都说明长程上下文断裂。
            for beat in CHAPTER_BEATS:
                assert any(
                    beat["summary"] == item or beat["summary"] in str(item)
                    for item in history_next.get("completed_summaries", [])
                ), f"第{beat['n']}章摘要未进入历史链"
            memory = (await session.execute(select(ProjectMemory).where(ProjectMemory.project_id == PROJECT_ID))).scalar_one()
            assert memory.last_updated_chapter == final_n
            assert memory.global_summary == _beat(final_n)["global"]
            package_late = await _build_package(session, final_n)
            assert package_late.memory_digest.get("last_updated_chapter") == final_n
            snap_nums = {int(item.get("chapter_number")) for item in (package_late.memory_digest.get("recent_snapshots") or [])}
            assert snap_nums, "第10章上下文包没有任何近期快照"
            assert max(snap_nums) == final_n - 1
            # 逐章定稿必须留下 10 份章节快照，确认没有中途丢章。
            all_snapshot_numbers = set(
                (
                    await session.execute(
                        select(ChapterSnapshot.chapter_number).where(ChapterSnapshot.project_id == PROJECT_ID)
                    )
                )
                .scalars()
                .all()
            )
            assert set(range(1, final_n + 1)).issubset(all_snapshot_numbers)
            chapter1 = (await session.execute(select(Chapter).where(Chapter.project_id == PROJECT_ID, Chapter.chapter_number == 1))).scalar_one()
            version1 = (await session.execute(select(ChapterVersion).where(ChapterVersion.id == chapter1.selected_version_id))).scalar_one()
            replay = await _finalize_one(session, monkeypatch, 1, version1.content)
            assert replay.get("idempotent_replay") is True or replay["success"] is True
            await session.refresh(chapter1)
            assert extract_narrative_summary(chapter1.real_summary) == _beat(1)["summary"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_longform_package_cross_chapter_freshness_after_sequential_updates(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'longform-freshness.db'}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            session.add(User(id=1, username="fresh", email="fresh@example.com", hashed_password="hash"))
            session.add(NovelProject(id="p-fresh", user_id=1, title="fresh", initial_prompt="t", status="draft"))
            session.add(NovelBlueprint(project_id="p-fresh", title="fresh", world_setting={"novel_outline": [{"title": "v1", "expected_chapter_range": "1-3"}]}))
            for n, title in [(1, "old"), (2, "new"), (3, "cur")]:
                session.add(ChapterOutline(project_id="p-fresh", chapter_number=n, title=title, summary=f"outline{n}"))
                session.add(Chapter(project_id="p-fresh", chapter_number=n, status="successful" if n < 3 else "pending"))
            await session.flush()
            chapters = {c.chapter_number: c for c in (await session.execute(select(Chapter).where(Chapter.project_id == "p-fresh"))).scalars().all()}
            session.add(ProjectMemory(project_id="p-fresh", global_summary="\u6700\u65b0\u5168\u5c40\uff1a\u7b2c2\u7ae0\u540e\u4e3b\u89d2\u5df2\u79bb\u5f00\u9a7f\u7ad9\uff0c\u706b\u5370\u6307\u5411\u7981\u536b\u53f8\u3002", plot_arcs={"unresolved_hooks": ["\u7981\u536b\u53f8\u65e7\u6863\u7f3a\u53e3"], "main_conflicts": ["\u591c\u96e8\u4ee4\u5f52\u5c5e"], "character_arcs": []}, last_updated_chapter=2))
            session.add(ChapterSnapshot(project_id="p-fresh", chapter_number=1, chapter_summary="\u65e7\u6458\u8981\uff1a\u53ea\u5728\u57ce\u95e8\u593a\u4ee4\u3002", global_summary_snapshot="\u65e7\u5168\u5c40\uff1a\u4ec5\u593a\u4ee4", word_count=1000))
            session.add(ChapterSnapshot(project_id="p-fresh", chapter_number=2, chapter_summary="\u65b0\u6458\u8981\uff1a\u9a7f\u7ad9\u53cd\u566c\u540e\u706b\u5370\u6307\u5411\u7981\u536b\u53f8\u3002", global_summary_snapshot="\u65b0\u5168\u5c40\uff1a\u706b\u5370\u6307\u5411\u7981\u536b\u53f8", word_count=1200))
            session.add(Foreshadowing(project_id="p-fresh", chapter_id=chapters[2].id, chapter_number=2, content="\u7981\u536b\u53f8\u65e7\u6863\u7f3a\u53e3\u5fc5\u987b\u5728\u7b2c3\u7ae0\u63a8\u8fdb", type="setup", status="planted", keywords=["\u7981\u536b\u53f8", "\u65e7\u6863"], name="\u7981\u536b\u65e7\u6863", target_reveal_chapter=3, importance="major"))
            session.add(StoryClue(project_id="p-fresh", name="\u519b\u76d1\u6697\u7eb9", clue_type="plot_hook", description="\u7b2c2\u7ae0\u65b0\u53d1\u73b0\u7684\u519b\u76d1\u6697\u7eb9", planted_chapter=2, resolution_chapter=3, status="active", importance=5))
            session.add(TimelineEvent(project_id="p-fresh", chapter_number=1, event_title="\u65e7\u4e8b\u4ef6\u593a\u4ee4", event_description="old", involved_characters=["\u6797\u821f"], importance=5))
            session.add(TimelineEvent(project_id="p-fresh", chapter_number=2, event_title="\u65b0\u4e8b\u4ef6\u53cd\u566c", event_description="new", involved_characters=["\u6797\u821f", "\u987e\u68e0"], importance=9))
            source = CharacterNode(project_id="p-fresh", name="\u6797\u821f", role_type="\u4e3b\u89d2")
            target = CharacterNode(project_id="p-fresh", name="\u987e\u68e0", role_type="\u76df\u53cb")
            session.add_all([source, target])
            await session.flush()
            session.add(EventEdge(project_id="p-fresh", source_node_id=source.id, target_node_id=target.id, chapter_number=2, event_type="causality", description="\u7b2c2\u7ae0\u65b0\u8fb9\uff1a\u53cd\u566c\u540e\u987e\u68e0\u4ea4\u51fa\u519b\u76d1\u7ebf\u7d22", causality="\u519b\u76d1\u6697\u7eb9"))
            session.add(BlueprintCharacter(project_id="p-fresh", name="\u6797\u821f", identity="\u4e3b\u89d2", position=0))
            session.add(BlueprintCharacter(project_id="p-fresh", name="\u987e\u68e0", identity="\u76df\u53cb", position=1))
            await session.commit()
        async with session_factory() as session:
            project = (
                await session.execute(
                    select(NovelProject)
                    .options(selectinload(NovelProject.blueprint), selectinload(NovelProject.outlines), selectinload(NovelProject.chapters))
                    .where(NovelProject.id == "p-fresh")
                )
            ).scalar_one()
            outline = next(item for item in project.outlines if item.chapter_number == 3)
            package = await LongformContextService(session).build_context_package(
                project=project,
                outline=outline,
                chapter_number=3,
                writing_notes="fresh-ch2",
                chapter_mission={"chapter_number": 3, "character_focus": ["\u6797\u821f"]},
            )
            assert "\u706b\u5370\u6307\u5411\u7981\u536b\u53f8" in (package.memory_digest.get("global_summary") or "")
            assert package.memory_digest.get("last_updated_chapter") == 2
            snap_text = " ".join(str(item.get("chapter_summary") or "") for item in (package.memory_digest.get("recent_snapshots") or []))
            assert "\u9a7f\u7ad9\u53cd\u566c" in snap_text
            events = package.timeline_digest.get("recent_events") or []
            assert any("\u65b0\u4e8b\u4ef6\u53cd\u566c" in str(ev.get("title") or "") for ev in events)
            assert any("\u519b\u76d1" in str(c.get("description") or c.get("name") or "") for c in (package.foreshadowing_task.active_clues or [])) or "\u519b\u76d1" in package.prompt_text or "\u7981\u536b" in package.prompt_text
            edges = package.knowledge_digest.get("recent_event_edges") or []
            assert any("\u7b2c2\u7ae0\u65b0\u8fb9" in str(edge.get("description") or "") for edge in edges)
            assert "\u65e7\u5168\u5c40\uff1a\u4ec5\u593a\u4ee4" not in (package.memory_digest.get("global_summary") or "")
    finally:
        await engine.dispose()
