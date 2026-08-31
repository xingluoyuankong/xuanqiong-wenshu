"""Persist relational Agent Catalog releases, Resolver snapshots and executions.

Revision ID: 020_agent_catalog_relational
Revises: 019_agent_lease_generation
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "020_agent_catalog_relational"
down_revision: Union[str, None] = "019_agent_lease_generation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables() -> set[str]:
    return set(inspect(op.get_bind()).get_table_names())


def _indexes(table: str) -> set[str]:
    inspector = inspect(op.get_bind())
    if table not in _tables():
        return set()
    return {str(item.get("name")) for item in inspector.get_indexes(table) if item.get("name")}


def _create_index_if_missing(name: str, table: str, columns: list[str]) -> None:
    if name not in _indexes(table):
        op.create_index(name, table, columns)


def _create_catalog_release() -> None:
    table = "agent_catalog_releases"
    if table not in _tables():
        op.create_table(
            table,
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("release_id", sa.String(255), nullable=False),
            sa.Column("catalog_id", sa.String(128), nullable=False),
            sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("generation", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(24), nullable=False, server_default="published"),
            sa.Column("digest", sa.String(64), nullable=False),
            sa.Column("manifest_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deprecated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("release_id", name="uq_agent_catalog_release_release_id"),
            sa.UniqueConstraint("catalog_id", "generation", name="uq_agent_catalog_release_generation"),
            sa.UniqueConstraint("digest", name="uq_agent_catalog_release_digest"),
        )
    for name, columns in {
        "ix_agent_catalog_releases_release_id": ["release_id"],
        "ix_agent_catalog_releases_catalog_id": ["catalog_id"],
        "ix_agent_catalog_releases_status": ["status"],
        "ix_agent_catalog_releases_digest": ["digest"],
        "ix_agent_catalog_releases_published_at": ["published_at"],
    }.items():
        _create_index_if_missing(name, table, columns)


def _create_provider_release() -> None:
    table = "agent_provider_releases"
    if table not in _tables():
        op.create_table(
            table,
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("catalog_release_id", sa.String(36), sa.ForeignKey("agent_catalog_releases.id", ondelete="CASCADE"), nullable=False),
            sa.Column("provider_id", sa.String(128), nullable=False),
            sa.Column("provider_version", sa.String(64), nullable=True),
            sa.Column("api_version", sa.String(64), nullable=True),
            sa.Column("status", sa.String(24), nullable=False, server_default="loaded"),
            sa.Column("source", sa.String(255), nullable=False, server_default="builtin"),
            sa.Column("failure_code", sa.String(160), nullable=True),
            sa.Column("tools_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("capability_tags_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("dependencies_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("catalog_release_id", "provider_id", name="uq_agent_provider_release_provider"),
        )
    for name, columns in {
        "ix_agent_provider_releases_catalog_release_id": ["catalog_release_id"],
        "ix_agent_provider_releases_provider_id": ["provider_id"],
        "ix_agent_provider_releases_status": ["status"],
    }.items():
        _create_index_if_missing(name, table, columns)


def _create_capability_definition() -> None:
    table = "agent_capability_definitions"
    if table not in _tables():
        op.create_table(
            table,
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("catalog_release_id", sa.String(36), sa.ForeignKey("agent_catalog_releases.id", ondelete="CASCADE"), nullable=False),
            sa.Column("provider_release_id", sa.String(36), sa.ForeignKey("agent_provider_releases.id", ondelete="CASCADE"), nullable=True),
            sa.Column("capability_id", sa.String(160), nullable=False),
            sa.Column("name", sa.String(160), nullable=False),
            sa.Column("version", sa.String(64), nullable=False, server_default="1"),
            sa.Column("manifest_version", sa.String(64), nullable=True),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("input_schema_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("output_schema_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("risk_level", sa.String(24), nullable=False),
            sa.Column("confirmation_policy", sa.String(32), nullable=False, server_default="none"),
            sa.Column("requires_confirmation", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("project_scoped", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("supports_stream", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("idempotency_key", sa.String(255), nullable=True),
            sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="60"),
            sa.Column("cancellation_policy", sa.String(32), nullable=False, server_default="cooperative"),
            sa.Column("idempotency_policy", sa.String(32), nullable=False, server_default="none"),
            sa.Column("audit_event_type", sa.String(128), nullable=False, server_default="capability_call"),
            sa.Column("context_bindings_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("capability_tags_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("handler_identity", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("catalog_release_id", "capability_id", name="uq_agent_capability_definition_key"),
        )
    for name, columns in {
        "ix_agent_capability_definitions_catalog_release_id": ["catalog_release_id"],
        "ix_agent_capability_definitions_provider_release_id": ["provider_release_id"],
        "ix_agent_capability_definitions_capability_id": ["capability_id"],
        "ix_agent_capability_definitions_name": ["name"],
        "ix_agent_capability_definitions_risk_level": ["risk_level"],
    }.items():
        _create_index_if_missing(name, table, columns)


def _create_run_snapshot() -> None:
    table = "agent_run_capability_snapshots"
    if table not in _tables():
        op.create_table(
            table,
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("snapshot_id", sa.String(255), nullable=False),
            sa.Column("run_id", sa.String(36), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("catalog_release_id", sa.String(36), sa.ForeignKey("agent_catalog_releases.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.String(120), nullable=True),
            sa.Column("resolver_schema_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("generation", sa.Integer(), nullable=False),
            sa.Column("selection_reason", sa.String(255), nullable=True),
            sa.Column("resolved_version", sa.String(64), nullable=True),
            sa.Column("release_digest", sa.String(64), nullable=False),
            sa.Column("digest", sa.String(64), nullable=False),
            sa.Column("request_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("resolved_scope_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("selected_capability_ids_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("exclusions_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("selected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("run_id", "snapshot_id", name="uq_agent_run_capability_snapshot_run"),
        )
    for name, columns in {
        "ix_agent_run_capability_snapshots_snapshot_id": ["snapshot_id"],
        "ix_agent_run_capability_snapshots_run_id": ["run_id"],
        "ix_agent_run_capability_snapshots_catalog_release_id": ["catalog_release_id"],
        "ix_agent_run_capability_snapshots_user_id": ["user_id"],
        "ix_agent_run_capability_snapshots_project_id": ["project_id"],
        "ix_agent_run_capability_snapshots_release_digest": ["release_digest"],
        "ix_agent_run_capability_snapshots_digest": ["digest"],
    }.items():
        _create_index_if_missing(name, table, columns)


def _create_capability_execution() -> None:
    table = "agent_capability_executions"
    if table not in _tables():
        op.create_table(
            table,
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("execution_id", sa.String(36), nullable=False),
            sa.Column("run_id", sa.String(36), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("step_id", sa.String(36), sa.ForeignKey("agent_run_steps.id", ondelete="SET NULL"), nullable=True),
            sa.Column("snapshot_id", sa.String(36), sa.ForeignKey("agent_run_capability_snapshots.id", ondelete="SET NULL"), nullable=True),
            sa.Column("capability_definition_id", sa.String(36), sa.ForeignKey("agent_capability_definitions.id", ondelete="SET NULL"), nullable=True),
            sa.Column("provider_release_id", sa.String(36), sa.ForeignKey("agent_provider_releases.id", ondelete="SET NULL"), nullable=True),
            sa.Column("correlation_id", sa.String(36), nullable=False),
            sa.Column("capability_id", sa.String(160), nullable=False),
            sa.Column("resolved_version", sa.String(64), nullable=True),
            sa.Column("selection_reason", sa.String(255), nullable=True),
            sa.Column("status", sa.String(24), nullable=False, server_default="started"),
            sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("idempotency_key", sa.String(255), nullable=True),
            sa.Column("input_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("input_digest", sa.String(64), nullable=True),
            sa.Column("output_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("output_digest", sa.String(64), nullable=True),
            sa.Column("error_type", sa.String(160), nullable=True),
            sa.Column("error_detail", sa.String(1000), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("lease_generation", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("execution_id", name="uq_agent_capability_execution_execution_id"),
            sa.UniqueConstraint("run_id", "idempotency_key", name="uq_agent_capability_execution_idempotency"),
        )
    for name, columns in {
        "ix_agent_capability_executions_execution_id": ["execution_id"],
        "ix_agent_capability_executions_run_id": ["run_id"],
        "ix_agent_capability_executions_step_id": ["step_id"],
        "ix_agent_capability_executions_snapshot_id": ["snapshot_id"],
        "ix_agent_capability_executions_capability_definition_id": ["capability_definition_id"],
        "ix_agent_capability_executions_provider_release_id": ["provider_release_id"],
        "ix_agent_capability_executions_correlation_id": ["correlation_id"],
        "ix_agent_capability_executions_capability_id": ["capability_id"],
        "ix_agent_capability_executions_status": ["status"],
        "ix_agent_capability_executions_input_digest": ["input_digest"],
        "ix_agent_capability_executions_output_digest": ["output_digest"],
    }.items():
        _create_index_if_missing(name, table, columns)


def upgrade() -> None:
    # Create parents first so both a 000-baseline database and a 019 legacy
    # database can reach the same shape. Every operation is table/index guarded
    # because startup and migration commands may be retried.
    _create_catalog_release()
    _create_provider_release()
    _create_capability_definition()
    _create_run_snapshot()
    _create_capability_execution()


def downgrade() -> None:
    existing = _tables()
    for table in (
        "agent_capability_executions",
        "agent_run_capability_snapshots",
        "agent_capability_definitions",
        "agent_provider_releases",
        "agent_catalog_releases",
    ):
        if table in existing:
            op.drop_table(table)
