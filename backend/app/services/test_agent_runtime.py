from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from app.models import AgentEventRecord, NovelProject, User
from app.services.agent_runtime import AgentConflict, AgentRuntimeService, AgentScopeViolation


async def _user(session, user_id: int, name: str) -> User:
    user = User(id=user_id, username=name, email=f"{name}@example.com", hashed_password="x", is_active=True)
    session.add(user)
    await session.flush()
    return user


@pytest.mark.asyncio
async def test_agent_session_message_run_event_and_cursor(task_session):
    user = await _user(task_session, 701, "agent-owner")
    task_session.add(NovelProject(id="agent-project", user_id=user.id, title="Agent Project"))
    await task_session.flush()
    service = AgentRuntimeService(task_session)
    session = await service.create_session(user_id=user.id, project_id="agent-project", title="writing")
    message = await service.append_message(session_id=session.id, user_id=user.id, role="user", content="inspect chapter")
    run = await service.create_run(session_id=session.id, user_id=user.id, project_id="agent-project")
    first = await service.append_event(run_id=run.id, user_id=user.id, event_type="run_started", summary="start", data={"reasoning": "private", "progress": 10})
    second = await service.append_event(run_id=run.id, user_id=user.id, event_type="tool_call_progress", summary="reading", data={"thought": "hidden", "progress": 50})
    assert message.sequence == 1
    assert [item.sequence for item in await service.list_events(run_id=run.id, user_id=user.id)] == [1, 2]
    assert [item.sequence for item in await service.list_events(run_id=run.id, user_id=user.id, after_sequence=first.sequence)] == [2]
    assert second.data_json == {"progress": 50}


@pytest.mark.asyncio
async def test_agent_scope_and_terminal_transition_are_enforced(task_session):
    owner = await _user(task_session, 702, "agent-owner-2")
    other = await _user(task_session, 703, "agent-other")
    task_session.add(NovelProject(id="agent-project-2", user_id=owner.id, title="Owned"))
    await task_session.flush()
    service = AgentRuntimeService(task_session)
    session = await service.create_session(user_id=owner.id, project_id="agent-project-2")
    with pytest.raises(Exception):
        await service.get_session(session.id, other.id)
    with pytest.raises(AgentScopeViolation):
        await service.create_session(user_id=other.id, project_id="agent-project-2")
    run = await service.create_run(session_id=session.id, user_id=owner.id, project_id="agent-project-2")
    await service.update_run(run_id=run.id, user_id=owner.id, status="completed", progress=100)
    with pytest.raises(AgentConflict):
        await service.update_run(run_id=run.id, user_id=owner.id, status="running")


@pytest.mark.asyncio
async def test_write_approval_is_explicit_and_single_decision(task_session):
    user = await _user(task_session, 704, "agent-owner-3")
    service = AgentRuntimeService(task_session)
    session = await service.create_session(user_id=user.id)
    run = await service.create_run(session_id=session.id, user_id=user.id)
    approval = await service.request_approval(run_id=run.id, user_id=user.id, tool_name="chapter.generate", project_id=None)
    decided = await service.decide_approval(approval_id=approval.id, user_id=user.id, approved=True, reason="confirmed")
    assert decided.status == "approved"
    with pytest.raises(AgentConflict):
        await service.decide_approval(approval_id=approval.id, user_id=user.id, approved=False)


@pytest.mark.asyncio
async def test_step_bound_approval_is_unique_and_execution_claim_is_single_use(task_session):
    user = await _user(task_session, 718, "agent-approval-step")
    service = AgentRuntimeService(task_session)
    session = await service.create_session(user_id=user.id)
    run = await service.create_run(session_id=session.id, user_id=user.id)
    step = await service.ensure_step(run_id=run.id, user_id=user.id, step_order=1, tool_name="chapter.generate", idempotency_key="approval-step")
    step.status = "awaiting_approval"
    await task_session.commit()
    first = await service.request_approval(run_id=run.id, user_id=user.id, step_id=step.id, tool_name="chapter.generate", project_id=None)
    second = await service.request_approval(run_id=run.id, user_id=user.id, step_id=step.id, tool_name="chapter.generate", project_id=None)
    assert first.id == second.id
    assert first.step_id == step.id
    await service.decide_approval(approval_id=first.id, user_id=user.id, approved=True)
    claimed = await service.claim_approval_execution(approval_id=first.id, user_id=user.id)
    assert claimed.status == "executing"
    with pytest.raises(AgentConflict):
        await service.claim_approval_execution(approval_id=first.id, user_id=user.id)
    executed = await service.mark_approval_executed(approval_id=first.id, user_id=user.id, status="executed")
    assert executed.status == "executed"


