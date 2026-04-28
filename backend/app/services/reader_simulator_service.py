"""
读者模拟器服务

目标：
1. 模拟不同读者类型的阅读反馈
2. 产出可用于后续优化链路的结构化问题
3. 给出是否建议继续流转到后续阶段的判定
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from .llm_service import LLMService
from .prompt_service import PromptService
from ..utils.json_utils import remove_think_tags, sanitize_json_like_text, unwrap_markdown_json

logger = logging.getLogger(__name__)


class ReaderType(str, Enum):
    CASUAL = "casual"
    HARDCORE = "hardcore"
    EMOTIONAL = "emotional"
    THRILL_SEEKER = "thrill_seeker"
    CRITIC = "critic"


class ReaderSimulatorService:
    READER_PROFILES: Dict[ReaderType, Dict[str, Any]] = {
        ReaderType.CASUAL: {
            "name": "休闲读者",
            "description": "希望轻松、顺畅、读起来不费劲。",
            "preferences": ["节奏明快", "信息清晰", "冲突直接"],
            "dislikes": ["大段说明", "拖沓", "设定堆砌"],
            "abandon_triggers": ["无聊", "看不懂", "推进太慢"],
            "thrill_sensitivity": 0.6,
            "patience": 0.4,
        },
        ReaderType.HARDCORE: {
            "name": "硬核读者",
            "description": "关注逻辑闭环、设定稳定、因果可靠。",
            "preferences": ["逻辑自洽", "伏笔回收", "设定稳定"],
            "dislikes": ["降智", "设定打架", "因果断裂"],
            "abandon_triggers": ["逻辑崩坏", "人设崩坏", "设定冲突"],
            "thrill_sensitivity": 0.4,
            "patience": 0.8,
        },
        ReaderType.EMOTIONAL: {
            "name": "情感读者",
            "description": "在乎情绪推进、关系变化、角色共鸣。",
            "preferences": ["情绪层次", "关系张力", "角色成长"],
            "dislikes": ["情绪空转", "关系不动", "角色工具化"],
            "abandon_triggers": ["情感线塌", "角色失真", "没有共鸣"],
            "thrill_sensitivity": 0.5,
            "patience": 0.7,
        },
        ReaderType.THRILL_SEEKER: {
            "name": "爽点读者",
            "description": "追求强反馈、强推进、强钩子。",
            "preferences": ["打脸", "反转", "升级", "奖励"],
            "dislikes": ["太慢", "太闷", "主角太弱"],
            "abandon_triggers": ["连续没爽点", "压抑过头", "章末没钩子"],
            "thrill_sensitivity": 1.0,
            "patience": 0.3,
        },
        ReaderType.CRITIC: {
            "name": "挑剔读者",
            "description": "关注文风、表达、叙事控制力。",
            "preferences": ["语言质感", "节奏控制", "现场感"],
            "dislikes": ["AI腔", "口水话", "重复啰嗦"],
            "abandon_triggers": ["文风太差", "表达空泛", "明显模板感"],
            "thrill_sensitivity": 0.3,
            "patience": 0.6,
        },
    }

    def __init__(self, db: AsyncSession, llm_service: LLMService, prompt_service: PromptService):
        self.db = db
        self.llm_service = llm_service
        self.prompt_service = prompt_service

    @staticmethod
    def _truncate_text(value: Any, limit: int = 120) -> str:
        text = str(value or "").strip()
        return text if len(text) <= limit else f"{text[:limit].rstrip()}..."

    @staticmethod
    def _safe_json_object(response: str) -> Optional[Dict[str, Any]]:
        content = sanitize_json_like_text(unwrap_markdown_json(remove_think_tags(response or "")))
        json_start = content.find("{")
        json_end = content.rfind("}") + 1
        if json_start < 0 or json_end <= json_start:
            return None
        try:
            data = json.loads(content[json_start:json_end])
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    def _normalize_single_feedback(
        self,
        reader_type: ReaderType,
        raw_feedback: Optional[Dict[str, Any]],
        thrill_score: float,
    ) -> Dict[str, Any]:
        feedback = dict(raw_feedback or {})
        profile = self.READER_PROFILES[reader_type]
        satisfaction = max(1, min(100, int(feedback.get("satisfaction", 50) or 50)))
        abandon_risk = max(1, min(10, int(feedback.get("abandon_risk", 5) or 5)))
        would_continue = bool(feedback.get("would_continue", satisfaction >= 60 and abandon_risk <= 6))
        highlights = [self._truncate_text(item, 80) for item in (feedback.get("highlights") or []) if str(item).strip()][:5]
        complaints = [self._truncate_text(item, 80) for item in (feedback.get("complaints") or []) if str(item).strip()][:5]
        emotions = [self._truncate_text(item, 40) for item in (feedback.get("emotions") or []) if str(item).strip()][:5]
        severity = "critical" if abandon_risk >= 8 else ("major" if abandon_risk >= 6 else "minor")
        diagnostics = [
            {
                "reader_type": reader_type.value,
                "severity": severity,
                "problem": complaint,
                "suggestion": f"优先修正“{complaint}”，提升{profile['name']}的持续阅读意愿",
            }
            for complaint in complaints[:3]
        ]
        return {
            "reader_type": reader_type.value,
            "reader_label": profile["name"],
            "satisfaction": satisfaction,
            "abandon_risk": abandon_risk,
            "would_continue": would_continue,
            "comment": self._truncate_text(feedback.get("comment") or "无法评价", 120),
            "emotions": emotions,
            "highlights": highlights,
            "complaints": complaints,
            "thrill_score": thrill_score,
            "patience": profile["patience"],
            "diagnostics": diagnostics,
        }

    @staticmethod
    def _aggregate_reader_diagnostics(reader_feedbacks: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        all_complaints: List[str] = []
        all_diagnostics: List[Dict[str, Any]] = []
        continue_count = 0
        highest_risk_reader: Optional[Dict[str, Any]] = None
        for feedback in reader_feedbacks.values():
            if feedback.get("would_continue"):
                continue_count += 1
            all_complaints.extend(feedback.get("complaints", []))
            all_diagnostics.extend(feedback.get("diagnostics", []))
            if highest_risk_reader is None or feedback.get("abandon_risk", 0) > highest_risk_reader.get("abandon_risk", 0):
                highest_risk_reader = feedback

        all_diagnostics.sort(key=lambda item: {"critical": 0, "major": 1, "minor": 2}.get(item.get("severity", "minor"), 3))
        common_complaints = [
            {"problem": problem, "count": count}
            for problem, count in Counter(all_complaints).most_common(5)
            if problem
        ]
        return {
            "continue_ratio": round(continue_count / max(len(reader_feedbacks), 1), 2),
            "common_complaints": common_complaints,
            "priority_issues": all_diagnostics[:8],
            "highest_risk_reader": highest_risk_reader,
        }

    async def simulate_reading_experience(
        self,
        chapter_content: str,
        chapter_number: int,
        reader_types: Optional[List[ReaderType]] = None,
        previous_summary: Optional[str] = None,
        user_id: int = 0,
    ) -> Dict[str, Any]:
        if reader_types is None:
            reader_types = list(ReaderType)

        results: Dict[str, Any] = {
            "overall_score": 0,
            "reader_feedbacks": {},
            "thrill_points": [],
            "abandon_risks": [],
            "hook_strength": {},
            "recommendations": [],
            "diagnostic_summary": {},
        }

        thrill_points = await self._detect_thrill_points(chapter_content, user_id)
        results["thrill_points"] = thrill_points

        total_score = 0
        for reader_type in reader_types:
            feedback = await self._simulate_single_reader(
                chapter_content=chapter_content,
                chapter_number=chapter_number,
                reader_type=reader_type,
                thrill_points=thrill_points,
                previous_summary=previous_summary,
                user_id=user_id,
            )
            results["reader_feedbacks"][reader_type.value] = feedback
            total_score += feedback.get("satisfaction", 50)

        results["overall_score"] = round(total_score / max(len(reader_types), 1), 1)
        results["abandon_risks"] = self._evaluate_abandon_risks(results["reader_feedbacks"])
        results["hook_strength"] = await self._evaluate_hook_strength(chapter_content, user_id)
        results["diagnostic_summary"] = self._aggregate_reader_diagnostics(results["reader_feedbacks"])
        results["reader_stage_decision"] = {
            "passed": results["overall_score"] >= 65 and not results["abandon_risks"],
            "continue_ratio": results["diagnostic_summary"].get("continue_ratio", 0),
            "top_issue_count": len(results["diagnostic_summary"].get("priority_issues", [])),
        }
        results["recommendations"] = self._generate_recommendations(results)
        return results

    async def _detect_thrill_points(self, chapter_content: str, user_id: int) -> List[Dict[str, Any]]:
        prompt = f"""请分析下面的章节内容，识别真正能刺激读者继续读下去的“爽点/强反馈点”。

