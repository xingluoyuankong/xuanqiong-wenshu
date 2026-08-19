# AIMETA P=长篇上下文服务_写前包与连续性门禁|R=记忆_角色_伏笔_线索_时间线_质量门|NR=不编排LLM|E=LongformContextService|X=internal|A=service|D=sqlalchemy|S=db|RD=./README.ai
from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.clue_tracker import StoryClue
from ..models.faction import Faction, FactionMember, FactionRelationship
from ..models.foreshadowing import Foreshadowing
from ..models.knowledge_graph import CharacterNode, EventEdge
from ..models.memory_layer import CausalChain, CharacterState, StoryTimeTracker, TimelineEvent
from ..models.novel import BlueprintCharacter, BlueprintRelationship, Chapter, ChapterOutline, NovelProject
from ..models.project_memory import ChapterSnapshot, ProjectMemory
from .novel_service import _infer_total_chapters_for_cast

logger = logging.getLogger(__name__)

ACTIVE_FORESHADOWING_STATUSES = {"open", "planted", "developing", "partial"}
ACTIVE_CLUE_STATUSES = {"active", "open", "planted", "developing"}


@dataclass
class CastPlan:
    target_character_count: int
    planned_character_count: int
    tiers: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    chapter_focus_names: List[str] = field(default_factory=list)
    active_character_states: List[Dict[str, Any]] = field(default_factory=list)
    faction_assignments: List[Dict[str, Any]] = field(default_factory=list)
    relationship_edges: List[Dict[str, Any]] = field(default_factory=list)
    dynamic_slots: List[Dict[str, Any]] = field(default_factory=list)
    rules: List[str] = field(default_factory=list)


@dataclass
class ForeshadowingChapterTask:
    must_resolve: List[Dict[str, Any]] = field(default_factory=list)
    should_reinforce: List[Dict[str, Any]] = field(default_factory=list)
    may_plant: List[Dict[str, Any]] = field(default_factory=list)
    avoid_forgetting: List[Dict[str, Any]] = field(default_factory=list)
    overdue_risks: List[Dict[str, Any]] = field(default_factory=list)
    active_clues: List[Dict[str, Any]] = field(default_factory=list)
    rules: List[str] = field(default_factory=list)


