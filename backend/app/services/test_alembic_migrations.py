from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from app.core.config import settings
from app.db.init_db import _run_schema_migrations


MIGRATION_TABLES = (
    "task_runtime_tasks",
    "task_runtime_events",
    "project_ledger_sync_leases",
    "agent_sessions",
    "agent_messages",
    "agent_runs",
    "agent_events",
    "agent_approvals",
    "agent_artifact_refs",
    "agent_run_steps",
    "agent_jobs",
    "agent_run_commands",
    "agent_run_reasoning_chunks",
)


def _config() -> Config:
    return Config(str(Path(__file__).parents[2] / "alembic.ini"))


def _upgrade(monkeypatch: pytest.MonkeyPatch, db_path: Path, target: str = "head") -> None:
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    command.upgrade(_config(), target)


def test_fresh_upgrade_is_repeatable_and_downgrade_is_clean(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "fresh.sqlite"
    _upgrade(monkeypatch, db_path)
    _upgrade(monkeypatch, db_path)

    con = sqlite3.connect(db_path)
    assert con.execute("select version_num from alembic_version").fetchone()[0] == "028_agent_reasoning_chunks"
    assert "step_id" in {row[1] for row in con.execute("pragma table_info(agent_approvals)")}
    assert {
        "cancel_requested_at", "cancel_reason", "event_sequence",
        "latest_public_summary_json", "latest_public_summary_sequence", "latest_public_summary_at",
    } <= {row[1] for row in con.execute("pragma table_info(agent_runs)")}
    assert con.execute("select 1 from sqlite_master where type='table' and name='agent_jobs'").fetchone() == (1,)
    for table in ("agent_catalog_releases", "agent_provider_releases", "agent_capability_definitions", "agent_run_capability_snapshots", "agent_capability_executions", "agent_quality_results", "agent_quality_findings", "agent_quality_gates", "agent_artifact_lineages", "agent_context_snapshots", "agent_context_snapshot_refs", "agent_plan_revisions", "agent_conversation_summaries"):
        assert con.execute("select 1 from sqlite_master where type='table' and name=?", (table,)).fetchone() == (1,)
    context_columns = {row[1] for row in con.execute("pragma table_info(agent_context_snapshots)")}
    assert {"run_id", "session_id", "context_json", "digest"} <= context_columns
    plan_columns = {row[1] for row in con.execute("pragma table_info(agent_plan_revisions)")}
    assert {"run_id", "session_id", "context_snapshot_id", "parent_revision_id", "revision_number", "digest"} <= plan_columns
    summary_columns = {row[1] for row in con.execute("pragma table_info(agent_conversation_summaries)")}
    assert {"session_id", "run_id", "start_message_sequence", "end_message_sequence", "source_digest", "digest"} <= summary_columns
    snapshot_columns = {row[1] for row in con.execute("pragma table_info(agent_run_capability_snapshots)")}
    assert {"selection_reason", "resolved_version"} <= snapshot_columns
    for table in ("agent_runs", "agent_run_steps", "agent_events", "agent_approvals", "agent_artifact_refs", "agent_run_commands", "agent_jobs", "agent_run_capability_snapshots", "agent_capability_executions", "agent_quality_results", "agent_quality_gates", "agent_artifact_lineages"):
        assert "transaction_id" in {row[1] for row in con.execute(f"pragma table_info({table})")}
    assert con.execute("select 1 from sqlite_master where type='table' and name='agent_run_commands'").fetchone() == (1,)
    assert {
        "id", "run_id", "correlation_id", "user_id", "command_type", "status", "reason",
        "idempotency_key", "payload_hash", "expected_state_version", "payload_json", "result_json",
        "error_type", "error_detail", "attempt_count", "lease_owner", "lease_expires_at",
        "requested_at", "started_at", "finished_at", "applied_at",
    } <= {row[1] for row in con.execute("pragma table_info(agent_run_commands)")}
    assert {"state_version", "pause_reason", "resume_target_status", "lease_generation", "transaction_id"} <= {
        row[1] for row in con.execute("pragma table_info(agent_runs)")
    }
    for lease_table in ("agent_run_steps", "agent_jobs", "agent_run_commands"):
        assert "lease_generation" in {row[1] for row in con.execute(f"pragma table_info({lease_table})")}
    assert con.execute(
        "select 1 from sqlite_master where type='table' and name='agent_run_steps'"
    ).fetchone() == (1,)
    assert set(row[1] for row in con.execute("pragma table_info(task_runtime_tasks)")) >= {
        "elapsed_ms", "input_tokens", "output_tokens", "total_tokens"
    }
    assert set(row[1] for row in con.execute("pragma table_info(project_ledger_sync_leases)")) >= {
        "project_id", "lease_token", "owner_id", "expires_at"
    }
    command.downgrade(_config(), "base")
    command.downgrade(_config(), "base")
    assert not any(
        con.execute("select 1 from sqlite_master where type='table' and name=?", (table,)).fetchone()
        for table in MIGRATION_TABLES
    )
    con.close()


def test_026_quality_result_same_run_triggers_reject_direct_cross_run_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The storage fence is repeatable and rejects INSERT/UPDATE bypassing services."""
    db_path = tmp_path / "quality-result-same-run-fence.sqlite"
    con = sqlite3.connect(db_path)
    con.executescript(
        """
        CREATE TABLE alembic_version (version_num VARCHAR(64) NOT NULL);
        INSERT INTO alembic_version VALUES ('025_agent_context_plan');
        CREATE TABLE agent_artifact_refs (
            id VARCHAR(36) PRIMARY KEY,
            run_id VARCHAR(36) NOT NULL
        );
        CREATE TABLE agent_quality_results (
            id VARCHAR(36) PRIMARY KEY,
            run_id VARCHAR(36) NOT NULL,
            artifact_ref_id VARCHAR(36)
        );
        INSERT INTO agent_artifact_refs (id, run_id) VALUES ('artifact-run-a', 'run-a');
        INSERT INTO agent_artifact_refs (id, run_id) VALUES ('artifact-run-b', 'run-b');
        """
    )
    con.commit()
    con.close()

    _upgrade(monkeypatch, db_path)
    _upgrade(monkeypatch, db_path)

    con = sqlite3.connect(db_path)
    trigger_names = {
        row[0]
        for row in con.execute("select name from sqlite_master where type='trigger'")
    }
    assert {
        "trg_agent_quality_result_artifact_run_insert",
        "trg_agent_quality_result_artifact_run_update",
    } <= trigger_names
    con.execute(
        "insert into agent_quality_results (id, run_id, artifact_ref_id) values (?, ?, ?)",
        ("result-valid", "run-a", "artifact-run-a"),
    )
    with pytest.raises(sqlite3.IntegrityError, match="artifact_ref_id must belong to run_id"):
        con.execute(
            "insert into agent_quality_results (id, run_id, artifact_ref_id) values (?, ?, ?)",
            ("result-invalid", "run-a", "artifact-run-b"),
        )
    with pytest.raises(sqlite3.IntegrityError, match="artifact_ref_id must belong to run_id"):
        con.execute(
            "update agent_quality_results set run_id=? where id=?",
            ("run-b", "result-valid"),
        )
    con.close()


@pytest.mark.asyncio
async def test_concurrent_schema_upgrades_are_serialized(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Multiple workers starting together must not race the baseline DDL."""
    db_path = tmp_path / "concurrent.sqlite"
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{db_path.as_posix()}")

    await asyncio.gather(_run_schema_migrations(), _run_schema_migrations())

    con = sqlite3.connect(db_path)
    assert con.execute("select version_num from alembic_version").fetchone()[0] == "028_agent_reasoning_chunks"
    assert "step_id" in {row[1] for row in con.execute("pragma table_info(agent_approvals)")}
    assert {
        "cancel_requested_at", "cancel_reason", "event_sequence",
        "latest_public_summary_json", "latest_public_summary_sequence", "latest_public_summary_at",
    } <= {row[1] for row in con.execute("pragma table_info(agent_runs)")}
    assert con.execute("select 1 from sqlite_master where type='table' and name='agent_jobs'").fetchone() == (1,)
    assert con.execute("select 1 from sqlite_master where type='table' and name='agent_run_commands'").fetchone() == (1,)
    assert {"state_version", "pause_reason", "resume_target_status", "lease_generation", "transaction_id"} <= {
        row[1] for row in con.execute("pragma table_info(agent_runs)")
    }
    for lease_table in ("agent_run_steps", "agent_jobs", "agent_run_commands"):
        assert "lease_generation" in {row[1] for row in con.execute(f"pragma table_info({lease_table})")}
    assert con.execute(
        "select 1 from sqlite_master where type='table' and name='agent_run_steps'"
    ).fetchone() == (1,)
    assert con.execute(
        "select 1 from sqlite_master where type='table' and name='admin_settings'"
    ).fetchone() == (1,)
    con.close()


def test_upgrade_adopts_legacy_create_all_schema_and_adds_accounting_columns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "legacy.sqlite"
    con = sqlite3.connect(db_path)
    con.executescript(
        """
        CREATE TABLE novel_projects (id VARCHAR(36) PRIMARY KEY);
        CREATE TABLE task_runtime_tasks (
            task_id VARCHAR(64) PRIMARY KEY, owner_user_id INTEGER, project_id VARCHAR(64), chapter_id VARCHAR(64),
            task_type VARCHAR(96) NOT NULL, idempotency_key VARCHAR(255), status VARCHAR(24) NOT NULL,
            stage VARCHAR(128), progress FLOAT NOT NULL, message TEXT, event_cursor BIGINT NOT NULL,
            retry_count INTEGER NOT NULL, max_retries INTEGER NOT NULL, lease_owner VARCHAR(128),
            heartbeat_at DATETIME, started_at DATETIME, finished_at DATETIME, error_code VARCHAR(96),
            error_detail TEXT, result_ref VARCHAR(255), payload JSON, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
        );
        CREATE TABLE task_runtime_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT, task_id VARCHAR(64) NOT NULL, event_type VARCHAR(48) NOT NULL,
            status VARCHAR(24), stage VARCHAR(128), progress FLOAT, message TEXT, idempotency_key VARCHAR(255),
            payload JSON, created_at DATETIME NOT NULL
        );
        CREATE TABLE project_ledger_sync_leases (
            project_id VARCHAR(36) PRIMARY KEY, chapter_number INTEGER NOT NULL, selected_version_id INTEGER,
            lease_token VARCHAR(36) NOT NULL UNIQUE, owner_id VARCHAR(128), acquired_at DATETIME NOT NULL,
            expires_at DATETIME NOT NULL, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO task_runtime_tasks VALUES ('task-1', NULL, NULL, NULL, 'chapter', 'retry-key', 'queued', NULL, 0, NULL, 0, 0, 3, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '{}', '2026-08-11', '2026-08-11');
        INSERT INTO task_runtime_tasks VALUES ('task-2', NULL, NULL, NULL, 'chapter', 'retry-key', 'queued', NULL, 0, NULL, 0, 0, 3, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '{}', '2026-08-11', '2026-08-11');
        INSERT INTO task_runtime_events VALUES (1, 'task-1', 'log', NULL, NULL, NULL, NULL, 'event-key', '[]', '2026-08-11');
        INSERT INTO task_runtime_events VALUES (2, 'task-1', 'log', NULL, NULL, NULL, NULL, 'event-key', '[]', '2026-08-11');
        INSERT INTO task_runtime_events VALUES (3, 'task-2', 'log', NULL, NULL, NULL, NULL, 'event-key', '[]', '2026-08-11');
        """
    )
    con.commit()
    con.close()

    _upgrade(monkeypatch, db_path)
    con = sqlite3.connect(db_path)
    columns = {row[1] for row in con.execute("pragma table_info(task_runtime_tasks)")}
    assert {"elapsed_ms", "input_tokens", "output_tokens", "total_tokens"} <= columns
    assert con.execute("select count(*) from task_runtime_tasks").fetchone()[0] == 2
    assert con.execute("select count(*) from task_runtime_events").fetchone()[0] == 3
    assert con.execute("select idempotency_key from task_runtime_tasks where task_id='task-1'").fetchone()[0] == "retry-key"
    assert con.execute("select idempotency_key from task_runtime_tasks where task_id='task-2'").fetchone()[0] is None
    assert con.execute("select idempotency_key from task_runtime_events where event_id=2").fetchone()[0] is None
    assert con.execute("select idempotency_key from task_runtime_events where event_id=3").fetchone()[0] == "event-key"

    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "insert into task_runtime_tasks (task_id, task_type, idempotency_key, status, progress, event_cursor, retry_count, max_retries, created_at, updated_at) values (?, ?, ?, ?, 0, 0, 0, 3, ?, ?)",
            ("task-3", "chapter", "retry-key", "queued", "2026-08-11", "2026-08-11"),
        )
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "insert into task_runtime_events (task_id, event_type, idempotency_key, created_at) values (?, ?, ?, ?)",
            ("task-1", "log", "event-key", "2026-08-11"),
        )
    con.execute(
        "insert into task_runtime_events (task_id, event_type, idempotency_key, created_at) values (?, ?, ?, ?)",
        ("task-2", "log", "event-key-2", "2026-08-11"),
    )
    con.close()



