import asyncio

import pytest
from fastapi import BackgroundTasks

from app.api.routers import research
from app.schemas.research import ResearchArtifactRead, ResearchRunRequest
from app.schemas.user import UserInDB


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def clear_research_jobs():
    research._RESEARCH_JOBS.clear()
    research._RESEARCH_TASKS.clear()
    yield
    research._RESEARCH_JOBS.clear()
    research._RESEARCH_TASKS.clear()


class _OwnerService:
    def __init__(self, _session):
        pass

    async def ensure_project_owner(self, _project_id, _user_id):
        return object()


class _ResearchService:
    def __init__(self, _session):
        pass

    async def get_or_create_config(self, _project_id):
        return object()

    @staticmethod
    def should_run(_config, _scope, **_kwargs):
        return True, "forced"

    async def get_active_artifact(self, _project_id, _scope, _chapter_number):
        return None

    async def get_artifact(self, _project_id, _run_id):
        return None

    async def touch_artifact_heartbeat(self, _project_id, _run_id, *, status=None):
        return None

    async def create_pending_artifact(self, **kwargs):
        return ResearchArtifactRead(
            id=1, run_id=kwargs["run_id"], project_id=kwargs["project_id"],
            scope=kwargs["scope"], chapter_number=kwargs["chapter_number"],
            status="queued", trigger=kwargs["trigger"],
        )

    async def mark_artifact_cancelled(self, project_id, run_id):
        return ResearchArtifactRead(
            id=1, run_id=run_id, project_id=project_id, scope="global",
            status="cancelled", trigger="manual_ui",
        )


@pytest.mark.anyio
async def test_manual_research_job_start_status_and_queued_cancel(monkeypatch):
    monkeypatch.setattr(research, "NovelService", _OwnerService)
    monkeypatch.setattr(research, "ProjectResearchService", _ResearchService)
    user = UserInDB(id=7, username="owner", email=None, hashed_password="x")
    background = BackgroundTasks()

    started = await research.start_research_job(
        "project-1", ResearchRunRequest(scope="global", consent=True, force=True),
        background, object(), user,
    )
    assert started.status == "queued"
    assert started.artifact and started.artifact.status == "queued"
    assert len(background.tasks) == 1

    status = await research.get_research_job_status("project-1", started.run_id, object(), user)
    assert status.run_id == started.run_id
    assert status.status == "queued"

    cancelled = await research.cancel_research_job("project-1", started.run_id, object(), user)
    assert cancelled.status == "cancelled"
    assert cancelled.cancel_signal_sent is False
    assert cancelled.artifact and cancelled.artifact.status == "cancelled"


@pytest.mark.anyio
async def test_manual_research_cancel_sends_signal_to_registered_task(monkeypatch):
    monkeypatch.setattr(research, "NovelService", _OwnerService)
    monkeypatch.setattr(research, "ProjectResearchService", _ResearchService)
    user = UserInDB(id=7, username="owner", email=None, hashed_password="x")
    run_id = "run-active"
    sleeper = asyncio.create_task(asyncio.sleep(60))
    research._RESEARCH_JOBS[run_id] = {
        "run_id": run_id, "project_id": "project-1", "scope": "global",
        "chapter_number": None, "status": "running", "artifact": None,
    }
    research._RESEARCH_TASKS[run_id] = sleeper

    cancelled = await research.cancel_research_job("project-1", run_id, object(), user)
    assert cancelled.cancel_signal_sent is True
    assert cancelled.in_process_task_cancelled is True
    await asyncio.sleep(0)
    assert sleeper.cancelled()
@pytest.mark.anyio
async def test_manual_research_cancel_recovers_database_job_after_restart(monkeypatch):
    artifact = ResearchArtifactRead(
        id=2, run_id="persisted-run", project_id="project-1", scope="chapter",
        chapter_number=8, status="running", trigger="manual_ui",
    )

    class _RestartedResearchService(_ResearchService):
        async def get_artifact(self, project_id, run_id):
            assert (project_id, run_id) == ("project-1", "persisted-run")
            return artifact

        async def mark_artifact_cancelled(self, project_id, run_id):
            return artifact.model_copy(update={"status": "cancelled"})

    monkeypatch.setattr(research, "NovelService", _OwnerService)
    monkeypatch.setattr(research, "ProjectResearchService", _RestartedResearchService)
    user = UserInDB(id=7, username="owner", email=None, hashed_password="x")

    cancelled = await research.cancel_research_job("project-1", "persisted-run", object(), user)

    assert cancelled.status == "cancelled"
    assert cancelled.cancel_signal_sent is False
    assert cancelled.in_process_task_cancelled is False
    assert cancelled.artifact and cancelled.artifact.status == "cancelled"


@pytest.mark.anyio
async def test_manual_research_start_rejects_duplicate_active_scope(monkeypatch):
    active = ResearchArtifactRead(
        id=3, run_id="already-running", project_id="project-1", scope="global",
        status="running", trigger="manual_ui",
    )

    class _BusyResearchService(_ResearchService):
        async def get_active_artifact(self, _project_id, _scope, _chapter_number):
            return active

    monkeypatch.setattr(research, "NovelService", _OwnerService)
    monkeypatch.setattr(research, "ProjectResearchService", _BusyResearchService)
    user = UserInDB(id=7, username="owner", email=None, hashed_password="x")

    with pytest.raises(Exception) as exc_info:
        await research.start_research_job(
            "project-1", ResearchRunRequest(scope="global", consent=True, force=True),
            BackgroundTasks(), object(), user,
        )

    assert getattr(exc_info.value, "status_code", None) == 409
    assert exc_info.value.detail["code"] == "RESEARCH_ALREADY_RUNNING"
    assert exc_info.value.detail["run_id"] == "already-running"