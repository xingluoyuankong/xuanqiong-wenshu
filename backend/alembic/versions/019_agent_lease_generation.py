"""Add monotonic lease generations for Agent Run/Step/Job/Command claims.

Revision ID: 019_agent_lease_generation
Revises: 018_agent_run_command_fences
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "019_agent_lease_generation"
down_revision: Union[str, None] = "018_agent_run_command_fences"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table: str) -> set[str]:
    inspector = inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {str(item["name"]) for item in inspector.get_columns(table)}


def _add(table: str) -> None:
    if "lease_generation" not in _columns(table):
        op.add_column(table, sa.Column("lease_generation", sa.Integer(), nullable=False, server_default="0"))


def upgrade() -> None:
    for table in ("agent_runs", "agent_run_steps", "agent_jobs", "agent_run_commands"):
        if table in inspect(op.get_bind()).get_table_names():
            _add(table)


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    for table in ("agent_run_commands", "agent_jobs", "agent_run_steps", "agent_runs"):
        if table in tables and "lease_generation" in _columns(table):
            op.drop_column(table, "lease_generation")
