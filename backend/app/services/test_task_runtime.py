from __future__ import annotations

from datetime import timedelta

import pytest
from app.schemas.task_runtime import TaskRuntimeEventType, TaskRuntimeStatus
from app.services.task_runtime import TaskRuntimeConflict, TaskRuntimeService


@pytest.mark.asyncio
async def test_create_is_idempotent_and_emits_creation_event(task_session):
    service = TaskRuntimeService(task_session)
    first = await service.create_task(task_type="outline", idempotency_key="outline-1", owner_user_id=7)
    second = await service.create_task(task_type="outline", idempotency_key="outline-1", owner_user_id=7)

    assert first.task_id == second.task_id
    events = await service.list_events(first.task_id)
    assert [event.event_type for event in events] == [TaskRuntimeEventType.TASK_CREATED.value]


@pytest.mark.asyncio
async def test_progress_and_heartbeat_update_state_and_cursor(task_session):
    service = TaskRuntimeService(task_session)
    task = await service.create_task(task_type="chapter", owner_user_id=3)
    task = await service.update_progress(task.task_id, progress=42.5, stage="draft", message="writing")
    task = await service.heartbeat(task.task_id, lease_owner="worker-a")

    assert task.status == "running"
    assert task.progress == 42.5
    assert task.heartbeat_at is not None
    assert task.lease_owner == "worker-a"
    assert task.event_cursor == 3


@pytest.mark.asyncio
async def test_active_progress_event_refreshes_heartbeat_for_provider_wait(task_session):
    service = TaskRuntimeService(task_session)
    task = await service.create_task(task_type="chapter")
    task = await service.claim(task.task_id, lease_owner="worker-a")
    old_heartbeat = service._now() - timedelta(seconds=301)
    task.heartbeat_at = old_heartbeat
    await task_session.commit()

    updated = await service.append_event(
        task.task_id,
        event_type=TaskRuntimeEventType.PROGRESS.value,
        status="running",
        stage="generate_variants",
        progress=42,
        message="Provider 仍在返回中",
    )

    assert updated.heartbeat_at is not None
    assert service._normalize_datetime(updated.heartbeat_at) >= service._now() - timedelta(seconds=2)
    assert await service.mark_stale(stale_after_seconds=120) == []


@pytest.mark.asyncio
async def test_longform_budget_protects_live_task_from_generic_stale_sweep(task_session):
    service = TaskRuntimeService(task_session)
    task = await service.create_task(
        task_type="chapter_generation",
        payload={
            "generation_spec": {
                "normalized_generation_timeout_seconds": 1800,
            }
        },
    )
    await service.claim(task.task_id, lease_owner="worker-longform")
    task.heartbeat_at = service._now() - timedelta(seconds=301)
    await task_session.commit()

    assert await service.mark_stale(stale_after_seconds=120) == []


@pytest.mark.asyncio
async def test_longform_budget_prevents_foreign_claim_before_budget_plus_grace(task_session):
    service = TaskRuntimeService(task_session)
    task = await service.create_task(
        task_type="chapter_generation",
        payload={
            "generation_spec": {
                "normalized_generation_timeout_seconds": 1800,
            }
        },
    )
    await service.claim(task.task_id, lease_owner="worker-longform")
    task.heartbeat_at = service._now() - timedelta(seconds=301)
    await task_session.commit()

    with pytest.raises(TaskRuntimeConflict, match="lease is held"):
        await service.claim(task.task_id, lease_owner="worker-other", stale_after_seconds=120)


async def test_longform_budget_still_becomes_stale_after_budget_plus_grace(task_session):
    service = TaskRuntimeService(task_session)
    task = await service.create_task(
        task_type="chapter_generation",
        payload={
            "generation_spec": {
                "normalized_generation_timeout_seconds": 1800,
            }
        },
    )
    await service.claim(task.task_id, lease_owner="worker-longform")
    task.heartbeat_at = service._now() - timedelta(seconds=2000)
    await task_session.commit()

    stale = await service.mark_stale(stale_after_seconds=120)
    assert [item.task_id for item in stale] == [task.task_id]
    assert stale[0].error_code == "STALE_TASK"

