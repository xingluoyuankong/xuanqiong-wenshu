from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping


class PlanHierarchyError(ValueError):
    """Raised when the compatibility plan hierarchy is structurally invalid."""


@dataclass(frozen=True)
class ScenePlanDraft:
    scene_id: str
    order: int
    title: str
    goal: str
    conflict: str
    turn: str
    outcome: str
    target_text_units: int | None = None
    source: str = "inferred"


@dataclass(frozen=True)
class ChapterPlanDraft:
    chapter_id: str
    chapter_number: int
    title: str
    volume_number: int | None
    volume_title: str | None
    summary: str
    target_text_units: int | None
    continuity_in: tuple[str, ...] = ()
    continuity_out: tuple[str, ...] = ()
    key_events: tuple[str, ...] = ()
    character_focus: tuple[str, ...] = ()
    scene_plans: tuple[ScenePlanDraft, ...] = ()
    source: str = "chapter_outline"


@dataclass(frozen=True)
class VolumePlanDraft:
    volume_id: str
    volume_number: int
    title: str
    start_chapter: int | None
    end_chapter: int | None
    chapter_numbers: tuple[int, ...]
    target_text_units: int | None
    purpose: str
    source: str
    chapter_plan_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class BookPlanDraft:
    plan_id: str
    project_id: str
    title: str
    genre: str | None
    style: str | None
    tone: str | None
    synopsis: str
    target_text_units: int
    volume_plan_ids: tuple[str, ...]
    source: str = "novel_blueprint_compat"


