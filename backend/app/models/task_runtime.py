"""持久化任务运行时模型。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, BigInteger, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base


class TaskRuntime(Base):
    """可恢复的任务状态记录。"""

    __tablename__ = "task_runtime_tasks"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_task_runtime_idempotency_key"),)

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    # Legacy jobs have no reliable Agent parent. Agent-originated jobs explicitly inherit it.
    correlation_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    chapter_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    task_type: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    input_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    config_snapshot_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    artifact_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    artifact_revision: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued", index=True)
    stage: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    event_cursor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    lease_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_owner: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    heartbeat_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    elapsed_ms: Mapped[Optional[int]] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), nullable=True)
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(96), nullable=True)
    error_detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    events: Mapped[list["TaskRuntimeEvent"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="TaskRuntimeEvent.event_id"
    )


class TaskRuntimeEvent(Base):
    """任务事件历史，event_id 同时作为可恢复游标。"""

    __tablename__ = "task_runtime_events"
    __table_args__ = (UniqueConstraint("task_id", "idempotency_key", name="uq_task_runtime_event_idempotency"),)

    event_id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(64), ForeignKey("task_runtime_tasks.task_id", ondelete="CASCADE"), nullable=False, index=True)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    status: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    stage: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    progress: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    lease_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    channel: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    sequence: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    task: Mapped[TaskRuntime] = relationship(back_populates="events")