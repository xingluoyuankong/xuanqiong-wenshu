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
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
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
    OutlineGenerationJobResponse,
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
from ...services.clue_tracker_service import ClueTrackerService
from ...services.knowledge_graph_service import KnowledgeGraphService
from ...services.generation_call_service import GenerationCallPolicy, GenerationJSONDecodeError, call_generation_json, call_generation_text
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
COMPAT_GENERATE_TARGET_WORD_COUNT = 5000
COMPAT_GENERATE_MIN_WORD_COUNT = 4500
# 兼容入口的后台任务会先跑导演脚本，再跑正文生成；质量模式下允许更长处理时间，
# 但 stale 只在确实长时间无心跳时才判定，避免“还在跑”与“已卡死”混淆。
CHAPTER_STALE_TIMEOUT = timedelta(minutes=30)
BACKGROUND_GENERATION_TIMEOUT_MIN_SECONDS = 15 * 60  # 最小15分钟
BACKGROUND_GENERATION_TIMEOUT_MAX_SECONDS = 4 * 60 * 60  # 最大4小时
GENERATION_HEARTBEAT_GRACE_SECONDS = 8 * 60
BACKGROUND_GENERATION_TIMEOUT_DISABLED = os.getenv("XUANQIONG_WENSHU_DISABLE_GENERATION_TIMEOUT", "0").strip().lower() in {"1", "true", "yes", "on"}
_GENERATION_TASK_SEMAPHORE = asyncio.Semaphore(8)
_FINALIZE_TASK_SEMAPHORE = asyncio.Semaphore(4)
_OUTLINE_JOBS: Dict[str, Dict[str, Any]] = {}
_OUTLINE_PROJECT_RUNS: Dict[str, str] = {}
_OUTLINE_JOB_LOCK = asyncio.Lock()
_OUTLINE_JOB_HEARTBEAT_SECONDS = 30
_OUTLINE_ACTIVE_STATUSES = {"queued", "generating", "outline_context", "outline_chapter_skeleton", "outline_rewrite", "saving"}
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


def _review_context_value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _review_context_text(value: Any, *, limit: int = 360) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    elif isinstance(value, (list, tuple, set)):
        text = "；".join(_review_context_text(item, limit=120) for item in value if item)
    elif isinstance(value, dict):
        try:
            text = json.dumps(value, ensure_ascii=False)
        except TypeError:
            text = str(value)
    else:
        text = str(value)
    text = " ".join(text.replace("\r", "\n").split())
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def _review_content_text(value: Any, *, limit: int = 50000) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r", "\n").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def _review_context_real_summary(value: Any) -> str:
    text = _review_context_text(value, limit=420)
    if not text:
        return ""
    if text.startswith("{") and "generation_runtime" in text[:120]:
        return ""
    return text


def _build_completed_chapter_review_context(
    chapters: List[Any],
    current_chapter_number: int,
    *,
    limit: int = 8,
) -> List[Dict[str, Any]]:
    """Build a compact previous-chapter package for multi-version review.

    The reviewer needs cross-chapter anchors, but not the full manuscript. Keep the
    latest previous chapters with summaries and ending anchors so it can judge
    continuity without bloating the review prompt.
    """
    previous: List[Any] = []
    for chapter in chapters or []:
        try:
            chapter_number = int(_review_context_value(chapter, "chapter_number", 0) or 0)
        except (TypeError, ValueError):
            continue
        if chapter_number <= 0 or chapter_number >= current_chapter_number:
            continue
        previous.append(chapter)

    result: List[Dict[str, Any]] = []
    for chapter in sorted(previous, key=lambda item: int(_review_context_value(item, "chapter_number", 0) or 0))[-limit:]:
        raw_content = _review_context_text(_review_context_value(chapter, "content"), limit=20000)
        ending_anchor = _review_context_text(raw_content[-360:] if raw_content else "", limit=360)
        summary = _review_context_text(_review_context_value(chapter, "summary"), limit=360)
        real_summary = _review_context_real_summary(_review_context_value(chapter, "real_summary"))
        continuity_notes = _review_context_value(chapter, "continuity_notes", []) or []
        foreshadowing_tasks = _review_context_value(chapter, "foreshadowing_tasks", {}) or {}
        cast_delta = _review_context_value(chapter, "cast_delta", {}) or {}
        character_focus = _review_context_value(chapter, "character_focus", []) or []
        result.append(
            {
                "chapter_number": int(_review_context_value(chapter, "chapter_number", 0) or 0),
                "title": _review_context_text(_review_context_value(chapter, "title"), limit=80),
                "summary": summary,
                "real_summary": real_summary,
                "ending_anchor": ending_anchor,
                "word_count": int(_review_context_value(chapter, "word_count", 0) or 0),
                "generation_status": str(_review_context_value(chapter, "generation_status", "") or ""),
                "character_focus": character_focus,
                "cast_delta": cast_delta,
                "continuity_notes": continuity_notes,
                "foreshadowing_tasks": foreshadowing_tasks,
            }
        )
    return result


def _review_context_list(value: Any, *, limit: int = 8) -> List[Any]:
    if not value:
        return []
    if isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        items = [value]
    normalized: List[Any] = []
    for item in items[:limit]:
        if isinstance(item, dict):
            normalized.append(item)
        else:
            normalized.append(_review_context_text(item, limit=220))
    return [item for item in normalized if item]


def _review_context_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump()
            return dict(dumped) if isinstance(dumped, dict) else {}
        except Exception:  # noqa: BLE001 - review context should degrade quietly.
            return {}
    if hasattr(value, "dict"):
        try:
            dumped = value.dict()
            return dict(dumped) if isinstance(dumped, dict) else {}
        except Exception:  # noqa: BLE001 - review context should degrade quietly.
            return {}
    return {}


def _build_outline_review_payload(outline: Any) -> Dict[str, Any]:
    metadata = _review_context_dict(_review_context_value(outline, "metadata", {}) or {})

    def pick(key: str, default: Any = None) -> Any:
        value = _review_context_value(outline, key, None)
        if value not in (None, "", [], {}):
            return value
        return metadata.get(key, default)

    return {
        "chapter_number": int(_review_context_value(outline, "chapter_number", 0) or 0),
        "title": _review_context_text(_review_context_value(outline, "title"), limit=100),
        "summary": _review_context_text(_review_context_value(outline, "summary"), limit=520),
        "chapter_role": _review_context_text(pick("chapter_role"), limit=260),
        "suspense_hook": _review_context_text(pick("suspense_hook"), limit=220),
        "emotional_progression": _review_context_text(pick("emotional_progression"), limit=220),
        "character_focus": _review_context_list(pick("character_focus"), limit=8),
        "cast_delta": _review_context_dict(pick("cast_delta", {})),
        "conflict_escalation": _review_context_list(pick("conflict_escalation"), limit=8),
        "continuity_notes": _review_context_list(pick("continuity_notes"), limit=8),
        "foreshadowing_tasks": _review_context_dict(pick("foreshadowing_tasks", {})),
        "payoff_window": _review_context_text(pick("payoff_window"), limit=180),
    }


