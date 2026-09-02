from __future__ import annotations

import asyncio
from datetime import timedelta
from types import SimpleNamespace
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.agent.executor import build_agent_plan
from app.agent.jobs import AgentJobService
from app.agent.schemas import AgentPlanRequest
from app.agent.worker import AgentWorker, handle_agent_execution_job, handle_visible_response_job
from app.db.base import Base
from app.models import AgentJob, AgentRun, User
from app.services.agent_runtime import AgentRuntimeService


async def _factory(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'worker.sqlite').as_posix()}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def _run(factory, user_id: int, kind: str = 'demo', max_attempts: int = 3):
    async with factory() as session:
        user = User(id=user_id, username=f'worker-{user_id}', email=f'worker-{user_id}@example.com', hashed_password='x', is_active=True)
        session.add(user)
        await session.flush()
        runtime = AgentRuntimeService(session)
        agent_session = await runtime.create_session(user_id=user.id)
        run = await runtime.create_run(session_id=agent_session.id, user_id=user.id)
        job = await AgentJobService(session).create_job(run_id=run.id, user_id=user.id, project_id=None, kind=kind, idempotency_key=f'{run.id}:job', max_attempts=max_attempts, payload={'goal': 'test', 'reasoning': 'secret'})
        return run.id, job.id


@pytest.mark.asyncio
async def test_worker_claims_and_completes_persisted_job(tmp_path):
    engine, factory = await _factory(tmp_path)
    try:
        run_id, job_id = await _run(factory, 1501)
        seen: list[str] = []

        async def handler(job, session):
            seen.append(job.id)
            return {'ok': True, 'reasoning': 'must not persist'}

        worker = AgentWorker(factory, worker_id='worker-a', handlers={'demo': handler})
        assert await worker.poll_once() is True
        assert seen == [job_id]
        async with factory() as session:
            job = (await session.execute(select(AgentJob).where(AgentJob.id == job_id))).scalar_one()
            assert job.status == 'succeeded'
            assert job.result_json == {'ok': True}
            assert job.run_id == run_id
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_worker_resumes_recovery_ready_run_after_expired_leases(tmp_path, monkeypatch):
    engine, factory = await _factory(tmp_path)
    try:
        run_id, job_id = await _run(factory, 1506, kind='visible_response')
        async with factory() as session:
            runtime = AgentRuntimeService(session)
            run = await runtime.update_run(
                run_id=run_id, user_id=1506, status='running', phase='assistant_response', progress=80
            )
            await runtime.claim_run(run_id=run_id, user_id=1506, lease_owner='crashed-runner', lease_seconds=1)
            job = await AgentJobService(session).claim_job(
                job_id=job_id, user_id=1506, lease_owner='crashed-worker', lease_seconds=1
            )
            run.lease_expires_at = runtime._now() - timedelta(seconds=1)
            job.lease_expires_at = AgentJobService._now() - timedelta(seconds=1)
            await session.commit()
            assert await runtime.reconcile_stale_runs() == [run_id]

        async def fake_runner(**kwargs):
            async with factory() as other_session:
                await AgentRuntimeService(other_session).update_run(
                    run_id=run_id, user_id=1506, status='completed', phase='summary', progress=100
                )

        monkeypatch.setattr('app.agent.worker._run_visible_response', fake_runner)
        worker = AgentWorker(
            factory,
            worker_id='replacement-worker',
            handlers={'visible_response': handle_visible_response_job},
        )
        assert await worker.poll_once() is True

        async with factory() as session:
            job = (await session.execute(select(AgentJob).where(AgentJob.id == job_id))).scalar_one()
            run = (await session.execute(select(AgentRun).where(AgentRun.id == run_id))).scalar_one()
            events = await AgentRuntimeService(session).list_events(run_id=run_id, user_id=1506)
            assert job.status == 'succeeded'
            assert run.status == 'completed'
            assert [event.event_type for event in events] == [
                'run_recovery_ready', 'run_resumed'
            ]
    finally:
        await engine.dispose()
@pytest.mark.asyncio
async def test_worker_reclaims_expired_running_run_after_process_crash(tmp_path, monkeypatch):
    engine, factory = await _factory(tmp_path)
    try:
        run_id, job_id = await _run(factory, 1507, kind='visible_response')
        async with factory() as session:
            runtime = AgentRuntimeService(session)
            run = await runtime.update_run(
                run_id=run_id, user_id=1507, status='running', phase='assistant_response', progress=80
            )
            await runtime.claim_run(run_id=run_id, user_id=1507, lease_owner='crashed-api', lease_seconds=1)
            job = await AgentJobService(session).claim_job(
                job_id=job_id, user_id=1507, lease_owner='crashed-worker', lease_seconds=1
            )
            run.lease_expires_at = runtime._now() - timedelta(seconds=1)
            job.lease_expires_at = AgentJobService._now() - timedelta(seconds=1)
            await session.commit()

        async def fake_runner(**kwargs):
            async with factory() as other_session:
                await AgentRuntimeService(other_session).update_run(
                    run_id=run_id, user_id=1507, status='completed', phase='summary', progress=100
                )

        monkeypatch.setattr('app.agent.worker._run_visible_response', fake_runner)
        worker = AgentWorker(
            factory,
            worker_id='replacement-worker-2',
            handlers={'visible_response': handle_visible_response_job},
        )
        assert await worker.poll_once() is True

        async with factory() as session:
            job = (await session.execute(select(AgentJob).where(AgentJob.id == job_id))).scalar_one()
            run = (await session.execute(select(AgentRun).where(AgentRun.id == run_id))).scalar_one()
            assert job.status == 'succeeded'
            assert run.status == 'completed'
    finally:
        await engine.dispose()
