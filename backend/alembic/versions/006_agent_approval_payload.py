"""Persist structured arguments for Agent approvals."""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "006_agent_approval_payload"
down_revision: Union[str, None] = "005_agent_runtime"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    return column in {item["name"] for item in inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if not _has_column("agent_approvals", "request_json"):
        op.add_column("agent_approvals", sa.Column("request_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))


def downgrade() -> None:
    if _has_column("agent_approvals", "request_json"):
        op.drop_column("agent_approvals", "request_json")
