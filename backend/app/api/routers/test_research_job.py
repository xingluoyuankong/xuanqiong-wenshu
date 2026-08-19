import asyncio
from contextlib import asynccontextmanager

import pytest
from fastapi import BackgroundTasks

from app.api.routers import research
from app.schemas.research import ResearchArtifactRead, ResearchRunRequest
from app.schemas.task_runtime import TaskRuntimeStatus
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


class _SessionWithoutDb:
    """No `execute` attribute, so TaskRuntime writes are skipped by design."""


def _fake_session_factory(session):
    @asynccontextmanager
    async def factory():
        yield session

    return factory


@pytest.mark.anyio
async def test_cancel_running_research_job_enters_cancelling_not_terminal(monkeypatch):
    """取消仍在跑的研究任务只能进入 cancelling，且不得提前把工件写成终态。

    终态 cancelled 必须由 worker 收敛点写入，否则前端会在 worker 仍在执行时
    看到终态，取消与恢复语义失真。
    """
    marked_cancelled: list[str] = []
    running_artifact = ResearchArtifactRead(
        id=9, run_id="run-live", project_id="project-1", scope="global",
        status="running", trigger="manual_ui",
    )

    class _LiveResearchService(_ResearchService):
        async def get_artifact(self, _project_id, _run_id):
            return running_artifact

        async def mark_artifact_cancelled(self, _project_id, run_id):
            marked_cancelled.append(run_id)
            return running_artifact.model_copy(update={"status": "cancelled"})

    monkeypatch.setattr(research, "NovelService", _OwnerService)
    monkeypatch.setattr(research, "ProjectResearchService", _LiveResearchService)
    user = UserInDB(id=7, username="owner", email=None, hashed_password="x")
    run_id = "run-live"
    sleeper = asyncio.create_task(asyncio.sleep(60))
    research._RESEARCH_JOBS[run_id] = {
        "run_id": run_id, "project_id": "project-1", "scope": "global",
        "chapter_number": None, "status": "running", "artifact": None,
    }
    research._RESEARCH_TASKS[run_id] = sleeper

    result = await research.cancel_research_job("project-1", run_id, object(), user)

    assert result.status == TaskRuntimeStatus.CANCELLING.value
    assert result.cancel_signal_sent is True
    assert result.in_process_task_cancelled is True
    # 关键断言：worker 未收敛前不得写终态工件。
    assert marked_cancelled == []
    assert result.artifact is not None and result.artifact.status == "running"
    assert research._RESEARCH_JOBS[run_id]["status"] == TaskRuntimeStatus.CANCELLING.value

    await asyncio.sleep(0)
    assert sleeper.cancelled()


@pytest.mark.anyio
async def test_research_worker_converges_cancelling_into_cancelled(monkeypatch):
    """worker 收到 CancelledError 后才把工件与内存态收敛到终态 cancelled。"""
    marked_cancelled: list[str] = []
    started = asyncio.Event()

    class _BlockingResearchService(_ResearchService):
        async def run_research(self, **_kwargs):
            started.set()
            await asyncio.sleep(60)
            raise AssertionError("研究任务不应正常完成")

        async def mark_artifact_cancelled(self, _project_id, run_id):
            marked_cancelled.append(run_id)
            return None

    monkeypatch.setattr(research, "ProjectResearchService", _BlockingResearchService)
    monkeypatch.setattr(research, "AsyncSessionLocal", _fake_session_factory(_SessionWithoutDb()))

    run_id = "run-converge"
    research._RESEARCH_JOBS[run_id] = {
        "run_id": run_id, "project_id": "project-1", "scope": "global",
        "chapter_number": None, "status": TaskRuntimeStatus.CANCELLING.value, "artifact": None,
    }

    worker = asyncio.create_task(
        research._run_research_job(
            run_id, "project-1", 7, ResearchRunRequest(scope="global", consent=True, force=True)
        )
    )
    # cancelling 状态下 worker 必须直接退出，不得把状态改回 running。
    await worker
    assert research._RESEARCH_JOBS[run_id]["status"] == TaskRuntimeStatus.CANCELLING.value
    assert started.is_set() is False

    # 再验证真正在跑的 worker 被取消时会收敛到终态。
    research._RESEARCH_JOBS[run_id]["status"] = "queued"
    worker = asyncio.create_task(
        research._run_research_job(
            run_id, "project-1", 7, ResearchRunRequest(scope="global", consent=True, force=True)
        )
    )
    await asyncio.wait_for(started.wait(), timeout=5)
    worker.cancel()
    with pytest.raises(asyncio.CancelledError):
        await worker

    assert marked_cancelled == [run_id]
    assert research._RESEARCH_JOBS[run_id]["status"] == "cancelled"


