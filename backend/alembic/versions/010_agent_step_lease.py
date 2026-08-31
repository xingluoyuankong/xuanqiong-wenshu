"""Add atomic claim fields to AgentRun step checkpoints."""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "010_agent_step_lease"
down_revision: Union[str, None] = "009_agent_run_steps"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns() -> set[str]:
    return {item["name"] for item in inspect(op.get_bind()).get_columns("agent_run_steps")}


def upgrade() -> None:
    columns = _columns()
    if "attempt_count" not in columns:
        op.add_column("agent_run_steps", sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"))
    if "lease_owner" not in columns:
        op.add_column("agent_run_steps", sa.Column("lease_owner", sa.String(128), nullable=True))
    if "lease_expires_at" not in columns:
        op.add_column("agent_run_steps", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    indexes = {item.get("name") for item in inspect(op.get_bind()).get_indexes("agent_run_steps")}
    if "ix_agent_run_steps_lease_owner" not in indexes:
        op.create_index("ix_agent_run_steps_lease_owner", "agent_run_steps", ["lease_owner"])
    if "ix_agent_run_steps_lease_expires_at" not in indexes:
        op.create_index("ix_agent_run_steps_lease_expires_at", "agent_run_steps", ["lease_expires_at"])


def downgrade() -> None:
    indexes = {item.get("name") for item in inspect(op.get_bind()).get_indexes("agent_run_steps")}
    if "ix_agent_run_steps_lease_expires_at" in indexes:
        op.drop_index("ix_agent_run_steps_lease_expires_at", table_name="agent_run_steps")
    if "ix_agent_run_steps_lease_owner" in indexes:
        op.drop_index("ix_agent_run_steps_lease_owner", table_name="agent_run_steps")
    columns = _columns()
    if "lease_expires_at" in columns:
        op.drop_column("agent_run_steps", "lease_expires_at")
    if "lease_owner" in columns:
        op.drop_column("agent_run_steps", "lease_owner")
    if "attempt_count" in columns:
        op.drop_column("agent_run_steps", "attempt_count")