[章节内容]
{chapter_content[:8000]}

请输出 JSON：
{{
  "thrill_points": [
    {{
      "type": "打脸/反转/升级/奖励/揭示/情感兑现/章末钩子",
      "description": "一句话描述",
      "intensity": 1,
      "position": "前段/中段/后段",
      "quote": "对应原文片段"
    }}
  ]
}}
"""
        try:
            response = await self.llm_service.get_llm_response(
                system_prompt="你是网络小说爽点分析编辑，只输出 JSON。",
                conversation_history=[{"role": "user", "content": prompt}],
                temperature=0.3,
                user_id=user_id,
                timeout=120.0,
            )
            data = self._safe_json_object(response)
            thrill_points = data.get("thrill_points", []) if data else []
            return thrill_points if isinstance(thrill_points, list) else []
        except Exception as exc:
            logger.warning("检测爽点失败: %s", exc)
            return []

    async def _simulate_single_reader(
        self,
        chapter_content: str,
        chapter_number: int,
        reader_type: ReaderType,
        thrill_points: List[Dict[str, Any]],
        previous_summary: Optional[str],
        user_id: int,
    ) -> Dict[str, Any]:
        profile = self.READER_PROFILES[reader_type]
        thrill_score = self._calculate_thrill_score(thrill_points, profile["thrill_sensitivity"])

        prompt = f"""你现在扮演一个“{profile['name']}”。

