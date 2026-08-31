"""Agent 会话消息范围的不可变摘要模型。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, event, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base
from .agent_context import AgentImmutableFactError


class ConversationSummary(Base):
    """A canonical, append-only summary over a contiguous AgentMessage sequence range."""

    __tablename__ = "agent_conversation_summaries"
    __table_args__ = (
        CheckConstraint("start_message_sequence >= 1", name="ck_agent_conversation_summary_start_sequence"),
        CheckConstraint("end_message_sequence >= start_message_sequence", name="ck_agent_conversation_summary_range"),
        CheckConstraint("message_count >= 1", name="ck_agent_conversation_summary_message_count"),
        UniqueConstraint("summary_id", name="uq_agent_conversation_summary_summary_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    summary_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    transaction_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    summary_kind: Mapped[str] = mapped_column(String(80), nullable=False, default="rolling", server_default="rolling", index=True)
    summarizer_id: Mapped[Optional[str]] = mapped_column(String(160), nullable=True, index=True)
    start_message_sequence: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    end_message_sequence: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    message_count: Mapped[int] = mapped_column(Integer, nullable=False)
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    digest: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    session: Mapped[Any] = relationship("AgentSession", foreign_keys=[session_id])
    run: Mapped[Optional[Any]] = relationship("AgentRun", foreign_keys=[run_id])


def _reject_update(_mapper: Any, _connection: Any, target: Any) -> None:
    raise AgentImmutableFactError(
        f"{type(target).__name__} is append-only; create a new fact instead of mutating a persisted record"
    )


event.listen(ConversationSummary, "before_update", _reject_update)