@pytest.mark.asyncio
async def test_worker_unknown_kind_is_non_retryable_failure(tmp_path):
    engine, factory = await _factory(tmp_path)
    try:
        _, job_id = await _run(factory, 1502, kind='missing')
        worker = AgentWorker(factory, worker_id='worker-b', handlers={})
        assert await worker.poll_once() is True
        async with factory() as session:
            job = (await session.execute(select(AgentJob).where(AgentJob.id == job_id))).scalar_one()
            assert job.status == 'failed'
            assert job.error_type == 'UnknownJobKind'
    finally:
        await engine.dispose()


class ProviderTimeout(Exception):
    pass


@pytest.mark.asyncio
async def test_visible_response_handler_refreshes_run_after_external_runner_commit(tmp_path, monkeypatch):
    engine, factory = await _factory(tmp_path)
    try:
        run_id, job_id = await _run(factory, 1505, kind='visible_response')
        async with factory() as session:
            job = await AgentJobService(session).claim_job(
                job_id=job_id, user_id=1505, lease_owner='worker-refresh', lease_seconds=60
            )
            async def fake_runner(**kwargs):
                async with factory() as other_session:
                    await AgentRuntimeService(other_session).update_run(
                        run_id=run_id, user_id=1505, status='completed', phase='summary', progress=100
                    )
            monkeypatch.setattr('app.agent.worker._run_visible_response', fake_runner)
            result = await handle_visible_response_job(job, session)
            assert result == {'visible_response_job_id': job_id}
    finally:
        await engine.dispose()
