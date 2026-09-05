"""Read-only inventory of OpenAPI smoke fixture projects."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
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
TERMINAL_RUNTIME_STATUSES = frozenset({"stale", "completed", "failed", "cancelled"})


def _dry_run_decision(task_statuses: list[str]) -> str:
    """Classify a fixture without mutating it or treating an empty task set as safe."""
    if task_statuses and all(status in TERMINAL_RUNTIME_STATUSES for status in task_statuses):
        return "candidate"
    return "hold-active-runtime"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=None, help="SQLite database path; defaults to SQLITE_DB_PATH or backend/storage/xuanqiong_wenshu.db")
    parser.add_argument("--as-of", default=None, help="ISO timestamp used for deterministic age calculations; defaults to current UTC time")
    args = parser.parse_args()
    db_path = _db_path(args.db)
    as_of_raw = args.as_of or datetime.now(timezone.utc).isoformat()
    try:
        as_of = datetime.fromisoformat(as_of_raw.replace("Z", "+00:00"))
    except ValueError as exc:
        parser.error(f"invalid --as-of timestamp: {exc}")
    if not db_path.exists():
        print(json.dumps({"status": "SMOKE_FIXTURE_AUDIT_FAILED", "error": f"database not found: {db_path}"}, ensure_ascii=False))
        return 1
    with sqlite3.connect(db_path) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute("SELECT id, title, user_id, status, created_at, updated_at FROM novel_projects WHERE title LIKE 'OpenAPI Smoke %' ORDER BY created_at ASC, id ASC").fetchall()
        fixtures: list[dict[str, Any]] = []
        status_counts: dict[str, int] = {}
        for row in rows:
            project_id = str(row["id"])
            related: dict[str, int] = {}
            for table, column in (("chapters", "project_id"), ("chapter_outlines", "project_id"), ("novel_blueprints", "project_id"), ("task_runtime_tasks", "project_id"), ("project_members", "project_id"), ("token_budgets", "project_id")):
                try:
                    related[table] = int(db.execute(f"SELECT COUNT(*) FROM {table} WHERE {column} = ?", (project_id,)).fetchone()[0])
                except sqlite3.OperationalError:
                    related[table] = -1
            task_statuses = [str(item[0]) for item in db.execute("SELECT status FROM task_runtime_tasks WHERE project_id = ? ORDER BY created_at ASC", (project_id,)).fetchall()]
            runtime_rows = db.execute("SELECT task_id, status, owner_user_id, lease_owner, heartbeat_at, updated_at FROM task_runtime_tasks WHERE project_id = ? ORDER BY created_at ASC", (project_id,)).fetchall()
            owner_ids = sorted({int(item["owner_user_id"]) for item in runtime_rows if item["owner_user_id"] is not None})
            markers = ["xq-smoke-fixture"] if "smoke" in str(row["title"]).lower() else []
            age_seconds = None
            if row["created_at"]:
                created = datetime.fromisoformat(str(row["created_at"]).replace(" ", "T").replace("Z", "+00:00"))
                if created.tzinfo is None: created = created.replace(tzinfo=timezone.utc)
                age_seconds = max(0, int((as_of - created).total_seconds()))
            decision = _dry_run_decision(task_statuses)
            status_counts[decision] = status_counts.get(decision, 0) + 1
            fixtures.append({"project_id": project_id, "title": row["title"], "user_id": row["user_id"], "status": row["status"], "created_at": row["created_at"], "updated_at": row["updated_at"], "has_uuid_title": len(str(row["title"]).rsplit(" ", 1)[-1]) >= 8, "task_statuses": task_statuses, "runtime_rows": [dict(item) for item in runtime_rows], "owner_ids": owner_ids, "markers": markers, "age_seconds": age_seconds, "dry_run_decision": decision, "related_counts": related})
    print(json.dumps({"status": "SMOKE_FIXTURE_AUDIT_PASSED", "database": str(db_path), "fixture_count": len(fixtures), "as_of": as_of.isoformat(), "decision_counts": status_counts, "fixtures": fixtures}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())