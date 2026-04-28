# AIMETA P=写作流水线编排_统一生成入口|R=上下文汇聚_生成_审查_优化|NR=不含API路由|E=PipelineOrchestrator|X=internal|A=编排器|D=fastapi,sqlalchemy|S=db,net|RD=./README.ai
from __future__ import annotations

import json
import logging
import os
import asyncio
import hashlib
import time
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import HTTPException
from openai import APIConnectionError, APIError, APITimeoutError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..models.novel import Chapter, ChapterVersion, ChapterOutline
from ..models.memory_layer import CharacterState, TimelineEvent
from ..models.foreshadowing import Foreshadowing
from ..models.clue_tracker import StoryClue
from ..schemas.novel import ChapterGenerationStatus
from ..models.project_memory import ProjectMemory
from ..repositories.system_config_repository import SystemConfigRepository
from ..services.ai_review_service import AIReviewService
from ..services.cache_service import CacheService
from ..services.chapter_context_service import ChapterContextService
from ..services.chapter_guardrails import ChapterGuardrails
from ..services.consistency_service import ConsistencyService, ViolationSeverity
from ..services.enhanced_writing_flow import EnhancedWritingFlow
from ..services.enrichment_service import EnrichmentService
from ..services.llm_config_service import LLMConfigService
from ..services.llm_service import LLMService
from ..services.knowledge_retrieval_service import KnowledgeRetrievalService, FilteredContext
from ..services.memory_layer_service import MemoryLayerService
from ..services.novel_service import NovelService
from ..services.preview_generation_service import PreviewGenerationService
from ..services.prompt_service import PromptService
from ..services.reader_simulator_service import ReaderSimulatorService, ReaderType
from ..services.style_rag_service import StyleRAGService
from ..services.self_critique_service import CritiqueDimension, SelfCritiqueService
from ..services.vector_store_service import VectorStoreService
from ..services.writer_context_builder import WriterContextBuilder
from ..utils.json_utils import remove_think_tags, unwrap_markdown_json

logger = logging.getLogger(__name__)
DEFAULT_GENERATED_VERSION_COUNT = 1  # 默认生成1个版本
MIN_GENERATED_VERSION_COUNT = 1
MAX_GENERATED_VERSION_COUNT = 4  # 最多生成4个版本
MAX_STORED_CHAPTER_VERSIONS = 4  # 最多保存4个版本


def _clamp_generated_version_count(value: int) -> int:
    return max(
        MIN_GENERATED_VERSION_COUNT,
        min(MAX_GENERATED_VERSION_COUNT, int(value)),
    )


@dataclass
class PipelineConfig:
    preset: str = "basic"
    version_count: int = DEFAULT_GENERATED_VERSION_COUNT
    enable_preview: bool = False
    enable_optimizer: bool = False
    enable_consistency: bool = False
    enable_enrichment: bool = False
    async_finalize: bool = False
    enable_constitution: bool = False
    enable_persona: bool = False
    enable_six_dimension: bool = False
    enable_reader_sim: bool = False
    enable_self_critique: bool = False
    enable_memory: bool = False
    enable_rag: bool = True
    rag_mode: str = "simple"
    enable_foreshadowing: bool = False
    enable_faction: bool = False
    target_word_count: int = 3200
    min_word_count: int = 2400
    max_enrich_iterations: int = 2
    allow_truncated_response: bool = False
    enforce_min_word_count: bool = False


