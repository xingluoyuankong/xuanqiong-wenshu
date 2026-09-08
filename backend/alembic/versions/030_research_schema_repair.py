"""Repair missing research tables on installations already at revision 029.

Definitions are frozen here rather than imported from application metadata:
legacy baseline creation depended on which model modules were imported first.
Existing research tables and records are deliberately retained on downgrade.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "030_research_schema_repair"
down_revision = "029_project_members"
branch_labels = None
depends_on = None

# Match novel_projects.id, including the MySQL foreign-key collation.
PROJECT_ID_TYPE = sa.String(36).with_variant(
    sa.String(36, collation="utf8mb4_unicode_ci"), "mysql"
)
ARTIFACT_INDEX_COLUMNS = (
    "run_id", "project_id", "user_id", "scope", "chapter_number", "status",
)


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "project_research_configs" not in tables:
        op.create_table(
            "project_research_configs",
            sa.Column("project_id", PROJECT_ID_TYPE, primary_key=True, nullable=False),
            sa.Column("mode", sa.String(16), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False),
            sa.Column("search_provider", sa.String(32), nullable=False),
            sa.Column("search_base_url", sa.Text(), nullable=True),
            sa.Column("search_api_key_encrypted", sa.Text(), nullable=True),
            sa.Column("research_llm_base_url", sa.Text(), nullable=True),
            sa.Column("research_llm_model", sa.String(255), nullable=True),
            sa.Column("research_llm_api_key_encrypted", sa.Text(), nullable=True),
            sa.Column("reuse_writing_llm", sa.Boolean(), nullable=False),
            sa.Column("local_model_enabled", sa.Boolean(), nullable=False),
            sa.Column("global_research_enabled", sa.Boolean(), nullable=False),
            sa.Column("enhanced_research_enabled", sa.Boolean(), nullable=False),
            sa.Column("chapter_research_enabled", sa.Boolean(), nullable=False),
            sa.Column("max_parallel_queries", sa.Integer(), nullable=False),
            sa.Column("max_results_per_query", sa.Integer(), nullable=False),
            sa.Column("preferred_domains", sa.JSON(), nullable=True),
            sa.Column("blocked_domains", sa.JSON(), nullable=True),
            sa.Column("category_preferences", sa.JSON(), nullable=True),
            sa.Column("extra", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["project_id"], ["novel_projects.id"], ondelete="CASCADE"),
        )
    if "research_artifacts" not in tables:
        op.create_table(
            "research_artifacts",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("run_id", sa.String(36), nullable=False),
            sa.Column("project_id", PROJECT_ID_TYPE, nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("scope", sa.String(32), nullable=False),
            sa.Column("chapter_number", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(24), nullable=False),
            sa.Column("trigger", sa.String(32), nullable=False),
            sa.Column("query_plan", sa.JSON(), nullable=True),
            sa.Column("sources", sa.JSON(), nullable=True),
            sa.Column("category_payload", sa.JSON(), nullable=True),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("file_manifest", sa.JSON(), nullable=True),
            sa.Column("provider_metadata", sa.JSON(), nullable=True),
            sa.Column("error", sa.JSON(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["project_id"], ["novel_projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("project_id", "run_id", name="uq_research_artifacts_project_run"),
        )
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("research_artifacts")}
    for column in ARTIFACT_INDEX_COLUMNS:
        name = f"ix_research_artifacts_{column}"
        if name not in indexes:
            op.create_index(name, "research_artifacts", [column], unique=False)


def downgrade() -> None:
    """Retain research data, even when this revision originally created it.

    Revision 029 can already contain these ORM-created tables. Their provenance
    does not justify deleting saved configuration, sources or research results.
    Re-upgrading simply adopts them and checks the indexes again.
    """
    pass
