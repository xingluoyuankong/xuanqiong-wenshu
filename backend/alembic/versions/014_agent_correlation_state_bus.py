"""Add durable correlation IDs for Agent and compatible TaskRuntime records.

The columns deliberately begin nullable at the database layer for mixed-version
and legacy deployments. New Agent writes always populate them; upgrade backfills
Agent-owned rows from their run and TaskRuntime events from their parent task.

Revision ID: 014_agent_correlation_state_bus
Revises: 013_agent_job_contract
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "014_agent_correlation_state_bus"
down_revision: Union[str, None] = "013_agent_job_contract"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_COLUMNS: dict[str, sa.Column] = {
    "agent_runs": sa.Column("correlation_id", sa.String(length=36), nullable=True),
    "agent_run_steps": sa.Column("correlation_id", sa.String(length=36), nullable=True),
    "agent_events": sa.Column("correlation_id", sa.String(length=36), nullable=True),
    "agent_approvals": sa.Column("correlation_id", sa.String(length=36), nullable=True),
    "agent_artifact_refs": sa.Column("correlation_id", sa.String(length=36), nullable=True),
    "agent_jobs": sa.Column("correlation_id", sa.String(length=36), nullable=True),
    "task_runtime_tasks": sa.Column("correlation_id", sa.String(length=36), nullable=True),
    "task_runtime_events": sa.Column("correlation_id", sa.String(length=36), nullable=True),
}


def _has_column(table: str, column: str) -> bool:
    inspector = inspect(op.get_bind())
    return table in inspector.get_table_names() and column in {item["name"] for item in inspector.get_columns(table)}


def _has_index(table: str, name: str) -> bool:
    return name in {item.get("name") for item in inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    tables = set(inspect(op.get_bind()).get_table_names())
    for table, column in _COLUMNS.items():
        if table in tables and not _has_column(table, "correlation_id"):
            op.add_column(table, column)

    # Existing Agent children can be deterministically linked to one parent run.
    if "agent_runs" in tables and _has_column("agent_runs", "correlation_id"):
        op.execute(sa.text("UPDATE agent_runs SET correlation_id = id WHERE correlation_id IS NULL OR correlation_id = ''"))
    for table in ("agent_run_steps", "agent_events", "agent_approvals", "agent_artifact_refs", "agent_jobs"):
        if table in tables and _has_column(table, "correlation_id") and "agent_runs" in tables:
            op.execute(sa.text(
                f"UPDATE {table} SET correlation_id = "
                "(SELECT correlation_id FROM agent_runs WHERE agent_runs.id = " + table + ".run_id) "
                "WHERE correlation_id IS NULL OR correlation_id = ''"
            ))
    if "task_runtime_events" in tables and "task_runtime_tasks" in tables and _has_column("task_runtime_events", "correlation_id"):
        op.execute(sa.text(
            "UPDATE task_runtime_events SET correlation_id = "
            "(SELECT correlation_id FROM task_runtime_tasks "
            "WHERE task_runtime_tasks.task_id = task_runtime_events.task_id) "
            "WHERE correlation_id IS NULL OR correlation_id = ''"
        ))

    for table in _COLUMNS:
        if table in tables and _has_column(table, "correlation_id"):
            index_name = f"ix_{table}_correlation_id"
            if not _has_index(table, index_name):
                op.create_index(index_name, table, ["correlation_id"])
    # A unique index works on SQLite and MySQL, unlike ALTER TABLE ADD CONSTRAINT on SQLite.
    if "agent_runs" in tables and _has_column("agent_runs", "correlation_id") and not _has_index("agent_runs", "uq_agent_runs_correlation_id"):
        op.create_index("uq_agent_runs_correlation_id", "agent_runs", ["correlation_id"], unique=True)


def downgrade() -> None:
    tables = set(inspect(op.get_bind()).get_table_names())
    if "agent_runs" in tables and _has_index("agent_runs", "uq_agent_runs_correlation_id"):
        op.drop_index("uq_agent_runs_correlation_id", table_name="agent_runs")
    for table in reversed(tuple(_COLUMNS)):
        if table not in tables or not _has_column(table, "correlation_id"):
            continue
        index_name = f"ix_{table}_correlation_id"
        if _has_index(table, index_name):
            op.drop_index(index_name, table_name=table)
        op.drop_column(table, "correlation_id")