@pytest.mark.asyncio
async def test_pause_resume_cancel_have_auditable_state_transitions(task_session):
    user = await _user(task_session, 705, "agent-owner-4")
    service = AgentRuntimeService(task_session)
    session = await service.create_session(user_id=user.id)
    run = await service.create_run(session_id=session.id, user_id=user.id)
    await service.update_run(run_id=run.id, user_id=user.id, status="running", progress=20)
    paused = await service.pause_run(run_id=run.id, user_id=user.id)
    assert paused.status == "paused"
    resumed = await service.resume_run(run_id=run.id, user_id=user.id)
    assert resumed.status == "running"
    cancelled = await service.cancel_run(run_id=run.id, user_id=user.id)
    assert cancelled.status == "cancelled"
    commands = await service.list_run_commands(run_id=run.id, user_id=user.id)
    assert [(item.command_type, item.status) for item in commands] == [
        ("pause", "applied"),
        ("resume", "applied"),
        ("cancel", "applied"),
    ]
    events = await service.list_events(run_id=run.id, user_id=user.id)
    assert [event.event_type for event in events] == [
        "run_command_requested", "run_paused", "run_command_applied",
        "run_command_requested", "run_resumed", "run_command_applied",
        "run_command_requested", "run_cancelled", "run_command_applied",
    ]
    with pytest.raises(AgentConflict):
        await service.resume_run(run_id=run.id, user_id=user.id)
    commands = await service.list_run_commands(run_id=run.id, user_id=user.id)
    assert commands[-1].command_type == "resume"
    assert commands[-1].status == "rejected"
    assert commands[-1].error_type == "AgentConflict"


@pytest.mark.asyncio
async def test_approval_decision_is_audited_and_artifact_is_user_scoped(task_session):
    user = await _user(task_session, 706, "agent-owner-5")
    service = AgentRuntimeService(task_session)
    session = await service.create_session(user_id=user.id, project_id=None)
    run = await service.create_run(session_id=session.id, user_id=user.id, project_id=None)
    approval = await service.request_approval(run_id=run.id, user_id=user.id, tool_name="chapter.generate", project_id=None)
    approved = await service.decide_approval(approval_id=approval.id, user_id=user.id, approved=True, reason="confirmed")
    assert approved.status == "approved"
    artifact = await service.add_artifact(run_id=run.id, user_id=user.id, project_id=None, kind="candidate", uri="agent://candidate/1", metadata={"source": "provider"})
    assert [item.id for item in await service.list_artifacts(run_id=run.id, user_id=user.id)] == [artifact.id]
    events = await service.list_events(run_id=run.id, user_id=user.id)
    assert [event.event_type for event in events] == [
        "approval_granted",
        "public_work_summary",
        "public_work_summary",
    ]
    assert events[1].data_json["selected_capability"] == "chapter.generate"
    assert events[-1].data_json["current_action"] == "已创建候选 Artifact，正在等待质量检查或作者查看。"


@pytest.mark.asyncio
async def test_run_context_is_persisted_for_recovery_without_private_fields(task_session):
    user = await _user(task_session, 707, "agent-recovery")
    service = AgentRuntimeService(task_session)
    session = await service.create_session(user_id=user.id)
    run = await service.create_run(session_id=session.id, user_id=user.id, context={"goal": "resume", "tool_results": [], "reasoning": "must not persist"})
    await service.set_run_context(run_id=run.id, user_id=user.id, context={"goal": "resume", "tool_results": [{"tool_name": "project.list"}], "thought": "hidden"})
    saved = await service.get_run(run.id, user.id)
    assert saved.context_json["goal"] == "resume"
    assert saved.context_json["tool_results"] == [{"tool_name": "project.list"}]
    assert saved.context_json["capability_snapshot"]["generation"] >= 1


@pytest.mark.asyncio
async def test_session_archive_is_user_scoped_and_durable(task_session):
    user = await _user(task_session, 708, "agent-archive")
    other = await _user(task_session, 709, "agent-archive-other")
    service = AgentRuntimeService(task_session)
    item = await service.create_session(user_id=user.id, title="archive me")
    archived = await service.archive_session(session_id=item.id, user_id=user.id)
    assert archived.status == "archived"
    with pytest.raises(Exception):
        await service.archive_session(session_id=item.id, user_id=other.id)


