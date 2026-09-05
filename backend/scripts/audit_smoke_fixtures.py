"""Read-only inventory and deterministic dry-run classification of OpenAPI smoke fixtures."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any


MARKER_PATTERN = re.compile(r"xq-smoke-fixture:[A-Za-z0-9._-]+")
TERMINAL_RUNTIME_STATUSES = frozenset({"stale", "completed", "failed", "cancelled"})


def _db_path(value: str | None) -> Path:
    configured = value or os.getenv("SQLITE_DB_PATH", "storage/xuanqiong_wenshu.db")
    path = Path(configured)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[1] / path
    return path.resolve()


def _extract_markers(*values: object) -> list[str]:
    markers: set[str] = set()
    for value in values:
        markers.update(MARKER_PATTERN.findall(str(value or "")))
    return sorted(markers)


def _dry_run_decision(
    task_statuses: list[str],
    markers: list[str] | tuple[str, ...] = (),
    age_seconds: int | None = None,
    min_age_seconds: int = 3600,
) -> str:
    """Classify without mutating data; marked, young, active, and empty fixtures are held."""
    if not task_statuses:
        return "hold-no-runtime"
    if any(status not in TERMINAL_RUNTIME_STATUSES for status in task_statuses):
        return "hold-active-runtime"
    if markers:
        return "hold-marked-fixture"
    if age_seconds is not None and age_seconds < max(0, int(min_age_seconds)):
        return "hold-too-young"
    return "candidate"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=None, help="SQLite database path; defaults to SQLITE_DB_PATH or backend/storage/xuanqiong_wenshu.db")
    parser.add_argument("--as-of", default=None, help="ISO timestamp used for deterministic age calculations; defaults to current UTC time")
    parser.add_argument("--min-age-seconds", type=int, default=3600, help="minimum age for an unmarked terminal fixture to become a candidate (default: 3600)")
    args = parser.parse_args()
    if args.min_age_seconds < 0:
        parser.error("--min-age-seconds must be non-negative")
    db_path = _db_path(args.db)
    as_of_raw = args.as_of or datetime.now(timezone.utc).isoformat()
    try:
        as_of = datetime.fromisoformat(as_of_raw.replace("Z", "+00:00"))
    except ValueError as exc:
        parser.error(f"invalid --as-of timestamp: {exc}")
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    if not db_path.exists():
        print(json.dumps({"status": "SMOKE_FIXTURE_AUDIT_FAILED", "error": f"database not found: {db_path}"}, ensure_ascii=False))
        return 1
    with sqlite3.connect(db_path) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute("SELECT id, title, initial_prompt, user_id, status, created_at, updated_at FROM novel_projects WHERE title LIKE 'OpenAPI Smoke %' ORDER BY created_at ASC, id ASC").fetchall()
        fixtures: list[dict[str, Any]] = []
        decision_counts: dict[str, int] = {}
        for row in rows:
            project_id = str(row["id"])
            related: dict[str, int] = {}
            for table, column in (("chapters", "project_id"), ("chapter_outlines", "project_id"), ("novel_blueprints", "project_id"), ("task_runtime_tasks", "project_id"), ("project_members", "project_id"), ("token_budgets", "project_id")):
                try:
                    related[table] = int(db.execute(f"SELECT COUNT(*) FROM {table} WHERE {column} = ?", (project_id,)).fetchone()[0])
                except sqlite3.OperationalError:
                    related[table] = -1
            runtime_rows = db.execute("SELECT task_id, status, owner_user_id, lease_owner, heartbeat_at, updated_at FROM task_runtime_tasks WHERE project_id = ? ORDER BY created_at ASC", (project_id,)).fetchall()
            task_statuses = [str(item["status"]) for item in runtime_rows]
            owner_ids = sorted({int(item["owner_user_id"]) for item in runtime_rows if item["owner_user_id"] is not None})
            markers = _extract_markers(row["title"], row["initial_prompt"])
            age_seconds = None
            if row["created_at"]:
                created = datetime.fromisoformat(str(row["created_at"]).replace(" ", "T").replace("Z", "+00:00"))
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                age_seconds = max(0, int((as_of - created).total_seconds()))
            decision = _dry_run_decision(task_statuses, markers, age_seconds, args.min_age_seconds)
            decision_counts[decision] = decision_counts.get(decision, 0) + 1
            fixtures.append({"project_id": project_id, "title": row["title"], "user_id": row["user_id"], "status": row["status"], "created_at": row["created_at"], "updated_at": row["updated_at"], "has_uuid_title": len(str(row["title"]).rsplit(" ", 1)[-1]) >= 8, "task_statuses": task_statuses, "runtime_rows": [dict(item) for item in runtime_rows], "owner_ids": owner_ids, "markers": markers, "age_seconds": age_seconds, "dry_run_decision": decision, "related_counts": related})
    print(json.dumps({"status": "SMOKE_FIXTURE_AUDIT_PASSED", "database": str(db_path), "as_of": as_of.isoformat(), "min_age_seconds": args.min_age_seconds, "fixture_count": len(fixtures), "decision_counts": decision_counts, "fixtures": fixtures}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
