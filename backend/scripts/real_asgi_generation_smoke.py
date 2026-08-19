"""真实隔离 ASGI 章节生成验收脚本，不输出认证令牌或 Provider 密钥。"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
load_dotenv(ROOT / ".env")
db_path = ROOT / "storage" / f"real-asgi-{time.time_ns()}.db"
os.environ["DB_PROVIDER"] = "sqlite"
os.environ["SQLITE_DB_PATH"] = str(db_path)
sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402
from app.api.routers.writer import stream_chapter_progress  # noqa: E402
from app.db.session import AsyncSessionLocal, engine  # noqa: E402
from app.models.novel import Chapter, NovelProject  # noqa: E402
from app.models.novel import ChapterVersion  # noqa: E402
from sqlalchemy import select  # noqa: E402


class _ConnectedSmokeRequest:
    """Route-level SSE probe request: ASGITransport buffers infinite media streams."""

    async def is_disconnected(self) -> bool:
        return False


def _safe_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
        detail = payload.get("detail", payload) if isinstance(payload, dict) else payload
        return str(detail)[:300]
    except Exception:
        return response.text[:300]


async def main() -> int:
    username = os.getenv("ADMIN_DEFAULT_USERNAME", "admin")
    password = os.getenv("ADMIN_DEFAULT_PASSWORD", "")
    if not password:
        print("SMOKE_BLOCKED missing admin password configuration")
        return 2

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver", timeout=30.0) as client:
            login = await client.post(
                "/api/auth/login",
                data={"username": username, "password": password},
            )
            print(f"LOGIN status={login.status_code}")
            if login.status_code != 200:
                print(f"LOGIN_ERROR {_safe_error(login)}")
                return 1
            token = login.json().get("access_token")
            headers = {"Authorization": f"Bearer {token}"}

            project = await client.post(
                "/api/novels",
                headers=headers,
                json={
                    "title": f"ASGI验收-{int(time.time())}",
                    "initial_prompt": "都市悬疑短章验收：旧档案修复师发现一份不应存在的潮汐记录。",
                },
            )
            print(f"PROJECT status={project.status_code}")
            if project.status_code not in (200, 201):
                print(f"PROJECT_ERROR {_safe_error(project)}")
                return 1
            project_payload = project.json()
            project_id = project_payload.get("id") or project_payload.get("project_id")
            if not project_id:
                print(f"PROJECT_ERROR missing project identifier keys={sorted(project_payload.keys())}")
                return 1

            generate = await client.post(
                f"/api/writer/novels/{project_id}/chapters/generate",
                headers=headers,
                json={
                    "chapter_number": 1,
                    "target_word_count": 1200,
                    "min_word_count": 900,
                    "preset": "enhanced",
                    "generation_timeout_seconds": 900,
                    "segment_word_limit": 1200,
                },
            )
            print(f"GENERATE status={generate.status_code}")
            if generate.status_code not in (200, 202):
                print(f"GENERATE_ERROR {_safe_error(generate)}")
                return 1

            # 后端章节流水线包含上下文、候选正文和质量门；单次 Provider
            # 调用上限约 200 秒，验收窗口必须覆盖该上限及落库收尾时间。
            deadline = time.monotonic() + 360
            last_stage = None
            terminal = {"successful", "failed", "waiting_for_confirm", "evaluation_failed", "cancelled"}
            status_payload: dict = {}
            while time.monotonic() < deadline:
                status = await client.get(
                    f"/api/writer/novels/{project_id}/chapters/1/status",
                    headers=headers,
                )
                if status.status_code != 200:
                    print(f"STATUS status={status.status_code} error={_safe_error(status)}")
                    return 1
                status_payload = status.json()
                runtime = status_payload.get("generation_runtime") or {}
                chapter_status = status_payload.get("generation_status") or status_payload.get("status")
                stage = runtime.get("progress_stage") or chapter_status
                if stage != last_stage:
                    print(
                        f"PROGRESS status={chapter_status} stage={stage} "
                        f"percent={runtime.get('progress_percent')} words={status_payload.get('word_count', 0)}"
                    )
                    last_stage = stage
                if chapter_status in terminal:
                    break
                await asyncio.sleep(2)
            else:
                print("SMOKE_TIMEOUT")
                return 1

            # httpx.ASGITransport buffers text/event-stream responses until the
            # generator closes, which makes it unsuitable for validating an infinite
            # live route. Consume the same authenticated route handler directly with
            # a bounded iterator; ownership and TaskRuntime lookup still run here.
            try:
                async with AsyncSessionLocal() as stream_session:
                    owner_id = await stream_session.scalar(
                        select(NovelProject.user_id).where(NovelProject.id == project_id)
                    )
                    stream_response = await stream_chapter_progress(
                        project_id,
                        1,
                        _ConnectedSmokeRequest(),
                        after_event_id=0,
                        last_event_id=None,
                        session=stream_session,
                        current_user=SimpleNamespace(id=owner_id),
                    )
                    chunks: list[str] = []

                    async def _consume_stream() -> None:
                        async for chunk in stream_response.body_iterator:
                            chunks.append(chunk)

                    await asyncio.wait_for(_consume_stream(), timeout=20.0)
            except asyncio.TimeoutError:
                print("STREAM_TIMEOUT endpoint did not close after terminal task")
                return 1
            stream_text = "".join(chunks)
            stream_events = stream_text.count("event:")
            print(
                f"STREAM status=200 events={stream_events} "
                f"content_deltas={stream_text.count('event: content_delta')} "
                f"terminal_completed={stream_text.count('event: task_completed')} "
                f"terminal_failed={stream_text.count('event: task_failed')} "
                f"terminal_cancelled={stream_text.count('event: task_cancelled')}"
            )
            terminal_events = {"event: task_completed", "event: task_failed", "event: task_cancelled"}
            stream_terminal = next((event for event in terminal_events if event in stream_text), None)
            if stream_events < 1 or stream_terminal is None:
                print("STREAM_ERROR missing terminal task event")
                return 1

            # 用同一真实任务验证 Last-Event-ID 续接：从最后一段正文之后重连，
            # 只能看到更大的游标和终态，不能把已经消费的正文再送一次。
            content_event_ids = [
                int(value)
                for value in re.findall(r"^id: (\d+)\nevent: content_delta$", stream_text, flags=re.MULTILINE)
            ]
            if not content_event_ids:
                print("REPLAY_ERROR no content cursor available")
                return 1
            resume_cursor = content_event_ids[-1]
            async with AsyncSessionLocal() as replay_session:
                replay_response = await stream_chapter_progress(
                    project_id,
                    1,
                    _ConnectedSmokeRequest(),
                    after_event_id=0,
                    last_event_id=resume_cursor,
                    session=replay_session,
                    current_user=SimpleNamespace(id=owner_id),
                )
                replay_chunks: list[str] = []

                async def _consume_replay() -> None:
                    async for chunk in replay_response.body_iterator:
                        replay_chunks.append(chunk)

                await asyncio.wait_for(_consume_replay(), timeout=20.0)
            replay_text = "".join(replay_chunks)
            replay_ids = [int(value) for value in re.findall(r"^id: (\d+)$", replay_text, flags=re.MULTILINE)]
            print(
                f"REPLAY after={resume_cursor} events={len(replay_ids)} "
                f"content_deltas={replay_text.count('event: content_delta')} "
                f"terminal_completed={replay_text.count('event: task_completed')} "
                f"terminal_failed={replay_text.count('event: task_failed')} "
                f"terminal_cancelled={replay_text.count('event: task_cancelled')}"
            )
            replay_terminal = next((event for event in terminal_events if event in replay_text), None)
            if (
                not replay_ids
                or any(event_id <= resume_cursor for event_id in replay_ids)
                or replay_terminal is None
            ):
                print("REPLAY_ERROR invalid Last-Event-ID replay")
                return 1

            novel = await client.get(f"/api/novels/{project_id}", headers=headers)
            print(f"NOVEL status={novel.status_code}")
            if novel.status_code != 200:
                print(f"NOVEL_ERROR {_safe_error(novel)}")
                return 1
            chapters = novel.json().get("chapters") or []
            chapter = next((item for item in chapters if item.get("chapter_number") == 1), None)
            content = (chapter or {}).get("content") or ""
            print(
                f"RESULT final_status={status_payload.get('generation_status') or status_payload.get('status')} content_chars={len(content)} "
                f"word_count={(chapter or {}).get('word_count', 0)} "
                f"has_runtime={bool((chapter or {}).get('generation_runtime'))}"
            )
            final_status = status_payload.get("generation_status") or status_payload.get("status")
            if final_status not in {"successful", "waiting_for_confirm"}:
                print(f"RESULT_ERROR {json.dumps(status_payload.get('generation_runtime') or {}, ensure_ascii=False)[:500]}")
                return 1
            if len(content) < 900:
                print("RESULT_ERROR content below minimum")
                return 1

            # 短章策略的关键验收：正文只允许一次正式 Provider 调用，且任务书
            # 的抽象措辞不得泄漏进正文。诊断保留在版本 metadata，便于失败复盘。
            async with AsyncSessionLocal() as verification_session:
                persisted_chapter = await verification_session.scalar(
                    select(Chapter).where(
                        Chapter.project_id == project_id,
                        Chapter.chapter_number == 1,
                    )
                )
                version = await verification_session.scalar(
                    select(ChapterVersion)
                    .where(ChapterVersion.chapter_id == persisted_chapter.id)
                    .order_by(ChapterVersion.id.desc())
                )
                metadata = version.metadata if version and isinstance(version.metadata, dict) else {}
                metrics = metadata.get("generation_call_metrics") if isinstance(metadata.get("generation_call_metrics"), list) else []
                draft_calls = [
                    item for item in metrics
                    if isinstance(item, dict) and str(item.get("label") or "").startswith("draft_candidate_")
                ]
                continuation_calls = [
                    item for item in metrics
                    if isinstance(item, dict) and str(item.get("label") or "").startswith("continuation_round_")
                ]
                retry = metadata.get("first_draft_retry") if isinstance(metadata.get("first_draft_retry"), dict) else {}
                retry_reasons = set(retry.get("reason_codes") or []) if isinstance(retry.get("reason_codes"), list) else set()
                print(
                    f"QUALITY draft_calls={len(draft_calls)} continuation_calls={len(continuation_calls)} "
                    f"first_draft_retry={bool(retry.get('used'))} "
                    f"retry_reasons={sorted(retry_reasons)} "
                    f"mission_source={((metadata.get('chapter_mission') or {}).get('generation_source'))}"
                )
                # 短章只能有一个首稿和一次受控的连续补足。抽象任务书命中、
                # 静态描写或对白启发式不得触发第二次整章重写。
                if (
                    len(draft_calls) != 1
                    or len(continuation_calls) > 1
                    or retry.get("used")
                    or retry_reasons
                ):
                    print("QUALITY_ERROR short chapter used an unexpected rewrite/provider retry")
                    return 1
            forbidden_contract_text = "在压力下作出了改变后续选择的行动"
            if forbidden_contract_text in content or re.search(
                r'(?m)^\s*\{\s*"(?:continuation|content|chapter_content)"\s*:', content
            ):
                print("QUALITY_ERROR local contract or JSON envelope leaked into prose")
                return 1
    await engine.dispose()
    print(f"SMOKE_PASS db={db_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
