"""长篇章节生成契约：分层上下文、分段预算、断点快照与质量门。

该服务不调用 LLM，也不修改现有编排器；它把长篇生成必须遵守的
确定性状态和校验集中成可被正式生成入口复用的最小契约。
"""
from __future__ import annotations

import hashlib
import inspect
import json
import math
import re
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping, Optional


class LongformGenerationContractError(ValueError):
    """长篇生成计划、快照或段落不满足契约。"""


class LongformGenerationCancelled(LongformGenerationContractError):
    """分段执行在下一次 LLM 调用前发现任务已取消。"""


@dataclass(frozen=True)
class SegmentBudget:
    """单个正文段的预算和上下文边界。"""

    index: int
    target_words: int
    min_words: int
    context_scope: tuple[str, ...] = ("book", "volume", "chapter", "paragraph")


@dataclass(frozen=True)
class QualityGateResult:
    """正文质量门结果。"""

    passed: bool
    blockers: tuple[dict[str, Any], ...] = ()
    warnings: tuple[dict[str, Any], ...] = ()
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LongformGenerationPlan:
    """一次章节分段生成的不可变计划。"""

    project_id: str
    chapter_number: int
    target_word_count: int
    min_word_count: int
    segment_word_limit: int
    book_context: dict[str, Any]
    volume_context: dict[str, Any]
    chapter_context: dict[str, Any]
    segments: tuple[SegmentBudget, ...]
    plan_key: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "chapter_number": self.chapter_number,
            "target_word_count": self.target_word_count,
            "min_word_count": self.min_word_count,
            "segment_word_limit": self.segment_word_limit,
            "book_context": self.book_context,
            "volume_context": self.volume_context,
            "chapter_context": self.chapter_context,
            "segments": [asdict(item) for item in self.segments],
            "plan_key": self.plan_key,
        }


@dataclass
class LongformCheckpoint:
    """可序列化的章节断点；每完成一段就应保存一次。"""

    plan_key: str
    next_segment_index: int = 0
    completed_segments: list[dict[str, Any]] = field(default_factory=list)
    assembled_text: str = ""
    used_words: int = 0
    total_tokens: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "snapshot_version": 1,
            "plan_key": self.plan_key,
            "next_segment_index": self.next_segment_index,
            "completed_segments": list(self.completed_segments),
            "assembled_text": self.assembled_text,
            "used_words": self.used_words,
            "total_tokens": self.total_tokens,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any], plan: LongformGenerationPlan) -> "LongformCheckpoint":
        if str(payload.get("plan_key") or "") != plan.plan_key:
            raise LongformGenerationContractError("断点快照与当前长篇生成计划不匹配")
        try:
            next_index = int(payload.get("next_segment_index") or 0)
        except (TypeError, ValueError) as exc:
            raise LongformGenerationContractError("断点快照的下一段编号非法") from exc
        if next_index < 0 or next_index > len(plan.segments):
            raise LongformGenerationContractError("断点快照的下一段编号非法")
        completed = payload.get("completed_segments") or []
        if not isinstance(completed, list) or any(not isinstance(item, Mapping) for item in completed):
            raise LongformGenerationContractError("断点快照的已完成段列表非法")
        completed_records = [dict(item) for item in completed]
        if len(completed_records) != next_index:
            raise LongformGenerationContractError("断点快照的完成段数量与下一段编号不一致")
        try:
            if any(int(item.get("index", -1)) != index for index, item in enumerate(completed_records)):
                raise LongformGenerationContractError("断点快照的完成段编号不连续")
            used_words = max(0, int(payload.get("used_words") or 0))
            total_tokens = max(0, int(payload.get("total_tokens") or 0))
            recorded_words = sum(max(0, int(item.get("word_count") or 0)) for item in completed_records)
            recorded_tokens = sum(max(0, int(item.get("token_usage") or 0)) for item in completed_records)
        except (TypeError, ValueError) as exc:
            raise LongformGenerationContractError("断点快照的数值字段非法") from exc
        if used_words != recorded_words or total_tokens != recorded_tokens:
            raise LongformGenerationContractError("断点快照的累计用量与完成段记录不一致")
        return cls(
            plan_key=plan.plan_key,
            next_segment_index=next_index,
            completed_segments=completed_records,
            assembled_text=str(payload.get("assembled_text") or ""),
            used_words=used_words,
            total_tokens=total_tokens,
        )


