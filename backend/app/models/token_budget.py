# Token 预算管理数据模型
from __future__ import annotations

from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base


class TokenBudget(Base):
    """Token 预算配置 - 项目级的预算上限和模块分配"""

    __tablename__ = "token_budgets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("novel_projects.id", ondelete="CASCADE"), nullable=False, index=True, unique=True
    )

    # ===== 预算配置 =====
    total_budget: Mapped[float] = mapped_column(Float, default=100.0)  # 总预算（人民币）
    chapter_budget: Mapped[float] = mapped_column(Float, default=5.0)  # 单章节预算

    # ===== 模块分配比例（百分比，总和应为100） =====
    # 默认分配：世界观20%、角色15%、大纲10%、正文55%
    module_allocation: Mapped[Optional[dict]] = mapped_column(JSON, default=lambda: {
        "world": 20,
        "character": 15,
        "outline": 10,
        "content": 55
    })

    # ===== 预警设置 =====
    warning_threshold: Mapped[float] = mapped_column(Float, default=80.0)  # 预警阈值（百分比）

    # ===== 额外字段 =====
    extra: Mapped[Optional[dict]] = mapped_column(JSON)

    # ===== 时间戳 =====
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class TokenUsage(Base):
    """Token 使用记录 - 追踪每个功能模块的实际消耗"""

    __tablename__ = "token_usages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("novel_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chapter_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # ===== 使用信息 =====
    module: Mapped[str] = mapped_column(String(32), nullable=False)  # 模块：world/character/outline/content
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)  # 使用的 Token 数量
    cost: Mapped[float] = mapped_column(Float, default=0.0)  # 花费（人民币）
    model_name: Mapped[Optional[str]] = mapped_column(String(64))  # 使用的模型名称

    # ===== 上下文 =====
    operation_type: Mapped[Optional[str]] = mapped_column(String(32))  # 操作类型：generation/optimization/extraction
    description: Mapped[Optional[str]] = mapped_column(Text)  # 操作描述

    # ===== 时间戳 =====
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TokenBudgetAlert(Base):
    """Token 预算预警记录"""

    __tablename__ = "token_budget_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("novel_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # ===== 预警信息 =====
    alert_type: Mapped[str] = mapped_column(String(32), nullable=False)  # 预警类型：warning/critical/exceeded
    threshold_percent: Mapped[float] = mapped_column(Float)  # 触发时的阈值百分比
    current_usage: Mapped[float] = mapped_column(Float)  # 触发时的使用量
    budget_limit: Mapped[float] = mapped_column(Float)  # 预算上限

    # ===== 预警消息 =====
    message: Mapped[Optional[str]] = mapped_column(Text)

    # ===== 处理状态 =====
    is_resolved: Mapped[bool] = mapped_column(default=False)  # 是否已处理
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # ===== 时间戳 =====
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())