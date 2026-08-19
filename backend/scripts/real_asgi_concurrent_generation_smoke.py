"""真实 Provider 双项目并发章节生成隔离验收，不输出认证令牌或密钥。"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
from dotenv import load_dotenv
from sqlalchemy import select


ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
load_dotenv(ROOT / ".env")
db_path = ROOT / "storage" / f"real-asgi-concurrent-{time.time_ns()}.db"
os.environ["DB_PROVIDER"] = "sqlite"
os.environ["SQLITE_DB_PATH"] = str(db_path)
sys.path.insert(0, str(ROOT))

from app.api.routers.writer import stream_chapter_progress  # noqa: E402
from app.db.session import AsyncSessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.novel import Chapter, ChapterVersion, NovelProject  # noqa: E402
from app.models.task_runtime import TaskRuntime, TaskRuntimeEvent  # noqa: E402


TERMINAL_CHAPTER_STATUSES = {
    "successful",
    "failed",
    "waiting_for_confirm",
    "evaluation_failed",
    "cancelled",
}
SUCCESSFUL_CHAPTER_STATUSES = {"successful", "waiting_for_confirm"}


class _ConnectedSmokeRequest:
    """Direct route invocation avoids ASGITransport's infinite SSE buffering."""

    async def is_disconnected(self) -> bool:
        return False


@dataclass(frozen=True)
class ProjectCase:
    label: str
    title: str
    prompt: str
    marker: str


def _safe_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
        detail = payload.get("detail", payload) if isinstance(payload, dict) else payload
        return str(detail)[:300]
    except Exception:
        return response.text[:300]


def _chapter_status(payload: dict[str, Any]) -> str:
    return str(payload.get("generation_status") or payload.get("status") or "")


async def _create_project(client: httpx.AsyncClient, headers: dict[str, str], case: ProjectCase) -> str:
    response = await client.post(
        "/api/novels",
        headers=headers,
        json={"title": case.title, "initial_prompt": case.prompt},
    )
    print(f"PROJECT label={case.label} status={response.status_code}")
    if response.status_code not in (200, 201):
        raise RuntimeError(f"PROJECT_ERROR {case.label} {_safe_error(response)}")
    payload = response.json()
    project_id = payload.get("id") or payload.get("project_id")
    if not project_id:
        raise RuntimeError(f"PROJECT_ERROR {case.label} missing id")
    return str(project_id)


async def _submit_generation(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    case: ProjectCase,
    project_id: str,
) -> None:
    response = await client.post(
        f"/api/writer/novels/{project_id}/chapters/generate",
        headers=headers,
        json={
            "chapter_number": 1,
            "target_word_count": 1200,
            "min_word_count": 900,
            "preset": "enhanced",
            "generation_timeout_seconds": 900,
            "segment_word_limit": 1200,
            "writing_notes": (
                f"本章必须围绕项目专属标记「{case.marker}」推进；"
                "不要出现其他项目的专属标记。"
            ),
        },
    )
    print(f"GENERATE label={case.label} status={response.status_code}")
    if response.status_code not in (200, 202):
        raise RuntimeError(f"GENERATE_ERROR {case.label} {_safe_error(response)}")


async def _wait_for_terminal(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    case: ProjectCase,
    project_id: str,
) -> dict[str, Any]:
    deadline = time.monotonic() + 420
    last_stage: str | None = None
    while time.monotonic() < deadline:
        response = await client.get(
            f"/api/writer/novels/{project_id}/chapters/1/status", headers=headers
        )
        if response.status_code != 200:
            raise RuntimeError(f"STATUS_ERROR {case.label} {_safe_error(response)}")
        payload = response.json()
        runtime = payload.get("generation_runtime") or {}
        status = _chapter_status(payload)
        stage = str(runtime.get("progress_stage") or status)
        if stage != last_stage:
            print(
                f"PROGRESS label={case.label} status={status} stage={stage} "
                f"percent={runtime.get('progress_percent')} words={payload.get('word_count', 0)}"
            )
            last_stage = stage
        if status in TERMINAL_CHAPTER_STATUSES:
            return payload
        await asyncio.sleep(2)
    raise RuntimeError(f"TIMEOUT label={case.label}")


