"""Add a lease fence for multi-worker Agent run claiming."""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
revision: str = "008_agent_run_lease"
down_revision: Union[str, None] = "007_agent_run_context"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
def _has_column(name: str) -> bool:
    return name in {item["name"] for item in inspect(op.get_bind()).get_columns("agent_runs")}
def upgrade() -> None:
    if not _has_column("lease_owner"):
        op.add_column("agent_runs", sa.Column("lease_owner", sa.String(128), nullable=True))
    if not _has_column("lease_expires_at"):
        op.add_column("agent_runs", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    indexes = {item.get("name") for item in inspect(op.get_bind()).get_indexes("agent_runs")}
    if "ix_agent_runs_lease_owner" not in indexes:
        op.create_index("ix_agent_runs_lease_owner", "agent_runs", ["lease_owner"])
    if "ix_agent_runs_lease_expires_at" not in indexes:
        op.create_index("ix_agent_runs_lease_expires_at", "agent_runs", ["lease_expires_at"])
def downgrade() -> None:
    indexes = {item.get("name") for item in inspect(op.get_bind()).get_indexes("agent_runs")}
    if "ix_agent_runs_lease_expires_at" in indexes:
        op.drop_index("ix_agent_runs_lease_expires_at", table_name="agent_runs")
    if "ix_agent_runs_lease_owner" in indexes:
        op.drop_index("ix_agent_runs_lease_owner", table_name="agent_runs")
    if _has_column("lease_expires_at"):
        op.drop_column("agent_runs", "lease_expires_at")
    if _has_column("lease_owner"):
        op.drop_column("agent_runs", "lease_owner")
