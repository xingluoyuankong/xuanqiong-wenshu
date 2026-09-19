#!/usr/bin/env python3
"""Generate a non-executing migration plan from provenance and schema baseline."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

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

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=("sqlite", "mysql"), default="sqlite")
    parser.add_argument("--output", default="-")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "backend/db/migration_manifest.json").read_text())
    baseline = json.loads((root / manifest["baseline_file"]).read_text())
    current_commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    steps = []
    provenance_failures = []
    for index, item in enumerate(manifest["migrations"], 1):
        path = root / item["path"]
        exists = path.is_file()
        actual_hash = sha256(path) if exists else None
        if not exists or actual_hash != item["sha256"] or path.stat().st_size != item["size"]:
            provenance_failures.append(item["path"])
        text = path.read_text(encoding="utf-8", errors="replace") if exists else ""
        mysql_tokens = sorted(name for name, pattern in MYSQL_ONLY.items() if pattern.search(text))
        dangerous_tokens = sorted(name for name, pattern in DANGEROUS.items() if pattern.search(text))
        if args.target == "sqlite":
            executable = False
            reason = "SQL fragment is not executed on SQLite; create a dialect-specific translation and test on a database copy."
        elif dangerous_tokens:
            executable = False
            reason = "Manual review required because destructive SQL tokens are present."
        elif mysql_tokens:
            executable = False
            reason = "MySQL fragment requires backup, transaction/rollback review, and a MySQL copy dry-run before execution."
        else:
            executable = False
            reason = "No automatic execution: migration runner is not established yet."
        steps.append({
            "order": index, "path": item["path"], "target": args.target,
            "mysql_only_tokens": mysql_tokens, "dangerous_tokens": dangerous_tokens,
            "execute": executable, "reason": reason,
        })
    plan = {
        "plan_type": "non_executing_migration_plan",
        "generated_at": "2026-09-19",
        "current_commit": current_commit,
        "manifest_commit": manifest.get("git_commit"),
        "baseline_file": manifest.get("baseline_file"),
        "baseline_schema_sha256": baseline.get("database_schema_sha256"),
        "target": args.target,
        "execute_policy": "never_execute",
        "preconditions": [
            "create a fresh database backup",
            "verify schema baseline and migration fragment hashes",
            "run dialect-specific dry-run on a database copy",
            "capture upgrade and rollback evidence",
            "obtain manual review before production apply",
        ],
        "provenance_failures": provenance_failures,
        "steps": steps,
        "status": "blocked_by_missing_runner" if not provenance_failures else "provenance_failed",
    }
    rendered = json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
    if args.output == "-": print(rendered, end="")
    else: Path(args.output).write_text(rendered, encoding="utf-8")
    return 0 if not provenance_failures else 10

if __name__ == "__main__":
    raise SystemExit(main())
