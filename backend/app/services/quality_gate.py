"""Structural quality gate evaluation for chapter generation.

Extracted from pipeline_orchestrator.py to improve maintainability.
This module contains all quality gate related logic including:
- Quality issue labels and hints
- Structural quality gate building
- Quality gate status attachment
- Patch suggestion generation
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple


QUALITY_ISSUE_LABELS: Dict[str, str] = {
    "static_description_risk": "静态描写过多",
    "repeated_paragraph_flood": "整段重复灌水",
    "insufficient_dialogue_pressure": "有效对白不足",
    "chapter_progression_weak": "实质推进不足",
    "scene_fulfillment_weak": "场景兑现不足",
    "dialogue_does_not_change_state": "对白未改变局势",
    "ending_pressure_missing": "章末递压不足",
    "focus_character_missing": "焦点角色缺席",
    "continuity_inherit_missing": "承接锚点缺失",
    "continuity_inherit_late": "承接锚点过晚",
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


QUALITY_ISSUE_HINTS: Dict[str, str] = {
    "static_description_risk": "压缩独立景物/心理段，把篇幅改成动作回合、对话攻防和后果。",
    "repeated_paragraph_flood": "删掉整段照抄的重复内容，用新的事件、对话或后果补足字数。",
    "insufficient_dialogue_pressure": "补足至少两轮有效对白，让人物互相施压、拒绝、让步或反制。",
    "chapter_progression_weak": "把本章目标、冲突、转折写成可见事件，而不是停留在铺陈。",
    "scene_fulfillment_weak": "逐场兑现 scene_list 的目标、阻碍、反应、转折和钩子。",
    "dialogue_does_not_change_state": "让对白造成主动权、信息量、关系、风险或下一步选择的变化。",
    "ending_pressure_missing": "结尾必须交出危险、证据、期限、误会或代价，避免总结式平收。",
    "focus_character_missing": "让本章焦点角色实际出场、说话、行动或被明确处理。",
    "continuity_inherit_missing": "开场必须承接上一章锚点，不要让前文压力断裂。",
    "continuity_inherit_late": "把承接锚点前置到开场前三段，不要让读者等太久。",
    "critical_issues_remaining": "先消除自检报告的严重问题，再推进后续情节。",
    "score_below_floor": "整体结构分过低，需要重写关键段落或调整节奏。",
    "too_many_major_issues": "主要结构问题过多，建议拆分重写。",
    "critical_consistency_unresolved": "先解决严重连续性冲突，再继续写作。",
    "major_consistency_unresolved": "处理未解决的连续性冲突。",
    "dialogue_pressure_weak": "增强对白的攻防力度，让对话推动情节。",
    "mission_progression_weak": "围绕本章目标展开，确保目标有明显推进。",
    "word_count_far_below_target": "字数离目标过远，需要补充内容。",
    "event_density_weak": "增加事件密度，减少无效描写。",
    "state_change_interval_weak": "缩短状态变化间隔，保持节奏紧凑。",
    "scene_structure_weak": "完善场景结构，确保有明确的行动链。",
    "long_chapter_event_density_weak": "长章需要更高的事件密度。",
}


def build_quality_issue_summary(
    *,
    blockers: Optional[List[Dict[str, Any]]] = None,
    reason_codes: Optional[List[str]] = None,
    story_guard: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a human-readable quality issue summary from blockers and reason codes."""
    items: List[Dict[str, Any]] = []
    seen: set = set()

    def add(code: str, source: str = "quality_gate", message: Optional[str] = None) -> None:
        if not code or code in seen:
            return
        seen.add(code)
        items.append({
            "code": code,
            "label": QUALITY_ISSUE_LABELS.get(code, code),
            "source": source,
            "hint": QUALITY_ISSUE_HINTS.get(code, message or ""),
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
            and guard.get("dialogue_changes_state") is not False
            and guard.get("ending_pressure_passed", guard.get("ending_hook_detected", True)) is not False
            and guard.get("event_density_passed") is not False
            and guard.get("state_change_interval_passed") is not False
        )
        if guard.get("static_description_risk"):
            add("static_description_risk")
        if guard.get("repetition_risk"):
            add("repeated_paragraph_flood")
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
        if guard.get("expected_dialogue") and "dialogue_changes_state" in guard and guard.get("dialogue_changes_state") is False:
            add("dialogue_does_not_change_state")
        if int(guard.get("word_count") or 0) >= 1200 and guard.get("ending_pressure_passed", guard.get("ending_hook_detected", True)) is False:
            add("ending_pressure_missing")
        if guard.get("focus_character_missing"):
            add("focus_character_missing")
        if guard.get("continuity_inherit_missing"):
            add("continuity_inherit_missing")
        if guard.get("continuity_inherit_late"):
            add("continuity_inherit_late")
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


def quality_gate_patch_suggestion(issue: Dict[str, Any], chapter_mission: Optional[dict]) -> str:
    """Generate a patch suggestion for a quality gate issue."""
    code = str((issue or {}).get("code") or "")
    mission = chapter_mission or {}
    scenes = mission.get("scene_list") or []
    scene_goal = str((scenes[0] or {}).get("goal") or "本章场景目标") if scenes else "本章场景目标"
    dialogue = "、".join((mission.get("dialogue_strategy") or {}).get("purpose") or [])
    focus = "、".join(mission.get("focus_characters") or mission.get("character_focus") or [])
    inherit = "、".join((mission.get("continuity_anchor") or {}).get("inherit_from_previous") or [])
    turn = str((scenes[-1] or {}).get("turn") or "局势反转") if scenes else "局势反转"
    mapping = {
        "scene_fulfillment_weak": f"围绕场景目标：{scene_goal}，补齐目标、阻碍、转折与后果。",
        "scene_structure_weak": f"将场景目标：{scene_goal} 写成可见的行动链与结果。",
        "dialogue_does_not_change_state": f"围绕对白职责：{dialogue or '施压与反制'}，让对话改变主动权、信息或风险。",
        "focus_character_missing": f"让任务书指定的焦点人物在本章实际出场、行动、说话或被明确处理。（焦点人物：{focus or '本章焦点人物'}）",
        "continuity_inherit_missing": f"在开场承接上一章锚点：{inherit or '上一章未闭环压力'}。",
        "continuity_inherit_late": f"将承接锚点：{inherit or '上一章未闭环压力'} 前置到开场。",
        "reversal_missing": f"兑现或改写本章转折：{turn}，让后段出现可见局势变化。",
    }
    return mapping.get(code, str((issue or {}).get("message") or "按质量门问题做局部修复。"))
