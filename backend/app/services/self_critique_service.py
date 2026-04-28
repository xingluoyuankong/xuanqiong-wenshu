"""Structured self-critique and targeted local revision service."""
from __future__ import annotations

from enum import Enum
from typing import Optional, Dict, Any, List, Callable, Awaitable, Tuple
import json
import logging
import re

from sqlalchemy.ext.asyncio import AsyncSession

from .llm_service import LLMService
from .prompt_service import PromptService
from ..utils.json_utils import remove_think_tags, unwrap_markdown_json

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
            "window_radius": 1,
            "rewrite_limit": 4,
            "instruction": "优先修复因果、承接、信息边界和 POV 越界，禁止为了润色而改动主线事实。",
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

    def _build_context_str(self, context: Optional[Dict[str, Any]]) -> str:
        if not context:
            return ""
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
        for key, label, limit in mapping:
            value = context.get(key)
            if value:
                sections.append(f"[{label}]\n{self._truncate_text(value, limit)}")
        return "\n\n".join(sections)

    def _normalize_dimension_value(self, value: Any, allowed_dimensions: List[CritiqueDimension], default_dimension: CritiqueDimension) -> str:
        raw = str(value or "").strip().lower()
        allowed_values = {dimension.value for dimension in allowed_dimensions}
        return raw if raw in allowed_values else default_dimension.value

    async def critique_dimension_batch(
        self,
        chapter_content: str,
        stage_name: str,
        dimensions: List[CritiqueDimension],
        context: Optional[Dict[str, Any]] = None,
        user_id: int = 0,
    ) -> Dict[str, Any]:
        if not dimensions:
            return {"stage": stage_name, "dimensions": [], "overall_score": 70, "issues": [], "strengths": [], "summary": "无可审查维度", "weight": 0.0}

        context_str = self._build_context_str(context)
        dimension_specs: List[str] = []
        total_weight = 0.0
        default_dimension = dimensions[0]
        for dimension in dimensions:
            dim_config = self.CRITIQUE_PROMPTS[dimension]
            focus_points = "\n".join(f"  - {item}" for item in dim_config["focus"])
            dimension_specs.append(f"[{dimension.value} | {dim_config['name']}]\n{focus_points}")
            total_weight += float(dim_config["severity_weight"])

        dimension_lines = ", ".join(dimension.value for dimension in dimensions)
        previous_chapter_bundle = self._truncate_text((context or {}).get("previous_chapter_bundle"), 3200)
        chapter_excerpt = self._truncate_text(chapter_content, 4500)
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
4. strengths 和 summary 也要基于本阶段整体表现给出。
请以 JSON 输出：
{{
  "stage": "{stage_name}",
  "dimensions": {json.dumps([dimension.value for dimension in dimensions], ensure_ascii=False)},
  "overall_score": 1,
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
            response = await self.llm_service.get_llm_response(
                system_prompt=f"你是一位专注于{stage_name}阶段审查的严格长篇小说编辑。请聚合输出问题，避免拆成多次独立诊断。",
                conversation_history=[{"role": "user", "content": prompt}],
                temperature=0.2,
                user_id=user_id,
                timeout=180.0,
            )
            content = unwrap_markdown_json(remove_think_tags(response))
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                result = json.loads(content[json_start:json_end])
                issues = []
                for issue in result.get("issues", []) or []:
                    if not isinstance(issue, dict):
                        continue
                    normalized_issue = dict(issue)
                    normalized_issue["dimension"] = self._normalize_dimension_value(issue.get("dimension"), dimensions, default_dimension)
                    issues.append(normalized_issue)
                result["stage"] = stage_name
                result["dimensions"] = [dimension.value for dimension in dimensions]
                result["issues"] = issues
                result["weight"] = total_weight
                return result
        except Exception as exc:
            logger.warning("Critique batch %s failed: %s", stage_name, exc)
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
        }
        total_weight = 0.0
        weighted_score_sum = 0.0
        stage_batches = self._build_dimension_batches(dimensions)
        critique_results: List[Dict[str, Any]] = []
        for batch_index, (stage_name, stage_dimensions) in enumerate(stage_batches, start=1):
            if progress_callback is not None:
                await progress_callback(stage_name, {"batch_index": batch_index, "batch_count": len(stage_batches), "dimensions": [dimension.value for dimension in stage_dimensions]})
            critique_results.append(await self.critique_dimension_batch(chapter_content, stage_name, stage_dimensions, context=context, user_id=user_id))
        for critique in critique_results:
            stage_name = str(critique.get("stage") or "unknown")
            stage_dimensions = [str(item) for item in critique.get("dimensions", []) if str(item).strip()]
            issue_count = 0
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
                results["all_issues"].append(normalized_issue)
                issue_count += 1
                if severity == "critical":
                    results["critical_count"] += 1
                elif severity == "major":
                    results["major_count"] += 1
                else:
                    results["minor_count"] += 1
            weight = float(critique.get("weight", 1.0))
            score = float(critique.get("overall_score", 70))
            weighted_score_sum += score * weight
            total_weight += weight
            results["stage_summaries"].append({"stage": stage_name, "dimensions": stage_dimensions, "issue_count": issue_count, "weighted_score": round(score, 1), "summary": critique.get("summary")})
            for dimension_value in stage_dimensions:
                results["dimension_critiques"][dimension_value] = {
                    "stage": stage_name,
                    "dimension": dimension_value,
                    "overall_score": round(score, 1),
                    "issues": [issue for issue in results["all_issues"] if issue.get("dimension") == dimension_value],
                    "strengths": critique.get("strengths", []),
                    "summary": critique.get("summary", ""),
                    "weight": weight,
                }
        if total_weight > 0:
            results["weighted_score"] = round(weighted_score_sum / total_weight, 1)
        results["needs_revision"] = results["critical_count"] > 0 or results["major_count"] >= 2 or results["weighted_score"] < 78
        priority_issues = [issue for issue in results["all_issues"] if issue.get("severity") in ["critical", "major"]]
        priority_issues.sort(key=lambda x: 0 if x.get("severity") == "critical" else 1)
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

    def _split_paragraphs(self, chapter_content: str) -> List[str]:
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", chapter_content) if part.strip()]
        return paragraphs or [chapter_content]

    def _match_issue_to_paragraph_indexes(self, paragraphs: List[str], issue: Dict[str, Any]) -> List[int]:
        location = str(issue.get("location") or "").strip()
        problem = str(issue.get("problem") or "").strip()
        suggestion = str(issue.get("suggestion") or "").strip()
        dimension = str(issue.get("dimension") or "").strip().lower()
        indexes: List[int] = []
        if location and location != "未定位":
            normalized_location = location.replace("“", "").replace("”", "").replace("...", "").strip()
            for idx, paragraph in enumerate(paragraphs):
                if normalized_location and normalized_location in paragraph:
                    indexes.append(idx)
        if indexes:
            return indexes[:3]
        haystack = f"{problem} {suggestion}".lower()
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
        window_indexes = self._expand_rewrite_window(sorted(target_indexes), len(paragraphs), radius=int(strategy.get("window_radius", 1)))
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
        }

    def _passes_local_cohesion_check(self, plan: Dict[str, Any], localized_text: str) -> bool:
        localized = localized_text.strip()
        if not localized:
            return False
        min_len = max(24, int(sum(len(p) for p in plan.get("target_paragraphs", [])) * 0.2))
        if len(localized) < min_len:
            return False
        prev_anchor = str(plan.get("prev_anchor") or "").strip()
        next_anchor = str(plan.get("next_anchor") or "").strip()
        first_line = localized.splitlines()[0].strip() if localized.splitlines() else localized[:80]
        last_line = localized.splitlines()[-1].strip() if localized.splitlines() else localized[-80:]
        if prev_anchor and any(first_line.startswith(token) for token in ("与此同时", "另一边", "突然", "总之")):
            return False
        if next_anchor and next_anchor[:16] and next_anchor[:16] in localized:
            return False
        if prev_anchor and prev_anchor[-16:] and prev_anchor[-16:] == first_line[: len(prev_anchor[-16:])]:
            return False
        if last_line.endswith(("……", "——")) and not next_anchor:
            return False
        return True

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
        prompt = f"""你是一位资深长篇连载作者，现在只对章节中的局部段落做精修，不要整章推翻重写。
[本轮修订目标]
- 修订策略：{strategy_label}
- 额外要求：{strategy_instruction or '优先修复当前问题，不扩写无关内容。'}

[必须修复的问题]
{issues_text}

{context_str}

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

修改要求：
1. 只输出“精修后的片段正文”，不要重复整章，不要输出说明。
2. 必须修复所有 critical 和 major 问题，优先修 location 指向的原文段落。
3. 开头必须能接上前文锚点，结尾必须能自然衔接后文锚点。
4. 保持人物身份、剧情走向、信息边界和章节职责稳定。
5. 允许补写、压缩、改写局部段落，但不要把片段缩成提纲。
6. 维持原片段大致篇幅，可略增但不要明显缩水。"""
        try:
            response = await self.llm_service.get_llm_response(
                system_prompt="你是一位擅长局部修文的白金网文作者，能在不跑偏剧情的前提下只重写必要片段。",
                conversation_history=[{"role": "user", "content": prompt}],
                temperature=0.55,
                user_id=user_id,
                timeout=180.0,
                retry_same_model_once=False,
            )
            localized = remove_think_tags(response).strip()
            if not localized:
                return chapter_content
            if not self._passes_local_cohesion_check(plan, localized):
                logger.warning("Localized revision failed cohesion check; fallback to original text")
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
            logger.warning("Localized revision failed: %s", exc)
            return chapter_content

    async def revise_chapter(self, chapter_content: str, issues: List[Dict[str, Any]], context: Optional[Dict[str, Any]] = None, user_id: int = 0) -> str:
        if not issues:
            return chapter_content
        current_content = chapter_content
        for strategy_key, strategy_issues in self._cluster_issues_by_strategy(issues):
            localized_content = await self._revise_chapter_locally(current_content, strategy_issues, context=context, user_id=user_id, strategy_key=strategy_key)
            if localized_content and localized_content != current_content:
                current_content = localized_content
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
    ) -> Dict[str, Any]:
        if dimensions is None:
            dimensions = list(CritiqueDimension)
        result = {"original_content": chapter_content, "final_content": chapter_content, "iterations": [], "final_score": 0, "improvement": 0, "status": "pending", "final_critique": None, "optimization_logs": []}
        critique = await self.full_critique(chapter_content, dimensions=dimensions, context=context, user_id=user_id, progress_callback=progress_callback)
        current_content = chapter_content
        grouped_issues: List[Tuple[str, List[Dict[str, Any]], List[str]]] = [
            ("structural", [issue for issue in critique.get("all_issues", []) if issue.get("dimension") in {"logic", "continuity", "pov"}], ["logic", "continuity", "pov"]),
            ("character", [issue for issue in critique.get("all_issues", []) if issue.get("dimension") in {"character", "relationship", "emotion", "dialogue"}], ["character", "relationship", "emotion", "dialogue"]),
            ("delivery", [issue for issue in critique.get("all_issues", []) if issue.get("dimension") in {"pacing", "scene", "suspense", "writing"}], ["pacing", "scene", "suspense", "writing"]),
        ]
        for stage_name, stage_issues, stage_dimensions in grouped_issues:
            if not stage_issues:
                continue
            prioritized_issues = self._prioritize_stage_issues(stage_issues, stage_dimensions)
            if stage_optimize_callback is not None:
                await stage_optimize_callback(stage_name, {"issue_count": len(prioritized_issues), "dimensions": stage_dimensions})
            before_content = current_content
            current_content = await self.revise_chapter(current_content, prioritized_issues, context=context, user_id=user_id)
            result["optimization_logs"].append({"stage": stage_name, "issue_count": len(prioritized_issues), "dimensions": stage_dimensions, "selected_issues": prioritized_issues, "changed": current_content != before_content})
        result["iterations"].append({"iteration": 1, "critique": {"weighted_score": critique["weighted_score"], "critical_count": critique["critical_count"], "major_count": critique["major_count"], "minor_count": critique["minor_count"], "needs_revision": critique["needs_revision"], "priority_fixes": critique.get("priority_fixes", []), "stage_summaries": critique.get("stage_summaries", [])}, "revised": current_content != chapter_content, "score_before": critique["weighted_score"], "score_after": critique["weighted_score"]})
        final_critique = critique
        if current_content != chapter_content:
            final_critique = await self.full_critique(current_content, dimensions=dimensions, context=context, user_id=user_id)
            result["iterations"][-1]["score_after"] = final_critique["weighted_score"]
            result["iterations"][-1]["post_revision_critique"] = {"weighted_score": final_critique["weighted_score"], "critical_count": final_critique["critical_count"], "major_count": final_critique["major_count"], "minor_count": final_critique["minor_count"], "needs_revision": final_critique["needs_revision"], "priority_fixes": final_critique.get("priority_fixes", []), "stage_summaries": final_critique.get("stage_summaries", [])}
        result["final_content"] = current_content
        result["final_score"] = final_critique["weighted_score"]
        result["improvement"] = round(final_critique["weighted_score"] - critique["weighted_score"], 1)
        result["final_critique"] = final_critique
        result["status"] = "optimized" if current_content != chapter_content and result["improvement"] > 0 else ("revised_but_unimproved" if current_content != chapter_content else "diagnosed_only")
        return result

    async def quick_critique(self, chapter_content: str, user_id: int = 0) -> Dict[str, Any]:
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
            response = await self.llm_service.get_llm_response(
                system_prompt="你是一位快速审稿编辑，请简洁指出最关键的问题。",
                conversation_history=[{"role": "user", "content": prompt}],
                temperature=0.2,
                user_id=user_id,
                timeout=60.0,
            )
            content = unwrap_markdown_json(remove_think_tags(response))
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                return json.loads(content[json_start:json_end])
        except Exception as exc:
            logger.warning("Quick critique failed: %s", exc)
        return {"quick_score": 70, "critical_issues": [], "ai_words_found": [], "has_hook": True, "pass": True}
