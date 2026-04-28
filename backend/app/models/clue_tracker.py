# 推理小说线索追踪 - 数据模型
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base

LONG_TEXT_TYPE = Text().with_variant(LONGTEXT, "mysql")


class ClueType(str, Enum):
    """线索类型"""
    KEY_EVIDENCE = "key_evidence"      # 关键证物
    MYSTERIOUS_EVENT = "mysterious_event"  # 神秘事件
    CHARACTER_SECRET = "character_secret"  # 人物秘密
    TIMELINE = "timeline"              # 时间线
    RED_HERRING = "red_herring"        # 红鲱鱼（误导线索）
    PLOT_HOOK = "plot_hook"            # 情节钩子


class ClueStatus(str, Enum):
    """线索状态"""
    ACTIVE = "active"          # 埋下但未回收
    RESOLVED = "resolved"      # 已回收/揭示
    RED_HERRING = "red_herring"  # 红鲱鱼
    ABANDONED = "abandoned"    # 放弃/未使用


class ClueAppearanceType(str, Enum):
    """线索在章节中的出现类型"""
    MENTION = "mention"        # 提及
    REVEAL = "reveal"          # 揭示
    CLUE_HINTS = "clue_hints"  # 暗示
    RESOLUTION = "resolution"  # 回收/解决


class StoryClue(Base):
    """故事线索 - 追踪推理小说中的伏笔和线索"""

    __tablename__ = "story_clues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("novel_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # ===== 线索基础信息 =====
    name: Mapped[str] = mapped_column(String(255), nullable=False)  # 线索名称
    clue_type: Mapped[str] = mapped_column(String(32), nullable=False)  # 线索类型
    description: Mapped[Optional[str]] = mapped_column(LONG_TEXT_TYPE)  # 线索描述
    importance: Mapped[int] = mapped_column(Integer, default=3)  # 重要程度 1-5

    # ===== 章节信息 =====
    planted_chapter: Mapped[Optional[int]] = mapped_column(Integer)  # 埋下线索的章节
    resolution_chapter: Mapped[Optional[int]] = mapped_column(Integer)  # 回收线索的章节

    # ===== 状态 =====
    status: Mapped[str] = mapped_column(String(32), default=ClueStatus.ACTIVE.value)

    # ===== 红鲱鱼标记 =====
    is_red_herring: Mapped[bool] = mapped_column(default=False)  # 是否为红鲱鱼
    red_herring_explanation: Mapped[Optional[str]] = mapped_column(Text)  # 红鲱鱼设计说明

    # ===== 线索内容 =====
    clue_content: Mapped[Optional[str]] = mapped_column(Text)  # 线索具体内容
    hint_level: Mapped[Optional[int]] = mapped_column(Integer, default=2)  # 暗示程度 1-5

    # ===== 设计意图 =====
    design_intent: Mapped[Optional[str]] = mapped_column(Text)  # 设计意图说明

    # ===== 时间戳 =====
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 关联：章节关联
    chapter_links: Mapped[List["ClueChapterLink"]] = relationship(
        "ClueChapterLink",
        back_populates="clue",
        cascade="all, delete-orphan"
    )


class ClueChapterLink(Base):
    """线索与章节的关联 - 追踪线索在哪些章节出现"""

    __tablename__ = "clue_chapter_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    clue_id: Mapped[int] = mapped_column(
        ForeignKey("story_clues.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chapter_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True, index=True
    )
    chapter_number: Mapped[Optional[int]] = mapped_column(Integer)  # 章节序号

    # ===== 出现信息 =====
    appearance_type: Mapped[str] = mapped_column(String(32), nullable=False)  # 出现类型
    content_excerpt: Mapped[Optional[str]] = mapped_column(LONG_TEXT_TYPE)  # 相关内容摘录

    # ===== 详细程度 =====
    detail_level: Mapped[Optional[int]] = mapped_column(Integer, default=3)  # 详细程度 1-5

    # ===== 章节角色 =====
    chapter_role: Mapped[Optional[str]] = mapped_column(String(32))  # 章节中扮演的角色：setup/reveal/resolution

    # ===== 时间戳 =====
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # 关联
    clue: Mapped["StoryClue"] = relationship("StoryClue", back_populates="chapter_links")


class ClueThread(Base):
    """线索网络 - 追踪线索之间的关系"""

    __tablename__ = "clue_threads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("novel_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # ===== 线索网络信息 =====
    thread_name: Mapped[str] = mapped_column(String(255))  # 线索网络名称
    description: Mapped[Optional[str]] = mapped_column(Text)  # 描述

    # ===== 包含的线索 =====
    clue_ids: Mapped[Optional[list]] = mapped_column(JSON)  # 线索ID列表

    # ===== 网络类型 =====
    thread_type: Mapped[Optional[str]] = mapped_column(String(32))  # main_arc/sub_plot/red_herring

    # ===== 分析结果 =====
    analysis_result: Mapped[Optional[dict]] = mapped_column(JSON)  # 分析结果缓存

    # ===== 时间戳 =====
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())