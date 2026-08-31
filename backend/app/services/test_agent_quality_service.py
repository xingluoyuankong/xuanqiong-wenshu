from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from sqlalchemy import select

from app.agent.tool_adapters import execute_chapter_version_accept
from app.agent.write_executor import _ARTIFACT_ROOT, accept_candidate_artifact, execute_approved_write
from app.models import ArtifactLineage, Chapter, ChapterVersion, NovelProject, QualityFinding, QualityGate, QualityResult, User
from app.models.agent import AgentArtifactRef
from app.services.agent_quality_service import AgentQualityService
from app.services.agent_runtime import AgentConflict, AgentRuntimeService


async def _owner(session, user_id: int) -> User:
    user = User(
        id=user_id,
        username=f"p1b-{user_id}",
        email=f"p1b-{user_id}@example.com",
        hashed_password="x",
        is_active=True,
    )
    session.add(user)
    await session.flush()
    return user


async def _candidate(session, *, user_id: int, project_id: str, content: str, chapter_number: int = 1):
    user = await _owner(session, user_id)
    session.add(NovelProject(id=project_id, user_id=user.id, title="P1-B"))
    await session.flush()
    runtime = AgentRuntimeService(session)
    agent_session = await runtime.create_session(user_id=user.id, project_id=project_id)
    run = await runtime.create_run(session_id=agent_session.id, user_id=user.id, project_id=project_id)
    key = f"p1b-{user_id}-{chapter_number}.md"
    _ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    (_ARTIFACT_ROOT / key).write_text(content, encoding="utf-8")
    artifact = await runtime.add_artifact(
        run_id=run.id,
        user_id=user.id,
        project_id=project_id,
        kind="chapter_candidate",
        uri=f"agent-artifact://{key}",
        sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        metadata={"status": "candidate", "storage_key": key, "chapter_number": chapter_number},
    )
    return user, run, artifact, _ARTIFACT_ROOT / key


