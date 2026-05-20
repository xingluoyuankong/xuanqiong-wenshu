# AIMETA P=小说API_项目和章节管理|R=小说CRUD_章节管理|NR=不含内容生成|E=route:GET_POST_/api/novels/*|X=http|A=小说CRUD_章节|D=fastapi,sqlalchemy|S=db|RD=./README.ai
import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.dependencies import get_current_user
from ...db.session import get_session
from ...db.session import AsyncSessionLocal
from ...schemas.novel import (
    Blueprint,
    BlueprintGenerationJobResponse,
    BlueprintGenerationResponse,
    BlueprintPatch,
    Chapter as ChapterSchema,
    ConverseRequest,
    ConverseResponse,
    NovelProject as NovelProjectSchema,
    NovelProjectSummary,
    NovelSectionResponse,
    NovelSectionType,
)
from ...schemas.user import User as UserSchema, UserInDB
from ...models import BlueprintGenerationJob, NovelProject
from ...services.export_service import ExportService
from ...services.import_service import ImportService
from ...services.generation_call_service import GenerationCallPolicy, call_generation_json, call_generation_text, is_retryable_http_exception
from ...services.llm_service import LLMService
from ...services.novel_service import NovelService
from ...services.prompt_service import PromptService
from ...utils.json_utils import remove_think_tags, sanitize_json_like_text, unwrap_markdown_json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/novels", tags=["Novels"])

_BLUEPRINT_JOBS: Dict[str, Dict[str, Any]] = {}
_BLUEPRINT_PROJECT_RUNS: Dict[str, str] = {}
_BLUEPRINT_JOB_LOCK = asyncio.Lock()
_BLUEPRINT_JOB_STALE_SECONDS = 2 * 60 * 60
_BLUEPRINT_JOB_HEARTBEAT_SECONDS = 45
_BLUEPRINT_ACTIVE_STATUSES = {"queued", "generating", "polishing"}

JSON_RESPONSE_INSTRUCTION = """
IMPORTANT: 你的回复必须是合法的 JSON 对象，并严格包含以下字段：
{
  "ai_message": "string",
  "ui_control": {
    "type": "single_choice | multi_choice | text_input",
    "options": [
      {"id": "option_1", "label": "string"}
    ],
    "placeholder": "string"
  },
  "conversation_state": {},
  "is_complete": false
}
不要输出额外的文本或解释。
"""

_CHARACTER_NAME_PLACEHOLDERS = {
    "主角",
    "男主",
    "女主",
    "男主角",
    "女主角",
    "主角a",
    "主角b",
    "主角1",
    "主角2",
    "角色1",
    "角色2",
    "角色a",
    "角色b",
    "protagonist",
    "maincharacter",
    "main_char",
    "hero",
    "heroine",
}


def _ensure_prompt(prompt: str | None, name: str) -> str:
    if not prompt:
        raise HTTPException(status_code=500, detail=f"未配置名为 {name} 的提示词，请联系管理员")
    return prompt


def _canonical_key(value: str) -> str:
    return "".join(ch for ch in str(value).strip().lower() if ch.isalnum() or ch == "_")


def _stringify_payload(value: Any, *, fallback: str = "") -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        labels = []
        for item in value:
            if isinstance(item, dict):
                label = str(item.get("label") or item.get("value") or item.get("id") or "").strip()
                if label:
                    labels.append(label)
            elif isinstance(item, str) and item.strip():
                labels.append(item.strip())
        if labels:
            return "；".join(labels)
    if isinstance(value, dict):
        for key in ("ai_message", "message", "content", "text", "value"):
            nested = value.get(key)
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
    return fallback.strip()


def _normalize_ui_control(raw_control: Any) -> Dict[str, Any]:
    default_placeholder = "请继续补充你的设定、冲突或写作方向。"
    if not isinstance(raw_control, dict):
        return {"type": "text_input", "placeholder": default_placeholder}

    normalized_control: Dict[str, Any] = {}
    control_type = str(raw_control.get("type") or "").strip().lower()
    raw_options = raw_control.get("options")
    options: List[Dict[str, str]] = []

    if isinstance(raw_options, list):
        for item in raw_options:
            if not isinstance(item, dict):
                continue
            option_id = str(item.get("id") or item.get("value") or "").strip()
            option_label = str(item.get("label") or item.get("value") or option_id).strip()
            if option_id and option_label:
                options.append({"id": option_id, "label": option_label})

    if control_type not in {"single_choice", "multi_choice", "text_input"}:
        control_type = "single_choice" if options else "text_input"

    normalized_control["type"] = control_type
    if options and control_type in {"single_choice", "multi_choice"}:
        normalized_control["options"] = options

    placeholder = str(raw_control.get("placeholder") or "").strip()
    if placeholder:
        normalized_control["placeholder"] = placeholder
    elif control_type == "text_input":
        normalized_control["placeholder"] = default_placeholder

    return normalized_control


def _normalize_converse_response_payload(parsed: Any, raw_response: str) -> Dict[str, Any]:
    fallback_message = _stringify_payload(raw_response, fallback="我已经收到你的想法，请继续补充。")
    default_payload = {
        "ai_message": fallback_message,
        "ui_control": {"type": "text_input", "placeholder": "请继续补充你的设定、冲突或写作方向。"},
        "conversation_state": {},
        "is_complete": False,
    }
    if isinstance(parsed, str):
        default_payload["ai_message"] = parsed.strip() or fallback_message
        return default_payload
    if not isinstance(parsed, dict):
        return default_payload

    normalized_map = {_canonical_key(key): value for key, value in parsed.items()}

    ai_message_value = None
    for key in ("ai_message", "message", "assistant_message", "reply"):
        candidate = normalized_map.get(key)
        if candidate is not None:
            ai_message_value = candidate
            break
    ai_message = _stringify_payload(ai_message_value, fallback=fallback_message) or fallback_message

    ui_control_raw = normalized_map.get("ui_control") or normalized_map.get("control") or normalized_map.get("uicontrol")
    if ui_control_raw is None:
        ui_control_raw = {
            "type": normalized_map.get("type"),
            "options": normalized_map.get("options"),
            "placeholder": normalized_map.get("placeholder"),
        }
    ui_control = _normalize_ui_control(ui_control_raw)

    conversation_state = normalized_map.get("conversation_state")
    if not isinstance(conversation_state, dict):
        conversation_state = {}

    is_complete = bool(normalized_map.get("is_complete") or normalized_map.get("complete"))
    ready_for_blueprint = normalized_map.get("ready_for_blueprint")

    normalized_payload = {
        "ai_message": ai_message,
        "ui_control": ui_control,
        "conversation_state": conversation_state,
        "is_complete": is_complete,
    }
    if ready_for_blueprint is not None:
        normalized_payload["ready_for_blueprint"] = bool(ready_for_blueprint)
    return normalized_payload


def _extract_latest_conversation_state(structured_dialogue: List[Dict[str, Any]]) -> Dict[str, Any]:
    for item in reversed(structured_dialogue):
        if item.get("role") != "assistant":
            continue
        state = item.get("conversation_state")
        if isinstance(state, dict) and state:
            return state
    return {}


def _build_compact_blueprint_context(
    formatted_history: List[Dict[str, str]],
    structured_dialogue: List[Dict[str, Any]],
    existing_blueprint: Blueprint | None = None,
) -> Dict[str, Any]:
    latest_state = _extract_latest_conversation_state(structured_dialogue)
    collected_info = latest_state.get("collected_info") if isinstance(latest_state, dict) else None
    compact_context: Dict[str, Any] = {
        "conversation_excerpt": formatted_history[-12:],
    }
    if isinstance(collected_info, dict) and collected_info:
        compact_context["collected_info"] = collected_info
    checklist = latest_state.get("checklist") if isinstance(latest_state, dict) else None
    if isinstance(checklist, dict) and checklist:
        compact_context["checklist"] = checklist
    if existing_blueprint and getattr(existing_blueprint, "title", None):
        compact_context["existing_blueprint"] = existing_blueprint.model_dump(exclude_none=True)
    return compact_context


def _build_story_constraint_profile(
    formatted_history: List[Dict[str, str]],
    structured_dialogue: List[Dict[str, Any]],
    *,
    project_title: str,
    existing_blueprint: Blueprint | None = None,
) -> Dict[str, Any]:
    latest_state = _extract_latest_conversation_state(structured_dialogue)
    collected_info = latest_state.get("collected_info") if isinstance(latest_state, dict) else {}
    checklist = latest_state.get("checklist") if isinstance(latest_state, dict) else {}
    recent_user_inputs = [
        item.get("content", "")
        for item in formatted_history
        if item.get("role") == "user" and str(item.get("content") or "").strip()
    ][-6:]
    recent_assistant_focus = [
        item.get("content", "")
        for item in formatted_history
        if item.get("role") == "assistant" and str(item.get("content") or "").strip()
    ][-4:]

    explicit_constraints: List[str] = []
    if isinstance(collected_info, dict):
        for key, value in collected_info.items():
            text = _stringify_payload(value)
            if text:
                explicit_constraints.append(f"{key}: {text}")

    unresolved_slots: List[str] = []
    if isinstance(checklist, dict):
        for key, value in checklist.items():
            if value is True:
                continue
            unresolved_slots.append(str(key))

    profile: Dict[str, Any] = {
        "project_title": project_title,
        "recent_user_inputs": recent_user_inputs,
        "recent_assistant_focus": recent_assistant_focus,
        "explicit_constraints": explicit_constraints[:20],
        "unresolved_slots": unresolved_slots[:20],
        "generation_principles": [
            "对话内容是约束来源，不是内容上限。",
            "如果长篇骨架关键槽位缺失，必须在不违背现有设定的前提下自动补全。",
            "补全结果必须服从当前项目已经形成的题材气质、人物目标、世界锚点和冲突方向。",
            "总纲目标是形成可拆章节、可支撑长篇连载的结构骨架，而不是把对话摘要改写得更长。",
        ],
    }
    if isinstance(collected_info, dict) and collected_info:
        profile["collected_info"] = collected_info
    if isinstance(checklist, dict) and checklist:
        profile["checklist"] = checklist
    if existing_blueprint and getattr(existing_blueprint, "title", None):
        profile["existing_blueprint"] = existing_blueprint.model_dump(exclude_none=True)
    return profile


def _has_substantive_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(_has_substantive_value(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_has_substantive_value(item) for item in value)
    return True


def _is_recoverable_blueprint_schema(blueprint: Blueprint | None) -> bool:
    if blueprint is None:
        return False
    if not str(getattr(blueprint, "title", "") or "").strip():
        return False
    if not str(getattr(blueprint, "one_sentence_summary", "") or "").strip():
        return False
    characters = getattr(blueprint, "characters", None)
    if not isinstance(characters, list) or not characters:
        return False
    has_novel_outline = isinstance(getattr(blueprint, "novel_outline", None), list) and len(getattr(blueprint, "novel_outline", None) or []) > 0
    has_chapter_outline = isinstance(getattr(blueprint, "chapter_outline", None), list) and len(getattr(blueprint, "chapter_outline", None) or []) > 0
    return has_novel_outline or has_chapter_outline


def _is_recoverable_for_requested_blueprint_stage(
    blueprint: Blueprint | None,
    requested_stage: str | None,
) -> bool:
    if not _is_recoverable_blueprint_schema(blueprint):
        return False

    stage = str(requested_stage or "").strip().lower()
    if stage == "chapter_outline":
        chapter_outline = getattr(blueprint, "chapter_outline", None)
        return isinstance(chapter_outline, list) and _has_complete_chapter_outline(chapter_outline)
    if stage == "novel_outline":
        novel_outline = getattr(blueprint, "novel_outline", None)
        return isinstance(novel_outline, list) and len(novel_outline) > 0
    return True


def _scan_longform_structure_gaps(blueprint_data: Dict[str, Any]) -> Dict[str, Any]:
    world_setting = blueprint_data.get("world_setting") if isinstance(blueprint_data.get("world_setting"), dict) else {}
    system_slots = {
        "era_background": world_setting.get("era_background"),
        "world_structure": world_setting.get("world_structure"),
        "power_system": world_setting.get("power_system"),
        "survival_system": world_setting.get("survival_system"),
        "life_system": world_setting.get("life_system"),
        "culture_system": world_setting.get("culture_system"),
        "civilization_system": world_setting.get("civilization_system"),
        "economy_system": world_setting.get("economy_system"),
        "social_structure": world_setting.get("social_structure"),
        "resource_system": world_setting.get("resource_system"),
        "belief_system": world_setting.get("belief_system"),
        "geography_system": world_setting.get("geography_system"),
        "faction_order": world_setting.get("faction_order"),
    }
    missing_world_slots = [key for key, value in system_slots.items() if not _has_substantive_value(value)]

    scalar_slots = {
        "title": blueprint_data.get("title"),
        "one_sentence_summary": blueprint_data.get("one_sentence_summary"),
        "full_synopsis": blueprint_data.get("full_synopsis"),
        "characters": blueprint_data.get("characters"),
        "relationships": blueprint_data.get("relationships"),
        "story_arcs": blueprint_data.get("story_arcs"),
        "volume_plan": blueprint_data.get("volume_plan"),
        "foreshadowing_system": blueprint_data.get("foreshadowing_system"),
    }
    missing_story_slots = []
    for key, value in scalar_slots.items():
        if not _has_substantive_value(value):
            missing_story_slots.append(key)

    return {
        "world_slots_missing": missing_world_slots,
        "story_slots_missing": missing_story_slots,
        "must_autofill": [
            "背景历史",
            "世界结构",
            "核心规则/力量或能力逻辑",
            "生存与生活运行逻辑",
            "文化与文明层",
            "资源与利益链",
            "长期冲突与阶段推进轴",
        ],
        "coverage_summary": {
            "world_slots_missing_count": len(missing_world_slots),
            "story_slots_missing_count": len(missing_story_slots),
        },
    }


def _normalize_character_name_token(value: Any) -> str:
    return "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum())


def _is_placeholder_character_name(value: Any) -> bool:
    normalized = _normalize_character_name_token(value)
    if not normalized:
        return True
    if normalized in _CHARACTER_NAME_PLACEHOLDERS:
        return True
    if normalized.startswith("角色") or normalized.startswith("主角"):
        return True
    return False


def _blueprint_has_valid_character_names(blueprint_data: Dict[str, Any]) -> bool:
    characters = blueprint_data.get("characters")
    if not isinstance(characters, list) or not characters:
        return False

    has_named_protagonist = False
    has_named_character = False
    for item in characters:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        role = str(item.get("role") or item.get("character_role") or item.get("importance") or "").strip().lower()
        if not _is_placeholder_character_name(name):
            has_named_character = True
            if any(token in role for token in ("主角", "protagonist", "main")):
                has_named_protagonist = True

    if has_named_protagonist:
        return True

    if not has_named_character:
        return False

    first_character = next((item for item in characters if isinstance(item, dict)), None)
    if not first_character:
        return False
    return not _is_placeholder_character_name(first_character.get("name"))


def _build_character_naming_profile(blueprint_data: Dict[str, Any], project_title: str) -> Dict[str, Any]:
    genre = str(blueprint_data.get("genre") or "").strip()
    style = str(blueprint_data.get("style") or "").strip()
    tone = str(blueprint_data.get("tone") or "").strip()
    target_audience = str(blueprint_data.get("target_audience") or "").strip()
    summary = str(blueprint_data.get("one_sentence_summary") or "").strip()
    synopsis = str(blueprint_data.get("full_synopsis") or "").strip()
    world_setting = blueprint_data.get("world_setting") if isinstance(blueprint_data.get("world_setting"), dict) else {}
    core_rules = str(world_setting.get("core_rules") or world_setting.get("core") or "").strip()
    locations = [
        str(item.get("name") or "").strip()
        for item in world_setting.get("key_locations", [])
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ]
    factions = [
        str(item.get("name") or "").strip()
        for item in world_setting.get("factions", [])
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ]

    naming_rules = [
        "主角姓名必须与题材、时代气质、世界观文化来源一致。",
        "东方玄幻、仙侠、古风、架空王朝题材默认使用自然中文姓名，避免现代网名感、英文名直译感和过度出戏的谐音名。",
        "都市、校园、现代题材允许更生活化命名，但避免过度古风或过度中二。",
        "西幻、海洋冒险、跨文明题材允许不同阵营有不同命名体系，但同一文化阵营内命名风格必须统一。",
        "主角名优先控制在 2-4 个汉字，朗读顺口、辨识度高，不要和核心配角高度同音。",
        "如果蓝图已有文化锚点、势力名称或地域名称，角色名必须与这些锚点相容。",
    ]

    return {
        "project_title": project_title,
        "genre": genre or "未指定",
        "style": style or "未指定",
        "tone": tone or "未指定",
        "target_audience": target_audience or "未指定",
        "one_sentence_summary": summary or "未提供",
        "full_synopsis_excerpt": synopsis[:500] or "未提供",
        "world_core_rules": core_rules or "未提供",
        "key_locations": locations[:8],
        "factions": factions[:8],
        "naming_rules": naming_rules,
    }


def _truncate_text(value: Any, limit: int = 320) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1].rstrip()}…"


