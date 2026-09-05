"""Reproducible isolated SQLite migration and backup/restore acceptance."""
from __future__ import annotations

import gc
import hashlib
import json
import shutil
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


def _cfg() -> Config:
    return Config(str(BACKEND_ROOT / "alembic.ini"))


def _upgrade(db_path: Path, target: str = "head") -> None:
    settings.database_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    command.upgrade(_cfg(), target)


def _revision(db_path: Path) -> str:
    with sqlite3.connect(db_path) as db:
        return str(db.execute("select version_num from alembic_version").fetchone()[0])


def _hash_and_counts(db_path: Path) -> tuple[str, dict[str, int]]:
    with sqlite3.connect(db_path) as db:
        db.execute("PRAGMA wal_checkpoint(FULL)")
        counts = {
            table: int(db.execute(f"select count(*) from {table}").fetchone()[0])
            for table in ("agent_sessions", "agent_messages", "project_members")
        }
    return hashlib.sha256(db_path.read_bytes()).hexdigest(), counts


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="xq-migration-restore-", ignore_cleanup_errors=True) as raw_dir:
        root = Path(raw_dir)
        source = root / "source.sqlite"
        restored = root / "restored.sqlite"
        _upgrade(source)
        with sqlite3.connect(source) as db:
            db.execute(
                "insert into agent_sessions (id, user_id, title, status, created_at, updated_at) values (?, ?, ?, ?, ?, ?)",
                ("migration-restore-sentinel", 1, "migration restore sentinel", "active", "2026-09-05", "2026-09-05"),
            )
            db.commit()
        source_hash, source_counts = _hash_and_counts(source)
        shutil.copy2(source, restored)
        restored_hash, restored_counts = _hash_and_counts(restored)
        if source_hash != restored_hash or source_counts != restored_counts:
            raise RuntimeError("backup copy hash/count mismatch")
        _upgrade(restored)
        if _revision(restored) != "029_project_members":
            raise RuntimeError(f"restored revision mismatch: {_revision(restored)}")
        with sqlite3.connect(restored) as db:
            sentinel_count = int(db.execute("select count(*) from agent_sessions where id = ?", ("migration-restore-sentinel",)).fetchone()[0])
            if sentinel_count != 1:
                raise RuntimeError("restore sentinel missing")
        _upgrade(restored, "028_agent_reasoning_chunks")
        _upgrade(restored, "head")
        final_hash, final_counts = _hash_and_counts(restored)
        result = {
            "status": "MIGRATION_BACKUP_RESTORE_MATRIX_PASSED",
            "fresh_revision": _revision(source),
            "restored_revision": _revision(restored),
            "source_sha256": source_hash,
            "restored_copy_sha256": restored_hash,
            "restored_copy_hash_matches": source_hash == restored_hash,
            "source_counts": source_counts,
            "restored_counts_after_reupgrade": final_counts,
            "final_sha256": final_hash,
            "sentinel_count": sentinel_count,
        }
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        gc.collect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
