# AIMETA P=小说服务_小说管理业务逻辑|R=小说CRUD_章节管理|NR=不含内容生成|E=NovelService|X=internal|A=服务类|D=sqlalchemy|S=db|RD=./README.ai
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from fastapi import HTTPException, status
from sqlalchemy import delete, func, inspect, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    BlueprintCharacter,
    BlueprintRelationship,
    Chapter,
    ChapterEvaluation,
    ChapterOutline,
    ChapterVersion,
    Faction,
    NovelBlueprint,
    NovelConversation,
    NovelProject,
)
from ..models.memory_layer import CharacterState, TimelineEvent
from ..services.vector_store_service import VectorStoreService
from ..repositories.novel_repository import NovelRepository
from ..schemas.admin import AdminNovelSummary
from ..schemas.novel import (
    Blueprint,
    Chapter as ChapterSchema,
    ChapterGenerationStatus,
    ChapterOutline as ChapterOutlineSchema,
    ChapterVersionSchema,
    NovelProject as NovelProjectSchema,
    NovelProjectSummary,
    NovelSectionResponse,
    NovelSectionType,
    WorkspaceSummary,
)

_PREFERRED_CONTENT_KEYS: tuple[str, ...] = (
    "content",
    "chapter_content",
    "chapter_text",
    "full_content",
    "text",
    "body",
    "story",
    "chapter",
    "real_summary",
    "summary",
)

_LEGACY_CHAPTER_STATUS_MAP: dict[str, str] = {
    "generation_failed": "failed",
    "generate_failed": "failed",
    "generation_successful": "successful",
    "generate_successful": "successful",
    "pending_confirmation": "waiting_for_confirm",
}

_LEGACY_RELATIONSHIP_META_MARKER = "\n[[ARBORIS_RELATIONSHIP_META]]\n"
_RELATIONSHIP_META_MARKER = "\n[[XUANQIONG_WENSHU_RELATIONSHIP_META]]\n"
_RELATIONSHIP_META_MARKERS: tuple[str, ...] = (
    _RELATIONSHIP_META_MARKER,
    _LEGACY_RELATIONSHIP_META_MARKER,
)
_BASE_CHARACTER_KEYS = {
    "name",
    "identity",
    "personality",
    "goals",
    "abilities",
    "relationship_to_protagonist",
    "extra",
}
_PROGRESS_STAGE_MAP: dict[str, str] = {
    "not_generated": "idle",
    "generating": "generating",
    "evaluating": "evaluating",
    "selecting": "selecting",
    "waiting_for_confirm": "waiting_for_confirm",
    "successful": "ready",
    "failed": "failed",
    "evaluation_failed": "evaluation_failed",
}
_PROGRESS_MESSAGE_MAP: dict[str, str] = {
    "idle": "章节尚未开始生成",
    "queued": "章节已进入队列，正在准备生成",
    "generating": "章节正在生成中",
    "evaluating": "候选版本正在评估",
    "selecting": "正在等待确认最终版本",
    "waiting_for_confirm": "等待确认最终版本",
    "ready": "章节已完成，可以继续下一章",
    "failed": "章节生成失败，请重试",
    "evaluation_failed": "版本评审异常，但已有候选版本仍可查看与确认",
}
_PROGRESS_ACTIONS_MAP: dict[str, List[str]] = {
    "idle": ["generate_chapter"],
    "queued": ["refresh_status"],
    "generating": ["refresh_status", "cancel_generation"],
    "evaluating": ["refresh_status", "cancel_generation"],
    "selecting": ["refresh_status", "review_versions", "cancel_generation"],
    "waiting_for_confirm": ["confirm_version", "review_versions", "refresh_status"],
    "ready": ["generate_next_chapter", "review_versions"],
    "failed": ["retry_generation", "refresh_status", "view_error"],
    "evaluation_failed": ["confirm_version", "review_versions", "retry_generation", "refresh_status", "view_error"],
}
_BUSY_CHAPTER_STATUSES = {
    "generating",
    "evaluating",
    "selecting",
}
_BUSY_CHAPTER_STALE_TIMEOUT = timedelta(minutes=15)
_RUNTIME_STALE_GRACE_SECONDS = 180
_MAX_RUNTIME_STALE_SECONDS = 24 * 60 * 60
_SUPPLEMENTAL_CHARACTER_NAMES: tuple[str, ...] = (
    "线索持有者",
    "旧日盟友",
    "对立代理人",
    "边缘证人",
    "信息中介",
    "失联亲属",
)
_SUPPLEMENTAL_CHARACTER_NAME_POOL: tuple[str, ...] = (
    "许岑",
    "陆青珩",
    "闻笙",
    "周砚",
    "顾小满",
    "程砚秋",
    "白砚宁",
    "秦照",
    "柳听澜",
    "贺微",
    "唐照夜",
    "苏问渠",
    "姜照雪",
    "林既白",
    "韩青芜",
    "谢停云",
    "方知返",
    "沈雁回",
    "宋临川",
    "叶无咎",
    "虞见微",
    "裴照影",
    "岑归舟",
    "温不器",
    "洛闻潮",
    "穆寒灯",
    "楚照山",
    "纪听雨",
    "宁折枝",
    "卫长缨",
    "萧渡",
    "钟离珩",
)
_SUPPLEMENTAL_CHARACTER_ARCHETYPES: tuple[dict[str, str], ...] = (
    {
        "identity": "关键线索持有者",
        "personality": "谨慎、多疑，习惯用半句真话试探来人。",
        "goals": "保住自己掌握的证据，同时判断主角是否值得托付。",
        "abilities": "掌握旧案碎片、地方传闻或被忽略的证物。",
        "relationship_to_protagonist": "先试探主角，后成为阶段性信息来源。",
    },
    {
        "identity": "旧日盟友",
        "personality": "念旧但不盲从，愿意帮忙却会要求代价。",
        "goals": "偿还旧债或守住旧约，同时避免被卷入更大清算。",
        "abilities": "熟悉旧路、人脉、账册或禁区规矩。",
        "relationship_to_protagonist": "与主角家族或核心盟友有旧，关系从观望转向协作。",
    },
    {
        "identity": "对立势力代理人",
        "personality": "克制、强势，做事讲秩序但不轻易交底。",
        "goals": "替所属势力确认主角价值、弱点或可利用之处。",
        "abilities": "拥有组织资源、追踪手段和谈判筹码。",
        "relationship_to_protagonist": "既压迫主角，也在关键时刻提供反向线索。",
    },
    {
        "identity": "边缘证人",
        "personality": "胆小、敏感，却记得别人忽略的细节。",
        "goals": "活下来，并把自己看见的异常换成保护。",
        "abilities": "目击关键场景、认得特殊声音/标记/路线。",
        "relationship_to_protagonist": "被主角保护或说服后，成为局部真相的拼图。",
    },
    {
        "identity": "信息中介",
        "personality": "圆滑、嘴紧，信奉消息必须等价交换。",
        "goals": "在多方势力之间维持生意和安全边界。",
        "abilities": "打听消息、转交物件、安排会面或伪装身份。",
        "relationship_to_protagonist": "与主角形成交易关系，逐步从买卖走向风险共担。",
    },
    {
        "identity": "失联亲属或旧案牵连者",
        "personality": "沉默、警惕，背负未公开的旧案压力。",
        "goals": "弄清亲人或旧案当事人的下落，同时躲避追索。",
        "abilities": "持有家族口述、旧物、血缘线索或隐秘路线。",
        "relationship_to_protagonist": "与主角形成情感牵引和旧案互证。",
    },
)
logger = logging.getLogger(__name__)


def _to_plain_data(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    if isinstance(value, dict):
        return {key: _to_plain_data(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain_data(item) for item in value]
    return value


def _normalize_version_content(raw_content: Any, metadata: Any) -> str:
    # 优先使用原始内容
    text = _coerce_text(raw_content)
    if text:
        return text
    
    # 如果没有原始内容，尝试从元数据提取（兼容旧逻辑）
    text = _coerce_text(metadata)
    return text or ""


def _coerce_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return _clean_string(value)
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        for key in _PREFERRED_CONTENT_KEYS:
            if key in value and value[key]:
                nested = _coerce_text(value[key])
                if nested:
                    return nested
        return _clean_string(json.dumps(value, ensure_ascii=False), parse_json=False)
    if isinstance(value, (list, tuple, set)):
        parts = [text for text in (_coerce_text(item) for item in value) if text]
        if parts:
            return "\n".join(parts)
        return None
    return _clean_string(str(value))


def _clean_string(text: str, parse_json: bool = True) -> str:
    stripped = text.strip()
    if not stripped:
        return stripped
    if parse_json and (
        (stripped.startswith("{") and stripped.endswith("}"))
        or (stripped.startswith("[") and stripped.endswith("]"))
    ):
        try:
            parsed = json.loads(stripped)
            coerced = _coerce_text(parsed)
            if coerced:
                return coerced
        except json.JSONDecodeError:
            pass
    if stripped.startswith('"') and stripped.endswith('"') and len(stripped) >= 2:
        stripped = stripped[1:-1]
    return (
        stripped.replace("\\n", "\n")
        .replace("\\t", "\t")
        .replace('\\"', '"')
        .replace("\\\\", "\\")
    )


def _normalize_datetime_to_utc(value: Optional[datetime]) -> Optional[datetime]:
    if not value:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalize_chapter_status(status: Any) -> str:
    if not status:
        return ChapterGenerationStatus.NOT_GENERATED.value
    normalized = str(status).strip().lower()
    if not normalized:
        return ChapterGenerationStatus.NOT_GENERATED.value
    mapped = _LEGACY_CHAPTER_STATUS_MAP.get(normalized)
    if mapped:
        return mapped
    known = {e.value for e in ChapterGenerationStatus}
    return normalized if normalized in known else ChapterGenerationStatus.NOT_GENERATED.value


def _blocks_sequential_generation(status: Any) -> bool:
    normalized = _normalize_chapter_status(status)
    return normalized in {
        ChapterGenerationStatus.NOT_GENERATED.value,
        ChapterGenerationStatus.GENERATING.value,
        ChapterGenerationStatus.EVALUATING.value,
        ChapterGenerationStatus.SELECTING.value,
        ChapterGenerationStatus.WAITING_FOR_CONFIRM.value,
    }


def _shorten_text(value: Any, limit: int = 180) -> str:
    text = _coerce_text(value) or ""
    cleaned = text.strip()
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit].rstrip()}..."


def _extract_marker_payload(text: str) -> tuple[str, Dict[str, Any]]:
    cleaned = _clean_string(text or "")
    if not cleaned:
        return cleaned, {}

    for marker in _RELATIONSHIP_META_MARKERS:
        if marker not in cleaned:
            continue
        description, _, payload = cleaned.partition(marker)
        description = description.rstrip()
        payload = payload.strip()
        if not payload:
            return description, {}
        try:
            meta = json.loads(payload)
            if isinstance(meta, dict):
                return description, meta
        except json.JSONDecodeError:
            return description, {}
    return cleaned, {}


def _encode_relationship_description(description: str, meta: Dict[str, Any]) -> str:
    clean_description = _clean_string(description or "")
    if not meta:
        return clean_description
    return f"{clean_description}{_RELATIONSHIP_META_MARKER}{json.dumps(meta, ensure_ascii=False, separators=(',', ':'))}"


def _safe_str(value: Any, default: str = "") -> str:
    text = _coerce_text(value)
    return text if text is not None else default


def _compact_list(values: Any) -> List[str]:
    if not values:
        return []
    if isinstance(values, str):
        parts = [part.strip() for part in values.replace("，", ",").split(",")]
        return [part for part in parts if part]
    if isinstance(values, (list, tuple, set)):
        result: List[str] = []
        for item in values:
            text = _safe_str(item).strip()
            if text:
                result.append(text)
        return result
    text = _safe_str(values).strip()
    return [text] if text else []


def _merge_character_extra(data: Dict[str, Any]) -> Dict[str, Any]:
    extra: Dict[str, Any] = {}
    nested_extra = data.get("extra")
    if isinstance(nested_extra, dict):
        extra.update(nested_extra)
    for key, value in data.items():
        if key not in _BASE_CHARACTER_KEYS and value is not None:
            extra[key] = value
    return extra


def _character_is_supplemental(data: Dict[str, Any]) -> bool:
    extra = data.get("extra")
    nested_flag = extra.get("is_supplemental") if isinstance(extra, dict) else None
    return bool(data.get("is_supplemental") or nested_flag)


def _is_legacy_supplemental_character(data: Dict[str, Any]) -> bool:
    name = _safe_str(data.get("name")).strip()
    identity = _safe_str(data.get("identity") or data.get("role")).strip()
    extra = data.get("extra")
    if isinstance(extra, dict):
        identity = identity or _safe_str(extra.get("role") or extra.get("identity")).strip()
    if identity.startswith("补强角色位"):
        return True
    return any(name.startswith(prefix) and any(ch.isdigit() for ch in name) for prefix in _SUPPLEMENTAL_CHARACTER_NAMES)


def _relationship_mentions_current_cast(relation: Dict[str, Any], character_names: set[str]) -> bool:
    from_name = _safe_str(relation.get("character_from")).strip()
    to_name = _safe_str(relation.get("character_to")).strip()
    if not from_name and not to_name:
        return True
    if not from_name or not to_name:
        return False
    return from_name in character_names and to_name in character_names


def _character_importance_label(index: int, total_target: int) -> str:
    if index == 0:
        return "protagonist"
    if index < min(4, max(2, total_target)):
        return "core"
    if index < min(10, max(6, total_target)):
        return "secondary"
    if index < min(18, max(10, total_target)):
        return "stage_support"
    if index < min(30, max(18, total_target)):
        return "faction_member"
    return "support"


def _estimate_highlight_chapter(index: int, total_chapters: int) -> int:
    if total_chapters <= 0:
        return max(1, index + 1)
    numerator = (index + 1) * total_chapters
    denominator = max(2, total_chapters + 1)
    return max(1, min(total_chapters, round(numerator / denominator)))