@pytest.mark.asyncio
async def test_unapproved_write_cannot_be_marked_executed(task_session):
    user = await _user(task_session, 710, "agent-unapproved")
    service = AgentRuntimeService(task_session)
    session = await service.create_session(user_id=user.id, project_id=None)
    run = await service.create_run(session_id=session.id, user_id=user.id, project_id=None)
    approval = await service.request_approval(run_id=run.id, user_id=user.id, tool_name="chapter.generate", project_id=None)
    with pytest.raises(AgentConflict):
        await service.mark_approval_executed(approval_id=approval.id, user_id=user.id)


@pytest.mark.asyncio
async def test_run_context_filters_nested_private_fields(task_session):
    user = await _user(task_session, 711, "agent-context-nested")
    service = AgentRuntimeService(task_session)
    session = await service.create_session(user_id=user.id)
    run = await service.create_run(session_id=session.id, user_id=user.id, context={"goal": "x"})
    await service.set_run_context(run_id=run.id, user_id=user.id, context={"goal": "x", "tool_results": [{"result": {"reasoning": "private", "ok": True}}]})
    saved = await service.get_run(run.id, user.id)
    assert saved.context_json["goal"] == "x"
    assert saved.context_json["tool_results"] == [{"result": {"ok": True}}]
    assert saved.context_json["capability_snapshot"]["generation"] >= 1


@pytest.mark.asyncio
async def test_run_step_checkpoint_is_idempotent_and_reuses_completed_output(task_session):
    user = await _user(task_session, 715, "agent-step-checkpoint")
    service = AgentRuntimeService(task_session)
    session = await service.create_session(user_id=user.id)
    run = await service.create_run(session_id=session.id, user_id=user.id)
    first = await service.ensure_step(run_id=run.id, user_id=user.id, step_order=1, tool_name="project.list", idempotency_key="run:1", input_payload={"goal": "x", "reasoning": "private"})
    second = await service.ensure_step(run_id=run.id, user_id=user.id, step_order=1, tool_name="project.list", idempotency_key="run:1", input_payload={"goal": "changed"})
    assert first.id == second.id
    assert first.input_json == {"goal": "x"}
    await service.start_step(step_id=first.id, user_id=user.id)
    completed = await service.complete_step(step_id=first.id, user_id=user.id, output={"projects": [], "reasoning": "private"})
    replay = await service.ensure_step(run_id=run.id, user_id=user.id, step_order=1, tool_name="project.list", idempotency_key="run:1")
    assert replay.status == "completed"
    assert replay.output_json == {"projects": []}
    assert completed.id == replay.id


@pytest.mark.asyncio
async def test_run_step_checkpoint_rejects_identity_collision(task_session):
    user = await _user(task_session, 716, "agent-step-collision")
    service = AgentRuntimeService(task_session)
    session = await service.create_session(user_id=user.id)
    run = await service.create_run(session_id=session.id, user_id=user.id)
    await service.ensure_step(run_id=run.id, user_id=user.id, step_order=1, tool_name="project.list", idempotency_key="run:collision")
    with pytest.raises(AgentConflict):
        await service.ensure_step(run_id=run.id, user_id=user.id, step_order=1, tool_name="chapter.inspect", idempotency_key="run:collision")


@pytest.mark.asyncio
async def test_run_step_claim_blocks_second_worker_and_allows_expiry_takeover(task_session):
    user = await _user(task_session, 717, "agent-step-lease")
    service = AgentRuntimeService(task_session)
    session = await service.create_session(user_id=user.id)
    run = await service.create_run(session_id=session.id, user_id=user.id)
    step = await service.ensure_step(run_id=run.id, user_id=user.id, step_order=1, tool_name="project.list", idempotency_key="run:lease")
    first = await service.claim_step(step_id=step.id, user_id=user.id, lease_owner="worker-a", lease_seconds=60)
    assert first.lease_owner == "worker-a"
    with pytest.raises(AgentConflict):
        await service.claim_step(step_id=step.id, user_id=user.id, lease_owner="worker-b", lease_seconds=60)
    first.lease_expires_at = service._now() - __import__("datetime").timedelta(seconds=1)
    await task_session.commit()
    taken = await service.claim_step(step_id=step.id, user_id=user.id, lease_owner="worker-b", lease_seconds=60)
    assert taken.lease_owner == "worker-b"
    assert taken.attempt_count == 2
    await service.complete_step(step_id=step.id, user_id=user.id, lease_owner="worker-b", output={"ok": True})
    replay = await service.claim_step(step_id=step.id, user_id=user.id, lease_owner="worker-c", lease_seconds=60)
    assert replay.status == "completed"
    assert replay.attempt_count == 2


