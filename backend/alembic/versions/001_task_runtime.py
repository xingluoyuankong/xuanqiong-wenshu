"""Add persistent task runtime tables and adopt partial legacy schemas."""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "001_task_runtime"
down_revision: Union[str, None] = "000_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MIGRATION_MARKER = "xq_task_runtime_migration"

# Old create_all databases can contain a partial task-runtime table. Repair all
# columns before creating indexes/constraints so adoption cannot fail with
# "no such column".
TASK_COLUMNS = (
    ("owner_user_id", sa.Integer(), True, None),
    ("project_id", sa.String(length=64), True, None),
    ("chapter_id", sa.String(length=64), True, None),
    ("task_type", sa.String(length=96), False, sa.text("'legacy'")),
    ("idempotency_key", sa.String(length=255), True, None),
    ("status", sa.String(length=24), False, sa.text("'queued'")),
    ("stage", sa.String(length=128), True, None),
    ("progress", sa.Float(), False, sa.text("0")),
    ("message", sa.Text(), True, None),
    ("event_cursor", sa.BigInteger(), False, sa.text("0")),
    ("retry_count", sa.Integer(), False, sa.text("0")),
    ("max_retries", sa.Integer(), False, sa.text("3")),
    ("lease_owner", sa.String(length=128), True, None),
    ("heartbeat_at", sa.DateTime(timezone=True), True, None),
    ("started_at", sa.DateTime(timezone=True), True, None),
    ("finished_at", sa.DateTime(timezone=True), True, None),
    ("error_code", sa.String(length=96), True, None),
    ("error_detail", sa.Text(), True, None),
    ("result_ref", sa.String(length=255), True, None),
    ("payload", sa.JSON(), True, None),
    ("elapsed_ms", sa.BigInteger(), False, sa.text("0")),
    ("input_tokens", sa.BigInteger(), False, sa.text("0")),
    ("output_tokens", sa.BigInteger(), False, sa.text("0")),
    ("total_tokens", sa.BigInteger(), False, sa.text("0")),
    ("created_at", sa.DateTime(timezone=True), False, sa.text("'1970-01-01 00:00:00'")),
    ("updated_at", sa.DateTime(timezone=True), False, sa.text("'1970-01-01 00:00:00'")),
)
EVENT_COLUMNS = (
    ("status", sa.String(length=24), True, None),
    ("stage", sa.String(length=128), True, None),
    ("progress", sa.Float(), True, None),
    ("message", sa.Text(), True, None),
    ("idempotency_key", sa.String(length=255), True, None),
    ("payload", sa.JSON(), True, None),
    ("created_at", sa.DateTime(timezone=True), False, sa.text("'1970-01-01 00:00:00'")),
)


def _table_exists(bind, table_name: str) -> bool:
    return inspect(bind).has_table(table_name)


def _ensure_index(table_name: str, index_name: str, columns: list[str]) -> None:
    bind = op.get_bind()
    indexes = inspect(bind).get_indexes(table_name)
    if any(index.get("name") == index_name for index in indexes):
        return
    op.create_index(index_name, table_name, columns)


def _ensure_columns(table_name: str, definitions) -> None:
    bind = op.get_bind()
    existing = {column["name"] for column in inspect(bind).get_columns(table_name)}
    for column_name, column_type, nullable, server_default in definitions:
        if column_name not in existing:
            op.add_column(
                table_name,
                sa.Column(column_name, column_type, nullable=nullable, server_default=server_default),
            )
            existing.add(column_name)


def _marker_state() -> tuple[bool, bool] | None:
    bind = op.get_bind()
    if not _table_exists(bind, _MIGRATION_MARKER):
        return None
    row = bind.execute(
        sa.text(f"SELECT tasks_preexisting, events_preexisting FROM {_MIGRATION_MARKER} WHERE id = 1")
    ).first()
    return (bool(row[0]), bool(row[1])) if row is not None else None


def _record_marker(tasks_preexisting: bool, events_preexisting: bool) -> None:
    op.create_table(
        _MIGRATION_MARKER,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tasks_preexisting", sa.Integer(), nullable=False),
        sa.Column("events_preexisting", sa.Integer(), nullable=False),
    )
    op.get_bind().execute(
        sa.text(
            f"INSERT INTO {_MIGRATION_MARKER} (id, tasks_preexisting, events_preexisting) "
            "VALUES (1, :tasks, :events)"
        ),
        {"tasks": int(tasks_preexisting), "events": int(events_preexisting)},
    )