@pytest.mark.asyncio
async def test_cancel_then_retry_is_persisted_and_retry_is_idempotent(task_session):
    service = TaskRuntimeService(task_session)
    task = await service.create_task(task_type="research", max_retries=2)
    task = await service.append_event(task.task_id, event_type="task_failed", status="failed")
    task = await service.retry(task.task_id, idempotency_key="retry-1")
    duplicate = await service.retry(task.task_id, idempotency_key="retry-1")

    assert duplicate.task_id == task.task_id
    assert task.status == "queued"
    assert task.retry_count == 1


@pytest.mark.asyncio
async def test_retry_releases_previous_worker_lease_and_assigns_event_channel(task_session):
    """重试必须切换 attempt，旧 worker 的租约不能阻塞重新派发。"""
    service = TaskRuntimeService(task_session)
    task = await service.create_task(task_type="research", max_retries=2)
    await service.claim(task.task_id, lease_owner="old-worker")
    await service.append_event(task.task_id, event_type=TaskRuntimeEventType.TASK_FAILED.value, status="failed")

    retried = await service.retry(task.task_id, idempotency_key="retry-release-1")
    assert retried.status == TaskRuntimeStatus.QUEUED.value
    assert retried.lease_owner is None
    assert retried.heartbeat_at is None

    events = await service.list_events(task.task_id)
    assert events[-1].payload["channel"] == "task_runtime"
    assert events[-1].payload["event_sequence"] == events[-1].event_id


@pytest.mark.asyncio
async def test_event_channels_keep_content_and_logs_separate(task_session):
    service = TaskRuntimeService(task_session)
    task = await service.create_task(task_type="chapter")
    await service.append_event(task.task_id, event_type=TaskRuntimeEventType.CONTENT_DELTA.value, payload={"text": "正文"})
    await service.append_event(task.task_id, event_type=TaskRuntimeEventType.LOG.value, message="日志")
    events = await service.list_events(task.task_id)
    assert events[-2].payload["channel"] == "content"
    assert events[-1].payload["channel"] == "log"


@pytest.mark.asyncio
async def test_retry_rejects_non_retryable_task(task_session):
    service = TaskRuntimeService(task_session)
    task = await service.create_task(task_type="chapter")
    with pytest.raises(TaskRuntimeConflict):
        await service.retry(task.task_id)


@pytest.mark.asyncio
async def test_event_cursor_supports_incremental_replay(task_session):
    service = TaskRuntimeService(task_session)
    task = await service.create_task(task_type="export")
    await service.append_event(task.task_id, event_type="log", message="one")
    task = await service.append_event(task.task_id, event_type="log", message="two")
    events = await service.list_events(task.task_id, after_event_id=2)

    assert len(events) == 1
    assert events[0].message == "two"
    assert events[0].event_id == task.event_cursor
@pytest.mark.asyncio
async def test_cancel_requests_cancellation_and_emits_event(task_session):
    service = TaskRuntimeService(task_session)
    task = await service.create_task(task_type="chapter")
    task = await service.request_cancel(task.task_id)

    assert task.status == "cancelling"
    events = await service.list_events(task.task_id, after_event_id=1)
    assert events[-1].event_type == "cancel_requested"

@pytest.mark.asyncio
async def test_claim_prevents_live_duplicate_and_metrics_are_persisted(task_session):
    service = TaskRuntimeService(task_session)
    task = await service.create_task(task_type="chapter", owner_user_id=11)
    task = await service.claim(task.task_id, lease_owner="worker-a", owner_user_id=11)
    assert task.status == "running"
    with pytest.raises(TaskRuntimeConflict):
        await service.claim(task.task_id, lease_owner="worker-b", stale_after_seconds=120, owner_user_id=11)
    task = await service.update_metrics(task.task_id, input_tokens=12, output_tokens=30, owner_user_id=11)
    assert task.total_tokens == 42


@pytest.mark.asyncio
async def test_stale_reconciliation_marks_timed_out_task(task_session):
    service = TaskRuntimeService(task_session)
    task = await service.create_task(task_type="research")
    task = await service.claim(task.task_id, lease_owner="worker-a")
    task.heartbeat_at = service._now() - __import__("datetime").timedelta(seconds=301)
    await task_session.commit()
    stale = await service.mark_stale(stale_after_seconds=120)
    assert [item.task_id for item in stale] == [task.task_id]
    assert stale[0].status == "stale"
    assert stale[0].error_code == "STALE_TASK"


