# AIMETA P=小说API_项目和章节管理|R=小说CRUD_章节管理|NR=不含内容生成|E=route:GET_POST_/api/novels/*|X=http|A=小说CRUD_章节|D=fastapi,sqlalchemy|S=db|RD=./README.ai
import asyncio
import json
import logging
import math
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.dependencies import get_current_user, get_project_owner_guard
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
    ImportNovelJobResponse,
    NovelProject as NovelProjectSchema,
    NovelProjectSummary,
    NovelSectionResponse,
    NovelSectionType,
)
from ...schemas.user import User as UserSchema, UserInDB
from ...models import BlueprintGenerationJob, NovelProject
from ...models.novel import Chapter, ChapterVersion
from ...services.export_service import ExportService
from ...services.import_service import ImportCancelledError, ImportService
from ...services.generation_call_service import GenerationCallPolicy, GenerationJSONDecodeError, call_generation_json, call_generation_text, is_retryable_http_exception
from ...services.llm_service import LLMService
from ...services.long_novel_outline_generator import LongNovelOutlineGenerator
from ...services.novel_service import NovelService
from ...schemas.task_runtime import TaskRuntimeEventType, TaskRuntimeStatus
from ...services.task_runtime import (
    TERMINAL_STATUSES,
    TaskRuntimeConflict,
    TaskRuntimeNotFound,
    TaskRuntimeService,
)
from ...services.prompt_service import PromptService
from ...services.pipeline_orchestrator import PipelineOrchestrator
from ...utils.json_utils import remove_think_tags, sanitize_json_like_text, unwrap_markdown_json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/novels", tags=["Novels"])

_BLUEPRINT_JOBS: Dict[str, Dict[str, Any]] = {}
_BLUEPRINT_PROJECT_RUNS: Dict[str, str] = {}
_BLUEPRINT_JOB_LOCK = asyncio.Lock()
_BLUEPRINT_JOB_STALE_SECONDS = 2 * 60 * 60
_BLUEPRINT_JOB_HEARTBEAT_SECONDS = 45
_BLUEPRINT_LEASE_STALE_SECONDS = 180
_BLUEPRINT_SCHEDULED_RUNS: set[str] = set()
_BLUEPRINT_ACTIVE_STATUSES = {
    "queued",
    "generating",
    "polishing",
    "blueprint_concept",
    "blueprint_setting_lock",
    "blueprint_cast_plan",
    "blueprint_plot_threads",
    "blueprint_foreshadowing",
    "blueprint_chapter_plan",
}

_IMPORT_JOBS: Dict[str, Dict[str, Any]] = {}
_IMPORT_USER_RUNS: Dict[int, str] = {}
_IMPORT_JOB_LOCK = asyncio.Lock()
_IMPORT_RUNNING_STATUSES = {
    "queued",
    "import_reading",
    "import_splitting",
    "import_sampling",
    "import_character_verify",
    "import_blueprint_extract",
    "import_saving",
    "import_ledger_rebuild",
}
_IMPORT_CANCELABLE_STATUSES = _IMPORT_RUNNING_STATUSES - {"import_saving", "import_ledger_rebuild"}
_IMPORT_RUNTIME_ACTIVE_STATUSES = {
    TaskRuntimeStatus.QUEUED.value,
    TaskRuntimeStatus.RUNNING.value,
    TaskRuntimeStatus.CANCELLING.value,
    TaskRuntimeStatus.STALE.value,
}
_IMPORT_STORAGE_ROOT = Path(__file__).resolve().parents[3] / "storage" / "novel_imports"
_IMPORT_SCHEDULED_RUNS: set[str] = set()
_IMPORT_LEASE_OWNER = f"novel-import-worker:{uuid.uuid4().hex}"

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
    length_contract = _build_length_contract(
        formatted_history,
        structured_dialogue,
        project_title=project_title,
        existing_blueprint=existing_blueprint,
    )
    if length_contract:
        profile["length_contract"] = length_contract
        profile["generation_principles"].append(
            "如果用户明确给出章节数、篇幅或连载规模，必须尊重该篇幅契约；长篇能力是支撑能力，不是强行把短中篇扩写成超长篇。"
        )
    return profile


def _walk_text_fragments(value: Any) -> List[str]:
    fragments: List[str] = []
    if value is None:
        return fragments
    if isinstance(value, str):
        text = value.strip()
        if text:
            fragments.append(text)
        return fragments
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        fragments.append(str(value))
        return fragments
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key).strip()
            for fragment in _walk_text_fragments(item):
                fragments.append(f"{key_text}: {fragment}" if key_text else fragment)
        return fragments
    if isinstance(value, (list, tuple, set)):
        for item in value:
            fragments.extend(_walk_text_fragments(item))
    return fragments


def _extract_requested_chapter_count(text: str) -> Optional[int]:
    if not text:
        return None
    normalized = str(text)
    patterns = [
        r"(?:约|大约|大概|预计|计划|全书|总共|一共|around|about|roughly)?\s*(\d{1,4})\s*[-–—]?\s*(?:章|章节|回|集|chapters?)\s*(?:左右|上下|以内|内|around|about)?",
        r"(?:章数|章节数|总章节|target[_\s-]*chapters?|chapter[_\s-]*count)\D{0,12}(\d{1,4})",
    ]
    matches: List[int] = []
    for pattern in patterns:
        for match in re.finditer(pattern, normalized, flags=re.IGNORECASE):
            try:
                value = int(match.group(1))
            except (TypeError, ValueError):
                continue
            if 1 <= value <= 1000:
                matches.append(value)
    if not matches:
        return None
    return matches[-1]


def _extract_requested_total_word_count(text: str) -> Optional[int]:
    if not text:
        return None
    normalized = str(text).replace(",", "").replace("，", "")
    if re.search(r"(?:百万字|一百万字|one\s+million\s+words?)", normalized, flags=re.IGNORECASE):
        return 1_000_000

    matches: List[int] = []
    for match in re.finditer(r"(\d+(?:\.\d+)?)\s*万\s*字", normalized, flags=re.IGNORECASE):
        try:
            matches.append(int(float(match.group(1)) * 10_000))
        except (TypeError, ValueError):
            continue
    for match in re.finditer(r"(\d+(?:\.\d+)?)\s*(?:k|千)\s*(?:字|words?)", normalized, flags=re.IGNORECASE):
        try:
            matches.append(int(float(match.group(1)) * 1_000))
        except (TypeError, ValueError):
            continue
    for match in re.finditer(r"(\d{5,8})\s*(?:字|words?)", normalized, flags=re.IGNORECASE):
        try:
            matches.append(int(match.group(1)))
        except (TypeError, ValueError):
            continue
    return matches[-1] if matches else None


def _infer_target_chapter_count_from_fragments(fragments: List[str]) -> Optional[int]:
    text = "\n".join(str(fragment or "") for fragment in fragments if str(fragment or "").strip())
    if not text:
        return None

    word_count = _extract_requested_total_word_count(text)
    lowered = text.lower()
    is_short = any(marker in text for marker in ("短篇", "小短篇", "短故事", "短剧")) or any(
        marker in lowered for marker in ("short story", "short novel")
    )
    is_mid = any(marker in text for marker in ("中篇", "中短篇")) or "novella" in lowered
    is_long = any(
        marker in text
        for marker in ("长篇", "超长篇", "百万字", "连载", "网文", "玄幻", "仙侠", "修仙", "奇幻", "群像", "升级")
    ) or any(marker in lowered for marker in ("longform", "serial", "epic fantasy"))

    if word_count:
        chapter_word_target = 3200 if is_short else 4500
        if is_long and word_count >= 500_000:
            chapter_word_target = 5000
        inferred = max(1, int(round(word_count / chapter_word_target)))
        return max(6 if is_short else 8, min(1000, inferred))

    if is_short:
        return 12
    if is_mid:
        return 36
    if is_long:
        return 120
    return 60


def _resolve_length_contract_defaults(target_chapter_count: int) -> Dict[str, int]:
    if target_chapter_count <= 10:
        stage_min, stage_max = 3, min(5, target_chapter_count)
    elif target_chapter_count <= 16:
        stage_min, stage_max = 4, min(6, target_chapter_count)
    elif target_chapter_count <= 36:
        stage_min, stage_max = 5, 8
    elif target_chapter_count <= 80:
        stage_min, stage_max = 7, 12
    elif target_chapter_count <= 160:
        stage_min, stage_max = 9, 16
    elif target_chapter_count <= 320:
        stage_min, stage_max = 12, 24
    elif target_chapter_count <= 600:
        stage_min, stage_max = 16, 32
    else:
        stage_min, stage_max = 20, 40

    if target_chapter_count <= 60:
        seed_count = target_chapter_count
    elif target_chapter_count <= 120:
        seed_count = 60
    elif target_chapter_count <= 300:
        seed_count = 80
    elif target_chapter_count <= 600:
        seed_count = 100
    else:
        seed_count = 120

    return {
        "stage_count_min": stage_min,
        "stage_count_max": stage_max,
        "chapter_outline_seed_count": seed_count,
    }


def _make_length_contract(target_chapter_count: int, *, source: str) -> Dict[str, Any]:
    defaults = _resolve_length_contract_defaults(target_chapter_count)

    return {
        "target_chapter_count": target_chapter_count,
        "stage_count_min": defaults["stage_count_min"],
        "stage_count_max": defaults["stage_count_max"],
        "chapter_outline_seed_count": defaults["chapter_outline_seed_count"],
        "source": source,
        "policy": "respect_explicit_length_without_compressing_longform_to_twelve",
    }


def _normalize_length_contract_candidate(candidate: Any, *, source: str) -> Dict[str, Any]:
    if not isinstance(candidate, dict):
        return {}
    try:
        target_chapter_count = int(candidate.get("target_chapter_count") or 0)
    except (TypeError, ValueError):
        return {}
    if not 1 <= target_chapter_count <= 1000:
        return {}

    normalized = _make_length_contract(target_chapter_count, source=source)
    defaults = _resolve_length_contract_defaults(target_chapter_count)
    for key in ("stage_count_min", "stage_count_max", "chapter_outline_seed_count"):
        try:
            value = int(candidate.get(key))
        except (TypeError, ValueError):
            continue
        if value > 0:
            normalized[key] = max(value, defaults[key])
    if normalized["stage_count_min"] > normalized["stage_count_max"]:
        normalized["stage_count_max"] = normalized["stage_count_min"]
    normalized["chapter_outline_seed_count"] = min(
        target_chapter_count,
        max(defaults["chapter_outline_seed_count"], int(normalized["chapter_outline_seed_count"])),
    )
    normalized["source"] = source
    return normalized


def _extract_stored_length_contract(existing_blueprint: Blueprint | None) -> Dict[str, Any]:
    if existing_blueprint is None:
        return {}
    try:
        blueprint_data = existing_blueprint.model_dump(exclude_none=True)
    except Exception:
        return {}
    if not isinstance(blueprint_data, dict):
        return {}

    world_setting = blueprint_data.get("world_setting") if isinstance(blueprint_data.get("world_setting"), dict) else {}
    system_blueprint = (
        world_setting.get("system_blueprint")
        if isinstance(world_setting, dict) and isinstance(world_setting.get("system_blueprint"), dict)
        else {}
    )
    candidates = [
        blueprint_data.get("length_contract"),
        world_setting.get("length_contract") if isinstance(world_setting, dict) else None,
        system_blueprint.get("length_contract") if isinstance(system_blueprint, dict) else None,
    ]
    for candidate in candidates:
        normalized = _normalize_length_contract_candidate(candidate, source="stored_blueprint_length_contract")
        if normalized:
            return normalized
    return {}


def _build_length_contract(
    formatted_history: List[Dict[str, str]],
    structured_dialogue: List[Dict[str, Any]],
    *,
    project_title: str,
    existing_blueprint: Blueprint | None = None,
) -> Dict[str, Any]:
    primary_fragments: List[str] = [project_title]
    primary_fragments.extend(
        str(item.get("content") or "")
        for item in formatted_history
        if item.get("role") == "user" and str(item.get("content") or "").strip()
    )
    latest_state = _extract_latest_conversation_state(structured_dialogue)
    if isinstance(latest_state, dict):
        primary_fragments.extend(_walk_text_fragments(latest_state.get("collected_info")))
        primary_fragments.extend(_walk_text_fragments(latest_state.get("checklist")))

    target_chapter_count: Optional[int] = None
    for fragment in primary_fragments:
        extracted = _extract_requested_chapter_count(fragment)
        if extracted:
            target_chapter_count = extracted

    if target_chapter_count:
        return _make_length_contract(target_chapter_count, source="explicit_user_or_project_length")

    stored_contract = _extract_stored_length_contract(existing_blueprint)
    if stored_contract:
        return stored_contract

    inferred_chapter_count = _infer_target_chapter_count_from_fragments(primary_fragments)
    if inferred_chapter_count:
        return _make_length_contract(inferred_chapter_count, source="inferred_project_scale")

    return {}


