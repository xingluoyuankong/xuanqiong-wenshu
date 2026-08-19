"""Create the versioned baseline schema for fresh installations.

This baseline adopts legacy databases without dropping or rewriting existing
data. Fresh databases receive the complete ORM schema before later revisions
add task-runtime compatibility and lease constraints.
"""
from __future__ import annotations

from typing import Sequence, Union
import warnings

from alembic import op
import sqlalchemy as sa
from sqlalchemy.exc import SAWarning
from sqlalchemy import inspect

from app.db.base import Base
import app.models  # noqa: F401 - register every mapped table

revision: str = "000_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MARKER = "xq_schema_baseline_marker"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    had_legacy_tables = any(
        inspector.has_table(name)
        for name in ("novel_projects", "users", "task_runtime_tasks", "task_runtime_events")
    )
    Base.metadata.create_all(bind=bind)
    if not had_legacy_tables and not inspect(bind).has_table(_MARKER):
        op.create_table(
            _MARKER,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        )
        bind.execute(sa.text(f"INSERT INTO {_MARKER} (id) VALUES (1)"))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table(_MARKER):
        return
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="Can't sort tables for DROP; an unresolvable foreign key dependency exists",
            category=SAWarning,
        )
        Base.metadata.drop_all(bind=bind)
    if inspect(bind).has_table(_MARKER):
        op.drop_table(_MARKER)
