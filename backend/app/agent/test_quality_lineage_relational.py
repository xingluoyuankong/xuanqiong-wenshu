from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.models import (
    AgentArtifactRef,
    AgentRun,
    AgentSession,
    ArtifactLineage,
    QualityFinding,
    QualityGate,
    QualityResult,
    User,
)


EXPECTED_TABLES = {
    "agent_quality_results",
    "agent_quality_findings",
    "agent_quality_gates",
    "agent_artifact_lineages",
}


async def _run_with_artifacts(task_session):
    user = User(
        id=2810,
        username="quality-lineage",
        email="quality-lineage@example.com",
        hashed_password="x",
        is_active=True,
    )
    task_session.add(user)
    await task_session.flush()
    agent_session = AgentSession(
        id="agent-session-quality-2810",
        user_id=user.id,
        status="active",
    )
    run = AgentRun(
        id="agent-run-quality-2810",
        session_id=agent_session.id,
        user_id=user.id,
        correlation_id="correlation-quality-2810",
        transaction_id="transaction-quality-2810",
        status="created",
        context_json={},
    )
    task_session.add_all([agent_session, run])
    await task_session.flush()
    source = AgentArtifactRef(
        id="artifact-source-2810",
        run_id=run.id,
        correlation_id=run.correlation_id,
        transaction_id=run.transaction_id,
        user_id=user.id,
        project_id=None,
        kind="chapter_candidate",
        uri="agent-artifact://quality-source-2810",
        sha256="a" * 64,
        metadata_json={"status": "candidate"},
    )
    derived = AgentArtifactRef(
        id="artifact-derived-2810",
        run_id=run.id,
        correlation_id=run.correlation_id,
        transaction_id=run.transaction_id,
        user_id=user.id,
        project_id=None,
        kind="chapter_candidate",
        uri="agent-artifact://quality-derived-2810",
        sha256="b" * 64,
        metadata_json={"status": "candidate"},
    )
    task_session.add_all([source, derived])
    await task_session.flush()
    return user, run, source, derived


@pytest.mark.asyncio
async def test_quality_result_findings_gate_and_lineage_persist_as_one_trace(task_session):
    user, run, source, derived = await _run_with_artifacts(task_session)
    result = QualityResult(
        result_id="quality-result-2810",
        run_id=run.id,
        artifact_ref_id=derived.id,
        correlation_id=run.correlation_id,
        transaction_id=run.transaction_id,
        user_id=user.id,
        project_id=None,
        assessor_id="structural-quality-v1",
        rubric_version="2026-08-28",
        score=83.5,
        summary="候选章节满足基本结构质量要求。",
        metrics_json={"word_count": 1800, "dialogue_state_changes": 3},
        input_digest="c" * 64,
        result_digest="d" * 64,
    )
    finding = QualityFinding(
        finding_id="quality-finding-2810",
        code="foreshadowing_weak",
        category="foreshadowing",
        severity="warning",
        status="open",
        message="伏笔回收力度不足。",
        fingerprint="e" * 64,
        location_json={"chapter_number": 2, "offset": 120},
        evidence_json={"excerpt": "线索只出现一次"},
        remediation_json={"action": "增强回收"},
    )
    result.findings.append(finding)
    gate = QualityGate(
        gate_id="quality-gate-2810",
        run_id=run.id,
        artifact_ref_id=derived.id,
        correlation_id=run.correlation_id,
        transaction_id=run.transaction_id,
        gate_name="structural_publish",
        gate_version="v1",
        decision="passed",
        blocker_count=0,
        rationale="没有 blocker。",
        policy_json={"minimum_score": 80},
    )
    result.gates.append(gate)
    lineage = ArtifactLineage(
        lineage_id="artifact-lineage-2810",
        run_id=run.id,
        source_artifact_ref_id=source.id,
        derived_artifact_ref_id=derived.id,
        correlation_id=run.correlation_id,
        transaction_id=run.transaction_id,
        relation_type="rewritten_from",
        operation="chapter.rewrite",
        input_digest=source.sha256,
        output_digest=derived.sha256,
        metadata_json={"selection": {"start": 120, "end": 280}},
    )
    task_session.add_all([result, lineage])
    await task_session.commit()

    saved = (
        await task_session.execute(select(QualityResult).where(QualityResult.result_id == "quality-result-2810"))
    ).scalar_one()
    assert saved.artifact_ref_id == derived.id
    assert saved.score == pytest.approx(83.5)
    assert [(item.code, item.severity) for item in saved.findings] == [("foreshadowing_weak", "warning")]
    assert [(item.gate_name, item.decision) for item in saved.gates] == [("structural_publish", "passed")]
    saved_lineage = (
        await task_session.execute(select(ArtifactLineage).where(ArtifactLineage.lineage_id == "artifact-lineage-2810"))
    ).scalar_one()
    assert (saved_lineage.source_artifact_ref_id, saved_lineage.derived_artifact_ref_id) == (source.id, derived.id)


