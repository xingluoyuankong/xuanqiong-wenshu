# AIMETA P=知识图谱API_角色节点和事件边管理|R=图谱CRUD_关系查询_情节分析|NR=不含前端展示|E=route:GET_POST_/api/projects/*/knowledge-graph|X=http|A=知识图谱|D=fastapi,sqlalchemy|S=db|RD=./README.ai
"""知识图谱 API 接口

将角色视为对象，情节视为有向图，实现复杂的叙事关系追踪。
"""
import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.session import get_session
from ...services.knowledge_graph_service import KnowledgeGraphService, PlotThread
from ...services.novel_service import NovelService
from ...core.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["knowledge-graph"])


# Pydantic 模型
from pydantic import BaseModel


class CharacterNodeCreate(BaseModel):
    """创建角色节点请求"""
    name: str
    role_type: Optional[str] = None
    description: Optional[str] = None
    traits: Optional[List[str]] = None
    goals: Optional[List[str]] = None
    fears: Optional[List[str]] = None
    background: Optional[str] = None
    status: Optional[str] = "alive"
    location: Optional[str] = None
    emotional_state: Optional[str] = None
    blueprint_character_id: Optional[int] = None
    extra: Optional[dict] = None


class CharacterNodeUpdate(BaseModel):
    """更新角色节点请求"""
    name: Optional[str] = None
    role_type: Optional[str] = None
    description: Optional[str] = None
    traits: Optional[List[str]] = None
    goals: Optional[List[str]] = None
    fears: Optional[List[str]] = None
    background: Optional[str] = None
    status: Optional[str] = None
    location: Optional[str] = None
    emotional_state: Optional[str] = None
    extra: Optional[dict] = None


class CharacterNodeResponse(BaseModel):
    """角色节点响应"""
    id: int
    project_id: str
    name: str
    role_type: Optional[str]
    description: Optional[str]
    traits: List[str]
    goals: List[str]
    fears: List[str]
    background: Optional[str]
    status: Optional[str]
    location: Optional[str]
    emotional_state: Optional[str]
    blueprint_character_id: Optional[int]
    extra: Optional[dict]
    created_at: str
    updated_at: str


class EventEdgeCreate(BaseModel):
    """创建事件边请求"""
    source_node_id: int
    target_node_id: int
    event_type: str
    description: Optional[str] = None
    chapter_number: Optional[int] = None
    scene_number: Optional[int] = None
    timestamp: Optional[str] = None
    order_index: Optional[int] = 0
    causality: Optional[str] = None
    importance: Optional[int] = 5
    emotional_impact: Optional[str] = None
    plot_advancement: Optional[str] = None
    extra: Optional[dict] = None


class EventEdgeUpdate(BaseModel):
    """更新事件边请求"""
    source_node_id: Optional[int] = None
    target_node_id: Optional[int] = None
    event_type: Optional[str] = None
    description: Optional[str] = None
    chapter_number: Optional[int] = None
    scene_number: Optional[int] = None
    timestamp: Optional[str] = None
    order_index: Optional[int] = None
    causality: Optional[str] = None
    importance: Optional[int] = None
    emotional_impact: Optional[str] = None
    plot_advancement: Optional[str] = None
    extra: Optional[dict] = None


class EventEdgeResponse(BaseModel):
    """事件边响应"""
    id: int
    project_id: str
    source_id: int
    target_id: int
    source_name: Optional[str]
    target_name: Optional[str]
    event_type: str
    description: Optional[str]
    chapter_number: Optional[int]
    scene_number: Optional[int]
    timestamp: Optional[str]
    order_index: Optional[int]
    causality: Optional[str]
    importance: Optional[int]
    emotional_impact: Optional[str]
    plot_advancement: Optional[str]
    extra: Optional[dict]
    created_at: str
    updated_at: str


class KnowledgeGraphResponse(BaseModel):
    """完整图谱响应"""
    project_id: str
    nodes: List[CharacterNodeResponse]
    edges: List[EventEdgeResponse]
    node_count: int
    edge_count: int


class CharacterTimelineResponse(BaseModel):
    """角色时间线响应"""
    character_id: int
    character_name: str
    events: List[dict]


class PlotThreadResponse(BaseModel):
    """情节线索响应"""
    thread_id: str
    title: str
    characters: List[str]
    events: List[dict]
    chapter_range: tuple


