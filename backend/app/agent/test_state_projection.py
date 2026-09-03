from __future__ import annotations

from copy import deepcopy

import pytest

from app.agent.jobs import AgentJobService
from app.agent.registry import get_default_tool_registry_snapshot
from app.agent.state_projection import AgentStateProjectionService
from app.models import User
from app.services.agent_runtime import AgentRuntimeService
from app.services.task_runtime import TaskRuntimeService


async def _user(session, user_id: int, name: str) -> User:
    item = User(id=user_id, username=name, email=f"{name}@example.com", hashed_password="x", is_active=True)
    session.add(item)
    await session.flush()
    return item


@pytest.mark.asyncio
async def test_state_projection_inherits_one_run_correlation_and_excludes_foreign_task(task_session):
    owner = await _user(task_session, 1801, "projection-owner")
    other = await _user(task_session, 1802, "projection-other")
    runtime = AgentRuntimeService(task_session)
    session = await runtime.create_session(user_id=owner.id)
    run = await runtime.create_run(session_id=session.id, user_id=owner.id)
    step = await runtime.ensure_step(run_id=run.id, user_id=owner.id, step_order=1, tool_name="chapter.generate", idempotency_key="projection-step")
    approval = await runtime.request_approval(run_id=run.id, user_id=owner.id, step_id=step.id, tool_name="chapter.generate", project_id=None)
    artifact = await runtime.add_artifact(run_id=run.id, user_id=owner.id, project_id=None, kind="chapter_candidate", uri="agent://safe", metadata={"accepted_version_id": 9, "acceptance_approval_id": approval.id, "content": "must not project"})
    event = await runtime.append_event(run_id=run.id, user_id=owner.id, event_type="tool_call_progress", summary="working", data={"progress": 20})
    job = await AgentJobService(task_session).create_job(run_id=run.id, user_id=owner.id, project_id=None, kind="visible_response", idempotency_key="projection-job")
    task = await TaskRuntimeService(task_session).create_task(task_type="chapter_generation", owner_user_id=owner.id, correlation_id=run.correlation_id)
    foreign_task = await TaskRuntimeService(task_session).create_task(task_type="chapter_generation", owner_user_id=other.id, correlation_id=run.correlation_id)

    projection = await AgentStateProjectionService(task_session).get_run_state(run_id=run.id, user_id=owner.id)

    assert run.correlation_id and run.correlation_id != run.id
    assert step.correlation_id == approval.correlation_id == artifact.correlation_id == event.correlation_id == job.correlation_id == run.correlation_id
    assert task.correlation_id == run.correlation_id
    assert projection["correlation_id"] == run.correlation_id
    assert projection["last_event_sequence"] == event.sequence
    assert projection["accepted_version_ids"] == [9]
    assert projection["steps"] == [{"id": step.id, "order": 1, "tool_name": "chapter.generate", "status": "pending", "attempt_count": 0}]
    assert projection["approvals"][0]["id"] == approval.id
    assert projection["artifacts"] == [{"id": artifact.id, "kind": "chapter_candidate", "created_at": artifact.created_at, "accepted_version_id": 9, "acceptance_approval_id": approval.id}]
    assert projection["jobs"][0]["id"] == job.id
    assert projection["task_runtime_refs"] == [{"task_id": task.task_id, "task_type": "chapter_generation", "status": "queued", "stage": None, "progress": 0.0}]
    assert foreign_task.task_id not in {item["task_id"] for item in projection["task_runtime_refs"]}
    assert "content" not in projection["artifacts"][0]
    assert isinstance(projection["capability_snapshot"]["generation"], int)
    assert projection["capability_snapshot"]["generation"] >= 1
    assert any(item["name"] == "project.context" for item in projection["capability_snapshot"]["tools"])


@pytest.mark.asyncio
async def test_state_projection_rejects_other_users_run(task_session):
    owner = await _user(task_session, 1803, "projection-owner-two")
    other = await _user(task_session, 1804, "projection-other-two")
    runtime = AgentRuntimeService(task_session)
    session = await runtime.create_session(user_id=owner.id)
    run = await runtime.create_run(session_id=session.id, user_id=owner.id)
    from app.services.agent_runtime import AgentNotFound
    with pytest.raises(AgentNotFound):
        await AgentStateProjectionService(task_session).get_run_state(run_id=run.id, user_id=other.id)


