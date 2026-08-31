"""Create durable Agent Run command records for pause/resume/cancel intent.

Revision ID: 017_agent_run_commands
Revises: 016_agent_public_summary_checkpoint
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "017_agent_run_commands"
down_revision: Union[str, None] = "016_agent_public_summary_checkpoint"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if "agent_run_commands" in inspector.get_table_names():
        return
    op.create_table(
        "agent_run_commands",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("correlation_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("command_type", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="requested"),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("error_type", sa.String(160), nullable=True),
        sa.Column("error_detail", sa.String(1000), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
    )
    for name, columns in {
        "ix_agent_run_commands_run_id": ["run_id"],
        "ix_agent_run_commands_correlation_id": ["correlation_id"],
        "ix_agent_run_commands_user_id": ["user_id"],
        "ix_agent_run_commands_command_type": ["command_type"],
        "ix_agent_run_commands_status": ["status"],
    }.items():
        op.create_index(name, "agent_run_commands", columns)


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if "agent_run_commands" not in inspector.get_table_names():
        return
    indexes = {item.get("name") for item in inspector.get_indexes("agent_run_commands")}
    for name in [
        "ix_agent_run_commands_status",
        "ix_agent_run_commands_command_type",
        "ix_agent_run_commands_user_id",
        "ix_agent_run_commands_correlation_id",
        "ix_agent_run_commands_run_id",
    ]:
        if name in indexes:
            op.drop_index(name, table_name="agent_run_commands")
    op.drop_table("agent_run_commands")
