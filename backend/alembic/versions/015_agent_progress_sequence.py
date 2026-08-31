"""Add an atomic per-Run visible event sequence counter.

Revision ID: 015_agent_progress_sequence
Revises: 014_agent_correlation_state_bus
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "015_agent_progress_sequence"
down_revision: Union[str, None] = "014_agent_correlation_state_bus"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    inspector = inspect(op.get_bind())
    return table in inspector.get_table_names() and column in {item["name"] for item in inspector.get_columns(table)}


def upgrade() -> None:
    tables = set(inspect(op.get_bind()).get_table_names())
    if "agent_runs" not in tables:
        return
    if not _has_column("agent_runs", "event_sequence"):
        op.add_column(
            "agent_runs",
            sa.Column("event_sequence", sa.Integer(), nullable=False, server_default="0"),
        )
    if "agent_events" in tables and _has_column("agent_events", "sequence"):
        op.execute(
            sa.text(
                "UPDATE agent_runs SET event_sequence = COALESCE(("
                "SELECT MAX(sequence) FROM agent_events WHERE agent_events.run_id = agent_runs.id"
                "), 0)"
            )
        )


def downgrade() -> None:
    tables = set(inspect(op.get_bind()).get_table_names())
    if "agent_runs" in tables and _has_column("agent_runs", "event_sequence"):
        op.drop_column("agent_runs", "event_sequence")
