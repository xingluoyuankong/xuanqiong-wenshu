"""
知识图谱数据模型

知识图谱叙事引擎用于管理小说中的角色和事件关系：
- CharacterNode: 角色节点（角色作为对象）
- EventEdge: 事件边（情节作为有向图）
- KnowledgeGraph: 知识图谱（完整的图结构）

角色视为对象，情节视为有向图边，实现复杂的叙事关系追踪。
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base

LONG_TEXT_TYPE = Text().with_variant(LONGTEXT, "mysql")


class CharacterNode(Base):
    """角色节点 - 将角色视为知识图谱中的节点对象

    用于存储角色的详细信息、属性和特征，作为图谱中的实体。
    """

    __tablename__ = "character_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("novel_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # ===== 基础信息 =====
    name: Mapped[str] = mapped_column(String(255), nullable=False)  # 角色名称
    role_type: Mapped[Optional[str]] = mapped_column(String(64))  # 角色类型（主角/反派/配角/龙套等）
    description: Mapped[Optional[str]] = mapped_column(LONG_TEXT_TYPE)  # 角色描述

    # ===== 角色属性 =====
    traits: Mapped[Optional[list]] = mapped_column(JSON)  # 性格特征列表
    goals: Mapped[Optional[list]] = mapped_column(JSON)  # 角色目标列表
    fears: Mapped[Optional[list]] = mapped_column(JSON)  # 角色恐惧/弱点
    background: Mapped[Optional[str]] = mapped_column(Text)  # 角色背景故事

    # ===== 角色状态 =====
    status: Mapped[Optional[str]] = mapped_column(String(64))  # 当前状态（ alive/dead/unknown）
    location: Mapped[Optional[str]] = mapped_column(String(255))  # 当前所在位置
    emotional_state: Mapped[Optional[str]] = mapped_column(String(128))  # 当前情感状态

    # ===== 关系映射 =====
    # 与 blueprint_characters 的关联（可选，用于同步）
    blueprint_character_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("blueprint_characters.id", ondelete="SET NULL"), nullable=True
    )

    # ===== 元数据 =====
    extra: Mapped[Optional[dict]] = mapped_column(JSON)  # 扩展字段
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 关联：出边（作为事件发起者）
    outgoing_edges: Mapped[List["EventEdge"]] = relationship(
        "EventEdge",
        foreign_keys="EventEdge.source_node_id",
        back_populates="source_node",
        cascade="all, delete-orphan"
    )

    # 关联：入边（作为事件接收者）
    incoming_edges: Mapped[List["EventEdge"]] = relationship(
        "EventEdge",
        foreign_keys="EventEdge.target_node_id",
        back_populates="target_node",
        cascade="all, delete-orphan"
    )


class EventEdge(Base):
    """事件边 - 将情节视为知识图谱中的有向边

    表示角色之间的交互事件，形成情节的有向图结构。
    """

    __tablename__ = "event_edges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("novel_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # ===== 边两端 =====
    source_node_id: Mapped[int] = mapped_column(
        ForeignKey("character_nodes.id", ondelete="CASCADE"), nullable=False
    )
    target_node_id: Mapped[int] = mapped_column(
        ForeignKey("character_nodes.id", ondelete="CASCADE"), nullable=False
    )

    # ===== 事件属性 =====
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)  # 事件类型
    # 可选值：conversation（对话）, conflict（冲突）, alliance（结盟）,
    #        betrayal（背叛）, meeting（相遇）, separation（分离）,
    #        action（行动）, transformation（转变）, death（死亡）

    description: Mapped[Optional[str]] = mapped_column(LONG_TEXT_TYPE)  # 事件详细描述
    chapter_number: Mapped[Optional[int]] = mapped_column(Integer)  # 发生在哪一章
    scene_number: Mapped[Optional[int]] = mapped_column(Integer)  # 场景序号

    # ===== 时间和因果 =====
    timestamp: Mapped[Optional[str]] = mapped_column(String(255))  # 故事内时间（如：第一天早晨）
    order_index: Mapped[Optional[int]] = mapped_column(Integer, default=0)  # 事件顺序索引
    causality: Mapped[Optional[str]] = mapped_column(Text)  # 因果关系说明

    # ===== 事件影响 =====
    importance: Mapped[Optional[int]] = mapped_column(Integer, default=5)  # 重要性 1-10
    emotional_impact: Mapped[Optional[str]] = mapped_column(String(64))  # 情感影响
    plot_advancement: Mapped[Optional[str]] = mapped_column(String(64))  # 情节推进程度

    # ===== 元数据 =====
    extra: Mapped[Optional[dict]] = mapped_column(JSON)  # 扩展字段
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 关联：源节点
    source_node: Mapped["CharacterNode"] = relationship(
        "CharacterNode",
        foreign_keys=[source_node_id],
        back_populates="outgoing_edges"
    )

    # 关联：目标节点
    target_node: Mapped["CharacterNode"] = relationship(
        "CharacterNode",
        foreign_keys=[target_node_id],
        back_populates="incoming_edges"
    )


class KnowledgeGraphMetadata(Base):
    """知识图谱元数据 - 存储图谱的整体信息"""

    __tablename__ = "knowledge_graph_metadata"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("novel_projects.id", ondelete="CASCADE"), nullable=False, index=True, unique=True
    )

    # ===== 图谱信息 =====
    name: Mapped[Optional[str]] = mapped_column(String(255))  # 图谱名称
    description: Mapped[Optional[str]] = mapped_column(Text)  # 图谱描述

    # ===== 统计信息 =====
    node_count: Mapped[Optional[int]] = mapped_column(Integer, default=0)  # 节点数量
    edge_count: Mapped[Optional[int]] = mapped_column(Integer, default=0)  # 边数量
    story_start_chapter: Mapped[Optional[int]] = mapped_column(Integer)  # 故事起始章节
    story_end_chapter: Mapped[Optional[int]] = mapped_column(Integer)  # 故事结束章节

    # ===== 分析结果缓存 =====
    plot_threads_cache: Mapped[Optional[dict]] = mapped_column(JSON)  # 情节线索缓存
    character_arcs_cache: Mapped[Optional[dict]] = mapped_column(JSON)  # 角色弧线缓存

    # ===== 元数据 =====
    extra: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())