"""Agent Run 的不可变计划修订模型。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, event, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base
from .agent_context import AgentImmutableFactError


class PlanRevision(Base):
    """An append-only planner output, optionally derived from a prior revision."""

    __tablename__ = "agent_plan_revisions"
    __table_args__ = (
        CheckConstraint("revision_number >= 1", name="ck_agent_plan_revision_number"),
        UniqueConstraint("revision_id", name="uq_agent_plan_revision_revision_id"),
        UniqueConstraint("run_id", "revision_number", name="uq_agent_plan_revision_run_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    revision_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[str] = mapped_column(
        ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    context_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("agent_context_snapshots.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    parent_revision_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("agent_plan_revisions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    correlation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    transaction_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    planner_id: Mapped[Optional[str]] = mapped_column(String(160), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="created", server_default="created", index=True)
    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    plan_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    digest: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    run: Mapped[Any] = relationship("AgentRun", foreign_keys=[run_id])
    session: Mapped[Any] = relationship("AgentSession", foreign_keys=[session_id])
    context_snapshot: Mapped[Any] = relationship("ContextSnapshot", back_populates="plan_revisions")
    parent_revision: Mapped[Optional["PlanRevision"]] = relationship(
        "PlanRevision", remote_side="PlanRevision.id", back_populates="child_revisions", foreign_keys=[parent_revision_id]
    )
    child_revisions: Mapped[list["PlanRevision"]] = relationship(
        "PlanRevision", back_populates="parent_revision", foreign_keys=[parent_revision_id]
    )


def _reject_update(_mapper: Any, _connection: Any, target: Any) -> None:
    raise AgentImmutableFactError(
        f"{type(target).__name__} is append-only; create a new fact instead of mutating a persisted record"
    )


event.listen(PlanRevision, "before_update", _reject_update)
