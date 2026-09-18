# AIMETA P=AI评审服务_多版本对比选优|R=版本评分_最佳选择_改进建议|NR=不含数据存储|E=none|X=internal|A=评审_对比|D=openai|S=net|RD=./README.ai
"""
AIReviewService: AI 评审服务

核心职责：
1. 对多个生成版本进行对比评审
2. 根据起点中文网爆款标准打分
3. 选出最佳版本并给出改进建议
"""

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..services.generation_call_service import GenerationCallPolicy, call_generation_text
from ..services.llm_service import LLMService
from ..services.prompt_service import PromptService
from ..utils.json_utils import remove_think_tags, unwrap_markdown_json

logger = logging.getLogger(__name__)


@dataclass
class ReviewResult:
    """评审结果"""
    best_version_index: Optional[int]
    scores: Dict[str, int]  # immersion, pacing, hook, character
    overall_evaluation: str
    critical_flaws: List[str]
    refinement_suggestions: str
    final_recommendation: str
    raw_response: Optional[str] = None
    status: str = "passed"


class AIReviewService:
    """
    AI 评审服务 - 金牌编辑模式
    
    使用 editor_review 提示词对多个版本进行对比评审，
    选出最具爆款潜力的版本。
    """

    def __init__(self, llm_service: LLMService, prompt_service: PromptService):
        self.llm_service = llm_service
        self.prompt_service = prompt_service

    async def review_versions(
        self,
        versions: List[str],
        chapter_mission: Optional[dict] = None,
        user_id: int = 0,
    ) -> Optional[ReviewResult]:
        """
        对多个版本进行评审，返回评审结果。

        Args:
            versions: 多个版本的正文内容
            chapter_mission: 章节导演脚本（用于评估是否符合预期）
            user_id: 用户 ID

        Returns:
            ReviewResult: 评审结果，如果失败返回 None
        """
        with LLMService.daily_limit_scope(f"ai_review:{user_id}:{len(versions)}"):
            if not versions:
                logger.warning("没有版本可供评审")
                return None

            if len(versions) == 1:
                return await self._review_single_version(
                    version=versions[0],
                    chapter_mission=chapter_mission,
                    user_id=user_id,
                )

            # 获取评审提示词
            review_prompt = await self.prompt_service.get_prompt("editor_review")
            if not review_prompt:
                logger.warning("未配置 editor_review 提示词，跳过 AI 评审")
                return None

            # 构建评审输入
            review_input = self._build_review_input(versions, chapter_mission)

            try:
                text_result = await call_generation_text(
                    llm_service=self.llm_service,
                    system_prompt=review_prompt,
                    conversation_history=[{"role": "user", "content": review_input}],
                    temperature=0.3,
                    user_id=user_id,
                    timeout=180.0,
                    policy=GenerationCallPolicy(
                        stage_label="多候选版本 AI 评审",
                        progress_stage="review",
                        retry_attempts=2,
                        response_format="json_object",
                        max_tokens=5000,
                        retry_same_model_once=True,
                    ),
                )
                cleaned = remove_think_tags(text_result.text)
                normalized = unwrap_markdown_json(cleaned)

                result = self._parse_review_response(normalized)
                result.raw_response = cleaned

                logger.info(
                    "AI 评审完成: 最佳版本=%s, 综合评分=%.1f",
                    result.best_version_index,
                    sum(result.scores.values()) / len(result.scores) if result.scores else 0,
                )
                return result
            except Exception as exc:
                logger.exception("AI 评审失败: %s", exc)
                return None

    @staticmethod
    def _split_paragraphs(content: str) -> List[str]:
        return [segment.strip() for segment in str(content or "").splitlines() if segment.strip()]

    @staticmethod
    def _count_dialogue_markers(content: str) -> int:
        return sum(str(content or "").count(marker) for marker in ("“", "”", "「", "」", "『", "』", '"'))

    @staticmethod
    def _count_progression_markers(content: str) -> int:
        text = str(content or "")
        markers = (
            "却",
            "但",
            "突然",
            "忽然",
            "发现",
            "意识到",
            "逼问",
            "拒绝",
            "反问",
            "威胁",
            "决定",
            "转而",
            "反转",
            "暴露",
            "失控",
            "代价",
            "线索",
            "危险",
            "门外",
            "脚步",
            "下一刻",
            "然而",
        )
        return sum(text.count(marker) for marker in markers)

    @staticmethod
    def _short_excerpt(content: str, *, limit: int = 180) -> str:
        text = " ".join(str(content or "").split())
        if len(text) <= limit:
            return text
        return f"{text[:limit].rstrip()}..."

    @classmethod
    def _build_structure_map(cls, paragraphs: List[str]) -> List[Dict[str, Any]]:
        if not paragraphs:
            return []

        indexes = {
            0,
            len(paragraphs) // 4,
            len(paragraphs) // 2,
            (len(paragraphs) * 3) // 4,
            len(paragraphs) - 1,
        }
        structure: List[Dict[str, Any]] = []
        for index in sorted(indexes):
            paragraph = paragraphs[index]
            structure.append(
                {
                    "paragraph": index + 1,
                    "chars": len(paragraph),
                    "dialogue_markers": cls._count_dialogue_markers(paragraph),
                    "progression_markers": cls._count_progression_markers(paragraph),
                    "excerpt": cls._short_excerpt(paragraph),
                }
            )
        return structure

    @classmethod
    def _estimate_static_description_risk(cls, paragraphs: List[str]) -> Dict[str, int]:
        static_count = 0
        max_static_run = 0
        current_run = 0
        for paragraph in paragraphs:
            is_static = (
                len(paragraph) >= 80
                and cls._count_dialogue_markers(paragraph) == 0
                and cls._count_progression_markers(paragraph) == 0
            )
            if is_static:
                static_count += 1
                current_run += 1
                max_static_run = max(max_static_run, current_run)
            else:
                current_run = 0
        return {"static_paragraph_count": static_count, "max_static_run": max_static_run}

    @staticmethod
    def _format_structure_map(excerpt_payload: Dict[str, Any]) -> str:
        risk = excerpt_payload.get("static_description_risk") or {}
        lines = [
            (
                f"- 全文约 {excerpt_payload.get('total_chars', 0)} 字，"
                f"{excerpt_payload.get('paragraph_count', 0)} 段，"
                f"对话标记 {excerpt_payload.get('dialogue_marker_count', 0)} 处，"
                f"推进标记 {excerpt_payload.get('progression_marker_count', 0)} 处；"
                f"静态段落 {risk.get('static_paragraph_count', 0)} 段，"
                f"最长连续静态段 {risk.get('max_static_run', 0)} 段。"
            )
        ]
        for item in excerpt_payload.get("structure_map") or []:
            lines.append(
                "- P{paragraph} | {chars}字 | 对话{dialogue_markers} | 推进{progression_markers}: {excerpt}".format(
                    **item
                )
            )
        return "\n".join(lines)

    @staticmethod
    def _format_mission_checklist(chapter_mission: Optional[dict]) -> str:
        if not isinstance(chapter_mission, dict) or not chapter_mission:
            return ""

        lines: List[str] = []
        purpose = chapter_mission.get("chapter_purpose") or chapter_mission.get("purpose")
        if purpose:
            lines.append(f"- 本章目的：{purpose}")

        continuity = chapter_mission.get("continuity_anchor")
        if isinstance(continuity, dict):
            inherit = continuity.get("inherit_from_previous") or []
            deliver = continuity.get("deliver_to_next") or []
            if inherit:
                lines.append(f"- 必须承接：{'; '.join(str(item) for item in inherit[:4])}")
            if deliver:
                lines.append(f"- 必须递给下一章：{'; '.join(str(item) for item in deliver[:4])}")

        dialogue_strategy = chapter_mission.get("dialogue_strategy")
        if isinstance(dialogue_strategy, dict):
            purposes = dialogue_strategy.get("purpose") or dialogue_strategy.get("goals") or []
            if purposes:
                lines.append(f"- 对话必须承担：{'; '.join(str(item) for item in purposes[:4])}")

        scene_list = chapter_mission.get("scene_list") or []
        if isinstance(scene_list, list):
            for index, scene in enumerate(scene_list[:8], start=1):
                if not isinstance(scene, dict):
                    continue
                beats = []
                for key, label in (
                    ("goal", "目标"),
                    ("conflict", "阻碍"),
                    ("turn", "转折"),
                    ("emotion_shift", "情绪变化"),
                    ("dialogue_value", "对话功能"),
                    ("end_hook", "钩子"),
                ):
                    value = scene.get(key)
                    if value:
                        beats.append(f"{label}={value}")
                if beats:
                    lines.append(f"- 场景{index}: " + "；".join(str(item) for item in beats))

        review_rules = chapter_mission.get("review_quality_rules") or []
        if isinstance(review_rules, list):
            for rule in review_rules[:6]:
                if rule:
                    lines.append(f"- 评审硬规则：{rule}")

        longform_context = chapter_mission.get("longform_review_context")
        if isinstance(longform_context, dict):
            cast_plan = longform_context.get("cast_plan") or {}
            foreshadowing_task = longform_context.get("foreshadowing_task") or {}
            focus_names = cast_plan.get("chapter_focus_names") or []
            must_resolve = foreshadowing_task.get("must_resolve") or []
            should_reinforce = foreshadowing_task.get("should_reinforce") or []
            avoid_forgetting = foreshadowing_task.get("avoid_forgetting") or []
            if focus_names:
                lines.append(
                    "- 长篇角色连续性：必须检查本章焦点角色 "
                    + ", ".join(str(item) for item in focus_names[:8])
                    + " 的状态承接和变化。"
                )
            if must_resolve or should_reinforce or avoid_forgetting:
                lines.append(
                    "- 伏笔/线索账本："
                    f" must_resolve={len(must_resolve)},"
                    f" should_reinforce={len(should_reinforce)},"
                    f" avoid_forgetting={len(avoid_forgetting)}；"
                    "选稿时必须优先看是否兑现这些任务。"
                )

        return "\n".join(lines)

    @classmethod
    def _extract_paragraph_window(cls, paragraphs: List[str], anchor_index: int, radius: int = 1) -> str:
        if not paragraphs:
            return ""
        safe_index = max(0, min(anchor_index, len(paragraphs) - 1))
        start = max(0, safe_index - radius)
        end = min(len(paragraphs), safe_index + radius + 1)
        return "\n\n".join(paragraphs[start:end]).strip()

    @classmethod
    def _find_keyword_window(cls, paragraphs: List[str], keywords: List[str], *, default_index: int = 0) -> str:
        if not paragraphs:
            return ""
        for idx, paragraph in enumerate(paragraphs):
            if any(keyword and keyword in paragraph for keyword in keywords):
                return cls._extract_paragraph_window(paragraphs, idx)
        return cls._extract_paragraph_window(paragraphs, default_index)

    @classmethod
    def _find_max_scored_window(cls, paragraphs: List[str], scorer) -> str:
        if not paragraphs:
            return ""
        best_index = 0
        best_score = None
        for idx, paragraph in enumerate(paragraphs):
            score = scorer(paragraph)
            if best_score is None or score > best_score:
                best_index = idx
                best_score = score
        return cls._extract_paragraph_window(paragraphs, best_index)

    @classmethod
    def _build_excerpt_payload(cls, content: str) -> Dict[str, Any]:
        text = str(content or "")
        total_chars = len(text)
        paragraphs = cls._split_paragraphs(text)
        dialogue_marker_count = cls._count_dialogue_markers(text)
        progression_marker_count = cls._count_progression_markers(text)
        middle_start = max((total_chars // 2) - 700, 0)
        return {
            "total_chars": total_chars,
            "paragraph_count": len(paragraphs),
            "dialogue_marker_count": dialogue_marker_count,
            "progression_marker_count": progression_marker_count,
            "structure_map": cls._build_structure_map(paragraphs),
            "static_description_risk": cls._estimate_static_description_risk(paragraphs),
            "head": text[:1400],
            "middle": text[middle_start: middle_start + 1400],
            "tail": text[-1400:],
            "first_conflict": cls._find_keyword_window(
                paragraphs,
                ["质问", "逼", "压", "拒绝", "反问", "冷笑", "却", "忽然", "突然", "翻脸", "门外", "脚步"],
            ),
            "dialogue_window": cls._find_max_scored_window(
                paragraphs,
                lambda paragraph: cls._count_dialogue_markers(paragraph) * 10 + sum(paragraph.count(keyword) for keyword in ("问", "答", "说", "笑", "冷", "盯", "逼")),
            ),
            "turn_window": cls._find_keyword_window(
                paragraphs,
                ["却", "忽然", "突然", "没想到", "谁知", "竟", "反而", "下一瞬", "然而"],
                default_index=max(0, len(paragraphs) // 2),
            ),
        }

    def _build_review_input(
        self, versions: List[str], chapter_mission: Optional[dict]
    ) -> str:
        """构建评审输入文本"""
        lines = []

        if chapter_mission:
            lines.append("[章节导演脚本]")
            lines.append(json.dumps(chapter_mission, ensure_ascii=False, indent=2))
            mission_checklist = self._format_mission_checklist(chapter_mission)
            if mission_checklist:
                lines.append("[导演脚本兑现清单]")
                lines.append(mission_checklist)
            lines.append("")

        lines.append("[待评审版本]")
        for i, content in enumerate(versions):
            lines.append(f"--- 版本 {i} ---")
            excerpt_payload = self._build_excerpt_payload(content)
            total_chars = excerpt_payload["total_chars"]
            lines.append(
                f"[版本概况] 原文共 {total_chars} 字，约 {excerpt_payload['paragraph_count']} 段，对话标记 {excerpt_payload['dialogue_marker_count']} 处。"
            )
            lines.append("[整章结构地图]")
            lines.append(self._format_structure_map(excerpt_payload))
            lines.append("请优先结合[整章结构地图]判断：是否存在连续静态描写、正文是否只是扩写氛围、对话是否真正改变局势、章节结尾是否把后果递给下一章。")
            lines.append("")
            if total_chars <= 3200:
                lines.append(content)
            else:
                lines.append("[开头片段]")
                lines.append(excerpt_payload["head"])
                lines.append("")
                lines.append("[中段片段]")
                lines.append(excerpt_payload["middle"])
                lines.append("")
                lines.append("[结尾片段]")
                lines.append(excerpt_payload["tail"])
                lines.append("")
                lines.append("[首个冲突片段]")
                lines.append(excerpt_payload["first_conflict"] or "（未提取到明显冲突片段）")
                lines.append("")
                lines.append("[最长对话片段]")
                lines.append(excerpt_payload["dialogue_window"] or "（未提取到高密度对话片段）")
                lines.append("")
                lines.append("[关键转折片段]")
                lines.append(excerpt_payload["turn_window"] or "（未提取到明显转折片段）")
                lines.append("")
                lines.append(
                    f"... (该版本较长，已截取开头/中段/结尾以及冲突/对话/转折关键区间，原文共 {total_chars} 字)"
                )
            lines.append("")

        lines.append("[评审要求]")
        lines.append("请按照评审流程，对上述版本进行对比分析，重点判断整章是否真正推进剧情、对话是否改变局势，并输出 JSON 格式的评审结果。")

        return "\n".join(lines)

    def _build_single_review_input(
        self,
        version: str,
        chapter_mission: Optional[dict],
    ) -> str:
        lines = []

        if chapter_mission:
            lines.append("[章节导演脚本]")
            lines.append(json.dumps(chapter_mission, ensure_ascii=False, indent=2))
            mission_checklist = self._format_mission_checklist(chapter_mission)
            if mission_checklist:
                lines.append("[导演脚本兑现清单]")
                lines.append(mission_checklist)
            lines.append("")

        lines.append("[待评审正文]")
        excerpt_payload = self._build_excerpt_payload(version)
        total_chars = excerpt_payload["total_chars"]
        lines.append("请优先结合[整章结构地图]判断：是否存在连续静态描写、正文是否只是扩写氛围、对话是否真正改变局势、章节结尾是否把后果递给下一章。")
        lines.append(
            f"[版本概况] 原文共 {total_chars} 字，约 {excerpt_payload['paragraph_count']} 段，对话标记 {excerpt_payload['dialogue_marker_count']} 处。"
        )
        lines.append("[整章结构地图]")
        lines.append(self._format_structure_map(excerpt_payload))
        lines.append("请优先结合[整章结构地图]判断：是否存在连续静态描写、正文是否只是扩写氛围、对话是否真正改变局势、章节结尾是否把后果递给下一章。")
        lines.append("")
        if total_chars <= 4200:
            lines.append(version)
        else:
            head = version[:2200]
            lines.append("[开头片段]")
            lines.append(head)
            lines.append("")
            lines.append("[中段片段]")
            lines.append(excerpt_payload["middle"])
            lines.append("")
            lines.append("[结尾片段]")
            lines.append(excerpt_payload["tail"])
            lines.append("")
            lines.append("[首个冲突片段]")
            lines.append(excerpt_payload["first_conflict"] or "（未提取到明显冲突片段）")
            lines.append("")
            lines.append("[最长对话片段]")
            lines.append(excerpt_payload["dialogue_window"] or "（未提取到高密度对话片段）")
            lines.append("")
            lines.append("[关键转折片段]")
            lines.append(excerpt_payload["turn_window"] or "（未提取到明显转折片段）")
            lines.append("")
            lines.append(f"...（正文较长，已截取开头/中段/结尾及冲突/对话/转折关键区间，原文共 {total_chars} 字）")

        lines.append("")
        lines.append("[评审要求]")
        lines.append(
            "请不要做版本对比，而是把这唯一版本当成正式候选稿做完整质量评审。"
            "请给出沉浸感、节奏、钩子、人物四项评分，指出关键问题，并给出明确修改建议。"
            "必须输出 JSON。"
        )
        lines.append(
            """```json
{
  "best_version_index": 0,
  "scores": {
    "immersion": 1,
    "pacing": 1,
    "hook": 1,
    "character": 1
  },
  "overall_evaluation": "整体评语",
  "critical_flaws": ["关键缺陷"],
  "refinement_suggestions": "具体优化建议",
  "final_recommendation": "是否建议采用当前版本"
}
```"""
        )
        return "\n".join(lines)

    async def _review_single_version(
        self,
        *,
        version: str,
        chapter_mission: Optional[dict],
        user_id: int,
    ) -> Optional[ReviewResult]:
        review_prompt = await self.prompt_service.get_prompt("editor_review")
        if not review_prompt:
            logger.warning("未配置 editor_review 提示词，无法执行单版本评审")
            return ReviewResult(
                best_version_index=0,
                scores={"immersion": 70, "pacing": 70, "hook": 70, "character": 70},
                overall_evaluation="单版本评审提示词缺失，已直接采用当前版本。",
                critical_flaws=[],
                refinement_suggestions="请补齐 editor_review 提示词后重新评审。",
                final_recommendation="暂时采用唯一版本",
                status="single_version_fallback",
            )

        review_input = self._build_single_review_input(version, chapter_mission)
        try:
            text_result = await call_generation_text(
                llm_service=self.llm_service,
                system_prompt=review_prompt,
                conversation_history=[{"role": "user", "content": review_input}],
                temperature=0.25,
                user_id=user_id,
                timeout=180.0,
                policy=GenerationCallPolicy(
                    stage_label="单候选版本 AI 评审",
                    progress_stage="review",
                    retry_attempts=2,
                    response_format="json_object",
                    max_tokens=4000,
                    retry_same_model_once=True,
                ),
            )
            cleaned = remove_think_tags(text_result.text)
            normalized = unwrap_markdown_json(cleaned)
            result = self._parse_review_response(normalized)
            result.raw_response = cleaned
            result.best_version_index = 0
            result.status = "single_version_reviewed" if result.status == "passed" else result.status
            logger.info("单版本 AI 评审完成")
            return result
        except Exception as exc:
            logger.warning("单版本 AI 评审失败，回退为基础评审结论: %s", exc)
            return ReviewResult(
                best_version_index=0,
                scores={"immersion": 68, "pacing": 68, "hook": 68, "character": 68},
                overall_evaluation="单版本 AI 评审异常，已回退为保守评审结果。",
                critical_flaws=[],
                refinement_suggestions="建议重新触发评审，或生成更多候选版本进行对比。",
                final_recommendation="暂时采用唯一版本",
                raw_response=str(exc),
                status="single_version_fallback",
            )

    def _parse_review_response(self, response: str) -> ReviewResult:
        """解析评审响应"""
        try:
            data = json.loads(response)
            best_version_index = data.get("best_version_index")
            if not isinstance(best_version_index, int):
                best_version_index = None
            return ReviewResult(
                best_version_index=best_version_index,
                scores=data.get("scores", {}),
                overall_evaluation=data.get("overall_evaluation", ""),
                critical_flaws=data.get("critical_flaws", []),
                refinement_suggestions=data.get("refinement_suggestions", ""),
                final_recommendation=data.get("final_recommendation", ""),
                status="passed" if best_version_index is not None else "failed",
            )
        except json.JSONDecodeError:
            logger.warning("评审响应不是有效 JSON，标记评审失败")
            return ReviewResult(
                best_version_index=None,
                scores={},
                overall_evaluation=response[:500] if response else "",
                critical_flaws=[],
                refinement_suggestions="",
                final_recommendation="解析失败，建议人工审核",
                status="failed",
            )

    async def auto_select_best_version(
        self,
        versions: List[str],
        chapter_mission: Optional[dict] = None,
        user_id: int = 0,
    ) -> int:
        """
        自动选择最佳版本的索引。

        Args:
            versions: 多个版本的正文内容
            chapter_mission: 章节导演脚本
            user_id: 用户 ID

        Returns:
            最佳版本的索引（从 0 开始）
        """
        result = await self.review_versions(versions, chapter_mission, user_id)
        if result:
            return result.best_version_index
        return 0  # 默认返回第一个版本
