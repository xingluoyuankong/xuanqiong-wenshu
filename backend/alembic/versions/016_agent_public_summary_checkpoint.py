"""Add durable latest public work-summary checkpoint to AgentRun.

Revision ID: 016_agent_public_summary_checkpoint
Revises: 015_agent_progress_sequence
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "016_agent_public_summary_checkpoint"
down_revision: Union[str, None] = "015_agent_progress_sequence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    inspector = inspect(op.get_bind())
    return table in inspector.get_table_names() and column in {item["name"] for item in inspector.get_columns(table)}


def upgrade() -> None:
    tables = set(inspect(op.get_bind()).get_table_names())
    if "agent_runs" not in tables:
        return
    if not _has_column("agent_runs", "latest_public_summary_json"):
        op.add_column(
            "agent_runs",
            sa.Column("latest_public_summary_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        )
    if not _has_column("agent_runs", "latest_public_summary_sequence"):
        op.add_column(
            "agent_runs",
            sa.Column("latest_public_summary_sequence", sa.Integer(), nullable=False, server_default="0"),
        )
    if not _has_column("agent_runs", "latest_public_summary_at"):
        op.add_column(
            "agent_runs",
            sa.Column("latest_public_summary_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    tables = set(inspect(op.get_bind()).get_table_names())
    if "agent_runs" not in tables:
        return
    for column in ("latest_public_summary_at", "latest_public_summary_sequence", "latest_public_summary_json"):
        if _has_column("agent_runs", column):
            op.drop_column("agent_runs", column)