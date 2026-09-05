"""Backward-compatible pagination contracts for Agent Run history collections."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.api.routers import agent
from app.agent.schemas import (
    AgentArtifactPageRead,
    AgentRunCommandPageRead,
    AgentRunStepPageRead,
)
from app.models import (
    AgentArtifactRef,
    AgentRunCommand,
    NovelProject,
    ProjectMember,
    User,
)
from app.models.project_member import ProjectMemberRole
from app.services.agent_runtime import AgentRuntimeService


async def _seed(task_session):
    owner = User(
        id=97801,
        username="agent-page-owner",
        email="agent-page-owner@example.com",
        hashed_password="x",
        is_active=True,
    )
    project = NovelProject(id="agent-page-project", user_id=owner.id, title="Agent 分页项目")
    task_session.add_all(
        [
            owner,
            project,
            ProjectMember(
                project_id=project.id,
                user_id=owner.id,
                role=ProjectMemberRole.owner.value,
            ),
        ]
    )
    await task_session.commit()

    runtime = AgentRuntimeService(task_session)
    session = await runtime.create_session(user_id=owner.id, project_id=project.id)
    run = await runtime.create_run(
        session_id=session.id,
        user_id=owner.id,
        project_id=project.id,
    )
    for step_order in range(1, 4):
        await runtime.ensure_step(
            run_id=run.id,
            user_id=owner.id,
            step_order=step_order,
            tool_name=f"fixture.tool.{step_order}",
            idempotency_key=f"fixture-step-{step_order}",
        )

    base_time = datetime.now(timezone.utc)
    for index in range(3):
        task_session.add(
            AgentRunCommand(
                id=f"fixture-command-{index + 1}",
                run_id=run.id,
                correlation_id=run.correlation_id,
                transaction_id=run.transaction_id,
                user_id=owner.id,
                command_type="pause",
                status="requested",
                idempotency_key=f"fixture-command-key-{index + 1}",
                payload_hash="",
                payload_json={},
                result_json={},
                requested_at=base_time + timedelta(seconds=index),
            )
        )
    await task_session.commit()

    for index in range(3):
        await runtime.add_artifact(
            run_id=run.id,
            user_id=owner.id,
            project_id=project.id,
            kind="fixture",
            uri=f"memory://agent-page-{index + 1}",
            metadata={"index": index + 1},
        )
    return SimpleNamespace(owner=owner, run=run)


@pytest.mark.asyncio
async def test_default_history_routes_keep_returning_lists(task_session):
    fixture = await _seed(task_session)
    principal = SimpleNamespace(id=fixture.owner.id)

    steps = await agent.list_agent_run_steps(fixture.run.id, session=task_session, current_user=principal)
    commands = await agent.list_agent_run_commands(fixture.run.id, session=task_session, current_user=principal)
    artifacts = await agent.list_agent_artifacts(fixture.run.id, session=task_session, current_user=principal)

    assert isinstance(steps, list)
    assert isinstance(commands, list)
    assert isinstance(artifacts, list)
    assert len(steps) == len(commands) == len(artifacts) == 3


@pytest.mark.asyncio
async def test_explicit_offset_returns_typed_pages_with_total_and_cursor(task_session):
    fixture = await _seed(task_session)
    principal = SimpleNamespace(id=fixture.owner.id)

    steps = await agent.list_agent_run_steps(
        fixture.run.id, limit=2, offset=0, session=task_session, current_user=principal
    )
    commands = await agent.list_agent_run_commands(
        fixture.run.id, limit=2, offset=1, session=task_session, current_user=principal
    )
    artifacts = await agent.list_agent_artifacts(
        fixture.run.id, limit=2, offset=2, session=task_session, current_user=principal
    )

    assert isinstance(steps, AgentRunStepPageRead)
    assert steps.run_id == fixture.run.id
    assert steps.total == 3
    assert steps.limit == 2
    assert steps.offset == 0
    assert [item.step_order for item in steps.items] == [1, 2]
    assert steps.has_more is True
    assert steps.next_offset == 2

    assert isinstance(commands, AgentRunCommandPageRead)
    assert commands.total == 3
    assert commands.offset == 1
    assert [item.id for item in commands.items] == ["fixture-command-2", "fixture-command-3"]
    assert commands.has_more is False
    assert commands.next_offset is None

    assert isinstance(artifacts, AgentArtifactPageRead)
    assert artifacts.total == 3
    assert artifacts.offset == 2
    assert len(artifacts.items) == 1
    assert artifacts.has_more is False
    assert artifacts.next_offset is None


@pytest.mark.asyncio
async def test_page_methods_keep_read_scope_and_empty_tail(task_session):
    fixture = await _seed(task_session)
    principal = SimpleNamespace(id=fixture.owner.id)
    runtime = AgentRuntimeService(task_session)

    steps, total = await runtime.list_steps_readable_page(
        run_id=fixture.run.id, user_id=fixture.owner.id, limit=2, offset=99
    )
    commands, command_total = await runtime.list_run_commands_readable_page(
        run_id=fixture.run.id, user_id=fixture.owner.id, limit=2, offset=99
    )
    artifacts, artifact_total = await runtime.list_artifacts_readable_page(
        run_id=fixture.run.id, user_id=fixture.owner.id, limit=2, offset=99
    )

    assert steps == [] and total == 3
    assert commands == [] and command_total == 3
    assert artifacts == [] and artifact_total == 3

    # The route remains readable through the same existing scope gate.
    page = await agent.list_agent_run_steps(
        fixture.run.id, limit=2, offset=99, session=task_session, current_user=principal
    )
    assert page.total == 3
    assert page.items == []
    assert page.has_more is False
