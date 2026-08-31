"""Offline, redacted quality benchmark utilities for generated novel chapters."""
from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - backend runtime normally includes python-dotenv
    load_dotenv = None

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.utils.llm_tool import LLMClient

MISSIONS_DIR = ROOT / "scripts" / "bench_missions"


def _smoke_missions() -> list[Path]:
    """Smoke is permanently cost-capped to its three public fixtures."""
    return sorted(MISSIONS_DIR.glob("smoke-*.json"))


METRIC_FIELDS = (
    "score", "word_count", "eligibility_score", "quality_positive_score", "quality_penalty",
    "event_density_evaluated", "event_density_skip_reason", "event_density_passed",
    "long_chapter_density_passed", "state_change_interval_passed", "ending_pressure_passed", "dialogue_changes_state",
    "static_description_risk", "repetition_risk", "focus_character_missing",
    "reversal_signal_count", "reversal_in_late_section",
    "dialogue_ratio", "action_ratio", "description_ratio", "content_balance_penalty",
    "speaker_count", "dominant_speaker_ratio",
    "hard_scene_cut_count", "summary_scene_cut_count", "scene_transition_warning",
    "continuity_inherit_missing", "continuity_inherit_late", "mission_quality_codes",
    "quality_issue_codes",
)

LIVE_PROVIDER_ENV_KEYS = (
    ("OPENAI_API_KEY", "OPENAI_API_BASE_URL", "OPENAI_MODEL_NAME"),
    ("CPA_API_KEY", "CPA_API_BASE", "CPA_MODEL_NAME"),
    ("CODEX_AGENT_API_KEY", "CODEX_AGENT_BASE_URL", "OPENAI_MODEL_NAME"),
)
LIVE_PROMPT_CONTRACT_VERSION = "quality-bench-live-v5"
LIVE_SYSTEM_PROMPT = "你是中文网络小说章节作者。"
LIVE_PROMPT_VARIANTS = {
    "baseline": "",
    "candidate": (
        "\n\n【仅用于非生产 benchmark 的候选提示词】\n"
        "在不改写任务书事实的前提下，让每次行动明确改变信息、主动权、风险或关系；"
        "转折和结尾钩子必须通过可观察的具体事件落地，禁止用概括性说明代替。"
    ),
}


class LiveProviderBlocked(RuntimeError):
    """Live runner cannot safely continue without claiming a live result."""


def _load_local_env() -> None:
    if load_dotenv is not None:
        load_dotenv(ROOT / ".env")


def resolve_live_provider_config(environ: dict[str, str] | None = None) -> dict[str, Any]:
    """Resolve provider settings without returning or logging the credential."""
    source = environ if environ is not None else os.environ
    for key_name, base_name, model_name in LIVE_PROVIDER_ENV_KEYS:
        api_key = str(source.get(key_name) or "").strip()
        base_url = str(source.get(base_name) or "").strip().rstrip("/")
        configured_model = str(source.get(model_name) or "").strip() or "deepseek-v4-flash-free"
        if not api_key or not base_url:
            continue
        # Direct benchmark calls do not instantiate LLMClient, so normalize the
        # model through the same production resolver before probing or generating.
        # Otherwise a gateway-only bare alias can make this script report a false
        # "model_listed=false" / empty-body failure while production uses a valid ID.
        model = LLMClient._resolve_model(configured_model, base_url)
        return {
            "api_key": api_key,
            "base_url": base_url,
            "model": model,
            "configured_model": configured_model,
            "credential_env": key_name,
            "provider_host": urlsplit(base_url).hostname or "unknown",
        }
    raise LiveProviderBlocked(
        "未找到完整 live provider 配置；需要 API key 和 base URL，未执行生成请求。"
    )


def _safe_provider_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                return str(error.get("message") or error.get("type") or "provider_error")[:240]
            return str(payload.get("detail") or payload.get("message") or "provider_error")[:240]
    except (ValueError, TypeError):
        pass
    return response.text[:240].replace("\n", " ")


