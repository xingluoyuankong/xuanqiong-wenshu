from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "audit_smoke_fixtures.py"
SPEC = importlib.util.spec_from_file_location("audit_smoke_fixtures", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_dry_run_decision_holds_empty_active_young_and_marked_fixtures():
    assert MODULE._dry_run_decision([]) == "hold-no-runtime"
    assert MODULE._dry_run_decision(["queued"]) == "hold-active-runtime"
    assert MODULE._dry_run_decision(["stale"], age_seconds=10, min_age_seconds=3600) == "hold-too-young"
    assert MODULE._dry_run_decision(["stale"], markers=["xq-smoke-fixture:id"]) == "hold-marked-fixture"
    assert MODULE._dry_run_decision(["stale"], age_seconds=3600, min_age_seconds=3600) == "candidate"
    assert MODULE._dry_run_decision(["completed", "failed", "cancelled"]) == "candidate"
