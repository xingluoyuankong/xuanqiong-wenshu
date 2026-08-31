"""Enforce QualityResult artifact/run identity at the storage boundary.

Revision ID: 026_agent_quality_same_run_fence
Revises: 025_agent_context_plan
Create Date: 2026-08-30

QualityResult references AgentRun directly and AgentArtifactRef indirectly.  The
application resolver already verifies that both references belong to the same
Run.  This migration adds database triggers so direct SQL or a future write path
cannot persist a mismatched pair on the supported SQLite/MySQL deployments.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect, text


revision: str = "026_agent_quality_same_run_fence"
down_revision: Union[str, None] = "025_agent_context_plan"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RESULT_TABLE = "agent_quality_results"
ARTIFACT_TABLE = "agent_artifact_refs"
INSERT_TRIGGER = "trg_agent_quality_result_artifact_run_insert"
UPDATE_TRIGGER = "trg_agent_quality_result_artifact_run_update"
TRIGGERS = (INSERT_TRIGGER, UPDATE_TRIGGER)
ERROR_TEXT = "agent_quality_result artifact_ref_id must belong to run_id"


def _tables() -> set[str]:
    return set(inspect(op.get_bind()).get_table_names())


def _dialect() -> str:
    return str(op.get_bind().dialect.name)


def _sqlite_upgrade() -> None:
    op.execute(text(f"""
        CREATE TRIGGER IF NOT EXISTS {INSERT_TRIGGER}
        BEFORE INSERT ON {RESULT_TABLE}
        WHEN NEW.artifact_ref_id IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM {ARTIFACT_TABLE}
            WHERE id = NEW.artifact_ref_id AND run_id = NEW.run_id
          )
        BEGIN
          SELECT RAISE(ABORT, '{ERROR_TEXT}');
        END
    """))
    op.execute(text(f"""
        CREATE TRIGGER IF NOT EXISTS {UPDATE_TRIGGER}
        BEFORE UPDATE OF artifact_ref_id, run_id ON {RESULT_TABLE}
        WHEN NEW.artifact_ref_id IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM {ARTIFACT_TABLE}
            WHERE id = NEW.artifact_ref_id AND run_id = NEW.run_id
          )
        BEGIN
          SELECT RAISE(ABORT, '{ERROR_TEXT}');
        END
    """))


def _mysql_trigger_exists(name: str) -> bool:
    return bool(op.get_bind().execute(text("""
        SELECT 1
        FROM information_schema.TRIGGERS
        WHERE TRIGGER_SCHEMA = DATABASE() AND TRIGGER_NAME = :name
        LIMIT 1
    """), {"name": name}).scalar())


def _mysql_upgrade() -> None:
    definitions = {
        INSERT_TRIGGER: f"""
            CREATE TRIGGER {INSERT_TRIGGER}
            BEFORE INSERT ON {RESULT_TABLE}
            FOR EACH ROW
            BEGIN
              IF NEW.artifact_ref_id IS NOT NULL
                 AND (SELECT COUNT(*) FROM {ARTIFACT_TABLE}
                      WHERE id = NEW.artifact_ref_id AND run_id = NEW.run_id) = 0 THEN
                SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '{ERROR_TEXT}';
              END IF;
            END
        """,
        UPDATE_TRIGGER: f"""
            CREATE TRIGGER {UPDATE_TRIGGER}
            BEFORE UPDATE ON {RESULT_TABLE}
            FOR EACH ROW
            BEGIN
              IF NEW.artifact_ref_id IS NOT NULL
                 AND (SELECT COUNT(*) FROM {ARTIFACT_TABLE}
                      WHERE id = NEW.artifact_ref_id AND run_id = NEW.run_id) = 0 THEN
                SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '{ERROR_TEXT}';
              END IF;
            END
        """,
    }
    for name, statement in definitions.items():
        if not _mysql_trigger_exists(name):
            op.execute(text(statement))


def upgrade() -> None:
    if not {RESULT_TABLE, ARTIFACT_TABLE} <= _tables():
        return
    dialect = _dialect()
    if dialect == "sqlite":
        _sqlite_upgrade()
    elif dialect == "mysql":
        _mysql_upgrade()


def downgrade() -> None:
    dialect = _dialect()
    if dialect not in {"sqlite", "mysql"}:
        return
    for trigger in TRIGGERS:
        op.execute(text(f"DROP TRIGGER IF EXISTS {trigger}"))