@pytest.mark.anyio
async def test_runtime_backed_research_worker_recovers_after_memory_cache_is_cleared(monkeypatch):
    """TaskRuntime 领取成功后，重启清空内存缓存不能让 worker 静默退出。"""
    calls: list[str] = []

    class _RecoveredResearchService(_ResearchService):
        async def run_research(self, **kwargs):
            calls.append(kwargs["run_id"])
            return ResearchArtifactRead(
                id=21, run_id=kwargs["run_id"], project_id=kwargs["project_id"],
                scope=kwargs["scope"], chapter_number=kwargs["chapter_number"],
                status="completed", trigger="manual_ui",
            )

    monkeypatch.setattr(research, "ProjectResearchService", _RecoveredResearchService)
    monkeypatch.setattr(research, "AsyncSessionLocal", _fake_session_factory(_SessionWithoutDb()))

    async def claimed(_run_id, _project_id, _user_id):
        return True

    async def not_cancelled(_run_id, _project_id, _user_id):
        return False

    async def persisted_event(*_args, **_kwargs):
        return True

    monkeypatch.setattr(research, "_claim_research_runtime", claimed)
    monkeypatch.setattr(research, "_research_is_cancelled", not_cancelled)
    monkeypatch.setattr(research, "_runtime_event", persisted_event)

    # 模拟进程重启：没有 _RESEARCH_JOBS，只有持久化 TaskRuntime 可用于恢复。
    assert research._RESEARCH_JOBS == {}
    await research._run_research_job(
        "runtime-only-run", "project-1", 7,
        ResearchRunRequest(scope="global", consent=True, force=True),
    )

    assert calls == ["runtime-only-run"]
    assert "runtime-only-run" not in research._RESEARCH_TASKS


@pytest.mark.anyio
async def test_research_status_uses_artifact_when_runtime_is_missing(monkeypatch):
    """旧记录没有 TaskRuntime 时，内存快照不得覆盖持久化工件状态。"""
    artifact = ResearchArtifactRead(
        id=12, run_id="run-legacy", project_id="project-1", scope="global",
        status="queued", trigger="manual_ui",
    )

    class _LegacyResearchService(_ResearchService):
        async def get_artifact(self, project_id, run_id):
            return artifact

        async def mark_artifact_interrupted(self, project_id, run_id, *, force=False):
            assert force is True
            return artifact

    class _MissingRuntime:
        def __init__(self, _session):
            pass

        async def get_task(self, *_args, **_kwargs):
            raise research.TaskRuntimeNotFound("legacy task")

    class _DbSession:
        async def execute(self, *_args, **_kwargs):
            raise AssertionError("service stubs should handle the legacy lookup")

    monkeypatch.setattr(research, "NovelService", _OwnerService)
    monkeypatch.setattr(research, "ProjectResearchService", _LegacyResearchService)
    monkeypatch.setattr(research, "TaskRuntimeService", _MissingRuntime)
    research._RESEARCH_JOBS["run-legacy"] = {
        "run_id": "run-legacy", "project_id": "project-1", "scope": "global",
        "chapter_number": None, "status": "running", "artifact": artifact,
    }
    user = UserInDB(id=7, username="owner", email=None, hashed_password="x")

    result = await research.get_research_job_status(
        "project-1", "run-legacy", _DbSession(), user
    )

    assert result.status == "queued"