def _compact_named_entries(items: Any, *, max_items: int, summary_keys: List[str]) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        return []
    compact: List[Dict[str, Any]] = []
    for item in items:
        if len(compact) >= max_items:
            break
        if not isinstance(item, dict):
            text = _truncate_text(item, 160)
            if text:
                compact.append({"text": text})
            continue
        record: Dict[str, Any] = {}
        for key in summary_keys:
            value = item.get(key)
            if isinstance(value, list):
                values = [_truncate_text(entry, 80) for entry in value[:4] if _truncate_text(entry, 80)]
                if values:
                    record[key] = values
            else:
                text = _truncate_text(value, 180)
                if text:
                    record[key] = text
        if record:
            compact.append(record)
    return compact


def _build_outline_source_context(blueprint_data: Dict[str, Any]) -> Dict[str, Any]:
    world_setting = blueprint_data.get("world_setting") if isinstance(blueprint_data.get("world_setting"), dict) else {}
    compact_world_setting = {
        "core_rules": _truncate_text(world_setting.get("core_rules") or world_setting.get("core"), 500),
        "era": _truncate_text(world_setting.get("era") or world_setting.get("time_period"), 120),
        "atmosphere": _truncate_text(world_setting.get("atmosphere") or world_setting.get("tone"), 120),
        "core_systems": _compact_system_payload(world_setting),
        "key_locations": _compact_named_entries(
            world_setting.get("key_locations"),
            max_items=8,
            summary_keys=["name", "description", "function", "danger"],
        ),
        "factions": _compact_named_entries(
            world_setting.get("factions"),
            max_items=8,
            summary_keys=["name", "goal", "description", "stance", "power_base"],
        ),
    }
    return {
        "title": _truncate_text(blueprint_data.get("title") or "未命名作品", 120),
        "genre": _truncate_text(blueprint_data.get("genre"), 80),
        "style": _truncate_text(blueprint_data.get("style"), 80),
        "tone": _truncate_text(blueprint_data.get("tone"), 80),
        "target_audience": _truncate_text(blueprint_data.get("target_audience"), 80),
        "one_sentence_summary": _truncate_text(blueprint_data.get("one_sentence_summary"), 220),
        "full_synopsis": _truncate_text(blueprint_data.get("full_synopsis"), 1500),
        "world_setting": compact_world_setting,
        "characters": _compact_named_entries(
            blueprint_data.get("characters"),
            max_items=10,
            summary_keys=["name", "role", "goal", "trait", "description", "arc", "background"],
        ),
        "relationships": _compact_named_entries(
            blueprint_data.get("relationships"),
            max_items=12,
            summary_keys=["character_a", "character_b", "relation_type", "description", "status"],
        ),
        "story_arcs": _compact_named_entries(
            blueprint_data.get("story_arcs"),
            max_items=8,
            summary_keys=["title", "theme", "goal", "conflict", "summary"],
        ),
        "volume_plan": _compact_named_entries(
            blueprint_data.get("volume_plan"),
            max_items=8,
            summary_keys=["volume", "title", "focus", "goal", "summary"],
        ),
        "foreshadowing_system": _compact_named_entries(
            blueprint_data.get("foreshadowing_system"),
            max_items=10,
            summary_keys=["plant", "payoff", "owner", "trigger", "summary"],
        ),
    }


def _build_chapter_outline_source_context(blueprint_data: Dict[str, Any]) -> Dict[str, Any]:
    context = _build_outline_source_context(blueprint_data)
    context["novel_outline"] = _compact_named_entries(
        blueprint_data.get("novel_outline"),
        max_items=6,
        summary_keys=["stage", "title", "goal", "main_conflict", "background", "ending_hook", "expected_chapter_range"],
    )
    context["story_arcs"] = _compact_named_entries(
        blueprint_data.get("story_arcs"),
        max_items=8,
        summary_keys=["title", "theme", "goal", "conflict", "summary"],
    )
    context["volume_plan"] = _compact_named_entries(
        blueprint_data.get("volume_plan"),
        max_items=8,
        summary_keys=["volume", "title", "focus", "goal", "summary"],
    )
    context["foreshadowing_system"] = _compact_named_entries(
        blueprint_data.get("foreshadowing_system"),
        max_items=10,
        summary_keys=["plant", "payoff", "owner", "trigger", "summary"],
    )
    return context


def _estimate_longform_complexity(blueprint_data: Dict[str, Any]) -> int:
    synopsis_length = len(str(blueprint_data.get("full_synopsis") or ""))
    complexity = synopsis_length
    complexity += len(blueprint_data.get("characters") or []) * 180
    complexity += len(blueprint_data.get("relationships") or []) * 120
    complexity += len(blueprint_data.get("story_arcs") or []) * 180
    complexity += len(blueprint_data.get("volume_plan") or []) * 180
    complexity += len(blueprint_data.get("foreshadowing_system") or []) * 140
    complexity += len(blueprint_data.get("novel_outline") or []) * 220
    world_setting = blueprint_data.get("world_setting") if isinstance(blueprint_data.get("world_setting"), dict) else {}
    complexity += len(_compact_system_payload(world_setting)) * 260
    return complexity


def _resolve_novel_outline_timeout_seconds(blueprint_data: Dict[str, Any]) -> float:
    complexity = _estimate_longform_complexity(blueprint_data)
    if complexity >= 11000:
        return 720.0
    if complexity >= 8000:
        return 600.0
    if complexity >= 5000:
        return 480.0
    if complexity >= 3000:
        return 360.0
    return 300.0


def _resolve_world_bible_timeout_seconds(blueprint_data: Dict[str, Any]) -> float:
    complexity = _estimate_longform_complexity(blueprint_data)
    world_setting = blueprint_data.get("world_setting") if isinstance(blueprint_data.get("world_setting"), dict) else {}
    compact_world = _compact_system_payload(world_setting)
    gap_count = len(_scan_longform_structure_gaps(blueprint_data).get("world_slots_missing") or [])
    timeout = 260.0 + gap_count * 18.0
    if complexity >= 9000:
        timeout += 140.0
    elif complexity >= 6000:
        timeout += 90.0
    elif complexity >= 3000:
        timeout += 50.0
    if not compact_world:
        timeout = max(timeout, 420.0)
    return min(timeout, 720.0)


def _resolve_outline_chunk_timeout_seconds(blueprint_data: Dict[str, Any], chunk_size: int) -> float:
    complexity = _estimate_longform_complexity(blueprint_data)
    timeout = 180.0 + chunk_size * 45.0
    if complexity >= 9000:
        timeout += 120.0
    elif complexity >= 6000:
        timeout += 80.0
    elif complexity >= 3000:
        timeout += 40.0
    return min(timeout, 540.0)


def _resolve_chapter_batch_timeout_seconds(blueprint_data: Dict[str, Any], batch_size: int) -> float:
    complexity = _estimate_longform_complexity(blueprint_data)
    timeout = 110.0 + batch_size * 20.0
    if complexity >= 9000:
        timeout += 80.0
    elif complexity >= 6000:
        timeout += 50.0
    elif complexity >= 3000:
        timeout += 30.0
    return min(timeout, 320.0)


def _is_retryable_http_exception(exc: HTTPException) -> bool:
    return is_retryable_http_exception(exc)


async def _call_llm_with_stage_retries(
    *,
    llm_service: LLMService,
    system_prompt: str,
    conversation_history: List[Dict[str, str]],
    temperature: float,
    user_id: int,
    timeout: float,
    response_format: Optional[str] = "json_object",
    max_tokens: Optional[int] = None,
    top_p: Optional[float] = None,
    allow_truncated_response: bool = False,
    retry_same_model_once: bool = True,
    stage_label: str,
    progress_callback: Callable[[str, str], Awaitable[None]] | None = None,
    progress_stage: str = "generating",
    retry_attempts: int = 2,
) -> str:
    result = await call_generation_text(
        llm_service=llm_service,
        system_prompt=system_prompt,
        conversation_history=conversation_history,
        temperature=temperature,
        user_id=user_id,
        timeout=timeout,
        policy=GenerationCallPolicy(
            stage_label=stage_label,
            progress_stage=progress_stage,
            retry_attempts=retry_attempts,
            response_format=response_format,
            max_tokens=max_tokens,
            top_p=top_p,
            allow_truncated_response=allow_truncated_response,
            retry_same_model_once=retry_same_model_once,
        ),
        progress_callback=progress_callback,
    )
    return result.text


_WORLD_BIBLE_SLOT_GROUPS: List[Dict[str, Any]] = [
    {
        "label": "历史与世界格局",
        "message": "正在补全世界体系（历史背景 / 世界结构 / 地理秩序）",
        "fields": ["era_background", "world_structure", "geography_system", "faction_order"],
    },
    {
        "label": "力量与生存运行",
        "message": "正在补全世界体系（力量体系 / 生存生活逻辑）",
        "fields": ["power_system", "survival_system", "life_system", "resource_system"],
    },
    {
        "label": "文明与社会规则",
        "message": "正在补全世界体系（文化文明 / 经济社会 / 信仰秩序）",
        "fields": ["culture_system", "civilization_system", "economy_system", "social_structure", "belief_system"],
    },
]


def _compact_system_payload(world_setting: Dict[str, Any]) -> Dict[str, Any]:
    system_keys = [
        "system_blueprint",
        "era_background",
        "world_structure",
        "power_system",
        "survival_system",
        "life_system",
        "culture_system",
        "civilization_system",
        "economy_system",
        "social_structure",
        "technology_system",
        "resource_system",
        "belief_system",
        "geography_system",
        "faction_order",
    ]
    compact: Dict[str, Any] = {}
    for key in system_keys:
        value = world_setting.get(key)
        if isinstance(value, dict):
            nested = {sub_key: _truncate_text(sub_value, 260) for sub_key, sub_value in value.items() if _truncate_text(sub_value, 260)}
            if nested:
                compact[key] = nested
        else:
            text = _truncate_text(value, 420)
            if text:
                compact[key] = text
    return compact


def _select_world_system_payload(world_setting: Dict[str, Any], fields: List[str]) -> Dict[str, Any]:
    compact = _compact_system_payload(world_setting)
    return {key: compact[key] for key in fields if key in compact}



def _resolve_world_bible_segment_timeout_seconds(blueprint_data: Dict[str, Any], field_count: int) -> float:
    base_timeout = _resolve_world_bible_timeout_seconds(blueprint_data)
    scaled_timeout = max(220.0, base_timeout * max(0.42, min(0.82, field_count / 8)))
    return min(base_timeout, scaled_timeout)