def test_partial_legacy_runtime_and_lease_schema_upgrades_and_downgrades_without_data_loss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "partial-legacy.sqlite"
    con = sqlite3.connect(db_path)
    con.executescript(
        """
        CREATE TABLE novel_projects (id VARCHAR(36) PRIMARY KEY);
        CREATE TABLE task_runtime_tasks (
            task_id VARCHAR(64) PRIMARY KEY, task_type VARCHAR(96) NOT NULL,
            idempotency_key VARCHAR(255), status VARCHAR(24) NOT NULL, progress FLOAT NOT NULL,
            event_cursor BIGINT NOT NULL, retry_count INTEGER NOT NULL, max_retries INTEGER NOT NULL,
            created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
        );
        CREATE TABLE task_runtime_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT, task_id VARCHAR(64) NOT NULL,
            event_type VARCHAR(48) NOT NULL, idempotency_key VARCHAR(255), created_at DATETIME NOT NULL
        );
        CREATE TABLE project_ledger_sync_leases (
            project_id VARCHAR(36) PRIMARY KEY, chapter_number INTEGER NOT NULL,
            lease_token VARCHAR(64), expires_at DATETIME
        );
        INSERT INTO task_runtime_tasks VALUES ('legacy-task', 'chapter', 'legacy-key', 'queued', 0, 0, 0, 3, '2026-08-11', '2026-08-11');
        INSERT INTO task_runtime_events VALUES (1, 'legacy-task', 'log', 'legacy-event', '2026-08-11');
        INSERT INTO project_ledger_sync_leases VALUES ('p1', 1, 'same-token', '2099-01-01');
        INSERT INTO project_ledger_sync_leases VALUES ('p2', 2, 'same-token', '2099-01-01');
        INSERT INTO project_ledger_sync_leases VALUES ('p3', 3, NULL, '2099-01-01');
        """
    )
    con.commit()
    con.close()

    _upgrade(monkeypatch, db_path)
    con = sqlite3.connect(db_path)
    task_columns = {row[1] for row in con.execute("pragma table_info(task_runtime_tasks)")}
    assert {
        "owner_user_id", "project_id", "chapter_id", "lease_owner", "heartbeat_at",
        "finished_at", "elapsed_ms", "input_tokens", "output_tokens", "total_tokens",
        "error_code", "error_detail", "result_ref", "payload",
    } <= task_columns
    event_columns = {row[1] for row in con.execute("pragma table_info(task_runtime_events)")}
    assert {"status", "stage", "progress", "message", "payload"} <= event_columns
    tokens = [row[0] for row in con.execute("select lease_token from project_ledger_sync_leases")]
    assert len(tokens) == 3 and len(set(tokens)) == 3 and all(tokens)
    assert con.execute("select count(*) from task_runtime_tasks").fetchone()[0] == 1
    assert con.execute("select count(*) from task_runtime_events").fetchone()[0] == 1
    con.close()

    command.downgrade(_config(), "base")
    con = sqlite3.connect(db_path)
    assert con.execute("select count(*) from task_runtime_tasks").fetchone()[0] == 1
    assert con.execute("select count(*) from task_runtime_events").fetchone()[0] == 1
    assert con.execute("select count(*) from project_ledger_sync_leases").fetchone()[0] == 3
    con.close()