@pytest.mark.anyio
async def test_research_status_prefers_task_runtime_over_stale_memory(monkeypatch):
    """TaskRuntime 是状态真相源：内存里的 running 不得覆盖持久化的 cancelling。"""
    artifact = ResearchArtifactRead(
        id=11, run_id="run-truth", project_id="project-1", scope="global",
        status="running", trigger="manual_ui",
    )

    class _TruthResearchService(_ResearchService):
        async def get_artifact(self, _project_id, _run_id):
            return artifact

    class _RuntimeStub:
        def __init__(self, _session):
            pass

        async def get_task(self, task_id, _owner_user_id):
            assert task_id == "run-truth"
            return type("T", (), {
                "status": TaskRuntimeStatus.CANCELLING.value,
                "project_id": "project-1",
                "task_type": "research",
            })()

    class _DbSession:
        async def execute(self, *_args, **_kwargs):  # 仅用于通过 hasattr 检查
            raise AssertionError("不应直接执行 SQL")

    monkeypatch.setattr(research, "NovelService", _OwnerService)
    monkeypatch.setattr(research, "ProjectResearchService", _TruthResearchService)
    monkeypatch.setattr(research, "TaskRuntimeService", _RuntimeStub)
    user = UserInDB(id=7, username="owner", email=None, hashed_password="x")

    research._RESEARCH_JOBS["run-truth"] = {
        "run_id": "run-truth", "project_id": "project-1", "scope": "global",
        "chapter_number": None, "status": "running", "artifact": None,
    }

    status = await research.get_research_job_status(
        "project-1", "run-truth", _DbSession(), user
    )

    assert status.status == TaskRuntimeStatus.CANCELLING.value


@pytest.mark.anyio
async def test_research_cancel_prefers_persisted_running_runtime_after_restart(monkeypatch):
    """重启后没有本地句柄时，取消活跃租约只能请求取消，不能伪造终态。"""
    artifact = ResearchArtifactRead(
        id=13, run_id="persisted-live", project_id="project-1", scope="global",
        status="running", trigger="manual_ui",
    )
    marked_cancelled: list[str] = []

    class _PersistedResearchService(_ResearchService):
        async def get_artifact(self, _project_id, _run_id):
            return artifact

        async def mark_artifact_cancelled(self, _project_id, run_id):
            marked_cancelled.append(run_id)
            return artifact.model_copy(update={"status": "cancelled"})

    class _RuntimeStub:
        def __init__(self, _session):
            pass

        async def get_task(self, task_id, owner_user_id):
            assert (task_id, owner_user_id) == ("persisted-live", 7)
            return type("T", (), {
                "project_id": "project-1",
                "task_type": "research",
                "status": TaskRuntimeStatus.RUNNING.value,
                "payload": {"scope": "global"},
            })()

        async def request_cancel(self, task_id, *, owner_user_id, finalize_unclaimed):
            assert (task_id, owner_user_id, finalize_unclaimed) == ("persisted-live", 7, True)
            return type("T", (), {
                "project_id": "project-1",
                "task_type": "research",
                "status": TaskRuntimeStatus.CANCELLING.value,
                "payload": {"scope": "global"},
            })()

    class _DbSession:
        async def execute(self, *_args, **_kwargs):
            raise AssertionError("取消语义必须由 TaskRuntimeService 决定")

    monkeypatch.setattr(research, "NovelService", _OwnerService)
    monkeypatch.setattr(research, "ProjectResearchService", _PersistedResearchService)
    monkeypatch.setattr(research, "TaskRuntimeService", _RuntimeStub)
    user = UserInDB(id=7, username="owner", email=None, hashed_password="x")

    result = await research.cancel_research_job("project-1", "persisted-live", _DbSession(), user)

    assert result.status == TaskRuntimeStatus.CANCELLING.value
    assert result.cancel_signal_sent is False
    assert result.artifact is artifact
    assert marked_cancelled == []


