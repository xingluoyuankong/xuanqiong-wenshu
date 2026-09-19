#!/usr/bin/env python3
"""Execute only SQLite-compatible migrations on a temporary copy and verify rollback."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

MYSQL_ONLY = {
    "AUTO_INCREMENT": re.compile(r"\bAUTO_INCREMENT\b", re.I),
    "ENGINE=": re.compile(r"\bENGINE\s*=", re.I),
    "COLLATE": re.compile(r"\bCOLLATE\b", re.I),
    "MODIFY COLUMN": re.compile(r"\bMODIFY\s+COLUMN\b", re.I),
    "ADD COLUMN IF NOT EXISTS": re.compile(r"\bADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\b", re.I),
}
DANGEROUS = {
    "DROP TABLE": re.compile(r"\bDROP\s+TABLE\b", re.I),
    "DROP DATABASE": re.compile(r"\bDROP\s+DATABASE\b", re.I),
    "TRUNCATE": re.compile(r"\bTRUNCATE\b", re.I),
}
ADD_COLUMN = re.compile(r"ALTER\s+TABLE\s+[`\"]?(\w+)[`\"]?\s+ADD\s+COLUMN\s+[`\"]?(\w+)", re.I)


def schema_fingerprint(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_master "
        "WHERE type IN ('table','index','trigger','view') AND name NOT LIKE 'sqlite_%' "
        "ORDER BY type, name"
    ).fetchall()
    payload = "\n".join("\t".join("" if value is None else str(value) for value in row) for row in rows)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def copy_database(source: Path, destination: Path) -> None:
    source_conn = sqlite3.connect(f"file:{source.resolve()}?mode=ro", uri=True)
    try:
        dest_conn = sqlite3.connect(destination)
        try:
            source_conn.backup(dest_conn)
            dest_conn.commit()
        finally:
            dest_conn.close()
    finally:
        source_conn.close()


def column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(row[1] == column for row in conn.execute(f"PRAGMA table_info({table})").fetchall())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="storage/xuanqiong_wenshu.db")
    parser.add_argument("--output", default="-")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    source = (root / args.database).resolve()
    manifest_path = root / "backend/db/migration_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_before = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    try:
        before_hash = schema_fingerprint(source_before)
    finally:
        source_before.close()

    with tempfile.TemporaryDirectory(prefix="xq-sqlite-migration-") as temp_dir:
        temp_root = Path(temp_dir)
        before_copy = temp_root / "before.db"
        working_copy = temp_root / "working.db"
        restored_copy = temp_root / "restored.db"
        copy_database(source, before_copy)
        copy_database(source, working_copy)
        conn = sqlite3.connect(working_copy)
        applied: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        provenance_failures: list[str] = []
        try:
            for item in manifest["migrations"]:
                path = root / item["path"]
                exists = path.is_file()
                actual_hash = hashlib.sha256(path.read_bytes()).hexdigest() if exists else None
                if not exists or actual_hash != item["sha256"] or path.stat().st_size != item["size"]:
                    provenance_failures.append(item["path"])
                    continue
                sql = path.read_text(encoding="utf-8", errors="replace")
                mysql_tokens = sorted(name for name, pattern in MYSQL_ONLY.items() if pattern.search(sql))
                dangerous_tokens = sorted(name for name, pattern in DANGEROUS.items() if pattern.search(sql))
                if mysql_tokens or dangerous_tokens:
                    skipped.append({
                        "path": item["path"],
                        "reason": "dialect_or_dangerous_sql_requires_manual_runner",
                        "mysql_only_tokens": mysql_tokens,
                        "dangerous_tokens": dangerous_tokens,
                    })
                    continue
                match = ADD_COLUMN.search(sql)
                if match and column_exists(conn, match.group(1), match.group(2)):
                    skipped.append({"path": item["path"], "reason": "already_applied_on_copy"})
                    continue
                conn.executescript(sql)
                conn.commit()
                applied.append({"path": item["path"], "schema_sha256": schema_fingerprint(conn)})
        finally:
            conn.close()
        copy_database(before_copy, restored_copy)
        restored_conn = sqlite3.connect(restored_copy)
        try:
            rollback_hash = schema_fingerprint(restored_conn)
        finally:
            restored_conn.close()
        working_conn = sqlite3.connect(working_copy)
        try:
            after_hash = schema_fingerprint(working_conn)
        finally:
            working_conn.close()

    source_after = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    try:
        source_after_hash = schema_fingerprint(source_after)
    finally:
        source_after.close()
    result = {
        "plan_type": "sqlite_copy_dry_run",
        "source_database": str(source),
        "source_schema_sha256_before": before_hash,
        "source_schema_sha256_after": source_after_hash,
        "source_unchanged": before_hash == source_after_hash,
        "working_copy_schema_sha256": after_hash,
        "rollback_schema_sha256": rollback_hash,
        "rollback_verified": rollback_hash == before_hash,
        "applied": applied,
        "skipped": skipped,
        "provenance_failures": provenance_failures,
        "status": "PASS" if before_hash == source_after_hash and rollback_hash == before_hash and not provenance_failures else "FAIL",
    }
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output == "-":
        print(rendered, end="")
    else:
        Path(args.output).write_text(rendered, encoding="utf-8")
    return 0 if result["status"] == "PASS" else 10


if __name__ == "__main__":
    raise SystemExit(main())