from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.agent import write_executor
from app.agent.provider_attempt import ProviderAttemptLedger
from app.agent.write_executor import execute_approved_write, read_artifact_content
from app.api.routers.agent import (
    accept_agent_artifact,
    get_agent_artifact_lineage,
    get_agent_artifact_quality,
    get_agent_run_provider_provenance,
    list_agent_artifact_quality_blockers,
    list_agent_artifact_rewrite_instructions,
    list_agent_artifacts,
    read_agent_artifact_content,
)
from app.agent.schemas import AgentArtifactAcceptRequest
from app.models import Chapter, ChapterVersion, NovelProject, User
from app.models.agent import AgentArtifactRef, AgentEventRecord
from app.models.agent_lineage import ArtifactLineage
from app.models.agent_quality import QualityGate, QualityResult
from app.services.agent_quality_query_service import AgentQualityQueryService
from app.services.agent_runtime import AgentRuntimeService, AgentConflict, AgentNotFound


async def _create_write_fixture(session):
    user = User(
        username="artifact-lifecycle-owner",
        email="artifact-lifecycle-owner@example.com",
        hashed_password="fixture-password",
        is_active=True,
    )
    session.add(user)
    await session.flush()
    project = NovelProject(id="artifact-lifecycle-project", user_id=user.id, title="Artifact lifecycle fixture")
    session.add(project)
    await session.flush()

    runtime = AgentRuntimeService(session)
    agent_session = await runtime.create_session(user_id=user.id, project_id=project.id)
    run = await runtime.create_run(session_id=agent_session.id, user_id=user.id, project_id=project.id, context={"requested_tools": ["chapter.generate"]})
    step = await runtime.ensure_step(
        run_id=run.id,
        user_id=user.id,
        step_order=1,
        tool_name="chapter.generate",
        idempotency_key=f"{run.id}:artifact-lifecycle-step",
        input_payload={"chapter_number": 1, "goal": "generate a recoverable candidate"},
    )
    step.status = "awaiting_approval"
    await session.commit()
    approval = await runtime.request_approval(
        run_id=run.id,
        user_id=user.id,
        step_id=step.id,
        tool_name="chapter.generate",
        project_id=project.id,
        arguments={
            "chapter_number": 1,
            "goal": "generate a recoverable candidate",
            "instruction": "写出一个有明确场景、动作和结果的章节候选",
        },
    )
    await runtime.decide_approval(approval_id=approval.id, user_id=user.id, approved=True, reason="fixture")
    return user, project, run, step, approval


