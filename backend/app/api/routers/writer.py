# AIMETA P=写作API_章节生成和大纲创建|R=章节生成_大纲生成_评审_L2导演脚本_护栏检查|NR=不含数据存储|E=route:POST_/api/writer/*|X=http|A=生成_评审_过滤|D=fastapi,openai|S=net,db|RD=./README.ai
"""
Writer API Router - 人类化起点长篇写作系统

核心架构：
- L1 Planner：全知规划层（蓝图/大纲）
- L2 Director：章节导演脚本（ChapterMission）
- L3 Writer：有限视角正文生成

关键改进：
1. 信息可见性过滤：L3 Writer 只能看到已登场角色
2. 跨章 1234 逻辑：通过 ChapterMission 控制每章只写一个节拍
3. 后置护栏检查：自动检测并修复违规内容
"""
import asyncio
import json
import logging
import uuid
import math
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...core.config import settings
from ...core.dependencies import get_current_user
from ...db.session import AsyncSessionLocal, get_session
from ...models.novel import Chapter, ChapterOutline, ChapterVersion, ChapterEvaluation, NovelProject
from ...models.project_memory import ProjectMemory
from ...schemas.novel import (
    CancelChapterRequest,
    Chapter as ChapterSchema,
    ChapterGenerationStatus,
    AdvancedGenerateRequest,
    AdvancedGenerateResponse,
    DeleteChapterRequest,
    EditChapterRequest,
    EvaluateChapterRequest,
    FinalizeChapterRequest,
    FinalizeChapterResponse,
    GenerateChapterRequest,
    GenerateOutlineRequest,
    NovelProject as NovelProjectSchema,
    RewriteChapterOutlineRequest,
    SelectVersionRequest,
    UpdateChapterOutlineRequest,
)
from ...schemas.user import UserInDB
from ...services.chapter_context_service import ChapterContextService
from ...services.chapter_ingest_service import ChapterIngestionService
from ...services.llm_service import LLMService
from ...services.novel_service import NovelService, build_chapter_progress_snapshot
from ...services.prompt_service import PromptService
from ...services.vector_store_service import VectorStoreService
from ...services.writer_context_builder import WriterContextBuilder
from ...services.chapter_guardrails import ChapterGuardrails
from ...services.ai_review_service import AIReviewService
from ...services.cache_service import CacheService
from ...services.finalize_service import FinalizeService
from ...services.foreshadowing_service import ForeshadowingService
from ...services.enrichment_service import EnrichmentService
from ...services.memory_layer_service import MemoryLayerService
from ...utils.json_utils import remove_think_tags, unwrap_markdown_json
from ...services.pipeline_orchestrator import PipelineOrchestrator

router = APIRouter(prefix="/api/writer", tags=["Writer"])
logger = logging.getLogger(__name__)
DEFAULT_GENERATED_VERSION_COUNT = 1  # 默认生成1个版本
MIN_GENERATED_VERSION_COUNT = 1
MAX_GENERATED_VERSION_COUNT = 4  # 最多生成4个版本
MAX_STORED_CHAPTER_VERSIONS = 4  # 最多保存4个版本
COMPAT_GENERATE_VERSION_COUNT = 1
COMPAT_GENERATE_TARGET_WORD_COUNT = 3200
COMPAT_GENERATE_MIN_WORD_COUNT = 2400
# 兼容入口的后台任务会先跑导演脚本，再跑正文生成；质量模式下允许更长处理时间，
# 但 stale 只在确实长时间无心跳时才判定，避免“还在跑”与“已卡死”混淆。
CHAPTER_STALE_TIMEOUT = timedelta(minutes=30)
BACKGROUND_GENERATION_TIMEOUT_MIN_SECONDS = 15 * 60  # 最小15分钟
BACKGROUND_GENERATION_TIMEOUT_MAX_SECONDS = 4 * 60 * 60  # 最大4小时
GENERATION_HEARTBEAT_GRACE_SECONDS = 8 * 60
BACKGROUND_GENERATION_TIMEOUT_DISABLED = os.getenv("XUANQIONG_WENSHU_DISABLE_GENERATION_TIMEOUT", "0").strip().lower() in {"1", "true", "yes", "on"}
_GENERATION_TASK_SEMAPHORE = asyncio.Semaphore(2)
_FINALIZE_TASK_SEMAPHORE = asyncio.Semaphore(1)
_BUSY_CHAPTER_STATUSES = {
    ChapterGenerationStatus.GENERATING.value,
    ChapterGenerationStatus.EVALUATING.value,
    ChapterGenerationStatus.SELECTING.value,
}


def _clamp_generated_version_count(value: int) -> int:
    return max(
        MIN_GENERATED_VERSION_COUNT,
        min(MAX_GENERATED_VERSION_COUNT, int(value)),
    )


def _normalize_datetime_to_utc(value: Optional[datetime]) -> Optional[datetime]:
    if not value:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _build_busy_progress_message(status_value: str) -> str:
    if status_value == ChapterGenerationStatus.EVALUATING.value:
        return "章节草稿已生成，正在评估候选版本"
    if status_value == ChapterGenerationStatus.SELECTING.value:
        return "章节候选版本已生成，正在整理可确认结果"
    return "章节已经在后台生成，请稍后刷新查看"


def _build_busy_progress_stage(status_value: str) -> str:
    if status_value == ChapterGenerationStatus.EVALUATING.value:
        return "evaluating"
    if status_value == ChapterGenerationStatus.SELECTING.value:
        return "selecting"
    return "generating"


def _extract_runtime_heartbeat_at(chapter: Optional[Chapter]) -> Optional[datetime]:
    runtime = _load_generation_runtime_state(chapter).get("generation_runtime")
    if not isinstance(runtime, dict):
        return None
    raw_value = runtime.get("heartbeat_at") or runtime.get("updated_at")
    if not raw_value:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw_value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return _normalize_datetime_to_utc(parsed)



def _is_busy_chapter_stale(chapter: Chapter) -> bool:
    if chapter.status not in _BUSY_CHAPTER_STATUSES:
        return False
    heartbeat_at = _extract_runtime_heartbeat_at(chapter)
    last_updated_at = heartbeat_at or _normalize_datetime_to_utc(chapter.updated_at or chapter.created_at)
    if not last_updated_at:
        return False
    return datetime.now(timezone.utc) - last_updated_at >= CHAPTER_STALE_TIMEOUT


