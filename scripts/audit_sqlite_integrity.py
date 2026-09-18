#!/usr/bin/env python3
"""Read-only SQLite integrity and project-orphan audit."""
from __future__ import annotations
import sqlite3
import sys
from pathlib import Path

def main() -> int:
    db_path = Path(sys.argv[1] if len(sys.argv) > 1 else "storage/xuanqiong_wenshu.db")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        fk = int(conn.execute("PRAGMA foreign_keys").fetchone()[0])
        tables = [row[0] for row in conn.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name")]
        orphan_counts: dict[str, int] = {}
        table_counts: dict[str, int] = {}
        for table in tables:
            quoted = table.replace('"', '""')
            columns = [row[1] for row in conn.execute(f'pragma table_info("{quoted}")')]
            table_counts[table] = int(conn.execute(f'select count(*) from "{quoted}"').fetchone()[0])
            if "project_id" in columns and table != "novel_projects":
                count = int(conn.execute(f'select count(*) from "{quoted}" child left join novel_projects parent on parent.id = child.project_id where parent.id is null').fetchone()[0])
                if count:
                    orphan_counts[table] = count
        print(f"db={db_path}")
        print(f"foreign_keys={fk}")
        print(f"novel_projects={table_counts.get('novel_projects', 0)}")
        print(f"orphan_project_rows={orphan_counts}")
        print(f"chapters={table_counts.get('chapters', 0)}")
        print(f"token_budgets={table_counts.get('token_budgets', 0)}")
        return 0 if fk == 1 and not orphan_counts else 10
    finally:
        conn.close()

if __name__ == "__main__":
    raise SystemExit(main())
