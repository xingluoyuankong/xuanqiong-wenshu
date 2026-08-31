"""Add durable Agent cancellation and recovery control fields."""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "012_agent_durable_control"
down_revision: Union[str, None] = "011_agent_approval_step"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    columns = {item["name"] for item in inspect(op.get_bind()).get_columns("agent_runs")}
    indexes = {item.get("name") for item in inspect(op.get_bind()).get_indexes("agent_runs")}
    if "cancel_requested_at" not in columns:
        op.add_column("agent_runs", sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True))
    if "cancel_reason" not in columns:
        op.add_column("agent_runs", sa.Column("cancel_reason", sa.String(255), nullable=True))
    if "ix_agent_runs_cancel_requested_at" not in indexes:
        op.create_index("ix_agent_runs_cancel_requested_at", "agent_runs", ["cancel_requested_at"])

def downgrade() -> None:
    indexes = {item.get("name") for item in inspect(op.get_bind()).get_indexes("agent_runs")}
    if "ix_agent_runs_cancel_requested_at" in indexes:
        op.drop_index("ix_agent_runs_cancel_requested_at", table_name="agent_runs")
    columns = {item["name"] for item in inspect(op.get_bind()).get_columns("agent_runs")}
    if "cancel_reason" in columns:
        op.drop_column("agent_runs", "cancel_reason")
    if "cancel_requested_at" in columns:
        op.drop_column("agent_runs", "cancel_requested_at")