def _load_generation_runtime_state(chapter: Optional[Chapter]) -> Dict[str, Any]:
    raw_summary = (chapter.real_summary or "").strip() if chapter else ""
    if not raw_summary:
        return {}
    try:
        payload = json.loads(raw_summary)
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _build_generation_runtime_state(
    *,
    run_id: str,
    cancel_requested: bool = False,
    reason: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> str:
    runtime_payload: Dict[str, Any] = {
        "run_id": run_id,
        "cancel_requested": cancel_requested,
    }
    if reason:
        runtime_payload["reason"] = reason
    if extra:
        runtime_payload.update(extra)
    payload: Dict[str, Any] = {
        "generation_runtime": runtime_payload,
    }
    return json.dumps(payload, ensure_ascii=False)


def _build_failed_generation_runtime_state(
    chapter: Chapter,
    *,
    run_id: str,
    reason: str,
    cancel_requested: bool = False,
    level: str = "error",
) -> str:
    payload = _load_generation_runtime_state(chapter)
    runtime = payload.get("generation_runtime") if isinstance(payload.get("generation_runtime"), dict) else {}
    now_iso = datetime.now(timezone.utc).isoformat()
    events = runtime.get("events") if isinstance(runtime.get("events"), list) else []
    event = {
        "at": now_iso,
        "stage": "failed",
        "level": level,
        "message": reason,
    }
    normalized_runtime: Dict[str, Any] = {
        **runtime,
        "run_id": run_id,
        "cancel_requested": cancel_requested,
        "reason": reason,
        "progress_stage": "failed",
        "progress_message": reason,
        "progress_percent": 100,
        "allowed_actions": ["refresh_status", "retry_generation"],
        "started_at": runtime.get("started_at") or now_iso,
        "updated_at": now_iso,
        "heartbeat_at": now_iso,
        "estimated_remaining_seconds": 0,
        "chapter_number": chapter.chapter_number,
        "events": [*events[-199:], event],
    }
    return json.dumps({"generation_runtime": normalized_runtime}, ensure_ascii=False)


def _get_generation_run_id(chapter: Optional[Chapter]) -> Optional[str]:
    runtime = _load_generation_runtime_state(chapter).get("generation_runtime")
    if not isinstance(runtime, dict):
        return None
    run_id = runtime.get("run_id")
    return str(run_id) if run_id else None


def _is_generation_cancel_requested(chapter: Optional[Chapter], run_id: Optional[str] = None) -> bool:
    runtime = _load_generation_runtime_state(chapter).get("generation_runtime")
    if not isinstance(runtime, dict):
        return False
    if run_id and runtime.get("run_id") and runtime.get("run_id") != run_id:
        return False
    return bool(runtime.get("cancel_requested"))


async def _try_claim_chapter_generation(
    session: AsyncSession,
    *,
    chapter_id: int,
    chapter_number: int,
) -> Optional[str]:
    run_id = str(uuid.uuid4())
    result = await session.execute(
        update(Chapter)
        .where(
            Chapter.id == chapter_id,
            Chapter.status.not_in(list(_BUSY_CHAPTER_STATUSES)),
        )
        .values(
            real_summary=_build_generation_runtime_state(
                run_id=run_id,
                extra={
                    "progress_stage": "queued",
                    "progress_message": "章节已进入后台队列，等待任务启动",
                    "chapter_number": chapter_number,
                    "allowed_actions": ["refresh_status", "cancel_generation"],
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
            ),
            selected_version_id=None,
            status=ChapterGenerationStatus.GENERATING.value,
            updated_at=datetime.now(timezone.utc),
        )
    )
    await session.commit()
    return run_id if result.rowcount else None


async def _mark_busy_chapter_failed(
    session: AsyncSession,
    *,
    chapter: Chapter,
    reason: str,
    run_id: Optional[str] = None,
) -> None:
    if run_id and _get_generation_run_id(chapter) != run_id:
        logger.info(
            "Skip marking chapter failed because run_id mismatched: project=%s chapter=%s expected=%s actual=%s",
            chapter.project_id,
            chapter.chapter_number,
            run_id,
            _get_generation_run_id(chapter),
        )
        return
    chapter.status = ChapterGenerationStatus.FAILED.value
    chapter.real_summary = _build_failed_generation_runtime_state(
        chapter,
        run_id=run_id or _get_generation_run_id(chapter) or "unknown",
        cancel_requested=_is_generation_cancel_requested(chapter, run_id),
        reason=reason,
    )
    session.add(
        ChapterEvaluation(
            chapter_id=chapter.id,
            version_id=chapter.selected_version_id,
            decision="generation_failed",
            feedback=reason,
        )
    )
    await session.commit()
    await session.refresh(chapter)


def _coerce_positive_int(value: Optional[Any], default: int) -> int:
    try:
        parsed = int(value)
        if parsed > 0:
            return parsed
    except (TypeError, ValueError):
        pass
    return default


@asynccontextmanager
async def _bounded_task_slot(semaphore: asyncio.Semaphore):
    async with semaphore:
        yield


def _calculate_generation_timeout_seconds(flow_config: Dict[str, Any]) -> int:
    """
    兼容入口会串行执行导演脚本、正文生成，以及可选的扩写与诊断优化阶段。
    这里给的是后台总闸门预算，宁可偏宽，也不要在任务仍有心跳时误杀长流程。
    """
    if BACKGROUND_GENERATION_TIMEOUT_DISABLED:
        return 0

    target_word_count = _coerce_positive_int(
        flow_config.get("target_word_count"),
        COMPAT_GENERATE_TARGET_WORD_COUNT,
    )
    estimated_seconds = 12 * 60
    estimated_seconds += min(30 * 60, max(0, int(target_word_count / 100)) * 18)
    if flow_config.get("enable_enrichment"):
        max_iterations = _coerce_positive_int(flow_config.get("max_enrich_iterations"), 1)
        estimated_seconds += min(max_iterations, 4) * 5 * 60
    if flow_config.get("enable_consistency"):
        estimated_seconds += 8 * 60
    if flow_config.get("enable_self_critique"):
        estimated_seconds += 45 * 60
    if flow_config.get("enable_optimizer"):
        estimated_seconds += 12 * 60
    return max(
        BACKGROUND_GENERATION_TIMEOUT_MIN_SECONDS,
        min(BACKGROUND_GENERATION_TIMEOUT_MAX_SECONDS, estimated_seconds),
    )


def _build_compat_generate_flow_config(request: GenerateChapterRequest) -> Dict[str, Any]:
    # 使用用户设置的字数，如果没有设置则使用默认值
    target_word_count = _coerce_positive_int(
        request.target_word_count,
        COMPAT_GENERATE_TARGET_WORD_COUNT,
    )
    # 不再强制限制字数上限，允许用户自由设置
    target_word_count = max(3000, target_word_count)  # 最低3000字

    min_word_count = _coerce_positive_int(
        request.min_word_count,
        COMPAT_GENERATE_MIN_WORD_COUNT,
    )
    min_word_count = max(3000, min_word_count)  # 最低3000字

    # 确保最低字数不超过目标字数
    if min_word_count > target_word_count:
        min_word_count = max(3000, int(target_word_count * 0.75))

    requires_word_enforcement = bool(request.target_word_count or request.min_word_count)
    requested_target = max(target_word_count, min_word_count)
    if requested_target >= 5500:
        enrich_iterations = 6
    elif requested_target >= 4500:
        enrich_iterations = 4
    elif requires_word_enforcement:
        enrich_iterations = 3
    else:
        enrich_iterations = 1

    return {
        "preset": "longform",
        "versions": COMPAT_GENERATE_VERSION_COUNT,
        "enable_preview": False,
        "enable_optimizer": False,
        "enable_consistency": False,
        "enable_enrichment": True,
        "enable_constitution": True,
        "enable_persona": True,
        "enable_six_dimension": False,
        "enable_reader_sim": False,
        "enable_self_critique": True,
        "enable_memory": True,
        "enable_rag": True,
        "rag_mode": "two_stage",
        "enable_foreshadowing": True,
        "enable_faction": True,
        "allow_truncated_response": True,
        "target_word_count": target_word_count,
        "min_word_count": min_word_count,
        "max_enrich_iterations": enrich_iterations,
        "enforce_min_word_count": True,
    }


async def _load_project_schema(
    service: NovelService,
    project_id: str,
    user_id: int,
    generation_runtime: Optional[Dict[str, Any]] = None,
) -> NovelProjectSchema:
    project = await service.get_project_schema(project_id, user_id)
    if generation_runtime:
        return project.model_copy(update={"generation_runtime": generation_runtime})
    return project


def _extract_tail_excerpt(text: Optional[str], limit: int = 500) -> str:
    """截取章节结尾文本，默认保留 500 字。"""
    if not text:
        return ""
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[-limit:]


def _count_non_whitespace_chars(text: Optional[str]) -> int:
    if not text:
        return 0
    return len("".join(str(text).split()))


def _truncate_text(text: Optional[str], limit: int) -> str:
    if not text:
        return ""
    cleaned = str(text).strip()
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit].rstrip()}..."


def _looks_like_ending_signal(text: Optional[str]) -> bool:
    if not text:
        return False
    lowered = str(text).lower()
    ending_keywords = (
        "大结局",
        "结局",
        "终章",
        "完结",
        "尾声",
        "落幕",
        "终局",
        "最终章",
        "the end",
        "finale",
        "ending",
    )
    return any(keyword in lowered for keyword in ending_keywords)


def _build_recent_chapter_track(
    completed_chapters: List[Dict[str, Any]],
    *,
    max_items: int = 6,
    summary_limit: int = 220,
) -> str:
    if not completed_chapters:
        return "暂无历史章节（这是第一章）"

    ordered = sorted(
        completed_chapters,
        key=lambda item: int(item.get("chapter_number") or 0),
    )
    recent = ordered[-max_items:]
    lines: List[str] = []
    for item in recent:
        chapter_no = int(item.get("chapter_number") or 0)
        title = str(item.get("title") or f"第{chapter_no}章").strip()
        summary = _truncate_text(item.get("summary"), summary_limit)
        if not summary:
            summary = "（暂无摘要）"
        lines.append(f"- 第{chapter_no}章《{title}》：{summary}")
    return "\n".join(lines)


