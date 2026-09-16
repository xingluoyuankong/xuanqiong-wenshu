"""跨层回归：真实章节生成 HTTP 入口到后台 worker、状态和 SSE。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from app.api.routers import writer
from app.core.dependencies import get_session
from app.db import session as db_session
from app.db.base import Base
from app.main import app
from app.models import Chapter, ChapterVersion, NovelBlueprint
from app.services.task_runtime import TaskRuntimeService

from .test_writer_member_http_acceptance import PASSWORD, _SessionContext, _seed


@dataclass(frozen=True)
class HttpGenerationFixture:
    project_id: str
    chapter_number: int
    token: str
    owner_user_id: int


@pytest.fixture
async def http_generation_client(task_session, monkeypatch):
    """使用隔离 SQLite 和真实 JWT；后台 callable 由测试显式执行。"""
    connection = await task_session.connection()
    await connection.run_sync(Base.metadata.create_all)
    seeded = await _seed(task_session)
    task_session.add(
        NovelBlueprint(
            project_id=seeded.project.id,
            title="跨层回归蓝图",
            genre="玄幻",
            style="紧凑",
            world_setting={"rules": ["fixture"]},
        )
    )
    await task_session.commit()
    monkeypatch.setattr(writer, "AsyncSessionLocal", lambda: _SessionContext(task_session))

    async def override_session():
        yield task_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[db_session.get_session] = override_session
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://writer-generation-http") as client:
            login = await client.post(
                "/api/auth/login",
                data={"username": seeded.owner.username, "password": PASSWORD},
            )
            assert login.status_code == 200, login.text
            yield client, task_session, HttpGenerationFixture(
                project_id=seeded.project.id,
                chapter_number=seeded.chapter.chapter_number,
                token=login.json()["access_token"],
                owner_user_id=seeded.owner.id,
            )
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(db_session.get_session, None)


@pytest.mark.asyncio
async def test_http_post_background_worker_status_and_sse_terminal_contract(
    http_generation_client, monkeypatch
):
    client, session, fixture = http_generation_client
    headers = {"Authorization": f"Bearer {fixture.token}"}
    scheduled: list[tuple[Any, ...]] = []
    original_schedule = writer._schedule_generate_task

    async def capture_schedule(*args):
        scheduled.append(args)

    async def deterministic_generate(self, **_kwargs):
        result = await self.session.execute(
            select(Chapter).where(
                Chapter.project_id == fixture.project_id,
                Chapter.chapter_number == fixture.chapter_number,
            )
        )
        chapter = result.scalars().first()
        assert chapter is not None
        content = "跨层回归确定性正文：局势在终点完成一次升级。"
        version = ChapterVersion(
            chapter_id=chapter.id,
            version_label="cross-layer-fixture",
            provider="fixture",
            content=content,
            content_hash="cross-layer-fixture-hash",
            status="candidate",
        )
        self.session.add(version)
        await self.session.commit()
        return {"variants": [{"content": content}]}

    # 保留真实类的静态配置契约，仅替换 Provider/编排主体为确定性输出。
    monkeypatch.setattr(writer, "_schedule_generate_task", capture_schedule)
    monkeypatch.setattr(writer.PipelineOrchestrator, "generate_chapter", deterministic_generate)

    response = await client.post(
        f"/api/writer/novels/{fixture.project_id}/chapters/generate",
        headers=headers,
        json={
            "chapter_number": fixture.chapter_number,
            "target_word_count": 1000,
            "min_word_count": 500,
            "preset": "basic",
            "generation_timeout_seconds": 0,
        },
    )
    assert response.status_code == 200, response.text
    queued_runtime = response.json()["generation_runtime"]
    assert queued_runtime["status"] == "queued"
    assert queued_runtime["queued"] is True
    assert len(scheduled) == 1
    assert scheduled[0][0] == fixture.project_id
    assert scheduled[0][1] == fixture.chapter_number
    run_id = scheduled[0][-1]
    assert isinstance(run_id, str) and run_id

    # 这里执行生产路由实际加入 BackgroundTasks 的 scheduler callable，
    # 因而覆盖 HTTP POST -> scheduler -> worker 的真实边界。
    await original_schedule(*scheduled[0])

    status = await client.get(
        f"/api/writer/novels/{fixture.project_id}/chapters/{fixture.chapter_number}/status",
        headers=headers,
    )
    assert status.status_code == 200, status.text
    status_payload = status.json()
    expected_content = "跨层回归确定性正文：局势在终点完成一次升级。"
    assert status_payload["generation_status"] == "successful"
    assert status_payload["selected_version_id"] is not None
    persisted = await session.execute(
        select(Chapter).where(
            Chapter.project_id == fixture.project_id,
            Chapter.chapter_number == fixture.chapter_number,
        )
    )
    assert status_payload["word_count"] == persisted.scalars().one().word_count

    stream = await client.get(
        f"/api/writer/novels/{fixture.project_id}/chapters/{fixture.chapter_number}/stream",
        headers=headers,
        params={"after_event_id": 0},
    )
    assert stream.status_code == 200, stream.text
    assert "event: task_started" in stream.text
    assert "event: task_completed" in stream.text
    assert run_id in stream.text

    task = await TaskRuntimeService(session).get_task(
        run_id, owner_user_id=fixture.owner_user_id
    )
    assert task.status == "succeeded"
    assert task.stage == "completed"
    events = await TaskRuntimeService(session).list_events(
        run_id, owner_user_id=fixture.owner_user_id
    )
    assert events[-1].event_type == "task_completed"
    assert events[-1].status == "succeeded"


