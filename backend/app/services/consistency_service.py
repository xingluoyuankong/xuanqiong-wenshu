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
from .generation_call_service import GenerationCallPolicy, call_generation_json, call_generation_text
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

    @classmethod
    def _extract_paragraph_indexes_from_location(cls, location: str, *, total: int) -> List[int]:
        numbers = [int(item) for item in re.findall(r"第\s*(\d+)\s*段", str(location or ""))]
        indexes: List[int] = []
        for number in numbers:
            index = number - 1
            if 0 <= index < total and index not in indexes:
                indexes.append(index)
        return indexes

    @staticmethod
    def _expand_indexes(indexes: List[int], total: int, radius: int = 1) -> List[int]:
        picked = set()
        for index in indexes:
            start = max(0, index - radius)
            end = min(total - 1, index + radius)
            picked.update(range(start, end + 1))
        return sorted(picked)

    @staticmethod
    def _violation_indicates_residue(violation: ConsistencyViolation) -> bool:
        haystack = " ".join(
            str(value or "")
            for value in (violation.description, violation.location, violation.suggested_fix)
        )
        residue_markers = (
            "重复", "再次", "重新", "首次", "第一次", "两次", "双版本", "拼接", "回卷", "时间线", "认知重置",
            "来源不一致", "重复发现", "多次呈现为第一次", "前后不一致",
        )
        return any(marker in haystack for marker in residue_markers)

    def _resolve_local_fix_window(self, indexes: List[int], violations: List[ConsistencyViolation], total: int) -> tuple[List[int], str]:
        if not indexes:
            return [], "none"
        span = max(indexes) - min(indexes)
        force_contiguous = span >= 3 or any(self._violation_indicates_residue(item) for item in violations)
        if force_contiguous:
            return list(range(min(indexes), max(indexes) + 1)), "contiguous_span"
        return self._expand_indexes(indexes, total, radius=1), "expanded_window"

    @classmethod
    def _build_residue_hints(cls, violations: List[ConsistencyViolation], *, limit: int = 4) -> List[str]:
        hints: List[str] = []
        for violation in violations:
            if not cls._violation_indicates_residue(violation):
                continue
            summary = str(violation.description or violation.location or "").strip()
            if summary and summary not in hints:
                hints.append(summary)
            if len(hints) >= limit:
                break
        return hints

    @staticmethod
    def _violation_haystack(violation: ConsistencyViolation) -> str:
        return " ".join(
            str(value or "")
            for value in (violation.description, violation.location, violation.suggested_fix)
        )

    @classmethod
    def _build_violation_execution_requirements(cls, violations: List[ConsistencyViolation], *, limit: int = 4) -> List[str]:
        requirements: List[str] = []
        haystack = "\n".join(cls._violation_haystack(item) for item in violations)
        if any(token in haystack for token in ("时间冲突", "年份很旧", "黑潮登陆夜", "日期", "旧卷", "旧档案", "最近一次黑潮")):
            requirements.append("若冲突来自‘旧卷/旧档案’与‘最近黑潮日期’并存，必须在正文里显式补一个单一解释踏板：旧封新页、后贴补录、人为夹带，或二次篡改其一，不能让两个版本并排成立。")
        if any(token in haystack for token in ("来源不一致", "物件流转", "借阅单", "残页", "外借", "清单", "卷宗")):
            requirements.append("若冲突来自物件来源或流转边界不清，必须把主卷、残页、借阅单、外借记录之间的关系说清，只保留一条正式流转链。")
        if any(token in haystack for token in ("重复", "双版本", "拼接", "回卷", "第一次", "再次", "认知重置")):
            requirements.append("若冲突来自重复发现或时间线回卷，必须删掉被废弃版本，只保留一次正式发现/确认动作。")
        if any(token in haystack for token in ("人称/性别指代", "性别指代", "人称冲突", "称谓冲突", "指代前后冲突", "代词前后不一致")):
            requirements.append("若冲突来自人称、称谓或性别指代不一致，必须统一同一角色在该场景内的称谓与代词，只保留一套稳定指代，不要在“他/她/TA”或不同身份称呼之间来回切换。")
        if any(token in haystack for token in ("说法冲突", "改口", "前后不一致", "设定冲突")):
            requirements.append("若同一事实出现两种说法，必须选定一种为正式事实，并把另一种改成误导、试探、记错或伪装，不要两种都当真。")
        for violation in violations[:2]:
            if violation.suggested_fix:
                line = f"优先落实：{str(violation.suggested_fix).strip()}"
                if line not in requirements:
                    requirements.append(line)
            if len(requirements) >= limit:
                break
        return requirements[:limit]

    def _locate_violation_indexes(self, paragraphs: List[str], violations: List[ConsistencyViolation]) -> List[int]:
        indexes: List[int] = []
        for violation in violations[:6]:
            matched_indexes: List[int] = []
            location = str(violation.location or "").strip()
            description = str(violation.description or "").strip()
            suggested_fix = str(violation.suggested_fix or "").strip()
            if location and location != "未知":
                matched_indexes.extend(self._extract_paragraph_indexes_from_location(location, total=len(paragraphs)))
                if not matched_indexes:
                    normalized = location.replace("...", "").strip()
                    for idx, paragraph in enumerate(paragraphs):
                        if normalized and normalized in paragraph and idx not in matched_indexes:
                            matched_indexes.append(idx)
            if not matched_indexes:
                keywords = [item for item in re.split(r"[，、；。,.。\s]+", description) if len(item) >= 2][:3]
                for keyword in keywords:
                    for idx, paragraph in enumerate(paragraphs):
                        if keyword in paragraph and idx not in matched_indexes:
                            matched_indexes.append(idx)
                    if matched_indexes:
                        break
            if not matched_indexes and suggested_fix:
                keywords = [item for item in re.split(r"[，、；。,.。\s]+", suggested_fix) if len(item) >= 2][:3]
                for keyword in keywords:
                    for idx, paragraph in enumerate(paragraphs):
                        if keyword in paragraph and idx not in matched_indexes:
                            matched_indexes.append(idx)
                    if matched_indexes:
                        break
            for idx in matched_indexes:
                if idx not in indexes:
                    indexes.append(idx)
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
        with LLMService.daily_limit_scope(f"consistency_check:{project_id}:{user_id}:{len(chapter_text or '')}"):
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
                json_result = await call_generation_json(
                    llm_service=self.llm_service,
                    system_prompt="你是一位长篇小说连续性审校，必须只输出 JSON。",
                    conversation_history=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    user_id=user_id,
                    timeout=120.0,
                    policy=GenerationCallPolicy(
                        stage_label="跨章节一致性检查",
                        progress_stage="continuity_gate",
                        retry_attempts=2,
                        response_format="json_object",
                        max_tokens=2200,
                        retry_same_model_once=True,
                        json_repair_attempts=1,
                    ),
                )
                result = self._parse_check_response(json.dumps(json_result.data, ensure_ascii=False))
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
        window_indexes, rewrite_mode = self._resolve_local_fix_window(target_indexes, violations, len(paragraphs))
        excerpt = "\n\n".join(paragraphs[index] for index in window_indexes)
        prev_anchor = paragraphs[window_indexes[0] - 1] if window_indexes[0] > 0 else ""
        next_anchor = paragraphs[window_indexes[-1] + 1] if window_indexes[-1] + 1 < len(paragraphs) else ""
        residue_hints = self._build_residue_hints(violations)
        residue_guard = ""
        if residue_hints:
            residue_guard = "[必须删除的旧版本残留]\n" + "\n".join(f"- {item}" for item in residue_hints[:4]) + "\n\n"
        execution_requirements = self._build_violation_execution_requirements(violations)
        execution_guard = ""
        if execution_requirements:
            execution_guard = "[本轮必须落地的修复动作]\n" + "\n".join(f"- {item}" for item in execution_requirements) + "\n\n"
        violations_text = "\n".join(
            f"- [{v.severity.value}] {v.category}: {v.description}"
            + (f"\n  位置: {v.location}" if v.location else "")
            + (f"\n  建议: {v.suggested_fix}" if v.suggested_fix else "")
            for v in violations[:6]
        )
        prompt = f"""你现在只修复章节中的局部一致性冲突，不要整章重写。

[必须修复的问题]
{violations_text}

[修复模式]
{'连续统一区段改写' if rewrite_mode == 'contiguous_span' else '局部窗口改写'}

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

{execution_guard}{residue_guard}要求：
1. 只输出修复后的片段正文。
2. 不改变既定剧情方向，只修复冲突和承接。
3. 开头和结尾必须自然衔接前后锚点。
4. 如果同一线索、发现动作、对话或事件推进在片段中出现多个版本，只保留一个正式版本，删除其余残留。
5. 如果角色在前文已经知道某事，不要在本片段里再写成第一次得知或第一次确认。
6. 如果冲突来自时间、来源或设定边界，只能给出一条正式解释链，不要并排保留两个都成立的版本。
7. 必须把修复落到正文动作、证据或说法上，不要只抽象解释“这里存在问题”。
"""
        try:
            text_result = await call_generation_text(
                llm_service=self.llm_service,
                system_prompt="你是一位只做局部补丁的长篇小说连续性编辑。",
                conversation_history=[{"role": "user", "content": prompt}],
                temperature=0.35,
                user_id=user_id,
                timeout=150.0,
                policy=GenerationCallPolicy(
                    stage_label="局部一致性修复",
                    progress_stage="consistency",
                    retry_attempts=2,
                    response_format=None,
                    max_tokens=2500,
                    retry_same_model_once=True,
                ),
            )
            cleaned = remove_think_tags(text_result.text).strip() if text_result.text else ""
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
        with LLMService.daily_limit_scope(f"consistency_fix:{project_id}:{user_id}:{len(chapter_text or '')}"):
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
            execution_requirements = self._build_violation_execution_requirements(violations, limit=5)
            if execution_requirements:
                violations_text = (
                    violations_text
                    + "\n\n[本轮必须落地的修复动作]\n"
                    + "\n".join(f"- {item}" for item in execution_requirements)
                )
            prompt = GENERATE_FIX_PROMPT.format(
                chapter_text=self._excerpt_chapter_for_check(chapter_text, limit=7000),
                violations=violations_text,
                novel_setting=self._truncate_text(context.get("novel_setting"), 1600),
                character_state=self._truncate_text(context.get("character_state"), 1400),
                global_summary=self._truncate_text(context.get("global_summary"), 1200),
            )
            try:
                text_result = await call_generation_text(
                    llm_service=self.llm_service,
                    system_prompt="你是一位长篇小说修复编辑。默认只做必要补丁，保持既有剧情和连续性。",
                    conversation_history=[{"role": "user", "content": prompt}],
                    temperature=0.5,
                    user_id=user_id,
                    timeout=240.0,
                    policy=GenerationCallPolicy(
                        stage_label="一致性补丁兜底",
                        progress_stage="consistency",
                        retry_attempts=2,
                        response_format=None,
                        max_tokens=8000,
                        retry_same_model_once=True,
                    ),
                )
                cleaned = remove_think_tags(text_result.text).strip() if text_result.text else ""
                if not cleaned:
                    return None
                guard_failure = self._fix_continuity_guard_failure(chapter_text, cleaned)
                if guard_failure:
                    logger.warning(
                        "Consistency fallback fix rejected by continuity guard: project=%s reason=%s",
                        project_id,
                        guard_failure,
                    )
                    return None
                return cleaned
            except Exception as exc:
                logger.error("自动修复失败: %s", exc)
                return None

    def _fix_continuity_guard_failure(self, original: str, fixed: str) -> Optional[str]:
        original_clean = str(original or "").strip()
        fixed_clean = str(fixed or "").strip()
        if not fixed_clean:
            return "empty_fixed_content"
        if fixed_clean.startswith("{") and "fixed" in fixed_clean[:240].lower():
            return "raw_json_returned"
        original_len = len(re.sub(r"\s+", "", original_clean))
        fixed_len = len(re.sub(r"\s+", "", fixed_clean))
        if original_len >= 1200 and fixed_len < int(original_len * 0.72):
            return f"fixed_content_shrank_too_much:{fixed_len}/{original_len}"
        if original_len >= 400 and fixed_len < int(original_len * 0.58):
            return f"fixed_content_lost_too_much:{fixed_len}/{original_len}"

        original_paragraphs = self._split_paragraphs(original_clean)
        fixed_paragraphs = self._split_paragraphs(fixed_clean)
        if len(original_paragraphs) >= 6 and len(fixed_paragraphs) < max(3, len(original_paragraphs) // 3):
            return f"fixed_content_collapsed_paragraphs:{len(fixed_paragraphs)}/{len(original_paragraphs)}"

        anchors: List[str] = []
        if original_paragraphs:
            first = re.sub(r"\s+", "", original_paragraphs[0])
            last = re.sub(r"\s+", "", original_paragraphs[-1])
            if len(first) >= 16:
                anchors.append(first[:24])
            if len(last) >= 16:
                anchors.append(last[-24:])
        if len(anchors) >= 2:
            compact_fixed = re.sub(r"\s+", "", fixed_clean)
            missing = [anchor for anchor in anchors if anchor and anchor not in compact_fixed]
            if len(missing) == len(anchors):
                return "lost_front_and_back_anchors"
        return None

    async def check_and_fix(
        self,
        project_id: str,
        chapter_text: str,
        user_id: int,
        auto_fix_threshold: ViolationSeverity = ViolationSeverity.CRITICAL,
    ) -> Dict[str, Any]:
        with LLMService.daily_limit_scope(f"consistency_check_fix:{project_id}:{user_id}:{len(chapter_text or '')}"):
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
