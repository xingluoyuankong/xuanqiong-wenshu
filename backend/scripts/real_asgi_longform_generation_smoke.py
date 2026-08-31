"""真实 Provider 长篇分段章节验收：验证计划、段级 checkpoint、正文事件和最终持久化。"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
load_dotenv(ROOT / ".env")
DB_PATH = ROOT / "storage" / f"real-asgi-longform-{time.time_ns()}.db"
os.environ["DB_PROVIDER"] = "sqlite"
os.environ["SQLITE_DB_PATH"] = str(DB_PATH)
sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402
from app.db.session import AsyncSessionLocal, engine  # noqa: E402
from app.models.novel import Chapter, ChapterVersion  # noqa: E402
from app.models.task_runtime import TaskRuntime, TaskRuntimeEvent  # noqa: E402
from app.services.longform_evidence import build_longform_failure_evidence  # noqa: E402


SMOKE_MIN_TIMEOUT_SECONDS = 15 * 60
SMOKE_MAX_TIMEOUT_SECONDS = 4 * 60 * 60


def _coerce_timeout_seconds(value: Any) -> int:
    try:
        seconds = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return max(0, min(SMOKE_MAX_TIMEOUT_SECONDS, seconds))


def _resolve_smoke_timeout_seconds(submitted_payload: dict[str, Any], requested_timeout_seconds: int) -> int:
    """Use the backend normalized budget; only explicit override wins."""
    requested = _coerce_timeout_seconds(requested_timeout_seconds)
    if requested:
        return max(SMOKE_MIN_TIMEOUT_SECONDS, requested)
    runtime = submitted_payload.get("generation_runtime") if isinstance(submitted_payload, dict) else None
    normalized = runtime.get("timeout_seconds") if isinstance(runtime, dict) else None
    normalized = _coerce_timeout_seconds(normalized)
    return max(SMOKE_MIN_TIMEOUT_SECONDS, normalized or SMOKE_MAX_TIMEOUT_SECONDS)


def _error(response: httpx.Response) -> str:
    try:
        return json.dumps(response.json(), ensure_ascii=False)[:500]
    except Exception:
        return response.text[:500]


def _write_failure_evidence(*, task: Any, runtime: dict[str, Any], events: list[Any], source_db: Path, error_code: str | None) -> Path:
    event_rows = [{"event_type": getattr(event, "event_type", None)} for event in events]
    task_row = {
        "task_id": getattr(task, "task_id", None),
        "status": getattr(task, "status", None),
        "stage": getattr(task, "stage", None),
        "progress": getattr(task, "progress", None),
        "attempt": getattr(task, "attempt", None),
        "retry_count": getattr(task, "retry_count", None),
        "elapsed_ms": getattr(task, "elapsed_ms", None),
        "error_code": error_code,
    }
    report = build_longform_failure_evidence(
        source_db=source_db,
        task=task_row,
        runtime=runtime,
        events=event_rows,
        failure={
            "error_code": error_code or "LONGFORM_TASK_FAILED",
            "error_class": "TaskRuntimeFailure",
            "normalized_reason": (error_code or "longform_task_failed").lower(),
        },
    )
    output = ROOT / "output" / f"t25-longform-failure-audit-{time.time_ns()}.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


async def main() -> int:
    username = os.getenv("ADMIN_DEFAULT_USERNAME", "admin")
    password = os.getenv("ADMIN_DEFAULT_PASSWORD", "")
    if not password:
        print("LONGFORM_SMOKE_BLOCKED missing admin password configuration")
        return 2
    target = int(os.getenv("LONGFORM_SMOKE_TARGET_WORDS", "20000"))
    # 真实 Provider 的上下文/输出上限差异很大；4500 是可恢复长篇的稳健默认，
    # 更大的预算必须由验收者显式覆盖，不能让默认入口触发截断。
    segment_limit = int(os.getenv("LONGFORM_SMOKE_SEGMENT_LIMIT", "4500"))
    # 默认交给后端计算 longform 的归一化总预算；只有验收者显式覆盖时才固定预算。
    requested_timeout_seconds = _coerce_timeout_seconds(os.getenv("LONGFORM_SMOKE_TIMEOUT_SECONDS", "0"))
    try:
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver", timeout=60) as client:
                login = await client.post("/api/auth/login", data={"username": username, "password": password})
                if login.status_code != 200:
                    print(f"LONGFORM_LOGIN_ERROR {_error(login)}")
                    return 1
                headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
                project = await client.post(
                    "/api/novels",
                    headers=headers,
                    json={"title": f"长篇分段验收-{time.time_ns()}", "initial_prompt": "玄幻悬疑：一枚失落的星门钥匙牵动十年旧案。"},
                )
                if project.status_code not in (200, 201):
                    print(f"LONGFORM_PROJECT_ERROR {_error(project)}")
                    return 1
                project_id = str(project.json().get("id") or project.json().get("project_id"))
                submitted = await client.post(
                    f"/api/writer/novels/{project_id}/chapters/generate",
                    headers=headers,
                    json={
                        "chapter_number": 1,
                        "target_word_count": target,
                        "min_word_count": max(18000, int(target * 0.9)),
                        "preset": "longform",
                        "segment_word_limit": segment_limit,
                        "generation_timeout_seconds": requested_timeout_seconds,
                        "writing_notes": "保持星门旧案线索递进；每段都必须推进新的行动与信息，不要重复前段内容。",
                    },
                )
                if submitted.status_code not in (200, 202):
                    print(f"LONGFORM_SUBMIT_ERROR {_error(submitted)}")
                    return 1
                submitted_payload = submitted.json() if submitted.content else {}
                smoke_timeout_seconds = _resolve_smoke_timeout_seconds(submitted_payload, requested_timeout_seconds)
                normalized_timeout = ((submitted_payload.get("generation_runtime") or {}).get("timeout_seconds")
                                      if isinstance(submitted_payload, dict) else None)
                print(
                    f"LONGFORM_STARTED project={project_id} target={target} segment_limit={segment_limit} "
                    f"timeout={smoke_timeout_seconds} normalized_timeout={normalized_timeout}"
                )

                deadline = time.monotonic() + smoke_timeout_seconds
                last = None
                while time.monotonic() < deadline:
                    status = await client.get(f"/api/writer/novels/{project_id}/chapters/1/status", headers=headers)
                    if status.status_code != 200:
                        print(f"LONGFORM_STATUS_ERROR {_error(status)}")
                        return 1
                    payload = status.json()
                    runtime = payload.get("generation_runtime") or {}
                    marker = (payload.get("generation_status"), runtime.get("progress_stage"), runtime.get("progress_percent"))
                    if marker != last:
                        print(f"LONGFORM_PROGRESS status={marker[0]} stage={marker[1]} percent={marker[2]}")
                        last = marker
                    if marker[0] in {"successful", "waiting_for_confirm", "failed", "cancelled", "evaluation_failed"}:
                        break
                    await asyncio.sleep(3)
                else:
                    print("LONGFORM_TIMEOUT")
                    return 1

                async with AsyncSessionLocal() as session:
                    chapter = await session.scalar(select(Chapter).where(Chapter.project_id == project_id, Chapter.chapter_number == 1))
                    if chapter is None:
                        print("LONGFORM_DB_ERROR chapter_missing")
                        return 1
                    task = await session.scalar(select(TaskRuntime).where(TaskRuntime.project_id == project_id, TaskRuntime.chapter_id == str(chapter.id)).order_by(TaskRuntime.created_at.desc()))
                    if task is None:
                        print("LONGFORM_DB_ERROR task_missing")
                        return 1
                    events = list((await session.execute(select(TaskRuntimeEvent).where(TaskRuntimeEvent.task_id == task.task_id).order_by(TaskRuntimeEvent.event_id))).scalars())
                    version = await session.scalar(select(ChapterVersion).where(ChapterVersion.chapter_id == chapter.id).order_by(ChapterVersion.id.desc()))
                    payload = dict(task.payload or {})
                    runtime = payload.get("longform_generation") or {}
                    checkpoint = runtime.get("checkpoint") or {}
                    delta_count = sum(1 for event in events if event.event_type == "content_delta")
                    content_length = len((version.content if version else "") or "")
                    print(f"LONGFORM_RESULT status={task.status} chars={content_length} segments={checkpoint.get('next_segment_index')} deltas={delta_count} events={len(events)}")
                    if task.status != "succeeded":
                        evidence_path = _write_failure_evidence(
                            task=task,
                            runtime=runtime,
                            events=events,
                            source_db=DB_PATH,
                            error_code=str(task.error_code or "LONGFORM_TASK_FAILED"),
                        )
                        print(
                            f"LONGFORM_FAILURE evidence={evidence_path.name} "
                            f"status={task.status} code={task.error_code or 'LONGFORM_TASK_FAILED'}"
                        )
                        return 1
                    if target >= 20000:
                        if checkpoint.get("next_segment_index", 0) < runtime.get("segment_count", 1):
                            print("LONGFORM_CONTRACT_ERROR checkpoint_incomplete")
                            return 1
                    elif runtime.get("checkpoint"):
                        print("LONGFORM_CONTRACT_ERROR unexpected_short_chapter_checkpoint")
                        return 1
                    if content_length < int(target * 0.85) or delta_count < 2:
                        print("LONGFORM_CONTRACT_ERROR content_or_stream_too_short")
                        return 1
                    if not any(event.event_type == "task_completed" for event in events):
                        print("LONGFORM_CONTRACT_ERROR terminal_event_missing")
                        return 1
    except Exception as exc:
        print(f"LONGFORM_SMOKE_ERROR {type(exc).__name__}: {exc}")
        return 1
    finally:
        await engine.dispose()
    print(f"LONGFORM_SMOKE_PASS db={DB_PATH.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
