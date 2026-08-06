"""
知识图谱服务层

提供知识图谱的 CRUD 操作、关系查询和情节分析功能。
将角色视为对象，情节视为有向图，实现复杂的叙事关系追踪。
"""
import json
from typing import Optional, List, Dict, Any
from collections import defaultdict
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, delete

from ..models.knowledge_graph import CharacterNode, EventEdge, KnowledgeGraphMetadata
from ..models.novel import BlueprintCharacter, BlueprintRelationship
from ..models.memory_layer import CausalChain, CharacterState, TimelineEvent

logger = logging.getLogger(__name__)


_RELATIONSHIP_META_MARKERS: tuple[str, ...] = (
    "\n[[XUANQIONG_WENSHU_RELATIONSHIP_META]]\n",
    "\n[[ARBORIS_RELATIONSHIP_META]]\n",
)


def _decode_relationship_description(text: str | None) -> tuple[str, Dict[str, Any]]:
    cleaned = (text or "").strip()
    if not cleaned:
        return "", {}
    for marker in _RELATIONSHIP_META_MARKERS:
        if marker not in cleaned:
            continue
        description, _, payload = cleaned.partition(marker)
        try:
            meta = json.loads(payload.strip()) if payload.strip() else {}
        except json.JSONDecodeError:
            meta = {}
        return description.strip(), meta if isinstance(meta, dict) else {}
    return cleaned, {}


def _edge_type_from_relationship(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"conflict", "enemy", "hostile", "rivalry"}:
        return "conflict"
    if text in {"alliance", "ally", "partner", "mentor", "family"}:
        return "alliance"
    if text in {"romance"}:
        return "transformation"
    return "relationship"


_LEGACY_SUPPLEMENTAL_NODE_PREFIXES: tuple[str, ...] = (
    "线索持有者",
    "旧日盟友",
    "对立代理人",
    "边缘证人",
    "信息中介",
    "失联亲属",
)


def _is_legacy_supplemental_node(node: CharacterNode) -> bool:
    name = (node.name or "").strip()
    role_type = (node.role_type or "").strip()
    if role_type.startswith("补强角色位"):
        return True
    return any(name.startswith(prefix) and any(ch.isdigit() for ch in name) for prefix in _LEGACY_SUPPLEMENTAL_NODE_PREFIXES)


_FACT_SOURCE_LABELS: dict[str, str] = {
    "blueprint_character": "蓝图角色",
    "dynamic_character": "动态角色入池",
    "chapter_state": "章节状态",
    "timeline_event": "时间线事件",
    "blueprint_relationship": "蓝图关系",
    "causal_chain": "因果链",
    "manual": "手工补充",
}

_FACT_SOURCE_CONFIDENCE_BASE: dict[str, int] = {
    "blueprint_character": 82,
    "dynamic_character": 76,
    "chapter_state": 90,
    "timeline_event": 74,
    "blueprint_relationship": 80,
    "causal_chain": 88,
    "manual": 58,
}


def _safe_int(value: Any) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _label_fact_source(source_key: Any) -> str:
    key = str(source_key or "").strip().lower()
    return _FACT_SOURCE_LABELS.get(key, key or "手工补充")