@dataclass(frozen=True)
class PlanHierarchy:
    book: BookPlanDraft
    volumes: tuple[VolumePlanDraft, ...]
    chapters: tuple[ChapterPlanDraft, ...]
    diagnostics: tuple[dict[str, Any], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "book": asdict(self.book),
            "volumes": [asdict(item) for item in self.volumes],
            "chapters": [asdict(item) for item in self.chapters],
            "diagnostics": list(self.diagnostics),
        }

    @property
    def content_digest(self) -> str:
        body = json.dumps(self.as_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(exclude_none=True)
        return dict(dumped) if isinstance(dumped, Mapping) else {}
    return {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _tuple_strings(value: Any) -> tuple[str, ...]:
    return tuple(str(item).strip() for item in _list(value) if str(item).strip())


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None and str(value).strip() else None
    except (TypeError, ValueError):
        return None


def parse_chapter_range(value: Any) -> tuple[int | None, int | None]:
    if isinstance(value, Mapping):
        start = value.get("start") or value.get("start_chapter")
        end = value.get("end") or value.get("end_chapter")
        return _int_or_none(start), _int_or_none(end)
    numbers = [int(item) for item in re.findall(r"\d+", str(value or ""))]
    if len(numbers) >= 2:
        return numbers[0], numbers[1]
    if len(numbers) == 1:
        return numbers[0], numbers[0]
    return None, None


def _outline_items(world_setting: Mapping[str, Any]) -> list[dict[str, Any]]:
    values = world_setting.get("novel_outline") or world_setting.get("stages") or []
    return [dict(item) for item in values if isinstance(item, Mapping)]


def _explicit_volume_items(world_setting: Mapping[str, Any]) -> list[dict[str, Any]]:
    values = world_setting.get("volume_plan") or world_setting.get("volumes") or []
    return [dict(item) for item in values if isinstance(item, Mapping)]


def _make_scene_plans(metadata: Mapping[str, Any], chapter_number: int) -> tuple[ScenePlanDraft, ...]:
    scenes = metadata.get("scene_list") or metadata.get("scenes") or []
    result: list[ScenePlanDraft] = []
    for index, item in enumerate(_list(scenes)):
        data = _mapping(item)
        result.append(
            ScenePlanDraft(
                scene_id=f"chapter-{chapter_number}-scene-{index + 1}",
                order=index + 1,
                title=str(data.get("title") or data.get("scene") or f"第{chapter_number}章场景{index + 1}"),
                goal=str(data.get("goal") or ""),
                conflict=str(data.get("conflict") or ""),
                turn=str(data.get("turn") or ""),
                outcome=str(data.get("outcome") or ""),
                target_text_units=_int_or_none(data.get("word_budget") or data.get("target_text_units")),
                source="chapter_outline.metadata",
            )
        )
    if result:
        return tuple(result)
    events = _tuple_strings(metadata.get("key_events"))
    return tuple(
        ScenePlanDraft(
            scene_id=f"chapter-{chapter_number}-scene-{index + 1}",
            order=index + 1,
            title=f"第{chapter_number}章事件{index + 1}",
            goal=event,
            conflict="",
            turn="",
            outcome="",
            source="chapter_outline.metadata.key_events",
        )
        for index, event in enumerate(events)
    )


def build_plan_hierarchy(project: Any, *, target_text_units: int = 100_000, plan_id: str = "NOVEL_100K_OPT_V1") -> PlanHierarchy:
    blueprint = getattr(project, "blueprint", None)
    world_setting = _mapping(getattr(blueprint, "world_setting", None))
    outline_items = _outline_items(world_setting)
    explicit_volumes = _explicit_volume_items(world_setting)
    chapter_rows = sorted(getattr(project, "outlines", None) or [], key=lambda item: (int(item.chapter_number), int(getattr(item, "id", 0) or 0)))
    chapters: list[ChapterPlanDraft] = []
    for outline in chapter_rows:
        metadata = _mapping(getattr(outline, "metadata", None))
        volume_number = _int_or_none(metadata.get("volume_number"))
        volume_title = str(metadata.get("volume_title") or "").strip() or None
        summary = str(getattr(outline, "summary", None) or "").strip()
        chapters.append(
            ChapterPlanDraft(
                chapter_id=f"chapter-{outline.chapter_number}",
                chapter_number=int(outline.chapter_number),
                title=str(getattr(outline, "title", None) or f"第{outline.chapter_number}章"),
                volume_number=volume_number,
                volume_title=volume_title,
                summary=summary,
                target_text_units=_int_or_none(metadata.get("word_count_estimate") or metadata.get("target_text_units")),
                continuity_in=_tuple_strings(metadata.get("continuity_in") or metadata.get("previous_tail")),
                continuity_out=_tuple_strings(metadata.get("continuity_out") or metadata.get("bridge")),
                key_events=_tuple_strings(metadata.get("key_events")),
                character_focus=_tuple_strings(metadata.get("character_focus")),
                scene_plans=_make_scene_plans(metadata, int(outline.chapter_number)),
            )
        )

    volume_rows: list[tuple[int, str, int | None, int | None, str]] = []
    by_metadata: dict[int, list[ChapterPlanDraft]] = {}
    for chapter in chapters:
        if chapter.volume_number is not None:
            by_metadata.setdefault(chapter.volume_number, []).append(chapter)
    metadata_covered = sum(len(items) for items in by_metadata.values())
    outline_covered = 0
    for item in outline_items:
        start, end = parse_chapter_range(item.get("expected_chapter_range") or item.get("chapter_range"))
        if start is not None and end is not None:
            outline_covered += sum(1 for chapter in chapters if start <= chapter.chapter_number <= end)

    if explicit_volumes:
        for index, item in enumerate(explicit_volumes, start=1):
            start, end = parse_chapter_range(item.get("chapter_range") or item)
            volume_rows.append((index, str(item.get("title") or item.get("name") or f"第{index}卷"), start, end, "blueprint.volume_plan"))
    elif metadata_covered >= outline_covered and by_metadata:
        for index, members in sorted(by_metadata.items()):
            volume_rows.append((index, members[0].volume_title or f"第{index}卷", min(item.chapter_number for item in members), max(item.chapter_number for item in members), "chapter_outline.metadata"))
    elif outline_items:
        for index, item in enumerate(outline_items, start=1):
            start, end = parse_chapter_range(item.get("expected_chapter_range") or item.get("chapter_range"))
            volume_rows.append((index, str(item.get("title") or f"第{index}卷"), start, end, "blueprint.novel_outline"))
    else:
        for index, members in sorted(by_metadata.items()):
            volume_rows.append((index, members[0].volume_title or f"第{index}卷", min(item.chapter_number for item in members), max(item.chapter_number for item in members), "chapter_outline.metadata"))

    volumes: list[VolumePlanDraft] = []
    diagnostics: list[dict[str, Any]] = []
    outline_by_number = {item.get("stage"): item for item in outline_items if item.get("stage") is not None}
    for index, title, start, end, source in volume_rows:
        members = [chapter for chapter in chapters if start is not None and end is not None and start <= chapter.chapter_number <= end]
        if start is None or end is None:
            members = [chapter for chapter in chapters if chapter.volume_number == index]
            if members:
                start, end = min(item.chapter_number for item in members), max(item.chapter_number for item in members)
        if not members and start is not None and end is not None:
            diagnostics.append({"code": "volume_without_outline_members", "volume_number": index, "start_chapter": start, "end_chapter": end})
        source_item = outline_by_number.get(index) or {}
        purpose = str(source_item.get("goal") or source_item.get("core_theme") or "").strip()
        estimated = sum(item.target_text_units or 0 for item in members) or None
        volumes.append(
            VolumePlanDraft(
                volume_id=f"volume-{index}",
                volume_number=index,
                title=title,
                start_chapter=start,
                end_chapter=end,
                chapter_numbers=tuple(item.chapter_number for item in members),
                target_text_units=estimated,
                purpose=purpose,
                source=source,
                chapter_plan_ids=tuple(item.chapter_id for item in members),
            )
        )
    if not explicit_volumes and metadata_covered >= outline_covered and by_metadata:
        diagnostics.append({"code": "volume_plan_derived_from_chapter_metadata", "source": "chapter_outline.metadata", "metadata_covered": metadata_covered, "outline_covered": outline_covered})
    elif not explicit_volumes and outline_items:
        diagnostics.append({"code": "volume_plan_derived_from_novel_outline", "source": "blueprint.novel_outline"})
    if metadata_covered < len(chapters):
        diagnostics.append({"code": "chapters_without_volume_metadata", "count": len(chapters) - metadata_covered, "chapter_numbers": [chapter.chapter_number for chapter in chapters if chapter.volume_number is None]})
    if outline_items and outline_covered < len(chapters):
        diagnostics.append({"code": "novel_outline_ranges_do_not_cover_all_chapters", "outline_covered": outline_covered, "chapter_count": len(chapters)})
    if not volumes:
        diagnostics.append({"code": "volume_mapping_unavailable", "reason": "no explicit volume plan, novel outline ranges, or chapter volume metadata"})
    if len({chapter.chapter_number for chapter in chapters}) != len(chapters):
        diagnostics.append({"code": "duplicate_chapter_number"})
    for volume in volumes:
        if volume.start_chapter is not None and volume.end_chapter is not None and volume.start_chapter > volume.end_chapter:
            diagnostics.append({"code": "invalid_volume_range", "volume_number": volume.volume_number})
    book = BookPlanDraft(
        plan_id=plan_id,
        project_id=str(project.id),
        title=str(getattr(blueprint, "title", None) or getattr(project, "title", None) or ""),
        genre=str(getattr(blueprint, "genre", None) or "").strip() or None,
        style=str(getattr(blueprint, "style", None) or "").strip() or None,
        tone=str(getattr(blueprint, "tone", None) or "").strip() or None,
        synopsis=str(getattr(blueprint, "full_synopsis", None) or getattr(blueprint, "one_sentence_summary", None) or "").strip(),
        target_text_units=target_text_units,
        volume_plan_ids=tuple(item.volume_id for item in volumes),
    )
    hierarchy = PlanHierarchy(book=book, volumes=tuple(volumes), chapters=tuple(chapters), diagnostics=tuple(diagnostics))
    validate_plan_hierarchy(hierarchy)
    return hierarchy


def validate_plan_hierarchy(hierarchy: PlanHierarchy) -> None:
    if not hierarchy.book.project_id:
        raise PlanHierarchyError("book project_id is required")
    chapter_numbers = [item.chapter_number for item in hierarchy.chapters]
    if len(chapter_numbers) != len(set(chapter_numbers)):
        raise PlanHierarchyError("chapter numbers must be unique")
    volume_numbers = [item.volume_number for item in hierarchy.volumes]
    if len(volume_numbers) != len(set(volume_numbers)):
        raise PlanHierarchyError("volume numbers must be unique")
    for volume in hierarchy.volumes:
        if volume.start_chapter is not None and volume.end_chapter is not None and volume.start_chapter > volume.end_chapter:
            raise PlanHierarchyError("volume chapter range is reversed")
        if len(volume.chapter_numbers) != len(set(volume.chapter_numbers)):
            raise PlanHierarchyError("volume chapter numbers must be unique")
    for chapter in hierarchy.chapters:
        orders = [scene.order for scene in chapter.scene_plans]
        if len(orders) != len(set(orders)):
            raise PlanHierarchyError("scene orders must be unique")
        if orders and orders != list(range(1, len(orders) + 1)):
            raise PlanHierarchyError("scene orders must be contiguous")