async def _read_stream(
    *, project_id: str, owner_id: int
) -> tuple[str, list[int], set[str]]:
    async with AsyncSessionLocal() as session:
        response = await stream_chapter_progress(
            project_id,
            1,
            _ConnectedSmokeRequest(),
            after_event_id=0,
            last_event_id=None,
            session=session,
            current_user=SimpleNamespace(id=owner_id),
        )
        chunks: list[str] = []

        async def consume() -> None:
            async for chunk in response.body_iterator:
                chunks.append(chunk)

        await asyncio.wait_for(consume(), timeout=30)
    text = "".join(chunks)
    ids = [int(value) for value in re.findall(r"^id: (\d+)$", text, flags=re.MULTILINE)]
    task_ids = set(re.findall(r'"task_id":\s*"([^"]+)"', text))
    return text, ids, task_ids


async def _verify_case(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    case: ProjectCase,
    project_id: str,
    other_case: ProjectCase,
    status_payload: dict[str, Any],
) -> str:
    final_status = _chapter_status(status_payload)
    if final_status not in SUCCESSFUL_CHAPTER_STATUSES:
        raise RuntimeError(
            f"RESULT_ERROR {case.label} status={final_status} runtime="
            f"{json.dumps(status_payload.get('generation_runtime') or {}, ensure_ascii=False)[:500]}"
        )

    project_response = await client.get(f"/api/novels/{project_id}", headers=headers)
    if project_response.status_code != 200:
        raise RuntimeError(f"NOVEL_ERROR {case.label} {_safe_error(project_response)}")
    chapters = project_response.json().get("chapters") or []
    chapter_payload = next((item for item in chapters if item.get("chapter_number") == 1), None)
    content = str((chapter_payload or {}).get("content") or "")
    if len(content) < 900:
        raise RuntimeError(f"CONTENT_ERROR {case.label} below minimum chars={len(content)}")
    if other_case.marker in content:
        raise RuntimeError(f"CONTENT_LEAK {case.label} contains other project marker")

    async with AsyncSessionLocal() as session:
        owner_id = await session.scalar(select(NovelProject.user_id).where(NovelProject.id == project_id))
        chapter = await session.scalar(
            select(Chapter).where(Chapter.project_id == project_id, Chapter.chapter_number == 1)
        )
        if chapter is None:
            raise RuntimeError(f"DB_ERROR {case.label} chapter missing")
        task = await session.scalar(
            select(TaskRuntime)
            .where(
                TaskRuntime.project_id == project_id,
                TaskRuntime.chapter_id == str(chapter.id),
                TaskRuntime.task_type == "chapter_generation",
            )
            .order_by(TaskRuntime.created_at.desc())
        )
        if task is None:
            raise RuntimeError(f"TASK_ERROR {case.label} runtime task missing")
        if task.status != "succeeded" or task.owner_user_id != owner_id:
            raise RuntimeError(
                f"TASK_ERROR {case.label} status={task.status} owner={task.owner_user_id} expected_owner={owner_id}"
            )
        events = list(
            (
                await session.execute(
                    select(TaskRuntimeEvent)
                    .where(TaskRuntimeEvent.task_id == task.task_id)
                    .order_by(TaskRuntimeEvent.event_id)
                )
            ).scalars()
        )
        version = await session.scalar(
            select(ChapterVersion)
            .where(ChapterVersion.chapter_id == chapter.id)
            .order_by(ChapterVersion.id.desc())
        )
        if version is None or len(version.content or "") < 900:
            raise RuntimeError(f"DB_ERROR {case.label} persisted version missing")
        if other_case.marker in (version.content or ""):
            raise RuntimeError(f"DB_CONTENT_LEAK {case.label} persisted version leaked")
        if any(event.task_id != task.task_id for event in events):
            raise RuntimeError(f"EVENT_LEAK {case.label} task mismatch")
        if not any(event.event_type == "content_delta" for event in events):
            raise RuntimeError(f"EVENT_ERROR {case.label} missing content delta")
        if not any(event.event_type == "task_completed" for event in events):
            raise RuntimeError(f"EVENT_ERROR {case.label} missing terminal event")

    stream_text, stream_ids, stream_task_ids = await _read_stream(project_id=project_id, owner_id=int(owner_id))
    print(
        f"STREAM label={case.label} events={len(stream_ids)} "
        f"content_deltas={stream_text.count('event: content_delta')} task_ids={len(stream_task_ids)}"
    )
    if not stream_ids or "event: task_completed" not in stream_text:
        raise RuntimeError(f"STREAM_ERROR {case.label} missing terminal replay")
    if stream_task_ids != {task.task_id}:
        raise RuntimeError(f"STREAM_LEAK {case.label} task_ids={sorted(stream_task_ids)}")
    if other_case.marker in stream_text:
        raise RuntimeError(f"STREAM_CONTENT_LEAK {case.label} contains other marker")
    print(
        f"RESULT label={case.label} task={task.task_id} chars={len(content)} "
        f"events={len(events)} status={task.status}"
    )
    return task.task_id