@pytest.mark.anyio
async def test_research_status_rejects_runtime_from_another_project(monkeypatch):
    class _RuntimeStub:
        def __init__(self, _session):
            pass

        async def get_task(self, task_id, owner_user_id):
            assert (task_id, owner_user_id) == ("shared-run", 7)
            return type("T", (), {
                "project_id": "project-2",

                "task_type": "research",
                "status": TaskRuntimeStatus.QUEUED.value,
                "payload": {"scope": "global"},
            })()

    class _DbSession:
        async def execute(self, *_args, **_kwargs):
            raise AssertionError("TaskRuntimeService stub owns database access")

    monkeypatch.setattr(research, "NovelService", _OwnerService)
    monkeypatch.setattr(research, "ProjectResearchService", _ResearchService)
    monkeypatch.setattr(research, "TaskRuntimeService", _RuntimeStub)
    user = UserInDB(id=7, username="owner", email=None, hashed_password="x")

    with pytest.raises(Exception) as exc_info:
        await research.get_research_job_status(
            "project-1", "shared-run", _DbSession(), user
        )

    assert getattr(exc_info.value, "status_code", None) == 404


@pytest.mark.anyio
async def test_research_cancel_rejects_other_project_before_mutation(monkeypatch):
    cancel_calls: list[str] = []

    class _RuntimeStub:
        def __init__(self, _session):
            pass

        async def get_task(self, task_id, owner_user_id):
            return type("T", (), {
                "project_id": "project-2",

                "task_type": "research",
                "status": TaskRuntimeStatus.RUNNING.value,
            })()

        async def request_cancel(self, task_id, **_kwargs):
            cancel_calls.append(task_id)
            raise AssertionError("cross-project task must not be mutated")

    class _DbSession:
        async def execute(self, *_args, **_kwargs):
            raise AssertionError("TaskRuntimeService stub owns database access")

    monkeypatch.setattr(research, "NovelService", _OwnerService)
    monkeypatch.setattr(research, "ProjectResearchService", _ResearchService)
    monkeypatch.setattr(research, "TaskRuntimeService", _RuntimeStub)
    user = UserInDB(id=7, username="owner", email=None, hashed_password="x")

    with pytest.raises(Exception) as exc_info:
        await research.cancel_research_job(
            "project-1", "shared-run", _DbSession(), user
        )

    assert getattr(exc_info.value, "status_code", None) == 404
    assert cancel_calls == []


@pytest.mark.anyio
async def test_runtime_disappearance_stops_worker_before_research(monkeypatch):
    research_calls: list[str] = []
    interrupted: list[str] = []

    class _InterruptedResearchService(_ResearchService):
        async def run_research(self, **kwargs):
            research_calls.append(kwargs["run_id"])
            raise AssertionError("detached runtime must stop before research")

        async def mark_artifact_interrupted(self, project_id, run_id, *, force=False):
            assert (project_id, force) == ("project-1", True)
            interrupted.append(run_id)
            return None

    async def claimed(_run_id, _project_id, _user_id):
        return True

    async def detached(_run_id, _project_id, _user_id):
        raise research._ResearchRuntimeDetached("runtime deleted")

    monkeypatch.setattr(research, "ProjectResearchService", _InterruptedResearchService)
    monkeypatch.setattr(research, "AsyncSessionLocal", _fake_session_factory(_SessionWithoutDb()))
    monkeypatch.setattr(research, "_claim_research_runtime", claimed)
    monkeypatch.setattr(research, "_research_is_cancelled", detached)

    await research._run_research_job(
        "missing-runtime", "project-1", 7,
        ResearchRunRequest(scope="global", consent=True, force=True),
    )

    assert research_calls == []
    assert interrupted == ["missing-runtime"]


