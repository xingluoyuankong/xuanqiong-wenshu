#!/usr/bin/env python3
"""Read-only comparison of SQLite schema against SQLAlchemy ORM metadata."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from backend.app.db.base import Base
import backend.app.models  # noqa: F401 - register all ORM tables


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("db_path", nargs="?", default="storage/xuanqiong_wenshu.db")
    parser.add_argument("--strict-extra", action="store_true", help="fail when the database has tables not in ORM metadata")
    return parser.parse_args()


def read_only_connection(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.resolve()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def main() -> int:
    args = parse_args()
    db_path = Path(args.db_path)
    if not db_path.is_file():
        print(json.dumps({"status": "error", "error": f"database not found: {db_path}"}, ensure_ascii=False))
        return 2

    expected_tables = set(Base.metadata.tables)
    conn = read_only_connection(db_path)
    try:
        actual_tables = {row[0] for row in conn.execute(
            "select name from sqlite_master where type='table' and name not like 'sqlite_%'"
        )}
        missing_tables = sorted(expected_tables - actual_tables)
        extra_tables = sorted(actual_tables - expected_tables)
        missing_columns: dict[str, list[str]] = {}
        extra_columns: dict[str, list[str]] = {}
        for table in sorted(expected_tables & actual_tables):
            quoted = table.replace('"', '""')
            actual_columns = {row[1] for row in conn.execute(f'pragma table_info("{quoted}")')}
            expected_columns = set(Base.metadata.tables[table].columns.keys())
            if expected_columns - actual_columns:
                missing_columns[table] = sorted(expected_columns - actual_columns)
            if actual_columns - expected_columns:
                extra_columns[table] = sorted(actual_columns - expected_columns)
        foreign_key_violations = [dict(zip(("table", "rowid", "parent", "fkid"), row)) for row in conn.execute("pragma foreign_key_check")]
        report = {
            "status": "pass" if not missing_tables and not missing_columns and not foreign_key_violations and (not args.strict_extra or not extra_tables) else "fail",
            "db_path": str(db_path),
            "expected_table_count": len(expected_tables),
            "actual_table_count": len(actual_tables),
            "missing_tables": missing_tables,
            "extra_tables": extra_tables,
            "missing_columns": missing_columns,
            "extra_columns": extra_columns,
            "foreign_key_violations": foreign_key_violations,
            "extra_tables_are_advisory": not args.strict_extra,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["status"] == "pass" else 10
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
