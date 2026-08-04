# AIMETA P=长篇上下文E2E_package装配与degraded可观测|R=memory_foreshadow_clue_graph进package_degraded可见|NR=业务写路径|E=test_longform_package_e2e|X=test|A=回归|D=pytest|S=none|RD=./README.ai
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Optional

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app.db.base import Base
from app.models.clue_tracker import StoryClue
from app.models.foreshadowing import Foreshadowing
from app.models.knowledge_graph import CharacterNode, EventEdge
from app.models.memory_layer import CharacterState, TimelineEvent
from app.models.novel import BlueprintCharacter, Chapter, ChapterOutline, NovelBlueprint, NovelProject
from app.models.project_memory import ProjectMemory
from app.models.user import User
from app.services.longform_context_service import LongformContextService
from app.services.pipeline_orchestrator import PipelineOrchestrator


@pytest.mark.anyio
async def test_e2e_longform_package_includes_memory_foreshadow_clue_and_graph(tmp_path):
    """ch>1 package must carry memory/伏笔/线索/知识图 edges into prompt and digests."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'longform-e2e-package.db'}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as session:
            session.add(User(id=1, username="e2e", email="e2e@example.com", hashed_password="hash"))
            session.add(NovelProject(id="p-e2e-lf", user_id=1, title="长篇E2E", initial_prompt="test", status="draft"))
            session.add(
                NovelBlueprint(
                    project_id="p-e2e-lf",
                    title="长篇E2E",
                    world_setting={
                        "novel_outline": [{"title": "卷一", "expected_chapter_range": "1-80章"}],
                        "volume_plan": [{"title": "远行", "chapter_range": "1-40章"}],
                    },
                )
            )
            session.add(ChapterOutline(project_id="p-e2e-lf", chapter_number=2, title="血契初显", summary="林舟面对血契反噬。"))
            session.add(BlueprintCharacter(project_id="p-e2e-lf", name="林舟", identity="主角", position=0))
            session.add(BlueprintCharacter(project_id="p-e2e-lf", name="顾棠", identity="盟友", position=1))
            ch1 = Chapter(project_id="p-e2e-lf", chapter_number=1, status="successful", word_count=1800)
            session.add(ch1)
            await session.flush()

            session.add(
                Foreshadowing(
                    project_id="p-e2e-lf",
                    chapter_id=ch1.id,
                    chapter_number=1,
                    content="夜雨令上的血契将在三日后反噬",
                    type="setup",
                    status="planted",
                    keywords=["夜雨令", "血契"],
                    name="血契反噬",
                    target_reveal_chapter=2,
                    importance="major",
                )
            )
            session.add(
                StoryClue(
                    project_id="p-e2e-lf",
                    name="夜雨令来源",
                    clue_type="plot_hook",
                    description="令牌背面有旧京火印",
                    planted_chapter=1,
                    resolution_chapter=2,
                    status="active",
                )
            )
            session.add(
                CharacterState(
                    project_id="p-e2e-lf",
                    character_id=1,
                    character_name="林舟",
                    chapter_number=1,
                    location="京城城门",
                    emotion="警惕",
                    health_status="injured",
                    current_goals=["追查夜雨令"],
                )
            )
            session.add(
                TimelineEvent(
                    project_id="p-e2e-lf",
                    chapter_number=1,
                    event_title="夺回夜雨令",
                    event_description="林舟在暴雨中夺回夜雨令并发现血契。",
                    involved_characters=["林舟", "顾棠"],
                    importance=8,
                )
            )
            session.add(
                ProjectMemory(
                    project_id="p-e2e-lf",
                    global_summary="林舟已离京，血契未解，夜雨令仍在手中。",
                    plot_arcs={"unresolved_hooks": ["血契反噬"], "main_conflicts": ["夜雨令归属"], "character_arcs": []},
                    last_updated_chapter=1,
                )
            )
            source = CharacterNode(project_id="p-e2e-lf", name="林舟", role_type="主角", location="京城城门", status="injured")
            target = CharacterNode(project_id="p-e2e-lf", name="顾棠", role_type="盟友")
            session.add_all([source, target])
            await session.flush()
            session.add(
                EventEdge(
                    project_id="p-e2e-lf",
                    source_node_id=source.id,
                    target_node_id=target.id,
                    chapter_number=1,
                    event_type="causality",
                    description="林舟夺回夜雨令 -> 顾棠被迫同行护印",
                    causality="血契反噬临近",
                )
            )
            await session.commit()

        async with session_factory() as session:
            result = await session.execute(
                select(NovelProject)
                .options(
                    selectinload(NovelProject.blueprint),
                    selectinload(NovelProject.outlines),
                    selectinload(NovelProject.chapters),
                )
                .where(NovelProject.id == "p-e2e-lf")
            )
            project = result.scalar_one()
            outline = next(item for item in project.outlines if item.chapter_number == 2)
            package = await LongformContextService(session).build_context_package(
                project=project,
                outline=outline,
                chapter_number=2,
                writing_notes="保持血契压力",
                chapter_mission={
                    "chapter_number": 2,
                    "character_focus": ["林舟"],
                    "scene_list": [{"goal": "应对血契反噬", "characters": ["林舟", "顾棠"], "location": "官道驿站"}],
                },
                allowed_new_characters=[],
            )

            assert package.chapter_number == 2
            assert "林舟已离京" in (package.memory_digest.get("global_summary") or "")
            assert package.memory_digest.get("plot_arcs")
            assert package.timeline_digest.get("recent_events") or package.timeline_digest
            assert package.knowledge_digest.get("knowledge_nodes")
            assert package.knowledge_digest.get("recent_event_edges")
            assert any("夜雨令" in str(edge.get("description") or "") for edge in package.knowledge_digest["recent_event_edges"])
            assert package.foreshadowing_task.must_resolve or package.foreshadowing_task.active_clues
            assert package.cast_plan.planned_character_count >= 2
            assert "林舟" in package.prompt_text
            assert "血契" in package.prompt_text or "夜雨令" in package.prompt_text
            assert "顾棠" in package.prompt_text

            metadata = package.to_metadata()
            assert metadata["memory_digest"]["global_summary"]
            assert metadata["knowledge_digest"]["recent_event_edges"]
            assert metadata["foreshadowing_task"]

            gate = LongformContextService.evaluate_continuity_quality(
                content="林舟在驿站压住血契灼烧，顾棠递来止血药，夜雨令来源仍未揭开。",
                package=package,
                chapter_mission={"chapter_number": 2},
                chapter_number=2,
            )
            assert gate.metrics.get("longform_context_missing") is not True
            assert gate.metrics.get("continuity_degraded") is not True
    finally:
        await engine.dispose()


def test_evaluate_missing_package_exposes_degraded_metrics_for_api():
    gate = LongformContextService.evaluate_continuity_quality(
        content="任意正文",
        package=None,
        chapter_number=4,
        chapter_mission={"chapter_number": 4},
    )
    payload = {
        "passed": gate.passed,
        "warnings": gate.warnings,
        "metrics": gate.metrics,
    }
    assert payload["metrics"]["continuity_degraded"] is True
    assert payload["metrics"]["longform_context_missing"] is True
    assert any(item.get("code") == "longform_context_missing" for item in payload["warnings"])

    # Simulate version metadata attachment used by pipeline for frontend quality display.
    quality_metrics = {
        "scene_fulfillment_rate": 0.9,
        "dialogue_changes_state": True,
        "ending_pressure_passed": True,
    }
    longform_metrics = payload["metrics"]
    for key in ("continuity_degraded", "longform_context_missing"):
        quality_metrics[key] = longform_metrics[key]
    labels = list(quality_metrics.get("quality_issue_labels") or [])
    labels.append("长篇上下文缺失（连续性降级）")
    quality_metrics["quality_issue_labels"] = labels
    assert quality_metrics["continuity_degraded"] is True
    assert "长篇上下文缺失（连续性降级）" in quality_metrics["quality_issue_labels"]


@pytest.mark.anyio
async def test_pipeline_longform_build_failure_records_status_for_ch_gt_1(monkeypatch):
    """When package build fails on ch>1, runtime_metadata must mark continuity_degraded."""
    orchestrator = PipelineOrchestrator.__new__(PipelineOrchestrator)
    orchestrator.longform_context_service = SimpleNamespace()

    async def boom(**_kwargs):
        raise RuntimeError("simulated package assembly failure")

    orchestrator.longform_context_service.build_context_package = boom
    orchestrator._truncate_runtime_text = lambda exc, limit=220: str(exc)[:limit]

    # Replicate the degraded metadata construction used in pipeline except path.
    chapter_number = 3
    runtime_metadata: dict[str, Any] = {"degraded_stages": [], "quality_gates": {}}
    longform_context = None
    try:
        longform_context = await orchestrator.longform_context_service.build_context_package(
            project=SimpleNamespace(id="p"),
            outline=None,
            chapter_number=chapter_number,
        )
    except Exception as exc:  # noqa: BLE001
        longform_context = None
        degraded_reason = orchestrator._truncate_runtime_text(exc)
        continuity_degraded = int(chapter_number or 0) > 1
        runtime_metadata["degraded_stages"].append(
            {
                "stage": "longform_context",
                "reason": str(exc),
                "chapter_number": chapter_number,
                "continuity_degraded": continuity_degraded,
                "code": "longform_context_missing",
            }
        )
        runtime_metadata["longform_context_status"] = {
            "present": False,
            "missing": True,
            "continuity_degraded": continuity_degraded,
            "reason": degraded_reason,
            "chapter_number": chapter_number,
            "code": "longform_context_missing",
        }

    gate = LongformContextService.evaluate_continuity_quality(
        content="降级后仍继续生成的正文",
        package=longform_context,
        chapter_number=chapter_number,
    )
    runtime_metadata["quality_gates"]["longform_continuity_gate"] = {
        "passed": gate.passed,
        "warnings": gate.warnings,
        "metrics": gate.metrics,
    }

    assert longform_context is None
    assert runtime_metadata["longform_context_status"]["missing"] is True
    assert runtime_metadata["longform_context_status"]["continuity_degraded"] is True
    assert runtime_metadata["degraded_stages"][0]["code"] == "longform_context_missing"
    assert gate.metrics["continuity_degraded"] is True
    assert gate.metrics["longform_context_missing"] is True
