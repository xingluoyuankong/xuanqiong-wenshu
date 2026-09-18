"""
US-006: 章节生成主链端到端验收（真实 HTTP + 真实 SSE 长连接）

诚实约束：
- 本机没有真实 OPENAI_API_KEY（backend/.env 中为空），因此**不伪造**真实 Provider 调用成功。
- 打桩位置 = LLMService.get_llm_response（所有文本生成的真实出口）。
  桩打在更上层的 generation_call_service 无效，因为 pipeline_orchestrator 用
  `from ..services.generation_call_service import call_generation_text` 早绑定。
- 验证"链路可跑通"的工程事实：
    POST /api/writer/novels/{pid}/chapters/generate
      -> ChapterVersion 创建并持久化（直查 DB）
      -> 正文非空落库（直查 DB）
      -> GET .../chapters/1/status 投影
      -> GET /api/updates/stream/{task_id} 真实 SSE 帧（含 terminal event）
- 隔离：独立 DB + 独立端口（默认 18099），不动生产 8013 / 生产库。

用法：
    /app/venv/bin/python3 backend/tests/e2e_us006_chapter_flow.py
"""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path("/run/csi/mount-root/nas/4079184d856ecc166ed19d4887083405/qwenpaw-data/xuanqiong-wenshu")
BACKEND_ROOT = REPO_ROOT / "backend"
E2E_ENV = Path("/tmp/e2e_backend.env")
PORT = int(os.environ.get("E2E_PORT", "18099"))
BASE = f"http://127.0.0.1:{PORT}"
PY = "/app/venv/bin/python3"

sys.path.insert(0, str(REPO_ROOT))


def load_env_file(path: Path):
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()


load_env_file(E2E_ENV)

import httpx  # noqa: E402