@pytest.mark.asyncio
async def test_repeated_stale_reconciliation_is_idempotent(task_session):
    service = TaskRuntimeService(task_session)
    task = await service.create_task(task_type="chapter")
    await service.claim(task.task_id, lease_owner="worker-a")
    task.heartbeat_at = service._now() - timedelta(seconds=301)
    await task_session.commit()

    first = await service.mark_stale(stale_after_seconds=120)
    second = await service.mark_stale(stale_after_seconds=120)

    assert [item.task_id for item in first] == [task.task_id]
    assert second == []
    events = await service.list_events(task.task_id)
    assert [event.event_type for event in events].count(TaskRuntimeEventType.TASK_STALE.value) == 1


@pytest.mark.asyncio
async def test_heartbeat_rejects_live_foreign_lease(task_session):
    service = TaskRuntimeService(task_session)
    task = await service.create_task(task_type="chapter")
    await service.claim(task.task_id, lease_owner="worker-a")
    with pytest.raises(TaskRuntimeConflict):
        await service.heartbeat(task.task_id, lease_owner="worker-b")


@pytest.mark.asyncio
async def test_stale_task_can_be_reclaimed_by_a_new_worker(task_session):
    service = TaskRuntimeService(task_session)
    task = await service.create_task(task_type="chapter")
    task = await service.claim(task.task_id, lease_owner="worker-a")
    task.heartbeat_at = service._now() - __import__("datetime").timedelta(seconds=301)
    await task_session.commit()
    await service.mark_stale(stale_after_seconds=120)
    task = await service.claim(task.task_id, lease_owner="worker-b")
    assert task.status == "running"
    assert task.lease_owner == "worker-b"


@pytest.mark.asyncio
async def test_recover_is_the_persistent_reclaim_entrypoint(task_session):
    service = TaskRuntimeService(task_session)
    task = await service.create_task(task_type="chapter")
    await service.claim(task.task_id, lease_owner="worker-a")
    task.heartbeat_at = service._now() - __import__("datetime").timedelta(seconds=301)
    await task_session.commit()
    await service.mark_stale(stale_after_seconds=120)

    recovered = await service.recover(task.task_id, lease_owner="worker-b", stale_after_seconds=120)

    assert recovered.status == "running"
    assert recovered.lease_owner == "worker-b"
    assert recovered.heartbeat_at is not None


@pytest.mark.asyncio
async def test_recover_rejects_queued_task_without_claiming_it(task_session):
    service = TaskRuntimeService(task_session)
    task = await service.create_task(task_type="chapter")

    with pytest.raises(TaskRuntimeConflict):
        await service.recover(task.task_id, lease_owner="worker-a")

    current = await service.get_task(task.task_id)
    assert current.status == "queued"


@pytest.mark.asyncio
async def test_terminal_event_normalizes_naive_db_started_at(task_session):
    service = TaskRuntimeService(task_session)
    task = await service.create_task(task_type="chapter")
    task.started_at = (service._now() - timedelta(seconds=2)).replace(tzinfo=None)
    await task_session.commit()
    await task_session.refresh(task)
    assert task.started_at is not None and task.started_at.tzinfo is None

    finished = await service.append_event(
        task.task_id,
        event_type="task_failed",
        status="failed",
    )

    assert finished.elapsed_ms is not None
    assert finished.elapsed_ms >= 0


@pytest.mark.asyncio
async def test_list_tasks_is_scoped_by_owner_project_and_status(task_session):
    service = TaskRuntimeService(task_session)
    await service.create_task(task_id="list-a", task_type="chapter", owner_user_id=7, project_id="p1")
    await service.create_task(task_id="list-b", task_type="research", owner_user_id=7, project_id="p2")
    await service.create_task(task_id="list-c", task_type="chapter", owner_user_id=8, project_id="p1")
    await service.append_event("list-a", event_type="task_started", status="running", owner_user_id=7)
    tasks = await service.list_tasks(owner_user_id=7, project_id="p1", statuses=["running"])
    assert [task.task_id for task in tasks] == ["list-a"]