async def probe_live_provider(
    config: dict[str, Any],
    *,
    timeout: float = 20.0,
    client_factory: Any = httpx.AsyncClient,
) -> dict[str, Any]:
    """Probe an OpenAI-compatible endpoint; no result is considered live until chat succeeds."""
    started = time.perf_counter()
    headers = {"Authorization": f"Bearer {config['api_key']}"}
    try:
        async with client_factory(timeout=timeout) as client:
            response = await client.get(f"{config['base_url']}/models", headers=headers)
    except Exception as exc:  # pragma: no cover - exercised with fake client in tests
        return {
            "ready": False,
            "stage": "probe",
            "error_type": type(exc).__name__,
            "error": str(exc)[:240],
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        }
    model_ids: list[str] = []
    try:
        payload = response.json()
        if isinstance(payload, dict) and isinstance(payload.get("data"), list):
            model_ids = [str(item.get("id")) for item in payload["data"] if isinstance(item, dict) and item.get("id")]
    except (ValueError, TypeError):
        pass
    return {
        "ready": response.status_code == 200,
        "stage": "probe",
        "status_code": response.status_code,
        "model_listed": config["model"] in model_ids if model_ids else None,
        "model_count": len(model_ids),
        "error": None if response.status_code == 200 else _safe_provider_error(response),
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def _live_completion_max_tokens(mission: dict[str, Any]) -> int:
    """Keep direct live benchmark requests capable of meeting their fixed word contract."""
    target_word_count = max(1, int(mission.get("target_word_count") or 1200))
    # 中文输出在兼容网关的 token/字符比会波动；给固定验收任务两倍预算，
    # 但保留 12k 上限，避免单次异常任务无限扩张成本。
    return min(max(target_word_count * 2, 1200), 12_000)


def _resolve_live_prompt_variant(prompt_variant: str = "baseline") -> str:
    """Return an explicit non-production benchmark prompt variant or fail closed."""
    if prompt_variant not in LIVE_PROMPT_VARIANTS:
        available = ", ".join(sorted(LIVE_PROMPT_VARIANTS))
        raise ValueError(f"unsupported non-production prompt variant: {prompt_variant!r}; choose one of: {available}")
    return prompt_variant


def _live_request_messages(mission: dict[str, Any], *, prompt_variant: str = "baseline") -> list[dict[str, str]]:
    variant = _resolve_live_prompt_variant(prompt_variant)
    return [
        {"role": "system", "content": LIVE_SYSTEM_PROMPT},
        {"role": "user", "content": _mission_prompt(mission, prompt_variant=variant)},
    ]


def _live_request_contract(mission: dict[str, Any], *, prompt_variant: str = "baseline") -> dict[str, Any]:
    variant = _resolve_live_prompt_variant(prompt_variant)
    messages = _live_request_messages(mission, prompt_variant=variant)
    return {
        "schema_version": 2,
        "prompt_contract_version": LIVE_PROMPT_CONTRACT_VERSION,
        "prompt_variant": variant,
        "system_prompt_sha256": hashlib.sha256(messages[0]["content"].encode("utf-8")).hexdigest(),
        "user_prompt_sha256": hashlib.sha256(messages[1]["content"].encode("utf-8")).hexdigest(),
        "prompt_sha256": _sha256_canonical(messages),
        "temperature": 0.8,
        "max_tokens": _live_completion_max_tokens(mission),
        "max_tokens_policy": "min(max(target_word_count*2,1200),12000)",
        "response_transport": "sse_preferred_with_nonstream_compat_fallback",
        "retry_policy": {"max_attempts": 2, "retry_on": ["empty_response", "http_429", "http_5xx", "network_transport"], "honor_retry_after_seconds_cap": 15},
    }


def _mission_prompt(mission: dict[str, Any], *, prompt_variant: str = "baseline") -> str:
    variant = _resolve_live_prompt_variant(prompt_variant)
    mission_view = {key: value for key, value in mission.items() if key != "fixture_content"}
    target_word_count = max(1, int(mission.get("target_word_count") or 1200))
    min_word_count = max(1, int(mission.get("min_word_count") or target_word_count))
    return (
        "请根据下面固定的章节任务书，直接输出一章中文小说正文。\n"
        "只输出正文，不要解释、标题、JSON、写作计划或任务书复述。\n"
        f"目标正文长度约 {target_word_count} 个汉字，最低不少于 {min_word_count} 个汉字；达到字数也不得提前收束。\n"
        "执行顺序必须可见：开篇尽快出现目标与阻碍，中段出现行动/对话导致的信息、主动权或风险变化，后段兑现任务书 turn 与 end_hook。\n"
        "最后 10% 必须留下未解决的危险、期限、证据、选择、误会或代价，把压力递给下一章；禁止用总结、感想、恢复平静或‘一切结束’收尾。\n"
        f"写到至少 {min_word_count} 个汉字之前，不得写最终收束；若接近结尾仍未达最低长度，必须新增一轮具体行动、反制、发现或代价后再继续。\n"
        "收尾前逐项自检：是否兑现 turn、是否落地 end_hook、是否留下下一步压力；三项任一缺失都不要结束正文。\n"
        "每 2-3 段至少发生一次行动、发现、反制、关系变化或后果；避免空泛景物描写和重复心理。"
        f"{LIVE_PROMPT_VARIANTS[variant]}\n\n"
        f"固定章节任务书：{json.dumps(mission_view, ensure_ascii=False, sort_keys=True)}"
    )


async def _generate_live_content_once(
    client: Any,
    config: dict[str, Any],
    mission: dict[str, Any],
    *,
    timeout: float,
    prompt_variant: str = "baseline",
) -> tuple[str, dict[str, Any]]:
    started = time.perf_counter()
    url = f"{config['base_url']}/chat/completions"
    headers = {"Authorization": f"Bearer {config['api_key']}", "Content-Type": "application/json"}
    messages = _live_request_messages(mission, prompt_variant=prompt_variant)
    request_payload = {
        "model": config["model"],
        "messages": messages,
        "temperature": 0.8,
        "max_tokens": _live_completion_max_tokens(mission),
        "stream": True,
    }

    def _finish(content: Any, usage: Any, transport: str) -> tuple[str, dict[str, Any]]:
        normalized = str(content or "").strip()
        if not normalized:
            raise LiveProviderBlocked("provider chat 返回空正文，未写入 live 成功记录。")
        usage = usage if isinstance(usage, dict) else {}
        return normalized, {
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "response_chars": len(normalized),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
            "response_transport": transport,
        }

    stream_factory = getattr(client, "stream", None)
    if callable(stream_factory):
        async with stream_factory("POST", url, headers=headers, json=request_payload, timeout=timeout) as response:
            if response.status_code != 200:
                retry_after = getattr(response, "headers", {}).get("Retry-After") if getattr(response, "headers", None) else None
                suffix = f" retry_after_seconds={str(retry_after).strip()}" if retry_after else ""
                raise LiveProviderBlocked(f"provider SSE 请求失败 HTTP {response.status_code}{suffix}")
            fragments: list[str] = []
            usage: dict[str, Any] = {}
            raw_lines: list[str] = []
            saw_sse = False
            async for line in response.aiter_lines():
                line = str(line or "").strip()
                if not line:
                    continue
                if not line.startswith("data:"):
                    raw_lines.append(line)
                    continue
                saw_sse = True
                raw = line[5:].strip()
                if raw == "[DONE]":
                    break
                try:
                    event = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                if not isinstance(event, dict):
                    continue
                event_usage = event.get("usage")
                if isinstance(event_usage, dict):
                    usage.update(event_usage)
                choices = event.get("choices")
                if not isinstance(choices, list) or not choices:
                    continue
                choice = choices[0] if isinstance(choices[0], dict) else {}
                delta = choice.get("delta") if isinstance(choice.get("delta"), dict) else {}
                message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
                fragment = delta.get("content") if delta else message.get("content")
                if isinstance(fragment, str):
                    fragments.append(fragment)
            if saw_sse:
                return _finish("".join(fragments), usage, "sse")
            # 少数兼容网关忽略 stream=true 仍返回单行 JSON；安全解析后标记真实传输。
            try:
                payload = json.loads("\n".join(raw_lines))
                content = payload["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                raise LiveProviderBlocked(f"provider SSE 返回结构无有效正文: {type(exc).__name__}") from exc
            return _finish(content, payload.get("usage") if isinstance(payload, dict) else {}, "nonstream_gateway_response")

    # 测试替身和极旧兼容 client 未实现 stream；保留非流式兼容分支，绝不伪称 SSE。
    request_payload["stream"] = False
    response = await client.post(url, headers=headers, json=request_payload, timeout=timeout)
    if response.status_code != 200:
        raise LiveProviderBlocked(
            f"provider chat 请求失败 HTTP {response.status_code}: {_safe_provider_error(response)}"
        )
    try:
        payload = response.json()
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise LiveProviderBlocked(f"provider chat 返回结构无有效正文: {type(exc).__name__}") from exc
    return _finish(content, payload.get("usage") if isinstance(payload, dict) else {}, "nonstream_compat")


async def _generate_live_content(
    client: Any,
    config: dict[str, Any],
    mission: dict[str, Any],
    *,
    timeout: float,
    prompt_variant: str = "baseline",
) -> tuple[str, dict[str, Any]]:
    """Mirror the production bounded retry without hiding exhausted failures."""
    last_error: LiveProviderBlocked | None = None
    retry_events: list[dict[str, Any]] = []
    for attempt in range(1, 3):
        try:
            content, meta = await _generate_live_content_once(
                client, config, mission, timeout=timeout, prompt_variant=prompt_variant,
            )
            meta["attempts"] = attempt
            meta["retry_events"] = retry_events
            return content, meta
        except (LiveProviderBlocked, httpx.TransportError) as exc:
            error = (
                LiveProviderBlocked(f"provider transport interrupted: {type(exc).__name__}")
                if isinstance(exc, httpx.TransportError)
                else exc
            )
            last_error = error
            message = str(error).lower()
            retryable = (
                isinstance(exc, httpx.TransportError)
                or "空正文" in str(error)
                or any(f"http {code}" in message for code in (429, 500, 502, 503, 504, 524))
            )
            if attempt >= 2 or not retryable:
                # Exhausted/non-retryable failures are surfaced by the caller;
                # keep the final reason in the failure record rather than
                # pretending a retry occurred.
                raise error
            retry_events.append({
                "attempt": attempt,
                "error_type": type(exc).__name__,
                "reason": str(error)[:240],
                "retryable": True,
            })
            delay = 0.8
            marker = "retry_after_seconds="
            if marker in message:
                raw_delay = message.split(marker, 1)[1].split()[0].strip(";,)")
                try:
                    delay = min(15.0, max(0.8, float(raw_delay)))
                except (TypeError, ValueError):
                    delay = 0.8
            await asyncio.sleep(delay)
    assert last_error is not None
    raise last_error


async def run_live_benchmark(
    output_dir: Path,
    *,
    mission_paths: list[Path] | None = None,
    timeout: float = 180.0,
    probe_timeout: float = 20.0,
    client_factory: Any = httpx.AsyncClient,
    prompt_variant: str = "baseline",
) -> tuple[Path, dict[str, Any], int]:
    """Run real provider calls and persist prose separately from compact metrics."""
    prompt_variant = _resolve_live_prompt_variant(prompt_variant)
    _load_local_env()
    generation_started_at = datetime.now(timezone.utc).isoformat()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = output_dir / f"provider-live-{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=False)
    status_path = run_dir / "live-status.json"
    try:
        config = resolve_live_provider_config()
    except LiveProviderBlocked as exc:
        blocked = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generation_started_at": generation_started_at,
            "run_dir": str(run_dir),
            "record_count": 0,
            "records": [],
            "aggregate": {"average_score": 0, "average_word_count": 0, "blocker_counts": {}},
            "status": "blocked",
            "reason": str(exc),
            "generated_record_count": 0,
        }
        _write_summary(run_dir, blocked)
        status_path.write_text(json.dumps(blocked, ensure_ascii=False, indent=2), encoding="utf-8")
        return run_dir, blocked, 2

    probe = await probe_live_provider(config, timeout=probe_timeout, client_factory=client_factory)
    safe_provider = {key: config[key] for key in ("provider_host", "model", "credential_env")}
    if not probe.get("ready"):
        blocked = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generation_started_at": generation_started_at,
            "run_dir": str(run_dir),
            "record_count": 0,
            "records": [],
            "aggregate": {"average_score": 0, "average_word_count": 0, "blocker_counts": {}},
            "status": "blocked",
            "provider": safe_provider,
            "probe": probe,
            "generated_record_count": 0,
        }
        _write_summary(run_dir, blocked)
        status_path.write_text(json.dumps(blocked, ensure_ascii=False, indent=2), encoding="utf-8")
        return run_dir, blocked, 2

    missions = mission_paths or _smoke_missions()
    if not missions:
        raise RuntimeError("live benchmark requires at least one fixed mission file")
    records: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    async with client_factory(timeout=timeout) as client:
        for mission_path in missions:
            mission = json.loads(mission_path.read_text(encoding="utf-8"))
            mission_id = str(mission["id"])
            try:
                content, call_meta = await _generate_live_content(
                    client, config, mission, timeout=timeout, prompt_variant=prompt_variant,
                )
                content_file = f"{mission_id}.txt"
                (run_dir / content_file).write_text(content, encoding="utf-8")
                (run_dir / f"{mission_id}.json").write_text(
                    json.dumps({
                        "mission_id": mission_id,
                        "content_file": content_file,
                        "chapter_mission": mission.get("chapter_mission") or {},
                        "target_word_count": mission.get("target_word_count") or 0,
                        "min_word_count": mission.get("min_word_count") or 0,
                        "source": "provider_live_direct_completion",
                        "provider_host": config["provider_host"],
                        "model": config["model"],
                        "request_contract": _live_request_contract(mission, prompt_variant=prompt_variant),
                        "call": call_meta,
                    }, ensure_ascii=False, indent=2), encoding="utf-8",
                )
                records.append({"mission_id": mission_id, **call_meta})
            except Exception as exc:  # keep an explicit failure record; never synthesize metrics
                failures.append({
                    "mission_id": mission_id,
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:240],
                })

    if records:
        summary = rescore_run(run_dir)
    else:
        summary = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "run_dir": str(run_dir),
            "record_count": 0,
            "records": [],
            "aggregate": {"average_score": 0, "average_word_count": 0, "blocker_counts": {}},
        }
    summary.update({
        "status": "passed" if not failures else "failed",
        "provider": safe_provider,
        "probe": probe,
        "live_calls": records,
        "live_failures": failures,
        "generation_started_at": generation_started_at,
    })
    _write_summary(run_dir, summary)
    status_path.write_text(json.dumps({
        "status": summary["status"],
        "provider": safe_provider,
        "probe": probe,
        "generation_started_at": generation_started_at,
        "generated_record_count": len(records),
        "failure_count": len(failures),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return run_dir, summary, 0 if not failures else 1


def _load_records(run_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    records: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(run_dir.glob("*.json")):
        if path.name.startswith("rescore-") or path.name == "rescore-summary.json":
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            continue
        if isinstance(payload, dict) and payload.get("content_file"):
            records.append((path, payload))
    return records


def _score_story_quality(*, content: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Load the production scorer only when a run actually needs rescoring."""
    from app.services.pipeline_orchestrator import PipelineOrchestrator

    return PipelineOrchestrator._score_story_quality_candidate(
        content=content,
        violations=[],
        chapter_mission=payload.get("chapter_mission") if isinstance(payload.get("chapter_mission"), dict) else None,
        target_word_count=int(payload.get("target_word_count") or 0),
        min_word_count=int(payload.get("min_word_count") or 0),
    )


def _sha256_canonical(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _comparison_fingerprint(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    """Hash the non-prose benchmark contract needed for a valid before/after diff."""
    contracts = []
    request_contracts = []
    for payload in payloads:
        request_contract = payload.get("request_contract") if isinstance(payload.get("request_contract"), dict) else None
        contracts.append({
            "mission_id": str(payload.get("mission_id") or "unknown"),
            "target_word_count": int(payload.get("target_word_count") or 0),
            "min_word_count": int(payload.get("min_word_count") or 0),
            "chapter_mission": payload.get("chapter_mission") if isinstance(payload.get("chapter_mission"), dict) else {},
            "source": str(payload.get("source") or "unknown"),
            "provider_host": str(payload.get("provider_host") or ""),
            "model": str(payload.get("model") or ""),
            "request_contract": request_contract,
        })
        request_contracts.append(request_contract)
    contracts.sort(key=lambda item: item["mission_id"])
    scorer_path = ROOT / "app" / "services" / "pipeline_orchestrator.py"
    scorer_sha256 = hashlib.sha256(scorer_path.read_bytes()).hexdigest()
    mission_contract_sha256 = _sha256_canonical([{key: value for key, value in item.items() if key != "request_contract"} for item in contracts])
    if all(item.get("request_contract") is not None for item in contracts):
        generation_request_contract_sha256 = _sha256_canonical([
            {"mission_id": item["mission_id"], "request_contract": item["request_contract"]}
            for item in contracts
        ])
    else:
        generation_request_contract_sha256 = None
    comparison_contract_sha256 = _sha256_canonical({
        "mission_contract_sha256": mission_contract_sha256,
        "generation_request_contract_sha256": generation_request_contract_sha256,
        "scorer_sha256": scorer_sha256,
    })
    return {
        "schema_version": 2,
        "record_count": len(contracts),
        "mission_ids": [item["mission_id"] for item in contracts],
        "mission_contract_sha256": mission_contract_sha256,
        "generation_request_contract_sha256": generation_request_contract_sha256,
        "scorer_sha256": scorer_sha256,
        "comparison_contract_sha256": comparison_contract_sha256,
    }


def _compact_record(payload: dict[str, Any], metrics: dict[str, Any]) -> dict[str, Any]:
    record = {
        "mission_id": str(payload.get("mission_id") or "unknown"),
        "target_word_count": int(payload.get("target_word_count") or 0),
        "min_word_count": int(payload.get("min_word_count") or 0),
    }
    for field in METRIC_FIELDS:
        record[field] = metrics.get(field)
    record["quality_issue_codes"] = list(record.get("quality_issue_codes") or [])
    return record


def rescore_run(run_dir: Path, *, compare_to: Path | None = None) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    # `--rescore-only` 可能用于 live 目录；保留其 provider/probe/failure 元数据，
    # 否则一次离线重算会把真实上游失败证据静默擦除。
    existing_summary: dict[str, Any] = {}
    existing_path = run_dir / "rescore-summary.json"
    if existing_path.is_file():
        try:
            loaded = json.loads(existing_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing_summary = loaded
        except (OSError, ValueError, TypeError):
            pass
    records: list[dict[str, Any]] = []
    payloads: list[dict[str, Any]] = []
    for record_path, payload in _load_records(run_dir):
        content_path = (record_path.parent / str(payload["content_file"])).resolve()
        if not content_path.is_file():
            raise FileNotFoundError(f"missing content file for {record_path.name}: {content_path}")
        content = content_path.read_text(encoding="utf-8")
        metrics = _score_story_quality(content=content, payload=payload)
        payloads.append(payload)
        records.append(_compact_record(payload, metrics))
    summary: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_dir": str(run_dir),
        "record_count": len(records),
        "records": records,
        "comparison_fingerprint": _comparison_fingerprint(payloads),
        "aggregate": _quality_aggregate(records),
    }
    for key in ("status", "provider", "probe", "live_calls", "live_failures", "generation_started_at"):
        if key in existing_summary:
            summary[key] = existing_summary[key]
    if compare_to is not None:
        summary["comparison"] = _compare_summaries(summary, _load_summary(compare_to))
    _write_summary(run_dir, summary)
    return summary


def _pass_rate(records: list[dict[str, Any]], field: str) -> dict[str, Any]:
    evaluated = [record for record in records if record.get(field) is not None]
    passed = sum(record.get(field) is True for record in evaluated)
    return {
        "evaluated": len(evaluated),
        "passed": passed,
        "rate": round(passed / len(evaluated), 4) if evaluated else None,
    }


def _quality_aggregate(records: list[dict[str, Any]]) -> dict[str, Any]:
    word_eligible = [record for record in records if int(record.get("min_word_count") or 0) > 0]
    word_met = sum(int(record.get("word_count") or 0) >= int(record.get("min_word_count") or 0) for record in word_eligible)
    issue_records = sum(bool(record.get("quality_issue_codes")) for record in records)
    return {
        "average_score": round(sum(int(item.get("score") or 0) for item in records) / len(records), 2) if records else 0,
        "average_word_count": round(sum(int(item.get("word_count") or 0) for item in records) / len(records), 2) if records else 0,
        "minimum_word_count": {
            "eligible": len(word_eligible),
            "met": word_met,
            "rate": round(word_met / len(word_eligible), 4) if word_eligible else None,
        },
        "ending_pressure": _pass_rate(records, "ending_pressure_passed"),
        "event_density": _pass_rate(records, "event_density_passed"),
        "long_chapter_density": _pass_rate(records, "long_chapter_density_passed"),
        "state_change_interval": _pass_rate(records, "state_change_interval_passed"),
        "quality_issue_record_count": issue_records,
        "blocker_counts": _count_issue_codes(records),
    }


def _count_issue_codes(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        for code in record.get("quality_issue_codes") or []:
            counts[str(code)] = counts.get(str(code), 0) + 1
    return dict(sorted(counts.items()))


def _load_summary(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _aggregate_metric_deltas(current: dict[str, Any], previous: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Compare auditable pass-rate aggregates without comparing prose or inventing missing data."""
    deltas: dict[str, dict[str, Any]] = {}
    for name in ("minimum_word_count", "ending_pressure", "event_density", "long_chapter_density", "state_change_interval"):
        current_metric = current.get(name) if isinstance(current.get(name), dict) else {}
        previous_metric = previous.get(name) if isinstance(previous.get(name), dict) else {}
        if not current_metric and not previous_metric:
            continue
        item: dict[str, Any] = {}
        for key in ("eligible", "evaluated", "met", "passed"):
            if key in current_metric or key in previous_metric:
                current_value = current_metric.get(key)
                previous_value = previous_metric.get(key)
                item[f"{key}_delta"] = (
                    int(current_value or 0) - int(previous_value or 0)
                    if current_value is not None or previous_value is not None
                    else None
                )
        if "rate" in current_metric or "rate" in previous_metric:
            current_rate = current_metric.get("rate")
            previous_rate = previous_metric.get("rate")
            item["rate_delta"] = (
                round(float(current_rate or 0) - float(previous_rate or 0), 4)
                if current_rate is not None or previous_rate is not None
                else None
            )
        deltas[name] = item
    return deltas


def _compare_summaries(current: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    current_fingerprint = current.get("comparison_fingerprint") if isinstance(current.get("comparison_fingerprint"), dict) else {}
    previous_fingerprint = previous.get("comparison_fingerprint") if isinstance(previous.get("comparison_fingerprint"), dict) else {}
    required = ("schema_version", "mission_contract_sha256", "generation_request_contract_sha256", "scorer_sha256", "comparison_contract_sha256")
    if not all(current_fingerprint.get(key) for key in required) or not all(previous_fingerprint.get(key) for key in required):
        return {"comparable": False, "reason": "missing_comparison_fingerprint"}
    mismatched = [
        key for key in ("mission_contract_sha256", "generation_request_contract_sha256", "scorer_sha256", "comparison_contract_sha256")
        if current_fingerprint.get(key) != previous_fingerprint.get(key)
    ]
    if mismatched:
        return {"comparable": False, "reason": "comparison_contract_mismatch", "mismatched_fields": mismatched}
    previous_aggregate = previous.get("aggregate") if isinstance(previous.get("aggregate"), dict) else {}
    current_aggregate = current["aggregate"]
    return {
        "comparable": True,
        "average_score_delta": round(float(current_aggregate.get("average_score") or 0) - float(previous_aggregate.get("average_score") or 0), 2),
        "average_word_count_delta": round(float(current_aggregate.get("average_word_count") or 0) - float(previous_aggregate.get("average_word_count") or 0), 2),
        "aggregate_metric_deltas": _aggregate_metric_deltas(current_aggregate, previous_aggregate),
    }


def _write_summary(run_dir: Path, summary: dict[str, Any]) -> None:
    json_path = run_dir / "rescore-summary.json"
    csv_path = run_dir / "rescore-summary.csv"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    fields = ["mission_id", "target_word_count", "min_word_count", *METRIC_FIELDS]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in summary["records"]:
            row = dict(record)
            row["quality_issue_codes"] = ",".join(row.get("quality_issue_codes") or [])
            writer.writerow(row)


def create_fixture_smoke_run(output_dir: Path) -> Path:
    """Create a deterministic, non-provider smoke run from fixed public fixtures."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = output_dir / f"fixture-smoke-{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=False)
    missions = _smoke_missions()
    if len(missions) != 3:
        raise RuntimeError("fixture smoke requires exactly three fixed mission files")
    for mission_path in missions:
        mission = json.loads(mission_path.read_text(encoding="utf-8"))
        mission_id = str(mission["id"])
        content = str(mission.pop("fixture_content"))
        content_file = f"{mission_id}.txt"
        (run_dir / content_file).write_text(content, encoding="utf-8")
        (run_dir / f"{mission_id}.json").write_text(json.dumps({
            "mission_id": mission_id,
            "content_file": content_file,
            "chapter_mission": mission.get("chapter_mission") or {},
            "target_word_count": mission.get("target_word_count") or 0,
            "min_word_count": mission.get("min_word_count") or 0,
            "source": "fixed_fixture_smoke",
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    return run_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run redacted novel-quality benchmark modes.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--rescore-only", type=Path, help="existing run directory containing record JSON and separate text files")
    mode.add_argument("--smoke", action="store_true", help="run the deterministic fixed-fixture pipeline smoke")
    mode.add_argument("--live", action="store_true", help="call the configured provider for fixed missions; stores prose separately")
    mode.add_argument("--provider-probe", action="store_true", help="probe configured provider /models only; never generates prose")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "runs", help="where smoke/live artifacts are written")
    parser.add_argument("--compare", type=Path, help="prior rescore-summary.json to diff against")
    parser.add_argument("--timeout", type=float, default=180.0, help="per live completion timeout in seconds")
    parser.add_argument("--probe-timeout", type=float, default=20.0, help="provider /models probe timeout in seconds")
    parser.add_argument("--all-missions", action="store_true", help="live mode: run every fixed mission instead of the cost-capped first three")
    parser.add_argument(
        "--prompt-variant",
        choices=tuple(sorted(LIVE_PROMPT_VARIANTS)),
        default="baseline",
        help="live mode only: explicit non-production benchmark prompt variant (default: baseline)",
    )
    args = parser.parse_args(argv)
    if args.prompt_variant != "baseline" and not args.live:
        parser.error("--prompt-variant other than baseline is only allowed with --live")
    if args.smoke:
        run_dir = create_fixture_smoke_run(args.output_dir)
        summary = rescore_run(run_dir, compare_to=args.compare)
    elif args.rescore_only is not None:
        run_dir = args.rescore_only
        summary = rescore_run(run_dir, compare_to=args.compare)
    elif args.provider_probe:
        _load_local_env()
        try:
            config = resolve_live_provider_config()
        except LiveProviderBlocked as exc:
            print(json.dumps({"status": "blocked", "reason": str(exc)}, ensure_ascii=False))
            return 2
        probe = asyncio.run(probe_live_provider(config, timeout=args.probe_timeout))
        print(json.dumps({
            "status": "ready" if probe.get("ready") else "blocked",
            "provider_host": config["provider_host"],
            "model": config["model"],
            "credential_env": config["credential_env"],
            "probe": probe,
        }, ensure_ascii=False))
        return 0 if probe.get("ready") else 2
    elif args.live:
        missions = sorted(MISSIONS_DIR.glob("*.json")) if args.all_missions else _smoke_missions()
        run_dir, summary, exit_code = asyncio.run(
            run_live_benchmark(
                args.output_dir,
                mission_paths=missions,
                timeout=args.timeout,
                probe_timeout=args.probe_timeout,
                prompt_variant=args.prompt_variant,
            )
        )
        if args.compare and (run_dir / "rescore-summary.json").is_file():
            summary["comparison"] = _compare_summaries(summary, _load_summary(args.compare))
            _write_summary(run_dir, summary)
        print(json.dumps({
            "status": summary.get("status"),
            "record_count": summary.get("record_count", 0),
            "failure_count": len(summary.get("live_failures") or []),
            "summary_file": str(run_dir / "rescore-summary.json"),
            "status_file": str(run_dir / "live-status.json"),
        }, ensure_ascii=False))
        return exit_code
    else:  # pragma: no cover - argparse enforces exactly one mode
        parser.error("supply a benchmark mode")
    print(json.dumps({
        "record_count": summary["record_count"],
        "average_score": summary["aggregate"]["average_score"],
        "average_word_count": summary["aggregate"]["average_word_count"],
        "summary_file": str(run_dir / "rescore-summary.json"),
    }, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
