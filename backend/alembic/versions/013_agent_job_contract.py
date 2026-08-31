"""Create durable Agent job contracts for worker handoff."""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
revision: str = "013_agent_job_contract"
down_revision: Union[str, None] = "012_agent_durable_control"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if "agent_jobs" in inspector.get_table_names():
        return
    op.create_table(
        "agent_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.String(120), nullable=True),
        sa.Column("kind", sa.String(80), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("result_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("error_type", sa.String(160), nullable=True),
        sa.Column("error_detail", sa.String(1000), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("lease_owner", sa.String(128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_agent_job_idempotency"),
    )
    for name, columns in {
        "ix_agent_jobs_run_id": ["run_id"], "ix_agent_jobs_user_id": ["user_id"],
        "ix_agent_jobs_project_id": ["project_id"], "ix_agent_jobs_kind": ["kind"],
        "ix_agent_jobs_status": ["status"], "ix_agent_jobs_available_at": ["available_at"],
        "ix_agent_jobs_lease_owner": ["lease_owner"], "ix_agent_jobs_lease_expires_at": ["lease_expires_at"],
        "ix_agent_jobs_cancel_requested_at": ["cancel_requested_at"],
    }.items():
        op.create_index(name, "agent_jobs", columns)

def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if "agent_jobs" not in inspector.get_table_names():
        return
    indexes = {item.get("name") for item in inspector.get_indexes("agent_jobs")}
    for name in ["ix_agent_jobs_cancel_requested_at", "ix_agent_jobs_lease_expires_at", "ix_agent_jobs_lease_owner", "ix_agent_jobs_available_at", "ix_agent_jobs_status", "ix_agent_jobs_kind", "ix_agent_jobs_project_id", "ix_agent_jobs_user_id", "ix_agent_jobs_run_id"]:
        if name in indexes: op.drop_index(name, table_name="agent_jobs")
    op.drop_table("agent_jobs")
