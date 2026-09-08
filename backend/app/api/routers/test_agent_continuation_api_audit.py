"""Real continuation API contracts; unfixed regressions intentionally remain red.
No skipped/xfail cases, workflow patches, live DB access, or replay requests.
"""
from __future__ import annotations
import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4
import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from app.api.routers import agent as routes
from app.core.dependencies import get_current_user
from app.db.session import get_session
from app.main import app
from app.models import NovelProject, ProjectMember, ProjectMemberRole, User
from app.models.agent import AgentJob
from app.services.agent_runtime import AgentRuntimeService

pytestmark = pytest.mark.asyncio
SECRET = "CONTINUATION_AUDIT_PRIVATE_SENTINEL"

@pytest.fixture
async def audit(task_session, monkeypatch):
    users = {}
    for i, name in enumerate(("owner", "viewer", "outsider", "admin"), 19701):
        users[name] = User(id=i, username=f"continuation-api-{name}",
            email=f"continuation-api-{name}@example.com", hashed_password="fixture",
            is_active=True, is_admin=name == "admin")
    task_session.add_all(users.values())
    project = NovelProject(id="continuation-api-project", user_id=users["owner"].id, title="API audit")
    other_project = NovelProject(id="continuation-api-other-project", user_id=users["outsider"].id, title="Other")
    member = ProjectMember(project_id=project.id, user_id=users["viewer"].id, role=ProjectMemberRole.viewer.value)
    task_session.add_all([project, other_project, member])
    await task_session.commit()
    runtime = AgentRuntimeService(task_session)
    conversation = await runtime.create_session(user_id=users["owner"].id, project_id=project.id)
    run = await runtime.create_run(session_id=conversation.id, user_id=users["owner"].id, project_id=project.id)
    principal = {"name": "owner"}
    async def current_user():
        return users[principal["name"]]
    async def session_override():
        yield task_session
    monkeypatch.setitem(app.dependency_overrides, get_current_user, current_user)
    monkeypatch.setitem(app.dependency_overrides, get_session, session_override)
    monkeypatch.setattr(routes, "AsyncSessionLocal", async_sessionmaker(task_session.bind, expire_on_commit=False))
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)
    async with httpx.AsyncClient(transport=transport, base_url="http://continuation-api") as client:
        async def get(path, *, actor="owner", **kwargs):
            principal["name"] = actor
            return await client.get(path, **kwargs)
        async def job(*, status="blocked", **changes):
            fields = dict(id=str(uuid4()), run_id=run.id, user_id=run.user_id,
                project_id=run.project_id, correlation_id=run.correlation_id,
                transaction_id=run.transaction_id, kind="agent_continuation", status=status,
                idempotency_key=str(uuid4()), payload_json={}, result_json={}, attempt_count=0, max_attempts=3)
            fields.update(changes)
            row = AgentJob(**fields)
            task_session.add(row)
            await task_session.commit()
            await task_session.refresh(row)
            return row
        yield SimpleNamespace(db=task_session, runtime=runtime, users=users, project=project,
            other_project=other_project, member=member, run=run, conversation=conversation, get=get, job=job,
            state=f"/api/agent/runs/{run.id}/state",
            events=f"/api/agent/sessions/{conversation.id}/runs/{run.id}/events",
            stream=f"/api/agent/sessions/{conversation.id}/runs/{run.id}/stream")

@pytest.mark.parametrize("status", ["blocked", "queued", "running", "completed", "failed", "cancelled", "dead_letter"])
async def test_continuation_status_visible_without_mutation(audit, status):
    row = await audit.job(status=status, error_type="ContinuationConflict" if status in {"failed", "dead_letter"} else None)
    before = (row.status, row.attempt_count, row.lease_generation, row.updated_at, dict(row.result_json))
    listed = await audit.get("/api/agent/jobs", params={"status": status, "project_id": audit.project.id})
    assert listed.status_code == 200
    assert [j["id"] for j in listed.json()] == [row.id]
    state = await audit.get(audit.state)
    assert state.status_code == 200
    assert state.json()["jobs"][0]["status"] == status
    assert state.json()["terminal_status"] is None  # Terminal Job is not a terminal Run.
    if row.error_type:
        assert state.json()["blocked_reason"] == row.error_type
    await audit.db.refresh(row)
    assert (row.status, row.attempt_count, row.lease_generation, row.updated_at, row.result_json) == before

async def test_jobs_owner_and_project_filter(audit):
    row = await audit.job()
    assert (await audit.get("/api/agent/jobs", actor="outsider")).json() == []
    assert (await audit.get("/api/agent/jobs", params={"project_id": audit.other_project.id})).json() == []
    assert (await audit.get("/api/agent/jobs", params={"project_id": audit.project.id})).json()[0]["id"] == row.id

