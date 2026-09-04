"""Small continuity guards shared by local rewrite/expansion stages.

The helpers in this file deliberately stay business-agnostic. They do not
orchestrate generation; they only check whether a proposed patch lost story
signals that were already present in the source text.
"""
from __future__ import annotations

import math
import re
from typing import Any, Dict, Iterable, List, Optional


_CONTEXT_SIGNAL_KEYS = {
    "chapter_mission",
    "continuity_anchor",
    "foreshadowing",
    "foreshadowing_tasks",
    "foreshadowing_task",
    "cast_delta",
    "character_focus",
    "character_state",
    "character_profiles",
    "previous_tail",
    "previous_chapter_bundle",
    "recent_track",
    "plot_arc_digest",
    "project_memory",
    "longform_context",
    "memory_digest",
    "timeline_digest",
    "knowledge_digest",
    "causal_chains",
}

_STOP_TOKENS = {
    "chapter",
    "current",
    "previous",
    "mission",
    "scene",
    "goal",
    "conflict",
    "turn",
    "bridge",
    "payoff",
    "must",
    "should",
    "avoid",
    "none",
    "unknown",
    "本章",
    "章节",
    "当前",
    "上一章",
    "下一章",
    "目标",
    "冲突",
    "转折",
    "承接",
    "伏笔",
    "角色",
    "任务",
    "必须",
    "需要",
    "不能",
    "保持",
    "继续",
}


def _iter_signal_values(value: Any, *, depth: int = 0) -> Iterable[str]:
    if value is None or depth > 5:
        return
    if isinstance(value, str):
        text = value.strip()
        if text:
            yield text
        return
    if isinstance(value, (int, float, bool)):
        yield str(value)
        return
    if isinstance(value, dict):
        for nested in value.values():
            yield from _iter_signal_values(nested, depth=depth + 1)
        return
    if isinstance(value, list):
        for item in value[:80]:
            yield from _iter_signal_values(item, depth=depth + 1)


def _add_token(tokens: List[str], seen: set[str], token: str) -> None:
    cleaned = re.sub(r"\s+", " ", str(token or "")).strip(" \t\r\n,.;:!?()[]{}<>\"'")
    if not cleaned:
        return
    normalized = cleaned.lower()
    compact = re.sub(r"\s+", "", normalized)
    if len(compact) < 2 or len(compact) > 32 or normalized in _STOP_TOKENS:
        return
    if compact in _STOP_TOKENS or compact in seen:
        return
    seen.add(compact)
    tokens.append(cleaned)


def extract_continuity_tokens(value: Any, *, limit: int = 24) -> List[str]:
    """Extract compact story terms from mission/context values."""

    tokens: List[str] = []
    seen: set[str] = set()
    for text in _iter_signal_values(value):
        text = text.strip()
        if not text:
            continue
        if 2 <= len(text) <= 48:
            _add_token(tokens, seen, text)

        parts = [part.strip() for part in re.split(r"[\s,.;:!?/|，。；、！？：（）()\[\]{}《》“”\"']+", text) if part.strip()]
        for part in parts:
            if 2 <= len(part) <= 24:
                _add_token(tokens, seen, part)

        for first, second in zip(parts, parts[1:]):
            phrase = f"{first} {second}"
            if 5 <= len(phrase) <= 32:
                _add_token(tokens, seen, phrase)

        for match in re.finditer(r"[\u4e00-\u9fff]{2,16}", text):
            cjk = match.group(0)
            _add_token(tokens, seen, cjk)
            if len(cjk) > 6:
                _add_token(tokens, seen, cjk[:6])
                _add_token(tokens, seen, cjk[-6:])

        for match in re.finditer(r"\b[A-Za-z][A-Za-z0-9_-]{2,}\b", text):
            _add_token(tokens, seen, match.group(0))

        if len(tokens) >= limit:
            break
    return tokens[:limit]


def collect_continuity_terms(
    *,
    chapter_mission: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None,
    extra_sources: Optional[Iterable[Any]] = None,
    limit: int = 36,
) -> List[str]:
    sources: List[Any] = []
    if isinstance(chapter_mission, dict):
        sources.append(chapter_mission)
    if isinstance(context, dict):
        for key in _CONTEXT_SIGNAL_KEYS:
            if key in context:
                sources.append(context.get(key))
    if extra_sources:
        sources.extend(extra_sources)

    terms: List[str] = []
    seen: set[str] = set()
    for source in sources:
        for token in extract_continuity_tokens(source, limit=limit):
            compact = re.sub(r"\s+", "", token.lower())
            if compact and compact not in seen:
                seen.add(compact)
                terms.append(token)
            if len(terms) >= limit:
                return terms
    return terms


def _contains_term(text: str, term: str) -> bool:
    source = str(text or "").lower()
    token = str(term or "").lower().strip()
    if not token:
        return False
    if token in source:
        return True
    return re.sub(r"\s+", "", token) in re.sub(r"\s+", "", source)


def continuity_terms_guard_failure(
    *,
    original: str,
    candidate: str,
    chapter_mission: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None,
    extra_sources: Optional[Iterable[Any]] = None,
    reason_code: str = "lost_continuity_terms",
    min_required_terms: int = 2,
    keep_ratio: float = 0.5,
) -> Optional[str]:
    """Return a failure reason when a patch drops too many required signals.

    Only terms that already appear in the original text become mandatory. This
    keeps the guard from forcing every mission note into a small local patch.
    """

    terms = collect_continuity_terms(
        chapter_mission=chapter_mission,
        context=context,
        extra_sources=extra_sources,
    )
    required: List[str] = []
    seen: set[str] = set()
    for term in terms:
        key = re.sub(r"\s+", "", term.lower())
        if key in seen:
            continue
        if _contains_term(original, term):
            seen.add(key)
            required.append(term)
        if len(required) >= 18:
            break

    if len(required) < min_required_terms:
        return None

    kept = [term for term in required if _contains_term(candidate, term)]
    required_kept = max(1, math.ceil(len(required) * max(0.1, min(1.0, keep_ratio))))
    if len(kept) < required_kept:
        return f"{reason_code}:{len(kept)}/{len(required)}"
    return None
