"""Agent Run 的不可变上下文快照与上下文引用模型。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint, event, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base


class AgentImmutableFactError(ValueError):
    """Raised when an append-only Agent fact is modified after persistence."""


class ContextSnapshot(Base):
    """A canonical, append-only context payload resolved for one Agent Run."""

    __tablename__ = "agent_context_snapshots"
    __table_args__ = (
        UniqueConstraint("snapshot_id", name="uq_agent_context_snapshot_snapshot_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    snapshot_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[str] = mapped_column(
        ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    correlation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    transaction_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    context_kind: Mapped[str] = mapped_column(String(80), nullable=False, default="run_context", server_default="run_context", index=True)
    context_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    digest: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    run: Mapped[Any] = relationship("AgentRun", foreign_keys=[run_id])
    session: Mapped[Any] = relationship("AgentSession", foreign_keys=[session_id])
    refs: Mapped[list["ContextSnapshotRef"]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan", order_by="ContextSnapshotRef.ref_order"
    )
    plan_revisions: Mapped[list[Any]] = relationship("PlanRevision", back_populates="context_snapshot")


class ContextSnapshotRef(Base):
    """A normalized immutable reference included in a ContextSnapshot."""

    __tablename__ = "agent_context_snapshot_refs"
    __table_args__ = (
        CheckConstraint("ref_order >= 0", name="ck_agent_context_snapshot_ref_order"),
        UniqueConstraint("context_snapshot_id", "ref_order", name="uq_agent_context_snapshot_ref_order"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    context_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("agent_context_snapshots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ref_order: Mapped[int] = mapped_column(Integer, nullable=False)
    ref_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    ref_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    ref_version: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    role: Mapped[Optional[str]] = mapped_column(String(80), nullable=True, index=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    digest: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    snapshot: Mapped[ContextSnapshot] = relationship(back_populates="refs")


def _reject_update(_mapper: Any, _connection: Any, target: Any) -> None:
    raise AgentImmutableFactError(
        f"{type(target).__name__} is append-only; create a new fact instead of mutating a persisted record"
    )


for _immutable_type in (ContextSnapshot, ContextSnapshotRef):
    event.listen(_immutable_type, "before_update", _reject_update)
