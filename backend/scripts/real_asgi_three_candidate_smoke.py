"""Real ASGI E-06 candidate-diversity smoke; never emits chapter prose or credentials."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
load_dotenv(ROOT / ".env")
os.environ["DB_PROVIDER"] = "sqlite"
os.environ["SQLITE_DB_PATH"] = str(ROOT / "storage" / f"real-asgi-e06-{time.time_ns()}.db")
sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402
from app.utils.smoke_timeout import resolve_smoke_poll_timeout_seconds  # noqa: E402
from app.db.session import AsyncSessionLocal, engine  # noqa: E402
from app.models.novel import Chapter, ChapterVersion  # noqa: E402
from sqlalchemy import select  # noqa: E402


METRIC_KEYS = (
    "score", "word_count", "event_density_passed", "ending_pressure_passed",
    "dialogue_changes_state", "reversal_signal_count", "dialogue_ratio",
    "action_ratio", "description_ratio", "speaker_count",
    "dominant_speaker_ratio", "hard_scene_cut_count", "summary_scene_cut_count",
)


def resolve_e06_output_path(requested: str | None = None) -> Path:
    """Allocate a unique, output-root-contained evidence file without overwriting prior runs."""
    output_root = (ROOT / "output").resolve()
    raw_path = str(requested or os.getenv("E06_OUTPUT_PATH") or "").strip()
    candidate = Path(raw_path) if raw_path else output_root / f"e06-three-candidate-asgi-{time.time_ns()}.json"
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    candidate = candidate.resolve()
    if candidate.parent != output_root:
        raise ValueError("E06 输出必须直接位于 backend/output，禁止覆盖或写出证据目录。")
    if candidate.exists():
        raise FileExistsError(f"E06 输出已存在，拒绝覆盖历史证据：{candidate.name}")
    return candidate


def _safe_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
        return str(payload.get("detail", payload))[:300] if isinstance(payload, dict) else str(payload)[:300]
    except Exception:
        return response.text[:300]


def _metrics(metadata: dict[str, Any]) -> dict[str, Any]:
    # Compact snapshot owns observability dimensions, while the full story guard
    # owns the selection score. Do not let a stale compact score alter E-06 margins.
    guard = metadata.get("story_progression_guard")
    compact = metadata.get("quality_metrics")
    merged: dict[str, Any] = {}
    if isinstance(compact, dict):
        merged.update(compact)
    if isinstance(guard, dict):
        for key, value in guard.items():
            if key == "score" or key not in merged:
                merged[key] = value
    return merged


def summarize_candidates(*, versions: list[dict[str, Any]], selected_version_id: int | None) -> dict[str, Any]:
    """Return only candidate-level diagnostics needed by E-06, never content."""
    records: list[dict[str, Any]] = []
    values_by_key: dict[str, set[str]] = {key: set() for key in METRIC_KEYS}
    selected_score: int | float | None = None
    unselected_scores: list[int | float] = []
    for item in versions:
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        metrics = _metrics(metadata)
        version_id = item.get("id")
        ai_review = metadata.get("ai_review") if isinstance(metadata.get("ai_review"), dict) else {}
        record = {
            "version_id": version_id,
            "version_label": item.get("version_label"),
            "selected": version_id == selected_version_id,
            "ai_selected": ai_review.get("is_best"),
            "ai_original_selected": ai_review.get("ai_original_best"),
            "heuristic_best": ai_review.get("heuristic_best"),
            "heuristic_score": ai_review.get("heuristic_score"),
            "heuristic_rank": ai_review.get("heuristic_rank"),
            "content_sha256": hashlib.sha256(str(item.get("content") or "").encode("utf-8")).hexdigest(),
            "quality_issue_codes": list(metrics.get("quality_issue_codes") or []),
        }
        for key in METRIC_KEYS:
            value = metrics.get(key)
            record[key] = value
            if value is not None:
                values_by_key[key].add(json.dumps(value, ensure_ascii=True, sort_keys=True))
        score = metrics.get("score")
        if isinstance(score, (int, float)) and not isinstance(score, bool):
            if record["selected"]:
                selected_score = score
            else:
                unselected_scores.append(score)
        records.append(record)
    divergent_dimensions = sorted(key for key, values in values_by_key.items() if len(values) >= 2)
    score_margin = None
    if selected_score is not None and unselected_scores:
        score_margin = selected_score - max(unselected_scores)
    return {
        "candidate_count": len(records),
        "selected_version_id": selected_version_id,
        "records": records,
        "divergent_dimensions": divergent_dimensions,
        "divergent_dimension_count": len(divergent_dimensions),
        "selected_score_margin_over_best_unselected": score_margin,
        "e06_candidate_count_passed": len(records) == 3,
        "e06_two_dimension_diversity_passed": len(divergent_dimensions) >= 2,
        "e06_score_margin_passed": score_margin is not None and score_margin >= 300,
    }


async def main() -> int:
    try:
        output = resolve_e06_output_path()
    except (ValueError, FileExistsError) as exc:
        print("E06_BLOCKED", str(exc))
        return 2
    username = os.getenv("ADMIN_DEFAULT_USERNAME", "admin")
    password = os.getenv("ADMIN_DEFAULT_PASSWORD", "")
    target_word_count = 1200
    min_word_count = 1080
    safe: dict[str, Any] = {
        "requested_versions": 3,
        "target_word_count": target_word_count,
        "min_word_count": min_word_count,
    }
    try:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
                timeout=45.0,
            ) as client:
                login = await client.post("/api/auth/login", data={"username": username, "password": password})
                if login.status_code != 200:
                    print("E06_LOGIN_ERROR", _safe_error(login))
                    return 1
                headers = {"Authorization": f"Bearer {login.json().get('access_token')}"}
                project = await client.post("/api/novels", headers=headers, json={
                    "title": f"E06三候选验收-{int(time.time())}",
                    "initial_prompt": "都市悬疑：档案修复师在封存仓发现一枚仍在计时的旧钥匙。",
                })
                if project.status_code not in (200, 201):
                    print("E06_PROJECT_ERROR", _safe_error(project))
                    return 1
                project_id = project.json().get("id") or project.json().get("project_id")
                safe["project_id"] = project_id
                response = await client.post("/api/writer/advanced/generate", headers=headers, json={
                    "project_id": project_id,
                    "chapter_number": 1,
                    "writing_notes": "保持悬疑推进；三种候选必须采用不同叙事处理，但不得输出任务书或元信息。",
                    "flow_config": {
                        "preset": "enhanced", "versions": 3,
                        "target_word_count": target_word_count, "min_word_count": min_word_count,
                        "segment_word_limit": min(4500, target_word_count), "generation_timeout_seconds": 1800,
                    },
                })
                if response.status_code not in (200, 202):
                    print("E06_GENERATE_ERROR", _safe_error(response))
                    return 1
                submitted_payload = response.json() if response.content else {}
                poll_timeout_seconds = resolve_smoke_poll_timeout_seconds(
                    submitted_payload, requested_timeout_seconds=1800, fallback_timeout_seconds=1800
                )
                deadline = time.monotonic() + poll_timeout_seconds
                status_payload: dict[str, Any] = {}
                while time.monotonic() < deadline:
                    status = await client.get(f"/api/writer/novels/{project_id}/chapters/1/status", headers=headers)
                    if status.status_code != 200:
                        print("E06_STATUS_ERROR", _safe_error(status))
                        return 1
                    status_payload = status.json()
                    state = status_payload.get("generation_status") or status_payload.get("status")
                    if state in {"successful", "waiting_for_confirm", "failed", "evaluation_failed", "cancelled"}:
                        break
                    await asyncio.sleep(2)
                state = status_payload.get("generation_status") or status_payload.get("status")
                safe["final_status"] = state
                safe["runtime_stage"] = (status_payload.get("generation_runtime") or {}).get("progress_stage")
                async with AsyncSessionLocal() as session:
                    chapter = await session.scalar(select(Chapter).where(Chapter.project_id == project_id, Chapter.chapter_number == 1))
                    if chapter is None:
                        print("E06_DB_ERROR chapter missing")
                        return 1
                    rows = list((await session.execute(
                        select(ChapterVersion).where(ChapterVersion.chapter_id == chapter.id).order_by(ChapterVersion.id)
                    )).scalars())
                    payload = [{
                        "id": row.id,
                        "version_label": row.version_label,
                        "content": row.content,
                        "metadata": row.metadata if isinstance(row.metadata, dict) else {},
                    } for row in rows]
                    pipeline_best = next(
                        (item["id"] for item in payload if ((item.get("metadata") or {}).get("ai_review") or {}).get("is_best")),
                        chapter.selected_version_id,
                    )
                    safe["confirmed_version_id"] = chapter.selected_version_id
                    safe["pipeline_best_version_id"] = pipeline_best
                    safe.update(summarize_candidates(versions=payload, selected_version_id=pipeline_best))
                safe["evidence_file"] = output.name
                output.write_text(json.dumps(safe, ensure_ascii=False, indent=2), encoding="utf-8")
                print(json.dumps({key: safe.get(key) for key in (
                    "final_status", "candidate_count", "divergent_dimensions",
                    "selected_score_margin_over_best_unselected", "e06_candidate_count_passed",
                    "e06_two_dimension_diversity_passed", "e06_score_margin_passed",
                )}, ensure_ascii=False))
                return 0 if (
                    state in {"successful", "waiting_for_confirm"}
                    and safe["e06_candidate_count_passed"]
                    and safe["e06_two_dimension_diversity_passed"]
                    and safe["e06_score_margin_passed"]
                ) else 1
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