def _merge_world_system_blueprint(world_setting: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(world_setting or {})
    system_blueprint = merged.get("system_blueprint") if isinstance(merged.get("system_blueprint"), dict) else {}
    for key, value in payload.items():
        if value in (None, "", [], {}):
            continue
        merged[key] = value
        system_blueprint[key] = value
    if system_blueprint:
        merged["system_blueprint"] = system_blueprint
    return merged


REQUIRED_OUTLINE_DEPTH_FIELDS = [
    "survival_and_life_progression",
    "cultural_and_civilizational_progression",
    "resource_and_operation_line",
    "emotional_core",
    "major_setpiece",
    "story_function",
]


def _outline_stage_has_depth(item: Dict[str, Any]) -> bool:
    if not isinstance(item, dict):
        return False
    if any(not str(item.get(key) or "").strip() for key in REQUIRED_OUTLINE_DEPTH_FIELDS):
        return False
    turning_points = item.get("turning_points") if isinstance(item.get("turning_points"), list) else []
    stage_tasks = item.get("stage_tasks") if isinstance(item.get("stage_tasks"), list) else []
    has_turning_points = any(str(value).strip() for value in turning_points)
    has_stage_tasks = any(str(value).strip() for value in stage_tasks)
    return has_turning_points or has_stage_tasks


def _is_chapter_outline_batch_complete(chapters: List[Dict[str, Any]], start_chapter: int, end_chapter: int) -> bool:
    expected = list(range(start_chapter, end_chapter + 1))
    actual = [
        int(item.get("chapter_number") or 0)
        for item in chapters
        if isinstance(item, dict) and start_chapter <= int(item.get("chapter_number") or 0) <= end_chapter
    ]
    return actual == expected


def _has_complete_chapter_outline(chapters: List[Dict[str, Any]]) -> bool:
    return _is_chapter_outline_batch_complete(chapters, 1, 12)


def _build_blueprint_checkpoint_patch(blueprint_data: Dict[str, Any]) -> Dict[str, Any]:
    patch: Dict[str, Any] = {}
    for key in [
        "one_sentence_summary",
        "full_synopsis",
        "world_setting",
        "characters",
        "relationships",
        "story_arcs",
        "volume_plan",
        "novel_outline",
        "foreshadowing_system",
        "chapter_outline",
    ]:
        if key in blueprint_data and blueprint_data.get(key) is not None:
            patch[key] = blueprint_data.get(key)
    return patch


async def _checkpoint_blueprint_progress(
    *,
    novel_service: NovelService,
    project_id: str,
    blueprint_data: Dict[str, Any],
    progress_callback: Callable[[str, str], Awaitable[None]] | None = None,
    stage: str = "generating",
    message: str | None = None,
) -> None:
    patch = _build_blueprint_checkpoint_patch(blueprint_data)
    if not patch:
        return
    await novel_service.patch_blueprint(project_id, patch)
    if progress_callback is not None and message:
        await progress_callback(stage, message)


def _parse_expected_chapter_range(value: Any) -> tuple[int, int] | None:
    raw = str(value or "").strip().replace("章节", "").replace("章", "")
    if not raw:
        return None
    normalized = raw.replace("—", "-").replace("–", "-").replace("至", "-").replace("~", "-")
    parts = [part.strip() for part in normalized.split("-") if part.strip()]
    if len(parts) != 2:
        return None
    try:
        start = int(parts[0])
        end = int(parts[1])
    except ValueError:
        return None
    if start <= 0 or end < start:
        return None
    return start, end


def _validate_novel_outline_coherence(outline: List[Dict[str, Any]]) -> None:
    if len(outline) < 4:
        raise HTTPException(status_code=500, detail=f"小说总大纲生成失败，有效阶段数不足：{len(outline)}")
    if len(outline) > 12:
        raise HTTPException(status_code=500, detail=f"小说总大纲生成失败，阶段数超出上限：{len(outline)}")

    previous_stage = 0
    previous_end = 0
    seen_stages: set[int] = set()
    for item in outline:
        stage = int(item.get("stage") or 0)
        if stage <= 0 or stage in seen_stages:
            raise HTTPException(status_code=500, detail="小说总大纲生成失败，阶段编号重复或非法")
        if previous_stage and stage != previous_stage + 1:
            raise HTTPException(status_code=500, detail="小说总大纲生成失败，阶段编号不连续")
        seen_stages.add(stage)
        previous_stage = stage

        core_theme = str(item.get("core_theme") or "").strip()
        if not core_theme:
            raise HTTPException(status_code=500, detail=f"小说总大纲生成失败，第 {stage} 阶段缺少主题")

        chapter_range = _parse_expected_chapter_range(item.get("expected_chapter_range"))
        if chapter_range is None:
            raise HTTPException(status_code=500, detail=f"小说总大纲生成失败，第 {stage} 阶段章节范围非法")
        start, end = chapter_range
        if stage == 1 and start != 1:
            raise HTTPException(status_code=500, detail="小说总大纲生成失败，首阶段章节范围必须从第 1 章开始")
        if previous_end:
            if start <= previous_end:
                raise HTTPException(status_code=500, detail=f"小说总大纲生成失败，第 {stage} 阶段章节范围与前序重叠")
            if start != previous_end + 1:
                raise HTTPException(status_code=500, detail=f"小说总大纲生成失败，第 {stage} 阶段章节范围与前序不连续")
        previous_end = end


def _validate_novel_outline_depth(outline: List[Dict[str, Any]]) -> None:
    missing_axes: List[str] = []
    for item in outline:
        stage = int(item.get("stage") or 0)
        for key in REQUIRED_OUTLINE_DEPTH_FIELDS:
            if not str(item.get(key) or "").strip():
                missing_axes.append(f"stage{stage}:{key}")

        turning_points = item.get("turning_points") if isinstance(item.get("turning_points"), list) else []
        stage_tasks = item.get("stage_tasks") if isinstance(item.get("stage_tasks"), list) else []
        has_turning_points = bool([str(value).strip() for value in turning_points if str(value).strip()])
        has_stage_tasks = bool([str(value).strip() for value in stage_tasks if str(value).strip()])
        if not (has_turning_points or has_stage_tasks):
            missing_axes.append(f"stage{stage}:turning_points_or_stage_tasks")

    if missing_axes:
        preview = "、".join(missing_axes[:8])
        raise HTTPException(status_code=500, detail=f"小说总大纲生成失败，细化骨架不完整：{preview}")


def _normalize_novel_outline_stage(item: Dict[str, Any], index: int) -> Dict[str, Any] | None:
    title_value = str(item.get("title") or "").strip()
    core_theme_value = str(item.get("core_theme") or "").strip()
    goal_value = str(item.get("goal") or "").strip()
    conflict_value = str(item.get("main_conflict") or "").strip()
    background_value = str(item.get("background") or "").strip()
    character_progression_value = str(item.get("character_progression") or "").strip()
    world_progression_value = str(item.get("world_progression") or "").strip()
    faction_progression_value = str(item.get("faction_progression") or "").strip()
    power_progression_value = str(item.get("power_progression") or "").strip()
    climax_value = str(item.get("stage_climax") or "").strip()
    foreshadowing_value = str(item.get("foreshadowing_and_payoff") or "").strip()
    hook_value = str(item.get("ending_hook") or "").strip()
    expected_chapter_range_value = str(item.get("expected_chapter_range") or "").strip()
    key_events_raw = item.get("key_events") if isinstance(item.get("key_events"), list) else []
    key_events = [str(v).strip() for v in key_events_raw if str(v).strip()]
    required_detail_fields = [
        title_value,
        goal_value,
        conflict_value,
        background_value,
        character_progression_value,
        world_progression_value,
        faction_progression_value,
        power_progression_value,
        climax_value,
        foreshadowing_value,
        hook_value,
    ]
    if any(not field for field in required_detail_fields) or len(key_events) < 5 or _parse_expected_chapter_range(expected_chapter_range_value) is None:
        return None

    normalized = {
        "stage": int(item.get("stage") or index),
        "title": title_value,
        "core_theme": core_theme_value,
        "goal": goal_value,
        "main_conflict": conflict_value,
        "background": background_value,
        "character_progression": character_progression_value,
        "world_progression": world_progression_value,
        "faction_progression": faction_progression_value,
        "power_progression": power_progression_value,
        "key_events": key_events,
        "stage_climax": climax_value,
        "foreshadowing_and_payoff": foreshadowing_value,
        "ending_hook": hook_value,
        "expected_chapter_range": expected_chapter_range_value,
    }
    optional_text_fields = [
        "story_function",
        "emotional_core",
        "survival_and_life_progression",
        "cultural_and_civilizational_progression",
        "resource_and_operation_line",
        "major_setpiece",
    ]
    for key in optional_text_fields:
        value = str(item.get(key) or "").strip()
        if value:
            normalized[key] = value
    optional_list_fields = ["turning_points", "stage_tasks"]
    for key in optional_list_fields:
        raw_values = item.get(key) if isinstance(item.get(key), list) else []
        values = [str(value).strip() for value in raw_values if str(value).strip()]
        if values:
            normalized[key] = values
    return normalized


async def _generate_novel_world_bible(
    *,
    llm_service: LLMService,
    blueprint_data: Dict[str, Any],
    user_id: int,
    progress_callback: Callable[[str, str], Awaitable[None]] | None = None,
    checkpoint_callback: Callable[[Dict[str, Any], str, str], Awaitable[None]] | None = None,
) -> Dict[str, Any]:
    outline_context = _build_outline_source_context(blueprint_data)
    stage_titles = [
        {
            "stage": item.get("stage"),
            "title": item.get("title"),
            "goal": item.get("goal"),
            "main_conflict": item.get("main_conflict"),
        }
        for item in blueprint_data.get("novel_outline", [])
        if isinstance(item, dict)
    ]
    gap_report = _scan_longform_structure_gaps(blueprint_data)
    merged_world_setting = blueprint_data.get("world_setting") if isinstance(blueprint_data.get("world_setting"), dict) else {}

    for index, slot_group in enumerate(_WORLD_BIBLE_SLOT_GROUPS, start=1):
        if progress_callback is not None:
            await progress_callback("polishing", f"{slot_group['message']}（{index}/{len(_WORLD_BIBLE_SLOT_GROUPS)}）")

        existing_segment = _select_world_system_payload(merged_world_setting, slot_group["fields"])
        segment_gap_report = {
            "already_covered": [field for field in slot_group["fields"] if field in existing_segment],
            "missing": [field for field in slot_group["fields"] if field not in existing_segment],
            "global_summary": gap_report,
        }
        prompt = f"""
[任务目标]
请为长篇小说《{outline_context.get('title') or '未命名作品'}》补全“{slot_group['label']}”这一组世界系统槽位。
这一步不是改写剧情，而是只补当前这组世界骨架，让后续章节大纲和正文有足够厚的设定支撑。

[现有蓝图摘要]
{json.dumps(outline_context, ensure_ascii=False, indent=2)}

[现有阶段骨架]
{json.dumps(stage_titles, ensure_ascii=False, indent=2)}

[结构缺口扫描]
{json.dumps(segment_gap_report, ensure_ascii=False, indent=2)}

[已有世界系统片段]
{json.dumps(_compact_system_payload(merged_world_setting), ensure_ascii=False, indent=2)}

[本轮只允许输出的字段]
{json.dumps(slot_group['fields'], ensure_ascii=False, indent=2)}

[输出要求]
1. 只补当前这一组字段，不重写已有总纲走向，也不要输出别的字段。
2. 你必须严格依据蓝图材料去填写这些槽位的真实含义，不得为了凑字段而强行引入题材模板，也不要弱化蓝图里本来就存在的重点。
3. 每一项都必须是后续能直接拿来约束写作的具体内容，不能只写空话；如果某槽位在该作品里不是字面意义，就写出它在当前作品中的实际约束和运行逻辑。
4. 允许字段值为字符串或对象，但必须是合法 JSON。
5. 只输出 JSON，不解释。

[输出格式]
{{
  "world_bible": {{
    {', '.join([json.dumps(field, ensure_ascii=False) + ': ""' for field in slot_group['fields']])}
  }}
}}
"""
        raw = await _call_llm_with_stage_retries(
            llm_service=llm_service,
            system_prompt="你是长篇小说世界圣经构建器。你只负责补全当前给定的一组世界、文明、力量、生存、生活与文化体系字段。只输出 JSON。",
            conversation_history=[{"role": "user", "content": prompt}],
            temperature=0.2,
            user_id=user_id,
            timeout=_resolve_world_bible_segment_timeout_seconds(blueprint_data, len(slot_group["fields"])),
            response_format="json_object",
            max_tokens=2600,
            stage_label=slot_group["label"],
            progress_callback=progress_callback,
            progress_stage="polishing",
            retry_attempts=3,
        )
        payload = json.loads(sanitize_json_like_text(unwrap_markdown_json(remove_think_tags(raw))))
        world_bible = payload.get("world_bible") if isinstance(payload, dict) else None
        if not isinstance(world_bible, dict):
            raise HTTPException(status_code=500, detail=f"世界体系补全失败，{slot_group['label']} 未返回合法的 world_bible 结构")
        filtered_world_bible = {key: value for key, value in world_bible.items() if key in slot_group["fields"]}
        if len(filtered_world_bible) != len(slot_group["fields"]):
            missing_fields = [field for field in slot_group["fields"] if field not in filtered_world_bible]
            raise HTTPException(status_code=500, detail=f"世界体系补全失败，{slot_group['label']} 缺少字段：{', '.join(missing_fields)}")
        merged_world_setting = _merge_world_system_blueprint(merged_world_setting, filtered_world_bible)
        blueprint_data["world_setting"] = merged_world_setting
        if checkpoint_callback is not None:
            await checkpoint_callback(
                blueprint_data,
                "polishing",
                f"已保存世界骨架阶段结果（{index}/{len(_WORLD_BIBLE_SLOT_GROUPS)}）",
            )

    blueprint_data["world_setting"] = merged_world_setting
    return blueprint_data


async def _enrich_novel_outline_in_chunks(
    *,
    llm_service: LLMService,
    blueprint_data: Dict[str, Any],
    user_id: int,
    progress_callback: Callable[[str, str], Awaitable[None]] | None = None,
    checkpoint_callback: Callable[[Dict[str, Any], str, str], Awaitable[None]] | None = None,
) -> List[Dict[str, Any]]:
    raw_outline = blueprint_data.get("novel_outline") if isinstance(blueprint_data.get("novel_outline"), list) else []
    if not raw_outline:
        return []
    normalized_outline = [item for item in raw_outline if isinstance(item, dict)]
    enriched_outline: List[Dict[str, Any]] = []
    existing_by_stage = {int(item.get("stage") or 0): item for item in normalized_outline if isinstance(item, dict)}
    complexity = _estimate_longform_complexity(blueprint_data)
    chunk_size = 2 if complexity >= 6000 else 3
    total_chunks = (len(normalized_outline) + chunk_size - 1) // chunk_size
    outline_context = _build_outline_source_context(blueprint_data)
    world_systems = _compact_system_payload(
        blueprint_data.get("world_setting") if isinstance(blueprint_data.get("world_setting"), dict) else {}
    )

    for chunk_index, start in enumerate(range(0, len(normalized_outline), chunk_size), start=1):
        chunk = normalized_outline[start:start + chunk_size]
        chunk_stage_ids = [int(item.get("stage") or 0) for item in chunk if isinstance(item, dict)]
        existing_chunk = [existing_by_stage.get(stage_id) for stage_id in chunk_stage_ids]
        if existing_chunk and all(item is not None and _outline_stage_has_depth(item) for item in existing_chunk):
            enriched_outline.extend([dict(item) for item in existing_chunk if item is not None])
            if progress_callback is not None:
                await progress_callback("polishing", f"检测到已保存的总纲细化结果，跳过第 {chunk_index}/{total_chunks} 段")
            continue
        if progress_callback is not None:
            await progress_callback("polishing", f"正在细化小说总大纲（第 {chunk_index}/{total_chunks} 段）")
        prompt = f"""
[任务目标]
你将收到一部超长篇小说的世界骨架和一小段阶段总纲骨架。
请只细化当前这几段阶段，把它们扩写到足够支撑百万到千万字长篇的密度。

[全局蓝图摘要]
{json.dumps(outline_context, ensure_ascii=False, indent=2)}

[世界系统总表]
{json.dumps(world_systems, ensure_ascii=False, indent=2)}

[当前待细化阶段]
{json.dumps(chunk, ensure_ascii=False, indent=2)}

[细化要求]
1. 保留每个阶段原有的 stage 与主方向，不要改成别的故事。
2. 必须把 background、character_progression、world_progression、faction_progression、power_progression 写得更厚、更可执行。
3. 必须明确补足该阶段里的 survival_and_life_progression、cultural_and_civilizational_progression、resource_and_operation_line、emotional_core、major_setpiece、turning_points，但它们都要严格服从当前蓝图里真实存在的设定与矛盾，不要额外替换成某种题材模板。
4. 如果某字段在当前作品中不是字面意义，就写出它在当前作品中的实际承担内容，但字段名保持不变，方便系统后续处理。
5. key_events 至少 6 条，且要能支撑后续拆章节。
6. 每段要像“整卷策划案”，不是几句总结。
7. 只输出当前这些阶段的 JSON，不要输出别的阶段。

[输出格式]
{{
  "novel_outline": [
    {{
      "stage": 1,
      "title": "阶段标题",
      "core_theme": "",
      "goal": "",
      "main_conflict": "",
      "background": "",
      "character_progression": "",
      "world_progression": "",
      "faction_progression": "",
      "power_progression": "",
      "survival_and_life_progression": "",
      "cultural_and_civilizational_progression": "",
      "resource_and_operation_line": "",
      "emotional_core": "",
      "major_setpiece": "",
      "turning_points": ["", ""],
      "key_events": ["", "", "", "", "", ""],
      "stage_climax": "",
      "foreshadowing_and_payoff": "",
      "story_function": "",
      "ending_hook": "",
      "expected_chapter_range": "1-60章"
    }}
  ]
}}
"""
        raw = await _call_llm_with_stage_retries(
            llm_service=llm_service,
            system_prompt="你是超长篇小说分卷策划师。你只细化当前给定的阶段片段，并补足世界、生存、生活、文明和资源层面的推进。只输出 JSON。",
            conversation_history=[{"role": "user", "content": prompt}],
            temperature=0.2,
            user_id=user_id,
            timeout=_resolve_outline_chunk_timeout_seconds(blueprint_data, len(chunk)),
            response_format="json_object",
            max_tokens=5200,
            stage_label=f"小说总大纲细化第 {chunk_index}/{total_chunks} 段",
            progress_callback=progress_callback,
            progress_stage="polishing",
            retry_attempts=3,
        )
        payload = json.loads(sanitize_json_like_text(unwrap_markdown_json(remove_think_tags(raw))))
        items = payload.get("novel_outline") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            raise HTTPException(status_code=500, detail=f"小说总大纲细化失败，第 {chunk_index} 段未返回合法阶段列表")
        chunk_result: List[Dict[str, Any]] = []
        for local_index, item in enumerate(items, start=start + 1):
            if not isinstance(item, dict):
                continue
            normalized = _normalize_novel_outline_stage(item, local_index)
            if normalized is not None:
                chunk_result.append(normalized)
        if len(chunk_result) != len(chunk):
            raise HTTPException(status_code=500, detail=f"小说总大纲细化失败，第 {chunk_index} 段返回阶段数不完整")
        enriched_outline.extend(chunk_result)
        blueprint_data["novel_outline"] = sorted(enriched_outline, key=lambda item: int(item.get("stage") or 0))
        if checkpoint_callback is not None:
            await checkpoint_callback(
                blueprint_data,
                "polishing",
                f"已保存总纲细化结果（第 {chunk_index}/{total_chunks} 段）",
            )
    enriched_outline.sort(key=lambda item: int(item.get("stage") or 0))
    _validate_novel_outline_coherence(enriched_outline)
    _validate_novel_outline_depth(enriched_outline)
    return enriched_outline


async def _repair_blueprint_character_names(
    *,
    llm_service: LLMService,
    blueprint_data: Dict[str, Any],
    user_id: int,
    project_title: str,
    progress_callback: Callable[[str, str], Awaitable[None]] | None = None,
) -> Dict[str, Any]:
    if _blueprint_has_valid_character_names(blueprint_data):
        return blueprint_data

    if progress_callback is not None:
        await progress_callback("polishing", "正在补全主角与核心角色命名")

    naming_profile = _build_character_naming_profile(blueprint_data, project_title)

    repair_prompt = f"""
[任务]
你会收到一个已经生成好的小说蓝图 JSON，但其中角色命名不合格：主角可能没有具体姓名，或者仍然使用“主角/男主/女主/角色1/protagonist”这类占位词。

请在不改变故事方向的前提下，输出一份修复后的完整蓝图 JSON。

[命名风格约束]
{json.dumps(naming_profile, ensure_ascii=False, indent=2)}

[硬性要求]
1. 必须给主角一个具体、自然、适配题材、时代气质、世界文化来源与叙事调性的中文姓名，不能再使用任何占位词。
2. 所有核心角色都必须有可读姓名，不能出现“主角、男主、女主、角色1、角色A、protagonist、main character”这类名称。
3. 命名必须考虑作品的题材、世界观、势力命名、地域命名和整体文风，避免出现违和感极强的名字。
4. 同一文化圈/同一势力阵营内的角色名风格应统一；如果存在不同文明阵营，可以区分命名体系，但不能混乱。
5. 尽量保留原来的题材、世界观、冲突、总纲、章节结构与字段格式，不要删字段。
6. 如果原文中的 long synopsis、novel_outline、chapter_outline、relationships 等字段仍然写“主角”，请同步改成修复后的具体姓名，保证上下文一致。
7. 只输出合法 JSON 对象，不要解释。

[判定标准]
- 输出后的 blueprint.characters 不能为空。
- 第一主角必须有明确姓名。
- 角色姓名必须能直接用于后续写作与展示。
- 主角名需要读起来顺口、辨识度高，并与题材气质一致。

[项目标题]
{project_title}

[待修复蓝图 JSON]
{json.dumps(blueprint_data, ensure_ascii=False, indent=2)}
""".strip()

    repaired_result = await call_generation_json(
        llm_service=llm_service,
        system_prompt="你是小说蓝图修复器。你只负责修复角色命名与相关引用一致性，不重写故事方向。输出必须是合法 JSON 对象。",
        conversation_history=[{"role": "user", "content": repair_prompt}],
        temperature=0.2,
        user_id=user_id,
        timeout=180.0,
        policy=GenerationCallPolicy(
            stage_label="蓝图角色命名修复",
            progress_stage="polishing",
            retry_attempts=3,
            response_format="json_object",
            max_tokens=5000,
            allow_truncated_response=True,
            json_repair_attempts=1,
        ),
    )
    repaired_data = repaired_result.data
    if not isinstance(repaired_data, dict):
        raise HTTPException(status_code=500, detail="蓝图角色命名修复失败，系统未返回有效结构")
    if not _blueprint_has_valid_character_names(repaired_data):
        raise HTTPException(status_code=500, detail="蓝图角色命名修复失败，主角姓名仍不完整，请重试")
    return repaired_data


async def _generate_novel_outline(
    *,
    llm_service: LLMService,
    blueprint_data: Dict[str, Any],
    user_id: int,
    progress_callback: Callable[[str, str], Awaitable[None]] | None = None,
    checkpoint_callback: Callable[[Dict[str, Any], str, str], Awaitable[None]] | None = None,
) -> Dict[str, Any]:
    existing_outline = blueprint_data.get("novel_outline")
    if isinstance(existing_outline, list) and len(existing_outline) >= 4:
        try:
            _validate_novel_outline_coherence([item for item in existing_outline if isinstance(item, dict)])
            _validate_novel_outline_depth([item for item in existing_outline if isinstance(item, dict)])
            return blueprint_data
        except HTTPException:
            pass

    world_bible_prepared = False
    if not _compact_system_payload(
        blueprint_data.get("world_setting") if isinstance(blueprint_data.get("world_setting"), dict) else {}
    ):
        blueprint_data = await _generate_novel_world_bible(
            llm_service=llm_service,
            blueprint_data=blueprint_data,
            user_id=user_id,
            progress_callback=progress_callback,
            checkpoint_callback=checkpoint_callback,
        )
        world_bible_prepared = True

    outline_source_context = _build_outline_source_context(blueprint_data)
    structure_gap_report = _scan_longform_structure_gaps(blueprint_data)
    title = str(outline_source_context.get("title") or "未命名作品").strip() or "未命名作品"

    outline_system_prompt = (
        "你是资深长篇网文总策划，擅长把小说蓝图整理成完整的全书大纲与分卷路线。"
        "你只输出 JSON。"
    )
    outline_user_prompt = f"""
[任务目标]
为小说《{title}》生成真正可支撑长篇连载的“小说总大纲”。
这是蓝图之后、章节大纲之前的核心中间层，必须能指导整本书的剧情走向、世界扩张、人物成长、势力博弈和伏笔回收。
不是简略提纲，不是几个标题，而是后续拆章节时可以直接拿来工作的全书结构骨架。

[蓝图材料]
以下是已经压缩整理过的蓝图关键信息，请基于这些信息扩展出完整总纲，不要遗漏其核心约束：
{json.dumps(outline_source_context, ensure_ascii=False, indent=2)}

[结构缺口扫描]
以下是系统根据当前蓝图识别出的长篇结构缺口。你的职责不是停在现有信息上，而是在不违背现有设定的前提下，把这些对长篇成立至关重要但尚未充分展开的骨架补齐：
{json.dumps(structure_gap_report, ensure_ascii=False, indent=2)}

[硬性要求]
1. 输出 8-12 个阶段节点，每个节点代表一个大阶段、一卷或一大段剧情推进。
2. 每个阶段都必须写得足够详细，能够独立回答：这一阶段的背景是什么、主角在做什么、主要矛盾怎么升级、世界发生了什么变化、这一段结束后故事被推进到了哪里。
3. 必须严格根据蓝图材料本身来归纳这本书的主推进线、副推进线、世界扩张线、人物成长线与长期矛盾，不能套固定题材模板，也不要额外强调、压制或改写某一种题材倾向。
4. 如果蓝图同时包含多条推进轴，必须把它们编织进同一部长篇主线，形成统一的长期结构。
5. 每个阶段至少覆盖一个明确的世界变化、一个人物成长变化、一个外部格局变化；如果作品外部格局较弱，也要替换成与其真实设定对应的组织/关系/制度/环境变化。
6. 必须体现“背景/框架/要点/细节”，不能只写空泛口号，不能只列两三个事件。
7. 所有字段必须具体，可用于后续直接生成章节大纲。

[字段要求]
每个阶段必须包含以下字段：
- stage: 阶段序号
- title: 阶段标题
- core_theme: 本阶段主题
- goal: 主角或主线在本阶段的核心目标
- main_conflict: 本阶段核心冲突
- background: 本阶段开局时的局势、世界背景、资源/环境/时代状态
- character_progression: 主角与核心角色在本阶段的成长、关系变化、认知变化
- world_progression: 世界观信息在本阶段如何展开、升级或揭露
- faction_progression: 势力格局在本阶段如何变化
- power_progression: 修炼/能力/技术/文明体系在本阶段如何推进
- key_events: 5-8 个关键事件，必须具体
- stage_climax: 本阶段高潮事件
- foreshadowing_and_payoff: 本阶段埋下或回收的伏笔
- ending_hook: 阶段结尾如何把读者推进到下一阶段
- expected_chapter_range: 预估章节范围，如“1-60章”

[输出约束]
1. key_events 不少于 5 条。
2. background、character_progression、world_progression、faction_progression、power_progression、foreshadowing_and_payoff 都必须是具体完整句，不要写“待补充”。
3. 允许慢热，但不能空洞，必须清楚交代每一阶段承担的叙事职责。
4. 要让人看完后能直接据此继续拆章节，而不是还得重新构思框架。

[输出格式]
只输出 JSON：
{{
  "novel_outline": [
    {{
      "stage": 1,
      "title": "阶段标题",
      "core_theme": "本阶段主题",
      "goal": "本阶段目标",
      "main_conflict": "本阶段核心冲突",
      "background": "阶段背景与局势",
      "character_progression": "人物成长与关系推进",
      "world_progression": "世界展开与设定升级",
      "faction_progression": "势力格局变化",
      "power_progression": "力量/修炼/体系推进",
      "key_events": ["关键事件1", "关键事件2", "关键事件3", "关键事件4", "关键事件5"],
      "stage_climax": "阶段高潮",
      "foreshadowing_and_payoff": "伏笔埋设与回收",
      "ending_hook": "阶段收尾钩子",
      "expected_chapter_range": "1-60章"
    }}
  ]
}}
"""

    if progress_callback is not None:
        await progress_callback("generating", "正在锁定设定与长篇目标（世界规则 / 角色规模 / 伏笔回收）")
        await progress_callback("generating", "正在生成小说总大纲（阶段骨架首轮）")

    outline_raw = await _call_llm_with_stage_retries(
        llm_service=llm_service,
        system_prompt=outline_system_prompt,
        conversation_history=[{"role": "user", "content": outline_user_prompt}],
        temperature=0.25,
        user_id=user_id,
        timeout=_resolve_novel_outline_timeout_seconds(blueprint_data),
        response_format="json_object",
        max_tokens=7000,
        stage_label="小说总大纲骨架生成",
        progress_callback=progress_callback,
        progress_stage="generating",
        retry_attempts=3,
    )
    if progress_callback is not None:
        await progress_callback("generating", "正在解析小说总大纲骨架")
    outline_cleaned = remove_think_tags(outline_raw)
    outline_normalized = unwrap_markdown_json(outline_cleaned)
    outline_sanitized = sanitize_json_like_text(outline_normalized)
    outline_data = json.loads(outline_sanitized)

    raw_items = outline_data.get("novel_outline") if isinstance(outline_data, dict) else None
    if not isinstance(raw_items, list):
        raise HTTPException(status_code=500, detail="小说总大纲生成失败，AI 没有返回合法的 novel_outline 列表")

    normalized_outline: List[Dict[str, Any]] = []
    for index, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            continue
        normalized = _normalize_novel_outline_stage(item, index)
        if normalized is not None:
            normalized_outline.append(normalized)

    normalized_outline.sort(key=lambda item: int(item.get("stage") or 0))
    if progress_callback is not None:
        await progress_callback("generating", "正在校验小说总大纲骨架连续性")
    _validate_novel_outline_coherence(normalized_outline)

    blueprint_data["novel_outline"] = normalized_outline
    if checkpoint_callback is not None:
        await checkpoint_callback(blueprint_data, "generating", "已保存小说总大纲骨架")
    if not world_bible_prepared:
        if progress_callback is not None:
            await progress_callback("generating", "正在补全设定锁定包（世界运行 / 势力 / 生存生活逻辑）")
        blueprint_data = await _generate_novel_world_bible(
            llm_service=llm_service,
            blueprint_data=blueprint_data,
            user_id=user_id,
            progress_callback=progress_callback,
            checkpoint_callback=checkpoint_callback,
        )
    if progress_callback is not None:
        await progress_callback("polishing", "正在细化角色生命周期、伏笔回收窗口和阶段任务")
    blueprint_data["novel_outline"] = await _enrich_novel_outline_in_chunks(
        llm_service=llm_service,
        blueprint_data=blueprint_data,
        user_id=user_id,
        progress_callback=progress_callback,
        checkpoint_callback=checkpoint_callback,
    )
    return blueprint_data


async def _generate_executable_chapter_outline(
    *,
    llm_service: LLMService,
    blueprint_data: Dict[str, Any],
    user_id: int,
    progress_callback: Callable[[str, str], Awaitable[None]] | None = None,
    checkpoint_callback: Callable[[Dict[str, Any], str, str], Awaitable[None]] | None = None,
) -> Dict[str, Any]:
    existing_outline = blueprint_data.get("chapter_outline")
    if isinstance(existing_outline, list) and len(existing_outline) >= 12:
        return blueprint_data

    outline_source_context = _build_chapter_outline_source_context(blueprint_data)
    title = str(outline_source_context.get("title") or "未命名作品").strip() or "未命名作品"

    outline_system_prompt = (
        "你是资深长篇网文总策划，擅长把小说概念蓝图拆成真正可写的首卷章节大纲。"
        "你只输出 JSON。"
    )

    normalized_outline: List[Dict[str, Any]] = [item for item in existing_outline if isinstance(item, dict)] if isinstance(existing_outline, list) else []
    chapter_batches = [(1, 4), (5, 8), (9, 12)]
    for batch_index, (start_chapter, end_chapter) in enumerate(chapter_batches, start=1):
        existing_batch = [
            chapter for chapter in normalized_outline
            if start_chapter <= int(chapter.get("chapter_number") or 0) <= end_chapter
        ]
        if _is_chapter_outline_batch_complete(existing_batch, start_chapter, end_chapter):
            if progress_callback is not None:
                await progress_callback("generating", f"检测到已保存的章节批次，跳过第 {batch_index}/{len(chapter_batches)} 批（{start_chapter}-{end_chapter} 章）")
            continue
        outline_user_prompt = f"""
[任务目标]
为小说《{title}》正式生成首卷章节大纲的一个分段批次。
本次只生成第 {start_chapter}-{end_chapter} 章，必须与整部作品的蓝图、总纲、世界骨架和前序章节计划保持一致。

[作品蓝图]
以下是已经压缩整理过的作品蓝图，请严格服从这些设定与总纲，不要脱离原始方向：
{json.dumps(outline_source_context, ensure_ascii=False, indent=2)}

[已完成章节批次]
{json.dumps(existing_batch, ensure_ascii=False, indent=2)}

[输出要求]
1. 本次只输出第 {start_chapter} 到第 {end_chapter} 章，chapter_number 必须连续递增。
2. 每章必须输出：chapter_number、title、summary、character_focus、cast_delta、continuity_notes、foreshadowing_tasks、payoff_window。
3. summary 控制在 120-220 字，必须写清本章推进点、使用了总纲中的哪一层背景/冲突/人物关系/世界规则、以及章末钩子。
4. cast_delta 要说明本章新增/回归/退出的角色位，必须落入角色池、势力或功能性路人规则；不能凭空出现又消失。
5. foreshadowing_tasks 要区分 plant / reinforce / payoff / avoid_forgetting，不能只写“埋伏笔”。
6. 首卷节奏必须严格服从当前项目的总纲与世界骨架，自行判断这几章优先承担哪些职责，例如：建立故事入口、挂载核心关系、显影关键规则、引爆首轮矛盾、埋设长线钩子。不要套任何固定题材模板。
7. 必须严格服从小说总大纲中的阶段背景、外部格局变化、人物推进与体系升级，不能脱离总纲另起炉灶。
8. 标题和摘要必须具体，不要模板腔，不要空泛口号。

[输出格式]
只输出 JSON：
{{
  "chapter_outline": [
    {{
      "chapter_number": {start_chapter},
      "title": "标题",
      "summary": "摘要",
      "character_focus": ["本章角色焦点"],
      "cast_delta": {{"new": [], "returning": [], "exit_or_absent": [], "faction_roles": []}},
      "continuity_notes": ["承接点", "递给后文的压力"],
      "foreshadowing_tasks": {{"plant": [], "reinforce": [], "payoff": [], "avoid_forgetting": []}},
      "payoff_window": "计划回收窗口，如第8-12章"
    }}
  ]
}}
"""

        if progress_callback is not None:
            await progress_callback("generating", f"正在生成可执行章节大纲（第 {batch_index}/{len(chapter_batches)} 批，第 {start_chapter}-{end_chapter} 章）")

        outline_raw = await _call_llm_with_stage_retries(
            llm_service=llm_service,
            system_prompt=outline_system_prompt,
            conversation_history=[{"role": "user", "content": outline_user_prompt}],
            temperature=0.25,
            user_id=user_id,
            timeout=_resolve_chapter_batch_timeout_seconds(blueprint_data, end_chapter - start_chapter + 1),
            response_format="json_object",
            max_tokens=1800,
            stage_label=f"章节大纲第 {start_chapter}-{end_chapter} 章生成",
            progress_callback=progress_callback,
            progress_stage="generating",
            retry_attempts=3,
        )
        if progress_callback is not None:
            await progress_callback("generating", f"正在解析章节大纲批次（第 {start_chapter}-{end_chapter} 章）")
        outline_cleaned = remove_think_tags(outline_raw)
        outline_normalized = unwrap_markdown_json(outline_cleaned)
        outline_sanitized = sanitize_json_like_text(outline_normalized)
        outline_data = json.loads(outline_sanitized)

        raw_items = outline_data.get("chapter_outline") if isinstance(outline_data, dict) else None
        if not isinstance(raw_items, list):
            raise HTTPException(status_code=500, detail=f"章节大纲生成失败，第 {start_chapter}-{end_chapter} 章未返回合法列表")

        batch_outline: List[Dict[str, Any]] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            try:
                chapter_number = int(item.get("chapter_number"))
            except (TypeError, ValueError):
                continue
            title_value = str(item.get("title") or "").strip()
            summary_value = str(item.get("summary") or "").strip()
            if not title_value or not summary_value:
                continue
            if chapter_number < start_chapter or chapter_number > end_chapter:
                continue
            batch_outline.append(
                {
                    "chapter_number": chapter_number,
                    "title": title_value,
                    "summary": summary_value,
                    "character_focus": item.get("character_focus") if isinstance(item.get("character_focus"), list) else [],
                    "cast_delta": item.get("cast_delta") if isinstance(item.get("cast_delta"), dict) else {},
                    "continuity_notes": item.get("continuity_notes") if isinstance(item.get("continuity_notes"), list) else [],
                    "foreshadowing_tasks": item.get("foreshadowing_tasks") if isinstance(item.get("foreshadowing_tasks"), dict) else {},
                    "payoff_window": str(item.get("payoff_window") or "").strip(),
                }
            )

        batch_outline.sort(key=lambda chapter: chapter["chapter_number"])
        expected_numbers = list(range(start_chapter, end_chapter + 1))
        actual_numbers = [chapter["chapter_number"] for chapter in batch_outline]
        if actual_numbers != expected_numbers:
            raise HTTPException(status_code=500, detail=f"章节大纲生成失败，第 {start_chapter}-{end_chapter} 章编号不连续")
        normalized_outline = [
            chapter for chapter in normalized_outline
            if not (start_chapter <= int(chapter.get("chapter_number") or 0) <= end_chapter)
        ]
        normalized_outline.extend(batch_outline)
        normalized_outline.sort(key=lambda chapter: chapter["chapter_number"])
        blueprint_data["chapter_outline"] = normalized_outline[:]
        if checkpoint_callback is not None:
            await checkpoint_callback(
                blueprint_data,
                "generating",
                f"已保存章节批次结果（第 {batch_index}/{len(chapter_batches)} 批，第 {start_chapter}-{end_chapter} 章）",
            )

    normalized_outline.sort(key=lambda chapter: chapter["chapter_number"])
    chapter_numbers = [chapter["chapter_number"] for chapter in normalized_outline]
    if len(normalized_outline) < 12:
        raise HTTPException(status_code=500, detail=f"章节大纲生成失败，返回的有效章节数不足：{len(normalized_outline)}")
    if chapter_numbers[:12] != list(range(1, 13)):
        raise HTTPException(status_code=500, detail="章节大纲生成失败，前 12 章的章节号不连续或存在缺失")
    blueprint_data["chapter_outline"] = normalized_outline[:12]
    return blueprint_data


async def _polish_chapter_outline_quality(
    *,
    llm_service: LLMService,
    blueprint_data: Dict[str, Any],
    user_id: int,
    progress_callback: Callable[[str, str], Awaitable[None]] | None = None,
    checkpoint_callback: Callable[[Dict[str, Any], str, str], Awaitable[None]] | None = None,
) -> Dict[str, Any]:
    chapter_outline = blueprint_data.get("chapter_outline")
    if not isinstance(chapter_outline, list) or not chapter_outline:
        return blueprint_data

    normalized_chapter_outline = [item for item in chapter_outline if isinstance(item, dict)]
    if not normalized_chapter_outline:
        return blueprint_data

    one_sentence_summary = str(blueprint_data.get("one_sentence_summary") or "").strip()
    full_synopsis = str(blueprint_data.get("full_synopsis") or "").strip()
    characters = blueprint_data.get("characters") or []
    relationships = blueprint_data.get("relationships") or []
    world_setting = blueprint_data.get("world_setting") if isinstance(blueprint_data.get("world_setting"), dict) else {}
    novel_outline = blueprint_data.get("novel_outline") if isinstance(blueprint_data.get("novel_outline"), list) else []
    story_arcs = blueprint_data.get("story_arcs") if isinstance(blueprint_data.get("story_arcs"), list) else []
    volume_plan = blueprint_data.get("volume_plan") if isinstance(blueprint_data.get("volume_plan"), list) else []
    foreshadowing_system = blueprint_data.get("foreshadowing_system") if isinstance(blueprint_data.get("foreshadowing_system"), list) else []

    polish_system_prompt = (
        "你是资深长篇网文总策划，擅长把粗糙大纲扩成可支撑长篇连载的高密度章节工程图。"
        "你只输出 JSON。"
    )

    polished_map: Dict[int, Dict[str, Any]] = {}
    chapter_batches = [(1, 4), (5, 8), (9, 12)]
    for batch_index, (start_chapter, end_chapter) in enumerate(chapter_batches, start=1):
        batch_items = [
            item for item in normalized_chapter_outline
            if start_chapter <= int(item.get("chapter_number") or 0) <= end_chapter
        ]
        existing_lines = []
        for item in batch_items:
            chapter_no = item.get("chapter_number")
            title = str(item.get("title") or "").strip()
            summary = str(item.get("summary") or "").strip()
            if chapter_no is None:
                continue
            existing_lines.append(f"第{chapter_no}章｜{title}｜{summary}")
        if not existing_lines:
            continue

        polish_user_prompt = f"""
[作品定位]
一句话梗概：{one_sentence_summary or "暂无"}
长梗概：{full_synopsis or "暂无"}

[主要角色]
{json.dumps(characters, ensure_ascii=False)}

[主要关系]
{json.dumps(relationships, ensure_ascii=False)}

[世界骨架]
{json.dumps(_compact_system_payload(world_setting), ensure_ascii=False)}

[小说总大纲]
{json.dumps(_compact_named_entries(novel_outline, max_items=8, summary_keys=["stage", "title", "goal", "main_conflict", "background", "world_progression", "character_progression", "ending_hook", "expected_chapter_range"]), ensure_ascii=False)}

[故事弧线]
{json.dumps(_compact_named_entries(story_arcs, max_items=8, summary_keys=["title", "theme", "goal", "conflict", "summary"]), ensure_ascii=False)}

[卷计划]
{json.dumps(_compact_named_entries(volume_plan, max_items=8, summary_keys=["volume", "title", "focus", "goal", "summary"]), ensure_ascii=False)}

[伏笔系统]
{json.dumps(_compact_named_entries(foreshadowing_system, max_items=10, summary_keys=["plant", "payoff", "owner", "trigger", "summary"]), ensure_ascii=False)}

[本轮待润色章节]
{chr(10).join(existing_lines)}

[改写目标]
1. 本轮只改写第 {start_chapter}-{end_chapter} 章，不改章节号，保持章节顺序与主线连续。
2. 每章 summary 必须有明确冲突、人物目标/阻碍、关键转折、章末钩子。
3. summary 长度控制在 180-360 字，避免空泛描述。
4. 补全每章承担的长线职责，保证前承后接，不允许只写“发生了什么”，还要写“推进了什么”。
5. 强制输出以下字段：narrative_phase、chapter_role、suspense_hook、emotional_progression、character_focus、cast_delta、conflict_escalation、continuity_notes、foreshadowing、foreshadowing_tasks、payoff_window。
6. cast_delta 必须说明新增/回归/退出角色与势力位置；foreshadowing_tasks 必须说明本章回收、强化、禁忘和可新增伏笔。
7. 语言要具体、可直接落地写作，避免模板腔。

[输出格式]
只输出 JSON：
{{
  "chapters": [
    {{
      "chapter_number": {start_chapter},
      "title": "标题",
      "summary": "摘要",
      "narrative_phase": "章节所处叙事阶段",
      "chapter_role": "本章在全书中的职责",
      "suspense_hook": "章末钩子",
      "emotional_progression": "情绪如何变化",
      "character_focus": ["角色A", "角色B"],
      "cast_delta": {{"new": [], "returning": [], "exit_or_absent": [], "faction_roles": []}},
      "conflict_escalation": ["升级点1", "升级点2"],
      "continuity_notes": ["承接上一章的点", "为下一章预埋的点"],
      "foreshadowing": {{
        "plant": ["埋下的伏笔"],
        "payoff": ["本章回收的伏笔"]
      }},
      "foreshadowing_tasks": {{"plant": [], "reinforce": [], "payoff": [], "avoid_forgetting": []}},
      "payoff_window": "计划回收窗口"
    }}
  ]
}}
"""

        try:
            if progress_callback is not None:
                await progress_callback("polishing", f"正在润色章节大纲（第 {batch_index}/{len(chapter_batches)} 批，第 {start_chapter}-{end_chapter} 章）")
            polished_raw = await _call_llm_with_stage_retries(
                llm_service=llm_service,
                system_prompt=polish_system_prompt,
                conversation_history=[{"role": "user", "content": polish_user_prompt}],
                temperature=0.35,
                user_id=user_id,
                timeout=_resolve_chapter_batch_timeout_seconds(blueprint_data, end_chapter - start_chapter + 1),
                response_format=None,
                allow_truncated_response=True,
                stage_label=f"章节大纲第 {start_chapter}-{end_chapter} 章润色",
                progress_callback=progress_callback,
                progress_stage="polishing",
                retry_attempts=3,
            )
            if progress_callback is not None:
                await progress_callback("polishing", f"正在解析润色结果（第 {start_chapter}-{end_chapter} 章）")
            polished_cleaned = remove_think_tags(polished_raw)
            polished_normalized = unwrap_markdown_json(polished_cleaned)
            polished_sanitized = sanitize_json_like_text(polished_normalized)
            polished_data = json.loads(polished_sanitized)
        except Exception as exc:
            logger.warning("蓝图章节大纲润色失败，保留原始结果: %s", exc)
            continue

        polished_items = []
        if isinstance(polished_data, dict):
            raw_items = polished_data.get("chapters", [])
            if isinstance(raw_items, list):
                polished_items = raw_items
        elif isinstance(polished_data, list):
            polished_items = polished_data

        batch_saved = False
        for item in polished_items:
            if not isinstance(item, dict):
                continue
            try:
                chapter_no = int(item.get("chapter_number"))
            except (TypeError, ValueError):
                continue
            title = str(item.get("title") or "").strip()
            summary = str(item.get("summary") or "").strip()
            if chapter_no < start_chapter or chapter_no > end_chapter:
                continue
            if not title or not summary or len("".join(summary.split())) < 150:
                continue
            polished_map[chapter_no] = item
            batch_saved = True
        if batch_saved:
            merged_outline_snapshot: List[Dict[str, Any]] = []
            for item in normalized_chapter_outline:
                if not isinstance(item, dict):
                    continue
                chapter_no_raw = item.get("chapter_number")
                try:
                    chapter_no = int(chapter_no_raw)
                except (TypeError, ValueError):
                    merged_outline_snapshot.append(item)
                    continue
                if chapter_no in polished_map:
                    polished = dict(polished_map[chapter_no])
                    merged_outline_snapshot.append(
                        {
                            **item,
                            **{k: v for k, v in polished.items() if k != "chapter_number" and v is not None},
                        }
                    )
                else:
                    merged_outline_snapshot.append(item)
            normalized_chapter_outline = merged_outline_snapshot
            blueprint_data["chapter_outline"] = merged_outline_snapshot
            if checkpoint_callback is not None:
                await checkpoint_callback(
                    blueprint_data,
                    "polishing",
                    f"已保存章节润色结果（第 {batch_index}/{len(chapter_batches)} 批，第 {start_chapter}-{end_chapter} 章）",
                )

    if not polished_map:
        return blueprint_data

    merged_outline: List[Dict[str, Any]] = []
    for item in chapter_outline:
        if not isinstance(item, dict):
            continue
        chapter_no_raw = item.get("chapter_number")
        try:
            chapter_no = int(chapter_no_raw)
        except (TypeError, ValueError):
            merged_outline.append(item)
            continue
        if chapter_no in polished_map:
            polished = dict(polished_map[chapter_no])
            merged_outline.append(
                {
                    **item,
                    **{k: v for k, v in polished.items() if k != "chapter_number" and v is not None},
                }
            )
        else:
            merged_outline.append(item)

    blueprint_data["chapter_outline"] = merged_outline
    return blueprint_data


@router.post("", response_model=NovelProjectSchema, status_code=status.HTTP_201_CREATED)
async def create_novel(
    title: str = Body(...),
    initial_prompt: str = Body(...),
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    """为当前用户创建一个新的小说项目。"""
    user_id = int(current_user.id)
    novel_service = NovelService(session)
    project = await novel_service.create_project(user_id, title, initial_prompt)
    logger.info("用户 %s 创建项目 %s", user_id, project.id)
    return await novel_service.get_project_schema(project.id, user_id)


@router.post("/import", response_model=Dict[str, str], status_code=status.HTTP_201_CREATED)
async def import_novel(
    file: UploadFile,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> Dict[str, str]:
    """上传并导入小说文件。"""
    user_id = int(current_user.id)
    import_service = ImportService(session)
    with LLMService.daily_limit_scope(f"import:{user_id}:{file.filename or 'unknown'}"):
        project_id = await import_service.import_novel_from_file(user_id, file)
    logger.info("用户 %s 导入项目 %s", user_id, project_id)
    return {"id": project_id}


@router.get("", response_model=List[NovelProjectSummary])
async def list_novels(
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> List[NovelProjectSummary]:
    """列出用户的全部小说项目摘要信息。"""
    user_id = int(current_user.id)
    novel_service = NovelService(session)
    projects = await novel_service.list_projects_for_user(user_id)
    logger.info("用户 %s 获取项目列表，共 %s 个", user_id, len(projects))
    return projects


@router.get("/current-user", response_model=UserSchema)
async def get_current_user_profile(
    current_user: UserInDB = Depends(get_current_user),
) -> UserSchema:
    """返回当前运行态绑定的用户信息，供前端初始化用户态与诊断单用户绑定。"""
    user_id = int(current_user.id)
    logger.info("返回当前运行态用户：id=%s username=%s is_admin=%s", user_id, current_user.username, current_user.is_admin)
    return UserSchema.model_validate(current_user)


@router.get("/{project_id}", response_model=NovelProjectSchema)
async def get_novel(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    user_id = int(current_user.id)
    novel_service = NovelService(session)
    logger.info("用户 %s 查询项目 %s", user_id, project_id)
    return await novel_service.get_project_schema(project_id, user_id)


@router.get("/{project_id}/sections/{section}", response_model=NovelSectionResponse)
async def get_novel_section(
    project_id: str,
    section: NovelSectionType,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelSectionResponse:
    user_id = int(current_user.id)
    novel_service = NovelService(session)
    logger.info("用户 %s 获取项目 %s 的 %s 区段", user_id, project_id, section)
    return await novel_service.get_section_data(project_id, user_id, section)


@router.get("/{project_id}/chapters/{chapter_number}", response_model=ChapterSchema)
async def get_chapter(
    project_id: str,
    chapter_number: int,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> ChapterSchema:
    user_id = int(current_user.id)
    novel_service = NovelService(session)
    logger.info("用户 %s 获取项目 %s 第 %s 章", user_id, project_id, chapter_number)
    return await novel_service.get_chapter_schema(project_id, user_id, chapter_number)


@router.get("/{project_id}/export/txt")
async def export_novel_as_txt(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
):
    """导出小说为 TXT 格式"""
    user_id = int(current_user.id)
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, user_id)

    export_service = ExportService(session)
    content = await export_service.export_novel_as_txt(project_id)

    from fastapi.responses import Response
    filename = f"novel_{project_id}_{datetime.now().strftime('%Y%m%d')}.txt"
    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/{project_id}/export/docx")
async def export_novel_as_docx(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
):
    """导出小说为 DOCX 格式"""
    user_id = int(current_user.id)
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, user_id)

    export_service = ExportService(session)
    content = await export_service.export_novel_as_docx(project_id)

    from fastapi.responses import Response
    filename = f"novel_{project_id}_{datetime.now().strftime('%Y%m%d')}.docx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


from datetime import datetime


@router.delete("", status_code=status.HTTP_200_OK)
async def delete_novels(
    project_ids: List[str] = Body(...),
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> Dict[str, str]:
    user_id = int(current_user.id)
    novel_service = NovelService(session)
    await novel_service.delete_projects(project_ids, user_id)
    logger.info("用户 %s 删除项目 %s", user_id, project_ids)
    return {"status": "success", "message": f"成功删除 {len(project_ids)} 个项目"}


@router.post("/{project_id}/concept/converse", response_model=ConverseResponse)
async def converse_with_concept(
    project_id: str,
    request: ConverseRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> ConverseResponse:
    """与概念设计师（LLM）进行对话，引导蓝图筹备。"""
    user_id = int(current_user.id)
    novel_service = NovelService(session)
    prompt_service = PromptService(session)
    llm_service = LLMService(session)

    project = await novel_service.ensure_project_owner(project_id, user_id)

    history_records = await novel_service.list_conversations(project_id)
    logger.info(
        "项目 %s 概念对话请求，用户 %s，历史记录 %s 条",
        project_id,
        user_id,
        len(history_records),
    )
    conversation_history = [
        {"role": record.role, "content": record.content}
        for record in history_records
    ]
    user_content = json.dumps(request.user_input, ensure_ascii=False)
    conversation_history.append({"role": "user", "content": user_content})

    system_prompt = _ensure_prompt(await prompt_service.get_prompt("concept"), "concept")
    system_prompt = f"{system_prompt}\n{JSON_RESPONSE_INSTRUCTION}"

    with LLMService.daily_limit_scope(f"concept:{project_id}:{user_id}"):
        llm_response = await llm_service.get_llm_response(
            system_prompt=system_prompt,
            conversation_history=conversation_history,
            temperature=0.8,
            user_id=user_id,
            timeout=240.0,
        )
    llm_response = remove_think_tags(llm_response)

    try:
        normalized = unwrap_markdown_json(llm_response)
        sanitized = sanitize_json_like_text(normalized)
        parsed: Any = json.loads(sanitized)
    except json.JSONDecodeError as exc:
        logger.warning(
            "Concept converse returned non-standard JSON, fallback to normalized text response: project_id=%s user_id=%s error=%s",
            project_id,
            user_id,
            exc,
        )
        normalized = llm_response
        parsed = llm_response

    normalized_payload = _normalize_converse_response_payload(parsed, llm_response)

    await novel_service.append_conversation(project_id, "user", user_content)
    await novel_service.append_conversation(
        project_id,
        "assistant",
        json.dumps(normalized_payload, ensure_ascii=False),
    )

    logger.info("项目 %s 概念对话完成，is_complete=%s", project_id, normalized_payload.get("is_complete"))

    if normalized_payload.get("is_complete"):
        normalized_payload["ready_for_blueprint"] = True

    normalized_payload.setdefault("conversation_state", normalized_payload.get("conversation_state", {}))
    return ConverseResponse(**normalized_payload)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_blueprint_job_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        normalized = raw if raw.endswith("Z") or "+" in raw[10:] else f"{raw}Z"
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _normalize_blueprint_error_detail(detail: Any) -> tuple[str | None, str | None, bool | None]:
    if isinstance(detail, HTTPException):
        detail = detail.detail
    if isinstance(detail, dict):
        message = str(detail.get("message") or detail.get("detail") or "").strip() or None
        hint = str(detail.get("hint") or "").strip() or None
        detail_text = None
        if message and hint and hint != message:
            detail_text = f"{message} 提示：{hint}"
        else:
            detail_text = message or hint
        retryable = detail.get("retryable") if isinstance(detail.get("retryable"), bool) else None
        return message, detail_text, retryable
    if detail is None:
        return None, None, None
    text = str(detail).strip()
    return (text or None), (text or None), None



def _blueprint_error(
    code: str,
    message: str,
    *,
    detail: Any = None,
    retryable: bool = True,
) -> Dict[str, Any]:
    resolved_message, resolved_detail, resolved_retryable = _normalize_blueprint_error_detail(detail)
    return {
        "code": code,
        "message": resolved_message or message,
        "detail": resolved_detail,
        "retryable": retryable if resolved_retryable is None else resolved_retryable,
    }


def _normalize_blueprint_job_payload(job: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(job)
    payload.setdefault("progress_stage", payload.get("status") or "idle")
    payload.setdefault("progress_message", "")
    payload.setdefault("started_at", None)
    payload.setdefault("updated_at", payload.get("started_at"))
    payload.setdefault("blueprint", None)
    payload.setdefault("ai_message", None)
    error = payload.get("error")
    if isinstance(error, str) and error:
        payload["error"] = _blueprint_error("blueprint_generation_failed", "Blueprint generation failed", detail=error)
    elif not isinstance(error, dict):
        payload["error"] = None
    return payload


def _recover_stale_blueprint_job(job: Dict[str, Any]) -> Dict[str, Any]:
    recovered = _normalize_blueprint_job_payload(job)
    if recovered.get("status") not in _BLUEPRINT_ACTIVE_STATUSES:
        return recovered
    updated_at = _parse_blueprint_job_time(recovered.get("updated_at") or recovered.get("started_at"))
    if not updated_at:
        return recovered
    stale_seconds = int((datetime.now(timezone.utc) - updated_at).total_seconds())
    if stale_seconds < _BLUEPRINT_JOB_STALE_SECONDS:
        return recovered
    stage = str(recovered.get("progress_stage") or recovered.get("status") or "generating")
    original_message = str(recovered.get("progress_message") or "蓝图生成进行中")
    recovered.update(
        {
            "status": stage if stage in _BLUEPRINT_ACTIVE_STATUSES else "generating",
            "progress_stage": stage if stage in _BLUEPRINT_ACTIVE_STATUSES else "generating",
            "progress_message": f"{original_message}（已持续 {stale_seconds} 秒未刷新；系统仅提示，不再自动判死，可继续等待或手动取消）",
            "updated_at": _utc_now_iso(),
            "error": None,
        }
    )
    return recovered



def _fail_orphaned_blueprint_job(job: Dict[str, Any]) -> Dict[str, Any]:
    recovered = _normalize_blueprint_job_payload(job)
    if recovered.get("status") not in _BLUEPRINT_ACTIVE_STATUSES:
        return recovered
    stage = str(recovered.get("progress_stage") or recovered.get("status") or "generating")
    original_message = str(recovered.get("progress_message") or "蓝图生成进行中")
    recovered.update(
        {
            "status": stage if stage in _BLUEPRINT_ACTIVE_STATUSES else "generating",
            "progress_stage": stage if stage in _BLUEPRINT_ACTIVE_STATUSES else "generating",
            "progress_message": f"{original_message}（当前进程未找到活跃执行器；系统仅提示，不自动判失败，如长期无结果可手动取消后重试）",
            "updated_at": _utc_now_iso(),
            "error": None,
        }
    )
    return recovered


def _serialize_blueprint_job(job: Dict[str, Any]) -> BlueprintGenerationJobResponse:
    return BlueprintGenerationJobResponse(**_normalize_blueprint_job_payload(job))


def _job_public_payload(job: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(job)
    blueprint = payload.get("blueprint")
    if hasattr(blueprint, "model_dump"):
        payload["blueprint"] = blueprint.model_dump()
    return payload


def _db_blueprint_job_to_payload(record: BlueprintGenerationJob) -> Dict[str, Any]:
    return _normalize_blueprint_job_payload(
        {
            "run_id": record.run_id,
            "project_id": record.project_id,
            "user_id": record.user_id,
            "status": record.status,
            "progress_stage": record.progress_stage,
            "progress_message": record.progress_message,
            "started_at": record.started_at.isoformat() if record.started_at else None,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None,
            "blueprint": record.blueprint_payload,
            "ai_message": record.ai_message,
            "error": record.error_payload,
        }
    )


async def _load_latest_blueprint_job_from_db(
    project_id: str,
    session: AsyncSession,
) -> Dict[str, Any] | None:
    result = await session.execute(
        select(BlueprintGenerationJob)
        .where(BlueprintGenerationJob.project_id == project_id)
        .order_by(BlueprintGenerationJob.started_at.desc(), BlueprintGenerationJob.created_at.desc())
        .limit(1)
    )
    record = result.scalar_one_or_none()
    if not record:
        return None
    return _recover_stale_blueprint_job(_db_blueprint_job_to_payload(record))


async def _upsert_blueprint_job_record(session: AsyncSession, job: Dict[str, Any]) -> None:
    payload = _job_public_payload(_normalize_blueprint_job_payload(job))
    started_at = _parse_blueprint_job_time(payload.get("started_at"))
    updated_at = _parse_blueprint_job_time(payload.get("updated_at"))
    status_value = str(payload.get("status") or "")

    user_id = payload.get("user_id")
    if user_id in (None, ""):
        owner_result = await session.execute(
            select(NovelProject.user_id).where(NovelProject.id == payload["project_id"]).limit(1)
        )
        owner_user_id = owner_result.scalar_one_or_none()
        if owner_user_id is None:
            raise ValueError(f"Cannot resolve project owner for blueprint job: {payload['project_id']}")
        user_id = owner_user_id
        payload["user_id"] = owner_user_id

    record = await session.get(BlueprintGenerationJob, payload["run_id"])
    if record is None:
        record = BlueprintGenerationJob(
            run_id=payload["run_id"],
            project_id=payload["project_id"],
            user_id=int(user_id),
        )
        session.add(record)

    record.project_id = payload["project_id"]
    record.user_id = int(user_id)
    record.status = status_value
    record.progress_stage = str(payload.get("progress_stage") or status_value or "queued")
    record.progress_message = str(payload.get("progress_message") or "")
    record.started_at = started_at
    record.finished_at = updated_at if status_value in {"successful", "failed", "cancelled"} else None
    blueprint_payload = payload.get("blueprint")
    record.blueprint_payload = blueprint_payload if isinstance(blueprint_payload, dict) else None
    record.ai_message = str(payload.get("ai_message") or "") or None
    error_payload = payload.get("error")
    record.error_payload = error_payload if isinstance(error_payload, dict) else None
    if updated_at is not None:
        record.updated_at = updated_at
    await session.commit()


async def _append_blueprint_job_history(job: Dict[str, Any]) -> None:
    async with AsyncSessionLocal() as history_session:
        service = NovelService(history_session)
        await service.append_conversation(
            job["project_id"],
            "system",
            json.dumps(_job_public_payload(job), ensure_ascii=False),
            metadata={
                "type": "blueprint_generation_job",
                "run_id": job.get("run_id"),
                "status": job.get("status"),
                "progress_stage": job.get("progress_stage"),
                "updated_at": job.get("updated_at"),
            },
        )


async def _persist_blueprint_job_state(job: Dict[str, Any]) -> None:
    try:
        async with AsyncSessionLocal() as persist_session:
            await _upsert_blueprint_job_record(persist_session, job)
        await _append_blueprint_job_history(job)
    except Exception:
        logger.exception("保存蓝图任务状态失败：project=%s run_id=%s", job.get("project_id"), job.get("run_id"))


async def _load_latest_blueprint_job_from_history(
    project_id: str,
    session: AsyncSession,
) -> Dict[str, Any] | None:
    service = NovelService(session)
    records = await service.list_conversations(project_id)
    for record in reversed(records):
        metadata = getattr(record, "metadata", None) or {}
        if not isinstance(metadata, dict) or metadata.get("type") != "blueprint_generation_job":
            continue
        try:
            payload = json.loads(record.content)
        except (TypeError, ValueError):
            continue
        if isinstance(payload, dict):
            return _recover_stale_blueprint_job(payload)
    return None


async def _load_latest_blueprint_job(
    project_id: str,
    session: AsyncSession,
) -> Dict[str, Any] | None:
    persisted = await _load_latest_blueprint_job_from_db(project_id, session)
    if persisted is not None:
        return persisted
    return await _load_latest_blueprint_job_from_history(project_id, session)


async def _recover_finished_blueprint_job_from_project(
    project_id: str,
    session: AsyncSession,
    user_id: int,
    job: Dict[str, Any],
) -> Dict[str, Any] | None:
    service = NovelService(session)
    project_schema = await service.get_project_schema(project_id, user_id)
    blueprint = project_schema.blueprint
    if not _is_recoverable_for_requested_blueprint_stage(blueprint, job.get("force_stage")):
        return None

    recovered = _normalize_blueprint_job_payload(job)
    recovered.update(
        {
            "user_id": user_id,
            "status": "successful",
            "progress_stage": "successful",
            "progress_message": "检测到蓝图已落库，已恢复为完成状态",
            "updated_at": _utc_now_iso(),
            "blueprint": project_schema.blueprint,
            "ai_message": recovered.get("ai_message") or "蓝图已生成，请确认后进入写作阶段。",
            "error": None,
        }
    )
    return recovered


async def _set_blueprint_job_state(run_id: str, **updates: Any) -> None:
    snapshot: Dict[str, Any] | None = None
    async with _BLUEPRINT_JOB_LOCK:
        job = _BLUEPRINT_JOBS.get(run_id)
        if not job:
            return
        if job.get("status") == "cancelled" and updates.get("status") != "cancelled":
            return
        job.update(updates)
        job["updated_at"] = _utc_now_iso()
        snapshot = dict(job)
    if snapshot:
        await _persist_blueprint_job_state(snapshot)


async def _run_blueprint_generation_job(
    run_id: str,
    project_id: str,
    user_id: int,
    force_stage: str | None = None,
) -> None:
    await _set_blueprint_job_state(
        run_id,
        status="generating",
        progress_stage="generating",
        progress_message="正在生成小说蓝图",
    )

    async def progress_callback(stage: str, message: str) -> None:
        await _set_blueprint_job_state(
            run_id,
            status=stage,
            progress_stage=stage,
            progress_message=message,
        )

    async def heartbeat() -> None:
        while True:
            await asyncio.sleep(_BLUEPRINT_JOB_HEARTBEAT_SECONDS)
            async with _BLUEPRINT_JOB_LOCK:
                job = _BLUEPRINT_JOBS.get(run_id)
                if not job:
                    return
                if job.get("status") not in _BLUEPRINT_ACTIVE_STATUSES:
                    return
                stage = str(job.get("progress_stage") or job.get("status") or "generating")
                message = str(job.get("progress_message") or "蓝图生成进行中")
            await _set_blueprint_job_state(
                run_id,
                status=stage,
                progress_stage=stage,
                progress_message=message,
            )

    heartbeat_task = asyncio.create_task(heartbeat())

    try:
        async with AsyncSessionLocal() as job_session:
            with LLMService.daily_limit_scope(f"blueprint:{project_id}:{force_stage or 'full'}:{user_id}"):
                response = await _generate_blueprint_impl(
                    project_id=project_id,
                    session=job_session,
                    current_user=user_id,
                    progress_callback=progress_callback,
                    force_stage=force_stage,
                )
        async with _BLUEPRINT_JOB_LOCK:
            current_job = _BLUEPRINT_JOBS.get(run_id)
            if current_job and current_job.get("status") == "cancelled":
                await _persist_blueprint_job_state(dict(current_job))
                return
        await _set_blueprint_job_state(
            run_id,
            status="successful",
            progress_stage="successful",
            progress_message="蓝图生成完成",
            blueprint=response.blueprint,
            ai_message=response.ai_message,
            error=None,
        )
    except Exception as exc:  # noqa: BLE001 - background task must not crash silently
        logger.exception("蓝图后台生成失败：project=%s run_id=%s", project_id, run_id)
        async with _BLUEPRINT_JOB_LOCK:
            current_job = _BLUEPRINT_JOBS.get(run_id)
            if current_job and current_job.get("status") == "cancelled":
                await _persist_blueprint_job_state(dict(current_job))
                return
        await _set_blueprint_job_state(
            run_id,
            status="failed",
            progress_stage="failed",
            progress_message="蓝图生成失败",
            error=_blueprint_error(
                "blueprint_generation_failed",
                "Blueprint generation failed",
                detail=exc,
                retryable=True,
            ),
        )
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass


@router.post("/{project_id}/blueprint/generate/start", response_model=BlueprintGenerationJobResponse)
async def start_blueprint_generation(
    project_id: str,
    background_tasks: BackgroundTasks,
    payload: Dict[str, Any] | None = Body(default=None),
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> BlueprintGenerationJobResponse:
    """Start blueprint generation as a background job; poll /status for result."""
    user_id = int(current_user.id)
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, user_id)

    force_stage_raw = payload.get("force_stage") if isinstance(payload, dict) else None
    force_stage = str(force_stage_raw).strip().lower() if isinstance(force_stage_raw, str) and force_stage_raw.strip() else None
    if force_stage not in {None, "novel_outline", "chapter_outline"}:
        raise HTTPException(status_code=400, detail="force_stage 仅支持 novel_outline 或 chapter_outline")

    existing = await _load_latest_blueprint_job(project_id, session)
    if existing and existing.get("status") in _BLUEPRINT_ACTIVE_STATUSES:
        existing_force_stage_raw = existing.get("force_stage")
        existing_force_stage = (
            str(existing_force_stage_raw).strip().lower()
            if isinstance(existing_force_stage_raw, str) and str(existing_force_stage_raw).strip()
            else None
        )

        if force_stage and existing_force_stage == force_stage:
            async with _BLUEPRINT_JOB_LOCK:
                if existing.get("run_id"):
                    _BLUEPRINT_PROJECT_RUNS[project_id] = existing["run_id"]
                    _BLUEPRINT_JOBS.setdefault(existing["run_id"], dict(existing))
            return _serialize_blueprint_job(existing)

        if not force_stage:
            recovered_success = await _recover_finished_blueprint_job_from_project(
                project_id,
                session,
                user_id,
                existing,
            )
            if recovered_success is not None:
                await _persist_blueprint_job_state(recovered_success)
                async with _BLUEPRINT_JOB_LOCK:
                    if recovered_success.get("run_id"):
                        _BLUEPRINT_PROJECT_RUNS[project_id] = recovered_success["run_id"]
                        _BLUEPRINT_JOBS[recovered_success["run_id"]] = dict(recovered_success)
                return _serialize_blueprint_job(recovered_success)

            async with _BLUEPRINT_JOB_LOCK:
                if existing.get("run_id"):
                    _BLUEPRINT_PROJECT_RUNS[project_id] = existing["run_id"]
                    _BLUEPRINT_JOBS.setdefault(existing["run_id"], dict(existing))
            return _serialize_blueprint_job(existing)

    async with _BLUEPRINT_JOB_LOCK:
        run_id = str(uuid.uuid4())
        now = _utc_now_iso()
        job = {
            "run_id": run_id,
            "project_id": project_id,
            "user_id": user_id,
            "status": "queued",
            "progress_stage": "queued",
            "progress_message": "蓝图生成任务已入队",
            "started_at": now,
            "updated_at": now,
            "blueprint": None,
            "ai_message": None,
            "error": None,
            "force_stage": force_stage,
        }
        _BLUEPRINT_JOBS[run_id] = job
        _BLUEPRINT_PROJECT_RUNS[project_id] = run_id

    await _persist_blueprint_job_state(job)
    background_tasks.add_task(_run_blueprint_generation_job, run_id, project_id, user_id, force_stage)
    return _serialize_blueprint_job(job)


@router.get("/{project_id}/blueprint/generate/status", response_model=BlueprintGenerationJobResponse)
async def get_blueprint_generation_status(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> BlueprintGenerationJobResponse:
    """Return the latest blueprint generation job status for a project."""
    user_id = int(current_user.id)
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, user_id)

    persisted = await _load_latest_blueprint_job(project_id, session)
    if persisted:
        async with _BLUEPRINT_JOB_LOCK:
            run_id = persisted.get("run_id") or _BLUEPRINT_PROJECT_RUNS.get(project_id)
            memory_job = _BLUEPRINT_JOBS.get(run_id or "")
            if memory_job:
                recovered_job = _recover_stale_blueprint_job(memory_job)
                if recovered_job != memory_job:
                    memory_job.update(recovered_job)
                    snapshot = dict(memory_job)
                else:
                    snapshot = None
                current = dict(memory_job)
            else:
                snapshot = None
                current = dict(persisted)
                if run_id:
                    _BLUEPRINT_PROJECT_RUNS[project_id] = run_id

        if snapshot:
            await _persist_blueprint_job_state(snapshot)
            current = snapshot

        if current.get("status") in _BLUEPRINT_ACTIVE_STATUSES:
            recovered_success = await _recover_finished_blueprint_job_from_project(
                project_id,
                session,
                user_id,
                current,
            )
            if recovered_success is not None:
                await _persist_blueprint_job_state(recovered_success)
                async with _BLUEPRINT_JOB_LOCK:
                    if recovered_success.get("run_id"):
                        _BLUEPRINT_PROJECT_RUNS[project_id] = recovered_success["run_id"]
                        _BLUEPRINT_JOBS[recovered_success["run_id"]] = dict(recovered_success)
                return _serialize_blueprint_job(recovered_success)

            if run_id and not memory_job:
                current = _fail_orphaned_blueprint_job(current)
                await _persist_blueprint_job_state(current)
                async with _BLUEPRINT_JOB_LOCK:
                    _BLUEPRINT_JOBS.pop(run_id, None)
                    _BLUEPRINT_PROJECT_RUNS.pop(project_id, None)
                return _serialize_blueprint_job(current)

        if current.get("run_id") and current.get("status") not in _BLUEPRINT_ACTIVE_STATUSES:
            async with _BLUEPRINT_JOB_LOCK:
                _BLUEPRINT_JOBS.pop(current["run_id"], None)
                _BLUEPRINT_PROJECT_RUNS.pop(project_id, None)
        return _serialize_blueprint_job(current)

    return BlueprintGenerationJobResponse(
        run_id="",
        project_id=project_id,
        status="idle",
        progress_stage="idle",
        progress_message="暂无蓝图生成任务",
    )


@router.post("/{project_id}/blueprint/generate/cancel", response_model=BlueprintGenerationJobResponse)
async def cancel_blueprint_generation(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> BlueprintGenerationJobResponse:
    """Cancel the latest queued/running blueprint generation job when possible."""
    user_id = int(current_user.id)
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, user_id)

    persisted = await _load_latest_blueprint_job(project_id, session)
    if not persisted:
        return BlueprintGenerationJobResponse(
            run_id="",
            project_id=project_id,
            status="idle",
            progress_stage="idle",
            progress_message="暂无可取消的蓝图生成任务",
        )

    run_id = str(persisted.get("run_id") or "")
    async with _BLUEPRINT_JOB_LOCK:
        job = _BLUEPRINT_JOBS.get(run_id or "")
        current = job if job else persisted
        if current.get("status") in _BLUEPRINT_ACTIVE_STATUSES:
            current.update({
                "status": "cancelled",
                "progress_stage": "cancelled",
                "progress_message": "蓝图生成任务已取消",
                "updated_at": _utc_now_iso(),
                "error": _blueprint_error(
                    "blueprint_job_cancelled",
                    "Blueprint generation job was cancelled",
                    retryable=True,
                ),
            })
        snapshot = dict(current)
        if run_id:
            _BLUEPRINT_PROJECT_RUNS[project_id] = run_id
            if job:
                _BLUEPRINT_JOBS[run_id] = current

    await _persist_blueprint_job_state(snapshot)
    return _serialize_blueprint_job(snapshot)


async def _generate_blueprint_impl(
    *,
    project_id: str,
    session: AsyncSession,
    current_user: UserInDB | int,
    progress_callback: Callable[[str, str], Awaitable[None]] | None = None,
    force_stage: str | None = None,
) -> BlueprintGenerationResponse:
    """根据完整对话生成可执行的小说蓝图。"""
    novel_service = NovelService(session)
    prompt_service = PromptService(session)
    llm_service = LLMService(session)
    user_id = int(current_user if isinstance(current_user, int) else current_user.id)

    project = await novel_service.ensure_project_owner(project_id, user_id)
    logger.info("项目 %s 开始生成蓝图", project_id)

    existing_blueprint: Blueprint | None = None
    try:
        project_schema = await novel_service.get_project_schema(project_id, user_id)
        if project_schema and project_schema.blueprint:
            existing_blueprint = project_schema.blueprint
    except Exception as exc:
        logger.warning("Failed to load existing blueprint before generation: project=%s error=%s", project_id, exc)

    history_records = await novel_service.list_conversations(project_id)
    if not history_records and existing_blueprint is None:
        logger.warning("项目 %s 缺少对话历史，无法生成蓝图", project_id)
        raise HTTPException(status_code=400, detail="缺少对话历史，请先完成概念对话后再生成蓝图")

    formatted_history: List[Dict[str, str]] = []
    structured_dialogue: List[Dict[str, Any]] = []
    for record in history_records:
        role = record.role
        content = record.content
        if not role or not content:
            continue
        try:
            normalized = unwrap_markdown_json(content)
            data = json.loads(normalized)
            if role == "user":
                user_value = data.get("value", data)
                if isinstance(user_value, str):
                    formatted_history.append({"role": "user", "content": user_value})
                structured_dialogue.append({
                    "role": "user",
                    "value": user_value,
                    "raw": data,
                })
            elif role == "assistant":
                ai_message = data.get("ai_message") if isinstance(data, dict) else None
                if ai_message:
                    formatted_history.append({"role": "assistant", "content": ai_message})
                structured_dialogue.append({
                    "role": "assistant",
                    "ai_message": ai_message,
                    "ui_control": data.get("ui_control") if isinstance(data, dict) else None,
                    "conversation_state": data.get("conversation_state") if isinstance(data, dict) else None,
                    "ready_for_blueprint": data.get("ready_for_blueprint") if isinstance(data, dict) else None,
                    "raw": data,
                })
        except (json.JSONDecodeError, AttributeError):
            continue

    if not formatted_history and existing_blueprint is None:
        logger.warning("项目 %s 对话历史格式异常，无法提取有效内容", project_id)
        raise HTTPException(
            status_code=400,
            detail="无法从历史对话中提取有效内容，请检查对话历史格式或重新进行概念对话"
        )

    existing_blueprint: Blueprint | None = None
    try:
        project_schema = await novel_service.get_project_schema(project_id, user_id)
        if project_schema and project_schema.blueprint:
            existing_blueprint = project_schema.blueprint
    except Exception as exc:
        logger.warning("项目 %s 读取现有蓝图失败，将继续走常规蓝图生成: %s", project_id, exc)

    async def checkpoint_callback(payload: Dict[str, Any], stage: str, message: str) -> None:
        await _checkpoint_blueprint_progress(
            novel_service=novel_service,
            project_id=project_id,
            blueprint_data=payload,
            progress_callback=progress_callback,
            stage=stage,
            message=message,
        )

    if progress_callback is not None:
        await progress_callback("generating", "正在整理灵感访谈并生成蓝图结构")

    existing_novel_outline = list(existing_blueprint.novel_outline or []) if existing_blueprint else []
    existing_chapter_outline = list(existing_blueprint.chapter_outline or []) if existing_blueprint else []
    force_stage = (force_stage or "").strip().lower() or None
    if force_stage == "novel_outline":
        existing_novel_outline = []
        existing_chapter_outline = []
    elif force_stage == "chapter_outline":
        existing_chapter_outline = []
    elif existing_chapter_outline and not _has_complete_chapter_outline(existing_chapter_outline):
        existing_chapter_outline = []
    generated_stage = "chapter_outline"

    if existing_blueprint:
        blueprint_data = existing_blueprint.model_dump(exclude_none=True)
    else:
        system_prompt = _ensure_prompt(await prompt_service.get_prompt("screenwriting"), "screenwriting")
        story_constraint_profile = _build_story_constraint_profile(
            formatted_history,
            structured_dialogue,
            project_title=project.title,
            existing_blueprint=existing_blueprint,
        )
        blueprint_context = {
            "project_title": project.title,
            "conversation_summary": _build_compact_blueprint_context(
                formatted_history,
                structured_dialogue,
                existing_blueprint=existing_blueprint,
            ),
            "story_constraint_profile": story_constraint_profile,
            "structure_gap_policy": {
                "conversation_is_constraint_not_ceiling": True,
                "must_autofill_missing_longform_slots": True,
                "must_respect_existing_world_and_character_anchors": True,
                "must_not_reduce_output_to_summary_rewrite": True,
            },
            "requirements": {
                "must_build_longform_architecture": True,
                "must_output_volume_plan": True,
                "must_include_multi_arc_progression": True,
                "must_not_skip_novel_outline_stage": True,
                "must_not_output_chapter_outline_yet": True,
                "must_assign_concrete_protagonist_name": True,
                "must_assign_concrete_core_character_names": True,
                "must_output_longform_cast_plan": True,
                "must_write_cast_plan_into_world_setting": "world_setting.cast_plan",
                "must_plan_cast_tiers": ["主角", "核心角色", "重要配角", "阶段配角", "势力成员", "功能性路人"],
                "must_plan_character_lifecycle": "每个重要角色都要有首次登场、退出/回归、所属势力、目标、秘密、知识边界和状态变化职责。",
                "must_plan_foreshadowing_payoff_windows": True,
                "must_not_keep_cast_tiny_for_longform": "长篇不能只有少数角色反复承担所有剧情功能。",
                "must_match_name_with_genre_style_tone": True,
                "must_keep_same_culture_name_system_within_same_faction": True,
                "must_avoid_overly_modern_or_out_of_setting_names": True,
                "forbid_placeholder_character_names": ["主角", "男主", "女主", "角色1", "角色A", "protagonist", "main character"],
                "character_naming_profile": _build_character_naming_profile(
                    existing_blueprint.model_dump(exclude_none=True) if existing_blueprint else {},
                    project.title,
                ),
            },
        }
        blueprint_raw = await _call_llm_with_stage_retries(
            llm_service=llm_service,
            system_prompt=system_prompt,
            conversation_history=[
                {
                    "role": "user",
                    "content": json.dumps(blueprint_context, ensure_ascii=False, indent=2),
                }
            ],
            temperature=0.25,
            user_id=user_id,
            timeout=max(420.0, _resolve_novel_outline_timeout_seconds(blueprint_data={
                "full_synopsis": "",
                "characters": existing_blueprint.characters if existing_blueprint else [],
                "relationships": existing_blueprint.relationships if existing_blueprint else [],
                "story_arcs": existing_blueprint.story_arcs if existing_blueprint else [],
                "volume_plan": existing_blueprint.volume_plan if existing_blueprint else [],
                "foreshadowing_system": existing_blueprint.foreshadowing_system if existing_blueprint else [],
                "world_setting": existing_blueprint.world_setting if existing_blueprint else {},
            })),
            response_format="json_object",
            max_tokens=6500,
            stage_label="蓝图主结构生成",
            progress_callback=progress_callback,
            progress_stage="generating",
            retry_attempts=2,
        )
        blueprint_raw = remove_think_tags(blueprint_raw)

        blueprint_normalized = unwrap_markdown_json(blueprint_raw)
        blueprint_sanitized = sanitize_json_like_text(blueprint_normalized)
        try:
            blueprint_data = json.loads(blueprint_sanitized)
        except json.JSONDecodeError as exc:
            logger.error(
                "项目 %s 蓝图生成 JSON 解析失败: %s\n原始响应: %s\n标准化后: %s\n清洗后: %s",
                project_id,
                exc,
                blueprint_raw[:500],
                blueprint_normalized[:500],
                blueprint_sanitized[:500],
            )
            raise HTTPException(
                status_code=500,
                detail=f"蓝图生成失败，AI 返回的内容格式不正确。请重试或联系管理员。错误详情: {str(exc)}"
            ) from exc

    if not isinstance(blueprint_data, dict):
        raise HTTPException(status_code=500, detail="蓝图生成失败，系统未得到可用的蓝图结构")

    if "novel_outline" not in blueprint_data or blueprint_data["novel_outline"] is None:
        blueprint_data["novel_outline"] = existing_novel_outline
    if "chapter_outline" not in blueprint_data or blueprint_data["chapter_outline"] is None:
        blueprint_data["chapter_outline"] = existing_chapter_outline

    await checkpoint_callback(blueprint_data, "generating", "已保存蓝图基础结构")

    if not existing_novel_outline:
        if not existing_chapter_outline:
            blueprint_data["chapter_outline"] = []
        blueprint_data = await _generate_novel_outline(
            llm_service=llm_service,
            blueprint_data=blueprint_data,
            user_id=user_id,
            progress_callback=progress_callback,
            checkpoint_callback=checkpoint_callback,
        )
        generated_stage = "novel_outline"
    elif not existing_chapter_outline:
        blueprint_data = await _generate_executable_chapter_outline(
            llm_service=llm_service,
            blueprint_data=blueprint_data,
            user_id=user_id,
            progress_callback=progress_callback,
            checkpoint_callback=checkpoint_callback,
        )
        blueprint_data = await _polish_chapter_outline_quality(
            llm_service=llm_service,
            blueprint_data=blueprint_data,
            user_id=user_id,
            progress_callback=progress_callback,
            checkpoint_callback=checkpoint_callback,
        )
        generated_stage = "chapter_outline"
    else:
        generated_stage = "chapter_outline"

    try:
        blueprint_data = await _repair_blueprint_character_names(
            llm_service=llm_service,
            blueprint_data=blueprint_data,
            user_id=user_id,
            project_title=project.title,
            progress_callback=progress_callback,
        )
    except Exception as exc:
        if not _blueprint_has_valid_character_names(blueprint_data):
            raise
        logger.warning(
            "Skip non-critical blueprint character-name repair after generation: project=%s error=%s",
            project_id,
            exc,
        )
        if progress_callback is not None:
            await progress_callback("polishing", "角色命名附加修复失败，已保留现有有效角色名")

    if progress_callback is not None:
        await progress_callback("generating", "正在保存蓝图与项目状态")

    blueprint = Blueprint(**blueprint_data)
    await novel_service.replace_blueprint(project_id, blueprint)
    if blueprint.title:
        project.title = blueprint.title
        project.status = "blueprint_ready"
        await session.commit()
        logger.info("项目 %s 更新标题为 %s，并标记为 blueprint_ready", project_id, blueprint.title)

    if generated_stage == "novel_outline":
        ai_message = "小说总大纲已经生成完成。请先检查全书推进结构，确认无误后，再继续生成章节大纲。"
    else:
        ai_message = "章节大纲已经生成完成。请确认整体结构是否可直接进入写作阶段，或返回继续调整。"
    return BlueprintGenerationResponse(blueprint=blueprint, ai_message=ai_message)


@router.post("/{project_id}/blueprint/generate", response_model=BlueprintGenerationResponse)
async def generate_blueprint(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> BlueprintGenerationResponse:
    with LLMService.daily_limit_scope(f"blueprint:{project_id}:full:{int(current_user.id)}"):
        return await _generate_blueprint_impl(
            project_id=project_id,
            session=session,
            current_user=current_user,
        )


@router.post("/{project_id}/blueprint/save", response_model=NovelProjectSchema)
async def save_blueprint(
    project_id: str,
    blueprint_data: Blueprint | None = Body(None),
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    """保存蓝图信息，可用于手动覆盖自动生成结果。"""
    user_id = int(current_user.id)
    novel_service = NovelService(session)
    project = await novel_service.ensure_project_owner(project_id, user_id)

    if blueprint_data:
        await novel_service.replace_blueprint(project_id, blueprint_data)
        if blueprint_data.title:
            project.title = blueprint_data.title
            await session.commit()
        logger.info("项目 %s 手动保存蓝图", project_id)
    else:
        logger.warning("项目 %s 保存蓝图时未提供蓝图数据", project_id)
        raise HTTPException(status_code=400, detail="缺少蓝图数据，请提供有效的蓝图内容")

    return await novel_service.get_project_schema(project_id, user_id)


@router.patch("/{project_id}/blueprint", response_model=NovelProjectSchema)
async def patch_blueprint(
    project_id: str,
    payload: BlueprintPatch,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    """局部更新蓝图字段，对世界观或角色做微调。"""
    user_id = int(current_user.id)
    novel_service = NovelService(session)
    project = await novel_service.ensure_project_owner(project_id, user_id)

    update_data = payload.model_dump(exclude_unset=True)
    await novel_service.patch_blueprint(project_id, update_data)
    logger.info("项目 %s 局部更新蓝图字段：%s", project_id, list(update_data.keys()))
    return await novel_service.get_project_schema(project_id, user_id)
