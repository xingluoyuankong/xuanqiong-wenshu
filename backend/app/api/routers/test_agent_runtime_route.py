from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.agent.context_refs import ContextRefValidationError
from app.agent.execution import execute_agent_execution_job
from app.agent.executor import build_agent_plan
from app.agent.jobs import AgentJobService
from app.agent.schemas import AgentMessageCreateRequest, AgentPlanRequest, AgentRunCommandRequest, AgentSessionCreateRequest
from app.api.routers.agent import create_agent_session, list_agent_project_entity_summaries, get_agent_run_plan, get_agent_run_provider_provenance, get_agent_run_state, get_agent_session, list_agent_dead_letters, list_agent_jobs, list_agent_run_steps, list_agent_run_activity, list_agent_run_commands, post_agent_message, replay_agent_dead_letter, submit_agent_run_command
from app.models import Chapter, ChapterVersion, NovelProject, User
from app.models.faction import Faction
from app.models.foreshadowing import Foreshadowing
from app.models.knowledge_graph import CharacterNode
from app.models.novel import BlueprintCharacter
from app.models.research import ResearchArtifact
from app.services.agent_runtime import AgentRuntimeService
from app.services.agent_context_service import AgentContextService
from app.services.agent_plan_service import AgentPlanService


async def _route_user(session, user_id: int, name: str) -> User:
    user = User(id=user_id, username=name, email=f"{name}@example.com", hashed_password="x", is_active=True)
    session.add(user)
    await session.flush()
    return user


@pytest.fixture(autouse=True)
def _disable_inline_execution_for_route_unit_tests(monkeypatch):
    """Route tests assert the durable enqueue boundary without background DB work."""
    monkeypatch.setattr("app.api.routers.agent.launch_agent_execution", lambda **kwargs: None)



@pytest.mark.asyncio
async def test_agent_session_route_enforces_project_ownership(task_session):
    owner = await _route_user(task_session, 1001, "route-owner")
    other = await _route_user(task_session, 1002, "route-other")
    task_session.add(NovelProject(id="route-project", user_id=owner.id, title="Route Project"))
    await task_session.flush()
    created = await create_agent_session(AgentSessionCreateRequest(project_id="route-project"), session=task_session, current_user=SimpleNamespace(id=owner.id))
    assert created.project_id == "route-project"
    with pytest.raises(HTTPException) as error:
        await create_agent_session(AgentSessionCreateRequest(project_id="route-project"), session=task_session, current_user=SimpleNamespace(id=other.id))
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_agent_project_entity_summaries_are_owner_scoped_and_do_not_return_prose(task_session):
    owner = await _route_user(task_session, 1009, "route-entity-owner")
    other = await _route_user(task_session, 1010, "route-entity-other")
    project = NovelProject(id="route-entity-project", user_id=owner.id, title="Entity Route Project")
    chapter = Chapter(project_id=project.id, chapter_number=1)
    task_session.add_all([project, chapter])
    await task_session.flush()
    character = BlueprintCharacter(project_id=project.id, name="沈星河", identity="主角", personality="DO_NOT_EXPOSE")
    faction = Faction(project_id=project.id, name="玄穹司", faction_type="组织", description="DO_NOT_EXPOSE")
    foreshadowing = Foreshadowing(
        project_id=project.id,
        chapter_id=chapter.id,
        chapter_number=chapter.chapter_number,
        content="DO_NOT_EXPOSE",
        type="hint",
        name="星图",
        status="planted",
    )
    node = CharacterNode(project_id=project.id, name="沈星河节点", role_type="主角", description="DO_NOT_EXPOSE")
    research = ResearchArtifact(
        project_id=project.id,
        user_id=owner.id,
        run_id="route-entity-research",
        scope="global",
        status="completed",
        trigger="manual",
        summary="DO_NOT_EXPOSE",
        provider_metadata={"secret": "DO_NOT_EXPOSE"},
    )
    task_session.add_all([character, faction, foreshadowing, node, research])
    await task_session.commit()

    result = await list_agent_project_entity_summaries(
        project.id,
        per_kind_limit=40,
        session=task_session,
        current_user=SimpleNamespace(id=owner.id),
    )

    assert result.project_id == project.id
    assert {(row.kind, row.label) for row in result.entities} == {
        ("character", "沈星河"),
        ("faction", "玄穹司"),
        ("foreshadowing", "星图"),
        ("knowledge_node", "沈星河节点"),
        ("research_artifact", f"研究 #{research.id} · global"),
    }
    serialized = result.model_dump_json()
    assert "DO_NOT_EXPOSE" not in serialized
    assert "provider_metadata" not in serialized

    with pytest.raises(HTTPException) as error:
        await list_agent_project_entity_summaries(
            project.id,
            per_kind_limit=40,
            session=task_session,
            current_user=SimpleNamespace(id=other.id),
        )
    assert error.value.status_code == 403