def _attach_length_contract_to_blueprint(
    blueprint_data: Dict[str, Any],
    length_contract: Dict[str, Any],
) -> Dict[str, Any]:
    if not length_contract:
        return blueprint_data
    world_setting = blueprint_data.get("world_setting")
    if not isinstance(world_setting, dict):
        world_setting = {}
        blueprint_data["world_setting"] = world_setting
    system_blueprint = world_setting.get("system_blueprint")
    if not isinstance(system_blueprint, dict):
        system_blueprint = {}
        world_setting["system_blueprint"] = system_blueprint
    system_blueprint["length_contract"] = dict(length_contract)
    world_setting["length_contract"] = dict(length_contract)
    return blueprint_data


def _resolve_blueprint_length_contract(blueprint_data: Dict[str, Any]) -> Dict[str, Any]:
    world_setting = blueprint_data.get("world_setting") if isinstance(blueprint_data.get("world_setting"), dict) else {}
    candidates = [
        blueprint_data.get("length_contract"),
        world_setting.get("length_contract") if isinstance(world_setting, dict) else None,
    ]
    system_blueprint = world_setting.get("system_blueprint") if isinstance(world_setting, dict) else None
    if isinstance(system_blueprint, dict):
        candidates.append(system_blueprint.get("length_contract"))
    for candidate in candidates:
        if isinstance(candidate, dict):
            target = candidate.get("target_chapter_count")
            try:
                target_int = int(target)
            except (TypeError, ValueError):
                continue
            if 1 <= target_int <= 1000:
                return _normalize_length_contract_candidate(candidate, source=str(candidate.get("source") or "blueprint_length_contract"))
    return {}


def _format_length_contract_instruction(length_contract: Dict[str, Any]) -> str:
    if not length_contract:
        return "未检测到明确章节数；请按题材和蓝图自然规划，但不要为了长篇模板而机械扩容。"
    target = int(length_contract["target_chapter_count"])
    stage_min = int(length_contract.get("stage_count_min") or 4)
    stage_max = int(length_contract.get("stage_count_max") or 12)
    seed_count = int(length_contract.get("chapter_outline_seed_count") or _resolve_length_contract_defaults(target)["chapter_outline_seed_count"])
    source = str(length_contract.get("source") or "")
    prefix = "用户/项目已明确篇幅目标" if source != "inferred_project_scale" else "系统已按题材/篇幅自然推断目标"
    return (
        f"{prefix}：约 {target} 章。小说总纲阶段数应控制在 {stage_min}-{stage_max} 个，"
        f"expected_chapter_range 必须连续覆盖第 1-{target} 章，不得扩写到 {target} 章之外；"
        f"章节大纲首轮生成 {seed_count} 章。短篇不会被强行扩成长篇，长篇也不会被压缩成 12 章骨架；"
        "超过首轮数量的章节后续按批次继续生成，不能让总纲只覆盖一个很薄的开头。"
    )


def _outline_exceeds_length_contract(outline: List[Dict[str, Any]], length_contract: Dict[str, Any]) -> bool:
    target = int(length_contract.get("target_chapter_count") or 0)
    if target <= 0:
        return False
    max_end = 0
    for item in outline:
        chapter_range = _parse_expected_chapter_range(item.get("expected_chapter_range"))
        if chapter_range is None:
            continue
        max_end = max(max_end, chapter_range[1])
    allowed_end = target + max(1, math.ceil(target * 0.1))
    return max_end > allowed_end


def _remap_outline_ranges_to_length_contract(
    outline: List[Dict[str, Any]],
    length_contract: Dict[str, Any],
) -> List[Dict[str, Any]]:
    target = int(length_contract.get("target_chapter_count") or 0)
    if target <= 0 or not outline:
        return outline
    try:
        stage_count_max = int(length_contract.get("stage_count_max") or len(outline))
    except (TypeError, ValueError):
        stage_count_max = len(outline)
    stage_count = min(len(outline), target, max(1, stage_count_max))
    if stage_count <= 0:
        return outline
    base = target // stage_count
    remainder = target % stage_count
    start = 1
    remapped: List[Dict[str, Any]] = []
    for index, item in enumerate(outline[:stage_count], start=1):
        width = base + (1 if index <= remainder else 0)
        end = start + max(1, width) - 1
        updated = dict(item)
        updated["stage"] = index
        updated["expected_chapter_range"] = f"{start}-{end}章"
        remapped.append(updated)
        start = end + 1
    return remapped


def _resolve_blueprint_chapter_outline_count(blueprint_data: Dict[str, Any]) -> int:
    length_contract = _resolve_blueprint_length_contract(blueprint_data)
    if length_contract:
        try:
            target = int(length_contract.get("target_chapter_count") or 0)
            default_seed = _resolve_length_contract_defaults(target)["chapter_outline_seed_count"] if target > 0 else 60
            seed_count = int(length_contract.get("chapter_outline_seed_count") or default_seed)
        except (TypeError, ValueError):
            seed_count = 60
        return max(1, min(120, seed_count))
    return 60


def _resolve_novel_outline_min_stage_count(blueprint_data: Dict[str, Any]) -> int:
    length_contract = _resolve_blueprint_length_contract(blueprint_data)
    if not length_contract:
        return 4
    try:
        return max(1, int(length_contract.get("stage_count_min") or 4))
    except (TypeError, ValueError):
        return 4


def _build_chapter_batches(total_chapters: int, *, batch_size: int = 4) -> List[tuple[int, int]]:
    total = max(1, int(total_chapters or 1))
    size = max(1, int(batch_size or 4))
    return [(start, min(total, start + size - 1)) for start in range(1, total + 1, size)]


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
        blueprint_data = blueprint.model_dump(exclude_none=True) if hasattr(blueprint, "model_dump") else {}
        expected_count = _resolve_blueprint_chapter_outline_count(blueprint_data) if isinstance(blueprint_data, dict) else None
        return isinstance(chapter_outline, list) and _has_complete_chapter_outline(chapter_outline, expected_count)
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
    soft_timeout_seconds: Optional[float] = None,
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
            soft_timeout_seconds=soft_timeout_seconds,
        ),
        progress_callback=progress_callback,
    )
    return result.text


async def _call_llm_json_with_stage_retries(
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
    json_repair_attempts: int = 1,
    soft_timeout_seconds: Optional[float] = None,
) -> Dict[str, Any]:
    try:
        result = await call_generation_json(
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
                json_repair_attempts=json_repair_attempts,
                soft_timeout_seconds=soft_timeout_seconds,
            ),
            progress_callback=progress_callback,
        )
    except GenerationJSONDecodeError as exc:
        logger.warning(
            "Blueprint generation JSON repair failed: stage=%s normalized=%s",
            stage_label,
            exc.normalized_text[:500],
        )
        raise HTTPException(
            status_code=500,
            detail={
                "code": "GENERATION_JSON_REPAIR_FAILED",
                "message": f"{stage_label} 返回格式仍不可解析，请重试。",
                "hint": "系统已尝试自动格式修复，但模型返回内容仍不是合法 JSON 对象。",
                "retryable": True,
                "stage": progress_stage,
            },
        ) from exc
    return result.data


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
    actual: List[int] = []
    for item in chapters:
        if not isinstance(item, dict):
            continue
        try:
            chapter_number = int(item.get("chapter_number") or 0)
        except (TypeError, ValueError):
            continue
        if start_chapter <= chapter_number <= end_chapter:
            actual.append(chapter_number)
    actual.sort()
    return actual == expected


def _has_complete_chapter_outline(chapters: List[Dict[str, Any]], expected_count: Optional[int] = None) -> bool:
    valid_numbers: List[int] = []
    for item in chapters:
        if not isinstance(item, dict):
            continue
        try:
            chapter_number = int(item.get("chapter_number") or 0)
        except (TypeError, ValueError):
            continue
        if chapter_number > 0:
            valid_numbers.append(chapter_number)
    valid_numbers = sorted(set(valid_numbers))
    if not valid_numbers:
        return False
    if expected_count is not None:
        try:
            target = max(1, int(expected_count))
        except (TypeError, ValueError):
            target = len(valid_numbers)
        if len(valid_numbers) < target:
            return False
    else:
        target = len(valid_numbers)
    return _is_chapter_outline_batch_complete(chapters, 1, target)


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


