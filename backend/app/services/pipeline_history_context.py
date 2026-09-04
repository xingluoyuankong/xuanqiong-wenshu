# AIMETA P=pipeline_history_context_mixin|R=history_summary_continuity_injection|NR=generation_side_effects|E=PipelineHistoryContextMixin|X=internal|A=mixin|D=none|S=none|RD=./README.ai
"""History continuity helpers extracted from PipelineOrchestrator.

Behavior-preserving mixin: method names/signatures stay the same so existing
call sites and tests continue to use PipelineOrchestrator.* unchanged.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..models.novel import Chapter
from ..utils.chapter_summary_utils import extract_chapter_narrative_summary


class PipelineHistoryContextMixin:
    """Chapter history collection and continuity injection helpers."""

    async def _collect_history_context(
        self,
        *,
        project_id: str,
        chapter_number: int,
        outlines_map: Dict[int, Any],
        chapters: List[Chapter],
        user_id: int,
    ) -> Dict[str, Any]:
        chapter_fingerprint = ",".join(
            f"{item.chapter_number}:{getattr(item, 'updated_at', None) or ''}:{getattr(item, 'selected_version_id', None) or ''}"
            for item in sorted(chapters, key=lambda value: value.chapter_number)
            if item.chapter_number < chapter_number
        )
        cache_key = self._make_cache_key("history", project_id, chapter_number, chapter_fingerprint)
        cached = await self._cache_get(cache_key)
        if isinstance(cached, dict) and cached:
            return cached

        completed_summaries = []
        completed_chapters = []
        latest_prev_number = -1
        previous_summary_text = ""
        previous_tail_excerpt = ""
        previous_chapter_bundle: Dict[str, Any] = {}

        # Prefer finalized ChapterSnapshot.chapter_summary when real_summary only holds runtime JSON.
        prior_numbers = [
            int(item.chapter_number)
            for item in chapters
            if int(getattr(item, "chapter_number", 0) or 0) < int(chapter_number)
        ]
        snapshot_summaries = await self._load_snapshot_chapter_summaries(project_id, prior_numbers)

        for existing in chapters:
            if existing.chapter_number >= chapter_number:
                continue
            if existing.selected_version is None or not existing.selected_version.content:
                continue

            outline_ref = outlines_map.get(existing.chapter_number)
            outline_summary = (getattr(outline_ref, "summary", None) or "").strip() if outline_ref else ""
            snap = snapshot_summaries.get(int(existing.chapter_number)) or {}
            snapshot_summary = snap.get("summary") if isinstance(snap, dict) else None
            overview_summary = snap.get("overview") if isinstance(snap, dict) else None
            summary_text = extract_chapter_narrative_summary(
                existing,
                outline_summary=outline_summary,
                content=existing.selected_version.content,
                snapshot_summary=snapshot_summary,
                overview_summary=overview_summary,
                truncate=420,
            )
            if not summary_text:
                summary_text = self._truncate_text(existing.selected_version.content, 220)

            completed_chapters.append(
                {
                    "chapter_number": existing.chapter_number,
                    "title": outlines_map.get(existing.chapter_number).title
                    if outlines_map.get(existing.chapter_number)
                    else f"第{existing.chapter_number}章",
                    "summary": summary_text,
                }
            )
            completed_summaries.append(summary_text)

            if existing.chapter_number > latest_prev_number:
                latest_prev_number = existing.chapter_number
                previous_summary_text = summary_text
                previous_tail_excerpt = self._extract_tail_excerpt(existing.selected_version.content)
                previous_chapter_bundle = {
                    "chapter_number": existing.chapter_number,
                    "title": outlines_map.get(existing.chapter_number).title
                    if outlines_map.get(existing.chapter_number)
                    else f"第{existing.chapter_number}章",
                    "summary": summary_text,
                    "tail_excerpt": previous_tail_excerpt,
                    "content_excerpt": self._truncate_text(existing.selected_version.content, 2500),
                }

        project_memory_text = await self._get_project_memory_text(project_id)
        recent_track = self._build_recent_chapter_track(completed_chapters)
        plot_arcs = None
        if project_memory_text and "### 剧情线追踪" in project_memory_text:
            try:
                plot_arcs_text = project_memory_text.split("### 剧情线追踪", 1)[1].strip()
                plot_arcs = json.loads(plot_arcs_text)
            except Exception:
                plot_arcs = None

        payload = {
            "completed_chapters": completed_chapters,
            "completed_summaries": completed_summaries,
            "previous_summary": previous_summary_text or "暂无（这是第一章）",
            "previous_tail": previous_tail_excerpt or "暂无（这是第一章）",
            "previous_chapter_bundle": previous_chapter_bundle or {
                "chapter_number": chapter_number - 1 if chapter_number > 1 else 0,
                "title": "暂无（这是第一章）",
                "summary": previous_summary_text or "暂无（这是第一章）",
                "tail_excerpt": previous_tail_excerpt or "暂无（这是第一章）",
                "content_excerpt": "暂无（这是第一章）",
            },
            "recent_track": recent_track,
            "plot_arc_digest": self._format_plot_arc_digest(plot_arcs),
        }
        await self._cache_set(cache_key, payload, expire=300)
        return payload


    async def _load_snapshot_chapter_summaries(
        self,
        project_id: str,
        chapter_numbers: List[int],
    ) -> Dict[int, Any]:
        """Load narrative summaries from ChapterSnapshot for continuity history.

        Bare unit-test orchestrator instances may lack a DB session; fail open.
        """
        numbers = sorted({int(n) for n in (chapter_numbers or []) if int(n) > 0})
        if not numbers:
            return {}
        session = getattr(self, "session", None)
        if session is None:
            return {}
        try:
            from sqlalchemy import select
            from ..models.project_memory import ChapterSnapshot

            rows = (
                await session.execute(
                    select(
                        ChapterSnapshot.chapter_number,
                        ChapterSnapshot.chapter_summary,
                        ChapterSnapshot.extra,
                    ).where(
                        ChapterSnapshot.project_id == project_id,
                        ChapterSnapshot.chapter_number.in_(numbers),
                    )
                )
            ).all()
        except Exception:
            return {}

        out: Dict[int, Any] = {}
        for chapter_no, summary, extra in rows:
            summary_text = str(summary or "").strip()
            overview = None
            if isinstance(extra, dict):
                overview_blob = extra.get("chapter_overview")
                if isinstance(overview_blob, dict):
                    overview = str(overview_blob.get("chapter_summary") or "").strip() or None
            if not summary_text and not overview:
                continue
            out[int(chapter_no)] = {
                "summary": summary_text or None,
                "overview": overview,
            }
        return out

    @staticmethod
    def _extract_tail_excerpt(text: Optional[str], limit: int = 500) -> str:
        if not text:
            return ""
        stripped = text.strip()
        if len(stripped) <= limit:
            return stripped
        return stripped[-limit:]

    @staticmethod
    def _truncate_text(text: Optional[str], limit: int = 220) -> str:
        if not text:
            return ""
        cleaned = str(text).strip()
        if len(cleaned) <= limit:
            return cleaned
        return f"{cleaned[:limit].rstrip()}..."

    @classmethod
    def _build_recent_chapter_track(cls, completed_chapters: List[Dict[str, Any]], *, max_items: int = 12) -> str:
        if not completed_chapters:
            return "暂无历史章节（这是第一章）"
        ordered = sorted(completed_chapters, key=lambda item: int(item.get("chapter_number") or 0))
        recent = ordered[-max_items:]
        lines: List[str] = []
        for item in recent:
            chapter_no = int(item.get("chapter_number") or 0)
            title = str(item.get("title") or "").strip() or f"第{chapter_no}章"
            summary = cls._truncate_text(item.get("summary"), 180)
            lines.append(f"- 第{chapter_no}章《{title}》：{summary}")
        return "\n".join(lines)

    @staticmethod
    def _format_plot_arc_digest(plot_arcs: Optional[Dict[str, Any]], *, max_items: int = 5) -> str:
        if not isinstance(plot_arcs, dict) or not plot_arcs:
            return "暂无未闭环剧情线"
        lines: List[str] = []
        unresolved_hooks = plot_arcs.get("unresolved_hooks") or []
        if isinstance(unresolved_hooks, list):
            for item in unresolved_hooks[:max_items]:
                if isinstance(item, dict):
                    desc = str(item.get("description") or item.get("content") or "").strip()
                    if desc:
                        lines.append(f"- 未闭环钩子：{desc}")
        active_conflicts = plot_arcs.get("active_conflicts") or []
        if isinstance(active_conflicts, list):
            for item in active_conflicts[:max_items]:
                if isinstance(item, dict):
                    desc = str(item.get("description") or item.get("conflict") or "").strip()
                    if desc:
                        lines.append(f"- 进行中冲突：{desc}")
        if not lines:
            return "暂无未闭环剧情线"
        return "\n".join(lines[:max_items])

    @classmethod
    def _build_continuity_retrieval_injection(cls, history_context: Optional[Dict[str, Any]]) -> str:
        history = history_context or {}
        previous_bundle = history.get("previous_chapter_bundle") if isinstance(history.get("previous_chapter_bundle"), dict) else {}
        previous_tail = str(history.get("previous_tail") or previous_bundle.get("tail_excerpt") or "").strip()
        previous_summary = str(history.get("previous_summary") or previous_bundle.get("summary") or "").strip()
        plot_arc_digest = str(history.get("plot_arc_digest") or "").strip()
        recent_track = str(history.get("recent_track") or "").strip()

        lines: List[str] = []
        if previous_summary:
            lines.append("## 上一章摘要（强制承接）\n" + previous_summary)
        if previous_tail:
            lines.append("## 上一章结尾原文尾巴（开篇必须接住）\n" + cls._truncate_text(previous_tail, 700))
        if plot_arc_digest and "暂无" not in plot_arc_digest and "鏆傛棤" not in plot_arc_digest:
            lines.append("## 未闭环钩子/长线压力（本章至少推进一项）\n" + plot_arc_digest)
        if recent_track:
            lines.append("## 近期章节轨迹（避免断层）\n" + recent_track)
        return "\n\n".join(lines)

    @classmethod
    def _inject_continuity_into_rag(
        cls,
        rag_context: Optional[Dict[str, Any]],
        history_context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        context = dict(rag_context or {"chunks": [], "summaries": []})
        injection = cls._build_continuity_retrieval_injection(history_context)
        if not injection:
            return context
        chunks = list(context.get("chunks") or [])
        summaries = list(context.get("summaries") or [])
        chunks.insert(0, injection)
        summaries.insert(0, "强制连续性上下文：上一章尾巴、近期轨迹与未闭环钩子已注入，正文必须承接并递压。")
        context["chunks"] = chunks
        context["summaries"] = summaries
        context["continuity_injection"] = True
        return context

