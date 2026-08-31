"""关系化 Agent Catalog、Resolver 快照和能力执行记录模型。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base


class AgentCatalogRelease(Base):
    """不可变能力目录的一次发布记录。"""

    __tablename__ = "agent_catalog_releases"
    __table_args__ = (
        UniqueConstraint("release_id", name="uq_agent_catalog_release_release_id"),
        UniqueConstraint("catalog_id", "generation", name="uq_agent_catalog_release_generation"),
        UniqueConstraint("digest", name="uq_agent_catalog_release_digest"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    release_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    catalog_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="published", server_default="published", index=True)
    digest: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    manifest_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    deprecated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    provider_releases: Mapped[list["AgentProviderRelease"]] = relationship(
        back_populates="catalog_release", cascade="all, delete-orphan", order_by="AgentProviderRelease.provider_id"
    )
    capability_definitions: Mapped[list["AgentCapabilityDefinition"]] = relationship(
        back_populates="catalog_release", cascade="all, delete-orphan", order_by="AgentCapabilityDefinition.capability_id"
    )
    run_snapshots: Mapped[list["AgentRunCapabilitySnapshot"]] = relationship(
        back_populates="catalog_release", passive_deletes=True, order_by="AgentRunCapabilitySnapshot.created_at"
    )


class AgentProviderRelease(Base):
    """某个 Catalog Release 中的 Provider 固化信息。"""

    __tablename__ = "agent_provider_releases"
    __table_args__ = (
        UniqueConstraint("catalog_release_id", "provider_id", name="uq_agent_provider_release_provider"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    catalog_release_id: Mapped[str] = mapped_column(
        ForeignKey("agent_catalog_releases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    provider_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    api_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="loaded", server_default="loaded", index=True)
    source: Mapped[str] = mapped_column(String(255), nullable=False, default="builtin", server_default="builtin")
    failure_code: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    tools_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    capability_tags_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    dependencies_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    catalog_release: Mapped[AgentCatalogRelease] = relationship(back_populates="provider_releases")
    capability_definitions: Mapped[list["AgentCapabilityDefinition"]] = relationship(
        back_populates="provider_release", cascade="all, delete-orphan", order_by="AgentCapabilityDefinition.capability_id"
    )


class AgentCapabilityDefinition(Base):
    """Catalog Release 中可被 Resolver 选择的能力定义。"""

    __tablename__ = "agent_capability_definitions"
    __table_args__ = (
        UniqueConstraint("catalog_release_id", "capability_id", name="uq_agent_capability_definition_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    catalog_release_id: Mapped[str] = mapped_column(
        ForeignKey("agent_catalog_releases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_release_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("agent_provider_releases.id", ondelete="CASCADE"), nullable=True, index=True
    )
    capability_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False, default="1", server_default="1")
    manifest_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    input_schema_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    output_schema_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    risk_level: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    confirmation_policy: Mapped[str] = mapped_column(String(32), nullable=False, default="none", server_default="none")
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    project_scoped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    supports_stream: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60, server_default="60")
    cancellation_policy: Mapped[str] = mapped_column(String(32), nullable=False, default="cooperative", server_default="cooperative")
    idempotency_policy: Mapped[str] = mapped_column(String(32), nullable=False, default="none", server_default="none")
    audit_event_type: Mapped[str] = mapped_column(String(128), nullable=False, default="capability_call", server_default="capability_call")
    context_bindings_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    capability_tags_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    handler_identity: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    catalog_release: Mapped[AgentCatalogRelease] = relationship(back_populates="capability_definitions")
    provider_release: Mapped[Optional[AgentProviderRelease]] = relationship(back_populates="capability_definitions")
    executions: Mapped[list["AgentCapabilityExecution"]] = relationship(
        back_populates="capability_definition", passive_deletes=True
    )


class AgentRunCapabilitySnapshot(Base):
    """Run 绑定的不可变 Resolver 结果，保存可复现选择依据。"""

    __tablename__ = "agent_run_capability_snapshots"
    __table_args__ = (
        UniqueConstraint("run_id", "snapshot_id", name="uq_agent_run_capability_snapshot_run"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    snapshot_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    transaction_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    catalog_release_id: Mapped[str] = mapped_column(
        ForeignKey("agent_catalog_releases.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    resolver_schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    selection_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    resolved_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    release_digest: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    digest: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    request_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    resolved_scope_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    selected_capability_ids_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    exclusions_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    selected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    run: Mapped[Any] = relationship("AgentRun", foreign_keys=[run_id])
    catalog_release: Mapped[AgentCatalogRelease] = relationship(back_populates="run_snapshots")
    executions: Mapped[list["AgentCapabilityExecution"]] = relationship(
        back_populates="snapshot", passive_deletes=True, order_by="AgentCapabilityExecution.started_at"
    )


class AgentCapabilityExecution(Base):
    """一次能力调用的事实记录，不包含运行时 handler 本身。"""

    __tablename__ = "agent_capability_executions"
    __table_args__ = (
        UniqueConstraint("execution_id", name="uq_agent_capability_execution_execution_id"),
        UniqueConstraint("run_id", "idempotency_key", name="uq_agent_capability_execution_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    execution_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    transaction_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    step_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("agent_run_steps.id", ondelete="SET NULL"), nullable=True, index=True
    )
    snapshot_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("agent_run_capability_snapshots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    capability_definition_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("agent_capability_definitions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    provider_release_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("agent_provider_releases.id", ondelete="SET NULL"), nullable=True, index=True
    )
    correlation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    capability_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    resolved_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    selection_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="started", server_default="started", index=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    input_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    input_digest: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    output_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    output_digest: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    error_type: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    error_detail: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    lease_generation: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    run: Mapped[Any] = relationship("AgentRun", foreign_keys=[run_id])
    step: Mapped[Any] = relationship("AgentRunStep", foreign_keys=[step_id])
    snapshot: Mapped[Optional[AgentRunCapabilitySnapshot]] = relationship(back_populates="executions")
    capability_definition: Mapped[Optional[AgentCapabilityDefinition]] = relationship(back_populates="executions")
    provider_release: Mapped[Optional[AgentProviderRelease]] = relationship(foreign_keys=[provider_release_id])
