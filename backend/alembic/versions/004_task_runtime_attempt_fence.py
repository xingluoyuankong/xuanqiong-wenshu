"""Add task attempts and lease-generation event fences."""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "004_task_runtime_attempt_fence"
down_revision: Union[str, None] = "003_schema_compatibility"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector():
    return inspect(op.get_bind())


def _has_table(table: str) -> bool:
    return _inspector().has_table(table)


def _has_column(table: str, column: str) -> bool:
    return column in {item["name"] for item in _inspector().get_columns(table)}


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    if _has_table(table) and not _has_column(table, column.name):
        op.add_column(table, column)


def upgrade() -> None:
    _add_column_if_missing(
        "task_runtime_tasks",
        sa.Column("attempt", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    _add_column_if_missing(
        "task_runtime_tasks",
        sa.Column("lease_generation", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    for name, length in (
        ("input_hash", 128),
        ("config_snapshot_id", 128),
        ("artifact_ref", 255),
        ("artifact_revision", 128),
    ):
        _add_column_if_missing(
            "task_runtime_tasks",
            sa.Column(name, sa.String(length=length), nullable=True),
        )
    _add_column_if_missing(
        "task_runtime_events",
        sa.Column("attempt", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    _add_column_if_missing(
        "task_runtime_events",
        sa.Column("lease_generation", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    _add_column_if_missing(
        "task_runtime_events",
        sa.Column("channel", sa.String(length=32), nullable=True),
    )
    _add_column_if_missing(
        "task_runtime_events",
        sa.Column("sequence", sa.BigInteger(), nullable=True),
    )

    if _has_table("task_runtime_events"):
        bind = op.get_bind()
        bind.execute(
            sa.text(
                "UPDATE task_runtime_events "
                "SET sequence = event_id "
                "WHERE sequence IS NULL"
            )
        )

    _add_column_if_missing(
        "chapters",
        sa.Column("revision", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    _add_column_if_missing(
        "chapter_versions",
        sa.Column("content_hash", sa.String(length=64), nullable=True),
    )
    _add_column_if_missing(
        "chapter_versions",
        sa.Column("parent_version_id", sa.BigInteger(), nullable=True),
    )
    _add_column_if_missing(
        "chapter_versions",
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'candidate'")),
    )
    _add_column_if_missing(
        "chapter_snapshots",
        sa.Column("version_id", sa.Integer(), nullable=True),
    )
    _add_column_if_missing(
        "chapter_snapshots",
        sa.Column("content_hash", sa.String(length=64), nullable=True),
    )
    if _has_table("chapter_versions"):
        op.get_bind().execute(
            sa.text(
                "UPDATE chapter_versions SET status = 'candidate' "
                "WHERE status IS NULL OR status = ''"
            )
        )


def downgrade() -> None:
    # Attempt and event-fence columns are append-only compatibility data. Keeping
    # them avoids erasing execution provenance when an application binary rolls back.
    return
