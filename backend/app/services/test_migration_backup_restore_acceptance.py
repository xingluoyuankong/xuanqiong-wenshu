"""Independent regressions for the real, isolated backup/restore acceptance."""
from __future__ import annotations

from contextlib import contextmanager, closing
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

BACKEND = Path(__file__).resolve().parents[2]
SCRIPT = BACKEND / "scripts" / "migration_backup_restore_acceptance.py"


@pytest.fixture
def acceptance():
    spec = importlib.util.spec_from_file_location("backup_acceptance_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def seeded_template(tmp_path_factory):
    spec = importlib.util.spec_from_file_location("backup_acceptance_fixture", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = tmp_path_factory.mktemp("backup-seeded") / "source.sqlite"
    module._upgrade(path)
    module._seed(path)
    module._verify_seed(module._snapshot(path))
    return path


@pytest.fixture
def seeded_db(tmp_path, seeded_template, acceptance):
    path = tmp_path / "isolated.sqlite"
    acceptance._backup(seeded_template, path)
    return path


def test_script_subprocess_verifies_real_roundtrips_and_leaves_environment_db_untouched(tmp_path):
    untouched = tmp_path / "environment.sqlite"
    with closing(sqlite3.connect(untouched)) as db, db:
        db.execute("CREATE TABLE untouched (value TEXT)")
        db.execute("INSERT INTO untouched VALUES ('do not migrate this database')")
    before = untouched.read_bytes()
    env = os.environ.copy()
    env.update(DATABASE_URL=f"sqlite+aiosqlite:///{untouched.as_posix()}", DB_PROVIDER="sqlite", TEMP=str(tmp_path), TMP=str(tmp_path))
    process = subprocess.run(
        [sys.executable, str(SCRIPT)], cwd=tmp_path, env=env,
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90,
    )
    assert process.returncode == 0, process.stdout + process.stderr
    result = json.loads(process.stdout)
    assert result["status"] == "MIGRATION_BACKUP_RESTORE_MATRIX_PASSED"
    assert result["backup_method"] == "sqlite3.Connection.backup"
    assert result["physical_hashes_are_diagnostic"] is True
    assert result["fresh_revision"] == result["restored_revision"] == "030_research_schema_repair"
    expected = {name: 1 for name in (
        "users", "novel_projects", "agent_sessions", "agent_messages", "project_members",
        "project_research_configs", "research_artifacts",
    )}
    assert result["source_counts"] == result["restored_counts_after_reupgrade"] == expected
    assert set(result["sentinels_verified"]) == set(expected)
    assert result["restored_copy_logical_hash_matches"] is True
    assert result["source_logical_sha256"] == result["restored_copy_logical_sha256"]
    assert result["roundtrip_targets"] == ["029_project_members", "028_agent_reasoning_chunks"]
    assert len(result["foreign_key_checks"]) == 7
    assert all(violations == [] for violations in result["foreign_key_checks"].values())
    assert "Running downgrade 030_research_schema_repair -> 029_project_members" in process.stderr
    assert "Running downgrade 029_project_members -> 028_agent_reasoning_chunks" in process.stderr
    assert untouched.read_bytes() == before
    assert not list(tmp_path.glob("xq-migration-restore-*")), "temporary databases/connections leaked"


def test_backup_captures_committed_wal_and_repeats(tmp_path, acceptance):
    source = tmp_path / "wal-source.sqlite"
    destination = tmp_path / "wal-backup.sqlite"
    # Keep this connection alive so SQLite cannot checkpoint WAL on last close.
    with closing(sqlite3.connect(source)) as writer:
        assert writer.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("CREATE TABLE wal_sentinel (id INTEGER PRIMARY KEY, value TEXT)")
        writer.execute("INSERT INTO wal_sentinel VALUES (1, 'committed WAL sentinel')")
        writer.commit()
        assert Path(str(source) + "-wal").stat().st_size > 0
        acceptance._backup(source, destination)
        with closing(sqlite3.connect(destination)) as restored:
            assert restored.execute("SELECT * FROM wal_sentinel").fetchall() == [(1, "committed WAL sentinel")]
        writer.execute("INSERT INTO wal_sentinel VALUES (2, 'second committed sentinel')")
        writer.commit()
        acceptance._backup(source, destination)
        with closing(sqlite3.connect(destination)) as restored:
            assert restored.execute("SELECT count(*) FROM wal_sentinel").fetchone()[0] == 2


@pytest.mark.parametrize("fail_inside", [False, True])
def test_connection_enforces_fk_and_closes_even_on_error(tmp_path, acceptance, fail_inside):
    connection = None
    try:
        with acceptance._connect(tmp_path / "close.sqlite") as connection:
            assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
            if fail_inside:
                raise ValueError("intentional context failure")
    except ValueError:
        assert fail_inside
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connection.execute("SELECT 1")


def test_backup_closes_both_connections(tmp_path, acceptance, monkeypatch):
    source, destination = tmp_path / "source.sqlite", tmp_path / "backup.sqlite"
    with closing(sqlite3.connect(source)) as db, db:
        db.execute("CREATE TABLE data (id INTEGER)")
    connections = []
    original = acceptance._connect

    @contextmanager
    def tracked(path):
        with original(path) as db:
            connections.append(db)
            yield db

    monkeypatch.setattr(acceptance, "_connect", tracked)
    acceptance._backup(source, destination)
    assert len(connections) == 2
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")


@pytest.mark.parametrize("table,column", [
    ("agent_sessions", "user_id"), ("research_artifacts", "user_id"),
    ("project_research_configs", "project_id"),
])
def test_snapshot_rejects_orphan_foreign_keys(seeded_db, acceptance, table, column):
    with closing(sqlite3.connect(seeded_db)) as db, db:
        db.execute("PRAGMA foreign_keys=OFF")
        db.execute(f'UPDATE "{table}" SET "{column}" = ?', (999999,))
    with pytest.raises(RuntimeError, match="foreign-key violations"):
        acceptance._snapshot(seeded_db)


@pytest.mark.parametrize("table", ["agent_messages", "project_research_configs", "research_artifacts"])
def test_snapshot_verification_rejects_lost_sentinels(seeded_db, acceptance, table):
    expected = acceptance._snapshot(seeded_db)
    with acceptance._connect(seeded_db) as db, db:
        db.execute(f'DELETE FROM "{table}"')
    with pytest.raises(RuntimeError, match="sentinel counts mismatch"):
        acceptance._verify_snapshot(expected, acceptance._snapshot(seeded_db), "final reupgrade")


@pytest.mark.parametrize("table,column", [
    ("agent_sessions", "title"), ("agent_messages", "content"),
    ("project_research_configs", "search_api_key_encrypted"), ("research_artifacts", "summary"),
])
def test_snapshot_verification_rejects_same_count_data_corruption(seeded_db, acceptance, table, column):
    expected = acceptance._snapshot(seeded_db)
    with acceptance._connect(seeded_db) as db, db:
        db.execute(f'UPDATE "{table}" SET "{column}" = ?', ("corrupted sentinel",))
    actual = acceptance._snapshot(seeded_db)
    assert expected["counts"] == actual["counts"]
    with pytest.raises(RuntimeError, match=f"sentinel data mismatch: {table}"):
        acceptance._verify_snapshot(expected, actual, "final reupgrade")


@pytest.mark.parametrize("damage", ["delete_message", "delete_artifact", "tamper_config"])
def test_main_rejects_final_roundtrip_damage(acceptance, monkeypatch, capsys, damage):
    original = acceptance._upgrade
    calls = 0

    def damaged_upgrade(path, target="head"):
        nonlocal calls
        original(path, target)
        calls += 1
        if calls == 4:  # Fresh, restored repeat, re-upgrade from 029, then from 028.
            with acceptance._connect(path) as db, db:
                if damage == "delete_message":
                    db.execute("DELETE FROM agent_messages")
                elif damage == "delete_artifact":
                    db.execute("DELETE FROM research_artifacts")
                else:
                    db.execute("UPDATE project_research_configs SET search_api_key_encrypted='corrupt'")

    monkeypatch.setattr(acceptance, "_upgrade", damaged_upgrade)
    original_url = acceptance.settings.database_url
    with pytest.raises(RuntimeError, match="reupgrade from 028.*sentinel (counts|data) mismatch"):
        acceptance.main()
    assert acceptance.settings.database_url == original_url
    assert "MIGRATION_BACKUP_RESTORE_MATRIX_PASSED" not in capsys.readouterr().out


@pytest.mark.parametrize("action", ["upgrade", "downgrade"])
def test_migration_restores_database_setting_on_failure(tmp_path, acceptance, monkeypatch, action):
    original_url = acceptance.settings.database_url

    def failed_migration(config, target):
        assert acceptance.settings.database_url.endswith("isolated.sqlite")
        raise RuntimeError("intentional migration failure")

    monkeypatch.setattr(acceptance.command, action, failed_migration)
    with pytest.raises(RuntimeError, match="intentional migration failure"):
        acceptance._migrate(tmp_path / "isolated.sqlite", action, acceptance.HEAD)
    assert acceptance.settings.database_url == original_url


def test_main_rejects_upgrade_disguised_as_downgrade(acceptance, monkeypatch, capsys):
    monkeypatch.setattr(acceptance, "_downgrade", acceptance._upgrade)
    with pytest.raises(RuntimeError, match="revision mismatch: expected 029_project_members"):
        acceptance.main()
    assert "MIGRATION_BACKUP_RESTORE_MATRIX_PASSED" not in capsys.readouterr().out


def test_backup_logical_hash_covers_tables_beyond_named_sentinels(acceptance, monkeypatch, capsys):
    original_seed = acceptance._seed
    original_backup = acceptance._backup

    def seed_with_extra_table(path):
        original_seed(path)
        with acceptance._connect(path) as db, db:
            db.execute("CREATE TABLE extra_backup_guard (value TEXT)")
            db.execute("INSERT INTO extra_backup_guard VALUES ('intact')")

    def corrupted_backup(source, destination):
        original_backup(source, destination)
        with acceptance._connect(destination) as db, db:
            db.execute("UPDATE extra_backup_guard SET value='corrupted'")

    monkeypatch.setattr(acceptance, "_seed", seed_with_extra_table)
    monkeypatch.setattr(acceptance, "_backup", corrupted_backup)
    with pytest.raises(RuntimeError, match="backup logical hash mismatch"):
        acceptance.main()
    assert "MIGRATION_BACKUP_RESTORE_MATRIX_PASSED" not in capsys.readouterr().out