@pytest.mark.asyncio
async def test_agent_run_state_route_returns_safe_read_only_projection(task_session):
    owner = await _route_user(task_session, 1012, "route-state-owner")
    created = await create_agent_session(AgentSessionCreateRequest(), session=task_session, current_user=SimpleNamespace(id=owner.id))
    runtime = AgentRuntimeService(task_session)
    run = await runtime.create_run(session_id=created.id, user_id=owner.id)
    await runtime.append_event(run_id=run.id, user_id=owner.id, event_type="assistant_delta", summary="visible", data={"content": "安全回复", "reasoning": "hidden"})

    state = await get_agent_run_state(run.id, session=task_session, current_user=SimpleNamespace(id=owner.id))

    assert state["run_id"] == run.id
    assert state["correlation_id"] == run.correlation_id
    assert state["last_event_sequence"] == 1
    assert "reasoning" not in state



@pytest.mark.asyncio
async def test_agent_run_activity_route_returns_user_scoped_durable_summaries(task_session):
    owner = await _route_user(task_session, 1013, "route-activity-owner")
    other = await _route_user(task_session, 1014, "route-activity-other")
    created = await create_agent_session(AgentSessionCreateRequest(), session=task_session, current_user=SimpleNamespace(id=owner.id))
    runtime = AgentRuntimeService(task_session)
    run = await runtime.create_run(session_id=created.id, user_id=owner.id)
    event = await runtime.append_public_work_summary(
        run_id=run.id,
        user_id=owner.id,
        summary={
            "action_id": "planner",
            "phase": "planning",
            "current_action": "正在建立创作计划。",
            "input_scope": [{"kind": "project"}],
        },
    )

    items = await list_agent_run_activity(run.id, session=task_session, current_user=SimpleNamespace(id=owner.id))

    assert [(item.sequence, item.event_type) for item in items] == [(event.sequence, "public_work_summary")]
    assert items[0].data_json["current_action"] == "正在建立创作计划。"
    with pytest.raises(HTTPException) as error:
        await list_agent_run_activity(run.id, session=task_session, current_user=SimpleNamespace(id=other.id))
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_agent_message_route_queues_write_execution_before_approval(task_session, monkeypatch):
    owner = await _route_user(task_session, 1003, "route-write-owner")
    task_session.add(NovelProject(id="route-write-project", user_id=owner.id, title="Write Project"))
    await task_session.flush()
    created = await create_agent_session(AgentSessionCreateRequest(project_id="route-write-project"), session=task_session, current_user=SimpleNamespace(id=owner.id))

    class FakePlanner:
        async def plan(self, **kwargs):
            return SimpleNamespace(
                plan=build_agent_plan(AgentPlanRequest(goal=kwargs["goal"], project_id=kwargs["project_id"], tools=["chapter.generate"]), user_id=kwargs["user_id"]),
                visible_summary="需要批准的候选生成计划",
                provider_called=False,
                fallback_reason=None,
            )

    monkeypatch.setattr("app.agent.execution.AgentOrchestrator", lambda provider, **kwargs: FakePlanner())
    monkeypatch.setattr("app.agent.execution.launch_visible_response", lambda **kwargs: None)
    response = await post_agent_message(created.id, AgentMessageCreateRequest(content="生成第三章候选", arguments={"chapter_number": 3}), session=task_session, current_user=SimpleNamespace(id=owner.id))

    assert response["run"].status == "planning"
    assert response["plan"].steps == []
    assert response["approvals"] == []
    jobs = await AgentJobService(task_session).list_jobs(user_id=owner.id)
    assert [(job.kind, job.status) for job in jobs] == [("agent_execution", "queued")]

    result = await execute_agent_execution_job(jobs[0], task_session)
    assert result["status"] == "awaiting_approval"
    runtime = AgentRuntimeService(task_session)
    run = await runtime.get_run(response["run"].id, owner.id)
    approvals = await runtime.list_approvals(run_id=run.id, user_id=owner.id)
    assert run.status == "awaiting_approval"
    assert approvals[0].tool_name == "chapter.generate"
    assert approvals[0].status == "pending"
    assert "context_refs" not in approvals[0].request_json