[读者画像]
- 描述：{profile['description']}
- 喜欢：{", ".join(profile['preferences'])}
- 讨厌：{", ".join(profile['dislikes'])}
- 弃书触发点：{", ".join(profile['abandon_triggers'])}

[上一章摘要]
{previous_summary or "这是第一章"}

[本章内容]
{chapter_content[:6000]}

[已识别爽点数]
{len(thrill_points)}

请以 JSON 输出：
{{
  "satisfaction": 1,
  "emotions": ["阅读时的情绪变化"],
  "highlights": ["本章亮点"],
  "complaints": ["本章槽点"],
  "would_continue": true,
  "abandon_risk": 1,
  "comment": "一句话评价"
}}
"""
        try:
            response = await self.llm_service.get_llm_response(
                system_prompt=f"你是一个真实的{profile['name']}，请只输出 JSON。",
                conversation_history=[{"role": "user", "content": prompt}],
                temperature=0.7,
                user_id=user_id,
                timeout=120.0,
            )
            data = self._safe_json_object(response)
            return self._normalize_single_feedback(reader_type, data, thrill_score)
        except Exception as exc:
            logger.warning("模拟 %s 失败: %s", profile["name"], exc)
            return self._normalize_single_feedback(
                reader_type,
                {
                    "satisfaction": 50,
                    "emotions": [],
                    "highlights": [],
                    "complaints": [],
                    "would_continue": True,
                    "abandon_risk": 5,
                    "comment": "无法评价",
                },
                thrill_score,
            )

    @staticmethod
    def _calculate_thrill_score(thrill_points: List[Dict[str, Any]], sensitivity: float) -> float:
        if not thrill_points:
            return 0.0
        total_intensity = sum(int(item.get("intensity", 5) or 5) for item in thrill_points)
        return round(min(100, total_intensity * 10) * sensitivity, 1)

    def _evaluate_abandon_risks(self, reader_feedbacks: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        risks: List[Dict[str, Any]] = []
        for reader_type, feedback in reader_feedbacks.items():
            abandon_risk = int(feedback.get("abandon_risk", 5) or 5)
            if abandon_risk >= 7:
                profile = self.READER_PROFILES.get(ReaderType(reader_type), {})
                risks.append(
                    {
                        "reader_type": reader_type,
                        "risk_level": abandon_risk,
                        "triggers": profile.get("abandon_triggers", []),
                        "complaints": feedback.get("complaints", []),
                    }
                )
        return sorted(risks, key=lambda item: item["risk_level"], reverse=True)

    async def _evaluate_hook_strength(self, chapter_content: str, user_id: int) -> Dict[str, Any]:
        ending = chapter_content[-500:] if len(chapter_content) > 500 else chapter_content
        prompt = f"""请分析下面章节结尾的钩子强度，只输出 JSON：