def _format_plot_arc_digest(plot_arcs: Optional[Dict[str, Any]], *, max_items: int = 4) -> str:
    if not isinstance(plot_arcs, dict) or not plot_arcs:
        return "暂无未闭环线索记录"

    lines: List[str] = []

    unresolved_hooks = plot_arcs.get("unresolved_hooks") or []
    if isinstance(unresolved_hooks, list) and unresolved_hooks:
        lines.append("未闭环钩子：")
        for item in unresolved_hooks[:max_items]:
            if not isinstance(item, dict):
                continue
            desc = _truncate_text(
                str(item.get("description") or item.get("content") or "").strip(),
                120,
            )
            if not desc:
                continue
            planted = item.get("planted_chapter") or item.get("chapter_number") or "?"
            lines.append(f"- [钩子] 第{planted}章埋设：{desc}")

    main_conflicts = plot_arcs.get("main_conflicts") or []
    if isinstance(main_conflicts, list) and main_conflicts:
        lines.append("主冲突状态：")
        for item in main_conflicts[:max_items]:
            if not isinstance(item, dict):
                continue
            desc = _truncate_text(str(item.get("description") or "").strip(), 120)
            if not desc:
                continue
            status = str(item.get("status") or "unknown").strip()
            lines.append(f"- [冲突/{status}] {desc}")

    character_arcs = plot_arcs.get("character_arcs") or []
    if isinstance(character_arcs, list) and character_arcs:
        lines.append("角色弧进度：")
        for item in character_arcs[:max_items]:
            if not isinstance(item, dict):
                continue
            character = str(item.get("character") or "角色").strip()
            stage = str(item.get("current_stage") or "当前阶段").strip()
            milestone = _truncate_text(
                str(item.get("next_milestone") or item.get("next_goal") or "").strip(),
                80,
            )
            if milestone:
                lines.append(f"- [{character}] {stage} -> 下一里程碑：{milestone}")
            else:
                lines.append(f"- [{character}] 当前阶段：{stage}")

    return "\n".join(lines) if lines else "暂无未闭环线索记录"


async def _refresh_edit_summary_and_ingest(
    project_id: str,
    chapter_number: int,
    content: str,
    user_id: Optional[int],
) -> None:
    async with AsyncSessionLocal() as session:
        llm_service = LLMService(session)

        stmt = (
            select(Chapter)
            .options(selectinload(Chapter.selected_version))
            .where(
                Chapter.project_id == project_id,
                Chapter.chapter_number == chapter_number,
            )
        )
        result = await session.execute(stmt)
        chapter = result.scalars().first()
        if not chapter:
            return

        summary_text = None
        try:
            summary = await llm_service.get_summary(
                content,
                temperature=0.15,
                user_id=user_id,
            )
            summary_text = remove_think_tags(summary)
        except Exception as exc:
            logger.warning("编辑章节后自动生成摘要失败: %s", exc)

        if summary_text and chapter.selected_version and chapter.selected_version.content == content:
            chapter.real_summary = summary_text
            await session.commit()

        try:
            outline_stmt = select(ChapterOutline).where(
                ChapterOutline.project_id == project_id,
                ChapterOutline.chapter_number == chapter_number,
            )
            outline_result = await session.execute(outline_stmt)
            outline = outline_result.scalars().first()
            title = outline.title if outline and outline.title else f"第{chapter_number}章"
            ingest_service = ChapterIngestionService(llm_service=llm_service)
            await ingest_service.ingest_chapter(
                project_id=project_id,
                chapter_number=chapter_number,
                title=title,
                content=content,
                summary=None,
                user_id=user_id or 0,
            )
            logger.info("章节 %s 向量化入库成功", chapter_number)
        except Exception as exc:
            logger.error("章节 %s 向量化入库失败: %s", chapter_number, exc)

async def _finalize_chapter_async(
    project_id: str,
    chapter_number: int,
    selected_version_id: int,
    user_id: int,
    skip_vector_update: bool = False,
) -> None:
    try:
        async with AsyncSessionLocal() as session:
            stmt = (
                select(Chapter)
                .options(selectinload(Chapter.versions))
                .where(
                    Chapter.project_id == project_id,
                    Chapter.chapter_number == chapter_number,
                )
            )
            result = await session.execute(stmt)
            chapter = result.scalars().first()
            if not chapter:
                return

            selected_version = next(
                (v for v in chapter.versions if v.id == selected_version_id),
                None,
            )
            if not selected_version or not selected_version.content:
                return

            chapter.selected_version_id = selected_version.id
            chapter.status = ChapterGenerationStatus.SUCCESSFUL.value
            chapter.word_count = len(selected_version.content or "")
            await session.commit()

            await _run_finalize_pipeline(
                session=session,
                project_id=project_id,
                chapter=chapter,
                selected_version=selected_version,
                user_id=user_id,
                skip_vector_update=skip_vector_update,
                refresh_memory_layer=True,
            )
    except Exception as exc:
        logger.warning(
            "后台定稿任务失败（已跳过）: project=%s chapter=%s error=%s",
            project_id,
            chapter_number,
            exc,
        )


async def _run_finalize_pipeline(
    *,
    session: AsyncSession,
    project_id: str,
    chapter: Chapter,
    selected_version: ChapterVersion,
    user_id: int,
    skip_vector_update: bool = False,
    refresh_memory_layer: bool = True,
) -> Dict[str, Any]:
    llm_service = LLMService(session)

    vector_store = None
    if settings.vector_store_enabled and not skip_vector_update:
        try:
            vector_store = VectorStoreService()
        except RuntimeError as exc:
            logger.warning("向量库初始化失败，跳过定稿写入: %s", exc)

    finalize_service = FinalizeService(session, llm_service, vector_store)
    finalize_result = await finalize_service.finalize_chapter(
        project_id=project_id,
        chapter_number=chapter.chapter_number,
        chapter_text=selected_version.content,
        user_id=user_id,
        skip_vector_update=skip_vector_update,
    )
    result: Dict[str, Any] = {"finalize": finalize_result}

    if not refresh_memory_layer:
        return result

    try:
        project_stmt = (
            select(NovelProject)
            .options(selectinload(NovelProject.characters))
            .where(
                NovelProject.id == project_id,
                NovelProject.user_id == user_id,
            )
        )
        project_result = await session.execute(project_stmt)
        project = project_result.scalars().first()
        character_names = [
            character.name.strip()
            for character in (project.characters if project else [])
            if getattr(character, "name", None) and character.name.strip()
        ]

        memory_service = MemoryLayerService(session, llm_service, PromptService(session))
        memory_result = await memory_service.update_memory_after_chapter(
            project_id=project_id,
            chapter_number=chapter.chapter_number,
            chapter_content=selected_version.content,
            character_names=character_names,
            user_id=user_id,
        )
        result["memory_layer"] = memory_result
    except Exception as exc:
        await session.rollback()
        logger.warning(
            "章节 %s 记忆层更新失败，已保留定稿结果: %s",
            chapter.chapter_number,
            exc,
        )
        result["memory_layer"] = {
            "success": False,
            "error": str(exc)[:200],
        }

    try:
        cache_service = CacheService()
        for cache_key in (
            f"emotion_curve_enhanced:{project_id}",
            f"story_trajectory:{project_id}",
            f"creative_guidance:{project_id}",
        ):
            await cache_service.delete(cache_key)
        result["analysis_cache"] = {"success": True, "invalidated": True}
    except Exception as exc:
        logger.warning("清理分析缓存失败，已保留定稿结果: %s", exc)
        result["analysis_cache"] = {"success": False, "error": str(exc)[:200]}

    return result


async def _schedule_finalize_task(
    project_id: str,
    chapter_number: int,
    selected_version_id: int,
    user_id: int,
    skip_vector_update: bool = False,
) -> None:
    async with _bounded_task_slot(_FINALIZE_TASK_SEMAPHORE):
        await _finalize_chapter_async(
            project_id=project_id,
            chapter_number=chapter_number,
            selected_version_id=selected_version_id,
            user_id=user_id,
            skip_vector_update=skip_vector_update,
        )


async def _collect_foreshadowing_async(
    project_id: str,
    chapter_id: int,
    chapter_number: int,
    chapter_content: str,
) -> None:
    try:
        async with AsyncSessionLocal() as session:
            foreshadowing_service = ForeshadowingService(session)
            auto_collect_result = await foreshadowing_service.auto_collect_from_chapter(
                project_id=project_id,
                chapter_id=chapter_id,
                chapter_number=chapter_number,
                chapter_content=chapter_content,
                max_items=6,
            )
            if auto_collect_result.get("created", 0) > 0:
                await session.commit()
                logger.info(
                    "章节 %s 自动收集伏笔成功: created=%s",
                    chapter_number,
                    auto_collect_result.get("created", 0),
                )
    except Exception as exc:
        logger.warning("章节 %s 自动收集伏笔失败（已跳过）: %s", chapter_number, exc)