def _coerce_mapping(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first_int(*values: Any) -> Optional[int]:
    for value in values:
        parsed = _safe_int(value)
        if parsed is not None:
            return parsed
    return None


def _max_int(*values: Any) -> Optional[int]:
    parsed = [_safe_int(value) for value in values]
    parsed = [value for value in parsed if value is not None]
    return max(parsed) if parsed else None


def _build_node_fact_profile(
    node: CharacterNode,
    *,
    blueprint_character: BlueprintCharacter | None,
    latest_state: CharacterState | None,
    connected_edges: List[EventEdge],
    project_latest_chapter: Optional[int],
) -> Dict[str, Any]:
    node_extra = _coerce_mapping(node.extra)
    blueprint_extra = _coerce_mapping(getattr(blueprint_character, "extra", None))
    state_extra = _coerce_mapping(getattr(latest_state, "extra", None))

    source_key = (
        _safe_text(node_extra.get("fact_source"))
        or _safe_text(blueprint_extra.get("fact_source"))
        or _safe_text(state_extra.get("fact_source"))
    )
    if not source_key:
        if node_extra.get("auto_created_from_memory") or blueprint_extra.get("auto_created_from_memory"):
            source_key = "dynamic_character"
        elif latest_state is not None:
            source_key = "chapter_state"
        elif blueprint_character is not None:
            source_key = "blueprint_character"
        else:
            for edge in connected_edges:
                edge_source = _safe_text(_coerce_mapping(edge.extra).get("source"))
                if edge_source:
                    source_key = edge_source
                    break
            if not source_key:
                source_key = "manual"

    connected_chapters = [
        parsed
        for edge in connected_edges
        if (parsed := _safe_int(edge.chapter_number)) is not None
    ]
    state_chapter = _safe_int(getattr(latest_state, "chapter_number", None))
    first_chapter = _first_int(
        node_extra.get("first_chapter"),
        blueprint_extra.get("first_appearance_chapter"),
        blueprint_extra.get("first_chapter"),
        state_chapter,
        min(connected_chapters) if connected_chapters else None,
    )
    latest_chapter = _max_int(
        node_extra.get("latest_chapter"),
        node_extra.get("latest_seen_chapter"),
        blueprint_extra.get("latest_chapter"),
        state_chapter,
        max(connected_chapters) if connected_chapters else None,
    )
    if latest_chapter is None:
        latest_chapter = first_chapter

    health = _safe_text(getattr(latest_state, "health_status", None)) or _safe_text(node.status)
    health_key = health.strip().lower()
    if health_key in {"dead", "deceased", "fallen"}:
        lifecycle = "ended"
    elif source_key == "dynamic_character":
        lifecycle = "dynamic"
    elif latest_state is not None:
        if project_latest_chapter is not None and latest_chapter is not None and latest_chapter < max(1, project_latest_chapter - 2):
            lifecycle = "tracked"
        else:
            lifecycle = "active"
    elif blueprint_character is not None:
        lifecycle = "planned"
    else:
        lifecycle = "manual"

    relationship_count = len(connected_edges)
    confidence = _first_int(
        node_extra.get("confidence"),
        blueprint_extra.get("confidence"),
        state_extra.get("confidence"),
    )
    if confidence is None:
        confidence = _FACT_SOURCE_CONFIDENCE_BASE.get(source_key, 60)
        if latest_state is not None:
            confidence += 4
        if first_chapter is not None and latest_chapter is not None and latest_chapter > first_chapter:
            confidence += 4
        if relationship_count >= 6:
            confidence += 4
        if source_key == "manual":
            confidence -= 4
        confidence = max(0, min(100, confidence))

    return {
        "fact_source": source_key,
        "fact_source_label": _label_fact_source(source_key),
        "first_chapter": first_chapter,
        "latest_chapter": latest_chapter,
        "confidence": confidence,
        "lifecycle": lifecycle,
        "relationship_count": relationship_count,
    }


def _build_edge_fact_profile(
    edge: EventEdge,
    *,
    source_profile: Dict[str, Any],
    target_profile: Dict[str, Any],
) -> Dict[str, Any]:
    edge_extra = _coerce_mapping(edge.extra)
    source_key = _safe_text(edge_extra.get("fact_source")) or _safe_text(edge_extra.get("source"))
    if not source_key:
        if edge.event_type == "causality":
            source_key = "causal_chain"
        elif edge.chapter_number is not None:
            source_key = "timeline_event"
        else:
            source_key = "blueprint_relationship"

    source_chapter = _first_int(
        edge_extra.get("source_chapter"),
        edge_extra.get("cause_chapter"),
        edge.chapter_number,
        source_profile.get("first_chapter"),
        target_profile.get("first_chapter"),
    )
    latest_chapter = _max_int(
        edge_extra.get("latest_chapter"),
        edge_extra.get("effect_chapter"),
        edge.chapter_number,
        source_profile.get("latest_chapter"),
        target_profile.get("latest_chapter"),
    )
    if latest_chapter is None:
        latest_chapter = source_chapter

    confidence = _first_int(edge_extra.get("confidence"))
    if confidence is None:
        importance = _safe_int(edge.importance) or 5
        confidence = max(10, min(100, importance * 10))
        if source_key in {"causal_chain", "timeline_event"}:
            confidence += 5
        if source_key == "blueprint_relationship":
            confidence += 3
        if source_profile.get("lifecycle") == "active" or target_profile.get("lifecycle") == "active":
            confidence += 2
        confidence = max(0, min(100, confidence))

    return {
        "fact_source": source_key,
        "fact_source_label": _label_fact_source(source_key),
        "source_chapter": source_chapter,
        "latest_chapter": latest_chapter,
        "confidence": confidence,
    }


class PlotThread:
    """情节线索 - 表示一个完整的叙事线"""

    def __init__(
        self,
        thread_id: str,
        title: str,
        characters: List[str],
        events: List[Dict[str, Any]],
        chapter_range: tuple
    ):
        self.thread_id = thread_id
        self.title = title
        self.characters = characters
        self.events = events
        self.chapter_range = chapter_range  # (start_chapter, end_chapter)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "thread_id": self.thread_id,
            "title": self.title,
            "characters": self.characters,
            "events": self.events,
            "chapter_range": self.chapter_range
        }


