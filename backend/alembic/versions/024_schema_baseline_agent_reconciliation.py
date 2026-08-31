"""Reconcile published Agent relational-table schema against the ORM baseline.

Revision ID: 024_schema_baseline_agent_reconciliation
Revises: 023_agent_quality_lineage
Create Date: 2026-08-28

This migration is deliberately append-only.  Older installations can contain an
early 020 table shape because the original create-if-missing migration could not
add columns to a pre-existing table.  The two fields below are nullable resolver
metadata, so adding them is safe for historical rows and repeatable deployments.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "024_schema_baseline_agent_reconciliation"
down_revision: Union[str, None] = "023_agent_quality_lineage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SNAPSHOT_TABLE = "agent_run_capability_snapshots"
MISSING_SNAPSHOT_COLUMNS = (
    ("selection_reason", sa.String(255)),
    ("resolved_version", sa.String(64)),
)


def _snapshot_columns() -> set[str]:
    bind = op.get_bind()
    inspector = inspect(bind)
    if SNAPSHOT_TABLE not in set(inspector.get_table_names()):
        return set()
    return {str(column["name"]) for column in inspector.get_columns(SNAPSHOT_TABLE)}


def upgrade() -> None:
    """Add only nullable Resolver Snapshot metadata missing from legacy 020 tables."""
    existing_columns = _snapshot_columns()
    if not existing_columns:
        return
    for name, column_type in MISSING_SNAPSHOT_COLUMNS:
        if name not in existing_columns:
            op.add_column(SNAPSHOT_TABLE, sa.Column(name, column_type, nullable=True))
            existing_columns.add(name)


def downgrade() -> None:
    """Keep reconciliation columns on downgrade to avoid destructive SQLite rebuilds.

    The columns are nullable, have no default or data backfill, and are harmless to
    the 023 schema.  Later downgrade steps drop the whole relational table when
    returning before 020, so this no-op preserves data and remains repeatable.
    """