@pytest.mark.asyncio
async def test_stale_step_reconcile_releases_expired_lease_once(task_session):
    user = await _user(task_session, 719, "agent-stale-step")
    service = AgentRuntimeService(task_session)
    session = await service.create_session(user_id=user.id)
    run = await service.create_run(session_id=session.id, user_id=user.id)
    step = await service.ensure_step(run_id=run.id, user_id=user.id, step_order=1, tool_name="project.list", idempotency_key="run:stale")
    claimed = await service.claim_step(step_id=step.id, user_id=user.id, lease_owner="stale-worker", lease_seconds=60)
    claimed.lease_expires_at = service._now() - __import__("datetime").timedelta(seconds=1)
    await task_session.commit()
    released = await service.reconcile_stale_steps()
    assert [item.id for item in released] == [step.id]
    assert released[0].status == "pending"
    assert released[0].lease_owner is None
    assert released[0].error_type == "LeaseExpiredRecovery"
    assert (await service.reconcile_stale_steps()) == []
    assert (await service.list_events(run_id=run.id, user_id=user.id))[-1].event_type == "step_lease_expired"


@pytest.mark.asyncio
async def test_event_payload_is_allowlisted_and_nested_provider_data_is_dropped(task_session):
    user = await _user(task_session, 713, "agent-event-allowlist")
    service = AgentRuntimeService(task_session)
    session = await service.create_session(user_id=user.id)
    run = await service.create_run(session_id=session.id, user_id=user.id)
    event = await service.append_event(
        run_id=run.id,
        user_id=user.id,
        event_type="assistant_delta",
        summary="visible",
        data={
            "content": "可见内容",
            "phase": "assistant_response",
            "reasoning": "private",
            "provider_secret": "secret",
            "raw_response": {"content": "不得写入", "reasoning": "不得泄漏"},
            "nested": {"ok": True},
        },
    )
    assert event.data_json == {"content": "可见内容", "phase": "assistant_response"}


@pytest.mark.asyncio
async def test_unknown_event_type_has_no_arbitrary_payload_fields(task_session):
    user = await _user(task_session, 714, "agent-event-unknown")
    service = AgentRuntimeService(task_session)
    session = await service.create_session(user_id=user.id)
    run = await service.create_run(session_id=session.id, user_id=user.id)
    event = await service.append_event(
        run_id=run.id,
        user_id=user.id,
        event_type="provider_raw_response",
        summary="不应暴露",
        data={"content": "raw", "status": "ok", "reasoning": "private"},
    )
    assert event.data_json == {}


@pytest.mark.asyncio
async def test_agent_run_lease_prevents_duplicate_worker_and_allows_expiry_takeover(task_session):
    user = await _user(task_session, 712, "agent-lease")
    service = AgentRuntimeService(task_session)
    session = await service.create_session(user_id=user.id)
    run = await service.create_run(session_id=session.id, user_id=user.id)
    claimed = await service.claim_run(run_id=run.id, user_id=user.id, lease_owner="worker-a", lease_seconds=60)
    assert claimed.lease_owner == "worker-a"
    with pytest.raises(AgentConflict):
        await service.claim_run(run_id=run.id, user_id=user.id, lease_owner="worker-b", lease_seconds=60)
    claimed.lease_expires_at = service._now() - __import__("datetime").timedelta(seconds=1)
    await task_session.commit()
    taken = await service.claim_run(run_id=run.id, user_id=user.id, lease_owner="worker-b", lease_seconds=60)
    assert taken.lease_owner == "worker-b"
    released = await service.release_run(run_id=run.id, user_id=user.id, lease_owner="worker-b")
    assert released.lease_owner is None


@pytest.mark.asyncio
async def test_cancel_request_is_durable_and_visible_to_other_worker(task_session):
    user = await _user(task_session, 720, "agent-durable-cancel")
    service = AgentRuntimeService(task_session)
    agent_session = await service.create_session(user_id=user.id)
    run = await service.create_run(session_id=agent_session.id, user_id=user.id)
    cancelled = await service.cancel_run(run_id=run.id, user_id=user.id, reason="browser_stop")
    assert cancelled.status == "cancelled"
    assert cancelled.cancel_requested_at is not None
    assert cancelled.cancel_reason == "browser_stop"
    other_session = AgentRuntimeService(task_session)
    assert await other_session.is_cancel_requested(run_id=run.id, user_id=user.id) is True


