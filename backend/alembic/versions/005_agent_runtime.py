"""Create persistent Agent runtime tables."""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "005_agent_runtime"
down_revision: Union[str, None] = "004_task_runtime_attempt_fence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    return inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    # 000_initial_schema uses Base.metadata.create_all, so a fresh database may
    # already contain these tables before revision 005 is recorded.
    if all(_has_table(name) for name in ("agent_sessions", "agent_messages", "agent_runs", "agent_events", "agent_approvals", "agent_artifact_refs")):
        return
    op.create_table(
        "agent_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("novel_projects.id", ondelete="CASCADE"), nullable=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_agent_sessions_user_id", "agent_sessions", ["user_id"])
    op.create_index("ix_agent_sessions_project_id", "agent_sessions", ["project_id"])
    op.create_index("ix_agent_sessions_status", "agent_sessions", ["status"])

    op.create_table(
        "agent_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(24), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("session_id", "sequence", name="uq_agent_message_sequence"),
    )
    op.create_index("ix_agent_messages_session_id", "agent_messages", ["session_id"])
    op.create_index("ix_agent_messages_user_id", "agent_messages", ["user_id"])

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.String(120), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="created"),
        sa.Column("current_phase", sa.String(80), nullable=True),
        sa.Column("current_step", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("progress", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_agent_runs_session_id", "agent_runs", ["session_id"])
    op.create_index("ix_agent_runs_user_id", "agent_runs", ["user_id"])
    op.create_index("ix_agent_runs_project_id", "agent_runs", ["project_id"])
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"])

    op.create_table(
        "agent_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("summary", sa.String(1000), nullable=False),
        sa.Column("data_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("run_id", "sequence", name="uq_agent_event_sequence"),
    )
    op.create_index("ix_agent_events_run_id", "agent_events", ["run_id"])
    op.create_index("ix_agent_events_user_id", "agent_events", ["user_id"])
    op.create_index("ix_agent_events_event_type", "agent_events", ["event_type"])

    op.create_table(
        "agent_approvals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.String(120), nullable=True),
        sa.Column("tool_name", sa.String(120), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
    )
    op.create_index("ix_agent_approvals_run_id", "agent_approvals", ["run_id"])
    op.create_index("ix_agent_approvals_user_id", "agent_approvals", ["user_id"])
    op.create_index("ix_agent_approvals_project_id", "agent_approvals", ["project_id"])
    op.create_index("ix_agent_approvals_status", "agent_approvals", ["status"])

    op.create_table(
        "agent_artifact_refs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.String(120), nullable=True),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("uri", sa.String(500), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_agent_artifact_refs_run_id", "agent_artifact_refs", ["run_id"])
    op.create_index("ix_agent_artifact_refs_user_id", "agent_artifact_refs", ["user_id"])
    op.create_index("ix_agent_artifact_refs_project_id", "agent_artifact_refs", ["project_id"])


def downgrade() -> None:
    for name in ("agent_artifact_refs", "agent_approvals", "agent_events", "agent_runs", "agent_messages", "agent_sessions"):
        if _has_table(name):
            op.drop_table(name)
