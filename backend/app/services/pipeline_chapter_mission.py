# AIMETA P=pipeline_chapter_mission_mixin|R=mission_schema_normalize_fallback_generate|NR=pipeline_side_effects_except_llm_mission|E=PipelineChapterMissionMixin|X=internal|A=mixin|D=generation_call_service|S=none|RD=./README.ai
"""Chapter mission (director script) helpers extracted from PipelineOrchestrator.

Behavior-preserving mixin: method names/signatures stay the same so existing
call sites and tests continue to use PipelineOrchestrator.* unchanged.

Depends on host methods still provided by PipelineOrchestrator / other mixins:
_make_cache_key, _cache_get, _cache_set, _truncate_text, llm_service.
"""
from __future__ import annotations

import json
from copy import deepcopy
import re
import logging
from typing import Any, Dict, List, Optional

from ..services.generation_call_service import (
    GenerationCallPolicy,
    call_generation_text,
    parse_llm_json_object,
    validate_json_schema_subset,
)

logger = logging.getLogger(__name__)


class PipelineChapterMissionMixin:
    """Chapter mission schema, normalization, fallback and generation helpers."""

    @staticmethod
    def _resolve_chapter_mission_timeout(target_word_count: int) -> float:
        """Bound director-script waits so fallback can take over quickly.

        Cloud free providers (non-local base URL) often have high first-token
        latency; keep local CPA snappy but give cloud more room before fallback.
        """
        words = max(500, int(target_word_count or 0))
        if words < 1200:
            timeout = 60.0
        elif words < 2500:
            timeout = 75.0
        elif words < 4000:
            timeout = 90.0
        elif words < 5500:
            timeout = 105.0
        elif words < 7500:
            timeout = 120.0
        elif words < 10000:
            timeout = 150.0
        else:
            timeout = 180.0
        try:
            from ..core.config import settings
            base_url = str(getattr(settings, 'openai_base_url', '') or '').lower()
            if base_url and ('localhost' not in base_url) and ('127.0.0.1' not in base_url):
                timeout = min(300.0, timeout * 2.0)
        except Exception:
            pass
        return timeout

    @staticmethod
    def _resolve_chapter_mission_max_tokens(target_word_count: int) -> int:
        words = max(500, int(target_word_count or 0))
        # This is a compact execution plan, not chapter prose. Oversized budgets let
        # providers ramble and delay deterministic schema repair/fallback.
        if words < 1500:
            return 2600
        if words < 3000:
            return 4000
        if words < 6000:
            return 5000
        if words < 10000:
            return 6500
        return 8000
    @staticmethod
    def _build_chapter_mission_schema() -> Dict[str, Any]:
        string_array = {"type": "array", "items": {"type": "string"}}
        nullable_string = {"type": ["string", "null"]}
        scene_schema = {
            "type": "object",
            "required": [
                "scene",
                "location",
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
                "location": {"type": "string"},
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

        def normalize_string_list(value: Any, *, limit: int = 6) -> List[str]:
            if isinstance(value, str):
                values = [value]
            elif isinstance(value, list):
                values = value
            else:
                values = []
            cleaned: List[str] = []
            for item in values:
                text = str(item or "").strip()
                if text and text not in cleaned:
                    cleaned.append(text)
                if len(cleaned) >= limit:
                    break
            return cleaned

        continuity = normalized.get("continuity_anchor")
        if not isinstance(continuity, dict):
            continuity = {}
        def _is_placeholder_inherit(item: Any) -> bool:
            text = str(item or "").strip()
            if not text:
                return True
            markers = (
                "暂无",
                "这是第一章",
                "无历史章节",
                "暂无历史",
                "无上一章",
                "无前文",
                "无前文承接",
                "直接展开",
                "直接开场",
                "故事开始",
                "n/a",
                "none",
            )
            return any(marker in text for marker in markers)

        continuity["inherit_from_previous"] = [
            str(item).strip()
            for item in (continuity.get("inherit_from_previous") or [])
            if str(item).strip() and not _is_placeholder_inherit(item)
        ][:5]
        continuity["deliver_to_next"] = [
            str(item).strip()
            for item in (continuity.get("deliver_to_next") or [])
            if str(item).strip()
        ][:5]
        normalized["continuity_anchor"] = continuity

        def _scrub_placeholder_mission_values(value: Any) -> Any:
            markers = ("暂无", "这是第一章", "无历史章节", "暂无历史", "无上一章", "无前文", "无前文承接", "直接展开")
            if isinstance(value, str):
                text = value.strip()
                if not text:
                    return text
                if any(marker in text for marker in markers) and len(text) <= 40:
                    return ""
                return text
            if isinstance(value, list):
                cleaned = []
                for item in value:
                    scrubbed = _scrub_placeholder_mission_values(item)
                    if scrubbed in ("", None, [], {}):
                        continue
                    cleaned.append(scrubbed)
                return cleaned
            if isinstance(value, dict):
                return {
                    key: _scrub_placeholder_mission_values(item)
                    for key, item in value.items()
                }
            return value

        normalized = _scrub_placeholder_mission_values(normalized)


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

        focus_characters = normalize_string_list(
            [
                *(normalized.get("focus_characters") or [] if isinstance(normalized.get("focus_characters"), list) else [normalized.get("focus_characters")]),
                *(normalized.get("character_focus") or [] if isinstance(normalized.get("character_focus"), list) else [normalized.get("character_focus")]),
                normalized.get("pov"),
                normalized.get("pov_character"),
            ],
            limit=6,
        )
        normalized["focus_characters"] = focus_characters
        normalized["character_focus"] = focus_characters
        if focus_characters:
            normalized.setdefault("pov", focus_characters[0])
            normalized.setdefault("pov_character", focus_characters[0])

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
                    "location": "承接上章结尾的当前位置",
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
            item["location"] = str(item.get("location") or item.get("setting") or item.get("scene_place") or "").strip()
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
            for name in focus_characters:
                if name and name not in item["characters"] and name in "\n".join(str(item.get(field) or "") for field in ("goal", "conflict", "turn", "outcome", "payoff", "bridge", "end_hook")):
                    item["characters"].append(name)
            normalized_scenes.append(item)
        normalized["scene_list"] = normalized_scenes
        normalized["chapter_draft_contract"] = draft_contract
        normalized["schema_version"] = "chapter_mission.v2"
        return normalized

    @classmethod
    def _strengthen_repaired_chapter_mission(
        cls,
        mission: Dict[str, Any],
        anchor: Dict[str, Any],
        *,
        target_word_count: int,
    ) -> Dict[str, Any]:
        """Use deterministic anchors to make a locally repaired LLM plan executable."""

        strengthened = deepcopy(mission or {})

        def merge_strings(*values: Any, limit: int = 6) -> List[str]:
            merged: List[str] = []
            for value in values:
                candidates = value if isinstance(value, list) else [value]
                for item in candidates:
                    text = str(item or "").strip()
                    if text and text not in merged:
                        merged.append(text)
                    if len(merged) >= limit:
                        return merged
            return merged

        focus = merge_strings(
            strengthened.get("focus_characters"),
            strengthened.get("character_focus"),
            strengthened.get("pov"),
            strengthened.get("pov_character"),
            anchor.get("focus_characters"),
            anchor.get("character_focus"),
            limit=6,
        )
        if focus:
            strengthened["focus_characters"] = focus
            strengthened["character_focus"] = focus
            strengthened["pov"] = strengthened.get("pov") or focus[0]
            strengthened["pov_character"] = strengthened.get("pov_character") or focus[0]

        continuity = dict(strengthened.get("continuity_anchor") or {})
        anchor_continuity = anchor.get("continuity_anchor") or {}
        continuity["inherit_from_previous"] = merge_strings(
            continuity.get("inherit_from_previous"),
            anchor_continuity.get("inherit_from_previous"),
            limit=5,
        )
        continuity["deliver_to_next"] = merge_strings(
            continuity.get("deliver_to_next"),
            anchor_continuity.get("deliver_to_next"),
            limit=5,
        )
        strengthened["continuity_anchor"] = continuity

        foreshadowing = dict(strengthened.get("foreshadowing_tasks") or {})
        anchor_foreshadowing = anchor.get("foreshadowing_tasks") or {}
        for key in ("must_resolve", "should_reinforce", "may_plant", "avoid_forgetting"):
            foreshadowing[key] = merge_strings(foreshadowing.get(key), anchor_foreshadowing.get(key), limit=6)
        strengthened["foreshadowing_tasks"] = foreshadowing

        dialogue = dict(strengthened.get("dialogue_strategy") or {})
        anchor_dialogue = anchor.get("dialogue_strategy") or {}
        dialogue["purpose"] = merge_strings(dialogue.get("purpose"), anchor_dialogue.get("purpose"), limit=6)
        dialogue["subtext"] = merge_strings(dialogue.get("subtext"), anchor_dialogue.get("subtext"), limit=6)
        dialogue["pressure_change"] = str(
            dialogue.get("pressure_change") or anchor_dialogue.get("pressure_change") or "对白必须改变主动权、信息量或风险"
        ).strip()
        strengthened["dialogue_strategy"] = dialogue

        generic_values = {
            "制造明确阻碍",
            "让局势发生变化",
            "交出行动后果",
            "兑现一处线索、关系或压力",
            "吃住上一场后果并推出下一场",
            "对话必须改变主动权、信息量或风险",
            "留下下一段压力",
            "情绪必须变化",
        }
        scenes = [scene for scene in (strengthened.get("scene_list") or []) if isinstance(scene, dict)]
        anchor_scenes = [scene for scene in (anchor.get("scene_list") or []) if isinstance(scene, dict)]
        for index, scene in enumerate(scenes):
            anchor_scene = anchor_scenes[index] if index < len(anchor_scenes) else {}
            for field in ("conflict", "turn", "outcome", "payoff", "bridge", "dialogue_value", "end_hook"):
                current = str(scene.get(field) or "").strip()
                anchor_value = str(anchor_scene.get(field) or "").strip()
                if anchor_value and (not current or current in generic_values or len(current) < 6):
                    scene[field] = anchor_value
            scene_chars = merge_strings(scene.get("characters"), anchor_scene.get("characters"), focus, limit=8)
            if scene_chars:
                scene["characters"] = scene_chars
        strengthened["scene_list"] = scenes or anchor_scenes

        return cls._normalize_chapter_mission(strengthened, target_word_count)

    @classmethod
    def _build_fallback_chapter_mission(
        cls,
        *,
        outline_title: str,
        outline_summary: str,
        writing_notes: str,
        previous_summary: str = "",
        previous_tail: str = "",
        recent_track: str = "",
        plot_arc_digest: str = "",
        introduced_characters: Optional[List[str]] = None,
        planned_characters: Optional[List[str]] = None,
        all_characters: Optional[List[str]] = None,
        target_word_count: int,
        reason: str = "llm_unavailable",
    ) -> Dict[str, Any]:
        title = cls._truncate_text(outline_title or "本章", 80)
        raw_summary = str(outline_summary or "按当前章节大纲推进主线").strip() or "按当前章节大纲推进主线"
        summary = cls._truncate_text(raw_summary, 140)
        raw_notes = str(writing_notes or "").strip()
        planned = [name.strip() for name in (planned_characters or []) if isinstance(name, str) and name.strip()]
        introduced = [name.strip() for name in (introduced_characters or []) if isinstance(name, str) and name.strip()]
        known = [name.strip() for name in (all_characters or []) if isinstance(name, str) and name.strip()]

        def compact_lines(value: str, *, limit: int = 3) -> List[str]:
            text = str(value or "").strip()
            if not text:
                return []
            pieces = [
                piece.strip()
                for piece in re.split(r"[\n。！？!?；;]+", text)
                if piece and piece.strip()
            ]
            if not pieces:
                pieces = [text]
            cleaned: List[str] = []
            for piece in pieces:
                compact = cls._truncate_text(piece, 90)
                if len(compact) < 4:
                    continue
                cleaned.append(compact)
                if len(cleaned) >= limit:
                    break
            return cleaned

        def is_boilerplate_note(value: str) -> bool:
            text = str(value or "").strip()
            return text.startswith((
                "基础质量底线",
                "本章必须至少",
                "正文要尽量",
                "质量方向",
                "禁止泛化",
            ))

        note_segments = [
            item for item in compact_lines(raw_notes, limit=8)
            if not is_boilerplate_note(item)
        ]
        notes = cls._truncate_text(note_segments[0], 120) if note_segments else ""
        outline_segments = compact_lines(raw_summary, limit=6) or [summary]

        def rank_focus_names() -> List[str]:
            ordered_names: List[str] = []
            for name in [*planned, *introduced, *known]:
                if name and name not in ordered_names:
                    ordered_names.append(name)
            context = "\n".join([title, raw_summary, raw_notes])
            scored: List[Tuple[int, int, str]] = []
            for index, name in enumerate(ordered_names):
                score = 0
                if name in introduced:
                    score += 70
                if name in planned:
                    score += 45
                if name in context:
                    score += 20
                positive_patterns = (
                    f"{name}决定",
                    f"{name}目标",
                    f"{name}必须",
                    f"{name}要",
                    f"{name}去",
                    f"{name}拿",
                    f"{name}追",
                    f"{name}查",
                    f"{name}赴",
                )
                negative_patterns = (
                    f"以{name}相逼",
                    f"拿{name}逼",
                    f"{name}藏身",
                    f"{name}被威胁",
                    f"威胁{name}",
                    f"{name}不现身",
                    f"{name}仍未露面",
                    f"{name}线索",
                )
                score += sum(60 for pattern in positive_patterns if pattern in context)
                score -= sum(80 for pattern in negative_patterns if pattern in context)
                scored.append((score, -index, name))
            scored.sort(reverse=True)
            return [name for _score, _order, name in scored[:4]]

        focus_characters = rank_focus_names()

        def _is_ch1_or_empty_history_text(value: str) -> bool:
            text_value = str(value or "").strip()
            if not text_value:
                return True
            markers = (
                "暂无",
                "这是第一章",
                "无历史章节",
                "暂无历史",
                "无上一章",
                "无前文",
                "无前文承接",
            )
            return any(marker in text_value for marker in markers)

        inherit = [
            item
            for item in (compact_lines(previous_tail, limit=2) or compact_lines(previous_summary, limit=2))
            if not _is_ch1_or_empty_history_text(item)
        ]
        if recent_track and len(inherit) < 3:
            inherit.extend(
                item
                for item in compact_lines(recent_track, limit=2)
                if item not in inherit and not _is_ch1_or_empty_history_text(item)
            )
        deliver = outline_segments[:3]
        if notes and len(deliver) < 3:
            deliver.append(notes)
        if plot_arc_digest and len(deliver) < 3:
            deliver.extend(item for item in compact_lines(plot_arc_digest, limit=1) if item not in deliver)
        # Chapter 1 / empty history: do not invent fake previous-pressure obligations.
        if not inherit and _is_ch1_or_empty_history_text(previous_summary) and _is_ch1_or_empty_history_text(previous_tail):
            inherit = []
        else:
            inherit = inherit[:4] or ["承接上一章已经公开的行动后果和压力"]
        deliver = deliver[:4] or [summary]

        dialogue_purpose = ["试探关键信息", "让主动权或风险发生变化"]
        if focus_characters:
            dialogue_purpose.insert(0, "让" + "、".join(focus_characters[:2]) + "在冲突中推进选择")

        scene_count = 3 if target_word_count >= 2200 else 2
        # Prefer concrete outline/title tokens so scene fulfillment scoring can match prose.
        concrete_conflict = notes or (
            f"{outline_segments[0]} 受阻" if outline_segments else f"《{title}》目标受阻"
        )
        concrete_turn = (
            outline_segments[1]
            if len(outline_segments) > 1
            else (deliver[0] if deliver else f"{title}关键信息翻转")
        )
        concrete_outcome = (
            outline_segments[2]
            if len(outline_segments) > 2
            else (deliver[0] if deliver else f"付出代价推进《{title}》")
        )
        concrete_hook = deliver[-1] if deliver else (outline_segments[-1] if outline_segments else f"{title}留下下一章压力")
        scene_templates = [
            {
                "scene": "1",
                "goal": outline_segments[0] if outline_segments else f"落地《{title}》的行动目标",
                "conflict": concrete_conflict,
                "turn": concrete_turn,
                "outcome": concrete_outcome,
                "payoff": inherit[0] if inherit else concrete_outcome,
                "bridge": outline_segments[1] if len(outline_segments) > 1 else f"把《{title}》冲突推向对峙",
                "dialogue_value": notes or "对话必须承担试探、压迫或反制",
                "end_hook": concrete_hook,
                "characters": focus_characters[:3],
            },
            {
                "scene": "2",
                "goal": outline_segments[1] if len(outline_segments) > 1 else summary,
                "conflict": notes or concrete_conflict,
                "turn": outline_segments[2] if len(outline_segments) > 2 else concrete_turn,
                "outcome": deliver[1] if len(deliver) > 1 else (deliver[0] if deliver else concrete_outcome),
                "payoff": deliver[-1] if deliver else concrete_hook,
                "bridge": f"带着《{title}》代价进入章末",
                "dialogue_value": notes or "每轮对白都要改变信息量或心理压力",
                "end_hook": concrete_hook,
                "characters": focus_characters[:4],
            },
        ]
        if scene_count >= 3:
            scene_templates.append({
                "scene": "3",
                "goal": outline_segments[3] if len(outline_segments) > 3 else "交出本章结果并把压力递到下一章",
                "conflict": "结果不能轻易完成，必须留下代价或新威胁",
                "turn": "最后一刻出现新的要求、发现或追兵压力",
                "outcome": deliver[-1],
                "payoff": "兑现本章标题、摘要或写作指令中的至少一个核心承诺",
                "bridge": "用行动后果而不是解释性总结收束",
                "dialogue_value": "章末对白只保留能改变下一步选择的信息",
                "end_hook": deliver[-1],
                "characters": focus_characters[:3],
            })

        ratios = cls._resolve_scene_execution_ratios(len(scene_templates), sequel_required=False)
        for index, scene in enumerate(scene_templates):
            ratio = ratios[index] if index < len(ratios) else 1 / max(1, len(scene_templates))
            scene["word_budget"] = max(260, int(max(500, target_word_count) * ratio))

        mission = {
            "macro_beat": f"兜底导演脚本：{title}",
            "chapter_purpose": f"{title}：{summary}",
            "pov": focus_characters[0] if focus_characters else None,
            "pov_character": focus_characters[0] if focus_characters else None,
            "character_focus": focus_characters,
            "focus_characters": focus_characters,
            "allowed_new_characters": [name for name in planned if name not in introduced][:4],
            "character_arc_task": (
                f"让{focus_characters[0]}在本章目标和代价之间做出可见选择"
                if focus_characters
                else "让核心行动产生可见选择、代价和后果"
            ),
            "continuity_anchor": {
                "inherit_from_previous": inherit,
                "deliver_to_next": deliver,
            },
            "dialogue_strategy": {
                "purpose": dialogue_purpose,
                "subtext": ["不要解释设定，用试探、隐瞒、反制推动信息差"],
                "pressure_change": "每个主要对话段落都要改变主动权、信息量或风险",
            },
            "scene_list": scene_templates,
            "foreshadowing_tasks": {
                "must_resolve": [],
                "should_reinforce": deliver[:2],
                "may_plant": ["章末递交下一章压力"],
                "avoid_forgetting": inherit[:2],
            },
            "sequel_required": True,
            "sequel_description": "章末用短余波确认代价、下一步选择或新威胁，不写成总结。",
            "mission_source": "deterministic_fallback",
            "fallback_reason": cls._truncate_text(reason, 120),
        }
        return cls._normalize_chapter_mission(mission, target_word_count)

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
            return self._build_fallback_chapter_mission(
                outline_title=outline_title,
                outline_summary=outline_summary,
                writing_notes=writing_notes,
                previous_summary=previous_summary,
                previous_tail=previous_tail,
                recent_track=recent_track,
                plot_arc_digest=plot_arc_digest,
                introduced_characters=introduced_characters,
                planned_characters=planned_characters,
                all_characters=all_characters,
                target_word_count=target_word_count,
                reason="missing chapter_plan prompt",
            )

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
正文硬上限：{int(target_word_count * 1.25)}（导演脚本的各场 word_budget 总和必须接近目标，不得超过硬上限）

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
- 只输出紧凑 JSON，不写解释、分析过程、正文示例或 Markdown；所有必填字段必须一次给全，缺省细节宁可短句明确。
"""

        schema = self._build_chapter_mission_schema()
        try:
            text_result = await call_generation_text(
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
                    max_tokens=self._resolve_chapter_mission_max_tokens(target_word_count),
                    soft_timeout_seconds=max(60.0, self._resolve_chapter_mission_timeout(target_word_count) * 0.6),
                    allow_truncated_response=True,
                    retry_same_model_once=False,
                ),
            )
            raw_mission, _normalized_text = parse_llm_json_object(text_result.text)
            schema_errors = validate_json_schema_subset(raw_mission, schema)
            mission = self._normalize_chapter_mission(raw_mission, target_word_count)
            if schema_errors:
                anchor_mission = self._build_fallback_chapter_mission(
                    outline_title=outline_title,
                    outline_summary=outline_summary,
                    writing_notes=writing_notes,
                    previous_summary=previous_summary,
                    previous_tail=previous_tail,
                    recent_track=recent_track,
                    plot_arc_digest=plot_arc_digest,
                    introduced_characters=introduced_characters,
                    planned_characters=planned_characters,
                    all_characters=all_characters,
                    target_word_count=target_word_count,
                    reason="local_schema_repair_anchor",
                )
                mission = self._strengthen_repaired_chapter_mission(
                    mission,
                    anchor_mission,
                    target_word_count=target_word_count,
                )
                mission["mission_source"] = "llm_local_repaired"
                mission["local_schema_repair_count"] = len(schema_errors)
                mission["local_schema_repairs"] = schema_errors[:12]
                logger.info(
                    "章节导演脚本本地补齐结构字段: project=%s chapter_title=%s repairs=%s",
                    blueprint_dict.get("id") or "",
                    outline_title,
                    "; ".join(schema_errors[:6]),
                )
            else:
                mission["mission_source"] = mission.get("mission_source") or "llm"
            await self._cache_set(cache_key, mission, expire=600)
            logger.info("章节导演脚本生成完成: macro_beat=%s", mission.get("macro_beat"))
            return mission
        except Exception as exc:
            logger.warning("生成章节导演脚本失败，将使用确定性兜底任务: %s", exc)
            mission = self._build_fallback_chapter_mission(
                outline_title=outline_title,
                outline_summary=outline_summary,
                writing_notes=writing_notes,
                previous_summary=previous_summary,
                previous_tail=previous_tail,
                recent_track=recent_track,
                plot_arc_digest=plot_arc_digest,
                introduced_characters=introduced_characters,
                planned_characters=planned_characters,
                all_characters=all_characters,
                target_word_count=target_word_count,
                reason=str(exc),
            )
            await self._cache_set(cache_key, mission, expire=120)
            return mission