def _validate_novel_outline_coherence(outline: List[Dict[str, Any]], *, min_stage_count: int = 4) -> None:
    min_stage_count = max(1, int(min_stage_count or 4))
    if len(outline) < min_stage_count:
        raise HTTPException(status_code=500, detail=f"小说总大纲生成失败，有效阶段数不足：{len(outline)}")
    if len(outline) > 40:
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
            await progress_callback("blueprint_setting_lock", f"{slot_group['message']}（{index}/{len(_WORLD_BIBLE_SLOT_GROUPS)}）")

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
        payload = await _call_llm_json_with_stage_retries(
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
            progress_stage="blueprint_setting_lock",
            retry_attempts=3,
        )
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
                "blueprint_setting_lock",
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
    length_contract = _resolve_blueprint_length_contract(blueprint_data)
    length_contract_instruction = _format_length_contract_instruction(length_contract)

    for chunk_index, start in enumerate(range(0, len(normalized_outline), chunk_size), start=1):
        chunk = normalized_outline[start:start + chunk_size]
        chunk_stage_ids = [int(item.get("stage") or 0) for item in chunk if isinstance(item, dict)]
        existing_chunk = [existing_by_stage.get(stage_id) for stage_id in chunk_stage_ids]
        if existing_chunk and all(item is not None and _outline_stage_has_depth(item) for item in existing_chunk):
            enriched_outline.extend([dict(item) for item in existing_chunk if item is not None])
            if progress_callback is not None:
                await progress_callback("blueprint_plot_threads", f"检测到已保存的总纲细化结果，跳过第 {chunk_index}/{total_chunks} 段")
            continue
        if progress_callback is not None:
            await progress_callback("blueprint_plot_threads", f"正在细化小说总大纲（第 {chunk_index}/{total_chunks} 段）")
        chapter_range_example = next(
            (
                str(item.get("expected_chapter_range")).strip()
                for item in chunk
                if isinstance(item, dict) and str(item.get("expected_chapter_range") or "").strip()
            ),
            "沿用输入阶段范围",
        )
        prompt = f"""
[任务目标]
你将收到一部小说的世界骨架和一小段阶段总纲骨架。
请只细化当前这几段阶段，把它们扩写到足够支撑对应篇幅的叙事密度；篇幅可以是短中篇，也可以是长篇，不要机械套用百万字模板。

[篇幅契约]
{length_contract_instruction}

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
7. 保留输入中的 expected_chapter_range，不得在细化时把章节范围扩出篇幅契约。
8. 只输出当前这些阶段的 JSON，不要输出别的阶段。

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
      "expected_chapter_range": "{chapter_range_example}"
    }}
  ]
}}
"""
        payload = await _call_llm_json_with_stage_retries(
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
            progress_stage="blueprint_plot_threads",
            retry_attempts=3,
        )
        items = payload.get("novel_outline") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            raise HTTPException(status_code=500, detail=f"小说总大纲细化失败，第 {chunk_index} 段未返回合法阶段列表")
        chunk_result: List[Dict[str, Any]] = []
        for local_index, item in enumerate(items, start=start + 1):
            if not isinstance(item, dict):
                continue
            normalized = _normalize_novel_outline_stage(item, local_index)
            if normalized is not None:
                original_stage = int(normalized.get("stage") or local_index)
                original_item = existing_by_stage.get(original_stage)
                original_range = (
                    str(original_item.get("expected_chapter_range") or "").strip()
                    if isinstance(original_item, dict)
                    else ""
                )
                if original_range:
                    normalized["expected_chapter_range"] = original_range
                chunk_result.append(normalized)
        if len(chunk_result) != len(chunk):
            raise HTTPException(status_code=500, detail=f"小说总大纲细化失败，第 {chunk_index} 段返回阶段数不完整")
        enriched_outline.extend(chunk_result)
        blueprint_data["novel_outline"] = sorted(enriched_outline, key=lambda item: int(item.get("stage") or 0))
        if checkpoint_callback is not None:
            await checkpoint_callback(
                blueprint_data,
                "blueprint_plot_threads",
                f"已保存总纲细化结果（第 {chunk_index}/{total_chunks} 段）",
            )
    enriched_outline.sort(key=lambda item: int(item.get("stage") or 0))
    _validate_novel_outline_coherence(
        enriched_outline,
        min_stage_count=_resolve_novel_outline_min_stage_count(blueprint_data),
    )
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
        await progress_callback("blueprint_cast_plan", "正在补全主角与核心角色命名")

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
            progress_stage="blueprint_cast_plan",
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
    volume_count_override: int | None = None,
    chapters_per_volume_override: int | None = None,
    long_form_override: bool | None = None,
) -> Dict[str, Any]:
    length_contract = _resolve_blueprint_length_contract(blueprint_data)
    length_contract_instruction = _format_length_contract_instruction(length_contract)
    existing_outline = blueprint_data.get("novel_outline")
    if isinstance(existing_outline, list) and len(existing_outline) >= 4:
        try:
            existing_items = [item for item in existing_outline if isinstance(item, dict)]
            if length_contract and _outline_exceeds_length_contract(existing_items, length_contract):
                existing_items = _remap_outline_ranges_to_length_contract(existing_items, length_contract)
                blueprint_data["novel_outline"] = existing_items
            _validate_novel_outline_coherence(
                existing_items,
                min_stage_count=_resolve_novel_outline_min_stage_count(blueprint_data),
            )
            _validate_novel_outline_depth(existing_items)
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
    length_contract = _resolve_blueprint_length_contract(blueprint_data)
    length_contract_instruction = _format_length_contract_instruction(length_contract)
    title = str(outline_source_context.get("title") or "未命名作品").strip() or "未命名作品"
    if length_contract:
        stage_min = int(length_contract.get("stage_count_min") or 4)
        stage_max = int(length_contract.get("stage_count_max") or 12)
        target_chapters = int(length_contract.get("target_chapter_count") or 0)
        outline_stage_requirement = f"输出 {stage_min}-{stage_max} 个阶段节点"
        chapter_range_example = f"1-{max(1, math.ceil(target_chapters / max(stage_min, 1)))}章"
    else:
        outline_stage_requirement = "输出 8-12 个阶段节点"
        chapter_range_example = "1-60章"


    # 长篇检测：如果目标超过30章或20万字，切换到长篇大纲生成器
    total_chapters = int(blueprint_data.get("total_chapters") or 0)
    total_word_count = int(blueprint_data.get("total_word_count") or int(length_contract.get("target_total_words") or 0))
    if total_chapters > 30 or total_word_count > 200000:
        logger.info("检测到长篇项目（%s章/%s字），尝试使用 LongNovelOutlineGenerator", total_chapters, total_word_count)
        generator = LongNovelOutlineGenerator(llm_service)
        volume_count = max(2, total_chapters // 15) if total_chapters > 0 else 6
        chapters_per_volume = max(8, total_chapters // max(volume_count, 1)) if total_chapters > 0 else 15
        try:
            blueprint_data = await generator.generate_outline(
                blueprint_data=blueprint_data,
                llm_service=llm_service,
                user_id=user_id,
                volume_count=volume_count,
                chapters_per_volume=chapters_per_volume,
                progress_callback=progress_callback,
            )
            if blueprint_data and blueprint_data.get("novel_outline"):
                _validate_novel_outline_coherence(
                    blueprint_data["novel_outline"],
                    min_stage_count=_resolve_novel_outline_min_stage_count(blueprint_data),
                )
                _validate_novel_outline_depth(blueprint_data["novel_outline"])
                return blueprint_data
        except Exception as e:
            logger.warning("LongNovelOutlineGenerator 失败，回退到标准流程: %s", str(e))


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

[篇幅契约]
{length_contract_instruction}
执行优先级：篇幅契约高于通用长篇模板；所有篇幅都启用连续性、角色池和伏笔回收，但不得无视明确章节数。

[硬性要求]
1. {outline_stage_requirement}，每个节点代表一个大阶段、一卷或一大段剧情推进；如果用户明确要求短中篇，不要套用超长篇阶段数量。
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
- expected_chapter_range: 预估章节范围，如“{chapter_range_example}”

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
      "expected_chapter_range": "{chapter_range_example}"
    }}
  ]
}}
"""

    if progress_callback is not None:
        await progress_callback("blueprint_setting_lock", "正在锁定设定与长篇目标（世界规则 / 角色规模 / 伏笔回收）")
        await progress_callback("blueprint_plot_threads", "正在生成小说总大纲（阶段骨架首轮）")

    outline_data = await _call_llm_json_with_stage_retries(
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
        progress_stage="blueprint_plot_threads",
        retry_attempts=3,
    )
    if progress_callback is not None:
        await progress_callback("blueprint_plot_threads", "正在解析小说总大纲骨架")

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
    if length_contract and _outline_exceeds_length_contract(normalized_outline, length_contract):
        normalized_outline = _remap_outline_ranges_to_length_contract(normalized_outline, length_contract)
    if progress_callback is not None:
        await progress_callback("blueprint_foreshadowing", "正在校验小说总大纲骨架连续性")
    _validate_novel_outline_coherence(
        normalized_outline,
        min_stage_count=_resolve_novel_outline_min_stage_count(blueprint_data),
    )

    blueprint_data["novel_outline"] = normalized_outline
    if checkpoint_callback is not None:
        await checkpoint_callback(blueprint_data, "blueprint_foreshadowing", "已保存小说总大纲骨架")
    if not world_bible_prepared:
        if progress_callback is not None:
            await progress_callback("blueprint_setting_lock", "正在补全设定锁定包（世界运行 / 势力 / 生存生活逻辑）")
        blueprint_data = await _generate_novel_world_bible(
            llm_service=llm_service,
            blueprint_data=blueprint_data,
            user_id=user_id,
            progress_callback=progress_callback,
            checkpoint_callback=checkpoint_callback,
        )
    if progress_callback is not None:
        await progress_callback("blueprint_foreshadowing", "正在细化角色生命周期、伏笔回收窗口和阶段任务")
    blueprint_data["novel_outline"] = await _enrich_novel_outline_in_chunks(
        llm_service=llm_service,
        blueprint_data=blueprint_data,
        user_id=user_id,
        progress_callback=progress_callback,
        checkpoint_callback=checkpoint_callback,
    )
    if length_contract and _outline_exceeds_length_contract(blueprint_data["novel_outline"], length_contract):
        blueprint_data["novel_outline"] = _remap_outline_ranges_to_length_contract(
            blueprint_data["novel_outline"],
            length_contract,
        )
        if checkpoint_callback is not None:
            await checkpoint_callback(blueprint_data, "blueprint_plot_threads", "已按篇幅契约校正小说总纲章节范围")
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
    target_chapter_outline_count = _resolve_blueprint_chapter_outline_count(blueprint_data)
    if isinstance(existing_outline, list) and len(existing_outline) >= target_chapter_outline_count:
        return blueprint_data

    outline_source_context = _build_chapter_outline_source_context(blueprint_data)
    title = str(outline_source_context.get("title") or "未命名作品").strip() or "未命名作品"

    outline_system_prompt = (
        "你是资深长篇网文总策划，擅长把小说概念蓝图拆成真正可写的首卷章节大纲。"
        "你只输出 JSON。"
    )

    normalized_outline: List[Dict[str, Any]] = [item for item in existing_outline if isinstance(item, dict)] if isinstance(existing_outline, list) else []
    chapter_batches = _build_chapter_batches(target_chapter_outline_count, batch_size=4)
    for batch_index, (start_chapter, end_chapter) in enumerate(chapter_batches, start=1):
        existing_batch = [
            chapter for chapter in normalized_outline
            if start_chapter <= int(chapter.get("chapter_number") or 0) <= end_chapter
        ]
        if _is_chapter_outline_batch_complete(existing_batch, start_chapter, end_chapter):
            if progress_callback is not None:
                await progress_callback("blueprint_chapter_plan", f"检测到已保存的章节批次，跳过第 {batch_index}/{len(chapter_batches)} 批（{start_chapter}-{end_chapter} 章）")
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
            await progress_callback("blueprint_chapter_plan", f"正在生成可执行章节大纲（第 {batch_index}/{len(chapter_batches)} 批，第 {start_chapter}-{end_chapter} 章）")

        outline_data = await _call_llm_json_with_stage_retries(
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
            progress_stage="blueprint_chapter_plan",
            retry_attempts=3,
        )
        if progress_callback is not None:
            await progress_callback("blueprint_chapter_plan", f"正在解析章节大纲批次（第 {start_chapter}-{end_chapter} 章）")

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
                "blueprint_chapter_plan",
                f"已保存章节批次结果（第 {batch_index}/{len(chapter_batches)} 批，第 {start_chapter}-{end_chapter} 章）",
            )

    normalized_outline.sort(key=lambda chapter: chapter["chapter_number"])
    chapter_numbers = [chapter["chapter_number"] for chapter in normalized_outline]
    if len(normalized_outline) < target_chapter_outline_count:
        raise HTTPException(status_code=500, detail=f"章节大纲生成失败，返回的有效章节数不足：{len(normalized_outline)}")
    if chapter_numbers[:target_chapter_outline_count] != list(range(1, target_chapter_outline_count + 1)):
        raise HTTPException(status_code=500, detail=f"章节大纲生成失败，前 {target_chapter_outline_count} 章的章节号不连续或存在缺失")
    blueprint_data["chapter_outline"] = normalized_outline[:target_chapter_outline_count]
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
    resolved_outline_target = _resolve_blueprint_chapter_outline_count(blueprint_data)
    existing_numbers: List[int] = []
    for item in normalized_chapter_outline:
        try:
            chapter_number = int(item.get("chapter_number") or 0)
        except (TypeError, ValueError):
            continue
        if chapter_number > 0:
            existing_numbers.append(chapter_number)
    target_chapter_outline_count = min(
        resolved_outline_target,
        max(existing_numbers) if existing_numbers else len(normalized_chapter_outline),
    )
    if target_chapter_outline_count <= 0:
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
    chapter_batches = _build_chapter_batches(target_chapter_outline_count, batch_size=4)
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
                await progress_callback("blueprint_chapter_plan", f"正在润色章节大纲（第 {batch_index}/{len(chapter_batches)} 批，第 {start_chapter}-{end_chapter} 章）")
            polished_data = await _call_llm_json_with_stage_retries(
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
                progress_stage="blueprint_chapter_plan",
                retry_attempts=3,
            )
            if progress_callback is not None:
                await progress_callback("blueprint_chapter_plan", f"正在解析润色结果（第 {start_chapter}-{end_chapter} 章）")
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
                    "blueprint_chapter_plan",
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


def _import_job_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _import_job_error(code: str, message: str, *, detail: Any = None, retryable: bool = True) -> Dict[str, Any]:
    if detail is None:
        detail_text = None
    elif isinstance(detail, str):
        detail_text = detail[:800]
    else:
        try:
            detail_text = json.dumps(detail, ensure_ascii=False, default=str)[:800]
        except TypeError:
            detail_text = str(detail)[:800]
    return {"code": code, "message": message, "detail": detail_text, "retryable": retryable}


def _import_storage_path(user_id: int, run_id: str) -> Path:
    return _IMPORT_STORAGE_ROOT / str(int(user_id)) / f"{run_id}.bin"


def _validated_import_storage_path(user_id: int, run_id: str, storage_value: Any) -> Optional[Path]:
    """仅允许读取当前用户、当前任务对应的规范导入文件。"""
    if not isinstance(storage_value, str) or not storage_value.strip():
        return None
    expected = _import_storage_path(user_id, run_id).resolve()
    try:
        candidate = Path(storage_value).resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    if candidate != expected or not candidate.is_file():
        return None
    return candidate


def _serialize_import_job(job: Dict[str, Any]) -> ImportNovelJobResponse:
    return ImportNovelJobResponse(
        run_id=str(job.get("run_id") or ""),
        status=str(job.get("status") or "idle"),
        progress_stage=str(job.get("progress_stage") or job.get("status") or "idle"),
        progress_message=str(job.get("progress_message") or ""),
        started_at=job.get("started_at"),
        updated_at=job.get("updated_at"),
        filename=job.get("filename"),
        project_id=job.get("project_id"),
        metrics=dict(job.get("metrics") or {}),
        error=job.get("error"),
    )


def _import_runtime_job_snapshot(job: Dict[str, Any]) -> Dict[str, Any]:
    """返回可持久化的旧稿导入状态快照，不保存上传正文或其他大对象。"""
    fields = (
        "run_id",
        "user_id",
        "status",
        "progress_stage",
        "progress_message",
        "started_at",
        "updated_at",
        "filename",
        "project_id",
        "metrics",
        "error",
        "storage_path",
    )
    snapshot = {key: job.get(key) for key in fields if key in job}
    snapshot["task_domain"] = "novel_import"
    return snapshot


def _import_runtime_datetime(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        return value.isoformat()
    return value if isinstance(value, str) else None


def _rebuild_import_job_from_runtime(task: Any, events: List[Any]) -> Dict[str, Any]:
    """从 TaskRuntime 的快照/事件恢复旧稿导入路由状态。"""
    task_payload = dict(getattr(task, "payload", None) or {})
    snapshot: Dict[str, Any] = {}
    for key in ("legacy_job", "novel_import_job", "job"):
        candidate = task_payload.get(key)
        if isinstance(candidate, dict) and candidate.get("task_domain", "novel_import") == "novel_import":
            snapshot.update(candidate)
    for event in events:
        payload = dict(getattr(event, "payload", None) or {})
        candidate = payload.get("legacy_job") or payload.get("novel_import_job") or payload.get("job")
        if isinstance(candidate, dict) and candidate.get("task_domain", "novel_import") == "novel_import":
            snapshot.update(candidate)

    runtime_status = str(getattr(task, "status", TaskRuntimeStatus.QUEUED.value) or TaskRuntimeStatus.QUEUED.value)
    stage = str(snapshot.get("progress_stage") or getattr(task, "stage", None) or runtime_status)
    message = str(snapshot.get("progress_message") or getattr(task, "message", None) or "")
    persisted_status = str(snapshot.get("status") or "")
    if runtime_status == TaskRuntimeStatus.QUEUED.value:
        legacy_status = "queued"
    elif runtime_status == TaskRuntimeStatus.RUNNING.value:
        legacy_status = persisted_status if persisted_status in _IMPORT_RUNNING_STATUSES else (
            stage if stage in _IMPORT_RUNNING_STATUSES else "import_reading"
        )
    elif runtime_status in {TaskRuntimeStatus.CANCELLING.value, TaskRuntimeStatus.STALE.value}:
        legacy_status = persisted_status if persisted_status in _IMPORT_RUNNING_STATUSES else "queued"
    elif runtime_status == TaskRuntimeStatus.SUCCEEDED.value:
        legacy_status = "successful"
    elif runtime_status == TaskRuntimeStatus.CANCELLED.value:
        legacy_status = "cancelled"
    elif runtime_status == TaskRuntimeStatus.FAILED.value:
        legacy_status = "failed"
    else:
        legacy_status = persisted_status or "queued"

    snapshot.update(
        {
            "run_id": str(snapshot.get("run_id") or getattr(task, "task_id", "")),
            "user_id": int(snapshot.get("user_id") or getattr(task, "owner_user_id", 0) or 0),
            "status": legacy_status,
            "progress_stage": stage,
            "progress_message": message,
            "started_at": _import_runtime_datetime(
                snapshot.get("started_at") or getattr(task, "started_at", None)
            ),
            "updated_at": _import_runtime_datetime(
                snapshot.get("updated_at") or getattr(task, "updated_at", None)
            ),
            "runtime_task_registered": True,
            "_runtime_status": runtime_status,
            "_runtime_retry_count": int(getattr(task, "retry_count", 0) or 0),
            "_runtime_payload": task_payload,
        }
    )
    if not snapshot.get("filename") and isinstance(task_payload.get("filename"), str):
        snapshot["filename"] = task_payload["filename"]
    if not snapshot.get("project_id"):
        snapshot["project_id"] = getattr(task, "project_id", None) or getattr(task, "result_ref", None)
    if legacy_status == "failed" and not snapshot.get("error"):
        snapshot["error"] = _import_job_error(
            "import_failed",
            "旧稿导入失败",
            detail=getattr(task, "error_detail", None),
            retryable=True,
        )
    elif legacy_status == "cancelled" and not snapshot.get("error"):
        snapshot["error"] = _import_job_error(
            "import_cancelled", "旧稿导入任务已取消", retryable=True
        )
    return snapshot


async def _claim_import_runtime(run_id: str, user_id: int) -> bool:
    """通过持久化租约领取恢复任务，避免多进程重复导入。"""
    async with AsyncSessionLocal() as session:
        if not hasattr(session, "execute"):
            return True
        try:
            await TaskRuntimeService(session).claim(
                run_id,
                lease_owner=_IMPORT_LEASE_OWNER,
                stale_after_seconds=180,
                owner_user_id=int(user_id),
            )
            return True
        except (TaskRuntimeNotFound, TaskRuntimeConflict):
            return False
        except Exception:
            logger.warning("领取旧稿导入任务失败：run_id=%s", run_id, exc_info=True)
            return False


def _schedule_import_recovery(job: Dict[str, Any]) -> bool:
    run_id = str(job.get("run_id") or "")
    user_id = int(job.get("user_id") or 0)
    runtime_payload = job.get("_runtime_payload") if isinstance(job.get("_runtime_payload"), dict) else {}
    storage_value = runtime_payload.get("storage_path") or job.get("storage_path")
    storage = _validated_import_storage_path(user_id, run_id, storage_value)
    runtime_status = str(job.get("_runtime_status") or "")
    if not run_id or user_id <= 0 or storage is None:
        return False
    if runtime_status not in {TaskRuntimeStatus.QUEUED.value, TaskRuntimeStatus.STALE.value}:
        return False
    if run_id in _IMPORT_SCHEDULED_RUNS:
        return False
    _IMPORT_SCHEDULED_RUNS.add(run_id)
    asyncio.create_task(
        _run_import_novel_job(
            run_id,
            user_id,
            str(runtime_payload.get("filename") or job.get("filename") or "import.txt"),
            storage_path=str(storage),
        )
    )
    return True


def _import_job_has_active_runtime(job: Dict[str, Any]) -> bool:
    runtime_status = str(job.get("_runtime_status") or "")
    if runtime_status:
        return runtime_status in _IMPORT_RUNTIME_ACTIVE_STATUSES
    return str(job.get("status") or "") in _IMPORT_RUNNING_STATUSES


async def _load_persisted_import_job(
    session: Any,
    *,
    user_id: int,
    run_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """按用户和任务类型从 TaskRuntime 查找旧稿导入任务。"""
    if not hasattr(session, "execute"):
        return None
    runtime = TaskRuntimeService(session)
    if run_id:
        try:
            task = await runtime.get_task(run_id, int(user_id))
        except TaskRuntimeNotFound:
            return None
        if task.task_type != "novel_import":
            return None
    else:
        tasks = await runtime.list_tasks(owner_user_id=int(user_id), limit=100)
        matching = [task for task in tasks if task.task_type == "novel_import"]
        if not matching:
            return None
        task = matching[0]
    try:
        events = await runtime.list_events(task.task_id, owner_user_id=int(user_id), limit=500)
    except TaskRuntimeNotFound:
        events = []
    return _rebuild_import_job_from_runtime(task, events)


async def _append_import_task_runtime_event(
    job: Dict[str, Any],
    *,
    session: Any = None,
) -> None:
    if not job.get("runtime_task_registered"):
        return
    run_id = str(job.get("run_id") or "")
    user_id = job.get("user_id")
    if not run_id or user_id is None:
        return
    status_raw = str(job.get("status") or "queued")
    terminal_map = {
        "successful": (TaskRuntimeStatus.SUCCEEDED.value, TaskRuntimeEventType.TASK_COMPLETED.value),
        "failed": (TaskRuntimeStatus.FAILED.value, TaskRuntimeEventType.TASK_FAILED.value),
        "cancelled": (TaskRuntimeStatus.CANCELLED.value, TaskRuntimeEventType.TASK_CANCELLED.value),
    }
    runtime_status, event_type = terminal_map.get(
        status_raw,
        (
            TaskRuntimeStatus.QUEUED.value
            if status_raw == "queued"
            else TaskRuntimeStatus.CANCELLING.value
            if status_raw == "cancelling"
            else TaskRuntimeStatus.RUNNING.value,
            TaskRuntimeEventType.PROGRESS.value,
        ),
    )
    async def persist(runtime_session: AsyncSession) -> None:
        service = TaskRuntimeService(runtime_session)
        await service.get_task(run_id, int(user_id))
        snapshot = _import_runtime_job_snapshot(job)
        await service.merge_payload(
            run_id,
            {"legacy_job": snapshot, "task_domain": "novel_import"},
            owner_user_id=int(user_id),
        )
        await service.append_event(
            run_id,
            event_type=event_type,
            status=runtime_status,
            stage=str(job.get("progress_stage") or status_raw),
            progress=100.0 if runtime_status in TERMINAL_STATUSES else 0.0,
            message=str(job.get("progress_message") or ""),
            idempotency_key=f"import-state:{job.get('updated_at') or _import_job_now_iso()}",
            payload={
                "task_domain": "novel_import",
                "legacy_status": status_raw,
                "filename": job.get("filename"),
                "legacy_job": snapshot,
            },
            owner_user_id=int(user_id),
        )
        task = await service.get_task(run_id, int(user_id))
        if runtime_status == TaskRuntimeStatus.SUCCEEDED.value and job.get("project_id"):
            task.project_id = str(job["project_id"])
            task.result_ref = str(job["project_id"])
        if runtime_status == TaskRuntimeStatus.FAILED.value:
            error = job.get("error") or {}
            task.error_code = str(error.get("code") or "import_failed")
            task.error_detail = str(error.get("detail") or error.get("message") or "")
        elif runtime_status == TaskRuntimeStatus.CANCELLED.value:
            task.error_code = "import_cancelled"
            task.error_detail = str((job.get("error") or {}).get("message") or "旧稿导入任务已取消")
        await runtime_session.commit()

    try:
        if hasattr(session, "execute"):
            await persist(session)
        else:
            async with AsyncSessionLocal() as runtime_session:
                await persist(runtime_session)
    except Exception:
        logger.warning("写入导入 TaskRuntime 事件失败：run_id=%s", run_id, exc_info=True)


async def _set_import_job_state(
    run_id: str,
    *,
    user_id: Optional[int] = None,
    **updates: Any,
) -> Dict[str, Any]:
    async with _IMPORT_JOB_LOCK:
        job = dict(_IMPORT_JOBS.get(run_id) or {})
    if not job and user_id is not None:
        try:
            async with AsyncSessionLocal() as runtime_session:
                restored = await _load_persisted_import_job(
                    runtime_session,
                    user_id=int(user_id),
                    run_id=run_id,
                )
            if restored:
                job = restored
        except Exception:
            logger.warning("恢复导入任务状态失败：run_id=%s", run_id, exc_info=True)
    async with _IMPORT_JOB_LOCK:
        job = _IMPORT_JOBS.get(run_id) or job
        if not job:
            job = {
                "run_id": run_id,
                "user_id": user_id,
                "status": "idle",
                "progress_stage": "idle",
                "runtime_task_registered": user_id is not None,
            }
            _IMPORT_JOBS[run_id] = job
        if job.get("status") == "cancelled" and updates.get("status") != "cancelled":
            return dict(job)
        if "metrics" in updates:
            merged_metrics = dict(job.get("metrics") or {})
            merged_metrics.update(updates.pop("metrics") or {})
            updates["metrics"] = merged_metrics
        job.update(updates)
        job["updated_at"] = _import_job_now_iso()
        snapshot = dict(job)
    await _append_import_task_runtime_event(snapshot)
    return snapshot


async def _is_import_job_cancelled(run_id: str, user_id: Optional[int] = None) -> bool:
    try:
        async with AsyncSessionLocal() as runtime_session:
            task = await TaskRuntimeService(runtime_session).get_task(run_id, user_id)
            if task.task_type != "novel_import":
                return False
            if task.status in {TaskRuntimeStatus.CANCELLING.value, TaskRuntimeStatus.CANCELLED.value}:
                return True
            legacy_job = dict(task.payload or {}).get("legacy_job")
            return isinstance(legacy_job, dict) and legacy_job.get("status") == "cancelled"
    except Exception:
        async with _IMPORT_JOB_LOCK:
            job = _IMPORT_JOBS.get(run_id) or {}
            return job.get("status") in {"cancelled", "import_cancelled", "cancelling"}


class _BufferedImportUpload:
    def __init__(self, filename: str, content: bytes):
        self.filename = filename
        self._content = content

    async def read(self) -> bytes:
        return self._content


async def _run_import_novel_job(
    run_id: str,
    user_id: int,
    filename: str,
    content: Optional[bytes] = None,
    *,
    storage_path: Optional[str] = None,
) -> None:
    async def progress(stage: str, message: str, metrics: Optional[Dict[str, Any]] = None) -> None:
        await _set_import_job_state(
            run_id,
            user_id=user_id,
            status=stage,
            progress_stage=stage,
            progress_message=message,
            metrics=metrics or {},
        )

    try:
        if not await _claim_import_runtime(run_id, user_id):
            return
        if storage_path is not None:
            validated = _validated_import_storage_path(user_id, run_id, storage_path)
            if validated is None:
                raise ValueError("旧稿导入文件路径无效")
            content = validated.read_bytes()
        if content is None:
            raise ValueError("旧稿导入正文缺失")
        if await _is_import_job_cancelled(run_id, user_id):
            return
        await progress("import_reading", "正在读取旧稿文件", {"filename": filename, "bytes": len(content)})
        async with AsyncSessionLocal() as job_session:
            import_service = ImportService(job_session)
            project_id = await import_service.import_novel_from_file(
                user_id,
                _BufferedImportUpload(filename, content),  # type: ignore[arg-type]
                progress_callback=progress,
                should_cancel=lambda: _is_import_job_cancelled(run_id, user_id),
            )
        await _set_import_job_state(
            run_id,
            user_id=user_id,
            status="successful",
            progress_stage="successful",
            progress_message="旧稿导入完成，已创建项目",
            project_id=project_id,
            error=None,
        )
    except ImportCancelledError:
        await _set_import_job_state(
            run_id,
            user_id=user_id,
            status="cancelled",
            progress_stage="cancelled",
            progress_message="旧稿导入任务已取消",
            error=_import_job_error("import_cancelled", "旧稿导入任务已取消", retryable=True),
        )
    except HTTPException as exc:
        await _set_import_job_state(
            run_id,
            user_id=user_id,
            status="failed",
            progress_stage="failed",
            progress_message="旧稿导入失败",
            error=_import_job_error(
                "import_failed",
                "旧稿导入失败",
                detail=exc.detail,
                retryable=exc.status_code >= 500,
            ),
        )
    except Exception as exc:  # noqa: BLE001 - background job must expose failures
        logger.exception("旧稿导入后台任务失败: run_id=%s filename=%s", run_id, filename)
        await _set_import_job_state(
            run_id,
            user_id=user_id,
            status="failed",
            progress_stage="failed",
            progress_message="旧稿导入失败",
            error=_import_job_error("import_failed", "旧稿导入失败", detail=exc, retryable=True),
        )
    finally:
        _IMPORT_SCHEDULED_RUNS.discard(run_id)


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


@router.post("/import/start", response_model=ImportNovelJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_import_novel(
    background_tasks: BackgroundTasks,
    file: UploadFile,
    session: AsyncSession | None = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> ImportNovelJobResponse:
    """启动旧稿导入后台任务。"""
    user_id = int(current_user.id)
    filename = file.filename or "import.txt"
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件内容为空")

    async with _IMPORT_JOB_LOCK:
        existing_run_id = _IMPORT_USER_RUNS.get(user_id)
        existing = _IMPORT_JOBS.get(existing_run_id or "")
        if existing and _import_job_has_active_runtime(existing):
            return _serialize_import_job(existing)

        # 进程重启后内存索引为空时，先从 TaskRuntime 恢复活动任务，避免重复导入。
        if session is not None and hasattr(session, "execute"):
            restored = await _load_persisted_import_job(session, user_id=user_id)
            if restored and _import_job_has_active_runtime(restored):
                _IMPORT_JOBS[restored["run_id"]] = dict(restored)
                _IMPORT_USER_RUNS[user_id] = restored["run_id"]
                return _serialize_import_job(restored)

        run_id = str(uuid.uuid4())
        storage_path = _import_storage_path(user_id, run_id)
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        storage_path.write_bytes(content)
        now = _import_job_now_iso()
        job = {
            "run_id": run_id,
            "user_id": user_id,
            "status": "queued",
            "progress_stage": "queued",
            "progress_message": "旧稿导入任务已入队",
            "started_at": now,
            "updated_at": now,
            "filename": filename,
            "project_id": None,
            "metrics": {"bytes": len(content)},
            "error": None,
            "storage_path": str(storage_path),
        }
        if session is not None and hasattr(session, "execute"):
            await TaskRuntimeService(session).create_task(
                task_id=run_id,
                task_type="novel_import",
                idempotency_key=f"novel-import:{run_id}",
                owner_user_id=user_id,
                payload={
                    "run_id": run_id,
                    "filename": filename,
                    "bytes": len(content),
                    "storage_path": str(storage_path),
                    "task_domain": "novel_import",
                    "legacy_job": _import_runtime_job_snapshot(job),
                },
            )
            job["runtime_task_registered"] = True
        _IMPORT_JOBS[run_id] = job
        _IMPORT_USER_RUNS[user_id] = run_id

    background_tasks.add_task(_run_import_novel_job, run_id, user_id, filename, content)
    return _serialize_import_job(job)


@router.get("/import/status", response_model=ImportNovelJobResponse)
async def get_import_novel_status(
    run_id: Optional[str] = Query(default=None),
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession | None = Depends(get_session),
) -> ImportNovelJobResponse:
    """读取当前用户最近一次旧稿导入任务状态。"""
    user_id = int(current_user.id)
    requested_run_id = run_id if isinstance(run_id, str) else None
    async with _IMPORT_JOB_LOCK:
        resolved_run_id = requested_run_id or _IMPORT_USER_RUNS.get(user_id)
        job = dict(_IMPORT_JOBS.get(resolved_run_id or "") or {})
        if job and job.get("user_id") not in {None, user_id}:
            job = {}
    # 数据库可用时，TaskRuntime 是唯一状态真相源；内存快照可能落后于取消/失败终态。
    restored = await _load_persisted_import_job(
        session,
        user_id=user_id,
        run_id=requested_run_id or resolved_run_id,
    ) if hasattr(session, "execute") else None
    if restored:
        async with _IMPORT_JOB_LOCK:
            _IMPORT_JOBS[restored["run_id"]] = dict(restored)
            _IMPORT_USER_RUNS[user_id] = restored["run_id"]
        job = restored
    if job:
        if _import_job_has_active_runtime(job):
            _schedule_import_recovery(job)
        return _serialize_import_job(job)
    return ImportNovelJobResponse(
        run_id=requested_run_id or "",
        status="idle",
        progress_stage="idle",
        progress_message="暂无旧稿导入任务",
    )


@router.post("/import/cancel", response_model=ImportNovelJobResponse)
async def cancel_import_novel(
    run_id: Optional[str] = Query(default=None),
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession | None = Depends(get_session),
) -> ImportNovelJobResponse:
    """取消当前用户最近一次旧稿导入任务。"""
    user_id = int(current_user.id)
    requested_run_id = run_id if isinstance(run_id, str) else None
    async with _IMPORT_JOB_LOCK:
        resolved_run_id = requested_run_id or _IMPORT_USER_RUNS.get(user_id)
        job = _IMPORT_JOBS.get(resolved_run_id or "")
    # 取消操作也必须先读取持久化状态，不能让旧 worker 的内存快照遮蔽数据库。
    restored = await _load_persisted_import_job(
        session,
        user_id=user_id,
        run_id=requested_run_id or resolved_run_id,
    ) if hasattr(session, "execute") else None
    if restored:
        async with _IMPORT_JOB_LOCK:
            _IMPORT_JOBS[restored["run_id"]] = dict(restored)
            _IMPORT_USER_RUNS[user_id] = restored["run_id"]
        job = restored
    if not job:
        return ImportNovelJobResponse(
            run_id=requested_run_id or "",
            status="idle",
            progress_stage="idle",
            progress_message="暂无可取消的旧稿导入任务",
        )
    runtime_status = str(job.get("_runtime_status") or "")
    runtime_payload = job.get("_runtime_payload") if isinstance(job.get("_runtime_payload"), dict) else {}
    # _rebuild_import_job_from_runtime exposes the durable lease indirectly
    # through the task payload only for compatibility; a running row without a
    # live lease is an unclaimed orphan and can be finalized immediately.
    worker_active = runtime_status == TaskRuntimeStatus.CANCELLING.value or (
        runtime_status == TaskRuntimeStatus.RUNNING.value
        and bool(runtime_payload.get("lease_owner"))
    )
    async with _IMPORT_JOB_LOCK:
        if job.get("user_id") not in {None, user_id}:
            raise HTTPException(status_code=404, detail="导入任务不存在")
        if worker_active:
            job.update({
                "status": "cancelling",
                "progress_stage": "cancelling",
                "progress_message": "已请求取消旧稿导入任务，等待后台安全收敛",
                "updated_at": _import_job_now_iso(),
                "error": _import_job_error(
                    "import_cancelling", "已请求取消旧稿导入任务，等待后台安全收敛", retryable=True
                ),
            })
        elif job.get("status") in _IMPORT_CANCELABLE_STATUSES:
            job.update({
                "status": "cancelled",
                "progress_stage": "cancelled",
                "progress_message": "旧稿导入任务已取消",
                "updated_at": _import_job_now_iso(),
                "error": _import_job_error("import_cancelled", "旧稿导入任务已取消", retryable=True),
            })
        elif job.get("status") in {"import_saving", "import_ledger_rebuild"}:
            job.update({
                "progress_message": "正在安全写入项目，保存阶段不能中途取消",
                "updated_at": _import_job_now_iso(),
            })
        snapshot = dict(job)

    if hasattr(session, "execute") and runtime_status in {
        TaskRuntimeStatus.QUEUED.value,
        TaskRuntimeStatus.RUNNING.value,
        TaskRuntimeStatus.CANCELLING.value,
    }:
        try:
            await TaskRuntimeService(session).request_cancel(
                str(snapshot["run_id"]),
                owner_user_id=user_id,
                finalize_unclaimed=runtime_status == TaskRuntimeStatus.QUEUED.value,
            )
        except (TaskRuntimeNotFound, TaskRuntimeConflict):
            logger.info("导入任务取消请求发生状态竞争：run_id=%s", snapshot["run_id"])
    await _append_import_task_runtime_event(snapshot, session=session if hasattr(session, "execute") else None)
    if hasattr(session, "execute") and runtime_status == TaskRuntimeStatus.QUEUED.value:
        refreshed = await _load_persisted_import_job(
            session, user_id=user_id, run_id=str(snapshot["run_id"])
        )
        if refreshed:
            snapshot = refreshed
    return _serialize_import_job(snapshot)


@router.post("/import", response_model=Dict[str, str], status_code=status.HTTP_201_CREATED, deprecated=True)
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


def _backfill_quality_observability_metrics(
    metrics: Dict[str, Any],
    *,
    content: Optional[str],
    chapter_mission: Optional[dict],
    chapter_number: int = 1,
) -> Dict[str, Any]:
    """只读回填旧质量快照缺失的观测字段。

    不写数据库、不返回正文；新快照已有字段优先，历史版本才从保存的正文重算。
    """
    result = dict(metrics or {})
    # T-14：旧版本已保存 passed 结果但没有 evaluated 标记；只读补齐状态，
    # 避免趋势页把“已评估”误留成未知。短正文且三个结果都为空时，明确标记为未评估。
    if result.get("event_density_evaluated") is None:
        density_fields = ("event_density_passed", "state_change_interval_passed", "long_chapter_density_passed")
        if any(result.get(key) is not None for key in density_fields):
            result["event_density_evaluated"] = True
        elif content is not None and len("".join(str(content).split())) < PipelineOrchestrator.EVENT_DENSITY_MIN_SAMPLE_CHARS:
            result["event_density_evaluated"] = False
            result["event_density_skip_reason"] = result.get("event_density_skip_reason") or "sample_too_short"
    # E-10：历史快照若未保存任务书体检结果，按已保存任务书只读重算；
    # 没有任务书时保持 None，不能把“未检查”伪装成“任务书正常”。
    if result.get("mission_quality_codes") is None and isinstance(chapter_mission, dict):
        target_word_count = int(result.get("target_word_count") or 0)
        mission_quality = PipelineOrchestrator._evaluate_mission_quality(
            chapter_mission,
            target_word_count,
            chapter_number=max(1, int(chapter_number or 1)),
        )
        result["mission_quality_codes"] = list(mission_quality.get("mission_quality_codes") or [])
    # E-07：历史快照可能保存了任务书承接锚点和正文，却没有保存 continuity
    # 观测字段。趋势读取只读重算，并且只补缺失/显式 null，不覆盖已有结果。
    continuity_keys = (
        "continuity_inherit_missing",
        "continuity_inherit_late",
        "continuity_inherit_hit_count",
        "inherit_hit_count",
        "continuity_inherit_total_hit_count",
        "continuity_inherit_match_mode",
    )
    if content is not None and isinstance(chapter_mission, dict):
        continuity_missing = any(result.get(key) is None for key in continuity_keys)
        if continuity_missing:
            continuity = PipelineOrchestrator._evaluate_continuity_inherit(
                str(content), chapter_mission
            )
            for key in continuity_keys:
                if result.get(key) is None and key in continuity:
                    result[key] = continuity.get(key)
    # T-08/T-15：旧 guard 将静态段和章末压力保存在嵌套对象；趋势字段是扁平契约，
    # 只读展开缺失键，不能让历史章节因快照版本不同而显示成“未观测”。
    nested_quality_sources = {
        "static_description_runs": ("static_paragraph_count", "max_static_run"),
        "ending_pressure": (
            "ending_pressure_passed",
            "ending_semantic_hit_count",
            "ending_weak_hit_count",
            "flat_closure_markers",
            "ending_core_chars",
            "ending_core_semantic_hit_count",
            "ending_core_weak_hit_count",
            "ending_core_deflating",
        ),
    }
    for source_key, target_keys in nested_quality_sources.items():
        nested = result.get(source_key)
        if not isinstance(nested, dict):
            continue
        for key in target_keys:
            if result.get(key) is None and key in nested:
                result[key] = nested.get(key)
    nested_sources = {
        "reversal_quality": ("reversal_signal_count", "reversal_in_late_section"),
        "dialogue_speaker_distribution": ("speaker_count", "dominant_speaker_ratio"),
        # 历史 guard 只保存嵌套诊断对象时，也必须还原趋势 API 的扁平字段。
        "static_description_runs": ("static_paragraph_count", "max_static_run"),
        "ending_pressure": (
            "ending_pressure_passed",
            "ending_semantic_hit_count",
            "ending_weak_hit_count",
            "ending_core_chars",
            "ending_core_semantic_hit_count",
            "ending_core_weak_hit_count",
            "ending_core_deflating",
        ),
    }
    for source_key, target_keys in nested_sources.items():
        nested = result.get(source_key)
        if isinstance(nested, dict):
            for key in target_keys:
                if result.get(key) is None and key in nested and nested.get(key) is not None:
                    result[key] = nested[key]
    ending_pressure = result.get("ending_pressure")
    if isinstance(ending_pressure, dict):
        if result.get("flat_closure_markers") is None and ending_pressure.get("flat_closure_markers") is not None:
            result["flat_closure_markers"] = list(ending_pressure.get("flat_closure_markers") or [])

    needed = {
        "reversal_signal_count", "reversal_in_late_section",
        "speaker_count", "dominant_speaker_ratio",
        "hard_scene_cut_count", "summary_scene_cut_count", "scene_transition_warning",
    }
    # 旧 JSON 快照可能显式保存 null；null 与缺键都表示“尚未观测”，允许只读回填。
    missing = {key for key in needed if result.get(key) is None}
    if not content or not missing:
        return result

    text = str(content)
    paragraphs = [item for item in text.splitlines() if item.strip()]
    word_count = PipelineOrchestrator._count_words(text)
    focus_names = PipelineOrchestrator._collect_focus_character_names(chapter_mission)
    if {"speaker_count", "dominant_speaker_ratio"} & missing:
        speaker = PipelineOrchestrator._evaluate_dialogue_speaker_distribution(text)
        for key in ("speaker_count", "dominant_speaker_ratio"):
            if key in missing:
                result[key] = speaker.get(key)
    if {"hard_scene_cut_count", "summary_scene_cut_count", "scene_transition_warning"} & missing:
        transition = PipelineOrchestrator._evaluate_scene_transition_clarity(paragraphs)
        for key in ("hard_scene_cut_count", "summary_scene_cut_count", "scene_transition_warning"):
            if key in missing:
                result[key] = transition.get(key)
    if {"reversal_signal_count", "reversal_in_late_section"} & missing:
        reversal = PipelineOrchestrator._evaluate_reversal_quality(text)
        for key in ("reversal_signal_count", "reversal_in_late_section"):
            if key in missing:
                result[key] = reversal.get(key)
    # E-04 is also a historical compact-snapshot backfill when old rows lack it.
    balance_keys = {"dialogue_ratio", "action_ratio", "description_ratio", "content_balance_penalty"}
    balance_missing = {key for key in balance_keys if result.get(key) is None}
    if balance_missing:
        balance = PipelineOrchestrator._evaluate_content_balance(
            paragraphs,
            word_count=word_count,
            character_names=focus_names,
        )
        for key in balance_missing:
            result[key] = balance.get(key)
    return result


def _redact_quality_trend_patch_suggestions(raw_suggestions: Any) -> List[Dict[str, str]]:
    """Expose actionable patch context without returning chapter prose in trend payloads."""
    if not isinstance(raw_suggestions, list):
        return []
    redacted: List[Dict[str, str]] = []
    for item in raw_suggestions:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip()
        suggestion = str(item.get("suggestion") or "").strip()
        if not code or not suggestion:
            continue
        # Runtime continuity hints can include an entire previous-chapter tail.
        if "（待承接：" in suggestion:
            suggestion = suggestion.split("（待承接：", 1)[0].rstrip() + "（待承接：上一章遗留）"
        redacted.append({"code": code[:120], "suggestion": suggestion[:500]})
    return redacted


@router.get("/{project_id}/quality-trend")
async def get_quality_trend(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> Dict[str, Any]:
    """Return redacted, cross-chapter quality metrics from existing version metadata."""
    await get_project_owner_guard(project_id, session, current_user)
    rows = list((await session.execute(
        select(Chapter, ChapterVersion)
        .outerjoin(ChapterVersion, Chapter.selected_version_id == ChapterVersion.id)
        .where(Chapter.project_id == project_id)
        .order_by(Chapter.chapter_number.asc())
    )).all())
    chapters: List[Dict[str, Any]] = []
    blocker_counts: Dict[str, int] = {}
    warning_counts: Dict[str, int] = {}
    exemption_counts: Dict[str, int] = {}
    for chapter, version in rows:
        metadata = dict(getattr(version, "metadata", None) or {}) if version is not None else {}
        metrics = dict(metadata.get("quality_metrics") or {})
        # 历史版本的 compact snapshot 没有总分/场景告警，但完整 guard 仍保存了它们。
        # 快照字段优先；仅回填缺失值，避免新版本的精简字段被旧结构覆盖。
        stored_story_guard = metadata.get("story_progression_guard")
        if isinstance(stored_story_guard, dict):
            for key, value in stored_story_guard.items():
                if key not in metrics and key not in {"quality_metric_snapshot", "quality_issue_summary"}:
                    metrics[key] = value
        gate = dict(metadata.get("quality_gate") or {})
        if not gate:
            quality_gates = metadata.get("quality_gates")
            structural_gate = quality_gates.get("structural_gate") if isinstance(quality_gates, dict) else None
            if isinstance(structural_gate, dict):
                gate = dict(structural_gate)
        # 拒绝章通常没有 selected_version：质量门诊断只存在 runtime 摘要。
        # 仅在版本 metadata 缺失该 gate 时回退，且绝不把正文/原始错误文本输出到趋势 API。
        runtime_gate: Dict[str, Any] = {}
        raw_summary = getattr(chapter, "real_summary", None)
        if raw_summary:
            try:
                runtime = (json.loads(raw_summary) or {}).get("generation_runtime") or {}
                candidate_gate = runtime.get("quality_gate")
                if isinstance(candidate_gate, dict):
                    runtime_gate = candidate_gate
            except (TypeError, ValueError, json.JSONDecodeError):
                runtime_gate = {}
        if not gate:
            gate = dict(runtime_gate)
        if not metrics and isinstance(runtime_gate.get("story_progression_guard"), dict):
            metrics = dict(runtime_gate["story_progression_guard"])
        chapter_mission = metadata.get("chapter_mission") if isinstance(metadata.get("chapter_mission"), dict) else None
        metrics = _backfill_quality_observability_metrics(
            metrics,
            content=getattr(version, "content", None) if version is not None else None,
            chapter_mission=chapter_mission,
            chapter_number=int(chapter.chapter_number or 1),
        )
        blockers = gate.get("blockers") if isinstance(gate.get("blockers"), list) else []
        warnings = gate.get("warnings") if isinstance(gate.get("warnings"), list) else []
        blocker_codes = [str(item.get("code")) for item in blockers if isinstance(item, dict) and item.get("code")]
        warning_codes = [str(item.get("code")) for item in warnings if isinstance(item, dict) and item.get("code")]
        patch_suggestions = _redact_quality_trend_patch_suggestions(gate.get("patch_suggestions"))
        exemptions = gate.get("exemptions") if isinstance(gate.get("exemptions"), list) else []
        if not isinstance(gate.get("exemptions"), list):
            metric_exemptions = metrics.get("critique_exemption_applied")
            metric_gate_summary = metrics.get("quality_gate_summary")
            summary_exemptions = (
                metric_gate_summary.get("exemptions")
                if isinstance(metric_gate_summary, dict)
                else None
            )
            if isinstance(metric_exemptions, list):
                exemptions = metric_exemptions
            elif isinstance(summary_exemptions, list):
                exemptions = summary_exemptions
        critique_exemption_applied = (
            gate.get("critique_exemption_applied")
            if isinstance(gate.get("critique_exemption_applied"), list)
            else (
                metrics.get("critique_exemption_applied")
                if isinstance(metrics.get("critique_exemption_applied"), list)
                else list(exemptions)
            )
        )
        def _quality_number(key: str) -> Any:
            value = gate.get(key)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                value = metrics.get(key)
            return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None

        def _quality_source() -> Optional[str]:
            for value in (gate.get("selected_critique_source"), metrics.get("selected_critique_source")):
                if isinstance(value, str) and value.strip():
                    return value.strip()[:96]
            return None

        critique_score = _quality_number("self_critique_final_score")
        critique_critical_count = _quality_number("self_critique_critical_count")
        critique_major_count = _quality_number("self_critique_major_count")
        selected_critique_source = _quality_source()
        for code in blocker_codes:
            blocker_counts[code] = blocker_counts.get(code, 0) + 1
        for code in warning_codes:
            warning_counts[code] = warning_counts.get(code, 0) + 1
        for code in exemptions:
            key = str(code)
            exemption_counts[key] = exemption_counts.get(key, 0) + 1
        chapters.append({
            "chapter_number": chapter.chapter_number,
            "status": chapter.status,
            "score": metrics.get("score"),
            "quality_gate_passed": metrics.get("quality_gate_passed", gate.get("passed")),
            # 拒绝章可能没有 selected_version，或版本 metadata 只保留了
            # quality_metrics 的部分字段；使用上面已归一化的 gate/metrics
            # 回退值，避免 T-18 真实 exemption 样本丢失其诊断输入。
            "self_critique_final_score": critique_score,
            "self_critique_critical_count": critique_critical_count,
            "self_critique_major_count": critique_major_count,
            "selected_critique_source": selected_critique_source,
            "word_count": metrics.get("word_count", chapter.word_count),
            # T-10：保留重复段落的可解释诊断字段，而不仅是 blocker code。
            "repetition_risk": metrics.get("repetition_risk"),
            "repeated_paragraph_count": metrics.get("repeated_paragraph_count"),
            "max_repeated_paragraph_count": metrics.get("max_repeated_paragraph_count"),
            "repeated_paragraph_ratio": metrics.get("repeated_paragraph_ratio"),
            "longest_repeated_paragraph_chars": metrics.get("longest_repeated_paragraph_chars"),
            # T-11：前端需要知道质量门判定时使用了哪些焦点人物。
            "focus_character_names": list(metrics.get("focus_character_names") or []),
            "focus_character_hit_count": metrics.get("focus_character_hit_count"),
            "missing_focus_characters": list(metrics.get("missing_focus_characters") or []),
            # T-12：同时返回目标、下限、偏好线、上限及对应判罚状态。
            "target_word_count": metrics.get("target_word_count"),
            "min_word_count": metrics.get("min_word_count"),
            "preferred_word_floor": metrics.get("preferred_word_floor"),
            "upper_word_ceiling": metrics.get("upper_word_ceiling"),
            "word_count_below_min": metrics.get("word_count_below_min"),
            "word_count_far_above_target": metrics.get("word_count_far_above_target"),
            "word_count_far_below_target": metrics.get("word_count_far_below_target"),
            "word_requirement_met": metrics.get("word_requirement_met"),
            # T-14：区分短样本未评估与事件密度实际不通过。
            "event_density_evaluated": metrics.get("event_density_evaluated"),
            "event_density_skip_reason": metrics.get("event_density_skip_reason"),
            "event_density_passed": metrics.get("event_density_passed"),
            "long_chapter_density_passed": metrics.get("long_chapter_density_passed"),
            "state_change_interval_passed": metrics.get("state_change_interval_passed"),
            "ending_pressure_passed": metrics.get("ending_pressure_passed"),
            # T-15：保留章末压力的可解释命中与末段否决指标，不能只返回布尔结果。
            "ending_semantic_hit_count": metrics.get("ending_semantic_hit_count"),
            "ending_weak_hit_count": metrics.get("ending_weak_hit_count"),
            "flat_closure_markers": list(metrics.get("flat_closure_markers") or []),
            "ending_core_chars": metrics.get("ending_core_chars"),
            "ending_core_semantic_hit_count": metrics.get("ending_core_semantic_hit_count"),
            "ending_core_weak_hit_count": metrics.get("ending_core_weak_hit_count"),
            "ending_core_deflating": metrics.get("ending_core_deflating"),
            "dialogue_changes_state": metrics.get("dialogue_changes_state"),
            # T-08：静态描写风险必须带上触发分支的计数，便于跨章趋势解释。
            "static_description_risk": metrics.get("static_description_risk"),
            "static_paragraph_count": metrics.get("static_paragraph_count"),
            "max_static_run": metrics.get("max_static_run"),
            "reversal_signal_count": metrics.get("reversal_signal_count"),
            "reversal_in_late_section": metrics.get("reversal_in_late_section"),
            "dialogue_ratio": metrics.get("dialogue_ratio"),
            "action_ratio": metrics.get("action_ratio"),
            "description_ratio": metrics.get("description_ratio"),
            "speaker_count": metrics.get("speaker_count"),
            "dominant_speaker_ratio": metrics.get("dominant_speaker_ratio"),
            "hard_scene_cut_count": metrics.get("hard_scene_cut_count"),
            "summary_scene_cut_count": metrics.get("summary_scene_cut_count"),
            "scene_transition_warning": metrics.get("scene_transition_warning"),
            "continuity_inherit_missing": metrics.get("continuity_inherit_missing"),
            "continuity_inherit_late": metrics.get("continuity_inherit_late"),
            "continuity_inherit_hit_count": metrics.get("continuity_inherit_hit_count"),
            "inherit_hit_count": metrics.get("inherit_hit_count"),
            "continuity_inherit_total_hit_count": metrics.get("continuity_inherit_total_hit_count"),
            "continuity_inherit_match_mode": metrics.get("continuity_inherit_match_mode"),
            "mission_quality_codes": list(metrics.get("mission_quality_codes") or []),
            "blocker_codes": blocker_codes,
            "warning_codes": warning_codes,
            "patch_suggestions": patch_suggestions[:8],
            "exemptions": [str(code) for code in exemptions],
            "critique_exemption_applied": [str(code) for code in critique_exemption_applied],
            "self_critique_final_score": critique_score,
            "self_critique_critical_count": critique_critical_count,
            "self_critique_major_count": critique_major_count,
            "selected_critique_source": selected_critique_source,
        })
    return {
        "project_id": project_id,
        "chapter_count": len(chapters),
        "chapters": chapters,
        "blocker_counts": dict(sorted(blocker_counts.items())),
        "warning_counts": dict(sorted(warning_counts.items())),
        "exemption_counts": dict(sorted(exemption_counts.items())),
    }


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
    await get_project_owner_guard(project_id, session, current_user)



    export_service = ExportService(session)
    content = await export_service.export_novel_as_txt(project_id)

    from fastapi.responses import Response
    filename = f"novel_{project_id}_{datetime.now().strftime('%Y%m%d')}.txt"
    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/{project_id}/export/preflight")
async def preflight_export_novel(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> Dict[str, Any]:
    """导出前预检：告诉用户缺章、未定稿或空版本，而不是直接下载失败。"""


    await get_project_owner_guard(project_id, session, current_user)

    export_service = ExportService(session)
    return await export_service.preflight_export(project_id)


@router.get("/{project_id}/export/docx")
async def export_novel_as_docx(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
):
    """导出小说为 DOCX 格式"""


    await get_project_owner_guard(project_id, session, current_user)

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
        llm_result = await call_generation_text(
            llm_service=llm_service,
            system_prompt=system_prompt,
            conversation_history=conversation_history,
            temperature=0.8,
            user_id=user_id,
            timeout=240.0,
            policy=GenerationCallPolicy(
                stage_label="概念蓝图对话",
                progress_stage="blueprint_concept",
                retry_attempts=2,
                response_format="json_object",
                max_tokens=5000,
                retry_same_model_once=True,
            ),
        )
        llm_response = llm_result.text
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


def _merge_metrics_update(job, updates):
    new_metrics = updates.get("metrics")
    if not isinstance(new_metrics, dict) or not isinstance(job.get("metrics"), dict):
        job.update(updates)
        return
    existing = dict(job.get("metrics") or {})
    if isinstance(new_metrics.get("retry_events"), list):
        existing["retry_events"] = existing.get("retry_events", []) + new_metrics.get("retry_events", [])
    if isinstance(new_metrics.get("stage_attempts"), dict):
        existing["stage_attempts"] = {**existing.get("stage_attempts", {}), **new_metrics.get("stage_attempts", {})}
    existing.update({k: v for k, v in new_metrics.items() if k not in ("retry_events", "stage_attempts")})
    job["metrics"] = existing
    remaining = {k: v for k, v in updates.items() if k != "metrics"}
    job.update(remaining)

def _normalize_blueprint_job_payload(job: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(job)
    payload.setdefault("progress_stage", payload.get("status") or "idle")
    payload.setdefault("progress_message", "")
    payload.setdefault("started_at", None)
    payload.setdefault("updated_at", payload.get("started_at"))
    payload.setdefault("blueprint", None)
    payload.setdefault("ai_message", None)
    payload.setdefault("metrics", {"retry_count": 0, "llm_call_count": 0, "degraded": False, "retry_events": []})
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


async def _append_blueprint_task_runtime_event(job: Dict[str, Any]) -> None:
    run_id = str(job.get("run_id") or "")
    project_id = str(job.get("project_id") or "")
    user_id = job.get("user_id")
    if not run_id or not project_id or user_id is None:
        return
    status_raw = str(job.get("status") or "queued")
    terminal_map = {
        "successful": (TaskRuntimeStatus.SUCCEEDED.value, TaskRuntimeEventType.TASK_COMPLETED.value),
        "failed": (TaskRuntimeStatus.FAILED.value, TaskRuntimeEventType.TASK_FAILED.value),
        "cancelled": (TaskRuntimeStatus.CANCELLED.value, TaskRuntimeEventType.TASK_CANCELLED.value),
    }
    runtime_status, event_type = terminal_map.get(
        status_raw, (TaskRuntimeStatus.RUNNING.value if status_raw != "queued" else TaskRuntimeStatus.QUEUED.value, TaskRuntimeEventType.PROGRESS.value)
    )
    try:
        async with AsyncSessionLocal() as runtime_session:
            service = TaskRuntimeService(runtime_session)
            await service.get_task(run_id, int(user_id))
            await service.append_event(
                run_id,
                event_type=event_type,
                status=runtime_status,
                stage=str(job.get("progress_stage") or status_raw),
                progress=100.0 if runtime_status in {TaskRuntimeStatus.SUCCEEDED.value, TaskRuntimeStatus.FAILED.value, TaskRuntimeStatus.CANCELLED.value} else 0.0,
                message=str(job.get("progress_message") or ""),
                idempotency_key=f"blueprint-state:{job.get('updated_at') or _utc_now_iso()}",
                payload={
                    "task_domain": "blueprint",
                    "legacy_status": status_raw,
                    "force_stage": job.get("force_stage"),
                },
                owner_user_id=int(user_id),
            )
    except Exception:
        logger.warning("写入蓝图 TaskRuntime 事件失败：project=%s run_id=%s", project_id, run_id, exc_info=True)


async def _persist_blueprint_job_state(job: Dict[str, Any]) -> None:
    try:
        async with AsyncSessionLocal() as persist_session:
            await _upsert_blueprint_job_record(persist_session, job)
        await _append_blueprint_job_history(job)
        await _append_blueprint_task_runtime_event(job)
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

async def _load_active_blueprint_job_from_db(
    project_id: str,
    user_id: int,
) -> Dict[str, Any] | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(BlueprintGenerationJob)
            .where(
                BlueprintGenerationJob.project_id == project_id,
                BlueprintGenerationJob.user_id == user_id,
                BlueprintGenerationJob.status.in_(_BLUEPRINT_ACTIVE_STATUSES),
            )
            .order_by(BlueprintGenerationJob.updated_at.desc())
            .limit(1)
        )
        record = result.scalar_one_or_none()
        return _db_blueprint_job_to_payload(record) if record is not None else None


async def _set_blueprint_job_state(run_id: str, **updates: Any) -> None:
    snapshot: Dict[str, Any] | None = None
    async with _BLUEPRINT_JOB_LOCK:
        job = _BLUEPRINT_JOBS.get(run_id)
        if not job:
            return
        if job.get("status") == "cancelled" and updates.get("status") != "cancelled":
            return
        _merge_metrics_update(job, updates)
        job["updated_at"] = _utc_now_iso()
        snapshot = dict(job)

        await _persist_blueprint_job_state(snapshot)


async def _blueprint_runtime_task(run_id: str, user_id: int) -> Any | None:
    """Load the TaskRuntime record used as the blueprint worker's source of truth."""
    async with AsyncSessionLocal() as session:
        try:
            return await TaskRuntimeService(session).get_task(run_id, int(user_id))
        except TaskRuntimeNotFound:
            return None


