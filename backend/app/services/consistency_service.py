"""
一致性检查服务

职责：
1. 检查章节与既有设定/状态/剧情线是否冲突
2. 优先进行局部修复，不轻易整章改写
3. 为上层流水线提供结构化冲突与修复结果
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.foreshadowing import Foreshadowing
from ..models.memory_layer import CharacterState
from ..models.novel import NovelBlueprint
from ..models.project_memory import ProjectMemory
from ..utils.json_utils import remove_think_tags, unwrap_markdown_json
from .llm_service import LLMService

logger = logging.getLogger(__name__)


class ViolationSeverity(str, Enum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


@dataclass
class ConsistencyViolation:
    severity: ViolationSeverity
    category: str
    description: str
    location: Optional[str] = None
    suggested_fix: Optional[str] = None
    confidence: float = 0.8


@dataclass
class ConsistencyCheckResult:
    is_consistent: bool
    violations: List[ConsistencyViolation]
    summary: str
    check_time_ms: int = 0
    status: str = "passed"


CONSISTENCY_CHECK_PROMPT = """请检查下面章节是否与既有信息存在明显冲突。

[小说设定]
{novel_setting}

[角色状态]
{character_state}

[前文摘要]
{global_summary}

[剧情线/未解决问题]
{plot_arcs}

[当前章节]
{chapter_text}

只输出 JSON：
{{
  "is_consistent": true,
  "violations": [
    {{
      "severity": "critical/major/minor",
      "category": "setting/character/plot/foreshadowing",
      "description": "问题描述",
      "location": "问题位置",
      "suggested_fix": "修复建议",
      "confidence": 0.8
    }}
  ],
  "summary": "整体评估"
}}
"""

GENERATE_FIX_PROMPT = """请修复下面章节中的一致性问题，尽量不改变主线剧情方向。

[章节内容]
{chapter_text}

[问题]
{violations}

[参考设定]
- 小说设定：{novel_setting}
- 角色状态：{character_state}
- 前文摘要：{global_summary}