@pytest.mark.asyncio
async def test_candidate_creation_persists_quality_result_findings_and_blocking_gate(task_session, monkeypatch):
    user = await _owner(task_session, 3111)
    task_session.add(NovelProject(id="p1b-created", user_id=user.id, title="Created"))
    await task_session.flush()
    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=user.id, project_id="p1b-created")
    run = await runtime.create_run(session_id=agent_session.id, user_id=user.id, project_id="p1b-created")
    approval = await runtime.request_approval(
        run_id=run.id,
        user_id=user.id,
        tool_name="chapter.generate",
        project_id="p1b-created",
        arguments={"chapter_number": 2, "goal": "candidate"},
    )
    await runtime.decide_approval(approval_id=approval.id, user_id=user.id, approved=True)

    async def fake_stream(self, **kwargs):
        yield "候选正文。"

    monkeypatch.setattr("app.agent.write_executor.LLMService.stream_visible_response", fake_stream)
    monkeypatch.setattr(
        "app.agent.write_executor._quality_observation",
        lambda content, metadata: (
            {"story_progression_guard": {"score": 32}},
            {"passed": False, "blockers": [{"code": "hard_block", "message": "必须重写", "source": "test"}]},
        ),
    )
    artifact = await execute_approved_write(approval_id=approval.id, user_id=user.id, session=task_session)
    try:
        result = (await task_session.execute(select(QualityResult).where(QualityResult.artifact_ref_id == artifact.id))).scalar_one()
        gate = (await task_session.execute(select(QualityGate).where(QualityGate.quality_result_id == result.id))).scalar_one()
        finding = (await task_session.execute(select(QualityFinding).where(QualityFinding.quality_result_id == result.id))).scalar_one()
        assert result.input_digest == artifact.sha256
        assert gate.decision == "blocked"
        assert gate.blocker_count == 1
        assert finding.code == "hard_block"
        assert finding.severity == "blocker"
        assert artifact.metadata_json["quality_persistence"]["gate_id"] == gate.id
    finally:
        (_ARTIFACT_ROOT / artifact.metadata_json["storage_key"]).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_blocked_persisted_gate_rejects_metadata_bypass_and_creates_no_version(task_session, monkeypatch):
    user, run, artifact, path = await _candidate(task_session, user_id=3112, project_id="p1b-blocked", content="blocked candidate", chapter_number=3)
    try:
        await AgentQualityService(task_session).evaluate_candidate(
            artifact=artifact,
            content="blocked candidate",
            summaries={},
            quality_gate={"passed": False, "blockers": [{"code": "must_fix", "message": "阻断", "source": "test"}]},
        )
        await task_session.commit()
        # Deliberate bypass attempt: forge the legacy projection and make a
        # re-evaluator return passed.  Acceptance must still consume the stored
        # blocked Gate and fail without creating a chapter version.
        metadata = dict(artifact.metadata_json or {})
        metadata["quality_gate"] = {"passed": True, "blockers": []}
        metadata["quality_status"] = "passed"
        artifact.metadata_json = metadata
        await task_session.commit()
        monkeypatch.setattr("app.agent.write_executor._quality_observation", lambda content, metadata: ({}, {"passed": True, "blockers": []}))
        with pytest.raises(AgentConflict, match="persisted quality gate"):
            await accept_candidate_artifact(artifact_id=artifact.id, user_id=user.id, note="bypass", session=task_session)
        chapter = (await task_session.execute(select(Chapter).where(Chapter.project_id == "p1b-blocked", Chapter.chapter_number == 3))).scalar_one_or_none()
        assert chapter is None
    finally:
        path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_passed_gate_accepts_and_writes_accepted_artifact_lineage(task_session):
    content = "passed candidate"
    user, run, artifact, path = await _candidate(task_session, user_id=3113, project_id="p1b-passed", content=content, chapter_number=4)
    try:
        evaluation = await AgentQualityService(task_session).evaluate_candidate(
            artifact=artifact,
            content=content,
            summaries={"story_progression_guard": {"score": 88}},
            quality_gate={"passed": True, "blockers": [], "warnings": [{"code": "minor", "message": "可优化", "source": "test"}]},
        )
        await task_session.commit()
        accepted = await accept_candidate_artifact(artifact_id=artifact.id, user_id=user.id, note="pass", session=task_session)
        assert accepted.metadata_json["status"] == "accepted"
        accepted_ref_id = accepted.metadata_json["accepted_artifact_ref_id"]
        accepted_ref = await task_session.get(AgentArtifactRef, accepted_ref_id)
        assert accepted_ref is not None
        lineage = (await task_session.execute(select(ArtifactLineage).where(ArtifactLineage.source_artifact_ref_id == artifact.id))).scalar_one()
        assert lineage.derived_artifact_ref_id == accepted_ref.id
        assert lineage.relation_type == "accepted_as_version"
        assert lineage.metadata_json["quality_gate_id"] == evaluation.gate.id
        chapter = (await task_session.execute(select(Chapter).where(Chapter.project_id == "p1b-passed", Chapter.chapter_number == 4))).scalar_one()
        version = (await task_session.execute(select(ChapterVersion).where(ChapterVersion.chapter_id == chapter.id))).scalar_one()
        assert version.metadata_["quality_gate_id"] == evaluation.gate.id
    finally:
        path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_blocked_gate_rejects_approved_accept_command_before_version_write(task_session):
    user, run, artifact, path = await _candidate(task_session, user_id=3114, project_id="p1b-command", content="blocked command", chapter_number=5)
    try:
        await AgentQualityService(task_session).evaluate_candidate(
            artifact=artifact,
            content="blocked command",
            summaries={},
            quality_gate={"passed": False, "blockers": [{"code": "command_block", "message": "禁止提交", "source": "test"}]},
        )
        runtime = AgentRuntimeService(task_session)
        approval = await runtime.request_approval(
            run_id=run.id,
            user_id=user.id,
            tool_name="chapter.version.accept",
            project_id="p1b-command",
            arguments={"artifact_id": artifact.id, "note": "must fail"},
        )
        await runtime.decide_approval(approval_id=approval.id, user_id=user.id, approved=True)
        with pytest.raises(AgentConflict, match="persisted quality gate"):
            await execute_chapter_version_accept(
                session=task_session,
                user_id=user.id,
                project_id="p1b-command",
                arguments={"_approval_id": approval.id, "artifact_id": artifact.id},
            )
        assert (await runtime.get_approval(approval_id=approval.id, user_id=user.id)).status == "execution_failed"
        chapter = (await task_session.execute(select(Chapter).where(Chapter.project_id == "p1b-command", Chapter.chapter_number == 5))).scalar_one_or_none()
        assert chapter is None
    finally:
        path.unlink(missing_ok=True)
