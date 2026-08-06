# AIMETA P=写作流水线编排_统一生成入口|R=上下文汇聚_生成_审查_优化|NR=不含API路由|E=PipelineOrchestrator|X=internal|A=编排器|D=fastapi,sqlalchemy|S=db,net|RD=./README.ai
from __future__ import annotations

import json
import logging
import math
import os
import re
import asyncio
import hashlib
import time
from copy import deepcopy
from datetime import datetime, timezone
from dataclasses import asdict, dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

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
from ..services.generation_call_service import GenerationCallPolicy, call_generation_json, call_generation_text
from ..services.llm_config_service import LLMConfigService
from ..services.llm_service import LLMService
from ..services.knowledge_retrieval_service import KnowledgeRetrievalService, FilteredContext
from ..services.memory_layer_service import MemoryLayerService
from ..services.novel_service import NovelService
from ..services.longform_context_service import LongformContextPackage, LongformContextService
from ..services.preview_generation_service import PreviewGenerationService
from ..services.prompt_service import PromptService
from ..services.reader_simulator_service import ReaderSimulatorService, ReaderType
from ..services.style_rag_service import StyleRAGService
from ..services.self_critique_service import CritiqueDimension, SelfCritiqueService
from ..services.token_budget_service import TokenBudgetService
from ..services.vector_store_service import VectorStoreService
from ..services.writer_context_builder import WriterContextBuilder
from ..utils.json_utils import remove_think_tags, unwrap_markdown_json

logger = logging.getLogger(__name__)
DEFAULT_GENERATED_VERSION_COUNT = 3  # 默认生成3个并行版本
MIN_GENERATED_VERSION_COUNT = 1
MAX_GENERATED_VERSION_COUNT = 4  # 最多生成4个版本
MAX_STORED_CHAPTER_VERSIONS = 4  # 最多保存4个版本