async def test_viewer_can_read_state_but_jobs_remain_owner_only(audit):
    row = await audit.job(status="dead_letter", error_type="RuntimeError")
    response = await audit.get(audit.state, actor="viewer")
    assert response.status_code == 200
    assert response.json()["jobs"][0]["id"] == row.id
    assert response.json()["allowed_commands"] == []
    assert (await audit.get("/api/agent/jobs", actor="viewer")).json() == []

@pytest.mark.parametrize("endpoint", ["state", "events", "stream"])
async def test_outsider_is_denied_before_response(audit, endpoint):
    await audit.job()
    response = await audit.get(getattr(audit, endpoint), actor="outsider")
    assert response.status_code in {403, 404}
    assert audit.run.correlation_id not in response.text

@pytest.mark.parametrize("endpoint", ["state", "events", "stream"])
async def test_revoked_viewer_is_denied(audit, endpoint):
    audit.member.deleted_at = datetime.now(timezone.utc)
    await audit.db.commit()
    response = await audit.get(getattr(audit, endpoint), actor="viewer")
    assert response.status_code in {403, 404}

async def test_projectless_run_stays_private(audit):
    conversation = await audit.runtime.create_session(user_id=audit.users["owner"].id)
    run = await audit.runtime.create_run(session_id=conversation.id, user_id=audit.users["owner"].id)
    response = await audit.get(f"/api/agent/runs/{run.id}/state", actor="viewer")
    assert response.status_code == 404

@pytest.mark.parametrize("dimension", ["user_id", "correlation_id", "run_id"])
async def test_state_excludes_foreign_job_dimensions(audit, dimension):
    other = await audit.runtime.create_run(session_id=audit.conversation.id, user_id=audit.users["owner"].id, project_id=audit.project.id)
    values = {"user_id": audit.users["outsider"].id, "correlation_id": str(uuid4()), "run_id": other.id}
    row = await audit.job(**{dimension: values[dimension]})
    response = await audit.get(audit.state)
    assert response.status_code == 200
    assert row.id not in {j["id"] for j in response.json()["jobs"]}

async def test_state_excludes_job_with_mismatched_project(audit):
    row = await audit.job(project_id=audit.other_project.id)
    response = await audit.get(audit.state, actor="viewer")
    assert response.status_code == 200
    assert row.id not in {j["id"] for j in response.json()["jobs"]}

@pytest.mark.parametrize("field,value", [
    ("payload_json", {"provider_token": SECRET}),
    ("result_json", {"private_context": {"prompt": SECRET}}),
    ("error_detail", f"Authorization: Bearer {SECRET}"),
    ("lease_owner", f"internal-host:{SECRET}"),
])
async def test_public_jobs_do_not_expose_private_fields(audit, field, value):
    await audit.job(**{field: value})
    response = await audit.get("/api/agent/jobs")
    assert response.status_code == 200
    assert SECRET not in response.text

async def test_state_omits_raw_job_payload_result_and_error_detail(audit):
    await audit.job(status="failed", payload_json={"token": SECRET}, result_json={"prompt": SECRET},
        error_detail=SECRET, lease_owner=SECRET, error_type="RuntimeError")
    response = await audit.get(audit.state, actor="viewer")
    assert response.status_code == 200
    assert SECRET not in response.text
    assert response.json()["blocked_reason"] == "RuntimeError"

async def test_public_jobs_offer_nonoverlapping_bounded_pages(audit):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = [await audit.job(created_at=start + timedelta(seconds=i)) for i in range(4)]
    first = await audit.get("/api/agent/jobs", params={"limit": 2, "offset": 0})
    second = await audit.get("/api/agent/jobs", params={"limit": 2, "offset": 2})
    assert first.status_code == second.status_code == 200
    first_ids, second_ids = [j["id"] for j in first.json()], [j["id"] for j in second.json()]
    assert len(first_ids) == len(second_ids) == 2
    assert set(first_ids).isdisjoint(second_ids)
    assert set(first_ids + second_ids) == {r.id for r in rows}

@pytest.mark.parametrize("query", [{"limit": 0}, {"limit": 201}, {"offset": -1}])
async def test_public_jobs_validate_pagination(audit, query):
    assert (await audit.get("/api/agent/jobs", params=query)).status_code == 422

async def test_dead_letter_list_requires_admin(audit):
    row = await audit.job(status="dead_letter", attempt_count=3)
    assert (await audit.get("/api/agent/dead-letters")).status_code == 403
    response = await audit.get("/api/agent/dead-letters", actor="admin")
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [row.id]
    assert response.json()[0]["attempt_count"] == 3

async def test_recovery_result_currently_queryable_from_owner_job(audit):
    """Observed capability, not proof that the worker performed recovery."""
    row = await audit.job(status="completed", result_json={"continuation_completed": True, "pending_approval": False})
    response = await audit.get("/api/agent/jobs", params={"status": "completed"})
    assert response.status_code == 200
    assert response.json()[0]["id"] == row.id
    assert response.json()[0]["result_json"]["continuation_completed"] is True
    assert response.json()[0]["recovery_status"] == "continuation_completed"
    state = (await audit.get(audit.state)).json()
    assert state["jobs"][0]["status"] == "completed"
    assert state["status"] == "created"

