"""Formalize the project ledger lease and runtime accounting fields."""
from __future__ import annotations

from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "002_ledger_lease_and_runtime_metrics"
down_revision: Union[str, None] = "001_task_runtime"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MIGRATION_MARKER = "xq_ledger_lease_migration"
RUNTIME_METRICS = (
    ("elapsed_ms", sa.BigInteger()),
    ("input_tokens", sa.BigInteger()),
    ("output_tokens", sa.BigInteger()),
    ("total_tokens", sa.BigInteger()),
)


def _inspector():
    return inspect(op.get_bind())


def _has_table(table: str) -> bool:
    return _inspector().has_table(table)


def _has_index(table: str, name: str) -> bool:
    return any(item.get("name") == name for item in _inspector().get_indexes(table))


def _has_unique(table: str, columns: tuple[str, ...]) -> bool:
    inspector = _inspector()
    wanted = tuple(columns)
    for item in inspector.get_unique_constraints(table):
        if tuple(item.get("column_names") or ()) == wanted:
            return True
    return any(
        item.get("unique") and tuple(item.get("column_names") or ()) == wanted
        for item in inspector.get_indexes(table)
    )


def _ensure_column(table: str, name: str, column_type: sa.types.TypeEngine, *, nullable: bool = False, default=None) -> None:
    if name in {item["name"] for item in _inspector().get_columns(table)}:
        return
    op.add_column(table, sa.Column(name, column_type, nullable=nullable, server_default=default))


def _ensure_index(table: str, name: str, columns: list[str]) -> None:
    if not _has_index(table, name):
        op.create_index(name, table, columns)


def _ensure_unique(table: str, name: str, columns: list[str]) -> None:
    if _has_unique(table, tuple(columns)):
        return
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(table, recreate="always") as batch_op:
            batch_op.create_unique_constraint(name, columns)
    else:
        op.create_unique_constraint(name, table, columns)


def _repair_duplicate_nullable_keys(table: str, key_columns: list[str], identity_column: str, nullable_columns: list[str] | None = None) -> None:
    """Keep the first legacy idempotency key and null later duplicates."""
    bind = op.get_bind()
    nullable_columns = nullable_columns or key_columns
    if bind.dialect.name not in {"sqlite", "mysql", "postgresql"}:
        return
    projection = ", ".join(key_columns)
    where = " AND ".join(f"{column} IS NOT NULL" for column in key_columns)
    rows = bind.execute(
        sa.text(f"SELECT {identity_column}, {projection} FROM {table} WHERE {where} ORDER BY {identity_column}")
    ).fetchall()
    seen: set[tuple[object, ...]] = set()
    for row in rows:
        identity = row[0]
        key = tuple(row[1:])
        if key in seen:
            assignments = ", ".join(f"{column} = NULL" for column in nullable_columns)
            bind.execute(sa.text(f"UPDATE {table} SET {assignments} WHERE {identity_column} = :identity"), {"identity": identity})
        else:
            seen.add(key)


def _repair_lease_tokens() -> None:
    """Make legacy/malformed lease tokens unique before adding the constraint."""
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT project_id, lease_token FROM project_ledger_sync_leases ORDER BY project_id")
    ).fetchall()
    seen: set[str] = set()
    for project_id, token in rows:
        token = str(token) if token is not None else ""
        if not token or token in seen:
            token = uuid4().hex
            bind.execute(
                sa.text("UPDATE project_ledger_sync_leases SET lease_token = :token WHERE project_id = :project_id"),
                {"token": token, "project_id": project_id},
            )
        seen.add(token)


def _marker_state() -> bool | None:
    if not _has_table(_MIGRATION_MARKER):
        return None
    row = op.get_bind().execute(
        sa.text(f"SELECT lease_preexisting FROM {_MIGRATION_MARKER} WHERE id = 1")
    ).first()
    return bool(row[0]) if row is not None else None


def _record_marker(lease_preexisting: bool) -> None:
    op.create_table(
        _MIGRATION_MARKER,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lease_preexisting", sa.Integer(), nullable=False),
    )
    op.get_bind().execute(
        sa.text(f"INSERT INTO {_MIGRATION_MARKER} (id, lease_preexisting) VALUES (1, :value)"),
        {"value": int(lease_preexisting)},
    )