@pytest.mark.asyncio
async def test_append_event_rejects_unknown_status(task_session):
    service = TaskRuntimeService(task_session)
    await service.create_task(task_id="status-guard", task_type="chapter")
    with pytest.raises(TaskRuntimeConflict, match="invalid task status"):
        await service.append_event("status-guard", event_type="progress", status="done")


@pytest.mark.asyncio
async def test_late_progress_cannot_overwrite_cancellation_request(task_session):
    """取消与迟到 Provider 进度竞态时，任务必须继续保持 cancelling。"""
    service = TaskRuntimeService(task_session)
    task = await service.create_task(task_type="chapter")
    await service.claim(task.task_id, lease_owner="worker-a")
    await service.request_cancel(task.task_id)

    updated = await service.update_progress(
        task.task_id,
        progress=65,
        stage="provider_wait",
        message="迟到的上游进度",
    )

    assert updated.status == "cancelling"
    assert updated.progress == 65
    events = await service.list_events(task.task_id)
    assert events[-1].event_type == TaskRuntimeEventType.PROGRESS.value
    assert events[-1].status == "cancelling"


@pytest.mark.asyncio
async def test_cancelling_task_rejects_late_terminal_success(task_session):
    """取消竞态下，迟到的成功回调不得伪造任务完成。"""
    service = TaskRuntimeService(task_session)
    task = await service.create_task(task_type="chapter")
    await service.claim(task.task_id, lease_owner="worker-a")
    await service.request_cancel(task.task_id)

    with pytest.raises(TaskRuntimeConflict, match="cannot transition cancelling task"):
        await service.append_event(
            task.task_id,
            event_type=TaskRuntimeEventType.TASK_COMPLETED.value,
            status=TaskRuntimeStatus.SUCCEEDED.value,
            progress=100,
        )

    current = await service.get_task(task.task_id)
    assert current.status == TaskRuntimeStatus.CANCELLING.value


@pytest.mark.asyncio
async def test_late_event_cannot_reopen_terminal_task(task_session):
    """终态任务拒绝迟到的非终态事件，防止伪造恢复或继续运行。"""
    service = TaskRuntimeService(task_session)
    task = await service.create_task(task_type="chapter")
    await service.append_event(
        task.task_id,
        event_type=TaskRuntimeEventType.TASK_FAILED.value,
        status="failed",
        message="provider failed",
    )

    with pytest.raises(TaskRuntimeConflict, match="cannot transition terminal task"):
        await service.append_event(
            task.task_id,
            event_type=TaskRuntimeEventType.PROGRESS.value,
            status="running",
            progress=80,
            message="late provider callback",
        )

    current = await service.get_task(task.task_id)
    assert current.status == "failed"


@pytest.mark.asyncio
async def test_idempotency_race_fallback_does_not_return_other_owner_task(task_session, monkeypatch):
    """唯一键竞争后的二次查询也必须执行归属校验，不能泄露他人任务。"""
    service = TaskRuntimeService(task_session)
    existing = await service.create_task(
        task_type="chapter", idempotency_key="race-key", owner_user_id=7
    )

    original_flush = task_session.flush
    first_flush = True

    async def racing_flush(*args, **kwargs):
        nonlocal first_flush
        if first_flush:
            first_flush = False
            from sqlalchemy.exc import IntegrityError
            raise IntegrityError("duplicate", {}, Exception("duplicate"))
        return await original_flush(*args, **kwargs)

    monkeypatch.setattr(task_session, "flush", racing_flush)
    with pytest.raises(TaskRuntimeConflict, match="idempotency_key is already used"):
        await service.create_task(
            task_type="chapter", idempotency_key="race-key", owner_user_id=99
        )

    assert (await service.get_task(existing.task_id, owner_user_id=7)).task_id == existing.task_id


@pytest.mark.asyncio
async def test_api_style_cancel_finalizes_unclaimed_queued_task(task_session):
    service = TaskRuntimeService(task_session)
    task = await service.create_task(task_type="chapter")
    task = await service.request_cancel(task.task_id, finalize_unclaimed=True)

    assert task.status == "cancelled"
    events = await service.list_events(task.task_id)
    assert [event.event_type for event in events][-2:] == [
        TaskRuntimeEventType.CANCEL_REQUESTED.value,
        TaskRuntimeEventType.TASK_CANCELLED.value,
    ]


