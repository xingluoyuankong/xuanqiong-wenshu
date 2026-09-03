"""Persist Provider reasoning chunks independently from the public event ledger."""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "028_agent_reasoning_chunks"
down_revision: Union[str, None] = "027_agent_terminal_event_key"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "agent_run_reasoning_chunks"


def _tables() -> set[str]:
    return set(inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if TABLE in _tables():
        return
    op.create_table(
        TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=120), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("phase", sa.String(length=80), nullable=True),
        sa.Column("action_id", sa.String(length=160), nullable=True),
        sa.Column("result_ref", sa.String(length=160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "chunk_index", name="uq_agent_reasoning_run_chunk"),
        sa.UniqueConstraint("run_id", "sequence", name="uq_agent_reasoning_run_sequence"),
    )
    op.create_index("ix_agent_run_reasoning_chunks_run_id", TABLE, ["run_id"], unique=False)
    op.create_index("ix_agent_run_reasoning_chunks_project_id", TABLE, ["project_id"], unique=False)
    op.create_index("ix_agent_run_reasoning_chunks_user_id", TABLE, ["user_id"], unique=False)
    op.create_index("ix_agent_reasoning_run_sequence", TABLE, ["run_id", "sequence"], unique=False)
    op.create_index("ix_agent_reasoning_run_chunk", TABLE, ["run_id", "chunk_index"], unique=False)


def downgrade() -> None:
    if TABLE not in _tables():
        return
    for name in (
        "ix_agent_reasoning_run_chunk",
        "ix_agent_reasoning_run_sequence",
        "ix_agent_run_reasoning_chunks_user_id",
        "ix_agent_run_reasoning_chunks_project_id",
        "ix_agent_run_reasoning_chunks_run_id",
    ):
        try:
            op.drop_index(name, table_name=TABLE)
        except Exception:
            pass
    op.drop_table(TABLE)
