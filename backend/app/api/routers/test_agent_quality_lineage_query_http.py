from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from app.agent.write_executor import list_artifact_quality_blockers
from app.api.routers.agent import get_current_user
from app.core.dependencies import get_current_user as dependency_current_user
from app.db.session import get_session
from app.main import app
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
from app.services.agent_quality_service import AgentQualityService


async def _seed_quality_lineage_facts(task_session):
    owner = User(
        id=4821,
        username="quality-query-owner",
        email="quality-query-owner@example.com",
        hashed_password="x",
        is_active=True,
    )
    other = User(
        id=4822,
        username="quality-query-other",
        email="quality-query-other@example.com",
        hashed_password="x",
        is_active=True,
    )
    owner_session = AgentSession(id="quality-query-session-owner", user_id=owner.id, status="active")
    owner_run = AgentRun(
        id="quality-query-run-owner",
        session_id=owner_session.id,
        user_id=owner.id,
        correlation_id="quality-query-correlation-owner",
        transaction_id="quality-query-transaction-owner",
        status="created",
        context_json={},
    )
    other_session = AgentSession(id="quality-query-session-other", user_id=other.id, status="active")
    other_run = AgentRun(
        id="quality-query-run-other",
        session_id=other_session.id,
        user_id=other.id,
        correlation_id="quality-query-correlation-other",
        transaction_id="quality-query-transaction-other",
        status="created",
        context_json={},
    )
    source = AgentArtifactRef(
        id="quality-query-source",
        run_id=owner_run.id,
        correlation_id=owner_run.correlation_id,
        transaction_id=owner_run.transaction_id,
        user_id=owner.id,
        project_id="quality-query-project",
        kind="chapter_version",
        uri="agent-artifact://quality-query-source",
        sha256="a" * 64,
        metadata_json={"status": "accepted"},
    )
    candidate = AgentArtifactRef(
        id="quality-query-candidate",
        run_id=owner_run.id,
        correlation_id=owner_run.correlation_id,
        transaction_id=owner_run.transaction_id,
        user_id=owner.id,
        project_id="quality-query-project",
        kind="chapter_candidate",
        uri="agent-artifact://quality-query-candidate",
        sha256="b" * 64,
        # Deliberately contradict the relational Gate.  It remains only a legacy projection.
        metadata_json={"status": "candidate", "quality_gate": {"decision": "passed", "blockers": []}},
    )
    legacy = AgentArtifactRef(
        id="quality-query-legacy",
        run_id=owner_run.id,
        correlation_id=owner_run.correlation_id,
        transaction_id=owner_run.transaction_id,
        user_id=owner.id,
        project_id="quality-query-project",
        kind="chapter_candidate",
        uri="agent-artifact://quality-query-legacy",
        sha256="c" * 64,
        metadata_json={"status": "candidate"},
    )
    other_artifact = AgentArtifactRef(
        id="quality-query-other-artifact",
        run_id=other_run.id,
        correlation_id=other_run.correlation_id,
        transaction_id=other_run.transaction_id,
        user_id=other.id,
        project_id="quality-query-other-project",
        kind="chapter_candidate",
        uri="agent-artifact://quality-query-other",
        sha256="d" * 64,
        metadata_json={"status": "candidate"},
    )
    result = QualityResult(
        result_id="quality-query-result",
        run_id=owner_run.id,
        artifact_ref_id=candidate.id,
        correlation_id=owner_run.correlation_id,
        transaction_id=owner_run.transaction_id,
        user_id=owner.id,
        project_id=candidate.project_id,
        assessor_id="quality-query-fixture",
        rubric_version="p1-b2-test",
        status="completed",
        score=41.0,
        summary="存在持久化 blocker。",
        metrics_json={"fixture": True},
        input_digest="e" * 64,
        result_digest="f" * 64,
    )
    result.findings.append(
        QualityFinding(
            finding_id="quality-query-finding",
            code="ending_pressure_missing",
            category="ending",
            severity="blocker",
            status="open",
            message="章节结尾缺少推进压力。",
            fingerprint="1" * 64,
            location_json={"start_char": 0, "end_char": 4},
            evidence_json={"excerpt": "候选正文"},
            remediation_json={"action": "补充结尾冲突"},
        )
    )
    result.gates.append(
        QualityGate(
            gate_id="quality-query-gate",
            run_id=owner_run.id,
            artifact_ref_id=candidate.id,
            correlation_id=owner_run.correlation_id,
            transaction_id=owner_run.transaction_id,
            gate_name=AgentQualityService.GATE_NAME,
            gate_version="p1-b2-test",
            decision="blocked",
            blocker_count=1,
            rationale="持久化 blocker 禁止接受。",
            policy_json={"fixture": True},
        )
    )
    lineage = ArtifactLineage(
        lineage_id="quality-query-lineage",
        run_id=owner_run.id,
        source_artifact_ref_id=source.id,
        derived_artifact_ref_id=candidate.id,
        correlation_id=owner_run.correlation_id,
        transaction_id=owner_run.transaction_id,
        relation_type="accepted_as_version",
        operation="chapter.version.accept",
        input_digest=source.sha256,
        output_digest=candidate.sha256,
        metadata_json={"fixture": True},
    )
    task_session.add_all([
        owner,
        other,
        owner_session,
        owner_run,
        other_session,
        other_run,
        source,
        candidate,
        legacy,
        other_artifact,
        result,
        lineage,
    ])
    await task_session.commit()
    return owner, other, source, candidate, legacy


