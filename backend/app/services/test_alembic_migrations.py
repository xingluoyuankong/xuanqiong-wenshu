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
    assert con.execute("select version_num from alembic_version").fetchone()[0] == "004_task_runtime_attempt_fence"
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


@pytest.mark.anyio
async def test_concurrent_schema_upgrades_are_serialized(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Multiple workers starting together must not race the baseline DDL."""
    db_path = tmp_path / "concurrent.sqlite"
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{db_path.as_posix()}")

    await asyncio.gather(_run_schema_migrations(), _run_schema_migrations())

    con = sqlite3.connect(db_path)
    assert con.execute("select version_num from alembic_version").fetchone()[0] == "004_task_runtime_attempt_fence"
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


def test_task_runtime_migration_matches_persistent_model_columns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "model-contract.sqlite"
    _upgrade(monkeypatch, db_path)
    con = sqlite3.connect(db_path)
    task_columns = {row[1] for row in con.execute("pragma table_info(task_runtime_tasks)")}
    event_columns = {row[1] for row in con.execute("pragma table_info(task_runtime_events)")}
    assert task_columns == {
        "task_id", "owner_user_id", "project_id", "chapter_id", "task_type", "idempotency_key",
        "input_hash", "config_snapshot_id", "artifact_ref", "artifact_revision",
        "status", "stage", "progress", "message", "event_cursor", "retry_count", "max_retries",
        "attempt", "lease_generation", "lease_owner", "heartbeat_at", "started_at", "finished_at", "elapsed_ms", "input_tokens",
        "output_tokens", "total_tokens", "error_code", "error_detail", "result_ref", "payload",
        "created_at", "updated_at",
    }
    assert event_columns == {
        "event_id", "task_id", "event_type", "status", "stage", "progress", "message",
        "idempotency_key", "attempt", "lease_generation", "channel", "sequence", "payload", "created_at",
    }
    con.close()