def test_agent_correlation_migration_backfills_children_and_keeps_legacy_task_runtime_nullable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """014 must upgrade a real pre-014 shape, not merely current ORM create_all."""
    db_path = tmp_path / "agent-correlation.sqlite"
    con = sqlite3.connect(db_path)
    con.executescript(
        """
        CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL);
        INSERT INTO alembic_version VALUES ('013_agent_job_contract');
        CREATE TABLE agent_runs (id VARCHAR(36) PRIMARY KEY);
        CREATE TABLE agent_run_steps (id VARCHAR(36) PRIMARY KEY, run_id VARCHAR(36));
        CREATE TABLE agent_events (id VARCHAR(36) PRIMARY KEY, run_id VARCHAR(36));
        CREATE TABLE agent_approvals (id VARCHAR(36) PRIMARY KEY, run_id VARCHAR(36));
        CREATE TABLE agent_artifact_refs (id VARCHAR(36) PRIMARY KEY, run_id VARCHAR(36));
        CREATE TABLE agent_jobs (id VARCHAR(36) PRIMARY KEY, run_id VARCHAR(36));
        CREATE TABLE task_runtime_tasks (task_id VARCHAR(64) PRIMARY KEY);
        CREATE TABLE task_runtime_events (event_id INTEGER PRIMARY KEY, task_id VARCHAR(64));
        INSERT INTO agent_runs VALUES ('run-correlation');
        INSERT INTO agent_run_steps VALUES ('step-correlation', 'run-correlation');
        INSERT INTO agent_events VALUES ('event-correlation', 'run-correlation');
        INSERT INTO agent_approvals VALUES ('approval-correlation', 'run-correlation');
        INSERT INTO agent_artifact_refs VALUES ('artifact-correlation', 'run-correlation');
        INSERT INTO agent_jobs VALUES ('job-correlation', 'run-correlation');
        INSERT INTO task_runtime_tasks VALUES ('legacy-task');
        INSERT INTO task_runtime_events VALUES (1, 'legacy-task');
        """
    )
    con.commit()
    con.close()

    _upgrade(monkeypatch, db_path)
    con = sqlite3.connect(db_path)
    assert con.execute("select correlation_id from agent_runs where id='run-correlation'").fetchone()[0] == "run-correlation"
    assert con.execute("select event_sequence from agent_runs where id='run-correlation'").fetchone()[0] == 0
    assert con.execute("select latest_public_summary_json, latest_public_summary_sequence, latest_public_summary_at from agent_runs where id='run-correlation'").fetchone() == ("{}", 0, None)
    for table, row_id in (("agent_run_steps", "step-correlation"), ("agent_events", "event-correlation"), ("agent_approvals", "approval-correlation"), ("agent_artifact_refs", "artifact-correlation"), ("agent_jobs", "job-correlation")):
        assert con.execute(f"select correlation_id from {table} where id=?", (row_id,)).fetchone()[0] == "run-correlation"
        assert con.execute(f"select transaction_id from {table} where id=?", (row_id,)).fetchone()[0] is None
    assert con.execute("select correlation_id from task_runtime_tasks where task_id='legacy-task'").fetchone()[0] is None
    assert con.execute("select correlation_id from task_runtime_events where task_id='legacy-task'").fetchone()[0] is None
    assert con.execute("select version_num from alembic_version").fetchone()[0] == "028_agent_reasoning_chunks"
    for lease_table in ("agent_runs", "agent_run_steps", "agent_jobs", "agent_run_commands"):
        assert "lease_generation" in {row[1] for row in con.execute(f"pragma table_info({lease_table})")}
    con.close()