def build_longform_generation_plan(
    *,
    project_id: str,
    chapter_number: int,
    target_word_count: int,
    min_word_count: Optional[int] = None,
    segment_word_limit: int = 4500,
    blueprint: Optional[Mapping[str, Any]] = None,
    volume: Optional[Mapping[str, Any]] = None,
    chapter_outline: Optional[Mapping[str, Any]] = None,
) -> LongformGenerationPlan:
    """建立全书—卷—章—段落四级计划，并保证段预算总和等于目标字数。"""
    project_id = str(project_id or "").strip()
    if not project_id:
        raise LongformGenerationContractError("project_id 不能为空")
    chapter_number = int(chapter_number)
    if chapter_number < 1:
        raise LongformGenerationContractError("chapter_number 必须大于 0")
    target = max(1, int(target_word_count))
    minimum = target if min_word_count is None else max(0, min(int(min_word_count), target))
    limit = max(500, int(segment_word_limit))
    segment_count = max(1, math.ceil(target / limit))
    targets = _split_budget(target, segment_count)
    minimums = _split_budget(minimum, segment_count)

    blueprint_data = dict(blueprint or {})
    chapter_data = dict(chapter_outline or {})
    volume_data = dict(volume or {}) or _select_volume(blueprint_data, chapter_number)
    book_context = _build_book_context(blueprint_data)
    volume_context = _build_volume_context(volume_data)
    chapter_context = {
        "chapter_number": chapter_number,
        "title": chapter_data.get("title") or f"第{chapter_number}章",
        "summary": chapter_data.get("summary") or chapter_data.get("content") or "",
        "goals": _as_list(chapter_data.get("goals") or chapter_data.get("chapter_goals")),
        "continuity_anchor": chapter_data.get("continuity_anchor") or chapter_data.get("continuity") or "",
        "scene_list": chapter_data.get("scene_list") or [],
    }
    segments = tuple(
        SegmentBudget(index=index, target_words=targets[index], min_words=minimums[index])
        for index in range(segment_count)
    )
    identity = {
        "project_id": project_id,
        "chapter_number": chapter_number,
        "target": target,
        "minimum": minimum,
        "limit": limit,
        "book": book_context,
        "volume": volume_context,
        "chapter": chapter_context,
        "segments": [asdict(item) for item in segments],
    }
    plan_key = hashlib.sha256(_json_bytes(identity)).hexdigest()[:24]
    return LongformGenerationPlan(
        project_id=project_id,
        chapter_number=chapter_number,
        target_word_count=target,
        min_word_count=minimum,
        segment_word_limit=limit,
        book_context=book_context,
        volume_context=volume_context,
        chapter_context=chapter_context,
        segments=segments,
        plan_key=plan_key,
    )


def start_longform_checkpoint(plan: LongformGenerationPlan) -> LongformCheckpoint:
    return LongformCheckpoint(plan_key=plan.plan_key)