def upgrade() -> None:
    """Create or adopt durable task state without destroying legacy data."""
    bind = op.get_bind()
    marker = _marker_state()
    if marker is None:
        tasks_preexisting = _table_exists(bind, "task_runtime_tasks")
        events_preexisting = _table_exists(bind, "task_runtime_events")
        # 000 creates the current ORM tables for a fresh database. Those tables
        # are migration-owned and must still be removed on downgrade.
        if _table_exists(bind, "xq_schema_baseline_marker"):
            tasks_preexisting = False
            events_preexisting = False
        _record_marker(tasks_preexisting, events_preexisting)

    if not _table_exists(bind, "task_runtime_tasks"):
        op.create_table(
            "task_runtime_tasks",
            sa.Column("task_id", sa.String(length=64), nullable=False),
            sa.Column("owner_user_id", sa.Integer(), nullable=True),
            sa.Column("project_id", sa.String(length=64), nullable=True),
            sa.Column("chapter_id", sa.String(length=64), nullable=True),
            sa.Column("task_type", sa.String(length=96), nullable=False),
            sa.Column("idempotency_key", sa.String(length=255), nullable=True),
            sa.Column("status", sa.String(length=24), server_default=sa.text("'queued'"), nullable=False),
            sa.Column("stage", sa.String(length=128), nullable=True),
            sa.Column("progress", sa.Float(), server_default=sa.text("0"), nullable=False),
            sa.Column("message", sa.Text(), nullable=True),
            sa.Column("event_cursor", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
            sa.Column("retry_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
            sa.Column("max_retries", sa.Integer(), server_default=sa.text("3"), nullable=False),
            sa.Column("lease_owner", sa.String(length=128), nullable=True),
            sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("error_code", sa.String(length=96), nullable=True),
            sa.Column("error_detail", sa.Text(), nullable=True),
            sa.Column("result_ref", sa.String(length=255), nullable=True),
            sa.Column("payload", sa.JSON(), nullable=True),
            sa.Column("elapsed_ms", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
            sa.Column("input_tokens", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
            sa.Column("output_tokens", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
            sa.Column("total_tokens", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.PrimaryKeyConstraint("task_id"),
            sa.UniqueConstraint("idempotency_key", name="uq_task_runtime_idempotency_key"),
        )
    else:
        _ensure_columns("task_runtime_tasks", TASK_COLUMNS)

    for index_name, columns in (
        ("ix_task_runtime_tasks_owner_user_id", ["owner_user_id"]),
        ("ix_task_runtime_tasks_project_id", ["project_id"]),
        ("ix_task_runtime_tasks_chapter_id", ["chapter_id"]),
        ("ix_task_runtime_tasks_task_type", ["task_type"]),
        ("ix_task_runtime_tasks_status", ["status"]),
    ):
        _ensure_index("task_runtime_tasks", index_name, columns)

    if not _table_exists(bind, "task_runtime_events"):
        op.create_table(
            "task_runtime_events",
            sa.Column("event_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), autoincrement=True, nullable=False),
            sa.Column("task_id", sa.String(length=64), nullable=False),
            sa.Column("event_type", sa.String(length=48), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=True),
            sa.Column("stage", sa.String(length=128), nullable=True),
            sa.Column("progress", sa.Float(), nullable=True),
            sa.Column("message", sa.Text(), nullable=True),
            sa.Column("idempotency_key", sa.String(length=255), nullable=True),
            sa.Column("payload", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.ForeignKeyConstraint(["task_id"], ["task_runtime_tasks.task_id"], name="fk_task_runtime_events_task_id", ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("event_id"),
            sa.UniqueConstraint("task_id", "idempotency_key", name="uq_task_runtime_event_idempotency"),
        )
    else:
        _ensure_columns("task_runtime_events", EVENT_COLUMNS)
    _ensure_index("task_runtime_events", "ix_task_runtime_events_task_id", ["task_id"])
    _ensure_index("task_runtime_events", "ix_task_runtime_events_event_type", ["event_type"])


def downgrade() -> None:
    """Drop only migration-owned tables; preserve adopted legacy data."""
    bind = op.get_bind()
    marker = _marker_state()
    # A missing marker is treated conservatively: an older build may have
    # adopted these tables, so never destroy them during downgrade.
    events_owned = marker is not None and not marker[1]
    tasks_owned = marker is not None and not marker[0]
    if events_owned and _table_exists(bind, "task_runtime_events"):
        for index_name in ("ix_task_runtime_events_event_type", "ix_task_runtime_events_task_id"):
            if any(index.get("name") == index_name for index in inspect(bind).get_indexes("task_runtime_events")):
                op.drop_index(index_name, table_name="task_runtime_events")
        op.drop_table("task_runtime_events")
    if tasks_owned and _table_exists(bind, "task_runtime_tasks"):
        for index_name in (
            "ix_task_runtime_tasks_status",
            "ix_task_runtime_tasks_task_type",
            "ix_task_runtime_tasks_chapter_id",
            "ix_task_runtime_tasks_project_id",
            "ix_task_runtime_tasks_owner_user_id",
        ):
            if any(index.get("name") == index_name for index in inspect(bind).get_indexes("task_runtime_tasks")):
                op.drop_index(index_name, table_name="task_runtime_tasks")
        op.drop_table("task_runtime_tasks")
    if _table_exists(bind, _MIGRATION_MARKER):
        op.drop_table(_MIGRATION_MARKER)