@pytest.mark.asyncio
async def test_agent_message_route_commits_message_run_job_and_events_once(task_session, monkeypatch):
    owner = await _route_user(task_session, 10081, "route-transaction-owner")
    created = await create_agent_session(AgentSessionCreateRequest(), session=task_session, current_user=SimpleNamespace(id=owner.id))
    original_commit = task_session.commit
    commits = 0

    async def counting_commit():
        nonlocal commits
        commits += 1
        await original_commit()

    monkeypatch.setattr(task_session, "commit", counting_commit)
    response = await post_agent_message(
        created.id,
        AgentMessageCreateRequest(content="事务边界检查"),
        session=task_session,
        current_user=SimpleNamespace(id=owner.id),
    )

    assert commits == 1
    runtime = AgentRuntimeService(task_session)
    messages = await runtime.list_messages(session_id=created.id, user_id=owner.id)
    assert len(messages) == 1
    jobs = await AgentJobService(task_session).list_jobs(user_id=owner.id)
    assert len(jobs) == 1
    events = await runtime.list_events(run_id=response["run"].id, user_id=owner.id)
    assert [event.event_type for event in events] == ["run_started", "progress_update"]
    assert jobs[0].payload_json["transaction_id"] == response["run"].correlation_id


@pytest.mark.asyncio
async def test_agent_message_route_persists_execution_then_visible_response_job(task_session, monkeypatch):
    owner = await _route_user(task_session, 1008, "route-job-owner")
    created = await create_agent_session(AgentSessionCreateRequest(), session=task_session, current_user=SimpleNamespace(id=owner.id))

    class FakePlanner:
        async def plan(self, **kwargs):
            return SimpleNamespace(
                plan=build_agent_plan(AgentPlanRequest(goal=kwargs["goal"], project_id=kwargs["project_id"], tools=["project.list"]), user_id=kwargs["user_id"]),
                visible_summary="只读项目计划",
                provider_called=False,
                fallback_reason=None,
            )

    async def fake_execute_read_tool(**kwargs):
        return {"projects": []}

    monkeypatch.setattr("app.agent.execution.AgentOrchestrator", lambda provider, **kwargs: FakePlanner())
    monkeypatch.setattr("app.agent.execution.execute_read_tool", fake_execute_read_tool)
    monkeypatch.setattr("app.agent.execution.launch_visible_response", lambda **kwargs: None)
    response = await post_agent_message(created.id, AgentMessageCreateRequest(content="列出项目"), session=task_session, current_user=SimpleNamespace(id=owner.id))
    jobs = await AgentJobService(task_session).list_jobs(user_id=owner.id)
    assert len(jobs) == 1
    assert jobs[0].run_id == response["run"].id
    assert jobs[0].status == "queued"
    assert jobs[0].kind == "agent_execution"

    result = await execute_agent_execution_job(jobs[0], task_session)
    assert result["status"] == "assistant_queued"
    jobs = await AgentJobService(task_session).list_jobs(user_id=owner.id)
    jobs_by_kind = {job.kind: job for job in jobs}
    assert set(jobs_by_kind) == {"agent_execution", "visible_response"}
    assert jobs_by_kind["visible_response"].status == "queued"


@pytest.mark.asyncio
async def test_agent_command_route_supports_queued_worker_mode(task_session, monkeypatch):
    owner = await _route_user(task_session, 10082, "route-queued-command")
    created = await create_agent_session(AgentSessionCreateRequest(), session=task_session, current_user=SimpleNamespace(id=owner.id))
    response = await post_agent_message(
        created.id,
        AgentMessageCreateRequest(content="排队控制命令"),
        session=task_session,
        current_user=SimpleNamespace(id=owner.id),
    )
    run = response["run"]
    command = await submit_agent_run_command(
        run.id,
        AgentRunCommandRequest(
            command_type="pause",
            idempotency_key="queued-pause-10082",
            expected_state_version=run.state_version,
            execution_mode="queued",
        ),
        session=task_session,
        current_user=SimpleNamespace(id=owner.id),
    )

    assert command.status == "requested"
    saved = await AgentRuntimeService(task_session).get_run(run.id, owner.id)
    assert saved.status == "planning"