async def main() -> int:
    username = os.getenv("ADMIN_DEFAULT_USERNAME", "admin")
    password = os.getenv("ADMIN_DEFAULT_PASSWORD", "")
    if not password:
        print("SMOKE_BLOCKED missing admin password configuration")
        return 2

    cases = (
        ProjectCase(
            label="A",
            title=f"并发隔离-A-{int(time.time())}",
            prompt="都市悬疑：档案修复师追查失踪的潮汐记录。",
            marker="苍梧档案-甲",
        ),
        ProjectCase(
            label="B",
            title=f"并发隔离-B-{int(time.time())}",
            prompt="科幻悬疑：轨道维修员在废弃信标中发现求救代码。",
            marker="天枢信标-乙",
        ),
    )
    try:
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver", timeout=30.0) as client:
                login = await client.post("/api/auth/login", data={"username": username, "password": password})
                print(f"LOGIN status={login.status_code}")
                if login.status_code != 200:
                    print(f"LOGIN_ERROR {_safe_error(login)}")
                    return 1
                headers = {"Authorization": f"Bearer {login.json().get('access_token')}"}
                project_ids = await asyncio.gather(*(_create_project(client, headers, case) for case in cases))

                # 同一个应用进程、同一个真实 Provider 下同时入队，覆盖信号量和 SQLite 写入竞争。
                await asyncio.gather(
                    *(
                        _submit_generation(client, headers, case=case, project_id=project_id)
                        for case, project_id in zip(cases, project_ids)
                    )
                )
                statuses = await asyncio.gather(
                    *(
                        _wait_for_terminal(client, headers, case=case, project_id=project_id)
                        for case, project_id in zip(cases, project_ids)
                    )
                )
                task_ids = await asyncio.gather(
                    *(
                        _verify_case(
                            client,
                            headers,
                            case=case,
                            project_id=project_id,
                            other_case=cases[1 - index],
                            status_payload=statuses[index],
                        )
                        for index, (case, project_id) in enumerate(zip(cases, project_ids))
                    )
                )
                if task_ids[0] == task_ids[1]:
                    raise RuntimeError("TASK_LEAK concurrent projects reused one task id")
    except Exception as exc:
        print(f"CONCURRENT_SMOKE_ERROR {type(exc).__name__}: {exc}")
        return 1
    finally:
        await engine.dispose()

    print(f"CONCURRENT_SMOKE_PASS db={db_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