请直接输出修复后的正文。
"""


class ConsistencyService:
    def __init__(self, db: AsyncSession, llm_service: LLMService):
        self.db = db
        self.llm_service = llm_service

    @staticmethod
    def _truncate_text(value: Optional[str], limit: int) -> str:
        text = (value or "").strip()
        return text if len(text) <= limit else f"{text[:limit].rstrip()}..."

    @classmethod
    def _excerpt_chapter_for_check(cls, chapter_text: str, *, limit: int = 9000) -> str:
        text = (chapter_text or "").strip()
        if len(text) <= limit:
            return text
        head = text[:4200]
        middle_start = max((len(text) // 2) - 1200, 0)
        middle = text[middle_start: middle_start + 2400]
        tail = text[-2200:]
        return "\n\n[开头摘录]\n" + head + "\n\n[中段摘录]\n" + middle + "\n\n[结尾摘录]\n" + tail

    @staticmethod
    def _split_paragraphs(chapter_text: str) -> List[str]:
        parts = [part.strip() for part in re.split(r"\n\s*\n", chapter_text or "") if part.strip()]
        return parts or [chapter_text]

    @staticmethod
    def _expand_indexes(indexes: List[int], total: int, radius: int = 1) -> List[int]:
        picked = set()
        for index in indexes:
            start = max(0, index - radius)
            end = min(total - 1, index + radius)
            picked.update(range(start, end + 1))
        return sorted(picked)

    def _locate_violation_indexes(self, paragraphs: List[str], violations: List[ConsistencyViolation]) -> List[int]:
        indexes: List[int] = []
        for violation in violations[:6]:
            location = str(violation.location or "").strip()
            description = str(violation.description or "").strip()
            if location and location != "未知":
                normalized = location.replace("...", "").strip()
                for idx, paragraph in enumerate(paragraphs):
                    if normalized and normalized in paragraph and idx not in indexes:
                        indexes.append(idx)
            if indexes:
                continue
            keywords = [item for item in re.split(r"[，、；。,.。\s]+", description) if len(item) >= 2][:3]
            for keyword in keywords:
                for idx, paragraph in enumerate(paragraphs):
                    if keyword in paragraph and idx not in indexes:
                        indexes.append(idx)
            if indexes:
                continue
        return indexes[:4] if indexes else ([0] if paragraphs else [])

    @staticmethod
    def _safe_json_object(response: str) -> Optional[Dict[str, Any]]:
        content = unwrap_markdown_json(remove_think_tags(response or ""))
        json_start = content.find("{")
        json_end = content.rfind("}") + 1
        if json_start < 0 or json_end <= json_start:
            return None
        try:
            data = json.loads(content[json_start:json_end])
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    async def check_consistency(
        self,
        project_id: str,
        chapter_text: str,
        user_id: int,
        include_foreshadowing: bool = True,
    ) -> ConsistencyCheckResult:
        started_at = time.time()
        context = await self._get_check_context(project_id, include_foreshadowing)
        prompt = CONSISTENCY_CHECK_PROMPT.format(
            novel_setting=self._truncate_text(context.get("novel_setting"), 2200) or "（未设定）",
            character_state=self._truncate_text(context.get("character_state"), 2000) or "（未记录）",
            global_summary=self._truncate_text(context.get("global_summary"), 1800) or "（无前文摘要）",
            plot_arcs=self._truncate_text(context.get("plot_arcs"), 1800) or "（无剧情线记录）",
            chapter_text=self._excerpt_chapter_for_check(chapter_text),
        )
        try:
            response = await self.llm_service.generate(
                prompt=prompt,
                user_id=user_id,
                max_tokens=2000,
                temperature=0.2,
            )
            result = self._parse_check_response(response)
            result.check_time_ms = int((time.time() - started_at) * 1000)
            return result
        except Exception as exc:
            logger.error("一致性检查失败: %s", exc)
            return ConsistencyCheckResult(
                is_consistent=False,
                violations=[],
                summary=f"检查过程出错: {exc}",
                check_time_ms=int((time.time() - started_at) * 1000),
                status="error",
            )

    async def _auto_fix_locally(
        self,
        *,
        chapter_text: str,
        violations: List[ConsistencyViolation],
        context: Dict[str, Any],
        user_id: int,
    ) -> Optional[str]:
        paragraphs = self._split_paragraphs(chapter_text)
        if len(paragraphs) < 3:
            return None

        target_indexes = self._locate_violation_indexes(paragraphs, violations)
        if not target_indexes:
            return None
        window_indexes = self._expand_indexes(target_indexes, len(paragraphs), radius=1)
        excerpt = "\n\n".join(paragraphs[index] for index in window_indexes)
        prev_anchor = paragraphs[window_indexes[0] - 1] if window_indexes[0] > 0 else ""
        next_anchor = paragraphs[window_indexes[-1] + 1] if window_indexes[-1] + 1 < len(paragraphs) else ""
        violations_text = "\n".join(
            f"- [{v.severity.value}] {v.category}: {v.description}"
            + (f"\n  位置: {v.location}" if v.location else "")
            + (f"\n  建议: {v.suggested_fix}" if v.suggested_fix else "")
            for v in violations[:6]
        )
        prompt = f"""你现在只修复章节中的局部一致性冲突，不要整章重写。

[必须修复的问题]
{violations_text}

[前文锚点]
{prev_anchor or "（无）"}

[允许改写的片段]
{excerpt}

[后文锚点]
{next_anchor or "（无）"}

[参考设定]
- 小说设定：{self._truncate_text(context.get("novel_setting"), 1200)}
- 角色状态：{self._truncate_text(context.get("character_state"), 1000)}
- 前文摘要：{self._truncate_text(context.get("global_summary"), 1000)}