@pytest.mark.asyncio
async def test_agent_session_route_does_not_leak_cross_user_session(task_session):
    owner = await _route_user(task_session, 1004, "route-owner-2")
    other = await _route_user(task_session, 1005, "route-other-2")
    created = await create_agent_session(AgentSessionCreateRequest(), session=task_session, current_user=SimpleNamespace(id=owner.id))
    with pytest.raises(HTTPException) as error:
        await get_agent_session(created.id, session=task_session, current_user=SimpleNamespace(id=other.id))
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_agent_run_step_route_is_user_scoped(task_session):
    owner = await _route_user(task_session, 1006, "route-step-owner")
    other = await _route_user(task_session, 1007, "route-step-other")
    created = await create_agent_session(AgentSessionCreateRequest(), session=task_session, current_user=SimpleNamespace(id=owner.id))
    runtime = AgentRuntimeService(task_session)
    run = await runtime.create_run(session_id=created.id, user_id=owner.id)
    await runtime.ensure_step(run_id=run.id, user_id=owner.id, step_order=1, tool_name="project.list", idempotency_key="route-step")
    steps = await list_agent_run_steps(run.id, session=task_session, current_user=SimpleNamespace(id=owner.id))
    assert len(steps) == 1
    with pytest.raises(HTTPException) as error:
        await list_agent_run_steps(run.id, session=task_session, current_user=SimpleNamespace(id=other.id))
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_agent_job_route_is_user_scoped(task_session):
    owner = await _route_user(task_session, 1009, "route-job-owner-2")
    other = await _route_user(task_session, 1010, "route-job-other")
    created = await create_agent_session(AgentSessionCreateRequest(), session=task_session, current_user=SimpleNamespace(id=owner.id))
    runtime = AgentRuntimeService(task_session)
    run = await runtime.create_run(session_id=created.id, user_id=owner.id)
    from app.agent.jobs import AgentJobService
    job = await AgentJobService(task_session).create_job(run_id=run.id, user_id=owner.id, project_id=None, kind="visible_response", idempotency_key="route-job")
    rows = await list_agent_jobs(project_id=None, status=None, session=task_session, current_user=SimpleNamespace(id=owner.id))
    assert [row.id for row in rows] == [job.id]
    other_rows = await list_agent_jobs(project_id=None, status=None, session=task_session, current_user=SimpleNamespace(id=other.id))
    assert other_rows == []


@pytest.mark.asyncio
async def test_admin_dead_letter_routes_list_and_replay_with_operator_identity(task_session):
    owner = await _route_user(task_session, 1011, "route-dlq-owner")
    runtime = AgentRuntimeService(task_session)
    created = await create_agent_session(AgentSessionCreateRequest(), session=task_session, current_user=SimpleNamespace(id=owner.id))
    run = await runtime.create_run(session_id=created.id, user_id=owner.id)
    from app.agent.jobs import AgentJobService
    service = AgentJobService(task_session)
    job = await service.create_job(run_id=run.id, user_id=owner.id, project_id=None, kind="provider", idempotency_key="route-dlq", max_attempts=1)
    await service.claim_job(job_id=job.id, user_id=owner.id, lease_owner="route-worker")
    await service.fail(job_id=job.id, user_id=owner.id, lease_owner="route-worker", error_type="ProviderTimeout")
    rows = await list_agent_dead_letters(limit=100, session=task_session, _=SimpleNamespace(id=9001, is_admin=True))
    assert [row.id for row in rows] == [job.id]
    replayed = await replay_agent_dead_letter(job.id, reason="route test", session=task_session, current_admin=SimpleNamespace(id=9001, is_admin=True))
    assert replayed.status == "queued"
    assert (await service.list_dead_letters()) == []



