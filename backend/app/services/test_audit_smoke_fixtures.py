from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "audit_smoke_fixtures.py"
SPEC = importlib.util.spec_from_file_location("audit_smoke_fixtures", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_dry_run_decision_requires_tasks_and_all_terminal_statuses():
    assert MODULE._dry_run_decision(["stale"]) == "candidate"
    assert MODULE._dry_run_decision(["completed", "failed", "cancelled"]) == "candidate"
    assert MODULE._dry_run_decision([]) == "hold-active-runtime"
    assert MODULE._dry_run_decision(["queued"]) == "hold-active-runtime"
    assert MODULE._dry_run_decision(["stale", "running"]) == "hold-active-runtime"