async def _generate_chapter_async(
    *,
    project_id: str,
    chapter_number: int,
    user_id: int,
    writing_notes: Optional[str],
    flow_config: Dict[str, Any],
    run_id: str,
) -> None:
    async with _bounded_task_slot(_GENERATION_TASK_SEMAPHORE):
        async with AsyncSessionLocal() as session:
            orchestrator = PipelineOrchestrator(session)
            novel_service = NovelService(session)
            timeout_seconds = _calculate_generation_timeout_seconds(flow_config)
            timeout_enabled = timeout_seconds > 0
            try:
                logger.info(
                    "Background chapter generation started: user=%s project=%s chapter=%s preset=%s timeout=%s",
                    user_id,
                    project_id,
                    chapter_number,
                    flow_config.get("preset"),
                    f"{timeout_seconds}s" if timeout_enabled else "disabled",
                )
                generation_coro = orchestrator.generate_chapter(
                    project_id=project_id,
                    chapter_number=chapter_number,
                    writing_notes=writing_notes,
                    user_id=user_id,
                    flow_config=flow_config,
                    generation_run_id=run_id,
                )
                if timeout_enabled:
                    await asyncio.wait_for(generation_coro, timeout=timeout_seconds)
                else:
                    await generation_coro
                logger.info(
                    "Background chapter generation finished: user=%s project=%s chapter=%s",
                    user_id,
                    project_id,
                    chapter_number,
                )
            except asyncio.TimeoutError:
                timeout_minutes = max(1, round(timeout_seconds / 60))
                reason = (
                    f"后台生成超时（超过 {timeout_minutes} 分钟仍未完成），"
                    "系统已自动终止本次任务。请检查模型连通性后重试。"
                )
                logger.error(
                    "Background chapter generation timed out: user=%s project=%s chapter=%s timeout=%ss",
                    user_id,
                    project_id,
                    chapter_number,
                    timeout_seconds,
                )
                try:
                    await session.rollback()
                    chapter = await novel_service.get_or_create_chapter(project_id, chapter_number)
                    await _mark_busy_chapter_failed(session, chapter=chapter, reason=reason, run_id=run_id)
                except Exception as mark_exc:
                    await session.rollback()
                    logger.exception(
                        "Failed to mark chapter as failed after timeout: project=%s chapter=%s error=%s",
                        project_id,
                        chapter_number,
                        mark_exc,
                    )
            except Exception as exc:
                logger.exception(
                    "Background chapter generation failed: user=%s project=%s chapter=%s error=%s",
                    user_id,
                    project_id,
                    chapter_number,
                    exc,
                )
                try:
                    await session.rollback()
                    chapter = await novel_service.get_or_create_chapter(project_id, chapter_number)
                    detail = exc.detail if isinstance(exc, HTTPException) else None
                    if isinstance(detail, dict):
                        message = detail.get("message") or str(exc)
                        hint = detail.get("hint")
                        current_word_count = detail.get("current_word_count")
                        min_word_count = detail.get("min_word_count")
                        target_word_count = detail.get("target_word_count")
                        stage = detail.get("stage")
                        reason_parts = [str(message).strip()]
                        if current_word_count is not None and min_word_count is not None and target_word_count is not None:
                            reason_parts.append(
                                f"当前字数 {current_word_count}，最低要求 {min_word_count}，目标字数 {target_word_count}。"
                            )
                        if stage:
                            reason_parts.append(f"失败阶段：{stage}。")
                        if hint:
                            reason_parts.append(str(hint).strip())
                        reason = " ".join(part for part in reason_parts if part)
                    else:
                        reason = f"生成失败：{str(exc)[:200]}"
                    await _mark_busy_chapter_failed(
                        session,
                        chapter=chapter,
                        reason=reason,
                        run_id=run_id,
                    )
                except Exception as mark_exc:
                    await session.rollback()
                    logger.exception(
                        "Failed to mark chapter as failed after background generation error: project=%s chapter=%s error=%s",
                        project_id,
                        chapter_number,
                        mark_exc,
                    )


async def _schedule_generate_task(
    project_id: str,
    chapter_number: int,
    user_id: int,
    writing_notes: Optional[str],
    flow_config: Dict[str, Any],
    run_id: str,
) -> None:
    await _generate_chapter_async(
        project_id=project_id,
        chapter_number=chapter_number,
        user_id=user_id,
        writing_notes=writing_notes,
        flow_config=flow_config,
        run_id=run_id,
    )