async def _blueprint_is_cancelled(run_id: str, user_id: int) -> bool:
    task = await _blueprint_runtime_task(run_id, user_id)
    return task is not None and task.status in {
        TaskRuntimeStatus.CANCELLING.value,
        TaskRuntimeStatus.CANCELLED.value,
    }


async def _claim_blueprint_runtime(run_id: str, user_id: int) -> bool:
    """Claim the durable task before starting work; a second worker must not run it."""
    async with AsyncSessionLocal() as session:
        try:
            await TaskRuntimeService(session).claim(
                run_id,
                lease_owner=f"blueprint:{run_id}",
                stale_after_seconds=_BLUEPRINT_LEASE_STALE_SECONDS,
                owner_user_id=int(user_id),
            )
            return True
        except (TaskRuntimeNotFound, TaskRuntimeConflict):
            return False


async def _blueprint_heartbeat(run_id: str, user_id: int, stage: str, message: str) -> None:
    async with AsyncSessionLocal() as session:
        try:
            await TaskRuntimeService(session).heartbeat(
                run_id,
                lease_owner=f"blueprint:{run_id}",
                message=message,
                owner_user_id=int(user_id),
            )
            await TaskRuntimeService(session).update_progress(
                run_id,
                progress=0.0,
                stage=stage,
                message=message,
                owner_user_id=int(user_id),
            )
        except (TaskRuntimeNotFound, TaskRuntimeConflict):
            logger.info("蓝图任务心跳未写入：run_id=%s", run_id)


