"""Agent 可追溯质量评估结果、发现项与质量门模型。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base


class QualityResult(Base):
    """一次针对 Agent Artifact 的可追溯质量评估事实。"""

    __tablename__ = "agent_quality_results"
    __table_args__ = (
        CheckConstraint("score IS NULL OR (score >= 0 AND score <= 100)", name="ck_agent_quality_result_score_range"),
        UniqueConstraint("result_id", name="uq_agent_quality_result_result_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    result_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    artifact_ref_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("agent_artifact_refs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    correlation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    transaction_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    assessor_id: Mapped[str] = mapped_column(String(160), nullable=False, default="system", server_default="system")
    rubric_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="completed", server_default="completed", index=True)
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metrics_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    input_digest: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    result_digest: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    run: Mapped[Any] = relationship("AgentRun", foreign_keys=[run_id])
    artifact_ref: Mapped[Optional[Any]] = relationship("AgentArtifactRef", foreign_keys=[artifact_ref_id])
    findings: Mapped[list["QualityFinding"]] = relationship(
        back_populates="quality_result", cascade="all, delete-orphan", order_by="QualityFinding.created_at"
    )
    gates: Mapped[list["QualityGate"]] = relationship(
        back_populates="quality_result", cascade="all, delete-orphan", order_by="QualityGate.evaluated_at"
    )


class QualityFinding(Base):
    """QualityResult 下一个可定位、可修复的质量发现项。"""

    __tablename__ = "agent_quality_findings"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('info', 'warning', 'error', 'blocker')",
            name="ck_agent_quality_finding_severity",
        ),
        UniqueConstraint("finding_id", name="uq_agent_quality_finding_finding_id"),
        UniqueConstraint("quality_result_id", "fingerprint", name="uq_agent_quality_finding_fingerprint"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    quality_result_id: Mapped[str] = mapped_column(
        ForeignKey("agent_quality_results.id", ondelete="CASCADE"), nullable=False, index=True
    )
    finding_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    category: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    severity: Mapped[str] = mapped_column(String(24), nullable=False, default="warning", server_default="warning", index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="open", server_default="open", index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    location_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    remediation_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    quality_result: Mapped[QualityResult] = relationship(back_populates="findings")


class QualityGate(Base):
    """将 QualityResult 固化为 Artifact 发布/审批可消费的门禁决策。"""

    __tablename__ = "agent_quality_gates"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('passed', 'blocked', 'waived')",
            name="ck_agent_quality_gate_decision",
        ),
        UniqueConstraint("gate_id", name="uq_agent_quality_gate_gate_id"),
        UniqueConstraint("quality_result_id", "gate_name", name="uq_agent_quality_gate_result_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    gate_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    quality_result_id: Mapped[str] = mapped_column(
        ForeignKey("agent_quality_results.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    artifact_ref_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("agent_artifact_refs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    correlation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    transaction_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    gate_name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    gate_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    decision: Mapped[str] = mapped_column(String(24), nullable=False, default="blocked", server_default="blocked", index=True)
    blocker_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    policy_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    quality_result: Mapped[QualityResult] = relationship(back_populates="gates")
    run: Mapped[Any] = relationship("AgentRun", foreign_keys=[run_id])
    artifact_ref: Mapped[Optional[Any]] = relationship("AgentArtifactRef", foreign_keys=[artifact_ref_id])