@pytest.mark.asyncio
async def test_state_projection_exposes_generation_from_the_run_capability_snapshot(task_session):
    user = await _user(task_session, 1805, "projection-generation")
    runtime = AgentRuntimeService(task_session)
    session = await runtime.create_session(user_id=user.id)
    run = await runtime.create_run(session_id=session.id, user_id=user.id)

    expected = get_default_tool_registry_snapshot()
    projection = await AgentStateProjectionService(task_session).get_run_state(run_id=run.id, user_id=user.id)

    assert projection["capability_snapshot"]["generation"] == expected["generation"]
    assert projection["capability_snapshot"]["providers"] == expected["providers"]
    assert projection["capability_snapshot"]["tools"] == expected["tools"]


@pytest.mark.asyncio
async def test_run_capability_snapshot_cannot_be_overwritten_by_later_context(task_session):
    user = await _user(task_session, 1806, "projection-snapshot-immutable")
    runtime = AgentRuntimeService(task_session)
    session = await runtime.create_session(user_id=user.id)
    run = await runtime.create_run(session_id=session.id, user_id=user.id)
    original_snapshot = deepcopy(run.context_json["capability_snapshot"])

    await runtime.set_run_context(
        run_id=run.id,
        user_id=user.id,
        context={"capability_snapshot": {"generation": -1, "tools": []}, "checkpoint": "saved"},
    )
    projection = await AgentStateProjectionService(task_session).get_run_state(run_id=run.id, user_id=user.id)

    assert run.context_json["capability_snapshot"] == original_snapshot
    assert run.context_json["checkpoint"] == "saved"
    assert projection["capability_snapshot"] == original_snapshot


@pytest.mark.asyncio
async def test_old_run_reuses_original_snapshot_when_registry_generation_changes(task_session, monkeypatch):
    user = await _user(task_session, 1807, "projection-old-run")
    runtime = AgentRuntimeService(task_session)
    session = await runtime.create_session(user_id=user.id)
    old_run = await runtime.create_run(session_id=session.id, user_id=user.id)
    old_snapshot = deepcopy(old_run.context_json["capability_snapshot"])

    new_snapshot = deepcopy(old_snapshot)
    new_snapshot["generation"] = old_snapshot["generation"] + 1
    monkeypatch.setattr("app.agent.registry.get_default_tool_registry_snapshot", lambda: deepcopy(new_snapshot))

    await runtime.set_run_context(run_id=old_run.id, user_id=user.id, context={"checkpoint": "resume-old-run"})
    new_run = await runtime.create_run(session_id=session.id, user_id=user.id)
    old_projection = await AgentStateProjectionService(task_session).get_run_state(run_id=old_run.id, user_id=user.id)
    new_projection = await AgentStateProjectionService(task_session).get_run_state(run_id=new_run.id, user_id=user.id)

    assert old_run.context_json["capability_snapshot"] == old_snapshot
    assert old_projection["capability_snapshot"] == old_snapshot
    assert new_run.context_json["capability_snapshot"] == new_snapshot
    assert new_projection["capability_snapshot"] == new_snapshot
    assert old_projection["capability_snapshot"]["generation"] != new_projection["capability_snapshot"]["generation"]


