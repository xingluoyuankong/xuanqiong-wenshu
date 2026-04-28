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
from typing import Dict, List, Optional

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
            response = await self.llm_service.get_llm_response(
                system_prompt=review_prompt,
                conversation_history=[{"role": "user", "content": review_input}],
                temperature=0.3,
                user_id=user_id,
                timeout=180.0,
            )
            cleaned = remove_think_tags(response)
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

    def _build_review_input(
        self, versions: List[str], chapter_mission: Optional[dict]
    ) -> str:
        """构建评审输入文本"""
        lines = []

        if chapter_mission:
            lines.append("[章节导演脚本]")
            lines.append(json.dumps(chapter_mission, ensure_ascii=False, indent=2))
            lines.append("")

        lines.append("[待评审版本]")
        for i, content in enumerate(versions):
            lines.append(f"--- 版本 {i} ---")
            total_chars = len(content)
            if total_chars <= 3200:
                lines.append(content)
            else:
                head = content[:1800]
                tail = content[-1400:]
                lines.append("[开头片段]")
                lines.append(head)
                lines.append("")
                lines.append("[结尾片段]")
                lines.append(tail)
                lines.append("")
                lines.append(
                    f"... (该版本较长，已截取开头 1800 字 + 结尾 1400 字，原文共 {total_chars} 字)"
                )
            lines.append("")

        lines.append("[评审要求]")
        lines.append("请按照评审流程，对上述版本进行对比分析，输出 JSON 格式的评审结果。")

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
            lines.append("")

        lines.append("[待评审正文]")
        total_chars = len(version)
        if total_chars <= 4200:
            lines.append(version)
        else:
            head = version[:2200]
            middle_start = max((total_chars // 2) - 700, 0)
            middle = version[middle_start: middle_start + 1400]
            tail = version[-1400:]
            lines.append("[开头片段]")
            lines.append(head)
            lines.append("")
            lines.append("[中段片段]")
            lines.append(middle)
            lines.append("")
            lines.append("[结尾片段]")
            lines.append(tail)
            lines.append("")
            lines.append(f"...（正文较长，已截取开头/中段/结尾片段，原文共 {total_chars} 字）")

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
            response = await self.llm_service.get_llm_response(
                system_prompt=review_prompt,
                conversation_history=[{"role": "user", "content": review_input}],
                temperature=0.25,
                user_id=user_id,
                timeout=180.0,
            )
            cleaned = remove_think_tags(response)
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
