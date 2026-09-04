"""Writer background identity invariants.

The HTTP actor may differ from the durable execution owner after recovery.  These
regressions keep the TaskRuntime owner authoritative and preserve the complete
UserInDB principal across the AsyncSession boundary.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.api.routers import writer
from app.models import User
from app.models.task_runtime import TaskRuntime
from app.schemas.user import UserInDB
from app.services.task_runtime import TaskRuntimeService


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_args):
        return False


@pytest.mark.asyncio
async def test_worker_user_restore_preserves_admin_and_member_identity(task_session):
    admin = User(
        id=98101,
        username="identity-admin",
        email="identity-admin@example.com",
        hashed_password="admin-hash",
        is_admin=True,
        is_active=True,
    )
    member = User(
        id=98102,
        username="identity-member",
        email="identity-member@example.com",
        hashed_password="member-hash",
        is_admin=False,
        is_active=True,
    )
    task_session.add_all([admin, member])
    await task_session.commit()

    restored_admin = await writer._load_worker_user(
        task_session, admin.id, purpose="章节大纲生成"
    )
    restored_member = await writer._load_worker_user(
        task_session, member.id, purpose="章节大纲重写"
    )

    assert isinstance(restored_admin, UserInDB)
    assert restored_admin.id == admin.id
    assert restored_admin.username == admin.username
    assert restored_admin.email == admin.email
    assert restored_admin.hashed_password == admin.hashed_password
    assert restored_admin.is_admin is True
    assert restored_admin.is_active is True

    assert restored_member.id == member.id
    assert restored_member.username == member.username
    assert restored_member.email == member.email
    assert restored_member.hashed_password == member.hashed_password
    assert restored_member.is_admin is False
    assert restored_member.is_active is True


@pytest.mark.asyncio
@pytest.mark.parametrize("owner_is_admin", [True, False])
async def test_outline_worker_rebinds_actor_to_runtime_owner_and_identity(
    task_session, monkeypatch, owner_is_admin: bool
):
    owner_id = 98111 if owner_is_admin else 98112
    actor_id = 98113 if owner_is_admin else 98114
    owner = User(
        id=owner_id,
        username="outline-runtime-admin" if owner_is_admin else "outline-runtime-member",
        email=("outline-admin@example.com" if owner_is_admin else "outline-member@example.com"),
        hashed_password="outline-hash",
        is_admin=owner_is_admin,
        is_active=True,
    )
    actor = User(
        id=actor_id,
        username="outline-http-actor",
        email="outline-actor@example.com",
        hashed_password="actor-hash",
        is_admin=False,
        is_active=True,
    )
    task_session.add_all([owner, actor])
    await task_session.commit()
    await TaskRuntimeService(task_session).create_task(
        task_id=f"outline-identity-{owner_id}",
        task_type="chapter_outline_generation",
        owner_user_id=owner_id,
        project_id="outline-identity-project",
        payload={"run_id": f"outline-identity-{owner_id}"},
    )

    captured: dict[str, object] = {}
    claimed: list[int] = []

    async def _claim_outline_runtime(run_id: str, execution_owner_id: int) -> bool:
        claimed.append(execution_owner_id)
        return True

    async def _false() -> bool:
        return False

    async def _noop(*_args, **_kwargs):
        return None

    async def _set_state(run_id: str, **updates):
        return {"run_id": run_id, **updates}

    monkeypatch.setattr(writer, "AsyncSessionLocal", lambda: _SessionContext(task_session))
    monkeypatch.setattr(writer, "_claim_outline_runtime", _claim_outline_runtime)
    monkeypatch.setattr(writer, "_outline_runtime_should_stop", lambda *_args: _false())
    monkeypatch.setattr(writer, "_outline_runtime_heartbeat", _noop)
    monkeypatch.setattr(writer, "_set_outline_job_state", _set_state)
    monkeypatch.setattr(writer, "_finish_outline_runtime", _noop)

    async def fake_generate(*, current_user, **_kwargs):
        captured["current_user"] = current_user
        return SimpleNamespace(id="project-schema")

    monkeypatch.setattr(writer, "generate_chapters_outline", fake_generate)

    run_id = f"outline-identity-{owner_id}"
    writer._OUTLINE_SCHEDULED_RUNS.discard(run_id)
    await writer._run_outline_generation_job(
        run_id,
        "outline-identity-project",
        actor_id,
        {"start_chapter": 1, "num_chapters": 1},
    )

    restored = captured["current_user"]
    assert isinstance(restored, UserInDB)
    assert restored.id == owner_id
    assert restored.username == owner.username
    assert restored.email == owner.email
    assert restored.is_admin is owner_is_admin
    assert claimed == [owner_id]


@pytest.mark.asyncio
async def test_chapter_worker_keeps_runtime_owner_for_lease_events_and_pipeline(
    task_session, monkeypatch
):
    owner = User(
        id=98121,
        username="chapter-runtime-owner",
        email="chapter-owner@example.com",
        hashed_password="owner-hash",
        is_admin=True,
        is_active=True,
    )
    actor = User(
        id=98122,
        username="chapter-http-editor",
        email="chapter-editor@example.com",
        hashed_password="editor-hash",
        is_admin=False,
        is_active=True,
    )
    task_session.add_all([owner, actor])
    await task_session.commit()
    owner_id = 98121
    actor_id = 98122
    run_id = "chapter-identity-owner"
    await TaskRuntimeService(task_session).create_task(
        task_id=run_id,
        task_type="chapter_generation",
        owner_user_id=owner_id,
        project_id="chapter-identity-project",
        chapter_id="11",
        payload={"run_id": run_id},
    )

    monkeypatch.setattr(writer, "AsyncSessionLocal", lambda: _SessionContext(task_session))

    claim_owners: list[int] = []
    original_claim = TaskRuntimeService.claim

    async def spy_claim(self, task_id, **kwargs):
        claim_owners.append(int(kwargs["owner_user_id"]))
        return await original_claim(self, task_id, **kwargs)

    monkeypatch.setattr(TaskRuntimeService, "claim", spy_claim)

    events: list[dict] = []

    async def _capture(target, item):
        target.append(item)

    async def _noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        writer,
        "_append_chapter_task_event",
        lambda _run_id, **kwargs: _capture(events, kwargs),
    )
    monkeypatch.setattr(writer, "_mark_busy_chapter_failed", _noop)

    class FakeNovelService:
        def __init__(self, _session):
            pass

        async def get_or_create_chapter(self, project_id, chapter_number):
            return SimpleNamespace(
                id=11,
                project_id=project_id,
                chapter_number=chapter_number,
                status="generating",
                real_summary="",
                selected_version_id=None,
            )

    class FakeOrchestrator:
        def __init__(self, _session):
            pass

        async def generate_chapter(self, **kwargs):
            pipeline_args.update(kwargs)
            raise asyncio.CancelledError

    pipeline_args: dict = {}
    monkeypatch.setattr(writer, "NovelService", FakeNovelService)
    monkeypatch.setattr(writer, "PipelineOrchestrator", FakeOrchestrator)

    with pytest.raises(asyncio.CancelledError):
        await writer._schedule_generate_task(
            "chapter-identity-project",
            1,
            actor_id,
            None,
            {},
            run_id,
        )

    assert claim_owners == [owner_id]
    assert pipeline_args["user_id"] == owner_id
    assert events
    assert all(event["owner_user_id"] == owner_id for event in events)


@pytest.mark.asyncio
async def test_outline_rewrite_worker_rehydrates_runtime_owner_identity(
    task_session, monkeypatch
):
    owner = User(
        id=98131,
        username="rewrite-runtime-admin",
        email="rewrite-admin@example.com",
        hashed_password="rewrite-owner-hash",
        is_admin=True,
        is_active=True,
    )
    actor = User(
        id=98132,
        username="rewrite-http-editor",
        email="rewrite-editor@example.com",
        hashed_password="rewrite-editor-hash",
        is_admin=False,
        is_active=True,
    )
    task_session.add_all([owner, actor])
    await task_session.commit()
    run_id = "outline-rewrite-identity-owner"
    await TaskRuntimeService(task_session).create_task(
        task_id=run_id,
        task_type="chapter_outline_rewrite",
        owner_user_id=98131,
        project_id="outline-rewrite-identity-project",
        payload={"run_id": run_id},
    )

    captured: dict[str, object] = {}

    async def _fake_claim(_run_id: str, execution_owner_id: int) -> bool:
        captured["claimed_owner_id"] = execution_owner_id
        return True

    async def _false(*_args) -> bool:
        return False

    async def _noop(*_args, **_kwargs):
        return None

    async def _set_state(run_id: str, **updates):
        return {"run_id": run_id, **updates}

    async def fake_rewrite(*, current_user, **_kwargs):
        captured["current_user"] = current_user
        return SimpleNamespace(id="rewrite-project-schema")

    monkeypatch.setattr(writer, "AsyncSessionLocal", lambda: _SessionContext(task_session))
    monkeypatch.setattr(writer, "_claim_outline_runtime", _fake_claim)
    monkeypatch.setattr(writer, "_outline_runtime_should_stop", _false)
    monkeypatch.setattr(writer, "_set_outline_job_state", _set_state)
    monkeypatch.setattr(writer, "_finish_outline_runtime", _noop)
    monkeypatch.setattr(writer, "rewrite_chapter_outline", fake_rewrite)

    await writer._run_outline_rewrite_job(
        run_id,
        "outline-rewrite-identity-project",
        98132,
        {
            "chapter_number": 1,
            "title": "旧标题",
            "summary": "旧摘要",
            "direction": "强化冲突",
        },
    )

    restored = captured["current_user"]
    assert isinstance(restored, UserInDB)
    assert restored.id == 98131
    assert restored.username == "rewrite-runtime-admin"
    assert restored.email == "rewrite-admin@example.com"
    assert restored.hashed_password == "rewrite-owner-hash"
    assert restored.is_admin is True
    assert restored.is_active is True
    assert captured["claimed_owner_id"] == 98131