要求：
1. 只输出修复后的片段正文。
2. 不改变既定剧情方向，只修复冲突和承接。
3. 开头和结尾必须自然衔接前后锚点。
"""
        try:
            response = await self.llm_service.generate(
                prompt=prompt,
                user_id=user_id,
                max_tokens=2500,
                temperature=0.35,
            )
            cleaned = remove_think_tags(response).strip() if response else ""
            if not cleaned:
                return None

            rebuilt: List[str] = []
            inserted = False
            for idx, paragraph in enumerate(paragraphs):
                if idx == window_indexes[0]:
                    rebuilt.append(cleaned)
                    inserted = True
                if idx in window_indexes:
                    continue
                rebuilt.append(paragraph)
            if not inserted:
                return None
            return "\n\n".join(part.strip() for part in rebuilt if part.strip())
        except Exception as exc:
            logger.warning("局部一致性修复失败: %s", exc)
            return None

    async def auto_fix(
        self,
        project_id: str,
        chapter_text: str,
        violations: List[ConsistencyViolation],
        user_id: int,
    ) -> Optional[str]:
        if not violations:
            return chapter_text

        context = await self._get_check_context(project_id)
        localized_fixed = await self._auto_fix_locally(
            chapter_text=chapter_text,
            violations=violations,
            context=context,
            user_id=user_id,
        )
        if localized_fixed and localized_fixed != chapter_text:
            return localized_fixed

        violations_text = "\n".join(
            f"- [{v.severity.value}] {v.category}: {v.description}"
            + (f"\n  位置: {v.location}" if v.location else "")
            + (f"\n  建议: {v.suggested_fix}" if v.suggested_fix else "")
            for v in violations[:6]
        )
        prompt = GENERATE_FIX_PROMPT.format(
            chapter_text=self._excerpt_chapter_for_check(chapter_text, limit=7000),
            violations=violations_text,
            novel_setting=self._truncate_text(context.get("novel_setting"), 1600),
            character_state=self._truncate_text(context.get("character_state"), 1400),
            global_summary=self._truncate_text(context.get("global_summary"), 1200),
        )
        try:
            response = await self.llm_service.generate(
                prompt=prompt,
                user_id=user_id,
                max_tokens=8000,
                temperature=0.5,
            )
            cleaned = remove_think_tags(response) if response else ""
            return cleaned.strip() if cleaned else None
        except Exception as exc:
            logger.error("自动修复失败: %s", exc)
            return None

    async def check_and_fix(
        self,
        project_id: str,
        chapter_text: str,
        user_id: int,
        auto_fix_threshold: ViolationSeverity = ViolationSeverity.CRITICAL,
    ) -> Dict[str, Any]:
        check_result = await self.check_consistency(project_id=project_id, chapter_text=chapter_text, user_id=user_id)
        result: Dict[str, Any] = {
            "check_result": check_result,
            "fixed_content": None,
            "needs_manual_review": False,
        }
        if check_result.is_consistent:
            return result

        severity_order = [ViolationSeverity.CRITICAL, ViolationSeverity.MAJOR, ViolationSeverity.MINOR]
        threshold_index = severity_order.index(auto_fix_threshold)
        violations_to_fix = [
            item for item in check_result.violations
            if severity_order.index(item.severity) <= threshold_index
        ]
        if violations_to_fix:
            result["fixed_content"] = await self.auto_fix(
                project_id=project_id,
                chapter_text=chapter_text,
                violations=violations_to_fix,
                user_id=user_id,
            )

        result["needs_manual_review"] = any(
            item.severity == ViolationSeverity.MAJOR for item in check_result.violations
        ) and auto_fix_threshold == ViolationSeverity.CRITICAL
        return result

    async def _get_check_context(self, project_id: str, include_foreshadowing: bool = True) -> Dict[str, str]:
        context: Dict[str, str] = {}

        blueprint = (
            await self.db.execute(
                select(NovelBlueprint).where(NovelBlueprint.project_id == project_id).limit(1)
            )
        ).scalar_one_or_none()
        if blueprint:
            setting_parts: List[str] = []
            if blueprint.genre:
                setting_parts.append(f"类型: {blueprint.genre}")
            if blueprint.style:
                setting_parts.append(f"风格: {blueprint.style}")
            if blueprint.world_setting:
                setting_parts.append(f"世界观: {blueprint.world_setting}")
            if blueprint.full_synopsis:
                setting_parts.append(f"故事概要: {blueprint.full_synopsis}")
            context["novel_setting"] = self._truncate_text("\n".join(setting_parts), 2600)

        memory = (
            await self.db.execute(
                select(ProjectMemory).where(ProjectMemory.project_id == project_id).limit(1)
            )
        ).scalar_one_or_none()
        if memory:
            context["global_summary"] = self._truncate_text(memory.global_summary or "", 2000)
            if memory.plot_arcs:
                context["plot_arcs"] = self._truncate_text(
                    json.dumps(memory.plot_arcs, ensure_ascii=False, indent=2),
                    2200,
                )

        states = (
            await self.db.execute(
                select(CharacterState)
                .where(CharacterState.project_id == project_id)
                .order_by(CharacterState.chapter_number.desc())
                .limit(10)
            )
        ).scalars().all()
        if states:
            state_texts: List[str] = []
            for state in states:
                if getattr(state, "extra", None) and "raw_state_text" in state.extra:
                    state_texts.append(str(state.extra["raw_state_text"]))
                    break
                fragments = [
                    f"角色: {getattr(state, 'character_name', '')}",
                    f"位置: {getattr(state, 'location', '') or '未知'}",
                    f"情绪: {getattr(state, 'emotion', '') or '未知'}",
                ]
                state_texts.append(" | ".join(fragments))
            context["character_state"] = self._truncate_text("\n".join(state_texts), 2000)

        if include_foreshadowing:
            foreshadowings = (
                await self.db.execute(
                    select(Foreshadowing).where(
                        Foreshadowing.project_id == project_id,
                        Foreshadowing.status.in_(["planted", "developing"]),
                    )
                )
            ).scalars().all()
            if foreshadowings:
                foreshadowing_texts = [
                    f"- 第{item.chapter_number}章埋设: {self._truncate_text(item.content, 100)}"
                    for item in foreshadowings[:10]
                ]
                context["foreshadowings"] = self._truncate_text("\n".join(foreshadowing_texts), 1200)
                if not context.get("plot_arcs"):
                    context["plot_arcs"] = context["foreshadowings"]

        return context

    def _parse_check_response(self, response: str) -> ConsistencyCheckResult:
        data = self._safe_json_object(response)
        if not data:
            return ConsistencyCheckResult(
                is_consistent=False,
                violations=[],
                summary="一致性检查结果解析失败",
                status="error",
            )

        raw_violations = data.get("violations", [])
        violations: List[ConsistencyViolation] = []
        if isinstance(raw_violations, list):
            for item in raw_violations:
                if not isinstance(item, dict):
                    continue
                severity_raw = str(item.get("severity") or "minor").lower()
                severity = (
                    ViolationSeverity.CRITICAL if severity_raw == "critical"
                    else ViolationSeverity.MAJOR if severity_raw == "major"
                    else ViolationSeverity.MINOR
                )
                violations.append(
                    ConsistencyViolation(
                        severity=severity,
                        category=str(item.get("category") or "plot"),
                        description=str(item.get("description") or "发现一致性问题"),
                        location=str(item.get("location") or "") or None,
                        suggested_fix=str(item.get("suggested_fix") or "") or None,
                        confidence=float(item.get("confidence", 0.8) or 0.8),
                    )
                )

        return ConsistencyCheckResult(
            is_consistent=bool(data.get("is_consistent", not violations)),
            violations=violations,
            summary=str(data.get("summary") or "一致性检查已完成"),
            status="passed" if not violations and bool(data.get("is_consistent", True)) else "warning",
        )