async def test_continuation_events_pagination_sse_and_last_event_id(audit):
    events = []
    for event_type, data in [
        ("plan_step_blocked", {"step": 2, "reason": "dependency_waiting", "dependencies": [1], "phase": "continuation"}),
        ("plan_step_cancelled", {"step": 3, "reason": "dependency_cancelled", "dependencies": [2], "phase": "continuation"}),
        ("run_failed", {"error_type": "RuntimeError", "phase": "continuation"}),
    ]:
        events.append(await audit.runtime.append_event(run_id=audit.run.id, user_id=audit.run.user_id,
            event_type=event_type, summary=event_type, data={**data, "provider_token": SECRET, "error_detail": SECRET}))
    audit.run.status = "failed"
    await audit.db.commit()
    first = await audit.get(audit.events, params={"after_sequence": events[0].sequence - 1, "limit": 2})
    second = await audit.get(audit.events, params={"after_sequence": events[1].sequence, "limit": 2})
    assert first.status_code == second.status_code == 200
    assert [e["sequence"] for e in first.json()] == [e.sequence for e in events[:2]]
    assert [e["sequence"] for e in second.json()] == [events[2].sequence]
    state = (await audit.get(audit.state, actor="viewer")).json()
    assert state["resume_after_sequence"] == state["last_event_sequence"] == events[-1].sequence
    response = await audit.get(audit.stream, actor="viewer", params={"after_sequence": 0},
        headers={"Last-Event-ID": str(events[0].sequence)})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    frames = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    assert [frame["sequence"] for frame in frames] == [e.sequence for e in events[1:]]
    assert frames[0]["data"]["dependencies"] == [2]
    assert frames[-1]["data"]["error_type"] == "RuntimeError"
    assert SECRET not in first.text + second.text + response.text

@pytest.mark.parametrize("terminal", ["completed", "failed", "cancelled", "dead_letter", "succeeded"])
async def test_sse_closes_for_every_state_projection_terminal(audit, terminal):
    audit.run.status = terminal
    await audit.db.commit()
    state = (await audit.get(audit.state)).json()
    assert state["terminal_status"] == terminal
    class ConnectedRequest:
        headers = {}
        async def is_disconnected(self):
            return False
    response = await routes.stream_agent_events(audit.conversation.id, audit.run.id,
        ConnectedRequest(), after_sequence=state["last_event_sequence"], current_user=audit.users["owner"])
    iterator, closed = response.body_iterator, False
    try:
        try:
            await asyncio.wait_for(anext(iterator), timeout=0.25)
        except StopAsyncIteration:
            closed = True
        except asyncio.TimeoutError:
            pass
    finally:
        await iterator.aclose()
    assert closed, f"state reports terminal {terminal!r}, but SSE continues polling"

@pytest.mark.parametrize('endpoint', ['state', 'jobs'])
async def test_job_projection_excludes_mismatched_transaction(audit, endpoint):
    row=await audit.job(transaction_id=str(uuid4()))
    response=await audit.get(audit.state if endpoint=='state' else '/api/agent/jobs')
    assert response.status_code==200
    jobs=response.json()['jobs'] if endpoint=='state' else response.json()
    assert row.id not in {j['id'] for j in jobs}

async def test_run_filtered_job_query_uses_current_project_read_access(audit):
    row=await audit.job()
    response=await audit.get('/api/agent/jobs',actor='viewer',params={'run_id':audit.run.id,'kind':'agent_continuation'})
    assert response.status_code==200 and [item['id'] for item in response.json()]==[row.id]
    assert (await audit.get('/api/agent/jobs',actor='outsider',params={'run_id':audit.run.id})).status_code in {403,404}
    audit.member.deleted_at=datetime.now(timezone.utc);await audit.db.commit()
    assert (await audit.get('/api/agent/jobs',actor='viewer',params={'run_id':audit.run.id})).status_code in {403,404}

async def test_run_filtered_job_query_rejects_conflicting_project(audit):
    await audit.job()
    response=await audit.get('/api/agent/jobs',params={'run_id':audit.run.id,'project_id':audit.other_project.id})
    assert response.status_code in {403,404}

async def test_run_and_kind_filters_do_not_mix_unrelated_jobs(audit):
    wanted=await audit.job()
    await audit.job(kind='agent_execution')
    other=await audit.runtime.create_run(session_id=audit.conversation.id,user_id=audit.users['owner'].id,project_id=audit.project.id)
    await audit.job(run_id=other.id,correlation_id=other.correlation_id,transaction_id=other.transaction_id)
    response=await audit.get('/api/agent/jobs',params={'run_id':audit.run.id,'kind':'agent_continuation'})
    assert response.status_code==200 and [item['id'] for item in response.json()]==[wanted.id]