class PipelineOrchestrator:
    """统一写作流水线编排器。"""

    _generation_semaphore: Optional[asyncio.Semaphore] = None
    _RUNTIME_MAX_EVENTS = 60
    _RUNTIME_MAX_STRING = 280
    _RUNTIME_MAX_LIST = 12
    _RUNTIME_MAX_DICT = 24
    _RUNTIME_MAX_JSON_CHARS = 24000

    def __init__(self, session: AsyncSession):
        self.session = session
        self.llm_service = LLMService(session)
        self.prompt_service = PromptService(session)
        self.novel_service = NovelService(session)
        self.context_builder = WriterContextBuilder()
        self.guardrails = ChapterGuardrails()
        self.cache_service = CacheService(getattr(settings, "redis_url", "redis://localhost:6379/0"))
        if PipelineOrchestrator._generation_semaphore is None:
            limit = max(1, int(getattr(settings, "writer_chapter_versions", 1) or 1))
            PipelineOrchestrator._generation_semaphore = asyncio.Semaphore(min(2, limit))

    def _create_llm_config_service(self) -> LLMConfigService:
        return LLMConfigService(self.session)

    @staticmethod
    def _normalize_overview_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        try:
            return json.dumps(value, ensure_ascii=False, indent=2).strip()
        except Exception:
            return str(value).strip()

    @classmethod
    def _build_chapter_overview_bundle(cls, context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        source = context or {}
        bundle = {
            "outline_title": cls._normalize_overview_text(source.get("outline_title")),
            "outline_summary": cls._normalize_overview_text(source.get("outline_summary")),
            "chapter_mission": cls._normalize_overview_text(source.get("chapter_mission")),
            "previous_summary": cls._normalize_overview_text(source.get("previous_summary")),
            "previous_tail": cls._normalize_overview_text(source.get("previous_tail")),
            "previous_chapter_bundle": cls._normalize_overview_text(source.get("previous_chapter_bundle")),
            "recent_track": cls._normalize_overview_text(source.get("recent_track")),
            "plot_arc_digest": cls._normalize_overview_text(source.get("plot_arc_digest")),
            "project_memory": cls._normalize_overview_text(source.get("project_memory")),
            "style_context": cls._normalize_overview_text(source.get("style_context")),
            "character_profiles": cls._normalize_overview_text(source.get("character_profiles")),
            "forbidden_characters": cls._normalize_overview_text(source.get("forbidden_characters")),
            "emotion_target": cls._normalize_overview_text(source.get("emotion_target")),
        }
        bundle["overview_hash"] = hashlib.sha1(
            json.dumps(bundle, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return bundle

    @staticmethod
    def _resolve_overview_change_level(previous_bundle: Optional[Dict[str, Any]], current_bundle: Optional[Dict[str, Any]]) -> Tuple[str, List[str]]:
        previous = previous_bundle if isinstance(previous_bundle, dict) else {}
        current = current_bundle if isinstance(current_bundle, dict) else {}
        previous_hash = str(previous.get("overview_hash") or "").strip()
        current_hash = str(current.get("overview_hash") or "").strip()
        if previous_hash and current_hash and previous_hash == current_hash:
            return "none", []

        changed_fields: List[str] = []
        tracked_keys = [
            "outline_title",
            "outline_summary",
            "chapter_mission",
            "previous_summary",
            "previous_tail",
            "previous_chapter_bundle",
            "recent_track",
            "plot_arc_digest",
            "project_memory",
            "style_context",
            "character_profiles",
            "forbidden_characters",
            "emotion_target",
        ]
        for key in tracked_keys:
            if str(previous.get(key) or "").strip() != str(current.get(key) or "").strip():
                changed_fields.append(key)

        if not previous:
            return "heavy", changed_fields
        if not changed_fields:
            return "none", []
        if len(changed_fields) <= 2:
            return "light", changed_fields
        if len(changed_fields) <= 5:
            return "medium", changed_fields
        return "heavy", changed_fields

    @staticmethod
    def _build_reuse_decision(change_level: str, changed_fields: List[str]) -> Dict[str, Any]:
        normalized_level = str(change_level or "heavy").strip().lower() or "heavy"
        return {
            "change_level": normalized_level,
            "changed_fields": list(changed_fields or []),
            "reused": normalized_level in {"none", "light"},
            "skip_self_critique": normalized_level in {"none", "light"},
        }

    @staticmethod
    def _build_reused_self_critique_summary(
        previous_summary: Optional[Dict[str, Any]],
        *,
        reuse_decision: Dict[str, Any],
        overview_bundle: Dict[str, Any],
        source_version_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        base = dict(previous_summary or {})
        base["status"] = "reused"
        base["iterations"] = 0
        base["reuse_decision"] = reuse_decision
        base["overview_bundle"] = overview_bundle
        base["reused_from_version_id"] = source_version_id
        base["reused_at"] = datetime.now(timezone.utc).isoformat()
        base.setdefault("critical_count", 0)
        base.setdefault("major_count", 0)
        base.setdefault("priority_fixes", [])
        base.setdefault("final_critique", {})
        base.setdefault("optimization_logs", [])
        return base

    @staticmethod
    def _map_consistency_category_to_dimension(category: Optional[str]) -> str:
        normalized = str(category or "").strip().lower()
        mapping = {
            "setting": "logic",
            "plot": "continuity",
            "foreshadowing": "suspense",
            "character": "character",
        }
        return mapping.get(normalized, "logic")

    @classmethod
    def _normalize_consistency_issues_for_local_fix(cls, report: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for item in (report or {}).get("violations") or []:
            if not isinstance(item, dict):
                continue
            severity = str(item.get("severity") or "minor").lower()
            if severity not in {"critical", "major"}:
                continue
            normalized.append({
                "dimension": item.get("dimension") or cls._map_consistency_category_to_dimension(item.get("category")),
                "severity": severity,
                "location": item.get("location") or "未知",
                "problem": item.get("description") or "发现一致性问题",
                "suggestion": item.get("suggested_fix") or "修正该处一致性问题并保持上下文承接",
                "example": item.get("example") or "无",
            })
        return normalized

    @staticmethod
    def _map_reader_problem_to_dimension(problem: Optional[str]) -> str:
        text = str(problem or "").lower()
        if any(keyword in text for keyword in ("节奏", "拖", "慢", "信息密度")):
            return "pacing"
        if any(keyword in text for keyword in ("对白", "对话", "口吻")):
            return "dialogue"
        if any(keyword in text for keyword in ("情绪", "感情", "共鸣")):
            return "emotion"
        if any(keyword in text for keyword in ("人设", "角色", "主角")):
            return "character"
        if any(keyword in text for keyword in ("钩子", "悬念", "追更")):
            return "suspense"
        if any(keyword in text for keyword in ("逻辑", "设定", "看不懂")):
            return "logic"
        return "writing"

    @classmethod
    def _normalize_reader_issues_for_local_fix(cls, feedback: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        priority_issues = (((feedback or {}).get("diagnostic_summary") or {}).get("priority_issues") or [])
        for item in priority_issues[:6]:
            if not isinstance(item, dict):
                continue
            problem = item.get("problem") or "读者反馈存在风险点"
            normalized.append({
                "dimension": cls._map_reader_problem_to_dimension(problem),
                "severity": item.get("severity") or "major",
                "location": item.get("location") or "未知",
                "problem": problem,
                "suggestion": item.get("suggestion") or f"针对“{problem}”进行局部读者体验修正",
                "example": item.get("example") or "无",
            })
        return normalized

    @staticmethod
    def _extract_enhanced_review_issues(review_result: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not isinstance(review_result, dict):
            return []

        issues: List[Dict[str, Any]] = []
        six_dimension_review = review_result.get("six_dimension_review")
        if isinstance(six_dimension_review, dict):
            for item in (six_dimension_review.get("issues") or []):
                if not isinstance(item, dict):
                    continue
                issues.append({
                    "dimension": item.get("dimension") or item.get("category") or "writing",
                    "severity": item.get("severity") or "major",
                    "location": item.get("location") or "未知",
                    "problem": item.get("description") or item.get("problem") or "发现增强评审问题",
                    "suggestion": item.get("suggestion") or item.get("fix") or "按评审意见修正",
                })

        for text in review_result.get("critical_issues") or []:
            if text:
                issues.append({
                    "dimension": "writing",
                    "severity": "critical",
                    "location": "未知",
                    "problem": str(text),
                    "suggestion": str(text),
                })

        for text in ((six_dimension_review or {}).get("priority_fixes") or review_result.get("priority_fixes") or []):
            if text:
                issues.append({
                    "dimension": "writing",
                    "severity": "major",
                    "location": "未知",
                    "problem": str(text),
                    "suggestion": str(text),
                })
        return issues[:12]

    @staticmethod
    def _make_cache_key(prefix: str, *parts: Any) -> str:
        normalized = "|".join(str(part or "") for part in parts)
        digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()
        return f"writer:{prefix}:{digest}"

    @staticmethod
    def _estimate_tokens(text: Optional[str]) -> int:
        if not text:
            return 0
        return max(1, len(str(text)) // 4)

    async def _cache_get(self, key: str) -> Optional[Any]:
        if not self.cache_service.is_available():
            return None
        return await self.cache_service.get(key)

    async def _cache_set(self, key: str, value: Any, expire: int) -> None:
        if not self.cache_service.is_available():
            return
        await self.cache_service.set(key, value, expire=expire)

    @staticmethod
    def _parse_generation_runtime(raw_summary: Optional[str]) -> Dict[str, Any]:
        if not raw_summary:
            return {}
        try:
            payload = json.loads(raw_summary)
        except (TypeError, ValueError):
            return {}
        return payload if isinstance(payload, dict) else {}

    @classmethod
    def _truncate_runtime_text(cls, value: Any, limit: Optional[int] = None) -> str:
        text = str(value or "")
        max_len = limit or cls._RUNTIME_MAX_STRING
        if len(text) <= max_len:
            return text
        return f"{text[:max_len]}…(已截断)"

    @classmethod
    def _compact_runtime_value(cls, value: Any, *, depth: int = 0) -> Any:
        if value is None or isinstance(value, (bool, int, float)):
            return value
        if isinstance(value, str):
            return cls._truncate_runtime_text(value)
        if depth >= 3:
            if isinstance(value, dict):
                return f"[object:{len(value)}]"
            if isinstance(value, (list, tuple, set)):
                return f"[list:{len(value)}]"
            return cls._truncate_runtime_text(value)
        if isinstance(value, dict):
            compact: Dict[str, Any] = {}
            for index, (key, item) in enumerate(value.items()):
                if index >= cls._RUNTIME_MAX_DICT:
                    compact["__truncated__"] = f"还剩 {len(value) - cls._RUNTIME_MAX_DICT} 项未展示"
                    break
                compact[str(key)] = cls._compact_runtime_value(item, depth=depth + 1)
            return compact
        if isinstance(value, (list, tuple, set)):
            items = list(value)
            compact_list = [cls._compact_runtime_value(item, depth=depth + 1) for item in items[:cls._RUNTIME_MAX_LIST]]
            if len(items) > cls._RUNTIME_MAX_LIST:
                compact_list.append(f"... 还剩 {len(items) - cls._RUNTIME_MAX_LIST} 项未展示")
            return compact_list
        return cls._truncate_runtime_text(value)

    @classmethod
    def _compact_runtime_event(cls, event: Dict[str, Any]) -> Dict[str, Any]:
        compact_event = {
            "at": event.get("at"),
            "stage": event.get("stage"),
            "level": event.get("level", "info"),
            "message": cls._truncate_runtime_text(event.get("message"), 360),
        }
        metadata = event.get("metadata")
        if isinstance(metadata, dict) and metadata:
            compact_event["metadata"] = cls._compact_runtime_value(metadata)
        return compact_event

    @classmethod
    def _compact_runtime_payload(cls, runtime: Dict[str, Any]) -> Dict[str, Any]:
        compact: Dict[str, Any] = {}
        for key, value in runtime.items():
            if key == "events":
                events = value if isinstance(value, list) else []
                compact["events"] = [cls._compact_runtime_event(item) for item in events[-cls._RUNTIME_MAX_EVENTS:] if isinstance(item, dict)]
                continue
            compact[key] = cls._compact_runtime_value(value)

        serialized = json.dumps({"generation_runtime": compact}, ensure_ascii=False)
        if len(serialized) <= cls._RUNTIME_MAX_JSON_CHARS:
            return compact

        compact["events"] = compact.get("events", [])[-24:]
        for noisy_key in [
            "previous_chapter_bundle",
            "chapter_overview",
            "chapter_overview_reuse",
            "review_summaries",
            "stage_timings_ms",
            "optimization_logs",
            "self_critique_priority_fixes",
        ]:
            if noisy_key in compact:
                compact[noisy_key] = cls._compact_runtime_value(compact[noisy_key], depth=3)

        serialized = json.dumps({"generation_runtime": compact}, ensure_ascii=False)
        if len(serialized) > cls._RUNTIME_MAX_JSON_CHARS:
            compact["events"] = compact.get("events", [])[-12:]
            compact["runtime_truncated"] = True
            compact["runtime_truncated_reason"] = "generation_runtime 过大，已自动裁剪"
        return compact

    @staticmethod
    def _estimate_remaining_seconds(stage: str, target_word_count: int) -> int:
        target_word_count = max(1200, int(target_word_count or 0))
        preparing_budget = max(50, min(180, 24 + int(target_word_count / 100) * 2))
        generating_budget = max(120, min(900, 60 + int(target_word_count / 100) * 12))
        review_budget = max(40, min(240, 30 + int(target_word_count / 100) * 2))
        enrichment_budget = max(30, min(300, 18 + int(target_word_count / 100) * 3))
        stage_remaining = {
            "queued": preparing_budget + generating_budget + review_budget + enrichment_budget + 36,
            "prepare_context": generating_budget + review_budget + enrichment_budget + 28,
            "generate_mission": generating_budget + review_budget + enrichment_budget + 18,
            "generate_variants": review_budget + enrichment_budget + 16,
            "review": enrichment_budget + 18,
            "enrichment": max(12, enrichment_budget),
            "persist_versions": 10,
            "waiting_for_confirm": 0,
            "failed": 0,
        }
        return max(0, stage_remaining.get(stage, 0))

    @staticmethod
    def _infer_stage_progress_percent(stage: str) -> int:
        stage_progress = {
            "queued": 4,
            "generate_mission": 18,
            "prepare_context": 28,
            "generate_variants": 62,
            "review": 72,
            "ai_review": 72,
            "self_critique": 84,
            "reader_simulator": 86,
            "consistency": 90,
            "persist_versions": 97,
            "waiting_for_confirm": 100,
            "failed": 100,
        }
        return stage_progress.get(stage, 80)

    async def _update_generation_runtime(
        self,
        chapter: Chapter,
        *,
        generation_run_id: Optional[str],
        stage: str,
        message: str,
        progress_percent: int,
        level: str = "info",
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not generation_run_id:
            return
        await self.session.refresh(chapter)
        payload = self._parse_generation_runtime(chapter.real_summary)
        runtime = payload.get("generation_runtime") if isinstance(payload.get("generation_runtime"), dict) else {}
        current_run_id = runtime.get("run_id")
        if current_run_id and current_run_id != generation_run_id:
            return

        now_iso = datetime.now(timezone.utc).isoformat()
        events = runtime.get("events") if isinstance(runtime.get("events"), list) else []
        event = {
            "at": now_iso,
            "stage": stage,
            "level": level,
            "message": message,
            "progress_percent": max(0, min(100, int(progress_percent))),
        }
        if extra:
            compact_extra = {key: value for key, value in extra.items() if value is not None}
            if compact_extra:
                event["metadata"] = self._compact_runtime_value(compact_extra)

        allowed_actions = ["refresh_status", "cancel_generation"]
        if stage == "waiting_for_confirm":
            allowed_actions = ["refresh_status", "confirm_version", "review_versions"]
        elif stage == "failed":
            allowed_actions = ["refresh_status", "retry_generation"]

        normalized_runtime: Dict[str, Any] = {
            "run_id": generation_run_id,
            "cancel_requested": bool(runtime.get("cancel_requested")),
            "progress_stage": stage,
            "progress_message": message,
            "progress_percent": max(0, min(100, int(progress_percent))),
            "allowed_actions": allowed_actions,
            "started_at": runtime.get("started_at") or now_iso,
            "updated_at": now_iso,
            "heartbeat_at": now_iso,
            "chapter_number": chapter.chapter_number,
            "events": [*events[-199:], event],
        }
        if runtime.get("reason"):
            normalized_runtime["reason"] = runtime.get("reason")
        if extra:
            normalized_runtime.update({
                key: self._compact_runtime_value(value)
                for key, value in extra.items()
                if value is not None
            })
        target_word_count = int(normalized_runtime.get("target_word_count") or 0)
        normalized_runtime["estimated_remaining_seconds"] = self._estimate_remaining_seconds(stage, target_word_count)
        normalized_runtime = self._compact_runtime_payload(normalized_runtime)
        chapter.real_summary = json.dumps({"generation_runtime": normalized_runtime}, ensure_ascii=False)
        await self.session.commit()

    async def _safe_session_rollback(self, reason: str) -> None:
        try:
            await self.session.rollback()
        except Exception as rollback_exc:  # noqa: BLE001 - rollback best effort
            logger.warning("Session rollback failed: reason=%s error=%s", reason, rollback_exc)
        else:
            logger.warning("Session rolled back after degraded stage failure: reason=%s", reason)

    async def _assert_generation_active(
        self,
        chapter: Chapter,
        *,
        generation_run_id: Optional[str],
        stage: str,
    ) -> None:
        if not generation_run_id:
            return

        await self.session.refresh(chapter)
        runtime_payload = self._parse_generation_runtime(chapter.real_summary)
        runtime_state = runtime_payload.get("generation_runtime") if isinstance(runtime_payload, dict) else None
        current_run_id = runtime_state.get("run_id") if isinstance(runtime_state, dict) else None
        cancel_requested = bool(runtime_state.get("cancel_requested")) if isinstance(runtime_state, dict) else False

        if (
            chapter.status != ChapterGenerationStatus.GENERATING.value
            or current_run_id != generation_run_id
            or cancel_requested
        ):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "GENERATION_CANCELLED",
                    "message": "章节生成任务已失效或被取消。",
                    "hint": f"后台流水线在 {stage} 阶段检测到任务已取消，请重新发起生成。",
                    "retryable": False,
                    "stage": stage,
                },
            )

    async def generate_chapter(
        self,
        *,
        project_id: str,
        chapter_number: int,
        user_id: int,
        writing_notes: Optional[str] = None,
        flow_config: Optional[Dict[str, Any]] = None,
        generation_run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        stage_timings: Dict[str, float] = {}

        async def mark_stage(stage_name: str, started_at: float, *, detail: Optional[str] = None) -> None:
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            stage_timings[stage_name] = duration_ms
            logger.info(
                "Pipeline stage completed: project=%s chapter=%s stage=%s duration_ms=%s",
                project_id,
                chapter_number,
                stage_name,
                duration_ms,
            )
            runtime_detail = detail or f"阶段 {stage_name} 完成，用时 {round(duration_ms / 1000, 2)} 秒"
            await self._update_generation_runtime(
                chapter,
                generation_run_id=generation_run_id,
                stage=stage_name,
                message=runtime_detail,
                progress_percent=self._infer_stage_progress_percent(stage_name),
                extra={
                    "stage_duration_ms": duration_ms,
                    "stage_duration_seconds": round(duration_ms / 1000, 2),
                    "stage_timings": dict(stage_timings),
                },
            )

        pipeline_started_at = time.perf_counter()
        config = await self._resolve_config(flow_config)
        runtime_metadata: Dict[str, Any] = {
            "provider_preflight": {},
            "degraded_stages": [],
            "generation_mode": "quality",
            "stable_retry_used": False,
            "target_word_count": 0,
            "min_word_count": 0,
            "actual_word_count": 0,
            "enrichment_triggered": False,
            "word_requirement_met": False,
            "word_requirement_reason": None,
            "generation_attempts": [],
            "candidate_generation": {},
            "quality_gates": {},
            "review_status": "skipped",
            "consistency_status": "skipped",
        }
        runtime_metadata["provider_preflight"] = await self._ensure_provider_ready(user_id)
        runtime_metadata["target_word_count"] = config.target_word_count
        runtime_metadata["min_word_count"] = config.min_word_count
        project = await self.novel_service.ensure_project_owner(project_id, user_id)

        outline = await self.novel_service.get_outline(project_id, chapter_number)
        if not outline:
            raise HTTPException(status_code=404, detail="蓝图中未找到对应章节纲要")

        chapter = await self.novel_service.get_or_create_chapter(project_id, chapter_number)
        if chapter.status != "generating":
            chapter.real_summary = None
            chapter.selected_version_id = None
            chapter.status = "generating"
            await self.session.commit()

        await self._update_generation_runtime(
            chapter,
            generation_run_id=generation_run_id,
            stage="prepare_context",
            message="正在整理章节上下文、历史摘要和写作约束",
            progress_percent=8,
            extra={
                "target_word_count": config.target_word_count,
                "min_word_count": config.min_word_count,
                "generation_mode": config.preset,
            },
        )
        await self._assert_generation_active(
            chapter,
            generation_run_id=generation_run_id,
            stage="prepare_context",
        )

        outlines_map = {item.chapter_number: item for item in project.outlines}
        prepare_context_started_at = time.perf_counter()
        history_context = await self._collect_history_context(
            project_id=project_id,
            chapter_number=chapter_number,
            outlines_map=outlines_map,
            chapters=project.chapters,
            user_id=user_id,
        )

        blueprint_dict = await self._get_writer_blueprint(project)

        outline_title = outline.title or f"第{outline.chapter_number}章"
        outline_summary = outline.summary or "暂无摘要"
        writing_notes = writing_notes or "无额外写作指令"

        all_characters = [c.get("name") for c in blueprint_dict.get("characters", []) if c.get("name")]

        mission_started_at = time.perf_counter()
        chapter_mission = await self._generate_chapter_mission(
            blueprint_dict=blueprint_dict,
            previous_summary=history_context["previous_summary"],
            previous_tail=history_context["previous_tail"],
            recent_track=history_context.get("recent_track", ""),
            plot_arc_digest=history_context.get("plot_arc_digest", ""),
            outline_title=outline_title,
            outline_summary=outline_summary,
            writing_notes=writing_notes,
            introduced_characters=[],
            all_characters=all_characters,
            user_id=user_id,
        )
        await mark_stage("generate_mission", mission_started_at, detail="章节导演脚本阶段完成")

        allowed_new_characters = chapter_mission.get("allowed_new_characters", []) if chapter_mission else []

        visibility_context = self.context_builder.build_visibility_context(
            blueprint=blueprint_dict,
            completed_summaries=history_context["completed_summaries"],
            previous_tail=history_context["previous_tail"],
            outline_title=outline_title,
            outline_summary=outline_summary,
            writing_notes=writing_notes,
            allowed_new_characters=allowed_new_characters,
        )

        writer_blueprint = visibility_context["writer_blueprint"]
        forbidden_characters = visibility_context["forbidden_characters"]
        introduced_characters = visibility_context["introduced_characters"]

        logger.info(
            "Pipeline context: project=%s chapter=%s introduced=%d allowed_new=%d forbidden=%d",
            project_id,
            chapter_number,
            len(introduced_characters),
            len(allowed_new_characters),
            len(forbidden_characters),
        )

        enhanced_flow = None
        enhanced_context = None
        if config.enable_constitution or config.enable_persona or config.enable_foreshadowing or config.enable_faction:
            enhanced_flow = EnhancedWritingFlow(self.session, self.llm_service, self.prompt_service)
            enhanced_context = await enhanced_flow.prepare_writing_context(
                project_id=project_id,
                chapter_number=chapter_number,
                chapter_outline=outline_summary,
                user_id=user_id,
            )

        memory_context = None
        if config.enable_memory:
            memory_context = await self._get_memory_context(
                project_id=project_id,
                chapter_number=chapter_number,
                involved_characters=introduced_characters,
            )

        project_memory_text = await self._get_project_memory_text(project_id)
        style_context = await self._get_style_context(project_id, user_id)
        analysis_guidance_context = await self._build_story_guidance_context(
            project_id=project_id,
            chapter_number=chapter_number,
        )

        rag_context = None
        knowledge_context = None
        rag_stats = None
        if config.enable_rag:
            if config.rag_mode == "two_stage":
                knowledge_context, rag_stats = await self._get_two_stage_rag_context(
                    project_id=project_id,
                    chapter_number=chapter_number,
                    writing_notes=writing_notes,
                    pov_character=self._resolve_pov_character(chapter_mission),
                    user_id=user_id,
                )
            else:
                rag_context = await self._get_rag_context(
                    project_id=project_id,
                    outline_title=outline_title,
                    outline_summary=outline_summary,
                    writing_notes="\n".join(filter(None, [writing_notes, history_context.get("plot_arc_digest", ""), history_context.get("recent_track", "")])),
                    user_id=user_id,
                )
                rag_stats = {
                    "mode": "simple",
                    "chunks": len(rag_context.get("chunks", [])) if rag_context else 0,
                    "summaries": len(rag_context.get("summaries", [])) if rag_context else 0,
                }
        await mark_stage("prepare_context", prepare_context_started_at, detail="上下文准备阶段完成")

        writer_prompt = await self.prompt_service.get_prompt("writing_v2")
        if not writer_prompt:
            writer_prompt = await self.prompt_service.get_prompt("writing")
        if not writer_prompt:
            raise HTTPException(status_code=500, detail="缺少写作提示词，请联系管理员配置")

        prompt_sections = self._build_prompt_sections(
            writer_blueprint=writer_blueprint,
            previous_summary=history_context["previous_summary"],
            previous_tail=history_context["previous_tail"],
            chapter_mission=chapter_mission,
            rag_context=rag_context,
            knowledge_context=knowledge_context,
            outline_title=outline_title,
            outline_summary=outline_summary,
            writing_notes=writing_notes,
            forbidden_characters=forbidden_characters,
            project_memory_text=project_memory_text,
            memory_context=memory_context,
            analysis_guidance_context=analysis_guidance_context,
            style_context=style_context,
            target_word_count=config.target_word_count,
            min_word_count=config.min_word_count,
        )

        if enhanced_flow and enhanced_context:
            prompt_sections = enhanced_flow.build_enhanced_prompt_sections(prompt_sections, enhanced_context)

        prompt_sections = self._apply_prompt_budget(prompt_sections)
        runtime_metadata["quality_gates"]["prompt_section_count"] = len(prompt_sections)
        runtime_metadata["quality_gates"]["prompt_estimated_tokens"] = sum(
            self._estimate_tokens(content) for _, content in prompt_sections if content
        )

        prompt_input = "\n\n".join(f"{title}\n{content}" for title, content in prompt_sections if content)
        logger.debug("Pipeline prompt length: %s chars", len(prompt_input))
        await self.session.commit()
        await self._update_generation_runtime(
            chapter,
            generation_run_id=generation_run_id,
            stage="generate_mission",
            message="上下文已就绪，正在生成正文任务与候选草稿",
            progress_percent=18,
            extra={
                "introduced_character_count": len(introduced_characters),
                "allowed_new_character_count": len(allowed_new_characters),
            },
        )
        await self._assert_generation_active(
            chapter,
            generation_run_id=generation_run_id,
            stage="before_generation",
        )

        active_config = config
        attempt_configs: List[PipelineConfig] = [config]
        stable_retry_config = self._build_stable_retry_config(config)
        if stable_retry_config is not None:
            attempt_configs.append(stable_retry_config)

        required_success_count = self._required_success_count(config.version_count)
        runtime_metadata["quality_gates"]["required_success_count"] = required_success_count
        runtime_metadata["quality_gates"]["requested_version_count"] = config.version_count

        versions: List[Dict[str, Any]] = []
        generation_errors: List[Exception] = []
        await self._update_generation_runtime(
            chapter,
            generation_run_id=generation_run_id,
            stage="generate_variants",
            message="正在调用模型生成候选版本",
            progress_percent=34,
            extra={
                "attempt_count": len(attempt_configs),
                "version_count": config.version_count,
            },
        )
        generation_variants_started_at = time.perf_counter()
        for attempt_idx, attempt_config in enumerate(attempt_configs):
            version_count = attempt_config.version_count
            version_style_hints = self._resolve_style_hints(enhanced_context, version_count)

            generation_tasks: List[asyncio.Task] = []
            generation_attempt_started_at = time.perf_counter()
            for idx in range(version_count):
                style_hint = version_style_hints[idx] if idx < len(version_style_hints) else None
                generation_tasks.append(
                    asyncio.create_task(
                        self._generate_single_version(
                            index=idx,
                            prompt_input=prompt_input,
                            writer_prompt=writer_prompt,
                            style_hint=style_hint,
                            project_id=project_id,
                            chapter_number=chapter_number,
                            outline_title=outline_title,
                            outline_summary=outline_summary,
                            chapter_mission=chapter_mission,
                            forbidden_characters=forbidden_characters,
                            allowed_new_characters=allowed_new_characters,
                            user_id=user_id,
                            writer_blueprint=writer_blueprint,
                            memory_context=memory_context,
                            enhanced_context=enhanced_context,
                            config=attempt_config,
                        )
                    )
                )

            generation_results = await asyncio.gather(*generation_tasks, return_exceptions=True)
            generation_attempt_duration_ms = round((time.perf_counter() - generation_attempt_started_at) * 1000, 2)
            await self._assert_generation_active(
                chapter,
                generation_run_id=generation_run_id,
                stage=f"generation_attempt_{attempt_idx + 1}",
            )
            attempt_versions: List[Dict[str, Any]] = []
            attempt_errors: List[Exception] = []
            for result in generation_results:
                if isinstance(result, Exception):
                    attempt_errors.append(result)
                    logger.warning(
                        "Single version generation candidate failed: project=%s chapter=%s mode=%s error=%s",
                        project_id,
                        chapter_number,
                        attempt_config.preset,
                        result,
                    )
                else:
                    attempt_versions.append(result)

            success_count = len(attempt_versions)
            generated_version_timings = [
                dict((item.get("metadata") or {}).get("timings") or {})
                for item in attempt_versions
                if isinstance(item, dict)
            ]
            generation_phase_total_ms = round(sum(float(timing.get("generation_ms", 0) or 0) for timing in generated_version_timings), 2)
            guardrail_check_total_ms = round(sum(float(timing.get("guardrail_check_ms", 0) or 0) for timing in generated_version_timings), 2)
            guardrail_rewrite_total_ms = round(sum(float(timing.get("guardrail_rewrite_ms", 0) or 0) for timing in generated_version_timings), 2)
            version_total_ms = round(sum(float(timing.get("total_ms", 0) or 0) for timing in generated_version_timings), 2)
            runtime_metadata["generation_attempts"].append(
                {
                    "attempt_index": attempt_idx + 1,
                    "mode": attempt_config.preset,
                    "requested_version_count": version_count,
                    "successful_versions": success_count,
                    "failed_versions": len(attempt_errors),
                    "meets_success_threshold": success_count >= required_success_count,
                    "duration_ms": generation_attempt_duration_ms,
                    "generation_phase_total_ms": generation_phase_total_ms,
                    "guardrail_check_total_ms": guardrail_check_total_ms,
                    "guardrail_rewrite_total_ms": guardrail_rewrite_total_ms,
                    "version_total_ms": version_total_ms,
                }
            )

            if success_count >= required_success_count:
                versions = attempt_versions
                generation_errors = attempt_errors
                active_config = attempt_config
                runtime_metadata["candidate_generation"] = {
                    "requested_version_count": version_count,
                    "successful_versions": success_count,
                    "failed_versions": len(attempt_errors),
                    "required_success_count": required_success_count,
                }
                if attempt_idx > 0:
                    runtime_metadata["stable_retry_used"] = True
                    runtime_metadata["generation_mode"] = "stable"
                await self._update_generation_runtime(
                    chapter,
                    generation_run_id=generation_run_id,
                    stage="review",
                    message="候选草稿已生成，正在执行 AI 评审与最佳版本筛选",
                    progress_percent=62,
                    extra={
                        "generated_version_count": len(attempt_versions),
                        "stable_retry_used": runtime_metadata["stable_retry_used"],
                        "generation_mode": runtime_metadata["generation_mode"],
                        "generation_attempt_duration_ms": generation_attempt_duration_ms,
                        "generation_attempt_duration_seconds": round(generation_attempt_duration_ms / 1000, 2),
                        "generation_phase_total_ms": generation_phase_total_ms,
                        "guardrail_check_total_ms": guardrail_check_total_ms,
                        "guardrail_rewrite_total_ms": guardrail_rewrite_total_ms,
                        "version_total_ms": version_total_ms,
                    },
                )
                break

            generation_errors = attempt_errors
            should_stable_retry = (
                attempt_idx == 0
                and len(attempt_configs) > 1
                and (
                    self._should_retry_with_stable_config(attempt_errors)
                    or self._should_retry_due_to_low_success_rate(
                        success_count=success_count,
                        requested_count=version_count,
                        required_success_count=required_success_count,
                    )
                )
            )
            if should_stable_retry:
                runtime_metadata["stable_retry_used"] = True
                runtime_metadata["generation_mode"] = "stable"
                runtime_metadata["quality_gates"]["stable_retry_reason"] = (
                    "transient_failures" if self._should_retry_with_stable_config(attempt_errors) else "insufficient_successful_candidates"
                )
                await self._update_generation_runtime(
                    chapter,
                    generation_run_id=generation_run_id,
                    stage="generate_variants",
                    message="主流程生成结果不足，正在切换稳定模式重试",
                    progress_percent=42,
                    level="warning",
                    extra={
                        "stable_retry_used": True,
                        "generation_mode": "stable",
                        "successful_versions": success_count,
                        "required_success_count": required_success_count,
                    },
                )
                logger.warning(
                    "Primary generation insufficient, retrying once with stable mode: project=%s chapter=%s success=%s required=%s",
                    project_id,
                    chapter_number,
                    success_count,
                    required_success_count,
                )
                continue
            break

        version_count = active_config.version_count
        await self._assert_generation_active(
            chapter,
            generation_run_id=generation_run_id,
            stage="before_review",
        )

        await mark_stage("generate_variants", generation_variants_started_at, detail="候选正文生成阶段完成")

        if not versions:
            await self._assert_generation_active(
                chapter,
                generation_run_id=generation_run_id,
                stage="generation_failed",
            )
            chapter.status = "failed"
            await self.session.commit()
            first_http_error = next(
                (err for err in generation_errors if isinstance(err, HTTPException)),
                None,
            )
            if first_http_error:
                raise first_http_error
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "GENERATION_ALL_CANDIDATES_FAILED",
                    "message": "章节生成失败：候选版本未达到最低成功阈值。",
                    "hint": "请在设置页执行健康检查和自动切换后重试，或降低候选版本数以提升稳定性。",
                    "retryable": True,
                    "required_success_count": required_success_count,
                    "attempts": runtime_metadata.get("generation_attempts", []),
                },
            )

        review_started_at = time.perf_counter()
        best_version_index, ai_review_result = await self._run_ai_review(
            versions=versions,
            chapter_mission=chapter_mission,
            user_id=user_id,
        )
        await mark_stage("ai_review", review_started_at, detail="AI 评审阶段完成")
        runtime_metadata["review_status"] = (ai_review_result or {}).get("status", "skipped")
        await self._update_generation_runtime(
            chapter,
            generation_run_id=generation_run_id,
            stage="review",
            message="AI 评审完成，正在整理增强处理结果",
            progress_percent=72,
            extra={
                "best_version_index": best_version_index,
                "review_status": runtime_metadata["review_status"],
                "review_skip_reason": (ai_review_result or {}).get("skip_reason"),
            },
        )
        await self._assert_generation_active(
            chapter,
            generation_run_id=generation_run_id,
            stage="after_ai_review",
        )

        review_summaries: Dict[str, Any] = {}
        if ai_review_result:
            review_summaries["ai_review"] = ai_review_result

        if versions:
            best_version_index = max(0, min(best_version_index, len(versions) - 1))
        else:
            best_version_index = 0

        if versions:
            best_version = versions[best_version_index]
            best_content = best_version["content"]
            enhanced_review_issues: List[Dict[str, Any]] = []

            if enhanced_flow and active_config.enable_six_dimension:
                try:
                    review_result = await enhanced_flow.post_generation_review(
                        project_id=project_id,
                        chapter_number=chapter_number,
                        chapter_title=outline_title,
                        chapter_content=best_content,
                        chapter_plan=json.dumps(chapter_mission, ensure_ascii=False) if chapter_mission else None,
                        previous_summary=history_context["previous_summary"],
                    )
                    review_summaries["enhanced_review"] = review_result
                    enhanced_review_issues = self._extract_enhanced_review_issues(review_result)
                except Exception as exc:  # noqa: BLE001 - degraded stage should not fail whole request
                    runtime_metadata["degraded_stages"].append({"stage": "enhanced_review", "reason": str(exc)})
                    if isinstance(exc, SQLAlchemyError):
                        await self._safe_session_rollback("enhanced_review")
                    await self._update_generation_runtime(
                        chapter,
                        generation_run_id=generation_run_id,
                        stage="review",
                        message="增强评审已降级跳过，继续后续流程",
                        progress_percent=74,
                        level="warning",
                        extra={
                            "degraded_stage": "enhanced_review",
                            "degraded_reason": self._truncate_runtime_text(exc),
                        },
                    )
                    logger.warning("Enhanced review degraded: project=%s chapter=%s error=%s", project_id, chapter_number, exc)

            if active_config.enable_self_critique:
                try:
                    self_critique_started_at = time.perf_counter()
                    await self._update_generation_runtime(
                        chapter,
                        generation_run_id=generation_run_id,
                        stage="diagnose_once",
                        message="AI 评审完成，正在准备单次诊断",
                        progress_percent=70,
                        extra={
                            "diagnosis_stage": "diagnose_once",
                            "diagnosis_stage_label": "单次诊断",
                        },
                    )
                    await self._update_generation_runtime(
                        chapter,
                        generation_run_id=generation_run_id,
                        stage="diagnose_previous_chapter",
                        message="正在整理前一章依据包，提取摘要、结尾锚点与关键片段",
                        progress_percent=72,
                        extra={
                            "diagnosis_stage": "previous_chapter",
                            "diagnosis_stage_label": "前一章依据",
                            "previous_chapter_bundle": history_context.get("previous_chapter_bundle"),
                        },
                    )
                    critique_context = {
                        "character_profiles": json.dumps(writer_blueprint.get("characters", []), ensure_ascii=False),
                        "previous_summary": history_context["previous_summary"],
                        "previous_tail": history_context.get("previous_tail"),
                        "previous_chapter_bundle": history_context.get("previous_chapter_bundle"),
                        "recent_track": history_context.get("recent_track"),
                        "plot_arc_digest": history_context.get("plot_arc_digest"),
                        "outline_title": outline_title,
                        "outline_summary": outline_summary,
                        "chapter_mission": chapter_mission,
                        "project_memory": project_memory_text,
                        "style_context": style_context,
                        "forbidden_characters": forbidden_characters,
                        "emotion_target": (chapter_mission or {}).get("emotion_target"),
                        "consistency_issues": [],
                        "guardrail_issues": (best_version.get("metadata") or {}).get("guardrail", {}).get("violations", []),
                        "enhanced_review_issues": enhanced_review_issues,
                    }
                    chapter_overview_bundle = self._build_chapter_overview_bundle(critique_context)
                    previous_overview_bundle = None
                    previous_self_critique_summary = None
                    previous_version_id: Optional[int] = None
                    if isinstance(chapter.selected_version, ChapterVersion):
                        previous_version_id = chapter.selected_version.id
                        previous_metadata = chapter.selected_version.metadata or {}
                        previous_overview_bundle = previous_metadata.get("chapter_overview") or None
                        previous_self_critique_summary = ((previous_metadata.get("review_summaries") or {}).get("self_critique") or None)
                    change_level, changed_fields = self._resolve_overview_change_level(previous_overview_bundle, chapter_overview_bundle)
                    reuse_decision = self._build_reuse_decision(change_level, changed_fields)
                    await self._update_generation_runtime(
                        chapter,
                        generation_run_id=generation_run_id,
                        stage="diagnose_context_bundle",
                        message="正在整理关联上下文，汇总章节目标、长期记忆与剧情线索",
                        progress_percent=74,
                        extra={
                            "diagnosis_stage": "context_bundle",
                            "diagnosis_stage_label": "关联上下文",
                            "chapter_overview_hash": chapter_overview_bundle.get("overview_hash"),
                            "chapter_overview_change_level": change_level,
                            "chapter_overview_changed_fields": changed_fields,
                            "chapter_overview_reuse": reuse_decision,
                        },
                    )
                    if reuse_decision.get("skip_self_critique") and previous_self_critique_summary:
                        critique_summary = self._build_reused_self_critique_summary(
                            previous_self_critique_summary,
                            reuse_decision=reuse_decision,
                            overview_bundle=chapter_overview_bundle,
                            source_version_id=previous_version_id,
                        )
                        await self._update_generation_runtime(
                            chapter,
                            generation_run_id=generation_run_id,
                            stage="optimize_content",
                            message="总览变更较小，已复用既有诊断结果并跳过重复诊断/优化",
                            progress_percent=88,
                            extra={
                                "optimization_stage": "reuse",
                                "optimization_stage_label": "复用既有诊断",
                                "optimization_issue_count": critique_summary.get("major_count", 0),
                                "optimization_dimensions": critique_summary.get("reuse_decision", {}).get("changed_fields", []),
                                "chapter_overview_reuse": reuse_decision,
                            },
                        )
                    else:
                        best_content, critique_summary = await self._run_self_critique(
                            chapter,
                            generation_run_id=generation_run_id,
                            chapter_content=best_content,
                            user_id=user_id,
                            context=critique_context,
                        )
                        critique_summary["overview_bundle"] = chapter_overview_bundle
                        critique_summary["reuse_decision"] = reuse_decision
                        await mark_stage("optimize_content", self_critique_started_at, detail="单次诊断与分阶段优化阶段完成")
                    review_summaries["self_critique"] = critique_summary
                except Exception as exc:  # noqa: BLE001 - degraded stage should not fail whole request
                    runtime_metadata["degraded_stages"].append({"stage": "self_critique", "reason": str(exc)})
                    if isinstance(exc, SQLAlchemyError):
                        await self._safe_session_rollback("self_critique")
                    await self._update_generation_runtime(
                        chapter,
                        generation_run_id=generation_run_id,
                        stage="optimize_content",
                        message="分阶段诊断/优化已降级失败，已跳过该步骤并继续后续流程",
                        progress_percent=88,
                        level="warning",
                        extra={
                            "degraded_stage": "self_critique",
                            "degraded_reason": self._truncate_runtime_text(exc),
                        },
                    )
                    logger.warning("Self critique degraded: project=%s chapter=%s error=%s", project_id, chapter_number, exc)

            if active_config.enable_reader_sim:
                try:
                    reader_feedback = await self._run_reader_simulation(
                        best_content,
                        chapter_number=chapter_number,
                        previous_summary=history_context["previous_summary"],
                        user_id=user_id,
                    )
                    review_summaries["reader_simulator"] = reader_feedback
                    reader_fix_issues = self._normalize_reader_issues_for_local_fix(reader_feedback)
                    reader_stage_decision = reader_feedback.get("reader_stage_decision") or {}
                    if (
                        reader_fix_issues
                        and (
                            not reader_stage_decision.get("passed", True)
                            or float(reader_feedback.get("overall_score", 100) or 100) < 65
                        )
                    ):
                        await self._update_generation_runtime(
                            chapter,
                            generation_run_id=generation_run_id,
                            stage="review",
                            message="读者模拟发现明显风险点，正在执行读者视角定向精修",
                            progress_percent=89,
                            extra={
                                "reader_issue_count": len(reader_fix_issues),
                                "reader_continue_ratio": reader_stage_decision.get("continue_ratio"),
                            },
                        )
                        reader_context = {
                            "outline_title": outline_title,
                            "outline_summary": outline_summary,
                            "chapter_mission": chapter_mission,
                            "previous_summary": history_context["previous_summary"],
                            "previous_tail": history_context.get("previous_tail"),
                            "previous_chapter_bundle": history_context.get("previous_chapter_bundle"),
                            "recent_track": history_context.get("recent_track"),
                            "plot_arc_digest": history_context.get("plot_arc_digest"),
                            "project_memory": project_memory_text,
                            "style_context": style_context,
                            "character_profiles": json.dumps(writer_blueprint.get("characters", []), ensure_ascii=False),
                            "emotion_target": (chapter_mission or {}).get("emotion_target"),
                            "enhanced_review_issues": enhanced_review_issues,
                            "reader_feedback_issues": reader_fix_issues,
                        }
                        reader_polish_service = SelfCritiqueService(self.session, self.llm_service, self.prompt_service)
                        polished_content = await reader_polish_service.revise_chapter(
                            chapter_content=best_content,
                            issues=reader_fix_issues,
                            context=reader_context,
                            user_id=user_id,
                        )
                        if polished_content and polished_content != best_content:
                            best_content = polished_content
                            review_summaries["reader_polish"] = {
                                "status": "applied",
                                "issue_count": len(reader_fix_issues),
                                "continue_ratio": reader_stage_decision.get("continue_ratio"),
                            }
                except Exception as exc:  # noqa: BLE001 - degraded stage should not fail whole request
                    runtime_metadata["degraded_stages"].append({"stage": "reader_simulator", "reason": str(exc)})
                    if isinstance(exc, SQLAlchemyError):
                        await self._safe_session_rollback("reader_simulator")
                    await self._update_generation_runtime(
                        chapter,
                        generation_run_id=generation_run_id,
                        stage="review",
                        message="读者模拟已降级跳过，继续后续流程",
                        progress_percent=89,
                        level="warning",
                        extra={
                            "degraded_stage": "reader_simulator",
                            "degraded_reason": self._truncate_runtime_text(exc),
                        },
                    )
                    logger.warning("Reader simulator degraded: project=%s chapter=%s error=%s", project_id, chapter_number, exc)

            if active_config.enable_consistency:
                try:
                    consistency_started_at = time.perf_counter()
                    best_content, consistency_report = await self._run_consistency_check(
                        project_id=project_id,
                        chapter_text=best_content,
                        user_id=user_id,
                    )
                    consistency_fix_issues = self._normalize_consistency_issues_for_local_fix(consistency_report)
                    if consistency_fix_issues and not consistency_report.get("auto_fix_accepted", False):
                        await self._update_generation_runtime(
                            chapter,
                            generation_run_id=generation_run_id,
                            stage="consistency",
                            message="一致性校验发现关键冲突，正在执行定向局部修复并复检",
                            progress_percent=90,
                            extra={
                                "consistency_issue_count": len(consistency_fix_issues),
                                "consistency_local_repair": True,
                            },
                        )
                        repair_context = {
                            "outline_title": outline_title,
                            "outline_summary": outline_summary,
                            "chapter_mission": chapter_mission,
                            "previous_summary": history_context["previous_summary"],
                            "previous_tail": history_context.get("previous_tail"),
                            "previous_chapter_bundle": history_context.get("previous_chapter_bundle"),
                            "recent_track": history_context.get("recent_track"),
                            "plot_arc_digest": history_context.get("plot_arc_digest"),
                            "project_memory": project_memory_text,
                            "style_context": style_context,
                            "character_profiles": json.dumps(writer_blueprint.get("characters", []), ensure_ascii=False),
                            "emotion_target": (chapter_mission or {}).get("emotion_target"),
                            "consistency_issues": consistency_fix_issues,
                            "guardrail_issues": (best_version.get("metadata") or {}).get("guardrail", {}).get("violations", []),
                            "enhanced_review_issues": enhanced_review_issues,
                        }
                        self_critique_service = SelfCritiqueService(self.session, self.llm_service, self.prompt_service)
                        repaired_content = await self_critique_service.revise_chapter(
                            chapter_content=best_content,
                            issues=consistency_fix_issues,
                            context=repair_context,
                            user_id=user_id,
                        )
                        if repaired_content and repaired_content != best_content:
                            rechecked_content, repaired_report = await self._run_consistency_check(
                                project_id=project_id,
                                chapter_text=repaired_content,
                                user_id=user_id,
                            )
                            repaired_report["repair_strategy"] = "self_critique_local_repair"
                            review_summaries["consistency_repair"] = repaired_report
                            if repaired_report.get("is_consistent") or repaired_report.get("auto_fix_accepted"):
                                best_content = rechecked_content
                                consistency_report = repaired_report
                    await mark_stage("consistency", consistency_started_at, detail="一致性校验阶段完成")
                    runtime_metadata["consistency_status"] = consistency_report.get("status", "unknown")
                    review_summaries["consistency"] = consistency_report
                except Exception as exc:  # noqa: BLE001 - degraded stage should not fail whole request
                    runtime_metadata["degraded_stages"].append({"stage": "consistency", "reason": str(exc)})
                    if isinstance(exc, SQLAlchemyError):
                        await self._safe_session_rollback("consistency")
                    await self._update_generation_runtime(
                        chapter,
                        generation_run_id=generation_run_id,
                        stage="consistency",
                        message="一致性校验已降级跳过，继续后续流程",
                        progress_percent=91,
                        level="warning",
                        extra={
                            "degraded_stage": "consistency",
                            "degraded_reason": self._truncate_runtime_text(exc),
                        },
                    )
                    logger.warning("Consistency check degraded: project=%s chapter=%s error=%s", project_id, chapter_number, exc)

            logger.info(
                "Post-generation extra stages: optimizer=%s enrichment=%s current_words=%s target=%s min=%s",
                active_config.enable_optimizer,
                active_config.enable_enrichment,
                self._count_words(best_content),
                active_config.target_word_count,
                active_config.min_word_count,
            )

            final_word_count = self._count_words(best_content)
            runtime_metadata["actual_word_count"] = final_word_count
            runtime_metadata["word_requirement_met"] = final_word_count >= active_config.min_word_count
            if runtime_metadata["word_requirement_met"]:
                if final_word_count >= active_config.target_word_count:
                    runtime_metadata["word_requirement_reason"] = "target_met"
                elif final_word_count >= max(active_config.min_word_count, int(active_config.target_word_count * 0.92)):
                    runtime_metadata["word_requirement_reason"] = "close_to_target"
                else:
                    runtime_metadata["word_requirement_reason"] = "minimum_met_but_below_target"
            else:
                runtime_metadata["word_requirement_reason"] = (
                    f"最终字数 {final_word_count} 低于最低要求 {active_config.min_word_count}，"
                    f"目标字数为 {active_config.target_word_count}。"
                )
                if active_config.enforce_min_word_count:
                    raise HTTPException(
                        status_code=422,
                        detail={
                            "code": "CHAPTER_WORD_COUNT_BELOW_MINIMUM",
                            "message": "章节生成未达到最低字数要求，已阻止静默成功落库。",
                            "hint": "请重试，或适当降低最低字数 / 目标字数后再生成。",
                            "retryable": True,
                            "current_word_count": final_word_count,
                            "min_word_count": active_config.min_word_count,
                            "target_word_count": active_config.target_word_count,
                            "stage": "enrichment" if active_config.enable_enrichment else "generation",
                        },
                    )

            best_version["content"] = best_content
            best_version_metadata = best_version.setdefault("metadata", {})
            best_version_metadata["review_summaries"] = review_summaries
            if review_summaries.get("self_critique"):
                self_critique_payload = review_summaries.get("self_critique") or {}
                best_version_metadata["chapter_overview"] = self_critique_payload.get("overview_bundle")
                best_version_metadata["chapter_overview_reuse"] = self_critique_payload.get("reuse_decision")

        await self._assert_generation_active(
            chapter,
            generation_run_id=generation_run_id,
            stage="before_persist_versions",
        )
        await self._update_generation_runtime(
            chapter,
            generation_run_id=generation_run_id,
            stage="persist_versions",
            message="正在写入候选版本并准备进入确认阶段",
            progress_percent=92,
            extra={
                "actual_word_count": runtime_metadata["actual_word_count"],
                "word_requirement_met": runtime_metadata["word_requirement_met"],
                "word_requirement_reason": runtime_metadata["word_requirement_reason"],
            },
        )
        contents = [v.get("content", "") for v in versions]
        metadata = [dict(v.get("metadata") or {}) for v in versions]
        if generation_run_id:
            for item in metadata:
                item.setdefault("generation_run_id", generation_run_id)
        persist_versions_started_at = time.perf_counter()
        versions_models = await self.novel_service.append_chapter_versions(
            chapter,
            contents,
            metadata,
            max_versions=MAX_STORED_CHAPTER_VERSIONS,
            expected_generation_run_id=generation_run_id,
        )
        await mark_stage("persist_versions", persist_versions_started_at, detail="候选版本落库阶段完成")

        variants = []
        for idx, version_model in enumerate(versions_models):
            variant = {
                "index": idx,
                "version_id": version_model.id,
                "content": version_model.content or "",
                "metadata": version_model.metadata,
            }
            variants.append(variant)

        generated_count = len(versions)
        if generated_count and len(variants) >= generated_count:
            start_index = len(variants) - generated_count
            best_version_index = start_index + max(
                0,
                min(best_version_index, generated_count - 1),
            )

        runtime_metadata["stage_timings_ms"] = stage_timings
        runtime_metadata["pipeline_total_duration_ms"] = round((time.perf_counter() - pipeline_started_at) * 1000, 2)
        logger.info(
            "Pipeline total duration: project=%s chapter=%s duration_ms=%s stages=%s",
            project_id,
            chapter_number,
            runtime_metadata["pipeline_total_duration_ms"],
            runtime_metadata["stage_timings_ms"],
        )
        self_critique_summary = review_summaries.get("self_critique") or {}
        post_consistency_summary = review_summaries.get("self_critique_after_consistency") or {}
        await self._update_generation_runtime(
            chapter,
            generation_run_id=generation_run_id,
            stage="waiting_for_confirm",
            message="候选版本已准备完成，等待确认最终版本",
            progress_percent=97,
            extra={
                "actual_word_count": runtime_metadata["actual_word_count"],
                "word_requirement_met": runtime_metadata["word_requirement_met"],
                "word_requirement_reason": runtime_metadata["word_requirement_reason"],
                "generated_version_count": len(variants),
                "best_version_index": best_version_index,
                "allowed_actions": ["confirm_version", "review_versions", "refresh_status"],
                "stage_timings_ms": runtime_metadata["stage_timings_ms"],
                "pipeline_total_duration_ms": runtime_metadata["pipeline_total_duration_ms"],
                "degraded_stages": runtime_metadata.get("degraded_stages", []),
                "self_critique_final_score": self_critique_summary.get("final_score"),
                "self_critique_improvement": self_critique_summary.get("improvement"),
                "self_critique_status": self_critique_summary.get("status"),
                "self_critique_critical_count": self_critique_summary.get("critical_count"),
                "self_critique_major_count": self_critique_summary.get("major_count"),
                "self_critique_priority_fixes": self_critique_summary.get("priority_fixes", []),
                "self_critique_after_consistency_status": post_consistency_summary.get("status"),
                "self_critique_after_consistency_improvement": post_consistency_summary.get("improvement"),
            },
        )
        return {
            "project_id": project_id,
            "chapter_number": chapter_number,
            "preset": active_config.preset,
            "best_version_index": best_version_index,
            "variants": variants,
            "review_summaries": review_summaries,
            "debug_metadata": {
                "version_count": version_count,
                "stages": self._build_stage_flags(active_config),
                "retrieval_stats": rag_stats,
                "runtime": runtime_metadata,
            },
            "runtime_metadata": runtime_metadata,
        }

    async def _resolve_config(self, flow_config: Optional[Dict[str, Any]]) -> PipelineConfig:
        flow_config = flow_config or {}
        preset = flow_config.get("preset", "basic")

        config = PipelineConfig(preset=preset)
        config.version_count = await self._resolve_version_count(flow_config.get("versions"))
        config.target_word_count = self._coerce_positive_int(flow_config.get("target_word_count"), default=3200, minimum=500)
        config.min_word_count = self._coerce_positive_int(
            flow_config.get("min_word_count"),
            default=max(500, int(config.target_word_count * 0.85)),
            minimum=200,
        )
        config.max_enrich_iterations = self._coerce_positive_int(
            flow_config.get("max_enrich_iterations"),
            default=2,
            minimum=1,
        )
        if config.min_word_count > config.target_word_count:
            config.min_word_count = config.target_word_count

        if preset in ("enhanced", "ultimate", "longform"):
            config.enable_constitution = True
            config.enable_persona = True
            config.enable_foreshadowing = True
            config.enable_faction = True
            config.rag_mode = "two_stage"

        if preset == "enhanced":
            config.enable_six_dimension = True

        if preset == "ultimate":
            config.enable_memory = True
            config.enable_consistency = True
            config.enable_enrichment = True
            config.enable_six_dimension = True
            config.enable_reader_sim = True
            config.enable_self_critique = True
            config.enable_preview = False
            config.enable_optimizer = False
            config.allow_truncated_response = True

        if preset == "longform":
            config.enable_memory = True
            config.enable_rag = True
            config.rag_mode = "two_stage"
            config.enable_enrichment = True
            config.enable_consistency = True
            config.enable_self_critique = True
            config.enable_optimizer = True
            config.enable_preview = False
            config.allow_truncated_response = True
            if flow_config.get("target_word_count") is None:
                config.target_word_count = 3000
            if flow_config.get("min_word_count") is None:
                config.min_word_count = max(1800, int(config.target_word_count * 0.75))

        if preset == "basic":
            config.enable_rag = True

        for key in (
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
            "async_finalize",
            "enable_rag",
            "enable_foreshadowing",
            "enable_faction",
            "allow_truncated_response",
            "enforce_min_word_count",
        ):
            if key in flow_config and flow_config[key] is not None:
                setattr(config, key, bool(flow_config[key]))

        if flow_config.get("rag_mode"):
            config.rag_mode = str(flow_config["rag_mode"])

        logger.info(
            "Pipeline config resolved: preset=%s enable_enrichment=%s target_words=%s min_words=%s max_enrich_iterations=%s",
            config.preset,
            config.enable_enrichment,
            config.target_word_count,
            config.min_word_count,
            config.max_enrich_iterations,
        )
        return config

    async def _ensure_provider_ready(self, user_id: int) -> Dict[str, Any]:
        metadata: Dict[str, Any] = {
            "checked": False,
            "auto_switched": False,
            "reason": "skipped",
            "current_profile_id": None,
            "current_profile_name": None,
            "active_profile_id": None,
            "active_profile_name": None,
        }
        try:
            config_service = self._create_llm_config_service()
            user_config = await config_service.get_config(user_id)
            if not user_config or not user_config.llm_provider_profiles:
                metadata["reason"] = "no_user_profiles"
                return metadata

            enabled_profiles = [profile for profile in user_config.llm_provider_profiles if getattr(profile, "enabled", True)]
            if len(enabled_profiles) == 1:
                active_profile = enabled_profiles[0]
                metadata["checked"] = False
                metadata["reason"] = "single_profile_locked_skip_preflight"
                metadata["current_profile_id"] = active_profile.id
                metadata["current_profile_name"] = active_profile.name
                metadata["active_profile_id"] = active_profile.id
                metadata["active_profile_name"] = active_profile.name
                metadata["has_usable_profile"] = True
                metadata["recommended_profile_id"] = active_profile.id
                metadata["recommended_profile_name"] = active_profile.name
                return metadata

            health = await config_service.run_health_check(user_id=user_id, include_disabled=True)
            metadata["checked"] = True
            metadata["current_profile_id"] = health.current_profile_id
            metadata["current_profile_name"] = health.current_profile_name
            metadata["active_profile_id"] = health.current_profile_id
            metadata["active_profile_name"] = health.current_profile_name
            metadata["has_usable_profile"] = health.has_usable_profile
            metadata["recommended_profile_id"] = health.recommended_profile_id
            metadata["recommended_profile_name"] = health.recommended_profile_name

            if not health.has_usable_profile:
                raise HTTPException(
                    status_code=503,
                    detail={
                        "code": "NO_AVAILABLE_PROVIDER",
                        "message": "当前没有可用的 Provider，无法执行章节生成",
                        "hint": "请在设置页执行健康检查并修复 Key、网络或额度问题",
                        "retryable": True,
                    },
                )

            current_usable = False
            if health.current_profile_id:
                current_status = next(
                    (item for item in health.profiles if item.profile_id == health.current_profile_id),
                    None,
                )
                current_usable = bool(current_status and current_status.usable)

            should_switch = (
                not current_usable
                and bool(health.recommended_profile_id)
                and health.recommended_profile_id != health.current_profile_id
            )
            if should_switch:
                switch_result = await config_service.auto_switch_provider(user_id=user_id)
                metadata["auto_switched"] = bool(switch_result.switched)
                metadata["reason"] = switch_result.reason
                metadata["active_profile_id"] = switch_result.active_profile_id
                metadata["active_profile_name"] = switch_result.active_profile_name
                if hasattr(self.session, "expire_all"):
                    self.session.expire_all()
                if not switch_result.health.has_usable_profile:
                    raise HTTPException(
                        status_code=503,
                        detail={
                            "code": "AUTO_SWITCH_FAILED_NO_PROVIDER",
                            "message": "自动切换后仍无可用 Provider，章节生成已终止",
                            "hint": switch_result.reason,
                            "retryable": True,
                        },
                    )
            else:
                metadata["reason"] = "current_profile_usable"
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001 - preflight must not block default fallback path
            logger.warning("Provider preflight failed, continue with runtime fallback: user=%s error=%s", user_id, exc)
            metadata["reason"] = "preflight_error"
            metadata["error"] = str(exc)
        return metadata

    @staticmethod
    def _build_stable_retry_config(config: PipelineConfig) -> Optional[PipelineConfig]:
        if config.preset == "stable":
            return None
        stable = PipelineConfig(**vars(config))
        stable.preset = "stable"
        stable.version_count = 1
        stable.enable_preview = False
        stable.enable_optimizer = False
        stable.enable_consistency = False
        stable.enable_enrichment = False
        stable.enable_reader_sim = False
        stable.enable_self_critique = False
        stable.enable_six_dimension = False
        stable.allow_truncated_response = True
        return stable

    @staticmethod
    def _should_retry_with_stable_config(errors: List[Exception]) -> bool:
        if not errors:
            return False
        for err in errors:
            if isinstance(err, HTTPException) and err.status_code in {408, 429, 500, 502, 503, 504}:
                return True
            if isinstance(err, (httpx.ConnectError, httpx.ReadError, httpx.TimeoutException, APIConnectionError, APITimeoutError)):
                return True
            detail_text = str(getattr(err, "detail", "") or err).lower()
            if any(keyword in detail_text for keyword in ("timeout", "connect", "readerror", "network", "服务暂时不可用")):
                return True
        return False

    @staticmethod
    def _required_success_count(requested_count: int) -> int:
        requested_count = max(1, int(requested_count or 1))
        if requested_count <= 1:
            return 1
        return max(2, (requested_count + 1) // 2)

    @staticmethod
    def _should_retry_due_to_low_success_rate(
        *,
        success_count: int,
        requested_count: int,
        required_success_count: int,
    ) -> bool:
        if requested_count <= 1:
            return success_count < required_success_count
        return success_count < required_success_count

    @staticmethod
    def _coerce_positive_int(value: Optional[Any], *, default: int, minimum: int = 1) -> int:
        if value is None:
            return default
        try:
            return max(minimum, int(value))
        except (TypeError, ValueError):
            return default

    async def _resolve_version_count(self, requested_count: Optional[int]) -> int:
        if requested_count:
            try:
                count = int(requested_count)
                return _clamp_generated_version_count(count)
            except (TypeError, ValueError):
                pass

        repo = SystemConfigRepository(self.session)
        for key in ("writer.chapter_versions", "writer.version_count"):
            record = await repo.get_by_key(key)
            if record and record.value:
                try:
                    val = int(record.value)
                    if val >= 1:
                        return _clamp_generated_version_count(val)
                except ValueError:
                    pass

        for env in ("WRITER_CHAPTER_VERSION_COUNT", "WRITER_CHAPTER_VERSIONS", "WRITER_VERSION_COUNT"):
            v = os.getenv(env)
            if v:
                try:
                    val = int(v)
                    if val >= 1:
                        return _clamp_generated_version_count(val)
                except ValueError:
                    pass

        return _clamp_generated_version_count(int(settings.writer_chapter_versions))

    async def _collect_history_context(
        self,
        *,
        project_id: str,
        chapter_number: int,
        outlines_map: Dict[int, Any],
        chapters: List[Chapter],
        user_id: int,
    ) -> Dict[str, Any]:
        chapter_fingerprint = ",".join(
            f"{item.chapter_number}:{getattr(item, 'updated_at', None) or ''}:{getattr(item, 'selected_version_id', None) or ''}"
            for item in sorted(chapters, key=lambda value: value.chapter_number)
            if item.chapter_number < chapter_number
        )
        cache_key = self._make_cache_key("history", project_id, chapter_number, chapter_fingerprint)
        cached = await self._cache_get(cache_key)
        if isinstance(cached, dict) and cached:
            return cached

        completed_summaries = []
        completed_chapters = []
        latest_prev_number = -1
        previous_summary_text = ""
        previous_tail_excerpt = ""
        previous_chapter_bundle: Dict[str, Any] = {}

        for existing in chapters:
            if existing.chapter_number >= chapter_number:
                continue
            if existing.selected_version is None or not existing.selected_version.content:
                continue

            summary_text = existing.real_summary or ""
            if not summary_text:
                outline_ref = outlines_map.get(existing.chapter_number)
                outline_summary = (getattr(outline_ref, "summary", None) or "").strip() if outline_ref else ""
                if outline_summary:
                    summary_text = outline_summary
                else:
                    summary_text = self._truncate_text(existing.selected_version.content, 220)

            completed_chapters.append(
                {
                    "chapter_number": existing.chapter_number,
                    "title": outlines_map.get(existing.chapter_number).title
                    if outlines_map.get(existing.chapter_number)
                    else f"第{existing.chapter_number}章",
                    "summary": summary_text,
                }
            )
            completed_summaries.append(summary_text)

            if existing.chapter_number > latest_prev_number:
                latest_prev_number = existing.chapter_number
                previous_summary_text = summary_text
                previous_tail_excerpt = self._extract_tail_excerpt(existing.selected_version.content)
                previous_chapter_bundle = {
                    "chapter_number": existing.chapter_number,
                    "title": outlines_map.get(existing.chapter_number).title
                    if outlines_map.get(existing.chapter_number)
                    else f"第{existing.chapter_number}章",
                    "summary": summary_text,
                    "tail_excerpt": previous_tail_excerpt,
                    "content_excerpt": self._truncate_text(existing.selected_version.content, 2500),
                }

        project_memory_text = await self._get_project_memory_text(project_id)
        recent_track = self._build_recent_chapter_track(completed_chapters)
        plot_arcs = None
        if project_memory_text and "### 剧情线追踪" in project_memory_text:
            try:
                plot_arcs_text = project_memory_text.split("### 剧情线追踪", 1)[1].strip()
                plot_arcs = json.loads(plot_arcs_text)
            except Exception:
                plot_arcs = None

        payload = {
            "completed_chapters": completed_chapters,
            "completed_summaries": completed_summaries,
            "previous_summary": previous_summary_text or "暂无（这是第一章）",
            "previous_tail": previous_tail_excerpt or "暂无（这是第一章）",
            "previous_chapter_bundle": previous_chapter_bundle or {
                "chapter_number": chapter_number - 1 if chapter_number > 1 else 0,
                "title": "暂无（这是第一章）",
                "summary": previous_summary_text or "暂无（这是第一章）",
                "tail_excerpt": previous_tail_excerpt or "暂无（这是第一章）",
                "content_excerpt": "暂无（这是第一章）",
            },
            "recent_track": recent_track,
            "plot_arc_digest": self._format_plot_arc_digest(plot_arcs),
        }
        await self._cache_set(cache_key, payload, expire=300)
        return payload

    @staticmethod
    def _extract_tail_excerpt(text: Optional[str], limit: int = 500) -> str:
        if not text:
            return ""
        stripped = text.strip()
        if len(stripped) <= limit:
            return stripped
        return stripped[-limit:]

    @staticmethod
    def _truncate_text(text: Optional[str], limit: int = 220) -> str:
        if not text:
            return ""
        cleaned = str(text).strip()
        if len(cleaned) <= limit:
            return cleaned
        return f"{cleaned[:limit].rstrip()}..."

    @classmethod
    def _build_recent_chapter_track(cls, completed_chapters: List[Dict[str, Any]], *, max_items: int = 4) -> str:
        if not completed_chapters:
            return "暂无历史章节（这是第一章）"
        ordered = sorted(completed_chapters, key=lambda item: int(item.get("chapter_number") or 0))
        recent = ordered[-max_items:]
        lines: List[str] = []
        for item in recent:
            chapter_no = int(item.get("chapter_number") or 0)
            title = str(item.get("title") or "").strip() or f"第{chapter_no}章"
            summary = cls._truncate_text(item.get("summary"), 180)
            lines.append(f"- 第{chapter_no}章《{title}》：{summary}")
        return "\n".join(lines)

    @staticmethod
    def _format_plot_arc_digest(plot_arcs: Optional[Dict[str, Any]], *, max_items: int = 5) -> str:
        if not isinstance(plot_arcs, dict) or not plot_arcs:
            return "暂无未闭环剧情线"
        lines: List[str] = []
        unresolved_hooks = plot_arcs.get("unresolved_hooks") or []
        if isinstance(unresolved_hooks, list):
            for item in unresolved_hooks[:max_items]:
                if isinstance(item, dict):
                    desc = str(item.get("description") or item.get("content") or "").strip()
                    if desc:
                        lines.append(f"- 未闭环钩子：{desc}")
        active_conflicts = plot_arcs.get("active_conflicts") or []
        if isinstance(active_conflicts, list):
            for item in active_conflicts[:max_items]:
                if isinstance(item, dict):
                    desc = str(item.get("description") or item.get("conflict") or "").strip()
                    if desc:
                        lines.append(f"- 进行中冲突：{desc}")
        if not lines:
            return "暂无未闭环剧情线"
        return "\n".join(lines[:max_items])

    @staticmethod
    def _normalize_blueprint(blueprint_dict: Dict[str, Any]) -> Dict[str, Any]:
        if "relationships" in blueprint_dict and blueprint_dict["relationships"]:
            for relation in blueprint_dict["relationships"]:
                if "character_from" in relation:
                    relation["from"] = relation.pop("character_from")
                if "character_to" in relation:
                    relation["to"] = relation.pop("character_to")
        return blueprint_dict

    async def _generate_chapter_mission(
        self,
        *,
        blueprint_dict: Dict[str, Any],
        previous_summary: str,
        previous_tail: str,
        recent_track: str,
        plot_arc_digest: str,
        outline_title: str,
        outline_summary: str,
        writing_notes: str,
        introduced_characters: List[str],
        all_characters: List[str],
        user_id: int,
    ) -> Optional[dict]:
        cache_key = self._make_cache_key(
            "chapter_mission",
            outline_title,
            outline_summary,
            writing_notes,
            previous_summary,
            previous_tail,
            recent_track,
            plot_arc_digest,
            json.dumps(introduced_characters, ensure_ascii=False),
            json.dumps(all_characters, ensure_ascii=False),
        )
        cached = await self._cache_get(cache_key)
        if isinstance(cached, dict) and cached:
            return cached

        plan_prompt = await self.prompt_service.get_prompt("chapter_plan")
        if not plan_prompt:
            logger.warning("未配置 chapter_plan 提示词，跳过导演脚本生成")
            return None

        plan_input = f"""
[近期章节轨迹]
{recent_track or "暂无"}

[未闭环剧情线]
{plot_arc_digest or "暂无"}

[上一章摘要]
{previous_summary}

[上一章结尾]
{previous_tail}

[当前章节大纲]
标题：{outline_title}
摘要：{outline_summary}

[已登场角色]
{json.dumps(introduced_characters, ensure_ascii=False) if introduced_characters else "暂无"}

[全部角色]
{json.dumps(all_characters, ensure_ascii=False)}

[写作指令]
{writing_notes}
"""

        try:
            response = await self.llm_service.get_llm_response(
                system_prompt=plan_prompt,
                conversation_history=[{"role": "user", "content": plan_input}],
                temperature=0.3,
                user_id=user_id,
                timeout=25.0,
                response_format=None,
            )
            cleaned = remove_think_tags(response)
            normalized = unwrap_markdown_json(cleaned)
            mission = json.loads(normalized)
            await self._cache_set(cache_key, mission, expire=600)
            logger.info("章节导演脚本生成完成: macro_beat=%s", mission.get("macro_beat"))
            return mission
        except Exception as exc:
            logger.warning("生成章节导演脚本失败，将使用默认模式: %s", exc)
            return None

    async def _get_rag_context(
        self,
        *,
        project_id: str,
        outline_title: str,
        outline_summary: str,
        writing_notes: str,
        user_id: int,
    ) -> Dict[str, Any]:
        if not settings.vector_store_enabled:
            return {"chunks": [], "summaries": []}

        try:
            vector_store = VectorStoreService()
        except RuntimeError as exc:
            logger.warning("向量库初始化失败，跳过 RAG: %s", exc)
            return {"chunks": [], "summaries": []}

        query_parts = [outline_title, outline_summary]
        if writing_notes:
            query_parts.append(writing_notes)
        rag_query = "\n".join(part for part in query_parts if part)

        context_service = ChapterContextService(llm_service=self.llm_service, vector_store=vector_store)
        rag_context = await context_service.retrieve_for_generation(
            project_id=project_id,
            query_text=rag_query or outline_title or outline_summary,
            user_id=user_id,
        )
        return {
            "chunks": rag_context.chunk_texts() if rag_context.chunks else [],
            "summaries": rag_context.summary_lines() if rag_context.summaries else [],
        }

    async def _get_two_stage_rag_context(
        self,
        *,
        project_id: str,
        chapter_number: int,
        writing_notes: str,
        pov_character: Optional[str],
        user_id: int,
    ) -> Tuple[Optional[str], Dict[str, Any]]:
        if not settings.vector_store_enabled:
            return None, {"mode": "two_stage", "enabled": False}

        try:
            vector_store = VectorStoreService()
        except RuntimeError as exc:
            logger.warning("向量库初始化失败，跳过两层 RAG: %s", exc)
            return None, {"mode": "two_stage", "enabled": False, "error": str(exc)}

        sync_session = getattr(self.session, "sync_session", self.session)
        retrieval_service = KnowledgeRetrievalService(sync_session, self.llm_service, vector_store)
        filtered = await retrieval_service.retrieve_and_filter(
            project_id=project_id,
            chapter_number=chapter_number,
            user_id=user_id,
            pov_character=pov_character,
            user_guidance=writing_notes,
            top_k=settings.vector_top_k_chunks,
        )
        context_text = self._format_filtered_context(filtered)
        stats = filtered.stats or {}
        stats["mode"] = "two_stage"
        return context_text, stats

    async def _get_project_memory_text(self, project_id: str) -> Optional[str]:
        cache_key = self._make_cache_key("project_memory", project_id)
        cached = await self._cache_get(cache_key)
        if isinstance(cached, str) and cached.strip():
            return cached

        result = await self.session.execute(
            select(ProjectMemory).where(ProjectMemory.project_id == project_id)
        )
        memory = result.scalars().first()
        if not memory:
            return None

        parts = []
        if memory.global_summary:
            parts.append(f"### 全局摘要\n{memory.global_summary}")
        if memory.plot_arcs:
            parts.append("### 剧情线追踪\n" + json.dumps(memory.plot_arcs, ensure_ascii=False, indent=2))
        if not parts:
            return None
        payload = "\n\n".join(parts)
        await self._cache_set(cache_key, payload, expire=300)
        return payload

    async def _get_style_context(self, project_id: str, user_id: int) -> Optional[str]:
        cache_key = self._make_cache_key("style_context", project_id, user_id)
        cached = await self._cache_get(cache_key)
        if isinstance(cached, str) and cached.strip():
            return cached

        style_service = StyleRAGService(self.session, self.llm_service)
        summary = await style_service.get_style_summary(project_id, user_id)
        if not summary.get("has_style"):
            return None

        source = summary.get("source") or {}
        source_mode = source.get("mode", "unknown")
        source_name = source.get("profile_name") or source.get("label") or ("项目章节" if source_mode == "project_chapters" else "外部参考文本")
        summary_payload = summary.get("summary") or {}
        lines = [
            f"- 来源类型：{source_mode}",
            f"- 当前风格：{source_name}",
        ]
        for key, label in [
            ("narrative", "叙事"),
            ("rhythm", "节奏"),
            ("vocabulary", "词汇"),
            ("dialogue", "对话"),
            ("sentence", "句式"),
            ("description", "描写"),
        ]:
            value = summary_payload.get(key)
            if value:
                lines.append(f"- {label}：{value}")
        lines.append("- 仅借鉴表达风格，不得照搬参考原句或覆盖项目既定剧情事实。")
        payload = "\n".join(lines)
        await self._cache_set(cache_key, payload, expire=300)
        return payload

    async def _get_writer_blueprint(self, project: NovelProject) -> Dict[str, Any]:
        chapter_count = len(project.chapters or [])
        outline_count = len(project.outlines or [])
        blueprint_updated_at = getattr(project, "updated_at", None)
        cache_key = self._make_cache_key(
            "writer_blueprint",
            project.id,
            chapter_count,
            outline_count,
            blueprint_updated_at.isoformat() if blueprint_updated_at else "",
        )
        cached = await self._cache_get(cache_key)
        if isinstance(cached, dict) and cached:
            return cached

        project_schema = await self.novel_service._serialize_project(project)
        blueprint = self._normalize_blueprint(project_schema.blueprint.model_dump())
        await self._cache_set(cache_key, blueprint, expire=300)
        return blueprint

    async def _get_memory_context(
        self,
        *,
        project_id: str,
        chapter_number: int,
        involved_characters: List[str],
    ) -> str:
        normalized_characters = sorted({name.strip() for name in involved_characters if isinstance(name, str) and name.strip()})
        cache_key = self._make_cache_key(
            "memory_context",
            project_id,
            chapter_number,
            json.dumps(normalized_characters, ensure_ascii=False),
        )
        cached = await self._cache_get(cache_key)
        if isinstance(cached, str) and cached.strip():
            return cached

        memory_layer = MemoryLayerService(self.session, self.llm_service, self.prompt_service)
        payload = await memory_layer.get_memory_context(project_id, chapter_number, normalized_characters)
        if payload and payload.strip():
            await self._cache_set(cache_key, payload, expire=180)
        return payload

    async def _build_story_guidance_context(
        self,
        *,
        project_id: str,
        chapter_number: int,
    ) -> str:
        sections: List[str] = []

        state_result = await self.session.execute(
            select(CharacterState)
            .where(
                CharacterState.project_id == project_id,
                CharacterState.chapter_number < chapter_number,
            )
            .order_by(CharacterState.chapter_number.desc(), CharacterState.id.desc())
        )
        latest_states: Dict[str, CharacterState] = {}
        for state in state_result.scalars():
            name = (state.character_name or "").strip()
            if name and name not in latest_states:
                latest_states[name] = state

        if latest_states:
            lines = []
            for name, state in list(latest_states.items())[:8]:
                parts = [f"{name}（最近出现在第{state.chapter_number}章）"]
                if state.location:
                    parts.append(f"位置：{state.location}")
                if state.emotion:
                    parts.append(f"情绪：{state.emotion}")
                if state.current_goals:
                    goals = "；".join(str(goal) for goal in state.current_goals[:2]) if isinstance(state.current_goals, list) else str(state.current_goals)
                    if goals:
                        parts.append(f"目标：{goals}")
                if state.relationship_changes:
                    relation = next((item for item in state.relationship_changes if isinstance(item, dict) and item.get("target") and item.get("change")), None)
                    if relation:
                        parts.append(f"关系变化：与{relation['target']}{relation['change']}")
                lines.append("- " + "｜".join(parts))
            sections.append("## 角色最新状态\n" + "\n".join(lines))

        event_result = await self.session.execute(
            select(TimelineEvent)
            .where(
                TimelineEvent.project_id == project_id,
                TimelineEvent.chapter_number < chapter_number,
            )
            .order_by(TimelineEvent.chapter_number.desc(), TimelineEvent.importance.desc(), TimelineEvent.id.desc())
        )
        events = list(event_result.scalars().all())[:6]
        if events:
            lines = []
            for event in events:
                title = event.event_title or "关键事件"
                detail = event.event_description or ""
                lines.append(f"- 第{event.chapter_number}章：{title}；{detail[:80]}")
            sections.append("## 最近关键事件\n" + "\n".join(lines))

        foreshadow_result = await self.session.execute(
            select(Foreshadowing)
            .where(
                Foreshadowing.project_id == project_id,
                Foreshadowing.chapter_number < chapter_number,
            )
            .order_by(Foreshadowing.chapter_number.desc(), Foreshadowing.updated_at.desc())
        )
        active_foreshadowings = [
            item for item in foreshadow_result.scalars().all()
            if item.status not in {"revealed", "resolved", "abandoned"}
        ][:6]
        if active_foreshadowings:
            lines = []
            for item in active_foreshadowings:
                target = f"；计划在第{item.target_reveal_chapter}章回收" if item.target_reveal_chapter else ""
                lines.append(f"- 第{item.chapter_number}章埋下：{(item.name or item.content or '')[:90]}{target}")
            sections.append("## 未回收伏笔\n" + "\n".join(lines))

        clue_result = await self.session.execute(
            select(StoryClue)
            .where(StoryClue.project_id == project_id)
            .order_by(StoryClue.importance.desc(), StoryClue.updated_at.desc())
        )
        active_clues = [
            clue for clue in clue_result.scalars().all()
            if clue.status not in {"resolved", "abandoned"}
        ][:6]
        if active_clues:
            lines = []
            for clue in active_clues:
                planted = f"（埋于第{clue.planted_chapter}章）" if clue.planted_chapter else ""
                lines.append(f"- {clue.name}{planted}：{(clue.description or clue.clue_content or '')[:80]}")
            sections.append("## 当前主线索/悬念\n" + "\n".join(lines))

        outline_result = await self.session.execute(
            select(ChapterOutline)
            .where(
                ChapterOutline.project_id == project_id,
                ChapterOutline.chapter_number == chapter_number,
            )
        )
        outline = outline_result.scalar_one_or_none()
        if outline:
            sections.append(
                "## 本章写作提醒\n"
                f"- 本章标题：{outline.title}\n"
                f"- 本章必须承接前文已有关系变化、未回收伏笔和线索，不要只照着摘要扩写。\n"
                f"- 如果已有关键角色状态变化，正文里必须继续推进，而不是回到蓝图初始状态。"
            )

        return "\n\n".join(section for section in sections if section).strip()

    def _apply_prompt_budget(self, sections: List[Tuple[str, str]], *, max_tokens: int = 6000) -> List[Tuple[str, str]]:
        budgeted: List[Tuple[str, str]] = []
        remaining = max_tokens
        for title, content in sections:
            estimated = self._estimate_tokens(content)
            if estimated <= remaining:
                budgeted.append((title, content))
                remaining -= estimated
                continue
            if remaining <= 0:
                continue
            approximate_chars = max(120, remaining * 4)
            truncated = self._truncate_text(content, approximate_chars)
            if truncated:
                budgeted.append((title, truncated))
                remaining = 0
        return budgeted

    @staticmethod
    def _build_prompt_sections(
        *,
        writer_blueprint: Dict[str, Any],
        previous_summary: str,
        previous_tail: str,
        chapter_mission: Optional[dict],
        rag_context: Optional[Dict[str, Any]],
        knowledge_context: Optional[str],
        outline_title: str,
        outline_summary: str,
        writing_notes: str,
        forbidden_characters: List[str],
        project_memory_text: Optional[str],
        memory_context: Optional[str],
        analysis_guidance_context: Optional[str],
        style_context: Optional[str],
        target_word_count: int,
        min_word_count: int,
    ) -> List[Tuple[str, str]]:
        blueprint_text = json.dumps(writer_blueprint, ensure_ascii=False, indent=2)
        mission_text = json.dumps(chapter_mission, ensure_ascii=False, indent=2) if chapter_mission else "无导演脚本"
        forbidden_text = json.dumps(forbidden_characters, ensure_ascii=False) if forbidden_characters else "无"

        sections: List[Tuple[str, str]] = [
            ("[世界蓝图](JSON，已裁剪)", blueprint_text),
        ]

        if project_memory_text:
            sections.append(("[项目长期记忆](摘要/剧情线)", project_memory_text))
        if memory_context:
            sections.append(("[记忆层上下文]", memory_context))
        if analysis_guidance_context:
            sections.append(("[角色/关系/伏笔/线索指导]", analysis_guidance_context))
        if style_context:
            sections.append(("[当前启用文风参考]", style_context))

        sections.extend(
            [
                ("[上一章摘要]", previous_summary or "暂无（这是第一章）"),
                ("[上一章结尾]", previous_tail or "暂无（这是第一章）"),
                ("[章节导演脚本](JSON)", mission_text),
            ]
        )

        if knowledge_context:
            sections.append(("[RAG精筛上下文](含POV裁剪)", knowledge_context))

        if rag_context:
            rag_chunks_text = "\n\n".join(rag_context.get("chunks", [])) or "未检索到章节片段"
            rag_summaries_text = "\n".join(rag_context.get("summaries", [])) or "未检索到章节摘要"
            sections.append(("[检索到的剧情上下文](Markdown)", rag_chunks_text))
            sections.append(("[检索到的章节摘要](Markdown)", rag_summaries_text))

        continuity_rules = (
            "- 开篇必须承接上一章结尾，禁止无过渡时间跳跃。\n"
            "- 角色认知边界要与前文一致，不能突然知道未知信息。\n"
            "- 本章至少推进一条既有冲突或未闭环线索。\n"
            "- 必须写出明确的情绪变化链条，不能全章一个温度。\n"
            "- 关键角色至少出现一个可感知的心理变化、关系变化或立场变化。\n"
            "- 对话必须承担试探、压迫、欺骗、暧昧、结盟、撕裂等至少一种功能，禁止空转闲聊。\n"
            "- 重要场景必须具备目标、阻碍、转折、余波，避免纯说明段落。\n"
            "- 环境描写必须服务情绪与冲突，至少调动两种感官，不要只写看见了什么。\n"
            "- 节奏必须有呼吸，紧张处短句、缓冲处留白，避免均匀段长和提纲扩写感。\n"
            "- 章末钩子要与主线相关，禁止新开无关支线，也禁止把本章冲突完全收束。"
        )
        length_rules = (
            f"- 本章初稿必须直接按目标长度写作，目标字数 {target_word_count} 字，最低不能低于 {min_word_count} 字。\n"
            f"- 不允许先写一个约 2000~3000 字的短稿再等后处理补齐，首稿就必须尽量一次写到接近目标字数。\n"
            f"- 若篇幅不足，优先在当前章既有冲突内补足场景推进、心理变化、动作过程、对话博弈、环境氛围与余波，不要偷懒用总结句跳过。\n"
            f"- 禁止为了凑字数重复表达同一信息；必须通过新增有效正文把篇幅写满。"
        )
        sections.extend(
            [
                ("[当前章节目标]", f"标题：{outline_title}\n摘要：{outline_summary}\n写作要求：{writing_notes}"),
                ("[章节长度硬约束]", length_rules),
                ("[连续性硬性约束]", continuity_rules),
                ("[禁止角色](本章不允许提及)", forbidden_text),
            ]
        )

        return sections

    @staticmethod
    def _resolve_style_hints(
        enhanced_context: Optional[Dict[str, Any]],
        version_count: int,
    ) -> List[str]:
        if enhanced_context and enhanced_context.get("version_style_hints"):
            hints = enhanced_context["version_style_hints"]
            if isinstance(hints, list) and hints:
                return hints[:version_count]
        return [
            "情绪更细腻，节奏更慢，多写内心戏和感官描写",
            "冲突更强，节奏更快，多写动作和对话",
            "悬念更重，多埋伏笔，结尾钩子更强",
        ][:version_count]

    @staticmethod
    def _resolve_pov_character(chapter_mission: Optional[dict]) -> Optional[str]:
        if not chapter_mission:
            return None
        return chapter_mission.get("pov") or chapter_mission.get("pov_character")

    async def _generate_single_version(
        self,
        *,
        index: int,
        prompt_input: str,
        writer_prompt: str,
        style_hint: Optional[str],
        project_id: str,
        chapter_number: int,
        outline_title: str,
        outline_summary: str,
        chapter_mission: Optional[dict],
        forbidden_characters: List[str],
        allowed_new_characters: List[str],
        user_id: int,
        writer_blueprint: Dict[str, Any],
        memory_context: Optional[str],
        enhanced_context: Optional[Dict[str, Any]],
        config: PipelineConfig,
    ) -> Dict[str, Any]:
        version_started_at = time.perf_counter()
        metadata: Dict[str, Any] = {
            "chapter_mission": chapter_mission,
            "style_hint": style_hint,
            "pipeline": {"preset": config.preset},
        }

        content = ""
        generation_duration_ms = 0.0
        if config.enable_preview:
            preview_started_at = time.perf_counter()
            content, preview_meta = await self._generate_with_preview(
                project_id=project_id,
                chapter_number=chapter_number,
                outline_title=outline_title,
                outline_summary=outline_summary,
                writer_blueprint=writer_blueprint,
                memory_context=memory_context,
                analysis_guidance_context=analysis_guidance_context,
                style_hint=style_hint,
                enhanced_context=enhanced_context,
                user_id=user_id,
            )
            generation_duration_ms = round((time.perf_counter() - preview_started_at) * 1000, 2)
            metadata["preview"] = preview_meta

        if not content:
            final_prompt_input = prompt_input
            final_prompt_input += (
                f"\n\n[本次输出红线]\n"
                f"- 直接输出完整章节正文，不要解释。\n"
                f"- 首稿目标字数：{config.target_word_count}；最低字数：{config.min_word_count}。\n"
                f"- 必须首稿就尽量写到接近目标字数，不能故意先写短稿留给后续扩写。"
            )
            if style_hint:
                final_prompt_input += f"\n\n[版本风格提示]\n{style_hint}"

            generation_started_at = time.perf_counter()
            try:
                response = await self.llm_service.get_llm_response(
                    system_prompt=writer_prompt,
                    conversation_history=[{"role": "user", "content": final_prompt_input}],
                    temperature=0.9,
                    user_id=user_id,
                    timeout=600.0,
                    response_format=None,
                    allow_truncated_response=config.allow_truncated_response,
                )
            except HTTPException:
                raise
            except (httpx.HTTPError, APIConnectionError, APITimeoutError, APIError) as exc:
                logger.error(
                    "Chapter generation network transport failed: project=%s chapter=%s version=%s error=%s",
                    project_id,
                    chapter_number,
                    index,
                    exc,
                    exc_info=exc,
                )
                raise HTTPException(
                    status_code=503,
                    detail={
                        "code": "PROVIDER_NETWORK_ERROR",
                        "message": "生成请求过程中与 AI 服务网络通信失败。",
                        "hint": "请检查网络连通性、Provider 状态或稍后重试。",
                        "retryable": True,
                    },
                ) from exc
            generation_duration_ms = round((time.perf_counter() - generation_started_at) * 1000, 2)
            cleaned = remove_think_tags(response)
            content = unwrap_markdown_json(cleaned)

        guardrail_check_started_at = time.perf_counter()
        guardrail_result = self.guardrails.check(
            generated_text=content,
            forbidden_characters=forbidden_characters,
            allowed_new_characters=allowed_new_characters,
            pov=chapter_mission.get("pov") if chapter_mission else None,
        )
        guardrail_check_duration_ms = round((time.perf_counter() - guardrail_check_started_at) * 1000, 2)
        guardrail_rewrite_duration_ms = 0.0
        guardrail_metadata = {"passed": guardrail_result.passed, "violations": []}

        if not guardrail_result.passed:
            guardrail_metadata["violations"] = [
                {
                    "type": v.type,
                    "severity": v.severity,
                    "description": v.description,
                    "location": v.context,
                    "context": v.context,
                }
                for v in guardrail_result.violations
            ]
            violations_text = self.guardrails.format_violations_for_rewrite(guardrail_result)
            guardrail_rewrite_started_at = time.perf_counter()
            content = await self._rewrite_with_guardrails(
                original_text=content,
                chapter_mission=chapter_mission,
                violations_text=violations_text,
                user_id=user_id,
            )
            guardrail_rewrite_duration_ms = round((time.perf_counter() - guardrail_rewrite_started_at) * 1000, 2)

        parsed_json = None
        extracted_text = None
        try:
            parsed_json = json.loads(content)
            extracted_text = self._extract_text(parsed_json)
        except Exception:
            parsed_json = None

        version_total_duration_ms = round((time.perf_counter() - version_started_at) * 1000, 2)
        metadata["timings"] = {
            "generation_ms": generation_duration_ms,
            "guardrail_check_ms": guardrail_check_duration_ms,
            "guardrail_rewrite_ms": guardrail_rewrite_duration_ms,
            "total_ms": version_total_duration_ms,
        }
        metadata["guardrail"] = guardrail_metadata
        if parsed_json is not None:
            metadata["parsed_json"] = parsed_json

        return {
            "index": index,
            "content": extracted_text or content,
            "metadata": metadata,
        }

    async def _generate_with_preview(
        self,
        *,
        project_id: str,
        chapter_number: int,
        outline_title: str,
        outline_summary: str,
        writer_blueprint: Dict[str, Any],
        memory_context: Optional[str],
        analysis_guidance_context: Optional[str],
        style_hint: Optional[str],
        enhanced_context: Optional[Dict[str, Any]],
        user_id: int,
    ) -> Tuple[str, Dict[str, Any]]:
        preview_service = PreviewGenerationService(self.session, self.llm_service, self.prompt_service)
        blueprint_context = json.dumps(writer_blueprint, ensure_ascii=False, indent=2)

        extra_constraints = []
        if enhanced_context:
            if enhanced_context.get("constitution"):
                extra_constraints.append(enhanced_context["constitution"])
            if enhanced_context.get("writer_persona"):
                extra_constraints.append(enhanced_context["writer_persona"])

        if extra_constraints:
            blueprint_context = blueprint_context + "\n\n" + "\n\n".join(extra_constraints)

        preview_result = await preview_service.generate_with_preview(
            project_id=project_id,
            chapter_number=chapter_number,
            outline={"title": outline_title, "summary": outline_summary},
            blueprint_context=blueprint_context,
            emotion_context=analysis_guidance_context or "（无额外角色/伏笔/线索指导）",
            memory_context=memory_context or "（无记忆层上下文）",
            style_hint=style_hint or "",
            user_id=user_id,
        )

        return preview_result.get("full_chapter", ""), preview_result

    async def _rewrite_with_guardrails(
        self,
        *,
        original_text: str,
        chapter_mission: Optional[dict],
        violations_text: str,
        user_id: int,
    ) -> str:
        rewrite_prompt = await self.prompt_service.get_prompt("rewrite_guardrails")
        if not rewrite_prompt:
            logger.warning("未配置 rewrite_guardrails 提示词，跳过自动修复")
            return original_text

        rewrite_input = f"""
[原文]
{original_text}

[章节导演脚本]
{json.dumps(chapter_mission, ensure_ascii=False, indent=2) if chapter_mission else "无"}

[违规列表]
{violations_text}
"""

        try:
            response = await self.llm_service.get_llm_response(
                system_prompt=rewrite_prompt,
                conversation_history=[{"role": "user", "content": rewrite_input}],
                temperature=0.3,
                user_id=user_id,
                timeout=120.0,
                response_format=None,
            )
            cleaned = remove_think_tags(response)
            return cleaned
        except Exception as exc:
            logger.warning("自动修复失败，返回原文: %s", exc)
            return original_text

    @staticmethod
    def _extract_text(value: object) -> Optional[str]:
        if not value:
            return None
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            for key in ("content", "chapter_content", "chapter_text", "text", "body", "story"):
                if value.get(key):
                    nested = PipelineOrchestrator._extract_text(value.get(key))
                    if nested:
                        return nested
            return None
        if isinstance(value, list):
            for item in value:
                nested = PipelineOrchestrator._extract_text(item)
                if nested:
                    return nested
        return None

    @staticmethod
    def _fallback_select_best_version(versions: List[Dict[str, Any]]) -> Tuple[int, Dict[str, Any]]:
        scored: List[Tuple[int, int, Dict[str, Any]]] = []
        for idx, variant in enumerate(versions):
            metadata = dict(variant.get("metadata") or {})
            guardrail = metadata.get("guardrail") or {}
            violations = guardrail.get("violations") or []
            content = variant.get("content") or ""
            word_count = len("".join(str(content).split()))
            score = word_count - len(violations) * 500
            scored.append(
                (
                    score,
                    idx,
                    {
                        "index": idx,
                        "word_count": word_count,
                        "guardrail_passed": bool(guardrail.get("passed", not violations)),
                        "guardrail_violation_count": len(violations),
                    },
                )
            )
        scored.sort(key=lambda item: (item[0], item[2]["guardrail_passed"]), reverse=True)
        best = scored[0] if scored else (0, 0, {"index": 0, "word_count": 0, "guardrail_passed": False, "guardrail_violation_count": 0})
        return best[1], {
            "strategy": "heuristic_guardrail_word_count",
            "candidates": [item[2] for item in scored],
        }

    async def _run_ai_review(
        self,
        *,
        versions: List[Dict[str, Any]],
        chapter_mission: Optional[dict],
        user_id: int,
    ) -> Tuple[int, Optional[Dict[str, Any]]]:
        contents = [v.get("content", "") for v in versions]
        try:
            ai_review_service = AIReviewService(self.llm_service, self.prompt_service)
            ai_review_result = await ai_review_service.review_versions(
                versions=contents,
                chapter_mission=chapter_mission,
                user_id=user_id,
            )
        except Exception as exc:
            logger.warning("AI 评审失败，跳过: %s", exc)
            return 0, None

        if not ai_review_result or ai_review_result.best_version_index is None:
            fallback_index, fallback_summary = self._fallback_select_best_version(versions)
            return fallback_index, {
                "best_version_index": fallback_index,
                "scores": ai_review_result.scores if ai_review_result else {},
                "evaluation": ai_review_result.overall_evaluation if ai_review_result else "AI 评审失败，已回退到规则选优",
                "flaws": ai_review_result.critical_flaws if ai_review_result else [],
                "suggestions": ai_review_result.refinement_suggestions if ai_review_result else "建议人工复核",
                "status": "fallback",
                "skip_reason": None,
                "fallback_summary": fallback_summary,
            }

        for idx, variant in enumerate(versions):
            variant.setdefault("metadata", {})["ai_review"] = {
                "is_best": idx == ai_review_result.best_version_index,
                "scores": ai_review_result.scores,
                "evaluation": ai_review_result.overall_evaluation if idx == ai_review_result.best_version_index else None,
                "flaws": ai_review_result.critical_flaws if idx == ai_review_result.best_version_index else None,
                "suggestions": ai_review_result.refinement_suggestions if idx == ai_review_result.best_version_index else None,
                "status": ai_review_result.status,
            }

        return ai_review_result.best_version_index, {
            "best_version_index": ai_review_result.best_version_index,
            "scores": ai_review_result.scores,
            "evaluation": ai_review_result.overall_evaluation,
            "flaws": ai_review_result.critical_flaws,
            "suggestions": ai_review_result.refinement_suggestions,
            "status": ai_review_result.status,
            "skip_reason": None,
        }

    async def _run_self_critique(
        self,
        chapter: Chapter,
        *,
        generation_run_id: Optional[str],
        chapter_content: str,
        user_id: int,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        service = SelfCritiqueService(self.session, self.llm_service, self.prompt_service)

        async def _report_diagnosis_progress(stage_name: str, metadata: Dict[str, Any]) -> None:
            stage_map = {
                "structural": "diagnose_structural",
                "character": "diagnose_character",
                "delivery": "diagnose_delivery",
            }
            message_map = {
                "structural": "正在执行结构诊断：聚合检查逻辑、承接与视角",
                "character": "正在执行人物诊断：聚合检查角色、关系、情绪与对话",
                "delivery": "正在执行表达诊断：聚合检查节奏、场景、悬念与文风",
            }
            runtime_stage = stage_map.get(stage_name, f"diagnose_{stage_name}")
            await self._update_generation_runtime(
                chapter,
                generation_run_id=generation_run_id,
                stage=runtime_stage,
                message=message_map.get(stage_name, "正在执行分阶段诊断"),
                progress_percent=min(79, 72 + metadata.get("batch_index", 1) * 2),
                extra={
                    "diagnosis_stage": stage_name,
                    "diagnosis_stage_label": message_map.get(stage_name, "分阶段诊断"),
                    "diagnosis_dimensions": metadata.get("dimensions"),
                    "diagnosis_batch_index": metadata.get("batch_index"),
                    "diagnosis_batch_count": metadata.get("batch_count"),
                },
            )

        async def _report_stage_optimization(stage_name: str, metadata: Dict[str, Any]) -> None:
            stage_map = {
                "structural": "optimize_structural",
                "character": "optimize_character",
                "delivery": "optimize_delivery",
            }
            message_map = {
                "structural": "正在执行结构优化：修复逻辑、承接与视角",
                "character": "正在执行人物优化：修复角色、关系、情绪与对话",
                "delivery": "正在执行表达优化：修复节奏、场景、悬念与文风",
            }
            runtime_stage = stage_map.get(stage_name, f"optimize_{stage_name}")
            await self._update_generation_runtime(
                chapter,
                generation_run_id=generation_run_id,
                stage=runtime_stage,
                message=message_map.get(stage_name, "正在执行分批优化"),
                progress_percent=min(90, 80 + len(metadata.get("dimensions", []))),
                extra={
                    "optimization_stage": stage_name,
                    "optimization_stage_label": message_map.get(stage_name, "分阶段优化"),
                    "optimization_issue_count": metadata.get("issue_count"),
                    "optimization_dimensions": metadata.get("dimensions"),
                },
            )

        critique = await service.critique_and_revise_loop(
            chapter_content=chapter_content,
            max_iterations=1,
            target_score=82.0,
            dimensions=[
                CritiqueDimension.LOGIC,
                CritiqueDimension.CONTINUITY,
                CritiqueDimension.POV,
                CritiqueDimension.CHARACTER,
                CritiqueDimension.RELATIONSHIP,
                CritiqueDimension.EMOTION,
                CritiqueDimension.DIALOGUE,
                CritiqueDimension.PACING,
                CritiqueDimension.SCENE,
                CritiqueDimension.SUSPENSE,
                CritiqueDimension.WRITING,
            ],
            context=context,
            user_id=user_id,
            progress_callback=_report_diagnosis_progress,
            stage_optimize_callback=_report_stage_optimization,
        )
        final_critique = critique.get("final_critique") or {}
        return critique.get("final_content", chapter_content), {
            "iterations": len(critique.get("iterations", [])),
            "final_score": critique.get("final_score", 0),
            "improvement": critique.get("improvement", 0),
            "status": critique.get("status", "unknown"),
            "critical_count": final_critique.get("critical_count", 0),
            "major_count": final_critique.get("major_count", 0),
            "priority_fixes": final_critique.get("priority_fixes", []),
            "final_critique": final_critique,
            "optimization_logs": critique.get("optimization_logs", []),
        }

    async def _run_reader_simulation(
        self,
        chapter_content: str,
        *,
        chapter_number: int,
        previous_summary: Optional[str],
        user_id: int,
    ) -> Dict[str, Any]:
        service = ReaderSimulatorService(self.session, self.llm_service, self.prompt_service)
        return await service.simulate_reading_experience(
            chapter_content=chapter_content,
            chapter_number=chapter_number,
            reader_types=[ReaderType.THRILL_SEEKER, ReaderType.CRITIC, ReaderType.CASUAL],
            previous_summary=previous_summary,
            user_id=user_id,
        )

    async def _run_consistency_check(
        self,
        *,
        project_id: str,
        chapter_text: str,
        user_id: int,
    ) -> Tuple[str, Dict[str, Any]]:
        service = ConsistencyService(self.session, self.llm_service)
        result = await service.check_consistency(project_id, chapter_text, user_id, include_foreshadowing=True)
        report = {
            "is_consistent": result.is_consistent,
            "status": result.status,
            "summary": result.summary,
            "check_time_ms": result.check_time_ms,
            "auto_fix_applied": False,
            "auto_fix_accepted": False,
            "violations": [
                {
                    "severity": v.severity.value if hasattr(v.severity, "value") else v.severity,
                    "category": v.category,
                    "description": v.description,
                    "location": v.location,
                    "suggested_fix": v.suggested_fix,
                    "confidence": v.confidence,
                }
                for v in result.violations
            ],
        }

        if result.status == "error":
            return chapter_text, report

        needs_fix = any(
            v.severity in (ViolationSeverity.CRITICAL, ViolationSeverity.MAJOR)
            for v in result.violations
        )
        if needs_fix:
            fixed = await service.auto_fix(project_id, chapter_text, result.violations, user_id)
            if fixed and fixed != chapter_text:
                report["auto_fix_applied"] = True
                recheck = await service.check_consistency(project_id, fixed, user_id, include_foreshadowing=True)
                report["post_fix_check"] = {
                    "status": recheck.status,
                    "is_consistent": recheck.is_consistent,
                    "summary": recheck.summary,
                    "violations": [
                        {
                            "severity": v.severity.value if hasattr(v.severity, "value") else v.severity,
                            "category": v.category,
                            "description": v.description,
                            "location": v.location,
                            "suggested_fix": v.suggested_fix,
                            "confidence": v.confidence,
                        }
                        for v in recheck.violations
                    ],
                }
                if recheck.status == "passed" and recheck.is_consistent:
                    report["auto_fix_accepted"] = True
                    return fixed, report
                report["auto_fix_accepted"] = False
                return chapter_text, report

        return chapter_text, report

    async def _run_optimizer(
        self,
        chapter_content: str,
        *,
        user_id: int,
        context: Optional[Dict[str, Any]] = None,
        dimensions: Optional[List[str]] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        prompt_map = {
            "dialogue": "optimize_dialogue",
            "psychology": "optimize_psychology",
            "rhythm": "optimize_rhythm",
        }

        optimized_content = chapter_content
        notes = []
        base_context = context or {}
        selected_dimensions = dimensions or list(prompt_map.keys())
        if len(selected_dimensions) > 2:
            selected_dimensions = selected_dimensions[:2]
        for dimension in selected_dimensions:
            prompt_name = prompt_map.get(dimension)
            if not prompt_name:
                continue
            prompt = await self.prompt_service.get_prompt(prompt_name)
            if not prompt:
                logger.warning("缺少优化提示词 %s，跳过 %s 维度", prompt_name, dimension)
                continue

            optimize_input = {
                "original_content": optimized_content,
                "characters": base_context.get("characters", []),
                "character_dna": base_context.get("character_dna", {}),
                "scene_emotion": base_context.get("scene_emotion") or base_context.get("emotion_target") or "保持本章既定情绪曲线",
                "scene_context": base_context.get("scene_context") or base_context.get("outline_summary") or "保持当前章节场景目标与冲突",
                "additional_notes": (
                    "在不改变剧情走向、信息边界和章节职责的前提下，"
                    "只优化当前维度，增强人物真实度、情绪温差、潜台词和节奏呼吸。"
                ),
            }
            try:
                response = await self.llm_service.get_llm_response(
                    system_prompt=prompt,
                    conversation_history=[{"role": "user", "content": json.dumps(optimize_input, ensure_ascii=False)}],
                    temperature=0.55,
                    user_id=user_id,
                    timeout=600.0,
                )
                cleaned = remove_think_tags(response)
                normalized = unwrap_markdown_json(cleaned)
                try:
                    parsed = json.loads(normalized)
                    optimized_content = parsed.get("optimized_content", cleaned)
                    notes.append(
                        {
                            "dimension": dimension,
                            "notes": parsed.get("optimization_notes", "优化完成"),
                        }
                    )
                except json.JSONDecodeError:
                    optimized_content = cleaned
                    notes.append({"dimension": dimension, "notes": "优化完成（响应格式非标准JSON）"})
            except Exception as exc:
                logger.warning("优化维度 %s 失败: %s", dimension, exc)

        return optimized_content, {"steps": notes}

    async def _run_enrichment(
        self,
        chapter_content: str,
        *,
        user_id: int,
        target_word_count: int = 3000,
        min_word_count: Optional[int] = None,
        max_iterations: int = 2,
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        original_word_count = self._count_words(chapter_content)
        effective_min = min_word_count if min_word_count is not None else int(target_word_count * 0.7)
        target_threshold = max(effective_min, int(target_word_count * 0.92))
        should_enrich = original_word_count < target_threshold
        logger.info(
            "Enrichment check: original_words=%s effective_min=%s target=%s threshold=%s will_enrich=%s",
            original_word_count,
            effective_min,
            target_word_count,
            target_threshold,
            should_enrich,
        )
        if not should_enrich:
            logger.info("Enrichment skipped: word count already close to target")
            return chapter_content, None

        service = EnrichmentService(self.session, self.llm_service)
        enriched_text = await service.enrich_to_target(
            chapter_text=chapter_content,
            target_word_count=target_word_count,
            user_id=user_id,
            max_iterations=max_iterations,
        )
        enriched_word_count = self._count_words(enriched_text)
        if enriched_word_count <= original_word_count:
            return chapter_content, None

        return enriched_text, {
            "original_word_count": original_word_count,
            "enriched_word_count": enriched_word_count,
            "enrichment_ratio": round(enriched_word_count / max(1, original_word_count), 4),
            "target_word_count": target_word_count,
            "min_word_count": effective_min,
            "max_iterations": max_iterations,
        }

    @staticmethod
    def _build_stage_flags(config: PipelineConfig) -> Dict[str, bool]:
        return {
            "preview": config.enable_preview,
            "optimizer": config.enable_optimizer,
            "consistency": config.enable_consistency,
            "enrichment": config.enable_enrichment,
            "constitution": config.enable_constitution,
            "persona": config.enable_persona,
            "six_dimension": config.enable_six_dimension,
            "reader_sim": config.enable_reader_sim,
            "self_critique": config.enable_self_critique,
            "memory": config.enable_memory,
            "rag": config.enable_rag,
            "rag_mode": config.rag_mode == "two_stage",
            "allow_truncated_response": config.allow_truncated_response,
            "enforce_min_word_count": config.enforce_min_word_count,
        }

    @staticmethod
    def _count_words(text: str) -> int:
        return len("".join((text or "").split()))

    @staticmethod
    def _format_filtered_context(filtered: FilteredContext) -> Optional[str]:
        if not filtered:
            return None

        sections = []
        if filtered.plot_fuel:
            sections.append("## 情节燃料\n" + "\n".join(f"- {item}" for item in filtered.plot_fuel))
        if filtered.character_info:
            sections.append("## 人物维度\n" + "\n".join(f"- {item}" for item in filtered.character_info))
        if filtered.world_fragments:
            sections.append("## 世界碎片\n" + "\n".join(f"- {item}" for item in filtered.world_fragments))
        if filtered.narrative_techniques:
            sections.append("## 叙事技法\n" + "\n".join(f"- {item}" for item in filtered.narrative_techniques))
        if filtered.warnings:
            sections.append("## 冲突警告\n" + "\n".join(f"- {item}" for item in filtered.warnings))

        if not sections:
            return "（未检索到有效上下文）"

        return "\n\n".join(sections)


__all__ = ["PipelineOrchestrator", "PipelineConfig"]
