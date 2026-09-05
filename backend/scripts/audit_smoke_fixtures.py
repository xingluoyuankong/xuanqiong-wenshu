"""Read-only inventory of OpenAPI smoke fixture projects."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path
from typing import Any


def _db_path(value: str | None) -> Path:
    configured = value or os.getenv("SQLITE_DB_PATH", "storage/xuanqiong_wenshu.db")
    path = Path(configured)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[1] / path
    return path.resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=None, help="SQLite database path; defaults to SQLITE_DB_PATH or backend/storage/xuanqiong_wenshu.db")
    args = parser.parse_args()
    db_path = _db_path(args.db)
    if not db_path.exists():
        print(json.dumps({"status": "SMOKE_FIXTURE_AUDIT_FAILED", "error": f"database not found: {db_path}"}, ensure_ascii=False))
        return 1
    with sqlite3.connect(db_path) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute("SELECT id, title, user_id, status, created_at, updated_at FROM novel_projects WHERE title LIKE 'OpenAPI Smoke %' ORDER BY created_at ASC, id ASC").fetchall()
        fixtures: list[dict[str, Any]] = []
        for row in rows:
            project_id = str(row["id"])
            related: dict[str, int] = {}
            for table, column in (("chapters", "project_id"), ("chapter_outlines", "project_id"), ("novel_blueprints", "project_id"), ("task_runtime_tasks", "project_id"), ("project_members", "project_id"), ("token_budgets", "project_id")):
                try:
                    related[table] = int(db.execute(f"SELECT COUNT(*) FROM {table} WHERE {column} = ?", (project_id,)).fetchone()[0])
                except sqlite3.OperationalError:
                    related[table] = -1
            task_statuses = [str(item[0]) for item in db.execute("SELECT status FROM task_runtime_tasks WHERE project_id = ? ORDER BY created_at ASC", (project_id,)).fetchall()]
            fixtures.append({"project_id": project_id, "title": row["title"], "user_id": row["user_id"], "status": row["status"], "created_at": row["created_at"], "updated_at": row["updated_at"], "has_uuid_title": len(str(row["title"]).rsplit(" ", 1)[-1]) >= 8, "task_statuses": task_statuses, "related_counts": related})
    print(json.dumps({"status": "SMOKE_FIXTURE_AUDIT_PASSED", "database": str(db_path), "fixture_count": len(fixtures), "fixtures": fixtures}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
