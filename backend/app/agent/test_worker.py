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

        monkeypatch.setattr("app.agent.execution.AgentOrchestrator", lambda provider: FakePlanner())
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

        monkeypatch.setattr("app.agent.execution.AgentOrchestrator", lambda provider: FakePlanner())
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

        monkeypatch.setattr("app.agent.execution.AgentOrchestrator", lambda provider: FakePlanner())
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

        monkeypatch.setattr("app.agent.execution.AgentOrchestrator", lambda provider: FakePlanner())
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
