#!/usr/bin/env python3
"""Classify SQL migration fragments without executing them."""
from __future__ import annotations

import json
import re
import sys
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


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    directory = root / "backend/db/migrations"
    records = []
    for path in sorted(directory.glob("*.sql")):
        text = path.read_text(encoding="utf-8", errors="replace")
        mysql_tokens = sorted(name for name, pattern in MYSQL_ONLY.items() if pattern.search(text))
        dangerous_tokens = sorted(name for name, pattern in DANGEROUS.items() if pattern.search(text))
        if dangerous_tokens:
            classification = "manual_review_required"
        elif mysql_tokens:
            classification = "mysql_only_translation_required"
        else:
            classification = "dialect_neutral_candidate"
        records.append({
            "path": str(path.relative_to(root)).replace("\\", "/"),
            "classification": classification,
            "mysql_only_tokens": mysql_tokens,
            "dangerous_tokens": dangerous_tokens,
            "execute_on_sqlite": False,
            "execute_on_mysql": not bool(dangerous_tokens),
        })
    report = {
        "report_type": "migration_fragment_dialect_audit",
        "status": "pass" if not any(item["dangerous_tokens"] for item in records) else "review",
        "execute_policy": "report_only_never_execute",
        "fragments": records,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