@pytest.mark.anyio
async def test_completion_event_loss_marks_research_interrupted_not_cancelled(monkeypatch):
    interrupted: list[str] = []
    cancelled: list[str] = []

    class _CompletionResearchService(_ResearchService):
        async def run_research(self, **kwargs):
            return ResearchArtifactRead(
                id=31, run_id=kwargs["run_id"], project_id=kwargs["project_id"],
                scope=kwargs["scope"], chapter_number=kwargs["chapter_number"],
                status="completed", trigger="manual_ui",
            )

        async def mark_artifact_interrupted(self, project_id, run_id, *, force=False):
            assert (project_id, force) == ("project-1", True)
            interrupted.append(run_id)
            return None

        async def mark_artifact_cancelled(self, _project_id, run_id):
            cancelled.append(run_id)
            return None

    async def claimed(_run_id, _project_id, _user_id):
        return True

    async def not_cancelled(_run_id, _project_id, _user_id):
        return False

    async def runtime_event(_session, _run_id, **kwargs):
        return kwargs["event_type"] != research.TaskRuntimeEventType.TASK_COMPLETED.value

    monkeypatch.setattr(research, "ProjectResearchService", _CompletionResearchService)
    monkeypatch.setattr(research, "AsyncSessionLocal", _fake_session_factory(_SessionWithoutDb()))
    monkeypatch.setattr(research, "_claim_research_runtime", claimed)
    monkeypatch.setattr(research, "_research_is_cancelled", not_cancelled)
    monkeypatch.setattr(research, "_runtime_event", runtime_event)

    await research._run_research_job(
        "lost-completion", "project-1", 7,
        ResearchRunRequest(scope="global", consent=True, force=True),
    )

    assert interrupted == ["lost-completion"]
    assert cancelled == []


@pytest.mark.anyio
async def test_database_status_does_not_fall_back_to_memory_without_runtime(monkeypatch):
    class _MissingRuntime:
        def __init__(self, _session):
            pass

        async def get_task(self, *_args, **_kwargs):
            raise research.TaskRuntimeNotFound("runtime missing")

    class _DbSession:
        async def execute(self, *_args, **_kwargs):
            raise AssertionError("TaskRuntimeService stub owns database access")

    monkeypatch.setattr(research, "NovelService", _OwnerService)
    monkeypatch.setattr(research, "ProjectResearchService", _ResearchService)
    monkeypatch.setattr(research, "TaskRuntimeService", _MissingRuntime)
    research._RESEARCH_JOBS["memory-only"] = {
        "run_id": "memory-only", "project_id": "project-1",
        "scope": "global", "chapter_number": None, "status": "running",
        "artifact": None,
    }
    user = UserInDB(id=7, username="owner", email=None, hashed_password="x")

    with pytest.raises(Exception) as exc_info:
        await research.get_research_job_status(
            "project-1", "memory-only", _DbSession(), user
        )

    assert getattr(exc_info.value, "status_code", None) == 404


@pytest.mark.anyio
async def test_research_cancel_rejects_same_project_non_research_runtime(monkeypatch):
    cancel_calls: list[str] = []

    class _RuntimeStub:
        def __init__(self, _session):
            pass

        async def get_task(self, task_id, owner_user_id):
            assert (task_id, owner_user_id) == ("style-run", 7)
            return type("T", (), {
                "project_id": "project-1",
                "task_type": "style_profile",
                "status": TaskRuntimeStatus.RUNNING.value,
            })()

        async def request_cancel(self, task_id, **_kwargs):
            cancel_calls.append(task_id)
            raise AssertionError("non-research runtime must not be mutated")

    class _DbSession:
        async def execute(self, *_args, **_kwargs):
            raise AssertionError("TaskRuntimeService stub owns database access")

    monkeypatch.setattr(research, "NovelService", _OwnerService)
    monkeypatch.setattr(research, "ProjectResearchService", _ResearchService)
    monkeypatch.setattr(research, "TaskRuntimeService", _RuntimeStub)
    user = UserInDB(id=7, username="owner", email=None, hashed_password="x")

    with pytest.raises(Exception) as exc_info:
        await research.cancel_research_job(
            "project-1", "style-run", _DbSession(), user
        )

    assert getattr(exc_info.value, "status_code", None) == 404
    assert cancel_calls == []
