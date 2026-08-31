from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.agent.registry import DEFAULT_TOOL_REGISTRY
from app.agent.write_executor import accept_candidate_artifact, execute_approved_write
from app.services.agent_runtime import AgentConflict
from app.models import Chapter, ChapterVersion, NovelProject, User
from app.models.agent import AgentEventRecord
from app.models.agent_catalog import AgentCapabilityExecution
from app.services.agent_runtime import AgentRuntimeService


async def _owner(session, user_id: int = 901) -> User:
    user = User(id=user_id, username=f"write-{user_id}", email=f"write-{user_id}@example.com", hashed_password="x", is_active=True)
    session.add(user)
    await session.flush()
    return user


@pytest.mark.asyncio
async def test_approved_write_creates_candidate_and_accept_saves_version(task_session, monkeypatch):
    user = await _owner(task_session)
    task_session.add(NovelProject(id="write-project", user_id=user.id, title="Write Project"))
    await task_session.flush()
    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=user.id, project_id="write-project")
    run = await runtime.create_run(session_id=agent_session.id, user_id=user.id, project_id="write-project")
    step = await runtime.ensure_step(run_id=run.id, user_id=user.id, step_order=1, tool_name="chapter.generate", idempotency_key="write-step", input_payload={"chapter_number": 3, "goal": "write chapter"})
    step.status = "awaiting_approval"
    await task_session.commit()
    approval = await runtime.request_approval(run_id=run.id, user_id=user.id, step_id=step.id, tool_name="chapter.generate", project_id="write-project", arguments={"chapter_number": 3, "goal": "write chapter"})
    await runtime.decide_approval(approval_id=approval.id, user_id=user.id, approved=True)

    async def fake_stream(self, **kwargs):
        yield "candidate first."
        yield "candidate second."

    monkeypatch.setattr("app.agent.write_executor.LLMService.stream_visible_response", fake_stream)
    artifact = await execute_approved_write(approval_id=approval.id, user_id=user.id, session=task_session)
    assert artifact.kind == "chapter_candidate"
    assert artifact.metadata_json["status"] == "candidate"
    assert artifact.metadata_json["candidate_writer_provider_called"] is True
    assert artifact.metadata_json["candidate_writer_provider_fallback_reason"] is None
    assert artifact.metadata_json["candidate_writer_model_ref"]
    refreshed_run = await runtime.get_run(run.id, user.id)
    assert refreshed_run.context_json["candidate_writer_provider_called"] is True
    candidate_path = Path(__file__).resolve().parents[2] / "output" / "agent-artifacts" / artifact.metadata_json["storage_key"]
    assert candidate_path.is_file()
    saved_step = (await runtime.list_steps(run_id=run.id, user_id=user.id))[0]
    assert saved_step.status == "completed"
    assert saved_step.output_json["artifact_id"] == artifact.id
    execution = (await task_session.execute(
        select(AgentCapabilityExecution).where(AgentCapabilityExecution.run_id == run.id)
    )).scalar_one()
    assert execution.capability_id == "chapter.generate"
    assert execution.step_id == step.id
    assert execution.status == "completed"
    assert execution.input_json["_approval_id"] == approval.id
    assert execution.output_json["artifact_id"] == artifact.id
    with pytest.raises(Exception):
        await execute_approved_write(approval_id=approval.id, user_id=user.id, session=task_session)
    try:
        accepted = await accept_candidate_artifact(artifact_id=artifact.id, user_id=user.id, note="accept", session=task_session)
        assert accepted.metadata_json["status"] == "accepted"
        chapter = (await task_session.execute(select(Chapter).where(Chapter.project_id == "write-project", Chapter.chapter_number == 3))).scalars().first()
        assert chapter is not None
        versions = (await task_session.execute(select(ChapterVersion).where(ChapterVersion.chapter_id == chapter.id))).scalars().all()
        assert len(versions) == 1
    finally:
        candidate_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_write_executor_rejects_unapproved_and_invalid_chapter(task_session):
    user = await _owner(task_session, 902)
    task_session.add(NovelProject(id="write-project-2", user_id=user.id, title="Write Project 2"))
    await task_session.flush()
    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=user.id, project_id="write-project-2")
    run = await runtime.create_run(session_id=agent_session.id, user_id=user.id, project_id="write-project-2")
    approval = await runtime.request_approval(run_id=run.id, user_id=user.id, tool_name="chapter.generate", project_id="write-project-2", arguments={"chapter_number": 0})
    with pytest.raises(Exception):
        await execute_approved_write(approval_id=approval.id, user_id=user.id, session=task_session)