@pytest.mark.asyncio
async def test_agent_message_context_refs_are_projected_per_tool_and_persisted(task_session, monkeypatch):
    owner = await _route_user(task_session, 1020, "context-route-owner")
    project = NovelProject(id="context-route-project", user_id=owner.id, title="Context Route Project")
    chapter = Chapter(project_id=project.id, chapter_number=3, status="generated")
    task_session.add_all([project, chapter])
    await task_session.flush()
    version = ChapterVersion(chapter_id=chapter.id, content="context version", status="accepted")
    task_session.add(version)
    await task_session.flush()
    chapter.selected_version_id = version.id
    await task_session.commit()
    created = await create_agent_session(
        AgentSessionCreateRequest(project_id=project.id),
        session=task_session,
        current_user=SimpleNamespace(id=owner.id),
    )

    planner_contexts = []
    calls = []

    class FakePlanner:
        async def plan(self, **kwargs):
            planner_contexts.append(kwargs["context_summary"])
            return SimpleNamespace(
                plan=build_agent_plan(
                    AgentPlanRequest(
                        goal=kwargs["goal"],
                        project_id=kwargs["project_id"],
                        tools=["project.context", "chapter.inspect", "quality.retest"],
                    ),
                    user_id=kwargs["user_id"],
                ),
                visible_summary="已按所选章节版本生成检查计划",
                provider_called=False,
                fallback_reason=None,
            )

    async def fake_execute_read_tool(*, tool_name, arguments, **kwargs):
        calls.append((tool_name, arguments))
        return {"tool_name": tool_name, "safe": True}

    monkeypatch.setattr("app.agent.execution.AgentOrchestrator", lambda provider, **kwargs: FakePlanner())
    monkeypatch.setattr("app.agent.execution.execute_read_tool", fake_execute_read_tool)
    monkeypatch.setattr("app.agent.execution.launch_visible_response", lambda **kwargs: None)

    response = await post_agent_message(
        created.id,
        AgentMessageCreateRequest(
            content="检查当前章节版本",
            context_refs=[
                {"kind": "project", "project_id": project.id},
                {
                    "kind": "chapter_version",
                    "project_id": project.id,
                    "chapter_number": chapter.chapter_number,
                    "version_id": version.id,
                },
            ],
        ),
        session=task_session,
        current_user=SimpleNamespace(id=owner.id),
    )

    execution_job = (await AgentJobService(task_session).list_jobs(user_id=owner.id))[0]
    await execute_agent_execution_job(execution_job, task_session)

    assert planner_contexts == [
        {
            "selected_project": True,
            "selected_chapter_number": chapter.chapter_number,
            "selected_version_id": version.id,
            "comparison_chapter_number": None,
            "has_comparison_versions": False,
            "has_artifact": False,
            "entity_context_count": 0,
            "entity_context_kinds": [],
            "quality_finding_context_count": 0,
        }
    ]
    assert calls == [
        ("project.context", {}),
        ("chapter.inspect", {"chapter_number": chapter.chapter_number}),
        (
            "quality.retest",
            {"chapter_number": chapter.chapter_number, "version_id": version.id},
        ),
    ]
    runtime = AgentRuntimeService(task_session)
    run = await runtime.get_run(response["run"].id, owner.id)
    assert run.context_json["context_refs"] == [
        {"kind": "project", "project_id": project.id, "role": "selected"},
        {
            "kind": "chapter_version",
            "project_id": project.id,
            "chapter_number": chapter.chapter_number,
            "version_id": version.id,
            "role": "selected",
        },
    ]
    assert run.context_json["tool_arguments"]["project.context"] == {}
    assert run.context_json["tool_arguments"]["chapter.inspect"] == {"chapter_number": chapter.chapter_number}
    events = await runtime.list_events(run_id=run.id, user_id=owner.id, after_sequence=0)
    progress_events = [event for event in events if event.event_type == "progress_update"]
    progress_values = [event.data_json["progress"] for event in progress_events]
    assert progress_values == sorted(progress_values)
    assert progress_events[0].data_json["progress_message"] == "已接受创作目标，正在等待 Agent 执行器。"
    assert any(event.data_json.get("tool_name") == "chapter.inspect" for event in progress_events)


@pytest.mark.asyncio
async def test_agent_message_rejects_cross_project_context_before_creating_run(task_session, monkeypatch):
    owner = await _route_user(task_session, 1021, "context-scope-owner")
    foreign = await _route_user(task_session, 1022, "context-scope-foreign")
    project = NovelProject(id="context-scope-project", user_id=owner.id, title="Owned")
    other_project = NovelProject(id="context-scope-other", user_id=foreign.id, title="Other")
    task_session.add_all([project, other_project])
    await task_session.flush()
    created = await create_agent_session(
        AgentSessionCreateRequest(project_id=project.id),
        session=task_session,
        current_user=SimpleNamespace(id=owner.id),
    )
    with pytest.raises(HTTPException) as error:
        await post_agent_message(
            created.id,
            AgentMessageCreateRequest(
                content="错误上下文",
                context_refs=[{"kind": "project", "project_id": other_project.id}],
            ),
            session=task_session,
            current_user=SimpleNamespace(id=owner.id),
        )
    assert error.value.status_code == 403
    runtime = AgentRuntimeService(task_session)
    assert await runtime.list_messages(session_id=created.id, user_id=owner.id) == []


@pytest.mark.asyncio
async def test_agent_execution_rejects_legacy_multi_tool_argument_broadcast(task_session, monkeypatch):
    owner = await _route_user(task_session, 1023, "context-legacy-owner")
    project = NovelProject(id="context-legacy-project", user_id=owner.id, title="Legacy")
    task_session.add(project)
    await task_session.flush()
    created = await create_agent_session(
        AgentSessionCreateRequest(project_id=project.id),
        session=task_session,
        current_user=SimpleNamespace(id=owner.id),
    )

    class FakePlanner:
        async def plan(self, **kwargs):
            return SimpleNamespace(
                plan=build_agent_plan(
                    AgentPlanRequest(
                        goal=kwargs["goal"],
                        project_id=kwargs["project_id"],
                        tools=["project.context", "chapter.inspect"],
                    ),
                    user_id=kwargs["user_id"],
                ),
                visible_summary="多工具计划",
                provider_called=False,
                fallback_reason=None,
            )

    monkeypatch.setattr("app.agent.execution.AgentOrchestrator", lambda provider, **kwargs: FakePlanner())
    response = await post_agent_message(
        created.id,
        AgentMessageCreateRequest(content="检查", arguments={"chapter_number": 3}),
        session=task_session,
        current_user=SimpleNamespace(id=owner.id),
    )
    execution_job = (await AgentJobService(task_session).list_jobs(user_id=owner.id))[0]
    with pytest.raises(ContextRefValidationError):
        await execute_agent_execution_job(execution_job, task_session)
    runtime = AgentRuntimeService(task_session)
    run = await runtime.get_run(response["run"].id, owner.id)
    assert run.context_json["tool_results"] == []