def upgrade() -> None:
    bind = op.get_bind()
    marker = _marker_state()
    if marker is None:
        lease_preexisting = _has_table("project_ledger_sync_leases")
        if _has_table("xq_schema_baseline_marker"):
            lease_preexisting = False
        _record_marker(lease_preexisting)

    if _has_table("task_runtime_tasks"):
        for name, column_type in RUNTIME_METRICS:
            _ensure_column("task_runtime_tasks", name, column_type, nullable=False, default=sa.text("0"))
        _repair_duplicate_nullable_keys("task_runtime_tasks", ["idempotency_key"], "task_id")
        _ensure_unique("task_runtime_tasks", "uq_task_runtime_idempotency_key", ["idempotency_key"])
        for name, columns in (
            ("ix_task_runtime_tasks_owner_user_id", ["owner_user_id"]),
            ("ix_task_runtime_tasks_project_id", ["project_id"]),
            ("ix_task_runtime_tasks_chapter_id", ["chapter_id"]),
            ("ix_task_runtime_tasks_task_type", ["task_type"]),
            ("ix_task_runtime_tasks_status", ["status"]),
        ):
            _ensure_index("task_runtime_tasks", name, columns)

    if _has_table("task_runtime_events"):
        _repair_duplicate_nullable_keys(
            "task_runtime_events", ["task_id", "idempotency_key"], "event_id", nullable_columns=["idempotency_key"]
        )
        _ensure_unique("task_runtime_events", "uq_task_runtime_event_idempotency", ["task_id", "idempotency_key"])
        _ensure_index("task_runtime_events", "ix_task_runtime_events_task_id", ["task_id"])
        _ensure_index("task_runtime_events", "ix_task_runtime_events_event_type", ["event_type"])

    if not _has_table("project_ledger_sync_leases"):
        constraints = [sa.PrimaryKeyConstraint("project_id")]
        if _has_table("novel_projects"):
            constraints.append(
                sa.ForeignKeyConstraint(
                    ["project_id"], ["novel_projects.id"],
                    name="fk_project_ledger_sync_lease_project_id", ondelete="CASCADE",
                )
            )
        op.create_table(
            "project_ledger_sync_leases",
            sa.Column("project_id", sa.String(length=36), nullable=False),
            sa.Column("chapter_number", sa.Integer(), server_default=sa.text("0"), nullable=False),
            sa.Column("selected_version_id", sa.Integer(), nullable=True),
            sa.Column("lease_token", sa.String(length=64), nullable=False),
            sa.Column("owner_id", sa.String(length=255), nullable=False),
            sa.Column("acquired_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            *constraints,
            sa.UniqueConstraint("lease_token", name="uq_project_ledger_sync_lease_token"),
        )
    else:
        # Legacy tables normally have all of these columns, but early builds
        # could have created a partial lease table. Keep existing rows usable.
        _ensure_column("project_ledger_sync_leases", "chapter_number", sa.Integer(), nullable=False, default=sa.text("0"))
        _ensure_column("project_ledger_sync_leases", "selected_version_id", sa.Integer(), nullable=True)
        _ensure_column("project_ledger_sync_leases", "lease_token", sa.String(length=64), nullable=True)
        _ensure_column("project_ledger_sync_leases", "owner_id", sa.String(length=255), nullable=True)
        _ensure_column("project_ledger_sync_leases", "acquired_at", sa.DateTime(timezone=True), nullable=True)
        _ensure_column("project_ledger_sync_leases", "expires_at", sa.DateTime(timezone=True), nullable=True)
        _repair_lease_tokens()

    _ensure_unique("project_ledger_sync_leases", "uq_project_ledger_sync_lease_token", ["lease_token"])
    _ensure_index("project_ledger_sync_leases", "ix_project_ledger_sync_leases_lease_token", ["lease_token"])
    _ensure_index("project_ledger_sync_leases", "ix_project_ledger_sync_leases_expires_at", ["expires_at"])


def downgrade() -> None:
    """Reverse only objects owned by this revision and preserve adopted leases."""
    bind = op.get_bind()
    marker = _marker_state()
    lease_owned = marker is not None and not marker
    if lease_owned and _has_table("project_ledger_sync_leases"):
        for name in ("ix_project_ledger_sync_leases_expires_at", "ix_project_ledger_sync_leases_lease_token"):
            if _has_index("project_ledger_sync_leases", name):
                op.drop_index(name, table_name="project_ledger_sync_leases")
        op.drop_table("project_ledger_sync_leases")
    if _has_table(_MIGRATION_MARKER):
        op.drop_table(_MIGRATION_MARKER)