@pytest.mark.asyncio
async def test_retry_starts_new_attempt_and_resets_attempt_clock(task_session):
    service = TaskRuntimeService(task_session)
    task = await service.create_task(task_type="chapter", max_retries=2)
    claimed = await service.claim(task.task_id, lease_owner="worker-old")
    assert claimed.attempt == 1
    assert claimed.lease_generation == 1

    await service.append_event(
        task.task_id,
        event_type=TaskRuntimeEventType.TASK_FAILED.value,
        status=TaskRuntimeStatus.FAILED.value,
        attempt=claimed.attempt,
        lease_owner=claimed.lease_owner,
        lease_generation=claimed.lease_generation,
    )
    retried = await service.retry(task.task_id, idempotency_key="new-attempt")

    assert retried.attempt == 2
    assert retried.started_at is None
    assert retried.finished_at is None
    assert retried.elapsed_ms is None
    assert retried.lease_owner is None


@pytest.mark.asyncio
async def test_old_worker_cannot_write_after_retry_and_reclaim(task_session):
    service = TaskRuntimeService(task_session)
    task = await service.create_task(task_type="chapter", max_retries=2)
    old_claim = await service.claim(task.task_id, lease_owner="worker-old")
    old_attempt = old_claim.attempt
    old_generation = old_claim.lease_generation

    await service.append_event(
        task.task_id,
        event_type=TaskRuntimeEventType.TASK_FAILED.value,
        status=TaskRuntimeStatus.FAILED.value,
        attempt=old_attempt,
        lease_owner="worker-old",
        lease_generation=old_generation,
    )
    await service.retry(task.task_id, idempotency_key="retry-after-failure")
    current = await service.claim(task.task_id, lease_owner="worker-new")

    with pytest.raises(TaskRuntimeConflict, match="stale task writer"):
        await service.append_event(
            task.task_id,
            event_type=TaskRuntimeEventType.TASK_COMPLETED.value,
            status=TaskRuntimeStatus.SUCCEEDED.value,
            attempt=old_attempt,
            lease_owner="worker-old",
            lease_generation=old_generation,
        )

    persisted = await service.get_task(task.task_id)
    assert persisted.status == TaskRuntimeStatus.RUNNING.value
    assert persisted.attempt == current.attempt
    assert persisted.lease_owner == "worker-new"
    assert persisted.lease_generation == current.lease_generation
    events = await service.list_events(task.task_id)
    assert events[-1].event_type == TaskRuntimeEventType.TASK_STARTED.value
    assert all(event.attempt == persisted.attempt for event in events[-1:])


@pytest.mark.asyncio
async def test_current_worker_event_records_attempt_and_lease_generation(task_session):
    service = TaskRuntimeService(task_session)
    task = await service.create_task(task_type="chapter")
    claimed = await service.claim(task.task_id, lease_owner="worker-a")

    await service.update_progress(
        task.task_id,
        progress=25,
        stage="draft",
        attempt=claimed.attempt,
        lease_owner="worker-a",
        lease_generation=claimed.lease_generation,
    )

    event = (await service.list_events(task.task_id))[-1]
    assert event.attempt == claimed.attempt
    assert event.lease_generation == claimed.lease_generation
    assert event.sequence == event.event_id
    assert event.channel == "progress"


@pytest.mark.asyncio
async def test_expired_worker_cannot_write_after_same_attempt_is_reclaimed(task_session):
    service = TaskRuntimeService(task_session)
    task = await service.create_task(task_type="chapter")
    old_claim = await service.claim(task.task_id, lease_owner="worker-shared")
    old_generation = old_claim.lease_generation
    old_claim.heartbeat_at = service._now() - timedelta(seconds=301)
    await task_session.commit()

    current = await service.claim(
        task.task_id,
        lease_owner="worker-shared",
        stale_after_seconds=120,
    )
    assert current.attempt == old_claim.attempt
    assert current.lease_generation == old_generation + 1

    with pytest.raises(TaskRuntimeConflict, match="stale task writer"):
        await service.update_progress(
            task.task_id,
            progress=99,
            attempt=current.attempt,
            lease_owner="worker-shared",
            lease_generation=old_generation,
        )