@pytest.mark.asyncio
async def test_agent_run_plan_route_returns_persisted_public_plan_draft(task_session):
    owner = await _route_user(task_session, 1024, "plan-read-owner")
    project = NovelProject(id="plan-read-project", user_id=owner.id, title="Plan Read")
    task_session.add(project)
    await task_session.flush()
    created = await create_agent_session(
        AgentSessionCreateRequest(project_id=project.id),
        session=task_session,
        current_user=SimpleNamespace(id=owner.id),
    )
    runtime = AgentRuntimeService(task_session)
    run = await runtime.create_run(
        session_id=created.id,
        user_id=owner.id,
        project_id=project.id,
        context={
            "goal": "读取版本信息",
            "plan_mode": "explore",
            "planner_provider_called": True,
            "plan_steps": [
                {
                    "order": 1,
                    "tool_name": "chapter.version.list",
                    "risk_level": "read",
                    "intent": "读取最近三个版本",
                    "expected_result": "版本元数据",
                    "depends_on": [],
                    "planner_arguments": {"limit": 3},
                }
            ],
        },
    )

    plan = await get_agent_run_plan(run.id, session=task_session, current_user=SimpleNamespace(id=owner.id))

    assert plan.goal == "读取版本信息"
    assert plan.provider_called is True
    assert [(step.tool_name, step.intent, step.expected_result, step.planner_arguments) for step in plan.steps] == [
        ("chapter.version.list", "读取最近三个版本", "版本元数据", {"limit": 3})
    ]


@pytest.mark.asyncio
async def test_agent_run_plan_route_returns_stable_persisted_revision_id(task_session):
    owner = await _route_user(task_session, 1025, "plan-stable-id-owner")
    created = await create_agent_session(
        AgentSessionCreateRequest(), session=task_session, current_user=SimpleNamespace(id=owner.id)
    )
    runtime = AgentRuntimeService(task_session)
    session = await runtime.get_session(created.id, owner.id)
    run = await runtime.create_run(
        session_id=session.id,
        user_id=owner.id,
        context={
            "goal": "稳定计划身份",
            "plan_mode": "explore",
            "plan_steps": [
                {"order": 1, "tool_name": "chapter.inspect", "intent": "读取章节"}
            ],
        },
    )
    snapshot = await AgentContextService(task_session).create_snapshot(
        run=run,
        session=session,
        context_json={"goal": "稳定计划身份"},
    )
    revision = await AgentPlanService(task_session).create_revision(
        run=run,
        session=session,
        context_snapshot=snapshot,
        plan_json={"steps": [{"order": 1, "tool_name": "chapter.inspect"}]},
    )

    first = await get_agent_run_plan(run.id, session=task_session, current_user=SimpleNamespace(id=owner.id))
    second = await get_agent_run_plan(run.id, session=task_session, current_user=SimpleNamespace(id=owner.id))

    assert first.plan_id == second.plan_id
    assert str(first.plan_id) == revision.revision_id


@pytest.mark.asyncio
async def test_legacy_agent_run_plan_route_returns_null_plan_id(task_session):
    owner = await _route_user(task_session, 1026, "plan-legacy-id-owner")
    created = await create_agent_session(
        AgentSessionCreateRequest(), session=task_session, current_user=SimpleNamespace(id=owner.id)
    )
    run = await AgentRuntimeService(task_session).create_run(
        session_id=created.id,
        user_id=owner.id,
        context={
            "goal": "兼容旧计划",
            "plan_steps": [
                {"order": 1, "tool_name": "chapter.inspect", "intent": "读取章节"}
            ],
        },
    )

    first = await get_agent_run_plan(run.id, session=task_session, current_user=SimpleNamespace(id=owner.id))
    second = await get_agent_run_plan(run.id, session=task_session, current_user=SimpleNamespace(id=owner.id))

    assert first.plan_id is None
    assert second.plan_id is None