CHAPTER_DRAFT_SUPPORTED_RANGE = {
    "min": 500,
    "standard_high_quality_min": 2500,
    "standard_high_quality_max": 7000,
    "long_chapter_max": 15000,
    "experimental_max": 30000,
    "supported_max": 50000,
}


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
    target_word_count: int = 2500
    min_word_count: int = 500
    max_enrich_iterations: int = 2
    allow_truncated_response: bool = True
    enforce_min_word_count: bool = True
    # 长章节多轮补充策略：当单轮生成字数不足时，自动触发续写
    enable_multi_round_fallback: bool = True
    multi_round_max_rounds: int = 5
    multi_round_min_increment: int = 400  # 每轮最低增量字数


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
        self.longform_context_service = LongformContextService(session)
        self.context_builder = WriterContextBuilder()
        self.guardrails = ChapterGuardrails()
        self.cache_service = CacheService(getattr(settings, "redis_url", "redis://localhost:6379/0"))
        if PipelineOrchestrator._generation_semaphore is None:
            limit = max(1, int(getattr(settings, "writer_chapter_versions", 1) or 1))
            PipelineOrchestrator._generation_semaphore = asyncio.Semaphore(max(3, min(12, limit)))
        self._config_sync_queue = None
        self._config_sync_task = None
        self._config_subscribed_user_id = None

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
        unresolved = cls._collect_unresolved_consistency_violations(report)
        for item in unresolved:
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

    @classmethod
    def _collect_unresolved_consistency_violations(cls, report: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not isinstance(report, dict):
            return []
        candidate = report
        if report.get("auto_fix_applied") and isinstance(report.get("post_fix_check"), dict):
            candidate = report.get("post_fix_check") or report
        violations = candidate.get("violations") if isinstance(candidate.get("violations"), list) else []
        unresolved: List[Dict[str, Any]] = []
        for item in violations:
            if not isinstance(item, dict):
                continue
            severity = str(item.get("severity") or "minor").strip().lower()
            if severity not in {"critical", "major"}:
                continue
            unresolved.append({
                "severity": severity,
                "category": item.get("category") or "unknown",
                "location": item.get("location") or "未知",
                "description": item.get("description") or "发现未解决的一致性问题",
                "suggested_fix": item.get("suggested_fix") or "修正该处一致性冲突并保持前后承接稳定",
            })
        return unresolved

    @classmethod
    def _summarize_consistency_severity(cls, report: Optional[Dict[str, Any]]) -> Dict[str, int]:
        unresolved = cls._collect_unresolved_consistency_violations(report)
        critical = sum(1 for item in unresolved if item.get("severity") == "critical")
        major = sum(1 for item in unresolved if item.get("severity") == "major")
        return {
            "critical": critical,
            "major": major,
            "total": len(unresolved),
            "weighted": critical * 3 + major,
        }

    @classmethod
    def _should_accept_consistency_improvement(
        cls,
        before_report: Optional[Dict[str, Any]],
        after_report: Optional[Dict[str, Any]],
    ) -> Tuple[bool, str, Dict[str, int], Dict[str, int]]:
        before_counts = cls._summarize_consistency_severity(before_report)
        after_counts = cls._summarize_consistency_severity(after_report)
        if bool((after_report or {}).get("is_consistent")) and str((after_report or {}).get("status") or "").lower() == "passed":
            return True, "fully_consistent", before_counts, after_counts
        if after_counts["critical"] <= before_counts["critical"] and after_counts["weighted"] < before_counts["weighted"]:
            return True, "reduced_unresolved_severity", before_counts, after_counts
        return False, "not_improved_enough", before_counts, after_counts

    @staticmethod
    def _summarize_self_critique_snapshot(report: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        data = report or {}
        raw_score = data.get("weighted_score", data.get("final_score", 0))
        try:
            score = float(raw_score or 0)
        except (TypeError, ValueError):
            score = 0.0
        return {
            "score": score,
            "critical": int(data.get("critical_count") or 0),
            "major": int(data.get("major_count") or 0),
            "minor": int(data.get("minor_count") or 0),
            "needs_revision": bool(data.get("needs_revision", False)),
        }

    @classmethod
    def _should_accept_self_critique_revision(
        cls,
        before_report: Optional[Dict[str, Any]],
        after_report: Optional[Dict[str, Any]],
    ) -> Tuple[bool, str, Dict[str, Any], Dict[str, Any]]:
        before = cls._summarize_self_critique_snapshot(before_report)
        after = cls._summarize_self_critique_snapshot(after_report)
        if after["critical"] > before["critical"]:
            return False, "critical_issues_increased", before, after
        if after["critical"] == before["critical"] and after["major"] > before["major"]:
            return False, "major_issues_increased", before, after
        if after["critical"] < before["critical"]:
            return True, "reduced_critical_issues", before, after
        if after["critical"] == before["critical"] and after["major"] < before["major"] and after["score"] >= before["score"] - 5:
            return True, "reduced_major_issues_without_large_score_drop", before, after
        if (
            after["critical"] == before["critical"]
            and after["major"] == before["major"]
            and after["minor"] < before["minor"]
            and after["score"] >= before["score"]
        ):
            return True, "reduced_minor_issues", before, after
        if (
            after["critical"] == before["critical"]
            and after["major"] == before["major"]
            and after["score"] > before["score"] + 1
        ):
            return True, "score_improved_without_issue_regression", before, after
        return False, "not_improved_enough", before, after

    @staticmethod
    def _content_fingerprint(text: Optional[str]) -> str:
        normalized = re.sub(r"\s+", " ", str(text or "")).strip()
        if not normalized:
            return ""
        return hashlib.sha1(normalized.encode("utf-8")).hexdigest()

    @classmethod
    def _select_quality_gate_critique_summary(cls, review_summaries: Optional[Dict[str, Any]]) -> Tuple[Dict[str, Any], str]:
        summaries = review_summaries or {}
        baseline_summary = summaries.get("self_critique") or {}
        post_consistency_summary = summaries.get("self_critique_after_consistency") or {}
        if not post_consistency_summary:
            return baseline_summary, "self_critique"
        if not baseline_summary:
            return post_consistency_summary, "self_critique_after_consistency"

        baseline_fingerprint = str(baseline_summary.get("content_fingerprint") or "").strip()
        post_fingerprint = str(post_consistency_summary.get("content_fingerprint") or "").strip()
        if baseline_fingerprint and baseline_fingerprint == post_fingerprint:
            before = cls._summarize_self_critique_snapshot(baseline_summary)
            after = cls._summarize_self_critique_snapshot(post_consistency_summary)
            if after["critical"] > before["critical"]:
                return baseline_summary, "self_critique_same_content_more_stable"
            if (
                after["critical"] == before["critical"]
                and after["major"] > before["major"]
                and after["score"] >= before["score"] - 5
            ):
                return baseline_summary, "self_critique_same_content_more_stable"

        return post_consistency_summary, "self_critique_after_consistency"

    @classmethod
    def _evaluate_structural_quality_gate_for_content(
        cls,
        *,
        review_summaries: Optional[Dict[str, Any]],
        content: str,
        violations: Optional[List[Dict[str, Any]]],
        chapter_mission: Optional[dict],
        story_guard_key: str = "story_progression_guard",
        target_word_count: int = 3000,
        min_word_count: int = 2000,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        summaries = dict(review_summaries or {})
        story_guard = cls._score_story_quality_candidate(
            content=content,
            violations=list(violations or []),
            chapter_mission=chapter_mission,
            target_word_count=target_word_count,
            min_word_count=min_word_count,
        )
        summaries[story_guard_key] = story_guard
        gate_input = dict(summaries)
        gate_input["story_progression_guard"] = story_guard
        return summaries, cls._build_structural_quality_gate(gate_input)

    QUALITY_ISSUE_LABELS = {
        "static_description_risk": "静态描写过多",
        "insufficient_dialogue_pressure": "有效对白不足",
        "chapter_progression_weak": "实质推进不足",
        "scene_fulfillment_weak": "场景兑现不足",
        "dialogue_does_not_change_state": "对白未改变局势",
        "ending_pressure_missing": "章末递压不足",
        "critical_issues_remaining": "自检严重问题未消除",
        "score_below_floor": "结构质量分过低",
        "too_many_major_issues": "主要结构问题过多",
        "critical_consistency_unresolved": "严重连续性冲突",
        "major_consistency_unresolved": "连续性冲突未处理",
        "dialogue_pressure_weak": "对白攻防不足",
        "mission_progression_weak": "本章目标命中不足",
        "word_count_far_below_target": "字数离目标过远",
        "event_density_weak": "事件密度不足",
        "state_change_interval_weak": "状态变化间隔过长",
        "scene_structure_weak": "场景结构证据不足",
        "long_chapter_event_density_weak": "长章事件密度不足",
    }

    QUALITY_ISSUE_HINTS = {
        "static_description_risk": "压缩独立景物/心理段，把篇幅改成动作回合、对话攻防和后果。",
        "insufficient_dialogue_pressure": "补足至少两轮有效对白，让人物互相施压、拒绝、让步或反制。",
        "chapter_progression_weak": "把本章目标、冲突、转折写成可见事件，而不是停留在铺陈。",
        "scene_fulfillment_weak": "逐场兑现 scene_list 的目标、阻碍、反应、转折和钩子。",
        "dialogue_does_not_change_state": "让对白造成主动权、信息量、关系、风险或下一步选择的变化。",
        "ending_pressure_missing": "结尾必须交出危险、证据、期限、误会或代价，避免总结式平收。",
        "critical_consistency_unresolved": "优先修复前后文事实冲突，再继续润色。",
        "major_consistency_unresolved": "补齐承接关系和未闭环钩子，避免章节断裂。",
        "word_count_far_below_target": "扩写只能补行动、对话、后果和短余波，不能用空泛描写凑字。",
        "event_density_weak": "把篇幅写到事件链里：行动、阻碍、反击、发现、代价和关系变化必须持续出现。",
        "state_change_interval_weak": "每个长段落窗口都要有可见变化，不能连续停在解释、回忆或氛围里。",
        "scene_structure_weak": "按目标、阻碍、转折、结果/压力逐场补齐，避免只点到场景关键词。",
        "long_chapter_event_density_weak": "长章需要更多有效场次和状态变化，不能把少量事件拉成一大章。",
    }

    @classmethod
    def _build_quality_issue_summary(
        cls,
        *,
        blockers: Optional[List[Dict[str, Any]]] = None,
        story_guard: Optional[Dict[str, Any]] = None,
        reason_codes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        items: List[Dict[str, Any]] = []
        seen = set()

        def add(code: str, source: str = "story_progression_guard", message: Optional[str] = None) -> None:
            if not code or code in seen:
                return
            seen.add(code)
            items.append({
                "code": code,
                "label": cls.QUALITY_ISSUE_LABELS.get(code, code),
                "source": source,
                "hint": cls.QUALITY_ISSUE_HINTS.get(code, message or ""),
                "message": message or "",
            })

        for blocker in blockers or []:
            if isinstance(blocker, dict):
                add(str(blocker.get("code") or ""), str(blocker.get("source") or "quality_gate"), str(blocker.get("message") or ""))
        for code in reason_codes or []:
            add(str(code or ""))

        if blockers is None and reason_codes is None:
            guard = story_guard or {}
            rich_progression_evidence = (
                float(guard.get("scene_fulfillment_rate") or 0.0) >= 0.75
                and float(guard.get("scene_structure_rate") or 0.0) >= 0.7
                and bool(guard.get("dialogue_changes_state", True))
                and bool(guard.get("ending_pressure_passed", guard.get("ending_hook_detected", True)))
                and bool(guard.get("event_density_passed", True))
                and bool(guard.get("state_change_interval_passed", True))
            )
            if guard.get("static_description_risk"):
                add("static_description_risk")
            if guard.get("expected_dialogue") and int(guard.get("dialogue_marker_count") or 0) < 4 and int(guard.get("word_count") or 0) >= 1500:
                add("insufficient_dialogue_pressure")
            if (
                int(guard.get("word_count") or 0) >= 1500
                and int(guard.get("mission_hit_count") or 0) < 2
                and not rich_progression_evidence
            ):
                add("chapter_progression_weak")
            if int(guard.get("scene_count") or 0) > 0 and float(guard.get("scene_fulfillment_rate") or 1.0) < 0.75:
                add("scene_fulfillment_weak")
            if int(guard.get("scene_count") or 0) > 0 and float(guard.get("scene_structure_rate") or 1.0) < 0.55:
                add("scene_structure_weak")
            if guard.get("expected_dialogue") and "dialogue_changes_state" in guard and not guard.get("dialogue_changes_state", True):
                add("dialogue_does_not_change_state")
            if int(guard.get("word_count") or 0) >= 1200 and not guard.get("ending_pressure_passed", guard.get("ending_hook_detected", True)):
                add("ending_pressure_missing")
            if int(guard.get("word_count") or 0) >= 1800 and guard.get("event_density_passed") is False:
                add("event_density_weak")
            if int(guard.get("word_count") or 0) >= 2500 and guard.get("state_change_interval_passed") is False:
                add("state_change_interval_weak")
            if int(guard.get("word_count") or 0) >= 7000 and guard.get("long_chapter_density_passed") is False:
                add("long_chapter_event_density_weak")

        tone = "success"
        if len(items) >= 2 or any(item["code"] in {"static_description_risk", "critical_consistency_unresolved"} for item in items):
            tone = "danger"
        elif items:
            tone = "warning"

        return {
            "passed": not items,
            "tone": tone,
            "count": len(items),
            "codes": [item["code"] for item in items],
            "labels": [item["label"] for item in items],
            "items": items,
        }

    @classmethod
    def _attach_quality_gate_status_to_guard(
        cls,
        story_guard: Dict[str, Any],
        structural_quality_gate: Dict[str, Any],
    ) -> Dict[str, Any]:
        guard = deepcopy(story_guard or {})
        gate_passed = bool(structural_quality_gate.get("passed", True))
        gate_summary = {
            "passed": gate_passed,
            "codes": list(structural_quality_gate.get("quality_issue_codes") or []),
            "labels": list(structural_quality_gate.get("quality_issue_labels") or []),
            "blocker_count": len(structural_quality_gate.get("blockers") or []),
        }
        guard["quality_gate_passed"] = gate_passed
        guard["quality_gate_summary"] = gate_summary
        guard["quality_gate_codes"] = gate_summary["codes"]
        guard["quality_gate_labels"] = gate_summary["labels"]

        snapshot = dict(guard.get("quality_metric_snapshot") or {})
        raw_summary = snapshot.get("quality_issue_summary") or guard.get("quality_issue_summary")
        if gate_passed and isinstance(raw_summary, dict) and not raw_summary.get("passed", True):
            warning_summary = deepcopy(raw_summary)
            guard["quality_rule_warnings"] = warning_summary
            snapshot["quality_rule_warnings"] = warning_summary
            clean_summary = {
                "passed": True,
                "tone": "success",
                "count": 0,
                "codes": [],
                "labels": [],
                "items": [],
            }
            guard["quality_issue_summary"] = clean_summary
            guard["quality_issue_codes"] = []
            guard["quality_issue_labels"] = []
            snapshot["quality_issue_summary"] = clean_summary
            snapshot["quality_issue_codes"] = []
            snapshot["quality_issue_labels"] = []
        if snapshot:
            snapshot["quality_gate_passed"] = gate_passed
            snapshot["quality_gate_summary"] = gate_summary
            guard["quality_metric_snapshot"] = snapshot
        return guard

    @classmethod
    def _build_structural_quality_gate(cls, review_summaries: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        summaries = review_summaries or {}
        critique_summary, critique_source = cls._select_quality_gate_critique_summary(summaries)
        consistency_summary = summaries.get("consistency_repair") or summaries.get("consistency") or {}
        ai_review_summary = summaries.get("ai_review") if isinstance(summaries.get("ai_review"), dict) else {}
        ai_review_text = " ".join(
            str(ai_review_summary.get(key) or "")
            for key in ("evaluation", "suggestions", "final_recommendation", "status")
        )
        ai_scene_supports_pass = any(
            marker in ai_review_text
            for marker in (
                "基本兑现",
                "结构兑现",
                "结构兑现度高",
                "兑现了导演脚本",
                "导演脚本兑现",
                "完成度较高",
                "推进清晰",
                "四场戏推进清晰",
                "结构清晰",
                "能直接上正稿",
                "可用",
                "结尾",
                "压给下一章",
                "递给下一章",
            )
        )
        unresolved_consistency = cls._collect_unresolved_consistency_violations(consistency_summary)
        critical_consistency = [item for item in unresolved_consistency if item.get("severity") == "critical"]
        major_consistency = [item for item in unresolved_consistency if item.get("severity") == "major"]

        critique_score = critique_summary.get("final_score")
        try:
            critique_score = float(critique_score) if critique_score is not None else None
        except (TypeError, ValueError):
            critique_score = None
        critique_critical = int(critique_summary.get("critical_count") or 0)
        critique_major = int(critique_summary.get("major_count") or 0)

        blockers: List[Dict[str, Any]] = []
        if critique_critical > 1:
            blockers.append({
                "source": "self_critique",
                "code": "critical_issues_remaining",
                "message": f"自检后仍残留 {critique_critical} 个 critical 问题，不能静默放行。",
            })
        if critique_score is not None and critique_score < 42:
            blockers.append({
                "source": "self_critique",
                "code": "score_below_floor",
                "message": f"自检最终分仅 {critique_score:.1f}，低于结构质量底线。",
            })
        if critique_major >= 12:
            blockers.append({
                "source": "self_critique",
                "code": "too_many_major_issues",
                "message": f"自检后仍有 {critique_major} 个 unique major 问题，说明文本仍存在大面积结构缺陷。",
            })
        if critical_consistency:
            blockers.append({
                "source": "consistency",
                "code": "critical_consistency_unresolved",
                "message": f"一致性校验仍残留 {len(critical_consistency)} 个 critical 冲突。",
                "examples": [item.get("description") for item in critical_consistency[:3]],
            })
        if len(major_consistency) >= 5:
            blockers.append({
                "source": "consistency",
                "code": "major_consistency_unresolved",
                "message": f"一致性校验仍残留 {len(major_consistency)} 个 major 冲突。",
                "examples": [item.get("description") for item in major_consistency[:3]],
            })

        story_guard = summaries.get("story_progression_guard") if isinstance(summaries.get("story_progression_guard"), dict) else {}
        if story_guard:
            story_word_count = int(story_guard.get("word_count") or 0)
            story_dialogue_markers = int(story_guard.get("dialogue_marker_count") or 0)
            story_mission_hits = int(story_guard.get("mission_hit_count") or 0)
            scene_count = int(story_guard.get("scene_count") or 0)
            scene_rate = float(story_guard.get("scene_fulfillment_rate") or 1.0)
            scene_structure_rate = float(story_guard.get("scene_structure_rate") or 1.0)
            rich_progression_evidence = (
                scene_count > 0
                and scene_rate >= 0.75
                and scene_structure_rate >= 0.7
                and story_dialogue_markers >= 8
                and not story_guard.get("static_description_risk")
                and story_guard.get("dialogue_changes_state", True)
                and story_guard.get("ending_pressure_passed", story_guard.get("ending_hook_detected", True))
                and story_guard.get("event_density_passed", True)
                and story_guard.get("state_change_interval_passed", True)
            )
            if story_guard.get("static_description_risk"):
                blockers.append({
                    "source": "story_progression_guard",
                    "code": "static_description_risk",
                    "message": "章节主体缺少有效对话/动作承压，存在大段静态描写硬撑篇幅的风险。",
                })
            if story_guard.get("chapter_artifact_markers"):
                blockers.append({
                    "source": "story_progression_guard",
                    "code": "chapter_artifact_markers",
                    "message": "章节正文含有提纲/标记残留，不能作为成品章节放行。",
                })
            if story_guard.get("expected_dialogue") and story_word_count >= 1500 and story_dialogue_markers < 4:
                blockers.append({
                    "source": "story_progression_guard",
                    "code": "insufficient_dialogue_pressure",
                    "message": "导演脚本要求存在对话/攻防，但正文里的有效对白痕迹过少，局势博弈不足。",
                })
            progression_soft_pass = (
                story_dialogue_markers >= 8
                and not story_guard.get("static_description_risk")
                and story_guard.get("dialogue_changes_state", False)
                and story_guard.get("ending_pressure_passed", story_guard.get("ending_hook_detected", False))
                and critique_critical <= 1
                and (critique_score is None or critique_score >= 70)
                and len(critical_consistency) == 0
                and len(major_consistency) < 2
            )
            if (
                story_word_count >= 1500
                and story_mission_hits < 2
                and not progression_soft_pass
                and not rich_progression_evidence
                and (critique_score is not None and critique_score < 72)
            ):
                blockers.append({
                    "source": "story_progression_guard",
                    "code": "chapter_progression_weak",
                    "message": "正文对本章目标、冲突、转折的命中不足，容易读起来像铺陈多、实质推进少。",
                })
            scene_soft_pass = (
                (
                    story_mission_hits >= 3
                    or (
                        ai_scene_supports_pass
                        and story_mission_hits >= 2
                        and story_dialogue_markers >= 8
                        and (critique_score is None or critique_score >= 70)
                    )
                )
                and story_dialogue_markers >= 4
                and not story_guard.get("static_description_risk")
                and story_guard.get("dialogue_changes_state", True)
                and story_guard.get("ending_pressure_passed", story_guard.get("ending_hook_detected", True))
                and critique_critical <= 1
                and (critique_score is None or critique_score >= 60)
                and not critical_consistency
            )
            semantic_scene_soft_pass = (
                ai_scene_supports_pass
                and progression_soft_pass
                and story_dialogue_markers >= 10
                and story_guard.get("event_density_passed", True)
                and story_guard.get("state_change_interval_passed", True)
                and critique_critical <= 1
                and critique_major < 8
                and not critical_consistency
                and len(major_consistency) < 2
            )
            dense_scene_soft_pass = (
                scene_rate >= 0.75
                and story_dialogue_markers >= 8
                and not story_guard.get("static_description_risk")
                and story_guard.get("dialogue_changes_state", True)
                and story_guard.get("ending_pressure_passed", story_guard.get("ending_hook_detected", True))
                and story_guard.get("event_density_passed", True)
                and story_guard.get("state_change_interval_passed", True)
                and critique_critical <= 1
                and (critique_score is None or critique_score >= 70)
                and not critical_consistency
                and len(major_consistency) < 2
            )
            scene_soft_pass = bool(scene_soft_pass or semantic_scene_soft_pass or dense_scene_soft_pass)
            if (
                story_word_count >= 1200
                and scene_count > 0
                and "scene_fulfillment_rate" in story_guard
                and scene_rate < 0.5
                and not scene_soft_pass
            ):
                blockers.append({
                    "source": "story_progression_guard",
                    "code": "scene_fulfillment_weak",
                    "message": "正文对导演脚本 scene_list 的目标、阻碍、转折、钩子兑现不足，章节像散段而不是完整戏剧单元。",
                })
            if (
                story_word_count >= 1800
                and scene_count > 0
                and "scene_structure_rate" in story_guard
                and scene_structure_rate < 0.45
                and not scene_soft_pass
            ):
                blockers.append({
                    "source": "story_progression_guard",
                    "code": "scene_structure_weak",
                    "message": "正文虽然可能点到了场景关键词，但缺少目标、阻碍、转折、结果/压力的结构证据。",
                })
            if (
                story_guard.get("expected_dialogue")
                and "dialogue_changes_state" in story_guard
                and not story_guard.get("dialogue_changes_state", True)
            ):
                blockers.append({
                    "source": "story_progression_guard",
                    "code": "dialogue_does_not_change_state",
                    "message": "正文虽然可能有对话痕迹，但缺少逼问、拒绝、让步、暴露、决断等局势变化，对话没有真正推动剧情。",
                })
            if (
                story_word_count >= 1200
                and ("ending_pressure_passed" in story_guard or "ending_hook_detected" in story_guard)
                and not story_guard.get("ending_pressure_passed", story_guard.get("ending_hook_detected"))
            ):
                blockers.append({
                    "source": "story_progression_guard",
                    "code": "ending_pressure_missing",
                    "message": "章节结尾没有把压力、危险、误会、证据或后果递给下一章，容易平收。",
                })
            density_soft_pass = (
                story_dialogue_markers >= 8
                and story_mission_hits >= 3
                and story_guard.get("dialogue_changes_state", True)
                and story_guard.get("ending_pressure_passed", story_guard.get("ending_hook_detected", True))
                and not story_guard.get("static_description_risk")
            )
            if (
                story_word_count >= 1800
                and story_guard.get("event_density_passed") is False
                and not density_soft_pass
            ):
                blockers.append({
                    "source": "story_progression_guard",
                    "code": "event_density_weak",
                    "message": "正文篇幅没有稳定长在行动、对话、发现、代价和关系变化上，存在低事件密度风险。",
                })
            if (
                story_word_count >= 2500
                and story_guard.get("state_change_interval_passed") is False
                and not density_soft_pass
            ):
                blockers.append({
                    "source": "story_progression_guard",
                    "code": "state_change_interval_weak",
                    "message": "章节中存在过长区间没有可见状态变化，读感容易变成解释或氛围拉长。",
                })
            if (
                story_word_count >= 7000
                and story_guard.get("long_chapter_density_passed") is False
                and not density_soft_pass
            ):
                blockers.append({
                    "source": "story_progression_guard",
                    "code": "long_chapter_event_density_weak",
                    "message": "长章目标下事件密度和状态变化窗口不足，不能把少量事件拉成长章静默放行。",
                })

        quality_issue_summary = cls._build_quality_issue_summary(
            blockers=blockers,
            story_guard=story_guard,
        )

        return {
            "passed": not blockers,
            "blockers": blockers,
            "quality_issue_summary": quality_issue_summary,
            "quality_issue_labels": quality_issue_summary.get("labels", []),
            "quality_issue_codes": quality_issue_summary.get("codes", []),
            "selected_critique_source": critique_source,
            "self_critique_final_score": critique_score,
            "self_critique_critical_count": critique_critical,
            "self_critique_major_count": critique_major,
            "self_critique_raw_issue_count": critique_summary.get("raw_issue_count"),
            "self_critique_deduped_issue_count": critique_summary.get("deduped_issue_count"),
            "self_critique_merged_issue_count": critique_summary.get("merged_issue_count"),
            "baseline_self_critique_major_count": (summaries.get("self_critique") or {}).get("major_count"),
            "post_consistency_self_critique_major_count": (summaries.get("self_critique_after_consistency") or {}).get("major_count"),
            "consistency_unresolved_count": len(unresolved_consistency),
            "consistency_unresolved_critical_count": len(critical_consistency),
            "consistency_unresolved_major_count": len(major_consistency),
            "story_progression_guard": story_guard,
        }

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
    def _build_structural_reader_polish_issues(story_guard: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        guard = story_guard or {}
        issues: List[Dict[str, Any]] = []
        if guard.get("static_description_risk"):
            issues.append({
                "dimension": "structure",
                "severity": "critical",
                "location": "整章",
                "problem": "静态描写风险过高，正文缺少动作、对话和局势变化承压。",
                "suggestion": "压缩独立景物/心理段，把篇幅改写成行动回合、对话攻防和因果后果。",
                "example": "不要润色原有描写，优先补出人物做什么、对方如何反应、局势如何变化。",
            })
        if int(guard.get("scene_count") or 0) > 0 and float(guard.get("scene_fulfillment_rate") or 1.0) < 0.75:
            issues.append({
                "dimension": "structure",
                "severity": "major",
                "location": "场景链",
                "problem": "导演脚本场景兑现不足，目标、阻碍、转折或钩子没有逐场落地。",
                "suggestion": "按 scene_list 补齐目标->阻碍->反应->转折->后果，不能只做句子润色。",
                "example": "每一场至少写出一个明确变化：信息量、主动权、关系、风险或下一步选择。",
            })
        if guard.get("event_density_passed") is False or guard.get("state_change_interval_passed") is False:
            issues.append({
                "dimension": "pacing",
                "severity": "major",
                "location": "正文中段",
                "problem": "事件密度或状态变化间隔不足，篇幅没有稳定长在剧情推进上。",
                "suggestion": "把空转段改成行动、阻碍、反制、发现、代价、关系变化或短余波决策。",
                "example": "每个长窗口至少出现一次新信息、主动权变化、风险升级或伏笔兑现。",
            })
        if guard.get("expected_dialogue") and not guard.get("dialogue_changes_state", True):
            issues.append({
                "dimension": "dialogue",
                "severity": "major",
                "location": "对话场",
                "problem": "对话没有改变局势，只是在交换信息或解释设定。",
                "suggestion": "改成至少两轮攻防，并让其中一轮造成逼问、拒绝、让步、暴露、误导或决断。",
                "example": "一方提出压力，另一方拒绝/反制，主角据此改变策略或付出代价。",
            })
        if not guard.get("ending_pressure_passed", guard.get("ending_hook_detected", True)):
            issues.append({
                "dimension": "suspense",
                "severity": "major",
                "location": "章末",
                "problem": "结尾没有把压力、危险、误会、证据或后果递给下一章。",
                "suggestion": "把结尾改成具体压力载体：一句话、一件证据、一个期限、一次失手或门外新动静。",
                "example": "禁止总结感悟和平静落幕，最后一拍必须让下一章更急、更险或更难。",
            })
        return issues

    @staticmethod
    def _should_run_reader_polish(
        feedback: Optional[Dict[str, Any]],
        issues: Optional[List[Dict[str, Any]]],
    ) -> Tuple[bool, Dict[str, Any]]:
        issue_count = len(issues or [])
        stage_decision = ((feedback or {}).get("reader_stage_decision") or {}) if isinstance(feedback, dict) else {}
        diagnostic_summary = ((feedback or {}).get("diagnostic_summary") or {}) if isinstance(feedback, dict) else {}
        overall_score = float((feedback or {}).get("overall_score", 100) or 100)
        continue_ratio = float(stage_decision.get("continue_ratio", diagnostic_summary.get("continue_ratio", 1)) or 0)
        top_issue_count = int(stage_decision.get("top_issue_count", len(diagnostic_summary.get("priority_issues") or [])) or 0)
        passed = bool(stage_decision.get("passed", True))
        abandon_risk_count = len((feedback or {}).get("abandon_risks") or []) if isinstance(feedback, dict) else 0

        decision = {
            "triggered": False,
            "reason": None,
            "issue_count": issue_count,
            "overall_score": overall_score,
            "continue_ratio": continue_ratio,
            "top_issue_count": top_issue_count,
            "passed": passed,
            "abandon_risk_count": abandon_risk_count,
        }
        if issue_count <= 0:
            decision["reason"] = "no_priority_issues"
            return False, decision
        if not passed or overall_score < 65:
            decision["triggered"] = True
            decision["reason"] = "reader_stage_failed"
            return True, decision
        if continue_ratio < 0.67:
            decision["triggered"] = True
            decision["reason"] = "low_continue_ratio"
            return True, decision
        if top_issue_count >= 3 and overall_score < 75:
            decision["triggered"] = True
            decision["reason"] = "multiple_priority_issues_under_soft_floor"
            return True, decision
        decision["reason"] = "reader_feedback_within_tolerance"
        return False, decision

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
        for key in ("kind", "title", "summary", "content_preview"):
            value = event.get(key)
            if value:
                compact_event[key] = cls._truncate_runtime_text(value, 520 if key == "content_preview" else 220)
        if event.get("progress_percent") is not None:
            compact_event["progress_percent"] = event.get("progress_percent")
        for key in ("metrics", "artifact_refs", "developer_detail"):
            value = event.get(key)
            if isinstance(value, (dict, list)) and value:
                compact_event[key] = cls._compact_runtime_value(value)
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
    def _resolve_chapter_draft_contract(target_word_count: int, min_word_count: Optional[int] = None) -> Dict[str, Any]:
        target = max(CHAPTER_DRAFT_SUPPORTED_RANGE["min"], int(target_word_count or 0))
        minimum = max(200, int(min_word_count if min_word_count is not None else int(target * 0.5)))
        if minimum > target:
            minimum = target

        if target < 1200:
            tier = "short"
            strategy = "single_pass_compact"
            scene_min, scene_max = 1, 2
        elif target < 2500:
            tier = "lean"
            strategy = "single_pass_scene_led"
            scene_min, scene_max = 2, 3
        elif target < 4500:
            tier = "standard"
            strategy = "single_pass_scene_led"
            scene_min, scene_max = 3, 4
        elif target < 7000:
            tier = "rich"
            strategy = "single_pass_scene_led_with_retry_gate"
            scene_min, scene_max = 4, 5
        elif target < 10000:
            tier = "long"
            strategy = "single_pass_grouped_scenes_with_fusion_check"
            scene_min, scene_max = 5, 7
        elif target < 20000:
            tier = "extra_long"
            strategy = "single_pass_grouped_scenes_with_strict_fusion_check"
            scene_min, scene_max = 6, 8
        elif target < 35000:
            tier = "ultra_long"
            strategy = "multi_pass_segmented_with_bridge_continuity"
            scene_min, scene_max = 8, 14
        else:
            tier = "mega_long"
            strategy = "multi_pass_segmented_with_dedicated_continuity_gates"
            scene_min, scene_max = 12, 20

        return {
            "target_word_count": target,
            "min_word_count": minimum,
            "supported_range": dict(CHAPTER_DRAFT_SUPPORTED_RANGE),
            "tier": tier,
            "generation_strategy": strategy,
            "recommended_scene_count_min": scene_min,
            "recommended_scene_count_max": scene_max,
            "preferred_floor": max(minimum, int(target * 0.92)),
            "retry_floor": max(minimum, int(target * (0.9 if target >= 4500 else 0.86))),
            "quality_policy": "first_draft_must_carry_length_with_scene_action_dialogue_and_turns",
        }

    @classmethod
    def _format_chapter_draft_contract_for_prompt(cls, target_word_count: int, min_word_count: int) -> str:
        contract = cls._resolve_chapter_draft_contract(target_word_count, min_word_count)
        supported = contract["supported_range"]
        return (
            "CHAPTER_DRAFT_CONTRACT\n"
            f"- target_chars: {contract['target_word_count']}; minimum_chars: {contract['min_word_count']}; "
            f"preferred_floor: {contract['preferred_floor']}.\n"
            f"- supported_range_chars: {supported['min']}-{supported['experimental_max']} "
            f"(standard high-quality range {supported['standard_high_quality_min']}-{supported['standard_high_quality_max']}, "
            f"long chapter range up to {supported['long_chapter_max']}).\n"
            f"- generation_strategy: {contract['generation_strategy']}; tier: {contract['tier']}.\n"
            f"- recommended_scene_count: {contract['recommended_scene_count_min']}-{contract['recommended_scene_count_max']} "
            "real scenes or scene groups. Do not pad with static scenery, repeated thoughts, or synopsis.\n"
            "- Every 900-1500 chars should contain a concrete state change: action pressure, dialogue leverage, discovery, cost, relationship shift, or payoff.\n"
            "- For long chapters, keep one continuous chapter voice: grouped scenes are planning units, not separate disconnected fragments."
        )

    @staticmethod
    def _resolve_chapter_generation_timeout(target_word_count: int) -> float:
        """Scale the main chapter LLM timeout to the requested length.

        Short test/quick chapters must not inherit the old fixed 600s budget; that
        made 700-word requests appear frozen. Long-form chapters still keep the
        former upper bound.
        """
        words = max(500, int(target_word_count or 0))
        if words < 1200:
            return 120.0
        if words < 2500:
            return 200.0
        if words < 4000:
            return 600.0
        if words < 5500:
            return 900.0
        if words < 7500:
            return 1200.0
        if words < 10000:
            return 1800.0
        if words < 12500:
            return 2400.0
        return 3000.0

    @staticmethod
    def _resolve_chapter_generation_soft_timeout(target_word_count: int) -> Optional[float]:
        """Abort a single provider attempt before the whole background task looks frozen."""
        words = max(500, int(target_word_count or 0))
        if words < 4000:
            return None
        if words < 7500:
            return 540.0
        if words < 10000:
            return 720.0
        if words < 12500:
            return 900.0
        return 1080.0

    @staticmethod
    def _resolve_chapter_mission_timeout(target_word_count: int) -> float:
        """Give long-form director-script generation enough time to avoid fallback.

        The mission JSON is much shorter than the final prose, but for 5k-word
        ultimate chapters the planning prompt still carries heavy context. A fixed
        60s budget has proven too tight in real runs and causes unnecessary
        fallback to the default mission mode.
        """
        words = max(500, int(target_word_count or 0))
        if words < 1200:
            return 30.0
        if words < 2500:
            return 45.0
        if words < 4000:
            return 90.0
        if words < 5500:
            return 120.0
        if words < 7500:
            return 180.0
        if words < 10000:
            return 240.0
        return 300.0

    @staticmethod
    @staticmethod
    def _resolve_chapter_mission_max_tokens(target_word_count: int) -> int:
        words = max(500, int(target_word_count or 0))
        if words < 2500:
            return 3200
        if words < 5500:
            return 4800
        if words < 9000:
            return 6400
        return 8000
    @staticmethod
    def _build_chapter_mission_schema() -> Dict[str, Any]:
        string_array = {"type": "array", "items": {"type": "string"}}
        nullable_string = {"type": ["string", "null"]}
        scene_schema = {
            "type": "object",
            "required": [
                "scene",
                "goal",
                "conflict",
                "turn",
                "outcome",
                "payoff",
                "bridge",
                "dialogue_value",
                "end_hook",
                "word_budget",
            ],
            "properties": {
                "scene": {"type": "string"},
                "goal": {"type": "string"},
                "conflict": {"type": "string"},
                "turn": {"type": "string"},
                "outcome": {"type": "string"},
                "payoff": {"type": "string"},
                "bridge": {"type": "string"},
                "dialogue_value": {"type": "string"},
                "end_hook": {"type": "string"},
                "word_budget": {"type": "integer"},
                "characters": string_array,
                "foreshadowing_task": nullable_string,
            },
        }
        return {
            "type": "object",
            "required": [
                "macro_beat",
                "chapter_purpose",
                "character_arc_task",
                "continuity_anchor",
                "dialogue_strategy",
                "scene_list",
                "foreshadowing_tasks",
            ],
            "properties": {
                "macro_beat": {"type": "string"},
                "chapter_purpose": {"type": "string"},
                "pov": nullable_string,
                "character_focus": string_array,
                "character_arc_task": {"type": "string"},
                "continuity_anchor": {
                    "type": "object",
                    "required": ["inherit_from_previous", "deliver_to_next"],
                    "properties": {
                        "inherit_from_previous": string_array,
                        "deliver_to_next": string_array,
                    },
                },
                "dialogue_strategy": {
                    "type": "object",
                    "required": ["purpose", "subtext", "pressure_change"],
                    "properties": {
                        "purpose": string_array,
                        "subtext": string_array,
                        "pressure_change": {"type": "string"},
                    },
                },
                "scene_list": {
                    "type": "array",
                    "items": scene_schema,
                },
                "foreshadowing_tasks": {
                    "type": "object",
                    "required": ["must_resolve", "should_reinforce", "may_plant", "avoid_forgetting"],
                    "properties": {
                        "must_resolve": string_array,
                        "should_reinforce": string_array,
                        "may_plant": string_array,
                        "avoid_forgetting": string_array,
                    },
                },
                "sequel_required": {"type": "boolean"},
                "sequel_description": nullable_string,
            },
        }

    @classmethod
    def _normalize_chapter_mission(cls, mission: Dict[str, Any], target_word_count: int) -> Dict[str, Any]:
        normalized = dict(mission or {})
        draft_contract = cls._resolve_chapter_draft_contract(target_word_count, max(500, int(target_word_count * 0.9)))

        continuity = normalized.get("continuity_anchor")
        if not isinstance(continuity, dict):
            continuity = {}
        continuity["inherit_from_previous"] = [
            str(item).strip()
            for item in (continuity.get("inherit_from_previous") or [])
            if str(item).strip()
        ][:5]
        continuity["deliver_to_next"] = [
            str(item).strip()
            for item in (continuity.get("deliver_to_next") or [])
            if str(item).strip()
        ][:5]
        normalized["continuity_anchor"] = continuity

        dialogue_strategy = normalized.get("dialogue_strategy")
        if not isinstance(dialogue_strategy, dict):
            dialogue_strategy = {}
        for key in ("purpose", "subtext"):
            value = dialogue_strategy.get(key)
            if isinstance(value, str):
                dialogue_strategy[key] = [value]
            elif isinstance(value, list):
                dialogue_strategy[key] = [str(item).strip() for item in value if str(item).strip()][:5]
            else:
                dialogue_strategy[key] = []
        dialogue_strategy["pressure_change"] = str(dialogue_strategy.get("pressure_change") or "对白必须改变主动权、信息量或风险").strip()
        normalized["dialogue_strategy"] = dialogue_strategy

        foreshadowing_tasks = normalized.get("foreshadowing_tasks")
        if not isinstance(foreshadowing_tasks, dict):
            foreshadowing_tasks = {}
        for key in ("must_resolve", "should_reinforce", "may_plant", "avoid_forgetting"):
            value = foreshadowing_tasks.get(key)
            if isinstance(value, str):
                foreshadowing_tasks[key] = [value]
            elif isinstance(value, list):
                foreshadowing_tasks[key] = [str(item).strip() for item in value if str(item).strip()][:6]
            else:
                foreshadowing_tasks[key] = []
        normalized["foreshadowing_tasks"] = foreshadowing_tasks

        raw_scenes = normalized.get("scene_list")
        scenes = [scene for scene in raw_scenes if isinstance(scene, dict)] if isinstance(raw_scenes, list) else []
        if not scenes:
            scenes = [
                {
                    "scene": "1",
                    "goal": normalized.get("chapter_purpose") or "推进本章核心目标",
                    "conflict": "制造正面阻碍",
                    "turn": "让局势发生实质变化",
                    "outcome": "交出本场后果",
                    "payoff": "兑现本章线索或情绪压力",
                    "bridge": "自然推向下一场或章末压力",
                    "dialogue_value": "对话承担试探、压迫或反制职责",
                    "end_hook": "把压力递到下一段或下一章",
                }
            ]
        ratios = cls._resolve_scene_execution_ratios(len(scenes), sequel_required=bool(normalized.get("sequel_required")))
        normalized_scenes: List[Dict[str, Any]] = []
        for index, scene in enumerate(scenes[:10]):
            item = dict(scene)
            item["scene"] = str(item.get("scene") or index + 1)
            item["goal"] = str(item.get("goal") or item.get("must_happen") or normalized.get("chapter_purpose") or "推进本章核心目标").strip()
            item["conflict"] = str(item.get("conflict") or "制造明确阻碍").strip()
            item["turn"] = str(item.get("turn") or "让局势发生变化").strip()
            item["outcome"] = str(item.get("outcome") or item.get("pressure_shift") or "交出行动后果").strip()
            item["payoff"] = str(item.get("payoff") or item.get("foreshadowing_task") or "兑现一处线索、关系或压力").strip()
            item["bridge"] = str(item.get("bridge") or "吃住上一场后果并推出下一场").strip()
            item["dialogue_value"] = str(item.get("dialogue_value") or "对话必须改变主动权、信息量或风险").strip()
            item["end_hook"] = str(item.get("end_hook") or "留下下一段压力").strip()
            try:
                word_budget = int(item.get("word_budget") or item.get("scene_word_goal") or 0)
            except (TypeError, ValueError):
                word_budget = 0
            if word_budget <= 0:
                ratio = ratios[index] if index < len(ratios) else max(0.1, 1 / max(1, len(scenes)))
                word_budget = max(220, int(max(500, target_word_count) * ratio))
            item["word_budget"] = word_budget
            if isinstance(item.get("characters"), list):
                item["characters"] = [str(value).strip() for value in item["characters"] if str(value).strip()][:8]
            else:
                item["characters"] = []
            normalized_scenes.append(item)
        normalized["scene_list"] = normalized_scenes
        normalized["chapter_draft_contract"] = draft_contract
        normalized["schema_version"] = "chapter_mission.v2"
        return normalized

    @staticmethod
    @staticmethod
    def _resolve_chapter_generation_max_tokens(target_word_count: int) -> int:
        words = max(500, int(target_word_count or 0))
        if words < 1200:
            return 3200
        if words < 2500:
            return 6400
        if words < 4000:
            return 9600
        if words < 5500:
            return 18000
        if words < 7500:
            return max(24000, int(words * 3.8))
        if words < 10000:
            return max(32000, int(words * 3.2))
        if words < 12500:
            return max(40000, int(words * 3.5))
        if words < 20000:
            return max(56000, int(words * 2.8))
        if words < 35000:
            return max(72000, int(words * 2.5))
        return min(100000, max(80000, int(words * 2.3)))
    @staticmethod
    def _estimate_remaining_seconds(stage: str, target_word_count: int) -> int:
        target_word_count = max(1200, int(target_word_count or 0))
        preparing_budget = max(50, min(180, 24 + int(target_word_count / 100) * 2))
        generating_budget = max(120, min(1800, 60 + int(target_word_count / 100) * 14))
        review_budget = max(40, min(360, 30 + int(target_word_count / 100) * 2))
        enrichment_budget = max(30, min(540, 18 + int(target_word_count / 100) * 4))
        stage_remaining = {
            "queued": preparing_budget + generating_budget + review_budget + enrichment_budget + 36,
            "prepare_context": generating_budget + review_budget + enrichment_budget + 28,
            "enhanced_context": generating_budget + review_budget + enrichment_budget + 24,
            "foreshadowing_chapter_task": generating_budget + review_budget + enrichment_budget + 22,
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
            "prepare_context": 8,
            "audit_context": 11,
            "cast_plan": 14,
            "foreshadowing_plan": 17,
            "enhanced_context": 18,
            "foreshadowing_chapter_task": 19,
            "generate_mission": 22,
            "longform_context": 26,
            "generate_variants": 62,
            "review": 72,
            "ai_review": 72,
            "self_critique": 84,
            "reader_simulator": 86,
            "consistency": 90,
            "continuity_gate": 91,
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
        event_kind: Optional[str] = None,
        title: Optional[str] = None,
        summary: Optional[str] = None,
        content_preview: Optional[str] = None,
        metrics: Optional[Dict[str, Any]] = None,
        artifact_refs: Optional[Dict[str, Any]] = None,
        developer_detail: Optional[Dict[str, Any]] = None,
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
        if event_kind:
            event["kind"] = event_kind
        if title:
            event["title"] = title
        if summary:
            event["summary"] = summary
        if content_preview:
            event["content_preview"] = content_preview
        if metrics:
            event["metrics"] = self._compact_runtime_value(metrics)
        if artifact_refs:
            event["artifact_refs"] = self._compact_runtime_value(artifact_refs)
        if developer_detail:
            event["developer_detail"] = self._compact_runtime_value(developer_detail)
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
            logger.warning("会话回滚失败：reason=%s error=%s", reason, rollback_exc)
        else:
            logger.warning("降级阶段失败后已完成会话回滚：reason=%s", reason)

    async def _record_generation_token_budget_usage(
        self,
        *,
        project_id: str,
        chapter: Chapter,
        versions: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        metrics: List[Dict[str, Any]] = []
        for version_index, version in enumerate(versions):
            metadata = version.get("metadata") if isinstance(version, dict) else None
            items = metadata.get("generation_call_metrics") if isinstance(metadata, dict) else None
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                enriched = dict(item)
                label = str(enriched.get("label") or "generation_call")
                enriched["label"] = f"v{version_index + 1}:{label}"
                metrics.append(enriched)

        if not metrics:
            return {"record_count": 0, "total_tokens": 0, "estimated_cost": 0.0, "module": "content"}

        try:
            return await TokenBudgetService(self.session).record_generation_call_metrics(
                project_id=project_id,
                metrics=metrics,
                module="content",
                chapter_id=chapter.id,
                operation_type="generation",
                description_prefix=f"第 {chapter.chapter_number} 章正文候选",
            )
        except Exception as exc:  # noqa: BLE001 - budget accounting must not block generation
            await self._safe_session_rollback("token_budget_usage")
            logger.warning(
                "记录章节生成 token 预算失败：project=%s chapter=%s error=%s",
                project_id,
                chapter.chapter_number,
                exc,
            )
            return {
                "record_count": 0,
                "total_tokens": 0,
                "estimated_cost": 0.0,
                "module": "content",
                "error": str(exc)[:180],
            }

    async def _check_token_budget_before_generation(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Check token budget before generation; return warning dict if budget is near or over threshold."""
        try:
            budget_service = TokenBudgetService(self.session)
            stats = await budget_service.get_usage_stats(project_id)
            usage_percent = stats.get("usage_percent", 0)
            budget_remaining = stats.get("budget_remaining", 0)
            total_budget = stats.get("total_budget", 0)
            if usage_percent >= 100:
                return {
                    "level": "exceeded",
                    "message": "项目 Token 预算已用尽，本次生成可能产生额外费用。",
                    "usage_percent": round(usage_percent, 1),
                    "budget_remaining": round(budget_remaining, 4),
                    "total_budget": total_budget,
                }
            if usage_percent >= 80:
                return {
                    "level": "warning",
                    "message": f"项目 Token 预算已使用 {usage_percent:.1f}%，接近上限。",
                    "usage_percent": round(usage_percent, 1),
                    "budget_remaining": round(budget_remaining, 4),
                    "total_budget": total_budget,
                }
            return None
        except Exception as exc:  # noqa: BLE001 - budget check must not block generation
            logger.warning("Token 预算预检失败：project=%s error=%s", project_id, exc)
            return None

    async def _persist_quality_gate_blocked_versions(
        self,
        *,
        chapter: Chapter,
        generation_run_id: Optional[str],
        versions: List[Dict[str, Any]],
        best_version_index: int,
        best_content: str,
        review_summaries: Dict[str, Any],
        structural_quality_gate: Dict[str, Any],
        longform_context: Optional[LongformContextPackage],
    ) -> Dict[str, Any]:
        if not versions:
            return {"persisted": False, "reason": "no_candidate_versions"}

        try:
            await self._assert_generation_active(
                chapter,
                generation_run_id=generation_run_id,
                stage="quality_gate_blocked_persist",
            )
        except HTTPException as exc:
            return {
                "persisted": False,
                "reason": "generation_not_active",
                "detail": self._truncate_runtime_text(exc.detail),
            }

        quality_payload = {
            "passed": False,
            "codes": list(structural_quality_gate.get("quality_issue_codes") or []),
            "labels": list(structural_quality_gate.get("quality_issue_labels") or []),
            "blockers": list(structural_quality_gate.get("blockers") or []),
            "failed_at": datetime.now(timezone.utc).isoformat(),
        }
        annotated_contents: List[str] = []
        annotated_metadata: List[Dict[str, Any]] = []
        best_version_index = max(0, min(best_version_index, len(versions) - 1))
        for index, item in enumerate(versions):
            content = best_content if index == best_version_index else str(item.get("content") or "")
            metadata = dict(item.get("metadata") or {})
            metadata["blocked_by_quality_gate"] = True
            metadata["quality_gate"] = quality_payload
            if generation_run_id:
                metadata["generation_run_id"] = generation_run_id
            if index == best_version_index:
                story_guard = structural_quality_gate.get("story_progression_guard") or {}
                metadata["review_summaries"] = review_summaries
                metadata["story_progression_guard"] = story_guard
                metadata["quality_metrics"] = story_guard.get("quality_metric_snapshot", story_guard)
                if longform_context:
                    metadata["longform_context"] = longform_context.to_metadata()
            annotated_contents.append(content)
            annotated_metadata.append(metadata)

        try:
            version_models = await self.novel_service.append_chapter_versions(
                chapter,
                annotated_contents,
                annotated_metadata,
                max_versions=MAX_STORED_CHAPTER_VERSIONS,
                expected_generation_run_id=generation_run_id,
            )
        except Exception as exc:  # noqa: BLE001 - failure to keep rejected draft should not mask the gate result
            await self._safe_session_rollback("quality_gate_blocked_persist")
            logger.warning(
                "质量门拒稿候选落库失败：project=%s chapter=%s error=%s",
                chapter.project_id,
                chapter.chapter_number,
                exc,
            )
            return {
                "persisted": False,
                "reason": "persist_failed",
                "detail": self._truncate_runtime_text(exc),
            }

        return {
            "persisted": True,
            "version_ids": [item.id for item in version_models if item.id is not None],
            "version_count": len(version_models),
        }

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
                event_kind="progress",
                title=f"{stage_name} 完成",
                summary=runtime_detail,
                extra={
                    "stage_duration_ms": duration_ms,
                    "stage_duration_seconds": round(duration_ms / 1000, 2),
                    "stage_timings": dict(stage_timings),
                },
            )

        pipeline_started_at = time.perf_counter()
        config = await self._resolve_config(flow_config)
        requested_preset = str((flow_config or {}).get("preset", "") or "").strip() or config.preset
        runtime_metadata: Dict[str, Any] = {
            "provider_preflight": {},
            "degraded_stages": [],
            "generation_mode": "quality",
            "stable_retry_used": False,
            "requested_preset": requested_preset,
            "actual_preset": config.preset,
            "preset_downgraded": False,
            "downgraded_capabilities": [],
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
        runtime_metadata["chapter_draft_contract"] = self._resolve_chapter_draft_contract(
            config.target_word_count,
            config.min_word_count,
        )
        runtime_metadata["chapter_generation_limits"] = {
            "timeout_seconds": self._resolve_chapter_generation_timeout(config.target_word_count),
            "soft_timeout_seconds": self._resolve_chapter_generation_soft_timeout(config.target_word_count),
            "max_tokens": self._resolve_chapter_generation_max_tokens(config.target_word_count),
            "mission_timeout_seconds": self._resolve_chapter_mission_timeout(config.target_word_count),
            "mission_max_tokens": self._resolve_chapter_mission_max_tokens(config.target_word_count),
        }
        project = await self.novel_service.ensure_project_owner(project_id, user_id)

        token_budget_warning = await self._check_token_budget_before_generation(project_id)
        if token_budget_warning:
            runtime_metadata["token_budget_warning"] = token_budget_warning

        # 长篇项目（大纲超过 10 章）自动启用 memory，保障跨章连续性
        # 仅在 preset 非 basic 且 memory 尚未显式启用时自动开启
        outline_count = len(project.outlines) if hasattr(project, "outlines") and project.outlines else 0
        if outline_count > 10 and config.preset != "basic" and not config.enable_memory:
            config.enable_memory = True
            logger.info(
                "Auto-enabled memory layer for long-form project: project=%s outlines=%s preset=%s",
                project_id,
                outline_count,
                config.preset,
            )

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
                "chapter_draft_contract": runtime_metadata["chapter_draft_contract"],
                "chapter_generation_limits": runtime_metadata["chapter_generation_limits"],
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

        pre_mission_scope = self.context_builder.analyze_character_scope(
            blueprint=blueprint_dict,
            completed_summaries=history_context["completed_summaries"],
            previous_tail=history_context["previous_tail"],
            outline_title=outline_title,
            outline_summary=outline_summary,
            writing_notes=writing_notes,
        )
        all_characters = pre_mission_scope["all_names"]
        introduced_characters = pre_mission_scope["introduced_characters"]
        planned_characters = pre_mission_scope["planned_characters"]

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
            introduced_characters=introduced_characters,
            planned_characters=planned_characters,
            all_characters=all_characters,
            target_word_count=config.target_word_count,
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
        macro_continuity_context = visibility_context.get("macro_continuity_context")

        logger.info(
            "Pipeline context: project=%s chapter=%s introduced=%d allowed_new=%d forbidden=%d",
            project_id,
            chapter_number,
            len(introduced_characters),
            len(allowed_new_characters),
            len(forbidden_characters),
        )

        longform_context: Optional[LongformContextPackage] = None
        longform_context_started_at = time.perf_counter()
        try:
            await self._update_generation_runtime(
                chapter,
                generation_run_id=generation_run_id,
                stage="audit_context",
                message="正在审计长期记忆、章节快照、时间线与知识图谱",
                progress_percent=11,
                extra={
                    "context_stage": "audit_context",
                    "context_stage_label": "长期上下文审计",
                },
            )
            await self._assert_generation_active(
                chapter,
                generation_run_id=generation_run_id,
                stage="audit_context",
            )
            longform_context = await self.longform_context_service.build_context_package(
                project=project,
                outline=outline,
                chapter_number=chapter_number,
                writing_notes=writing_notes,
                chapter_mission=chapter_mission,
                allowed_new_characters=allowed_new_characters,
            )
            runtime_metadata["longform_context"] = longform_context.to_metadata()
            await self._update_generation_runtime(
                chapter,
                generation_run_id=generation_run_id,
                stage="cast_plan",
                message="正在装配角色规模、登场层级、势力归属和动态角色规则",
                progress_percent=14,
                extra={
                    "target_character_count": longform_context.cast_plan.target_character_count,
                    "planned_character_count": longform_context.cast_plan.planned_character_count,
                    "chapter_focus_names": longform_context.cast_plan.chapter_focus_names,
                },
            )
            await self._update_generation_runtime(
                chapter,
                generation_run_id=generation_run_id,
                stage="foreshadowing_plan",
                message="正在规划本章伏笔回收、强化、禁忘和可新增线索",
                progress_percent=17,
                extra={
                    "must_resolve_count": len(longform_context.foreshadowing_task.must_resolve),
                    "should_reinforce_count": len(longform_context.foreshadowing_task.should_reinforce),
                    "avoid_forgetting_count": len(longform_context.foreshadowing_task.avoid_forgetting),
                    "active_clue_count": len(longform_context.foreshadowing_task.active_clues),
                },
            )
            await mark_stage("longform_context", longform_context_started_at, detail="长篇上下文包装配完成")
        except Exception as exc:  # noqa: BLE001 - longform context should improve generation, not take the writer down.
            runtime_metadata["degraded_stages"].append({"stage": "longform_context", "reason": str(exc)})
            if isinstance(exc, SQLAlchemyError):
                await self._safe_session_rollback("longform_context")
            await self._update_generation_runtime(
                chapter,
                generation_run_id=generation_run_id,
                stage="audit_context",
                message="长篇上下文装配已降级跳过，继续使用基础上下文生成",
                progress_percent=17,
                level="warning",
                extra={
                    "degraded_stage": "longform_context",
                    "degraded_reason": self._truncate_runtime_text(exc),
                },
            )
            logger.warning("长篇上下文装配已降级：project=%s chapter=%s error=%s", project_id, chapter_number, exc)

        enhanced_flow = None
        enhanced_context = None
        if config.enable_constitution or config.enable_persona or config.enable_foreshadowing or config.enable_faction:
            enhanced_flow = EnhancedWritingFlow(self.session, self.llm_service, self.prompt_service)

            async def report_enhanced_context_progress(stage: str, message: str) -> None:
                await self._update_generation_runtime(
                    chapter,
                    generation_run_id=generation_run_id,
                    stage=stage,
                    message=message,
                    progress_percent=self._infer_stage_progress_percent(stage),
                    event_kind="progress",
                    title="写前账本等待中",
                    summary=message,
                    extra={
                        "provider_waiting": True,
                        "context_stage": stage,
                        "context_stage_label": "写前增强上下文",
                        "target_word_count": config.target_word_count,
                        "min_word_count": config.min_word_count,
                    },
                )
                await self._assert_generation_active(
                    chapter,
                    generation_run_id=generation_run_id,
                    stage=f"{stage}_provider_wait",
                )

            await self._update_generation_runtime(
                chapter,
                generation_run_id=generation_run_id,
                stage="enhanced_context",
                message="正在装配小说宪法、文风、伏笔提醒和势力关系",
                progress_percent=18,
                extra={
                    "context_stage": "enhanced_context",
                    "context_stage_label": "写前增强上下文",
                    "enable_constitution": config.enable_constitution,
                    "enable_persona": config.enable_persona,
                    "enable_foreshadowing": config.enable_foreshadowing,
                    "enable_faction": config.enable_faction,
                },
            )
            await self._assert_generation_active(
                chapter,
                generation_run_id=generation_run_id,
                stage="enhanced_context",
            )
            enhanced_context = await enhanced_flow.prepare_writing_context(
                project_id=project_id,
                chapter_number=chapter_number,
                chapter_outline=outline_summary,
                user_id=user_id,
                progress_callback=report_enhanced_context_progress,
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
                continuity_injection = self._build_continuity_retrieval_injection(history_context)
                if continuity_injection:
                    knowledge_context = "\n\n".join(part for part in [continuity_injection, knowledge_context] if part)
                    if isinstance(rag_stats, dict):
                        rag_stats["continuity_injection"] = True
            else:
                rag_context = await self._get_rag_context(
                    project_id=project_id,
                    outline_title=outline_title,
                    outline_summary=outline_summary,
                    writing_notes="\n".join(filter(None, [writing_notes, history_context.get("plot_arc_digest", ""), history_context.get("recent_track", "")])),
                    user_id=user_id,
                )
                rag_context = self._inject_continuity_into_rag(rag_context, history_context)
                rag_stats = {
                    "mode": "simple",
                    "chunks": len(rag_context.get("chunks", [])) if rag_context else 0,
                    "summaries": len(rag_context.get("summaries", [])) if rag_context else 0,
                    "continuity_injection": bool((rag_context or {}).get("continuity_injection")),
                }
        await mark_stage("prepare_context", prepare_context_started_at, detail="上下文准备阶段完成")

        writer_prompt = await self.prompt_service.get_prompt("writing_v2")
        if not writer_prompt:
            writer_prompt = await self.prompt_service.get_prompt("writing")
        if not writer_prompt:
            raise HTTPException(status_code=500, detail="缺少写作提示词，请联系管理员配置")

        prompt_sections = self._build_prompt_sections(
            preset=requested_preset,
            writer_blueprint=writer_blueprint,
            previous_summary=history_context["previous_summary"],
            previous_tail=history_context["previous_tail"],
            chapter_mission=chapter_mission,
            macro_continuity_context=macro_continuity_context,
            longform_context_text=longform_context.prompt_text if longform_context else None,
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
        best_partial_versions: List[Dict[str, Any]] = []
        best_partial_errors: List[Exception] = []
        best_partial_config: PipelineConfig = config
        best_partial_required_success_count = required_success_count
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

        async def report_generation_call_progress(stage: str, message: str) -> None:
            await self._update_generation_runtime(
                chapter,
                generation_run_id=generation_run_id,
                stage=stage,
                message=message,
                progress_percent=self._infer_stage_progress_percent(stage),
                event_kind="progress",
                title="Provider 等待中",
                summary=message,
                extra={
                    "provider_waiting": True,
                    "target_word_count": config.target_word_count,
                    "min_word_count": config.min_word_count,
                    "soft_timeout_seconds": self._resolve_chapter_generation_soft_timeout(config.target_word_count),
                },
            )
            await self._assert_generation_active(
                chapter,
                generation_run_id=generation_run_id,
                stage=f"{stage}_provider_wait",
            )

        for attempt_idx, attempt_config in enumerate(attempt_configs):
            version_count = attempt_config.version_count
            attempt_required_success_count = self._attempt_required_success_count(
                required_success_count=required_success_count,
                requested_count=version_count,
            )
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
                            analysis_guidance_context=analysis_guidance_context,
                            enhanced_context=enhanced_context,
                            config=attempt_config,
                            progress_callback=report_generation_call_progress,
                        )
                    )
                )

            # 在LLM调用前强制提交并释放数据库session锁，允许其他请求在生成期间读取
            await self.session.commit()
            await self.session.flush()
            self.session.expire_all()
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
                    "required_success_count": attempt_required_success_count,
                    "original_required_success_count": required_success_count,
                    "meets_success_threshold": success_count >= attempt_required_success_count,
                    "duration_ms": generation_attempt_duration_ms,
                    "generation_phase_total_ms": generation_phase_total_ms,
                    "guardrail_check_total_ms": guardrail_check_total_ms,
                    "guardrail_rewrite_total_ms": guardrail_rewrite_total_ms,
                    "version_total_ms": version_total_ms,
                }
            )

            if success_count > 0 and (
                not best_partial_versions
                or success_count > len(best_partial_versions)
                or (
                    success_count == len(best_partial_versions)
                    and attempt_config.preset == "stable"
                )
            ):
                best_partial_versions = attempt_versions
                best_partial_errors = attempt_errors
                best_partial_config = attempt_config
                best_partial_required_success_count = attempt_required_success_count

            if success_count >= attempt_required_success_count:
                versions = attempt_versions
                generation_errors = attempt_errors
                active_config = attempt_config
                runtime_metadata["candidate_generation"] = {
                    "requested_version_count": version_count,
                    "successful_versions": success_count,
                    "failed_versions": len(attempt_errors),
                    "required_success_count": attempt_required_success_count,
                    "original_required_success_count": required_success_count,
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
                    event_kind="content",
                    title="候选草稿已生成",
                    summary=f"本轮生成 {len(attempt_versions)} 个候选版本，开始评审筛选。",
                    content_preview=self._truncate_runtime_text(
                        (attempt_versions[0].get("content") or "") if attempt_versions else "",
                        420,
                    ),
                    metrics={
                        "generated_version_count": len(attempt_versions),
                        "failed_versions": len(attempt_errors),
                        "target_word_count": config.target_word_count,
                    },
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
                runtime_metadata["actual_preset"] = "stable"
                runtime_metadata["preset_downgraded"] = True
                # 记录降级时被关闭的高级能力，让前端可见
                downgraded = []
                if config.enable_preview:
                    downgraded.append("preview")
                if config.enable_optimizer:
                    downgraded.append("optimizer")
                if config.enable_consistency:
                    downgraded.append("consistency")
                if config.enable_enrichment:
                    downgraded.append("enrichment")
                if config.enable_reader_sim:
                    downgraded.append("reader_sim")
                if config.enable_self_critique:
                    downgraded.append("self_critique")
                if config.enable_six_dimension:
                    downgraded.append("six_dimension")
                if config.enable_memory:
                    downgraded.append("memory")
                if config.enable_constitution:
                    downgraded.append("constitution")
                if config.enable_persona:
                    downgraded.append("persona")
                if config.enable_foreshadowing:
                    downgraded.append("foreshadowing")
                if config.enable_faction:
                    downgraded.append("faction")
                runtime_metadata["downgraded_capabilities"] = downgraded
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
                        "preset_downgraded": True,
                        "downgraded_capabilities": downgraded,
                        "successful_versions": success_count,
                        "required_success_count": attempt_required_success_count,
                        "original_required_success_count": required_success_count,
                    },
                )
                logger.warning(
                    "Primary generation insufficient, retrying once with stable mode: project=%s chapter=%s success=%s required=%s",
                    project_id,
                    chapter_number,
                    success_count,
                    attempt_required_success_count,
                )
                continue
            break

        if not versions and best_partial_versions:
            versions = best_partial_versions
            generation_errors = best_partial_errors
            active_config = best_partial_config
            runtime_metadata["stable_retry_used"] = bool(active_config.preset == "stable" or runtime_metadata.get("stable_retry_used"))
            runtime_metadata["generation_mode"] = active_config.preset
            runtime_metadata["quality_gates"]["partial_candidate_salvage_used"] = True
            runtime_metadata["candidate_generation"] = {
                "requested_version_count": active_config.version_count,
                "successful_versions": len(best_partial_versions),
                "failed_versions": len(best_partial_errors),
                "required_success_count": best_partial_required_success_count,
                "original_required_success_count": required_success_count,
                "salvaged_partial_success": True,
            }
            await self._update_generation_runtime(
                chapter,
                generation_run_id=generation_run_id,
                stage="review",
                message="Provider 抖动导致候选不足，已保留合格候选并进入评审",
                progress_percent=62,
                level="warning",
                event_kind="content",
                title="保留合格候选",
                summary="多候选生成未完全达标，但已有候选通过首稿底线，系统继续评审而不是直接失败。",
                content_preview=self._truncate_runtime_text(
                    (best_partial_versions[0].get("content") or "") if best_partial_versions else "",
                    420,
                ),
                metrics={
                    "generated_version_count": len(best_partial_versions),
                    "failed_versions": len(best_partial_errors),
                    "required_success_count": best_partial_required_success_count,
                    "original_required_success_count": required_success_count,
                    "target_word_count": config.target_word_count,
                    "salvaged_partial_success": True,
                },
                extra={
                    "generated_version_count": len(best_partial_versions),
                    "stable_retry_used": runtime_metadata["stable_retry_used"],
                    "generation_mode": runtime_metadata["generation_mode"],
                    "salvaged_partial_success": True,
                },
            )

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

        # ── Multi-round continuation for long chapters (free API workaround) ──
        if config.enable_multi_round_fallback and versions:
            best_initial = max(
                versions,
                key=lambda v: len(v.get("content") or ""),
            )
            best_content_initial = best_initial.get("content") or ""
            initial_words = len(best_content_initial.replace(chr(10), ""))
            target_words = config.target_word_count

            continuation_rounds = 0
            while (initial_words < target_words * 0.6
                   and continuation_rounds < config.multi_round_max_rounds):
                continuation_rounds += 1
                await self._update_generation_runtime(
                    chapter,
                    generation_run_id=generation_run_id,
                    stage="multi_round_continuation",
                    message=f"字数不足（{initial_words}/{target_words}），启动第{continuation_rounds}轮续写...",
                    progress_percent=min(62 + continuation_rounds * 3, 68),
                    event_kind="progress",
                    title=f"多轮续写 第{continuation_rounds}轮",
                )

                continuation_prompt = (
                    f"【续写指令】请紧接着上面的内容继续写下去，保持同样的风格、视角和节奏。"
                    f"当前已写{initial_words}字，目标{target_words}字，还需要至少{int(target_words * 0.6) - initial_words}字。"
                    f"不要重复已写内容，直接接续结尾继续推进剧情。"
                )

                try:
                    cont_result = await call_generation_text(
                        llm_service=self.llm_service,
                        system_prompt=writer_prompt,
                        conversation_history=[
                            {"role": "user", "content": prompt_input},
                            {"role": "assistant", "content": best_content_initial[-800:]},
                            {"role": "user", "content": continuation_prompt},
                        ],
                        temperature=0.75,
                        user_id=user_id,
                        timeout=self._resolve_chapter_generation_timeout(config.target_word_count),
                        policy=GenerationCallPolicy(
                            stage_label=f"续写轮{continuation_rounds}",
                            progress_stage="multi_round_continuation",
                            retry_attempts=1,
                            max_tokens=self._resolve_chapter_generation_max_tokens(target_words),
                            allow_truncated_response=True,
                        ),
                    )
                    if cont_result and cont_result.text:
                        new_content = best_content_initial + "\n\n" + cont_result.text
                        best_initial["content"] = new_content
                        best_initial["word_count"] = len(new_content.replace(chr(10), ""))
                        best_content_initial = new_content
                        initial_words = best_initial["word_count"]
                        logger.info(
                            "Continuation round %s: words -> %s",
                            continuation_rounds,
                            initial_words,
                        )
                    else:
                        logger.warning("Continuation round %s returned empty", continuation_rounds)
                        break
                except Exception as exc:
                    logger.warning("Continuation round %s failed: %s", continuation_rounds, exc)
                    runtime_metadata["degraded_stages"].append({
                        "stage": f"multi_round_continuation_{continuation_rounds}",
                        "reason": str(exc),
                    })
                    break

            if continuation_rounds > 0:
                runtime_metadata["continuation"] = {
                    "rounds": continuation_rounds,
                    "final_words": initial_words,
                    "target_words": target_words,
                }

        review_started_at = time.perf_counter()
        review_chapter_mission = self._build_ai_review_mission(
            chapter_mission=chapter_mission,
            longform_context=longform_context,
        )
        best_version_index, ai_review_result = await self._run_ai_review(
            versions=versions,
            chapter_mission=review_chapter_mission,
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
            event_kind="review",
            title="AI 评审完成",
            summary=f"最佳候选：第 {best_version_index + 1} 版；状态：{runtime_metadata['review_status']}",
            metrics={
                "best_version_index": best_version_index,
                "candidate_count": len(versions),
                "review_status": runtime_metadata["review_status"],
            },
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
                    logger.warning("增强评审已降级：project=%s chapter=%s error=%s", project_id, chapter_number, exc)

            if active_config.enable_self_critique:
                try:
                    self_critique_started_at = time.perf_counter()
                    pre_critique_content = best_content
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
                        best_content, content_guard = self._preserve_non_regressive_content(
                            previous_content=pre_critique_content,
                            candidate_content=best_content,
                            stage_label="self_critique",
                            min_word_count=active_config.min_word_count,
                        )
                        if content_guard is not None:
                            critique_summary.setdefault("degraded_stages", []).append(content_guard)
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
                    logger.warning("自检诊断已降级：project=%s chapter=%s error=%s", project_id, chapter_number, exc)

            if active_config.enable_reader_sim:
                try:
                    reader_feedback = await asyncio.wait_for(
                        self._run_reader_simulation(
                        best_content,
                        chapter_number=chapter_number,
                        previous_summary=history_context["previous_summary"],
                        user_id=user_id,
                    ),
                    timeout=300.0,
                    )
                    review_summaries["reader_simulator"] = reader_feedback
                    reader_fix_issues = self._normalize_reader_issues_for_local_fix(reader_feedback)
                    reader_structural_guard = self._score_story_quality_candidate(
                        content=best_content,
                        violations=(best_version.get("metadata") or {}).get("guardrail", {}).get("violations", []),
                        chapter_mission=chapter_mission,
                    )
                    structural_reader_issues = self._build_structural_reader_polish_issues(reader_structural_guard)
                    if structural_reader_issues:
                        reader_fix_issues = (structural_reader_issues + reader_fix_issues)[:8]
                        review_summaries["reader_polish_structural_guard"] = reader_structural_guard
                    reader_stage_decision = reader_feedback.get("reader_stage_decision") or {}
                    should_reader_polish, reader_polish_decision = self._should_run_reader_polish(
                        reader_feedback,
                        reader_fix_issues,
                    )
                    review_summaries["reader_polish_decision"] = reader_polish_decision
                    if should_reader_polish:
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
                            "reader_polish_hard_rule": (
                                "本轮 reader polish 必须优先修结构问题：场景兑现、对话改局势、结尾递压、连续性。"
                                "只有在这些问题解决后才允许做句子润色；禁止把优化变成补景物、补心理、补形容词。"
                            ),
                        }
                        reader_polish_service = SelfCritiqueService(self.session, self.llm_service, self.prompt_service)
                        previous_best_content = best_content
                        polished_content = await reader_polish_service.revise_chapter(
                            chapter_content=best_content,
                            issues=reader_fix_issues,
                            context=reader_context,
                            user_id=user_id,
                            allow_stagewide=False,
                        )
                        if polished_content and polished_content != best_content:
                            next_content, content_guard = self._preserve_non_regressive_content(
                                previous_content=previous_best_content,
                                candidate_content=polished_content,
                                stage_label="reader_polish",
                                min_word_count=active_config.min_word_count,
                            )
                            best_content = next_content
                            review_summaries["reader_polish"] = {
                                "status": "guarded_rejected" if content_guard is not None else "applied",
                                "issue_count": len(reader_fix_issues),
                                "continue_ratio": reader_stage_decision.get("continue_ratio"),
                                "content_guard": content_guard,
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
                    logger.warning("读者模拟已降级：project=%s chapter=%s error=%s", project_id, chapter_number, exc)

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
                            allow_stagewide=False,
                        )
                        if repaired_content and repaired_content != best_content:
                            rechecked_content, repaired_report = await self._run_consistency_check(
                                project_id=project_id,
                                chapter_text=repaired_content,
                                user_id=user_id,
                            )
                            repaired_report["repair_strategy"] = "self_critique_local_repair"
                            improved_repair, repair_reason, before_counts, after_counts = self._should_accept_consistency_improvement(
                                consistency_report,
                                repaired_report,
                            )
                            repaired_report["repair_comparison"] = {
                                "accepted": improved_repair,
                                "acceptance_reason": repair_reason,
                                "before": before_counts,
                                "after": after_counts,
                            }
                            if repaired_report.get("is_consistent") or repaired_report.get("auto_fix_accepted") or improved_repair:
                                next_content, content_guard = self._preserve_non_regressive_content(
                                    previous_content=best_content,
                                    candidate_content=rechecked_content,
                                    stage_label="consistency_repair",
                                    min_word_count=active_config.min_word_count,
                                )
                                repaired_report["content_guard"] = content_guard
                                repaired_report["repair_accepted"] = True
                                repaired_report["repair_acceptance_reason"] = (
                                    repaired_report.get("auto_fix_acceptance_reason")
                                    or repair_reason
                                )
                                best_content = next_content
                                consistency_report = repaired_report
                            review_summaries["consistency_repair"] = repaired_report
                    await mark_stage("consistency", consistency_started_at, detail="一致性校验阶段完成")
                    runtime_metadata["consistency_status"] = consistency_report.get("status", "unknown")
                    unresolved_for_warning = self._collect_unresolved_consistency_violations(consistency_report)
                    if unresolved_for_warning:
                        runtime_metadata["consistency_violation_count"] = len(unresolved_for_warning)
                        runtime_metadata["consistency_violation_summary"] = [
                            {
                                "severity": str(item.get("severity") or "minor"),
                                "category": str(item.get("category") or ""),
                                "description": str(item.get("description") or "")[:200],
                            }
                            for item in unresolved_for_warning[:5]
                        ]
                    review_summaries["consistency"] = consistency_report
                    repair_attempts = consistency_report.get("repair_attempts")
                    if not isinstance(repair_attempts, list):
                        repair_attempts = []
                    unresolved_consistency_issues = self._normalize_consistency_issues_for_local_fix(consistency_report)
                    if repair_attempts or unresolved_consistency_issues:
                        manual_confirmation_required = any(
                            bool(item.get("manual_confirmation_required"))
                            for item in repair_attempts
                            if isinstance(item, dict)
                        )
                        await self._update_generation_runtime(
                            chapter,
                            generation_run_id=generation_run_id,
                            stage="consistency",
                            message=(
                                "一致性局部修复已完成，仍有问题需按局部补丁处理"
                                if unresolved_consistency_issues
                                else "一致性局部修复已完成，未触发整章自动替换"
                            ),
                            progress_percent=91,
                            level="warning" if unresolved_consistency_issues else "info",
                            event_kind="continuity",
                            title="一致性局部修复结果",
                            summary=(
                                f"局部修复尝试 {len(repair_attempts)} 次，未解决问题 {len(unresolved_consistency_issues)} 项；"
                                "整章候选需要人工确认。"
                                if manual_confirmation_required
                                else f"局部修复尝试 {len(repair_attempts)} 次，未解决问题 {len(unresolved_consistency_issues)} 项。"
                            ),
                            metrics={
                                "repair_attempt_count": len(repair_attempts),
                                "unresolved_consistency_issues": len(unresolved_consistency_issues),
                                "auto_fix_accepted": bool(consistency_report.get("auto_fix_accepted")),
                            },
                            extra={
                                "repair_attempts": repair_attempts[:3],
                                "manual_stagewide_confirmation_required": manual_confirmation_required,
                                "manual_patch_suggestions": unresolved_consistency_issues[:5],
                            },
                        )
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
                    logger.warning("一致性校验已降级：project=%s chapter=%s error=%s", project_id, chapter_number, exc)

            if active_config.enable_self_critique:
                try:
                    post_consistency_context = {
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
                        "consistency_issues": self._normalize_consistency_issues_for_local_fix(
                            review_summaries.get("consistency_repair") or review_summaries.get("consistency")
                        ),
                        "guardrail_issues": (best_version.get("metadata") or {}).get("guardrail", {}).get("violations", []),
                        "enhanced_review_issues": enhanced_review_issues,
                    }
                    review_summaries["self_critique_after_consistency"] = await self._run_post_consistency_self_critique_summary(
                        chapter_content=best_content,
                        context=post_consistency_context,
                        user_id=user_id,
                        baseline_summary=review_summaries.get("self_critique"),
                    )
                except Exception as exc:  # noqa: BLE001 - degraded stage should not fail whole request
                    runtime_metadata["degraded_stages"].append({"stage": "self_critique_after_consistency", "reason": str(exc)})
                    if isinstance(exc, SQLAlchemyError):
                        await self._safe_session_rollback("self_critique_after_consistency")
                    logger.warning(
                        "Post-consistency self critique degraded: project=%s chapter=%s error=%s",
                        project_id,
                        chapter_number,
                        exc,
                    )

            guardrail_violations = ((best_version.get("metadata") or {}).get("guardrail") or {}).get("violations") or []
            if active_config.enable_enrichment:
                review_summaries, pre_enrichment_gate = self._evaluate_structural_quality_gate_for_content(
                    review_summaries=review_summaries,
                    content=best_content,
                    violations=guardrail_violations,
                    chapter_mission=chapter_mission,
                    story_guard_key="story_progression_guard_pre_enrichment",
                )
                runtime_metadata["quality_gates"]["pre_enrichment_structural_gate"] = pre_enrichment_gate
            else:
                review_summaries, structural_quality_gate = self._evaluate_structural_quality_gate_for_content(
                    review_summaries=review_summaries,
                    content=best_content,
                    violations=guardrail_violations,
                    chapter_mission=chapter_mission,
                )
                runtime_metadata["quality_gates"]["structural_gate"] = structural_quality_gate
                if not structural_quality_gate.get("passed", True):
                    blocked_candidate_refs = await self._persist_quality_gate_blocked_versions(
                        chapter=chapter,
                        generation_run_id=generation_run_id,
                        versions=versions,
                        best_version_index=best_version_index,
                        best_content=best_content,
                        review_summaries=review_summaries,
                        structural_quality_gate=structural_quality_gate,
                        longform_context=longform_context,
                    )
                    runtime_metadata["quality_gate_blocked_versions"] = blocked_candidate_refs
                    await self._update_generation_runtime(
                        chapter,
                        generation_run_id=generation_run_id,
                        stage="review",
                        message="结构质量闸门未通过，已阻止低质量章节进入确认阶段",
                        progress_percent=91,
                        level="warning",
                        event_kind="quality_gate",
                        title="质量门拦截候选稿",
                        summary="候选稿已保留供查看，但不会静默定稿；请按拦截原因重试或人工确认。",
                        content_preview=self._truncate_runtime_text(best_content, 520),
                        metrics={
                            "actual_word_count": self._count_words(best_content),
                            "candidate_count": len(versions),
                            "quality_issue_codes": structural_quality_gate.get("quality_issue_codes", []),
                            "quality_issue_labels": structural_quality_gate.get("quality_issue_labels", []),
                        },
                        artifact_refs=blocked_candidate_refs if blocked_candidate_refs.get("persisted") else None,
                        extra={
                            "quality_gate_failed": True,
                            "quality_gate": structural_quality_gate,
                            "review_summaries": review_summaries,
                            "runtime_metadata": runtime_metadata,
                        },
                    )
                    raise HTTPException(
                        status_code=422,
                        detail={
                            "code": "CHAPTER_QUALITY_GATE_FAILED",
                            "message": "章节仍存在严重结构/一致性问题，已阻止静默成功落库。",
                            "hint": "请结合 self_critique 与 consistency 结果重试生成，优先消除重复时间线、拼接回卷和关键设定冲突。",
                            "retryable": True,
                            "stage": "quality_gate",
                            "quality_gate": structural_quality_gate,
                        },
                    )

            logger.info(
                "Post-generation extra stages: optimizer=%s enrichment=%s current_words=%s target=%s min=%s",
                active_config.enable_optimizer,
                active_config.enable_enrichment,
                self._count_words(best_content),
                active_config.target_word_count,
                active_config.min_word_count,
            )

            if active_config.enable_enrichment:
                try:
                    enrichment_started_at = time.perf_counter()
                    await self._update_generation_runtime(
                        chapter,
                        generation_run_id=generation_run_id,
                        stage="enrichment",
                        message="正在按目标字数补足章节篇幅",
                        progress_percent=91,
                        extra={
                            "current_word_count": self._count_words(best_content),
                            "target_word_count": active_config.target_word_count,
                            "min_word_count": active_config.min_word_count,
                        },
                    )
                    pre_enrichment_content = best_content
                    enriched_content, enrichment_summary = await self._run_enrichment(
                        best_content,
                        user_id=user_id,
                        target_word_count=active_config.target_word_count,
                        min_word_count=active_config.min_word_count,
                        max_iterations=active_config.max_enrich_iterations,
                        context={
                            "chapter_mission": chapter_mission,
                            "previous_summary": history_context["previous_summary"],
                            "previous_tail": history_context.get("previous_tail"),
                            "previous_chapter_bundle": history_context.get("previous_chapter_bundle"),
                            "recent_track": history_context.get("recent_track"),
                            "plot_arc_digest": history_context.get("plot_arc_digest"),
                            "project_memory": project_memory_text,
                            "longform_context": longform_context.to_optimizer_payload(max_prompt_chars=2600) if longform_context else None,
                        },
                    )
                    if enrichment_summary is not None:
                        best_content, content_guard = self._preserve_non_regressive_content(
                            previous_content=pre_enrichment_content,
                            candidate_content=enriched_content,
                            stage_label="enrichment",
                            min_word_count=active_config.min_word_count,
                        )
                        enrichment_summary["content_guard"] = content_guard
                        enrichment_summary["applied"] = content_guard is None and best_content != pre_enrichment_content
                        review_summaries["enrichment"] = enrichment_summary
                    await mark_stage("enrichment", enrichment_started_at, detail="章节扩写阶段完成")
                except Exception as exc:  # noqa: BLE001 - degraded stage should not fail whole request
                    runtime_metadata["degraded_stages"].append({"stage": "enrichment", "reason": str(exc)})
                    if isinstance(exc, SQLAlchemyError):
                        await self._safe_session_rollback("enrichment")
                    await self._update_generation_runtime(
                        chapter,
                        generation_run_id=generation_run_id,
                        stage="enrichment",
                        message="章节扩写已降级跳过，继续后续流程",
                        progress_percent=91,
                        level="warning",
                        extra={
                            "degraded_stage": "enrichment",
                            "degraded_reason": self._truncate_runtime_text(exc),
                        },
                    )
                    logger.warning("章节扩写已降级：project=%s chapter=%s error=%s", project_id, chapter_number, exc)

            review_summaries, structural_quality_gate = self._evaluate_structural_quality_gate_for_content(
                review_summaries=review_summaries,
                content=best_content,
                violations=guardrail_violations,
                chapter_mission=chapter_mission,
            )
            runtime_metadata["quality_gates"]["structural_gate"] = structural_quality_gate
            if not structural_quality_gate.get("passed", True):
                blocked_candidate_refs = await self._persist_quality_gate_blocked_versions(
                    chapter=chapter,
                    generation_run_id=generation_run_id,
                    versions=versions,
                    best_version_index=best_version_index,
                    best_content=best_content,
                    review_summaries=review_summaries,
                    structural_quality_gate=structural_quality_gate,
                    longform_context=longform_context,
                )
                runtime_metadata["quality_gate_blocked_versions"] = blocked_candidate_refs
                await self._update_generation_runtime(
                    chapter,
                    generation_run_id=generation_run_id,
                    stage="review",
                    message="结构质量闸门未通过，已阻止低质量章节进入确认阶段",
                    progress_percent=91,
                    level="warning",
                    event_kind="quality_gate",
                    title="质量门拦截候选稿",
                    summary="候选稿已保留供查看，但不会静默定稿；请按拦截原因重试或人工确认。",
                    content_preview=self._truncate_runtime_text(best_content, 520),
                    metrics={
                        "actual_word_count": self._count_words(best_content),
                        "candidate_count": len(versions),
                        "quality_issue_codes": structural_quality_gate.get("quality_issue_codes", []),
                        "quality_issue_labels": structural_quality_gate.get("quality_issue_labels", []),
                    },
                    artifact_refs=blocked_candidate_refs if blocked_candidate_refs.get("persisted") else None,
                    extra={
                        "quality_gate_failed": True,
                        "quality_gate": structural_quality_gate,
                        "review_summaries": review_summaries,
                        "runtime_metadata": runtime_metadata,
                    },
                )
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "CHAPTER_QUALITY_GATE_FAILED",
                        "message": "章节仍存在严重结构/一致性问题，已阻止静默成功落库。",
                        "hint": "请结合 self_critique 与 consistency 结果重试生成，优先消除重复时间线、拼接回卷和关键设定冲突。",
                        "retryable": True,
                        "stage": "quality_gate",
                        "quality_gate": structural_quality_gate,
                    },
                )

            final_word_count = self._count_words(best_content)
            final_quality_guard = self._score_story_quality_candidate(
                content=best_content,
                violations=guardrail_violations,
                chapter_mission=chapter_mission,
            )
            final_quality_guard = self._attach_quality_gate_status_to_guard(
                final_quality_guard,
                structural_quality_gate,
            )
            review_summaries["final_quality_metrics"] = final_quality_guard.get("quality_metric_snapshot", final_quality_guard)
            continuity_gate_started_at = time.perf_counter()
            longform_continuity_gate = self.longform_context_service.evaluate_continuity_quality(
                content=best_content,
                package=longform_context,
                chapter_mission=chapter_mission,
            )
            longform_continuity_payload = asdict(longform_continuity_gate)
            review_summaries["longform_continuity_gate"] = longform_continuity_payload
            runtime_metadata["quality_gates"]["longform_continuity_gate"] = longform_continuity_payload
            await self._update_generation_runtime(
                chapter,
                generation_run_id=generation_run_id,
                stage="continuity_gate",
                message=(
                    "长篇连续性检查完成"
                    if longform_continuity_gate.passed
                    else "长篇连续性检查发现需要局部补丁的问题，已写入候选版本报告"
                ),
                progress_percent=91,
                level="info" if longform_continuity_gate.passed else "warning",
                event_kind="continuity",
                title="连续性质量门完成",
                summary=(
                    "跨章节角色、时间线、伏笔和线索检查通过"
                    if longform_continuity_gate.passed
                    else "发现需要局部补丁处理的连续性风险"
                ),
                metrics=longform_continuity_gate.metrics,
                extra={
                    "longform_gate_passed": longform_continuity_gate.passed,
                    "longform_gate_blockers": longform_continuity_gate.blockers,
                    "longform_gate_warnings": longform_continuity_gate.warnings,
                    "longform_gate_metrics": longform_continuity_gate.metrics,
                },
            )
            await mark_stage("continuity_gate", continuity_gate_started_at, detail="长篇连续性质量门完成")
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
                    await self._update_generation_runtime(
                        chapter,
                        generation_run_id=generation_run_id,
                        stage="review",
                        message="章节字数未达到最低要求，已阻止低质量章节进入确认阶段",
                        progress_percent=91,
                        level="warning",
                        extra={
                            "quality_gate_failed": True,
                            "review_summaries": review_summaries,
                            "runtime_metadata": runtime_metadata,
                            "actual_word_count": final_word_count,
                            "word_requirement_met": False,
                            "word_requirement_reason": runtime_metadata["word_requirement_reason"],
                        },
                    )
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
            best_version_metadata["story_progression_guard"] = final_quality_guard
            best_version_metadata["quality_metrics"] = final_quality_guard.get("quality_metric_snapshot", final_quality_guard)
            if longform_context:
                best_version_metadata["longform_context"] = longform_context.to_metadata()
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
            event_kind="save",
            title="正在保存候选版本",
            summary="正文、评审结果和连续性检查结果正在一起落库。",
            content_preview=self._truncate_runtime_text(best_content, 420),
            metrics={
                "actual_word_count": runtime_metadata["actual_word_count"],
                "candidate_count": len(versions),
            },
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
        token_budget_usage = await self._record_generation_token_budget_usage(
            project_id=project_id,
            chapter=chapter,
            versions=versions,
        )
        runtime_metadata["token_budget_usage"] = token_budget_usage

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
            event_kind="content",
            title="候选版本可确认",
            summary=f"已生成 {len(variants)} 个候选版本，推荐第 {best_version_index + 1} 版。",
            content_preview=self._truncate_runtime_text(
                (variants[best_version_index].get("content") or "") if 0 <= best_version_index < len(variants) else best_content,
                520,
            ),
            metrics={
                "actual_word_count": runtime_metadata["actual_word_count"],
                "generated_version_count": len(variants),
                "best_version_index": best_version_index,
                "pipeline_total_duration_ms": runtime_metadata["pipeline_total_duration_ms"],
                "token_budget_records": token_budget_usage.get("record_count"),
                "estimated_generation_tokens": token_budget_usage.get("total_tokens"),
            },
            artifact_refs={
                "version_ids": [item.get("version_id") for item in variants if item.get("version_id")],
                "best_version_id": (
                    variants[best_version_index].get("version_id")
                    if 0 <= best_version_index < len(variants)
                    else None
                ),
            },
            extra={
                "actual_word_count": runtime_metadata["actual_word_count"],
                "word_requirement_met": runtime_metadata["word_requirement_met"],
                "word_requirement_reason": runtime_metadata["word_requirement_reason"],
                "generated_version_count": len(variants),
                "best_version_index": best_version_index,
                "allowed_actions": ["confirm_version", "review_versions", "refresh_status"],
                "stage_timings_ms": runtime_metadata["stage_timings_ms"],
                "pipeline_total_duration_ms": runtime_metadata["pipeline_total_duration_ms"],
                "token_budget_usage": token_budget_usage,
                "degraded_stages": runtime_metadata.get("degraded_stages", []),
                "self_critique_final_score": self_critique_summary.get("final_score"),
                "self_critique_improvement": self_critique_summary.get("improvement"),
                "self_critique_status": self_critique_summary.get("status"),
                "self_critique_critical_count": self_critique_summary.get("critical_count"),
                "self_critique_major_count": self_critique_summary.get("major_count"),
                "self_critique_priority_fixes": self_critique_summary.get("priority_fixes", []),
                "self_critique_after_consistency_status": post_consistency_summary.get("status"),
                "self_critique_after_consistency_improvement": post_consistency_summary.get("improvement"),
                "quality_metrics": review_summaries.get("final_quality_metrics"),
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
        config.target_word_count = self._coerce_positive_int(flow_config.get("target_word_count"), default=5000, minimum=500)
        config.min_word_count = self._coerce_positive_int(
            flow_config.get("min_word_count"),
            default=max(500, int(config.target_word_count * 0.9)),
            minimum=200,
        )
        config.max_enrich_iterations = self._coerce_positive_int(
            flow_config.get("max_enrich_iterations"),
            default=8 if config.target_word_count >= 10000 else 6 if config.target_word_count >= 7000 else 4 if config.target_word_count >= 4500 else 2,
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
            config.enable_consistency = True

        if preset == "ultimate":
            config.enable_memory = True
            config.enable_consistency = True
            config.enable_enrichment = True
            config.enable_six_dimension = True
            config.enable_reader_sim = True
            config.enable_self_critique = True
            config.enable_preview = False
            config.enable_optimizer = False
            config.allow_truncated_response = False

        if preset == "longform":
            config.enable_memory = True
            config.enable_rag = True
            config.rag_mode = "two_stage"
            config.enable_enrichment = True
            config.enable_consistency = True
            config.enable_self_critique = True
            config.enable_optimizer = True
            config.enable_reader_sim = True
            config.enable_preview = False
            config.allow_truncated_response = False
            if flow_config.get("target_word_count") is None:
                config.target_word_count = 5000
            if flow_config.get("min_word_count") is None:
                config.min_word_count = max(800, int(config.target_word_count * 0.9))

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
            if not enabled_profiles:
                metadata["reason"] = "no_enabled_profiles"
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
            logger.warning("供应商预检失败，继续走运行时回退：user=%s error=%s", user_id, exc)
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
        stable.allow_truncated_response = config.allow_truncated_response
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
    def _attempt_required_success_count(*, required_success_count: int, requested_count: int) -> int:
        """Clamp a retry attempt's threshold to the number of candidates it actually requested."""
        return min(
            max(1, int(required_success_count or 1)),
            max(1, int(requested_count or 1)),
        )

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

    @classmethod
    def _build_continuity_retrieval_injection(cls, history_context: Optional[Dict[str, Any]]) -> str:
        history = history_context or {}
        previous_bundle = history.get("previous_chapter_bundle") if isinstance(history.get("previous_chapter_bundle"), dict) else {}
        previous_tail = str(history.get("previous_tail") or previous_bundle.get("tail_excerpt") or "").strip()
        previous_summary = str(history.get("previous_summary") or previous_bundle.get("summary") or "").strip()
        plot_arc_digest = str(history.get("plot_arc_digest") or "").strip()
        recent_track = str(history.get("recent_track") or "").strip()

        lines: List[str] = []
        if previous_summary:
            lines.append("## 上一章摘要（强制承接）\n" + previous_summary)
        if previous_tail:
            lines.append("## 上一章结尾原文尾巴（开篇必须接住）\n" + cls._truncate_text(previous_tail, 700))
        if plot_arc_digest and "暂无" not in plot_arc_digest and "鏆傛棤" not in plot_arc_digest:
            lines.append("## 未闭环钩子/长线压力（本章至少推进一项）\n" + plot_arc_digest)
        if recent_track:
            lines.append("## 近期章节轨迹（避免断层）\n" + recent_track)
        return "\n\n".join(lines)

    @classmethod
    def _inject_continuity_into_rag(
        cls,
        rag_context: Optional[Dict[str, Any]],
        history_context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        context = dict(rag_context or {"chunks": [], "summaries": []})
        injection = cls._build_continuity_retrieval_injection(history_context)
        if not injection:
            return context
        chunks = list(context.get("chunks") or [])
        summaries = list(context.get("summaries") or [])
        chunks.insert(0, injection)
        summaries.insert(0, "强制连续性上下文：上一章尾巴、近期轨迹与未闭环钩子已注入，正文必须承接并递压。")
        context["chunks"] = chunks
        context["summaries"] = summaries
        context["continuity_injection"] = True
        return context

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
        planned_characters: List[str],
        all_characters: List[str],
        target_word_count: int,
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
            str(max(500, int(target_word_count or 0))),
            json.dumps(introduced_characters, ensure_ascii=False),
            json.dumps(planned_characters, ensure_ascii=False),
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

[本章大纲已提及角色]
{json.dumps(planned_characters, ensure_ascii=False) if planned_characters else "暂无"}

[全部角色]
{json.dumps(all_characters, ensure_ascii=False)}

[写作指令]
{writing_notes}
"""
        plan_input += f"""

[本章字数目标]
目标字数：{target_word_count}
建议最低完成度：{max(int(target_word_count * 0.92), max(1200, int(target_word_count * 0.75)))}

[CHAPTER_DRAFT_CONTRACT]
{self._format_chapter_draft_contract_for_prompt(target_word_count, max(int(target_word_count * 0.9), 500))}

[首稿执行要求]
- 规划出来的 scene_list 必须能直接拿去写正文，不要只给抽象氛围词。
- 每个场景都尽量体现：目标、阻碍、转折、情绪变化、对话职责、收尾钩子。
- 第一场必须尽快落到动作目标或冲突，不要把前 15% 篇幅浪费在纯描写。
- 如果本章预计字数较长，请提前把篇幅分配到场景推进和对话攻防，不要把补字数任务留给后处理。
- scene_list 数量必须服务章节长度：短章 1-3 场，中等章节 3-5 场，7000 字以上建议 5-7 个真实场景或场景组，10000 字以上建议 6-8 个场景组；每场都要有 goal/conflict/turn/payoff/bridge，不要机械碎切正文。
- 输出必须是合法 JSON 对象，至少包含 macro_beat、chapter_purpose、character_arc_task、continuity_anchor、dialogue_strategy、foreshadowing_tasks、scene_list。
- scene_list 每场必须包含 scene、goal、conflict、turn、outcome、payoff、bridge、dialogue_value、end_hook、word_budget；word_budget 要服务目标字数，不要所有场景平均敷衍。
"""

        try:
            json_result = await call_generation_json(
                llm_service=self.llm_service,
                system_prompt=plan_prompt,
                conversation_history=[{"role": "user", "content": plan_input}],
                temperature=0.3,
                user_id=user_id,
                timeout=self._resolve_chapter_mission_timeout(target_word_count),
                policy=GenerationCallPolicy(
                    stage_label="章节导演脚本",
                    progress_stage="generate_mission",
                    retry_attempts=1,
                    response_format="json_object",
                    json_schema=self._build_chapter_mission_schema(),
                    json_schema_name="chapter_mission",
                    json_schema_strict=False,
                    max_tokens=self._resolve_chapter_mission_max_tokens(target_word_count),
                    retry_same_model_once=True,
                    json_repair_attempts=2,
                ),
            )
            mission = self._normalize_chapter_mission(json_result.data, target_word_count)
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
        blueprint = self._normalize_blueprint(project_schema.blueprint.model_dump() if project_schema.blueprint else {})
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

    @staticmethod
    def _resolve_scene_execution_ratios(scene_count: int, sequel_required: bool = False) -> List[float]:
        normalized_count = max(1, min(int(scene_count or 1), 10))
        presets = {
            1: [1.0],
            2: [0.42, 0.58],
            3: [0.24, 0.35, 0.41],
            4: [0.18, 0.26, 0.27, 0.29],
            5: [0.15, 0.2, 0.21, 0.21, 0.23],
            6: [0.12, 0.17, 0.18, 0.18, 0.17, 0.18],
            7: [0.1, 0.14, 0.15, 0.15, 0.15, 0.15, 0.16],
            8: [0.09, 0.12, 0.13, 0.13, 0.13, 0.13, 0.13, 0.14],
        }
        if normalized_count in presets:
            ratios = list(presets[normalized_count])
        else:
            raw = [1.0 + (0.04 if index in {normalized_count - 1, normalized_count} else 0.0) for index in range(1, normalized_count + 1)]
            total = sum(raw)
            ratios = [round(item / total, 4) for item in raw]
        if sequel_required and ratios:
            ratios = [round(item * 0.94, 4) for item in ratios]
        total = sum(ratios) or 1.0
        return [round(item / total, 4) for item in ratios]

    @staticmethod
    def _build_scene_execution_ledger(
        *,
        chapter_mission: Optional[dict],
        outline_title: str,
        outline_summary: str,
        target_word_count: int,
        min_word_count: int,
    ) -> Optional[str]:
        if not isinstance(chapter_mission, dict):
            return None

        scene_list = [scene for scene in (chapter_mission.get("scene_list") or []) if isinstance(scene, dict)]
        if not scene_list:
            return None

        target_word_count = max(0, int(target_word_count or 0))
        min_word_count = max(0, int(min_word_count or 0))
        draft_contract = PipelineOrchestrator._resolve_chapter_draft_contract(target_word_count, min_word_count)
        preferred_floor = max(min_word_count, int(target_word_count * 0.92)) if target_word_count else min_word_count
        sequel_required = bool(chapter_mission.get("sequel_required"))
        dialogue_expected = PipelineOrchestrator._chapter_mission_expects_dialogue(chapter_mission)
        ratios = PipelineOrchestrator._resolve_scene_execution_ratios(len(scene_list), sequel_required=sequel_required)
        opening_limit = max(180, int(target_word_count * 0.14)) if target_word_count else 180

        lines = [
            f"本章标题：{outline_title}",
            f"本章摘要：{outline_summary}",
            f"目标字数：尽量写到 {target_word_count} 字，至少不要低于 {min_word_count} 字，优先冲到 {preferred_floor} 字以上。",
            f"生成策略：{draft_contract['generation_strategy']}；建议场景/场景组数量 {draft_contract['recommended_scene_count_min']}-{draft_contract['recommended_scene_count_max']}，场景组只是规划单位，正文必须保持整章连续。",
            f"开篇推进时限：前 {opening_limit} 字左右内，必须让读者看见本章动作目标和第一层阻碍，禁止把开场耗在纯氛围、纯回忆、纯解释上。",
            "段落推进规则：每 2-3 段至少发生一次可感知变化（动作推进 / 对话攻防 / 信息释放 / 关系变化 / 风险升级），不要连续空转。",
            "长章密度规则：每 900-1500 字至少有一次实质状态变化，不能连续用解释、背景介绍或同义心理独白凑篇幅。",
            "场景衔接规则：下一段必须吃住上一段留下的动作、情绪或风险，不要只靠关键词拼接。",
        ]
        if len(scene_list) < int(draft_contract["recommended_scene_count_min"]):
            lines.append(
                "场景数量偏少时的补强规则：不要新增无关支线，必须把现有场景扩成更完整的攻防回合、试探、反击、代价、余波和过渡。"
            )
        if dialogue_expected:
            lines.append("对话硬要求：只要进入对话场，至少两轮来回，其中一轮必须改变主动权、信息量或风险级别。")

        continuity_anchor = chapter_mission.get("continuity_anchor") or {}
        inherit_items = continuity_anchor.get("inherit_from_previous") or []
        deliver_items = continuity_anchor.get("deliver_to_next") or []
        if inherit_items:
            lines.append("承接上章时必须落地：" + " / ".join(str(item) for item in inherit_items[:3]))
        if deliver_items:
            lines.append("章末必须递交的新压力：" + " / ".join(str(item) for item in deliver_items[:3]))

        lines.append("")
        lines.append("场景执行清单：")
        for idx, scene in enumerate(scene_list):
            ratio = ratios[idx] if idx < len(ratios) else max(0.12, round(1 / len(scene_list), 4))
            suggested_words = max(220, int(target_word_count * ratio)) if target_word_count else 0
            lines.extend(
                [
                    f"{idx + 1}. 场景{scene.get('scene') or idx + 1} | 建议篇幅 {suggested_words} 字左右",
                    f"   - 本场必须完成：{str(scene.get('goal') or '推动本场核心目标').strip()}",
                    f"   - 正面阻碍：{str(scene.get('conflict') or '制造明确阻碍').strip()}",
                    f"   - 本场转折：{str(scene.get('turn') or '让局势发生变化').strip()}",
                    f"   - 情绪变化：{str(scene.get('emotion_shift') or '情绪必须变化').strip()}",
                    f"   - 对话职责：{str(scene.get('dialogue_value') or '对话承担推进职责').strip()}",
                    f"   - 收尾钩子：{str(scene.get('end_hook') or '给下一场或章末留下压力').strip()}",
                ]
            )
            if idx == 0:
                lines.append("   - 开场要求：尽快把人物拉进动作、试探、威胁或决策，不许只铺环境。")
            if idx < len(scene_list) - 1:
                lines.append("   - 过渡要求：本场结尾必须自然推出下一场，不要用总结句硬切。")
            else:
                lines.append("   - 章末要求：必须让局势相比章首发生实质变化，再把压力递到下一章。")

        if sequel_required:
            sequel_description = str(chapter_mission.get("sequel_description") or "").strip()
            lines.append("")
            lines.append("短余波限制：只允许用短余波压实后果与下一步决策，不准用大段抒情或解释替代剧情推进。")
            if sequel_description:
                lines.append(f"短余波用途：{sequel_description}")

        lines.extend(
            [
                "",
                "补字数优先级：先补场景内攻防回合、动作过程、因果后果、关系变化，再补必要感官细节；禁止靠重复描写和同义心理独白凑字数。",
                "如果某一场戏明显写短，优先把该场的目标、阻碍、反击、转折、余波写完整，不要额外平移出无关描写段落。",
            ]
        )
        return "\n".join(line for line in lines if line is not None).strip()

    @staticmethod
    def _prompt_section_priority(title: str) -> int:
        priorities = {
            "[当前章节目标]": 0,
            "[章节导演脚本](JSON)": 1,
            "[长线连续性摘要](安全压缩)": 2,
            "[长篇上下文包](角色/伏笔/时间线)": 2.5,
            "[上一章摘要]": 3,
            "[上一章结尾]": 4,
            "[连续性硬性约束]": 5,
            "[章节长度约束]": 6,
            "[禁止角色](本章不允许提及)": 7,
            "[角色/关系/伏笔/线索指导]": 8,
            "[项目长期记忆](摘要/剧情线)": 9,
            "[记忆层上下文]": 10,
            "[当前启用文风参考]": 11,
            "[RAG精筛上下文](含POV裁剪)": 12,
            "[检索到的章节摘要](Markdown)": 13,
            "[检索到的剧情上下文](Markdown)": 14,
            "[世界蓝图](JSON，已裁剪)": 15,
        }
        priorities["[SCENE_EXECUTION_LEDGER]"] = 1.5
        return priorities.get(title, 50)

    def _apply_prompt_budget(self, sections: List[Tuple[str, str]], *, max_tokens: int = 6000) -> List[Tuple[str, str]]:
        prioritized_sections = [
            section
            for _, section in sorted(
                enumerate(sections),
                key=lambda item: (self._prompt_section_priority(item[1][0]), item[0]),
            )
        ]

        budgeted: List[Tuple[str, str]] = []
        remaining = max_tokens
        for title, content in prioritized_sections:
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
        preset: str = "quality",
        writer_blueprint: Dict[str, Any],
        previous_summary: str,
        previous_tail: str,
        chapter_mission: Optional[dict],
        macro_continuity_context: Optional[str],
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
        longform_context_text: Optional[str] = None,
    ) -> List[Tuple[str, str]]:
        blueprint_text = json.dumps(writer_blueprint, ensure_ascii=False, indent=2)
        scene_execution_ledger = PipelineOrchestrator._build_scene_execution_ledger(
            chapter_mission=chapter_mission,
            outline_title=outline_title,
            outline_summary=outline_summary,
            target_word_count=target_word_count,
            min_word_count=min_word_count,
        )
        mission_text = json.dumps(chapter_mission, ensure_ascii=False, indent=2) if chapter_mission else "无导演脚本"
        forbidden_text = json.dumps(forbidden_characters, ensure_ascii=False) if forbidden_characters else "无"

        draft_contract_rules = PipelineOrchestrator._format_chapter_draft_contract_for_prompt(
            target_word_count,
            min_word_count,
        )
        continuity_rules = (
            "- 开篇必须承接上一章结尾，禁止无过渡时间跳跃。\n"
            "- 角色认知边界要与前文一致，不能突然知道未知信息。\n"
            "- 本章必须完成一个可感知的最小戏剧单元：目标推进 / 阻碍升级 / 局部反转 / 代价或收获，至少满足其中三项。\n"
            "- 本章至少推进一条既有冲突或未闭环线索，且要让局势与章首相比发生实质变化。\n"
            "- 必须写出明确的情绪变化链条，不能全章一个温度。\n"
            "- 关键角色至少出现一个可感知的心理变化、关系变化、立场变化或决策变化。\n"
            "- 对话必须承担试探、压迫、欺骗、暧昧、结盟、撕裂等至少一种功能，且至少出现两轮有效攻防，禁止空转闲聊。\n"
            "- 重要场景必须具备目标、阻碍、转折、余波，避免纯说明段落。\n"
            "- 连续三段以上不能只做景物描写、心理回声或背景说明，必须回到动作、对白或局势变化。\n"
            "- 环境描写必须服务情绪与冲突，至少调动两种感官，不要只写看见了什么。\n"
            "- 节奏必须有呼吸，紧张处短句、缓冲处留白，避免均匀段长和提纲扩写感。\n"
            "- 章末钩子要与主线相关，禁止新开无关支线；可以留压力，但不能让本章像没发生真正事件。"
        )
        length_rules = (
            f"{draft_contract_rules}\n"
            f"- 目标字数约 {target_word_count} 字，硬性底线为 {min_word_count} 字。\n"
            f"- 优先保证承接、推进、转折、余波和章末牵引完整；在此基础上必须尽量逼近目标字数，不能主动提前收笔。\n"
            f"- 若篇幅不足，优先补足当前章既有冲突内的场景推进、心理变化、动作过程、对话博弈、局势反噬与余波，不要用独立景物描写或总结句拉长。\n"
            f"- 禁止为了凑字数重复表达同一信息；必须通过新增有效正文补足必要篇幅。"
        )

        sections: List[Tuple[str, str]] = [
            ("[当前章节目标]", f"标题：{outline_title}\n摘要：{outline_summary}\n写作要求：{writing_notes}"),
            ("[章节导演脚本](JSON)", mission_text),
        ]
        if macro_continuity_context:
            sections.append(("[长线连续性摘要](安全压缩)", macro_continuity_context))
        if longform_context_text:
            sections.append(("[长篇上下文包](角色/伏笔/时间线)", longform_context_text))
        if scene_execution_ledger:
            sections.append(("[SCENE_EXECUTION_LEDGER]", scene_execution_ledger))
        sections.extend(
            [
                ("[上一章摘要]", previous_summary or "暂无（这是第一章）"),
                ("[上一章结尾]", previous_tail or "暂无（这是第一章）"),
                ("[连续性硬性约束]", continuity_rules),
                ("[章节长度约束]", length_rules),
                ("[禁止角色](本章不允许提及)", forbidden_text),
            ]
        )

        if analysis_guidance_context:
            sections.append(("[角色/关系/伏笔/线索指导]", analysis_guidance_context))
        if project_memory_text:
            sections.append(("[项目长期记忆](摘要/剧情线)", project_memory_text))
        if memory_context:
            sections.append(("[记忆层上下文]", memory_context))
        if style_context:
            sections.append(("[当前启用文风参考]", style_context))
        if knowledge_context:
            sections.append(("[RAG精筛上下文](含POV裁剪)", knowledge_context))

        if rag_context:
            rag_chunks_text = "\n\n".join(rag_context.get("chunks", [])) or "未检索到章节片段"
            rag_summaries_text = "\n".join(rag_context.get("summaries", [])) or "未检索到章节摘要"
            sections.append(("[检索到的章节摘要](Markdown)", rag_summaries_text))
            sections.append(("[检索到的剧情上下文](Markdown)", rag_chunks_text))

        sections.append(("[世界蓝图](JSON，已裁剪)", blueprint_text))

        # lightweight/basic preset: strip non-essential sections to reduce prompt size for constrained APIs
        if preset in ("basic", "lightweight", "fast"):
            essential_keys = {
                "[当前章节目标]", "[章节导演脚本](JSON)", "[上一章摘要]",
                "[上一章结尾]", "[连续性硬性约束]", "[章节长度约束]", "[禁止角色](本章不允许提及)",
                "[世界蓝图](JSON，已裁剪)",
            }
            sections = [(k, v) for k, v in sections if k in essential_keys]
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
            "冲突推进优先，描写只服务情绪与动作，避免空转内心戏和静态景物铺陈",
            "冲突更强，节奏更快，多写动作和对话博弈",
            "悬念更重，多埋伏笔，结尾钩子更强，但不要牺牲当前章的动作推进",
        ][:version_count]

    @staticmethod
    def _resolve_pov_character(chapter_mission: Optional[dict]) -> Optional[str]:
        if not chapter_mission:
            return None
        return chapter_mission.get("pov") or chapter_mission.get("pov_character")

    @classmethod
    def _evaluate_first_draft_retry(
        cls,
        *,
        content: str,
        violations: Optional[List[Dict[str, Any]]],
        chapter_mission: Optional[dict],
        target_word_count: int,
        min_word_count: int,
    ) -> Tuple[bool, Dict[str, Any], List[str]]:
        story_guard = cls._score_story_quality_candidate(
            content=content,
            violations=list(violations or []),
            chapter_mission=chapter_mission,
        )
        target_word_count = max(0, int(target_word_count or 0))
        min_word_count = max(0, int(min_word_count or 0))
        draft_contract = cls._resolve_chapter_draft_contract(target_word_count, min_word_count)
        preferred_floor = int(draft_contract.get("retry_floor") or max(min_word_count, int(target_word_count * 0.88))) if target_word_count else min_word_count
        scene_floor = 0.72 if target_word_count >= 4500 else 0.58
        dialogue_floor = max(4, len((chapter_mission or {}).get("scene_list") or []) * 2)
        scene_soft_pass = bool(
            (
                int(story_guard.get("mission_hit_count") or 0) >= 3
                or float(story_guard.get("scene_fulfillment_rate") or 0) >= 0.75
            )
            and int(story_guard.get("dialogue_marker_count") or 0) >= 4
            and not story_guard.get("static_description_risk")
            and story_guard.get("dialogue_changes_state", True)
            and story_guard.get("ending_pressure_passed", story_guard.get("ending_hook_detected", True))
            and story_guard.get("event_density_passed", True)
        )
        density_soft_pass = bool(
            int(story_guard.get("mission_hit_count") or 0) >= 4
            and int(story_guard.get("dialogue_marker_count") or 0) >= 8
            and story_guard.get("dialogue_changes_state", True)
            and story_guard.get("ending_pressure_passed", story_guard.get("ending_hook_detected", True))
            and not story_guard.get("static_description_risk")
        )

        reasons: List[str] = []
        if story_guard.get("static_description_risk"):
            reasons.append("static_description_risk")
        if story_guard.get("expected_dialogue") and int(story_guard.get("dialogue_marker_count") or 0) < dialogue_floor:
            reasons.append("dialogue_pressure_weak")
        if int(story_guard.get("mission_hit_count") or 0) < 2:
            reasons.append("mission_progression_weak")
        if (
            int(story_guard.get("scene_count") or 0) > 0
            and float(story_guard.get("scene_fulfillment_rate") or 1.0) < scene_floor
            and not scene_soft_pass
        ):
            reasons.append("scene_fulfillment_weak")
        if (
            int(story_guard.get("scene_count") or 0) > 0
            and float(story_guard.get("scene_structure_rate") or 1.0) < (0.58 if target_word_count >= 4500 else 0.45)
            and not scene_soft_pass
        ):
            reasons.append("scene_structure_weak")
        if story_guard.get("expected_dialogue") and not story_guard.get("dialogue_changes_state", True):
            reasons.append("dialogue_does_not_change_state")
        if int(story_guard.get("word_count") or 0) >= 1200 and not story_guard.get("ending_pressure_passed", story_guard.get("ending_hook_detected")):
            reasons.append("ending_pressure_missing")
        if preferred_floor and int(story_guard.get("word_count") or 0) < preferred_floor:
            reasons.append("word_count_far_below_target")
        if (
            int(story_guard.get("word_count") or 0) >= 1800
            and story_guard.get("event_density_passed") is False
            and not density_soft_pass
        ):
            reasons.append("event_density_weak")
        if (
            int(story_guard.get("word_count") or 0) >= 2500
            and story_guard.get("state_change_interval_passed") is False
            and not density_soft_pass
        ):
            reasons.append("state_change_interval_weak")
        if target_word_count >= 7000 and int(story_guard.get("paragraph_count") or 0) < 10:
            reasons.append("long_chapter_scene_density_weak")
        if (
            target_word_count >= 7000
            and story_guard.get("long_chapter_density_passed") is False
            and not density_soft_pass
        ):
            reasons.append("long_chapter_event_density_weak")
        return bool(reasons), story_guard, reasons

    @classmethod
    def _build_first_draft_retry_feedback(
        cls,
        *,
        story_guard: Dict[str, Any],
        reason_codes: List[str],
        chapter_mission: Optional[dict],
        target_word_count: int,
        min_word_count: int,
    ) -> str:
        reason_map = {
            "static_description_risk": "上一版静态描写占比过高，缺少有效动作/对话承压。",
            "dialogue_pressure_weak": "上一版对话攻防不足，对白没有把局势顶起来。",
            "mission_progression_weak": "上一版对本章目标、冲突、转折的命中不够，实质推进偏少。",
            "scene_fulfillment_weak": "上一版没有逐场兑现导演脚本，场景目标、阻碍、转折或钩子落地不足。",
            "dialogue_does_not_change_state": "上一版对白没有造成主动权、信息量、风险或关系状态变化。",
            "ending_pressure_missing": "上一版结尾没有把压力、后果或危险递给下一章，收得太平。",
            "word_count_far_below_target": "上一版字数离目标差距过大，很多该展开的场景没有写满。",
            "long_chapter_scene_density_weak": "上一版是长章目标，但段落/场景密度不足，像把少量内容拉长而不是写出足够事件。",
            "event_density_weak": "上一版事件密度不足，正文没有稳定出现行动、阻碍、反击、发现、代价或关系变化。",
            "state_change_interval_weak": "上一版存在过长区间没有状态变化，容易读成解释、回忆或气氛拉长。",
            "scene_structure_weak": "上一版点到了场景词，但缺少目标、阻碍、转折、结果/压力的完整场景结构。",
            "long_chapter_event_density_weak": "上一版按长章目标生成，但没有提供足够多的有效事件和状态变化。",
        }
        mission_keywords = story_guard.get("mission_hits") or cls._collect_fallback_mission_keywords(chapter_mission)[:8]
        focus_text = " / ".join(str(item) for item in mission_keywords[:6]) if mission_keywords else "本章目标、冲突、转折、章末压力"
        lines = [
            "请重写这一版正文，不要修修补补地补描写，要直接把剧情场景写扎实。",
            f"目标字数：尽量接近 {target_word_count} 字，至少不要低于 {min_word_count} 字。",
            "本次重写优先级：先保证承接、推进、反击、转折、余波完整，再考虑文气。",
            f"必须重点命中：{focus_text}",
            "如果进入对话场，至少两轮来回，其中一轮必须让主动权、信息量或风险发生变化。",
            "请把字数主要补在场景执行里：动作回合、试探压迫、因果后果、关系变化，不要补成纯景物描写。",
            "每 900-1500 字至少交出一次可见状态变化：新信息、代价、关系转向、风险升级、行动结果或伏笔兑现。",
            "",
            "上一版主要问题：",
        ]
        for code in reason_codes:
            lines.append(f"- {reason_map.get(code, code)}")
        lines.append("请直接输出新的完整章节正文，不要解释。")
        return "\n".join(lines).strip()

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
        analysis_guidance_context: Optional[str],
        enhanced_context: Optional[Dict[str, Any]],
        config: PipelineConfig,
        progress_callback: Optional[Callable[[str, str], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        with LLMService.daily_limit_scope(f"writer_version:{project_id}:{chapter_number}:{index}:{user_id}"):
            version_started_at = time.perf_counter()
            metadata: Dict[str, Any] = {
                "chapter_mission": chapter_mission,
                "style_hint": style_hint,
                "pipeline": {"preset": config.preset},
            }

            def record_generation_call_metrics(label: str, text_result: Any) -> None:
                metrics = {
                    "label": label,
                    "attempts": getattr(text_result, "attempts", None),
                    "provider_error_type": getattr(text_result, "provider_error_type", None),
                    "effective_max_tokens": getattr(text_result, "effective_max_tokens", None),
                    "estimated_input_tokens": getattr(text_result, "estimated_input_tokens", None),
                    "estimated_output_tokens": getattr(text_result, "estimated_output_tokens", None),
                    "estimated_total_tokens": getattr(text_result, "estimated_total_tokens", None),
                    "prompt_character_count": getattr(text_result, "prompt_character_count", None),
                    "output_character_count": getattr(text_result, "output_character_count", None),
                }
                metadata.setdefault("generation_call_metrics", []).append(
                    {key: value for key, value in metrics.items() if value is not None}
                )

            async def run_writer_pass(
                *,
                temperature: float,
                additional_feedback: Optional[str] = None,
                prior_excerpt: Optional[str] = None,
            ) -> str:
                nonlocal generation_duration_ms

                final_prompt_input = prompt_input
                final_prompt_input += (
                    f"\n\n[本次输出红线]\n"
                    f"- 直接输出完整章节正文，不要解释。\n"
                    f"- 先保证承接、冲突推进、角色变化、局势反转与章末牵引完整，再追求文气。\n"
                    f"- {self._format_chapter_draft_contract_for_prompt(config.target_word_count, config.min_word_count)}\n"
                    f"- 目标字数：{config.target_word_count}；最低字数：{config.min_word_count}。不要刚过底线就提前收束，要把该展开的场景写满。\n"
                    f"- 字数优先写在场景执行里：对话攻防、动作过程、因果后果、关系变化、短余波，不要写成纯描写补字数。\n"
                )
                if additional_feedback:
                    final_prompt_input += f"\n\n[首稿回炉要求]\n{additional_feedback}"
                if prior_excerpt:
                    final_prompt_input += f"\n\n[上一版片段（只用于识别缺陷，不要照抄）]\n{prior_excerpt}"
                if style_hint:
                    final_prompt_input += f"\n\n[版本风格提示]\n{style_hint}"

                generation_started_at = time.perf_counter()
                try:
                    text_result = await call_generation_text(
                        llm_service=self.llm_service,
                        system_prompt=writer_prompt,
                        conversation_history=[{"role": "user", "content": final_prompt_input}],
                        temperature=temperature,
                        user_id=user_id,
                        timeout=self._resolve_chapter_generation_timeout(config.target_word_count),
                        policy=GenerationCallPolicy(
                            stage_label=f"章节正文候选 {index + 1}",
                            progress_stage="generate_variants",
                            retry_attempts=2,
                            response_format=None,
                            max_tokens=self._resolve_chapter_generation_max_tokens(config.target_word_count),
                            prompt_cache_key=f"xq:{project_id}:{chapter_number}:draft",
                            allow_truncated_response=config.allow_truncated_response,
                            retry_same_model_once=True,
                            heartbeat_interval_seconds=60.0,
                            soft_timeout_seconds=self._resolve_chapter_generation_soft_timeout(config.target_word_count),
                        ),
                        progress_callback=progress_callback,
                    )
                    record_generation_call_metrics(f"draft_candidate_{index + 1}", text_result)
                    response = text_result.text
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

                generation_duration_ms += round((time.perf_counter() - generation_started_at) * 1000, 2)
                cleaned = remove_think_tags(response)
                return unwrap_markdown_json(cleaned)

            async def apply_guardrails(text: str) -> Tuple[str, Dict[str, Any], float, float]:
                guardrail_check_started_at = time.perf_counter()
                guardrail_result = self.guardrails.check(
                    generated_text=text,
                    forbidden_characters=forbidden_characters,
                    allowed_new_characters=allowed_new_characters,
                    pov=chapter_mission.get("pov") if chapter_mission else None,
                )
                guardrail_check_ms = round((time.perf_counter() - guardrail_check_started_at) * 1000, 2)
                guardrail_rewrite_ms = 0.0
                guardrail_meta = {"passed": guardrail_result.passed, "violations": []}

                if not guardrail_result.passed:
                    guardrail_meta["violations"] = [
                        {
                            "type": violation.type,
                            "severity": violation.severity,
                            "description": violation.description,
                            "location": violation.context,
                            "context": violation.context,
                        }
                        for violation in guardrail_result.violations
                    ]
                    violations_text = self.guardrails.format_violations_for_rewrite(guardrail_result)
                    guardrail_rewrite_started_at = time.perf_counter()
                    text = await self._rewrite_with_guardrails(
                        original_text=text,
                        chapter_mission=chapter_mission,
                        violations_text=violations_text,
                        user_id=user_id,
                    )
                    guardrail_rewrite_ms = round((time.perf_counter() - guardrail_rewrite_started_at) * 1000, 2)

                return text, guardrail_meta, guardrail_check_ms, guardrail_rewrite_ms

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
                    target_word_count=config.target_word_count,
                    user_id=user_id,
                )
                generation_duration_ms = round((time.perf_counter() - preview_started_at) * 1000, 2)
                metadata["preview"] = preview_meta

            if not content:
                content = await run_writer_pass(temperature=0.9)
            if not content:
                final_prompt_input = prompt_input
                final_prompt_input += (
                    f"\n\n[本次输出红线]\n"
                    f"- 直接输出完整章节正文，不要解释。\n"
                    f"- 先保证剧情承接、冲突推进、角色变化与章末牵引完整。\n"
                    f"- {self._format_chapter_draft_contract_for_prompt(config.target_word_count, config.min_word_count)}\n"
                    f"- 目标字数约 {config.target_word_count}；最低字数：{config.min_word_count}。在保证质量的前提下，必须尽量逼近目标字数，不能写到刚过底线就提前收束。"
                )
                if style_hint:
                    final_prompt_input += f"\n\n[版本风格提示]\n{style_hint}"

                generation_started_at = time.perf_counter()
                try:
                    text_result = await call_generation_text(
                        llm_service=self.llm_service,
                        system_prompt=writer_prompt,
                        conversation_history=[{"role": "user", "content": final_prompt_input}],
                        temperature=0.9,
                        user_id=user_id,
                        timeout=self._resolve_chapter_generation_timeout(config.target_word_count),
                        policy=GenerationCallPolicy(
                            stage_label=f"章节正文候选 {index + 1} 兜底生成",
                            progress_stage="generate_variants",
                            retry_attempts=2,
                            response_format=None,
                            max_tokens=self._resolve_chapter_generation_max_tokens(config.target_word_count),
                            prompt_cache_key=f"xq:{project_id}:{chapter_number}:draft",
                            allow_truncated_response=config.allow_truncated_response,
                            retry_same_model_once=True,
                            heartbeat_interval_seconds=60.0,
                            soft_timeout_seconds=self._resolve_chapter_generation_soft_timeout(config.target_word_count),
                        ),
                        progress_callback=progress_callback,
                    )
                    record_generation_call_metrics(f"draft_candidate_{index + 1}_fallback", text_result)
                    response = text_result.text
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

            retry_needed, initial_story_guard, retry_reason_codes = self._evaluate_first_draft_retry(
                content=content,
                violations=guardrail_metadata.get("violations"),
                chapter_mission=chapter_mission,
                target_word_count=config.target_word_count,
                min_word_count=config.min_word_count,
            )
            story_progression_guard = initial_story_guard
            first_draft_retry_metadata: Dict[str, Any] = {
                "used": False,
                "reason_codes": retry_reason_codes,
                "before": initial_story_guard,
            }
            if retry_needed:
                retry_feedback = self._build_first_draft_retry_feedback(
                    story_guard=initial_story_guard,
                    reason_codes=retry_reason_codes,
                    chapter_mission=chapter_mission,
                    target_word_count=config.target_word_count,
                    min_word_count=config.min_word_count,
                )
                retry_candidate = await run_writer_pass(
                    temperature=0.55,
                    additional_feedback=retry_feedback,
                    prior_excerpt=self._truncate_text(content, 1800),
                )
                retry_candidate, retry_guardrail_metadata, retry_guardrail_check_ms, retry_guardrail_rewrite_ms = await apply_guardrails(retry_candidate)
                guardrail_check_duration_ms += retry_guardrail_check_ms
                guardrail_rewrite_duration_ms += retry_guardrail_rewrite_ms
                retry_story_guard = self._score_story_quality_candidate(
                    content=retry_candidate,
                    violations=retry_guardrail_metadata.get("violations") or [],
                    chapter_mission=chapter_mission,
                )
                retry_score = int(retry_story_guard.get("score") or 0)
                current_score = int(initial_story_guard.get("score") or 0)
                retry_word_count = int(retry_story_guard.get("word_count") or 0)
                initial_word_count = int(initial_story_guard.get("word_count") or 0)
                meaningful_word_gain = max(300, int(config.target_word_count * (0.06 if config.target_word_count >= 7000 else 0.08)))
                retry_reaches_floor = retry_word_count >= max(config.min_word_count, int(config.target_word_count * 0.9))
                accept_retry = bool(
                    retry_score >= current_score + 120
                    or (
                        retry_story_guard.get("guardrail_violation_count", 0)
                        < initial_story_guard.get("guardrail_violation_count", 0)
                    )
                    or (
                        retry_story_guard.get("mission_hit_count", 0) >= initial_story_guard.get("mission_hit_count", 0)
                        and retry_word_count >= initial_word_count + meaningful_word_gain
                    )
                    or (
                        retry_reaches_floor
                        and retry_story_guard.get("mission_hit_count", 0) >= initial_story_guard.get("mission_hit_count", 0)
                        and retry_score >= current_score - 80
                        and not retry_story_guard.get("static_description_risk")
                    )
                )
                first_draft_retry_metadata.update(
                    {
                        "used": True,
                        "accepted": accept_retry,
                        "after": retry_story_guard,
                        "after_guardrail": retry_guardrail_metadata,
                    }
                )
                if accept_retry:
                    content = retry_candidate
                    guardrail_metadata = retry_guardrail_metadata
                    story_progression_guard = retry_story_guard

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
            metadata["first_draft_retry"] = first_draft_retry_metadata
            metadata["story_progression_guard"] = story_progression_guard
            metadata["quality_metrics"] = story_progression_guard.get("quality_metric_snapshot", story_progression_guard)
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
        target_word_count: int,
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
            target_word_count=target_word_count,
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
            text_result = await call_generation_text(
                llm_service=self.llm_service,
                system_prompt=rewrite_prompt,
                conversation_history=[{"role": "user", "content": rewrite_input}],
                temperature=0.3,
                user_id=user_id,
                timeout=120.0,
                policy=GenerationCallPolicy(
                    stage_label="章节护栏局部修复",
                    progress_stage="consistency",
                    retry_attempts=2,
                    response_format=None,
                    max_tokens=8000,
                    retry_same_model_once=True,
                ),
            )
            cleaned = remove_think_tags(text_result.text)
            guard_failure = self._guardrail_rewrite_guard_failure(original_text, cleaned, chapter_mission=chapter_mission)
            if guard_failure:
                logger.warning("Chapter guardrail rewrite rejected by continuity guard: reason=%s", guard_failure)
                return original_text
            return cleaned
        except Exception as exc:
            logger.warning("自动修复失败，返回原文: %s", exc)
            return original_text

    @staticmethod
    def _guardrail_rewrite_guard_failure(
        original_text: str,
        rewritten_text: str,
        chapter_mission: Optional[dict] = None,
    ) -> Optional[str]:
        original = str(original_text or "").strip()
        rewritten = str(rewritten_text or "").strip()
        if not rewritten:
            return "empty_rewrite"
        if rewritten.startswith("{") and "content" in rewritten[:240].lower():
            return "raw_json_returned"

        original_compact = re.sub(r"\s+", "", original)
        rewritten_compact = re.sub(r"\s+", "", rewritten)
        if len(original_compact) >= 1200 and len(rewritten_compact) < int(len(original_compact) * 0.72):
            return "rewrite_shrank_too_much"
        if len(original_compact) >= 400 and len(rewritten_compact) < int(len(original_compact) * 0.58):
            return "rewrite_lost_too_much"

        original_paragraphs = [part.strip() for part in re.split(r"\n\s*\n", original) if part.strip()]
        rewritten_paragraphs = [part.strip() for part in re.split(r"\n\s*\n", rewritten) if part.strip()]
        if len(original_paragraphs) >= 6 and len(rewritten_paragraphs) < max(3, len(original_paragraphs) // 3):
            return "rewrite_collapsed_paragraph_structure"

        anchors: List[str] = []
        if original_paragraphs:
            first = re.sub(r"\s+", "", original_paragraphs[0])
            last = re.sub(r"\s+", "", original_paragraphs[-1])
            if len(first) >= 16:
                anchors.append(first[:24])
            if len(last) >= 16:
                anchors.append(last[-24:])
        if len(anchors) >= 2 and all(anchor not in rewritten_compact for anchor in anchors):
            return "rewrite_lost_front_and_back_anchors"
        if isinstance(chapter_mission, dict):
            mission_keywords = PipelineOrchestrator._collect_fallback_mission_keywords(chapter_mission)
            if mission_keywords:
                original_lower = original.lower()
                rewritten_lower = rewritten.lower()
                required: List[str] = []
                for keyword in mission_keywords:
                    for token in PipelineOrchestrator._extract_quality_tokens(keyword):
                        normalized = str(token or "").strip().lower()
                        if len(normalized) < 3:
                            continue
                        if normalized in original_lower and normalized not in required:
                            required.append(normalized)
                    if len(required) >= 12:
                        break
                if len(required) >= 2:
                    kept = [token for token in required if token in rewritten_lower]
                    if len(kept) < max(1, len(required) // 2):
                        return "rewrite_lost_mission_continuity_terms"
        return None

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
    def _collect_fallback_mission_keywords(chapter_mission: Optional[dict]) -> List[str]:
        if not isinstance(chapter_mission, dict):
            return []

        candidates: List[str] = []

        def add_phrase(value: Any) -> None:
            if not value:
                return
            if isinstance(value, dict):
                for item in value.values():
                    add_phrase(item)
                return
            if isinstance(value, list):
                for item in value:
                    add_phrase(item)
                return

            text = str(value).strip()
            if not text:
                return
            if 2 <= len(text) <= 24:
                candidates.append(text)
            for token in re.split(r"[，。；、,\s/]+", text):
                normalized = token.strip("：:- ").strip()
                if 2 <= len(normalized) <= 12:
                    candidates.append(normalized)

        add_phrase(chapter_mission.get("chapter_purpose"))
        add_phrase((chapter_mission.get("continuity_anchor") or {}).get("inherit_from_previous"))
        add_phrase((chapter_mission.get("continuity_anchor") or {}).get("deliver_to_next"))
        add_phrase(chapter_mission.get("character_arc_task"))
        add_phrase(chapter_mission.get("pov"))
        add_phrase(chapter_mission.get("pov_character"))
        add_phrase(chapter_mission.get("focus_characters"))
        add_phrase((chapter_mission.get("dialogue_strategy") or {}).get("purpose"))
        add_phrase((chapter_mission.get("dialogue_strategy") or {}).get("subtext"))
        for scene in chapter_mission.get("scene_list") or []:
            if isinstance(scene, dict):
                add_phrase(scene.get("characters"))
                for key in (
                    "goal",
                    "conflict",
                    "turn",
                    "outcome",
                    "payoff",
                    "bridge",
                    "emotion_shift",
                    "dialogue_value",
                    "end_hook",
                    "foreshadowing_task",
                ):
                    add_phrase(scene.get(key))

        deduped: List[str] = []
        seen = set()
        for item in candidates:
            if item not in seen:
                seen.add(item)
                deduped.append(item)
        return deduped[:24]

    @staticmethod
    def _chapter_mission_expects_dialogue(chapter_mission: Optional[dict]) -> bool:
        if not isinstance(chapter_mission, dict):
            return False
        dialogue_strategy = chapter_mission.get("dialogue_strategy")
        if isinstance(dialogue_strategy, dict) and dialogue_strategy:
            return True
        for scene in chapter_mission.get("scene_list") or []:
            if isinstance(scene, dict) and any(scene.get(key) for key in ("dialogue_value", "conflict", "turn")):
                return True
        return False

    @staticmethod
    def _extract_quality_tokens(value: Any) -> List[str]:
        if not value:
            return []
        if isinstance(value, dict):
            tokens: List[str] = []
            for item in value.values():
                tokens.extend(PipelineOrchestrator._extract_quality_tokens(item))
            return tokens
        if isinstance(value, list):
            tokens: List[str] = []
            for item in value:
                tokens.extend(PipelineOrchestrator._extract_quality_tokens(item))
            return tokens

        text = str(value).strip()
        if not text:
            return []
        stop_tokens = {
            "本章", "主角", "目标", "冲突", "转折", "压力", "下一章", "下一场",
            "必须", "不能", "需要", "继续", "同时", "最终", "真正", "方式",
        }
        tokens = [text] if 2 <= len(text) <= 32 and text not in stop_tokens else []
        for token in re.split(r"[，。；、！？：:\s/|,.;!?()\[\]{}<>《》“”\"'\\-]+", text):
            token = token.strip()
            if 2 <= len(token) <= 12:
                tokens.append(token)
            compact = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", token)
            if 5 <= len(compact) <= 18:
                # 章节任务常把“潮宗正式发缉印令”这类动作+名词写成一整句，
                # 正文更可能只落到“缉印令”。补充较短的命名片段，减少硬关键词误杀。
                for size in (5, 4, 3):
                    for start in range(0, max(0, len(compact) - size + 1)):
                        piece = compact[start:start + size]
                        if piece and piece not in stop_tokens:
                            tokens.append(piece)

        deduped: List[str] = []
        seen = set()
        for token in tokens:
            if token not in seen and token not in stop_tokens:
                seen.add(token)
                deduped.append(token)
        return deduped[:20]

    @classmethod
    def _score_text_hits(cls, value: Any, condensed_text: str) -> Tuple[int, List[str]]:
        tokens = cls._extract_quality_tokens(value)
        hits = [token for token in tokens if token and token in condensed_text]
        return len(hits), hits[:6]

    @classmethod
    def _evaluate_scene_fulfillment(cls, chapter_mission: Optional[dict], condensed_text: str) -> Dict[str, Any]:
        scene_list = (chapter_mission or {}).get("scene_list") if isinstance(chapter_mission, dict) else []
        if not isinstance(scene_list, list) or not scene_list:
            return {
                "scene_count": 0,
                "fulfilled_scene_count": 0,
                "scene_fulfillment_rate": 1.0,
                "structure_passed_scene_count": 0,
                "scene_structure_rate": 1.0,
                "scene_details": [],
            }

        tracked_keys = (
            "goal",
            "conflict",
            "turn",
            "must_happen",
            "outcome",
            "pressure_shift",
            "dialogue_value",
            "end_hook",
            "payoff",
            "bridge",
        )
        structure_groups = {
            "goal": ("goal", "must_happen"),
            "conflict": ("conflict", "dialogue_value"),
            "turn": ("turn", "outcome", "pressure_shift", "payoff"),
            "bridge": ("bridge", "end_hook"),
        }
        details: List[Dict[str, Any]] = []
        fulfilled_count = 0
        structure_passed_count = 0
        for index, scene in enumerate(scene_list[:8], start=1):
            if not isinstance(scene, dict):
                continue
            required_fields = 0
            hit_fields = 0
            hit_by_key: Dict[str, bool] = {}
            field_results = []
            for key in tracked_keys:
                value = scene.get(key)
                if not value:
                    continue
                required_fields += 1
                hit_count, hits = cls._score_text_hits(value, condensed_text)
                field_hit = hit_count > 0
                hit_fields += 1 if field_hit else 0
                hit_by_key[key] = field_hit
                field_results.append({"field": key, "hit": field_hit, "hits": hits})

            required_to_pass = max(1, min(3, math.ceil(required_fields * 0.45)))
            fulfilled = bool(required_fields == 0 or hit_fields >= required_to_pass)
            structure_hits = 0
            structure_results: Dict[str, bool] = {}
            for group_name, keys in structure_groups.items():
                group_hit = any(hit_by_key.get(key) for key in keys)
                structure_results[group_name] = group_hit
                structure_hits += 1 if group_hit else 0
            structure_required = 2 if required_fields <= 3 else 3
            structure_passed = bool(required_fields == 0 or structure_hits >= structure_required)
            fulfilled_count += 1 if fulfilled else 0
            structure_passed_count += 1 if structure_passed else 0
            details.append(
                {
                    "scene_index": index,
                    "required_fields": required_fields,
                    "hit_fields": hit_fields,
                    "required_to_pass": required_to_pass,
                    "fulfilled": fulfilled,
                    "structure_hits": structure_hits,
                    "structure_required": structure_required,
                    "structure_passed": structure_passed,
                    "structure_results": structure_results,
                    "fields": field_results,
                }
            )

        scene_count = len(details)
        return {
            "scene_count": scene_count,
            "fulfilled_scene_count": fulfilled_count,
            "scene_fulfillment_rate": round(fulfilled_count / max(1, scene_count), 4),
            "structure_passed_scene_count": structure_passed_count,
            "scene_structure_rate": round(structure_passed_count / max(1, scene_count), 4),
            "scene_details": details,
        }

    STORY_PROGRESSION_MARKERS = (
        "逼问", "质问", "追问", "反问", "试探", "压迫", "威胁", "拒绝", "反制", "让步",
        "改口", "承认", "暴露", "揭开", "揭露", "证实", "发现", "意识到", "明白", "决定",
        "选择", "交换", "代价", "风险", "危险", "失控", "反转", "翻脸", "背叛", "线索",
        "证据", "期限", "后果", "付出", "受伤", "倒下", "失去", "得到", "夺回", "打开",
        "推开", "抓住", "按住", "拔出", "砸开", "冲进", "闯入", "逃出", "追上", "救下",
        "杀", "死", "活", "必须", "否则", "来不及", "下一步", "转而", "却", "但", "然而",
    )

    @classmethod
    def _story_units(cls, text: str) -> List[str]:
        units = [unit.strip() for unit in re.split(r"[。！？!?\n]+", str(text or "")) if unit.strip()]
        expanded: List[str] = []
        for unit in units:
            if len(unit) <= 180:
                expanded.append(unit)
                continue
            for index in range(0, len(unit), 140):
                chunk = unit[index:index + 140].strip()
                if chunk:
                    expanded.append(chunk)
        return expanded

    @classmethod
    def _unit_has_progression(cls, unit: str) -> bool:
        if not unit:
            return False
        if any(mark in unit for mark in ("“", "”", "「", "」", "『", "』", '"')):
            return True
        return any(marker in unit for marker in cls.STORY_PROGRESSION_MARKERS)

    @classmethod
    def _evaluate_event_density(cls, text: str, *, word_count: int) -> Dict[str, Any]:
        if word_count < 800:
            return {
                "event_density_passed": True,
                "long_chapter_density_passed": True,
                "state_change_interval_passed": True,
                "progression_unit_count": 0,
                "story_unit_count": 0,
                "progression_unit_rate": 1.0,
                "event_density_per_1000": 0.0,
                "state_change_window_pass_rate": 1.0,
                "max_plain_unit_run": 0,
            }

        units = cls._story_units(text)
        progression_flags = [cls._unit_has_progression(unit) for unit in units]
        progression_count = sum(1 for item in progression_flags if item)
        story_unit_count = len(units)
        max_plain_run = 0
        current_plain_run = 0
        for flag in progression_flags:
            if flag:
                current_plain_run = 0
            else:
                current_plain_run += 1
                max_plain_run = max(max_plain_run, current_plain_run)

        condensed = "".join(str(text or "").split())
        window_size = 1200 if word_count >= 7000 else 950
        windows = [condensed[index:index + window_size] for index in range(0, len(condensed), window_size)] or [condensed]
        window_hits = sum(1 for window in windows if cls._unit_has_progression(window))
        window_pass_rate = round(window_hits / max(1, len(windows)), 4)

        density_per_1000 = round(progression_count / max(1.0, word_count / 1000), 4)
        progression_rate = round(progression_count / max(1, story_unit_count), 4)
        density_floor = 1.0 if word_count < 2500 else 1.25 if word_count < 7000 else 1.45
        unit_rate_floor = 0.16 if word_count < 2500 else 0.2 if word_count < 7000 else 0.22
        window_floor = 0.6 if word_count < 2500 else 0.68 if word_count < 7000 else 0.74
        plain_run_limit = 5 if word_count < 7000 else 4

        state_interval_passed = bool(window_pass_rate >= window_floor)
        dense_progression_override = bool(
            state_interval_passed
            and density_per_1000 >= density_floor * 2
            and progression_rate >= unit_rate_floor * 1.6
        )
        event_density_passed = bool(
            density_per_1000 >= density_floor
            and progression_rate >= unit_rate_floor
            and (max_plain_run <= plain_run_limit or dense_progression_override)
        )
        long_chapter_passed = True
        if word_count >= 7000:
            long_chapter_passed = bool(event_density_passed and state_interval_passed and progression_count >= 12)

        return {
            "event_density_passed": event_density_passed,
            "long_chapter_density_passed": long_chapter_passed,
            "state_change_interval_passed": state_interval_passed,
            "progression_unit_count": progression_count,
            "story_unit_count": story_unit_count,
            "progression_unit_rate": progression_rate,
            "event_density_per_1000": density_per_1000,
            "state_change_window_count": len(windows),
            "state_change_window_hit_count": window_hits,
            "state_change_window_pass_rate": window_pass_rate,
            "max_plain_unit_run": max_plain_run,
        }

    @staticmethod
    def _count_dialogue_state_change_markers(text: str) -> int:
        markers = (
            "逼问", "反问", "拒绝", "改口", "让步", "沉默", "威胁", "试探", "压低",
            "盯", "笑了", "停住", "转而", "暴露", "发现", "意识到", "决定", "条件",
            "交换", "代价", "风险", "失控",
        )
        normalized_markers = (
            "逼问", "反问", "质问", "追问", "试探", "压迫", "压住", "拒绝", "沉默", "打断",
            "反制", "威胁", "翻脸", "让步", "改口", "承认", "暴露", "泄露", "发现", "意识到",
            "决定", "选择", "条件", "交换", "代价", "风险", "危险", "失控", "反转", "退路",
        )
        return sum(str(text or "").count(marker) for marker in markers + normalized_markers)

    @classmethod
    def _evaluate_dialogue_changes_state(cls, text: str, *, expected_dialogue: bool, dialogue_markers: int) -> Dict[str, Any]:
        marker_count = cls._count_dialogue_state_change_markers(text)
        passed = True if not expected_dialogue else dialogue_markers >= 2 and marker_count >= 2
        return {
            "expected_dialogue": expected_dialogue,
            "dialogue_marker_count": dialogue_markers,
            "state_change_marker_count": marker_count,
            "dialogue_changes_state": passed,
        }

    @classmethod
    def _evaluate_ending_pressure(cls, condensed_text: str, chapter_mission: Optional[dict]) -> Dict[str, Any]:
        ending_excerpt = condensed_text[-260:]
        continuity = (chapter_mission or {}).get("continuity_anchor") if isinstance(chapter_mission, dict) else {}
        deliver_to_next = continuity.get("deliver_to_next") if isinstance(continuity, dict) else []
        _, deliver_hits = cls._score_text_hits(deliver_to_next, ending_excerpt)
        mission_hook_sources: List[Any] = []
        if isinstance(chapter_mission, dict):
            for key in (
                "suspense_hook",
                "chapter_role",
                "chapter_purpose",
                "payoff_window",
                "conflict_escalation",
                "foreshadowing_tasks",
            ):
                if chapter_mission.get(key):
                    mission_hook_sources.append(chapter_mission.get(key))
            scene_list = chapter_mission.get("scene_list")
            if isinstance(scene_list, list) and scene_list:
                last_scene = scene_list[-1] if isinstance(scene_list[-1], dict) else {}
                for key in ("end_hook", "bridge", "outcome", "pressure_shift", "payoff", "turn"):
                    if last_scene.get(key):
                        mission_hook_sources.append(last_scene.get(key))
        _, mission_hook_hits = cls._score_text_hits(mission_hook_sources, ending_excerpt)
        hook_markers = (
            "却", "突然", "忽然", "门外", "脚步", "消息", "期限", "代价", "危险",
            "线索", "证据", "下一刻", "来不及", "问题", "？", "?", "！", "!",
        )
        closure_markers = ("终于结束", "告一段落", "松了口气", "一切都", "暂时平静", "圆满", "尘埃落定")
        zh_hook_markers = (
            "\u4e0b\u4e00", "\u4e0b\u4e00\u8f6e", "\u4e0b\u4e00\u7ae0",
            "\u6da8\u6f6e", "\u6f6e\u6c34", "\u5371\u9669", "\u5371\u673a",
            "\u538b\u529b", "\u4ee3\u4ef7", "\u540e\u679c", "\u8bc1\u636e",
            "\u7ebf\u7d22", "\u5f02\u5e38", "\u4e0d\u81ea\u7136",
            "\u6765\u4e0d\u53ca", "\u5fc5\u987b", "\u5426\u5219",
            "\u9000\u8def", "\u5c01\u9501", "\u7f09\u5370\u4ee4", "\u901a\u7f09",
            "\u5012\u8ba1\u65f6", "\u8ffd\u7d22", "\u8ffd\u6740", "\u903c\u8fd1",
            "\u5835\u6b7b", "\u9501\u6b7b", "\u53ea\u80fd", "\u4e0d\u5f97\u4e0d",
            "\u4f1a\u5148\u6b7b", "\u6b7b\u5728", "\u65e7\u6728\u7247",
            "\u6b7b\u4eba", "\u4f1a\u6b7b\u4eba", "\u771f\u4f1a\u6b7b",
            "\u65e7\u5357\u6e20", "\u836f\u6e23", "\u836f\u5473", "\u836f\u8017",
            "\u89c1\u4e86\u5730", "\u4eba\u547d", "\u75c5\u4eba",
        )
        hook_hits = [marker for marker in (*hook_markers, *zh_hook_markers) if marker in ending_excerpt]
        closure_hits = [marker for marker in closure_markers if marker in ending_excerpt]
        mission_hook_pass = bool(mission_hook_hits and hook_hits)
        passed = bool((deliver_hits or len(hook_hits) >= 2 or mission_hook_pass) and not closure_hits)
        return {
            "ending_pressure_passed": passed,
            "ending_pressure_hits": (deliver_hits + mission_hook_hits + hook_hits)[:10],
            "mission_hook_hits": mission_hook_hits[:6],
            "flat_closure_markers": closure_hits[:4],
        }

    @staticmethod
    def _estimate_static_description_runs(paragraphs: List[str]) -> Dict[str, int]:
        static_count = 0
        max_run = 0
        current_run = 0
        action_markers = ("说", "问", "答", "走", "退", "伸手", "抬头", "看", "盯", "推", "抓", "按", "转身", "决定", "发现", "却", "但")
        for paragraph in paragraphs:
            plain = "".join(str(paragraph or "").split())
            is_static = len(plain) >= 100 and not any(marker in plain for marker in action_markers)
            if is_static:
                static_count += 1
                current_run += 1
                max_run = max(max_run, current_run)
            else:
                current_run = 0
        return {"static_paragraph_count": static_count, "max_static_run": max_run}

    @classmethod
    def _score_fallback_candidate(
        cls,
        *,
        content: str,
        violations: List[Dict[str, Any]],
        chapter_mission: Optional[dict],
    ) -> Dict[str, Any]:
        text = str(content or "")
        condensed = "".join(text.split())
        word_count = len(condensed)
        target_floor = max(0, int(target_word_count or 0))
        minimum_floor = max(0, int(min_word_count or 0))
        if target_floor and minimum_floor > target_floor:
            minimum_floor = target_floor
        preferred_floor = max(minimum_floor, int(target_floor * 0.92)) if target_floor else minimum_floor
        word_count_below_min = bool(minimum_floor and word_count < minimum_floor)
        word_count_far_below_target = bool(preferred_floor and word_count < preferred_floor)
        upper_target = int(target_floor * 1.25) if target_floor else 0
        word_count_far_above_target = bool(upper_target and word_count > upper_target)
        paragraphs = [segment for segment in text.splitlines() if segment.strip()]
        paragraph_count = len(paragraphs)
        dialogue_markers = sum(text.count(marker) for marker in ("“", "”", "「", "」", "『", "』", '"'))
        mission_keywords = cls._collect_fallback_mission_keywords(chapter_mission)
        mission_hits = [keyword for keyword in mission_keywords if keyword and keyword in condensed]
        expected_dialogue = cls._chapter_mission_expects_dialogue(chapter_mission)
        ending_excerpt = condensed[-220:]
        hook_markers = ("？", "！", "?", "!", "忽然", "却", "竟", "脚步", "敲门", "消息", "声音", "目光", "门外", "下一瞬")
        ending_hook = any(marker in ending_excerpt for marker in hook_markers)
        static_description_risk = dialogue_markers == 0 and paragraph_count <= 4 and word_count >= 1800

        score = 0
        score += len(mission_hits) * 180
        score += min(paragraph_count, 12) * 18
        score += min(dialogue_markers, 10) * 12
        score += 80 if ending_hook else 0
        score += min(word_count, 2400) // 50
        score -= len(violations) * 500
        score -= 160 if static_description_risk else 0

        return {
            "score": score,
            "word_count": word_count,
            "paragraph_count": paragraph_count,
            "dialogue_marker_count": dialogue_markers,
            "guardrail_violation_count": len(violations),
            "mission_hit_count": len(mission_hits),
            "mission_hits": mission_hits[:8],
            "expected_dialogue": expected_dialogue,
            "ending_hook_detected": ending_hook,
            "static_description_risk": static_description_risk,
        }

    @staticmethod
    def _detect_chapter_artifact_markers(text):
        """Detect chapter artifact markers in content."""
        if not text:
            return {"chapter_artifact_markers": False, "chapter_artifact_marker_count": 0, "chapter_artifact_marker_examples": []}
        
        import re
        patterns = [
            re.compile(r'^\s*#{1,6}\s*(?:场景|scene|扩写|修订|完整章节正文|本章正文|章节大纲|章节导演)\s*\d*\s*[|\uff5c:\uff1a\u3011]?\s*\S*', re.IGNORECASE | re.MULTILINE),
            re.compile(r'^\s*(?:【|\*\*【)?\s*场景\s*\d+\s*(?:[|\uff5c:\uff1a\u3011]|$)', re.MULTILINE),
            re.compile(r'^\s*(?:【|\*\*【)?\s*扩写部分\s*\d*\s*(?:[|\uff5c:\uff1a\u3011]|$)', re.MULTILINE),
            re.compile(r'^\s*(?:修改说明|修订说明|以下是|本章正文|完整章节正文)\s*[:\uff1a]', re.MULTILINE),
            re.compile(r'(?:写作指令|写作要求|质量方向|基础质量底线|首稿执行要求)\s*[:\uff1a]'),
            re.compile(r'约\s*\d+\s*字'),
        ]
        
        examples = []
        for p in patterns:
            for m in p.finditer(text):
                example = m.group(0).strip()
                if example and len(example) <= 100:
                    examples.append(example)
                    if len(examples) >= 5:
                        break
            if len(examples) >= 5:
                break
        
        # Also check for structural bold headings
        for m in re.finditer(r'\*\*(.+?)\*\*', text):
            s = m.group(1)
            if any(kw in s for kw in ['场景', '章节', '扩写', '修订']):
                examples.append(m.group(0).strip())
                if len(examples) >= 5:
                    break
        
        return {"chapter_artifact_markers": len(examples) > 0, "chapter_artifact_marker_count": len(examples), "chapter_artifact_marker_examples": examples[:5]}

    @classmethod
    def _score_story_quality_candidate(
        cls,
        *,
        content: str,
        violations: List[Dict[str, Any]],
        chapter_mission: Optional[dict],
        target_word_count: Optional[int] = None,
        min_word_count: Optional[int] = None,
    ) -> Dict[str, Any]:
        text = str(content or "")
        condensed = "".join(text.split())
        word_count = len(condensed)
        paragraphs = [segment for segment in text.splitlines() if segment.strip()]
        paragraph_count = len(paragraphs)
        dialogue_markers = sum(text.count(marker) for marker in ("“", "”", "「", "」", "『", "』", '"'))
        mission_keywords = cls._collect_fallback_mission_keywords(chapter_mission)
        mission_hits = [keyword for keyword in mission_keywords if keyword and keyword in condensed]
        expected_dialogue = cls._chapter_mission_expects_dialogue(chapter_mission)
        scene_fulfillment = cls._evaluate_scene_fulfillment(chapter_mission, condensed)
        dialogue_state = cls._evaluate_dialogue_changes_state(
            text,
            expected_dialogue=expected_dialogue,
            dialogue_markers=dialogue_markers,
        )
        ending_pressure = cls._evaluate_ending_pressure(condensed, chapter_mission)
        ending_hook = bool(ending_pressure.get("ending_pressure_passed"))
        static_runs = cls._estimate_static_description_runs(paragraphs)
        event_density = cls._evaluate_event_density(text, word_count=word_count)
        artifact_markers = cls._detect_chapter_artifact_markers(text)
        static_description_risk = bool(
            (dialogue_markers == 0 and paragraph_count <= 4 and word_count >= 1800)
            or (word_count >= 1500 and static_runs.get("max_static_run", 0) >= 3)
            or (word_count >= 2500 and event_density.get("event_density_passed") is False and static_runs.get("max_static_run", 0) >= 2)
        )
        scene_rate = float(scene_fulfillment.get("scene_fulfillment_rate", 1.0) or 0)
        scene_structure_rate = float(scene_fulfillment.get("scene_structure_rate", 1.0) or 0)
        scene_count = int(scene_fulfillment.get("scene_count") or 0)

        score = 0
        score += len(mission_hits) * 180
        score += min(paragraph_count, 12) * 18
        score += min(dialogue_markers, 10) * 12
        score += int(scene_rate * 280) if scene_count else 80
        score += int(scene_structure_rate * 140) if scene_count else 40
        score += 140 if dialogue_state.get("dialogue_changes_state") else -140
        score += 140 if ending_hook else -120
        score += min(int(event_density.get("progression_unit_count") or 0), 18) * 16
        score += 80 if event_density.get("event_density_passed") else -180
        score += 60 if event_density.get("state_change_interval_passed") else -130
        score += 90 if event_density.get("long_chapter_density_passed") else -180
        score += min(word_count, 2400) // 50
        score -= len(violations) * 500
        score -= 260 if static_description_risk else 0

        quality_metric_snapshot = {
            "word_count": word_count,
            "paragraph_count": paragraph_count,
            "mission_hit_count": len(mission_hits),
            "scene_fulfillment_rate": scene_rate,
            "fulfilled_scene_count": scene_fulfillment.get("fulfilled_scene_count", 0),
            "scene_count": scene_count,
            "scene_structure_rate": scene_structure_rate,
            "structure_passed_scene_count": scene_fulfillment.get("structure_passed_scene_count", 0),
            "dialogue_changes_state": bool(dialogue_state.get("dialogue_changes_state")),
            "dialogue_state_change_markers": dialogue_state.get("state_change_marker_count", 0),
            "ending_pressure_passed": ending_hook,
            "static_description_risk": static_description_risk,
            "static_paragraph_count": static_runs.get("static_paragraph_count", 0),
            "max_static_run": static_runs.get("max_static_run", 0),
            "event_density_passed": bool(event_density.get("event_density_passed")),
            "chapter_artifact_markers": artifact_markers.get("chapter_artifact_markers"),
            "chapter_artifact_marker_examples": artifact_markers.get("chapter_artifact_marker_examples", []),
            "long_chapter_density_passed": bool(event_density.get("long_chapter_density_passed")),
            "state_change_interval_passed": bool(event_density.get("state_change_interval_passed")),
            "progression_unit_count": event_density.get("progression_unit_count", 0),
            "story_unit_count": event_density.get("story_unit_count", 0),
            "progression_unit_rate": event_density.get("progression_unit_rate", 0),
            "event_density_per_1000": event_density.get("event_density_per_1000", 0),
            "state_change_window_pass_rate": event_density.get("state_change_window_pass_rate", 0),
            "max_plain_unit_run": event_density.get("max_plain_unit_run", 0),
        }
        quality_issue_summary = cls._build_quality_issue_summary(story_guard=quality_metric_snapshot)
        quality_metric_snapshot["quality_issue_summary"] = quality_issue_summary
        quality_metric_snapshot["quality_issue_codes"] = quality_issue_summary.get("codes", [])
        quality_metric_snapshot["quality_issue_labels"] = quality_issue_summary.get("labels", [])

        return {
            "score": score,
            "word_count": word_count,
            "paragraph_count": paragraph_count,
            "dialogue_marker_count": dialogue_markers,
            "guardrail_violation_count": len(violations),
            "mission_hit_count": len(mission_hits),
            "mission_hits": mission_hits[:8],
            "expected_dialogue": expected_dialogue,
            "ending_hook_detected": ending_hook,
            "static_description_risk": static_description_risk,
            "scene_fulfillment_rate": scene_rate,
            "fulfilled_scene_count": scene_fulfillment.get("fulfilled_scene_count", 0),
            "scene_count": scene_count,
            "scene_structure_rate": scene_structure_rate,
            "structure_passed_scene_count": scene_fulfillment.get("structure_passed_scene_count", 0),
            "scene_fulfillment": scene_fulfillment,
            "dialogue_changes_state": dialogue_state.get("dialogue_changes_state"),
            "dialogue_state_change_markers": dialogue_state.get("state_change_marker_count", 0),
            "ending_pressure_passed": ending_pressure.get("ending_pressure_passed"),
            "ending_pressure": ending_pressure,
            "static_description_runs": static_runs,
            "event_density": event_density,
            "event_density_passed": event_density.get("event_density_passed"),
            "long_chapter_density_passed": event_density.get("long_chapter_density_passed"),
            "state_change_interval_passed": event_density.get("state_change_interval_passed"),
            "progression_unit_count": event_density.get("progression_unit_count", 0),
            "event_density_per_1000": event_density.get("event_density_per_1000", 0),
            "state_change_window_pass_rate": event_density.get("state_change_window_pass_rate", 0),
            "quality_issue_summary": quality_issue_summary,
            "quality_issue_codes": quality_issue_summary.get("codes", []),
            "quality_issue_labels": quality_issue_summary.get("labels", []),
            "quality_metric_snapshot": quality_metric_snapshot,
            **artifact_markers,
        }

    @classmethod
    def _fallback_select_best_version(
        cls,
        versions: List[Dict[str, Any]],
        chapter_mission: Optional[dict] = None,
    ) -> Tuple[int, Dict[str, Any]]:
        scored: List[Tuple[int, int, Dict[str, Any]]] = []
        for idx, variant in enumerate(versions):
            metadata = dict(variant.get("metadata") or {})
            guardrail = metadata.get("guardrail") or {}
            violations = guardrail.get("violations") or []
            content = variant.get("content") or ""
            candidate_summary = cls._score_story_quality_candidate(
                content=content,
                violations=violations,
                chapter_mission=chapter_mission,
            )
            candidate_summary.update(
                {
                    "index": idx,
                    "guardrail_passed": bool(guardrail.get("passed", not violations)),
                }
            )
            scored.append((candidate_summary["score"], idx, candidate_summary))

        scored.sort(key=lambda item: (item[0], item[2]["guardrail_passed"], item[2]["mission_hit_count"]), reverse=True)
        best = scored[0] if scored else (0, 0, {"index": 0, "word_count": 0, "guardrail_passed": False, "guardrail_violation_count": 0})
        return best[1], {
            "strategy": "heuristic_story_progression_guardrails",
            "candidates": [item[2] for item in scored],
        }

    @staticmethod
    def _find_candidate_summary(
        fallback_summary: Optional[Dict[str, Any]],
        index: int,
    ) -> Dict[str, Any]:
        for item in (fallback_summary or {}).get("candidates") or []:
            if isinstance(item, dict) and int(item.get("index", -1)) == int(index):
                return item
        return {}

    @classmethod
    def _should_override_ai_review_choice(
        cls,
        *,
        ai_index: int,
        fallback_index: int,
        fallback_summary: Optional[Dict[str, Any]],
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        if ai_index == fallback_index:
            return False, None

        ai_candidate = cls._find_candidate_summary(fallback_summary, ai_index)
        fallback_candidate = cls._find_candidate_summary(fallback_summary, fallback_index)
        if not ai_candidate or not fallback_candidate:
            return False, None

        ai_word_count = int(ai_candidate.get("word_count") or 0)
        ai_dialogue_markers = int(ai_candidate.get("dialogue_marker_count") or 0)
        ai_mission_hits = int(ai_candidate.get("mission_hit_count") or 0)
        fallback_dialogue_markers = int(fallback_candidate.get("dialogue_marker_count") or 0)
        fallback_mission_hits = int(fallback_candidate.get("mission_hit_count") or 0)
        ai_score = int(ai_candidate.get("score") or 0)
        fallback_score = int(fallback_candidate.get("score") or 0)
        ai_scene_rate = float(ai_candidate.get("scene_fulfillment_rate") or 1.0)
        fallback_scene_rate = float(fallback_candidate.get("scene_fulfillment_rate") or 1.0)

        ai_has_basic_story_risk = bool(
            ai_candidate.get("static_description_risk")
            or (ai_candidate.get("expected_dialogue") and ai_word_count >= 1500 and ai_dialogue_markers < 4)
            or (ai_word_count >= 1500 and ai_mission_hits < 2)
            or (int(ai_candidate.get("scene_count") or 0) > 0 and ai_scene_rate < 0.5)
            or (ai_candidate.get("expected_dialogue") and not ai_candidate.get("dialogue_changes_state", True))
            or (ai_word_count >= 1200 and not ai_candidate.get("ending_pressure_passed", ai_candidate.get("ending_hook_detected")))
            or (not ai_candidate.get("guardrail_passed", True) and fallback_candidate.get("guardrail_passed", False))
        )
        fallback_materially_better = bool(
            fallback_score >= ai_score + 180
            or fallback_mission_hits >= ai_mission_hits + 2
            or fallback_dialogue_markers >= ai_dialogue_markers + 4
            or fallback_scene_rate >= ai_scene_rate + 0.34
            or (fallback_candidate.get("dialogue_changes_state") and not ai_candidate.get("dialogue_changes_state"))
            or (fallback_candidate.get("ending_pressure_passed") and not ai_candidate.get("ending_pressure_passed"))
            or (fallback_candidate.get("ending_hook_detected") and not ai_candidate.get("ending_hook_detected"))
            or (fallback_candidate.get("guardrail_passed", False) and not ai_candidate.get("guardrail_passed", True))
        )
        if not (ai_has_basic_story_risk and fallback_materially_better):
            return False, None

        return True, {
            "reason": "ai_choice_has_story_progression_risk",
            "ai_best_index": ai_index,
            "fallback_best_index": fallback_index,
            "ai_candidate": ai_candidate,
            "fallback_candidate": fallback_candidate,
        }

    @staticmethod
    def _build_ai_review_mission(
        *,
        chapter_mission: Optional[dict],
        longform_context: Optional[LongformContextPackage],
    ) -> Optional[dict]:
        if not isinstance(chapter_mission, dict) and not longform_context:
            return None

        review_mission = deepcopy(chapter_mission) if isinstance(chapter_mission, dict) else {}
        review_mission.setdefault("review_quality_rules", [])
        review_mission["review_quality_rules"] = list(review_mission.get("review_quality_rules") or []) + [
            "候选稿必须承接前文角色状态、时间线、知识边界和章末压力。",
            "必须检查本章伏笔/线索任务是否被看见、强化或回收，不能只按文风选稿。",
            "如果候选稿需要修补，优先输出局部锚点补丁建议，不把优化阶段导向默认整章重写。",
        ]

        if longform_context:
            optimizer_payload = longform_context.to_optimizer_payload(max_prompt_chars=3200)
            review_mission["longform_review_context"] = {
                "chapter_number": optimizer_payload.get("chapter_number"),
                "prompt_digest": optimizer_payload.get("prompt_digest"),
                "cast_plan": optimizer_payload.get("cast_plan"),
                "foreshadowing_task": optimizer_payload.get("foreshadowing_task"),
                "memory_digest": optimizer_payload.get("memory_digest"),
                "timeline_digest": optimizer_payload.get("timeline_digest"),
            }
        return review_mission

    async def _run_ai_review(
        self,
        *,
        versions: List[Dict[str, Any]],
        chapter_mission: Optional[dict],
        user_id: int,
    ) -> Tuple[int, Optional[Dict[str, Any]]]:
        if len(versions) <= 1:
            candidate = versions[0] if versions else {}
            candidate.setdefault("metadata", {})["ai_review"] = {
                "is_best": True,
                "scores": {},
                "evaluation": None,
                "flaws": [],
                "suggestions": "",
                "status": "single_candidate_rule_review",
                "skip_reason": "single_candidate_no_selection_needed",
            }
            return 0, {
                "best_version_index": 0,
                "scores": {},
                "evaluation": "单候选直接采用，无需 AI 评审选择。",
                "flaws": [],
                "suggestions": "",
                "status": "single_candidate_rule_review",
                "skip_reason": "single_candidate_no_selection_needed",
                "fallback_summary": None,
            }

        contents = [v.get("content", "") for v in versions]
        fallback_index, fallback_summary = self._fallback_select_best_version(
            versions,
            chapter_mission=chapter_mission,
        )
        try:
            ai_review_service = AIReviewService(self.llm_service, self.prompt_service)
            ai_review_result = await ai_review_service.review_versions(
                versions=contents,
                chapter_mission=chapter_mission,
                user_id=user_id,
            )
        except Exception as exc:
            logger.warning("AI 评审失败，跳过: %s", exc)
            return fallback_index, None

        if not ai_review_result or ai_review_result.best_version_index is None:
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

        selected_index = ai_review_result.best_version_index
        override_applied, override_detail = self._should_override_ai_review_choice(
            ai_index=selected_index,
            fallback_index=fallback_index,
            fallback_summary=fallback_summary,
        )
        if override_applied:
            logger.info(
                "AI 评审选优被故事推进护栏改写: ai_best=%s fallback_best=%s reason=%s",
                selected_index,
                fallback_index,
                (override_detail or {}).get("reason"),
            )
            selected_index = fallback_index

        for idx, variant in enumerate(versions):
            variant.setdefault("metadata", {})["ai_review"] = {
                "is_best": idx == selected_index,
                "ai_original_best": idx == ai_review_result.best_version_index,
                "scores": ai_review_result.scores,
                "evaluation": ai_review_result.overall_evaluation if idx == ai_review_result.best_version_index else None,
                "flaws": ai_review_result.critical_flaws if idx == ai_review_result.best_version_index else None,
                "suggestions": ai_review_result.refinement_suggestions if idx == ai_review_result.best_version_index else None,
                "status": "overridden_by_story_guard" if override_applied else ai_review_result.status,
                "selection_override": override_detail if idx == selected_index and override_applied else None,
            }

        return selected_index, {
            "best_version_index": selected_index,
            "ai_original_best_index": ai_review_result.best_version_index,
            "scores": ai_review_result.scores,
            "evaluation": ai_review_result.overall_evaluation,
            "flaws": ai_review_result.critical_flaws,
            "suggestions": ai_review_result.refinement_suggestions,
            "status": "ai_review_overridden_by_story_guard" if override_applied else ai_review_result.status,
            "skip_reason": None,
            "fallback_summary": fallback_summary,
            "selection_override": override_detail,
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

        async def _report_strategy_optimization(strategy_key: str, metadata: Dict[str, Any]) -> None:
            strategy_to_stage = {
                "structure_guardrail": ("optimize_structural", "正在执行结构优化：细化规则、承接与因果"),
                "character_dynamics": ("optimize_character", "正在执行人物优化：细化动机、关系与压迫"),
                "delivery_polish": ("optimize_delivery", "正在执行表达优化：压缩拖沓并强化动作/钩子"),
            }
            runtime_stage, base_message = strategy_to_stage.get(
                strategy_key,
                (f"optimize_{strategy_key}", "正在执行策略级优化"),
            )
            phase = str(metadata.get("phase") or "strategy_start")
            phase_message_map = {
                "strategy_start": f"{base_message}（进入策略子阶段）",
                "localized_primary": f"{base_message}（优先局部连续窗口修补）",
                "stagewide_primary": f"{base_message}（例外路径：连续性整合候选）",
                "aggregate_retry": f"{base_message}（根据聚合反馈重试）",
            }
            await self._update_generation_runtime(
                chapter,
                generation_run_id=generation_run_id,
                stage=runtime_stage,
                message=phase_message_map.get(phase, base_message),
                progress_percent=86 if phase == "aggregate_retry" else 84,
                extra={
                    "optimization_strategy": strategy_key,
                    "optimization_strategy_phase": phase,
                    "optimization_issue_count": metadata.get("issue_count"),
                    "optimization_aggregate_issue_count": metadata.get("aggregate_issue_count"),
                    "optimization_retry_reason": metadata.get("retry_reason"),
                },
            )

        try:
            critique = await asyncio.wait_for(
                service.critique_and_revise_loop(
                    chapter_content=chapter_content,
                    max_iterations=1,
                    target_score=60.0,
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
                    strategy_optimize_callback=_report_strategy_optimization,
                ),
                timeout=540.0,
            )
        except asyncio.TimeoutError:
            logger.error('Self-critique timed out after 540s, using original content')
            critique = {
                'final_content': chapter_content,
                'final_critique': {'weighted_score': 0, 'critical_count': 0, 'major_count': 0, 'minor_count': 0, 'needs_revision': False},
                'iterations': [],
                'status': 'timeout_skipped',
                'improvement': 0,
                'optimization_logs': [],
            }
        final_content = critique.get("final_content", chapter_content)
        final_critique = critique.get("final_critique") or {}
        candidate_content = final_content
        candidate_critique = deepcopy(final_critique)
        initial_snapshot = ((critique.get("iterations") or [{}])[0].get("critique") or {})
        accepted_revision = True
        acceptance_reason = "no_revision_applied"
        before_stats: Dict[str, Any] = self._summarize_self_critique_snapshot(initial_snapshot)
        after_stats: Dict[str, Any] = self._summarize_self_critique_snapshot(final_critique)
        if final_content != chapter_content:
            accepted_revision, acceptance_reason, before_stats, after_stats = self._should_accept_self_critique_revision(
                initial_snapshot,
                final_critique,
            )
            if not accepted_revision:
                logger.warning(
                    "Self-critique revision degraded chapter; revert to original: reason=%s before=%s after=%s",
                    acceptance_reason,
                    before_stats,
                    after_stats,
                )
                final_content = chapter_content
                final_critique = {
                    "weighted_score": initial_snapshot.get("weighted_score", 0),
                    "critical_count": initial_snapshot.get("critical_count", 0),
                    "major_count": initial_snapshot.get("major_count", 0),
                    "minor_count": initial_snapshot.get("minor_count", 0),
                    "needs_revision": initial_snapshot.get("needs_revision", False),
                    "priority_fixes": initial_snapshot.get("priority_fixes", []),
                    "stage_summaries": initial_snapshot.get("stage_summaries", []),
                    "raw_issue_count": initial_snapshot.get("raw_issue_count"),
                    "deduped_issue_count": initial_snapshot.get("deduped_issue_count"),
                    "merged_issue_count": initial_snapshot.get("merged_issue_count"),
                }
        summary_status = critique.get("status", "unknown")
        summary_improvement = critique.get("improvement", 0)
        if final_content == chapter_content and critique.get("final_content", chapter_content) != chapter_content and not accepted_revision:
            summary_status = "reverted_to_original"
            summary_improvement = 0
        manual_patch_suggestions: List[Dict[str, Any]] = []
        stagewide_deferred_count = 0
        for optimization_log in critique.get("optimization_logs", []) or []:
            for strategy_log in optimization_log.get("strategy_logs", []) or []:
                for attempt in strategy_log.get("attempts", []) or []:
                    if attempt.get("mode") != "stagewide" or not attempt.get("manual_confirmation_required"):
                        continue
                    stagewide_deferred_count += 1
                    for suggestion in attempt.get("patch_suggestions") or []:
                        if isinstance(suggestion, dict):
                            manual_patch_suggestions.append({
                                **suggestion,
                                "stage": optimization_log.get("stage"),
                                "strategy": strategy_log.get("strategy"),
                            })
        return final_content, {
            "iterations": len(critique.get("iterations", [])),
            "final_score": final_critique.get("weighted_score", critique.get("final_score", 0)),
            "improvement": summary_improvement,
            "status": summary_status,
            "critical_count": final_critique.get("critical_count", 0),
            "major_count": final_critique.get("major_count", 0),
            "minor_count": final_critique.get("minor_count", 0),
            "priority_fixes": final_critique.get("priority_fixes", []),
            "final_critique": final_critique,
            "optimization_logs": critique.get("optimization_logs", []),
            "manual_stagewide_confirmation_required": stagewide_deferred_count > 0,
            "stagewide_deferred_count": stagewide_deferred_count,
            "manual_patch_suggestions": manual_patch_suggestions[:12],
            "accepted_revision": accepted_revision,
            "acceptance_reason": acceptance_reason,
            "before_revision_stats": before_stats,
            "after_revision_stats": after_stats,
            "rejected_candidate_content_fingerprint": (
                self._content_fingerprint(candidate_content)
                if not accepted_revision and candidate_content != chapter_content
                else None
            ),
            "rejected_candidate_critique": (
                candidate_critique
                if not accepted_revision and candidate_content != chapter_content
                else None
            ),
            "content_fingerprint": self._content_fingerprint(final_content),
            "raw_issue_count": final_critique.get("raw_issue_count"),
            "deduped_issue_count": final_critique.get("deduped_issue_count"),
            "merged_issue_count": final_critique.get("merged_issue_count"),
        }

    async def _run_post_consistency_self_critique_summary(
        self,
        *,
        chapter_content: str,
        context: Optional[Dict[str, Any]],
        user_id: int,
        baseline_summary: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        content_fingerprint = self._content_fingerprint(chapter_content)
        baseline = baseline_summary or {}
        baseline_fingerprint = str(baseline.get("content_fingerprint") or "").strip()
        if baseline and baseline_fingerprint and baseline_fingerprint == content_fingerprint:
            reused_summary = deepcopy(baseline)
            reused_summary.update({
                "improvement": 0,
                "status": "post_consistency_reused_same_content",
                "content_fingerprint": content_fingerprint,
                "reused_from": "self_critique",
            })
            return reused_summary

        service = SelfCritiqueService(self.session, self.llm_service, self.prompt_service)
        critique = await service.full_critique(
            chapter_content,
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
        )
        return {
            "final_score": critique.get("weighted_score", 0),
            "improvement": 0,
            "status": "post_consistency_verified",
            "critical_count": critique.get("critical_count", 0),
            "major_count": critique.get("major_count", 0),
            "minor_count": critique.get("minor_count", 0),
            "priority_fixes": critique.get("priority_fixes", []),
            "final_critique": critique,
            "stage_summaries": critique.get("stage_summaries", []),
            "content_fingerprint": content_fingerprint,
            "raw_issue_count": critique.get("raw_issue_count"),
            "deduped_issue_count": critique.get("deduped_issue_count"),
            "merged_issue_count": critique.get("merged_issue_count"),
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
        with LLMService.daily_limit_scope(f"consistency_pipeline:{project_id}:{user_id}:{len(chapter_text)}"):
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
                report["repair_attempts"] = []
                fixed = await service.auto_fix(project_id, chapter_text, result.violations, user_id)
                if fixed and fixed != chapter_text:
                    report["auto_fix_applied"] = True
                    recheck = await service.check_consistency(project_id, fixed, user_id, include_foreshadowing=True)
                    post_fix_report = {
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
                    accepted, acceptance_reason, before_counts, after_counts = self._should_accept_consistency_improvement(
                        report,
                        post_fix_report,
                    )
                    report["post_fix_check"] = post_fix_report
                    report["post_fix_comparison"] = {
                        "accepted": accepted,
                        "acceptance_reason": acceptance_reason,
                        "before": before_counts,
                        "after": after_counts,
                    }
                    report["repair_attempts"].append({
                        "attempt": 1,
                        "accepted": accepted,
                        "acceptance_reason": acceptance_reason,
                        "before": before_counts,
                        "after": after_counts,
                        "content_changed": fixed != chapter_text,
                    })
                    report["auto_fix_accepted"] = accepted
                    if accepted:
                        report["auto_fix_acceptance_reason"] = acceptance_reason
                        return fixed, report

                    retry_violations = [
                        item for item in recheck.violations
                        if item.severity in (ViolationSeverity.CRITICAL, ViolationSeverity.MAJOR)
                    ]
                    if retry_violations:
                        retry_fixed = await service.auto_fix(project_id, fixed, retry_violations, user_id)
                        if retry_fixed and retry_fixed not in {chapter_text, fixed}:
                            retry_recheck = await service.check_consistency(project_id, retry_fixed, user_id, include_foreshadowing=True)
                            retry_post_fix_report = {
                                "status": retry_recheck.status,
                                "is_consistent": retry_recheck.is_consistent,
                                "summary": retry_recheck.summary,
                                "violations": [
                                    {
                                        "severity": v.severity.value if hasattr(v.severity, "value") else v.severity,
                                        "category": v.category,
                                        "description": v.description,
                                        "location": v.location,
                                        "suggested_fix": v.suggested_fix,
                                        "confidence": v.confidence,
                                    }
                                    for v in retry_recheck.violations
                                ],
                            }
                            retry_accepted, retry_reason, retry_before_counts, retry_after_counts = self._should_accept_consistency_improvement(
                                report,
                                retry_post_fix_report,
                            )
                            report["post_fix_check"] = retry_post_fix_report
                            report["post_fix_comparison"] = {
                                "accepted": retry_accepted,
                                "acceptance_reason": retry_reason,
                                "before": retry_before_counts,
                                "after": retry_after_counts,
                            }
                            report["repair_attempts"].append({
                                "attempt": 2,
                                "accepted": retry_accepted,
                                "acceptance_reason": retry_reason,
                                "before": retry_before_counts,
                                "after": retry_after_counts,
                                "content_changed": retry_fixed != fixed,
                                "retry_source": "post_fix_feedback",
                            })
                            report["auto_fix_accepted"] = retry_accepted
                            if retry_accepted:
                                report["auto_fix_acceptance_reason"] = retry_reason
                                return retry_fixed, report
                    return chapter_text, report
                report["repair_attempts"].append({
                    "attempt": 1,
                    "mode": "local_patch",
                    "accepted": False,
                    "acceptance_reason": "local_repair_failed_full_chapter_deferred",
                    "content_changed": False,
                    "full_chapter_fallback_deferred": True,
                    "manual_confirmation_required": True,
                })

            return chapter_text, report

    async def _run_optimizer(
        self,
        chapter_content: str,
        *,
        user_id: int,
        context: Optional[Dict[str, Any]] = None,
        dimensions: Optional[List[str]] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        with LLMService.daily_limit_scope(f"pipeline_optimizer:{user_id}:{len(chapter_content)}"):
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
                    text_result = await call_generation_text(
                        llm_service=self.llm_service,
                        system_prompt=prompt,
                        conversation_history=[{"role": "user", "content": json.dumps(optimize_input, ensure_ascii=False)}],
                        temperature=0.55,
                        user_id=user_id,
                        timeout=600.0,
                        policy=GenerationCallPolicy(
                            stage_label=f"局部优化维度 {dimension}",
                            progress_stage="optimize_content",
                            retry_attempts=2,
                            response_format="json_object",
                            max_tokens=8000,
                            retry_same_model_once=True,
                            json_repair_attempts=0,
                        ),
                    )
                    cleaned = remove_think_tags(text_result.text)
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

    @staticmethod
    def _should_run_enrichment(
        original_word_count: int,
        *,
        target_word_count: int,
        min_word_count: Optional[int] = None,
    ) -> Tuple[bool, int]:
        effective_min = max(0, int(min_word_count if min_word_count is not None else int(target_word_count * 0.7)))
        preferred_floor = max(effective_min, int(target_word_count * 0.92))
        return original_word_count < preferred_floor, effective_min

    async def _run_enrichment(
        self,
        chapter_content: str,
        *,
        user_id: int,
        target_word_count: int = 3000,
        min_word_count: Optional[int] = None,
        max_iterations: int = 2,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        original_word_count = self._count_words(chapter_content)
        should_enrich, effective_min = self._should_run_enrichment(
            original_word_count,
            target_word_count=target_word_count,
            min_word_count=min_word_count,
        )
        preferred_floor = max(effective_min, int(target_word_count * 0.92))
        logger.info(
            "扩写检查：original_words=%s effective_min=%s preferred_floor=%s target=%s will_enrich=%s",
            original_word_count,
            effective_min,
            preferred_floor,
            target_word_count,
            should_enrich,
        )
        if not should_enrich:
            logger.info("扩写已跳过：当前内容已达到接近目标字数的阈值")
            return chapter_content, None

        service = EnrichmentService(self.session, self.llm_service)
        enriched_text = await service.enrich_to_target(
            chapter_text=chapter_content,
            target_word_count=target_word_count,
            user_id=user_id,
            max_iterations=max_iterations,
            context=context,
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
            "preferred_floor": preferred_floor,
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

    @classmethod
    def _preserve_non_regressive_content(
        cls,
        *,
        previous_content: Optional[str],
        candidate_content: Optional[str],
        stage_label: str,
        min_word_count: Optional[int] = None,
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        previous_text = previous_content or ""
        candidate_text = candidate_content or ""
        previous_word_count = cls._count_words(previous_text)
        candidate_word_count = cls._count_words(candidate_text)

        if not candidate_text.strip():
            return previous_text, {
                "stage": stage_label,
                "reason": "empty_candidate",
                "previous_word_count": previous_word_count,
                "candidate_word_count": candidate_word_count,
                "min_word_count": min_word_count,
            }

        if previous_word_count <= 0:
            return candidate_text, None

        if candidate_word_count >= previous_word_count:
            return candidate_text, None

        effective_min = max(0, int(min_word_count or 0))
        if effective_min and candidate_word_count >= effective_min:
            return candidate_text, None

        revision_friendly_stages = {"self_critique", "reader_polish", "consistency_repair"}
        floor_ratio = 0.72 if stage_label in revision_friendly_stages else 0.85
        non_regressive_floor = max(1, int(previous_word_count * floor_ratio))
        if candidate_word_count >= non_regressive_floor:
            return candidate_text, None

        shrink_ratio = round(candidate_word_count / max(1, previous_word_count), 4)
        return previous_text, {
            "stage": stage_label,
            "reason": "catastrophic_shrinkage",
            "previous_word_count": previous_word_count,
            "candidate_word_count": candidate_word_count,
            "min_word_count": effective_min or None,
            "preserved_floor": non_regressive_floor,
            "preserved_floor_ratio": floor_ratio,
            "shrink_ratio": shrink_ratio,
        }

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

# force reload