def wait_ready(timeout: float = 90.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(f"{BASE}/api/health", timeout=3.0)
            if r.status_code == 200:
                return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(1.0)
    return False


async def sse_frames(client, path, headers, *, max_frames=40, idle_seconds=6.0):
    """真实长连接读 SSE 帧：拿到 terminal 或静默 idle_seconds 后断开。"""
    frames = []
    terminal = None
    async with client.stream("GET", path, headers=headers, timeout=None) as resp:
        ctype = resp.headers.get("content-type", "")
        status = resp.status_code
        iterator = resp.aiter_lines().__aiter__()
        while True:
            try:
                line = await asyncio.wait_for(iterator.__anext__(), timeout=idle_seconds)
            except (asyncio.TimeoutError, StopAsyncIteration):
                break
            if not line or not line.startswith("data:"):
                continue
            try:
                payload = json.loads(line[5:].strip())
            except json.JSONDecodeError:
                continue
            frames.append(payload)
            meta = payload.get("metadata") or {}
            if meta.get("event_kind") == "terminal" or meta.get("type") == "complete":
                terminal = payload
                break
            if len(frames) >= max_frames:
                break
    return status, ctype, frames, terminal


async def main():
    results = {}
    proc = subprocess.Popen(
        [PY, "-m", "uvicorn", "backend.tests.e2e_us006_app_stubbed:app",
         "--host", "127.0.0.1", "--port", str(PORT), "--log-level", "warning"],
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        results["server_ready"] = wait_ready()
        assert results["server_ready"], f"服务未就绪，日志: {(proc.stdout.read() or '')[:2000] if proc.stdout else ''}"

        # 真实 Provider 生成耗时长，且后台任务会持 SQLite 写锁，
        # status 读可能被阻塞 —— connect 短、read 长分别设置。
        timeout_cfg = httpx.Timeout(connect=10.0, read=float(os.environ.get("E2E_READ_TIMEOUT", "300")), write=10.0, pool=10.0)
        async with httpx.AsyncClient(base_url=BASE, timeout=timeout_cfg) as client:
            # 1. 登录
            r = await client.post("/api/auth/login", data={
                "username": os.environ.get("ADMIN_DEFAULT_USERNAME", "admin"),
                "password": os.environ.get("ADMIN_DEFAULT_PASSWORD", ""),
            })
            results["login"] = r.status_code
            assert r.status_code == 200, f"登录失败: {r.text[:300]}"
            headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

            # 2. 建项目
            uniq = os.urandom(3).hex()
            r = await client.post("/api/novels", json={
                "title": f"US006 E2E {uniq}",
                "genre": "玄幻",
                "description": "US-006 end-to-end verification",
                "initial_prompt": "写一部玄幻小说，主角林默，山雨欲来的开篇。",
            }, headers=headers)
            assert r.status_code in (200, 201), f"建项目失败: {r.text[:400]}"
            project_id = r.json().get("id")
            results["project_id"] = project_id

            # 2b. 保存蓝图（含第1章纲要）——generate 强依赖 outline
            r = await client.post(f"/api/novels/{project_id}/blueprint/save", json={
                "title": f"US006 E2E {uniq}",
                "genre": "玄幻",
                "one_sentence_summary": "少年林默在风雨将至的山门中揭开身世之谜。",
                "full_synopsis": "林默自幼被师父收养，山雨欲来之日，他手中的木匣引出一段被掩埋的血案。",
                "chapter_outline": [{
                    "chapter_number": 1,
                    "title": "山雨欲来",
                    "summary": "林默在山门前察觉异象，风起鸟静，他握紧木匣等待师父归来。",
                }],
            }, headers=headers)
            results["save_blueprint"] = r.status_code
            assert r.status_code == 200, f"保存蓝图失败: {r.text[:300]}"

            # 3. 触发 generate（同步返回 queued，后台跑）
            r = await client.post(
                f"/api/writer/novels/{project_id}/chapters/generate",
                json={"chapter_number": 1, "target_word_count": 300, "min_word_count": 100},
                headers=headers,
            )
            results["generate_http"] = r.status_code
            assert r.status_code == 200, f"generate 失败: {r.text[:500]}"

            # 4. 轮询 status 直到终态，拿到 run_id
            #    真实 Provider 生成期间，单 worker uvicorn 可能被 pipeline 长时间占用，
            #    且 SQLite 写锁会短暂阻塞读请求 —— 用短超时 + 容错重试，单次超时不致命。
            run_id = None
            status_body = {}
            consecutive_errors = 0
            poll_deadline = time.time() + float(os.environ.get("E2E_POLL_TIMEOUT", "600"))
            last_http = None
            while time.time() < poll_deadline:
                await asyncio.sleep(2.0)
                try:
                    r = await client.get(
                        f"/api/writer/novels/{project_id}/chapters/1/status",
                        headers=headers, timeout=20.0,
                    )
                except httpx.HTTPError:
                    consecutive_errors += 1
                    results["poll_transient_errors"] = consecutive_errors
                    continue
                last_http = r.status_code
                if r.status_code != 200:
                    continue
                status_body = r.json()
                rt = status_body.get("generation_runtime") or {}
                run_id = run_id or rt.get("task_id") or rt.get("run_id")
                if rt.get("progress_stage") in ("waiting_for_confirm", "completed", "failed"):
                    break
            r = type("R", (), {"status_code": last_http})()
            results["run_id"] = run_id
            results["run_id"] = run_id
            results["status_http"] = r.status_code
            results["status_stage"] = (status_body.get("generation_runtime") or {}).get("progress_stage")
            results["status_field"] = status_body.get("status")
            results["status_content_len"] = len(status_body.get("content") or "")
            results["status_content_head"] = (status_body.get("content") or "")[:100]
            results["status_versions"] = len(status_body.get("versions") or [])

            # 5. 真实 SSE 长连接
            sse_path = f"/api/updates/stream/{run_id}" if run_id else "/api/updates/stream/tasks"
            results["sse_path"] = sse_path
            sse_client = httpx.AsyncClient(base_url=BASE, timeout=None)
            try:
                status, ctype, frames, terminal = await sse_frames(sse_client, sse_path, headers)
                results["sse_http"] = status
                results["sse_content_type"] = ctype
                results["sse_frame_count"] = len(frames)
                results["sse_terminal_event"] = terminal
                results["sse_last_frames"] = [
                    {k: v for k, v in f.items() if k in ("level", "message", "metadata")}
                    for f in frames[-3:]
                ]
            finally:
                await sse_client.aclose()

            results["stub_calls"] = (await client.get("/__e2e/stub_calls")).json()

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:  # noqa: F821
            proc.kill()
        out = proc.stdout.read() if proc.stdout else ""
        if out:
            Path("/tmp/us006_server.log").write_text(out)

    # 6. 直查 DB
    from sqlalchemy import select  # noqa: E402
    from backend.app.db.session import AsyncSessionLocal  # noqa: E402
    from backend.app.models.novel import Chapter, ChapterVersion  # noqa: E402

    async with AsyncSessionLocal() as s:
        ch = (await s.execute(
            select(Chapter).where(Chapter.project_id == project_id, Chapter.chapter_number == 1)
        )).scalar_one_or_none()
        results["db_chapter_found"] = ch is not None
        results["db_chapter_status"] = getattr(ch, "status", None) if ch else None
        results["db_chapter_word_count"] = getattr(ch, "word_count", None) if ch else None
        results["db_chapter_selected_version_id"] = getattr(ch, "selected_version_id", None) if ch else None
        vs = (await s.execute(
            select(ChapterVersion).where(ChapterVersion.chapter_id == ch.id)
        )).scalars().all() if ch else []
        results["db_version_count"] = len(vs)
        results["db_version_labels"] = [v.version_label for v in vs]
        results["db_version_lens"] = [len(v.content or "") for v in vs]
        results["db_version_content_head"] = (vs[0].content or "")[:120] if vs else ""

    return results


if __name__ == "__main__":
    out = asyncio.run(main())
    print("=== US-006 E2E RESULT ===")
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
