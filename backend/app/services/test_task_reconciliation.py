"""重启恢复与僵尸任务巡检回归。"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.novel import Chapter, NovelProject
from app.models.user import User
from app.models.task_runtime import TaskRuntime
from app.schemas.novel import ChapterGenerationStatus
from app.schemas.task_runtime import TaskRuntimeStatus
from app.services.task_reconciliation import TaskReconciliationService
from app.services.task_runtime import TaskRuntimeService


async def _make_project(session, project_id: str = "proj-recon", user_id: int = 41) -> NovelProject:
    session.add(
        User(
            id=user_id,
            username=f"recon-user-{user_id}",
            email=f"recon{user_id}@example.com",
            hashed_password="x",
        )
    )
    project = NovelProject(id=project_id, user_id=user_id, title="巡检项目")
    session.add(project)
    await session.commit()
    return project


async def _make_busy_chapter(
    session,
    *,
    project_id: str,
    chapter_number: int,
    run_id: str | None,
    status: str = ChapterGenerationStatus.GENERATING.value,
) -> Chapter:
    real_summary = ""
    if run_id:
        real_summary = json.dumps(
            {
                "generation_runtime": {
                    "run_id": run_id,
                    "progress_stage": "drafting",
                    "events": [{"at": "2026-08-12T00:00:00+00:00", "stage": "drafting"}],
                }
            },
            ensure_ascii=False,
        )
    chapter = Chapter(
        project_id=project_id,
        chapter_number=chapter_number,
        status=status,
        real_summary=real_summary,
    )
    session.add(chapter)
    await session.commit()
    await session.refresh(chapter)
    return chapter


@pytest.mark.asyncio
async def test_live_lease_chapter_is_preserved_not_reset(task_session):
    """回归：旧启动逻辑会把仍在运行的章节无条件重置，必须不再发生。"""
    await _make_project(task_session)
    runtime = TaskRuntimeService(task_session)
    task = await runtime.create_task(
        task_type="chapter_generation",
        owner_user_id=41,
        project_id="proj-recon",
        chapter_id="1",
    )
    await runtime.claim(task.task_id, lease_owner="worker-live")
    await runtime.heartbeat(task.task_id, lease_owner="worker-live")
    chapter = await _make_busy_chapter(
        task_session, project_id="proj-recon", chapter_number=1, run_id=task.task_id
    )

    report = await TaskReconciliationService(task_session).reconcile(stale_after_seconds=180)

    await task_session.refresh(chapter)
    assert chapter.id in report.preserved_chapter_ids
    assert chapter.id not in report.released_chapter_ids
    assert chapter.status == ChapterGenerationStatus.GENERATING.value


@pytest.mark.asyncio
async def test_heartbeat_timeout_marks_task_stale_and_releases_chapter(task_session):
    await _make_project(task_session)
    runtime = TaskRuntimeService(task_session)
    task = await runtime.create_task(
        task_type="chapter_generation",
        owner_user_id=41,
        project_id="proj-recon",
        chapter_id="1",
    )
    await runtime.claim(task.task_id, lease_owner="worker-dead")
    # 模拟进程被杀：心跳停在很久以前。
    task.heartbeat_at = datetime.now(timezone.utc) - timedelta(hours=2)
    await task_session.commit()
    chapter = await _make_busy_chapter(
        task_session, project_id="proj-recon", chapter_number=1, run_id=task.task_id
    )

    report = await TaskReconciliationService(task_session).reconcile(stale_after_seconds=180)

    await task_session.refresh(task)
    await task_session.refresh(chapter)
    assert task.task_id in report.stale_task_ids
    assert task.status == TaskRuntimeStatus.STALE.value
    assert chapter.id in report.released_chapter_ids
    assert chapter.status == ChapterGenerationStatus.FAILED.value


@pytest.mark.asyncio
async def test_released_chapter_keeps_run_id_and_retry_action(task_session):
    """恢复信息必须保留：run_id、事件历史与可执行动作不能被抹掉。"""
    await _make_project(task_session)
    runtime = TaskRuntimeService(task_session)
    task = await runtime.create_task(
        task_type="chapter_generation",
        owner_user_id=41,
        project_id="proj-recon",
        chapter_id="1",
    )
    await runtime.append_event(task.task_id, event_type="task_failed", status="failed")
    chapter = await _make_busy_chapter(
        task_session, project_id="proj-recon", chapter_number=1, run_id=task.task_id
    )

    await TaskReconciliationService(task_session).reconcile(stale_after_seconds=180)

    await task_session.refresh(chapter)
    runtime_state = json.loads(chapter.real_summary)["generation_runtime"]
    assert runtime_state["run_id"] == task.task_id
    assert runtime_state["recovered_from_restart"] is True
    assert "retry_generation" in runtime_state["allowed_actions"]
    # 原有事件历史保留，并追加一条 interrupted 记录。
    assert len(runtime_state["events"]) >= 2
    assert runtime_state["events"][-1]["stage"] == "interrupted"


@pytest.mark.asyncio
async def test_busy_chapter_without_task_record_is_released(task_session):
    await _make_project(task_session)
    chapter = await _make_busy_chapter(
        task_session, project_id="proj-recon", chapter_number=7, run_id=None
    )

    report = await TaskReconciliationService(task_session).reconcile(stale_after_seconds=180)

    await task_session.refresh(chapter)
    assert chapter.id in report.released_chapter_ids
    assert chapter.status == ChapterGenerationStatus.FAILED.value


@pytest.mark.asyncio
async def test_reconcile_does_not_touch_other_projects_tasks(task_session):
    """多小说并发：巡检不得把另一个项目的活跃任务连带处理。"""
    await _make_project(task_session, project_id="proj-a", user_id=51)
    await _make_project(task_session, project_id="proj-b", user_id=52)
    runtime = TaskRuntimeService(task_session)
    live = await runtime.create_task(
        task_type="chapter_generation", owner_user_id=52, project_id="proj-b", chapter_id="2"
    )
    await runtime.claim(live.task_id, lease_owner="worker-b")
    await runtime.heartbeat(live.task_id, lease_owner="worker-b")

    orphan = await _make_busy_chapter(
        task_session, project_id="proj-a", chapter_number=1, run_id=None
    )
    healthy = await _make_busy_chapter(
        task_session, project_id="proj-b", chapter_number=2, run_id=live.task_id
    )

    report = await TaskReconciliationService(task_session).reconcile(stale_after_seconds=180)

    await task_session.refresh(live)
    await task_session.refresh(healthy)
    await task_session.refresh(orphan)
    assert live.status == TaskRuntimeStatus.RUNNING.value
    assert healthy.status == ChapterGenerationStatus.GENERATING.value
    assert orphan.id in report.released_chapter_ids


@pytest.mark.asyncio
async def test_reconcile_is_idempotent(task_session):
    await _make_project(task_session)
    await _make_busy_chapter(task_session, project_id="proj-recon", chapter_number=3, run_id=None)
    service = TaskReconciliationService(task_session)

    first = await service.reconcile(stale_after_seconds=180)
    second = await service.reconcile(stale_after_seconds=180)

    assert len(first.released_chapter_ids) == 1
    assert second.released_chapter_ids == []


@pytest.mark.asyncio
async def test_stale_task_can_be_recovered_after_reconcile(task_session):
    """巡检标记 stale 后，必须能被新 worker 通过租约重新领取。"""
    await _make_project(task_session)
    runtime = TaskRuntimeService(task_session)
    task = await runtime.create_task(
        task_type="chapter_generation", owner_user_id=41, project_id="proj-recon", chapter_id="9"
    )
    await runtime.claim(task.task_id, lease_owner="worker-old")
    task.heartbeat_at = datetime.now(timezone.utc) - timedelta(hours=1)
    await task_session.commit()

    await TaskReconciliationService(task_session).reconcile(stale_after_seconds=60)
    recovered = await runtime.recover(task.task_id, lease_owner="worker-new")

    assert recovered.status == TaskRuntimeStatus.RUNNING.value
    assert recovered.lease_owner == "worker-new"