class KnowledgeGraphService:
    """知识图谱服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def sync_from_story_memory(self, project_id: str) -> Dict[str, int]:
        """从蓝图角色、角色状态和时间线事件自动回填知识图谱。"""
        created_nodes = 0
        created_edges = 0
        removed_nodes = 0
        removed_edges = 0

        blueprint_result = await self.db.execute(
            select(BlueprintCharacter)
            .where(BlueprintCharacter.project_id == project_id)
            .order_by(BlueprintCharacter.position.asc(), BlueprintCharacter.id.asc())
        )
        blueprint_characters = list(blueprint_result.scalars().all())
        blueprint_names = {(character.name or "").strip() for character in blueprint_characters if (character.name or "").strip()}
        blueprint_ids = {character.id for character in blueprint_characters if character.id is not None}

        state_result = await self.db.execute(
            select(CharacterState)
            .where(CharacterState.project_id == project_id)
            .order_by(CharacterState.chapter_number.desc(), CharacterState.id.desc())
        )
        latest_states: Dict[str, CharacterState] = {}
        for state in state_result.scalars():
            name = (state.character_name or "").strip()
            if name and name not in latest_states:
                latest_states[name] = state

        existing_nodes = await self.get_project_nodes(project_id)
        stale_nodes = [
            node for node in existing_nodes
            if (node.name or "").strip() not in blueprint_names
            and (node.name or "").strip() not in latest_states
            and (
                _is_legacy_supplemental_node(node)
                or (
                    node.blueprint_character_id is not None
                    and node.blueprint_character_id not in blueprint_ids
                )
            )
        ]
        if stale_nodes:
            stale_node_ids = [node.id for node in stale_nodes if node.id is not None]
            if stale_node_ids:
                edge_delete_result = await self.db.execute(
                    delete(EventEdge).where(
                        EventEdge.project_id == project_id,
                        or_(
                            EventEdge.source_node_id.in_(stale_node_ids),
                            EventEdge.target_node_id.in_(stale_node_ids),
                        ),
                    )
                )
                removed_edges = int(edge_delete_result.rowcount or 0)
            for node in stale_nodes:
                await self.db.delete(node)
            await self.db.flush()
            removed_nodes = len(stale_nodes)
            stale_ids = {node.id for node in stale_nodes}
            existing_nodes = [node for node in existing_nodes if node.id not in stale_ids]
        node_map = {(node.name or "").strip(): node for node in existing_nodes if (node.name or "").strip()}

        for character in blueprint_characters:
            node = node_map.get(character.name.strip())
            state = latest_states.get(character.name.strip())
            if node is None:
                node = CharacterNode(
                    project_id=project_id,
                    name=character.name.strip(),
                    role_type=character.identity or "角色",
                    description=character.personality,
                    traits=[character.personality] if character.personality else [],
                    goals=[character.goals] if character.goals else [],
                    status=state.health_status if state and state.health_status else "active",
                    location=state.location if state else None,
                    emotional_state=state.emotion if state else None,
                    blueprint_character_id=character.id,
                )
                self.db.add(node)
                await self.db.flush()
                node_map[node.name] = node
                created_nodes += 1
            else:
                node.role_type = node.role_type or character.identity or "角色"
                node.description = node.description or character.personality
                node.blueprint_character_id = node.blueprint_character_id or character.id
                if state:
                    node.location = state.location or node.location
                    node.emotional_state = state.emotion or node.emotional_state

        event_result = await self.db.execute(
            select(TimelineEvent)
            .where(TimelineEvent.project_id == project_id)
            .order_by(TimelineEvent.chapter_number.asc(), TimelineEvent.id.asc())
        )
        timeline_events = list(event_result.scalars().all())
        existing_edges = await self.get_project_edges(project_id)
        edge_keys = {
            (edge.source_node_id, edge.target_node_id, edge.chapter_number or 0, edge.event_type or "", (edge.description or "")[:120])
            for edge in existing_edges
        }

        relationship_result = await self.db.execute(
            select(BlueprintRelationship)
            .where(BlueprintRelationship.project_id == project_id)
            .order_by(BlueprintRelationship.position.asc(), BlueprintRelationship.id.asc())
        )
        for relation in relationship_result.scalars():
            source_name = (relation.character_from or "").strip()
            target_name = (relation.character_to or "").strip()
            if not source_name or not target_name or source_name == target_name:
                continue
            source_node = node_map.get(source_name)
            target_node = node_map.get(target_name)
            if not source_node or not target_node:
                continue
            description, meta = _decode_relationship_description(relation.description)
            relation_type = str(meta.get("relationship_type") or "relationship").strip()
            event_type = _edge_type_from_relationship(relation_type)
            key = (source_node.id, target_node.id, 0, event_type, (description or relation_type)[:120])
            if key in edge_keys:
                continue
            try:
                importance = int(meta.get("importance") or 3)
            except (TypeError, ValueError):
                importance = 3
            edge = EventEdge(
                project_id=project_id,
                source_node_id=source_node.id,
                target_node_id=target_node.id,
                event_type=event_type,
                description=description or f"{source_name}与{target_name}存在{relation_type}关系",
                chapter_number=None,
                importance=max(1, min(10, importance)),
                emotional_impact=str(meta.get("tension") or meta.get("status") or "ongoing"),
                plot_advancement=str(meta.get("direction") or "relationship_arc"),
                causality=str(meta.get("core_conflict") or meta.get("trigger_event") or ""),
                extra={
                    "source": "blueprint_relationship",
                    "relationship_id": relation.id,
                    "relationship_type": relation_type,
                    "status": meta.get("status"),
                    "trigger_event": meta.get("trigger_event"),
                    "is_supplemental": bool(meta.get("is_supplemental", False)),
                },
            )
            self.db.add(edge)
            edge_keys.add(key)
            created_edges += 1

        for event in timeline_events:
            names = [str(name or "").strip() for name in (event.involved_characters or []) if str(name or "").strip()]
            if len(names) < 2:
                continue
            for index, source_name in enumerate(names):
                for target_name in names[index + 1:]:
                    source_node = node_map.get(source_name)
                    target_node = node_map.get(target_name)
                    if not source_node or not target_node:
                        continue
                    event_type = "interaction" if not event.is_turning_point else "turning_point"
                    key = (source_node.id, target_node.id, event.chapter_number or 0, event_type, (event.event_title or "")[:120])
                    if key in edge_keys:
                        continue
                    edge = EventEdge(
                        project_id=project_id,
                        source_node_id=source_node.id,
                        target_node_id=target_node.id,
                        event_type=event_type,
                        description=event.event_title or event.event_description,
                        chapter_number=event.chapter_number,
                        timestamp=event.story_time,
                        importance=event.importance,
                        emotional_impact="turning" if event.is_turning_point else "ongoing",
                        plot_advancement="major" if event.event_type == "major" else "normal",
                        extra={
                            "source": "timeline_event",
                            "timeline_event_id": event.id,
                            "event_title": event.event_title,
                            "event_type": event.event_type,
                            "source_chapter": event.chapter_number,
                            "latest_chapter": event.chapter_number,
                            "is_turning_point": event.is_turning_point,
                        },
                    )
                    self.db.add(edge)
                    edge_keys.add(key)
                    created_edges += 1

        chain_result = await self.db.execute(
            select(CausalChain)
            .where(CausalChain.project_id == project_id)
            .order_by(CausalChain.cause_chapter.asc(), CausalChain.id.asc())
        )
        for chain in chain_result.scalars():
            names = [str(name or "").strip() for name in (chain.involved_characters or []) if str(name or "").strip()]
            if len(names) < 2:
                continue
            description = f"{(chain.cause_description or '').strip()} -> {(chain.effect_description or '').strip()}".strip()
            if not description or description == "->":
                continue
            chapter_number = chain.effect_chapter or chain.cause_chapter
            try:
                importance = max(1, min(10, int(chain.importance or 5)))
            except (TypeError, ValueError):
                importance = 5
            for index, source_name in enumerate(names):
                for target_name in names[index + 1:]:
                    source_node = node_map.get(source_name)
                    target_node = node_map.get(target_name)
                    if not source_node or not target_node:
                        continue
                    key = (source_node.id, target_node.id, chapter_number or 0, "causality", description[:120])
                    if key in edge_keys:
                        continue
                    edge = EventEdge(
                        project_id=project_id,
                        source_node_id=source_node.id,
                        target_node_id=target_node.id,
                        event_type="causality",
                        description=description,
                        chapter_number=chapter_number,
                        importance=importance,
                        emotional_impact=str(chain.status or "pending")[:64],
                        plot_advancement=str(chain.effect_type or "causal_pressure")[:64],
                        causality=chain.cause_description,
                        extra={
                            "source": "causal_chain",
                            "causal_chain_id": chain.id,
                            "cause_chapter": chain.cause_chapter,
                            "effect_chapter": chain.effect_chapter,
                            "status": chain.status,
                            "effect": chain.effect_description,
                        },
                    )
                    self.db.add(edge)
                    edge_keys.add(key)
                    created_edges += 1

        await self.db.commit()
        await self._update_metadata(project_id)
        return {
            "created_nodes": created_nodes,
            "created_edges": created_edges,
            "removed_nodes": removed_nodes,
            "removed_edges": removed_edges,
        }

    # ===== 节点 CRUD =====

    async def create_node(self, project_id: str, character_data: dict) -> CharacterNode:
        """创建角色节点"""
        node = CharacterNode(project_id=project_id)
        for key, value in character_data.items():
            if hasattr(node, key):
                setattr(node, key, value)
        self.db.add(node)
        await self.db.commit()
        await self.db.refresh(node)
        await self._update_metadata(project_id)
        return node

    async def get_node(self, node_id: int) -> Optional[CharacterNode]:
        """获取角色节点"""
        result = await self.db.execute(
            select(CharacterNode).where(CharacterNode.id == node_id)
        )
        return result.scalar_one_or_none()

    async def get_project_nodes(self, project_id: str) -> List[CharacterNode]:
        """获取项目的所有角色节点"""
        result = await self.db.execute(
            select(CharacterNode).where(CharacterNode.project_id == project_id)
        )
        return list(result.scalars().all())

    async def update_node(self, node_id: int, data: dict) -> Optional[CharacterNode]:
        """更新角色节点"""
        node = await self.get_node(node_id)
        if node is None:
            return None
        for key, value in data.items():
            if hasattr(node, key):
                setattr(node, key, value)
        await self.db.commit()
        await self.db.refresh(node)
        if node.project_id:
            await self._update_metadata(node.project_id)
        return node

    async def delete_node(self, node_id: int) -> bool:
        """删除角色节点（级联删除相关边）"""
        node = await self.get_node(node_id)
        if node is None:
            return False
        project_id = node.project_id
        await self.db.delete(node)
        await self.db.commit()
        await self._update_metadata(project_id)
        return True

    # ===== 边 CRUD =====

    async def create_edge(self, project_id: str, event_data: dict) -> EventEdge:
        """创建事件边"""
        edge = EventEdge(project_id=project_id)
        for key, value in event_data.items():
            if hasattr(edge, key):
                setattr(edge, key, value)
        self.db.add(edge)
        await self.db.commit()
        await self.db.refresh(edge)
        await self._update_metadata(project_id)
        return edge

    async def get_edge(self, edge_id: int) -> Optional[EventEdge]:
        """获取事件边"""
        result = await self.db.execute(
            select(EventEdge).where(EventEdge.id == edge_id)
        )
        return result.scalar_one_or_none()

    async def get_project_edges(self, project_id: str) -> List[EventEdge]:
        """获取项目的所有事件边"""
        result = await self.db.execute(
            select(EventEdge)
            .where(EventEdge.project_id == project_id)
            .order_by(EventEdge.chapter_number, EventEdge.order_index)
        )
        return list(result.scalars().all())

    async def update_edge(self, edge_id: int, data: dict) -> Optional[EventEdge]:
        """更新事件边"""
        edge = await self.get_edge(edge_id)
        if edge is None:
            return None
        for key, value in data.items():
            if hasattr(edge, key):
                setattr(edge, key, value)
        await self.db.commit()
        await self.db.refresh(edge)
        if edge.project_id:
            await self._update_metadata(edge.project_id)
        return edge

    async def delete_edge(self, edge_id: int) -> bool:
        """删除事件边"""
        edge = await self.get_edge(edge_id)
        if edge is None:
            return False
        project_id = edge.project_id
        await self.db.delete(edge)
        await self.db.commit()
        await self._update_metadata(project_id)
        return True

    # ===== 图谱操作 =====

    async def get_project_graph(self, project_id: str) -> Dict[str, Any]:
        """获取项目的完整知识图谱"""
        nodes = await self.get_project_nodes(project_id)
        edges = await self.get_project_edges(project_id)

        blueprint_result = await self.db.execute(
            select(BlueprintCharacter).where(BlueprintCharacter.project_id == project_id)
        )
        blueprint_characters = list(blueprint_result.scalars().all())
        blueprint_by_id = {character.id: character for character in blueprint_characters if character.id is not None}
        blueprint_by_name = {
            (character.name or "").strip(): character
            for character in blueprint_characters
            if (character.name or "").strip()
        }

        state_result = await self.db.execute(
            select(CharacterState)
            .where(CharacterState.project_id == project_id)
            .order_by(CharacterState.chapter_number.asc(), CharacterState.id.asc())
        )
        latest_states: Dict[str, CharacterState] = {}
        project_chapter_numbers: List[int] = []
        for state in state_result.scalars().all():
            name = (state.character_name or "").strip()
            chapter_number = _safe_int(state.chapter_number)
            if chapter_number is not None:
                project_chapter_numbers.append(chapter_number)
            if name:
                latest_states[name] = state

        for edge in edges:
            chapter_number = _safe_int(edge.chapter_number)
            if chapter_number is not None:
                project_chapter_numbers.append(chapter_number)
        project_latest_chapter = max(project_chapter_numbers) if project_chapter_numbers else None

        node_edges: Dict[int, List[EventEdge]] = defaultdict(list)
        for edge in edges:
            if edge.source_node_id is not None:
                node_edges[edge.source_node_id].append(edge)
            if edge.target_node_id is not None:
                node_edges[edge.target_node_id].append(edge)

        # 构建节点映射
        node_map = {node.id: node for node in nodes}
        node_profiles: Dict[int, Dict[str, Any]] = {}

        # 序列化节点
        nodes_data = []
        for node in nodes:
            node_name = (node.name or "").strip()
            blueprint_character = (
                blueprint_by_id.get(node.blueprint_character_id)
                if node.blueprint_character_id is not None
                else None
            ) or blueprint_by_name.get(node_name)
            profile = _build_node_fact_profile(
                node,
                blueprint_character=blueprint_character,
                latest_state=latest_states.get(node_name),
                connected_edges=node_edges.get(node.id, []),
                project_latest_chapter=project_latest_chapter,
            )
            node_profiles[node.id] = profile
            nodes_data.append({
                "id": node.id,
                "project_id": node.project_id,
                "name": node.name,
                "role_type": node.role_type,
                "description": node.description,
                "traits": node.traits or [],
                "goals": node.goals or [],
                "fears": node.fears or [],
                "background": node.background,
                "status": node.status,
                "location": node.location,
                "emotional_state": node.emotional_state,
                "blueprint_character_id": node.blueprint_character_id,
                "extra": node.extra,
                **profile,
                "created_at": node.created_at.isoformat() if node.created_at else None,
                "updated_at": node.updated_at.isoformat() if node.updated_at else None
            })

        # 序列化边
        edges_data = []
        for edge in edges:
            source_node = node_map.get(edge.source_node_id)
            target_node = node_map.get(edge.target_node_id)
            profile = _build_edge_fact_profile(
                edge,
                source_profile=node_profiles.get(edge.source_node_id, {}),
                target_profile=node_profiles.get(edge.target_node_id, {}),
            )
            edges_data.append({
                "id": edge.id,
                "source_id": edge.source_node_id,
                "target_id": edge.target_node_id,
                "source_name": source_node.name if source_node else None,
                "target_name": target_node.name if target_node else None,
                "event_type": edge.event_type,
                "description": edge.description,
                "chapter_number": edge.chapter_number,
                "scene_number": edge.scene_number,
                "timestamp": edge.timestamp,
                "order_index": edge.order_index,
                "causality": edge.causality,
                "importance": edge.importance,
                "emotional_impact": edge.emotional_impact,
                "plot_advancement": edge.plot_advancement,
                "extra": edge.extra,
                **profile,
                "created_at": edge.created_at.isoformat() if edge.created_at else None,
                "updated_at": edge.updated_at.isoformat() if edge.updated_at else None
            })

        return {
            "project_id": project_id,
            "nodes": nodes_data,
            "edges": edges_data,
            "node_count": len(nodes_data),
            "edge_count": len(edges_data)
        }

    # ===== 关系查询 =====

    async def get_character_timeline(self, character_id: int) -> List[Dict[str, Any]]:
        """获取角色的时间线（该角色参与的所有事件，按章节排序）"""
        # 获取角色节点
        node = await self.get_node(character_id)
        if node is None:
            return []

        # 获取该角色作为源节点和目标节点的所有边
        result = await self.db.execute(
            select(EventEdge).where(
                or_(
                    EventEdge.source_node_id == character_id,
                    EventEdge.target_node_id == character_id
                )
            ).order_by(EventEdge.chapter_number, EventEdge.order_index)
        )
        edges = list(result.scalars().all())

        # 构建时间线
        timeline = []
        for edge in edges:
            is_outgoing = edge.source_node_id == character_id
            timeline.append({
                "edge_id": edge.id,
                "event_type": edge.event_type,
                "description": edge.description,
                "chapter_number": edge.chapter_number,
                "scene_number": edge.scene_number,
                "timestamp": edge.timestamp,
                "role": "initiator" if is_outgoing else "recipient",
                "other_character_id": edge.target_node_id if is_outgoing else edge.source_node_id,
                "importance": edge.importance,
                "emotional_impact": edge.emotional_impact
            })

        return timeline

    async def find_connected_characters(
        self,
        character_id: int,
        depth: int = 1
    ) -> List[Dict[str, Any]]:
        """查找与角色直接关联的其他角色（可指定深度）"""
        if depth < 1:
            return []

        node = await self.get_node(character_id)
        if node is None:
            return []

        # BFS 查找关联角色
        visited = {character_id}
        queue = [(character_id, 0)]
        connected = []

        while queue:
            current_id, current_depth = queue.pop(0)

            if current_depth >= depth:
                continue

            # 获取所有关联边
            result = await self.db.execute(
                select(EventEdge).where(
                    or_(
                        EventEdge.source_node_id == current_id,
                        EventEdge.target_node_id == current_id
                    )
                )
            )
            edges = list(result.scalars().all())

            for edge in edges:
                other_id = edge.target_node_id if edge.source_node_id == current_id else edge.source_node_id

                if other_id not in visited:
                    visited.add(other_id)
                    other_node = await self.get_node(other_id)

                    if other_node:
                        connection_info = {
                            "character_id": other_id,
                            "character_name": other_node.name,
                            "role_type": other_node.role_type,
                            "relationship_type": edge.event_type,
                            "description": edge.description,
                            "chapter_number": edge.chapter_number,
                            "distance": current_depth + 1
                        }
                        connected.append(connection_info)
                        queue.append((other_id, current_depth + 1))

        return connected

    # ===== 情节分析 =====

    async def analyze_plot_threads(self) -> List[PlotThread]:
        """分析情节线索 - 识别独立的叙事线"""
        # 获取所有项目
        result = await self.db.execute(
            select(CharacterNode.project_id).distinct()
        )
        project_ids = list(result.scalars().all())

        all_threads = []

        for project_id in project_ids:
            threads = await self._analyze_project_threads(project_id)
            all_threads.extend(threads)

        return all_threads

    async def _analyze_project_threads(self, project_id: str) -> List[PlotThread]:
        """分析单个项目的情节线索"""
        nodes = await self.get_project_nodes(project_id)
        edges = await self.get_project_edges(project_id)

        if not nodes or not edges:
            return []

        # 构建邻接表
        adjacency = defaultdict(list)
        for edge in edges:
            adjacency[edge.source_node_id].append({
                "target_id": edge.target_node_id,
                "event_type": edge.event_type,
                "chapter_number": edge.chapter_number,
                "description": edge.description
            })

        # 使用 DFS 查找独立的情节线索
        visited = set()
        threads = []

        for node in nodes:
            if node.id not in visited:
                thread_events = []
                thread_characters = set()

                # DFS 遍历
                stack = [node.id]
                while stack:
                    current_id = stack.pop()
                    if current_id in visited:
                        continue
                    visited.add(current_id)

                    current_node = next((n for n in nodes if n.id == current_id), None)
                    if current_node:
                        thread_characters.add(current_node.name)

                    for edge_info in adjacency[current_id]:
                        target_id = edge_info["target_id"]
                        thread_events.append({
                            "from": current_id,
                            "to": target_id,
                            "event_type": edge_info["event_type"],
                            "chapter_number": edge_info["chapter_number"],
                            "description": edge_info["description"]
                        })
                        if target_id not in visited:
                            stack.append(target_id)

                if thread_events:
                    chapters = [e["chapter_number"] for e in thread_events if e["chapter_number"]]
                    chapter_range = (min(chapters), max(chapters)) if chapters else (0, 0)

                    thread = PlotThread(
                        thread_id=f"thread_{project_id}_{node.id}",
                        title=f"角色 {node.name} 的故事线",
                        characters=list(thread_characters),
                        events=thread_events,
                        chapter_range=chapter_range
                    )
                    threads.append(thread)

        return threads


    # --- Enhanced: Configurable node types ---
    
    _NODE_TYPE_REGISTRY: Dict[str, Dict[str, Any]] = {
        "character": {"label": "角色", "color": "#4f46e5", "icon": "person"},
        "location": {"label": "地点", "color": "#059669", "icon": "map-pin"},
        "faction": {"label": "势力", "color": "#dc2626", "icon": "shield"},
        "item": {"label": "物品", "color": "#d97706", "icon": "box"},
        "event": {"label": "事件", "color": "#7c3aed", "icon": "calendar"},
        "concept": {"label": "概念", "color": "#0891b2", "icon": "lightbulb"},
        "relationship": {"label": "关系", "color": "#db2777", "icon": "heart"},
        "timeline_node": {"label": "时间线", "color": "#4b5563", "icon": "clock"},
    }
    
    @classmethod
    def get_node_types(cls) -> dict:
        """Return all registered node types with labels and colors."""
        return dict(cls._NODE_TYPE_REGISTRY)
    
    @classmethod
    def register_node_type(cls, type_name: str, label: str, color: str, icon: str = "circle") -> None:
        """Register a custom node type for the knowledge graph."""
        cls._NODE_TYPE_REGISTRY[type_name] = {
            "label": label, "color": color, "icon": icon
        }
    
    async def batch_create_nodes(self, project_id: str, nodes: list) -> list:
        """Create multiple nodes in a single transaction for efficiency."""
        created = []
        for node_data in nodes:
            node = await self.create_node(
                project_id=project_id,
                name=node_data.get("name", ""),
                node_type=node_data.get("node_type", "character"),
                properties=node_data.get("properties", {}),
            )
            created.append(node)
        return created
    
    async def batch_create_edges(self, project_id: str, edges: list) -> list:
        """Create multiple edges in a single transaction."""
        created = []
        for edge_data in edges:
            edge = await self.create_edge(
                project_id=project_id,
                source_id=edge_data["source_id"],
                target_id=edge_data["target_id"],
                relationship=edge_data.get("relationship", "related_to"),
                properties=edge_data.get("properties", {}),
            )
            created.append(edge)
        return created
    
    async def export_graph(self, project_id: str, format: str = "json") -> Dict[str, Any]:
        """导出图谱数据"""
        graph = await self.get_project_graph(project_id)

        if format == "json":
            return graph

        # 可以扩展其他格式（如 graphml, gexf 等）
        return graph

    # ===== 辅助方法 =====

    async def _update_metadata(self, project_id: str) -> None:
        """更新图谱元数据"""
        # 检查是否已有元数据
        result = await self.db.execute(
            select(KnowledgeGraphMetadata).where(
                KnowledgeGraphMetadata.project_id == project_id
            )
        )
        metadata = result.scalar_one_or_none()

        # 统计节点和边数量
        nodes_result = await self.db.execute(
            select(CharacterNode).where(CharacterNode.project_id == project_id)
        )
        nodes = list(nodes_result.scalars().all())

        edges_result = await self.db.execute(
            select(EventEdge).where(EventEdge.project_id == project_id)
        )
        edges = list(edges_result.scalars().all())

        if metadata:
            metadata.node_count = len(nodes)
            metadata.edge_count = len(edges)
        else:
            metadata = KnowledgeGraphMetadata(
                project_id=project_id,
                node_count=len(nodes),
                edge_count=len(edges)
            )
            self.db.add(metadata)

        await self.db.commit()

    async def get_or_create_metadata(self, project_id: str) -> KnowledgeGraphMetadata:
        """获取或创建图谱元数据"""
        result = await self.db.execute(
            select(KnowledgeGraphMetadata).where(
                KnowledgeGraphMetadata.project_id == project_id
            )
        )
        metadata = result.scalar_one_or_none()

        if metadata is None:
            metadata = KnowledgeGraphMetadata(project_id=project_id)
            self.db.add(metadata)
            await self.db.commit()
            await self.db.refresh(metadata)

        return metadata
