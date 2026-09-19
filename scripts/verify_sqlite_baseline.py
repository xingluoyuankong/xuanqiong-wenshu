#!/usr/bin/env python3
"""Read-only exact comparison against a committed SQLite schema baseline."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path


def digest(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def current_snapshot(path: Path) -> dict:
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    try:
        tables = {}
        names = [row[0] for row in conn.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name")]
        for name in names:
            columns = conn.execute(f'pragma table_info("{name.replace(chr(34), chr(34) * 2)}")').fetchall()
            tables[name] = {"columns": [{"name": row[1], "type": str(row[2]), "nullable": not bool(row[3]), "primary_key": bool(row[5])} for row in sorted(columns, key=lambda row: row[1])] }
        return {"tables": tables}
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("db_path", nargs="?", default="storage/xuanqiong_wenshu.db")
    parser.add_argument("baseline", nargs="?", default="docs/schema_baselines/20260918-production-sqlite.json")
    args = parser.parse_args()
    baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    expected = {"tables": baseline["actual_tables"]}
    current = current_snapshot(Path(args.db_path))
    expected_hash = digest(expected)
    current_hash = digest(current)
    stored_hash = baseline.get("database_schema_sha256")
    result = {
        "status": "match" if stored_hash == expected_hash == current_hash else "drift",
        "database": args.db_path,
        "baseline": args.baseline,
        "stored_baseline_schema_sha256": stored_hash,
        "baseline_schema_sha256": expected_hash,
        "current_schema_sha256": current_hash,
        "baseline_commit": baseline.get("git_commit"),
        "baseline_table_count": len(expected["tables"]),
        "current_table_count": len(current["tables"]),
        "missing_tables": sorted(set(expected["tables"]) - set(current["tables"])),
        "extra_tables": sorted(set(current["tables"]) - set(expected["tables"])),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "match" else 10


if __name__ == "__main__":
    raise SystemExit(main())