async def _finish_blueprint_runtime(
    run_id: str,
    user_id: int,
    *,
    status: str,
    event_type: str,
    stage: str,
    message: str,
    payload: Optional[dict[str, Any]] = None,
) -> None:
    async with AsyncSessionLocal() as session:
        try:
            await TaskRuntimeService(session).append_event(
                run_id,
                event_type=event_type,
                status=status,
                stage=stage,
                progress=100.0 if status in TERMINAL_STATUSES else None,
                message=message,
                payload=payload,
                owner_user_id=int(user_id),
                idempotency_key=f"blueprint-terminal:{run_id}:{status}",
            )
        except (TaskRuntimeNotFound, TaskRuntimeConflict):
            logger.warning("蓝图任务终态未写入：run_id=%s status=%s", run_id, status)


async def _schedule_blueprint_recovery(
    run_id: str,
    project_id: str,
    user_id: int,
    force_stage: str | None,
    background_tasks: BackgroundTasks,
) -> None:
    """Schedule a persisted queued/stale blueprint exactly once per process."""
    if run_id in _BLUEPRINT_SCHEDULED_RUNS:
        return
    _BLUEPRINT_SCHEDULED_RUNS.add(run_id)
    background_tasks.add_task(
        _run_blueprint_generation_job, run_id, project_id, user_id, force_stage
    )