@pytest.mark.asyncio
async def test_stale_run_reconcile_moves_expired_run_to_recovery_ready(task_session):
    user = await _user(task_session, 721, "agent-stale-run")
    service = AgentRuntimeService(task_session)
    agent_session = await service.create_session(user_id=user.id)
    run = await service.create_run(session_id=agent_session.id, user_id=user.id)
    await service.update_run(run_id=run.id, user_id=user.id, status="running", phase="tool_execution", progress=30)
    run.lease_owner = "dead-worker"
    run.lease_expires_at = service._now() - __import__("datetime").timedelta(seconds=1)
    await task_session.commit()
    recovered = await service.reconcile_stale_runs()
    assert recovered == [run.id]
    saved = await service.get_run(run.id, user.id)
    assert saved.status == "paused"
    assert saved.current_phase == "recovery_ready"
    assert saved.lease_owner is None
    events = await service.list_events(run_id=run.id, user_id=user.id)
    assert any(item.event_type == "run_recovery_ready" for item in events)


@pytest.mark.asyncio
async def test_run_binds_immutable_catalog_release_and_resolver_snapshot(task_session):
    user = await _user(task_session, 800, "agent-catalog-binding")
    task_session.add(NovelProject(id="agent-catalog-project", user_id=user.id, title="Catalog Project"))
    await task_session.flush()
    service = AgentRuntimeService(task_session)
    session = await service.create_session(user_id=user.id, project_id="agent-catalog-project")
    run = await service.create_run(
        session_id=session.id,
        user_id=user.id,
        project_id="agent-catalog-project",
        context={"requested_tools": ["project.context"]},
    )

    release = run.context_json["catalog_release"]
    resolution = run.context_json["capability_resolution"]
    assert release["release_id"] == run.context_json["catalog_release_id"]
    assert resolution["snapshot_id"] == run.context_json["capability_resolution_id"]
    assert resolution["release_id"] == release["release_id"]
    assert resolution["tools"] and [item["name"] for item in resolution["tools"]] == ["project.context"]
    assert resolution["digest"]

    await service.set_run_context(
        run_id=run.id,
        user_id=user.id,
        context={"goal": "继续", "requested_tools": ["chapter.generate"]},
    )
    assert run.context_json["catalog_release"]["digest"] == release["digest"]
    assert run.context_json["capability_resolution"]["snapshot_id"] == resolution["snapshot_id"]


@pytest.mark.asyncio
async def test_run_capability_snapshot_is_persisted_and_not_overwritten(task_session):
    user = await _user(task_session, 799, "agent-snapshot")
    service = AgentRuntimeService(task_session)
    session = await service.create_session(user_id=user.id)
    run = await service.create_run(session_id=session.id, user_id=user.id)
    snapshot = run.context_json["capability_snapshot"]
    assert snapshot["generation"] >= 1
    assert any(item["name"] == "project.context" for item in snapshot["tools"])
    await service.set_run_context(run_id=run.id, user_id=user.id, context={"capability_snapshot": {"generation": 999}, "safe": "ok"})
    assert run.context_json["capability_snapshot"] == snapshot
    assert run.context_json["safe"] == "ok"


@pytest.mark.asyncio
async def test_public_work_summary_is_bounded_durable_and_updates_the_run_checkpoint(task_session):
    from pydantic import ValidationError

    user = await _user(task_session, 715, "agent-public-summary")
    service = AgentRuntimeService(task_session)
    session = await service.create_session(user_id=user.id, project_id=None)
    run = await service.create_run(session_id=session.id, user_id=user.id)

    event = await service.append_public_work_summary(
        run_id=run.id,
        user_id=user.id,
        summary={
            "action_id": "plan-step-1",
            "phase": "planning",
            "current_action": "正在读取当前项目的章节结构。",
            "completed_action": "已确认项目上下文。",
            "input_scope": [
                {"kind": "project"},
                {"kind": "chapter_version", "chapter_number": 3, "version_id": 12},
            ],
            "selected_capability": "chapter.version.list",
            "decision_summary": "先读取版本元数据，再判断是否需要质量检查。",
            "next_action": "读取最近版本。",
            "expected_output": "版本摘要。",
            "step_order": 1,
            "revision": 0,
        },
    )
    saved = await service.get_run(run.id, user.id)

    assert event.event_type == "public_work_summary"
    assert event.data_json["input_scope_kinds"] == ["project", "chapter_version"]
    assert event.data_json["input_scope_count"] == 2
    assert "input_scope" not in event.data_json
    assert saved.latest_public_summary_sequence == event.sequence
    assert saved.latest_public_summary_json == {
        "action_id": "plan-step-1",
        "phase": "planning",
        "current_action": "正在读取当前项目的章节结构。",
        "completed_action": "已确认项目上下文。",
        "input_scope": [
            {"kind": "project", "project_id": None, "chapter_number": None, "version_id": None, "artifact_id": None},
            {"kind": "chapter_version", "project_id": None, "chapter_number": 3, "version_id": 12, "artifact_id": None},
        ],
        "selected_capability": "chapter.version.list",
        "decision_summary": "先读取版本元数据，再判断是否需要质量检查。",
        "next_action": "读取最近版本。",
        "expected_output": "版本摘要。",
        "step_order": 1,
        "revision": 0,
    }

    with pytest.raises(ValidationError):
        await service.append_public_work_summary(
            run_id=run.id,
            user_id=user.id,
            summary={
                "action_id": "bad",
                "phase": "planning",
                "current_action": "错误摘要",
                "reasoning": "must never become public activity",
            },
        )

