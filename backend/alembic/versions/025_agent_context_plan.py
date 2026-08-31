"""Add immutable Agent ContextSnapshot, PlanRevision, and ConversationSummary facts.

Revision ID: 025_agent_context_plan
Revises: 024_schema_baseline_agent_reconciliation
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "025_agent_context_plan"
down_revision: Union[str, None] = "024_schema_baseline_agent_reconciliation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables() -> set[str]:
    return set(inspect(op.get_bind()).get_table_names())


def _indexes(table: str) -> set[str]:
    return {str(item.get("name")) for item in inspect(op.get_bind()).get_indexes(table) if item.get("name")}


def _create_index_if_missing(name: str, table: str, columns: list[str]) -> None:
    if table in _tables() and name not in _indexes(table):
        op.create_index(name, table, columns)


def _create_context_snapshots() -> None:
    table = "agent_context_snapshots"
    if table not in _tables():
        op.create_table(
            table,
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("snapshot_id", sa.String(36), nullable=False),
            sa.Column("run_id", sa.String(36), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("session_id", sa.String(36), sa.ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.String(120), nullable=True),
            sa.Column("correlation_id", sa.String(36), nullable=False),
            sa.Column("transaction_id", sa.String(36), nullable=True),
            sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("context_kind", sa.String(80), nullable=False, server_default="run_context"),
            sa.Column("context_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("digest", sa.String(64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("snapshot_id", name="uq_agent_context_snapshot_snapshot_id"),
        )
    for name, columns in {
        "ix_agent_context_snapshots_snapshot_id": ["snapshot_id"],
        "ix_agent_context_snapshots_run_id": ["run_id"],
        "ix_agent_context_snapshots_session_id": ["session_id"],
        "ix_agent_context_snapshots_user_id": ["user_id"],
        "ix_agent_context_snapshots_project_id": ["project_id"],
        "ix_agent_context_snapshots_correlation_id": ["correlation_id"],
        "ix_agent_context_snapshots_transaction_id": ["transaction_id"],
        "ix_agent_context_snapshots_context_kind": ["context_kind"],
        "ix_agent_context_snapshots_digest": ["digest"],
    }.items():
        _create_index_if_missing(name, table, columns)


def _create_context_refs() -> None:
    table = "agent_context_snapshot_refs"
    if table not in _tables():
        op.create_table(
            table,
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("context_snapshot_id", sa.String(36), sa.ForeignKey("agent_context_snapshots.id", ondelete="CASCADE"), nullable=False),
            sa.Column("ref_order", sa.Integer(), nullable=False),
            sa.Column("ref_type", sa.String(80), nullable=False),
            sa.Column("ref_key", sa.String(255), nullable=False),
            sa.Column("ref_version", sa.String(120), nullable=True),
            sa.Column("role", sa.String(80), nullable=True),
            sa.Column("payload_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("digest", sa.String(64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint("ref_order >= 0", name="ck_agent_context_snapshot_ref_order"),
            sa.UniqueConstraint("context_snapshot_id", "ref_order", name="uq_agent_context_snapshot_ref_order"),
        )
    for name, columns in {
        "ix_agent_context_snapshot_refs_context_snapshot_id": ["context_snapshot_id"],
        "ix_agent_context_snapshot_refs_ref_type": ["ref_type"],
        "ix_agent_context_snapshot_refs_ref_key": ["ref_key"],
        "ix_agent_context_snapshot_refs_role": ["role"],
        "ix_agent_context_snapshot_refs_digest": ["digest"],
    }.items():
        _create_index_if_missing(name, table, columns)


def _create_plan_revisions() -> None:
    table = "agent_plan_revisions"
    if table not in _tables():
        op.create_table(
            table,
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("revision_id", sa.String(36), nullable=False),
            sa.Column("run_id", sa.String(36), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("session_id", sa.String(36), sa.ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False),
            sa.Column("context_snapshot_id", sa.String(36), sa.ForeignKey("agent_context_snapshots.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("parent_revision_id", sa.String(36), sa.ForeignKey("agent_plan_revisions.id", ondelete="SET NULL"), nullable=True),
            sa.Column("revision_number", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.String(120), nullable=True),
            sa.Column("correlation_id", sa.String(36), nullable=False),
            sa.Column("transaction_id", sa.String(36), nullable=True),
            sa.Column("planner_id", sa.String(160), nullable=True),
            sa.Column("status", sa.String(24), nullable=False, server_default="created"),
            sa.Column("rationale", sa.Text(), nullable=True),
            sa.Column("plan_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("digest", sa.String(64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint("revision_number >= 1", name="ck_agent_plan_revision_number"),
            sa.UniqueConstraint("revision_id", name="uq_agent_plan_revision_revision_id"),
            sa.UniqueConstraint("run_id", "revision_number", name="uq_agent_plan_revision_run_number"),
        )
    for name, columns in {
        "ix_agent_plan_revisions_revision_id": ["revision_id"],
        "ix_agent_plan_revisions_run_id": ["run_id"],
        "ix_agent_plan_revisions_session_id": ["session_id"],
        "ix_agent_plan_revisions_context_snapshot_id": ["context_snapshot_id"],
        "ix_agent_plan_revisions_parent_revision_id": ["parent_revision_id"],
        "ix_agent_plan_revisions_user_id": ["user_id"],
        "ix_agent_plan_revisions_project_id": ["project_id"],
        "ix_agent_plan_revisions_correlation_id": ["correlation_id"],
        "ix_agent_plan_revisions_transaction_id": ["transaction_id"],
        "ix_agent_plan_revisions_planner_id": ["planner_id"],
        "ix_agent_plan_revisions_status": ["status"],
        "ix_agent_plan_revisions_digest": ["digest"],
    }.items():
        _create_index_if_missing(name, table, columns)


def _create_conversation_summaries() -> None:
    table = "agent_conversation_summaries"
    if table not in _tables():
        op.create_table(
            table,
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("summary_id", sa.String(36), nullable=False),
            sa.Column("session_id", sa.String(36), sa.ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False),
            sa.Column("run_id", sa.String(36), sa.ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.String(120), nullable=True),
            sa.Column("correlation_id", sa.String(36), nullable=True),
            sa.Column("transaction_id", sa.String(36), nullable=True),
            sa.Column("summary_kind", sa.String(80), nullable=False, server_default="rolling"),
            sa.Column("summarizer_id", sa.String(160), nullable=True),
            sa.Column("start_message_sequence", sa.Integer(), nullable=False),
            sa.Column("end_message_sequence", sa.Integer(), nullable=False),
            sa.Column("message_count", sa.Integer(), nullable=False),
            sa.Column("source_digest", sa.String(64), nullable=False),
            sa.Column("summary_text", sa.Text(), nullable=False),
            sa.Column("summary_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("digest", sa.String(64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint("start_message_sequence >= 1", name="ck_agent_conversation_summary_start_sequence"),
            sa.CheckConstraint("end_message_sequence >= start_message_sequence", name="ck_agent_conversation_summary_range"),
            sa.CheckConstraint("message_count >= 1", name="ck_agent_conversation_summary_message_count"),
            sa.UniqueConstraint("summary_id", name="uq_agent_conversation_summary_summary_id"),
        )
    for name, columns in {
        "ix_agent_conversation_summaries_summary_id": ["summary_id"],
        "ix_agent_conversation_summaries_session_id": ["session_id"],
        "ix_agent_conversation_summaries_run_id": ["run_id"],
        "ix_agent_conversation_summaries_user_id": ["user_id"],
        "ix_agent_conversation_summaries_project_id": ["project_id"],
        "ix_agent_conversation_summaries_correlation_id": ["correlation_id"],
        "ix_agent_conversation_summaries_transaction_id": ["transaction_id"],
        "ix_agent_conversation_summaries_summary_kind": ["summary_kind"],
        "ix_agent_conversation_summaries_summarizer_id": ["summarizer_id"],
        "ix_agent_conversation_summaries_start_message_sequence": ["start_message_sequence"],
        "ix_agent_conversation_summaries_end_message_sequence": ["end_message_sequence"],
        "ix_agent_conversation_summaries_source_digest": ["source_digest"],
        "ix_agent_conversation_summaries_digest": ["digest"],
    }.items():
        _create_index_if_missing(name, table, columns)


def upgrade() -> None:
    _create_context_snapshots()
    _create_context_refs()
    _create_plan_revisions()
    _create_conversation_summaries()


def downgrade() -> None:
    existing = _tables()
    for table in (
        "agent_conversation_summaries",
        "agent_plan_revisions",
        "agent_context_snapshot_refs",
        "agent_context_snapshots",
    ):
        if table in existing:
            op.drop_table(table)