@pytest.mark.asyncio
async def test_rewrite_uses_owned_source_version_and_records_parent(task_session, monkeypatch):
    user = await _owner(task_session, 903)
    task_session.add(NovelProject(id="rewrite-project", user_id=user.id, title="Rewrite Project"))
    chapter = Chapter(project_id="rewrite-project", chapter_number=4, status="successful", word_count=10)
    task_session.add(chapter)
    await task_session.flush()
    source = ChapterVersion(chapter_id=chapter.id, content="原始第一句。\n原始第二句。", status="selected")
    task_session.add(source)
    await task_session.flush()
    chapter.selected_version_id = source.id
    await task_session.commit()

    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=user.id, project_id="rewrite-project")
    run = await runtime.create_run(session_id=agent_session.id, user_id=user.id, project_id="rewrite-project")
    step = await runtime.ensure_step(run_id=run.id, user_id=user.id, step_order=1, tool_name="chapter.rewrite", idempotency_key="rewrite-step", input_payload={"chapter_number": 4, "source_version_id": source.id})
    step.status = "awaiting_approval"
    await task_session.commit()
    approval = await runtime.request_approval(run_id=run.id, user_id=user.id, step_id=step.id, tool_name="chapter.rewrite", project_id="rewrite-project", arguments={"chapter_number": 4, "source_version_id": source.id, "instruction": "优化对话"})
    await runtime.decide_approval(approval_id=approval.id, user_id=user.id, approved=True)
    captured = {}

    async def fake_stream(self, **kwargs):
        captured["prompt"] = kwargs["user_prompt"]
        yield "改写后的候选。"

    monkeypatch.setattr("app.agent.write_executor.LLMService.stream_visible_response", fake_stream)
    artifact = await execute_approved_write(approval_id=approval.id, user_id=user.id, session=task_session)
    assert str(source.id) in captured["prompt"]
    assert "原始第一句" in captured["prompt"]
    assert artifact.metadata_json["source_version_id"] == source.id
    candidate_path = Path(__file__).resolve().parents[2] / "output" / "agent-artifacts" / artifact.metadata_json["storage_key"]
    try:
        accepted = await accept_candidate_artifact(artifact_id=artifact.id, user_id=user.id, note="rewrite", session=task_session)
        versions = (await task_session.execute(select(ChapterVersion).where(ChapterVersion.chapter_id == chapter.id).order_by(ChapterVersion.id))).scalars().all()
        assert accepted.metadata_json["source_version_id"] == source.id
        assert versions[-1].parent_version_id == source.id
    finally:
        candidate_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_rewrite_rejects_source_version_from_another_project(task_session, monkeypatch):
    user = await _owner(task_session, 904)
    task_session.add_all([
        NovelProject(id="rewrite-project-a", user_id=user.id, title="A"),
        NovelProject(id="rewrite-project-b", user_id=user.id, title="B"),
    ])
    chapter_a = Chapter(project_id="rewrite-project-a", chapter_number=4, status="successful", word_count=3)
    chapter_b = Chapter(project_id="rewrite-project-b", chapter_number=4, status="successful", word_count=3)
    task_session.add_all([chapter_a, chapter_b])
    await task_session.flush()
    source_a = ChapterVersion(chapter_id=chapter_a.id, content="A source", status="selected")
    source_b = ChapterVersion(chapter_id=chapter_b.id, content="B source", status="selected")
    task_session.add_all([source_a, source_b])
    await task_session.flush()
    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=user.id, project_id="rewrite-project-a")
    run = await runtime.create_run(session_id=agent_session.id, user_id=user.id, project_id="rewrite-project-a")
    approval = await runtime.request_approval(run_id=run.id, user_id=user.id, tool_name="chapter.rewrite", project_id="rewrite-project-a", arguments={"chapter_number": 4, "source_version_id": source_b.id})
    await runtime.decide_approval(approval_id=approval.id, user_id=user.id, approved=True)
    with pytest.raises(Exception):
        await execute_approved_write(approval_id=approval.id, user_id=user.id, session=task_session)

