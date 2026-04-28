"""
知识图谱服务层

提供知识图谱的 CRUD 操作、关系查询和情节分析功能。
将角色视为对象，情节视为有向图，实现复杂的叙事关系追踪。
"""
from typing import Optional, List, Dict, Any
from collections import defaultdict
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_

from ..models.knowledge_graph import CharacterNode, EventEdge, KnowledgeGraphMetadata
from ..models.novel import BlueprintCharacter
from ..models.memory_layer import CharacterState, TimelineEvent

logger = logging.getLogger(__name__)


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

        blueprint_result = await self.db.execute(
            select(BlueprintCharacter)
            .where(BlueprintCharacter.project_id == project_id)
            .order_by(BlueprintCharacter.position.asc(), BlueprintCharacter.id.asc())
        )
        blueprint_characters = list(blueprint_result.scalars().all())

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
                    )
                    self.db.add(edge)
                    edge_keys.add(key)
                    created_edges += 1

        await self.db.commit()
        await self._update_metadata(project_id)
        return {"created_nodes": created_nodes, "created_edges": created_edges}

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

        # 构建节点映射
        node_map = {node.id: node for node in nodes}

        # 序列化节点
        nodes_data = []
        for node in nodes:
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
                "created_at": node.created_at.isoformat() if node.created_at else None,
                "updated_at": node.updated_at.isoformat() if node.updated_at else None
            })

        # 序列化边
        edges_data = []
        for edge in edges:
            source_node = node_map.get(edge.source_node_id)
            target_node = node_map.get(edge.target_node_id)
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