@pytest.mark.asyncio
async def test_state_projection_reads_latest_public_summary_checkpoint_without_event_scan(task_session):
    user = await _user(task_session, 1806, "projection-public-summary")
    runtime = AgentRuntimeService(task_session)
    session = await runtime.create_session(user_id=user.id)
    run = await runtime.create_run(session_id=session.id, user_id=user.id)
    event = await runtime.append_public_work_summary(
        run_id=run.id,
        user_id=user.id,
        summary={
            "action_id": "tool-2",
            "phase": "tool_execution",
            "current_action": "正在核查伏笔状态。",
            "input_scope": [{"kind": "chapter", "chapter_number": 4}],
            "selected_capability": "foreshadowing.inspect",
            "next_action": "整理发现。",
        },
    )

    projection = await AgentStateProjectionService(task_session).get_run_state(run_id=run.id, user_id=user.id)

    assert projection["last_event_sequence"] == event.sequence
    assert projection["latest_public_summary_sequence"] == event.sequence
    assert projection["latest_public_summary_at"] is not None
    assert projection["latest_public_summary"] == {
        "action_id": "tool-2",
        "phase": "tool_execution",
        "current_action": "正在核查伏笔状态。",
        "completed_action": None,
        "input_scope": [{"kind": "chapter", "project_id": None, "chapter_number": 4, "version_id": None, "artifact_id": None}],
        "selected_capability": "foreshadowing.inspect",
        "decision_summary": None,
        "next_action": "整理发现。",
        "expected_output": None,
        "step_order": None,
        "revision": 0,
    }

@pytest.mark.asyncio
async def test_state_projection_exposes_command_fences_and_server_allowed_commands(task_session):
    user = await _user(task_session, 1810, "projection-command-fences")
    runtime = AgentRuntimeService(task_session)
    session = await runtime.create_session(user_id=user.id)
    run = await runtime.create_run(session_id=session.id, user_id=user.id)
    running = await runtime.update_run(
        run_id=run.id,
        user_id=user.id,
        status="running",
        phase="tool_execution",
    )
    expected_state_version = int(running.state_version or 0)
    command = await runtime.submit_run_command(
        run_id=run.id,
        user_id=user.id,
        command_type="pause",
        idempotency_key="projection:pause:1810",
        expected_state_version=expected_state_version,
    )

    projection = await AgentStateProjectionService(task_session).get_run_state(
        run_id=run.id,
        user_id=user.id,
    )

    assert projection["status"] == "paused"
    assert projection["pause_reason"] == "user"
    assert projection["resume_target_status"] == "running"
    assert projection["state_version"] > expected_state_version
    assert projection["allowed_commands"] == ["resume", "cancel"]
    assert projection["active_command"] is None
    assert projection["commands"] == [
        {
            **projection["commands"][0],
            "id": command.id,
            "command_type": "pause",
            "status": "applied",
            "idempotency_key": "projection:pause:1810",
            "expected_state_version": expected_state_version,
        }
    ]



@pytest.mark.asyncio
async def test_public_summary_keeps_run_state_projection_in_sync(task_session):
    user = await _user(task_session, 1811, "projection-summary-state-sync")
    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=user.id)
    run = await runtime.create_run(session_id=agent_session.id, user_id=user.id)
    before_version = int(run.state_version or 0)

    await runtime.append_public_work_summary(
        run_id=run.id,
        user_id=user.id,
        summary={
            "action_id": "tool:state-sync",
            "phase": "tool_execution",
            "current_action": "正在执行状态同步测试。",
            "input_scope": [{"kind": "project"}],
            "selected_capability": "project.context",
            "step_order": 3,
        },
    )

    projection = await AgentStateProjectionService(task_session).get_run_state(run_id=run.id, user_id=user.id)

    assert projection["phase"] == "tool_execution"
    assert projection["current_step"] == 3
    assert projection["state_version"] == before_version + 1
    assert projection["latest_public_summary"]["phase"] == projection["phase"]
    assert projection["latest_public_summary"]["step_order"] == projection["current_step"]

@pytest.mark.asyncio
async def test_state_projection_exposes_explicit_resume_cursor(task_session):
    user = await _user(task_session, 1816, "projection-resume-cursor")
    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=user.id)
    run = await runtime.create_run(session_id=agent_session.id, user_id=user.id)
    event = await runtime.append_event(
        run_id=run.id,
        user_id=user.id,
        event_type="run_started",
        summary="开始运行",
        data={"phase": "observe"},
    )

    projection = await AgentStateProjectionService(task_session).get_run_state(run_id=run.id, user_id=user.id)

    assert projection["resume_after_sequence"] == event.sequence
    assert projection["resume_after_sequence"] == projection["last_event_sequence"]