async def _schedule_persisted_blueprint_recovery_if_needed(
    job: Dict[str, Any],
    *,
    project_id: str,
    user_id: int,
    background_tasks: BackgroundTasks,
) -> None:
    """复用旧任务时，确保 queued/stale 任务不会因进程重启永久停留。"""
    run_id = str(job.get("run_id") or "")
    if not run_id:
        return
    runtime_task = await _blueprint_runtime_task(run_id, user_id)
    if runtime_task is None:
        return
    if runtime_task.status in {
        TaskRuntimeStatus.QUEUED.value,
        TaskRuntimeStatus.STALE.value,
    }:
        await _schedule_blueprint_recovery(
            run_id,
            project_id,
            user_id,
            job.get("force_stage"),
            background_tasks,
        )


async def _run_blueprint_generation_job(
    run_id: str,
    project_id: str,
    user_id: int,
    force_stage: str | None = None,
) -> None:
    if not await _claim_blueprint_runtime(run_id, user_id):
        logger.info("蓝图任务未获得持久化租约，跳过执行：run_id=%s", run_id)
        return

    await _set_blueprint_job_state(
        run_id,
        status="generating",
        progress_stage="blueprint_concept",
        progress_message="正在生成小说蓝图",
    )

    async def progress_callback(stage: str, message: str) -> None:
        if await _blueprint_is_cancelled(run_id, user_id):
            raise asyncio.CancelledError()
        await _set_blueprint_job_state(
            run_id,
            status=stage,
            progress_stage=stage,
            progress_message=message,
        )
        await _blueprint_heartbeat(run_id, user_id, stage, message)

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
            if await _blueprint_is_cancelled(run_id, user_id):
                return
            await _set_blueprint_job_state(run_id, status=stage, progress_stage=stage, progress_message=message)
            await _blueprint_heartbeat(run_id, user_id, stage, message)

    heartbeat_task = asyncio.create_task(heartbeat())

    try:
        if await _blueprint_is_cancelled(run_id, user_id):
            await _finish_blueprint_runtime(
                run_id, user_id, status=TaskRuntimeStatus.CANCELLED.value,
                event_type=TaskRuntimeEventType.TASK_CANCELLED.value,
                stage="cancelled", message="蓝图生成任务已取消",
            )
            return
        async with AsyncSessionLocal() as job_session:
            with LLMService.daily_limit_scope(f"blueprint:{project_id}:{force_stage or 'full'}:{user_id}"):
                response = await _generate_blueprint_impl(
                    project_id=project_id,
                    session=job_session,
                    current_user=user_id,
                    progress_callback=progress_callback,
                    force_stage=force_stage,
                )
        if await _blueprint_is_cancelled(run_id, user_id):
            await _finish_blueprint_runtime(
                run_id, user_id, status=TaskRuntimeStatus.CANCELLED.value,
                event_type=TaskRuntimeEventType.TASK_CANCELLED.value,
                stage="cancelled", message="蓝图生成任务已取消",
            )
            return
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
        await _finish_blueprint_runtime(
            run_id, user_id, status=TaskRuntimeStatus.SUCCEEDED.value,
            event_type=TaskRuntimeEventType.TASK_COMPLETED.value,
            stage="successful", message="蓝图生成完成",
        )
    except asyncio.CancelledError:
        await _set_blueprint_job_state(
            run_id,
            status="cancelled",
            progress_stage="cancelled",
            progress_message="蓝图生成任务已取消",
        )
        await _finish_blueprint_runtime(
            run_id, user_id, status=TaskRuntimeStatus.CANCELLED.value,
            event_type=TaskRuntimeEventType.TASK_CANCELLED.value,
            stage="cancelled", message="蓝图生成任务已取消",
        )
        raise
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
        await _finish_blueprint_runtime(
            run_id, user_id, status=TaskRuntimeStatus.FAILED.value,
            event_type=TaskRuntimeEventType.TASK_FAILED.value,
            stage="failed", message="蓝图生成失败",
            payload={"error": str(exc)[:500]},
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
    await get_project_owner_guard(project_id, session, current_user)

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
            await _schedule_persisted_blueprint_recovery_if_needed(
                existing,
                project_id=project_id,
                user_id=user_id,
                background_tasks=background_tasks,
            )
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
            await _schedule_persisted_blueprint_recovery_if_needed(
                existing,
                project_id=project_id,
                user_id=user_id,
                background_tasks=background_tasks,
            )
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

    if hasattr(session, "execute"):
        await TaskRuntimeService(session).create_task(
            task_id=run_id,
            task_type="blueprint_generation",
            idempotency_key=f"blueprint-generation:{run_id}",
            owner_user_id=user_id,
            project_id=project_id,
            payload={"run_id": run_id, "force_stage": force_stage},
        )
    await _persist_blueprint_job_state(job)
    await _schedule_blueprint_recovery(
        run_id, project_id, user_id, force_stage, background_tasks
    )
    return _serialize_blueprint_job(job)


@router.get("/{project_id}/blueprint/generate/status", response_model=BlueprintGenerationJobResponse)
async def get_blueprint_generation_status(
    project_id: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> BlueprintGenerationJobResponse:
    """Return the latest blueprint generation job status for a project."""
    user_id = int(current_user.id)
    novel_service = NovelService(session)
    await get_project_owner_guard(project_id, session, current_user)

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
                    # 进程重启后先回填内存快照，恢复 worker 的进度回调仍能
                    # 持久化到同一条 BlueprintGenerationJob 记录。
                    _BLUEPRINT_JOBS[run_id] = dict(current)

        if snapshot:
            await _persist_blueprint_job_state(snapshot)
            current = snapshot

        # TaskRuntime 是运行状态唯一真相源；内存快照只保留编排句柄和兼容元数据。
        # 查询时重新读取同一 run 的持久化任务，避免旧 worker 的内存状态覆盖取消/失败/恢复状态。
        if run_id:
            runtime_task = await _blueprint_runtime_task(run_id, user_id)
            if runtime_task is not None:
                current["_runtime_status"] = runtime_task.status
                runtime_to_legacy = {
                    TaskRuntimeStatus.QUEUED.value: "queued",
                    TaskRuntimeStatus.RUNNING.value: current.get("status") if current.get("status") in _BLUEPRINT_ACTIVE_STATUSES else "generating",
                    TaskRuntimeStatus.CANCELLING.value: "cancelling",
                    TaskRuntimeStatus.CANCELLED.value: "cancelled",
                    TaskRuntimeStatus.SUCCEEDED.value: "successful",
                    TaskRuntimeStatus.FAILED.value: "failed",
                    TaskRuntimeStatus.STALE.value: "queued",
                }
                current["status"] = runtime_to_legacy.get(runtime_task.status, current.get("status", "queued"))
                if getattr(runtime_task, "stage", None):
                    current["progress_stage"] = runtime_task.stage
                if getattr(runtime_task, "message", None):
                    current["progress_message"] = runtime_task.message
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
                runtime_task = await _blueprint_runtime_task(run_id, user_id)
                if runtime_task is not None and runtime_task.status in {
                    TaskRuntimeStatus.QUEUED.value,
                    TaskRuntimeStatus.STALE.value,
                }:
                    await _schedule_blueprint_recovery(
                        run_id,
                        project_id,
                        user_id,
                        current.get("force_stage"),
                        background_tasks,
                    )
                elif runtime_task is not None and runtime_task.status in {
                    TaskRuntimeStatus.RUNNING.value,
                    TaskRuntimeStatus.CANCELLING.value,
                }:
                    # 另一个 worker 仍持有活租约：不重复启动，也不把任务
                    # 改写为“孤儿”，让其继续通过轮询/SSE 汇报状态。
                    pass
                else:
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
    await get_project_owner_guard(project_id, session, current_user)

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
    runtime_status = ""
    if run_id and hasattr(session, "execute"):
        runtime_task = await _blueprint_runtime_task(run_id, user_id)
        runtime_status = str(getattr(runtime_task, "status", "") or "")
    async with _BLUEPRINT_JOB_LOCK:
        job = _BLUEPRINT_JOBS.get(run_id or "")
        current = job if job else persisted
        if runtime_status in {
            TaskRuntimeStatus.RUNNING.value,
            TaskRuntimeStatus.CANCELLING.value,
        }:
            current.update({
                "status": "cancelling",
                "progress_stage": "cancelling",
                "progress_message": "已请求取消蓝图生成任务，等待后台安全收敛",
                "updated_at": _utc_now_iso(),
            })
        elif current.get("status") in _BLUEPRINT_ACTIVE_STATUSES:
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

    if run_id:
        async with AsyncSessionLocal() as runtime_session:
            try:
                await TaskRuntimeService(runtime_session).request_cancel(
                    run_id,
                    owner_user_id=user_id,
                    finalize_unclaimed=runtime_status == TaskRuntimeStatus.QUEUED.value,
                )
            except TaskRuntimeNotFound:
                pass

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
    initial_prompt_text = str(project.initial_prompt or "").strip()
    if not history_records and existing_blueprint is None and not initial_prompt_text:
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

    if not formatted_history and initial_prompt_text:
        formatted_history.append({"role": "user", "content": initial_prompt_text})
        structured_dialogue.append({
            "role": "user",
            "value": initial_prompt_text,
            "raw": {"source": "initial_prompt", "value": initial_prompt_text},
        })

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
        await progress_callback("blueprint_concept", "正在整理灵感访谈并生成蓝图结构")

    length_contract = _build_length_contract(
        formatted_history,
        structured_dialogue,
        project_title=project.title,
        existing_blueprint=existing_blueprint,
    )
    existing_novel_outline = list(existing_blueprint.novel_outline or []) if existing_blueprint else []
    existing_chapter_outline = list(existing_blueprint.chapter_outline or []) if existing_blueprint else []
    force_stage = (force_stage or "").strip().lower() or None
    if force_stage == "novel_outline":
        existing_novel_outline = []
        existing_chapter_outline = []
    elif force_stage == "chapter_outline":
        existing_chapter_outline = []
    elif existing_chapter_outline:
        existing_blueprint_data = existing_blueprint.model_dump(exclude_none=True) if existing_blueprint else {}
        expected_outline_count = _resolve_blueprint_chapter_outline_count(
            _attach_length_contract_to_blueprint(existing_blueprint_data, length_contract)
        )
        if not _has_complete_chapter_outline(existing_chapter_outline, expected_outline_count):
            existing_chapter_outline = []
    generated_stage = "chapter_outline"

    if existing_blueprint:
        blueprint_data = existing_blueprint.model_dump(exclude_none=True)
        blueprint_data = _attach_length_contract_to_blueprint(blueprint_data, length_contract)
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
                "must_build_length_aware_architecture": True,
                "length_contract": length_contract or {},
                "must_preserve_explicit_length_constraints": True,
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
        blueprint_data = await _call_llm_json_with_stage_retries(
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
            timeout=min(180.0, _resolve_novel_outline_timeout_seconds(blueprint_data={
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
            progress_stage="blueprint_concept",
            retry_attempts=1,
            soft_timeout_seconds=75.0,
        )

    if not isinstance(blueprint_data, dict):
        raise HTTPException(status_code=500, detail="蓝图生成失败，系统未得到可用的蓝图结构")

    blueprint_data = _attach_length_contract_to_blueprint(blueprint_data, length_contract)
    if "novel_outline" not in blueprint_data or blueprint_data["novel_outline"] is None:
        blueprint_data["novel_outline"] = existing_novel_outline
    if "chapter_outline" not in blueprint_data or blueprint_data["chapter_outline"] is None:
        blueprint_data["chapter_outline"] = existing_chapter_outline

    await checkpoint_callback(blueprint_data, "blueprint_concept", "已保存蓝图基础结构")

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
            await progress_callback("blueprint_cast_plan", "角色命名附加修复失败，已保留现有有效角色名")

    if progress_callback is not None:
        await progress_callback("blueprint_chapter_plan", "正在保存蓝图与项目状态")

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


@router.post(
    "/{project_id}/blueprint/generate",
    response_model=BlueprintGenerationJobResponse,
    deprecated=True,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_blueprint(
    project_id: str,
    response: Response,
    background_tasks: BackgroundTasks,
    payload: Dict[str, Any] | None = Body(default=None),
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> BlueprintGenerationJobResponse:
    response.headers["Deprecation"] = "true"
    response.headers["X-Xuanqiong-Legacy-Route"] = "blueprint-generate-sync"
    response.headers["Link"] = f"</api/novels/{project_id}/blueprint/generate/start>; rel=\"successor-version\""
    logger.warning(
        "Legacy synchronous blueprint route called; forwarding to background job route: project=%s user=%s",
        project_id,
        current_user.id,
    )
    return await start_blueprint_generation(
        project_id=project_id,
        background_tasks=background_tasks,
        payload=payload,
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
