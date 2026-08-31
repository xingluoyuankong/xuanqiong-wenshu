"""Add relational Agent quality findings, quality gates, and artifact lineage.

Revision ID: 023_agent_quality_lineage
Revises: 022_agent_catalog_transaction_ids
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "023_agent_quality_lineage"
down_revision: Union[str, None] = "022_agent_catalog_transaction_ids"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables() -> set[str]:
    return set(inspect(op.get_bind()).get_table_names())


def _indexes(table: str) -> set[str]:
    return {str(item.get("name")) for item in inspect(op.get_bind()).get_indexes(table) if item.get("name")}


def _create_index_if_missing(name: str, table: str, columns: list[str]) -> None:
    if table in _tables() and name not in _indexes(table):
        op.create_index(name, table, columns)


def _create_quality_results() -> None:
    table = "agent_quality_results"
    if table not in _tables():
        op.create_table(
            table,
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("result_id", sa.String(36), nullable=False),
            sa.Column("run_id", sa.String(36), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("artifact_ref_id", sa.String(36), sa.ForeignKey("agent_artifact_refs.id", ondelete="SET NULL"), nullable=True),
            sa.Column("correlation_id", sa.String(36), nullable=False),
            sa.Column("transaction_id", sa.String(36), nullable=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.String(120), nullable=True),
            sa.Column("assessor_id", sa.String(160), nullable=False, server_default="system"),
            sa.Column("rubric_version", sa.String(64), nullable=True),
            sa.Column("status", sa.String(24), nullable=False, server_default="completed"),
            sa.Column("score", sa.Float(), nullable=True),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("metrics_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("input_digest", sa.String(64), nullable=True),
            sa.Column("result_digest", sa.String(64), nullable=True),
            sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint("score IS NULL OR (score >= 0 AND score <= 100)", name="ck_agent_quality_result_score_range"),
            sa.UniqueConstraint("result_id", name="uq_agent_quality_result_result_id"),
        )
    for name, columns in {
        "ix_agent_quality_results_result_id": ["result_id"],
        "ix_agent_quality_results_run_id": ["run_id"],
        "ix_agent_quality_results_artifact_ref_id": ["artifact_ref_id"],
        "ix_agent_quality_results_correlation_id": ["correlation_id"],
        "ix_agent_quality_results_transaction_id": ["transaction_id"],
        "ix_agent_quality_results_user_id": ["user_id"],
        "ix_agent_quality_results_project_id": ["project_id"],
        "ix_agent_quality_results_status": ["status"],
        "ix_agent_quality_results_input_digest": ["input_digest"],
        "ix_agent_quality_results_result_digest": ["result_digest"],
    }.items():
        _create_index_if_missing(name, table, columns)


def _create_quality_findings() -> None:
    table = "agent_quality_findings"
    if table not in _tables():
        op.create_table(
            table,
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("quality_result_id", sa.String(36), sa.ForeignKey("agent_quality_results.id", ondelete="CASCADE"), nullable=False),
            sa.Column("finding_id", sa.String(36), nullable=False),
            sa.Column("code", sa.String(160), nullable=False),
            sa.Column("category", sa.String(120), nullable=True),
            sa.Column("severity", sa.String(24), nullable=False, server_default="warning"),
            sa.Column("status", sa.String(24), nullable=False, server_default="open"),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("fingerprint", sa.String(64), nullable=False),
            sa.Column("location_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("evidence_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("remediation_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint("severity IN ('info', 'warning', 'error', 'blocker')", name="ck_agent_quality_finding_severity"),
            sa.UniqueConstraint("finding_id", name="uq_agent_quality_finding_finding_id"),
            sa.UniqueConstraint("quality_result_id", "fingerprint", name="uq_agent_quality_finding_fingerprint"),
        )
    for name, columns in {
        "ix_agent_quality_findings_quality_result_id": ["quality_result_id"],
        "ix_agent_quality_findings_finding_id": ["finding_id"],
        "ix_agent_quality_findings_code": ["code"],
        "ix_agent_quality_findings_category": ["category"],
        "ix_agent_quality_findings_severity": ["severity"],
        "ix_agent_quality_findings_status": ["status"],
        "ix_agent_quality_findings_fingerprint": ["fingerprint"],
    }.items():
        _create_index_if_missing(name, table, columns)


def _create_quality_gates() -> None:
    table = "agent_quality_gates"
    if table not in _tables():
        op.create_table(
            table,
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("gate_id", sa.String(36), nullable=False),
            sa.Column("quality_result_id", sa.String(36), sa.ForeignKey("agent_quality_results.id", ondelete="CASCADE"), nullable=False),
            sa.Column("run_id", sa.String(36), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("artifact_ref_id", sa.String(36), sa.ForeignKey("agent_artifact_refs.id", ondelete="SET NULL"), nullable=True),
            sa.Column("correlation_id", sa.String(36), nullable=False),
            sa.Column("transaction_id", sa.String(36), nullable=True),
            sa.Column("gate_name", sa.String(160), nullable=False),
            sa.Column("gate_version", sa.String(64), nullable=True),
            sa.Column("decision", sa.String(24), nullable=False, server_default="blocked"),
            sa.Column("blocker_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("rationale", sa.Text(), nullable=True),
            sa.Column("policy_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint("decision IN ('passed', 'blocked', 'waived')", name="ck_agent_quality_gate_decision"),
            sa.UniqueConstraint("gate_id", name="uq_agent_quality_gate_gate_id"),
            sa.UniqueConstraint("quality_result_id", "gate_name", name="uq_agent_quality_gate_result_name"),
        )
    for name, columns in {
        "ix_agent_quality_gates_gate_id": ["gate_id"],
        "ix_agent_quality_gates_quality_result_id": ["quality_result_id"],
        "ix_agent_quality_gates_run_id": ["run_id"],
        "ix_agent_quality_gates_artifact_ref_id": ["artifact_ref_id"],
        "ix_agent_quality_gates_correlation_id": ["correlation_id"],
        "ix_agent_quality_gates_transaction_id": ["transaction_id"],
        "ix_agent_quality_gates_gate_name": ["gate_name"],
        "ix_agent_quality_gates_decision": ["decision"],
    }.items():
        _create_index_if_missing(name, table, columns)


def _create_artifact_lineages() -> None:
    table = "agent_artifact_lineages"
    if table not in _tables():
        op.create_table(
            table,
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("lineage_id", sa.String(36), nullable=False),
            sa.Column("run_id", sa.String(36), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("source_artifact_ref_id", sa.String(36), sa.ForeignKey("agent_artifact_refs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("derived_artifact_ref_id", sa.String(36), sa.ForeignKey("agent_artifact_refs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("correlation_id", sa.String(36), nullable=False),
            sa.Column("transaction_id", sa.String(36), nullable=True),
            sa.Column("relation_type", sa.String(64), nullable=False, server_default="derived_from"),
            sa.Column("operation", sa.String(120), nullable=True),
            sa.Column("input_digest", sa.String(64), nullable=True),
            sa.Column("output_digest", sa.String(64), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint("source_artifact_ref_id <> derived_artifact_ref_id", name="ck_agent_artifact_lineage_distinct_endpoints"),
            sa.UniqueConstraint("lineage_id", name="uq_agent_artifact_lineage_lineage_id"),
            sa.UniqueConstraint("source_artifact_ref_id", "derived_artifact_ref_id", "relation_type", name="uq_agent_artifact_lineage_edge"),
        )
    for name, columns in {
        "ix_agent_artifact_lineages_lineage_id": ["lineage_id"],
        "ix_agent_artifact_lineages_run_id": ["run_id"],
        "ix_agent_artifact_lineages_source_artifact_ref_id": ["source_artifact_ref_id"],
        "ix_agent_artifact_lineages_derived_artifact_ref_id": ["derived_artifact_ref_id"],
        "ix_agent_artifact_lineages_correlation_id": ["correlation_id"],
        "ix_agent_artifact_lineages_transaction_id": ["transaction_id"],
        "ix_agent_artifact_lineages_relation_type": ["relation_type"],
        "ix_agent_artifact_lineages_operation": ["operation"],
        "ix_agent_artifact_lineages_input_digest": ["input_digest"],
        "ix_agent_artifact_lineages_output_digest": ["output_digest"],
    }.items():
        _create_index_if_missing(name, table, columns)


def upgrade() -> None:
    _create_quality_results()
    _create_quality_findings()
    _create_quality_gates()
    _create_artifact_lineages()


def downgrade() -> None:
    existing = _tables()
    for table in (
        "agent_artifact_lineages",
        "agent_quality_gates",
        "agent_quality_findings",
        "agent_quality_results",
    ):
        if table in existing:
            op.drop_table(table)
