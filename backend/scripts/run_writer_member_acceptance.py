"""隔离 SQLite + 真实 JWT 的 Writer 成员 HTTP 验收。

脚本不读取或写入项目主数据库。每次执行都创建临时 SQLite 文件，
通过 FastAPI ASGITransport 走实际 HTTP 路由；后台生成入口使用确定性
本地桩，只记录调度，不触发任何 LLM/Provider 网络请求。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
load_dotenv(ROOT / ".env")

# 必须在 app.main / app.db.session 导入前设置，保证全局 engine 指向本次临时库。
_KEEP_ENV = {
    "DB_PROVIDER": "sqlite",
    "SECRET_KEY": "writer-member-http-acceptance-secret-2026",
    "ADMIN_DEFAULT_USERNAME": "acceptance-admin-bootstrap",
    "ADMIN_DEFAULT_PASSWORD": "AcceptanceBootstrap123!",
    "ALLOW_USER_REGISTRATION": "false",
}
for _key, _value in _KEEP_ENV.items():
    os.environ[_key] = _value

# 先创建临时数据库路径，再导入 app.db.session；全局 engine 由此绑定到
# 本次运行的隔离 SQLite，不会接触项目默认数据库。
_RUNTIME_DIR = Path(tempfile.mkdtemp(prefix="writer-member-http-acceptance-", dir=str(ROOT / "storage")))
_DB_PATH = _RUNTIME_DIR / "acceptance.sqlite"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_DB_PATH.as_posix()}"
os.environ["SQLITE_DB_PATH"] = str(_DB_PATH)

sys.path.insert(0, str(ROOT))

from app.api.routers import writer  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.session import AsyncSessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    Chapter,
    ChapterOutline,
    ChapterVersion,
    NovelProject,
    ProjectMember,
    TaskRuntime,
    TaskRuntimeEvent,
    User,
)
from app.models.project_member import ProjectMemberRole  # noqa: E402


PASSWORD = "WriterAcceptance123!"
PROJECT_ID = "script-http-member-acceptance-project"
OTHER_PROJECT_ID = "script-http-member-acceptance-other-project"


class AcceptanceFailure(RuntimeError):
    pass


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_args):
        return False


async def _seed() -> dict[str, Any]:
    owner = User(id=98201, username="script-accept-owner", email="script-accept-owner@example.com", hashed_password=hash_password(PASSWORD), is_active=True)
    editor = User(id=98202, username="script-accept-editor", email="script-accept-editor@example.com", hashed_password=hash_password(PASSWORD), is_active=True)
    viewer = User(id=98203, username="script-accept-viewer", email="script-accept-viewer@example.com", hashed_password=hash_password(PASSWORD), is_active=True)
    admin = User(id=98204, username="script-accept-admin", email="script-accept-admin@example.com", hashed_password=hash_password(PASSWORD), is_active=True, is_admin=True)
    outsider = User(id=98205, username="script-accept-outsider", email="script-accept-outsider@example.com", hashed_password=hash_password(PASSWORD), is_active=True)
    project = NovelProject(id=PROJECT_ID, user_id=owner.id, title="脚本 HTTP JWT 成员验收")
    other_project = NovelProject(id=OTHER_PROJECT_ID, user_id=outsider.id, title="脚本隔离项目")

    async with AsyncSessionLocal() as session:
        session.add_all([
            owner,
            editor,
            viewer,
            admin,
            outsider,
            project,
            other_project,
            ProjectMember(project_id=PROJECT_ID, user_id=owner.id, role=ProjectMemberRole.owner.value),
            ProjectMember(project_id=PROJECT_ID, user_id=editor.id, role=ProjectMemberRole.editor.value),
            ProjectMember(project_id=PROJECT_ID, user_id=viewer.id, role=ProjectMemberRole.viewer.value),
            ChapterOutline(project_id=PROJECT_ID, chapter_number=1, title="第一章", summary="HTTP 验收大纲"),
            ChapterOutline(project_id=PROJECT_ID, chapter_number=2, title="第二章", summary="生成验收大纲"),
        ])
        await session.flush()

        chapter = Chapter(project_id=PROJECT_ID, chapter_number=1, status="successful", real_summary="稳定 SSE 章节")
        generate_chapter = Chapter(project_id=PROJECT_ID, chapter_number=2, status="not_generated")
        cancel_chapter = Chapter(
            project_id=PROJECT_ID,
            chapter_number=3,
            status="generating",
            real_summary=json.dumps({"run_id": "script-owner-cancel-run", "status": "generating"}),
        )
        resume_chapter = Chapter(
            project_id=PROJECT_ID,
            chapter_number=4,
            status="failed",
            real_summary=json.dumps({"run_id": "script-owner-resume-run", "status": "failed"}),
        )
        other_chapter = Chapter(project_id=OTHER_PROJECT_ID, chapter_number=1, status="successful", real_summary="隔离章节")
        session.add_all([chapter, generate_chapter, cancel_chapter, resume_chapter, other_chapter])
        await session.flush()

        selected_version = ChapterVersion(
            chapter_id=chapter.id,
            version_label="script-http-v1",
            provider="fixture",
            content="脚本 HTTP JWT 验收正文。",
            content_hash="script-http-member-v1",
            status="selected",
        )
        session.add(selected_version)
        await session.flush()
        chapter.selected_version_id = selected_version.id

        cancel_task = TaskRuntime(
            task_id="script-owner-cancel-run",
            owner_user_id=owner.id,
            project_id=PROJECT_ID,
            chapter_id=str(cancel_chapter.id),
            task_type="chapter_generation",
            status="running",
            stage="drafting",
            progress=42.0,
            message="Owner 运行中",
            lease_owner="script-owner-cancel-worker",
            lease_generation=5,
            payload={"run_id": "script-owner-cancel-run"},
        )
        resume_task = TaskRuntime(
            task_id="script-owner-resume-run",
            owner_user_id=owner.id,
            project_id=PROJECT_ID,
            chapter_id=str(resume_chapter.id),
            task_type="chapter_generation",
            status="stale",
            stage="checkpoint",
            progress=58.0,
            message="Owner 等待断点恢复",
            lease_owner="script-owner-resume-worker",
            lease_generation=8,
            payload={
                "run_id": "script-owner-resume-run",
                "generation_spec": {
                    "writing_notes": "deterministic acceptance",
                    "flow_config": {"preset": "basic", "versions": 1},
                },
            },
        )
        stream_task = TaskRuntime(
            task_id="script-http-stream-run",
            owner_user_id=owner.id,
            project_id=PROJECT_ID,
            chapter_id=str(chapter.id),
            task_type="chapter_generation",
            status="succeeded",
            stage="completed",
            progress=100.0,
            message="SSE 终态",
            lease_owner="script-stream-worker",
            lease_generation=2,
            payload={"run_id": "script-http-stream-run", "project_id": PROJECT_ID, "chapter_id": str(chapter.id)},
        )
        other_task = TaskRuntime(
            task_id="script-http-other-run",
            owner_user_id=outsider.id,
            project_id=OTHER_PROJECT_ID,
            chapter_id=str(other_chapter.id),
            task_type="chapter_generation",
            status="succeeded",
            stage="completed",
            progress=100.0,
            message="隔离 SSE 终态",
            payload={"run_id": "script-http-other-run", "project_id": OTHER_PROJECT_ID, "chapter_id": str(other_chapter.id)},
        )
        session.add_all([cancel_task, resume_task, stream_task, other_task])
        await session.flush()
        first_event = TaskRuntimeEvent(
            task_id=stream_task.task_id,
            event_type="content_delta",
            status="running",
            stage="writing",
            progress=65.0,
            message="脚本 SSE 内容事件",
            payload={"delta": "script-shared-delta"},
            idempotency_key="script-http-stream-first",
        )
        terminal_event = TaskRuntimeEvent(
            task_id=stream_task.task_id,
            event_type="task_completed",
            status="succeeded",
            stage="completed",
            progress=100.0,
            message="脚本 SSE 终态事件",
            payload={"word_count": 1200},
            idempotency_key="script-http-stream-terminal",
        )
        session.add_all([first_event, terminal_event])
        await session.commit()
        await session.refresh(first_event)
        await session.refresh(terminal_event)

    return {
        "owner": owner,
        "editor": editor,
        "viewer": viewer,
        "admin": admin,
        "outsider": outsider,
        "project": project,
        "other_project": other_project,
        "chapter": chapter,
        "cancel_chapter": cancel_chapter,
        "resume_chapter": resume_chapter,
        "selected_version": selected_version,
        "first_event_id": int(first_event.event_id),
        "terminal_event_id": int(terminal_event.event_id),
    }


def _detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
        return str(payload.get("detail", payload))[:300] if isinstance(payload, dict) else str(payload)[:300]
    except Exception:
        return response.text[:300]


def _expect(response: httpx.Response, expected: set[int], phase: str) -> httpx.Response:
    if response.status_code not in expected:
        raise AcceptanceFailure(f"phase={phase} status={response.status_code} detail={_detail(response)}")
    return response


async def _login(client: httpx.AsyncClient, fixture: dict[str, Any]) -> dict[str, dict[str, str]]:
    tokens: dict[str, dict[str, str]] = {}
    for role in ("owner", "editor", "viewer", "admin", "outsider"):
        user = fixture[role]
        response = _expect(
            await client.post("/api/auth/login", data={"username": user.username, "password": PASSWORD}),
            {200},
            f"login:{role}",
        )
        tokens[role] = {"Authorization": f"Bearer {response.json()['access_token']}"}
    return tokens


async def _run_checks(fixture: dict[str, Any]) -> dict[str, Any]:
    dispatches: list[dict[str, Any]] = []

    async def fake_generate(*args: Any, **kwargs: Any) -> None:
        dispatches.append({"kind": "generate", "args": list(args), "kwargs": dict(kwargs)})

    async def fake_outline(*args: Any, **kwargs: Any) -> None:
        dispatches.append({"kind": "outline", "args": list(args), "kwargs": dict(kwargs)})

    async def fake_finalize(*args: Any, **kwargs: Any) -> dict[str, Any]:
        dispatches.append({"kind": "finalize", "args": list(args), "kwargs": dict(kwargs)})
        return {"success": True, "fixture": True}

    original_generate = writer._schedule_generate_task
    original_outline = writer._schedule_outline_recovery
    original_finalize = writer._run_finalize_pipeline
    writer._schedule_generate_task = fake_generate
    writer._schedule_outline_recovery = fake_outline
    writer._run_finalize_pipeline = fake_finalize
    try:
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)
        async with httpx.AsyncClient(transport=transport, base_url="http://writer-member-acceptance") as client:
            tokens = await _login(client, fixture)
            project_id = fixture["project"].id
            other_project_id = fixture["other_project"].id

            for role in ("owner", "editor", "viewer", "admin"):
                payload = _expect(
                    await client.get(f"/api/projects/{project_id}/members", headers=tokens[role]),
                    {200},
                    f"members:{role}",
                ).json()
                if {item["user_id"] for item in payload["members"]} != {98201, 98202, 98203}:
                    raise AcceptanceFailure(f"phase=members:{role} unexpected member set")
            _expect(await client.get(f"/api/projects/{project_id}/members", headers=tokens["outsider"]), {403}, "members:outsider")

            for role in ("owner", "editor", "viewer", "admin"):
                for suffix in ("chapters/1/status", "chapters/outline/status", "chapters/rewrite-outline/status"):
                    _expect(await client.get(f"/api/writer/novels/{project_id}/{suffix}", headers=tokens[role]), {200}, f"status:{role}:{suffix}")
            _expect(await client.get(f"/api/writer/novels/{project_id}/chapters/1/status", headers=tokens["outsider"]), {403}, "status:outsider")

            stream = _expect(
                await client.get(f"/api/writer/novels/{project_id}/chapters/1/stream", headers=tokens["viewer"], params={"after_event_id": 0}),
                {200},
                "sse:first",
            )
            if f"id: {fixture['first_event_id']}" not in stream.text or f"id: {fixture['terminal_event_id']}" not in stream.text or "event: task_completed" not in stream.text:
                raise AcceptanceFailure("phase=sse:first missing durable replay events")

            replay = _expect(
                await client.get(f"/api/writer/novels/{project_id}/chapters/1/stream", headers=tokens["editor"], params={"after_event_id": fixture["first_event_id"]}),
                {200},
                "sse:cursor",
            )
            if f"id: {fixture['first_event_id']}" in replay.text or "script SSE 内容事件" in replay.text or f"id: {fixture['terminal_event_id']}" not in replay.text:
                raise AcceptanceFailure("phase=sse:cursor cursor replay returned an earlier event")
            isolated = _expect(
                await client.get(f"/api/writer/novels/{other_project_id}/chapters/1/stream", headers=tokens["outsider"], params={"after_event_id": 0}),
                {200},
                "sse:isolation",
            )
            if "script SSE 内容事件" in isolated.text:
                raise AcceptanceFailure("phase=sse:isolation leaked shared project event")
            _expect(await client.get(f"/api/writer/novels/{project_id}/chapters/1/stream", headers=tokens["outsider"], params={"after_event_id": 0}), {403}, "sse:outsider")

            generated = _expect(
                await client.post(
                    f"/api/writer/novels/{project_id}/chapters/generate",
                    headers=tokens["editor"],
                    json={"chapter_number": 2, "target_word_count": 800, "min_word_count": 500, "preset": "basic", "generation_timeout_seconds": 30},
                ),
                {200, 202},
                "generate:editor",
            )
            if not dispatches or dispatches[-1]["kind"] != "generate":
                raise AcceptanceFailure("phase=generate:editor deterministic scheduler was not called")

            cancelled = _expect(
                await client.post(f"/api/writer/novels/{project_id}/chapters/cancel", headers=tokens["editor"], json={"chapter_number": 3, "reason": "member acceptance cancel"}),
                {200},
                "cancel:editor-owner-run",
            )
            if cancelled.status_code != 200:
                raise AcceptanceFailure("phase=cancel:editor-owner-run unexpected response")

            resumed = _expect(
                await client.post(f"/api/writer/novels/{project_id}/chapters/resume", headers=tokens["editor"], json={"run_id": "script-owner-resume-run"}),
                {200, 202},
                "resume:editor-owner-run",
            )
            if not any(item["kind"] == "generate" for item in dispatches):
                raise AcceptanceFailure("phase=resume:editor-owner-run deterministic scheduler was not called")

            finalized = _expect(
                await client.post(
                    "/api/writer/chapters/1/finalize",
                    headers=tokens["editor"],
                    json={"project_id": project_id, "selected_version_id": fixture["selected_version"].id, "async_finalize": False, "skip_vector_update": True},
                ),
                {200},
                "finalize:editor",
            )
            if finalized.json().get("result", {}).get("fixture") is not True:
                raise AcceptanceFailure("phase=finalize:editor fixture pipeline result missing")

            outline = _expect(
                await client.post(
                    f"/api/writer/novels/{project_id}/chapters/outline/start",
                    headers=tokens["editor"],
                    json={"start_chapter": 5, "num_chapters": 2, "chapter_word_target": 800},
                ),
                {200, 202},
                "outline:start:editor",
            )
            if not any(item["kind"] == "outline" for item in dispatches):
                raise AcceptanceFailure("phase=outline:start:editor deterministic scheduler was not called")
            _expect(await client.post(f"/api/writer/novels/{project_id}/chapters/outline/cancel", headers=tokens["editor"]), {200}, "outline:cancel:editor")
            _expect(await client.post(f"/api/writer/novels/{project_id}/chapters/generate", headers=tokens["viewer"], json={"chapter_number": 2}), {403}, "generate:viewer")
            _expect(await client.post(f"/api/writer/novels/{project_id}/chapters/generate", headers=tokens["outsider"], json={"chapter_number": 2}), {403}, "generate:outsider")

            return {
                "checks": 5 + 12 + 5 + 9,
                "dispatch_kinds": [item["kind"] for item in dispatches],
                "generate_status": generated.status_code,
                "resume_status": resumed.status_code,
                "finalize_status": finalized.status_code,
                "outline_status": outline.status_code,
            }
    finally:
        writer._schedule_generate_task = original_generate
        writer._schedule_outline_recovery = original_outline
        writer._run_finalize_pipeline = original_finalize


async def _async_main(*, keep: bool) -> int:
    temp_dir = _RUNTIME_DIR
    db_path = _DB_PATH
    print(f"ISOLATED_DB={db_path}")
    try:
        async with app.router.lifespan_context(app):
            fixture = await _seed()
            result = await _run_checks(fixture)
            print("SMOKE_PASSED " + json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 0
    except AcceptanceFailure as exc:
        print(f"SMOKE_FAILED {exc}")
        return 1
    except Exception as exc:  # noqa: BLE001 - smoke must report unexpected failures
        print(f"SMOKE_ERROR {type(exc).__name__}: {str(exc)[:500]}")
        return 1
    finally:
        await engine.dispose()
        if keep:
            print(f"KEPT_DIR={temp_dir}")
        else:
            shutil.rmtree(temp_dir, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="隔离 SQLite/JWT Writer 成员 HTTP 验收")
    parser.add_argument("--keep", action="store_true", help="保留本次临时 SQLite 与运行目录")
    args = parser.parse_args()
    return asyncio.run(_async_main(keep=args.keep))


if __name__ == "__main__":
    raise SystemExit(main())