def test_task_runtime_migration_matches_persistent_model_columns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "model-contract.sqlite"
    _upgrade(monkeypatch, db_path)
    con = sqlite3.connect(db_path)
    task_columns = {row[1] for row in con.execute("pragma table_info(task_runtime_tasks)")}
    event_columns = {row[1] for row in con.execute("pragma table_info(task_runtime_events)")}
    assert task_columns == {
        "task_id", "owner_user_id", "project_id", "correlation_id", "chapter_id", "task_type", "idempotency_key",
        "input_hash", "config_snapshot_id", "artifact_ref", "artifact_revision",
        "status", "stage", "progress", "message", "event_cursor", "retry_count", "max_retries",
        "attempt", "lease_generation", "lease_owner", "heartbeat_at", "started_at", "finished_at", "elapsed_ms", "input_tokens",
        "output_tokens", "total_tokens", "error_code", "error_detail", "result_ref", "payload",
        "created_at", "updated_at",
    }
    assert event_columns == {
        "event_id", "task_id", "correlation_id", "event_type", "status", "stage", "progress", "message",
        "idempotency_key", "attempt", "lease_generation", "channel", "sequence", "payload", "created_at",
    }
    con.close()


def test_024_reconciles_legacy_snapshot_table_without_rebuilding_or_losing_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A database already marked 023 can safely receive the missing 020 metadata columns."""
    db_path = tmp_path / "snapshot-023-legacy.sqlite"
    con = sqlite3.connect(db_path)
    con.executescript(
        """
        CREATE TABLE alembic_version (version_num VARCHAR(64) NOT NULL);
        INSERT INTO alembic_version VALUES ('023_agent_quality_lineage');
        CREATE TABLE agent_run_capability_snapshots (
            id VARCHAR(36) PRIMARY KEY,
            snapshot_id VARCHAR(255) NOT NULL,
            run_id VARCHAR(36) NOT NULL,
            generation INTEGER NOT NULL,
            digest VARCHAR(64) NOT NULL
        );
        INSERT INTO agent_run_capability_snapshots (id, snapshot_id, run_id, generation, digest)
        VALUES ('snapshot-1', 'resolver-1', 'run-1', 1, 'digest-1');
        """
    )
    con.commit()
    con.close()

    _upgrade(monkeypatch, db_path)
    _upgrade(monkeypatch, db_path)

    con = sqlite3.connect(db_path)
    columns = {row[1] for row in con.execute("pragma table_info(agent_run_capability_snapshots)")}
    assert {"selection_reason", "resolved_version"} <= columns
    assert con.execute(
        "select id, snapshot_id, run_id, generation, digest, selection_reason, resolved_version "
        "from agent_run_capability_snapshots where id='snapshot-1'"
    ).fetchone() == ("snapshot-1", "resolver-1", "run-1", 1, "digest-1", None, None)
    assert con.execute("select version_num from alembic_version").fetchone()[0] == "028_agent_reasoning_chunks"
    con.close()