@dataclass
class ContinuityQualityGate:
    passed: bool
    blockers: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    patch_suggestions: List[Dict[str, Any]] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LongformContextPackage:
    project_id: str
    chapter_number: int
    prompt_text: str
    cast_plan: CastPlan
    foreshadowing_task: ForeshadowingChapterTask
    memory_digest: Dict[str, Any] = field(default_factory=dict)
    timeline_digest: Dict[str, Any] = field(default_factory=dict)
    knowledge_digest: Dict[str, Any] = field(default_factory=dict)

    def to_metadata(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload.pop("prompt_text", None)
        return payload

    def to_optimizer_payload(self, *, max_prompt_chars: int = 4200) -> Dict[str, Any]:
        return {
            "chapter_number": self.chapter_number,
            "prompt_digest": _truncate_text(self.prompt_text, max_prompt_chars),
            "cast_plan": asdict(self.cast_plan),
            "foreshadowing_task": asdict(self.foreshadowing_task),
            "memory_digest": self.memory_digest,
            "timeline_digest": self.timeline_digest,
        }


def _truncate_text(value: Any, limit: int = 240) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def _compact_list(values: Any, *, limit: int = 8, item_limit: int = 140) -> List[str]:
    if not values:
        return []
    if isinstance(values, str):
        values = re.split(r"[、，,；;\n]+", values)
    if not isinstance(values, Iterable) or isinstance(values, (bytes, dict)):
        values = [values]
    result: List[str] = []
    seen: set[str] = set()
    for value in values:
        text = _truncate_text(value, item_limit)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def _signal_terms_from_text(value: Any, *, limit: int = 8) -> List[str]:
    text = str(value or "").strip()
    if not text:
        return []
    terms: List[str] = []
    seen: set[str] = set()

    def add(term: str) -> None:
        cleaned = term.strip().lower()
        if len(cleaned) < 2 or cleaned in seen:
            return
        seen.add(cleaned)
        terms.append(cleaned)

    for match in re.finditer(r"[\u4e00-\u9fff]{2,12}", text):
        token = match.group(0)
        add(token[:8])
        add(token[-8:])
    for part in re.split(r"[^A-Za-z0-9_-]+", text):
        word = part.strip().lower()
        if len(word) >= 4 and word not in {"chapter", "pressure", "effect", "cause", "pending"}:
            add(word)
    return terms[:limit]


def _content_has_any_signal(content: str, signals: Iterable[str]) -> bool:
    lowered = (content or "").lower()
    return any(signal and signal.lower() in lowered for signal in signals)


def _safe_extra(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _estimate_longform_cast_target(total_chapters: int) -> int:
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


def _cast_tier_for_index(index: int) -> str:
    if index == 0:
        return "protagonist"
    if index <= 3:
        return "core"
    if index <= 9:
        return "important_support"
    if index <= 17:
        return "stage_support"
    if index <= 29:
        return "faction_member"
    return "functional"


def _serialise_character(character: BlueprintCharacter, index: int) -> Dict[str, Any]:
    extra = _safe_extra(character.extra)
    tier = str(extra.get("cast_tier") or extra.get("role_rank") or extra.get("importance") or _cast_tier_for_index(index))
    return {
        "id": character.id,
        "name": character.name,
        "tier": tier,
        "identity": _truncate_text(character.identity, 120),
        "goals": _truncate_text(character.goals, 160),
        "relationship_to_protagonist": _truncate_text(character.relationship_to_protagonist, 160),
        "first_appearance_chapter": extra.get("first_appearance_chapter") or extra.get("first_highlight_chapter"),
        "exit_or_return_plan": _truncate_text(extra.get("exit_or_return_plan"), 140),
        "faction_role": _truncate_text(extra.get("faction_role"), 120),
        "knowledge_boundary": _truncate_text(extra.get("knowledge_boundary"), 160),
        "dynamic_role_policy": _truncate_text(extra.get("dynamic_role_policy"), 120),
    }


def _serialise_state(state: CharacterState) -> Dict[str, Any]:
    return {
        "character_name": state.character_name,
        "chapter_number": state.chapter_number,
        "location": _truncate_text(state.location, 100),
        "emotion": state.emotion,
        "health_status": state.health_status,
        "inventory": _compact_list(state.inventory, limit=5),
        "known_secrets": _compact_list(state.known_secrets, limit=5),
        "current_goals": _compact_list(state.current_goals, limit=5),
    }


def _serialise_foreshadowing(item: Foreshadowing, current_chapter: int) -> Dict[str, Any]:
    keywords = _compact_list(item.keywords, limit=6, item_limit=40)
    if item.name:
        keywords.insert(0, item.name)
    return {
        "id": item.id,
        "name": _truncate_text(item.name or item.content, 80),
        "content": _truncate_text(item.content, 180),
        "type": item.type,
        "status": item.status,
        "keywords": keywords[:8],
        "planted_chapter": item.chapter_number,
        "distance": max(0, current_chapter - int(item.chapter_number or current_chapter)),
        "target_reveal_chapter": item.target_reveal_chapter,
        "urgency": item.urgency,
        "importance": item.importance,
        "reveal_method": _truncate_text(item.reveal_method, 160),
        "reveal_impact": _truncate_text(item.reveal_impact, 160),
        "related_characters": _compact_list(item.related_characters, limit=5),
    }


def _serialise_clue(item: StoryClue, current_chapter: int) -> Dict[str, Any]:
    return {
        "id": item.id,
        "name": _truncate_text(item.name, 80),
        "description": _truncate_text(item.description or item.clue_content, 180),
        "status": item.status,
        "type": item.clue_type,
        "importance": item.importance,
        "planted_chapter": item.planted_chapter,
        "resolution_chapter": item.resolution_chapter,
        "distance": max(0, current_chapter - int(item.planted_chapter or current_chapter)),
    }


def _extract_outline_focus(outline: Optional[ChapterOutline], chapter_mission: Optional[Dict[str, Any]]) -> List[str]:
    focus: List[str] = []
    metadata = _safe_extra(getattr(outline, "metadata", None))
    for source in (
        metadata.get("character_focus"),
        metadata.get("characters"),
        (chapter_mission or {}).get("character_focus") if isinstance(chapter_mission, dict) else None,
        (chapter_mission or {}).get("key_characters") if isinstance(chapter_mission, dict) else None,
    ):
        focus.extend(_compact_list(source, limit=12, item_limit=32))
    if isinstance(chapter_mission, dict):
        for scene in chapter_mission.get("scene_list") or []:
            if isinstance(scene, dict):
                focus.extend(_compact_list(scene.get("characters") or scene.get("character_focus"), limit=6, item_limit=32))
    seen: set[str] = set()
    result: List[str] = []
    for name in focus:
        if name in seen:
            continue
        seen.add(name)
        result.append(name)
    return result[:12]


def _extract_outline_foreshadowing(outline: Optional[ChapterOutline], chapter_mission: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    metadata = _safe_extra(getattr(outline, "metadata", None))
    payloads = []
    for source_label, source in (
        ("outline", metadata.get("foreshadowing")),
        ("outline_tasks", metadata.get("foreshadowing_tasks")),
        ("mission", (chapter_mission or {}).get("foreshadowing") if isinstance(chapter_mission, dict) else None),
    ):
        if isinstance(source, dict):
            for key in ("plant", "setup", "hint", "payoff", "reinforce"):
                for item in _compact_list(source.get(key), limit=6, item_limit=120):
                    payloads.append({"source": source_label, "action": key, "content": item})
        elif isinstance(source, list):
            for item in source[:8]:
                payloads.append({"source": source_label, "action": "plan", "content": _truncate_text(item, 120)})
    return payloads[:10]


class LongformContextService:
    """Builds compact long-form context from existing project ledgers."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def build_context_package(
        self,
        *,
        project: NovelProject,
        outline: Optional[ChapterOutline],
        chapter_number: int,
        writing_notes: Optional[str] = None,
        chapter_mission: Optional[Dict[str, Any]] = None,
        allowed_new_characters: Optional[List[str]] = None,
    ) -> LongformContextPackage:
        project_id = project.id
        world_setting = getattr(getattr(project, "blueprint", None), "world_setting", None) or {}
        total_chapters = _infer_total_chapters_for_cast(
            chapter_outline=getattr(project, "outlines", []) or [],
            novel_outline=world_setting.get("novel_outline") if isinstance(world_setting, dict) else [],
            volume_plan=world_setting.get("volume_plan") if isinstance(world_setting, dict) else [],
            fallback=max(len(getattr(project, "outlines", []) or []), chapter_number),
        )

        memory_digest = await self._build_memory_digest(project_id, chapter_number)
        timeline_digest = await self._build_timeline_digest(project_id, chapter_number)
        knowledge_digest = await self._build_knowledge_digest(project_id, chapter_number)
        cast_plan = await self._build_cast_plan(
            project_id=project_id,
            total_chapters=total_chapters,
            chapter_number=chapter_number,
            outline=outline,
            chapter_mission=chapter_mission,
            allowed_new_characters=allowed_new_characters or [],
        )
        foreshadowing_task = await self._build_foreshadowing_task(
            project_id=project_id,
            chapter_number=chapter_number,
            outline=outline,
            chapter_mission=chapter_mission,
            cast_focus=cast_plan.chapter_focus_names,
        )
        prompt_text = self._format_prompt_text(
            chapter_number=chapter_number,
            writing_notes=writing_notes,
            memory_digest=memory_digest,
            timeline_digest=timeline_digest,
            knowledge_digest=knowledge_digest,
            cast_plan=cast_plan,
            foreshadowing_task=foreshadowing_task,
        )
        return LongformContextPackage(
            project_id=project_id,
            chapter_number=chapter_number,
            prompt_text=prompt_text,
            cast_plan=cast_plan,
            foreshadowing_task=foreshadowing_task,
            memory_digest=memory_digest,
            timeline_digest=timeline_digest,
            knowledge_digest=knowledge_digest,
        )

    async def _build_memory_digest(self, project_id: str, chapter_number: int) -> Dict[str, Any]:
        result = await self.session.execute(select(ProjectMemory).where(ProjectMemory.project_id == project_id))
        memory = result.scalar_one_or_none()
        snapshot_result = await self.session.execute(
            select(ChapterSnapshot)
            .where(ChapterSnapshot.project_id == project_id, ChapterSnapshot.chapter_number < chapter_number)
            .order_by(ChapterSnapshot.chapter_number.desc())
            .limit(10)
        )
        snapshots = list(snapshot_result.scalars().all())
        return {
            "global_summary": _truncate_text(memory.global_summary if memory else "", 900),
            "plot_arcs": memory.plot_arcs if memory and isinstance(memory.plot_arcs, dict) else {},
            "story_timeline_summary": _truncate_text(memory.story_timeline_summary if memory else "", 520),
            "last_updated_chapter": memory.last_updated_chapter if memory else 0,
            "recent_snapshots": [
                {
                    "chapter_number": item.chapter_number,
                    "chapter_summary": _truncate_text(item.chapter_summary, 220),
                    "word_count": item.word_count,
                }
                for item in sorted(snapshots, key=lambda value: value.chapter_number)
            ],
        }

    async def _build_timeline_digest(self, project_id: str, chapter_number: int) -> Dict[str, Any]:
        event_result = await self.session.execute(
            select(TimelineEvent)
            .where(TimelineEvent.project_id == project_id, TimelineEvent.chapter_number < chapter_number)
            .order_by(TimelineEvent.chapter_number.desc(), TimelineEvent.id.desc())
            .limit(16)
        )
        chain_result = await self.session.execute(
            select(CausalChain)
            .where(CausalChain.project_id == project_id)
            .order_by(CausalChain.cause_chapter.desc(), CausalChain.id.desc())
            .limit(14)
        )
        tracker_result = await self.session.execute(select(StoryTimeTracker).where(StoryTimeTracker.project_id == project_id))
        tracker = tracker_result.scalar_one_or_none()
        events = list(event_result.scalars().all())
        chains = list(chain_result.scalars().all())
        return {
            "current_story_time": {
                "date": tracker.current_date if tracker else None,
                "time": tracker.current_time if tracker else None,
            },
            "recent_events": [
                {
                    "chapter_number": event.chapter_number,
                    "title": _truncate_text(event.event_title, 100),
                    "description": _truncate_text(event.event_description, 180),
                    "characters": _compact_list(event.involved_characters, limit=5),
                    "location": _truncate_text(event.location, 80),
                    "importance": event.importance,
                }
                for event in sorted(events, key=lambda value: (value.chapter_number, value.id or 0))[-10:]
            ],
            "causal_chains": [
                {
                    "cause_chapter": chain.cause_chapter,
                    "cause": _truncate_text(chain.cause_description, 150),
                    "effect_chapter": chain.effect_chapter,
                    "effect": _truncate_text(chain.effect_description, 150),
                    "status": chain.status,
                    "importance": chain.importance,
                    "characters": _compact_list(chain.involved_characters, limit=5),
                }
                for chain in chains
            ],
        }

    async def _build_knowledge_digest(self, project_id: str, chapter_number: int) -> Dict[str, Any]:
        faction_result = await self.session.execute(
            select(Faction)
            .where(Faction.project_id == project_id)
            .order_by(Faction.id.asc())
            .limit(12)
        )
        faction_relation_result = await self.session.execute(
            select(FactionRelationship)
            .where(FactionRelationship.project_id == project_id)
            .order_by(FactionRelationship.id.asc())
            .limit(16)
        )
        node_result = await self.session.execute(
            select(CharacterNode)
            .where(CharacterNode.project_id == project_id)
            .order_by(CharacterNode.id.asc())
            .limit(18)
        )
        edge_result = await self.session.execute(
            select(EventEdge)
            .where(EventEdge.project_id == project_id, EventEdge.chapter_number < chapter_number)
            .order_by(EventEdge.chapter_number.desc(), EventEdge.id.desc())
            .limit(18)
        )
        return {
            "factions": [
                {
                    "name": faction.name,
                    "type": faction.faction_type,
                    "leader": faction.leader,
                    "status": _truncate_text(faction.current_status, 120),
                    "goals": _compact_list(faction.goals, limit=4),
                }
                for faction in faction_result.scalars().all()
            ],
            "faction_relationships": [
                {
                    "from_id": rel.faction_from_id,
                    "to_id": rel.faction_to_id,
                    "type": rel.relationship_type,
                    "description": _truncate_text(rel.description, 120),
                }
                for rel in faction_relation_result.scalars().all()
            ],
            "knowledge_nodes": [
                {
                    "name": node.name,
                    "role_type": node.role_type,
                    "status": node.status,
                    "location": node.location,
                    "emotional_state": node.emotional_state,
                }
                for node in node_result.scalars().all()
            ],
            "recent_event_edges": [
                {
                    "chapter_number": edge.chapter_number,
                    "type": edge.event_type,
                    "description": _truncate_text(edge.description, 150),
                    "causality": _truncate_text(edge.causality, 120),
                }
                for edge in edge_result.scalars().all()
            ],
        }

    async def _build_cast_plan(
        self,
        *,
        project_id: str,
        total_chapters: int,
        chapter_number: int,
        outline: Optional[ChapterOutline],
        chapter_mission: Optional[Dict[str, Any]],
        allowed_new_characters: List[str],
    ) -> CastPlan:
        character_result = await self.session.execute(
            select(BlueprintCharacter)
            .where(BlueprintCharacter.project_id == project_id)
            .order_by(BlueprintCharacter.position.asc(), BlueprintCharacter.id.asc())
        )
        characters = list(character_result.scalars().all())
        relationship_result = await self.session.execute(
            select(BlueprintRelationship)
            .where(BlueprintRelationship.project_id == project_id)
            .order_by(BlueprintRelationship.position.asc(), BlueprintRelationship.id.asc())
            .limit(24)
        )
        relationships = list(relationship_result.scalars().all())
        member_result = await self.session.execute(
            select(FactionMember)
            .where(FactionMember.project_id == project_id)
            .order_by(FactionMember.id.asc())
            .limit(24)
        )
        state_result = await self.session.execute(
            select(CharacterState)
            .where(CharacterState.project_id == project_id, CharacterState.chapter_number < chapter_number)
            .order_by(CharacterState.chapter_number.desc(), CharacterState.id.desc())
        )
        latest_states: Dict[str, CharacterState] = {}
        for state in state_result.scalars().all():
            name = (state.character_name or "").strip()
            if name and name not in latest_states:
                latest_states[name] = state

        target_count = _estimate_longform_cast_target(total_chapters)
        tiers: Dict[str, List[Dict[str, Any]]] = {}
        for index, character in enumerate(characters):
            item = _serialise_character(character, index)
            tiers.setdefault(item["tier"], []).append(item)

        chapter_focus = _extract_outline_focus(outline, chapter_mission)
        if not chapter_focus:
            for character in characters[:4]:
                if character.name:
                    chapter_focus.append(character.name)
        for name in allowed_new_characters:
            if name and name not in chapter_focus:
                chapter_focus.append(name)

        needed = max(0, target_count - len(characters))
        dynamic_slots: List[Dict[str, Any]] = []
        slot_labels = [
            ("stage_support", "阶段配角：承接当前阶段冲突，至少保留2-6章生命周期"),
            ("faction_member", "势力成员：必须绑定势力、职务、忠诚/利益关系"),
            ("functional", "功能性路人：只承担单章信息/阻碍，不抢主线位置"),
            ("returning_support", "回归角色：从既有角色池找人回场，优先于凭空新增"),
        ]
        for index in range(min(max(needed, 2), 6)):
            tier, rule = slot_labels[index % len(slot_labels)]
            dynamic_slots.append(
                {
                    "tier": tier,
                    "slot_index": index + 1,
                    "rule": rule,
                    "persistence_rule": "新增后必须进入角色池/势力/关系/知识边界账本，不能用完消失。",
                }
            )

        return CastPlan(
            target_character_count=target_count,
            planned_character_count=len(characters),
            tiers={key: value[:10] for key, value in tiers.items()},
            chapter_focus_names=chapter_focus[:12],
            active_character_states=[_serialise_state(state) for state in list(latest_states.values())[:16]],
            faction_assignments=[
                {
                    "character_id": member.character_id,
                    "faction_id": member.faction_id,
                    "role": member.role,
                    "rank": member.rank,
                    "loyalty": member.loyalty,
                }
                for member in member_result.scalars().all()
            ],
            relationship_edges=[
                {
                    "from": relation.character_from,
                    "to": relation.character_to,
                    "description": _truncate_text(relation.description, 180),
                }
                for relation in relationships
            ],
            dynamic_slots=dynamic_slots,
            rules=[
                "主角、核心角色、阶段配角、势力成员、功能性路人要分层使用，避免全书只有少数角色反复承担所有功能。",
                "本章新增角色必须说明归属、目标、信息边界和后续去向；没有后续价值的只允许作为功能性路人短暂出现。",
                "角色不能突然知道未获得的信息，不能忘记上一章状态、伤势、物品、立场和关系变化。",
            ],
        )

    async def _build_foreshadowing_task(
        self,
        *,
        project_id: str,
        chapter_number: int,
        outline: Optional[ChapterOutline],
        chapter_mission: Optional[Dict[str, Any]],
        cast_focus: List[str],
    ) -> ForeshadowingChapterTask:
        foreshadowing_result = await self.session.execute(
            select(Foreshadowing)
            .where(Foreshadowing.project_id == project_id, Foreshadowing.status.in_(ACTIVE_FORESHADOWING_STATUSES))
            .order_by(Foreshadowing.chapter_number.asc(), Foreshadowing.id.asc())
            .limit(80)
        )
        clue_result = await self.session.execute(
            select(StoryClue)
            .where(StoryClue.project_id == project_id, StoryClue.status.in_(ACTIVE_CLUE_STATUSES))
            .order_by(StoryClue.importance.desc(), StoryClue.id.asc())
            .limit(40)
        )
        must_resolve: List[Dict[str, Any]] = []
        should_reinforce: List[Dict[str, Any]] = []
        avoid_forgetting: List[Dict[str, Any]] = []
        overdue_risks: List[Dict[str, Any]] = []
        focus_text = " ".join(cast_focus)

        for item in foreshadowing_result.scalars().all():
            serialised = _serialise_foreshadowing(item, chapter_number)
            target = item.target_reveal_chapter
            distance = serialised["distance"]
            target_due = target is not None and int(target) <= chapter_number
            related_focus = any(name and name in focus_text for name in _compact_list(item.related_characters, limit=8))
            urgent = bool((item.urgency or 0) >= 8)
            if target_due or urgent:
                must_resolve.append(serialised)
            elif (target is not None and int(target) <= chapter_number + 3) or related_focus or distance >= 6:
                should_reinforce.append(serialised)
            if distance >= 4 and item.importance in {"major", "long", "medium"}:
                avoid_forgetting.append(serialised)
            if (target is not None and int(target) < chapter_number) or distance >= 12:
                overdue_risks.append(serialised)

        active_clues: List[Dict[str, Any]] = []
        for clue in clue_result.scalars().all():
            payload = _serialise_clue(clue, chapter_number)
            active_clues.append(payload)
            if clue.resolution_chapter is not None and int(clue.resolution_chapter) <= chapter_number:
                must_resolve.append(
                    {
                        "id": f"clue:{clue.id}",
                        "name": payload["name"],
                        "content": payload["description"],
                        "type": "story_clue",
                        "status": clue.status,
                        "keywords": [payload["name"]],
                        "planted_chapter": clue.planted_chapter,
                        "distance": payload["distance"],
                        "target_reveal_chapter": clue.resolution_chapter,
                        "importance": clue.importance,
                    }
                )

        may_plant = _extract_outline_foreshadowing(outline, chapter_mission)
        return ForeshadowingChapterTask(
            must_resolve=must_resolve[:10],
            should_reinforce=should_reinforce[:10],
            may_plant=may_plant[:10],
            avoid_forgetting=avoid_forgetting[:12],
            overdue_risks=overdue_risks[:12],
            active_clues=active_clues[:16],
            rules=[
                "本章必须优先处理 must_resolve；如果不能回收，要在正文里明确强化并给出下一次回收窗口。",
                "伏笔回收要有因果兑现和情绪/局势后果，不能只用一句解释抹平。",
                "允许新增伏笔，但必须服务当前冲突或长线账本，不能随手开无承接的新坑。",
            ],
        )

    def _format_prompt_text(
        self,
        *,
        chapter_number: int,
        writing_notes: Optional[str],
        memory_digest: Dict[str, Any],
        timeline_digest: Dict[str, Any],
        knowledge_digest: Dict[str, Any],
        cast_plan: CastPlan,
        foreshadowing_task: ForeshadowingChapterTask,
    ) -> str:
        payload = {
            "chapter_number": chapter_number,
            "writing_notes": writing_notes or "",
            "memory": memory_digest,
            "timeline": timeline_digest,
            "knowledge": knowledge_digest,
            "cast_plan": asdict(cast_plan),
            "foreshadowing_task": asdict(foreshadowing_task),
        }
        compact_json = json.dumps(payload, ensure_ascii=False, indent=2)
        return (
            "你正在写一个需要跨章节连续的小说项目；无论篇幅长短，本节写前长期上下文包都必须作为约束使用，不要照抄成正文。\n"
            "核心目标：跨章节、跨卷、跨剧情线保持连续；角色、伏笔、线索、时间线、势力和知识边界都要闭环。\n\n"
            f"{compact_json}\n\n"
            "[执行要求]\n"
            "- 开篇承接上一章和长期账本，不只承接相邻章节。\n"
            "- 正文必须让角色状态、物品、伤势、知识边界、势力立场与前文一致。\n"
            "- 本章新增角色必须有层级、归属、目标、信息边界和后续去向；禁止凭空出现又消失。\n"
            "- 当角色池低于目标规模时，优先安排阶段配角、势力成员或功能性路人承担明确职责；新增后必须进入角色/势力/知识边界账本。\n"
            "- 伏笔处理顺序：到期回收 > 逾期补偿 > 临近强化 > 本章新埋。回收必须写出因果揭示和后果，不得只提关键词。"
        )

    @staticmethod
    def evaluate_continuity_quality(
        *,
        content: str,
        package: Optional[LongformContextPackage],
        chapter_mission: Optional[Dict[str, Any]] = None,
        chapter_number: Optional[int] = None,
    ) -> ContinuityQualityGate:
        if package is None:
            return ContinuityQualityGate(
                passed=True,
                warnings=[{"code": "longform_context_missing", "message": "长篇上下文包缺失，本轮只执行基础质量门。"}],
            )

        text = content or ""
        warnings: List[Dict[str, Any]] = []
        blockers: List[Dict[str, Any]] = []
        patch_suggestions: List[Dict[str, Any]] = []
        if chapter_number is not None and int(chapter_number) != int(package.chapter_number):
            blockers.append({
                "code": "longform_context_chapter_mismatch",
                "message": "长篇上下文包与当前章节号不一致，禁止用错章节上下文继续生成。",
                "expected_chapter": int(chapter_number),
                "package_chapter": int(package.chapter_number),
            })

        missing_focus = [
            name for name in package.cast_plan.chapter_focus_names
            if name and name not in text and not name.startswith("角色")
        ][:6]
        if missing_focus:
            warnings.append(
                {
                    "code": "chapter_focus_missing",
                    "message": "本章角色焦点在正文中缺席或弱化。",
                    "characters": missing_focus,
                }
            )

        dead_action_words = ("说", "问", "笑", "走", "抬", "看", "冲", "握", "坐")
        for state in package.cast_plan.active_character_states:
            name = str(state.get("character_name") or "")
            health = str(state.get("health_status") or "")
            if not name or name not in text:
                continue
            if health.lower() in {"dead", "死亡", "已死"} and any(f"{name}{word}" in text for word in dead_action_words):
                blockers.append(
                    {
                        "code": "dead_character_active_without_explanation",
                        "message": f"{name}在记忆层中已死亡，但正文像正常行动，需要解释或修复。",
                        "character": name,
                    }
                )

        unresolved_due: List[Dict[str, Any]] = []
        payoff_signal_words = (
            "揭开",
            "真相",
            "原来",
            "证据",
            "兑现",
            "回收",
            "解释",
            "指向",
            "导致",
            "因此",
            "代价",
            "暴露",
            "确认",
            "证实",
        )
        for item in package.foreshadowing_task.must_resolve:
            keywords = [str(value).strip() for value in item.get("keywords") or [] if str(value).strip()]
            if not keywords:
                keywords = [str(item.get("name") or "").strip(), str(item.get("content") or "").strip()[:12]]
            hit = any(keyword and keyword in text for keyword in keywords if len(keyword) >= 2)
            payoff_signal_hit = any(word in text for word in payoff_signal_words)
            if hit and payoff_signal_hit:
                continue
            if hit and not payoff_signal_hit:
                warnings.append(
                    {
                        "code": "due_foreshadowing_payoff_weak",
                        "message": "到期伏笔虽然被提到，但缺少揭示、兑现或后果，容易像没有真正回收。",
                        "foreshadowing": item.get("name") or item.get("id"),
                    }
                )
                patch_suggestions.append(
                    {
                        "code": "strengthen_payoff_patch",
                        "target": item.get("name") or item.get("id"),
                        "suggestion": "保留当前正文，只在命中伏笔的场景附近补1-2段：写清它揭开了什么、改变了谁的判断、带来什么代价或新压力。",
                    }
                )
                continue
            unresolved_due.append(item)
            warning = {
                "code": "due_foreshadowing_not_visible",
                "message": "到期伏笔/线索在正文中没有可见回收或强化。",
                "foreshadowing": item.get("name") or item.get("id"),
                "target_reveal_chapter": item.get("target_reveal_chapter"),
            }
            if int(item.get("distance") or 0) >= 12 or item.get("importance") in {"major", "long", 5}:
                blockers.append(warning)
            else:
                warnings.append(warning)
            patch_suggestions.append(
                {
                    "code": "local_payoff_patch",
                    "target": item.get("name") or item.get("id"),
                    "suggestion": "在相关场景增加1-3段局部补丁：先让角色意识到旧伏笔，再用行动/证据兑现或明确推迟回收窗口。",
                }
            )

        long_gap_items = [
            item for item in package.foreshadowing_task.avoid_forgetting
            if int(item.get("distance") or 0) >= 8 and not any(str(keyword) in text for keyword in item.get("keywords") or [])
        ][:6]
        if long_gap_items:
            warnings.append(
                {
                    "code": "long_gap_foreshadowing_memory_risk",
                    "message": "较久未出现的伏笔本章仍未强化，读者记忆可能断裂。",
                    "items": [item.get("name") or item.get("id") for item in long_gap_items],
                }
            )

        pending_causal_gaps: List[Dict[str, Any]] = []
        for chain in (package.timeline_digest.get("causal_chains") or [])[:12]:
            if not isinstance(chain, dict):
                continue
            status = str(chain.get("status") or "pending").lower()
            if status in {"resolved", "abandoned"}:
                continue
            try:
                importance = int(chain.get("importance") or 5)
            except (TypeError, ValueError):
                importance = 5
            cause_chapter = int(chain.get("cause_chapter") or package.chapter_number)
            if importance < 7 and package.chapter_number - cause_chapter > 4:
                continue
            signal_terms: List[str] = []
            for value in (chain.get("cause"), chain.get("effect")):
                signal_terms.extend(_signal_terms_from_text(value, limit=5))
            if _content_has_any_signal(text, signal_terms):
                continue
            pending_causal_gaps.append(chain)

        if pending_causal_gaps:
            warnings.append(
                {
                    "code": "pending_causal_chain_not_carried",
                    "message": "Pending causal pressure from prior chapters is not visibly carried into this draft.",
                    "chains": [
                        {
                            "cause_chapter": item.get("cause_chapter"),
                            "cause": item.get("cause"),
                            "effect": item.get("effect"),
                            "importance": item.get("importance"),
                        }
                        for item in pending_causal_gaps[:5]
                    ],
                }
            )
            for item in pending_causal_gaps[:3]:
                patch_suggestions.append(
                    {
                        "code": "carry_causal_chain_patch",
                        "target": item.get("effect") or item.get("cause"),
                        "suggestion": "Keep the chapter structure and add 1-2 anchored paragraphs near the relevant scene so the prior cause creates concrete pressure, choice, cost, or danger in this chapter.",
                    }
                )

        metrics = {
            "chapter_number": package.chapter_number,
            "focus_character_count": len(package.cast_plan.chapter_focus_names),
            "missing_focus_count": len(missing_focus),
            "must_resolve_count": len(package.foreshadowing_task.must_resolve),
            "unresolved_due_count": len(unresolved_due),
            "pending_causal_gap_count": len(pending_causal_gaps),
            "active_clue_count": len(package.foreshadowing_task.active_clues),
            "planned_character_count": package.cast_plan.planned_character_count,
            "target_character_count": package.cast_plan.target_character_count,
            "mission_scene_count": len((chapter_mission or {}).get("scene_list") or []) if isinstance(chapter_mission, dict) else 0,
        }
        return ContinuityQualityGate(
            passed=not blockers,
            blockers=blockers,
            warnings=warnings,
            patch_suggestions=patch_suggestions,
            metrics=metrics,
        )