@pytest.mark.asyncio
async def test_registry_version_accept_requires_approved_same_run_artifact_and_is_idempotent(task_session, monkeypatch):
    user = await _owner(task_session, 905)
    task_session.add(NovelProject(id="accept-tool-project", user_id=user.id, title="Accept Tool Project"))
    await task_session.flush()
    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=user.id, project_id="accept-tool-project")
    run = await runtime.create_run(session_id=agent_session.id, user_id=user.id, project_id="accept-tool-project")
    write_step = await runtime.ensure_step(run_id=run.id, user_id=user.id, step_order=1, tool_name="chapter.generate", idempotency_key="accept-tool-write", input_payload={"chapter_number": 5})
    write_step.status = "awaiting_approval"
    await task_session.commit()
    write_approval = await runtime.request_approval(run_id=run.id, user_id=user.id, step_id=write_step.id, tool_name="chapter.generate", project_id="accept-tool-project", arguments={"chapter_number": 5})
    await runtime.decide_approval(approval_id=write_approval.id, user_id=user.id, approved=True)

    async def fake_stream(self, **kwargs):
        yield "可接受的候选正文。"

    monkeypatch.setattr("app.agent.write_executor.LLMService.stream_visible_response", fake_stream)
    monkeypatch.setattr("app.agent.write_executor._quality_observation", lambda content, metadata: ({}, {"passed": True, "quality_issue_codes": [], "blockers": []}))
    artifact = await execute_approved_write(approval_id=write_approval.id, user_id=user.id, session=task_session)
    candidate_path = Path(__file__).resolve().parents[2] / "output" / "agent-artifacts" / artifact.metadata_json["storage_key"]
    try:
        acceptance = await runtime.request_approval(run_id=run.id, user_id=user.id, tool_name="chapter.version.accept", project_id="accept-tool-project", arguments={"artifact_id": artifact.id, "note": "accept through registry"})
        await runtime.decide_approval(approval_id=acceptance.id, user_id=user.id, approved=True)
        result = await DEFAULT_TOOL_REGISTRY.execute("chapter.version.accept", session=task_session, user_id=user.id, project_id="accept-tool-project", arguments={"_approval_id": acceptance.id, "artifact_id": artifact.id})
        accepted = result["artifact"]
        assert accepted.metadata_json["status"] == "accepted"
        assert accepted.metadata_json["acceptance_approval_id"] == acceptance.id
        assert (await runtime.get_approval(approval_id=acceptance.id, user_id=user.id)).status == "executed"
        acceptance_execution = (await task_session.execute(
            select(AgentCapabilityExecution).where(
                AgentCapabilityExecution.run_id == run.id,
                AgentCapabilityExecution.capability_id == "chapter.version.accept",
            )
        )).scalar_one()
        assert acceptance_execution.status == "completed"
        assert acceptance_execution.input_json["_approval_id"] == acceptance.id
        assert acceptance_execution.output_json["artifact_id"] == accepted.id
        chapter = (await task_session.execute(select(Chapter).where(Chapter.project_id == "accept-tool-project", Chapter.chapter_number == 5))).scalar_one()
        versions = (await task_session.execute(select(ChapterVersion).where(ChapterVersion.chapter_id == chapter.id))).scalars().all()
        assert len(versions) == 1
        assert versions[0].metadata_["acceptance_approval_id"] == acceptance.id
        repeated = await accept_candidate_artifact(artifact_id=artifact.id, user_id=user.id, note="duplicate", session=task_session)
        assert repeated.id == accepted.id
        assert len((await task_session.execute(select(ChapterVersion).where(ChapterVersion.chapter_id == chapter.id))).scalars().all()) == 1
        mismatch = await runtime.request_approval(run_id=run.id, user_id=user.id, tool_name="chapter.version.accept", project_id="accept-tool-project", arguments={"artifact_id": "different-artifact"})
        await runtime.decide_approval(approval_id=mismatch.id, user_id=user.id, approved=True)
        with pytest.raises(Exception):
            await DEFAULT_TOOL_REGISTRY.execute("chapter.version.accept", session=task_session, user_id=user.id, project_id="accept-tool-project", arguments={"_approval_id": mismatch.id, "artifact_id": artifact.id})
    finally:
        candidate_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_write_handler_identity_mismatch_is_rejected_and_recorded(task_session, monkeypatch):
    """Deliberately replace the live handler: frozen Run identity must reject it."""
    user = await _owner(task_session, 906)
    task_session.add(NovelProject(id="write-identity-project", user_id=user.id, title="Write Identity Project"))
    await task_session.flush()
    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=user.id, project_id="write-identity-project")
    run = await runtime.create_run(session_id=agent_session.id, user_id=user.id, project_id="write-identity-project")
    step = await runtime.ensure_step(
        run_id=run.id, user_id=user.id, step_order=1, tool_name="chapter.generate",
        idempotency_key="identity-write-step", input_payload={"chapter_number": 7},
    )
    step.status = "awaiting_approval"
    await task_session.commit()
    approval = await runtime.request_approval(
        run_id=run.id, user_id=user.id, step_id=step.id, tool_name="chapter.generate",
        project_id="write-identity-project", arguments={"chapter_number": 7},
    )
    await runtime.decide_approval(approval_id=approval.id, user_id=user.id, approved=True)

    async def tampered_write_handler(**kwargs):
        return {"tampered": True}

    # Reverse validation: a changed live handler must not execute under the old snapshot.
    monkeypatch.setitem(DEFAULT_TOOL_REGISTRY._handlers, "chapter.generate", tampered_write_handler)
    with pytest.raises(Exception, match="handler identity"):
        await execute_approved_write(approval_id=approval.id, user_id=user.id, session=task_session)

    execution = (await task_session.execute(
        select(AgentCapabilityExecution).where(AgentCapabilityExecution.run_id == run.id)
    )).scalar_one()
    assert execution.status == "failed"
    assert execution.capability_id == "chapter.generate"
    assert execution.error_type == "AgentCapabilityHandlerIdentityMismatch"
    assert execution.input_json["_approval_id"] == approval.id
    assert (await runtime.get_approval(approval_id=approval.id, user_id=user.id)).status == "execution_failed"
    event = (await task_session.execute(
        select(AgentEventRecord).where(
            AgentEventRecord.run_id == run.id,
            AgentEventRecord.event_type == "write_execution_failed",
        )
    )).scalar_one()
    assert event.data_json["error_type"] == "AgentCapabilityHandlerIdentityMismatch"


