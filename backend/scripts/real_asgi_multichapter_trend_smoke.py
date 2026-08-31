"""隔离项目三章真实生成与 quality-trend 端到端验收。"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")
os.environ["DB_PROVIDER"] = "sqlite"
os.environ["SQLITE_DB_PATH"] = str(ROOT / "storage" / f"real-asgi-multichapter-{time.time_ns()}.db")

from app.main import app
from app.utils.smoke_timeout import resolve_smoke_poll_timeout_seconds


def safe_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
        return str(payload.get("detail", payload))[:300]
    except Exception:
        return response.text[:300]


def compact_failure_diagnostics(payload: dict) -> dict:
    """保留失败原因，避免多章采样遇到一章拒绝就丢掉整批证据。"""
    runtime = payload.get("generation_runtime") or {}
    gate = runtime.get("quality_gate") or {}
    exemptions = gate.get("exemptions") if isinstance(gate.get("exemptions"), list) else []
    critique_exemption_applied = gate.get("critique_exemption_applied")
    if not isinstance(critique_exemption_applied, list):
        critique_exemption_applied = list(exemptions)
    def redacted_number(key: str):
        value = gate.get(key)
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    critique_source = gate.get("selected_critique_source")
    if not isinstance(critique_source, str) or not critique_source.strip():
        critique_source = None
    else:
        critique_source = critique_source.strip()[:96]

    patch_suggestions = gate.get("patch_suggestions") if isinstance(gate.get("patch_suggestions"), list) else []
    quality_issue_codes = gate.get("quality_issue_codes") if isinstance(gate.get("quality_issue_codes"), list) else []
    return {
        "runtime_stage": runtime.get("progress_stage"),
        "error_code": runtime.get("error_code"),
        "quality_gate_passed": gate.get("passed"),
        "self_critique_final_score": redacted_number("self_critique_final_score"),
        "self_critique_critical_count": redacted_number("self_critique_critical_count"),
        "self_critique_major_count": redacted_number("self_critique_major_count"),
        "selected_critique_source": critique_source,
        "exemptions": [str(code) for code in exemptions],
        "critique_exemption_applied": [str(code) for code in critique_exemption_applied],
        "patch_suggestions": [
            {
                "code": str(item.get("code") or ""),
                "suggestion": str(item.get("suggestion") or "")[:360],
            }
            for item in patch_suggestions
            if isinstance(item, dict) and item.get("code")
        ],
        "quality_issue_codes": [str(code) for code in quality_issue_codes],
        "blocker_codes": [
            str(item.get("code"))
            for item in gate.get("blockers", [])
            if isinstance(item, dict) and item.get("code")
        ],
        "warning_codes": [
            str(item.get("code"))
            for item in gate.get("warnings", [])
            if isinstance(item, dict) and item.get("code")
        ],
    }


async def main(chapter_count: int = 3, *, enable_self_critique: bool = False, initial_prompt: str | None = None, writing_notes: str | None = None, preset: str = "enhanced", target_word_count: int = 1200, min_word_count: int = 900) -> int:
    username = os.getenv("ADMIN_DEFAULT_USERNAME", "admin")
    password = os.getenv("ADMIN_DEFAULT_PASSWORD", "")
    if not password:
        print("MULTICHAPTER_BLOCKED missing admin password")
        return 2
    results = []
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver", timeout=45.0) as client:
            login = await client.post("/api/auth/login", data={"username": username, "password": password})
            if login.status_code != 200:
                print("MULTICHAPTER_LOGIN_ERROR", safe_error(login)); return 1
            headers = {"Authorization": f"Bearer {login.json().get('access_token')}"}
            project = await client.post("/api/novels", headers=headers, json={"title": f"多章趋势验收-{int(time.time())}", "initial_prompt": initial_prompt or "悬疑短章多章趋势验收。"})
            if project.status_code not in (200, 201):
                print("MULTICHAPTER_PROJECT_ERROR", safe_error(project)); return 1
            project_id = project.json().get("id") or project.json().get("project_id")
            for chapter_number in range(1, chapter_count + 1):
                request_payload = {
                    "chapter_number": chapter_number,
                    "target_word_count": target_word_count,
                    "min_word_count": min_word_count,
                    "preset": preset,
                    "generation_timeout_seconds": 900,
                    "segment_word_limit": target_word_count,
                }
                if writing_notes:
                    request_payload["writing_notes"] = writing_notes
                if enable_self_critique:
                    request_payload["flow_config"] = json.dumps(
                        {"enable_self_critique": True}, ensure_ascii=False
                    )
                response = await client.post(
                    f"/api/writer/novels/{project_id}/chapters/generate",
                    headers=headers,
                    json=request_payload,
                )
                if response.status_code not in (200, 202):
                    print("MULTICHAPTER_GENERATE_ERROR", chapter_number, safe_error(response)); return 1
                submitted_payload = response.json() if response.content else {}
                poll_timeout_seconds = resolve_smoke_poll_timeout_seconds(
                    submitted_payload, requested_timeout_seconds=900, fallback_timeout_seconds=900
                )
                deadline = time.monotonic() + poll_timeout_seconds
                payload = {}
                while time.monotonic() < deadline:
                    status = await client.get(f"/api/writer/novels/{project_id}/chapters/{chapter_number}/status", headers=headers)
                    if status.status_code != 200:
                        print("MULTICHAPTER_STATUS_ERROR", chapter_number, safe_error(status)); return 1
                    payload = status.json()
                    state = payload.get("generation_status") or payload.get("status")
                    if state in {"successful", "waiting_for_confirm", "failed", "evaluation_failed", "cancelled"}:
                        break
                    await asyncio.sleep(2)
                state = payload.get("generation_status") or payload.get("status")
                result = {
                    "chapter_number": chapter_number,
                    "status": state,
                    "word_count": payload.get("word_count"),
                    "content_char_count": payload.get("word_count"),
                    "word_count_unit": "content_char_count_legacy_api_field",
                    **compact_failure_diagnostics(payload),
                }
                results.append(result)
                print(json.dumps(result, ensure_ascii=False))
                if state not in {"successful", "waiting_for_confirm"}:
                    print("MULTICHAPTER_CHAPTER_REJECTED", chapter_number)
                    # 继续采样：拒绝样本本身是放行率/误杀率审计所需证据。
            trend = await client.get(f"/api/novels/{project_id}/quality-trend", headers=headers)
            if trend.status_code != 200:
                print("MULTICHAPTER_TREND_ERROR", safe_error(trend)); return 1
            trend_payload = trend.json()
            successful = sum(item["status"] in {"successful", "waiting_for_confirm"} for item in results)
            rejected = len(results) - successful
            safe = {
                "project_id": project_id,
                "requested_chapter_count": chapter_count,
                "chapter_count": trend_payload.get("chapter_count"),
                "attempted_count": len(results),
                "successful_count": successful,
                "rejected_count": rejected,
                "pass_rate": successful / len(results) if results else 0.0,
                "attempt_results": results,
                "chapters": [{k: c.get(k) for k in (
                    "chapter_number", "status", "score", "word_count",
                    "self_critique_final_score", "self_critique_critical_count",
                    "self_critique_major_count", "selected_critique_source",
                    "event_density_passed", "event_density_skip_reason",
                    "ending_pressure_passed", "dialogue_changes_state",
                    "reversal_signal_count", "reversal_in_late_section",
                    "dialogue_ratio", "action_ratio", "description_ratio",
                    "speaker_count", "dominant_speaker_ratio",
                    "hard_scene_cut_count", "summary_scene_cut_count",
                    "scene_transition_warning", "continuity_inherit_missing",
                    "continuity_inherit_late", "mission_quality_codes",
                    "blocker_codes", "warning_codes", "exemptions", "critique_exemption_applied",
                    "patch_suggestions", "quality_issue_codes",
                )} | {
                    "quality_metric_word_count": c.get("word_count"),
                    "word_count_unit": "quality_metric_word_count",
                } for c in trend_payload.get("chapters", [])],
                "word_count_semantics": {
                    "attempt_results.word_count": "legacy API field; persisted content character count",
                    "attempt_results.content_char_count": "persisted content character count",
                    "chapters.word_count": "quality metric word count",
                    "chapters.quality_metric_word_count": "quality metric word count",
                },
                "blocker_counts": trend_payload.get("blocker_counts"),
                "warning_counts": trend_payload.get("warning_counts"),
                "exemption_counts": trend_payload.get("exemption_counts"),
                "enable_self_critique": enable_self_critique,
                "target_word_count": target_word_count,
                "min_word_count": min_word_count,
                "preset": preset,
            }
            run_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            output = ROOT / "output" / f"e09-multichapter-trend-{chapter_count}chapters-{run_stamp}.json"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(safe, ensure_ascii=False, indent=2), encoding="utf-8")
            final_status = "pass" if rejected == 0 else "completed_with_rejections"
            print(json.dumps({"status": final_status, "chapter_count": safe["chapter_count"], "pass_rate": safe["pass_rate"], "trend_file": str(output)}, ensure_ascii=False))
    return 0 if rejected == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--chapters", type=int, default=3, choices=range(1, 21))
    parser.add_argument("--writing-notes", default=None, help="仅用于真实 repair 探针的写作约束。")
    parser.add_argument("--preset", choices=("basic", "enhanced", "ultimate"), default="enhanced")
    parser.add_argument("--target-word-count", type=int, default=1200)
    parser.add_argument("--min-word-count", type=int, default=900)
    parser.add_argument(
        "--initial-prompt",
        default=None,
        help="仅用于真实质量门探针的项目初始提示，不改变生产默认流程。",
    )
    parser.add_argument(
        "--enable-self-critique",
        action="store_true",
        help="仅用于真实 repair 观测；显式开启 self-critique，不改变生产默认配置。",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.chapters, enable_self_critique=args.enable_self_critique, initial_prompt=args.initial_prompt, writing_notes=args.writing_notes, preset=args.preset, target_word_count=args.target_word_count, min_word_count=args.min_word_count)))