[章节结尾]
{ending}

{{
  "hook_strength": 1,
  "hook_type": "悬念/冲突/期待/情感/反转",
  "hook_description": "钩子描述",
  "improvement_suggestion": "如何增强"
}}
"""
        try:
            response = await self.llm_service.get_llm_response(
                system_prompt="你是网文钩子编辑，只输出 JSON。",
                conversation_history=[{"role": "user", "content": prompt}],
                temperature=0.3,
                user_id=user_id,
                timeout=60.0,
            )
            return self._safe_json_object(response) or {
                "hook_strength": 5,
                "hook_type": "未知",
                "hook_description": "",
                "improvement_suggestion": "",
            }
        except Exception as exc:
            logger.warning("评估钩子强度失败: %s", exc)
            return {
                "hook_strength": 5,
                "hook_type": "未知",
                "hook_description": "",
                "improvement_suggestion": "",
            }

    def _generate_recommendations(self, results: Dict[str, Any]) -> List[str]:
        recommendations: List[str] = []
        overall_score = float(results.get("overall_score", 50) or 50)
        if overall_score < 60:
            recommendations.append("整体读者满意度偏低，需要优先处理关键阅读障碍。")

        thrill_count = len(results.get("thrill_points", []))
        if thrill_count == 0:
            recommendations.append("本章缺少明确爽点或强反馈，建议补一个可感知的情节兑现点。")
        elif thrill_count < 2:
            recommendations.append("爽点数量偏少，建议提高中后段反馈密度。")

        abandon_risks = results.get("abandon_risks", [])
        if abandon_risks:
            high_risk = abandon_risks[0]
            complaints = ", ".join(high_risk.get("complaints", [])[:2]) or "存在高风险槽点"
            recommendations.append(f"{high_risk['reader_type']} 读者弃书风险偏高，主要风险点：{complaints}")

        hook_data = results.get("hook_strength", {})
        if isinstance(hook_data, dict) and int(hook_data.get("hook_strength", 5) or 5) < 6:
            recommendations.append(
                f"章末钩子偏弱，建议加强：{hook_data.get('improvement_suggestion') or '制造更明确的未解压力'}"
            )

        diagnostic_summary = results.get("diagnostic_summary") or {}
        common_complaints = diagnostic_summary.get("common_complaints") or []
        if common_complaints:
            recommendations.append(f"优先修复共性槽点：{common_complaints[0]['problem']}")

        top_issue = (diagnostic_summary.get("priority_issues") or [None])[0]
        if isinstance(top_issue, dict) and top_issue.get("problem"):
            recommendations.append(f"优先处理读者风险点：{top_issue['problem']}")

        return recommendations[:5]

    async def get_reader_simulation_context(self, chapter_content: str, chapter_number: int, user_id: int) -> str:
        results = await self.simulate_reading_experience(
            chapter_content=chapter_content,
            chapter_number=chapter_number,
            reader_types=[ReaderType.THRILL_SEEKER, ReaderType.CRITIC],
            user_id=user_id,
        )

        lines = [
            "# 读者模拟反馈",
            f"## 整体得分：{results['overall_score']}/100",
            "",
            f"## 爽点数量：{len(results['thrill_points'])}",
        ]
        for item in results["thrill_points"][:3]:
            lines.append(f"- [{item.get('type', '未知')}] {item.get('description', '')}（强度 {item.get('intensity', 0)}/10）")

        lines.append("")
        lines.append("## 读者反馈")
        for reader_type, feedback in results["reader_feedbacks"].items():
            lines.append(f"### {reader_type}")
            lines.append(f"- 满意度：{feedback.get('satisfaction')}/100")
            lines.append(f"- 弃书风险：{feedback.get('abandon_risk')}/10")
            lines.append(f"- 评价：{feedback.get('comment')}")

        if results["recommendations"]:
            lines.append("")
            lines.append("## 改进建议")
            for item in results["recommendations"]:
                lines.append(f"- {item}")

        return "\n".join(lines)
