"""Agent Artifact 来源、派生与合并关系模型。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base


class ArtifactLineage(Base):
    """一个候选/正式 Artifact 与其直接来源 Artifact 的有向血缘边。"""

    __tablename__ = "agent_artifact_lineages"
    __table_args__ = (
        CheckConstraint(
            "source_artifact_ref_id <> derived_artifact_ref_id",
            name="ck_agent_artifact_lineage_distinct_endpoints",
        ),
        UniqueConstraint("lineage_id", name="uq_agent_artifact_lineage_lineage_id"),
        UniqueConstraint(
            "source_artifact_ref_id", "derived_artifact_ref_id", "relation_type",
            name="uq_agent_artifact_lineage_edge",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    lineage_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_artifact_ref_id: Mapped[str] = mapped_column(
        ForeignKey("agent_artifact_refs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    derived_artifact_ref_id: Mapped[str] = mapped_column(
        ForeignKey("agent_artifact_refs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    correlation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    transaction_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    relation_type: Mapped[str] = mapped_column(String(64), nullable=False, default="derived_from", server_default="derived_from", index=True)
    operation: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    input_digest: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    output_digest: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    run: Mapped[Any] = relationship("AgentRun", foreign_keys=[run_id])
    source_artifact_ref: Mapped[Any] = relationship("AgentArtifactRef", foreign_keys=[source_artifact_ref_id])
    derived_artifact_ref: Mapped[Any] = relationship("AgentArtifactRef", foreign_keys=[derived_artifact_ref_id])