@pytest.mark.asyncio
async def test_candidate_writer_timeout_records_writer_provenance_and_rejects_candidate(task_session, monkeypatch):
    user = await _owner(task_session, 907)
    task_session.add(NovelProject(id="write-timeout-project", user_id=user.id, title="Write Timeout Project"))
    await task_session.flush()
    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=user.id, project_id="write-timeout-project")
    run = await runtime.create_run(session_id=agent_session.id, user_id=user.id, project_id="write-timeout-project")
    step = await runtime.ensure_step(
        run_id=run.id, user_id=user.id, step_order=1, tool_name="chapter.generate",
        idempotency_key="timeout-write-step", input_payload={"chapter_number": 6},
    )
    step.status = "awaiting_approval"
    await task_session.commit()
    approval = await runtime.request_approval(
        run_id=run.id, user_id=user.id, step_id=step.id, tool_name="chapter.generate",
        project_id="write-timeout-project", arguments={"chapter_number": 6, "goal": "timeout fixture"},
    )
    await runtime.decide_approval(approval_id=approval.id, user_id=user.id, approved=True)

    async def timeout_stream(self, **kwargs):
        raise TimeoutError("candidate writer timeout fixture")
        yield "unreachable"

    monkeypatch.setattr("app.agent.write_executor.LLMService.stream_visible_response", timeout_stream)
    with pytest.raises(AgentConflict, match="candidate writer execution failed: TimeoutError"):
        await execute_approved_write(approval_id=approval.id, user_id=user.id, session=task_session)

    saved = await runtime.get_run(run.id, user.id)
    assert saved.status == "failed"
    assert saved.context_json["candidate_writer_provider_called"] is False
    assert saved.context_json["candidate_writer_provider_fallback_reason"] == "TimeoutError"
    assert (await runtime.get_approval(approval_id=approval.id, user_id=user.id)).status == "execution_failed"
    events = await runtime.list_events(run_id=run.id, user_id=user.id)
    failure = next(item for item in events if item.event_type == "write_execution_failed")
    assert failure.data_json["candidate_writer_provider_called"] is False
    assert failure.data_json["candidate_writer_provider_fallback_reason"] == "TimeoutError"
    assert await runtime.list_artifacts(run_id=run.id, user_id=user.id) == []