def restore_longform_generation_plan(payload: Mapping[str, Any]) -> LongformGenerationPlan:
    """从 TaskRuntime 的 JSON 快照恢复计划，并拒绝被篡改或不完整的计划。"""
    if not isinstance(payload, Mapping):
        raise LongformGenerationContractError("长篇生成计划快照非法")
    try:
        segments = tuple(
            SegmentBudget(
                index=int(item["index"]),
                target_words=int(item["target_words"]),
                min_words=int(item["min_words"]),
                context_scope=tuple(item.get("context_scope") or ("book", "volume", "chapter", "paragraph")),
            )
            for item in (payload.get("segments") or [])
            if isinstance(item, Mapping)
        )
        plan = LongformGenerationPlan(
            project_id=str(payload["project_id"]),
            chapter_number=int(payload["chapter_number"]),
            target_word_count=int(payload["target_word_count"]),
            min_word_count=int(payload["min_word_count"]),
            segment_word_limit=int(payload["segment_word_limit"]),
            book_context=dict(payload.get("book_context") or {}),
            volume_context=dict(payload.get("volume_context") or {}),
            chapter_context=dict(payload.get("chapter_context") or {}),
            segments=segments,
            plan_key=str(payload["plan_key"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise LongformGenerationContractError("长篇生成计划快照字段非法") from exc
    if not plan.segments or any(item.index != index for index, item in enumerate(plan.segments)):
        raise LongformGenerationContractError("长篇生成计划的段编号不连续")
    identity = {
        "project_id": plan.project_id,
        "chapter_number": plan.chapter_number,
        "target": plan.target_word_count,
        "minimum": plan.min_word_count,
        "limit": plan.segment_word_limit,
        "book": plan.book_context,
        "volume": plan.volume_context,
        "chapter": plan.chapter_context,
        "segments": [asdict(item) for item in plan.segments],
    }
    expected_key = hashlib.sha256(_json_bytes(identity)).hexdigest()[:24]
    if plan.plan_key != expected_key:
        raise LongformGenerationContractError("长篇生成计划校验和不匹配")
    return plan


async def execute_longform_segments(
    plan: LongformGenerationPlan,
    *,
    generate_segment: Callable[[SegmentBudget, LongformCheckpoint, int], Any],
    checkpoint: Optional[LongformCheckpoint] = None,
    checkpoint_store: Optional[Callable[[LongformCheckpoint], Awaitable[None]]] = None,
    content_delta_callback: Optional[Callable[[int, str, LongformCheckpoint], Awaitable[None]]] = None,
    cancel_check: Optional[Callable[[], Any]] = None,
    progress_callback: Optional[Callable[[int, int, LongformCheckpoint], Awaitable[None]]] = None,
    required_terms: Iterable[str] = (),
    max_attempts: int = 2,
) -> LongformCheckpoint:
    """按段执行正文生成，段后持久化 checkpoint，支持取消和进程重启续跑。

    ``generate_segment`` 每次只负责一个段；返回正文字符串，或包含 ``content`` /
    ``token_usage`` 的映射。质量门失败只重试当前段，不会推进断点。
    """
    current = checkpoint or start_longform_checkpoint(plan)
    if current.plan_key != plan.plan_key:
        raise LongformGenerationContractError("断点快照与当前计划不匹配")
    attempts_limit = max(1, int(max_attempts))

    async def maybe_cancel() -> None:
        if not cancel_check:
            return
        result = cancel_check()
        if inspect.isawaitable(result):
            result = await result
        if result:
            raise LongformGenerationCancelled("长篇分段生成已取消")

    while current.next_segment_index < len(plan.segments):
        await maybe_cancel()
        segment = plan.segments[current.next_segment_index]
        last_error: Optional[Exception] = None
        for attempt in range(1, attempts_limit + 1):
            await maybe_cancel()
            try:
                generated = generate_segment(segment, current, attempt)
                if inspect.isawaitable(generated):
                    generated = await generated
                if isinstance(generated, Mapping):
                    content = str(generated.get("content") or generated.get("text") or "")
                    token_usage = int(generated.get("token_usage") or generated.get("total_tokens") or 0)
                else:
                    content = str(generated or "")
                    token_usage = 0
                next_checkpoint, _gate = append_segment(
                    current,
                    plan,
                    segment_index=segment.index,
                    content=content,
                    token_usage=token_usage,
                    required_terms=required_terms,
                )
                current = next_checkpoint
                if checkpoint_store:
                    await checkpoint_store(current)
                if content_delta_callback:
                    segment_text = extract_segment_text(current, segment.index)
                    if segment_text:
                        await content_delta_callback(segment.index, segment_text, current)
                if progress_callback:
                    await progress_callback(current.next_segment_index, len(plan.segments), current)
                last_error = None
                break
            except LongformGenerationCancelled:
                raise
            except LongformGenerationContractError as exc:
                last_error = exc
                if attempt >= attempts_limit:
                    raise
        if last_error is not None:
            raise last_error
    return current


def append_segment(
    checkpoint: LongformCheckpoint,
    plan: LongformGenerationPlan,
    *,
    segment_index: int,
    content: str,
    token_usage: int = 0,
    required_terms: Iterable[str] = (),
) -> tuple[LongformCheckpoint, QualityGateResult]:
    """校验并提交下一段；失败时不修改原断点。"""
    if checkpoint.plan_key != plan.plan_key:
        raise LongformGenerationContractError("断点快照与当前计划不匹配")
    if segment_index != checkpoint.next_segment_index:
        raise LongformGenerationContractError(
            f"必须按顺序提交段落：期待 {checkpoint.next_segment_index}，收到 {segment_index}"
        )
    if segment_index >= len(plan.segments):
        raise LongformGenerationContractError("章节分段已经全部提交")

    budget = plan.segments[segment_index]
    gate = evaluate_segment_quality(
        content,
        target_word_count=budget.target_words,
        min_word_count=budget.min_words,
        prior_content=checkpoint.assembled_text,
        required_terms=required_terms,
    )
    if not gate.passed:
        raise LongformGenerationContractError(
            "段落质量门未通过: " + ",".join(str(item.get("code")) for item in gate.blockers)
        )

    text = str(content or "").strip()
    word_count = _measure_words(text)
    assembled = f"{checkpoint.assembled_text}\n\n{text}".strip() if checkpoint.assembled_text else text
    record = {
        "index": segment_index,
        "word_count": word_count,
        "char_count": len(text),
        "target_words": budget.target_words,
        "fingerprint": _fingerprint(text),
        "token_usage": max(0, int(token_usage)),
    }
    next_checkpoint = LongformCheckpoint(
        plan_key=plan.plan_key,
        next_segment_index=segment_index + 1,
        completed_segments=[*checkpoint.completed_segments, record],
        assembled_text=assembled,
        used_words=checkpoint.used_words + word_count,
        total_tokens=checkpoint.total_tokens + max(0, int(token_usage)),
    )
    return next_checkpoint, gate


def extract_segment_text(snapshot: LongformCheckpoint, segment_index: int) -> str:
    """从断点快照还原指定段正文，供按段输出 content_delta 事件。

    ``append_segment`` 以 ``\n\n`` 连接各段并用 ``char_count`` 记录每段长度，
    因此可以按“前序段累计长度 + 分隔符长度”精确定位任意一段，避免只切尾段时
    在各段等长的情况下串段。缺少 ``char_count`` 的旧快照回退到按分隔符切分。
    输出顺序由执行器串行驱动保证；恢复续跑时已完成段不会再次输出。
    """
    assembled = snapshot.assembled_text or ""
    if not assembled:
        return ""
    separator = "\n\n"
    records = [item for item in snapshot.completed_segments if isinstance(item, dict)]
    records.sort(key=lambda item: int(item.get("index", 0)))

    position = -1
    offset = 0
    counts_known = True
    for cursor, item in enumerate(records):
        char_count = int(item.get("char_count") or 0)
        if int(item.get("index", -1)) == segment_index:
            position = cursor
            if char_count <= 0:
                counts_known = False
            break
        if char_count <= 0:
            counts_known = False
            break
        offset += char_count + len(separator)

    if position >= 0 and counts_known:
        char_count = int(records[position].get("char_count") or 0)
        chunk = assembled[offset : offset + char_count]
        if chunk.strip():
            return chunk.strip()

    parts = assembled.split(separator)
    if position >= 0 and len(parts) == len(records):
        return parts[position].strip()
    return ""


def evaluate_segment_quality(
    content: str,
    *,
    target_word_count: int,
    min_word_count: int,
    prior_content: str = "",
    required_terms: Iterable[str] = (),
) -> QualityGateResult:
    """执行段级字数、重复和必要上下文锚点检查。"""
    text = str(content or "").strip()
    word_count = _measure_words(text)
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if not text:
        blockers.append({"code": "empty_segment", "message": "段落正文为空"})
    if word_count < max(0, int(min_word_count)):
        blockers.append(
            {
                "code": "segment_below_minimum",
                "message": f"段落字数 {word_count} 低于最低要求 {int(min_word_count)}",
            }
        )
    duplicate_ratio = _duplicate_sentence_ratio(text, prior_content)
    if _fingerprint(text) and _fingerprint(text) == _fingerprint(prior_content):
        blockers.append({"code": "duplicate_segment", "message": "段落与已有正文完全重复"})
    elif duplicate_ratio >= 0.5:
        blockers.append(
            {"code": "duplicate_content", "message": "段落与已有正文存在过高句子重复"}
        )
    elif duplicate_ratio >= 0.25:
        warnings.append({"code": "repeated_content_risk", "message": "段落与已有正文存在重复表达风险"})

    missing_terms = [term for term in required_terms if str(term).strip() and str(term).strip() not in text]
    if missing_terms:
        blockers.append(
            {"code": "required_anchor_missing", "message": "缺少本段必须保留的上下文锚点", "terms": missing_terms}
        )
    return QualityGateResult(
        passed=not blockers,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
        metrics={
            "word_count": word_count,
            "target_word_count": int(target_word_count),
            "min_word_count": int(min_word_count),
            "duplicate_sentence_ratio": round(duplicate_ratio, 4),
        },
    )


def evaluate_chapter_quality(
    plan: LongformGenerationPlan,
    content: str,
    *,
    required_terms: Iterable[str] = (),
) -> QualityGateResult:
    """执行定稿级最低字数、重复和章节锚点检查。"""
    text = str(content or "").strip()
    word_count = _measure_words(text)
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if word_count < plan.min_word_count:
        blockers.append(
            {
                "code": "chapter_below_minimum",
                "message": f"章节字数 {word_count} 低于最低要求 {plan.min_word_count}",
            }
        )
    duplicate_ratio = _duplicate_sentence_ratio(text)
    if duplicate_ratio >= 0.35:
        blockers.append({"code": "chapter_duplicate_content", "message": "章节内部重复表达过高"})
    elif duplicate_ratio >= 0.2:
        warnings.append({"code": "chapter_repetition_risk", "message": "章节内部存在重复表达风险"})
    missing_terms = [term for term in required_terms if str(term).strip() and str(term).strip() not in text]
    if missing_terms:
        blockers.append({"code": "chapter_anchor_missing", "message": "章节缺少必要连续性锚点", "terms": missing_terms})
    return QualityGateResult(
        passed=not blockers,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
        metrics={
            "word_count": word_count,
            "target_word_count": plan.target_word_count,
            "min_word_count": plan.min_word_count,
            "segment_count": len(plan.segments),
            "duplicate_sentence_ratio": round(duplicate_ratio, 4),
        },
    )


def _split_budget(total: int, count: int) -> list[int]:
    base, remainder = divmod(max(0, int(total)), max(1, int(count)))
    return [base + (1 if index < remainder else 0) for index in range(count)]


def _build_book_context(blueprint: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "title": blueprint.get("title") or blueprint.get("book_title") or "",
        "world_setting": blueprint.get("world_setting") or blueprint.get("world") or {},
        "novel_outline": blueprint.get("novel_outline") or blueprint.get("outline") or [],
        "long_term_threads": blueprint.get("long_term_threads") or blueprint.get("story_arcs") or [],
    }


def _build_volume_context(volume: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "title": volume.get("title") or volume.get("name") or "",
        "summary": volume.get("summary") or volume.get("description") or "",
        "chapter_range": volume.get("chapter_range") or volume.get("expected_chapter_range") or "",
        "plot_arc": volume.get("plot_arc") or volume.get("arc") or "",
        "threads": volume.get("threads") or volume.get("subplots") or [],
    }


def _select_volume(blueprint: Mapping[str, Any], chapter_number: int) -> dict[str, Any]:
    candidates = blueprint.get("volume_plan") or blueprint.get("volumes") or []
    if not isinstance(candidates, list):
        return {}
    for item in candidates:
        if not isinstance(item, Mapping):
            continue
        if _chapter_in_range(chapter_number, item.get("chapter_range") or item.get("expected_chapter_range")):
            return dict(item)
    return dict(candidates[0]) if candidates and isinstance(candidates[0], Mapping) else {}


def _chapter_in_range(chapter_number: int, value: Any) -> bool:
    match = re.search(r"(\d+)\s*[-~至到]\s*(\d+)", str(value or ""))
    return bool(match and int(match.group(1)) <= chapter_number <= int(match.group(2)))


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    return [value]


def _measure_words(text: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9]+", str(text or "")))


def _sentences(text: str) -> list[str]:
    return [item for item in re.split(r"[。！？!?；;\n]+", str(text or "")) if item.strip()]


def _normalize_sentence(value: str) -> str:
    return re.sub(r"\s+", "", value).strip().lower()


def _duplicate_sentence_ratio(text: str, prior_content: str = "") -> float:
    current = [_normalize_sentence(item) for item in _sentences(text)]
    current = [item for item in current if item]
    if not current:
        return 0.0
    if prior_content:
        previous = {_normalize_sentence(item) for item in _sentences(prior_content)}
        previous.discard("")
        return sum(item in previous for item in current) / len(current)
    counts: dict[str, int] = {}
    for item in current:
        counts[item] = counts.get(item, 0) + 1
    repeated = sum(count - 1 for count in counts.values() if count > 1)
    return repeated / len(current)


def _fingerprint(value: str) -> str:
    normalized = re.sub(r"\s+", "", str(value or "")).strip().lower()
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest() if normalized else ""


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


__all__ = [
    "LongformCheckpoint",
    "LongformGenerationCancelled",
    "LongformGenerationContractError",
    "LongformGenerationPlan",
    "QualityGateResult",
    "SegmentBudget",
    "append_segment",
    "build_longform_generation_plan",
    "execute_longform_segments",
    "evaluate_chapter_quality",
    "evaluate_segment_quality",
    "extract_segment_text",
    "restore_longform_generation_plan",
    "start_longform_checkpoint",
]
