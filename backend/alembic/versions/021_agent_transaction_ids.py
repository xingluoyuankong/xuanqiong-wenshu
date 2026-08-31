"""Add durable transaction identifiers to Agent runs and child records.

Revision ID: 021_agent_transaction_ids
Revises: 020_agent_catalog_relational
"""
from __future__ import annotations

from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision: str = "021_agent_transaction_ids"
down_revision: Union[str, None] = "020_agent_catalog_relational"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("agent_runs", "agent_run_steps", "agent_events", "agent_approvals", "agent_artifact_refs", "agent_run_commands", "agent_jobs")

def _columns(table: str) -> set[str]:
    inspector = inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {str(item["name"]) for item in inspector.get_columns(table)}

def _add(table: str, nullable: bool = True) -> None:
    if "transaction_id" not in _columns(table):
        op.add_column(table, sa.Column("transaction_id", sa.String(36), nullable=nullable, index=False))

def upgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    for table in _TABLES:
        if table in tables:
            _add(table, nullable=True)
    if "agent_runs" in tables and "transaction_id" in _columns("agent_runs"):
        rows = bind.execute(text("SELECT id FROM agent_runs WHERE transaction_id IS NULL")).fetchall()
        for row in rows:
            bind.execute(text("UPDATE agent_runs SET transaction_id = :value WHERE id = :id"), {"value": str(uuid4()), "id": row[0]})
    if "agent_runs" in tables and "transaction_id" in _columns("agent_runs"):
        indexes = {str(item.get("name")) for item in inspect(bind).get_indexes("agent_runs") if item.get("name")}
        if "ix_agent_runs_transaction_id" not in indexes:
            op.create_index("ix_agent_runs_transaction_id", "agent_runs", ["transaction_id"])
        # SQLite/MySQL both accept a unique index after backfill.
        if "uq_agent_run_transaction_id" not in indexes:
            op.create_index("uq_agent_run_transaction_id", "agent_runs", ["transaction_id"], unique=True)
    for table in _TABLES[1:]:
        if table in tables and "transaction_id" in _columns(table):
            indexes = {str(item.get("name")) for item in inspect(bind).get_indexes(table) if item.get("name")}
            name = f"ix_{table}_transaction_id"
            if name not in indexes:
                op.create_index(name, table, ["transaction_id"])

def downgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    for table in reversed(_TABLES):
        if table not in tables or "transaction_id" not in _columns(table):
            continue
        indexes = {str(item.get("name")) for item in inspect(bind).get_indexes(table) if item.get("name")}
        for name in ("uq_agent_run_transaction_id", "ix_agent_runs_transaction_id") if table == "agent_runs" else (f"ix_{table}_transaction_id",):
            if name in indexes:
                op.drop_index(name, table_name=table)
        op.drop_column(table, "transaction_id")