@router.post("/{project_id}/knowledge-graph/nodes", response_model=CharacterNodeResponse)
async def create_graph_node(
    project_id: str,
    data: CharacterNodeCreate,
    session: AsyncSession = Depends(get_session),
    current_user = Depends(get_current_user),
):
    """创建角色节点"""
    try:
        novel_service = NovelService(session)
        await novel_service.ensure_project_owner(project_id, current_user.id)
        service = KnowledgeGraphService(session)
        node = await service.create_node(
            project_id=project_id,
            character_data=data.model_dump(exclude_none=True)
        )

        return CharacterNodeResponse(
            id=node.id,
            project_id=node.project_id,
            name=node.name,
            role_type=node.role_type,
            description=node.description,
            traits=node.traits or [],
            goals=node.goals or [],
            fears=node.fears or [],
            background=node.background,
            status=node.status,
            location=node.location,
            emotional_state=node.emotional_state,
            blueprint_character_id=node.blueprint_character_id,
            extra=node.extra,
            created_at=node.created_at.isoformat() if node.created_at else "",
            updated_at=node.updated_at.isoformat() if node.updated_at else ""
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建角色节点失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{project_id}/knowledge-graph/nodes", response_model=List[CharacterNodeResponse])
async def get_graph_nodes(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user = Depends(get_current_user),
):
    """获取项目的所有角色节点"""
    try:
        novel_service = NovelService(session)
        await novel_service.ensure_project_owner(project_id, current_user.id)
        service = KnowledgeGraphService(session)
        nodes = await service.get_project_nodes(project_id)

        return [
            CharacterNodeResponse(
                id=node.id,
                project_id=node.project_id,
                name=node.name,
                role_type=node.role_type,
                description=node.description,
                traits=node.traits or [],
                goals=node.goals or [],
                fears=node.fears or [],
                background=node.background,
                status=node.status,
                location=node.location,
                emotional_state=node.emotional_state,
                blueprint_character_id=node.blueprint_character_id,
                extra=node.extra,
                created_at=node.created_at.isoformat() if node.created_at else "",
                updated_at=node.updated_at.isoformat() if node.updated_at else ""
            )
            for node in nodes
        ]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取角色节点失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{project_id}/knowledge-graph/nodes/{node_id}", response_model=CharacterNodeResponse)
async def update_graph_node(
    project_id: str,
    node_id: int,
    data: CharacterNodeUpdate,
    session: AsyncSession = Depends(get_session),
    current_user = Depends(get_current_user),
):
    """更新角色节点"""
    try:
        novel_service = NovelService(session)
        await novel_service.ensure_project_owner(project_id, current_user.id)
        service = KnowledgeGraphService(session)
        current_node = await service.get_node(node_id)
        if current_node is None or current_node.project_id != project_id:
            raise HTTPException(status_code=404, detail="角色节点不存在")

        node = await service.update_node(node_id, data.model_dump(exclude_none=True))

        return CharacterNodeResponse(
            id=node.id,
            project_id=node.project_id,
            name=node.name,
            role_type=node.role_type,
            description=node.description,
            traits=node.traits or [],
            goals=node.goals or [],
            fears=node.fears or [],
            background=node.background,
            status=node.status,
            location=node.location,
            emotional_state=node.emotional_state,
            blueprint_character_id=node.blueprint_character_id,
            extra=node.extra,
            created_at=node.created_at.isoformat() if node.created_at else "",
            updated_at=node.updated_at.isoformat() if node.updated_at else ""
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新角色节点失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{project_id}/knowledge-graph/nodes/{node_id}")
async def delete_graph_node(
    project_id: str,
    node_id: int,
    session: AsyncSession = Depends(get_session),
    current_user = Depends(get_current_user),
):
    """删除角色节点（级联删除相关边）"""
    try:
        novel_service = NovelService(session)
        await novel_service.ensure_project_owner(project_id, current_user.id)
        service = KnowledgeGraphService(session)
        node = await service.get_node(node_id)
        if node is None or node.project_id != project_id:
            raise HTTPException(status_code=404, detail="角色节点不存在")

        success = await service.delete_node(node_id)

        return {"message": "角色节点已删除", "node_id": node_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除角色节点失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{project_id}/knowledge-graph/edges", response_model=EventEdgeResponse)
async def create_graph_edge(
    project_id: str,
    data: EventEdgeCreate,
    session: AsyncSession = Depends(get_session),
    current_user = Depends(get_current_user),
):
    """创建事件边"""
    try:
        novel_service = NovelService(session)
        await novel_service.ensure_project_owner(project_id, current_user.id)
        service = KnowledgeGraphService(session)

        # 验证源节点和目标节点存在且属于当前项目
        source_node = await service.get_node(data.source_node_id)
        target_node = await service.get_node(data.target_node_id)

        if source_node is None or source_node.project_id != project_id:
            raise HTTPException(status_code=404, detail="源角色节点不存在")
        if target_node is None or target_node.project_id != project_id:
            raise HTTPException(status_code=404, detail="目标角色节点不存在")

        edge = await service.create_edge(
            project_id=project_id,
            event_data=data.model_dump(exclude_none=True)
        )

        return EventEdgeResponse(
            id=edge.id,
            project_id=edge.project_id,
            source_id=edge.source_node_id,
            target_id=edge.target_node_id,
            source_name=source_node.name,
            target_name=target_node.name,
            event_type=edge.event_type,
            description=edge.description,
            chapter_number=edge.chapter_number,
            scene_number=edge.scene_number,
            timestamp=edge.timestamp,
            order_index=edge.order_index,
            causality=edge.causality,
            importance=edge.importance,
            emotional_impact=edge.emotional_impact,
            plot_advancement=edge.plot_advancement,
            extra=edge.extra,
            created_at=edge.created_at.isoformat() if edge.created_at else "",
            updated_at=edge.updated_at.isoformat() if edge.updated_at else ""
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建事件边失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{project_id}/knowledge-graph/edges", response_model=List[EventEdgeResponse])
async def get_graph_edges(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user = Depends(get_current_user),
):
    """获取项目的所有事件边"""
    try:
        novel_service = NovelService(session)
        await novel_service.ensure_project_owner(project_id, current_user.id)
        service = KnowledgeGraphService(session)
        edges = await service.get_project_edges(project_id)

        # 获取节点名称映射
        nodes = await service.get_project_nodes(project_id)
        node_names = {node.id: node.name for node in nodes}

        return [
            EventEdgeResponse(
                id=edge.id,
                project_id=edge.project_id,
                source_id=edge.source_node_id,
                target_id=edge.target_node_id,
                source_name=node_names.get(edge.source_node_id),
                target_name=node_names.get(edge.target_node_id),
                event_type=edge.event_type,
                description=edge.description,
                chapter_number=edge.chapter_number,
                scene_number=edge.scene_number,
                timestamp=edge.timestamp,
                order_index=edge.order_index,
                causality=edge.causality,
                importance=edge.importance,
                emotional_impact=edge.emotional_impact,
                plot_advancement=edge.plot_advancement,
                extra=edge.extra,
                created_at=edge.created_at.isoformat() if edge.created_at else "",
                updated_at=edge.updated_at.isoformat() if edge.updated_at else ""
            )
            for edge in edges
        ]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取事件边失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{project_id}/knowledge-graph/edges/{edge_id}")
async def delete_graph_edge(
    project_id: str,
    edge_id: int,
    session: AsyncSession = Depends(get_session),
    current_user = Depends(get_current_user),
):
    """删除事件边"""
    try:
        novel_service = NovelService(session)
        await novel_service.ensure_project_owner(project_id, current_user.id)
        service = KnowledgeGraphService(session)
        edge = await service.get_edge(edge_id)
        if edge is None or edge.project_id != project_id:
            raise HTTPException(status_code=404, detail="事件边不存在")

        await service.delete_edge(edge_id)
        return {"message": "事件边已删除", "edge_id": edge_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除事件边失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{project_id}/knowledge-graph", response_model=KnowledgeGraphResponse)
async def get_full_graph(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user = Depends(get_current_user),
):
    """获取完整知识图谱"""
    try:
        novel_service = NovelService(session)
        await novel_service.ensure_project_owner(project_id, current_user.id)
        service = KnowledgeGraphService(session)
        await service.sync_from_story_memory(project_id)
        graph_data = await service.get_project_graph(project_id)

        # 转换节点
        nodes = [
            CharacterNodeResponse(
                id=node["id"],
                project_id=node["project_id"],
                name=node["name"],
                role_type=node["role_type"],
                description=node["description"],
                traits=node["traits"],
                goals=node["goals"],
                fears=node["fears"],
                background=node["background"],
                status=node["status"],
                location=node["location"],
                emotional_state=node["emotional_state"],
                blueprint_character_id=node["blueprint_character_id"],
                extra=node["extra"],
                created_at=node["created_at"] or "",
                updated_at=node["updated_at"] or ""
            )
            for node in graph_data["nodes"]
        ]

        # 转换边
        edges = [
            EventEdgeResponse(
                id=edge["id"],
                project_id=project_id,
                source_id=edge["source_id"],
                target_id=edge["target_id"],
                source_name=edge["source_name"],
                target_name=edge["target_name"],
                event_type=edge["event_type"],
                description=edge["description"],
                chapter_number=edge["chapter_number"],
                scene_number=edge["scene_number"],
                timestamp=edge["timestamp"],
                order_index=edge["order_index"],
                causality=edge["causality"],
                importance=edge["importance"],
                emotional_impact=edge["emotional_impact"],
                plot_advancement=edge["plot_advancement"],
                extra=edge["extra"],
                created_at=edge["created_at"] or "",
                updated_at=edge["updated_at"] or ""
            )
            for edge in graph_data["edges"]
        ]

        return KnowledgeGraphResponse(
            project_id=project_id,
            nodes=nodes,
            edges=edges,
            node_count=graph_data["node_count"],
            edge_count=graph_data["edge_count"]
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取完整图谱失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{project_id}/knowledge-graph/character/{character_id}/timeline")
async def get_character_timeline(
    project_id: str,
    character_id: int,
    session: AsyncSession = Depends(get_session),
    current_user = Depends(get_current_user),
):
    """获取角色时间线"""
    try:
        novel_service = NovelService(session)
        await novel_service.ensure_project_owner(project_id, current_user.id)
        service = KnowledgeGraphService(session)
        node = await service.get_node(character_id)
        if node is None or node.project_id != project_id:
            raise HTTPException(status_code=404, detail="角色节点不存在")

        timeline = await service.get_character_timeline(character_id)

        return CharacterTimelineResponse(
            character_id=character_id,
            character_name=node.name,
            events=timeline
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取角色时间线失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{project_id}/knowledge-graph/connected/{character_id}")
async def get_connected_characters(
    project_id: str,
    character_id: int,
    depth: int = Query(1, ge=1, le=3),
    session: AsyncSession = Depends(get_session),
    current_user = Depends(get_current_user),
):
    """获取与角色关联的其他角色"""
    try:
        novel_service = NovelService(session)
        await novel_service.ensure_project_owner(project_id, current_user.id)
        service = KnowledgeGraphService(session)
        node = await service.get_node(character_id)
        if node is None or node.project_id != project_id:
            raise HTTPException(status_code=404, detail="角色节点不存在")
        connected = await service.find_connected_characters(character_id, depth)

        return {
            "character_id": character_id,
            "depth": depth,
            "connected_characters": connected
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取关联角色失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{project_id}/knowledge-graph/threads")
async def analyze_plot_threads(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user = Depends(get_current_user),
):
    """分析情节线索"""
    try:
        novel_service = NovelService(session)
        await novel_service.ensure_project_owner(project_id, current_user.id)
        service = KnowledgeGraphService(session)

        # 分析当前项目的情节线索
        threads = await service._analyze_project_threads(project_id)

        return {
            "project_id": project_id,
            "threads": [thread.to_dict() for thread in threads],
            "thread_count": len(threads)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"分析情节线索失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{project_id}/knowledge-graph/export")
async def export_graph(
    project_id: str,
    format: str = Query("json", pattern="^(json|graphml)$"),
    session: AsyncSession = Depends(get_session),
    current_user = Depends(get_current_user),
):
    """导出图谱数据"""
    try:
        novel_service = NovelService(session)
        await novel_service.ensure_project_owner(project_id, current_user.id)
        service = KnowledgeGraphService(session)
        export_data = await service.export_graph(project_id, format)

        return export_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"导出图谱失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
