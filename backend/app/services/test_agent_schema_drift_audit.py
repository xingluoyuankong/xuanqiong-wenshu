from __future__ import annotations

from pathlib import Path

import pytest

from app.services.test_alembic_migrations import _upgrade
from scripts.audit_agent_schema_drift import P0_B_TABLES, audit_p0_b_schema_drift


def test_p0_b_schema_drift_audit_is_clean_after_fresh_head_upgrade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "agent-p0b-audit.sqlite"
    _upgrade(monkeypatch, db_path)

    report = audit_p0_b_schema_drift(f"sqlite:///{db_path.as_posix()}")

    assert report["clean"] is True
    assert report["drift_count"] == 0
    assert report["drift"] == []
    assert tuple(report["tables"]) == P0_B_TABLES


def test_p0_b_schema_drift_audit_reports_missing_snapshot_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "agent-p0b-drift.sqlite"
    _upgrade(monkeypatch, db_path)

    import sqlite3

    con = sqlite3.connect(db_path)
    con.execute("ALTER TABLE agent_run_capability_snapshots DROP COLUMN resolved_version")
    con.commit()
    con.close()

    report = audit_p0_b_schema_drift(f"sqlite:///{db_path.as_posix()}")

    assert report["clean"] is False
    assert report["drift_count"] >= 1
    assert any("resolved_version" in item["rendered"] for item in report["drift"])
