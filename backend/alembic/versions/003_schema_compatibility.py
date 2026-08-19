"""Version historical compatibility repairs instead of startup ALTER TABLE."""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision: str = "003_schema_compatibility"
down_revision: Union[str, None] = "002_ledger_lease_and_runtime_metrics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector():
    return inspect(op.get_bind())


def _has_table(table: str) -> bool:
    return _inspector().has_table(table)


def _has_column(table: str, column: str) -> bool:
    return column in {item["name"] for item in _inspector().get_columns(table)}


def _has_index(table: str, name: str) -> bool:
    inspector = _inspector()
    return any(item.get("name") == name for item in inspector.get_indexes(table)) or any(
        item.get("name") == name for item in inspector.get_unique_constraints(table)
    )


def _has_duplicates(table: str) -> bool:
    row = op.get_bind().execute(
        text(f"SELECT project_id, chapter_number FROM {table} GROUP BY project_id, chapter_number HAVING COUNT(*) > 1 LIMIT 1")
    ).first()
    return row is not None


def upgrade() -> None:
    bind = op.get_bind()
    if _has_table("chapter_outlines"):
        if not _has_column("chapter_outlines", "metadata"):
            op.add_column("chapter_outlines", sa.Column("metadata", sa.JSON(), nullable=True))
        if not _has_index("chapter_outlines", "uq_chapter_outlines_project_chapter_number") and not _has_duplicates("chapter_outlines"):
            op.create_index(
                "uq_chapter_outlines_project_chapter_number",
                "chapter_outlines",
                ["project_id", "chapter_number"],
                unique=True,
            )

    if _has_table("chapters") and not _has_index("chapters", "uq_chapters_project_chapter_number") and not _has_duplicates("chapters"):
        op.create_index("uq_chapters_project_chapter_number", "chapters", ["project_id", "chapter_number"], unique=True)

    if _has_table("llm_configs") and not _has_column("llm_configs", "llm_provider_profiles"):
        op.add_column("llm_configs", sa.Column("llm_provider_profiles", sa.Text(), nullable=True))

    if _has_table("user_style_libraries"):
        for name in ("style_sources_json", "style_profiles_json", "global_active_profile_id"):
            if not _has_column("user_style_libraries", name):
                op.add_column("user_style_libraries", sa.Column(name, sa.Text(), nullable=True))


def downgrade() -> None:
    # These repairs may have adopted data from a legacy database. Keep columns
    # and uniqueness guarantees on downgrade rather than silently deleting data.
    return
