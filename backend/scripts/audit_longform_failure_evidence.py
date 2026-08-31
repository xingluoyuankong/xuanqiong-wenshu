"""Validate a redacted T-25 long-form failure evidence JSON file."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.longform_evidence import validate_longform_failure_evidence


def audit(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {
            "kind": "t25_real_longform_failure_evidence_audit",
            "source_file": path.name,
            "valid": False,
            "errors": [f"cannot read evidence: {type(exc).__name__}"],
        }
    errors = validate_longform_failure_evidence(payload)
    return {
        "kind": "t25_real_longform_failure_evidence_audit",
        "source_file": path.name,
        "valid": not errors,
        "errors": errors,
        "limitations": [
            "This validates redaction and internal counters only; it does not judge literary quality.",
            "This does not create Provider or human-review evidence.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.evidence)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
