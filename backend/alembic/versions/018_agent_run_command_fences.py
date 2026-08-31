"""Add command fences and explicit Run lifecycle markers.

Revision ID: 018_agent_run_command_fences
Revises: 017_agent_run_commands
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "018_agent_run_command_fences"
down_revision: Union[str, None] = "017_agent_run_commands"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table: str) -> set[str]:
    inspector = inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {item["name"] for item in inspector.get_columns(table)}


def _add(table: str, column: sa.Column) -> None:
    if column.name not in _columns(table):
        op.add_column(table, column)


def _unique_constraints(table: str) -> set[str]:
    inspector = inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {
        str(item.get("name"))
        for item in inspector.get_unique_constraints(table)
        if item.get("name")
    }


def upgrade() -> None:
    if "agent_runs" in inspect(op.get_bind()).get_table_names():
        _add("agent_runs", sa.Column("state_version", sa.Integer(), nullable=False, server_default="0"))
        _add("agent_runs", sa.Column("pause_reason", sa.String(32), nullable=True))
        _add("agent_runs", sa.Column("resume_target_status", sa.String(24), nullable=True))

    if "agent_run_commands" not in inspect(op.get_bind()).get_table_names():
        return
    _add("agent_run_commands", sa.Column("idempotency_key", sa.String(255), nullable=True))
    _add("agent_run_commands", sa.Column("payload_hash", sa.String(64), nullable=False, server_default=""))
    _add("agent_run_commands", sa.Column("expected_state_version", sa.Integer(), nullable=True))
    _add("agent_run_commands", sa.Column("result_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    _add("agent_run_commands", sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"))
    _add("agent_run_commands", sa.Column("lease_owner", sa.String(128), nullable=True))
    _add("agent_run_commands", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    _add("agent_run_commands", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    _add("agent_run_commands", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))
    # Backfill old 017 rows deterministically before creating the idempotency index.
    op.execute(sa.text("UPDATE agent_run_commands SET idempotency_key = 'legacy:' || id WHERE idempotency_key IS NULL"))
    op.execute(sa.text("UPDATE agent_run_commands SET payload_hash = '' WHERE payload_hash IS NULL"))
    index_names = {item.get("name") for item in inspect(op.get_bind()).get_indexes("agent_run_commands")}
    # Fresh installs are created by 000_initial_schema from the current ORM
    # metadata, which already contains the named table-level UniqueConstraint.
    # Legacy 017 databases do not have it and need the explicit unique index.
    if (
        "uq_agent_run_command_idempotency" not in index_names
        and "uq_agent_run_command_idempotency" not in _unique_constraints("agent_run_commands")
    ):
        op.create_index(
            "uq_agent_run_command_idempotency",
            "agent_run_commands",
            ["run_id", "idempotency_key"],
            unique=True,
        )
    for name, columns in {
        "ix_agent_run_commands_lease_owner": ["lease_owner"],
        "ix_agent_run_commands_lease_expires_at": ["lease_expires_at"],
    }.items():
        if name not in index_names:
            op.create_index(name, "agent_run_commands", columns)


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "agent_run_commands" in tables:
        indexes = {item.get("name") for item in inspector.get_indexes("agent_run_commands")}
        for name in ["ix_agent_run_commands_lease_expires_at", "ix_agent_run_commands_lease_owner", "uq_agent_run_command_idempotency"]:
            if name in indexes:
                op.drop_index(name, table_name="agent_run_commands")
        # A fresh baseline may carry the same named table-level constraint
        # from AgentRunCommand.__table_args__. SQLite cannot drop one of its
        # columns while that constraint remains. In that case 017/000 owns the
        # table cleanup; do not corrupt the baseline table here.
        if "uq_agent_run_command_idempotency" not in _unique_constraints("agent_run_commands"):
            for name in ["finished_at", "started_at", "lease_expires_at", "lease_owner", "attempt_count", "result_json", "expected_state_version", "payload_hash", "idempotency_key"]:
                if name in _columns("agent_run_commands"):
                    op.drop_column("agent_run_commands", name)
    if "agent_runs" in tables:
        for name in ["resume_target_status", "pause_reason", "state_version"]:
            if name in _columns("agent_runs"):
                op.drop_column("agent_runs", name)