@router.post("/advanced/generate", response_model=AdvancedGenerateResponse)
async def advanced_generate_chapter(
    request: AdvancedGenerateRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> AdvancedGenerateResponse:
    """
    高级写作入口：通过 PipelineOrchestrator 统一编排生成流程。
    """
    orchestrator = PipelineOrchestrator(session)
    result = await orchestrator.generate_chapter(
        project_id=request.project_id,
        chapter_number=request.chapter_number,
        writing_notes=request.writing_notes,
        user_id=current_user.id,
        flow_config=request.flow_config.model_dump(),
    )

    flow_config = request.flow_config
    if flow_config.async_finalize and result.get("variants"):
        best_index = result.get("best_version_index", 0)
        variants = result["variants"]
        if 0 <= best_index < len(variants):
            selected_version_id = variants[best_index]["version_id"]
            background_tasks.add_task(
                _schedule_finalize_task,
                request.project_id,
                request.chapter_number,
                selected_version_id,
                current_user.id,
                False,
            )

    return AdvancedGenerateResponse(**result)


@router.post("/chapters/{chapter_number}/finalize", response_model=FinalizeChapterResponse)
async def finalize_chapter(
    chapter_number: int,
    request: FinalizeChapterRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> FinalizeChapterResponse:
    """
    定稿入口：选中版本后触发 FinalizeService 进行记忆更新与快照写入。
    """
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(request.project_id, current_user.id)

    stmt = (
        select(Chapter)
        .options(selectinload(Chapter.versions))
        .where(
            Chapter.project_id == request.project_id,
            Chapter.chapter_number == chapter_number,
        )
    )
    result = await session.execute(stmt)
    chapter = result.scalars().first()
    if not chapter:
        raise HTTPException(status_code=404, detail="章节不存在")

    selected_version = next(
        (v for v in chapter.versions if v.id == request.selected_version_id),
        None,
    )
    if not selected_version or not selected_version.content:
        raise HTTPException(status_code=400, detail="选中的版本不存在或内容为空")

    chapter.selected_version_id = selected_version.id
    chapter.status = ChapterGenerationStatus.SUCCESSFUL.value
    chapter.word_count = len(selected_version.content or "")
    await session.commit()

    finalize_result = await _run_finalize_pipeline(
        session=session,
        project_id=request.project_id,
        chapter=chapter,
        selected_version=selected_version,
        user_id=current_user.id,
        skip_vector_update=request.skip_vector_update or False,
        refresh_memory_layer=True,
    )

    return FinalizeChapterResponse(
        project_id=request.project_id,
        chapter_number=chapter_number,
        selected_version_id=selected_version.id,
        result=finalize_result,
    )


@router.post("/novels/{project_id}/chapters/generate", response_model=NovelProjectSchema)
async def generate_chapter(
    project_id: str,
    request: GenerateChapterRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    """
    兼容旧版前端的章节生成入口。
    旧前端会默认传入较高字数参数，这里将其收敛为稳定、轻量的默认配置，
    让生成入口优先可用、可完成，再保留高级入口给更重的流水线。
    """
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)
    writing_notes_parts: List[str] = []
    if request.writing_notes and request.writing_notes.strip():
        writing_notes_parts.append(request.writing_notes.strip())
    if request.quality_requirements and request.quality_requirements.strip():
        writing_notes_parts.append(f"质量方向：{request.quality_requirements.strip()}")

    flow_config = _build_compat_generate_flow_config(request)

    logger.info(
        "用户 %s 通过兼容入口调用统一流水线: project=%s chapter=%s preset=%s versions=%s request_target=%s request_min=%s effective_target=%s effective_min=%s",
        current_user.id,
        project_id,
        request.chapter_number,
        flow_config["preset"],
        flow_config["versions"],
        request.target_word_count,
        request.min_word_count,
        flow_config["target_word_count"],
        flow_config["min_word_count"],
    )
    outline = await novel_service.get_outline(project_id, request.chapter_number)
    if not outline:
        raise HTTPException(status_code=404, detail="蓝图中未找到对应章节纲要")

    chapter = await novel_service.get_or_create_chapter(project_id, request.chapter_number)
    if chapter.status in _BUSY_CHAPTER_STATUSES:
        if _is_busy_chapter_stale(chapter):
            stale_reason = (
                f"上一轮后台任务超过 {int(CHAPTER_STALE_TIMEOUT.total_seconds() // 60)} 分钟未更新，"
                "已自动终止，请重新生成。"
            )
            logger.warning(
                "Detected stale chapter task, reset to failed so it can be regenerated: "
                "user=%s project=%s chapter=%s status=%s updated_at=%s",
                current_user.id,
                project_id,
                request.chapter_number,
                chapter.status,
                chapter.updated_at,
            )
            await _mark_busy_chapter_failed(session, chapter=chapter, reason=stale_reason)
        else:
            logger.info(
                "Generate chapter skipped because chapter is already busy: user=%s project=%s chapter=%s status=%s",
                current_user.id,
                project_id,
                request.chapter_number,
                chapter.status,
            )
            progress_runtime = build_chapter_progress_snapshot(
                chapter,
                status_value=chapter.status,
                progress_stage=_build_busy_progress_stage(chapter.status),
                progress_message=_build_busy_progress_message(chapter.status),
                allowed_actions=["refresh_status", "cancel_generation"],
            )
            return await _load_project_schema(
                novel_service,
                project_id,
                current_user.id,
                generation_runtime={
                    "queued": True,
                    "generation_mode": flow_config["preset"],
                    "status": "already_generating",
                    "timeout_seconds": _calculate_generation_timeout_seconds(flow_config),
                    **progress_runtime,
                },
            )

    run_id = await _try_claim_chapter_generation(
        session,
        chapter_id=chapter.id,
        chapter_number=chapter.chapter_number,
    )
    if not run_id:
        await session.refresh(chapter)
        logger.info(
            "Generate chapter skipped because chapter claim lost: user=%s project=%s chapter=%s status=%s",
            current_user.id,
            project_id,
            request.chapter_number,
            chapter.status,
        )
        progress_runtime = build_chapter_progress_snapshot(
            chapter,
            status_value=chapter.status,
            progress_stage=_build_busy_progress_stage(chapter.status),
            progress_message=_build_busy_progress_message(chapter.status),
            allowed_actions=["refresh_status", "cancel_generation"],
        )
        return await _load_project_schema(
            novel_service,
            project_id,
            current_user.id,
            generation_runtime={
                "queued": True,
                "generation_mode": flow_config["preset"],
                "status": "already_generating",
                "timeout_seconds": _calculate_generation_timeout_seconds(flow_config),
                **progress_runtime,
            },
        )

    await session.refresh(chapter)

    progress_runtime = build_chapter_progress_snapshot(
        chapter,
        status_value=ChapterGenerationStatus.GENERATING.value,
        progress_stage="queued",
        progress_message="章节已进入后台队列，正在启动快速稳定生成",
        allowed_actions=["refresh_status", "cancel_generation"],
        started_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    background_tasks.add_task(
        _schedule_generate_task,
        project_id,
        request.chapter_number,
        current_user.id,
        "\n\n".join(writing_notes_parts) if writing_notes_parts else None,
        flow_config,
        run_id,
    )

    logger.info(
        "Queued background chapter generation: user=%s project=%s chapter=%s preset=%s",
        current_user.id,
        project_id,
        request.chapter_number,
        flow_config["preset"],
    )
    return await _load_project_schema(
        novel_service,
        project_id,
        current_user.id,
        generation_runtime={
            **progress_runtime,
            "queued": True,
            "generation_mode": flow_config["preset"],
            "version_count": flow_config["versions"],
            "target_word_count": flow_config["target_word_count"],
            "min_word_count": flow_config["min_word_count"],
            "timeout_seconds": _calculate_generation_timeout_seconds(flow_config),
            "status": "queued",
        },
    )


@router.post("/novels/{project_id}/chapters/cancel", response_model=NovelProjectSchema)
async def cancel_chapter_generation(
    project_id: str,
    request: CancelChapterRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)
    chapter = await novel_service.get_or_create_chapter(project_id, request.chapter_number)

    if chapter.status not in _BUSY_CHAPTER_STATUSES:
        logger.info(
            "Skip cancel because chapter is not in busy status: user=%s project=%s chapter=%s status=%s",
            current_user.id,
            project_id,
            request.chapter_number,
            chapter.status,
        )
        return await _load_project_schema(novel_service, project_id, current_user.id)

    cancel_reason = (request.reason or "").strip() or (
        f"后台任务已被手动终止（章节状态：{chapter.status}），请重新生成。"
    )
    logger.warning(
        "Manually cancelled chapter task: user=%s project=%s chapter=%s status=%s reason=%s",
        current_user.id,
        project_id,
        request.chapter_number,
        chapter.status,
        cancel_reason,
    )
    current_run_id = _get_generation_run_id(chapter)
    chapter.real_summary = _build_failed_generation_runtime_state(
        chapter,
        run_id=current_run_id or str(uuid.uuid4()),
        cancel_requested=True,
        reason=cancel_reason,
        level="warning",
    )
    await session.commit()
    await session.refresh(chapter)
    await _mark_busy_chapter_failed(session, chapter=chapter, reason=cancel_reason, run_id=current_run_id)

    return await _load_project_schema(
        novel_service,
        project_id,
        current_user.id,
    )


@router.get("/novels/{project_id}/chapters/{chapter_number}/status", response_model=ChapterSchema)
async def get_chapter_generation_status(
    project_id: str,
    chapter_number: int,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> ChapterSchema:
    novel_service = NovelService(session)
    logger.info("用户 %s 获取项目 %s 第 %s 章轻量状态", current_user.id, project_id, chapter_number)
    return await novel_service.get_chapter_status_schema(project_id, current_user.id, chapter_number)


@router.post("/novels/{project_id}/chapters/select", response_model=NovelProjectSchema)
async def select_chapter_version(
    project_id: str,
    request: SelectVersionRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    novel_service = NovelService(session)
    project = await novel_service.ensure_project_owner(project_id, current_user.id)
    chapter = await novel_service.get_or_create_chapter(project_id, request.chapter_number)

    # 使用 novel_service.select_chapter_version 确保排序一致
    # 该函数会按 created_at 排序并校验索引
    selected_version = await novel_service.select_chapter_version(chapter, request.version_index)

    # 校验内容是否为空
    if not selected_version.content or len(selected_version.content.strip()) == 0:
        # 回滚状态，不标记为 successful
        await session.rollback()
        raise HTTPException(status_code=400, detail="选中的版本内容为空，无法确认为最终版")

    background_tasks.add_task(
        _collect_foreshadowing_async,
        project_id,
        chapter.id,
        request.chapter_number,
        selected_version.content,
    )

    background_tasks.add_task(
        _schedule_finalize_task,
        project_id,
        request.chapter_number,
        selected_version.id,
        current_user.id,
        True,
    )

    return await _load_project_schema(novel_service, project_id, current_user.id)


class DeleteVersionRequest(BaseModel):
    chapter_number: int = Field(..., ge=1, description="章节号")
    version_index: int = Field(..., ge=0, description="要删除的版本索引（0-based）")


@router.post("/novels/{project_id}/chapters/delete-version", response_model=NovelProjectSchema)
async def delete_chapter_version(
    project_id: str,
    request: DeleteVersionRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    """删除章节的某个候选版本"""
    novel_service = NovelService(session)
    project = await novel_service.ensure_project_owner(project_id, current_user.id)
    chapter = await novel_service.get_or_create_chapter(project_id, request.chapter_number)

    # 获取所有版本
    versions = list(chapter.versions) if chapter.versions else []
    if request.version_index < 0 or request.version_index >= len(versions):
        raise HTTPException(status_code=400, detail="版本索引超出范围")

    # 不允许删除当前生效的版本
    version_to_delete = versions[request.version_index]
    selected_version = chapter.selected_version
    if selected_version and selected_version.id == version_to_delete.id:
        raise HTTPException(status_code=400, detail="不能删除当前生效的版本")

    # 至少保留一个版本
    if len(versions) <= 1:
        raise HTTPException(status_code=400, detail="至少需要保留一个版本")

    # 删除版本
    await session.delete(version_to_delete)
    await session.commit()

    logger.info(
        "删除章节版本: project=%s chapter=%s version_index=%s user=%s",
        project_id,
        request.chapter_number,
        request.version_index,
        current_user.id,
    )

    # 重新从数据库获取项目以确保状态同步
    session.expire_all()
    return await _load_project_schema(novel_service, project_id, current_user.id)


@router.post("/novels/{project_id}/chapters/evaluate", response_model=NovelProjectSchema)
async def evaluate_chapter(
    project_id: str,
    request: EvaluateChapterRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    novel_service = NovelService(session)
    prompt_service = PromptService(session)
    llm_service = LLMService(session)

    project = await novel_service.ensure_project_owner(project_id, current_user.id)

    # 获取该章节及其所有版本
    stmt_versions = (
        select(Chapter)
        .options(selectinload(Chapter.versions), selectinload(Chapter.selected_version))
        .where(
            Chapter.project_id == project_id,
            Chapter.chapter_number == request.chapter_number,
        )
    )
    result_versions = await session.execute(stmt_versions)
    chapter = result_versions.scalars().first()

    if not chapter:
        chapter = await novel_service.get_or_create_chapter(project_id, request.chapter_number)
        result_versions = await session.execute(stmt_versions)
        chapter = result_versions.scalars().first()

    if not chapter:
        raise HTTPException(status_code=404, detail="无法定位或创建章节")

    # 获取所有版本（按创建时间排序）
    versions = sorted(list(chapter.versions or []), key=lambda v: v.created_at)
    if not versions:
        raise HTTPException(status_code=400, detail="该章节还没有生成任何版本，无法进行评审")

    # 多版本评审模式
    if request.evaluate_all:
        return await _evaluate_all_versions(
            session=session,
            novel_service=novel_service,
            prompt_service=prompt_service,
            llm_service=llm_service,
            project=project,
            chapter=chapter,
            versions=versions,
            project_id=project_id,
            chapter_number=request.chapter_number,
            user_id=current_user.id,
        )

    # 单版本评审模式（原有逻辑）
    version_to_evaluate = None

    # 情况 A: 指定了版本索引
    if request.version_index is not None:
        if request.version_index < 0 or request.version_index >= len(versions):
            raise HTTPException(status_code=400, detail=f"版本索引 {request.version_index} 无效")
        version_to_evaluate = versions[request.version_index]

    # 情况 B: 未指定索引，优先使用已选版本
    if not version_to_evaluate:
        version_to_evaluate = chapter.selected_version

    # 情况 C: 既没指定也没已选，使用最新版本
    if not version_to_evaluate:
        version_to_evaluate = versions[-1]

    if not version_to_evaluate or not version_to_evaluate.content:
        raise HTTPException(status_code=400, detail="版本内容为空，无法进行评审")

    version_id_for_failure = version_to_evaluate.id if version_to_evaluate else None

    try:
        chapter.status = "evaluating"
        await session.commit()

        eval_prompt = await prompt_service.get_prompt("evaluation")
        if not eval_prompt:
            logger.warning("未配置名为 'evaluation' 的评审提示词，将跳过 AI 评审")
            await novel_service.add_chapter_evaluation(
                chapter=chapter,
                version=version_to_evaluate,
                feedback="未配置评审提示词",
                decision="skipped"
            )
            return await _load_project_schema(novel_service, project_id, current_user.id)

        evaluation_raw = await llm_service.get_llm_response(
            system_prompt=eval_prompt,
            conversation_history=[{"role": "user", "content": version_to_evaluate.content}],
            temperature=0.3,
            user_id=current_user.id,
        )
        evaluation_text = remove_think_tags(evaluation_raw)

        if not evaluation_text or len(evaluation_text.strip()) == 0:
            raise ValueError("评审结果为空")

        await novel_service.add_chapter_evaluation(
            chapter=chapter,
            version=version_to_evaluate,
            feedback=evaluation_text,
            decision="reviewed"
        )
        logger.info("项目 %s 第 %s 章单版本评审成功", project_id, request.chapter_number)
    except Exception as exc:
        logger.exception("项目 %s 第 %s 章评审失败: %s", project_id, request.chapter_number, exc)
        await session.rollback()

        stmt = (
            select(Chapter)
            .where(
                Chapter.project_id == project_id,
                Chapter.chapter_number == request.chapter_number,
            )
        )
        result = await session.execute(stmt)
        chapter = result.scalars().first()

        if chapter:
            from app.models.novel import ChapterEvaluation
            evaluation_record = ChapterEvaluation(
                chapter_id=chapter.id,
                version_id=version_id_for_failure,
                decision="failed",
                feedback=f"评审失败: {str(exc)}",
                score=None
            )
            session.add(evaluation_record)
            chapter.status = "evaluation_failed"
            await session.commit()

        if isinstance(exc, HTTPException):
            raise HTTPException(status_code=exc.status_code, detail=exc.detail)
        raise HTTPException(status_code=500, detail=f"评审失败: {str(exc)}")

    return await _load_project_schema(novel_service, project_id, current_user.id)


async def _evaluate_all_versions(
    session: AsyncSession,
    novel_service: NovelService,
    prompt_service: PromptService,
    llm_service: LLMService,
    project: NovelProject,
    chapter: Chapter,
    versions: List[ChapterVersion],
    project_id: str,
    chapter_number: int,
    user_id: int,
) -> NovelProjectSchema:
    """多版本对比评审"""
    # 过滤掉空内容的版本
    valid_versions = [(i, v) for i, v in enumerate(versions) if v.content and v.content.strip()]
    if not valid_versions:
        raise HTTPException(status_code=400, detail="没有有效内容的版本可供评审")

    try:
        chapter.status = "evaluating"
        await session.commit()

        eval_prompt = await prompt_service.get_prompt("evaluation")
        if not eval_prompt:
            logger.warning("未配置 evaluation 提示词，跳过多版本评审")
            # 回退到单版本评审
            if valid_versions:
                await novel_service.add_chapter_evaluation(
                    chapter=chapter,
                    version=valid_versions[-1][1],
                    feedback="未配置评审提示词",
                    decision="skipped"
                )
            return await _load_project_schema(novel_service, project_id, user_id)

        # 构建多版本评审输入
        project_schema = await novel_service._serialize_project(project)

        # 构建蓝图上下文
        blueprint_context = {
            "world_setting": getattr(project_schema.blueprint, 'world_setting', {}) or {},
            "characters": [],
            "chapter_outline": [],
            "style": getattr(project_schema.blueprint, 'style', '') or '',
            "tone": getattr(project_schema.blueprint, 'tone', '') or '',
        }

        # 添加角色信息
        if hasattr(project_schema.blueprint, 'characters') and project_schema.blueprint.characters:
            for char in project_schema.blueprint.characters:
                blueprint_context["characters"].append({
                    "name": getattr(char, 'name', ''),
                    "personality": getattr(char, 'personality', ''),
                    "background": getattr(char, 'background', ''),
                })

        current_outline_title = None

        # 添加章节大纲
        if hasattr(project_schema.blueprint, 'chapter_outline') and project_schema.blueprint.chapter_outline:
            for outline in project_schema.blueprint.chapter_outline:
                if outline.chapter_number == chapter_number:
                    current_outline_title = outline.title or None
                    blueprint_context["chapter_outline"].append({
                        "chapter_number": outline.chapter_number,
                        "title": outline.title or '',
                        "summary": outline.summary or '',
                    })

        # 构建待评估内容
        versions_content = []
        version_indices = []  # 记录有效版本的编号
        for idx, version in valid_versions:
            content = version.content
            # 截断过长的内容
            if len(content) > 3000:
                content = content[:1800] + "\n...\n" + content[-1200:]
            version_number = idx + 1  # 版本编号从1开始
            versions_content.append({
                "version_index": version_number,
                "style": version.version_label or f"版本{version_number}",
                "content": content,
            })
            version_indices.append(version_number)

        # 构建评审输入
        eval_input = {
            "novel_blueprint": blueprint_context,
            "completed_chapters": [],  # TODO: 可以添加前序章节摘要
            "content_to_evaluate": {
                "chapter_title": current_outline_title or f"第{chapter_number}章",
                "total_versions": len(versions_content),  # 明确告诉AI有多少个版本
                "version_numbers": version_indices,  # 明确列出所有版本编号
                "versions": versions_content,
            }
        }

        eval_input_text = json.dumps(eval_input, ensure_ascii=False, indent=2)

        logger.info(
            "开始多版本评审: project=%s chapter=%s versions=%d",
            project_id, chapter_number, len(valid_versions)
        )

        evaluation_raw = await llm_service.get_llm_response(
            system_prompt=eval_prompt,
            conversation_history=[{"role": "user", "content": eval_input_text}],
            temperature=0.3,
            user_id=user_id,
            timeout=180.0,
        )
        evaluation_text = remove_think_tags(evaluation_raw)

        if not evaluation_text or len(evaluation_text.strip()) == 0:
            raise ValueError("评审结果为空")

        # 尝试解析JSON，提取最佳版本索引
        try:
            cleaned = unwrap_markdown_json(evaluation_text)
            parsed = json.loads(cleaned)

            # 确保评价结果包含所有版本
            if "evaluation" not in parsed:
                parsed["evaluation"] = {}

            # 确保每个有效版本都有评价
            for version_number in version_indices:
                version_key = f"version{version_number}"
                if version_key not in parsed["evaluation"]:
                    logger.warning(
                        "AI评审结果缺少版本 %s 的评价，自动补充默认评价",
                        version_number
                    )
                    parsed["evaluation"][version_key] = {
                        "pros": ["版本内容已生成"],
                        "cons": ["AI未对该版本进行详细评审"],
                        "overall_review": "该版本已生成，但AI评审结果中缺少对此版本的详细评价。"
                    }

            # 记录评审结果中实际包含的版本数
            actual_eval_count = len(parsed.get("evaluation", {}))
            expected_eval_count = len(version_indices)
            logger.info(
                "评审结果版本数: 预期=%d, 实际=%d",
                expected_eval_count,
                actual_eval_count
            )

            # 保存完整的评价结果
            evaluation_text = json.dumps(parsed, ensure_ascii=False, indent=2)

        except (json.JSONDecodeError, Exception) as parse_err:
            logger.warning("评审结果解析失败，使用原始文本: %s", parse_err)

        # 创建评审记录，关联到所有版本
        await novel_service.add_chapter_evaluation(
            chapter=chapter,
            version=valid_versions[0][1],  # 关联到第一个有效版本
            feedback=evaluation_text,
            decision="reviewed_all"
        )

        logger.info(
            "多版本评审成功: project=%s chapter=%s versions=%d",
            project_id, chapter_number, len(valid_versions)
        )

    except Exception as exc:
        logger.exception("多版本评审失败: project=%s chapter=%s error=%s", project_id, chapter_number, exc)
        await session.rollback()

        stmt = select(Chapter).where(
            Chapter.project_id == project_id,
            Chapter.chapter_number == chapter_number,
        )
        result = await session.execute(stmt)
        chapter = result.scalars().first()

        if chapter:
            from app.models.novel import ChapterEvaluation
            evaluation_record = ChapterEvaluation(
                chapter_id=chapter.id,
                version_id=None,
                decision="failed",
                feedback=f"多版本评审失败: {str(exc)}",
                score=None
            )
            session.add(evaluation_record)
            chapter.status = "evaluation_failed"
            await session.commit()

        if isinstance(exc, HTTPException):
            raise HTTPException(status_code=exc.status_code, detail=exc.detail)
        raise HTTPException(status_code=500, detail=f"评审失败: {str(exc)}")

    return await _load_project_schema(novel_service, project_id, user_id)


@router.post("/novels/{project_id}/chapters/update-outline", response_model=NovelProjectSchema)
async def update_chapter_outline(
    project_id: str,
    request: UpdateChapterOutlineRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    outline = await novel_service.get_outline(project_id, request.chapter_number)
    if not outline:
        raise HTTPException(status_code=404, detail="未找到对应章节大纲")

    outline.title = request.title
    outline.summary = request.summary
    await session.commit()

    return await _load_project_schema(novel_service, project_id, current_user.id)


@router.post("/novels/{project_id}/chapters/rewrite-outline", response_model=NovelProjectSchema)
async def rewrite_chapter_outline(
    project_id: str,
    request: RewriteChapterOutlineRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    novel_service = NovelService(session)
    prompt_service = PromptService(session)
    llm_service = LLMService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    outline = await novel_service.get_outline(project_id, request.chapter_number)
    if not outline:
        raise HTTPException(status_code=404, detail="未找到对应章节大纲")

    rewrite_prompt = await prompt_service.get_prompt("outline_rewrite")
    if not rewrite_prompt:
        rewrite_prompt = (
            "你是顶级网文编辑，请在不改变主线剧情的前提下，重写章节标题与章节摘要。"
            "要求：更抓人、更有冲突、更有悬念、可直接用于正文写作。"
            "只输出 JSON：{\"title\":\"...\",\"summary\":\"...\"}"
        )

    direction = (request.direction or "").strip() or "无额外方向"
    user_prompt = f"""
[章节号]
第 {request.chapter_number} 章

[原始标题]
{request.title}

[原始摘要]
{request.summary}

[重写方向]
{direction}

[硬性要求]
1. 标题更有辨识度，建议 8-22 字。
2. 摘要长度 160-360 字，必须包含：本章冲突、角色目标/阻碍、关键转折、章尾钩子。
3. 保持与前后章节连续，不得胡乱跳剧情。
4. 只输出 JSON，不要附加说明。
"""

    try:
        response = await llm_service.get_llm_response(
            system_prompt=rewrite_prompt,
            conversation_history=[{"role": "user", "content": user_prompt}],
            temperature=0.55,
            user_id=current_user.id,
            timeout=240.0,
            response_format=None,
            allow_truncated_response=True,
        )
        cleaned = remove_think_tags(response)
        normalized = unwrap_markdown_json(cleaned).strip()

        parsed = {}
        try:
            parsed = json.loads(normalized)
        except Exception:
            parsed = {}

        rewritten_title = str(parsed.get("title") or request.title).strip()
        rewritten_summary = str(parsed.get("summary") or normalized or request.summary).strip()
        if len("".join(rewritten_summary.split())) < 80:
            rewritten_summary = request.summary
        if not rewritten_title:
            rewritten_title = request.title

        outline.title = rewritten_title
        outline.summary = rewritten_summary
        await session.commit()
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("重写章节摘要失败: project_id=%s chapter=%s error=%s", project_id, request.chapter_number, exc)
        raise HTTPException(status_code=500, detail=f"AI 重写失败: {str(exc)[:160]}")

    return await _load_project_schema(novel_service, project_id, current_user.id)


@router.post("/novels/{project_id}/chapters/delete", response_model=NovelProjectSchema)
async def delete_chapters(
    project_id: str,
    request: DeleteChapterRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    for ch_num in request.chapter_numbers:
        await novel_service.delete_chapter(project_id, ch_num)

    await session.commit()
    return await _load_project_schema(novel_service, project_id, current_user.id)


@router.post("/novels/{project_id}/chapters/outline", response_model=NovelProjectSchema)
async def generate_chapters_outline(
    project_id: str,
    request: GenerateOutlineRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    novel_service = NovelService(session)
    prompt_service = PromptService(session)
    llm_service = LLMService(session)

    project = await novel_service.ensure_project_owner(project_id, current_user.id)

    if request.start_chapter < 1:
        raise HTTPException(status_code=400, detail="start_chapter 必须大于等于 1")
    if request.num_chapters < 1 or request.num_chapters > 1000:
        raise HTTPException(status_code=400, detail="num_chapters 必须在 1-1000 之间")

    target_total_chapters = request.target_total_chapters
    target_total_words = request.target_total_words
    chapter_word_target = request.chapter_word_target

    if target_total_chapters is not None and target_total_chapters < request.start_chapter:
        raise HTTPException(status_code=400, detail="target_total_chapters 不能小于 start_chapter")
    if target_total_words is not None and target_total_words < 10000:
        raise HTTPException(status_code=400, detail="target_total_words 不能小于 10000")
    if chapter_word_target is not None and chapter_word_target < 500:
        raise HTTPException(status_code=400, detail="chapter_word_target 不能小于 500")

    effective_target_total_chapters = (
        target_total_chapters
        if target_total_chapters is not None
        else max(request.start_chapter + request.num_chapters + 30, 60)
    )

    if chapter_word_target is None and target_total_words:
        chapter_word_target = max(500, math.ceil(target_total_words / max(1, effective_target_total_chapters)))

    summary_min_chars = 140
    summary_max_chars = 320

    # 获取蓝图信息
    project_schema = await novel_service._serialize_project(project)
    blueprint_text = json.dumps(project_schema.blueprint.model_dump(), ensure_ascii=False, indent=2)

    existing_outlines_sorted = sorted(project.outlines, key=lambda x: x.chapter_number)
    existing_outline_lines = [
        f"第{o.chapter_number}章 - {o.title}: {o.summary}"
        for o in existing_outlines_sorted
    ]
    base_existing_outlines_text = "\n".join(existing_outline_lines) if existing_outline_lines else "暂无"

    existing_total_words = sum(max(0, int(ch.word_count or 0)) for ch in project.chapters)

    outline_prompt = await prompt_service.get_prompt("outline_generation")
    if not outline_prompt:
        raise HTTPException(status_code=500, detail="未配置大纲生成提示词")

    target_numbers = list(range(request.start_chapter, request.start_chapter + request.num_chapters))
    generated_outline_map: Dict[int, Dict[str, str]] = {}
    max_attempts = 3
    batch_size = min(20, max(1, request.num_chapters))
    pending_numbers = target_numbers[:]

    while pending_numbers:
        batch_numbers = pending_numbers[:batch_size]
        batch_done = False

        for attempt in range(max_attempts):
            missing_numbers = [n for n in batch_numbers if n not in generated_outline_map]
            if not missing_numbers:
                batch_done = True
                break

            generated_outline_lines = [
                f"第{num}章 - {item['title']}: {item['summary']}"
                for num, item in sorted(generated_outline_map.items(), key=lambda x: x[0])
            ]
            existing_outlines_text = base_existing_outlines_text
            if generated_outline_lines:
                existing_outlines_text = f"{base_existing_outlines_text}\n" + "\n".join(generated_outline_lines)

            goal_lines = []
            if target_total_chapters is not None:
                goal_lines.append(f"- 全书目标总章节：{target_total_chapters} 章")
            if target_total_chapters is None:
                goal_lines.append(
                    f"- 全书目标总章节（系统估算，未显式配置）：{effective_target_total_chapters} 章"
                )
            if target_total_words is not None:
                goal_lines.append(f"- 全书目标总字数：约 {target_total_words} 字")
            if chapter_word_target is not None:
                goal_lines.append(f"- 单章目标字数：约 {chapter_word_target} 字")
            if not goal_lines:
                goal_lines.append("- 未显式指定总量目标，请按长篇连载节奏规划")

            near_final_stage = bool(
                max(missing_numbers) >= max(1, effective_target_total_chapters - 2)
            )
            ending_constraint = (
                "可以开始进入收束阶段，但仍需保留合理的情节推进。"
                if near_final_stage
                else "严禁进入终章/大结局式收束，必须保留后续主线与冲突空间。"
            )

            missing_str = "、".join(str(n) for n in missing_numbers)
            retry_hint = ""
            if attempt > 0:
                retry_hint = f"\n[补全重试]\n上一次仍缺少章节：{missing_str}。请严格补全这些章节。"

            prompt_input = f"""
[世界蓝图]
{blueprint_text}

[已有章节大纲]
{existing_outlines_text}

[创作目标]
{chr(10).join(goal_lines)}
- 当前已生成正文字数（估算）：{existing_total_words} 字

[本次任务]
请生成并返回以下章节号的大纲：{missing_str}
{retry_hint}

[硬性要求]
1. 只输出 JSON 对象：{{"chapters":[{{"chapter_number":数字,"title":"标题","summary":"摘要","narrative_phase":"阶段","chapter_role":"职责","suspense_hook":"钩子","emotional_progression":"情绪变化","character_focus":["角色"],"conflict_escalation":["升级点"],"continuity_notes":["承接/递进说明"],"foreshadowing":{{"plant":["伏笔"],"payoff":["回收" ]}}}}]}}
2. chapter_number 必须只来自本次要求的章节号，不得跳号、重号、缺号。
3. 每章 summary 必须具体可写，不得空泛，长度控制在 {summary_min_chars}-{summary_max_chars} 字之间。
4. 每章 summary 必须包含：本章核心冲突、人物目标/阻碍、关键转折、章尾钩子。
5. 每章还必须说明：承接上一章什么、推进长线什么、给下一章留下什么压力。
6. 每章必须有人物焦点与情绪推进，禁止只有事件流水账。
7. {ending_constraint}
8. 与已有章节保持连续，避免剧情断层。
"""

            response = await llm_service.get_llm_response(
                system_prompt=outline_prompt,
                conversation_history=[{"role": "user", "content": prompt_input}],
                temperature=0.7,
                user_id=current_user.id,
                allow_truncated_response=True,
            )

            cleaned = remove_think_tags(response)
            normalized = unwrap_markdown_json(cleaned)
            try:
                data = json.loads(normalized)
            except Exception as exc:
                logger.warning("大纲生成分批第 %s 次解析失败: %s", attempt + 1, exc)
                continue

            chapters_payload = []
            if isinstance(data, dict):
                raw = data.get("chapters", [])
                if isinstance(raw, list):
                    chapters_payload = raw
            elif isinstance(data, list):
                chapters_payload = data

            for item in chapters_payload:
                if not isinstance(item, dict):
                    continue
                chapter_no_raw = item.get("chapter_number")
                try:
                    chapter_no = int(chapter_no_raw)
                except (TypeError, ValueError):
                    continue
                if chapter_no not in missing_numbers:
                    continue

                title = str(item.get("title") or "").strip() or f"第{chapter_no}章"
                summary = str(item.get("summary") or "").strip()
                summary_len = _count_non_whitespace_chars(summary)
                if not summary or summary_len < summary_min_chars:
                    continue
                if (not near_final_stage) and (
                    _looks_like_ending_signal(title) or _looks_like_ending_signal(summary)
                ):
                    logger.info(
                        "skip premature ending outline: project=%s chapter=%s near_final=%s",
                        project_id,
                        chapter_no,
                        near_final_stage,
                    )
                    continue

                generated_outline_map[chapter_no] = {
                    "title": title,
                    "summary": summary,
                    "narrative_phase": str(item.get("narrative_phase") or "").strip() or None,
                    "chapter_role": str(item.get("chapter_role") or "").strip() or None,
                    "suspense_hook": str(item.get("suspense_hook") or "").strip() or None,
                    "emotional_progression": str(item.get("emotional_progression") or "").strip() or None,
                    "character_focus": list(item.get("character_focus") or []),
                    "conflict_escalation": list(item.get("conflict_escalation") or []),
                    "continuity_notes": list(item.get("continuity_notes") or []),
                    "foreshadowing": dict(item.get("foreshadowing") or {}),
                }

            if all(n in generated_outline_map for n in batch_numbers):
                batch_done = True
                break

        if not batch_done:
            batch_missing = [n for n in batch_numbers if n not in generated_outline_map]
            missing_str = "、".join(str(n) for n in batch_missing)
            raise HTTPException(status_code=500, detail=f"大纲生成不完整，缺少章节：{missing_str}，请重试")

        pending_numbers = [n for n in pending_numbers if n not in generated_outline_map]

    for chapter_no in target_numbers:
        item = generated_outline_map[chapter_no]
        await novel_service.update_or_create_outline(
            project_id,
            chapter_no,
            item["title"],
            item["summary"],
            metadata={
                "narrative_phase": item.get("narrative_phase"),
                "chapter_role": item.get("chapter_role"),
                "suspense_hook": item.get("suspense_hook"),
                "emotional_progression": item.get("emotional_progression"),
                "character_focus": item.get("character_focus") or [],
                "conflict_escalation": item.get("conflict_escalation") or [],
                "continuity_notes": item.get("continuity_notes") or [],
                "foreshadowing": item.get("foreshadowing") or {},
            },
        )
    await session.commit()

    return await _load_project_schema(novel_service, project_id, current_user.id)


@router.post("/novels/{project_id}/chapters/edit", response_model=NovelProjectSchema)
async def edit_chapter_content(
    project_id: str,
    request: EditChapterRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    novel_service = NovelService(session)

    await novel_service.ensure_project_owner(project_id, current_user.id)
    await novel_service.get_or_create_chapter(project_id, request.chapter_number)
    chapter_stmt = (
        select(Chapter)
        .options(
            selectinload(Chapter.versions),
            selectinload(Chapter.selected_version),
        )
        .where(
            Chapter.project_id == project_id,
            Chapter.chapter_number == request.chapter_number,
        )
    )
    chapter_result = await session.execute(chapter_stmt)
    chapter = chapter_result.scalars().first()
    if not chapter:
        raise HTTPException(status_code=404, detail="章节不存在")
    
    # 更新内容：优先更新选中版本，否则选最新版本或创建新版本
    target_version = chapter.selected_version
    if not target_version and chapter.versions:
        target_version = sorted(chapter.versions, key=lambda item: item.created_at)[-1]

    if target_version:
        target_version.content = request.content
        if not chapter.selected_version_id:
            chapter.selected_version_id = target_version.id
    else:
        target_version = ChapterVersion(
            chapter_id=chapter.id,
            content=request.content,
            version_label="manual_edit",
        )
        session.add(target_version)
        await session.flush()
        chapter.selected_version_id = target_version.id
    
    chapter.status = "successful"
    chapter.word_count = len(request.content or "")
    await session.commit()

    background_tasks.add_task(
        _refresh_edit_summary_and_ingest,
        project_id,
        request.chapter_number,
        request.content,
        current_user.id,
    )

    return await _load_project_schema(novel_service, project_id, current_user.id)


@router.post("/novels/{project_id}/chapters/edit-fast", response_model=ChapterSchema)
async def edit_chapter_content_fast(
    project_id: str,
    request: EditChapterRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> ChapterSchema:
    novel_service = NovelService(session)

    await novel_service.ensure_project_owner(project_id, current_user.id)
    await novel_service.get_or_create_chapter(project_id, request.chapter_number)
    chapter_stmt = (
        select(Chapter)
        .options(
            selectinload(Chapter.versions),
            selectinload(Chapter.selected_version),
        )
        .where(
            Chapter.project_id == project_id,
            Chapter.chapter_number == request.chapter_number,
        )
    )
    chapter_result = await session.execute(chapter_stmt)
    chapter = chapter_result.scalars().first()
    if not chapter:
        raise HTTPException(status_code=404, detail="章节不存在")

    target_version = chapter.selected_version
    if not target_version and chapter.versions:
        target_version = sorted(chapter.versions, key=lambda item: item.created_at)[-1]

    if target_version:
        target_version.content = request.content
        if not chapter.selected_version_id:
            chapter.selected_version_id = target_version.id
    else:
        target_version = ChapterVersion(
            chapter_id=chapter.id,
            content=request.content,
            version_label="manual_edit",
        )
        session.add(target_version)
        await session.flush()
        chapter.selected_version_id = target_version.id

    chapter.status = "successful"
    chapter.word_count = len(request.content or "")
    await session.commit()

    background_tasks.add_task(
        _refresh_edit_summary_and_ingest,
        project_id,
        request.chapter_number,
        request.content,
        current_user.id,
    )

    return await novel_service.get_chapter_schema_for_admin(project_id, request.chapter_number)
