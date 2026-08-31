"""Persist AgentRun step checkpoints for idempotent recovery."""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "009_agent_run_steps"
down_revision: Union[str, None] = "008_agent_run_lease"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if "agent_run_steps" in inspector.get_table_names():
        return
    op.create_table(
        "agent_run_steps",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("tool_name", sa.String(120), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("input_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("output_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("error_type", sa.String(160), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("run_id", "step_order", name="uq_agent_run_step_order"),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_agent_run_step_idempotency"),
    )
    op.create_index("ix_agent_run_steps_run_id", "agent_run_steps", ["run_id"])
    op.create_index("ix_agent_run_steps_user_id", "agent_run_steps", ["user_id"])
    op.create_index("ix_agent_run_steps_status", "agent_run_steps", ["status"])


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if "agent_run_steps" in inspector.get_table_names():
        op.drop_table("agent_run_steps")