@pytest.mark.asyncio
async def test_public_work_summary_retries_sequence_conflict_without_partial_checkpoint(task_session, monkeypatch):
    user = await _user(task_session, 752, "agent-public-summary-retry")
    service = AgentRuntimeService(task_session)
    agent_session = await service.create_session(user_id=user.id)
    run = await service.create_run(session_id=agent_session.id, user_id=user.id)

    run_id = run.id
    user_id = user.id
    original_commit = task_session.commit
    attempts = 0

    async def conflict_once():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise IntegrityError(
                "INSERT INTO agent_events",
                {},
                Exception("UNIQUE constraint failed: agent_events.run_id, agent_events.sequence"),
            )
        await original_commit()

    monkeypatch.setattr(task_session, "commit", conflict_once)

    event = await service.append_public_work_summary(
        run_id=run_id,
        user_id=user_id,
        summary={
            "action_id": "retry:public-summary",
            "phase": "planning",
            "current_action": "正在在冲突重试后恢复公开工作摘要。",
            "input_scope": [{"kind": "project"}],
            "selected_capability": "project.context",
            "revision": 2,
        },
    )

    saved = await service.get_run(run_id, user_id)
    events = await service.list_events(run_id=run_id, user_id=user_id, after_sequence=0)

    assert attempts == 2
    assert [(item.sequence, item.event_type) for item in events] == [(1, "public_work_summary")]
    assert event.sequence == 1
    assert saved.latest_public_summary_sequence == event.sequence
    assert saved.latest_public_summary_json["current_action"] == "正在在冲突重试后恢复公开工作摘要。"
    assert saved.latest_public_summary_json["revision"] == 2

@pytest.mark.asyncio
async def test_list_events_caps_large_activity_page_at_five_hundred(task_session):
    user = await _user(task_session, 753, "agent-activity-cap")
    service = AgentRuntimeService(task_session)
    agent_session = await service.create_session(user_id=user.id)
    run = await service.create_run(session_id=agent_session.id, user_id=user.id)

    task_session.add_all(
        [
            AgentEventRecord(
                id=f"activity-cap-{sequence:04d}",
                run_id=run.id,
                correlation_id=run.correlation_id,
                user_id=user.id,
                event_type="planner_started",
                sequence=sequence,
                summary=f"event {sequence}",
                data_json={"phase": "planning"},
            )
            for sequence in range(1, 502)
        ]
    )
    run.event_sequence = 501
    await task_session.commit()

    page = await service.list_events(run_id=run.id, user_id=user.id, after_sequence=0, limit=999)

    assert len(page) == 500
    assert page[0].sequence == 1
    assert page[-1].sequence == 500
    assert [item.sequence for item in page] == list(range(1, 501))

@pytest.mark.asyncio
async def test_public_work_summary_redacts_marker_shaped_private_values_before_storage(task_session):
    user = await _user(task_session, 754, "agent-public-summary-redaction")
    service = AgentRuntimeService(task_session)
    agent_session = await service.create_session(user_id=user.id)
    run = await service.create_run(session_id=agent_session.id, user_id=user.id)

    event = await service.append_public_work_summary(
        run_id=run.id,
        user_id=user.id,
        summary={
            "action_id": "redaction:summary",
            "phase": "planning",
            "current_action": "正在整理计划。 api_key=SUPER_SECRET_VALUE_12345",
            "completed_action": "reasoning: hidden private chain",
            "decision_summary": "<analysis>hidden planning detail</analysis>",
            "next_action": "Bearer abcdefghijklmnopqrstuvwxyz",
            "expected_output": "raw_response: provider prose that must not persist",
            "input_scope": [{"kind": "project"}],
        },
    )
    saved = await service.get_run(run.id, user.id)

    serialized = "\n".join(
        str(value)
        for value in [
            event.summary,
            *event.data_json.values(),
            *saved.latest_public_summary_json.values(),
        ]
    )
    assert "[已脱敏]" in serialized
    for private_value in (
        "SUPER_SECRET_VALUE_12345",
        "hidden private chain",
        "hidden planning detail",
        "abcdefghijklmnopqrstuvwxyz",
        "provider prose that must not persist",
    ):
        assert private_value not in serialized
    assert event.data_json["current_action"] == "正在整理计划。 [已脱敏]"
    assert saved.latest_public_summary_json["next_action"] == "[已脱敏]"