@pytest.mark.asyncio
async def test_agent_run_provider_artifact_quality_acceptance_is_recoverable(task_session, monkeypatch, tmp_path: Path):
    """Exercise the real write path without leaving files or hand-built Artifact IDs."""
    user, project, run, step, approval = await _create_write_fixture(task_session)
    artifact_root = tmp_path / "agent-artifacts"
    monkeypatch.setattr(write_executor, "_ARTIFACT_ROOT", artifact_root)

    content = (
        "夜雨落在青石巷，沈砚收起伞，沿着河堤追上那盏忽明忽暗的纸灯。"
        "纸灯停在旧戏台前，台下没有观众，台上却传来三声木鱼。"
        "他推开半掩的幕布，看见一枚刻着玄穹印记的铜牌，随后把铜牌收入袖中，转身走向城门。"
    )

    async def fixture_provider_stream(self, **kwargs):
        ledger: ProviderAttemptLedger = kwargs["attempt_ledger"]
        attempt = ledger.begin(
            role=kwargs["attempt_role"],
            provider_ref="artifact-lifecycle-fixture-provider",
            model_ref="artifact-lifecycle-fixture-model",
        )
        ledger.mark_first_token(attempt.attempt_id)
        ledger.finish(attempt.attempt_id, output=content)
        yield content[: len(content) // 2]
        yield content[len(content) // 2 :]

    monkeypatch.setattr(write_executor.LLMService, "stream_visible_response", fixture_provider_stream)

    candidate = await execute_approved_write(
        approval_id=approval.id,
        user_id=user.id,
        session=task_session,
    )

    assert candidate.id
    assert candidate.kind == "chapter_candidate"
    assert candidate.run_id == run.id
    assert candidate.project_id == project.id
    assert candidate.sha256 == hashlib.sha256(content.encode("utf-8")).hexdigest()
    assert candidate.metadata_json["status"] == "candidate"
    assert candidate.metadata_json["storage_key"]
    assert candidate.metadata_json["candidate_writer_provider_called"] is True
    candidate_path = artifact_root / candidate.metadata_json["storage_key"]
    assert candidate_path.is_file()
    assert candidate_path.read_text(encoding="utf-8") == content

    saved_run = await AgentRuntimeService(task_session).get_run(run.id, user.id)
    assert saved_run.status == "paused"
    assert saved_run.current_phase == "candidate_ready"
    provenance = saved_run.context_json
    assert provenance["candidate_writer_provider_called"] is True
    assert provenance["candidate_writer_model_ref"]
    attempts = provenance["candidate_writer_provider_attempts"]["provider_attempts"]
    assert len(attempts) == 1
    assert attempts[0]["role"] == "writer"
    assert attempts[0]["provider_ref"] == "artifact-lifecycle-fixture-provider"
    assert attempts[0]["model_ref"] == "artifact-lifecycle-fixture-model"
    assert attempts[0]["status"] == "succeeded"

    api_user = SimpleNamespace(id=user.id)
    api_provenance = await get_agent_run_provider_provenance(
        run_id=run.id, session=task_session, current_user=api_user
    )
    assert api_provenance.candidate_writer_provider_called is True
    assert api_provenance.candidate_writer_provider_attempts["provider_attempts"][0]["provider_ref"] == (
        "artifact-lifecycle-fixture-provider"
    )

    api_artifacts = await list_agent_artifacts(
        run_id=run.id, limit=100, offset=None, session=task_session, current_user=api_user
    )
    assert [item.id for item in api_artifacts] == [candidate.id]

    api_content = await read_agent_artifact_content(
        artifact_id=candidate.id, session=task_session, current_user=api_user
    )
    assert api_content.body == content.encode("utf-8")
    api_quality = await get_agent_artifact_quality(
        artifact_id=candidate.id, session=task_session, current_user=api_user
    )
    assert api_quality.artifact_id == candidate.id
    assert api_quality.quality_result is not None
    assert api_quality.gate is not None
    assert api_quality.gate.decision == "passed"
    assert await list_agent_artifact_quality_blockers(
        artifact_id=candidate.id, session=task_session, current_user=api_user
    ) == []
    assert await list_agent_artifact_rewrite_instructions(
        artifact_id=candidate.id, session=task_session, current_user=api_user
    ) == []
    candidate_lineage = await get_agent_artifact_lineage(
        artifact_id=candidate.id, session=task_session, current_user=api_user
    )
    assert candidate_lineage.artifact_id == candidate.id
    assert candidate_lineage.upstream_edges == []
    assert candidate_lineage.downstream_edges == []

    saved_step = (await AgentRuntimeService(task_session).list_steps(run_id=run.id, user_id=user.id))[0]
    assert saved_step.id == step.id
    assert saved_step.status == "completed"
    assert saved_step.output_json["artifact_id"] == candidate.id

    quality_facts = await AgentQualityQueryService(task_session).get_quality_facts(
        artifact_id=candidate.id,
        user_id=user.id,
    )
    assert quality_facts.artifact.id == candidate.id
    assert quality_facts.result is not None
    assert quality_facts.result.artifact_ref_id == candidate.id
    assert quality_facts.gate is not None
    assert quality_facts.gate.decision == "passed"
    assert quality_facts.gate.blocker_count == 0

    readable_artifact, readable_content = await read_artifact_content(
        artifact_id=candidate.id,
        user_id=user.id,
        session=task_session,
    )
    assert readable_artifact.id == candidate.id
    assert readable_content == content

    events = await AgentRuntimeService(task_session).list_events(run_id=run.id, user_id=user.id)
    event_types = [event.event_type for event in events]
    assert "write_execution_started" in event_types
    assert "quality_check_completed" in event_types
    assert "artifact_created" in event_types
    created_event = next(event for event in events if event.event_type == "artifact_created")
    assert created_event.data_json["artifact_id"] == candidate.id

    accepted = await accept_agent_artifact(
        artifact_id=candidate.id,
        payload=AgentArtifactAcceptRequest(note="accept lifecycle fixture"),
        session=task_session,
        current_user=SimpleNamespace(id=user.id),
    )
    assert accepted.id == candidate.id
    assert accepted.metadata_json["status"] == "accepted"
    assert accepted.metadata_json["accepted_artifact_ref_id"]
    accepted_artifact_id = accepted.metadata_json["accepted_artifact_ref_id"]
    assert accepted_artifact_id != candidate.id

    accepted_artifact = (
        await task_session.execute(
            select(AgentArtifactRef).where(AgentArtifactRef.id == accepted_artifact_id)
        )
    ).scalar_one()
    assert accepted_artifact.kind == "chapter_version"
    assert accepted_artifact.metadata_json["source_artifact_id"] == candidate.id
    assert accepted_artifact.uri.startswith("chapter-version://")

    lineage = (
        await task_session.execute(
            select(ArtifactLineage).where(
                ArtifactLineage.source_artifact_ref_id == candidate.id,
                ArtifactLineage.derived_artifact_ref_id == accepted_artifact.id,
            )
        )
    ).scalar_one()
    assert lineage.relation_type == "accepted_as_version"
    assert lineage.operation == "chapter.version.accept"
    assert lineage.input_digest == candidate.sha256
    assert lineage.output_digest == accepted_artifact.sha256

    accepted_lineage = await get_agent_artifact_lineage(
        artifact_id=candidate.id, session=task_session, current_user=api_user
    )
    assert len(accepted_lineage.downstream_edges) == 1
    assert accepted_lineage.downstream_edges[0].derived_artifact.id == accepted_artifact.id
    assert accepted_lineage.downstream_edges[0].relation_type == "accepted_as_version"

    accepted_api_artifacts = await list_agent_artifacts(
        run_id=run.id, limit=100, offset=None, session=task_session, current_user=api_user
    )
    assert {item.id for item in accepted_api_artifacts} == {candidate.id, accepted_artifact.id}

    chapter = (
        await task_session.execute(
            select(Chapter).where(
                Chapter.project_id == project.id,
                Chapter.chapter_number == 1,
            )
        )
    ).scalar_one()
    version = (
        await task_session.execute(
            select(ChapterVersion).where(ChapterVersion.chapter_id == chapter.id)
        )
    ).scalar_one()
    assert int(accepted.metadata_json["accepted_version_id"]) == int(version.id)
    assert version.content == content

    accepted_content = await read_agent_artifact_content(
        artifact_id=accepted_artifact.id, session=task_session, current_user=api_user
    )
    assert accepted_content.body == content.encode("utf-8")
    original_metadata = dict(accepted_artifact.metadata_json)
    accepted_artifact.metadata_json = {**original_metadata, "chapter_number": 999}
    await task_session.flush()
    with pytest.raises(AgentNotFound, match="version is unavailable"):
        await read_artifact_content(artifact_id=accepted_artifact.id, user_id=user.id, session=task_session)
    accepted_artifact.metadata_json = original_metadata
    await task_session.flush()
    version.content = "tampered accepted version"
    await task_session.flush()
    with pytest.raises(AgentConflict, match="integrity"):
        await read_artifact_content(artifact_id=accepted_artifact.id, user_id=user.id, session=task_session)
    version.content = content
    await task_session.flush()

    final_run = await AgentRuntimeService(task_session).get_run(run.id, user.id)
    assert final_run.status == "completed"
    assert final_run.current_phase == "accepted"
    final_events = await AgentRuntimeService(task_session).list_events(run_id=run.id, user_id=user.id)
    assert "quality_check_completed" in [event.event_type for event in final_events]
    assert "artifact_accepted" in [event.event_type for event in final_events]
    assert "run_completed" in [event.event_type for event in final_events]

    artifacts = await AgentRuntimeService(task_session).list_artifacts(run_id=run.id, user_id=user.id)
    assert {item.id for item in artifacts} == {candidate.id, accepted_artifact.id}
    assert not any(item.id == "artifact-lifecycle-fixture" for item in artifacts)

    # The temporary root is the only external resource and is removed by pytest.
    assert candidate_path.exists()

    # Keep the relational assertions explicit so schema regressions fail here,
    # rather than appearing later as missing UI data.
    assert (
        await task_session.execute(
            select(QualityResult).where(QualityResult.artifact_ref_id == candidate.id)
        )
    ).scalar_one().result_id
    assert (
        await task_session.execute(
            select(QualityGate).where(QualityGate.artifact_ref_id == candidate.id)
        )
    ).scalar_one().gate_id
    assert (
        await task_session.execute(
            select(AgentEventRecord).where(
                AgentEventRecord.run_id == run.id,
                AgentEventRecord.event_type == "run_completed",
            )
        )
    ).scalar_one()


@pytest.mark.asyncio
async def test_acceptance_reservation_does_not_expand_read_only_runs(task_session):
    user, project, run, _, _ = await _create_write_fixture(task_session)
    from app.models.agent_catalog import AgentRunCapabilitySnapshot
    snapshot = (await task_session.execute(select(AgentRunCapabilitySnapshot).where(AgentRunCapabilitySnapshot.run_id == run.id))).scalar_one()
    assert set(snapshot.selected_capability_ids_json) == {"chapter.generate", "chapter.version.accept"}
    assert run.context_json["requested_tools"] == ["chapter.generate"]
    readonly = await AgentRuntimeService(task_session).create_run(
        session_id=run.session_id, user_id=user.id, project_id=project.id,
        context={"requested_tools": ["project.context"]},
    )
    read_snapshot = (await task_session.execute(select(AgentRunCapabilitySnapshot).where(AgentRunCapabilitySnapshot.run_id == readonly.id))).scalar_one()
    assert set(read_snapshot.selected_capability_ids_json) == {"project.context"}


@pytest.mark.asyncio
async def test_historical_candidate_without_acceptance_capability_has_no_partial_approval(task_session):
    from fastapi import HTTPException
    from app.models.agent import AgentApproval
    from app.models.agent_catalog import AgentRunCapabilitySnapshot
    user, project, run, _, _ = await _create_write_fixture(task_session)
    snapshot = (await task_session.execute(select(AgentRunCapabilitySnapshot).where(AgentRunCapabilitySnapshot.run_id == run.id))).scalar_one()
    # Reproduce a persisted pre-fix snapshot without mutating production history.
    snapshot.selected_capability_ids_json = ["chapter.generate"]
    await task_session.commit()
    candidate = await AgentRuntimeService(task_session).add_artifact(
        run_id=run.id, user_id=user.id, project_id=project.id, kind="chapter_candidate",
        uri="agent-artifact://historical-fixture.md", metadata={"status": "candidate"},
    )
    before = list((await task_session.execute(select(AgentApproval.id))).scalars())
    with pytest.raises(HTTPException) as error:
        await accept_agent_artifact(candidate.id, AgentArtifactAcceptRequest(), session=task_session, current_user=SimpleNamespace(id=user.id))
    assert error.value.status_code == 409
    assert "snapshot" in str(error.value.detail)
    assert list((await task_session.execute(select(AgentApproval.id))).scalars()) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("requested, expected", [
    ([" chapter.generate "], {"chapter.generate", "chapter.version.accept"}),
    ([" chapter.rewrite "], {"chapter.rewrite", "chapter.version.accept"}),
    (["chapter.generate", {"unknown": ["value"]}], {"chapter.generate", "chapter.version.accept"}),
    ([" project.context ", {"unknown": ["value"]}], {"project.context"}),
])
async def test_acceptance_reservation_uses_resolver_normalization(task_session, requested, expected):
    from app.models.agent_catalog import AgentRunCapabilitySnapshot
    user, project, initial, _, _ = await _create_write_fixture(task_session)
    run = await AgentRuntimeService(task_session).create_run(
        session_id=initial.session_id, user_id=user.id, project_id=project.id,
        context={"requested_tools": requested},
    )
    snapshot = (await task_session.execute(select(AgentRunCapabilitySnapshot).where(
        AgentRunCapabilitySnapshot.run_id == run.id
    ))).scalar_one()
    assert set(snapshot.selected_capability_ids_json) == expected
    assert run.context_json["requested_tools"] == requested