@pytest.mark.asyncio
async def test_quality_and_lineage_http_return_durable_facts_scope_and_empty_legacy_projection(task_session):
    owner, other, source, candidate, legacy = await _seed_quality_lineage_facts(task_session)
    active_user = SimpleNamespace(id=owner.id)

    async def override_session():
        yield task_session

    async def override_current_user():
        return active_user

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[dependency_current_user] = override_current_user
    app.dependency_overrides[get_current_user] = override_current_user
    try:
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)
        async with httpx.AsyncClient(transport=transport, base_url="http://agent-test") as client:
            quality_response = await client.get(f"/api/agent/artifacts/{candidate.id}/quality")
            lineage_response = await client.get(f"/api/agent/artifacts/{candidate.id}/lineage")
            legacy_quality_response = await client.get(f"/api/agent/artifacts/{legacy.id}/quality")
            legacy_lineage_response = await client.get(f"/api/agent/artifacts/{legacy.id}/lineage")
            active_user.id = other.id
            denied_quality_response = await client.get(f"/api/agent/artifacts/{candidate.id}/quality")
            denied_lineage_response = await client.get(f"/api/agent/artifacts/{candidate.id}/lineage")

        assert quality_response.status_code == 200
        quality_payload = quality_response.json()
        assert quality_payload["artifact_id"] == candidate.id
        assert quality_payload["quality_result"]["result_id"] == "quality-query-result"
        assert quality_payload["quality_result"]["score"] == 41.0
        assert quality_payload["gate"]["decision"] == "blocked"
        assert quality_payload["gate"]["blocker_count"] == 1
        assert [(item["code"], item["severity"]) for item in quality_payload["findings"]] == [
            ("ending_pressure_missing", "blocker")
        ]
        assert "metadata_json" not in quality_payload

        assert lineage_response.status_code == 200
        lineage_payload = lineage_response.json()
        assert lineage_payload["artifact_id"] == candidate.id
        assert lineage_payload["downstream_edges"] == []
        assert len(lineage_payload["upstream_edges"]) == 1
        edge = lineage_payload["upstream_edges"][0]
        assert edge["relation_type"] == "accepted_as_version"
        assert edge["source_artifact"]["id"] == source.id
        assert edge["derived_artifact"]["id"] == candidate.id

        assert legacy_quality_response.status_code == 200
        assert legacy_quality_response.json() == {
            "artifact_id": legacy.id,
            "quality_result": None,
            "findings": [],
            "gate": None,
        }
        assert legacy_lineage_response.status_code == 200
        assert legacy_lineage_response.json() == {
            "artifact_id": legacy.id,
            "upstream_edges": [],
            "downstream_edges": [],
        }

        assert denied_quality_response.status_code == 404
        assert denied_quality_response.json()["detail"]["code"] == "AGENT_NOT_FOUND"
        assert denied_lineage_response.status_code == 404
        assert denied_lineage_response.json()["detail"]["code"] == "AGENT_NOT_FOUND"
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(dependency_current_user, None)
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_quality_blockers_prefer_relational_findings_over_tampered_metadata(task_session, monkeypatch):
    owner, _, _, candidate, _ = await _seed_quality_lineage_facts(task_session)

    async def fake_read_artifact_content(*, artifact_id: str, user_id: int, session):
        assert artifact_id == candidate.id
        assert user_id == owner.id
        return candidate, "候选正文继续展开。"

    monkeypatch.setattr("app.agent.write_executor.read_artifact_content", fake_read_artifact_content)
    rows = await list_artifact_quality_blockers(
        artifact_id=candidate.id,
        user_id=owner.id,
        session=task_session,
    )

    assert [(item["code"], item["source"], item["severity"]) for item in rows] == [
        ("ending_pressure_missing", "quality_finding", "blocker")
    ]
    assert rows[0]["message"] == "章节结尾缺少推进压力。"
    assert rows[0]["anchor_status"] == "located"
