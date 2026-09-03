"""Create project membership grants and materialize legacy project owners."""
from __future__ import annotations

from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "029_project_members"
down_revision: Union[str, None] = "028_agent_reasoning_chunks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "project_members"
INDEXES = (
    ("ix_project_members_project_id", ["project_id"]),
    ("ix_project_members_user_id", ["user_id"]),
    ("ix_project_members_deleted_at", ["deleted_at"]),
)


def _tables() -> set[str]:
    return set(inspect(op.get_bind()).get_table_names())


def _indexes(table: str) -> set[str]:
    return {
        str(item["name"])
        for item in inspect(op.get_bind()).get_indexes(table)
        if item.get("name")
    }


def _create_table() -> None:
    if TABLE in _tables():
        return
    op.create_table(
        TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False, server_default="viewer"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["novel_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "user_id", name="uq_project_member_project_user"),
    )


def _create_indexes() -> None:
    if TABLE not in _tables():
        return
    existing = _indexes(TABLE)
    for name, columns in INDEXES:
        if name not in existing:
            op.create_index(name, TABLE, columns, unique=False)


def _backfill_legacy_owners() -> None:
    bind = op.get_bind()
    if TABLE not in _tables() or "novel_projects" not in _tables():
        return
    project_columns = {item["name"] for item in inspect(bind).get_columns("novel_projects")}
    # Some historical partial schemas only carried the project primary key.
    # They have no legacy owner to materialize; later project creation will add
    # the owner membership transactionally.
    if "id" not in project_columns or "user_id" not in project_columns:
        return

    rows = bind.execute(sa.text("SELECT id, user_id FROM novel_projects WHERE user_id IS NOT NULL")).mappings()
    membership_table = sa.table(
        TABLE,
        sa.column("id", sa.String(36)),
        sa.column("project_id", sa.String(36)),
        sa.column("user_id", sa.Integer()),
        sa.column("role", sa.String(16)),
    )
    for row in rows:
        exists = bind.execute(
            sa.text(
                "SELECT 1 FROM project_members "
                "WHERE project_id = :project_id AND user_id = :user_id"
            ),
            {"project_id": row["id"], "user_id": row["user_id"]},
        ).first()
        if exists:
            continue
        bind.execute(
            membership_table.insert().values(
                id=str(uuid4()),
                project_id=row["id"],
                user_id=row["user_id"],
                role="owner",
            )
        )


def upgrade() -> None:
    _create_table()
    _create_indexes()
    _backfill_legacy_owners()


def downgrade() -> None:
    if TABLE in _tables():
        op.drop_table(TABLE)
