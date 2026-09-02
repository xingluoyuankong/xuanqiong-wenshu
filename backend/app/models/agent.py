"""持久化 Agent 会话、运行、事件和审批模型。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base


class AgentSession(Base):
    __tablename__ = "agent_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[Optional[str]] = mapped_column(ForeignKey("novel_projects.id", ondelete="CASCADE"), nullable=True, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    messages: Mapped[list["AgentMessage"]] = relationship(back_populates="session", cascade="all, delete-orphan", order_by="AgentMessage.sequence")
    runs: Mapped[list["AgentRun"]] = relationship(back_populates="session", cascade="all, delete-orphan", order_by="AgentRun.created_at")


class AgentMessage(Base):
    __tablename__ = "agent_messages"
    __table_args__ = (UniqueConstraint("session_id", "sequence", name="uq_agent_message_sequence"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(24), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    session: Mapped[AgentSession] = relationship(back_populates="messages")


class AgentRun(Base):
    __tablename__ = "agent_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    # Stable trace identifier shared by every durable record caused by this run.
    # It is intentionally distinct from run_id for future TaskRuntime fan-out.
    correlation_id: Mapped[str] = mapped_column(String(36), nullable=False, default=lambda: str(uuid4()), unique=True, index=True)
    transaction_id: Mapped[str] = mapped_column(String(36), nullable=False, default=lambda: str(uuid4()), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="created", index=True)
    current_phase: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    current_step: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # Atomic source of the next visible event sequence for this Run.
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # Optimistic concurrency version for durable Run commands and UI refreshes.
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    pause_reason: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    resume_target_status: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    # Latest safe, user-visible work summary.  The full activity remains in
    # AgentEventRecord; this checkpoint lets the state endpoint recover the
    # current action without scanning the complete event ledger.
    latest_public_summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    latest_public_summary_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    latest_public_summary_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    context_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    lease_owner: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    # Monotonic claim fence; increments on every successful lease acquisition.
    lease_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    cancel_requested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    cancel_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    session: Mapped[AgentSession] = relationship(back_populates="runs")
    events: Mapped[list["AgentEventRecord"]] = relationship(back_populates="run", cascade="all, delete-orphan", order_by="AgentEventRecord.sequence")
    steps: Mapped[list["AgentRunStep"]] = relationship(back_populates="run", cascade="all, delete-orphan", order_by="AgentRunStep.step_order")


class AgentRunStep(Base):
    __tablename__ = "agent_run_steps"
    __table_args__ = (
        UniqueConstraint("run_id", "step_order", name="uq_agent_run_step_order"),
        UniqueConstraint("run_id", "idempotency_key", name="uq_agent_run_step_idempotency"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    correlation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    transaction_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    tool_name: Mapped[str] = mapped_column(String(120), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_owner: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    # Monotonic claim fence; increments on every successful lease acquisition.
    lease_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    input_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    output_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    error_type: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    run: Mapped[AgentRun] = relationship(back_populates="steps")


class AgentEventRecord(Base):
    __tablename__ = "agent_events"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_agent_event_sequence"),
        Index("uq_agent_event_terminal_key", "terminal_key", unique=True),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    correlation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    transaction_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # Only terminal lifecycle events receive a value; NULL keeps ordinary events
    # outside the uniqueness fence on SQLite/MySQL.
    terminal_key: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    summary: Mapped[str] = mapped_column(String(1000), nullable=False)
    data_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    run: Mapped[AgentRun] = relationship(back_populates="events")


class AgentApproval(Base):
    __tablename__ = "agent_approvals"
    __table_args__ = (UniqueConstraint("run_id", "step_id", name="uq_agent_approval_step"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    correlation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    transaction_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    step_id: Mapped[Optional[str]] = mapped_column(ForeignKey("agent_run_steps.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    tool_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending", index=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    request_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class AgentArtifactRef(Base):
    __tablename__ = "agent_artifact_refs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    correlation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    transaction_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    uri: Mapped[str] = mapped_column(String(500), nullable=False)
    sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)




class AgentRunCommand(Base):
    """Durable user/operator intent to change one Agent Run lifecycle."""
    __tablename__ = "agent_run_commands"
    __table_args__ = (
        UniqueConstraint("run_id", "idempotency_key", name="uq_agent_run_command_idempotency"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    correlation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    transaction_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    command_type: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="requested", index=True)
    reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Nullable at the database layer during the 017→018 compatibility upgrade;
    # every newly-created command receives a non-empty value from the service.
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default="")
    expected_state_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    error_type: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    error_detail: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    lease_owner: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    # Monotonic claim fence; increments on every successful lease acquisition.
    lease_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    run: Mapped[AgentRun] = relationship()

class AgentJob(Base):
    """Durable execution contract; creating a row does not imply a worker ran it."""
    __tablename__ = "agent_jobs"
    __table_args__ = (
        UniqueConstraint("run_id", "idempotency_key", name="uq_agent_job_idempotency"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    correlation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    transaction_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    error_type: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    error_detail: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    lease_owner: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    # Monotonic claim fence; increments on every successful lease acquisition.
    lease_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    cancel_requested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    cancel_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    run: Mapped[AgentRun] = relationship()