@pytest.mark.asyncio
async def test_agent_run_activity_route_replays_ordered_cursor_pages(task_session):
    owner = await _route_user(task_session, 1015, "route-activity-page-owner")
    created = await create_agent_session(
        AgentSessionCreateRequest(), session=task_session, current_user=SimpleNamespace(id=owner.id)
    )
    runtime = AgentRuntimeService(task_session)
    run = await runtime.create_run(session_id=created.id, user_id=owner.id)

    first = await runtime.append_public_work_summary(
        run_id=run.id,
        user_id=owner.id,
        summary={
            "action_id": "context",
            "phase": "context",
            "current_action": "正在读取项目上下文。",
            "input_scope": [{"kind": "project"}],
        },
    )
    second = await runtime.append_event(
        run_id=run.id,
        user_id=owner.id,
        event_type="planner_started",
        summary="正在建立计划。",
        data={"phase": "planning"},
    )
    third = await runtime.append_public_work_summary(
        run_id=run.id,
        user_id=owner.id,
        summary={
            "action_id": "plan",
            "phase": "planning",
            "current_action": "正在整理计划输出。",
            "input_scope": [{"kind": "project"}],
            "revision": 1,
        },
    )

    first_page = await list_agent_run_activity(
        run.id, after_sequence=first.sequence, limit=2, session=task_session, current_user=SimpleNamespace(id=owner.id)
    )
    second_page = await list_agent_run_activity(
        run.id, after_sequence=second.sequence, limit=2, session=task_session, current_user=SimpleNamespace(id=owner.id)
    )

    assert [item.sequence for item in first_page] == [second.sequence, third.sequence]
    assert [item.sequence for item in second_page] == [third.sequence]
    assert [item.event_type for item in first_page] == ["planner_started", "public_work_summary"]

@pytest.mark.asyncio
async def test_agent_run_command_routes_persist_and_project_applied_commands(task_session):
    owner = await _route_user(task_session, 1016, "route-command-owner")
    created = await create_agent_session(
        AgentSessionCreateRequest(), session=task_session, current_user=SimpleNamespace(id=owner.id)
    )
    runtime = AgentRuntimeService(task_session)
    run = await runtime.create_run(session_id=created.id, user_id=owner.id)
    await runtime.update_run(run_id=run.id, user_id=owner.id, status="running", phase="tool_execution", progress=31)

    command = await submit_agent_run_command(
        run.id,
        AgentRunCommandRequest(
            command_type="pause",
            reason="作者检查当前计划",
            idempotency_key="route:pause:1016",
            expected_state_version=int(run.state_version or 0),
        ),
        session=task_session,
        current_user=SimpleNamespace(id=owner.id),
    )
    commands = await list_agent_run_commands(
        run.id, session=task_session, current_user=SimpleNamespace(id=owner.id)
    )
    state = await get_agent_run_state(run.id, session=task_session, current_user=SimpleNamespace(id=owner.id))

    assert command.command_type == "pause"
    assert command.status == "applied"
    assert command.reason == "作者检查当前计划"
    assert command.idempotency_key == "route:pause:1016"
    assert command.expected_state_version == 1
    assert [(item.command_type, item.status) for item in commands] == [("pause", "applied")]
    assert [(item["command_type"], item["status"]) for item in state["commands"]] == [("pause", "applied")]



@pytest.mark.asyncio
async def test_agent_run_provider_provenance_route_is_scoped_and_stage_specific(task_session):
    owner = await _route_user(task_session, 1026, "provenance-owner")
    other = await _route_user(task_session, 1027, "provenance-other")
    created = await create_agent_session(
        AgentSessionCreateRequest(), session=task_session, current_user=SimpleNamespace(id=owner.id)
    )
    runtime = AgentRuntimeService(task_session)
    run = await runtime.create_run(
        session_id=created.id,
        user_id=owner.id,
        context={
            "planner_provider_called": True,
            "planner_provider_fallback_reason": None,
            "response_provider_called": True,
            "response_provider_fallback_reason": None,
            "candidate_writer_provider_called": False,
            "candidate_writer_provider_fallback_reason": "empty_response",
            "candidate_writer_model_ref": "fixture-model",
            "planner_provider_attempts": {
                "provider_attempts": [{
                    "attempt": 1, "role": "planner", "provider_ref": "planner-fixture",
                    "status": "failed", "error_category": "TIMEOUT", "headers": {"x-api-key": "secret"},
                }],
                "selected_provider_attempt": None, "fallback_used": False,
            },
            "response_provider_attempts": {
                "provider_attempts": [{
                    "attempt": 1, "role": "response", "provider_ref": "response-fixture",
                    "status": "failed", "error_category": "TIMEOUT", "prompt": "private",
                }],
                "selected_provider_attempt": None, "fallback_used": False,
            },
            "reasoning": "private",
        },
    )

    provenance = await get_agent_run_provider_provenance(
        run.id, session=task_session, current_user=SimpleNamespace(id=owner.id)
    )

    assert provenance.planner_provider_called is True
    assert provenance.response_provider_called is True
    assert provenance.candidate_writer_provider_called is False
    assert provenance.candidate_writer_provider_fallback_reason == "empty_response"
    assert provenance.candidate_writer_model_ref == "fixture-model"
    assert provenance.planner_provider_attempts["provider_attempts"][0]["role"] == "planner"
    assert provenance.response_provider_attempts["provider_attempts"][0]["role"] == "response"
    dumped = provenance.model_dump()
    assert "reasoning" not in dumped
    assert "headers" not in dumped["planner_provider_attempts"]["provider_attempts"][0]
    assert "prompt" not in dumped["response_provider_attempts"]["provider_attempts"][0]
    with pytest.raises(HTTPException) as error:
        await get_agent_run_provider_provenance(
            run.id, session=task_session, current_user=SimpleNamespace(id=other.id)
        )
    assert error.value.status_code == 404




