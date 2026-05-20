"""Structured self-critique and targeted local revision service."""
from __future__ import annotations

from enum import Enum
from typing import Optional, Dict, Any, List, Callable, Awaitable, Tuple
import hashlib
import json
import logging
import re

from sqlalchemy.ext.asyncio import AsyncSession

from .generation_call_service import GenerationCallPolicy, call_generation_json, call_generation_text
from .llm_service import LLMService
from .prompt_service import PromptService
from ..utils.json_utils import remove_think_tags, sanitize_json_like_text, unwrap_markdown_json

logger = logging.getLogger(__name__)


class CritiqueDimension(str, Enum):
    LOGIC = "logic"
    CONTINUITY = "continuity"
    POV = "pov"
    CHARACTER = "character"
    RELATIONSHIP = "relationship"
    WRITING = "writing"
    PACING = "pacing"
    EMOTION = "emotion"
    DIALOGUE = "dialogue"
    SCENE = "scene"
    SUSPENSE = "suspense"


class SelfCritiqueService:
    REVISION_STRATEGIES = {
        "structure_guardrail": {
            "label": "结构与护栏修订",
            "dimensions": {"logic", "continuity", "pov"},
            "window_radius": 2,
            "rewrite_limit": 6,
            "instruction": "优先修复因果、承接、信息边界和 POV 越界；若出现重复时间线、双版本拼接或事件回卷，必须合并为单一正式事件链，禁止为了润色而改动主线事实。",
        },
        "character_dynamics": {
            "label": "人物与关系修订",
            "dimensions": {"character", "relationship", "emotion", "dialogue"},
            "window_radius": 1,
            "rewrite_limit": 4,
            "instruction": "优先修复人物反应、关系张力、情绪递进与对白口吻，让角色行为更像角色本人。",
        },
        "delivery_polish": {
            "label": "表达与节奏修订",
            "dimensions": {"pacing", "scene", "suspense", "writing"},
            "window_radius": 1,
            "rewrite_limit": 4,
            "instruction": "优先修复节奏拖沓、场景失焦、钩子不足和表达空泛，但不要稀释冲突强度。",
        },
    }

    LOCAL_REWRITE_DIMENSION_HINTS = {
        "continuity": ["承接", "上一章", "状态", "时间", "关系"],
        "dialogue": ["对话", "台词", "说", "问", "回应"],
        "emotion": ["情绪", "心理", "呼吸", "恐惧", "愤怒", "挣扎"],
        "character": ["动机", "欲望", "顾虑", "人物", "角色"],
        "relationship": ["关系", "互动", "拉扯", "试探", "冲突"],
        "pacing": ["节奏", "拖沓", "推进", "转折", "高潮"],
        "scene": ["场景", "动作", "环境", "空间", "细节"],
        "suspense": ["悬念", "章末", "钩子", "反转", "压力"],
        "logic": ["因果", "逻辑", "矛盾", "前后不一致"],
        "pov": ["视角", "边界", "越界", "全知"],
        "writing": ["文风", "说明", "表达", "描写", "重复"],
    }

    CRITIQUE_PROMPTS = {
        CritiqueDimension.LOGIC: {
            "name": "逻辑一致性",
            "focus": ["事件因果是否合理", "时间线是否自洽", "角色行为动机是否充足", "世界规则是否稳定", "是否存在明显自相矛盾"],
            "severity_weight": 1.5,
        },
        CritiqueDimension.CONTINUITY: {
            "name": "跨章连续性",
            "focus": ["开篇是否承接上一章", "本章是否推进既有冲突", "角色状态与关系是否承接前文", "是否有无过渡跳切", "章末压力是否传递给下一章"],
            "severity_weight": 1.45,
        },
        CritiqueDimension.POV: {
            "name": "视角与信息边界",
            "focus": ["是否严格限制在 POV 感知范围", "是否出现全知旁白或偷渡信息", "心理描写是否越界到他人内心", "信息揭示顺序是否失控", "是否有明显视角穿帮"],
            "severity_weight": 1.45,
        },
        CritiqueDimension.CHARACTER: {
            "name": "角色真实度",
            "focus": ["角色性格与欲望是否鲜明", "言行是否符合人设", "决策是否符合立场与伤口", "关键角色是否有可感知变化", "人物是否只是工具人"],
            "severity_weight": 1.35,
        },
        CritiqueDimension.RELATIONSHIP: {
            "name": "关系张力",
            "focus": ["主要角色关系是否发生变化", "互动是否体现试探/拉扯/压迫", "关系推进是否有代价", "潜台词是否成立", "关系温度是否始终不变"],
            "severity_weight": 1.15,
        },
        CritiqueDimension.WRITING: {
            "name": "文风与可读性",
            "focus": ["是否存在 AI 套话", "是否重复、口水、空泛判断", "描写是否具体", "是否过度解释", "语言是否有现场感"],
            "severity_weight": 1.0,
        },
        CritiqueDimension.PACING: {
            "name": "节奏控制",
            "focus": ["是否拖沓或像提纲扩写", "句式呼吸是否匹配情绪", "转折点是否有效", "高潮与缓冲分布是否合理", "信息密度是否失衡"],
            "severity_weight": 1.05,
        },
        CritiqueDimension.EMOTION: {
            "name": "情绪推进",
            "focus": ["全章是否存在明确情绪曲线", "情绪是否通过动作细节而非贴标签表达", "情绪变化是否自然且有因果", "读者是否能感到温差和压迫"],
            "severity_weight": 1.15,
        },
        CritiqueDimension.DIALOGUE: {
            "name": "对话质量",
            "focus": ["角色是否有明显口吻差异", "对话是否承担试探/误导/撕裂等功能", "是否存在说明书式灌输", "潜台词是否成立", "是否有可记忆的句子"],
            "severity_weight": 1.1,
        },
        CritiqueDimension.SCENE: {
            "name": "场景推进",
            "focus": ["重要场景是否有目标阻碍转折余波", "环境描写是否服务冲突", "是否调动至少两种感官", "场景切换是否自然", "是否被说明性段落挤压"],
            "severity_weight": 1.05,
        },
        CritiqueDimension.SUSPENSE: {
            "name": "悬念与章末牵引",
            "focus": ["本章是否制造新压力或误会", "章末钩子是否与主线有关", "是否提前写满冲突导致自我收束", "未解问题是否成立", "读者是否有追更动力"],
            "severity_weight": 1.1,
        },
    }

    CRITIQUE_STAGE_GROUPS: List[Tuple[str, List[CritiqueDimension]]] = [
        ("structural", [CritiqueDimension.LOGIC, CritiqueDimension.CONTINUITY, CritiqueDimension.POV]),
        ("character", [CritiqueDimension.CHARACTER, CritiqueDimension.RELATIONSHIP, CritiqueDimension.EMOTION, CritiqueDimension.DIALOGUE]),
        ("delivery", [CritiqueDimension.PACING, CritiqueDimension.SCENE, CritiqueDimension.SUSPENSE, CritiqueDimension.WRITING]),
    ]
    DIMENSION_ENUM_MAP: Dict[str, CritiqueDimension] = {dimension.value: dimension for dimension in CritiqueDimension}
    EXECUTION_REQUIREMENT_LIMIT = 10
    # Automatic optimization must preserve continuity. Whole-chapter candidates
    # are kept behind an explicit/manual path; normal generation uses anchored
    # local patches and reports deferred broad fixes instead of silently
    # replacing the chapter.
    MAX_STAGEWIDE_REWRITES_PER_ITERATION = 0
    MAX_DEFERRED_STAGE_DRAIN_ITERATIONS = 1
    STAGEWIDE_SAFETY_DIMENSIONS: List[CritiqueDimension] = [
        CritiqueDimension.CONTINUITY,
        CritiqueDimension.SCENE,
        CritiqueDimension.SUSPENSE,
        CritiqueDimension.WRITING,
    ]

    def __init__(self, db: AsyncSession, llm_service: LLMService, prompt_service: PromptService):
        self.db = db
        self.llm_service = llm_service
        self.prompt_service = prompt_service

    def _build_dimension_batches(self, dimensions: List[CritiqueDimension]) -> List[Tuple[str, List[CritiqueDimension]]]:
        normalized: List[CritiqueDimension] = []
        seen = set()
        for dimension in dimensions:
            if dimension in seen:
                continue
            seen.add(dimension)
            normalized.append(dimension)
        remaining = list(normalized)
        batches: List[Tuple[str, List[CritiqueDimension]]] = []
        for stage_name, stage_dimensions in self.CRITIQUE_STAGE_GROUPS:
            current_batch = [dimension for dimension in stage_dimensions if dimension in remaining]
            if current_batch:
                batches.append((stage_name, current_batch))
                remaining = [dimension for dimension in remaining if dimension not in current_batch]
        for dimension in remaining:
            batches.append((dimension.value, [dimension]))
        return batches

    @staticmethod
    def _truncate_text(value: Any, limit: int) -> str:
        if value is None:
            return ""
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
        text = str(text).strip()
        if len(text) <= limit:
            return text
        return f"{text[:limit].rstrip()}..."

    @staticmethod
    def _resolve_context_limit_profile(stage_name: Optional[str]) -> str:
        normalized = str(stage_name or "").strip().lower()
        if "character" in normalized:
            return "character"
        if "delivery" in normalized:
            return "delivery"
        return "structural"

    def _build_context_str(self, context: Optional[Dict[str, Any]], *, stage_name: Optional[str] = None) -> str:
        if not context:
            return ""
        profile = self._resolve_context_limit_profile(stage_name)
        stage_overrides: Dict[str, Dict[str, int]] = {
            "structural": {
                "chapter_mission": 2200,
                "previous_chapter_bundle": 2400,
                "project_memory": 1400,
                "character_profiles": 1800,
            },
            "character": {
                "chapter_mission": 1600,
                "previous_summary": 900,
                "previous_tail": 700,
                "previous_chapter_bundle": 1600,
                "recent_track": 1000,
                "plot_arc_digest": 900,
                "project_memory": 900,
                "style_context": 800,
                "character_profiles": 1600,
                "forbidden_characters": 400,
                "emotion_target": 400,
            },
            "delivery": {
                "chapter_mission": 1400,
                "previous_summary": 800,
                "previous_tail": 600,
                "previous_chapter_bundle": 1200,
                "recent_track": 800,
                "plot_arc_digest": 800,
                "project_memory": 700,
                "style_context": 700,
                "character_profiles": 900,
                "forbidden_characters": 300,
                "emotion_target": 300,
            },
        }
        sections: List[str] = []
        mapping = [
            ("outline_title", "章节标题", 200),
            ("outline_summary", "章节摘要", 1200),
            ("chapter_mission", "章节导演脚本", 2500),
            ("previous_summary", "上一章摘要", 1200),
            ("previous_tail", "上一章结尾", 1000),
            ("previous_chapter_bundle", "前一章依据包", 2800),
            ("recent_track", "近期章节轨迹", 1500),
            ("plot_arc_digest", "未闭环剧情线", 1200),
            ("project_memory", "项目长期记忆", 1800),
            ("style_context", "风格约束", 1200),
            ("character_profiles", "角色设定", 2500),
            ("forbidden_characters", "禁止角色", 600),
            ("emotion_target", "情绪目标", 600),
        ]
        overrides = stage_overrides.get(profile, {})
        for key, label, limit in mapping:
            value = context.get(key)
            if value:
                sections.append(f"[{label}]\n{self._truncate_text(value, overrides.get(key, limit))}")
        return "\n\n".join(sections)

    def _normalize_dimension_value(self, value: Any, allowed_dimensions: List[CritiqueDimension], default_dimension: CritiqueDimension) -> str:
        raw = str(value or "").strip().lower()
        allowed_values = {dimension.value for dimension in allowed_dimensions}
        return raw if raw in allowed_values else default_dimension.value

    @staticmethod
    def _normalize_overall_score(value: Any) -> float:
        try:
            score = float(value)
        except (TypeError, ValueError):
            return 70.0
        if 0 <= score <= 10:
            score *= 10
        return max(0.0, min(100.0, score))

    @staticmethod
    def _content_fingerprint(value: Any) -> str:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        if not text:
            return ""
        return hashlib.sha1(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _normalize_similarity_text(value: Any) -> str:
        return re.sub(r"\s+", "", str(value or "")).strip()

    @classmethod
    def _char_ngram_jaccard(cls, left: Any, right: Any, *, width: int = 5) -> float:
        left_text = cls._normalize_similarity_text(left)
        right_text = cls._normalize_similarity_text(right)
        if not left_text or not right_text:
            return 0.0
        if left_text == right_text:
            return 1.0
        if min(len(left_text), len(right_text)) < width:
            shorter, longer = (left_text, right_text) if len(left_text) <= len(right_text) else (right_text, left_text)
            return 1.0 if shorter and shorter in longer else 0.0
        left_grams = {left_text[idx: idx + width] for idx in range(len(left_text) - width + 1)}
        right_grams = {right_text[idx: idx + width] for idx in range(len(right_text) - width + 1)}
        union = left_grams | right_grams
        if not union:
            return 0.0
        return len(left_grams & right_grams) / len(union)

    @classmethod
    def _extract_paragraph_indexes_from_location(cls, location: str, *, total: int) -> List[int]:
        numbers = [int(item) for item in re.findall(r"第\s*(\d+)\s*段", str(location or ""))]
        indexes: List[int] = []
        for number in numbers:
            index = number - 1
            if 0 <= index < total and index not in indexes:
                indexes.append(index)
        return indexes

    def _build_rule_based_issues(self, chapter_content: str, *, context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        issues: List[Dict[str, Any]] = []
        issues.extend(self._detect_previous_tail_overlap_issue(chapter_content, context=context))
        issues.extend(self._detect_duplicate_residue_issues(chapter_content))
        unique: List[Dict[str, Any]] = []
        seen_keys = set()
        for issue in issues:
            key = (
                str(issue.get("dimension") or "").strip(),
                str(issue.get("location") or "").strip(),
                str(issue.get("problem") or "").strip(),
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)
            unique.append(issue)
        return unique

    def _detect_previous_tail_overlap_issue(self, chapter_content: str, *, context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        previous_tail = str((context or {}).get("previous_tail") or "").strip()
        if not previous_tail:
            return []
        paragraphs = self._split_paragraphs(chapter_content)
        opening = "\n\n".join(paragraphs[:2]).strip()
        if not opening:
            return []
        opening_window = opening[:320]
        previous_window = previous_tail[-320:]
        opening_norm = self._normalize_similarity_text(opening_window)
        previous_norm = self._normalize_similarity_text(previous_window)
        if len(opening_norm) < 80 or len(previous_norm) < 80:
            return []
        similarity = self._char_ngram_jaccard(opening_norm, previous_norm, width=5)
        prefix_overlap = bool(opening_norm[:20] and opening_norm[:20] in previous_norm)
        if similarity < 0.66 and not prefix_overlap:
            return []
        return [{
            "dimension": "continuity",
            "severity": "major",
            "location": "第1段",
            "problem": "开篇与上一章结尾高相似，像重复开场或旧片段回卷，削弱了跨章推进。",
            "suggestion": "保留必要承接句后立即推进新动作/新信息，不要把上一章尾声再写一遍。",
            "example": f"上一章结尾：{self._truncate_text(previous_window, 90)}｜当前开篇：{self._truncate_text(opening_window, 90)}",
            "_critique_stage": "heuristic_guard",
        }]

    def _detect_duplicate_residue_issues(self, chapter_content: str) -> List[Dict[str, Any]]:
        paragraphs = self._split_paragraphs(chapter_content)
        issues: List[Dict[str, Any]] = []
        for left_index, left_paragraph in enumerate(paragraphs):
            left_norm = self._normalize_similarity_text(left_paragraph)
            if len(left_norm) < 70:
                continue
            best_match: Optional[Tuple[int, float]] = None
            upper_bound = min(len(paragraphs), left_index + 6)
            for right_index in range(left_index + 1, upper_bound):
                right_paragraph = paragraphs[right_index]
                right_norm = self._normalize_similarity_text(right_paragraph)
                if len(right_norm) < 70:
                    continue
                similarity = self._char_ngram_jaccard(left_norm, right_norm, width=5)
                shared_prefix = (
                    (left_norm[:18] and left_norm[:18] in right_norm)
                    or (right_norm[:18] and right_norm[:18] in left_norm)
                )
                if shared_prefix:
                    similarity = max(similarity, 0.92)
                if similarity < 0.74:
                    continue
                if best_match is None or similarity > best_match[1]:
                    best_match = (right_index, similarity)
            if best_match is None:
                continue
            right_index, similarity = best_match
            issues.append({
                "dimension": "continuity",
                "severity": "major",
                "location": f"第{left_index + 1}段与第{right_index + 1}段",
                "problem": "同一推进回合在两个高相似段落里重复出现，像旧版本残留或双版本拼接。",
                "suggestion": "只保留一个正式版本，把另一个段落的有效信息并入或删去，确保动作和结论只推进一次。",
                "example": f"片段A：{self._truncate_text(left_paragraph, 80)}｜片段B：{self._truncate_text(paragraphs[right_index], 80)}｜相似度={similarity:.2f}",
                "_critique_stage": "heuristic_guard",
            })
            if len(issues) >= 2:
                break
        return issues

    @staticmethod
    def _normalize_issue_text(value: Any) -> str:
        text = str(value or "").strip().lower()
        if not text:
            return ""
        return re.sub(r"[^0-9a-z一-鿿]+", "", text)

    @classmethod
    def _summarize_issue_counts(cls, issues: List[Dict[str, Any]]) -> Dict[str, int]:
        counts = {"critical": 0, "major": 0, "minor": 0, "total": 0, "weighted": 0}
        for issue in issues or []:
            if not isinstance(issue, dict):
                continue
            severity = str(issue.get("severity") or "minor").strip().lower()
            if severity == "warning":
                severity = "major"
            if severity not in {"critical", "major", "minor"}:
                severity = "minor"
            counts[severity] += 1
            counts["total"] += 1
        counts["weighted"] = counts["critical"] * 100 + counts["major"] * 10 + counts["minor"]
        return counts

    @staticmethod
    def _should_accept_strategy_snapshot(before: Dict[str, int], after: Dict[str, int]) -> Tuple[bool, str]:
        if after["critical"] > before["critical"]:
            return False, "critical_issues_increased"
        if after["critical"] == before["critical"] and after["major"] > before["major"]:
            return False, "major_issues_increased"
        if after["critical"] < before["critical"]:
            return True, "reduced_critical_issues"
        if after["major"] < before["major"]:
            return True, "reduced_major_issues"
        if after["minor"] < before["minor"]:
            return True, "reduced_minor_issues"
        return False, "not_improved_enough"

    @staticmethod
    def _is_better_strategy_snapshot(candidate: Dict[str, int], incumbent: Optional[Dict[str, int]]) -> bool:
        if incumbent is None:
            return True
        candidate_key = (candidate["weighted"], candidate["critical"], candidate["major"], candidate["minor"], candidate["total"])
        incumbent_key = (incumbent["weighted"], incumbent["critical"], incumbent["major"], incumbent["minor"], incumbent["total"])
        return candidate_key < incumbent_key

    @staticmethod
    def _stagewide_safety_regression_reason(before: Optional[Dict[str, int]], after: Optional[Dict[str, int]]) -> Optional[str]:
        if before is None or after is None:
            return None
        if after.get("critical", 0) > before.get("critical", 0):
            return "safety_critical_issues_increased"
        if after.get("major", 0) > before.get("major", 0):
            return "safety_major_issues_increased"
        return None

    @classmethod
    def _classify_issue_family(cls, issue: Dict[str, Any]) -> str:
        haystack = " ".join(
            str(issue.get(key) or "")
            for key in ("problem", "suggestion", "example", "location")
        )
        families = {
            "duplicate_residue": ("重复", "双版本", "拼接", "回卷", "第一次", "再次", "并排保留", "复现", "反复"),
            "over_explained": ("解释", "总结", "作者感", "说破", "判断", "直给", "概括", "替读者总结", "点破"),
            "weak_reaction": ("体感", "身体反应", "情绪", "生理", "反应不够", "不够狠", "失忆", "记忆缺口", "怀疑不够"),
            "dialogue_drag": ("对话", "拉扯", "回合", "改口", "口吻", "说明书式", "问答", "话术"),
            "hook_pressure": ("钩子", "悬念", "章末", "追更", "压力", "临门一脚", "行动意志"),
            "pacing_drag": ("拖沓", "节奏", "推进", "信息密度", "缓冲", "升级感", "边际效应", "中后段"),
            "logic_continuity": ("逻辑", "因果", "承接", "时间线", "前后不一致", "连续性", "自洽", "链路"),
            "pov_boundary": ("视角", "全知", "越界", "信息边界"),
        }
        for family, markers in families.items():
            if any(marker in haystack for marker in markers):
                return family
        return "generic"

    @classmethod
    def _issue_similarity_ratio(cls, left: str, right: str) -> float:
        if not left or not right:
            return 0.0
        if left == right:
            return 1.0
        width = 2
        left_grams = {left[idx: idx + width] for idx in range(max(len(left) - width + 1, 1))}
        right_grams = {right[idx: idx + width] for idx in range(max(len(right) - width + 1, 1))}
        if not left_grams or not right_grams:
            return 0.0
        return len(left_grams & right_grams) / max(1, min(len(left_grams), len(right_grams)))

    @classmethod
    def _should_merge_issues(cls, existing: Dict[str, Any], candidate: Dict[str, Any]) -> bool:
        existing_location = cls._normalize_issue_text(existing.get("location"))
        candidate_location = cls._normalize_issue_text(candidate.get("location"))
        same_location = bool(existing_location and candidate_location) and (
            existing_location == candidate_location
            or existing_location in candidate_location
            or candidate_location in existing_location
        )
        existing_problem = cls._normalize_issue_text(existing.get("problem"))
        candidate_problem = cls._normalize_issue_text(candidate.get("problem"))
        similarity = cls._issue_similarity_ratio(existing_problem, candidate_problem)
        existing_family = cls._classify_issue_family(existing)
        candidate_family = cls._classify_issue_family(candidate)
        if same_location and existing_family == candidate_family and existing_family != "generic":
            return True
        if same_location and similarity >= 0.55:
            return True
        if (
            existing_family == candidate_family
            and existing_family != "generic"
            and similarity >= 0.72
            and (not existing_location or not candidate_location)
        ):
            return True
        return False

    def _deduplicate_issues(self, issues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        deduped: List[Dict[str, Any]] = []
        severity_rank = {"critical": 3, "major": 2, "minor": 1}
        for raw_issue in issues:
            issue = dict(raw_issue)
            issue.setdefault("merged_dimensions", [issue.get("dimension")])
            issue.setdefault("merged_stages", [issue.get("_critique_stage")])
            issue.setdefault("merged_issue_count", 1)
            merged = False
            for current in deduped:
                if not self._should_merge_issues(current, issue):
                    continue
                current_dims = {str(item) for item in current.get("merged_dimensions") or [] if str(item or "").strip()}
                current_dims.add(str(issue.get("dimension") or "").strip())
                current["merged_dimensions"] = sorted(current_dims)
                current_stages = {str(item) for item in current.get("merged_stages") or [] if str(item or "").strip()}
                current_stages.add(str(issue.get("_critique_stage") or "").strip())
                current["merged_stages"] = sorted(current_stages)
                current["merged_issue_count"] = int(current.get("merged_issue_count") or 1) + 1
                if severity_rank.get(str(issue.get("severity") or "minor"), 1) > severity_rank.get(str(current.get("severity") or "minor"), 1):
                    current["severity"] = issue.get("severity")
                if self._issue_priority_score(issue) > self._issue_priority_score(current):
                    current.update({
                        "dimension": issue.get("dimension"),
                        "location": issue.get("location"),
                        "problem": issue.get("problem"),
                        "suggestion": issue.get("suggestion"),
                        "example": issue.get("example"),
                    })
                merged = True
                break
            if not merged:
                deduped.append(issue)
        return deduped

    def _limit_stage_issues(self, issues: List[Dict[str, Any]], *, limit: int = 3) -> List[Dict[str, Any]]:
        deduped = self._deduplicate_issues(issues)
        ranked = sorted(deduped, key=self._issue_priority_score, reverse=True)
        picked: List[Dict[str, Any]] = []
        seen_families: Dict[str, int] = {}
        seen_locations: set[str] = set()
        for issue in ranked:
            family = self._classify_issue_family(issue)
            location = self._normalize_issue_text(issue.get("location"))
            if family != "generic" and seen_families.get(family, 0) >= 1 and len(picked) >= 2:
                continue
            if location and location in seen_locations:
                continue
            picked.append(issue)
            if family != "generic":
                seen_families[family] = seen_families.get(family, 0) + 1
            if location:
                seen_locations.add(location)
            if len(picked) >= limit:
                break
        if not picked:
            return ranked[:limit]
        return picked

    async def critique_dimension_batch(
        self,
        chapter_content: str,
        stage_name: str,
        dimensions: List[CritiqueDimension],
        context: Optional[Dict[str, Any]] = None,
        user_id: int = 0,
        focus_issues: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        if not dimensions:
            return {"stage": stage_name, "dimensions": [], "overall_score": 70, "issues": [], "strengths": [], "summary": "无可审查维度", "weight": 0.0}

        context_str = self._build_context_str(context, stage_name=stage_name)
        dimension_specs: List[str] = []
        total_weight = 0.0
        default_dimension = dimensions[0]
        for dimension in dimensions:
            dim_config = self.CRITIQUE_PROMPTS[dimension]
            focus_points = "\n".join(f"  - {item}" for item in dim_config["focus"])
            dimension_specs.append(f"[{dimension.value} | {dim_config['name']}]\n{focus_points}")
            total_weight += float(dim_config["severity_weight"])

        profile = self._resolve_context_limit_profile(stage_name)
        dimension_lines = ", ".join(dimension.value for dimension in dimensions)
        previous_bundle_limit = {"structural": 3200, "character": 1800, "delivery": 1200}.get(profile, 3200)
        excerpt_limits = {
            "structural": (5600, 4500),
            "character": (4200, 3400),
            "delivery": (3600, 3000),
        }
        focus_limit, aggregate_limit = excerpt_limits.get(profile, (5600, 4500))
        previous_chapter_bundle = self._truncate_text((context or {}).get("previous_chapter_bundle"), previous_bundle_limit)
        chapter_excerpt = self._truncate_text(chapter_content, focus_limit if focus_issues else aggregate_limit)
        focus_text = self._build_issues_text(focus_issues or [], limit=min(len(focus_issues or []), 6))
        if focus_issues:
            prompt = f"""你是一位严格的长篇连载小说编辑，现在需要对以下章节执行“{stage_name}”阶段的定向复核。
[本阶段维度]
{chr(10).join(dimension_specs)}

{context_str}

[前一章依据包]
{previous_chapter_bundle or '暂无（这可能是第一章）'}

[待验证的原始问题]
{focus_text}

[修订后本章正文]
{chapter_excerpt}

请只验证上面列出的原始问题是否仍然成立，要求：
1. 只围绕这些原始问题做复核，不要新增无关的新问题，不要泛化重报。
2. 若原问题已经被解决，就不要再输出对应 issue。
3. 只有当原问题仍然存在、恶化，或只是部分缓解但依然影响阅读时，才保留 issue。
4. 每条保留 issue 必须带上 dimension 字段，且只能填写以下值之一：{dimension_lines}
5. 同一根因不要拆成多条；本阶段 issues 最多输出 3 条。
6. strengths 和 summary 只总结这些原始问题的修复情况。
7. overall_score 必须使用 0-100 分制整数或小数，不要使用 1-10 分制。
请以 JSON 输出：
{{
  "stage": "{stage_name}",
  "dimensions": {json.dumps([dimension.value for dimension in dimensions], ensure_ascii=False)},
  "overall_score": 75,
  "issues": [
    {{
      "dimension": "{default_dimension.value}",
      "severity": "critical/major/minor",
      "location": "仍未修好的位置（引用原文片段或说明段落位置）",
      "problem": "为什么该原问题仍然存在或只被部分修复",
      "suggestion": "继续修这个原问题的具体建议",
      "example": "修改示例（如适用）"
    }}
  ],
  "strengths": ["哪些原问题已被修好或明显缓解"],
  "summary": "一句话总结原问题的修复结果"
}}"""
        else:
            prompt = f"""你是一位严格的长篇连载小说编辑，现在需要对以下章节执行“{stage_name}”阶段的聚合审查。
[本阶段维度]
{chr(10).join(dimension_specs)}

{context_str}

[前一章依据包]
{previous_chapter_bundle or '暂无（这可能是第一章）'}

[本章正文]
{chapter_excerpt}

请一次性输出本阶段的聚合诊断结果，要求：
1. 只指出真正影响连载阅读体验的问题，少而准。
2. 每条 issue 必须带上 dimension 字段，且只能填写以下值之一：{dimension_lines}
3. 优先保留 critical / major 问题；如果没有明显问题，可以减少 issues 数量。
4. 同一根因如果同时影响多个维度，只保留一个最核心的问题，不要换不同维度重复上报同一症状。
5. 本阶段 issues 最多输出 3 条；只有在确实存在彼此独立、不可合并的问题时才允许写满 3 条。
6. strengths 和 summary 也要基于本阶段整体表现给出。
7. overall_score 必须使用 0-100 分制整数或小数，不要使用 1-10 分制。
请以 JSON 输出：
{{
  "stage": "{stage_name}",
  "dimensions": {json.dumps([dimension.value for dimension in dimensions], ensure_ascii=False)},
  "overall_score": 75,
  "issues": [
    {{
      "dimension": "{default_dimension.value}",
      "severity": "critical/major/minor",
      "location": "问题所在位置（引用原文片段或说明段落位置）",
      "problem": "问题描述",
      "suggestion": "具体修改建议",
      "example": "修改示例（如适用）"
    }}
  ],
  "strengths": ["做得好的地方"],
  "summary": "一句话总结"
}}"""
        try:
            json_result = await call_generation_json(
                llm_service=self.llm_service,
                system_prompt=f"你是一位专注于{stage_name}阶段审查的严格长篇小说编辑。请聚合输出问题，避免拆成多次独立诊断。",
                conversation_history=[{"role": "user", "content": prompt}],
                temperature=0.2,
                user_id=user_id,
                timeout=180.0,
                policy=GenerationCallPolicy(
                    stage_label=f"{stage_name} 聚合诊断",
                    progress_stage="diagnose_once",
                    retry_attempts=2,
                    response_format="json_object",
                    max_tokens=2600,
                    retry_same_model_once=True,
                    json_repair_attempts=1,
                ),
            )
            result = json_result.data
            if result:
                issues = []
                for issue in result.get("issues", []) or []:
                    if not isinstance(issue, dict):
                        continue
                    normalized_issue = dict(issue)
                    normalized_issue["dimension"] = self._normalize_dimension_value(issue.get("dimension"), dimensions, default_dimension)
                    issues.append(normalized_issue)
                issues = self._limit_stage_issues(issues, limit=3)
                result["stage"] = stage_name
                result["dimensions"] = [dimension.value for dimension in dimensions]
                result["issues"] = issues
                result["overall_score"] = self._normalize_overall_score(result.get("overall_score", 70))
                result["weight"] = total_weight
                return result
        except Exception as exc:
            logger.warning("评审批次 %s 执行失败：%s", stage_name, exc)
        return {
            "stage": stage_name,
            "dimensions": [dimension.value for dimension in dimensions],
            "overall_score": 70,
            "issues": [],
            "strengths": [],
            "summary": "无法完成审查",
            "weight": total_weight,
        }

    async def full_critique(
        self,
        chapter_content: str,
        dimensions: Optional[List[CritiqueDimension]] = None,
        context: Optional[Dict[str, Any]] = None,
        user_id: int = 0,
        progress_callback: Optional[Callable[[str, Dict[str, Any]], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        with LLMService.daily_limit_scope(f"self_critique_full:{user_id}:{len(chapter_content)}"):
            if dimensions is None:
                dimensions = list(CritiqueDimension)
            results = {
                "dimension_critiques": {},
                "all_issues": [],
                "weighted_score": 0.0,
                "critical_count": 0,
                "major_count": 0,
                "minor_count": 0,
                "needs_revision": False,
                "priority_fixes": [],
                "stage_summaries": [],
                "raw_issue_count": 0,
                "deduped_issue_count": 0,
                "merged_issue_count": 0,
            }
            total_weight = 0.0
            weighted_score_sum = 0.0
            stage_batches = self._build_dimension_batches(dimensions)
            critique_results: List[Dict[str, Any]] = []
            collected_issues: List[Dict[str, Any]] = []
            for batch_index, (stage_name, stage_dimensions) in enumerate(stage_batches, start=1):
                if progress_callback is not None:
                    await progress_callback(stage_name, {"batch_index": batch_index, "batch_count": len(stage_batches), "dimensions": [dimension.value for dimension in stage_dimensions]})
                critique_results.append(await self.critique_dimension_batch(chapter_content, stage_name, stage_dimensions, context=context, user_id=user_id))
            for critique in critique_results:
                stage_name = str(critique.get("stage") or "unknown")
                stage_dimensions = [str(item) for item in critique.get("dimensions", []) if str(item).strip()]
                raw_issue_count = 0
                for issue in critique.get("issues", []) or []:
                    if not isinstance(issue, dict):
                        continue
                    normalized_issue = dict(issue)
                    severity = str(normalized_issue.get("severity") or "minor").lower()
                    if severity == "warning":
                        severity = "major"
                    if severity not in {"critical", "major", "minor"}:
                        severity = "minor"
                    normalized_issue["severity"] = severity
                    normalized_issue["_critique_stage"] = stage_name
                    collected_issues.append(normalized_issue)
                    raw_issue_count += 1
                weight = float(critique.get("weight", 1.0))
                score = self._normalize_overall_score(critique.get("overall_score", 70))
                weighted_score_sum += score * weight
                total_weight += weight
                results["stage_summaries"].append({"stage": stage_name, "dimensions": stage_dimensions, "issue_count": raw_issue_count, "raw_issue_count": raw_issue_count, "weighted_score": round(score, 1), "summary": critique.get("summary")})
            rule_based_issues = self._build_rule_based_issues(chapter_content, context=context)
            if rule_based_issues:
                collected_issues.extend(rule_based_issues)
                heuristic_dimensions = sorted(
                    {
                        str(issue.get("dimension") or "").strip()
                        for issue in rule_based_issues
                        if str(issue.get("dimension") or "").strip()
                    }
                )
                results["stage_summaries"].append({
                    "stage": "heuristic_guard",
                    "dimensions": heuristic_dimensions,
                    "issue_count": len(rule_based_issues),
                    "raw_issue_count": len(rule_based_issues),
                    "weighted_score": None,
                    "summary": "规则化检测命中了重复推进或跨章回卷风险。",
                })
            deduped_issues = self._deduplicate_issues(collected_issues)
            results["all_issues"] = deduped_issues
            results["raw_issue_count"] = len(collected_issues)
            results["deduped_issue_count"] = len(deduped_issues)
            results["merged_issue_count"] = max(0, results["raw_issue_count"] - results["deduped_issue_count"])
            for issue in deduped_issues:
                severity = str(issue.get("severity") or "minor")
                if severity == "critical":
                    results["critical_count"] += 1
                elif severity == "major":
                    results["major_count"] += 1
                else:
                    results["minor_count"] += 1
            stage_issue_counts: Dict[str, int] = {}
            for issue in deduped_issues:
                for stage_name in issue.get("merged_stages") or [issue.get("_critique_stage")]:
                    if not stage_name:
                        continue
                    stage_issue_counts[str(stage_name)] = stage_issue_counts.get(str(stage_name), 0) + 1
            for summary in results["stage_summaries"]:
                stage_name = str(summary.get("stage") or "")
                raw_issue_count = int(summary.get("raw_issue_count") or summary.get("issue_count") or 0)
                deduped_issue_count = stage_issue_counts.get(stage_name, raw_issue_count)
                summary["raw_issue_count"] = raw_issue_count
                summary["issue_count"] = deduped_issue_count
                summary["merged_issue_count"] = max(0, raw_issue_count - deduped_issue_count)
            for critique in critique_results:
                stage_name = str(critique.get("stage") or "unknown")
                stage_dimensions = [str(item) for item in critique.get("dimensions", []) if str(item).strip()]
                score = self._normalize_overall_score(critique.get("overall_score", 70))
                for dimension_value in stage_dimensions:
                    results["dimension_critiques"][dimension_value] = {
                        "stage": stage_name,
                        "dimension": dimension_value,
                        "overall_score": round(score, 1),
                        "issues": [issue for issue in deduped_issues if dimension_value in (issue.get("merged_dimensions") or [issue.get("dimension")])],
                        "strengths": critique.get("strengths", []),
                        "summary": critique.get("summary", ""),
                        "weight": float(critique.get("weight", 1.0)),
                    }
            if total_weight > 0:
                results["weighted_score"] = round(weighted_score_sum / total_weight, 1)
            has_hard_major_guard = any(
                str(issue.get("severity") or "").lower() == "major"
                and self._classify_issue_family(issue) == "duplicate_residue"
                for issue in deduped_issues
            )
            results["needs_revision"] = (
                results["critical_count"] > 0
                or results["major_count"] >= 2
                or results["weighted_score"] < 78
                or has_hard_major_guard
            )
            priority_issues = [issue for issue in deduped_issues if issue.get("severity") in ["critical", "major"]]
            priority_issues.sort(key=self._issue_priority_score, reverse=True)
            results["priority_fixes"] = priority_issues[:8]
            return results

    def _build_issues_text(self, issues: List[Dict[str, Any]], *, limit: int = 12) -> str:
        blocks = []
        for index, issue in enumerate(issues[:limit], start=1):
            blocks.append("\n".join([
                f"问题 {index}：",
                f"- 维度：{issue.get('dimension', 'unknown')}",
                f"- 严重程度：{issue.get('severity', 'minor')}",
                f"- 位置：{issue.get('location', '未定位')}",
                f"- 问题：{issue.get('problem', '')}",
                f"- 建议：{issue.get('suggestion', '')}",
                f"- 示例：{issue.get('example', '无')}",
            ]))
        return "\n\n".join(blocks)

    @staticmethod
    def _issue_priority_score(issue: Dict[str, Any]) -> int:
        severity_score = {"critical": 300, "major": 200, "minor": 100}.get(str(issue.get("severity") or "minor"), 100)
        dimension_score = {
            "logic": 45, "continuity": 40, "pov": 38, "character": 35, "relationship": 32,
            "emotion": 30, "dialogue": 28, "pacing": 26, "scene": 24, "suspense": 22, "writing": 20,
        }.get(str(issue.get("dimension") or ""), 10)
        location_bonus = 8 if str(issue.get("location") or "").strip() and str(issue.get("location")) != "未定位" else 0
        return severity_score + dimension_score + location_bonus

    def _prioritize_stage_issues(self, stage_issues: List[Dict[str, Any]], stage_dimensions: List[str], *, limit: int = 6) -> List[Dict[str, Any]]:
        ranked = sorted(stage_issues, key=self._issue_priority_score, reverse=True)
        picked: List[Dict[str, Any]] = []
        covered_dimensions = set()
        for issue in ranked:
            dimension = str(issue.get("dimension") or "")
            if dimension in stage_dimensions and dimension not in covered_dimensions:
                picked.append(issue)
                covered_dimensions.add(dimension)
            if len(picked) >= limit:
                break
        for issue in ranked:
            if len(picked) >= limit:
                break
            if issue not in picked:
                picked.append(issue)
        return picked

    def _stage_issue_pressure_score(self, stage_issues: List[Dict[str, Any]]) -> int:
        counts = self._summarize_issue_counts(stage_issues)
        score = counts["critical"] * 1000 + counts["major"] * 100 + counts["minor"] * 10
        for issue in stage_issues[:8]:
            strategy_key = self._resolve_revision_strategy(str(issue.get("dimension") or "").strip().lower())
            if self._issue_requires_stagewide_rewrite(issue, strategy_key=strategy_key):
                score += 35
            if self._issue_indicates_structure_residue(issue):
                score += 45
        return score

    def _order_stage_groups(
        self,
        grouped_issues: List[Tuple[str, List[Dict[str, Any]], List[str]]],
        *,
        preferred_stage_names: Optional[List[str]] = None,
    ) -> List[Tuple[str, List[Dict[str, Any]], List[str]]]:
        preferred_stage_names = [str(name) for name in (preferred_stage_names or []) if str(name).strip()]
        preferred_order = {name: index for index, name in enumerate(preferred_stage_names)}
        default_order = {"structural": 0, "character": 1, "delivery": 2}
        return sorted(
            grouped_issues,
            key=lambda item: (
                preferred_order.get(item[0], len(preferred_order)),
                -self._stage_issue_pressure_score(item[1]),
                default_order.get(item[0], len(default_order)),
            ),
        )

    def _should_attempt_stagewide_rewrite(
        self,
        *,
        before_counts: Dict[str, int],
        strategy_issues: List[Dict[str, Any]],
        best_content_changed: bool,
    ) -> bool:
        if int(before_counts.get("critical") or 0) > 0:
            return True
        if any(self._issue_indicates_structure_residue(issue) for issue in strategy_issues):
            return True
        # Major-only feedback should be handled by local windows. If the local pass
        # cannot produce a safe change, keep the original content instead of
        # escalating to a continuity-risky whole-chapter candidate.
        return False

    def _split_paragraphs(self, chapter_content: str) -> List[str]:
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", chapter_content) if part.strip()]
        return paragraphs or [chapter_content]

    def _match_issue_to_paragraph_indexes(self, paragraphs: List[str], issue: Dict[str, Any]) -> List[int]:
        location = str(issue.get("location") or "").strip()
        problem = str(issue.get("problem") or "").strip()
        suggestion = str(issue.get("suggestion") or "").strip()
        example = str(issue.get("example") or "").strip()
        dimension = str(issue.get("dimension") or "").strip().lower()
        indexes: List[int] = []
        if location and location != "未定位":
            indexes.extend(self._extract_paragraph_indexes_from_location(location, total=len(paragraphs)))
            if indexes:
                return indexes[:4]
            normalized_location = location.replace("“", "").replace("”", "").replace("...", "").strip()
            for idx, paragraph in enumerate(paragraphs):
                if normalized_location and normalized_location in paragraph:
                    indexes.append(idx)
        if indexes:
            return indexes[:3]

        snippet_sources = [example, problem, suggestion]
        snippet_candidates: List[str] = []
        for source in snippet_sources:
            if not source:
                continue
            normalized_source = source.replace("“", "").replace("”", "").replace("...", " ")
            direct = normalized_source.strip()
            if len(direct) >= 8 and direct not in snippet_candidates:
                snippet_candidates.append(direct)
            for piece in re.split(r"[，。；：、,.!?！？\n\r]+", normalized_source):
                cleaned = piece.strip(" \t\"'‘’“”()（）[]【】")
                if len(cleaned) >= 8 and cleaned not in snippet_candidates:
                    snippet_candidates.append(cleaned)
        for snippet in snippet_candidates[:8]:
            for idx, paragraph in enumerate(paragraphs):
                if snippet in paragraph and idx not in indexes:
                    indexes.append(idx)
            if indexes:
                break
        if indexes:
            return indexes[:4]

        haystack = f"{problem} {suggestion} {example}".lower()
        for keyword in self.LOCAL_REWRITE_DIMENSION_HINTS.get(dimension, []):
            if keyword.lower() not in haystack:
                continue
            for idx, paragraph in enumerate(paragraphs):
                if keyword in paragraph and idx not in indexes:
                    indexes.append(idx)
            if indexes:
                break
        if indexes:
            return indexes[:3]
        if dimension == "continuity":
            return [0] if paragraphs else []
        if dimension in {"suspense", "pacing"}:
            return [max(len(paragraphs) - 1, 0)] if paragraphs else []
        if dimension in {"dialogue", "emotion", "character", "relationship", "scene", "writing", "logic", "pov"}:
            return [max(len(paragraphs) // 2, 0)] if paragraphs else []
        return [0] if paragraphs else []

    def _expand_rewrite_window(self, indexes: List[int], total: int, *, radius: int = 1) -> List[int]:
        expanded = set()
        for index in indexes:
            start = max(0, index - radius)
            end = min(total - 1, index + radius)
            expanded.update(range(start, end + 1))
        return sorted(expanded)

    @staticmethod
    def _issue_indicates_structure_residue(issue: Dict[str, Any]) -> bool:
        # 这里只看诊断结论本身，不看 suggestion/example。
        # 否则像“删掉重复铺陈”这类正常表达优化建议，也会被误判成
        # 双版本残留，从而触发高成本的整章重写。
        haystack = " ".join(
            str(issue.get(key) or "")
            for key in ("location", "problem")
        )
        hard_residue_markers = (
            "双版本", "拼接", "回卷", "时间线", "认知重置", "来源不一致",
            "重复发现", "重复开场", "多次呈现为第一次", "前后不一致",
        )
        if any(marker in haystack for marker in hard_residue_markers):
            return True
        repeat_markers = ("重复", "再次", "重新", "首次", "第一次", "两次")
        structural_markers = ("时间", "事件", "发现", "认知", "开场", "版本", "进入", "抵达")
        return any(marker in haystack for marker in repeat_markers) and any(
            marker in haystack for marker in structural_markers
        )

    def _resolve_window_indexes(
        self,
        *,
        strategy_key: str,
        target_indexes: List[int],
        total: int,
        radius: int,
        issues: List[Dict[str, Any]],
    ) -> Tuple[List[int], str]:
        if not target_indexes:
            return [], "none"
        if strategy_key == "structure_guardrail":
            span = max(target_indexes) - min(target_indexes)
            force_contiguous = span >= 3 or any(self._issue_indicates_structure_residue(issue) for issue in issues)
            if force_contiguous:
                start = max(0, min(target_indexes) - 1)
                end = min(total - 1, max(target_indexes) + 1)
                return list(range(start, end + 1)), "contiguous_span"
        return self._expand_rewrite_window(target_indexes, total, radius=radius), "expanded_window"

    @classmethod
    def _build_residue_hints(cls, issues: List[Dict[str, Any]], *, limit: int = 4) -> List[str]:
        hints: List[str] = []
        for issue in issues:
            if not cls._issue_indicates_structure_residue(issue):
                continue
            problem = str(issue.get("problem") or "").strip()
            location = str(issue.get("location") or "").strip()
            summary = problem or location
            if summary and summary not in hints:
                hints.append(summary)
            if len(hints) >= limit:
                break
        return hints

    @staticmethod
    def _issue_requires_stagewide_rewrite(issue: Dict[str, Any], *, strategy_key: str = "delivery_polish") -> bool:
        location = str(issue.get("location") or "").strip()
        problem = str(issue.get("problem") or "").strip()
        haystack = f"{location}\n{problem}"
        broad_markers = (
            "全章", "整体", "整章", "一整段", "这一整段", "整个调查过程", "主调查过程",
            "以及章末", "章末", "通话段", "对话段", "全章整体", "从“", "到“", "从\"", "到\"",
        )
        if any(marker in haystack for marker in broad_markers):
            return True
        if strategy_key in {"structure_guardrail", "character_dynamics"} and "以及" in location:
            return True
        return False

    @classmethod
    def _should_skip_stagewide_rewrite(
        cls,
        chapter_content: str,
        issues: List[Dict[str, Any]],
        before_counts: Dict[str, int],
        *,
        strategy_key: str = "delivery_polish",
    ) -> bool:
        if strategy_key != "delivery_polish":
            return False
        if any(cls._issue_indicates_structure_residue(issue) for issue in issues):
            return False
        if any(cls._issue_requires_stagewide_rewrite(issue, strategy_key=strategy_key) for issue in issues):
            return False
        normalized = (chapter_content or "").strip()
        if len(normalized) < 3500:
            return False
        return int(before_counts.get("critical") or 0) == 0 and int(before_counts.get("major") or 0) <= 2

    def _build_issue_execution_requirements(
        self,
        issues: List[Dict[str, Any]],
        *,
        strategy_key: str = "delivery_polish",
        limit: int = 4,
    ) -> List[str]:
        if not issues:
            return []
        requirements: List[str] = []
        problem_haystack = "\n".join(str(issue.get("problem") or "") for issue in issues)
        location_haystack = "\n".join(str(issue.get("location") or "") for issue in issues)
        example_lines = [
            self._truncate_text(str(issue.get("example") or "").strip(), 120)
            for issue in issues
            if str(issue.get("example") or "").strip()
        ]
        suggestion_lines = [
            self._truncate_text(str(issue.get("suggestion") or "").strip(), 120)
            for issue in issues
            if str(issue.get("suggestion") or "").strip()
        ]

        if strategy_key == "structure_guardrail":
            requirements.append("必须把结构问题落实成正文里的可观察规则、前因后果或信息边界修正，不能只换措辞。")
            if any(token in (problem_haystack + location_haystack) for token in ("公共记忆被删改", "记忆被删改", "记忆也被改写", "人的记忆也被改写", "公共记忆", "中间踏板", "摘要目标与正文中段")):
                requirements.append("若问题指向“公共记忆被删改”命题跳级，必须先补一个客观证据踏板：让同一条目/称呼/借阅事实先被主角客观捕获，再在短时间内发生消失、改口或错认；若做不到，只能先把判断收束在“流程/档案被改写”，不要直接上升到公共记忆层。")
            if any(token in problem_haystack for token in ("规则", "边界", "记忆", "抹除", "触发条件")):
                requirements.append("若问题指向异常规则模糊，必须补一条“当前可观察规则”，但不要一次讲透全部真相。")
            if any(token in problem_haystack for token in ("触得到", "手背", "物理书写", "口头复述", "离开视线", "临时变动")):
                requirements.append("若问题指向规则像临时变动，必须补一次对照验证：同一信息至少用两种媒介/动作测试，并明确哪一种暂时有效。")
            if any(token in problem_haystack for token in ("正常修复损耗", "技术操作误伤", "拓印后果", "常规水损", "独立于他的操作发生")):
                requirements.append("若问题指向异常抹除与正常修复损耗混淆，必须补一个专业对照判断：说明当前湿度/手法不足以造成这种退墨，或让未接触区域同步消退，明确异常独立于主角操作发生。")
            if any(token in (problem_haystack + location_haystack) for token in ("对象边界", "原件/残页/同批卷宗", "物件追踪", "外借清单", "整批都被借走", "被借走的是同批中的哪些件")):
                requirements.append("若问题指向物件流转边界不清，必须用一句流程化说明交代主卷、散页、外借清单之间的关系，明确哪些件被调走、哪些件仍留在修复台。")
            if any(token in problem_haystack for token in ("离线照片", "便签", "物证袋", "分散备份", "拆写", "一锅端")):
                requirements.append("若问题指向证据保全不够专业，主角必须先测试哪类载体还能留住信息，再把名字、编号、物证分散保存，不能只做单线备份。")
            if any(token in problem_haystack for token in ("多种异常机制", "并列出现", "世界规则", "主观联想", "任何事都可能异常")):
                requirements.append("若问题指向异常机制并列失焦，必须收束为一条当前可验证的主异常链，其他异常只保留为术语、传闻或边缘暗示。")
            if any(token in problem_haystack for token in ("提前预判", "跳得过远", "剧透式铺垫", "高度具体的社交预警", "凭空知道")):
                requirements.append("若问题指向预警过于精准，必须把提示降级成低确定性警告，或先补一个可追溯的信息来源，避免替章末钩子剧透。")
            if any(token in problem_haystack for token in ("工具化", "退场", "被移出场", "自保冲动", "为什么会退")):
                requirements.append("若问题指向配角退场像作者调度，必须补一个当场失控/恐慌/生理反应，让他主动退场，而不是只听主角安排。")
            if any(token in (problem_haystack + location_haystack) for token in ("因果链", "追来", "锁定", "同步", "外泄", "监控", "精准报出")):
                requirements.append("若问题指向“对方为何能追来/知道得过于精准”，必须在前文补出可见的同步、转发、监控或检索痕迹。")
            if any(token in problem_haystack for token in ("没有真正落地", "准备做事", "兑现", "钩子偏软", "压力不够实锤")):
                requirements.append("若问题指向章末兑现不足，最后一个关键动作必须真正做完并产出结果/反咬，不能停在准备执行或回忆解释。")
            if any(token in problem_haystack for token in ("解释略偏满", "讲透", "说透", "总结", "留白")):
                requirements.append("若问题指向解释过满，必须删掉一层结论性说明，让规则只被确认一半。")
        elif strategy_key == "character_dynamics":
            requirements.append("必须补一个能刺中角色本人的触发、身体反应或旧伤回声，让行动动机从职业负责升级为私人被击中。")
            requirements.append("必须把至少一段功能性对话改成试探、诱导、识破或反制回合，而不是只传递信息。")
            if any(token in (problem_haystack + location_haystack) for token in ("体制外备份", "上报后原件大概率再也看不到", "制度经验", "先例支撑", "职业判断推动", "非这么做不可", "个人伤口", "黑潮失忆", "记录被删改", "先藏证据", "先上报", "补报")):
                requirements.append("若问题指向主角越线依据仍偏弱，必须补一记制度先例或失败经验，让“上交流程=证据离开视野/再次被抹平”的判断有来历；同时给出一个极短身体反应或旧伤回声，把违规留证钉成‘非这么做不可’。")
            if any(token in problem_haystack for token in ("转折", "临界点", "越线", "不肯放手", "按流程的人")):
                requirements.append("若问题指向人物转身不够锋利，必须补一个“差点服从—被刺回去—主动越线”的即时动作节点。")
            if any(token in problem_haystack for token in ("流程主义者", "先藏证据", "身体记忆", "职业代价", "签过字的修复记录", "被改成了另一版")):
                requirements.append("若问题指向主角越线仍偏功能性，必须补一个具体职业伤口回弹：最好落到被篡改的签字记录、工序记录或亲手补报失效的身体记忆上，让越线决定像旧伤复发。")
            if any(token in problem_haystack for token in ("制度", "抽象", "匿名声音", "记不住", "人际特征", "关系对手")):
                requirements.append("若问题指向对手过于抽象，必须给施压方补一个可复现的人际锚点：固定措辞、停顿习惯、越界称呼或权限痕迹。")
            if any(token in problem_haystack for token in ("熟人", "同事", "默契", "称呼", "关系断裂", "工具人")):
                requirements.append("若问题指向熟人关系过薄，必须在异常爆发前补一笔工作默契、互怼习惯或固定称呼，让后续失忆直接撕裂这层熟悉感。")
            if any(token in problem_haystack for token in ("关系", "张力", "博弈", "功能性对峙", "改口")):
                requirements.append("若问题指向关系张力不足，至少补一记带判断或拿捏意味的压迫台词。")
            if any(token in (problem_haystack + location_haystack) for token in ("自保动机", "个人代价", "害怕担责", "害怕被追责", "害怕自己也被改写", "立场", "工具人")):
                requirements.append("若问题指向对手仍像工具人，必须补一个可感知的自保代价：担责记录、被调离、记忆松动后果或权限追责，让他的回避不是抽象改口，而是具体避祸。")
            if any(token in problem_haystack for token in ("功能过于接近", "具体人际拉扯", "制度代言人", "明知却不敢说", "关系功能")):
                requirements.append("若问题指向对手位功能重叠，必须把一人写成制度代言人、另一人写成有裂缝的具体熟人/同事，让压迫与回避分层，不要只给统一口径。")
        else:
            requirements.append("必须压缩至少一处重复验证、解释性复述或节奏回踩，让信息推进更陡。")
            requirements.append("必须把章末压力保留在动作、威胁或未完成决断上，不要用说明句收口。")
            if any(token in (problem_haystack + location_haystack) for token in ("先封袋", "上报档案司", "不合规", "流程争执", "同一压力反复确认")):
                requirements.append("若问题指向流程争执横向重复，必须把“封袋/上报/不合规”这类程序口径合并成一次有效施压；之后每一轮都必须带出新信息、新阻碍或新结果。")
            if any(token in (problem_haystack + location_haystack) for token in ("连续检索", "验证步骤", "同质信息", "平行例证", "回踩", "程序性展示")):
                requirements.append("若问题指向检索/比对步骤过多，必须把平行验证压成 2-3 个最有杀伤力的证据，并并入动作反应。")
            if any(token in (problem_haystack + location_haystack) for token in ("同型冲突", "回合数偏多", "平台期", "重复追问", "同一堵墙前反复试探")):
                requirements.append("若问题指向中段同型冲突重复，必须删并或压缩至少一轮追问回合，让每次交锋只对应一个升级结果：查无此人 / 卷宗外借 / 决定藏证。")
            if any(token in (problem_haystack + location_haystack) for token in ("内心归纳", "回忆", "重复论证", "解释为什么", "停下来解释")):
                requirements.append("若问题指向中后段说明过多，必须把重复归纳压成 1 次最短触发，并立刻推进到下一个动作决定。")
            if any(token in (problem_haystack + location_haystack) for token in ("黑潮", "背景回忆", "回溯", "求助单", "历史阴影")):
                requirements.append("若问题指向高压节点插入背景回忆，历史信息只能保留为一记最短创伤闪回，不能展开成整段补设定。")
            if any(token in (problem_haystack + location_haystack) for token in ("动作场景", "覆拓", "耗材", "老话", "说明性内容", "高潮前")):
                requirements.append("若问题指向高潮前动作被说明挤压，器具/设定信息只能嵌在动作里一闪带出，不能停下来单独讲解。")
            if any(token in (problem_haystack + location_haystack) for token in ("门外人", "门锁", "通道", "物理局势", "即时选择", "门把手")):
                requirements.append("若问题指向章末危险只停留在语言试探，必须补一个可见物理障碍或倒计时选择，让主角立刻在开门/撤离/藏证之间取舍。")
            if any(token in (problem_haystack + location_haystack) for token in ("借阅记录", "06:40", "门外忽然传来钥匙碰撞的轻响", "门外声响", "双尾声", "近身威胁", "有人更早注意到附纸")):
                requirements.append("若问题指向章末尾声叠压，必须明确“成果钩子”和“逼近钩子”二选一：要么保留借阅/签名反咬，要么保留门外逼近，另一项只能前置成余波，不得连续加码成双尾声。")
            if any(token in (problem_haystack + location_haystack) for token in ("章末", "主钩子", "分流", "乱码", "异动", "重心", "新异常类别")):
                requirements.append("若问题指向章末钩子分流，章末只能保留一个主钩子；次级异动要前置成预警或直接删除。")

        for line in suggestion_lines[:2]:
            if line and line not in requirements:
                requirements.append(f"优先落地：{line}")
        for line in example_lines[:2]:
            if line and f"可直接改成类似：{line}" not in requirements:
                requirements.append(f"可直接改成类似：{line}")
        return requirements[:limit]

    def _resolve_revision_strategy(self, dimension: str) -> str:
        for strategy_key, config in self.REVISION_STRATEGIES.items():
            if dimension in config["dimensions"]:
                return strategy_key
        return "delivery_polish"

    def _cluster_issues_by_strategy(self, issues: List[Dict[str, Any]]) -> List[Tuple[str, List[Dict[str, Any]]]]:
        buckets: Dict[str, List[Dict[str, Any]]] = {}
        for issue in issues:
            strategy_key = self._resolve_revision_strategy(str(issue.get("dimension") or "").strip().lower())
            buckets.setdefault(strategy_key, []).append(issue)
        ordered_clusters: List[Tuple[str, List[Dict[str, Any]]]] = []
        for strategy_key in ["structure_guardrail", "character_dynamics", "delivery_polish"]:
            strategy_issues = buckets.get(strategy_key) or []
            if strategy_issues:
                ordered_clusters.append((strategy_key, sorted(strategy_issues, key=self._issue_priority_score, reverse=True)))
        return ordered_clusters

    def _strategy_dimensions(self, strategy_key: str) -> List[str]:
        strategy = self.REVISION_STRATEGIES.get(strategy_key, self.REVISION_STRATEGIES["delivery_polish"])
        return [str(item) for item in strategy.get("dimensions", [])]

    def _strategy_dimension_enums(self, strategy_key: str) -> List[CritiqueDimension]:
        enums: List[CritiqueDimension] = []
        for value in self._strategy_dimensions(strategy_key):
            enum_value = self.DIMENSION_ENUM_MAP.get(value)
            if enum_value is not None:
                enums.append(enum_value)
        return enums

    async def _critique_strategy_report(
        self,
        chapter_content: str,
        *,
        strategy_key: str,
        context: Optional[Dict[str, Any]] = None,
        user_id: int = 0,
        focus_issues: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        dimensions = self._strategy_dimension_enums(strategy_key)
        if not dimensions:
            return {
                "stage": f"verify_{strategy_key}",
                "dimensions": [],
                "overall_score": 100,
                "issues": [],
                "strengths": [],
                "summary": "无可审查维度",
            }
        return await self.critique_dimension_batch(
            chapter_content,
            f"verify_{strategy_key}",
            dimensions,
            context=context,
            user_id=user_id,
            focus_issues=focus_issues,
        )

    async def _critique_strategy_snapshot(
        self,
        chapter_content: str,
        *,
        strategy_key: str,
        context: Optional[Dict[str, Any]] = None,
        user_id: int = 0,
        focus_issues: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, int]:
        critique = await self._critique_strategy_report(
            chapter_content,
            strategy_key=strategy_key,
            context=context,
            user_id=user_id,
            focus_issues=focus_issues,
        )
        return self._summarize_issue_counts(critique.get("issues", []))

    async def _critique_stagewide_safety_snapshot(
        self,
        chapter_content: str,
        *,
        context: Optional[Dict[str, Any]] = None,
        user_id: int = 0,
    ) -> Dict[str, int]:
        critique = await self.critique_dimension_batch(
            chapter_content,
            "verify_stagewide_safety",
            self.STAGEWIDE_SAFETY_DIMENSIONS,
            context=context,
            user_id=user_id,
        )
        return self._summarize_issue_counts(critique.get("issues", []))

    def _collect_external_local_issues(self, context: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not context:
            return []
        normalized: List[Dict[str, Any]] = []
        for item in context.get("consistency_issues") or []:
            if isinstance(item, dict):
                normalized.append({"dimension": item.get("dimension") or item.get("category") or "logic", "severity": item.get("severity") or "major", "location": item.get("location") or "未定位", "problem": item.get("problem") or item.get("description") or "发现一致性问题", "suggestion": item.get("suggestion") or item.get("suggested_fix") or "修正该处冲突并保持前后设定一致", "example": item.get("example") or "无"})
        for item in context.get("guardrail_issues") or []:
            if isinstance(item, dict):
                normalized.append({"dimension": item.get("dimension") or "pov", "severity": item.get("severity") or "major", "location": item.get("location") or item.get("context") or "未定位", "problem": item.get("problem") or item.get("description") or "发现护栏违规", "suggestion": item.get("suggestion") or "修正该处违规并保持 POV/登场协议稳定", "example": item.get("example") or "无"})
        for item in context.get("enhanced_review_issues") or []:
            if isinstance(item, dict):
                normalized.append({"dimension": item.get("dimension") or item.get("category") or "writing", "severity": item.get("severity") or "major", "location": item.get("location") or "未定位", "problem": item.get("problem") or item.get("description") or "发现增强评审问题", "suggestion": item.get("suggestion") or item.get("fix") or "按增强评审意见修正该段内容", "example": item.get("example") or "无"})
        return normalized

    def _build_local_rewrite_plan(self, chapter_content: str, issues: List[Dict[str, Any]], context: Optional[Dict[str, Any]] = None, *, strategy_key: str = "delivery_polish") -> Optional[Dict[str, Any]]:
        paragraphs = self._split_paragraphs(chapter_content)
        if len(paragraphs) < 3:
            return None
        strategy = self.REVISION_STRATEGIES.get(strategy_key, self.REVISION_STRATEGIES["delivery_polish"])
        strategy_dimensions = set(strategy["dimensions"])
        filtered_issues = [issue for issue in issues if str(issue.get("dimension") or "").strip().lower() in strategy_dimensions] or issues
        if any(self._issue_requires_stagewide_rewrite(issue, strategy_key=strategy_key) for issue in filtered_issues[:6]):
            return None
        target_indexes = set()
        localized_issues = []
        candidate_issues = [*filtered_issues[:8], *self._collect_external_local_issues(context)]
        for issue in candidate_issues[:12]:
            indexes = self._match_issue_to_paragraph_indexes(paragraphs, issue)
            if not indexes:
                continue
            localized_issues.append(issue)
            target_indexes.update(indexes)
        if not target_indexes:
            return None
        window_indexes, rewrite_mode = self._resolve_window_indexes(
            strategy_key=strategy_key,
            target_indexes=sorted(target_indexes),
            total=len(paragraphs),
            radius=int(strategy.get("window_radius", 1)),
            issues=localized_issues,
        )
        target_paragraphs = [paragraphs[idx] for idx in window_indexes]
        if not target_paragraphs:
            return None
        return {
            "all_paragraphs": paragraphs,
            "window_indexes": window_indexes,
            "untouched_indexes": [idx for idx in range(len(paragraphs)) if idx not in window_indexes],
            "target_paragraphs": target_paragraphs,
            "issues": localized_issues,
            "prev_anchor": paragraphs[window_indexes[0] - 1] if window_indexes[0] > 0 else "",
            "next_anchor": paragraphs[window_indexes[-1] + 1] if window_indexes[-1] + 1 < len(paragraphs) else "",
            "strategy_label": strategy["label"],
            "strategy_instruction": strategy["instruction"],
            "rewrite_mode": rewrite_mode,
            "residue_hints": self._build_residue_hints(localized_issues),
        }

    def _local_cohesion_failure_reason(self, plan: Dict[str, Any], localized_text: str) -> Optional[str]:
        localized = localized_text.strip()
        if not localized:
            return "empty_localized"
        target_paragraphs = plan.get("target_paragraphs", [])
        residue_cleanup_mode = bool(plan.get("residue_hints")) and str(plan.get("rewrite_mode") or "") == "contiguous_span"
        min_ratio = 0.12 if residue_cleanup_mode else 0.2
        min_len = max(24, int(sum(len(p) for p in target_paragraphs) * min_ratio))
        if len(localized) < min_len:
            return f"too_short:{len(localized)}<{min_len}"
        prev_anchor = str(plan.get("prev_anchor") or "").strip()
        next_anchor = str(plan.get("next_anchor") or "").strip()
        first_line = localized.splitlines()[0].strip() if localized.splitlines() else localized[:80]
        last_line = localized.splitlines()[-1].strip() if localized.splitlines() else localized[-80:]
        if prev_anchor and any(first_line.startswith(token) for token in ("与此同时", "另一边", "突然", "总之")):
            return "generic_transition_after_prev_anchor"
        normalized_localized = " ".join(localized.split())
        normalized_next_anchor = " ".join(next_anchor.split())
        if next_anchor and normalized_next_anchor:
            next_anchor_prefix = normalized_next_anchor[:24]
            if normalized_localized.endswith(normalized_next_anchor) or (
                next_anchor_prefix and normalized_localized.endswith(next_anchor_prefix)
            ):
                return "tail_copies_next_anchor"
        if prev_anchor and prev_anchor[-16:] and prev_anchor[-16:] == first_line[: len(prev_anchor[-16:])]:
            return "head_copies_prev_anchor"
        if last_line.endswith(("……", "——")) and not next_anchor:
            return "dangling_ending_without_next_anchor"
        return None

    def _passes_local_cohesion_check(self, plan: Dict[str, Any], localized_text: str) -> bool:
        return self._local_cohesion_failure_reason(plan, localized_text) is None

    def _salvage_localized_anchor_overlap(self, plan: Dict[str, Any], localized_text: str) -> Optional[str]:
        localized = localized_text.strip()
        if not localized:
            return None
        repaired = localized
        next_anchor = str(plan.get("next_anchor") or "").strip()
        if next_anchor:
            if repaired.endswith(next_anchor):
                repaired = repaired[: -len(next_anchor)].rstrip()
            else:
                next_anchor_prefix = " ".join(next_anchor.split())[:24].strip()
                normalized_repaired = " ".join(repaired.split())
                if next_anchor_prefix and normalized_repaired.endswith(next_anchor_prefix):
                    idx = repaired.rfind(next_anchor_prefix)
                    if idx > 0:
                        repaired = repaired[:idx].rstrip()
        prev_anchor = str(plan.get("prev_anchor") or "").strip()
        if prev_anchor:
            prev_anchor_suffix = prev_anchor[-16:]
            first_line = repaired.splitlines()[0].strip() if repaired.splitlines() else repaired[:80]
            if prev_anchor_suffix and first_line.startswith(prev_anchor_suffix):
                leading_idx = repaired.find(prev_anchor_suffix)
                if leading_idx == 0:
                    repaired = repaired[len(prev_anchor_suffix):].lstrip()
        repaired = repaired.strip()
        if not repaired or repaired == localized:
            return None
        if self._local_cohesion_failure_reason(plan, repaired) is not None:
            return None
        return repaired

    def _stagewide_revision_guard_failure_reason(self, original_content: str, revised_content: str, *, residue_cleanup_mode: bool) -> Optional[str]:
        original = str(original_content or "").strip()
        revised = str(revised_content or "").strip()
        if not original:
            return "empty_original"
        if not revised:
            return "empty_revised"
        if revised == original:
            return "unchanged"
        min_ratio = 0.58 if residue_cleanup_mode else 0.72
        min_len = int(len(original) * min_ratio)
        if len(revised) < min_len:
            return f"too_short:{len(revised)}<{min_len}"
        original_paragraphs = self._split_paragraphs(original)
        revised_paragraphs = self._split_paragraphs(revised)
        min_paragraphs = max(3, len(original_paragraphs) // 3)
        if len(revised_paragraphs) < min_paragraphs:
            return f"too_few_paragraphs:{len(revised_paragraphs)}<{min_paragraphs}"
        if revised.endswith(("，", "、", "：", "；", "（", "[", "{", "“", "‘", "—", "-")):
            return "dangling_ending_punctuation"
        return None

    def _passes_stagewide_revision_guard(self, original_content: str, revised_content: str, *, residue_cleanup_mode: bool) -> bool:
        return self._stagewide_revision_guard_failure_reason(
            original_content,
            revised_content,
            residue_cleanup_mode=residue_cleanup_mode,
        ) is None

    async def _revise_chapter_stagewide(self, chapter_content: str, issues: List[Dict[str, Any]], context: Optional[Dict[str, Any]] = None, user_id: int = 0, *, strategy_key: str = "delivery_polish") -> str:
        if not issues:
            return chapter_content
        strategy = self.REVISION_STRATEGIES.get(strategy_key, self.REVISION_STRATEGIES["delivery_polish"])
        context_str = self._build_context_str(context)
        issues_text = self._build_issues_text(issues, limit=min(len(issues), 8))
        residue_hints = self._build_residue_hints(issues, limit=6)
        residue_cleanup_mode = bool(residue_hints)
        residue_guard = ""
        if residue_hints:
            residue_guard = "[必须清除的旧版本残留]\n" + "\n".join(f"- {item}" for item in residue_hints[:6]) + "\n\n"
        execution_requirements = self._build_issue_execution_requirements(issues, strategy_key=strategy_key, limit=self.EXECUTION_REQUIREMENT_LIMIT)
        execution_guard = ""
        if execution_requirements:
            execution_guard = "[本轮必须落地的执行动作]\n" + "\n".join(f"- {item}" for item in execution_requirements) + "\n\n"
        strategy_instruction = str(strategy.get("instruction") or "优先解决本轮问题，不偏离章节职责。")
        length_guidance = (
            "6. 当前允许压缩被污染的重复片段，但必须保留唯一正式事件链、必要因果节点、关键动作回合和章末压力。"
            if residue_cleanup_mode
            else "6. 保持原章的大致篇幅与段落呼吸，不要把正文缩成提纲。"
        )
        prompt = f"""你是一位擅长连载修订的资深小说编辑，现在要对整章做一次针对性的强修，但不能把故事改跑偏。
[本轮强修目标]
- 修订策略：{strategy.get('label', '整章强修')}
- 额外要求：{strategy_instruction}
- 本轮只重点解决与该策略相关的 critical / major 问题，其他已成立的剧情事实与信息边界保持稳定。

[必须修复的问题]
{issues_text}

{execution_guard}{context_str}

[原章节正文]
{chapter_content}

{residue_guard}修改要求：
1. 直接输出“修订后的完整章节正文”，不要解释，不要分点说明。
2. 必须修复本轮列出的 critical / major 问题，尤其是重复时间线、双版本拼接、逻辑回卷、对话空转、情绪发空、节奏拖沓等问题。
3. 保持章节标题对应的任务、人物身份、主线事实、POV 边界和世界规则稳定。
4. 如果同一事件、线索、对话或发现动作出现多个版本，只保留一个正式版本，删掉废弃版本，不要并排保留。
5. 章末压力必须继续存在，不能把钩子修没。
{length_guidance}
7. 不要为了修文新增无关设定、无关角色或跳出当前 POV 的解释性旁白。"""
        try:
            text_result = await call_generation_text(
                llm_service=self.llm_service,
                system_prompt="你是一位擅长整章强修的白金网文作者，能在不跑偏主线的前提下重构问题段落并保留连载张力。",
                conversation_history=[{"role": "user", "content": prompt}],
                temperature=0.45,
                user_id=user_id,
                timeout=240.0,
                policy=GenerationCallPolicy(
                    stage_label=f"{strategy.get('label', '强修')}候选补丁",
                    progress_stage="optimize_content",
                    retry_attempts=1,
                    response_format=None,
                    max_tokens=12000,
                    retry_same_model_once=False,
                ),
            )
            revised = remove_think_tags(text_result.text).strip()
            failure_reason = self._stagewide_revision_guard_failure_reason(
                chapter_content,
                revised,
                residue_cleanup_mode=residue_cleanup_mode,
            )
            if failure_reason is not None:
                logger.info(
                    "Stagewide revision rejected by guard: strategy=%s reason=%s residue_hints=%s",
                    strategy_key,
                    failure_reason,
                    len(residue_hints),
                )
                return chapter_content
            return revised
        except Exception as exc:
            logger.warning("整段修订失败：strategy=%s error=%s", strategy_key, exc)
            return chapter_content

    async def _revise_chapter_locally(self, chapter_content: str, issues: List[Dict[str, Any]], context: Optional[Dict[str, Any]] = None, user_id: int = 0, *, strategy_key: str = "delivery_polish") -> str:
        plan = self._build_local_rewrite_plan(chapter_content, issues, context, strategy_key=strategy_key)
        if not plan:
            return chapter_content
        issues_text = self._build_issues_text(plan["issues"], limit=int(self.REVISION_STRATEGIES.get(strategy_key, {}).get("rewrite_limit", 4)))
        context_str = self._build_context_str(context)
        window_indexes = plan["window_indexes"]
        target_text = "\n\n".join(plan["target_paragraphs"])
        unchanged_text = "\n".join([f"- 保持第 {idx + 1} 段不动" for idx in plan["untouched_indexes"][:12]])
        prev_anchor = plan.get("prev_anchor") or ""
        next_anchor = plan.get("next_anchor") or ""
        strategy_instruction = str(plan.get("strategy_instruction") or "").strip()
        strategy_label = str(plan.get("strategy_label") or "局部精修").strip()
        rewrite_mode = str(plan.get("rewrite_mode") or "expanded_window")
        residue_hints = plan.get("residue_hints") or []
        residue_guard = ""
        if residue_hints:
            residue_guard = "[必须清除的旧版本残留]\n" + "\n".join(f"- {item}" for item in residue_hints[:4]) + "\n\n"
        residue_cleanup_mode = bool(residue_hints) and rewrite_mode == "contiguous_span"
        execution_requirements = self._build_issue_execution_requirements(plan["issues"], strategy_key=strategy_key, limit=self.EXECUTION_REQUIREMENT_LIMIT)
        execution_guard = ""
        if execution_requirements:
            execution_guard = "[本轮必须落地的执行动作]\n" + "\n".join(f"- {item}" for item in execution_requirements) + "\n\n"
        length_guidance = (
            "6. 如果是在清除重复版本、旧片段残留或双版本拼接，允许明显压缩被污染片段，但必须保留唯一正式事件链、必要因果节点和前后承接。"
            if residue_cleanup_mode
            else "6. 维持原片段大致篇幅，可略增但不要明显缩水。"
        )
        prompt = f"""你是一位资深长篇连载作者，现在只对章节中的局部段落做精修，不要整章推翻重写。
[本轮修订目标]
- 修订策略：{strategy_label}
- 额外要求：{strategy_instruction or '优先修复当前问题，不扩写无关内容。'}
- 局部改写模式：{'连续统一区段改写' if rewrite_mode == 'contiguous_span' else '局部窗口改写'}

[必须修复的问题]
{issues_text}

{execution_guard}{context_str}

[本次允许重写的段落范围]
- 允许改写第 {window_indexes[0] + 1} 段到第 {window_indexes[-1] + 1} 段。
- 重点处理上述问题对应的局部段落，保留其余段落的剧情事实与信息边界。
{unchanged_text if unchanged_text else '- 未列出的段落默认保持原意。'}

[前文锚点]
{prev_anchor or '（无）'}

[待精修片段]
{target_text}

[后文锚点]
{next_anchor or '（无）'}

{residue_guard}修改要求：
1. 只输出“精修后的片段正文”，不要重复整章，不要输出说明。
2. 必须修复所有 critical 和 major 问题，优先修 location 指向的原文段落。
3. 开头必须能接上前文锚点，结尾必须能自然衔接后文锚点。
4. 保持人物身份、剧情走向、信息边界和章节职责稳定。
5. 允许补写、压缩、改写局部段落，但不要把片段缩成提纲。
{length_guidance}
7. 如果同一事件、线索、对话或发现动作在片段里出现了两个版本，只保留一个正式版本，删掉被废弃版本，不要并排保留。
8. 如果人物在前文已经确认某个事实，本次片段不得再写成“第一次发现/第一次核对/第一次得知”。"""
        try:
            text_result = await call_generation_text(
                llm_service=self.llm_service,
                system_prompt="你是一位擅长局部修文的白金网文作者，能在不跑偏剧情的前提下只重写必要片段。",
                conversation_history=[{"role": "user", "content": prompt}],
                temperature=0.55,
                user_id=user_id,
                timeout=180.0,
                policy=GenerationCallPolicy(
                    stage_label=f"{strategy_label}局部补丁",
                    progress_stage="optimize_content",
                    retry_attempts=2,
                    response_format=None,
                    max_tokens=5000,
                    retry_same_model_once=False,
                ),
            )
            localized = remove_think_tags(text_result.text).strip()
            if not localized:
                return chapter_content
            failure_reason = self._local_cohesion_failure_reason(plan, localized)
            if failure_reason is not None:
                salvaged = None
                if failure_reason in {"tail_copies_next_anchor", "head_copies_prev_anchor"}:
                    salvaged = self._salvage_localized_anchor_overlap(plan, localized)
                if salvaged is not None:
                    logger.info(
                        "局部修订在连贯性修复后已挽救：reason=%s mode=%s residue_hints=%s",
                        failure_reason,
                        plan.get("rewrite_mode"),
                        len(plan.get("residue_hints") or []),
                    )
                    localized = salvaged
                else:
                    logger.warning(
                        "局部修订未通过连贯性检查，已回退原文：reason=%s mode=%s residue_hints=%s",
                        failure_reason,
                        plan.get("rewrite_mode"),
                        len(plan.get("residue_hints") or []),
                    )
                    return chapter_content
            paragraphs = plan["all_paragraphs"]
            rebuilt = []
            inserted = False
            for idx, paragraph in enumerate(paragraphs):
                if idx == window_indexes[0]:
                    rebuilt.append(localized)
                    inserted = True
                if idx in window_indexes:
                    continue
                rebuilt.append(paragraph)
            if not inserted:
                return chapter_content
            return "\n\n".join(part.strip() for part in rebuilt if part.strip())
        except Exception as exc:
            logger.warning("局部修订失败：%s", exc)
            return chapter_content

    async def revise_chapter(
        self,
        chapter_content: str,
        issues: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None,
        user_id: int = 0,
        *,
        return_diagnostics: bool = False,
        allow_stagewide: bool = True,
        strategy_progress_callback: Optional[Callable[[str, Dict[str, Any]], Awaitable[None]]] = None,
    ) -> Any:
        if not issues:
            return (chapter_content, []) if return_diagnostics else chapter_content
        current_content = chapter_content
        strategy_logs: List[Dict[str, Any]] = []
        for strategy_key, strategy_issues in self._cluster_issues_by_strategy(issues):
            if strategy_progress_callback is not None:
                await strategy_progress_callback(
                    strategy_key,
                    {
                        "phase": "strategy_start",
                        "issue_count": len(strategy_issues),
                        "return_diagnostics": return_diagnostics,
                    },
                )
            before_fingerprint = self._content_fingerprint(current_content)
            before_counts = self._summarize_issue_counts(strategy_issues)
            strategy_aggregate_before: Optional[Dict[str, int]] = None
            strategy_aggregate_before_report: Optional[Dict[str, Any]] = None
            best_content = current_content
            best_after_counts: Optional[Dict[str, int]] = None
            stagewide_safety_before: Optional[Dict[str, int]] = None
            attempts: List[Dict[str, Any]] = []

            if strategy_progress_callback is not None:
                await strategy_progress_callback(
                    strategy_key,
                    {
                        "phase": "localized_primary",
                        "issue_count": len(strategy_issues),
                        "allow_stagewide": allow_stagewide,
                    },
                )
            localized_content = await self._revise_chapter_locally(current_content, strategy_issues, context=context, user_id=user_id, strategy_key=strategy_key)
            if localized_content and localized_content != current_content:
                localized_after = await self._critique_strategy_snapshot(localized_content, strategy_key=strategy_key, context=context, user_id=user_id, focus_issues=strategy_issues)
                localized_accepted, localized_reason = self._should_accept_strategy_snapshot(before_counts, localized_after)
                localized_aggregate_after: Optional[Dict[str, int]] = None
                if localized_accepted:
                    if strategy_aggregate_before is None:
                        strategy_aggregate_before_report = await self._critique_strategy_report(
                            current_content,
                            strategy_key=strategy_key,
                            context=context,
                            user_id=user_id,
                        )
                        strategy_aggregate_before = self._summarize_issue_counts(
                            strategy_aggregate_before_report.get("issues", [])
                        )
                    localized_aggregate_report = await self._critique_strategy_report(
                        localized_content,
                        strategy_key=strategy_key,
                        context=context,
                        user_id=user_id,
                    )
                    localized_aggregate_after = self._summarize_issue_counts(
                        localized_aggregate_report.get("issues", [])
                    )
                    localized_accepted, aggregate_reason = self._should_accept_strategy_snapshot(
                        strategy_aggregate_before,
                        localized_aggregate_after,
                    )
                    if not localized_accepted:
                        localized_reason = f"aggregate_{aggregate_reason}"
                attempts.append({
                    "mode": "localized",
                    "changed": True,
                    "accepted": localized_accepted,
                    "reason": localized_reason,
                    "before": before_counts,
                    "after": localized_after,
                    "aggregate_before": strategy_aggregate_before,
                    "aggregate_after": localized_aggregate_after,
                    "content_fingerprint": self._content_fingerprint(localized_content),
                })
                if localized_accepted:
                    best_content = localized_content
                    best_after_counts = localized_aggregate_after or localized_after
            else:
                attempts.append({
                    "mode": "localized",
                    "changed": False,
                    "accepted": False,
                    "reason": "unchanged",
                    "before": before_counts,
                    "after": before_counts,
                    "content_fingerprint": before_fingerprint,
                })

            skip_stagewide = self._should_skip_stagewide_rewrite(
                current_content,
                strategy_issues,
                before_counts,
                strategy_key=strategy_key,
            )
            if skip_stagewide:
                logger.info(
                    "Stagewide rewrite skipped for long-form delivery polish: critical=%s major=%s issue_count=%s content_length=%s",
                    before_counts.get("critical"),
                    before_counts.get("major"),
                    len(strategy_issues),
                    len((current_content or "").strip()),
                )
            needs_stagewide = not skip_stagewide and self._should_attempt_stagewide_rewrite(
                before_counts=before_counts,
                strategy_issues=strategy_issues,
                best_content_changed=best_content != current_content,
            )
            if needs_stagewide:
                if not allow_stagewide:
                    attempts.append({
                        "mode": "stagewide",
                        "changed": False,
                        "accepted": False,
                        "reason": "stagewide_deferred",
                        "before": before_counts,
                        "after": best_after_counts or before_counts,
                        "content_fingerprint": self._content_fingerprint(best_content),
                    })
                else:
                    if strategy_progress_callback is not None:
                        await strategy_progress_callback(
                            strategy_key,
                            {
                                "phase": "stagewide_primary",
                                "issue_count": len(strategy_issues),
                                "allow_stagewide": allow_stagewide,
                            },
                        )
                    stagewide_content = await self._revise_chapter_stagewide(current_content, strategy_issues, context=context, user_id=user_id, strategy_key=strategy_key)
                    if stagewide_content and stagewide_content != current_content:
                        stagewide_after = await self._critique_strategy_snapshot(stagewide_content, strategy_key=strategy_key, context=context, user_id=user_id, focus_issues=strategy_issues)
                        stagewide_accepted, stagewide_reason = self._should_accept_strategy_snapshot(before_counts, stagewide_after)
                        stagewide_aggregate_report: Optional[Dict[str, Any]] = None
                        stagewide_aggregate_after: Optional[Dict[str, int]] = None
                        safety_after: Optional[Dict[str, int]] = None
                        if stagewide_accepted:
                            if strategy_aggregate_before is None:
                                strategy_aggregate_before_report = await self._critique_strategy_report(
                                    current_content,
                                    strategy_key=strategy_key,
                                    context=context,
                                    user_id=user_id,
                                )
                                strategy_aggregate_before = self._summarize_issue_counts(
                                    strategy_aggregate_before_report.get("issues", [])
                                )
                            stagewide_aggregate_report = await self._critique_strategy_report(
                                stagewide_content,
                                strategy_key=strategy_key,
                                context=context,
                                user_id=user_id,
                            )
                            stagewide_aggregate_after = self._summarize_issue_counts(
                                stagewide_aggregate_report.get("issues", [])
                            )
                            stagewide_accepted, aggregate_reason = self._should_accept_strategy_snapshot(
                                strategy_aggregate_before,
                                stagewide_aggregate_after,
                            )
                            if not stagewide_accepted:
                                stagewide_reason = f"aggregate_{aggregate_reason}"
                        if stagewide_accepted:
                            if stagewide_safety_before is None:
                                stagewide_safety_before = await self._critique_stagewide_safety_snapshot(
                                    current_content,
                                    context=context,
                                    user_id=user_id,
                                )
                            safety_after = await self._critique_stagewide_safety_snapshot(
                                stagewide_content,
                                context=context,
                                user_id=user_id,
                            )
                            safety_regression_reason = self._stagewide_safety_regression_reason(stagewide_safety_before, safety_after)
                            if safety_regression_reason is not None:
                                stagewide_accepted = False
                                stagewide_reason = safety_regression_reason
                        attempts.append({
                            "mode": "stagewide",
                            "changed": True,
                            "accepted": stagewide_accepted,
                            "reason": stagewide_reason,
                            "before": before_counts,
                            "after": stagewide_after,
                            "aggregate_before": strategy_aggregate_before,
                            "aggregate_after": stagewide_aggregate_after,
                            "safety_before": stagewide_safety_before,
                            "safety_after": safety_after,
                            "content_fingerprint": self._content_fingerprint(stagewide_content),
                        })
                        if (
                            not stagewide_accepted
                            and stagewide_reason == "aggregate_not_improved_enough"
                            and stagewide_aggregate_report is not None
                        ):
                            if strategy_progress_callback is not None:
                                await strategy_progress_callback(
                                    strategy_key,
                                    {
                                        "phase": "aggregate_retry",
                                        "issue_count": len(strategy_issues),
                                        "aggregate_issue_count": len(stagewide_aggregate_report.get("issues") or []),
                                        "retry_reason": stagewide_reason,
                                    },
                                )
                            aggregate_retry_issues = self._limit_stage_issues(
                                [*strategy_issues, *(stagewide_aggregate_report.get("issues") or [])],
                                limit=max(3, min(6, len(strategy_issues) + len(stagewide_aggregate_report.get("issues") or []))),
                            )
                            retry_content = await self._revise_chapter_stagewide(
                                current_content,
                                aggregate_retry_issues,
                                context=context,
                                user_id=user_id,
                                strategy_key=strategy_key,
                            )
                            if retry_content and retry_content != current_content:
                                retry_after = await self._critique_strategy_snapshot(
                                    retry_content,
                                    strategy_key=strategy_key,
                                    context=context,
                                    user_id=user_id,
                                    focus_issues=strategy_issues,
                                )
                                retry_accepted, retry_reason = self._should_accept_strategy_snapshot(
                                    before_counts,
                                    retry_after,
                                )
                                retry_aggregate_report: Optional[Dict[str, Any]] = None
                                retry_aggregate_after: Optional[Dict[str, int]] = None
                                retry_safety_after: Optional[Dict[str, int]] = None
                                if retry_accepted:
                                    retry_aggregate_report = await self._critique_strategy_report(
                                        retry_content,
                                        strategy_key=strategy_key,
                                        context=context,
                                        user_id=user_id,
                                    )
                                    retry_aggregate_after = self._summarize_issue_counts(
                                        retry_aggregate_report.get("issues", [])
                                    )
                                    retry_accepted, retry_aggregate_reason = self._should_accept_strategy_snapshot(
                                        strategy_aggregate_before,
                                        retry_aggregate_after,
                                    )
                                    if not retry_accepted:
                                        retry_reason = f"aggregate_{retry_aggregate_reason}"
                                if retry_accepted:
                                    if stagewide_safety_before is None:
                                        stagewide_safety_before = await self._critique_stagewide_safety_snapshot(
                                            current_content,
                                            context=context,
                                            user_id=user_id,
                                        )
                                    retry_safety_after = await self._critique_stagewide_safety_snapshot(
                                        retry_content,
                                        context=context,
                                        user_id=user_id,
                                    )
                                    retry_safety_reason = self._stagewide_safety_regression_reason(
                                        stagewide_safety_before,
                                        retry_safety_after,
                                    )
                                    if retry_safety_reason is not None:
                                        retry_accepted = False
                                        retry_reason = retry_safety_reason
                                attempts.append({
                                    "mode": "stagewide",
                                    "retry_source": "aggregate_feedback",
                                    "changed": True,
                                    "accepted": retry_accepted,
                                    "reason": retry_reason,
                                    "before": before_counts,
                                    "after": retry_after,
                                    "aggregate_before": strategy_aggregate_before,
                                    "aggregate_after": retry_aggregate_after,
                                    "safety_before": stagewide_safety_before,
                                    "safety_after": retry_safety_after,
                                    "content_fingerprint": self._content_fingerprint(retry_content),
                                })
                                if retry_accepted and self._is_better_strategy_snapshot(retry_aggregate_after or retry_after, best_after_counts):
                                    best_content = retry_content
                                    best_after_counts = retry_aggregate_after or retry_after
                        if stagewide_accepted and self._is_better_strategy_snapshot(stagewide_aggregate_after or stagewide_after, best_after_counts):
                            best_content = stagewide_content
                            best_after_counts = stagewide_aggregate_after or stagewide_after
                    else:
                        attempts.append({
                            "mode": "stagewide",
                            "changed": False,
                            "accepted": False,
                            "reason": "unchanged",
                            "before": before_counts,
                            "after": before_counts,
                            "content_fingerprint": before_fingerprint,
                        })

            current_content = best_content
            stagewide_attempts = [item for item in attempts if item.get("mode") == "stagewide"]
            strategy_logs.append({
                "strategy": strategy_key,
                "issue_count": len(strategy_issues),
                "before": before_counts,
                "selected_after": best_after_counts or before_counts,
                "content_changed": before_fingerprint != self._content_fingerprint(best_content),
                "accepted": best_after_counts is not None,
                "stagewide_allowed": allow_stagewide,
                "stagewide_attempted": bool(stagewide_attempts),
                "stagewide_accepted": any(item.get("accepted") for item in stagewide_attempts),
                "stagewide_deferred": any(item.get("reason") == "stagewide_deferred" for item in stagewide_attempts),
                "attempts": attempts,
            })
        if return_diagnostics:
            return current_content, strategy_logs
        return current_content

    async def critique_and_revise_loop(
        self,
        chapter_content: str,
        max_iterations: int = 1,
        target_score: float = 82.0,
        dimensions: Optional[List[CritiqueDimension]] = None,
        context: Optional[Dict[str, Any]] = None,
        user_id: int = 0,
        progress_callback: Optional[Callable[[str, Dict[str, Any]], Awaitable[None]]] = None,
        stage_optimize_callback: Optional[Callable[[str, Dict[str, Any]], Awaitable[None]]] = None,
        strategy_optimize_callback: Optional[Callable[[str, Dict[str, Any]], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        with LLMService.daily_limit_scope(f"self_critique_loop:{user_id}:{len(chapter_content)}"):
            if dimensions is None:
                dimensions = list(CritiqueDimension)
            max_iterations = max(1, int(max_iterations or 1))
            iteration_limit = max_iterations
            deferred_drain_iterations_used = 0
            result = {"original_content": chapter_content, "final_content": chapter_content, "iterations": [], "final_score": 0, "improvement": 0, "status": "pending", "final_critique": None, "optimization_logs": []}
            current_content = chapter_content
            critique = await self.full_critique(chapter_content, dimensions=dimensions, context=context, user_id=user_id, progress_callback=progress_callback)
            initial_critique = critique
            final_critique = critique
            deferred_stage_names: List[str] = []
            iteration_index = 0

            while iteration_index < iteration_limit:
                iteration_index += 1
                iteration_entry = {
                    "iteration": iteration_index,
                    "critique": {
                        "weighted_score": critique["weighted_score"],
                        "critical_count": critique["critical_count"],
                        "major_count": critique["major_count"],
                        "minor_count": critique["minor_count"],
                        "needs_revision": critique["needs_revision"],
                        "priority_fixes": critique.get("priority_fixes", []),
                        "stage_summaries": critique.get("stage_summaries", []),
                        "raw_issue_count": critique.get("raw_issue_count"),
                        "deduped_issue_count": critique.get("deduped_issue_count"),
                        "merged_issue_count": critique.get("merged_issue_count"),
                        "content_fingerprint": self._content_fingerprint(current_content),
                    },
                    "revised": False,
                    "score_before": critique["weighted_score"],
                    "score_after": critique["weighted_score"],
                }
                result["iterations"].append(iteration_entry)

                if not critique.get("needs_revision") and critique.get("weighted_score", 0) >= target_score:
                    final_critique = critique
                    break

                grouped_issues: List[Tuple[str, List[Dict[str, Any]], List[str]]] = [
                    ("structural", [issue for issue in critique.get("all_issues", []) if issue.get("dimension") in {"logic", "continuity", "pov"}], ["logic", "continuity", "pov"]),
                    ("character", [issue for issue in critique.get("all_issues", []) if issue.get("dimension") in {"character", "relationship", "emotion", "dialogue"}], ["character", "relationship", "emotion", "dialogue"]),
                    ("delivery", [issue for issue in critique.get("all_issues", []) if issue.get("dimension") in {"pacing", "scene", "suspense", "writing"}], ["pacing", "scene", "suspense", "writing"]),
                ]
                grouped_issues = self._order_stage_groups(grouped_issues, preferred_stage_names=deferred_stage_names)
                next_deferred_stage_names: List[str] = []
                any_stage_changed = False
                stagewide_budget = self.MAX_STAGEWIDE_REWRITES_PER_ITERATION
                for stage_name, stage_issues, stage_dimensions in grouped_issues:
                    if not stage_issues:
                        continue
                    prioritized_issues = self._prioritize_stage_issues(stage_issues, stage_dimensions)
                    allow_stagewide = stagewide_budget > 0
                    if stage_optimize_callback is not None:
                        await stage_optimize_callback(stage_name, {"issue_count": len(prioritized_issues), "dimensions": stage_dimensions, "iteration": iteration_index})
                    before_content = current_content
                    revise_kwargs: Dict[str, Any] = {
                        "context": context,
                        "user_id": user_id,
                        "return_diagnostics": True,
                        "allow_stagewide": allow_stagewide,
                    }
                    if strategy_optimize_callback is not None:
                        revise_kwargs["strategy_progress_callback"] = strategy_optimize_callback
                    current_content, strategy_logs = await self.revise_chapter(
                        current_content,
                        prioritized_issues,
                        **revise_kwargs,
                    )
                    changed = current_content != before_content
                    any_stage_changed = any_stage_changed or changed
                    stagewide_attempted = any(
                        log.get("stagewide_attempted")
                        or log.get("stagewide_accepted")
                        or log.get("stagewide_deferred")
                        for log in strategy_logs
                    )
                    stagewide_accepted = any(log.get("stagewide_accepted") for log in strategy_logs)
                    stagewide_deferred = any(log.get("stagewide_deferred") for log in strategy_logs)
                    if stagewide_attempted and stagewide_budget > 0:
                        stagewide_budget -= 1
                    if stagewide_deferred and stage_name not in next_deferred_stage_names:
                        next_deferred_stage_names.append(stage_name)
                    result["optimization_logs"].append({
                        "iteration": iteration_index,
                        "stage": stage_name,
                        "issue_count": len(prioritized_issues),
                        "dimensions": stage_dimensions,
                        "selected_issues": prioritized_issues,
                        "changed": changed,
                        "allow_stagewide": allow_stagewide,
                        "stagewide_accepted": stagewide_accepted,
                        "stagewide_deferred": stagewide_deferred,
                        "remaining_stagewide_budget": stagewide_budget,
                        "strategy_logs": strategy_logs,
                    })
                iteration_entry["revised"] = current_content != chapter_content
                if not any_stage_changed:
                    final_critique = critique
                    break

                final_critique = await self.full_critique(current_content, dimensions=dimensions, context=context, user_id=user_id)
                iteration_entry["score_after"] = final_critique["weighted_score"]
                iteration_entry["post_revision_critique"] = {
                    "weighted_score": final_critique["weighted_score"],
                    "critical_count": final_critique["critical_count"],
                    "major_count": final_critique["major_count"],
                    "minor_count": final_critique["minor_count"],
                    "needs_revision": final_critique["needs_revision"],
                    "priority_fixes": final_critique.get("priority_fixes", []),
                    "stage_summaries": final_critique.get("stage_summaries", []),
                    "raw_issue_count": final_critique.get("raw_issue_count"),
                    "deduped_issue_count": final_critique.get("deduped_issue_count"),
                    "merged_issue_count": final_critique.get("merged_issue_count"),
                    "content_fingerprint": self._content_fingerprint(current_content),
                }
                critique = final_critique
                deferred_stage_names = next_deferred_stage_names
                if not critique.get("needs_revision") and critique.get("weighted_score", 0) >= target_score:
                    break

                if (
                    iteration_index >= iteration_limit
                    and deferred_stage_names
                    and critique.get("needs_revision")
                    and deferred_drain_iterations_used < self.MAX_DEFERRED_STAGE_DRAIN_ITERATIONS
                ):
                    iteration_limit += 1
                    deferred_drain_iterations_used += 1
                    iteration_entry["deferred_stage_replay_extension"] = {
                        "granted": True,
                        "deferred_stage_names": list(deferred_stage_names),
                        "extension_iteration_limit": iteration_limit,
                    }
                    continue

            result["final_content"] = current_content
            result["final_score"] = final_critique["weighted_score"]
            result["improvement"] = round(final_critique["weighted_score"] - initial_critique["weighted_score"], 1)
            result["final_critique"] = final_critique
            result["status"] = "optimized" if current_content != chapter_content and result["improvement"] > 0 else ("revised_but_unimproved" if current_content != chapter_content else "diagnosed_only")
            return result

    async def quick_critique(self, chapter_content: str, user_id: int = 0) -> Dict[str, Any]:
        with LLMService.daily_limit_scope(f"self_critique_quick:{user_id}:{len(chapter_content)}"):
            prompt = f"""快速审查以下章节，找出最严重的问题。
[章节内容]
{chapter_content[:7000]}

请快速检查：
1. 是否有明显逻辑漏洞或连续性断裂
2. 是否有 POV 越界或全知旁白
3. 是否有人物、情绪、对话明显发空
4. 章末是否具备钩子
5. 是否有 AI 典型词汇

请以 JSON 输出：
{{
  "quick_score": 1,
  "critical_issues": ["严重问题列表"],
  "ai_words_found": ["发现的 AI 典型词汇"],
  "has_hook": true,
  "pass": true
}}"""
            try:
                json_result = await call_generation_json(
                    llm_service=self.llm_service,
                    system_prompt="你是一位快速审稿编辑，请简洁指出最关键的问题。",
                    conversation_history=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    user_id=user_id,
                    timeout=60.0,
                    policy=GenerationCallPolicy(
                        stage_label="快速质量复核",
                        progress_stage="review",
                        retry_attempts=2,
                        response_format="json_object",
                        max_tokens=1200,
                        retry_same_model_once=True,
                        json_repair_attempts=1,
                    ),
                )
                return json_result.data
            except Exception as exc:
                logger.warning("Quick critique failed: %s", exc)
            return {"quick_score": 70, "critical_issues": [], "ai_words_found": [], "has_hook": True, "pass": True}