@pytest.mark.asyncio
async def test_quality_and_lineage_constraints_reject_duplicate_finding_invalid_gate_and_self_edge(task_session):
    user, run, source, derived = await _run_with_artifacts(task_session)
    result = QualityResult(
        result_id="quality-result-constraint-2810",
        run_id=run.id,
        artifact_ref_id=derived.id,
        correlation_id=run.correlation_id,
        transaction_id=run.transaction_id,
        user_id=user.id,
        project_id=None,
        score=60,
    )
    task_session.add(result)
    await task_session.flush()

    task_session.add_all([
        QualityFinding(
            quality_result_id=result.id, finding_id="quality-finding-constraint-a", code="repeat",
            severity="warning", message="a", fingerprint="f" * 64,
        ),
        QualityFinding(
            quality_result_id=result.id, finding_id="quality-finding-constraint-b", code="repeat",
            severity="warning", message="b", fingerprint="f" * 64,
        ),
    ])
    with pytest.raises(IntegrityError):
        await task_session.flush()
    await task_session.rollback()

    user, run, source, derived = await _run_with_artifacts(task_session)
    result = QualityResult(
        result_id="quality-result-invalid-gate-2810",
        run_id=run.id,
        artifact_ref_id=derived.id,
        correlation_id=run.correlation_id,
        transaction_id=run.transaction_id,
        user_id=user.id,
        project_id=None,
    )
    task_session.add(result)
    await task_session.flush()
    task_session.add(QualityGate(
        gate_id="quality-gate-invalid-2810", quality_result_id=result.id, run_id=run.id,
        artifact_ref_id=derived.id, correlation_id=run.correlation_id, decision="unknown",
    ))
    with pytest.raises(IntegrityError):
        await task_session.flush()
    await task_session.rollback()

    user, run, source, _ = await _run_with_artifacts(task_session)
    task_session.add(ArtifactLineage(
        lineage_id="artifact-lineage-invalid-2810", run_id=run.id,
        source_artifact_ref_id=source.id, derived_artifact_ref_id=source.id,
        correlation_id=run.correlation_id,
    ))
    with pytest.raises(IntegrityError):
        await task_session.flush()


def _upgrade_to_023(monkeypatch: pytest.MonkeyPatch, db_path: Path) -> None:
    from alembic import command
    from alembic.config import Config

    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    command.upgrade(config, "023_agent_quality_lineage")


def test_fresh_023_upgrade_is_repeatable_and_creates_quality_lineage_tables(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "quality-lineage-fresh-023.sqlite"
    _upgrade_to_023(monkeypatch, db_path)
    _upgrade_to_023(monkeypatch, db_path)

    con = sqlite3.connect(db_path)
    assert con.execute("select version_num from alembic_version").fetchone()[0] == "023_agent_quality_lineage"
    tables = {row[0] for row in con.execute("select name from sqlite_master where type='table'")}
    assert EXPECTED_TABLES <= tables
    assert con.execute("select name from sqlite_master where type='index' and name='ix_agent_artifact_lineages_relation_type'").fetchone() == ("ix_agent_artifact_lineages_relation_type",)
    assert {row[2] for row in con.execute("pragma foreign_key_list(agent_quality_gates)").fetchall()} >= {
        "agent_quality_results", "agent_runs", "agent_artifact_refs",
    }
    con.close()


def test_022_upgrade_to_023_creates_relational_quality_and_lineage_constraints(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "quality-lineage-old-022.sqlite"
    con = sqlite3.connect(db_path)
    con.executescript(
        """
        PRAGMA foreign_keys=ON;
        CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL);
        INSERT INTO alembic_version VALUES ('022_agent_catalog_transaction_ids');
        CREATE TABLE agent_runs (id VARCHAR(36) PRIMARY KEY);
        CREATE TABLE agent_artifact_refs (id VARCHAR(36) PRIMARY KEY);
        """
    )
    con.commit()
    con.close()

    _upgrade_to_023(monkeypatch, db_path)
    _upgrade_to_023(monkeypatch, db_path)

    con = sqlite3.connect(db_path)
    assert con.execute("select version_num from alembic_version").fetchone()[0] == "023_agent_quality_lineage"
    for table in EXPECTED_TABLES:
        assert con.execute("select 1 from sqlite_master where type='table' and name=?", (table,)).fetchone() == (1,)
    quality_fk_targets = {row[2] for row in con.execute("pragma foreign_key_list(agent_quality_results)").fetchall()}
    lineage_fk_targets = {row[2] for row in con.execute("pragma foreign_key_list(agent_artifact_lineages)").fetchall()}
    assert quality_fk_targets >= {"agent_runs", "agent_artifact_refs"}
    assert lineage_fk_targets == {"agent_runs", "agent_artifact_refs"}
    ddl = con.execute("select sql from sqlite_master where type='table' and name='agent_artifact_lineages'").fetchone()[0]
    assert "ck_agent_artifact_lineage_distinct_endpoints" in ddl
    assert "uq_agent_artifact_lineage_edge" in ddl
    con.close()