@pytest.mark.asyncio
async def test_agent_run_plan_route_projects_latest_revision_payload_over_mutable_run_context(task_session):
    owner = await _route_user(task_session, 1027, "plan-revision-projection-owner")
    created = await create_agent_session(
        AgentSessionCreateRequest(), session=task_session, current_user=SimpleNamespace(id=owner.id)
    )
    runtime = AgentRuntimeService(task_session)
    session = await runtime.get_session(created.id, owner.id)
    run = await runtime.create_run(
        session_id=session.id,
        user_id=owner.id,
        context={
            "goal": "已变更的临时目标",
            "plan_mode": "explore",
            "planner_provider_called": False,
            "plan_steps": [{"order": 1, "tool_name": "chapter.inspect", "intent": "临时步骤"}],
        },
    )
    snapshot = await AgentContextService(task_session).create_snapshot(
        run=run,
        session=session,
        context_json={"goal": "持久化计划上下文"},
    )
    await AgentPlanService(task_session).create_revision(
        run=run,
        session=session,
        context_snapshot=snapshot,
        plan_json={
            "schema_version": 1,
            "goal": "持久化计划目标",
            "mode": "strict",
            "phase": "planning",
            "steps": [
                {
                    "order": 1,
                    "tool_name": "chapter.version.list",
                    "intent": "读取持久化版本",
                    "expected_result": "版本列表",
                    "depends_on": [],
                    "planner_arguments": {"limit": 7},
                }
            ],
            "provider_called": True,
            "fallback_reason": "provider-timeout",
        },
    )

    plan = await get_agent_run_plan(run.id, session=task_session, current_user=SimpleNamespace(id=owner.id))

    assert plan.goal == "持久化计划目标"
    assert plan.mode == "strict"
    assert plan.provider_called is True
    assert plan.planner_fallback_reason == "provider-timeout"
    assert [(step.tool_name, step.intent, step.expected_result, step.planner_arguments) for step in plan.steps] == [
        ("chapter.version.list", "读取持久化版本", "版本列表", {"limit": 7})
    ]


@pytest.mark.asyncio
async def test_agent_run_plan_route_does_not_fallback_to_mutable_steps_when_revision_steps_are_malformed(task_session):
    owner = await _route_user(task_session, 1028, "plan-revision-malformed-owner")
    created = await create_agent_session(
        AgentSessionCreateRequest(), session=task_session, current_user=SimpleNamespace(id=owner.id)
    )
    runtime = AgentRuntimeService(task_session)
    session = await runtime.get_session(created.id, owner.id)
    run = await runtime.create_run(
        session_id=session.id,
        user_id=owner.id,
        context={
            "goal": "临时目标",
            "plan_steps": [{"order": 1, "tool_name": "chapter.inspect", "intent": "不应投影"}],
        },
    )
    snapshot = await AgentContextService(task_session).create_snapshot(
        run=run,
        session=session,
        context_json={"goal": "持久化目标"},
    )
    await AgentPlanService(task_session).create_revision(
        run=run,
        session=session,
        context_snapshot=snapshot,
        plan_json={"goal": "持久化目标", "mode": "strict", "steps": {"invalid": True}},
    )

    plan = await get_agent_run_plan(run.id, session=task_session, current_user=SimpleNamespace(id=owner.id))

    assert plan.goal == "持久化目标"
    assert plan.mode == "strict"
    assert plan.steps == []