@pytest.mark.asyncio
async def test_worker_retryable_failure_reaches_dead_letter(tmp_path):
    engine, factory = await _factory(tmp_path)
    try:
        _, job_id = await _run(factory, 1503, max_attempts=1)

        async def handler(job, session):
            raise ProviderTimeout('temporary')

        worker = AgentWorker(factory, worker_id='worker-c', handlers={'demo': handler})
        assert await worker.poll_once() is True
        async with factory() as session:
            job = (await session.execute(select(AgentJob).where(AgentJob.id == job_id))).scalar_one()
            assert job.status == 'dead_letter'
            assert job.attempt_count == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_two_workers_do_not_both_process_one_job(tmp_path):
    engine, factory = await _factory(tmp_path)
    try:
        _, job_id = await _run(factory, 1504)
        calls: list[str] = []

        async def handler(job, session):
            calls.append(job.id)
            return {'worker': job.id}

        workers = [AgentWorker(factory, worker_id='worker-d', handlers={'demo': handler}), AgentWorker(factory, worker_id='worker-e', handlers={'demo': handler})]
        results = await asyncio.gather(*(worker.poll_once() for worker in workers))
        assert sum(results) == 1
        assert calls == [job_id]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_worker_executes_agent_execution_after_enqueue_and_queues_visible_response(tmp_path, monkeypatch):
    engine, factory = await _factory(tmp_path)
    try:
        async with factory() as session:
            user = User(id=1551, username="execution-worker", email="execution-worker@example.com", hashed_password="x", is_active=True)
            from app.models import NovelProject

            project = NovelProject(id="execution-worker-project", user_id=user.id, title="Execution Worker")
            session.add_all([user, project])
            await session.flush()
            runtime = AgentRuntimeService(session)
            agent_session = await runtime.create_session(user_id=user.id, project_id=project.id)
            run = await runtime.create_run(
                session_id=agent_session.id,
                user_id=user.id,
                project_id=project.id,
                context={
                    "goal": "检查项目状态",
                    "context_refs": [],
                    "requested_tools": ["project.context"],
                    "arguments": {},
                    "tool_arguments": {},
                    "tool_results": [],
                    "plan_steps": [],
                },
            )
            job = await AgentJobService(session).create_job(
                run_id=run.id,
                user_id=user.id,
                project_id=project.id,
                kind="agent_execution",
                idempotency_key=f"{run.id}:agent_execution",
            )

        class FakePlanner:
            async def plan(self, **kwargs):
                return SimpleNamespace(
                    plan=build_agent_plan(
                        AgentPlanRequest(
                            goal=kwargs["goal"],
                            project_id=kwargs["project_id"],
                            tools=["project.context"],
                        ),
                        user_id=kwargs["user_id"],
                    ),
                    visible_summary="项目状态读取计划",
                    provider_called=False,
                    fallback_reason=None,
                )

        async def fake_execute_read_tool(**kwargs):
            return {"project_id": kwargs["project_id"], "safe": True}

        monkeypatch.setattr("app.agent.execution.AgentOrchestrator", lambda provider, **kwargs: FakePlanner())
        monkeypatch.setattr("app.agent.execution.execute_read_tool", fake_execute_read_tool)
        monkeypatch.setattr("app.agent.execution.launch_visible_response", lambda **kwargs: None)

        worker = AgentWorker(
            factory,
            worker_id="execution-worker-a",
            handlers={"agent_execution": handle_agent_execution_job, "visible_response": handle_visible_response_job},
        )
        assert await worker.poll_once() is True

        async with factory() as session:
            jobs = await AgentJobService(session).list_jobs(user_id=1551)
            jobs_by_kind = {item.kind: item for item in jobs}
            assert jobs_by_kind["agent_execution"].status == "succeeded"
            assert jobs_by_kind["visible_response"].status == "queued"
            runtime = AgentRuntimeService(session)
            stored_run = await runtime.get_run(run.id, 1551)
            assert stored_run.status == "running"
            assert stored_run.current_phase == "assistant_response"
            assert stored_run.context_json["execution_job_id"] == job.id
            assert stored_run.context_json["visible_response_job_id"] == jobs_by_kind["visible_response"].id
            steps = await runtime.list_steps(run_id=run.id, user_id=1551)
            assert [(item.tool_name, item.status) for item in steps] == [("project.context", "completed")]
            events = await runtime.list_events(run_id=run.id, user_id=1551, after_sequence=0)
            kinds = [item.event_type for item in events]
            assert kinds.index("planner_started") < kinds.index("plan_created")
            assert kinds.index("plan_created") < kinds.index("tool_call_started")
            assert kinds.index("tool_call_started") < kinds.index("tool_call_completed")
            assert kinds.index("tool_call_completed") < kinds.index("assistant_queued")
            started_event = next(item for item in events if item.event_type == "tool_call_started")
            completed_event = next(item for item in events if item.event_type == "tool_call_completed")
            progress_events = [item for item in events if item.event_type == "progress_update" and item.data_json.get("step") == 1]
            assert started_event.data_json["action_id"] == completed_event.data_json["action_id"]
            assert started_event.data_json["action_id"].startswith("step:")
            assert completed_event.data_json["result_ref"].startswith("execution:")
            assert progress_events
            assert all(item.data_json["action_id"] == started_event.data_json["action_id"] for item in progress_events)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_worker_marks_invalid_agent_execution_failed_without_visible_response(tmp_path):
    engine, factory = await _factory(tmp_path)
    try:
        async with factory() as session:
            user = User(id=1552, username="execution-invalid", email="execution-invalid@example.com", hashed_password="x", is_active=True)
            session.add(user)
            await session.flush()
            runtime = AgentRuntimeService(session)
            agent_session = await runtime.create_session(user_id=user.id)
            run = await runtime.create_run(session_id=agent_session.id, user_id=user.id, context={"context_refs": []})
            job = await AgentJobService(session).create_job(
                run_id=run.id,
                user_id=user.id,
                project_id=None,
                kind="agent_execution",
                idempotency_key=f"{run.id}:agent_execution",
            )

        worker = AgentWorker(
            factory,
            worker_id="execution-invalid-worker",
            handlers={"agent_execution": handle_agent_execution_job},
        )
        assert await worker.poll_once() is True

        async with factory() as session:
            stored_job = await AgentJobService(session).get_job(job_id=job.id, user_id=1552)
            assert stored_job.status == "failed"
            assert stored_job.error_type == "ValueError"
            runtime = AgentRuntimeService(session)
            stored_run = await runtime.get_run(run.id, 1552)
            assert stored_run.status == "failed"
            events = await runtime.list_events(run_id=run.id, user_id=1552, after_sequence=0)
            assert [(event.event_type, event.data_json.get("error_type")) for event in events] == [
                ("run_failed", "ValueError"),
            ]
            assert [item.kind for item in await AgentJobService(session).list_jobs(user_id=1552)] == ["agent_execution"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_worker_projects_structured_plan_draft_arguments_and_persists_digest(tmp_path, monkeypatch):
    engine, factory = await _factory(tmp_path)
    try:
        async with factory() as session:
            user = User(id=1553, username="plan-draft-worker", email="plan-draft-worker@example.com", hashed_password="x", is_active=True)
            from app.models import NovelProject

            project = NovelProject(id="plan-draft-project", user_id=user.id, title="Plan Draft")
            session.add_all([user, project])
            await session.flush()
            runtime = AgentRuntimeService(session)
            agent_session = await runtime.create_session(user_id=user.id, project_id=project.id)
            run = await runtime.create_run(
                session_id=agent_session.id,
                user_id=user.id,
                project_id=project.id,
                context={
                    "goal": "列出版本元数据",
                    "context_refs": [],
                    "requested_tools": [],
                    "arguments": {},
                    "tool_arguments": {},
                    "tool_results": [],
                    "plan_steps": [],
                },
            )
            job = await AgentJobService(session).create_job(
                run_id=run.id, user_id=user.id, project_id=project.id,
                kind="agent_execution", idempotency_key=f"{run.id}:agent_execution"
            )

        class FakePlanner:
            async def plan(self, **kwargs):
                plan = build_agent_plan(
                    AgentPlanRequest(goal=kwargs["goal"], project_id=kwargs["project_id"], tools=["chapter.version.list"]),
                    user_id=kwargs["user_id"],
                )
                plan.steps[0].intent = "读取最近三个版本的元数据"
                plan.steps[0].expected_result = "版本列表摘要"
                plan.steps[0].planner_arguments = {"limit": 3}
                return SimpleNamespace(
                    plan=plan,
                    visible_summary="先读取受限版本元数据。",
                    provider_called=True,
                    fallback_reason=None,
                )

        calls = []

        async def fake_execute_read_tool(**kwargs):
            calls.append((kwargs["tool_name"], kwargs["arguments"]))
            return {"versions": [{"version_id": 9, "content": "must not reach digest"}], "count": 1}

        monkeypatch.setattr("app.agent.execution.AgentOrchestrator", lambda provider, **kwargs: FakePlanner())
        monkeypatch.setattr("app.agent.execution.execute_read_tool", fake_execute_read_tool)
        monkeypatch.setattr("app.agent.execution.launch_visible_response", lambda **kwargs: None)
        worker = AgentWorker(factory, worker_id="plan-draft-worker-a", handlers={"agent_execution": handle_agent_execution_job})
        assert await worker.poll_once() is True

        async with factory() as session:
            runtime = AgentRuntimeService(session)
            stored_run = await runtime.get_run(run.id, 1553)
            assert calls == [("chapter.version.list", {"limit": 3})]
            assert stored_run.context_json["tool_arguments"]["chapter.version.list"] == {"limit": 3}
            assert stored_run.context_json["plan_steps"] == [
                {
                    "order": 1,
                    "tool_name": "chapter.version.list",
                    "risk_level": "read",
                    "intent": "读取最近三个版本的元数据",
                    "expected_result": "版本列表摘要",
                    "depends_on": [],
                    "planner_arguments": {"limit": 3},
                }
            ]
            digest = stored_run.context_json["tool_result_digests"][0]
            assert digest["summary"]["versions"][0]["content"] == "[omitted-prose]"
            assert digest["summary"]["count"] == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_worker_blocks_structured_plan_step_when_dependency_failed(tmp_path, monkeypatch):
    engine, factory = await _factory(tmp_path)
    try:
        async with factory() as session:
            user = User(id=1554, username="dependency-worker", email="dependency-worker@example.com", hashed_password="x", is_active=True)
            from app.models import NovelProject

            project = NovelProject(id="dependency-project", user_id=user.id, title="Dependencies")
            session.add_all([user, project])
            await session.flush()
            runtime = AgentRuntimeService(session)
            agent_session = await runtime.create_session(user_id=user.id, project_id=project.id)
            run = await runtime.create_run(
                session_id=agent_session.id,
                user_id=user.id,
                project_id=project.id,
                context={"goal": "先读取再研究", "context_refs": [], "requested_tools": [], "arguments": {}, "tool_arguments": {}, "tool_results": [], "plan_steps": []},
            )
            job = await AgentJobService(session).create_job(
                run_id=run.id, user_id=user.id, project_id=project.id,
                kind="agent_execution", idempotency_key=f"{run.id}:agent_execution"
            )

        class FakePlanner:
            async def plan(self, **kwargs):
                plan = build_agent_plan(
                    AgentPlanRequest(goal=kwargs["goal"], project_id=kwargs["project_id"], tools=["chapter.version.list", "research.inspect"]),
                    user_id=kwargs["user_id"],
                )
                plan.steps[1].depends_on = [1]
                return SimpleNamespace(plan=plan, visible_summary="依赖计划", provider_called=True, fallback_reason=None)

        calls = []

        async def fake_execute_read_tool(**kwargs):
            calls.append(kwargs["tool_name"])
            if kwargs["tool_name"] == "chapter.version.list":
                raise RuntimeError("fixture first step failure")
            return {"ok": True}

        monkeypatch.setattr("app.agent.execution.AgentOrchestrator", lambda provider, **kwargs: FakePlanner())
        monkeypatch.setattr("app.agent.execution.execute_read_tool", fake_execute_read_tool)
        monkeypatch.setattr("app.agent.execution.launch_visible_response", lambda **kwargs: None)
        worker = AgentWorker(factory, worker_id="dependency-worker-a", handlers={"agent_execution": handle_agent_execution_job})
        assert await worker.poll_once() is True

        async with factory() as session:
            runtime = AgentRuntimeService(session)
            steps = await runtime.list_steps(run_id=run.id, user_id=1554)
            assert calls == ["chapter.version.list"]
            assert [(step.tool_name, step.status, step.error_type) for step in steps] == [
                ("chapter.version.list", "failed", "RuntimeError"),
                ("research.inspect", "failed", "DependencyNotCompleted"),
            ]
            events = await runtime.list_events(run_id=run.id, user_id=1554, after_sequence=0)
            assert any(event.event_type == "plan_step_failed" and event.data_json.get("error_type") == "DependencyNotCompleted" for event in events)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_worker_queues_and_executes_one_digest_driven_replan_after_read_failure(tmp_path, monkeypatch):
    engine, factory = await _factory(tmp_path)
    try:
        async with factory() as session:
            user = User(id=1555, username="replan-worker", email="replan-worker@example.com", hashed_password="x", is_active=True)
            from app.models import NovelProject

            project = NovelProject(id="replan-project", user_id=user.id, title="Replan")
            session.add_all([user, project])
            await session.flush()
            runtime = AgentRuntimeService(session)
            agent_session = await runtime.create_session(user_id=user.id, project_id=project.id)
            run = await runtime.create_run(
                session_id=agent_session.id,
                user_id=user.id,
                project_id=project.id,
                context={
                    "goal": "先读取版本和研究，再给出项目统计",
                    "context_refs": [],
                    "requested_tools": [],
                    "arguments": {},
                    "tool_arguments": {},
                    "tool_results": [],
                    "plan_steps": [],
                },
            )
            initial_job = await AgentJobService(session).create_job(
                run_id=run.id, user_id=user.id, project_id=project.id,
                kind="agent_execution", idempotency_key=f"{run.id}:agent_execution"
            )

        planner_contexts = []

        class FakePlanner:
            async def plan(self, **kwargs):
                planner_contexts.append(kwargs)
                ledger = kwargs.get("attempt_ledger")
                if ledger is not None:
                    attempt = ledger.begin(
                        role="planner",
                        provider_ref="replan-fixture",
                        model_ref="replan-model",
                        retry_index=len(planner_contexts) - 1,
                    )
                    ledger.finish(attempt.attempt_id, output=f"planner-call-{len(planner_contexts)}")
                if kwargs.get("requested_tools"):
                    return SimpleNamespace(
                        plan=build_agent_plan(
                            AgentPlanRequest(
                                goal=kwargs["goal"], project_id=kwargs["project_id"], tools=kwargs["requested_tools"]
                            ),
                            user_id=kwargs["user_id"],
                        ),
                        visible_summary="执行已持久化的修订计划。",
                        provider_called=False,
                        fallback_reason=None,
                    )
                if len([item for item in planner_contexts if not item.get("requested_tools")]) == 1:
                    plan = build_agent_plan(
                        AgentPlanRequest(
                            goal=kwargs["goal"], project_id=kwargs["project_id"],
                            tools=["chapter.version.list", "research.inspect"],
                        ),
                        user_id=kwargs["user_id"],
                    )
                    return SimpleNamespace(plan=plan, visible_summary="先读取版本与研究摘要。", provider_called=True, fallback_reason=None)
                digest = kwargs["context_summary"]["completed_tool_results"]
                assert digest[0]["summary"]["versions"][0]["content"] == "[omitted-prose]"
                assert kwargs["context_summary"]["failed_steps"] == [
                    {"step": 2, "tool_name": "research.inspect", "error_type": "RuntimeError"}
                ]
                plan = build_agent_plan(
                    AgentPlanRequest(goal=kwargs["goal"], project_id=kwargs["project_id"], tools=["statistics.project"]),
                    user_id=kwargs["user_id"],
                )
                plan.steps[0].intent = "使用已完成版本信息补充项目统计"
                plan.steps[0].expected_result = "项目统计摘要"
                return SimpleNamespace(plan=plan, visible_summary="研究读取失败，改用项目统计补充结论。", provider_called=True, fallback_reason=None)

        calls = []

        async def fake_execute_read_tool(**kwargs):
            calls.append(kwargs["tool_name"])
            if kwargs["tool_name"] == "chapter.version.list":
                return {"versions": [{"version_id": 7, "content": "secret prose"}], "count": 1}
            if kwargs["tool_name"] == "research.inspect":
                raise RuntimeError("research fixture failure")
            if kwargs["tool_name"] == "statistics.project":
                return {"total_chapters": 12, "completed_chapters": 3}
            raise AssertionError(kwargs["tool_name"])

        monkeypatch.setattr("app.agent.execution.AgentOrchestrator", lambda provider, **kwargs: FakePlanner())
        monkeypatch.setattr("app.agent.execution.execute_read_tool", fake_execute_read_tool)
        monkeypatch.setattr("app.agent.execution.launch_visible_response", lambda **kwargs: None)
        worker = AgentWorker(
            factory, worker_id="replan-worker-a",
            handlers={"agent_execution": handle_agent_execution_job},
        )

        assert await worker.poll_once() is True
        async with factory() as session:
            jobs = await AgentJobService(session).list_jobs(user_id=1555)
            jobs_by_key = {item.id: item for item in jobs}
            assert jobs_by_key[initial_job.id].status == "succeeded"
            revision_jobs = [item for item in jobs if item.kind == "agent_execution" and item.id != initial_job.id]
            assert len(revision_jobs) == 1
            assert revision_jobs[0].status == "queued"
            runtime = AgentRuntimeService(session)
            pending = await runtime.get_run(run.id, 1555)
            assert pending.current_phase == "replanning"
            assert pending.context_json["replan_revision"] == 1
            assert [item["tool_name"] for item in pending.context_json["plan_steps"]] == [
                "chapter.version.list", "research.inspect", "statistics.project"
            ]
            planner_attempts = pending.context_json["planner_provider_attempts"]["provider_attempts"]
            assert [item["status"] for item in planner_attempts] == ["succeeded", "succeeded"]
            assert [item["retry_index"] for item in planner_attempts] == [0, 1]

        assert await worker.poll_once() is True
        async with factory() as session:
            runtime = AgentRuntimeService(session)
            stored_run = await runtime.get_run(run.id, 1555)
            jobs = await AgentJobService(session).list_jobs(user_id=1555)
            jobs_by_kind = {}
            for item in jobs:
                jobs_by_kind.setdefault(item.kind, []).append(item)
            assert all(item.status == "succeeded" for item in jobs_by_kind["agent_execution"])
            assert jobs_by_kind["visible_response"][0].status == "queued"
            assert calls == ["chapter.version.list", "research.inspect", "statistics.project"]
            assert stored_run.context_json["tool_result_digests"][-1]["tool_name"] == "statistics.project"
            revisions = stored_run.context_json["plan_revisions"]
            assert len(revisions) == 1
            assert revisions[0]["visible_summary"] == "研究读取失败，改用项目统计补充结论。"
            steps = await runtime.list_steps(run_id=run.id, user_id=1555)
            assert [(step.step_order, step.tool_name, step.status) for step in steps] == [
                (1, "chapter.version.list", "completed"),
                (2, "research.inspect", "failed"),
                (3, "statistics.project", "completed"),
            ]
            events = await runtime.list_events(run_id=run.id, user_id=1555, after_sequence=0)
            revisions_events = [event for event in events if event.event_type == "plan_revised"]
            assert revisions_events[0].data_json["revision"] == 1
            assert revisions_events[0].summary == "研究读取失败，改用项目统计补充结论。"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_visible_response_dead_letter_replay_completes_once(tmp_path, monkeypatch):
    """Retry exhaustion stays replayable and a later success writes one final reply."""
    engine, factory = await _factory(tmp_path)
    try:
        run_id, job_id = await _run(factory, 1510, kind="visible_response", max_attempts=2)
        async with factory() as session:
            runtime = AgentRuntimeService(session)
            await runtime.update_run(
                run_id=run_id,
                user_id=1510,
                status="running",
                phase="assistant_response",
                progress=85,
            )

        calls: list[str] = []

        async def fake_visible_runner(**_kwargs):
            calls.append("visible_response")
            if len(calls) <= 2:
                raise ProviderTimeout(f"fixture-timeout-{len(calls)}")
            async with factory() as completion_session:
                runtime = AgentRuntimeService(completion_session)
                await runtime.append_message(
                    session_id=(await runtime.get_run(run_id, 1510)).session_id,
                    user_id=1510,
                    role="assistant",
                    content="重放后仅保存这一条最终可见回复。",
                )
                await runtime.update_run(
                    run_id=run_id,
                    user_id=1510,
                    status="completed",
                    phase="summary",
                    progress=100,
                )
                await runtime.append_event(
                    run_id=run_id,
                    user_id=1510,
                    event_type="assistant_completed",
                    summary="fixture visible response completed",
                    data={},
                )
                await runtime.append_event(
                    run_id=run_id,
                    user_id=1510,
                    event_type="run_completed",
                    summary="fixture run completed",
                    data={},
                )

        monkeypatch.setattr("app.agent.worker._run_visible_response", fake_visible_runner)
        worker = AgentWorker(
            factory,
            worker_id="visible-response-retry-worker",
            handlers={"visible_response": handle_visible_response_job},
        )

        assert await worker.poll_once() is True
        async with factory() as session:
            runtime = AgentRuntimeService(session)
            job = await AgentJobService(session).get_job(job_id=job_id, user_id=1510)
            run = await runtime.get_run(run_id, 1510)
            assert (job.status, job.attempt_count, job.error_type) == ("queued", 1, "ProviderTimeout")
            assert run.status == "running"
            job.available_at = AgentJobService._now()
            await session.commit()

        assert await worker.poll_once() is True
        async with factory() as session:
            runtime = AgentRuntimeService(session)
            job = await AgentJobService(session).get_job(job_id=job_id, user_id=1510)
            run = await runtime.get_run(run_id, 1510)
            assert (job.status, job.attempt_count, job.error_type) == ("dead_letter", 2, "ProviderTimeout")
            assert run.status == "running"
            replayed = await AgentJobService(session).replay_dead_letter(
                job_id=job_id,
                operator_id=9001,
                reason="fixture provider recovered",
            )
            assert (replayed.status, replayed.attempt_count) == ("queued", 2)

        assert await worker.poll_once() is True
        assert await worker.poll_once() is False

        async with factory() as session:
            runtime = AgentRuntimeService(session)
            job = await AgentJobService(session).get_job(job_id=job_id, user_id=1510)
            run = await runtime.get_run(run_id, 1510)
            messages = await runtime.list_messages(session_id=run.session_id, user_id=1510)
            events = await runtime.list_events(run_id=run_id, user_id=1510)
            event_types = [event.event_type for event in events]
            assert (job.status, job.attempt_count) == ("succeeded", 3)
            assert run.status == "completed"
            assert [(message.role, message.content) for message in messages] == [
                ("assistant", "重放后仅保存这一条最终可见回复。"),
            ]
            assert event_types.count("job_replayed") == 1
            assert event_types.count("assistant_completed") == 1
            assert event_types.count("run_completed") == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_visible_response_provider_retry_uses_real_runner_and_completes_once(tmp_path, monkeypatch):
    """A retryable provider failure must leave the Run claimable for the next Worker."""
    engine, factory = await _factory(tmp_path)
    try:
        run_id, job_id = await _run(factory, 1511, kind="visible_response", max_attempts=2)
        async with factory() as session:
            runtime = AgentRuntimeService(session)
            run = await runtime.update_run(
                run_id=run_id,
                user_id=1511,
                status="running",
                phase="assistant_response",
                progress=85,
            )

        attempts = 0

        class RetryVisibleLLM:
            def __init__(self, _session):
                pass

            async def stream_visible_response(self, **kwargs):
                nonlocal attempts
                attempts += 1
                ledger = kwargs["attempt_ledger"]
                record = ledger.begin(
                    role=kwargs["attempt_role"],
                    provider_ref="retry-fixture",
                    model_ref="retry-model",
                    retry_index=attempts - 1,
                )
                if attempts == 1:
                    ledger.fail(record.attempt_id, ProviderTimeout("fixture-provider-timeout"))
                    if False:
                        yield ""
                    raise ProviderTimeout("fixture-provider-timeout")
                ledger.finish(record.attempt_id, output="重试后只生成这一条最终可见回复。")
                yield "重试后只生成这一条最终可见回复。"

        monkeypatch.setattr("app.agent.runner.AsyncSessionLocal", factory)
        monkeypatch.setattr("app.agent.runner.LLMService", RetryVisibleLLM)
        worker = AgentWorker(
            factory,
            worker_id="visible-response-real-retry-worker",
            handlers={"visible_response": handle_visible_response_job},
        )

        assert await worker.poll_once() is True
        async with factory() as session:
            runtime = AgentRuntimeService(session)
            job = await AgentJobService(session).get_job(job_id=job_id, user_id=1511)
            retry_run = await runtime.get_run(run_id, 1511)
            messages = await runtime.list_messages(session_id=run.session_id, user_id=1511)
            events = await runtime.list_events(run_id=run_id, user_id=1511)
            event_types = [event.event_type for event in events]
            assert (job.status, job.attempt_count, job.error_type) == ("queued", 1, "ProviderTimeout")
            assert (retry_run.status, retry_run.current_phase) == ("running", "assistant_response_retry")
            assert messages == []
            assert event_types.count("visible_response_retry_pending") == 1
            retry_event = next(event for event in events if event.event_type == "visible_response_retry_pending")
            assert retry_event.data_json["action_id"] == "response:retry"
            assert retry_event.data_json["result_ref"] == f"response:{run_id}"
            assert event_types.count("assistant_completed") == 0
            assert event_types.count("run_completed") == 0
            job.available_at = AgentJobService._now()
            await session.commit()

        assert await worker.poll_once() is True
        assert await worker.poll_once() is False

        async with factory() as session:
            runtime = AgentRuntimeService(session)
            job = await AgentJobService(session).get_job(job_id=job_id, user_id=1511)
            completed_run = await runtime.get_run(run_id, 1511)
            messages = await runtime.list_messages(session_id=run.session_id, user_id=1511)
            events = await runtime.list_events(run_id=run_id, user_id=1511)
            event_types = [event.event_type for event in events]
            assert attempts == 2
            assert (job.status, job.attempt_count) == ("succeeded", 2)
            assert completed_run.status == "completed"
            assert [(message.role, message.content) for message in messages] == [
                ("assistant", "重试后只生成这一条最终可见回复。"),
            ]
            snapshot = completed_run.context_json["response_provider_attempts"]
            assert [item["status"] for item in snapshot["provider_attempts"]] == ["failed", "succeeded"]
            assert [item["error_category"] for item in snapshot["provider_attempts"][:1]] == ["TIMEOUT"]
            assert snapshot["selected_provider_attempt"] == 2
            assistant_events = [event for event in events if event.event_type in {"assistant_started", "assistant_delta", "assistant_completed"}]
            assert assistant_events
            assert all(event.data_json.get("action_id") for event in assistant_events)
            assert all(event.data_json.get("result_ref") == f"response:{run_id}" for event in assistant_events)
            assert event_types.count("visible_response_retry_pending") == 1
            assert event_types.count("assistant_completed") == 1
            assert event_types.count("run_completed") == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_worker_settles_expired_visible_response_ack_after_atomic_completion(tmp_path):
    engine, factory = await _factory(tmp_path)
    try:
        run_id, job_id = await _run(factory, 1512, kind="visible_response")
        async with factory() as session:
            runtime = AgentRuntimeService(session)
            run = await runtime.update_run(run_id=run_id, user_id=1512, status="running", phase="assistant_response")
            job = await AgentJobService(session).claim_job(
                job_id=job_id, user_id=1512, lease_owner="crashed-after-finalize", lease_seconds=60
            )
            await runtime.finalize_visible_response(
                run_id=run_id,
                user_id=1512,
                session_id=run.session_id,
                content="原子完成后等待 Job 确认。",
                completion_data={"phase": "summary", "length": 12, "provider_called": True, "response_provider_called": True, "response_provider_fallback_reason": None},
            )
            # A prior retry can leave diagnostic failure fields on the durable Job.
            # Atomic completion recovery must not surface that stale Provider failure as
            # the final state of an acknowledged success.
            job.error_type = "ProviderTimeout"
            job.error_detail = "first provider attempt timed out"
            job.lease_expires_at = AgentJobService._now() - timedelta(seconds=1)
            await session.commit()

        worker = AgentWorker(factory, worker_id="ack-reconciler", handlers={})
        assert await worker.poll_once() is True
        assert await worker.poll_once() is False

        async with factory() as session:
            runtime = AgentRuntimeService(session)
            job = await AgentJobService(session).get_job(job_id=job_id, user_id=1512)
            run = await runtime.get_run(run_id, 1512)
            messages = await runtime.list_messages(session_id=run.session_id, user_id=1512)
            events = await runtime.list_events(run_id=run_id, user_id=1512)
            assert job.status == "succeeded"
            assert job.result_json == {"visible_response_job_id": job_id}
            assert job.error_type is None
            assert job.error_detail is None
            assert run.status == "completed"
            assert len(messages) == 1
            assert [event.event_type for event in events].count("assistant_completed") == 1
            assert [event.event_type for event in events].count("run_completed") == 1
    finally:
        await engine.dispose()

@pytest.mark.asyncio
async def test_worker_settles_expired_execution_ack_after_completed_visible_response_handoff(tmp_path):
    engine, factory = await _factory(tmp_path)
    try:
        run_id, execution_job_id = await _run(factory, 1513, kind="agent_execution")
        async with factory() as session:
            runtime = AgentRuntimeService(session)
            jobs = AgentJobService(session)
            run = await runtime.update_run(
                run_id=run_id, user_id=1513, status="running", phase="assistant_response"
            )
            execution_job = await jobs.claim_job(
                job_id=execution_job_id, user_id=1513, lease_owner="crashed-after-handoff", lease_seconds=60
            )
            visible_job = await jobs.create_job(
                run_id=run_id,
                user_id=1513,
                project_id=run.project_id,
                kind="visible_response",
                idempotency_key=f"{run_id}:visible_response",
                payload={"goal": "交接确认", "tool_results": []},
            )
            visible_claim = await jobs.claim_job(
                job_id=visible_job.id, user_id=1513, lease_owner="visible-response-worker", lease_seconds=60
            )
            await jobs.complete(
                job_id=visible_job.id,
                user_id=1513,
                lease_owner="visible-response-worker",
                lease_generation=visible_claim.lease_generation,
                result={"visible_response_job_id": visible_job.id},
            )
            await runtime.set_run_context(
                run_id=run_id,
                user_id=1513,
                context={
                    **dict(run.context_json or {}),
                    "execution_job_id": execution_job_id,
                    "visible_response_job_id": visible_job.id,
                    "job_id": visible_job.id,
                },
            )
            await runtime.finalize_visible_response(
                run_id=run_id,
                user_id=1513,
                session_id=run.session_id,
                content="可见回复已经完成，等待执行阶段确认收敛。",
                completion_data={"phase": "summary", "length": 18, "provider_called": True},
            )
            execution_job.error_type = "ProviderTimeout"
            execution_job.error_detail = "stale retry diagnostic"
            execution_job.lease_expires_at = AgentJobService._now() - timedelta(seconds=1)
            await session.commit()

        worker = AgentWorker(factory, worker_id="execution-ack-reconciler", handlers={})
        assert await worker.poll_once() is True
        assert await worker.poll_once() is False

        async with factory() as session:
            runtime = AgentRuntimeService(session)
            jobs = AgentJobService(session)
            execution_job = await jobs.get_job(job_id=execution_job_id, user_id=1513)
            saved_visible_job = await jobs.get_job(job_id=visible_job.id, user_id=1513)
            run = await runtime.get_run(run_id, 1513)
            messages = await runtime.list_messages(session_id=run.session_id, user_id=1513)
            events = await runtime.list_events(run_id=run_id, user_id=1513)
            assert execution_job.status == "succeeded"
            assert execution_job.lease_owner is None
            assert execution_job.lease_expires_at is None
            assert execution_job.error_type is None
            assert execution_job.error_detail is None
            assert execution_job.result_json == {
                "status": "assistant_queued",
                "visible_response_job_id": saved_visible_job.id,
                "reconciled_after_handoff": True,
            }
            assert saved_visible_job.status == "succeeded"
            assert run.status == "completed"
            assert len(messages) == 1
            assert [event.event_type for event in events].count("assistant_completed") == 1
            assert [event.event_type for event in events].count("run_completed") == 1
    finally:
        await engine.dispose()
