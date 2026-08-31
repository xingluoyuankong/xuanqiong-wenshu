"""Add transaction IDs to relational Agent capability records.

Revision ID: 022_agent_catalog_transaction_ids
Revises: 021_agent_transaction_ids
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
revision: str = "022_agent_catalog_transaction_ids"
down_revision: Union[str, None] = "021_agent_transaction_ids"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
_TABLES = ("agent_run_capability_snapshots", "agent_capability_executions")
def _columns(table: str) -> set[str]:
    inspector = inspect(op.get_bind())
    if table not in inspector.get_table_names(): return set()
    return {str(item["name"]) for item in inspector.get_columns(table)}
def upgrade() -> None:
    for table in _TABLES:
        if table in inspect(op.get_bind()).get_table_names() and "transaction_id" not in _columns(table):
            op.add_column(table, sa.Column("transaction_id", sa.String(36), nullable=True))
            op.create_index(f"ix_{table}_transaction_id", table, ["transaction_id"])
def downgrade() -> None:
    for table in reversed(_TABLES):
        if table in inspect(op.get_bind()).get_table_names() and "transaction_id" in _columns(table):
            indexes = {str(item.get("name")) for item in inspect(op.get_bind()).get_indexes(table) if item.get("name")}
            name = f"ix_{table}_transaction_id"
            if name in indexes: op.drop_index(name, table_name=table)
            op.drop_column(table, "transaction_id")
