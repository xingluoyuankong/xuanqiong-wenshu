"""Isolated SQLite backup/restore acceptance with real migration round trips."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

from alembic import command
from alembic.config import Config

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings  # noqa: E402

HEAD = "030_research_schema_repair"
PREVIOUS = "029_project_members"
OLDER = "028_agent_reasoning_chunks"
USER_ID = 8801
PROJECT_ID = "restore-project-sentinel"
SESSION_ID = "migration-restore-sentinel"
STAMP = "2026-09-06T00:00:00+00:00"
# Insertion order is parent-first, with real FK enforcement throughout seeding.
SENTINELS = {
    "users": {"id": USER_ID, "username": "restore-user-sentinel", "hashed_password": "hash-sentinel", "is_admin": 0, "is_active": 1},
    "novel_projects": {"id": PROJECT_ID, "user_id": USER_ID, "title": "restore project sentinel", "status": "draft"},
    "agent_sessions": {"id": SESSION_ID, "user_id": USER_ID, "project_id": PROJECT_ID, "title": "restore session sentinel", "status": "active", "created_at": STAMP, "updated_at": STAMP},
    "agent_messages": {"id": "restore-message-sentinel", "session_id": SESSION_ID, "user_id": USER_ID, "role": "user", "content": "message sentinel: 研究备份", "sequence": 1},
    "project_members": {"id": "restore-member-sentinel", "project_id": PROJECT_ID, "user_id": USER_ID, "role": "owner", "deleted_at": None},
    "project_research_configs": {
        "project_id": PROJECT_ID, "mode": "manual", "enabled": 1, "search_provider": "tavily",
        "reuse_writing_llm": 1, "local_model_enabled": 0, "global_research_enabled": 1,
        "enhanced_research_enabled": 1, "chapter_research_enabled": 1,
        "max_parallel_queries": 4, "max_results_per_query": 5,
        "search_api_key_encrypted": "encrypted-key-sentinel",
        "preferred_domains": '["example.org"]', "extra": '{"sentinel":"research-config"}',
    },
    "research_artifacts": {
        "id": 8802, "run_id": "restore-research-run-sentinel", "project_id": PROJECT_ID,
        "user_id": USER_ID, "scope": "global", "chapter_number": 1, "status": "completed",
        "trigger": "manual", "summary": "研究成果 sentinel", "sources": '[{"title":"source-sentinel"}]',
        "category_payload": '{"sentinel":[1,2]}', "file_manifest": '{"path":"sentinel.json"}',
    },
}
MEMBERSHIP_REGENERATED_COLUMNS = {"id", "created_at", "updated_at"}


def _cfg() -> Config:
    return Config(str(BACKEND_ROOT / "alembic.ini"))


def _migrate(db_path: Path, action: str, target: str) -> None:
    original_url = settings.database_url
    try:
        settings.database_url = f"sqlite+aiosqlite:///{db_path.resolve().as_posix()}"
        getattr(command, action)(_cfg(), target)
    finally:
        settings.database_url = original_url


def _upgrade(db_path: Path, target: str = "head") -> None:
    _migrate(db_path, "upgrade", target)


def _downgrade(db_path: Path, target: str) -> None:
    _migrate(db_path, "downgrade", target)


@contextmanager
def _connect(db_path: Path):
    db = sqlite3.connect(db_path)
    try:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        if db.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            raise RuntimeError("foreign-key enforcement is disabled")
        yield db
    finally:
        db.close()


def _revision(db_path: Path) -> str:
    with _connect(db_path) as db:
        return str(db.execute("SELECT version_num FROM alembic_version").fetchone()[0])


def _expect_revision(db_path: Path, expected: str) -> None:
    actual = _revision(db_path)
    if actual != expected:
        raise RuntimeError(f"revision mismatch: expected {expected}, got {actual}")


def _seed(db_path: Path) -> None:
    with _connect(db_path) as db, db:
        for table, values in SENTINELS.items():
            columns = ", ".join(f'"{name}"' for name in values)
            placeholders = ", ".join("?" for _ in values)
            db.execute(f'INSERT INTO "{table}" ({columns}) VALUES ({placeholders})', tuple(values.values()))


def _backup(source: Path, destination: Path) -> None:
    # The SQLite backup API includes committed WAL pages; a file copy does not.
    with _connect(source) as src, _connect(destination) as dst:
        src.backup(dst)


def _snapshot(db_path: Path, *, members: bool = True) -> dict:
    with _connect(db_path) as db:
        db.execute("BEGIN")  # One consistent read snapshot for all checks/data.
        violations = [tuple(row) for row in db.execute("PRAGMA foreign_key_check")]
        if violations:
            raise RuntimeError(f"foreign-key violations: {violations}")
        integrity = [row[0] for row in db.execute("PRAGMA integrity_check")]
        if integrity != ["ok"]:
            raise RuntimeError(f"SQLite integrity failure: {integrity}")
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        expected = set(SENTINELS) - (set() if members else {"project_members"})
        if not expected <= tables or (not members and "project_members" in tables):
            raise RuntimeError("sentinel schema mismatch")
        rows = {table: [dict(row) for row in db.execute(f'SELECT * FROM "{table}" ORDER BY 1')] for table in sorted(expected)}
        counts = {table: len(values) for table, values in rows.items()}
        # A backup can alter SQLite header bytes. Compare complete logical dumps
        # for backup equivalence; physical file hashes remain diagnostic only.
        logical_hash = hashlib.sha256("\n".join(db.iterdump()).encode("utf-8")).hexdigest()
    return {"rows": rows, "counts": counts, "logical_sha256": logical_hash, "foreign_key_check": violations}


def _verify_seed(snapshot: dict, *, rebuilt_members: bool = False) -> None:
    if snapshot["counts"] != {table: 1 for table in SENTINELS}:
        raise RuntimeError("seed sentinel counts mismatch")
    for table, values in SENTINELS.items():
        row = snapshot["rows"][table][0]
        for column, value in values.items():
            if rebuilt_members and table == "project_members" and column in MEMBERSHIP_REGENERATED_COLUMNS:
                continue
            if row[column] != value:
                raise RuntimeError(f"seed sentinel mismatch: {table}.{column}")


def _verify_snapshot(expected: dict, actual: dict, stage: str, *, rebuilt_members: bool = False) -> None:
    if actual["counts"] != expected["counts"]:
        raise RuntimeError(f"{stage}: sentinel counts mismatch")
    for table, rows in expected["rows"].items():
        actual_rows = actual["rows"][table]
        if rebuilt_members and table == "project_members":
            # Revision 029 drops this table on downgrade to 028, then rebuilds
            # legacy owner grants. IDs/timestamps change; grant semantics must not.
            if any(not row.get(column) for row in actual_rows for column in MEMBERSHIP_REGENERATED_COLUMNS):
                raise RuntimeError(f"{stage}: invalid rebuilt owner membership")
            rows = [{key: value for key, value in row.items() if key not in MEMBERSHIP_REGENERATED_COLUMNS} for row in rows]
            actual_rows = [{key: value for key, value in row.items() if key not in MEMBERSHIP_REGENERATED_COLUMNS} for row in actual_rows]
        if actual_rows != rows:
            raise RuntimeError(f"{stage}: sentinel data mismatch: {table}")


def main() -> int:
    stages = {}
    with tempfile.TemporaryDirectory(prefix="xq-migration-restore-") as raw_dir:
        source = Path(raw_dir) / "source.sqlite"
        restored = Path(raw_dir) / "restored.sqlite"
        _upgrade(source)
        _expect_revision(source, HEAD)
        _seed(source)
        baseline = _snapshot(source)
        _verify_seed(baseline)
        stages["source"] = baseline["foreign_key_check"]
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        _backup(source, restored)
        copied = _snapshot(restored)
        _expect_revision(restored, HEAD)
        _verify_snapshot(baseline, copied, "backup")
        if baseline["logical_sha256"] != copied["logical_sha256"]:
            raise RuntimeError("backup logical hash mismatch")
        restored_hash = hashlib.sha256(restored.read_bytes()).hexdigest()
        stages["backup"] = copied["foreign_key_check"]
        _upgrade(restored)
        snapshot = _snapshot(restored)
        _verify_snapshot(baseline, snapshot, "restored upgrade")
        _expect_revision(restored, HEAD)
        stages["restored_upgrade"] = snapshot["foreign_key_check"]
        for target in (PREVIOUS, OLDER):
            _downgrade(restored, target)
            _expect_revision(restored, target)
            snapshot = _snapshot(restored, members=target != OLDER)
            expected = {"counts": dict(baseline["counts"]), "rows": dict(baseline["rows"])}
            if target == OLDER:
                expected["counts"].pop("project_members")
                expected["rows"].pop("project_members")
            _verify_snapshot(expected, snapshot, f"downgrade {target}")
            stages[f"downgrade_{target}"] = snapshot["foreign_key_check"]
            _upgrade(restored)
            _expect_revision(restored, HEAD)
            snapshot = _snapshot(restored)
            _verify_snapshot(baseline, snapshot, f"reupgrade from {target}", rebuilt_members=target == OLDER)
            _verify_seed(snapshot, rebuilt_members=target == OLDER)
            stages[f"reupgrade_from_{target}"] = snapshot["foreign_key_check"]
        _verify_snapshot(baseline, _snapshot(source), "source unchanged")
        result = {
            "status": "MIGRATION_BACKUP_RESTORE_MATRIX_PASSED",
            "backup_method": "sqlite3.Connection.backup",
            "physical_hashes_are_diagnostic": True,
            "fresh_revision": _revision(source), "restored_revision": _revision(restored),
            "source_sha256": source_hash, "restored_copy_sha256": restored_hash,
            "restored_copy_hash_matches": source_hash == restored_hash,
            "source_logical_sha256": baseline["logical_sha256"],
            "restored_copy_logical_sha256": copied["logical_sha256"],
            "restored_copy_logical_hash_matches": True,
            "source_counts": baseline["counts"], "restored_counts_after_reupgrade": snapshot["counts"],
            "final_sha256": hashlib.sha256(restored.read_bytes()).hexdigest(),
            "sentinel_count": snapshot["counts"]["agent_sessions"],
            "sentinels_verified": list(SENTINELS), "foreign_key_checks": stages,
            "roundtrip_targets": [PREVIOUS, OLDER],
            "membership_028_roundtrip": "owner grant verified; generated ID/timestamps may change",
        }
    # Print success only after all connections are closed and temp cleanup passes.
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