def _build_blueprint_review_context(
    project_schema: NovelProjectSchema,
    current_chapter_number: int,
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    blueprint = getattr(project_schema, "blueprint", None)
    if not blueprint:
        return {
            "title": "",
            "genre": "",
            "style": "",
            "tone": "",
            "world_setting": {},
            "characters": [],
            "nearby_outlines": [],
        }, None

    characters: List[Dict[str, Any]] = []
    for raw in list(getattr(blueprint, "characters", []) or [])[:24]:
        if not isinstance(raw, dict):
            continue
        characters.append(
            {
                "name": _review_context_text(raw.get("name"), limit=80),
                "role": _review_context_text(raw.get("role") or raw.get("identity"), limit=120),
                "personality": _review_context_text(raw.get("personality"), limit=220),
                "motivation": _review_context_text(raw.get("motivation") or raw.get("goal"), limit=220),
                "background": _review_context_text(raw.get("background"), limit=260),
                "faction": _review_context_text(raw.get("faction") or raw.get("affiliation"), limit=120),
            }
        )

    current_outline: Optional[Dict[str, Any]] = None
    nearby_outlines: List[Dict[str, Any]] = []
    for outline in list(getattr(blueprint, "chapter_outline", []) or []):
        try:
            number = int(_review_context_value(outline, "chapter_number", 0) or 0)
        except (TypeError, ValueError):
            continue
        payload = _build_outline_review_payload(outline)
        if number == current_chapter_number:
            current_outline = payload
        if current_chapter_number - 2 <= number <= current_chapter_number + 2:
            nearby_outlines.append(payload)

    context = {
        "title": _review_context_text(getattr(blueprint, "title", ""), limit=100),
        "genre": _review_context_text(getattr(blueprint, "genre", ""), limit=100),
        "style": _review_context_text(getattr(blueprint, "style", ""), limit=160),
        "tone": _review_context_text(getattr(blueprint, "tone", ""), limit=160),
        "one_sentence_summary": _review_context_text(getattr(blueprint, "one_sentence_summary", ""), limit=260),
        "full_synopsis": _review_context_text(getattr(blueprint, "full_synopsis", ""), limit=700),
        "world_setting": _review_context_dict(getattr(blueprint, "world_setting", {}) or {}),
        "characters": characters,
        "nearby_outlines": nearby_outlines,
        "foreshadowing_system": _review_context_list(getattr(blueprint, "foreshadowing_system", []) or [], limit=12),
    }
    return context, current_outline


def _build_version_review_content_payload(version: Any, *, long_threshold: int = 5200) -> Dict[str, Any]:
    content = _review_content_text(_review_context_value(version, "content"), limit=50000)
    total_chars = len(content)
    payload: Dict[str, Any] = {
        "version_id": _review_context_value(version, "id"),
        "style": _review_context_text(
            _review_context_value(version, "version_label")
            or _review_context_value(version, "style")
            or "draft",
            limit=100,
        ),
        "word_count": int(_review_context_value(version, "word_count", 0) or 0),
        "total_chars": total_chars,
        "metadata": _review_context_dict(_review_context_value(version, "metadata", {}) or {}),
    }
    if total_chars <= long_threshold:
        payload["content"] = content
    else:
        middle_start = max(total_chars // 2 - 900, 0)
        head = content[:2200]
        middle = content[middle_start: middle_start + 1800]
        tail = content[-1800:]
        payload["content_excerpt"] = {
            "head": head,
            "middle": middle,
            "tail": tail,
            "note": "Long chapter excerpt keeps head/middle/tail so the reviewer can judge continuity, density and ending pressure.",
        }
        payload["content"] = f"[head]\n{head}\n\n[middle]\n{middle}\n\n[tail]\n{tail}"
    return payload


def _build_single_chapter_evaluation_input(
    project_schema: NovelProjectSchema,
    chapter: Chapter,
    version: ChapterVersion,
    chapter_number: int,
) -> str:
    blueprint_context, current_outline = _build_blueprint_review_context(project_schema, chapter_number)
    chapter_title = (
        (current_outline or {}).get("title")
        or _review_context_text(_review_context_value(chapter, "title"), limit=100)
        or f"Chapter {chapter_number}"
    )
    payload = {
        "review_mode": "single_version_cross_chapter_quality_review",
        "review_rules": [
            "Judge this as a formal candidate chapter, not an isolated prose fragment.",
            "Use completed_chapters ending anchors, current_outline, character_focus, cast_delta and foreshadowing_tasks to check cross-chapter continuity.",
            "Prioritize event density, dialogue that changes the situation, visible consequences, character state changes and ending pressure.",
            "If the chapter needs repair, propose local anchored patches first; do not recommend whole-chapter rewrite unless the user explicitly confirms a structural rewrite.",
        ],
        "novel_blueprint": blueprint_context,
        "completed_chapters": _build_completed_chapter_review_context(
            list(getattr(project_schema, "chapters", []) or []),
            chapter_number,
        ),
        "current_chapter_outline": current_outline,
        "content_to_evaluate": {
            "chapter_number": chapter_number,
            "chapter_title": chapter_title,
            "generation_status": str(_review_context_value(chapter, "generation_status", "") or ""),
            "version": _build_version_review_content_payload(version),
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _resolve_outline_generation_goal(
    *,
    start_chapter: int,
    num_chapters: int,
    target_total_chapters: Optional[int],
    target_total_words: Optional[int],
    chapter_word_target: Optional[int],
) -> Tuple[int, Optional[int]]:
    if target_total_chapters is not None and target_total_chapters < start_chapter:
        raise HTTPException(status_code=400, detail="target_total_chapters 不能小于 start_chapter")
    if target_total_words is not None and target_total_words < 1000:
        raise HTTPException(status_code=400, detail="target_total_words 不能小于 1000")
    if chapter_word_target is not None and chapter_word_target < 500:
        raise HTTPException(status_code=400, detail="chapter_word_target 不能小于 500")

    effective_target_total_chapters = (
        target_total_chapters
        if target_total_chapters is not None
        else max(start_chapter + num_chapters + 30, 60)
    )

    if chapter_word_target is None and target_total_words:
        chapter_word_target = max(500, math.ceil(target_total_words / max(1, effective_target_total_chapters)))

    return effective_target_total_chapters, chapter_word_target


async def _resolve_chapter_version(
    session: AsyncSession,
    chapter: Chapter,
    *,
    version_id: Optional[int] = None,
    version_index: Optional[int] = None,
    require_content: bool = True,
) -> ChapterVersion:
    stmt = (
        select(ChapterVersion)
        .where(ChapterVersion.chapter_id == chapter.id)
        .order_by(ChapterVersion.created_at, ChapterVersion.id)
    )
    result = await session.execute(stmt)
    versions = list(result.scalars().all())

    selected: Optional[ChapterVersion] = None
    if version_id is not None:
        selected = next((version for version in versions if version.id == version_id), None)
        if selected is None:
            raise HTTPException(status_code=400, detail="版本不存在或不属于当前章节，请刷新后重试")
    else:
        if version_index is None:
            raise HTTPException(status_code=400, detail="缺少版本 ID 或版本索引")
        if version_index < 0 or version_index >= len(versions):
            raise HTTPException(status_code=400, detail="版本索引无效，请刷新后重试")
        logger.warning(
            "使用兼容 version_index 解析版本: project=%s chapter=%s version_index=%s",
            chapter.project_id,
            chapter.chapter_number,
            version_index,
        )
        selected = versions[version_index]

    if require_content and not (selected.content or "").strip():
        raise HTTPException(status_code=400, detail="选中的版本内容为空，无法执行该操作")
    return selected


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
    allowed_actions: Optional[List[str]] = None,
    stage: str = "failed",
) -> str:
    payload = _load_generation_runtime_state(chapter)
    runtime = payload.get("generation_runtime") if isinstance(payload.get("generation_runtime"), dict) else {}
    now_iso = datetime.now(timezone.utc).isoformat()
    events = runtime.get("events") if isinstance(runtime.get("events"), list) else []
    # 质量门拦截但候选已保存时用 evaluation_failed 语义，前端可区分"可恢复评审"与"彻底失败"
    normalized_stage = stage if stage in {"failed", "evaluation_failed"} else "failed"
    event = {
        "at": now_iso,
        "stage": normalized_stage,
        "level": level,
        "message": reason,
    }
    normalized_runtime: Dict[str, Any] = {
        **runtime,
        "run_id": run_id,
        "cancel_requested": cancel_requested,
        "reason": reason,
        "progress_stage": normalized_stage,
        "progress_message": reason,
        "progress_percent": 100,
        "allowed_actions": allowed_actions or ["refresh_status", "retry_generation"],
        "started_at": runtime.get("started_at") or now_iso,
        "updated_at": now_iso,
        "heartbeat_at": now_iso,
        "estimated_remaining_seconds": 0,
        "chapter_number": chapter.chapter_number,
        "events": [*events[-199:], event],
    }
    return json.dumps({"generation_runtime": normalized_runtime}, ensure_ascii=False)


def _truncate_runtime_text(value: Any, limit: int = 420) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _append_generation_runtime_event(
    chapter: Optional[Chapter],
    *,
    stage: str,
    message: str,
    level: str = "info",
    event_kind: str = "ledger",
    title: Optional[str] = None,
    summary: Optional[str] = None,
    progress_percent: Optional[int] = None,
    content_preview: Optional[str] = None,
    metrics: Optional[Dict[str, Any]] = None,
    artifact_refs: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    if chapter is None:
        return
    payload = _load_generation_runtime_state(chapter)
    runtime = payload.get("generation_runtime") if isinstance(payload.get("generation_runtime"), dict) else {}
    now_iso = datetime.now(timezone.utc).isoformat()
    events = runtime.get("events") if isinstance(runtime.get("events"), list) else []
    event: Dict[str, Any] = {
        "at": now_iso,
        "stage": stage,
        "level": level,
        "kind": event_kind,
        "message": message,
        "title": title or message,
        "summary": summary or message,
    }
    if content_preview:
        event["content_preview"] = _truncate_runtime_text(content_preview)
    if metrics:
        event["metrics"] = metrics
    if artifact_refs:
        event["artifact_refs"] = artifact_refs
    if metadata:
        event["metadata"] = metadata

    normalized_runtime: Dict[str, Any] = {
        **runtime,
        "progress_stage": stage,
        "progress_message": message,
        "progress_percent": progress_percent if progress_percent is not None else runtime.get("progress_percent", 100),
        "updated_at": now_iso,
        "heartbeat_at": now_iso,
        "chapter_number": chapter.chapter_number,
        "events": [*events[-199:], event],
    }
    chapter.real_summary = json.dumps({"generation_runtime": normalized_runtime}, ensure_ascii=False)


def _build_memory_layer_runtime_summary(memory_result: Dict[str, Any]) -> str:
    if not isinstance(memory_result, dict):
        return "记忆层已尝试同步，结果结构异常，保留原文并等待后续重试。"

    dynamic_names = [
        str(name).strip()
        for name in (memory_result.get("dynamic_character_names") or [])
        if str(name).strip()
    ]
    pieces: List[str] = []
    character_count = int(memory_result.get("character_states_updated") or 0)
    timeline_count = int(memory_result.get("timeline_events_added") or 0)
    causal_count = int(memory_result.get("causal_chains_added") or 0)
    dynamic_count = int(memory_result.get("dynamic_characters_created") or len(dynamic_names) or 0)

    if character_count:
        pieces.append(f"角色状态 {character_count} 条")
    if timeline_count:
        pieces.append(f"时间线事件 {timeline_count} 条")
    if causal_count:
        pieces.append(f"因果链 {causal_count} 条")
    if dynamic_count:
        shown_names = "、".join(dynamic_names[:5]) if dynamic_names else f"{dynamic_count} 个新角色"
        suffix = "等" if len(dynamic_names) > 5 else ""
        pieces.append(f"动态角色入池：{shown_names}{suffix}")

    if not pieces:
        return "记忆层已检查本章，没有发现必须新增的角色状态、时间线或因果账本。"
    return "已写入" + "，".join(pieces) + "。"


def _build_ledger_sync_runtime_summary(clue_result: Dict[str, Any], graph_result: Dict[str, Any]) -> str:
    pieces: List[str] = []
    if isinstance(clue_result, dict):
        created = int(clue_result.get("created") or 0)
        updated = int(clue_result.get("updated") or 0)
        if created:
            pieces.append(f"线索新增 {created} 条")
        if updated:
            pieces.append(f"线索更新 {updated} 条")
    if isinstance(graph_result, dict):
        created_nodes = int(graph_result.get("created_nodes") or 0)
        created_edges = int(graph_result.get("created_edges") or 0)
        removed_nodes = int(graph_result.get("removed_nodes") or 0)
        removed_edges = int(graph_result.get("removed_edges") or 0)
        if created_nodes:
            pieces.append(f"图谱新增角色节点 {created_nodes} 个")
        if created_edges:
            pieces.append(f"图谱新增关系边 {created_edges} 条")
        if removed_nodes:
            pieces.append(f"清理过期节点 {removed_nodes} 个")
        if removed_edges:
            pieces.append(f"清理过期关系 {removed_edges} 条")
    if not pieces:
        return "线索与知识图谱已完成检查，本章没有需要新增或清理的账本项。"
    return "，".join(pieces) + "。"


def _build_finalized_runtime_summary(result: Dict[str, Any]) -> str:
    degraded: List[str] = []
    for key, label in (
        ("memory_layer", "记忆层"),
        ("foreshadowing_closure", "伏笔闭环"),
        ("ledger_sync", "线索/图谱同步"),
    ):
        value = result.get(key)
        if isinstance(value, dict) and value.get("success") is False:
            degraded.append(label)
    if degraded:
        return "正文已确认；" + "、".join(degraded) + "有降级警告，已保留原文并写入可重试的账本提示。"
    return "正文已确认；记忆、伏笔、线索和知识图谱同步结果已写入运行日志。"


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


async def _mark_busy_chapter_evaluation_failed(
    session: AsyncSession,
    *,
    chapter: Chapter,
    reason: str,
    run_id: Optional[str] = None,
    decision: str = "evaluation_failed",
) -> None:
    if run_id and _get_generation_run_id(chapter) != run_id:
        logger.info(
            "Skip marking chapter evaluation failed because run_id mismatched: project=%s chapter=%s expected=%s actual=%s",
            chapter.project_id,
            chapter.chapter_number,
            run_id,
            _get_generation_run_id(chapter),
        )
        return
    version_count = 0
    try:
        count_result = await session.execute(
            select(func.count(ChapterVersion.id)).where(ChapterVersion.chapter_id == chapter.id)
        )
        version_count = int(count_result.scalar_one() or 0)
    except Exception as exc:  # noqa: BLE001 - action hint only
        logger.warning(
            "Failed to count blocked candidate versions: project=%s chapter=%s error=%s",
            chapter.project_id,
            chapter.chapter_number,
            exc,
        )
    chapter.status = ChapterGenerationStatus.EVALUATION_FAILED.value
    chapter.real_summary = _build_failed_generation_runtime_state(
        chapter,
        run_id=run_id or _get_generation_run_id(chapter) or "unknown",
        cancel_requested=_is_generation_cancel_requested(chapter, run_id),
        reason=reason,
        allowed_actions=(
            ["refresh_status", "confirm_version", "review_versions", "retry_generation", "view_error"]
            if version_count > 0
            else ["refresh_status", "retry_generation", "view_error"]
        ),
        stage="evaluation_failed",
    )
    session.add(
        ChapterEvaluation(
            chapter_id=chapter.id,
            version_id=chapter.selected_version_id,
            decision=decision,
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


def _resolve_quality_candidate_version_count(*, preset: str, target_word_count: int) -> int:
    normalized_preset = str(preset or "basic").strip() or "basic"
    target = max(500, int(target_word_count or 0))

    # basic 预设：快速优先，始终 1 个版本
    if normalized_preset == "basic":
        return 1

    # ultimate 预设：质量优先，至少 2 个版本
    if normalized_preset == "ultimate":
        if target >= 10000:
            return 4
        if target >= 6500:
            return 3
        return 2

    # longform / enhanced 预设：按字数推断，但不少于 2
    if target >= 10000:
        return 4
    if target >= 6500:
        return 3
    if target >= 4500:
        return 2
    if target >= 2800:
        return 2
    # 短章节但非 basic：仍给 1 版本，避免短文本多版本浪费
    return COMPAT_GENERATE_VERSION_COUNT


def _compose_generation_writing_notes(
    writing_notes: Optional[str],
    quality_requirements: Optional[str] = None,
) -> Optional[str]:
    notes_parts: List[str] = [
        "基础质量底线：优先保证章节推进、对话攻防、逻辑递进、关系变化；描写必须服务冲突，禁止空转景物、空转心理和解释性旁白。",
        "本章必须至少完成一个清晰的局势升级或局部反转，并通过至少两轮有效对话攻防或同等级动作博弈推动局势。",
        "正文要尽量一开始就进入本章目标与阻碍，不能把大半篇幅耗在纯氛围、纯感受、纯回忆上。",
        "如果字数较长，优先把篇幅写在场景执行、动作过程、对话压力、因果后果和章末传压上，不要靠描述性补字数。",
        "单章字数契约：短章可以紧凑，但 4500 字以上必须有多场景推进；7000 字以上必须用场景组承载事件密度，10000 字以上要保持整章融合感，不能写成松散片段合集。",
        "结尾必须留下与当前主线直接相关的压力、误会、危险、悬念或回收后的新问题，不能平着收束。",
    ]
    if writing_notes and writing_notes.strip():
        notes_parts.append(writing_notes.strip())
    if quality_requirements and quality_requirements.strip():
        notes_parts.append(f"质量方向：{quality_requirements.strip()}")
    return "\n\n".join(notes_parts) if notes_parts else None


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


def _build_advanced_background_flow_config(request: AdvancedGenerateRequest) -> Dict[str, Any]:
    """Normalize advanced generation config for the background chapter task."""
    raw_config = request.flow_config.model_dump(exclude_none=True)
    target_word_count = max(
        500,
        _coerce_positive_int(raw_config.get("target_word_count"), COMPAT_GENERATE_TARGET_WORD_COUNT),
    )
    min_word_count = max(
        200,
        _coerce_positive_int(raw_config.get("min_word_count"), COMPAT_GENERATE_MIN_WORD_COUNT),
    )
    if min_word_count > target_word_count:
        min_word_count = target_word_count
    draft_contract = PipelineOrchestrator._resolve_chapter_draft_contract(target_word_count, min_word_count)

    preset = str(raw_config.get("preset") or "basic").strip() or "basic"
    default_versions = _resolve_quality_candidate_version_count(
        preset=preset,
        target_word_count=target_word_count,
    )
    versions = min(
        MAX_GENERATED_VERSION_COUNT,
        max(MIN_GENERATED_VERSION_COUNT, _coerce_positive_int(raw_config.get("versions"), default_versions)),
    )

    config: Dict[str, Any] = {
        "preset": preset,
        "versions": versions,
        "target_word_count": target_word_count,
        "min_word_count": min_word_count,
        "chapter_draft_contract": draft_contract,
        "generation_strategy": draft_contract["generation_strategy"],
        "enforce_min_word_count": True,
        "advanced_background_mode": True,
        "async_finalize": False,
    }

    optional_bool_keys = (
        "enable_preview",
        "enable_optimizer",
        "enable_consistency",
        "enable_enrichment",
        "enable_constitution",
        "enable_persona",
        "enable_six_dimension",
        "enable_reader_sim",
        "enable_self_critique",
        "enable_memory",
        "enable_rag",
        "enable_foreshadowing",
        "enable_faction",
        "allow_truncated_response",
    )
    for key in optional_bool_keys:
        if raw_config.get(key) is not None:
            config[key] = bool(raw_config.get(key))

    if raw_config.get("rag_mode"):
        config["rag_mode"] = raw_config.get("rag_mode")
    if raw_config.get("max_enrich_iterations") is not None:
        config["max_enrich_iterations"] = min(8, max(1, _coerce_positive_int(raw_config.get("max_enrich_iterations"), 1)))

    return config

def _build_compat_generate_flow_config(request: GenerateChapterRequest) -> Dict[str, Any]:
    explicit_target = request.target_word_count is not None
    explicit_min = request.min_word_count is not None
    # Respect explicit user word-count choices. The previous compat path silently
    # raised short chapters (for example 700/350) to 3000/3000, which made quick
    # generation unexpectedly expensive and look stuck in generate_variants.
    target_word_count = _coerce_positive_int(
        request.target_word_count,
        COMPAT_GENERATE_TARGET_WORD_COUNT,
    )
    min_word_count = _coerce_positive_int(
        request.min_word_count,
        COMPAT_GENERATE_MIN_WORD_COUNT,
    )

    # Keep only a defensive floor that matches PipelineOrchestrator._resolve_config.
    target_word_count = max(500, target_word_count)
    min_word_count = max(200, min_word_count)
    if min_word_count > target_word_count:
        min_word_count = target_word_count

    requires_word_enforcement = explicit_target or explicit_min
    requested_target = max(target_word_count, min_word_count)
    if requested_target >= 6500:
        enrich_iterations = 8 if requested_target >= 10000 else 6
    elif requested_target >= 4500:
        enrich_iterations = 5
    elif requested_target >= 1200 and requires_word_enforcement:
        enrich_iterations = 3
    else:
        enrich_iterations = 1

    # 尊重前端显式传入的 preset；未传时保持原有字数自动推断逻辑
    explicit_preset = str(getattr(request, "preset", None) or "").strip()
    is_short_chapter = requested_target < 1200
    high_quality_longform = requested_target >= 4500
    if explicit_preset in {"basic", "enhanced", "longform", "ultimate"}:
        preset = explicit_preset
    elif is_short_chapter:
        preset = "basic"
    else:
        preset = "ultimate" if high_quality_longform else "longform"
    version_count = _resolve_quality_candidate_version_count(
        preset=preset,
        target_word_count=requested_target,
    )
    draft_contract = PipelineOrchestrator._resolve_chapter_draft_contract(target_word_count, min_word_count)

    config: Dict[str, Any] = {
        "preset": preset,
        "versions": version_count,
        "allow_truncated_response": False,
        "target_word_count": target_word_count,
        "min_word_count": min_word_count,
        "chapter_draft_contract": draft_contract,
        "generation_strategy": draft_contract["generation_strategy"],
        "max_enrich_iterations": enrich_iterations,
        "enforce_min_word_count": True,
        "compat_short_chapter_mode": is_short_chapter,
        "explicit_target_word_count": explicit_target,
        "explicit_min_word_count": explicit_min,
    }
    if is_short_chapter:
        config.update(
            {
                "enable_preview": False,
                "enable_optimizer": False,
                "enable_consistency": False,
                "enable_enrichment": False,
                "enable_constitution": False,
                "enable_persona": False,
                "enable_six_dimension": False,
                "enable_reader_sim": False,
                "enable_self_critique": False,
                "enable_memory": False,
                "enable_rag": True,
                "rag_mode": "simple",
                "enable_foreshadowing": False,
                "enable_faction": False,
            }
        )

    return config


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


def _outline_job_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _outline_job_error(
    code: str,
    message: str,
    *,
    detail: Any = None,
    retryable: bool = True,
) -> Dict[str, Any]:
    if detail is None:
        detail_text = None
    elif isinstance(detail, str):
        detail_text = detail[:800]
    else:
        try:
            detail_text = json.dumps(detail, ensure_ascii=False, default=str)[:800]
        except TypeError:
            detail_text = str(detail)[:800]
    return {
        "code": code,
        "message": message,
        "detail": detail_text,
        "retryable": retryable,
    }


def _outline_stage_title(stage: str) -> str:
    return {
        "queued": "任务排队",
        "outline_context": "上下文审计",
        "outline_chapter_skeleton": "章节职责与骨架",
        "outline_rewrite": "局部大纲重写",
        "saving": "保存章节大纲",
        "successful": "章节大纲完成",
        "failed": "章节大纲失败",
        "cancelled": "任务已取消",
        "idle": "暂无任务",
    }.get(stage, "章节大纲任务")


def _outline_runtime_event(
    stage: str,
    message: str,
    *,
    status: str = "",
    level: str = "info",
) -> Dict[str, Any]:
    return {
        "at": _outline_job_now_iso(),
        "stage": stage,
        "level": level,
        "kind": "status",
        "title": _outline_stage_title(stage),
        "summary": message,
        "message": message,
        "metrics": {
            "status": status or stage,
            "progress_stage": stage,
        },
    }


def _normalize_outline_job_payload(job: Dict[str, Any]) -> Dict[str, Any]:
    events = job.get("events") if isinstance(job.get("events"), list) else []
    return {
        "run_id": str(job.get("run_id") or ""),
        "project_id": str(job.get("project_id") or ""),
        "status": str(job.get("status") or "idle"),
        "progress_stage": str(job.get("progress_stage") or job.get("status") or "idle"),
        "progress_message": str(job.get("progress_message") or ""),
        "started_at": job.get("started_at"),
        "updated_at": job.get("updated_at"),
        "project": job.get("project"),
        "events": [event for event in events[-200:] if isinstance(event, dict)],
        "error": job.get("error"),
    }


def _serialize_outline_job(job: Dict[str, Any]) -> OutlineGenerationJobResponse:
    return OutlineGenerationJobResponse(**_normalize_outline_job_payload(job))


async def _set_outline_job_state(run_id: str, **updates: Any) -> Dict[str, Any]:
    async with _OUTLINE_JOB_LOCK:
        job = _OUTLINE_JOBS.get(run_id)
        if not job:
            job = {"run_id": run_id, "status": "idle", "progress_stage": "idle"}
            _OUTLINE_JOBS[run_id] = job
        if job.get("status") == "cancelled" and updates.get("status") != "cancelled":
            return dict(job)
        previous_stage = str(job.get("progress_stage") or job.get("status") or "idle")
        previous_message = str(job.get("progress_message") or "")
        previous_status = str(job.get("status") or "idle")
        job.update(updates)
        job["updated_at"] = _outline_job_now_iso()
        stage = str(job.get("progress_stage") or job.get("status") or "idle")
        message = str(job.get("progress_message") or "")
        status = str(job.get("status") or stage)
        if stage != previous_stage or message != previous_message or status != previous_status:
            events = job.get("events") if isinstance(job.get("events"), list) else []
            level = "error" if status == "failed" else "warning" if status == "cancelled" else "info"
            job["events"] = [*events[-199:], _outline_runtime_event(stage, message, status=status, level=level)]
        return dict(job)


async def _run_outline_generation_job(
    run_id: str,
    project_id: str,
    user_id: int,
    request_payload: Dict[str, Any],
) -> None:
    async def heartbeat() -> None:
        max_beats = 720  # 6 hours max (720 beats * 30s = 21600s)
        beat_count = 0
        while beat_count < max_beats:
            await asyncio.sleep(_OUTLINE_JOB_HEARTBEAT_SECONDS)
            beat_count += 1
            async with _OUTLINE_JOB_LOCK:
                job = _OUTLINE_JOBS.get(run_id)
                if not job or job.get("status") not in _OUTLINE_ACTIVE_STATUSES:
                    return
                stage = str(job.get("progress_stage") or "outline_chapter_skeleton")
                message = str(job.get("progress_message") or "章节大纲生成中")
            await _set_outline_job_state(
                run_id,
                status="generating",
                progress_stage=stage,
                progress_message=message,
            )
        logger.warning("Outline job heartbeat maxed out: run_id=%s, job assumed timed out", run_id)

    heartbeat_task = asyncio.create_task(heartbeat())
    try:
        state = await _set_outline_job_state(
            run_id,
            status="generating",
            progress_stage="outline_context",
            progress_message="正在整理蓝图、已有章节和目标篇幅",
        )
        if state.get("status") == "cancelled":
            return
        request = GenerateOutlineRequest(**request_payload)
        current_user = UserInDB(id=user_id, username=f"outline-job-{user_id}", email=None, hashed_password="")
        async with AsyncSessionLocal() as job_session:
            state = await _set_outline_job_state(
                run_id,
                status="generating",
                progress_stage="outline_chapter_skeleton",
                progress_message="正在分批生成可执行章节大纲",
            )
            if state.get("status") == "cancelled":
                return
            project_schema = await generate_chapters_outline(
                project_id=project_id,
                request=request,
                session=job_session,
                current_user=current_user,
            )

        async with _OUTLINE_JOB_LOCK:
            current = _OUTLINE_JOBS.get(run_id)
            if current and current.get("status") == "cancelled":
                return

        await _set_outline_job_state(
            run_id,
            status="saving",
            progress_stage="saving",
            progress_message="正在保存章节大纲并更新项目状态",
        )
        await _set_outline_job_state(
            run_id,
            status="successful",
            progress_stage="successful",
            progress_message="章节大纲生成完成",
            project=project_schema,
            error=None,
        )
    except HTTPException as exc:
        logger.warning(
            "章节大纲后台生成失败: project=%s run_id=%s status=%s detail=%s",
            project_id,
            run_id,
            exc.status_code,
            exc.detail,
        )
        await _set_outline_job_state(
            run_id,
            status="failed",
            progress_stage="failed",
            progress_message="章节大纲生成失败",
            error=_outline_job_error(
                "outline_generation_failed",
                "章节大纲生成失败",
                detail=exc.detail,
                retryable=exc.status_code >= 500 or exc.status_code in {408, 409, 429},
            ),
        )
    except Exception as exc:  # noqa: BLE001 - background task must surface failures
        logger.exception("章节大纲后台生成异常: project=%s run_id=%s", project_id, run_id)
        await _set_outline_job_state(
            run_id,
            status="failed",
            progress_stage="failed",
            progress_message="章节大纲生成失败",
            error=_outline_job_error(
                "outline_generation_failed",
                "章节大纲生成失败",
                detail=exc,
                retryable=True,
            ),
        )
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass


async def _run_outline_rewrite_job(
    run_id: str,
    project_id: str,
    user_id: int,
    request_payload: Dict[str, Any],
) -> None:
    try:
        state = await _set_outline_job_state(
            run_id,
            status="outline_rewrite",
            progress_stage="outline_rewrite",
            progress_message="正在重写目标章节大纲并保护前后承接",
        )
        if state.get("status") == "cancelled":
            return
        request = RewriteChapterOutlineRequest(**request_payload)
        current_user = UserInDB(id=user_id, username=f"outline-rewrite-job-{user_id}", email=None, hashed_password="")
        async with AsyncSessionLocal() as job_session:
            project_schema = await rewrite_chapter_outline(
                project_id=project_id,
                request=request,
                session=job_session,
                current_user=current_user,
            )

        async with _OUTLINE_JOB_LOCK:
            current = _OUTLINE_JOBS.get(run_id)
            if current and current.get("status") == "cancelled":
                return

        await _set_outline_job_state(
            run_id,
            status="saving",
            progress_stage="saving",
            progress_message="正在保存重写后的章节大纲",
        )
        await _set_outline_job_state(
            run_id,
            status="successful",
            progress_stage="successful",
            progress_message="章节大纲重写完成",
            project=project_schema,
            error=None,
        )
    except HTTPException as exc:
        logger.warning(
            "章节大纲后台重写失败: project=%s run_id=%s status=%s detail=%s",
            project_id,
            run_id,
            exc.status_code,
            exc.detail,
        )
        await _set_outline_job_state(
            run_id,
            status="failed",
            progress_stage="failed",
            progress_message="章节大纲重写失败",
            error=_outline_job_error(
                "outline_rewrite_failed",
                "章节大纲重写失败",
                detail=exc.detail,
                retryable=exc.status_code >= 500 or exc.status_code in {408, 409, 429},
            ),
        )
    except Exception as exc:  # noqa: BLE001 - background task must surface failures
        logger.exception("章节大纲后台重写异常: project=%s run_id=%s", project_id, run_id)
        await _set_outline_job_state(
            run_id,
            status="failed",
            progress_stage="failed",
            progress_message="章节大纲重写失败",
            error=_outline_job_error("outline_rewrite_failed", "章节大纲重写失败", detail=exc, retryable=True),
        )


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


def _normalize_outline_string_list(value: Any, *, limit: int = 5) -> List[str]:
    if isinstance(value, list):
        raw_items = value
    elif value:
        raw_items = [value]
    else:
        return []

    items: List[str] = []
    for raw_item in raw_items:
        text = str(raw_item or "").strip()
        if text and text not in items:
            items.append(text)
        if len(items) >= limit:
            break
    return items


def _outline_contains_any(text: str, keywords: Tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _validate_outline_item_executability(
    item: Dict[str, Any],
    *,
    chapter_no: int,
    summary_min_chars: int,
    summary_max_chars: int,
) -> Tuple[bool, List[str], Dict[str, Any]]:
    title = str(item.get("title") or "").strip() or f"第{chapter_no}章"
    summary = str(item.get("summary") or "").strip()
    summary_len = _count_non_whitespace_chars(summary)
    chapter_role = str(item.get("chapter_role") or "").strip()
    suspense_hook = str(item.get("suspense_hook") or "").strip()
    emotional_progression = str(item.get("emotional_progression") or "").strip()
    narrative_phase = str(item.get("narrative_phase") or "").strip()
    character_focus = _normalize_outline_string_list(item.get("character_focus"), limit=4)
    cast_delta = item.get("cast_delta") if isinstance(item.get("cast_delta"), dict) else {}
    conflict_escalation = _normalize_outline_string_list(item.get("conflict_escalation"), limit=5)
    continuity_notes = _normalize_outline_string_list(item.get("continuity_notes"), limit=5)

    raw_foreshadowing = item.get("foreshadowing")
    foreshadowing = raw_foreshadowing if isinstance(raw_foreshadowing, dict) else {}
    raw_foreshadowing_tasks = item.get("foreshadowing_tasks")
    foreshadowing_tasks = raw_foreshadowing_tasks if isinstance(raw_foreshadowing_tasks, dict) else {}
    payoff_window = str(item.get("payoff_window") or "").strip()

    goal_markers = ("想", "要", "必须", "决定", "试图", "寻找", "确认", "逼问", "救", "夺", "查", "进入")
    conflict_markers = ("却", "但", "阻", "拒绝", "威胁", "反制", "冲突", "误会", "压迫", "遭到", "敌")
    turn_markers = ("突然", "发现", "意识到", "反转", "转而", "没想到", "谁知", "暴露", "失控", "代价", "局势")
    hook_markers = ("章末", "结尾", "留下", "逼近", "线索", "悬念", "危险", "下一章", "门外", "消息", "后果")
    summary_signal_count = sum(
        [
            _outline_contains_any(summary, goal_markers),
            _outline_contains_any(summary, conflict_markers),
            _outline_contains_any(summary, turn_markers),
            _outline_contains_any(summary, hook_markers),
        ]
    )

    reasons: List[str] = []
    if not summary or summary_len < summary_min_chars:
        reasons.append(f"summary_too_short<{summary_min_chars}")
    if summary_len > max(summary_max_chars + 120, summary_min_chars):
        reasons.append(f"summary_too_loose>{summary_max_chars + 120}")
    if summary_signal_count < 2:
        reasons.append("summary_lacks_goal_conflict_turn_hook")
    if _count_non_whitespace_chars(chapter_role) < 10:
        reasons.append("chapter_role_weak")
    if _count_non_whitespace_chars(suspense_hook) < 8:
        reasons.append("suspense_hook_weak")
    if _count_non_whitespace_chars(emotional_progression) < 6:
        reasons.append("emotional_progression_missing")
    if not character_focus:
        reasons.append("character_focus_missing")
    if not conflict_escalation or all(_count_non_whitespace_chars(text) < 6 for text in conflict_escalation):
        reasons.append("conflict_escalation_missing")
    if not continuity_notes or all(_count_non_whitespace_chars(text) < 8 for text in continuity_notes):
        reasons.append("continuity_notes_missing")

    normalized = {
        "title": title,
        "summary": summary,
        "narrative_phase": narrative_phase or None,
        "chapter_role": chapter_role or None,
        "suspense_hook": suspense_hook or None,
        "emotional_progression": emotional_progression or None,
        "character_focus": character_focus,
        "cast_delta": cast_delta,
        "conflict_escalation": conflict_escalation,
        "continuity_notes": continuity_notes,
        "foreshadowing": foreshadowing,
        "foreshadowing_tasks": foreshadowing_tasks,
        "payoff_window": payoff_window or None,
    }
    return not reasons, reasons, normalized


OUTLINE_EXECUTION_METADATA_KEYS = (
    "narrative_phase",
    "chapter_role",
    "suspense_hook",
    "emotional_progression",
    "character_focus",
    "cast_delta",
    "conflict_escalation",
    "continuity_notes",
    "foreshadowing",
    "foreshadowing_tasks",
    "payoff_window",
)


def _outline_item_json_schema(*, require_chapter_number: bool = False) -> Dict[str, Any]:
    string_array = {"type": "array", "items": {"type": "string"}}
    cast_delta_schema = {
        "type": "object",
        "required": ["new", "returning", "exit_or_absent", "faction_roles"],
        "properties": {
            "new": string_array,
            "returning": string_array,
            "exit_or_absent": string_array,
            "faction_roles": string_array,
        },
    }
    foreshadowing_schema = {
        "type": "object",
        "required": ["plant", "payoff"],
        "properties": {
            "plant": string_array,
            "payoff": string_array,
        },
    }
    foreshadowing_tasks_schema = {
        "type": "object",
        "required": ["plant", "reinforce", "payoff", "avoid_forgetting"],
        "properties": {
            "plant": string_array,
            "reinforce": string_array,
            "payoff": string_array,
            "avoid_forgetting": string_array,
        },
    }
    required = [
        "title",
        "summary",
        "narrative_phase",
        "chapter_role",
        "suspense_hook",
        "emotional_progression",
        "character_focus",
        "cast_delta",
        "conflict_escalation",
        "continuity_notes",
        "foreshadowing",
        "foreshadowing_tasks",
        "payoff_window",
    ]
    properties: Dict[str, Any] = {
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "narrative_phase": {"type": "string"},
        "chapter_role": {"type": "string"},
        "suspense_hook": {"type": "string"},
        "emotional_progression": {"type": "string"},
        "character_focus": string_array,
        "cast_delta": cast_delta_schema,
        "conflict_escalation": string_array,
        "continuity_notes": string_array,
        "foreshadowing": foreshadowing_schema,
        "foreshadowing_tasks": foreshadowing_tasks_schema,
        "payoff_window": {"type": "string"},
    }
    if require_chapter_number:
        required = ["chapter_number", *required]
        properties["chapter_number"] = {"type": "integer"}
    return {"type": "object", "required": required, "properties": properties}


def _outline_batch_json_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "required": ["chapters"],
        "properties": {
            "chapters": {
                "type": "array",
                "items": _outline_item_json_schema(require_chapter_number=True),
            }
        },
    }


def _unwrap_outline_payload_root(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    chapter_payload = payload.get("chapter")
    if isinstance(chapter_payload, dict):
        return {**payload, **chapter_payload}
    return payload


def _build_rewritten_outline_metadata(
    *,
    parsed_payload: Dict[str, Any],
    existing_metadata: Optional[Dict[str, Any]],
    chapter_no: int,
    title: str,
    summary: str,
    direction: str,
) -> Dict[str, Any]:
    """Merge a rewritten outline back into the existing execution metadata."""

    old_metadata = dict(existing_metadata or {})
    parsed = _unwrap_outline_payload_root(parsed_payload)
    merged_for_gate = {
        **old_metadata,
        **parsed,
        "title": title,
        "summary": summary,
    }
    valid, rejection_reasons, normalized = _validate_outline_item_executability(
        merged_for_gate,
        chapter_no=chapter_no,
        summary_min_chars=120,
        summary_max_chars=420,
    )

    metadata = dict(old_metadata)
    for key in OUTLINE_EXECUTION_METADATA_KEYS:
        value = normalized.get(key)
        if value not in (None, "", [], {}):
            metadata[key] = value

    metadata["outline_quality"] = {
        **(old_metadata.get("outline_quality") if isinstance(old_metadata.get("outline_quality"), dict) else {}),
        "rewrite_executability_gate_passed": valid,
        "rewrite_rejection_reasons": rejection_reasons,
        "rewrite_checked_at": datetime.now(timezone.utc).isoformat(),
    }
    metadata["last_rewrite"] = {
        "direction": direction,
        "preserved_existing_metadata": bool(old_metadata),
        "updated_fields": [
            key
            for key in OUTLINE_EXECUTION_METADATA_KEYS
            if key in parsed and parsed.get(key) not in (None, "", [], {})
        ],
    }
    return metadata


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
                chapter_number=chapter.chapter_number,
                selected_version=selected_version,
                user_id=user_id,
                skip_vector_update=skip_vector_update,
                refresh_memory_layer=True,
                chapter=chapter,
            )
    except Exception as exc:
        logger.warning(
            "后台定稿任务失败（已跳过）: project=%s chapter=%s error=%s",
            project_id,
            chapter_number,
            exc,
        )
        await _record_background_finalize_failure(
            project_id=project_id,
            chapter_number=chapter_number,
            error=exc,
        )


async def _record_background_finalize_failure(
    *,
    project_id: str,
    chapter_number: int,
    error: Exception,
) -> None:
    """Mark async finalize as degraded so the UI does not wait forever."""
    try:
        async with AsyncSessionLocal() as session:
            stmt = select(Chapter).where(
                Chapter.project_id == project_id,
                Chapter.chapter_number == chapter_number,
            )
            result = await session.execute(stmt)
            chapter = result.scalars().first()
            if not chapter:
                return
            _append_generation_runtime_event(
                chapter,
                stage="finalized",
                message="定稿正文已保存，账本同步降级",
                level="warning",
                progress_percent=100,
                event_kind="ledger",
                title="定稿降级完成",
                summary="后台账本更新遇到异常，已保留选中正文；可稍后重试账本同步。",
                metadata={"error": str(error)[:300]},
            )
            await session.commit()
    except Exception as record_exc:
        logger.warning(
            "记录后台定稿降级状态失败: project=%s chapter=%s error=%s",
            project_id,
            chapter_number,
            record_exc,
        )


async def _refresh_chapter_runtime_state(session: AsyncSession, chapter: Optional[Chapter]) -> None:
    if chapter is None:
        return
    refresh = getattr(session, "refresh", None)
    if not callable(refresh):
        return
    try:
        await refresh(chapter, attribute_names=["real_summary", "chapter_number"])
    except TypeError:
        await refresh(chapter)
    except Exception:
        logger.debug("刷新章节运行态失败，继续使用当前内存值", exc_info=True)




async def _run_finalize_pipeline(
    *,
    session: AsyncSession,
    project_id: str,
    chapter_number: int,
    selected_version: ChapterVersion,
    user_id: int,
    skip_vector_update: bool = False,
    refresh_memory_layer: bool = True,
    chapter: Optional[Chapter] = None,
) -> Dict[str, Any]:
    llm_service = LLMService(session)
    selected_content = getattr(selected_version, "content", None) or ""
    selected_version_id = getattr(selected_version, "id", None)
    selected_chapter_id = getattr(selected_version, "chapter_id", None)

    if chapter is not None:
        _append_generation_runtime_event(
            chapter,
            stage="finalize",
            message="正在确认定稿并更新故事账本",
            progress_percent=98,
            event_kind="ledger",
            title="定稿闭环开始",
            summary="将同步章节摘要、角色状态、伏笔/线索和知识图谱。",
            content_preview=selected_content,
            metrics={"selected_version_id": selected_version_id},
        )
        await session.commit()

    vector_store = None
    if settings.vector_store_enabled and not skip_vector_update:
        try:
            vector_store = VectorStoreService()
        except RuntimeError as exc:
            logger.warning("向量库初始化失败，跳过定稿写入: %s", exc)

    finalize_service = FinalizeService(session, llm_service, vector_store)
    finalize_result = await finalize_service.finalize_chapter(
        project_id=project_id,
        chapter_number=chapter_number,
        chapter_text=selected_content,
        user_id=user_id,
        skip_vector_update=skip_vector_update,
    )
    result: Dict[str, Any] = {"finalize": finalize_result}

    if chapter is not None:
        await _refresh_chapter_runtime_state(session, chapter)
        finalize_success = bool(finalize_result.get("success", True)) if isinstance(finalize_result, dict) else True
        _append_generation_runtime_event(
            chapter,
            stage="finalize",
            message="定稿摘要和章节快照已处理" if finalize_success else "定稿摘要或章节快照处理降级",
            level="info" if finalize_success else "warning",
            progress_percent=98,
            event_kind="ledger",
            title="定稿快照完成" if finalize_success else "定稿快照降级",
            summary="全局摘要、剧情线和章节快照已写入或尝试写入。",
            metrics=(finalize_result.get("updates") if isinstance(finalize_result, dict) else None),
            content_preview=selected_content,
        )
        await session.commit()

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
            chapter_number=chapter_number,
            chapter_content=selected_content,
            character_names=character_names,
            user_id=user_id,
        )
        result["memory_layer"] = memory_result
        if chapter is not None:
            await _refresh_chapter_runtime_state(session, chapter)
            memory_summary = _build_memory_layer_runtime_summary(memory_result)
            _append_generation_runtime_event(
                chapter,
                stage="ledger_memory",
                message="角色状态、时间线和因果账本更新完成",
                progress_percent=99,
                event_kind="ledger",
                title="记忆层更新完成",
                summary=memory_summary,
                metrics=memory_result,
                artifact_refs={
                    "dynamic_character_names": memory_result.get("dynamic_character_names", []),
                    "dynamic_characters_created": memory_result.get("dynamic_characters_created", 0),
                },
            )
            await session.commit()
    except Exception as exc:
        await session.rollback()
        logger.warning(
            "章节 %s 记忆层更新失败，已保留定稿结果: %s",
            chapter_number,
            exc,
        )
        result["memory_layer"] = {
            "success": False,
            "error": str(exc)[:200],
        }
        if chapter is not None:
            await _refresh_chapter_runtime_state(session, chapter)
            _append_generation_runtime_event(
                chapter,
                stage="ledger_memory",
                message="记忆层更新降级，定稿正文已保留",
                level="warning",
                progress_percent=99,
                event_kind="ledger",
                title="记忆层更新降级",
                summary="角色状态或时间线抽取失败，后续可重试账本同步。",
                metadata={"error": str(exc)[:300]},
            )
            await session.commit()

    try:
        foreshadowing_service = ForeshadowingService(session)
        foreshadowing_result = await foreshadowing_service.auto_resolve_from_chapter(
            project_id=project_id,
            chapter_id=selected_chapter_id,
            chapter_number=chapter_number,
            chapter_content=selected_content,
        )
        auto_collect_result = await foreshadowing_service.auto_collect_from_chapter(
            project_id=project_id,
            chapter_id=selected_chapter_id,
            chapter_number=chapter_number,
            chapter_content=selected_content,
            max_items=6,
        )
        total_chapters = await session.scalar(
            select(func.count(ChapterOutline.id)).where(ChapterOutline.project_id == project_id)
        )
        reminders = await foreshadowing_service.check_and_create_reminders(
            project_id=project_id,
            current_chapter_number=chapter_number,
            total_chapters=max(int(total_chapters or chapter_number), chapter_number),
        )
        await session.commit()
        result["foreshadowing_closure"] = {
            **foreshadowing_result,
            "auto_collected": auto_collect_result,
            "active_reminders_checked": len(reminders),
        }
        if chapter is not None:
            await _refresh_chapter_runtime_state(session, chapter)
            _append_generation_runtime_event(
                chapter,
                stage="ledger_foreshadowing",
                message="伏笔回收和新伏笔抽取完成",
                progress_percent=99,
                event_kind="ledger",
                title="伏笔闭环完成",
                summary=(
                    f"回收 {foreshadowing_result.get('resolved', 0)} 条，强化 "
                    f"{foreshadowing_result.get('reinforced', 0)} 条，新增 "
                    f"{auto_collect_result.get('created', 0) if isinstance(auto_collect_result, dict) else 0} 条。"
                ),
                metrics=result["foreshadowing_closure"],
                artifact_refs={
                    "resolution_ids": foreshadowing_result.get("resolution_ids", []),
                    "reinforced_ids": foreshadowing_result.get("reinforced_ids", []),
                    "unresolved_due_ids": foreshadowing_result.get("unresolved_due_ids", []),
                },
            )
            await session.commit()
    except Exception as exc:
        await session.rollback()
        logger.warning(
            "章节 %s 伏笔写后闭环失败，已保留定稿结果: %s",
            chapter_number,
            exc,
        )
        result["foreshadowing_closure"] = {
            "success": False,
            "error": str(exc)[:200],
        }
        if chapter is not None:
            await _refresh_chapter_runtime_state(session, chapter)
            _append_generation_runtime_event(
                chapter,
                stage="ledger_foreshadowing",
                message="伏笔闭环降级，定稿正文已保留",
                level="warning",
                progress_percent=99,
                event_kind="ledger",
                title="伏笔闭环降级",
                summary="伏笔回收或新伏笔抽取失败，后续可重试账本同步。",
                metadata={"error": str(exc)[:300]},
            )
            await session.commit()

    try:
        clue_result = await ClueTrackerService(session).sync_from_foreshadowings(project_id)
        graph_result = await KnowledgeGraphService(session).sync_from_story_memory(project_id)
        result["ledger_sync"] = {
            "clues": clue_result,
            "knowledge_graph": graph_result,
        }
        if chapter is not None:
            await _refresh_chapter_runtime_state(session, chapter)
            ledger_summary = _build_ledger_sync_runtime_summary(
                clue_result if isinstance(clue_result, dict) else {},
                graph_result if isinstance(graph_result, dict) else {},
            )
            _append_generation_runtime_event(
                chapter,
                stage="ledger_graph",
                message="线索和知识图谱同步完成",
                progress_percent=100,
                event_kind="ledger",
                title="线索/图谱同步完成",
                summary=ledger_summary,
                metrics={
                    "clues": clue_result if isinstance(clue_result, dict) else {},
                    "knowledge_graph": graph_result if isinstance(graph_result, dict) else {},
                },
            )
            await session.commit()
    except Exception as exc:
        await session.rollback()
        logger.warning(
            "章节 %s 线索/知识图谱同步失败，已保留定稿结果: %s",
            chapter_number,
            exc,
        )
        result["ledger_sync"] = {
            "success": False,
            "error": str(exc)[:200],
        }
        if chapter is not None:
            await _refresh_chapter_runtime_state(session, chapter)
            _append_generation_runtime_event(
                chapter,
                stage="ledger_graph",
                message="线索/知识图谱同步降级，定稿正文已保留",
                level="warning",
                progress_percent=100,
                event_kind="ledger",
                title="线索/图谱同步降级",
                summary="线索或知识图谱同步失败，章节正文和其他账本结果不受影响。",
                metadata={"error": str(exc)[:300]},
            )
            await session.commit()

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

    if chapter is not None:
        await _refresh_chapter_runtime_state(session, chapter)
        memory_layer_result = result.get("memory_layer") if isinstance(result.get("memory_layer"), dict) else {}
        _append_generation_runtime_event(
            chapter,
            stage="finalized",
            message="定稿闭环完成",
            progress_percent=100,
            event_kind="ledger",
            title="定稿闭环完成",
            summary=_build_finalized_runtime_summary(result),
            metrics={
                "memory_success": bool((result.get("memory_layer") or {}).get("success", True)),
                "foreshadowing_success": bool((result.get("foreshadowing_closure") or {}).get("success", True)),
                "ledger_sync_success": bool((result.get("ledger_sync") or {}).get("success", True)),
                "dynamic_characters_created": memory_layer_result.get("dynamic_characters_created", 0),
                "dynamic_character_names": memory_layer_result.get("dynamic_character_names", []),
            },
        )
        await session.commit()

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
                with LLMService.daily_limit_scope(f"chapter:{project_id}:{chapter_number}:{run_id}"):
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
                # ---- auto-select best version ----
                try:
                    async with AsyncSessionLocal() as auto_sess:
                        from sqlalchemy import select as sql_select
                        from sqlalchemy.orm import selectinload
                        stmt = sql_select(Chapter).options(selectinload(Chapter.versions)).where(
                            Chapter.project_id == project_id,
                            Chapter.chapter_number == chapter_number,
                        )
                        result = await auto_sess.execute(stmt)
                        chapter_obj = result.scalars().first()
                        if chapter_obj and chapter_obj.versions:
                            best = max(
                                (v for v in chapter_obj.versions if v.content),
                                key=lambda v: len(v.content or ""),
                                default=None,
                            )
                            if best:
                                chapter_obj.selected_version_id = best.id
                                chapter_obj.status = "successful"
                                chapter_obj.word_count = len(best.content or "")
                                await auto_sess.commit()
                                logger.info(
                                    "Auto-selected best version %s: project=%s chapter=%s words=%s",
                                    best.id, project_id, chapter_number, chapter_obj.word_count,
                                )
                except Exception as _e:
                    logger.debug("Auto-select skipped: %s", _e)
                # -----------------------------------
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
                        error_code = str(detail.get("code") or "").strip()
                        message = detail.get("message") or str(exc)
                        hint = detail.get("hint")
                        current_word_count = detail.get("current_word_count")
                        min_word_count = detail.get("min_word_count")
                        target_word_count = detail.get("target_word_count")
                        stage = detail.get("stage")
                        quality_gate = detail.get("quality_gate") if isinstance(detail.get("quality_gate"), dict) else None
                        reason_parts = [str(message).strip()]
                        if current_word_count is not None and min_word_count is not None and target_word_count is not None:
                            reason_parts.append(
                                f"当前字数 {current_word_count}，最低要求 {min_word_count}，目标字数 {target_word_count}。"
                            )
                        if stage:
                            reason_parts.append(f"失败阶段：{stage}。")
                        if quality_gate and quality_gate.get("blockers"):
                            blocker_messages = [
                                str(item.get("message") or "").strip()
                                for item in (quality_gate.get("blockers") or [])[:4]
                                if isinstance(item, dict) and str(item.get("message") or "").strip()
                            ]
                            if blocker_messages:
                                reason_parts.append("质量闸门拦截：" + "；".join(blocker_messages))
                        if hint:
                            reason_parts.append(str(hint).strip())
                        reason = " ".join(part for part in reason_parts if part)
                    else:
                        error_code = ""
                        reason = f"生成失败：{str(exc)[:200]}"
                    if error_code == "CHAPTER_QUALITY_GATE_FAILED":
                        await _mark_busy_chapter_evaluation_failed(
                            session,
                            chapter=chapter,
                            reason=reason,
                            run_id=run_id,
                            decision="quality_gate_failed",
                        )
                    else:
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


@router.post("/advanced/generate", response_model=NovelProjectSchema)
async def advanced_generate_chapter(
    request: AdvancedGenerateRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    """
    高级写作入口：不再同步等待完整流水线，统一进入后台任务状态机。

    历史版本在此处直接 await PipelineOrchestrator.generate_chapter()，
    会导致 HTTP 请求长时间挂起，且缺少 busy/stale/cancel/status 保护。
    现在高级配置仍被保留，但执行方式与普通章节生成入口一致：立即返回
    项目快照和 generation_runtime，前端/调用方通过章节 status 接口跟踪结果。
    """
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(request.project_id, current_user.id)
    outline = await novel_service.get_outline(request.project_id, request.chapter_number)
    if not outline:
        logger.warning("章节纲要缺失，自动创建基础纲要: project=%s chapter=%s", project_id, request.chapter_number)
        try:
            outline = await novel_service.update_or_create_outline(
                project_id,
                request.chapter_number,
                f"第{request.chapter_number}章",
                "自动生成章节纲要",
            )
        except Exception as exc:
            logger.error("自动创建章节纲要失败: project=%s chapter=%s error=%s", project_id, request.chapter_number, exc)
            raise HTTPException(status_code=404, detail="蓝图中未找到对应章节纲要且自动创建失败")

    flow_config = _build_advanced_background_flow_config(request)
    chapter = await novel_service.get_or_create_chapter(request.project_id, request.chapter_number)
    if chapter.status in _BUSY_CHAPTER_STATUSES:
        if _is_busy_chapter_stale(chapter):
            stale_reason = (
                f"上一轮高级生成任务超过 {int(CHAPTER_STALE_TIMEOUT.total_seconds() // 60)} 分钟未更新，"
                "已自动终止，请重新生成。"
            )
            await _mark_busy_chapter_failed(session, chapter=chapter, reason=stale_reason)
        else:
            progress_runtime = build_chapter_progress_snapshot(
                chapter,
                status_value=chapter.status,
                progress_stage=_build_busy_progress_stage(chapter.status),
                progress_message=_build_busy_progress_message(chapter.status),
                allowed_actions=["refresh_status", "cancel_generation"],
            )
            return await _load_project_schema(
                novel_service,
                request.project_id,
                current_user.id,
                generation_runtime={
                    "queued": True,
                    "generation_mode": flow_config["preset"],
                    "status": "already_generating",
                    "advanced_background_mode": True,
                    "timeout_seconds": _calculate_generation_timeout_seconds(flow_config),
                    **progress_runtime,
                },
            )

    run_id = await _try_claim_chapter_generation(
        session,
        chapter_id=chapter.id,
        chapter_number=request.chapter_number,
    )
    if not run_id:
        await session.refresh(chapter)
        progress_runtime = build_chapter_progress_snapshot(
            chapter,
            status_value=chapter.status,
            progress_stage=_build_busy_progress_stage(chapter.status),
            progress_message=_build_busy_progress_message(chapter.status),
            allowed_actions=["refresh_status", "cancel_generation"],
        )
        return await _load_project_schema(
            novel_service,
            request.project_id,
            current_user.id,
            generation_runtime={
                "queued": True,
                "generation_mode": flow_config["preset"],
                "status": "already_generating",
                "advanced_background_mode": True,
                "timeout_seconds": _calculate_generation_timeout_seconds(flow_config),
                **progress_runtime,
            },
        )

    await session.refresh(chapter)
    progress_runtime = build_chapter_progress_snapshot(
        chapter,
        status_value=ChapterGenerationStatus.GENERATING.value,
        progress_stage="queued",
        progress_message="高级章节生成已进入后台队列，正在启动可观测流水线",
        allowed_actions=["refresh_status", "cancel_generation"],
        started_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    composed_writing_notes = _compose_generation_writing_notes(
        request.writing_notes,
        getattr(request, "quality_requirements", None),
    )

    background_tasks.add_task(
        _schedule_generate_task,
        request.project_id,
        request.chapter_number,
        current_user.id,
        composed_writing_notes,
        flow_config,
        run_id,
    )

    logger.info(
        "Queued advanced background chapter generation: user=%s project=%s chapter=%s preset=%s versions=%s",
        current_user.id,
        request.project_id,
        request.chapter_number,
        flow_config["preset"],
        flow_config["versions"],
    )
    return await _load_project_schema(
        novel_service,
        request.project_id,
        current_user.id,
        generation_runtime={
            **progress_runtime,
            "queued": True,
            "generation_mode": flow_config["preset"],
            "version_count": flow_config["versions"],
            "target_word_count": flow_config["target_word_count"],
            "min_word_count": flow_config["min_word_count"],
            "chapter_draft_contract": flow_config.get("chapter_draft_contract"),
            "generation_strategy": flow_config.get("generation_strategy"),
            "timeout_seconds": _calculate_generation_timeout_seconds(flow_config),
            "status": "queued",
            "advanced_background_mode": True,
        },
    )

@router.post("/chapters/{chapter_number}/finalize", response_model=FinalizeChapterResponse)
async def finalize_chapter(
    chapter_number: int,
    request: FinalizeChapterRequest,
    background_tasks: BackgroundTasks,
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

    if request.async_finalize is not False:
        _append_generation_runtime_event(
            chapter,
            stage="finalize",
            message="定稿账本后台同步已排队",
            progress_percent=98,
            event_kind="ledger",
            title="定稿后台同步排队",
            summary="正文已确认，角色、伏笔、线索和知识图谱会在后台继续同步；可在章节状态或运行日志里查看进度。",
            content_preview=selected_version.content,
            metrics={"selected_version_id": selected_version.id, "async_finalize": True},
        )
        await session.commit()
        background_tasks.add_task(
            _schedule_finalize_task,
            request.project_id,
            chapter.chapter_number,
            selected_version.id,
            current_user.id,
            request.skip_vector_update or False,
        )
        return FinalizeChapterResponse(
            project_id=request.project_id,
            chapter_number=chapter_number,
            selected_version_id=selected_version.id,
            result={
                "queued": True,
                "async_finalize": True,
                "message": "定稿正文已保存，账本同步已进入后台任务。",
                "status_url": f"/api/writer/novels/{request.project_id}/chapters/{chapter_number}/status",
            },
        )

    finalize_result = await _run_finalize_pipeline(
        session=session,
        project_id=request.project_id,
        chapter_number=chapter.chapter_number,
        selected_version=selected_version,
        user_id=current_user.id,
        skip_vector_update=request.skip_vector_update or False,
        refresh_memory_layer=True,
        chapter=chapter,
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
    保留用户显式传入的字数与质量方向，并统一接入当前章节生成质量基线。
    """
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)
    writing_notes_parts: List[str] = [
        "基础质量底线：优先保证章级推进、对话博弈、逻辑递进、关系变化；描写必须服务冲突，禁止空转景物、空转心理和解释性旁白。",
        "本章必须至少完成一个清晰的局势升级或局部反转，并通过至少两轮有效对话攻防或同等级动作博弈推动局势。",
        "结尾必须留下与当前主线直接相关的压力、误会、危险、悬念或回收后的新问题，不能平着收束。"
    ]
    if request.writing_notes and request.writing_notes.strip():
        writing_notes_parts.append(request.writing_notes.strip())
    if request.quality_requirements and request.quality_requirements.strip():
        writing_notes_parts.append(f"质量方向：{request.quality_requirements.strip()}")

    composed_writing_notes = _compose_generation_writing_notes(
        request.writing_notes,
        request.quality_requirements,
    )
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
        logger.warning("章节纲要缺失，自动创建基础纲要: project=%s chapter=%s", project_id, request.chapter_number)
        try:
            outline = await novel_service.update_or_create_outline(
                project_id,
                request.chapter_number,
                f"第{request.chapter_number}章",
                "自动生成章节纲要",
            )
        except Exception as exc:
            logger.error("自动创建章节纲要失败: project=%s chapter=%s error=%s", project_id, request.chapter_number, exc)
            raise HTTPException(status_code=404, detail="蓝图中未找到对应章节纲要且自动创建失败")

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
        chapter_number=request.chapter_number,
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
        composed_writing_notes,
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
            "chapter_draft_contract": flow_config.get("chapter_draft_contract"),
            "generation_strategy": flow_config.get("generation_strategy"),
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

    selected_version = await _resolve_chapter_version(
        session,
        chapter,
        version_id=request.version_id,
        version_index=request.version_index,
        require_content=True,
    )
    chapter.selected_version_id = selected_version.id
    chapter.selected_version = selected_version
    chapter.status = ChapterGenerationStatus.SUCCESSFUL.value
    chapter.word_count = len(selected_version.content or "")
    await novel_service._touch_project(project_id, auto_commit=False)
    await session.commit()

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
    version_index: Optional[int] = Field(default=None, ge=0, description="兼容旧前端的版本索引（0-based）")
    version_id: Optional[int] = Field(default=None, description="稳定版本 ID，优先于 version_index")


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

    versions = sorted(list(chapter.versions or []), key=lambda item: (item.created_at, item.id))
    version_to_delete = await _resolve_chapter_version(
        session,
        chapter,
        version_id=request.version_id,
        version_index=request.version_index,
        require_content=False,
    )

    # 不允许删除当前生效的版本
    selected_version = chapter.selected_version
    if chapter.selected_version_id == version_to_delete.id or (
        selected_version and selected_version.id == version_to_delete.id
    ):
        raise HTTPException(status_code=400, detail="不能删除当前生效的版本")

    # 至少保留一个版本
    if len(versions) <= 1:
        raise HTTPException(status_code=400, detail="至少需要保留一个版本")

    # 删除版本
    await session.delete(version_to_delete)
    await session.commit()

    logger.info(
        "删除章节版本: project=%s chapter=%s version_id=%s version_index=%s user=%s",
        project_id,
        request.chapter_number,
        version_to_delete.id,
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

    # 获取所有版本（按创建时间 + ID 排序，兼容旧版 index，同时优先使用稳定 version_id）
    versions = sorted(list(chapter.versions or []), key=lambda v: (v.created_at, v.id))
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

    # 情况 A: 指定了稳定版本 ID / 兼容版本索引
    if request.version_id is not None or request.version_index is not None:
        version_to_evaluate = await _resolve_chapter_version(
            session,
            chapter,
            version_id=request.version_id,
            version_index=request.version_index,
            require_content=True,
        )

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

        with LLMService.daily_limit_scope(f"chapter_review_single:{project_id}:{request.chapter_number}:{current_user.id}"):
            project_schema = await novel_service._serialize_project(project)
            eval_input_text = _build_single_chapter_evaluation_input(
                project_schema,
                chapter,
                version_to_evaluate,
                request.chapter_number,
            )
            evaluation_result = await call_generation_text(
                llm_service=llm_service,
                system_prompt=eval_prompt,
                conversation_history=[{"role": "user", "content": eval_input_text}],
                temperature=0.3,
                user_id=current_user.id,
                timeout=180.0,
                policy=GenerationCallPolicy(
                    stage_label="单版本章节评审",
                    progress_stage="review",
                    retry_attempts=2,
                    response_format=None,
                    max_tokens=4000,
                    retry_same_model_once=True,
                ),
            )
            evaluation_raw = evaluation_result.text
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
        blueprint_review_context, current_outline = _build_blueprint_review_context(project_schema, chapter_number)

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
        blueprint_context = blueprint_review_context
        current_outline_title = (current_outline or {}).get("title") or current_outline_title

        versions_content = []
        version_indices = []  # 记录有效版本的编号
        for idx, version in valid_versions:
            version_payload = _build_version_review_content_payload(version, long_threshold=3000)
            content = version_payload["content"]
            # 截断过长的内容
            if len(content) > 3000:
                content = content[:1800] + "\n...\n" + content[-1200:]
            version_number = idx + 1  # 版本编号从1开始
            version_payload.update({
                "version_index": version_number,
                "style": version.version_label or f"版本{version_number}",
                "content": content,
            })
            versions_content.append(version_payload)
            version_indices.append(version_number)

        # 构建评审输入
        eval_input = {
            "novel_blueprint": blueprint_context,
            "completed_chapters": _build_completed_chapter_review_context(
                list(getattr(project_schema, "chapters", []) or []),
                chapter_number,
            ),
            "current_chapter_outline": current_outline,
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

        with LLMService.daily_limit_scope(f"chapter_review_all:{project_id}:{chapter_number}:{user_id}"):
            evaluation_result = await call_generation_text(
                llm_service=llm_service,
                system_prompt=eval_prompt,
                conversation_history=[{"role": "user", "content": eval_input_text}],
                temperature=0.3,
                user_id=user_id,
                timeout=180.0,
                policy=GenerationCallPolicy(
                    stage_label="多版本章节评审",
                    progress_stage="review",
                    retry_attempts=2,
                    response_format="json_object",
                    max_tokens=6000,
                    retry_same_model_once=True,
                ),
            )
            evaluation_raw = evaluation_result.text
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
    project = await novel_service.ensure_project_owner(project_id, current_user.id)

    outline = await novel_service.get_outline(project_id, request.chapter_number)
    if not outline:
        raise HTTPException(status_code=404, detail="未找到对应章节大纲")

    rewrite_prompt = await prompt_service.get_prompt("outline_rewrite")
    if not rewrite_prompt:
        rewrite_prompt = (
            "你是顶级网文编辑，请在不改变主线剧情的前提下，重写章节标题、章节摘要与执行字段。"
            "要求：更抓人、更有冲突、更有悬念、可直接用于正文写作，并保留角色、伏笔和连续性承接。"
            "只输出 JSON 对象。"
        )

    direction = (request.direction or "").strip() or "无额外方向"
    existing_metadata = dict(getattr(outline, "metadata", None) or {})
    metadata_context = (
        json.dumps(existing_metadata, ensure_ascii=False, indent=2)
        if existing_metadata
        else "暂无执行 metadata"
    )
    neighbor_lines = []
    for candidate in sorted(getattr(project, "outlines", []) or [], key=lambda item: item.chapter_number):
        if abs(candidate.chapter_number - request.chapter_number) <= 2 and candidate.chapter_number != request.chapter_number:
            neighbor_lines.append(
                f"第 {candidate.chapter_number} 章《{candidate.title}》：{(candidate.summary or '').strip()[:260]}"
            )
    neighbor_context = "\n".join(neighbor_lines) if neighbor_lines else "暂无相邻章节大纲"

    user_prompt = f"""
[章节号]
第 {request.chapter_number} 章

[原始标题]
{request.title}

[原始摘要]
{request.summary}

[重写方向]
{direction}

[相邻章节连续性锚点]
{neighbor_context}

[当前执行字段 metadata]
{metadata_context}

[硬性要求]
1. 标题更有辨识度，建议 8-22 字。
2. 摘要长度 160-360 字，必须包含：本章冲突、角色目标/阻碍、关键转折、章尾钩子。
3. 保持与前后章节连续，不得胡乱跳剧情。
4. 不要改变本章在前后两章之间承担的因果位置，不要新增无法承接的支线。
5. 同步输出可执行字段：narrative_phase、chapter_role、suspense_hook、emotional_progression、character_focus、cast_delta、conflict_escalation、continuity_notes、foreshadowing、foreshadowing_tasks、payoff_window。
6. cast_delta 要说明新增/回归/退出角色如何进入角色池、势力或功能路人规划；foreshadowing_tasks 要说明本章回收、强化、禁忘和可新增伏笔。
7. 只输出 JSON，不要附加说明。格式：
{{"title":"...","summary":"...","narrative_phase":"...","chapter_role":"...","suspense_hook":"...","emotional_progression":"...","character_focus":["..."],"cast_delta":{{"new":[],"returning":[],"exit_or_absent":[],"faction_roles":[]}},"conflict_escalation":["..."],"continuity_notes":["..."],"foreshadowing":{{"plant":[],"payoff":[]}},"foreshadowing_tasks":{{"plant":[],"reinforce":[],"payoff":[],"avoid_forgetting":[]}},"payoff_window":"..."}}
"""

    try:
        with LLMService.daily_limit_scope(f"rewrite_outline:{project_id}:{request.chapter_number}:{current_user.id}"):
            json_result = await call_generation_json(
                llm_service=llm_service,
                system_prompt=rewrite_prompt,
                conversation_history=[{"role": "user", "content": user_prompt}],
                temperature=0.55,
                user_id=current_user.id,
                timeout=240.0,
                policy=GenerationCallPolicy(
                    stage_label="章节大纲重写",
                    retry_attempts=3,
                    response_format="json_object",
                    json_schema=_outline_item_json_schema(),
                    json_schema_name="chapter_outline_rewrite",
                    json_schema_strict=False,
                    allow_truncated_response=True,
                    json_repair_attempts=2,
                ),
            )
        parsed = _unwrap_outline_payload_root(json_result.data)

        rewritten_title = str(parsed.get("title") or request.title).strip()
        rewritten_summary = str(parsed.get("summary") or request.summary).strip()
        if len("".join(rewritten_summary.split())) < 80:
            rewritten_summary = request.summary
        if not rewritten_title:
            rewritten_title = request.title

        outline.title = rewritten_title
        outline.summary = rewritten_summary
        outline.metadata = _build_rewritten_outline_metadata(
            parsed_payload=parsed,
            existing_metadata=existing_metadata,
            chapter_no=request.chapter_number,
            title=rewritten_title,
            summary=rewritten_summary,
            direction=direction,
        )
        await session.commit()
    except GenerationJSONDecodeError as exc:
        logger.warning(
            "章节大纲重写返回 JSON 不可解析，保留原大纲: project_id=%s chapter=%s error=%s raw=%s",
            project_id,
            request.chapter_number,
            exc,
            exc.raw_text[:500],
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("重写章节摘要失败: project_id=%s chapter=%s error=%s", project_id, request.chapter_number, exc)
        raise HTTPException(status_code=500, detail=f"AI 重写失败: {str(exc)[:160]}")

    return await _load_project_schema(novel_service, project_id, current_user.id)


@router.post("/novels/{project_id}/chapters/rewrite-outline/start", response_model=OutlineGenerationJobResponse)
async def start_chapter_outline_rewrite(
    project_id: str,
    request: RewriteChapterOutlineRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> OutlineGenerationJobResponse:
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    async with _OUTLINE_JOB_LOCK:
        existing_run_id = _OUTLINE_PROJECT_RUNS.get(project_id)
        existing = _OUTLINE_JOBS.get(existing_run_id or "")
        if existing and existing.get("status") in _OUTLINE_ACTIVE_STATUSES:
            return _serialize_outline_job(existing)

        run_id = str(uuid.uuid4())
        now = _outline_job_now_iso()
        job = {
            "run_id": run_id,
            "project_id": project_id,
            "status": "queued",
            "progress_stage": "queued",
            "progress_message": "章节大纲重写任务已入队",
            "started_at": now,
            "updated_at": now,
            "project": None,
            "error": None,
            "request": request.model_dump(),
            "events": [_outline_runtime_event("queued", "章节大纲重写任务已入队", status="queued")],
        }
        _OUTLINE_JOBS[run_id] = job
        _OUTLINE_PROJECT_RUNS[project_id] = run_id

    background_tasks.add_task(
        _run_outline_rewrite_job,
        run_id,
        project_id,
        int(current_user.id),
        request.model_dump(),
    )
    return _serialize_outline_job(job)


@router.get("/novels/{project_id}/chapters/rewrite-outline/status", response_model=OutlineGenerationJobResponse)
async def get_chapter_outline_rewrite_status(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> OutlineGenerationJobResponse:
    return await get_chapters_outline_generation_status(project_id, session, current_user)


@router.post("/novels/{project_id}/chapters/rewrite-outline/cancel", response_model=OutlineGenerationJobResponse)
async def cancel_chapter_outline_rewrite(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> OutlineGenerationJobResponse:
    return await cancel_chapters_outline_generation(project_id, session, current_user)


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


@router.post("/novels/{project_id}/chapters/outline/start", response_model=OutlineGenerationJobResponse)
async def start_chapters_outline_generation(
    project_id: str,
    request: GenerateOutlineRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> OutlineGenerationJobResponse:
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    async with _OUTLINE_JOB_LOCK:
        existing_run_id = _OUTLINE_PROJECT_RUNS.get(project_id)
        existing = _OUTLINE_JOBS.get(existing_run_id or "")
        if existing and existing.get("status") in _OUTLINE_ACTIVE_STATUSES:
            return _serialize_outline_job(existing)

        run_id = str(uuid.uuid4())
        now = _outline_job_now_iso()
        job = {
            "run_id": run_id,
            "project_id": project_id,
            "status": "queued",
            "progress_stage": "queued",
            "progress_message": "章节大纲生成任务已入队",
            "started_at": now,
            "updated_at": now,
            "project": None,
            "error": None,
            "request": request.model_dump(),
            "events": [_outline_runtime_event("queued", "章节大纲生成任务已入队", status="queued")],
        }
        _OUTLINE_JOBS[run_id] = job
        _OUTLINE_PROJECT_RUNS[project_id] = run_id

    background_tasks.add_task(
        _run_outline_generation_job,
        run_id,
        project_id,
        int(current_user.id),
        request.model_dump(),
    )
    return _serialize_outline_job(job)


@router.get("/novels/{project_id}/chapters/outline/status", response_model=OutlineGenerationJobResponse)
async def get_chapters_outline_generation_status(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> OutlineGenerationJobResponse:
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    async with _OUTLINE_JOB_LOCK:
        run_id = _OUTLINE_PROJECT_RUNS.get(project_id)
        job = dict(_OUTLINE_JOBS.get(run_id or "") or {})
        if job and job.get("status") not in _OUTLINE_ACTIVE_STATUSES:
            _OUTLINE_JOBS.pop(str(job.get("run_id") or ""), None)
            _OUTLINE_PROJECT_RUNS.pop(project_id, None)

    if job:
        return _serialize_outline_job(job)

    return OutlineGenerationJobResponse(
        run_id="",
        project_id=project_id,
        status="idle",
        progress_stage="idle",
        progress_message="暂无章节大纲生成任务",
    )


@router.post("/novels/{project_id}/chapters/outline/cancel", response_model=OutlineGenerationJobResponse)
async def cancel_chapters_outline_generation(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> OutlineGenerationJobResponse:
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    async with _OUTLINE_JOB_LOCK:
        run_id = _OUTLINE_PROJECT_RUNS.get(project_id)
        job = _OUTLINE_JOBS.get(run_id or "")
        if not job:
            return OutlineGenerationJobResponse(
                run_id="",
                project_id=project_id,
                status="idle",
                progress_stage="idle",
                progress_message="暂无可取消的章节大纲生成任务",
            )
        if job.get("status") in _OUTLINE_ACTIVE_STATUSES:
            events = job.get("events") if isinstance(job.get("events"), list) else []
            job.update({
                "status": "cancelled",
                "progress_stage": "cancelled",
                "progress_message": "章节大纲生成任务已取消",
                "updated_at": _outline_job_now_iso(),
                "error": _outline_job_error(
                    "outline_generation_cancelled",
                    "章节大纲生成任务已取消",
                    retryable=True,
                ),
                "events": [
                    *events[-199:],
                    _outline_runtime_event("cancelled", "章节大纲生成任务已取消", status="cancelled", level="warning"),
                ],
            })
        snapshot = dict(job)

    return _serialize_outline_job(snapshot)


@router.post("/novels/{project_id}/chapters/outline", response_model=NovelProjectSchema, deprecated=True)
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

    effective_target_total_chapters, chapter_word_target = _resolve_outline_generation_goal(
        start_chapter=request.start_chapter,
        num_chapters=request.num_chapters,
        target_total_chapters=target_total_chapters,
        target_total_words=target_total_words,
        chapter_word_target=chapter_word_target,
    )

    summary_min_chars = 140
    summary_max_chars = 260

    # 获取蓝图信息
    project_schema = await novel_service._serialize_project(project)
    if project_schema.blueprint is None:
        raise HTTPException(status_code=400, detail="当前项目缺少可用蓝图，请先完成蓝图确认后再生成章节大纲")
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
    generated_outline_map: Dict[int, Dict[str, Any]] = {}
    outline_rejection_feedback: Dict[int, List[str]] = {}
    max_attempts = 3
    batch_size = min(4, max(1, request.num_chapters))
    pending_numbers = target_numbers[:]

    with LLMService.daily_limit_scope(
        f"outline:{project_id}:{request.start_chapter}:{request.num_chapters}:{current_user.id}"
    ):
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
                    feedback_lines = []
                    for number in missing_numbers:
                        reasons = outline_rejection_feedback.get(number) or []
                        if reasons:
                            feedback_lines.append(f"- 第{number}章：{'; '.join(reasons[:8])}")
                    if feedback_lines:
                        retry_hint += "\n[质量退回原因]\n" + "\n".join(feedback_lines)

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
1. 只输出 JSON 对象：{{"chapters":[{{"chapter_number":数字,"title":"标题","summary":"摘要","narrative_phase":"阶段","chapter_role":"职责","suspense_hook":"钩子","emotional_progression":"情绪变化","character_focus":["角色"],"cast_delta":{{"new":[],"returning":[],"exit_or_absent":[],"faction_roles":[]}},"conflict_escalation":["升级点"],"continuity_notes":["承接/递进说明"],"foreshadowing":{{"plant":["伏笔"],"payoff":["回收"]}},"foreshadowing_tasks":{{"plant":[],"reinforce":[],"payoff":[],"avoid_forgetting":[]}},"payoff_window":"回收窗口"}}]}}
2. chapter_number 必须只来自本次要求的章节号，不得跳号、重号、缺号。
3. 每章 summary 必须具体可写，不得空泛，长度控制在 {summary_min_chars}-{summary_max_chars} 字之间。
4. 每章 summary 必须包含：本章核心冲突、人物目标/阻碍、关键转折、章尾钩子。
5. 每章还必须说明：承接上一章什么、推进长线什么、给下一章留下什么压力。
6. 每章必须有人物焦点与情绪推进，禁止只有事件流水账。
7. {ending_constraint}
8. 与已有章节保持连续，避免剧情断层。
9. cast_delta 必须说明本章新增/回归/退出角色如何落入角色池、势力或功能性路人规则；不能凭空出现又消失。
10. foreshadowing_tasks 必须说明本章回收、强化、禁忘和可新增伏笔，不能只写“埋伏笔”。
11. 代码会拒绝缺少 chapter_role / suspense_hook / conflict_escalation / continuity_notes 的空泛章节；请一次生成可直接进入正文写作的执行型大纲。
"""

                try:
                    json_result = await call_generation_json(
                        llm_service=llm_service,
                        system_prompt=outline_prompt,
                        conversation_history=[{"role": "user", "content": prompt_input}],
                        temperature=0.7,
                        user_id=current_user.id,
                        timeout=180.0,
                        policy=GenerationCallPolicy(
                            stage_label="章节大纲分批生成",
                            progress_stage="outline_chapter_skeleton",
                            retry_attempts=3,
                            response_format="json_object",
                            json_schema=_outline_batch_json_schema(),
                            json_schema_name="chapter_outline_batch",
                            json_schema_strict=False,
                            max_tokens=5000,
                            allow_truncated_response=True,
                            retry_same_model_once=True,
                            json_repair_attempts=2,
                        ),
                    )
                    data = json_result.data
                except Exception as exc:
                    logger.warning("大纲生成分批第 %s 次生成/解析失败: %s", attempt + 1, exc)
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

                    valid_outline, rejection_reasons, normalized_outline = _validate_outline_item_executability(
                        item,
                        chapter_no=chapter_no,
                        summary_min_chars=summary_min_chars,
                        summary_max_chars=summary_max_chars,
                    )
                    if not valid_outline:
                        outline_rejection_feedback[chapter_no] = rejection_reasons
                        logger.info(
                            "skip weak outline item: project=%s chapter=%s reasons=%s",
                            project_id,
                            chapter_no,
                            rejection_reasons,
                        )
                        continue

                    title = normalized_outline["title"]
                    summary = normalized_outline["summary"]
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

                    generated_outline_map[chapter_no] = normalized_outline
                    outline_rejection_feedback.pop(chapter_no, None)

            if all(n in generated_outline_map for n in batch_numbers):
                batch_done = True
                break

        if not batch_done:
            batch_missing = [n for n in batch_numbers if n not in generated_outline_map]
            missing_str = "、".join(str(n) for n in batch_missing)
            rejection_summary = {
                str(number): outline_rejection_feedback.get(number, [])
                for number in batch_missing
            }
            logger.warning(
                "outline generation rejected after retries: project=%s missing=%s rejection_summary=%s",
                project_id,
                batch_missing,
                rejection_summary,
            )
            raise HTTPException(
                status_code=500,
                detail={
                    "code": "OUTLINE_GENERATION_QUALITY_REJECTED",
                    "message": f"大纲生成不完整，缺少章节：{missing_str}，请重试",
                    "missing_chapters": batch_missing,
                    "rejection_summary": rejection_summary,
                    "retryable": True,
                },
            )

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
                "cast_delta": item.get("cast_delta") or {},
                "conflict_escalation": item.get("conflict_escalation") or [],
                "continuity_notes": item.get("continuity_notes") or [],
                "foreshadowing": item.get("foreshadowing") or {},
                "foreshadowing_tasks": item.get("foreshadowing_tasks") or {},
                "payoff_window": item.get("payoff_window"),
                "outline_quality": {
                    "accepted_by_executability_gate": True,
                    "rejection_reasons": [],
                },
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


# ==================== SSE Streaming Endpoint ====================
import asyncio
import hashlib
import json as json_module
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from ...db.session import AsyncSessionLocal
from ...models.novel import Chapter

@router.get("/novels/{project_id}/chapters/{chapter_number}/stream")
async def stream_chapter_progress(
    project_id: str,
    chapter_number: int,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
):
    """Stream real-time chapter generation progress via SSE."""
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    async def event_generator():
        last_status = None
        last_hash = None
        max_iter = 900  # 30 minutes at 2s intervals
        for _ in range(max_iter):
            try:
                async with AsyncSessionLocal() as s:
                    result = await s.execute(
                        select(Chapter).where(
                            Chapter.project_id == project_id,
                            Chapter.chapter_number == chapter_number,
                        )
                    )
                    ch = result.scalars().first()
                    if not ch:
                        yield f"event: error\ndata: {json_module.dumps({'message': 'Chapter not found'})}\n\n"
                        return

                    status = ch.status or "not_generated"
                    rs = ch.real_summary or ""
                    try:
                        payload = json_module.loads(rs) if rs.startswith("{") else {}
                    except Exception:
                        payload = {}
                    runtime = payload.get("generation_runtime", {})

                    h = hashlib.md5(json_module.dumps(runtime, sort_keys=True, default=str).encode()).hexdigest()
                    if status != last_status or h != last_hash:
                        last_status = status
                        last_hash = h
                        yield f"event: status_update\ndata: {json_module.dumps({'status': status, 'progress_message': runtime.get('progress_message', ''), 'progress_stage': runtime.get('progress_stage', ''), 'word_count': ch.word_count or 0, 'updated_at': ch.updated_at.isoformat() if ch.updated_at else None, 'runtime': runtime})}\n\n"

                    if status in ("successful", "failed", "waiting_for_confirm", "evaluation_failed"):
                        yield f"event: complete\ndata: {json_module.dumps({'status': status, 'word_count': ch.word_count or 0})}\n\n"
                        return
            except Exception as e:
                yield f"event: error\ndata: {json_module.dumps({'message': str(e)})}\n\n"
                return
            await asyncio.sleep(2)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