def _target_character_count(total_chapters: int) -> int:
    if total_chapters >= 200:
        return 42
    if total_chapters >= 120:
        return 32
    if total_chapters >= 80:
        return 26
    if total_chapters >= 50:
        return 20
    if total_chapters >= 36:
        return 16
    if total_chapters >= 24:
        return 12
    if total_chapters >= 12:
        return 8
    return 5


def _target_relationship_count(character_count: int, total_chapters: int) -> int:
    if total_chapters >= 200:
        base_target = 90
    elif total_chapters >= 120:
        base_target = 70
    elif total_chapters >= 80:
        base_target = 56
    elif total_chapters >= 50:
        base_target = 44
    elif total_chapters >= 36:
        base_target = 32
    elif total_chapters >= 24:
        base_target = 24
    elif total_chapters >= 12:
        base_target = 16
    else:
        base_target = 8
    return max(character_count * 2, base_target)


def _item_get(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _parse_chapter_range_end(value: Any) -> Optional[int]:
    text = _safe_str(value).strip()
    if not text:
        return None
    numbers = [int(match) for match in re.findall(r"\d+", text)]
    if not numbers:
        return None
    return max(numbers)


def _extract_length_contract_target(value: Any) -> Optional[int]:
    payload = _to_plain_data(value)
    if not isinstance(payload, dict):
        return None
    candidates = []
    length_contract = payload.get("length_contract")
    if isinstance(length_contract, dict):
        candidates.append(length_contract)
    system_blueprint = payload.get("system_blueprint")
    if isinstance(system_blueprint, dict) and isinstance(system_blueprint.get("length_contract"), dict):
        candidates.append(system_blueprint["length_contract"])
    for candidate in candidates:
        try:
            target = int(candidate.get("target_chapter_count") or 0)
        except (TypeError, ValueError):
            continue
        if 1 <= target <= 1000:
            return target
    return None


def _infer_total_chapters_for_cast(
    *,
    chapter_outline: Any = None,
    novel_outline: Any = None,
    volume_plan: Any = None,
    world_setting: Any = None,
    fallback: int = 0,
) -> int:
    length_contract_target = _extract_length_contract_target(world_setting)
    if length_contract_target:
        return length_contract_target

    total = max(0, int(fallback or 0))
    chapter_items = _to_plain_data(chapter_outline or [])
    if isinstance(chapter_items, list):
        total = max(total, len(chapter_items))
        for item in chapter_items:
            chapter_number = _item_get(item, "chapter_number")
            try:
                total = max(total, int(chapter_number))
            except (TypeError, ValueError):
                continue

    outline_items = _to_plain_data(novel_outline or [])
    if isinstance(outline_items, list):
        for item in outline_items:
            for key in ("expected_chapter_range", "chapter_range", "chapters", "range"):
                end = _parse_chapter_range_end(_item_get(item, key))
                if end:
                    total = max(total, end)

    volume_items = _to_plain_data(volume_plan or [])
    if isinstance(volume_items, list):
        for item in volume_items:
            for key in ("expected_chapter_range", "chapter_range", "chapters", "range"):
                end = _parse_chapter_range_end(_item_get(item, key))
                if end:
                    total = max(total, end)
    return total


def _build_supplemental_character_seed(
    *,
    index: int,
    total_chapters: int,
    blueprint_title: str,
    genre: str,
) -> Dict[str, Any]:
    archetype = _SUPPLEMENTAL_CHARACTER_ARCHETYPES[index % len(_SUPPLEMENTAL_CHARACTER_ARCHETYPES)]
    name = _SUPPLEMENTAL_CHARACTER_NAME_POOL[index % len(_SUPPLEMENTAL_CHARACTER_NAME_POOL)]
    if index >= len(_SUPPLEMENTAL_CHARACTER_NAME_POOL):
        name = f"{name}{index + 1}"
    first_chapter = _estimate_highlight_chapter(index, max(1, total_chapters))
    identity = archetype["identity"]
    return {
        "name": name,
        "identity": identity,
        "personality": archetype["personality"],
        "goals": archetype["goals"],
        "abilities": archetype["abilities"],
        "relationship_to_protagonist": archetype["relationship_to_protagonist"],
        "core_motivation": archetype["goals"],
        "fear_or_wound": "害怕自己掌握的信息害死身边人，因此不会一次说尽。",
        "external_goal": f"在第 {first_chapter} 章附近把{identity}的作用落到具体事件中。",
        "hidden_secret": f"与{blueprint_title or genre or '主线旧案'}存在尚未公开的牵连。",
        "relationship_hook": archetype["relationship_to_protagonist"],
        "extra": {
            "is_supplemental": True,
            "supplemental_reason": "角色数量不足时自动补强，但必须带具体姓名、职责、登场窗口和后续去向。",
            "first_appearance_chapter": first_chapter,
            "first_highlight_chapter": first_chapter,
            "exit_or_return_plan": "完成阶段职责后留下清晰去向，并在对应伏笔、证据或势力线需要时回归。",
            "knowledge_boundary": "只知道自身经历、所属势力和登场前合理可知的信息，不得提前知道核心谜底。",
            "dynamic_role_policy": "可作为阶段配角、势力成员或功能性路人登场；登场后必须进入角色池/关系/知识边界账本。",
        },
    }


def _default_relationship_hooks(name: str, identity: str, goals: str, genre: str) -> List[str]:
    hooks = [
        f"{name}与主线的情绪牵引",
        f"围绕{identity or '角色身份'}与{goals or '核心目标'}的碰撞",
    ]
    if genre:
        hooks.append(f"在{genre}语境下与主角形成持续张力")
    return hooks


def _normalize_character_record(
    data: Dict[str, Any],
    *,
    index: int,
    total_chapters: int,
    blueprint_title: str,
    genre: str,
    supplemental: bool = False,
) -> Dict[str, Any]:
    name = _safe_str(data.get("name")).strip()
    if not name:
        if supplemental:
            name = _build_supplemental_character_seed(
                index=index,
                total_chapters=total_chapters,
                blueprint_title=blueprint_title,
                genre=genre,
            )["name"]
        else:
            name = f"角色{index + 1}"
    identity = _safe_str(data.get("identity")).strip()
    personality = _safe_str(data.get("personality")).strip()
    goals = _safe_str(data.get("goals")).strip()
    abilities = _safe_str(data.get("abilities")).strip()
    relationship_to_protagonist = _safe_str(data.get("relationship_to_protagonist")).strip()
    extra = _merge_character_extra(data)

    total_target = max(_target_character_count(total_chapters), 1)
    importance_label = _character_importance_label(index, total_target)
    extra.setdefault("importance", importance_label)
    extra.setdefault("role_rank", "protagonist" if index == 0 else ("core" if index < 4 else importance_label))
    extra.setdefault("cast_tier", importance_label)
    extra.setdefault("first_highlight_chapter", _estimate_highlight_chapter(index, max(1, total_chapters)))
    extra.setdefault("first_appearance_chapter", extra.get("first_highlight_chapter"))
    extra.setdefault(
        "exit_or_return_plan",
        "主角/核心角色持续推进；阶段配角在完成阶段职责后要么退出、牺牲、转阵营，要么在后续伏笔回收时回归。"
        if index < 10
        else "服务当前阶段或势力线，离场前必须留下可追踪去向或影响。",
    )
    extra.setdefault(
        "faction_role",
        _safe_str(extra.get("faction_role") or extra.get("affiliation") or "").strip(),
    )
    extra.setdefault(
        "knowledge_boundary",
        _safe_str(extra.get("knowledge_boundary") or "只知道其身份、经历和登场章节合理可知的信息，不得提前知道核心秘密。").strip(),
    )
    extra.setdefault(
        "dynamic_role_policy",
        "可随剧情新增同层级角色，但必须绑定目标、所属势力/关系、首次登场章节和后续去向。",
    )
    extra.setdefault(
        "relationship_hooks",
        _default_relationship_hooks(name, identity, goals, genre or blueprint_title),
    )
    extra.setdefault(
        "growth_arc",
        _safe_str(
            extra.get("growth_arc")
            or extra.get("arc")
            or (f"{identity or name}在{blueprint_title or genre or '故事'}中逐步完成自我更新")
        ).strip(),
    )
    extra.setdefault("is_supplemental", supplemental)
    extra.setdefault("hidden_info", _safe_str(extra.get("hidden_info")).strip())

    payload = {
        "name": name,
        "identity": identity,
        "personality": personality,
        "goals": goals,
        "abilities": abilities,
        "relationship_to_protagonist": relationship_to_protagonist,
        **extra,
        "extra": extra,
    }
    return payload


def _infer_relationship_type(description: str, from_name: str, to_name: str) -> str:
    text = f"{description} {from_name} {to_name}"
    if any(token in text for token in ("父", "母", "兄", "姐", "妹", "亲属", "家人", "家族")):
        return "family"
    if any(token in text for token in ("恋", "爱", "情", "暧昧", "伴侣")):
        return "romance"
    if any(token in text for token in ("盟", "合作", "伙伴", "协作", "联手")):
        return "alliance"
    if any(token in text for token in ("敌", "仇", "对立", "冲突", "竞争", "较量")):
        return "conflict"
    if any(token in text for token in ("师", "指导", "教导", "带领")):
        return "mentor"
    return "tension"


def _infer_relationship_status(relationship_type: str, description: str) -> str:
    text = f"{relationship_type} {description}"
    if relationship_type in {"family", "romance", "alliance"}:
        return "stable"
    if any(token in text for token in ("破裂", "决裂", "背叛", "敌", "仇")):
        return "hostile"
    if any(token in text for token in ("脆弱", "摇摆", "暂时", "临时")):
        return "fragile"
    return "developing"


def _infer_relationship_direction(relationship_type: str, description: str) -> str:
    if relationship_type == "family":
        return "从依赖走向理解"
    if relationship_type == "romance":
        return "从试探走向确认"
    if relationship_type == "alliance":
        return "从合作走向互信"
    if relationship_type == "mentor":
        return "从指导走向分歧"
    if any(token in description for token in ("背叛", "决裂", "敌", "仇")):
        return "从合作走向对立"
    return "从陌生走向碰撞"


def _infer_relationship_trigger(
    from_name: str,
    to_name: str,
    chapter_count: int,
    description: str,
) -> str:
    if chapter_count > 0:
        pivot = max(2, min(chapter_count, round(chapter_count * 0.4)))
        return f"在第{pivot}章前后因{from_name}与{to_name}的关键事件而激化"
    return f"围绕{from_name}与{to_name}的核心冲突逐步展开"


def _infer_relationship_importance(relationship_type: str, from_name: str, protagonist_name: str) -> int:
    if from_name == protagonist_name:
        return 5
    if relationship_type in {"family", "romance", "conflict"}:
        return 4
    if relationship_type == "alliance":
        return 3
    return 2


def _normalize_relationship_record(
    relation: Dict[str, Any],
    *,
    index: int,
    chapter_count: int,
    protagonist_name: str,
) -> Dict[str, Any]:
    description, meta = _extract_marker_payload(_safe_str(relation.get("description")))
    extra = {}
    relation_extra = relation.get("extra")
    if isinstance(relation_extra, dict):
        extra.update(relation_extra)
    extra.update({k: v for k, v in meta.items() if v is not None})
    for key in ("relationship_type", "status", "tension", "direction", "trigger_event", "importance"):
        value = relation.get(key)
        if value is not None:
            extra[key] = value

    from_name = _safe_str(relation.get("character_from")).strip() or protagonist_name
    to_name = _safe_str(relation.get("character_to")).strip() or protagonist_name
    if not description:
        relation_type = _safe_str(extra.get("relationship_type")).strip() or _infer_relationship_type(
            "",
            from_name,
            to_name,
        )
        description = f"{from_name}与{to_name}维持着{relation_type}型牵引，围绕共同目标与隐性冲突持续推进。"
    relation_type = _safe_str(extra.get("relationship_type")).strip() or _infer_relationship_type(
        description,
        from_name,
        to_name,
    )
    status = _safe_str(extra.get("status")).strip() or _infer_relationship_status(relation_type, description)
    tension = _safe_str(extra.get("tension")).strip() or ("high" if relation_type in {"conflict", "romance"} else "medium")
    direction = _safe_str(extra.get("direction")).strip() or _infer_relationship_direction(relation_type, description)
    trigger_event = _safe_str(extra.get("trigger_event")).strip() or _infer_relationship_trigger(
        from_name,
        to_name,
        chapter_count,
        description,
    )
    importance_value = extra.get("importance")
    try:
        importance = int(importance_value) if importance_value is not None else _infer_relationship_importance(
            relation_type,
            from_name,
            protagonist_name,
        )
    except (TypeError, ValueError):
        importance = _infer_relationship_importance(relation_type, from_name, protagonist_name)

    extra.update(
        {
            "relationship_type": relation_type,
            "status": status,
            "tension": tension,
            "direction": direction,
            "trigger_event": trigger_event,
            "importance": importance,
            "is_supplemental": bool(extra.get("is_supplemental", False)),
        }
    )
    stored_description = _encode_relationship_description(description, extra)
    return {
        "character_from": from_name,
        "character_to": to_name,
        "description": description,
        "stored_description": stored_description,
        "relationship_type": relation_type,
        "status": status,
        "tension": tension,
        "direction": direction,
        "trigger_event": trigger_event,
        "importance": importance,
        "extra": extra,
        "position": index,
    }


def _augment_character_profile(
    record: Dict[str, Any],
    *,
    index: int,
    total_chapters: int,
    blueprint_title: str,
    genre: str,
    supplemental: bool = False,
) -> Dict[str, Any]:
    normalized = dict(record)
    extra = dict(normalized.get("extra") or {})

    role = _safe_str(normalized.get("role") or extra.get("role") or normalized.get("identity") or extra.get("role_rank")).strip()
    core_motivation = _safe_str(
        normalized.get("core_motivation")
        or extra.get("core_motivation")
        or normalized.get("goals")
        or normalized.get("personality")
        or normalized.get("identity")
    ).strip()
    fear_or_wound = _safe_str(
        normalized.get("fear_or_wound")
        or extra.get("fear_or_wound")
        or extra.get("wound")
        or normalized.get("personality")
    ).strip()
    external_goal = _safe_str(
        normalized.get("external_goal")
        or extra.get("external_goal")
        or normalized.get("goals")
    ).strip()
    hidden_secret = _safe_str(
        normalized.get("hidden_secret")
        or extra.get("hidden_secret")
        or extra.get("secret")
    ).strip()
    relationship_hook = _safe_str(
        normalized.get("relationship_hook")
        or extra.get("relationship_hook")
        or normalized.get("relationship_to_protagonist")
    ).strip()

    hooks = _compact_list(extra.get("relationship_hooks")) or _default_relationship_hooks(
        normalized.get("name", ""),
        normalized.get("identity", ""),
        normalized.get("goals", ""),
        genre or blueprint_title,
    )

    total_target = max(_target_character_count(total_chapters), 1)
    role_rank = extra.get("role_rank") or ("protagonist" if index == 0 else ("core" if index < 4 else "support"))
    importance_label = _character_importance_label(index, total_target)

    extra.setdefault("importance", importance_label)
    extra.setdefault("role_rank", role_rank)
    extra.setdefault("cast_tier", extra.get("importance") or importance_label)
    extra.setdefault("first_highlight_chapter", _estimate_highlight_chapter(index, max(1, total_chapters)))
    extra.setdefault("first_appearance_chapter", extra.get("first_highlight_chapter"))
    extra.setdefault("relationship_hooks", hooks)
    extra.setdefault("role", role or role_rank)
    extra.setdefault("core_motivation", core_motivation or f"{normalized.get('name', '角色')}围绕主线目标展开行动")
    extra.setdefault("fear_or_wound", fear_or_wound or f"{normalized.get('name', '角色')}存在尚未愈合的心理缺口")
    extra.setdefault("external_goal", external_goal or f"{normalized.get('name', '角色')}推动当前章节的外在目标")
    extra.setdefault("hidden_secret", hidden_secret or "")
    extra.setdefault("relationship_hook", relationship_hook or hooks[0])
    extra.setdefault(
        "growth_arc",
        _safe_str(
            extra.get("growth_arc")
            or extra.get("arc")
            or (f"{normalized.get('identity') or normalized.get('name') or '角色'}在{blueprint_title or genre or '故事'}中逐步完成自我更新")
        ).strip(),
    )
    extra.setdefault("is_supplemental", supplemental)
    extra.setdefault("hidden_info", _safe_str(extra.get("hidden_info")).strip())
    extra.setdefault(
        "exit_or_return_plan",
        _safe_str(extra.get("exit_or_return_plan")).strip()
        or (
            "完成阶段职责后要留下清晰去向，并在对应伏笔/势力线需要时回归。"
            if index >= 4
            else "随主线长期推进，关键状态变化必须进入记忆层。"
        ),
    )
    extra.setdefault(
        "faction_role",
        _safe_str(extra.get("faction_role") or extra.get("affiliation") or "").strip(),
    )
    extra.setdefault(
        "knowledge_boundary",
        _safe_str(extra.get("knowledge_boundary") or "只能掌握其经历与登场位置合理可知的信息，不能提前知道未揭示秘密。").strip(),
    )
    extra.setdefault(
        "dynamic_role_policy",
        _safe_str(extra.get("dynamic_role_policy") or "新增角色必须绑定角色池、势力/关系、首次登场章节和后续去向。").strip(),
    )

    normalized.update(
        {
            "role": extra["role"],
            "core_motivation": extra["core_motivation"],
            "fear_or_wound": extra["fear_or_wound"],
            "external_goal": extra["external_goal"],
            "hidden_secret": extra["hidden_secret"],
            "growth_arc": extra["growth_arc"],
            "first_highlight_chapter": extra["first_highlight_chapter"],
            "first_appearance_chapter": extra["first_appearance_chapter"],
            "relationship_hook": extra["relationship_hook"],
            "importance": extra["importance"],
            "cast_tier": extra["cast_tier"],
            "exit_or_return_plan": extra["exit_or_return_plan"],
            "faction_role": extra["faction_role"],
            "knowledge_boundary": extra["knowledge_boundary"],
            "extra": extra,
        }
    )
    return normalized


def _augment_relationship_profile(
    record: Dict[str, Any],
    relation_data: Dict[str, Any],
    *,
    index: int,
    chapter_count: int,
    protagonist_name: str,
) -> Dict[str, Any]:
    normalized = dict(record)
    extra = dict(normalized.get("extra") or {})
    relation_extra = relation_data.get("extra")
    if isinstance(relation_extra, dict):
        extra.update(relation_extra)

    for key in ("core_conflict", "relationship_type", "status", "tension", "direction", "trigger_event", "importance"):
        value = relation_data.get(key)
        if value is not None:
            extra[key] = value

    core_conflict = _safe_str(
        relation_data.get("core_conflict")
        or normalized.get("core_conflict")
        or extra.get("core_conflict")
        or normalized.get("description")
    ).strip()
    if not core_conflict:
        core_conflict = _shorten_text(normalized.get("description"), 120)

    relation_type = _safe_str(extra.get("relationship_type")).strip() or _infer_relationship_type(
        normalized.get("description", ""),
        normalized.get("character_from", protagonist_name),
        normalized.get("character_to", protagonist_name),
    )
    status = _safe_str(extra.get("status")).strip() or _infer_relationship_status(
        relation_type,
        normalized.get("description", ""),
    )
    tension = _safe_str(extra.get("tension")).strip() or ("high" if relation_type in {"conflict", "romance"} else "medium")
    direction = _safe_str(extra.get("direction")).strip() or _infer_relationship_direction(
        relation_type,
        normalized.get("description", ""),
    )
    trigger_event = _safe_str(extra.get("trigger_event")).strip() or _infer_relationship_trigger(
        normalized.get("character_from", protagonist_name),
        normalized.get("character_to", protagonist_name),
        chapter_count,
        normalized.get("description", ""),
    )
    importance_value = extra.get("importance")
    try:
        importance = int(importance_value) if importance_value is not None else _infer_relationship_importance(
            relation_type,
            normalized.get("character_from", protagonist_name),
            protagonist_name,
        )
    except (TypeError, ValueError):
        importance = _infer_relationship_importance(
            relation_type,
            normalized.get("character_from", protagonist_name),
            protagonist_name,
        )

    extra.update(
        {
            "core_conflict": core_conflict,
            "relationship_type": relation_type,
            "status": status,
            "tension": tension,
            "direction": direction,
            "trigger_event": trigger_event,
            "importance": importance,
            "is_supplemental": bool(extra.get("is_supplemental", False)),
        }
    )
    normalized.update(
        {
            "core_conflict": core_conflict,
            "relationship_type": relation_type,
            "status": status,
            "tension": tension,
            "direction": direction,
            "trigger_event": trigger_event,
            "importance": importance,
            "stored_description": _encode_relationship_description(normalized.get("description", ""), extra),
            "extra": extra,
        }
    )
    return normalized


def _normalize_blueprint_characters_for_storage(
    characters: List[Any],
    *,
    total_chapters: int,
    blueprint_title: str,
    genre: str,
    expand: bool = True,
) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    seen_names: Dict[str, int] = {}

    for index, raw_character in enumerate(characters):
        if hasattr(raw_character, "model_dump"):
            character_data = raw_character.model_dump()
        elif isinstance(raw_character, dict):
            character_data = dict(raw_character)
        else:
            character_data = {
                key: value
                for key, value in getattr(raw_character, "__dict__", {}).items()
                if not key.startswith("_")
            }

        supplemental = _character_is_supplemental(character_data)
        if supplemental and _is_legacy_supplemental_character(character_data):
            character_data = _build_supplemental_character_seed(
                index=index,
                total_chapters=total_chapters,
                blueprint_title=blueprint_title,
                genre=genre,
            )
            supplemental = True

        base_record = _normalize_character_record(
            character_data,
            index=index,
            total_chapters=total_chapters,
            blueprint_title=blueprint_title,
            genre=genre,
            supplemental=supplemental,
        )
        record = _augment_character_profile(
            base_record,
            index=index,
            total_chapters=total_chapters,
            blueprint_title=blueprint_title,
            genre=genre,
            supplemental=supplemental,
        )

        key = record["name"].strip().lower()
        if key in seen_names:
            existing = normalized[seen_names[key]]
            existing_extra = dict(existing.get("extra") or {})
            incoming_extra = dict(record.get("extra") or {})
            for extra_key, value in incoming_extra.items():
                if extra_key == "role_rank":
                    rank_order = {"protagonist": 3, "core": 2, "secondary": 1, "support": 0}
                    current_rank = _safe_str(existing_extra.get(extra_key)).strip()
                    incoming_rank = _safe_str(value).strip()
                    if rank_order.get(incoming_rank, -1) > rank_order.get(current_rank, -1):
                        existing_extra[extra_key] = incoming_rank
                    elif not current_rank and incoming_rank:
                        existing_extra[extra_key] = incoming_rank
                elif extra_key == "importance":
                    rank_order = {"protagonist": 3, "core": 2, "secondary": 1, "support": 0}
                    current_rank = _safe_str(existing_extra.get(extra_key)).strip()
                    incoming_rank = _safe_str(value).strip()
                    if rank_order.get(incoming_rank, -1) > rank_order.get(current_rank, -1):
                        existing_extra[extra_key] = incoming_rank
                    elif not current_rank and incoming_rank:
                        existing_extra[extra_key] = incoming_rank
                elif extra_key == "relationship_hooks":
                    current_hooks = _compact_list(existing_extra.get(extra_key))
                    incoming_hooks = _compact_list(value)
                    merged_hooks = current_hooks[:]
                    for hook in incoming_hooks:
                        if hook not in merged_hooks:
                            merged_hooks.append(hook)
                    if merged_hooks:
                        existing_extra[extra_key] = merged_hooks
                elif extra_key == "is_supplemental":
                    existing_extra[extra_key] = bool(existing_extra.get(extra_key, False) or value)
                elif extra_key not in existing_extra or existing_extra.get(extra_key) in (None, ""):
                    existing_extra[extra_key] = value
            existing.update(
                {
                    "role": existing.get("role") or record.get("role"),
                    "core_motivation": existing.get("core_motivation") or record.get("core_motivation"),
                    "fear_or_wound": existing.get("fear_or_wound") or record.get("fear_or_wound"),
                    "external_goal": existing.get("external_goal") or record.get("external_goal"),
                    "hidden_secret": existing.get("hidden_secret") or record.get("hidden_secret"),
                    "growth_arc": existing.get("growth_arc") or record.get("growth_arc"),
                    "first_highlight_chapter": existing.get("first_highlight_chapter") or record.get("first_highlight_chapter"),
                    "relationship_hook": existing.get("relationship_hook") or record.get("relationship_hook"),
                    "importance": existing.get("importance") or record.get("importance"),
                    "extra": existing_extra,
                }
            )
            continue

        seen_names[key] = len(normalized)
        normalized.append(record)

    if not expand:
        return normalized

    target_count = _target_character_count(total_chapters)
    if len(normalized) > target_count:
        anchored = [
            item for item in normalized
            if not bool((item.get("extra") or {}).get("is_supplemental"))
        ]
        supplemental = [
            item for item in normalized
            if bool((item.get("extra") or {}).get("is_supplemental"))
        ]
        if len(anchored) < len(normalized):
            normalized = anchored + supplemental[:max(0, target_count - len(anchored))]

    while len(normalized) < target_count:
        index = len(normalized)
        supplemental_seed = _build_supplemental_character_seed(
            index=index,
            total_chapters=total_chapters,
            blueprint_title=blueprint_title,
            genre=genre,
        )
        supplemental_record = _augment_character_profile(
            supplemental_seed,
            index=index,
            total_chapters=total_chapters,
            blueprint_title=blueprint_title,
            genre=genre,
            supplemental=True,
        )
        normalized.append(supplemental_record)

    return normalized


def _normalize_blueprint_relationships_for_storage(
    relationships: List[Any],
    *,
    characters: List[Dict[str, Any]],
    total_chapters: int,
    blueprint_title: str,
    expand: bool = True,
) -> List[Dict[str, Any]]:
    protagonist_name = characters[0]["name"] if characters else blueprint_title or "主角"
    character_names = {
        str(character.get("name") or "").strip()
        for character in characters
        if str(character.get("name") or "").strip()
    }
    normalized: List[Dict[str, Any]] = []
    seen_pairs: Dict[tuple[str, str], int] = {}

    for index, raw_relationship in enumerate(relationships):
        if hasattr(raw_relationship, "model_dump"):
            relation_data = raw_relationship.model_dump()
        elif isinstance(raw_relationship, dict):
            relation_data = dict(raw_relationship)
        else:
            relation_data = {
                key: value
                for key, value in getattr(raw_relationship, "__dict__", {}).items()
                if not key.startswith("_")
            }

        if character_names and not _relationship_mentions_current_cast(relation_data, character_names):
            continue

        base_record = _normalize_relationship_record(
            relation_data,
            index=index,
            chapter_count=total_chapters,
            protagonist_name=protagonist_name,
        )
        record = _augment_relationship_profile(
            base_record,
            relation_data,
            index=index,
            chapter_count=total_chapters,
            protagonist_name=protagonist_name,
        )
        pair = tuple(sorted((record["character_from"], record["character_to"])))
        if pair in seen_pairs:
            existing = normalized[seen_pairs[pair]]
            if not existing.get("description") and record.get("description"):
                existing["description"] = record["description"]
                existing["stored_description"] = record["stored_description"]
            if not existing.get("core_conflict") and record.get("core_conflict"):
                existing["core_conflict"] = record["core_conflict"]
            existing_extra = dict(existing.get("extra") or {})
            incoming_extra = dict(record.get("extra") or {})
            for key, value in incoming_extra.items():
                if key == "is_supplemental":
                    existing_extra[key] = bool(existing_extra.get(key, False) or value)
                elif key == "importance":
                    if existing_extra.get(key) is None:
                        existing_extra[key] = value
                    else:
                        try:
                            existing_extra[key] = max(int(existing_extra[key]), int(value))
                        except (TypeError, ValueError):
                            pass
                elif key not in existing_extra or existing_extra.get(key) in (None, ""):
                    existing_extra[key] = value
            existing.update(
                {
                    "relationship_type": existing.get("relationship_type") or record.get("relationship_type"),
                    "status": existing.get("status") or record.get("status"),
                    "tension": existing.get("tension") or record.get("tension"),
                    "direction": existing.get("direction") or record.get("direction"),
                    "trigger_event": existing.get("trigger_event") or record.get("trigger_event"),
                    "importance": existing.get("importance") or record.get("importance"),
                    "extra": existing_extra,
                }
            )
            continue

        seen_pairs[pair] = len(normalized)
        normalized.append(record)

    if not expand:
        return normalized

    target_count = _target_relationship_count(len(characters), total_chapters)
    existing_pairs = set(seen_pairs.keys())

    def _append_support_relation(from_char: Dict[str, Any], to_char: Dict[str, Any], description: str, *, relation_type: str = "alliance") -> None:
        if len(normalized) >= target_count:
            return
        pair = tuple(sorted((from_char["name"], to_char["name"])))
        if pair in existing_pairs:
            return
        support_record = _augment_relationship_profile(
            {
                "character_from": from_char["name"],
                "character_to": to_char["name"],
                "description": description,
                "extra": {
                    "relationship_type": relation_type,
                    "status": "developing",
                    "tension": "medium",
                    "core_conflict": description,
                    "direction": "从试探走向互信",
                    "trigger_event": f"在第{max(2, total_chapters // 3 or 2)}章前后建立关键连接。",
                    "is_supplemental": True,
                },
            },
            {
                "character_from": from_char["name"],
                "character_to": to_char["name"],
                "description": description,
                "extra": {
                    "relationship_type": relation_type,
                    "status": "developing",
                    "tension": "medium",
                    "core_conflict": description,
                    "direction": "从试探走向互信",
                    "trigger_event": f"在第{max(2, total_chapters // 3 or 2)}章前后建立关键连接。",
                    "is_supplemental": True,
                },
            },
            index=len(normalized),
            chapter_count=total_chapters,
            protagonist_name=protagonist_name,
        )
        normalized.append(support_record)
        existing_pairs.add(pair)

    if characters:
        for character in characters[1:]:
            if len(normalized) >= target_count:
                break
            description = (
                f"{protagonist_name}与{character['name']}围绕{character.get('goals') or character.get('identity') or '主线目标'}持续牵引，"
                "关系在合作与冲突之间摆动。"
            )
            _append_support_relation(characters[0], character, description, relation_type="alliance")

    if len(normalized) < target_count and len(characters) > 2:
        for index in range(1, len(characters) - 1):
            if len(normalized) >= target_count:
                break
            from_char = characters[index]
            to_char = characters[index + 1]
            description = (
                f"{from_char['name']}与{to_char['name']}在{blueprint_title or '故事'}中形成并行推进与隐性分歧的关系。"
            )
            _append_support_relation(from_char, to_char, description, relation_type="tension")

    if len(normalized) < target_count and len(characters) > 2:
        for index in range(1, len(characters) - 1):
            if len(normalized) >= target_count:
                break
            from_char = characters[index]
            to_char = characters[(index + 2) % len(characters)]
            description = (
                f"{from_char['name']}与{to_char['name']}在{blueprint_title or '主线'}中形成镜像/对照关系，"
                "用于加强支线密度。"
            )
            _append_support_relation(from_char, to_char, description, relation_type="tension")

    return normalized


def _prepare_blueprint_characters(
    characters: List[Any],
    *,
    total_chapters: int,
    blueprint_title: str,
    genre: str,
) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for index, raw_character in enumerate(characters):
        if hasattr(raw_character, "model_dump"):
            character_data = raw_character.model_dump()
        elif isinstance(raw_character, dict):
            character_data = dict(raw_character)
        else:
            character_data = dict(getattr(raw_character, "__dict__", {}))
        supplemental = _character_is_supplemental(character_data)
        if supplemental and _is_legacy_supplemental_character(character_data):
            character_data = _build_supplemental_character_seed(
                index=index,
                total_chapters=total_chapters,
                blueprint_title=blueprint_title,
                genre=genre,
            )
            supplemental = True
        normalized.append(
            _normalize_character_record(
                character_data,
                index=index,
                total_chapters=total_chapters,
                blueprint_title=blueprint_title,
                genre=genre,
                supplemental=supplemental,
            )
        )

    target_count = _target_character_count(total_chapters)
    if len(normalized) > target_count:
        anchored = [
            item for item in normalized
            if not bool((item.get("extra") or {}).get("is_supplemental"))
        ]
        supplemental = [
            item for item in normalized
            if bool((item.get("extra") or {}).get("is_supplemental"))
        ]
        if len(anchored) < len(normalized):
            normalized = anchored + supplemental[:max(0, target_count - len(anchored))]

    while len(normalized) < target_count:
        index = len(normalized)
        normalized.append(
            _normalize_character_record(
                _build_supplemental_character_seed(
                    index=index,
                    total_chapters=total_chapters,
                    blueprint_title=blueprint_title,
                    genre=genre,
                ),
                index=index,
                total_chapters=total_chapters,
                blueprint_title=blueprint_title,
                genre=genre,
                supplemental=True,
            )
        )

    return normalized


def _prepare_blueprint_relationships(
    relationships: List[Any],
    *,
    characters: List[Dict[str, Any]],
    total_chapters: int,
    blueprint_title: str,
) -> List[Dict[str, Any]]:
    protagonist_name = characters[0]["name"] if characters else blueprint_title or "主角"
    character_names = {
        str(character.get("name") or "").strip()
        for character in characters
        if str(character.get("name") or "").strip()
    }
    normalized: List[Dict[str, Any]] = []
    for index, raw_relationship in enumerate(relationships):
        if hasattr(raw_relationship, "model_dump"):
            relation_data = raw_relationship.model_dump()
        elif isinstance(raw_relationship, dict):
            relation_data = dict(raw_relationship)
        else:
            relation_data = dict(getattr(raw_relationship, "__dict__", {}))
        if character_names and not _relationship_mentions_current_cast(relation_data, character_names):
            continue
        normalized.append(
            _normalize_relationship_record(
                relation_data,
                index=index,
                chapter_count=total_chapters,
                protagonist_name=protagonist_name,
            )
        )

    existing_pairs = {
        tuple(sorted((item["character_from"], item["character_to"])))
        for item in normalized
        if item.get("character_from") and item.get("character_to")
    }
    target_count = _target_relationship_count(len(characters), total_chapters)

    def _add_support_relation(from_char: Dict[str, Any], to_char: Dict[str, Any], description: str) -> None:
        pair = tuple(sorted((from_char["name"], to_char["name"])))
        if pair in existing_pairs or len(normalized) >= target_count:
            return
        normalized.append(
            _normalize_relationship_record(
                {
                    "character_from": from_char["name"],
                    "character_to": to_char["name"],
                    "description": description,
                    "extra": {
                        "relationship_type": "alliance"
                        if from_char["name"] == protagonist_name
                        else "tension",
                        "status": "developing",
                        "tension": "medium",
                        "direction": "从试探走向互相影响",
                        "trigger_event": f"在第{max(2, total_chapters // 3 or 2)}章前后建立关键连接",
                        "is_supplemental": True,
                    },
                },
                index=len(normalized),
                chapter_count=total_chapters,
                protagonist_name=protagonist_name,
            )
        )
        existing_pairs.add(pair)

    if characters:
        for character in characters[1:]:
            if len(normalized) >= target_count:
                break
            description = (
                f"{protagonist_name}与{character['name']}围绕{character.get('goals') or character.get('identity') or '主线目标'}持续牵引，"
                "关系在合作与冲突之间摆动。"
            )
            _add_support_relation(characters[0], character, description)

    if len(normalized) < target_count:
        for index in range(1, max(1, len(characters) - 1)):
            if len(normalized) >= target_count:
                break
            from_char = characters[index]
            to_char = characters[index + 1]
            description = (
                f"{from_char['name']}与{to_char['name']}在{blueprint_title or '故事'}中形成并行推进与隐性分歧的关系。"
            )
            _add_support_relation(from_char, to_char, description)

    if len(normalized) < target_count and len(characters) > 2:
        for index in range(1, len(characters) - 1):
            if len(normalized) >= target_count:
                break
            from_char = characters[index]
            to_char = characters[(index + 2) % len(characters)]
            description = (
                f"{from_char['name']}与{to_char['name']}在{blueprint_title or '主线'}中形成镜像/对照关系，"
                "用于加强支线密度。"
            )
            _add_support_relation(from_char, to_char, description)

    return normalized


def _chapter_progress_stage(status_value: str) -> str:
    return _PROGRESS_STAGE_MAP.get(status_value, "idle")


def _chapter_progress_message(stage: str, last_error_summary: Optional[str] = None) -> str:
    base = _PROGRESS_MESSAGE_MAP.get(stage, "章节状态更新中")
    if stage in {"failed", "evaluation_failed"} and last_error_summary:
        return f"{base}：{last_error_summary}"
    return base


def _chapter_allowed_actions(stage: str) -> List[str]:
    return list(_PROGRESS_ACTIONS_MAP.get(stage, ["refresh_status"]))


def _get_loaded_relation_items(chapter: Optional[Chapter], attr_name: str) -> List[Any]:
    if not chapter:
        return []
    try:
        state = inspect(chapter)
        if attr_name in state.unloaded:
            return []
    except Exception:
        pass
    value = getattr(chapter, attr_name, None)
    return list(value or [])


def _get_loaded_relation_value(chapter: Optional[Chapter], attr_name: str) -> Any:
    if not chapter:
        return None
    try:
        state = inspect(chapter)
        if attr_name in state.unloaded:
            return None
    except Exception:
        pass
    return getattr(chapter, attr_name, None)


def _get_loaded_scalar_value(chapter: Optional[Chapter], attr_name: str) -> Any:
    if not chapter:
        return None
    try:
        state = inspect(chapter)
        if attr_name in state.unloaded or attr_name in getattr(state, "expired_attributes", set()):
            return None
    except Exception:
        pass
    try:
        return getattr(chapter, attr_name, None)
    except Exception:
        return None


def _coerce_runtime_datetime(value: Any) -> Optional[datetime]:
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


def _runtime_stale_after_seconds(runtime: Dict[str, Any]) -> int:
    """Keep legacy stale behavior, but honor a persisted generation budget."""
    stale_after_seconds = int(_BUSY_CHAPTER_STALE_TIMEOUT.total_seconds())
    try:
        timeout_seconds = int(float(runtime.get("timeout_seconds") or 0))
    except (TypeError, ValueError):
        timeout_seconds = 0
    if timeout_seconds > 0:
        stale_after_seconds = min(
            _MAX_RUNTIME_STALE_SECONDS,
            max(stale_after_seconds, timeout_seconds + _RUNTIME_STALE_GRACE_SECONDS),
        )
    return stale_after_seconds


def _extract_generation_runtime_payload(chapter: Optional[Chapter]) -> Dict[str, Any]:
    raw_summary = _get_loaded_scalar_value(chapter, "real_summary") if chapter else None
    if not isinstance(raw_summary, str):
        return {}
    raw_summary = raw_summary.strip()
    if not raw_summary:
        return {}
    try:
        payload = json.loads(raw_summary)
    except (TypeError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    runtime = payload.get("generation_runtime")
    if not isinstance(runtime, dict):
        return {}
    normalized_runtime = dict(runtime)
    for field in ("started_at", "updated_at", "heartbeat_at"):
        parsed = _coerce_runtime_datetime(normalized_runtime.get(field))
        if parsed is not None:
            normalized_runtime[field] = parsed
    chapter_status = _normalize_chapter_status(_get_loaded_scalar_value(chapter, "status") if chapter else None)
    runtime_stage = _safe_str(
        normalized_runtime.get("progress_stage") or normalized_runtime.get("status") or chapter_status
    ).lower()
    runtime_updated_at = (
        _coerce_runtime_datetime(normalized_runtime.get("heartbeat_at"))
        or _coerce_runtime_datetime(normalized_runtime.get("updated_at"))
        or _coerce_runtime_datetime(_get_loaded_scalar_value(chapter, "updated_at") if chapter else None)
        or _coerce_runtime_datetime(normalized_runtime.get("started_at"))
        or _coerce_runtime_datetime(_get_loaded_scalar_value(chapter, "created_at") if chapter else None)
    )
    busy_runtime_stages = {
        "queued",
        "generating",
        "prepare_context",
        "generate_mission",
        "generate_variants",
        "review",
        "ai_review",
        "evaluating",
        "self_critique",
        "enrichment",
        "persist_versions",
        "selecting",
        "running",
        "in_progress",
    }
    if runtime_stage in busy_runtime_stages and runtime_updated_at is not None:
        stale_seconds = int((datetime.now(timezone.utc) - runtime_updated_at).total_seconds())
        normalized_runtime["stale"] = False
        normalized_runtime["stale_seconds"] = max(0, stale_seconds)
        if stale_seconds >= _runtime_stale_after_seconds(normalized_runtime):
            normalized_runtime["stale"] = True
            normalized_runtime["stale_reason"] = "generation_runtime_has_not_updated"
    elif runtime_stage in busy_runtime_stages:
        normalized_runtime["stale"] = None
        normalized_runtime["stale_reason"] = "generation_runtime_missing_update_timestamp"
    return normalized_runtime


def _build_chapter_time_snapshot(
    chapter: Optional[Chapter],
    *,
    status_value: str,
    runtime_payload: Optional[Dict[str, Any]] = None,
) -> tuple[Optional[datetime], Optional[datetime]]:
    if not chapter:
        return None, None
    runtime_payload = runtime_payload or {}
    versions = _get_loaded_relation_items(chapter, "versions")
    evaluations = _get_loaded_relation_items(chapter, "evaluations")
    has_activity = status_value != ChapterGenerationStatus.NOT_GENERATED.value
    selected_version_id = _get_loaded_scalar_value(chapter, "selected_version_id")
    if not has_activity and not versions and not evaluations and not selected_version_id and not runtime_payload:
        return None, None

    def normalize_dt(value: Any) -> Optional[datetime]:
        return _coerce_runtime_datetime(value)

    runtime_started_at = normalize_dt(runtime_payload.get("started_at"))
    runtime_updated_at = normalize_dt(runtime_payload.get("updated_at"))
    chapter_updated_at = normalize_dt(_get_loaded_scalar_value(chapter, "updated_at"))
    chapter_created_at = normalize_dt(_get_loaded_scalar_value(chapter, "created_at"))
    started_at = runtime_started_at or chapter_created_at or chapter_updated_at
    timestamps: List[datetime] = []
    for candidate in (runtime_started_at, runtime_updated_at, chapter_created_at, chapter_updated_at):
        normalized = normalize_dt(candidate)
        if normalized:
            timestamps.append(normalized)
    for version in versions:
        normalized = normalize_dt(version.created_at)
        if normalized:
            timestamps.append(normalized)
    for evaluation in evaluations:
        normalized = normalize_dt(evaluation.created_at)
        if normalized:
            timestamps.append(normalized)
    updated_at = max(timestamps) if timestamps else started_at
    return started_at, updated_at


def _build_chapter_last_error_summary(chapter: Optional[Chapter], status_value: str) -> Optional[str]:
    if not chapter:
        return None
    latest_failure: Optional[str] = None
    evaluations = sorted(_get_loaded_relation_items(chapter, "evaluations"), key=lambda item: item.created_at)
    for evaluation in reversed(evaluations):
        decision = _safe_str(evaluation.decision).lower()
        if decision in {"failed", "generation_failed", "evaluation_failed"}:
            latest_failure = evaluation.feedback or evaluation.decision
            break
    if latest_failure and status_value in {
        ChapterGenerationStatus.FAILED.value,
        ChapterGenerationStatus.EVALUATION_FAILED.value,
    }:
        return _shorten_text(latest_failure, 200)
    if status_value in {
        ChapterGenerationStatus.FAILED.value,
        ChapterGenerationStatus.EVALUATION_FAILED.value,
    }:
        fallback = evaluations[-1].feedback if evaluations else "生成失败"
        chapter_real_summary = _get_loaded_scalar_value(chapter, "real_summary")
        return _shorten_text(chapter_real_summary or fallback, 200)
    return None


def build_chapter_progress_snapshot(
    chapter: Optional[Chapter],
    *,
    status_value: Optional[str] = None,
    progress_stage: Optional[str] = None,
    progress_message: Optional[str] = None,
    allowed_actions: Optional[List[str]] = None,
    last_error_summary: Optional[str] = None,
    started_at: Optional[datetime] = None,
    updated_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    normalized_status = _normalize_chapter_status(status_value or (chapter.status if chapter else None))
    runtime_payload = _extract_generation_runtime_payload(chapter)
    runtime_stage = _safe_str(runtime_payload.get("progress_stage")) if runtime_payload else ""
    runtime_message = _safe_str(runtime_payload.get("progress_message")) if runtime_payload else ""
    runtime_actions = runtime_payload.get("allowed_actions") if isinstance(runtime_payload.get("allowed_actions"), list) else None
    runtime_error_summary = _safe_str(runtime_payload.get("last_error_summary")) if runtime_payload else ""
    stage = progress_stage or runtime_stage or _chapter_progress_stage(normalized_status)
    error_summary = last_error_summary or runtime_error_summary or None
    if error_summary is None and normalized_status in {
        ChapterGenerationStatus.FAILED.value,
        ChapterGenerationStatus.EVALUATION_FAILED.value,
    }:
        error_summary = _build_chapter_last_error_summary(chapter, normalized_status)
    stage_message = progress_message or runtime_message or _chapter_progress_message(stage, error_summary)
    chapter_started_at, chapter_updated_at = _build_chapter_time_snapshot(
        chapter,
        status_value=normalized_status,
        runtime_payload=runtime_payload,
    )
    return {
        "progress_stage": stage,
        "progress_message": stage_message,
        "started_at": started_at or chapter_started_at,
        "updated_at": updated_at or chapter_updated_at,
        "allowed_actions": allowed_actions if allowed_actions is not None else (runtime_actions or _chapter_allowed_actions(stage)),
        "last_error_summary": error_summary,
    }


class NovelService:
    """小说项目服务，基于拆表后的结构提供聚合与业务操作。"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = NovelRepository(session)
        self._vector_store = VectorStoreService()

    # ------------------------------------------------------------------
    # 项目与摘要
    # ------------------------------------------------------------------
    async def create_project(self, user_id: int, title: str, initial_prompt: str) -> NovelProject:
        project = NovelProject(
            id=str(uuid.uuid4()),
            user_id=user_id,
            title=title,
            initial_prompt=initial_prompt,
        )
        self.session.add(project)
        await self.session.commit()
        await self.session.refresh(project)
        return project

    async def ensure_project_owner(self, project_id: str, user_id: int) -> NovelProject:
        project = await self.repo.get_by_id(project_id)
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
        if project.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该项目")
        return project

    async def get_project_schema(self, project_id: str, user_id: int) -> NovelProjectSchema:
        project = await self.ensure_project_owner(project_id, user_id)
        return await self._serialize_project(project)

    async def get_section_data(
        self,
        project_id: str,
        user_id: int,
        section: NovelSectionType,
    ) -> NovelSectionResponse:
        project = await self.ensure_project_owner(project_id, user_id)
        if section in {NovelSectionType.CHARACTERS, NovelSectionType.RELATIONSHIPS}:
            return await self._build_dynamic_section_response(project, section)
        return self._build_section_response(project, section)

    async def get_chapter_schema(
        self,
        project_id: str,
        user_id: int,
        chapter_number: int,
    ) -> ChapterSchema:
        project = await self.ensure_project_owner(project_id, user_id)
        return self._build_chapter_schema(project, chapter_number)

    async def get_chapter_status_schema(
        self,
        project_id: str,
        user_id: int,
        chapter_number: int,
    ) -> ChapterSchema:
        project = await self.ensure_project_owner(project_id, user_id)
        # 状态轮询不仅要看进度，还要在 waiting_for_confirm / selecting / successful 等阶段
        # 回填正文与候选版本，否则前端会在轮询后把已生成内容替换成空壳章节。
        return self._build_chapter_schema(project, chapter_number, include_content=True)

    async def list_projects_for_user(self, user_id: int) -> List[NovelProjectSummary]:
        projects = await self.repo.list_by_user(user_id)
        summaries: List[NovelProjectSummary] = []
        for project in projects:
            blueprint = project.blueprint
            genre = blueprint.genre if blueprint and blueprint.genre else "未知"
            outlines = project.outlines
            chapters = project.chapters
            total = len(outlines) or len(chapters)
            completed = sum(1 for chapter in chapters if chapter.selected_version_id)
            summaries.append(
                NovelProjectSummary(
                    id=project.id,
                    title=project.title,
                    genre=genre,
                    last_edited=project.updated_at.isoformat() if project.updated_at else "未知",
                    completed_chapters=completed,
                    total_chapters=total,
                )
            )
        return summaries

    async def list_projects_for_admin(self) -> List[AdminNovelSummary]:
        projects = await self.repo.list_all()
        summaries: List[AdminNovelSummary] = []
        for project in projects:
            blueprint = project.blueprint
            genre = blueprint.genre if blueprint and blueprint.genre else "未知"
            outlines = project.outlines
            chapters = project.chapters
            total = len(outlines) or len(chapters)
            completed = sum(1 for chapter in chapters if chapter.selected_version_id)
            owner = project.owner
            summaries.append(
                AdminNovelSummary(
                    id=project.id,
                    title=project.title,
                    owner_id=owner.id if owner else 0,
                    owner_username=owner.username if owner else "未知",
                    genre=genre,
                    last_edited=project.updated_at.isoformat() if project.updated_at else "",
                    completed_chapters=completed,
                    total_chapters=total,
                )
            )
        return summaries

    async def delete_projects(self, project_ids: List[str], user_id: int) -> None:
        for pid in project_ids:
            project = await self.ensure_project_owner(pid, user_id)
            await self.repo.delete(project)
            # 同步清理向量数据
            try:
                await self._vector_store.delete_by_project(pid)
            except Exception as e:
                logging.error(f"Failed to delete vector data for project {pid}: {e}")
        await self.session.commit()

    async def count_projects(self) -> int:
        result = await self.session.execute(select(func.count(NovelProject.id)))
        return result.scalar_one()

    # ------------------------------------------------------------------
    # 对话管理
    # ------------------------------------------------------------------
    async def list_conversations(self, project_id: str) -> List[NovelConversation]:
        stmt = (
            select(NovelConversation)
            .where(NovelConversation.project_id == project_id)
            .order_by(NovelConversation.seq.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars())

    async def append_conversation(self, project_id: str, role: str, content: str, metadata: Optional[Dict] = None) -> None:
        result = await self.session.execute(
            select(func.max(NovelConversation.seq)).where(NovelConversation.project_id == project_id)
        )
        current_max = result.scalar()
        next_seq = (current_max or 0) + 1
        convo = NovelConversation(
            project_id=project_id,
            seq=next_seq,
            role=role,
            content=content,
            metadata=metadata,
        )
        self.session.add(convo)
        await self._touch_project(project_id, auto_commit=False)
        await self.session.commit()

    # ------------------------------------------------------------------
    # 蓝图管理
    # ------------------------------------------------------------------
    async def replace_blueprint(self, project_id: str, blueprint: Blueprint) -> None:
        record = await self.session.get(NovelBlueprint, project_id)
        if not record:
            record = NovelBlueprint(project_id=project_id)
            self.session.add(record)
        record.title = blueprint.title
        record.target_audience = blueprint.target_audience
        record.genre = blueprint.genre
        record.style = blueprint.style
        record.tone = blueprint.tone
        record.one_sentence_summary = blueprint.one_sentence_summary
        record.full_synopsis = blueprint.full_synopsis
        record.world_setting = {
            **(_to_plain_data(blueprint.world_setting) or {}),
            "story_arcs": _to_plain_data(blueprint.story_arcs or []),
            "volume_plan": _to_plain_data(blueprint.volume_plan or []),
            "novel_outline": _to_plain_data(blueprint.novel_outline or []),
            "foreshadowing_system": _to_plain_data(blueprint.foreshadowing_system or []),
        }

        total_chapters = _infer_total_chapters_for_cast(
            chapter_outline=blueprint.chapter_outline or [],
            novel_outline=blueprint.novel_outline or [],
            volume_plan=blueprint.volume_plan or [],
            world_setting=blueprint.world_setting,
            fallback=len(blueprint.chapter_outline or []),
        )
        normalized_characters = _normalize_blueprint_characters_for_storage(
            blueprint.characters or [],
            total_chapters=total_chapters,
            blueprint_title=blueprint.title or "",
            genre=blueprint.genre or "",
        )
        normalized_relationships = _normalize_blueprint_relationships_for_storage(
            blueprint.relationships or [],
            characters=normalized_characters,
            total_chapters=total_chapters,
            blueprint_title=blueprint.title or "",
        )

        await self.session.execute(delete(BlueprintCharacter).where(BlueprintCharacter.project_id == project_id))
        for index, data in enumerate(normalized_characters):
            self.session.add(
                BlueprintCharacter(
                    project_id=project_id,
                    name=data.get("name", ""),
                    identity=data.get("identity"),
                    personality=data.get("personality"),
                    goals=data.get("goals"),
                    abilities=data.get("abilities"),
                    relationship_to_protagonist=data.get("relationship_to_protagonist"),
                    extra=data.get("extra") or {
                        k: v
                        for k, v in data.items()
                        if k
                        not in {
                            "name",
                            "identity",
                            "personality",
                            "goals",
                            "abilities",
                            "relationship_to_protagonist",
                            "extra",
                        }
                    },
                    position=index,
                )
            )

        await self.session.execute(delete(BlueprintRelationship).where(BlueprintRelationship.project_id == project_id))
        for index, relation in enumerate(normalized_relationships):
            self.session.add(
                BlueprintRelationship(
                    project_id=project_id,
                    character_from=relation["character_from"],
                    character_to=relation["character_to"],
                    description=relation["stored_description"],
                    position=index,
                )
            )

        await self.session.execute(delete(ChapterOutline).where(ChapterOutline.project_id == project_id))
        for outline in blueprint.chapter_outline:
            self.session.add(
                ChapterOutline(
                    project_id=project_id,
                    chapter_number=outline.chapter_number,
                    title=outline.title,
                    summary=outline.summary,
                    metadata=outline.model_dump(exclude={"chapter_number", "title", "summary", "metadata"}, exclude_none=True) | (outline.metadata or {}),
                )
            )

        await self._touch_project(project_id, auto_commit=False)
        await self.session.commit()

    async def patch_blueprint(self, project_id: str, patch: Dict) -> None:
        project = await self.repo.get_by_id(project_id)
        blueprint = await self.session.get(NovelBlueprint, project_id)
        if not blueprint:
            blueprint = NovelBlueprint(project_id=project_id)
            self.session.add(blueprint)

        current_blueprint = self._build_blueprint_schema(project) if project else Blueprint(
            title="",
            target_audience="",
            genre="",
            style="",
            tone="",
            one_sentence_summary="",
            full_synopsis="",
            world_setting={},
            characters=[],
            relationships=[],
            story_arcs=[],
            volume_plan=[],
            novel_outline=[],
            foreshadowing_system=[],
            chapter_outline=[],
        )
        total_chapters = _infer_total_chapters_for_cast(
            chapter_outline=current_blueprint.chapter_outline or [],
            novel_outline=current_blueprint.novel_outline or [],
            volume_plan=current_blueprint.volume_plan or [],
            world_setting=current_blueprint.world_setting,
            fallback=len(current_blueprint.chapter_outline or []),
        )

        if "one_sentence_summary" in patch:
            blueprint.one_sentence_summary = patch["one_sentence_summary"]
        if "full_synopsis" in patch:
            blueprint.full_synopsis = patch["full_synopsis"]
        if "world_setting" in patch and patch["world_setting"] is not None:
            # 创建新字典对象以触发 SQLAlchemy 的变更检测
            existing = blueprint.world_setting or {}
            world_setting_patch = _to_plain_data(patch["world_setting"]) or {}
            factions_payload = world_setting_patch.pop("factions", None)
            blueprint.world_setting = {**existing, **world_setting_patch}

        if "story_arcs" in patch and patch["story_arcs"] is not None:
            current_world = dict(blueprint.world_setting or {})
            current_world["story_arcs"] = patch["story_arcs"]
            blueprint.world_setting = current_world

        if "volume_plan" in patch and patch["volume_plan"] is not None:
            current_world = dict(blueprint.world_setting or {})
            current_world["volume_plan"] = patch["volume_plan"]
            blueprint.world_setting = current_world

        if "novel_outline" in patch and patch["novel_outline"] is not None:
            current_world = dict(blueprint.world_setting or {})
            current_world["novel_outline"] = patch["novel_outline"]
            blueprint.world_setting = current_world

        if "foreshadowing_system" in patch and patch["foreshadowing_system"] is not None:
            current_world = dict(blueprint.world_setting or {})
            current_world["foreshadowing_system"] = patch["foreshadowing_system"]
            blueprint.world_setting = current_world

            if factions_payload is not None:
                await self.session.execute(delete(Faction).where(Faction.project_id == project_id))
                for item in factions_payload:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("name") or item.get("title") or "").strip()
                    if not name:
                        continue
                    self.session.add(
                        Faction(
                            project_id=project_id,
                            name=name,
                            description=str(item.get("description") or "").strip() or None,
                            faction_type=str(item.get("faction_type") or "").strip() or None,
                            power_level=str(item.get("power_level") or "").strip() or None,
                            territory=str(item.get("territory") or "").strip() or None,
                            leader=str(item.get("leader") or "").strip() or None,
                            member_count=str(item.get("member_count") or "").strip() or None,
                            current_status=str(item.get("current_status") or "").strip() or None,
                            culture=str(item.get("culture") or "").strip() or None,
                            resources=item.get("resources") if isinstance(item.get("resources"), list) else None,
                            hierarchy=item.get("hierarchy") if isinstance(item.get("hierarchy"), dict) else None,
                            goals=item.get("goals") if isinstance(item.get("goals"), list) else None,
                            recent_events=item.get("recent_events") if isinstance(item.get("recent_events"), list) else None,
                            rules=item.get("rules") if isinstance(item.get("rules"), list) else None,
                            traditions=item.get("traditions") if isinstance(item.get("traditions"), list) else None,
                            extra=item.get("extra") if isinstance(item.get("extra"), dict) else None,
                        )
                    )
        if "characters" in patch and patch["characters"] is not None:
            normalized_characters = _normalize_blueprint_characters_for_storage(
                patch["characters"],
                total_chapters=total_chapters,
                blueprint_title=blueprint.title or current_blueprint.title,
                genre=blueprint.genre or current_blueprint.genre,
            )
            await self.session.execute(delete(BlueprintCharacter).where(BlueprintCharacter.project_id == project_id))
            for index, data in enumerate(normalized_characters):
                self.session.add(
                    BlueprintCharacter(
                        project_id=project_id,
                        name=data.get("name", ""),
                        identity=data.get("identity"),
                        personality=data.get("personality"),
                        goals=data.get("goals"),
                        abilities=data.get("abilities"),
                        relationship_to_protagonist=data.get("relationship_to_protagonist"),
                        extra=data.get("extra") or {
                            k: v
                            for k, v in data.items()
                            if k
                            not in {
                                "name",
                                "identity",
                                "personality",
                                "goals",
                                "abilities",
                                "relationship_to_protagonist",
                                "extra",
                            }
                        },
                        position=index,
                    )
                )
        if "relationships" in patch and patch["relationships"] is not None:
            source_characters = (
                normalized_characters
                if "characters" in patch and patch["characters"] is not None
                else current_blueprint.characters
            )
            normalized_relationships = _normalize_blueprint_relationships_for_storage(
                patch["relationships"],
                characters=source_characters,
                total_chapters=total_chapters,
                blueprint_title=blueprint.title or current_blueprint.title,
            )
            await self.session.execute(delete(BlueprintRelationship).where(BlueprintRelationship.project_id == project_id))
            for index, relation in enumerate(normalized_relationships):
                self.session.add(
                    BlueprintRelationship(
                        project_id=project_id,
                        character_from=relation["character_from"],
                        character_to=relation["character_to"],
                        description=relation["stored_description"],
                        position=index,
                    )
                )
        if "chapter_outline" in patch and patch["chapter_outline"] is not None:
            await self.session.execute(delete(ChapterOutline).where(ChapterOutline.project_id == project_id))
            for outline in patch["chapter_outline"]:
                outline_payload = dict(outline)
                metadata = dict(outline_payload.get("metadata") or {})
                metadata.update({
                    key: value
                    for key, value in outline_payload.items()
                    if key not in {"chapter_number", "title", "summary", "metadata"} and value is not None
                })
                self.session.add(
                    ChapterOutline(
                        project_id=project_id,
                        chapter_number=outline_payload.get("chapter_number"),
                        title=outline_payload.get("title", ""),
                        summary=outline_payload.get("summary"),
                        metadata=metadata,
                    )
                )
        await self._touch_project(project_id, auto_commit=False)
        await self.session.commit()

    # ------------------------------------------------------------------
    # 章节与版本
    # ------------------------------------------------------------------
    async def get_outline(self, project_id: str, chapter_number: int) -> Optional[ChapterOutline]:
        stmt = (
            select(ChapterOutline)
            .where(
                ChapterOutline.project_id == project_id,
                ChapterOutline.chapter_number == chapter_number,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def update_or_create_outline(
        self,
        project_id: str,
        chapter_number: int,
        title: str,
        summary: str,
        metadata: Optional[dict] = None,
    ) -> ChapterOutline:
        """更新或创建章节大纲，支持 metadata 存储导演脚本等信息。"""
        stmt = select(ChapterOutline).where(
            ChapterOutline.project_id == project_id,
            ChapterOutline.chapter_number == chapter_number,
        )
        result = await self.session.execute(stmt)
        outline = result.scalars().first()
        if outline:
            outline.title = title
            outline.summary = summary
            if metadata is not None:
                outline.metadata = metadata
            await self.session.flush()
            return outline

        outline = ChapterOutline(
            project_id=project_id,
            chapter_number=chapter_number,
            title=title,
            summary=summary,
            metadata=metadata,
        )
        try:
            async with self.session.begin_nested():
                self.session.add(outline)
                await self.session.flush()
            return outline
        except IntegrityError:
            result = await self.session.execute(stmt)
            outline = result.scalars().first()
            if not outline:
                raise
            outline.title = title
            outline.summary = summary
            if metadata is not None:
                outline.metadata = metadata
            await self.session.flush()
            return outline

    async def get_or_create_chapter(self, project_id: str, chapter_number: int) -> Chapter:
        stmt = (
            select(Chapter)
            .options(
                selectinload(Chapter.selected_version),
                selectinload(Chapter.versions),
                selectinload(Chapter.evaluations),
            )
            .where(
                Chapter.project_id == project_id,
                Chapter.chapter_number == chapter_number,
            )
        )
        result = await self.session.execute(stmt)
        chapter = result.scalars().first()
        if chapter:
            return chapter
        chapter = Chapter(project_id=project_id, chapter_number=chapter_number)
        self.session.add(chapter)
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            result = await self.session.execute(stmt)
            chapter = result.scalars().first()
            if not chapter:
                raise
            return chapter
        await self.session.refresh(chapter)
        return chapter

    async def replace_chapter_versions(self, chapter: Chapter, contents: List[str], metadata: Optional[List[Dict]] = None) -> List[ChapterVersion]:
        await self.session.execute(delete(ChapterVersion).where(ChapterVersion.chapter_id == chapter.id))
        versions: List[ChapterVersion] = []
        for index, content in enumerate(contents):
            extra = metadata[index] if metadata and index < len(metadata) else None
            text_content = _normalize_version_content(content, extra)
            version = ChapterVersion(
                chapter_id=chapter.id,
                content=text_content,
                metadata=extra,  # ✅ 落盘 metadata
                version_label=f"v{index+1}",
            )
            self.session.add(version)
            versions.append(version)
        chapter.status = ChapterGenerationStatus.WAITING_FOR_CONFIRM.value
        await self._touch_project(chapter.project_id, auto_commit=False)
        await self.session.commit()
        await self.session.refresh(chapter)
        return versions

    async def append_chapter_versions(
        self,
        chapter: Chapter,
        contents: List[str],
        metadata: Optional[List[Dict]] = None,
        *,
        max_versions: int = 6,
        expected_generation_run_id: Optional[str] = None,
    ) -> List[ChapterVersion]:
        """
        追加写入新版本，并按时间保留最近 max_versions 个版本。
        用于“每次生成 2 个版本，但最多保留 6 个历史版本”的场景。
        """
        current_stmt = (
            select(ChapterVersion)
            .where(ChapterVersion.chapter_id == chapter.id)
            .order_by(ChapterVersion.created_at)
        )
        current_result = await self.session.execute(current_stmt)
        existing_versions = current_result.scalars().all()
        existing_count = len(existing_versions)

        for index, content in enumerate(contents):
            extra = metadata[index] if metadata and index < len(metadata) else None
            text_content = _normalize_version_content(content, extra)
            version = ChapterVersion(
                chapter_id=chapter.id,
                content=text_content,
                metadata=extra,
                version_label=f"v{existing_count + index + 1}",
            )
            self.session.add(version)

        await self.session.flush()

        if expected_generation_run_id:
            await self.session.refresh(chapter)
            chapter_runtime = str(chapter.real_summary or "")
            if expected_generation_run_id not in chapter_runtime or chapter.status != ChapterGenerationStatus.GENERATING.value:
                raise HTTPException(status_code=409, detail="章节生成任务已失效或被取消")

        refreshed_result = await self.session.execute(current_stmt)
        all_versions = refreshed_result.scalars().all()

        if max_versions > 0 and len(all_versions) > max_versions:
            remove_count = len(all_versions) - max_versions
            to_remove = all_versions[:remove_count]
            remove_ids = {item.id for item in to_remove if item.id is not None}
            for item in to_remove:
                await self.session.delete(item)
            if chapter.selected_version_id in remove_ids:
                chapter.selected_version_id = None
            all_versions = all_versions[remove_count:]

        for idx, version in enumerate(all_versions, start=1):
            version.version_label = f"v{idx}"

        chapter.status = ChapterGenerationStatus.WAITING_FOR_CONFIRM.value
        await self._touch_project(chapter.project_id, auto_commit=False)
        await self.session.commit()
        await self.session.refresh(chapter)
        return all_versions

    async def select_chapter_version(self, chapter: Chapter, version_index: int) -> ChapterVersion:
        stmt = select(ChapterVersion).where(ChapterVersion.chapter_id == chapter.id).order_by(ChapterVersion.created_at)
        result = await self.session.execute(stmt)
        versions = result.scalars().all()
        
        if not versions or version_index < 0 or version_index >= len(versions):
            raise HTTPException(status_code=400, detail="版本索引无效")
        selected = versions[version_index]
        
        # 校验内容是否为空
        if not selected.content or len(selected.content.strip()) == 0:
            raise HTTPException(status_code=400, detail="选中的版本内容为空，无法确认为最终版")
        
        chapter.selected_version_id = selected.id
        chapter.selected_version = selected
        chapter.status = ChapterGenerationStatus.SUCCESSFUL.value
        chapter.word_count = len(selected.content or "")
        await self._touch_project(chapter.project_id, auto_commit=False)
        await self.session.commit()
        await self.session.refresh(chapter)
        return selected

    async def add_chapter_evaluation(self, chapter: Chapter, version: Optional[ChapterVersion], feedback: str, decision: Optional[str] = None) -> None:
        evaluation = ChapterEvaluation(
            chapter_id=chapter.id,
            version_id=version.id if version else None,
            feedback=feedback,
            decision=decision,
        )
        self.session.add(evaluation)
        chapter.status = ChapterGenerationStatus.WAITING_FOR_CONFIRM.value
        await self._touch_project(chapter.project_id, auto_commit=False)
        await self.session.commit()
        await self.session.refresh(chapter)

    async def delete_chapters(self, project_id: str, chapter_numbers: Iterable[int]) -> None:
        await self.session.execute(
            delete(Chapter).where(
                Chapter.project_id == project_id,
                Chapter.chapter_number.in_(list(chapter_numbers)),
            )
        )
        await self.session.execute(
            delete(ChapterOutline).where(
                ChapterOutline.project_id == project_id,
                ChapterOutline.chapter_number.in_(list(chapter_numbers)),
            )
        )
        await self._touch_project(project_id, auto_commit=False)
        await self.session.commit()

    # ------------------------------------------------------------------
    # 序列化辅助
    # ------------------------------------------------------------------
    async def get_project_schema_for_admin(self, project_id: str) -> NovelProjectSchema:
        project = await self.repo.get_by_id(project_id)
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
        return await self._serialize_project(project)

    async def get_section_data_for_admin(
        self,
        project_id: str,
        section: NovelSectionType,
    ) -> NovelSectionResponse:
        project = await self.repo.get_by_id(project_id)
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
        if section in {NovelSectionType.CHARACTERS, NovelSectionType.RELATIONSHIPS}:
            return await self._build_dynamic_section_response(project, section)
        return self._build_section_response(project, section)

    async def get_chapter_schema_for_admin(
        self,
        project_id: str,
        chapter_number: int,
    ) -> ChapterSchema:
        project = await self.repo.get_by_id(project_id)
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
        return self._build_chapter_schema(project, chapter_number)

    async def _recover_stale_busy_chapters(self, project: NovelProject) -> None:
        now_utc = datetime.now(timezone.utc)
        dirty = False

        for chapter in project.chapters:
            status_value = _normalize_chapter_status(_get_loaded_scalar_value(chapter, "status"))
            if status_value not in _BUSY_CHAPTER_STATUSES:
                continue
            runtime = _extract_generation_runtime_payload(chapter)
            chapter_updated_at = _get_loaded_scalar_value(chapter, "updated_at")
            chapter_created_at = _get_loaded_scalar_value(chapter, "created_at")
            last_updated_at = (
                _coerce_runtime_datetime(runtime.get("heartbeat_at"))
                or _coerce_runtime_datetime(runtime.get("updated_at"))
                or _normalize_datetime_to_utc(chapter_updated_at or chapter_created_at)
            )
            if not last_updated_at:
                continue
            stale_after_seconds = _runtime_stale_after_seconds(runtime)
            if now_utc - last_updated_at < timedelta(seconds=stale_after_seconds):
                continue

            timeout_minutes = max(1, int(stale_after_seconds // 60))
            reason = f"后台任务超过 {timeout_minutes} 分钟未更新，系统已自动终止，请重新生成。"
            chapter.status = ChapterGenerationStatus.FAILED.value
            chapter.real_summary = reason
            chapter_id = _get_loaded_scalar_value(chapter, "id")
            selected_version_id = _get_loaded_scalar_value(chapter, "selected_version_id")
            if chapter_id is None:
                continue
            self.session.add(
                ChapterEvaluation(
                    chapter_id=chapter_id,
                    version_id=selected_version_id,
                    decision="generation_failed",
                    feedback=reason,
                )
            )
            dirty = True
            logger.warning(
                "Auto-recovered stale chapter to failed state: project=%s chapter=%s status=%s updated_at=%s",
                project.id,
                _get_loaded_scalar_value(chapter, "chapter_number"),
                status_value,
                chapter_updated_at or chapter_created_at,
            )

        if dirty:
            await self.session.commit()

    def _is_blueprint_schema_usable(self, blueprint: Blueprint | None) -> bool:
        if blueprint is None:
            return False

        chapter_outline = list(getattr(blueprint, "chapter_outline", None) or [])
        title = str(getattr(blueprint, "title", "") or "").strip()
        one_sentence_summary = str(getattr(blueprint, "one_sentence_summary", "") or "").strip()
        full_synopsis = str(getattr(blueprint, "full_synopsis", "") or "").strip()
        world_setting_value = getattr(blueprint, "world_setting", None)
        if hasattr(world_setting_value, "model_dump"):
            world_setting = {
                key: value
                for key, value in world_setting_value.model_dump(exclude_none=True).items()
                if value not in (None, "", [], {})
            }
        else:
            world_setting = dict(world_setting_value or {})
        characters = list(getattr(blueprint, "characters", None) or [])
        relationships = list(getattr(blueprint, "relationships", None) or [])

        return bool(
            chapter_outline
            or title
            or one_sentence_summary
            or full_synopsis
            or world_setting
            or characters
            or relationships
        )

    async def _serialize_project(self, project: NovelProject) -> NovelProjectSchema:
        await self._recover_stale_busy_chapters(project)
        conversations = [
            {"role": convo.role, "content": convo.content}
            for convo in sorted(project.conversations, key=lambda c: c.seq)
        ]

        blueprint_schema = self._build_blueprint_schema(project)
        serialized_blueprint = blueprint_schema if self._is_blueprint_schema_usable(blueprint_schema) else None

        outlines_map = {outline.chapter_number: outline for outline in project.outlines}
        chapters_map = {chapter.chapter_number: chapter for chapter in project.chapters}
        chapter_numbers = sorted(set(outlines_map.keys()) | set(chapters_map.keys()))
        chapters_schema: List[ChapterSchema] = [
            self._build_chapter_schema(
                project,
                number,
                outlines_map=outlines_map,
                chapters_map=chapters_map,
            )
            for number in chapter_numbers
        ]
        workspace_summary = self._build_workspace_summary(project, chapter_numbers, chapters_map)

        return NovelProjectSchema(
            id=project.id,
            user_id=project.user_id,
            title=project.title,
            initial_prompt=project.initial_prompt or "",
            conversation_history=conversations,
            blueprint=serialized_blueprint,
            chapters=chapters_schema,
            workspace_summary=workspace_summary,
        )

    async def _touch_project(self, project_id: str, *, auto_commit: bool = True) -> None:
        await self.session.execute(
            update(NovelProject)
            .where(NovelProject.id == project_id)
            .values(updated_at=datetime.now(timezone.utc))
        )
        if auto_commit:
            await self.session.commit()

    def _build_blueprint_schema(self, project: NovelProject) -> Blueprint:
        blueprint_obj = project.blueprint
        if blueprint_obj:
            world_setting = getattr(blueprint_obj, "world_setting", {}) or {}
            if getattr(project, "factions", None):
                world_setting = {
                    **world_setting,
                    "factions": [
                        {
                            "id": faction.id,
                            "name": faction.name,
                            "description": faction.description or "",
                            "title": faction.name,
                        }
                        for faction in project.factions
                    ],
                }
            characters = _normalize_blueprint_characters_for_storage(
                project.characters,
                total_chapters=len(project.outlines or []),
                blueprint_title=blueprint_obj.title or "",
                genre=blueprint_obj.genre or "",
                expand=False,
            )

            relationships = _normalize_blueprint_relationships_for_storage(
                project.relationships_,
                characters=characters,
                total_chapters=len(project.outlines or []),
                blueprint_title=blueprint_obj.title or "",
                expand=False,
            )

            return Blueprint(
                title=blueprint_obj.title or "",
                target_audience=blueprint_obj.target_audience or "",
                genre=blueprint_obj.genre or "",
                style=blueprint_obj.style or "",
                tone=blueprint_obj.tone or "",
                one_sentence_summary=blueprint_obj.one_sentence_summary or "",
                full_synopsis=blueprint_obj.full_synopsis or "",
                world_setting=world_setting,
                characters=characters,
                relationships=relationships,
                story_arcs=list((world_setting or {}).get("story_arcs") or []),
                volume_plan=list((world_setting or {}).get("volume_plan") or []),
                novel_outline=list((world_setting or {}).get("novel_outline") or []),
                foreshadowing_system=list((world_setting or {}).get("foreshadowing_system") or []),
                chapter_outline=[
                    ChapterOutlineSchema(
                        chapter_number=outline.chapter_number,
                        title=outline.title,
                        summary=outline.summary or "",
                        narrative_phase=(getattr(outline, "metadata", None) or {}).get("narrative_phase"),
                        chapter_role=(getattr(outline, "metadata", None) or {}).get("chapter_role"),
                        suspense_hook=(getattr(outline, "metadata", None) or {}).get("suspense_hook"),
                        emotional_progression=(getattr(outline, "metadata", None) or {}).get("emotional_progression"),
                        character_focus=list((getattr(outline, "metadata", None) or {}).get("character_focus") or []),
                        cast_delta=dict((getattr(outline, "metadata", None) or {}).get("cast_delta") or {}),
                        conflict_escalation=list((getattr(outline, "metadata", None) or {}).get("conflict_escalation") or []),
                        continuity_notes=list((getattr(outline, "metadata", None) or {}).get("continuity_notes") or []),
                        foreshadowing=dict((getattr(outline, "metadata", None) or {}).get("foreshadowing") or {}),
                        foreshadowing_tasks=dict((getattr(outline, "metadata", None) or {}).get("foreshadowing_tasks") or {}),
                        payoff_window=(getattr(outline, "metadata", None) or {}).get("payoff_window"),
                        metadata=dict(getattr(outline, "metadata", None) or {}),
                    )
                    for outline in sorted(project.outlines, key=lambda o: o.chapter_number)
                ],
            )
        return Blueprint(
            title="",
            target_audience="",
            genre="",
            style="",
            tone="",
            one_sentence_summary="",
            full_synopsis="",
            world_setting={},
            characters=[],
            relationships=[],
            story_arcs=[],
            volume_plan=[],
            novel_outline=[],
            foreshadowing_system=[],
            chapter_outline=[],
        )

    def _build_section_response(
        self,
        project: NovelProject,
        section: NovelSectionType,
    ) -> NovelSectionResponse:
        blueprint = self._build_blueprint_schema(project)

        if section == NovelSectionType.OVERVIEW:
            data = {
                "title": project.title,
                "initial_prompt": project.initial_prompt or "",
                "status": project.status,
                "one_sentence_summary": blueprint.one_sentence_summary,
                "target_audience": blueprint.target_audience,
                "genre": blueprint.genre,
                "style": blueprint.style,
                "tone": blueprint.tone,
                "full_synopsis": blueprint.full_synopsis,
                "updated_at": project.updated_at.isoformat() if project.updated_at else None,
                "character_count": len(blueprint.characters),
                "relationship_count": len(blueprint.relationships),
            }
        elif section == NovelSectionType.WORLD_SETTING:
            data = {
                "world_setting": blueprint.world_setting or {},
            }
        elif section == NovelSectionType.NOVEL_OUTLINE:
            data = {
                "novel_outline": blueprint.novel_outline or [],
                "story_arcs": blueprint.story_arcs or [],
                "volume_plan": blueprint.volume_plan or [],
                "foreshadowing_system": blueprint.foreshadowing_system or [],
                "world_setting": blueprint.world_setting or {},
                "outline_stage_count": len(blueprint.novel_outline or []),
                "story_arc_count": len(blueprint.story_arcs or []),
                "volume_count": len(blueprint.volume_plan or []),
                "foreshadowing_count": len(blueprint.foreshadowing_system or []),
            }
        elif section == NovelSectionType.CHARACTERS:
            data = {
                "characters": blueprint.characters,
                "character_count": len(blueprint.characters),
            }
        elif section == NovelSectionType.RELATIONSHIPS:
            data = {
                "relationships": blueprint.relationships,
                "relationship_count": len(blueprint.relationships),
            }
        elif section == NovelSectionType.CHAPTER_OUTLINE:
            data = {
                "chapter_outline": [outline.model_dump() for outline in blueprint.chapter_outline],
            }
        elif section == NovelSectionType.CHAPTERS:
            outlines_map = {outline.chapter_number: outline for outline in project.outlines}
            chapters_map = {chapter.chapter_number: chapter for chapter in project.chapters}
            chapter_numbers = sorted(set(outlines_map.keys()) | set(chapters_map.keys()))
            # 章节列表只返回元数据，不包含完整内容
            chapters = [
                self._build_chapter_schema(
                    project,
                    number,
                    outlines_map=outlines_map,
                    chapters_map=chapters_map,
                    include_content=False,
                ).model_dump()
                for number in chapter_numbers
            ]
            data = {
                "chapters": chapters,
                "total": len(chapters),
            }
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="未知的章节类型")

        return NovelSectionResponse(section=section, data=data)

    def _build_workspace_summary(
        self,
        project: NovelProject,
        chapter_numbers: List[int],
        chapters_map: Dict[int, Chapter],
    ) -> WorkspaceSummary:
        total_chapters = len(chapter_numbers)
        completed = 0
        failed = 0
        in_progress = 0
        total_word_count = 0
        active_chapter: Optional[int] = None
        first_incomplete: Optional[int] = None
        next_chapter_to_generate: Optional[int] = None
        can_generate_next = False

        normalized_statuses: Dict[int, str] = {}
        for chapter_number in chapter_numbers:
            chapter = chapters_map.get(chapter_number)
            status = _normalize_chapter_status(_get_loaded_scalar_value(chapter, "status") if chapter else None)
            normalized_statuses[chapter_number] = status
            if chapter:
                try:
                    total_word_count += int(_get_loaded_scalar_value(chapter, "word_count") or 0)
                except (TypeError, ValueError):
                    total_word_count += 0
            if status == ChapterGenerationStatus.SUCCESSFUL.value:
                completed += 1
                continue
            if _blocks_sequential_generation(status) and first_incomplete is None:
                first_incomplete = chapter_number
            if status in {
                ChapterGenerationStatus.GENERATING.value,
                ChapterGenerationStatus.EVALUATING.value,
                ChapterGenerationStatus.SELECTING.value,
                ChapterGenerationStatus.WAITING_FOR_CONFIRM.value,
            }:
                in_progress += 1
                if active_chapter is None:
                    active_chapter = chapter_number
                continue
            if status in {
                ChapterGenerationStatus.FAILED.value,
                ChapterGenerationStatus.EVALUATION_FAILED.value,
            }:
                failed += 1
                if active_chapter is None:
                    active_chapter = chapter_number

        if active_chapter is None:
            active_chapter = first_incomplete

        if first_incomplete is not None:
            previous_numbers = [number for number in chapter_numbers if number < first_incomplete]
            can_generate_next = all(
                not _blocks_sequential_generation(normalized_statuses.get(number))
                for number in previous_numbers
            )
            next_chapter_to_generate = first_incomplete if can_generate_next else None

        actions: List[str] = []
        if total_chapters == 0:
            actions.append("generate_outline")
        if next_chapter_to_generate is not None:
            actions.append("generate_next_chapter")
        if in_progress > 0:
            actions.append("resume_in_progress")
        if failed > 0:
            actions.append("review_failed_chapters")
        if completed > 0:
            actions.append("open_latest_chapter")

        return WorkspaceSummary(
            total_chapters=total_chapters,
            completed_chapters=completed,
            failed_chapters=failed,
            in_progress_chapters=in_progress,
            total_word_count=total_word_count,
            active_chapter=active_chapter,
            first_incomplete_chapter=first_incomplete,
            next_chapter_to_generate=next_chapter_to_generate,
            can_generate_next=can_generate_next,
            available_actions=actions,
        )

    async def _build_dynamic_section_response(
        self,
        project: NovelProject,
        section: NovelSectionType,
    ) -> NovelSectionResponse:
        blueprint = self._build_blueprint_schema(project)
        latest_states = await self._get_latest_character_states(project.id)
        timeline_events = await self._get_recent_timeline_events(project.id)

        if section == NovelSectionType.CHARACTERS:
            return NovelSectionResponse(
                section=section,
                data=self._build_dynamic_character_section(
                    blueprint=blueprint,
                    latest_states=latest_states,
                    timeline_events=timeline_events,
                ),
            )
        if section == NovelSectionType.RELATIONSHIPS:
            return NovelSectionResponse(
                section=section,
                data=self._build_dynamic_relationship_section(
                    blueprint=blueprint,
                    latest_states=latest_states,
                    timeline_events=timeline_events,
                ),
            )
        return self._build_section_response(project, section)

    async def _get_latest_character_states(self, project_id: str) -> Dict[str, CharacterState]:
        result = await self.session.execute(
            select(CharacterState)
            .where(CharacterState.project_id == project_id)
            .order_by(CharacterState.chapter_number.desc(), CharacterState.id.desc())
        )
        latest: Dict[str, CharacterState] = {}
        for state in result.scalars():
            name = (state.character_name or "").strip()
            if name and name not in latest:
                latest[name] = state
        return latest

    async def _get_recent_timeline_events(self, project_id: str) -> List[TimelineEvent]:
        result = await self.session.execute(
            select(TimelineEvent)
            .where(TimelineEvent.project_id == project_id)
            .order_by(TimelineEvent.chapter_number.desc(), TimelineEvent.id.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    def _build_dynamic_character_section(
        *,
        blueprint: Blueprint,
        latest_states: Dict[str, CharacterState],
        timeline_events: List[TimelineEvent],
    ) -> Dict[str, Any]:
        timeline_map: Dict[str, set[int]] = {}
        for event in timeline_events:
            for raw_name in event.involved_characters or []:
                name = str(raw_name or "").strip()
                if name:
                    timeline_map.setdefault(name, set()).add(event.chapter_number)

        base_items: Dict[str, Dict[str, Any]] = {}
        for item in blueprint.characters:
            record = item.model_dump() if hasattr(item, "model_dump") else dict(item)
            name = str(record.get("name") or "").strip()
            if name:
                base_items[name] = {**record, "source": "blueprint"}

        dynamic_names = sorted(set(base_items.keys()) | set(latest_states.keys()) | set(timeline_map.keys()))
        characters: List[Dict[str, Any]] = []
        for name in dynamic_names:
            base = dict(base_items.get(name) or {})
            state = latest_states.get(name)
            chapters = sorted(timeline_map.get(name) or set())
            recent_changes: List[str] = []
            if state:
                for change in state.relationship_changes or []:
                    if isinstance(change, dict) and change.get("target") and change.get("change"):
                        recent_changes.append(f"与{change['target']}：{change['change']}")
                for info in state.new_knowledge or []:
                    if info:
                        recent_changes.append(f"新信息：{info}")
                for goal in state.goal_progress or []:
                    if isinstance(goal, dict) and goal.get("goal"):
                        suffix = f"（{goal.get('progress')}）" if goal.get("progress") else ""
                        recent_changes.append(f"目标推进：{goal['goal']}{suffix}")

            characters.append({
                "name": name,
                "identity": base.get("identity") or ("动态角色" if name not in base_items else None),
                "personality": base.get("personality"),
                "goals": base.get("goals"),
                "abilities": base.get("abilities"),
                "relationship_to_protagonist": base.get("relationship_to_protagonist"),
                "current_location": state.location if state else None,
                "current_emotion": state.emotion if state else None,
                "emotion_reason": state.emotion_reason if state else None,
                "health_status": state.health_status if state else None,
                "current_goals": state.current_goals if state else None,
                "known_secrets": state.known_secrets if state else None,
                "last_active_chapter": state.chapter_number if state else (chapters[-1] if chapters else None),
                "appearance_chapters": chapters,
                "recent_changes": recent_changes[:6],
                "source": "memory_layer" if name not in base_items else ("blueprint+memory" if state else "blueprint"),
            })

        characters.sort(
            key=lambda item: (
                0 if str(item.get("source", "")).startswith("blueprint") else 1,
                -(item.get("last_active_chapter") or 0),
                item.get("name") or "",
            )
        )

        return {
            "characters": characters,
            "character_count": len(characters),
            "blueprint_character_count": len(base_items),
            "dynamic_character_count": max(0, len(characters) - len(base_items)),
            "tracked_character_count": sum(1 for item in characters if item.get("last_active_chapter")),
            "generation_usage": "章节定稿后会自动写入记忆层，后续生成会回读角色状态、目标、情绪和已知信息。",
        }

    @staticmethod
    def _build_dynamic_relationship_section(
        *,
        blueprint: Blueprint,
        latest_states: Dict[str, CharacterState],
        timeline_events: List[TimelineEvent],
    ) -> Dict[str, Any]:
        relationship_map: Dict[tuple[str, str], Dict[str, Any]] = {}

        def ensure_item(source: str, target: str) -> Dict[str, Any]:
            key = (source.strip(), target.strip())
            if key not in relationship_map:
                relationship_map[key] = {
                    "character_from": key[0],
                    "character_to": key[1],
                    "relationship_type": "关系",
                    "description": "",
                    "last_changed_chapter": None,
                    "interaction_count": 0,
                    "recent_events": [],
                    "source": "dynamic",
                }
            return relationship_map[key]

        for relation in blueprint.relationships:
            record = relation.model_dump() if hasattr(relation, "model_dump") else dict(relation)
            source = str(record.get("character_from") or "").strip()
            target = str(record.get("character_to") or "").strip()
            if source and target:
                item = ensure_item(source, target)
                item["relationship_type"] = record.get("relationship_type") or item["relationship_type"]
                item["description"] = record.get("description") or item["description"]
                item["source"] = "blueprint"

        for name, state in latest_states.items():
            for change in state.relationship_changes or []:
                if not isinstance(change, dict):
                    continue
                target = str(change.get("target") or "").strip()
                if not target:
                    continue
                item = ensure_item(name, target)
                item["relationship_type"] = change.get("type") or item["relationship_type"] or "关系变化"
                item["description"] = change.get("change") or item["description"]
                item["last_changed_chapter"] = max(item.get("last_changed_chapter") or 0, state.chapter_number or 0)
                item["source"] = "blueprint+memory" if item["source"] == "blueprint" else "memory_layer"

        for event in timeline_events:
            characters = [str(name or "").strip() for name in (event.involved_characters or []) if str(name or "").strip()]
            if len(characters) < 2:
                continue
            summary = event.event_title or event.event_description or "共同事件"
            for index, source in enumerate(characters):
                for target in characters[index + 1:]:
                    for pair in ((source, target), (target, source)):
                        item = ensure_item(pair[0], pair[1])
                        item["interaction_count"] += 1
                        if summary and summary not in item["recent_events"]:
                            item["recent_events"].append(summary)
                        item["last_changed_chapter"] = max(item.get("last_changed_chapter") or 0, event.chapter_number or 0)
                        if item["source"] == "dynamic":
                            item["source"] = "timeline"

        relationships = sorted(
            relationship_map.values(),
            key=lambda item: (-(item.get("last_changed_chapter") or 0), -(item.get("interaction_count") or 0), item.get("character_from") or ""),
        )
        for item in relationships:
            item["recent_events"] = item.get("recent_events", [])[:4]

        return {
            "relationships": relationships,
            "relationship_count": len(relationships),
            "active_relationship_count": sum(1 for item in relationships if item.get("interaction_count")),
            "generation_usage": "后续写作会读取关系变化、共同事件和角色状态，避免人物关系一直停在初始蓝图。",
        }

    def _build_chapter_schema(
        self,
        project: NovelProject,
        chapter_number: int,
        *,
        outlines_map: Optional[Dict[int, ChapterOutline]] = None,
        chapters_map: Optional[Dict[int, Chapter]] = None,
        include_content: bool = True,
    ) -> ChapterSchema:
        outlines = outlines_map or {outline.chapter_number: outline for outline in project.outlines}
        chapters = chapters_map or {chapter.chapter_number: chapter for chapter in project.chapters}
        outline = outlines.get(chapter_number)
        chapter = chapters.get(chapter_number)

        if not outline and not chapter:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="章节不存在")

        title = outline.title if outline else f"第{chapter_number}章"
        summary = outline.summary if outline else ""
        outline_metadata = dict(getattr(outline, "metadata", None) or {}) if outline else {}
        raw_real_summary = _get_loaded_scalar_value(chapter, "real_summary") if chapter else None
        runtime_payload = _extract_generation_runtime_payload(chapter)
        real_summary = None if runtime_payload else raw_real_summary
        content = None
        selected_version_id = None
        versions: Optional[List[str]] = None
        evaluation_text: Optional[str] = None
        status_value = ChapterGenerationStatus.NOT_GENERATED.value
        word_count = 0

        def _pick_fallback_version_content(items: List[Any]) -> Optional[str]:
            for item in reversed(items):
                candidate = getattr(item, "content", None)
                if isinstance(candidate, str) and candidate.strip():
                    return candidate
            return None

        if chapter:
            status_value = _normalize_chapter_status(_get_loaded_scalar_value(chapter, "status"))
            try:
                word_count = int(_get_loaded_scalar_value(chapter, "word_count") or 0)
            except (TypeError, ValueError):
                word_count = 0
            if word_count <= 0 and runtime_payload:
                try:
                    runtime_actual_word_count = int(runtime_payload.get("actual_word_count") or 0)
                except (TypeError, ValueError):
                    runtime_actual_word_count = 0
                if runtime_actual_word_count > 0 and status_value in {
                    ChapterGenerationStatus.WAITING_FOR_CONFIRM.value,
                    ChapterGenerationStatus.SELECTING.value,
                }:
                    word_count = runtime_actual_word_count
            selected_version_id = _get_loaded_scalar_value(chapter, "selected_version_id")
            selected_version = _get_loaded_relation_value(chapter, "selected_version")
            chapter_versions = sorted(
                _get_loaded_relation_items(chapter, "versions"),
                key=lambda item: item.created_at,
            )
            chapter_evaluations = sorted(
                _get_loaded_relation_items(chapter, "evaluations"),
                key=lambda item: item.created_at,
            )

            # 只有在 include_content=True 时才包含完整内容
            if selected_version_id is not None:
                selected_version = next(
                    (
                        version
                        for version in chapter_versions
                        if str(getattr(version, "id", "")) == str(selected_version_id)
                    ),
                    selected_version,
                )

            if include_content:
                if selected_version and isinstance(selected_version.content, str) and selected_version.content.strip():
                    content = selected_version.content
                else:
                    content = _pick_fallback_version_content(chapter_versions)

                # 建立版本 ID 到评估反馈的映射
                eval_map = {}
                for ev in chapter_evaluations:
                    if ev.version_id:
                        # 总是使用该版本的最新评审（由于 evaluations 已按 created_at 排序，后者会覆盖前者）
                        eval_map[ev.version_id] = ev.feedback or ev.decision

                if chapter_versions:
                    versions = [
                        ChapterVersionSchema(
                            id=v.id,
                            content=v.content,
                            style=v.version_label,
                            evaluation=eval_map.get(v.id),
                            metadata=v.metadata,
                            word_count=len(v.content or ""),
                            created_at=v.created_at
                        ) for v in chapter_versions
                    ]
                
                if chapter_evaluations:
                    latest = chapter_evaluations[-1]
                    evaluation_text = latest.feedback or latest.decision

            quality_metric_snapshot = None
            quality_source_version_id = None
            quality_candidates = []
            if selected_version:
                quality_candidates.append(selected_version)
            quality_candidates.extend(reversed(chapter_versions))
            seen_quality_version_ids = set()
            for version_item in quality_candidates:
                version_id = getattr(version_item, "id", None)
                if version_id in seen_quality_version_ids:
                    continue
                seen_quality_version_ids.add(version_id)
                version_metadata = getattr(version_item, "metadata", None) or {}
                if not isinstance(version_metadata, dict):
                    continue
                quality_metric_snapshot = version_metadata.get("quality_metrics")
                if not quality_metric_snapshot:
                    guard = version_metadata.get("story_progression_guard") or {}
                    if isinstance(guard, dict):
                        quality_metric_snapshot = guard.get("quality_metric_snapshot")
                if isinstance(quality_metric_snapshot, dict):
                    quality_source_version_id = version_id
                    break
                quality_metric_snapshot = None

            if quality_metric_snapshot:
                runtime_payload = dict(runtime_payload or {})
                runtime_payload.setdefault("quality_metrics", quality_metric_snapshot)
                runtime_payload.setdefault("quality_metrics_source_version_id", quality_source_version_id)

        progress_snapshot = build_chapter_progress_snapshot(
            chapter,
            status_value=status_value,
            last_error_summary=evaluation_text if status_value in {
                ChapterGenerationStatus.FAILED.value,
                ChapterGenerationStatus.EVALUATION_FAILED.value,
            } else None,
        )

        return ChapterSchema(
            chapter_number=chapter_number,
            title=title,
            summary=summary,
            narrative_phase=outline_metadata.get("narrative_phase"),
            chapter_role=outline_metadata.get("chapter_role"),
            suspense_hook=outline_metadata.get("suspense_hook"),
            emotional_progression=outline_metadata.get("emotional_progression"),
            character_focus=list(outline_metadata.get("character_focus") or []),
            cast_delta=dict(outline_metadata.get("cast_delta") or {}),
            conflict_escalation=list(outline_metadata.get("conflict_escalation") or []),
            continuity_notes=list(outline_metadata.get("continuity_notes") or []),
            foreshadowing=dict(outline_metadata.get("foreshadowing") or {}),
            foreshadowing_tasks=dict(outline_metadata.get("foreshadowing_tasks") or {}),
            payoff_window=outline_metadata.get("payoff_window"),
            metadata=outline_metadata,
            real_summary=real_summary,
            content=content,
            selected_version_id=selected_version_id,
            versions=versions,
            evaluation=evaluation_text,
            generation_status=ChapterGenerationStatus(status_value),
            word_count=word_count,
            progress_stage=progress_snapshot["progress_stage"],
            progress_message=progress_snapshot["progress_message"],
            started_at=progress_snapshot["started_at"],
            updated_at=progress_snapshot["updated_at"],
            allowed_actions=progress_snapshot["allowed_actions"],
            last_error_summary=progress_snapshot["last_error_summary"],
            generation_runtime=runtime_payload or None,
        )