@pytest.mark.asyncio
async def test_run_command_idempotency_replays_the_same_command_and_rejects_payload_mismatch(task_session):
    user = await _user(task_session, 761, "agent-command-idempotency")
    service = AgentRuntimeService(task_session)
    agent_session = await service.create_session(user_id=user.id)
    run = await service.create_run(session_id=agent_session.id, user_id=user.id)
    running = await service.update_run(
        run_id=run.id,
        user_id=user.id,
        status="running",
        phase="tool_execution",
    )
    expected_version = int(running.state_version or 0)

    first = await service.submit_run_command(
        run_id=run.id,
        user_id=user.id,
        command_type="pause",
        reason="作者检查计划",
        payload={"source": "chat"},
        idempotency_key="chat:pause:761",
        expected_state_version=expected_version,
    )
    replay = await service.submit_run_command(
        run_id=run.id,
        user_id=user.id,
        command_type="pause",
        reason="作者检查计划",
        payload={"source": "chat"},
        idempotency_key="chat:pause:761",
        expected_state_version=expected_version,
    )

    assert first.status == "applied"
    assert replay.id == first.id
    assert replay.payload_hash == first.payload_hash
    assert len(await service.list_run_commands(run_id=run.id, user_id=user.id)) == 1

    with pytest.raises(AgentConflict, match="idempotency key"):
        await service.submit_run_command(
            run_id=run.id,
            user_id=user.id,
            command_type="pause",
            reason="作者检查计划",
            payload={"source": "different"},
            idempotency_key="chat:pause:761",
            expected_state_version=expected_version,
        )


@pytest.mark.asyncio
async def test_run_command_rejects_stale_state_version_without_mutating_run(task_session):
    user = await _user(task_session, 762, "agent-command-stale")
    service = AgentRuntimeService(task_session)
    agent_session = await service.create_session(user_id=user.id)
    run = await service.create_run(session_id=agent_session.id, user_id=user.id)
    current = await service.update_run(
        run_id=run.id,
        user_id=user.id,
        status="running",
        phase="tool_execution",
    )
    stale_version = max(0, int(current.state_version or 0) - 1)

    command = await service.submit_run_command(
        run_id=run.id,
        user_id=user.id,
        command_type="pause",
        idempotency_key="chat:stale:762",
        expected_state_version=stale_version,
    )
    saved = await service.get_run(run.id, user.id)

    assert command.status == "rejected"
    assert command.error_type == "AgentStateVersionConflict"
    assert saved.status == "running"
    assert saved.state_version == current.state_version


@pytest.mark.asyncio
async def test_late_progress_cannot_revive_a_user_paused_run(task_session):
    user = await _user(task_session, 763, "agent-progress-pause")
    service = AgentRuntimeService(task_session)
    agent_session = await service.create_session(user_id=user.id)
    run = await service.create_run(session_id=agent_session.id, user_id=user.id)
    await service.update_run(run_id=run.id, user_id=user.id, status="running", phase="tool_execution")
    paused = await service.pause_run(run_id=run.id, user_id=user.id)
    paused_version = int(paused.state_version or 0)

    late = await service.publish_progress(
        run_id=run.id,
        user_id=user.id,
        status="running",
        phase="late_worker_progress",
        progress=80,
        progress_message="迟到 Worker 仍在上报进度。",
    )

    assert late.status == "paused"
    assert late.pause_reason == "user"
    assert late.state_version == paused_version
    assert late.progress >= paused.progress


@pytest.mark.asyncio
async def test_step_lease_generation_fences_old_completion_after_reclaim(task_session):
    user = await _user(task_session, 798, "step-generation-fence")
    runtime = AgentRuntimeService(task_session)
    session = await runtime.create_session(user_id=user.id)
    run = await runtime.create_run(session_id=session.id, user_id=user.id)
    step = await runtime.ensure_step(run_id=run.id, user_id=user.id, step_order=1, tool_name="project.list", idempotency_key="step-generation")
    first = await runtime.claim_step(step_id=step.id, user_id=user.id, lease_owner="reused-step-owner", lease_seconds=60)
    first_generation = int(first.lease_generation or 0)
    first.lease_expires_at = runtime._now() - __import__("datetime").timedelta(seconds=1)
    await task_session.commit()
    second = await runtime.claim_step(step_id=step.id, user_id=user.id, lease_owner="reused-step-owner", lease_seconds=60)
    assert second.lease_generation == first_generation + 1
    with pytest.raises(AgentConflict, match="generation"):
        await runtime.complete_step(step_id=step.id, user_id=user.id, lease_owner="reused-step-owner", lease_generation=first_generation, output={"late": True})


