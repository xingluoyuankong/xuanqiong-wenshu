"""Bind write approvals to a unique AgentRun step checkpoint."""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "011_agent_approval_step"
down_revision: Union[str, None] = "010_agent_step_lease"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    columns = {item["name"] for item in inspector.get_columns("agent_approvals")}
    uniques = {item.get("name") for item in inspector.get_unique_constraints("agent_approvals")}
    indexes = {item.get("name") for item in inspector.get_indexes("agent_approvals")}
    if (
        "step_id" not in columns
        or "uq_agent_approval_step" not in uniques
        or "ix_agent_approvals_step_id" not in indexes
    ):
        with op.batch_alter_table("agent_approvals", recreate="always") as batch:
            if "step_id" not in columns:
                batch.add_column(sa.Column("step_id", sa.String(36), nullable=True))
                batch.create_foreign_key(None, "agent_run_steps", ["step_id"], ["id"], ondelete="CASCADE")
            if "uq_agent_approval_step" not in uniques:
                batch.create_unique_constraint("uq_agent_approval_step", ["run_id", "step_id"])
            if "ix_agent_approvals_step_id" not in indexes:
                batch.create_index("ix_agent_approvals_step_id", ["step_id"])


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    uniques = {item.get("name") for item in inspector.get_unique_constraints("agent_approvals")}
    indexes = {item.get("name") for item in inspector.get_indexes("agent_approvals")}
    columns = {item["name"] for item in inspector.get_columns("agent_approvals")}
    with op.batch_alter_table("agent_approvals", recreate="always") as batch:
        if "ix_agent_approvals_step_id" in indexes:
            batch.drop_index("ix_agent_approvals_step_id")
        if "uq_agent_approval_step" in uniques:
            batch.drop_constraint("uq_agent_approval_step", type_="unique")
        if "step_id" in columns:
            batch.drop_column("step_id")