@pytest.mark.asyncio
async def test_provider_provenance_is_stage_scoped_and_public_events_are_allowlisted(task_session):
    user = await _user(task_session, 729, "agent-provider-provenance")
    service = AgentRuntimeService(task_session)
    session = await service.create_session(user_id=user.id)
    run = await service.create_run(session_id=session.id, user_id=user.id)

    saved = await service.update_run_provider_provenance(
        run_id=run.id,
        user_id=user.id,
        updates={
            "planner_provider_called": True,
            "planner_provider_fallback_reason": None,
            "response_provider_called": False,
            "response_provider_fallback_reason": "empty_response",
            "candidate_writer_provider_called": True,
            "candidate_writer_provider_fallback_reason": None,
            "candidate_writer_model_ref": "fixture-model",
        },
    )
    assert saved.context_json["planner_provider_called"] is True
    assert saved.context_json["response_provider_called"] is False
    assert saved.context_json["response_provider_fallback_reason"] == "empty_response"
    assert saved.context_json["candidate_writer_provider_called"] is True
    assert saved.context_json["candidate_writer_model_ref"] == "fixture-model"

    planner_event = await service.append_event(
        run_id=run.id,
        user_id=user.id,
        event_type="assistant_queued",
        summary="queued",
        data={
            "phase": "assistant_response",
            "planner_provider_called": True,
            "planner_provider_fallback_reason": None,
            "response_provider_called": True,
            "reasoning": "private",
        },
    )
    assert planner_event.data_json == {
        "phase": "assistant_response",
        "planner_provider_called": True,
        "planner_provider_fallback_reason": None,
    }
    response_event = await service.append_event(
        run_id=run.id,
        user_id=user.id,
        event_type="run_completed",
        summary="completed",
        data={
            "phase": "summary",
            "response_provider_called": True,
            "response_provider_fallback_reason": None,
            "provider_secret": "must-not-persist",
        },
    )
    assert response_event.data_json == {
        "phase": "summary",
        "response_provider_called": True,
        "response_provider_fallback_reason": None,
    }
    with pytest.raises(AgentConflict, match="unknown provider provenance"):
        await service.update_run_provider_provenance(
            run_id=run.id,
            user_id=user.id,
            updates={"reasoning": "private"},
        )


@pytest.mark.asyncio
async def test_project_run_initial_snapshot_contains_bounded_novel_selection(task_session):
    user = await _user(task_session, 799, "agent-novel-snapshot")
    from app.models.novel import Chapter, ChapterOutline, ChapterVersion, NovelBlueprint
    from app.models.agent_context import ContextSnapshot
    from sqlalchemy import select

    project = NovelProject(id="agent-novel-snapshot", user_id=user.id, title="十万字项目")
    project.blueprint = NovelBlueprint(
        project_id=project.id,
        title="十万字项目",
        world_setting={"novel_outline": [{"stage": 1, "title": "第一段", "expected_chapter_range": "1-2章"}]},
    )
    project.outlines = [
        ChapterOutline(project_id=project.id, chapter_number=1, title="第一章", summary="开端", metadata={"volume_number": 1}),
        ChapterOutline(project_id=project.id, chapter_number=2, title="第二章", summary="承接", metadata={"volume_number": 1}),
    ]
    first = Chapter(project_id=project.id, chapter_number=1, status="successful")
    second = Chapter(project_id=project.id, chapter_number=2, status="successful")
    project.chapters = [first, second]
    task_session.add(project)
    await task_session.flush()
    selected = ChapterVersion(chapter_id=first.id, content="第一章正文", status="candidate")
    task_session.add(selected)
    await task_session.flush()
    first.selected_version_id = selected.id
    await task_session.commit()

    service = AgentRuntimeService(task_session)
    agent_session = await service.create_session(user_id=user.id, project_id=project.id)
    run = await service.create_run(
        session_id=agent_session.id,
        user_id=user.id,
        project_id=project.id,
        context={"target_chapter": 1, "max_context_text_units": 100},
    )
    snapshot = (await task_session.execute(select(ContextSnapshot).where(ContextSnapshot.run_id == run.id))).scalar_one()
    assert snapshot.project_id == project.id
    assert snapshot.context_json["novel_context_selection"]["target_chapter"] == 1
    assert snapshot.context_json["novel_context_selection"]["estimated_text_units"] <= 100
    assert any(ref.ref_type == "chapter_version" for ref in snapshot.refs)
    await service.get_run(run.id, user.id)
