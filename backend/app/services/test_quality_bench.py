from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest


def test_rescore_only_writes_metrics_without_embedding_prose(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    prose = "顾沉推开门，发现桌上的钥匙不见了，于是决定追到走廊尽头。" * 60
    (run_dir / "m-01.txt").write_text(prose, encoding="utf-8")
    (run_dir / "m-01.json").write_text(json.dumps({
        "mission_id": "m-01",
        "content_file": "m-01.txt",
        "chapter_mission": {"scene_list": [{"goal": "找到钥匙", "conflict": "有人阻拦", "turn": "线索反转", "end_hook": "门外脚步"}]},
        "target_word_count": 2500,
        "min_word_count": 2200,
    }, ensure_ascii=False), encoding="utf-8")

    script = Path(__file__).resolve().parents[2] / "scripts" / "quality_bench.py"
    result = subprocess.run(
        [sys.executable, str(script), "--rescore-only", str(run_dir)],
        check=True, capture_output=True, text=True, encoding="utf-8",
    )

    summary_path = run_dir / "rescore-summary.json"
    csv_path = run_dir / "rescore-summary.csv"
    assert summary_path.exists()
    assert csv_path.exists()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["record_count"] == 1
    assert "content" not in summary["records"][0]
    fingerprint = summary["comparison_fingerprint"]
    assert fingerprint["record_count"] == 1
    assert fingerprint["mission_ids"] == ["m-01"]
    assert len(fingerprint["comparison_contract_sha256"]) == 64
    assert summary["records"][0]["mission_id"] == "m-01"
    with csv_path.open(encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["mission_id"] == "m-01"
    assert prose not in result.stdout


def test_smoke_writes_three_redacted_fixture_records(tmp_path):
    script = Path(__file__).resolve().parents[2] / "scripts" / "quality_bench.py"
    output_dir = tmp_path / "runs"
    subprocess.run(
        [sys.executable, str(script), "--smoke", "--output-dir", str(output_dir)],
        check=True, capture_output=True, text=True, encoding="utf-8",
    )
    run_dirs = [path for path in output_dir.iterdir() if path.is_dir()]
    assert len(run_dirs) == 1
    summary = json.loads((run_dirs[0] / "rescore-summary.json").read_text(encoding="utf-8"))
    assert summary["record_count"] == 3
    assert all("content" not in item for item in summary["records"])



def _load_quality_bench_module():
    import importlib.util

    script = Path(__file__).resolve().parents[2] / "scripts" / "quality_bench.py"
    spec = importlib.util.spec_from_file_location("quality_bench_live_test", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeProviderResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload, ensure_ascii=False)

    def json(self):
        return self._payload


class _FakeProviderClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def get(self, url, headers):
        assert url.endswith("/models")
        assert "Bearer secret-for-test" in headers["Authorization"]
        return _FakeProviderResponse(200, {"data": [{"id": "test-model"}]})

    async def post(self, url, headers, json, timeout):
        assert url.endswith("/chat/completions")
        assert json["model"] == "test-model"
        return _FakeProviderResponse(200, {
            "choices": [{"message": {"content": "顾沉推开门，锁芯已经被人换过。"}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 17, "total_tokens": 28},
        })


def _fake_client_factory(**kwargs):
    return _FakeProviderClient()


class _FakeSSEResponse:
    status_code = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def aiter_lines(self):
        yield 'data: {"choices":[{"delta":{"content":"顾沉推开门，"}}]}'
        yield 'data: {"choices":[{"delta":{"content":"锁芯已经被人换过。"}}],"usage":{"prompt_tokens":11,"completion_tokens":17,"total_tokens":28}}'
        yield 'data: [DONE]'


class _FakeSSEProviderClient(_FakeProviderClient):
    def stream(self, method, url, headers, json, timeout):
        assert method == "POST"
        assert url.endswith("/chat/completions")
        assert json["stream"] is True
        assert json["model"] == "test-model"
        return _FakeSSEResponse()


class _FlakySSEProviderClient(_FakeSSEProviderClient):
    def __init__(self):
        self.calls = 0

    def stream(self, method, url, headers, json, timeout):
        self.calls += 1
        if self.calls == 1:
            class EmptyResponse(_FakeSSEResponse):
                async def aiter_lines(self):
                    yield "data: [DONE]"
            return EmptyResponse()
        return super().stream(method, url, headers, json, timeout)


class _TransportFlakySSEProviderClient(_FakeSSEProviderClient):
    def __init__(self):
        self.calls = 0

    def stream(self, method, url, headers, json, timeout):
        self.calls += 1
        if self.calls == 1:
            class BrokenResponse(_FakeSSEResponse):
                async def aiter_lines(self):
                    import httpx
                    raise httpx.RemoteProtocolError("incomplete chunked read")
                    yield ""
            return BrokenResponse()
        return super().stream(method, url, headers, json, timeout)


class _RateLimitedSSEProviderClient(_FakeSSEProviderClient):
    def __init__(self):
        self.calls = 0

    def stream(self, method, url, headers, json, timeout):
        self.calls += 1
        if self.calls == 1:
            class RateLimitedResponse(_FakeSSEResponse):
                status_code = 429
                headers = {"Retry-After": "0.8"}
            return RateLimitedResponse()
        return super().stream(method, url, headers, json, timeout)


def _fake_sse_client_factory(**kwargs):
    return _FakeSSEProviderClient()


def test_provider_probe_redacts_credential_and_reports_model_availability():
    import asyncio

    quality_bench = _load_quality_bench_module()
    config = {
        "api_key": "secret-for-test",
        "base_url": "https://provider.example/v1",
        "model": "test-model",
        "credential_env": "OPENAI_API_KEY",
        "provider_host": "provider.example",
    }
    probe = asyncio.run(quality_bench.probe_live_provider(
        config,
        client_factory=_fake_client_factory,
    ))
    assert probe == {
        "ready": True,
        "stage": "probe",
        "status_code": 200,
        "model_listed": True,
        "model_count": 1,
        "error": None,
        "duration_ms": probe["duration_ms"],
    }
    assert "secret-for-test" not in json.dumps(probe, ensure_ascii=False)


def test_live_runner_persists_redacted_provider_output(tmp_path, monkeypatch):
    import asyncio

    quality_bench = _load_quality_bench_module()
    mission = tmp_path / "mission.json"
    mission.write_text(json.dumps({
        "id": "live-mission",
        "target_word_count": 1200,
        "min_word_count": 900,
        "chapter_mission": {"scene_list": [{"goal": "开门", "conflict": "锁被换", "turn": "钥匙失效", "end_hook": "脚步靠近"}]},
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(quality_bench, "_load_local_env", lambda: None)
    monkeypatch.setattr(quality_bench, "resolve_live_provider_config", lambda: {
        "api_key": "secret-for-test",
        "base_url": "https://provider.example/v1",
        "model": "test-model",
        "credential_env": "OPENAI_API_KEY",
        "provider_host": "provider.example",
    })

    run_dir, summary, exit_code = asyncio.run(quality_bench.run_live_benchmark(
        tmp_path / "runs",
        mission_paths=[mission],
        client_factory=_fake_client_factory,
    ))

    assert exit_code == 0
    assert summary["status"] == "passed"
    assert summary["record_count"] == 1
    assert summary["generation_started_at"]
    status = json.loads((run_dir / "live-status.json").read_text(encoding="utf-8"))
    assert status["generation_started_at"] == summary["generation_started_at"]
    assert (run_dir / "live-mission.txt").exists()
    assert "顾沉推开门" not in (run_dir / "rescore-summary.json").read_text(encoding="utf-8")
    assert "顾沉推开门" not in (run_dir / "rescore-summary.csv").read_text(encoding="utf-8")
    record = json.loads((run_dir / "live-mission.json").read_text(encoding="utf-8"))
    assert record["source"] == "provider_live_direct_completion"
    assert record["call"]["total_tokens"] == 28
    assert record["request_contract"]["temperature"] == 0.8
    assert record["request_contract"]["prompt_variant"] == "baseline"
    mission_payload = json.loads(mission.read_text(encoding="utf-8"))
    assert record["request_contract"]["prompt_sha256"] == quality_bench._sha256_canonical(
        quality_bench._live_request_messages(mission_payload)
    )
    assert record["request_contract"]["max_tokens"] == 2400
    assert record["request_contract"]["response_transport"] == "sse_preferred_with_nonstream_compat_fallback"
    assert record["request_contract"]["retry_policy"]["max_attempts"] == 2
    assert "http_429" in record["request_contract"]["retry_policy"]["retry_on"]
    assert "network_transport" in record["request_contract"]["retry_policy"]["retry_on"]
    assert record["call"]["response_transport"] == "nonstream_compat"
    assert record["call"]["attempts"] == 1


def test_missing_provider_configuration_blocks_without_generating():
    quality_bench = _load_quality_bench_module()
    try:
        quality_bench.resolve_live_provider_config({})
    except quality_bench.LiveProviderBlocked as exc:
        assert "未找到完整 live provider 配置" in str(exc)
    else:
        raise AssertionError("expected missing provider configuration to block")



class _RateLimitedProviderClient(_FakeProviderClient):
    async def post(self, url, headers, json, timeout):
        return _FakeProviderResponse(429, {"error": {"message": "Rate limit exceeded. Please try again later."}})


def _rate_limited_client_factory(**kwargs):
    return _RateLimitedProviderClient()


def test_rate_limit_writes_blocking_summary_without_metrics(tmp_path, monkeypatch):
    import asyncio

    quality_bench = _load_quality_bench_module()
    mission = tmp_path / "mission.json"
    mission.write_text(json.dumps({"id": "limited", "chapter_mission": {}}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(quality_bench, "_load_local_env", lambda: None)
    monkeypatch.setattr(quality_bench, "resolve_live_provider_config", lambda: {
        "api_key": "secret-for-test", "base_url": "https://provider.example/v1",
        "model": "test-model", "credential_env": "OPENAI_API_KEY", "provider_host": "provider.example",
    })
    run_dir, summary, exit_code = asyncio.run(quality_bench.run_live_benchmark(
        tmp_path / "runs", mission_paths=[mission], client_factory=_rate_limited_client_factory,
    ))
    assert exit_code == 1
    assert summary["record_count"] == 0
    assert summary["live_failures"][0]["error_type"] == "LiveProviderBlocked"
    assert "429" in summary["live_failures"][0]["error"]
    assert (run_dir / "rescore-summary.json").exists()
    assert (run_dir / "live-status.json").exists()
    assert not list(run_dir.glob("*.txt"))
    assert "secret-for-test" not in (run_dir / "rescore-summary.json").read_text(encoding="utf-8")

def test_quality_bench_keeps_three_smoke_missions_and_exposes_ten_fixed_missions():
    quality_bench = _load_quality_bench_module()
    smoke = quality_bench._smoke_missions()
    all_missions = sorted(quality_bench.MISSIONS_DIR.glob("*.json"))
    assert [path.name for path in smoke] == [
        "smoke-dialogue.json", "smoke-opening.json", "smoke-pressure.json",
    ]
    assert len(all_missions) == 10
    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in all_missions]
    assert {item["target_word_count"] for item in payloads} >= {1200, 1500, 3000, 6000}

def test_quality_bench_refuses_to_compare_mismatched_or_legacy_contracts():
    quality_bench = _load_quality_bench_module()
    current = {
        "aggregate": {"average_score": 10, "average_word_count": 20},
        "comparison_fingerprint": {
            "schema_version": 2, "mission_contract_sha256": "m1",
            "generation_request_contract_sha256": "r1",
            "scorer_sha256": "s1", "comparison_contract_sha256": "c1",
        },
    }
    assert quality_bench._compare_summaries(current, {"aggregate": {}}) == {
        "comparable": False, "reason": "missing_comparison_fingerprint",
    }
    mismatch = dict(current, comparison_fingerprint=dict(current["comparison_fingerprint"], scorer_sha256="other"))
    result = quality_bench._compare_summaries(current, mismatch)
    assert result["comparable"] is False
    assert result["reason"] == "comparison_contract_mismatch"
    assert "scorer_sha256" in result["mismatched_fields"]

def test_quality_bench_live_budget_can_meet_fixed_longform_contract():
    quality_bench = _load_quality_bench_module()
    assert quality_bench._live_completion_max_tokens({"target_word_count": 1200}) == 2400
    assert quality_bench._live_completion_max_tokens({"target_word_count": 6000}) == 12000
    assert quality_bench._live_completion_max_tokens({"target_word_count": 10000}) == 12000
    prompt = quality_bench._mission_prompt({
        "target_word_count": 6000,
        "min_word_count": 5400,
        "chapter_mission": {"scene_list": []},
    })
    assert "目标正文长度约 6000 个汉字" in prompt
    assert "最低不少于 5400 个汉字" in prompt
    assert "最后 10% 必须留下未解决的危险" in prompt
    assert "兑现任务书 turn 与 end_hook" in prompt
    assert "禁止用总结、感想、恢复平静" in prompt
    assert "写到至少 5400 个汉字之前，不得写最终收束" in prompt
    assert "收尾前逐项自检" in prompt

def test_quality_bench_compare_exposes_quality_metric_deltas():
    quality_bench = _load_quality_bench_module()
    fingerprint = {
        "schema_version": 2, "mission_contract_sha256": "m",
        "generation_request_contract_sha256": "r", "scorer_sha256": "s",
        "comparison_contract_sha256": "c",
    }
    current = {
        "aggregate": {
            "average_score": 12, "average_word_count": 1200,
            "minimum_word_count": {"eligible": 2, "met": 2, "rate": 1.0},
            "event_density": {"evaluated": 2, "passed": 2, "rate": 1.0},
            "long_chapter_density": {"evaluated": 2, "passed": 1, "rate": 0.5},
            "state_change_interval": {"evaluated": 2, "passed": 1, "rate": 0.5},
            "ending_pressure": {"evaluated": 2, "passed": 1, "rate": 0.5},
        },
        "comparison_fingerprint": fingerprint,
    }
    previous = {
        "aggregate": {
            "average_score": 10, "average_word_count": 1100,
            "minimum_word_count": {"eligible": 2, "met": 1, "rate": 0.5},
            "event_density": {"evaluated": 2, "passed": 1, "rate": 0.5},
            "long_chapter_density": {"evaluated": 2, "passed": 2, "rate": 1.0},
            "state_change_interval": {"evaluated": 1, "passed": 1, "rate": 1.0},
            "ending_pressure": {"evaluated": 2, "passed": 2, "rate": 1.0},
        },
        "comparison_fingerprint": fingerprint,
    }
    result = quality_bench._compare_summaries(current, previous)
    assert result["comparable"] is True
    assert result["average_score_delta"] == 2.0
    assert result["aggregate_metric_deltas"]["minimum_word_count"] == {
        "eligible_delta": 0, "met_delta": 1, "rate_delta": 0.5,
    }
    assert result["aggregate_metric_deltas"]["long_chapter_density"]["passed_delta"] == -1
    assert result["aggregate_metric_deltas"]["state_change_interval"]["evaluated_delta"] == 1
    assert result["aggregate_metric_deltas"]["ending_pressure"]["rate_delta"] == -0.5


def test_quality_bench_compare_metric_delta_contract_is_not_removed():
    import inspect
    quality_bench = _load_quality_bench_module()
    source = inspect.getsource(quality_bench._compare_summaries)
    metric_output_key = '"aggregate_metric_deltas":'
    assert metric_output_key in source
    sabotaged = source.replace(metric_output_key, '"removed_metric_deltas":', 1)
    with pytest.raises(AssertionError):
        assert metric_output_key in sabotaged


def test_quality_bench_refuses_generation_request_contract_mismatch():
    quality_bench = _load_quality_bench_module()
    base = {
        "aggregate": {"average_score": 1, "average_word_count": 2},
        "comparison_fingerprint": {
            "schema_version": 2, "mission_contract_sha256": "m",
            "generation_request_contract_sha256": "r1", "scorer_sha256": "s",
            "comparison_contract_sha256": "c1",
        },
    }
    other = {
        "aggregate": {"average_score": 3, "average_word_count": 4},
        "comparison_fingerprint": dict(base["comparison_fingerprint"], generation_request_contract_sha256="r2", comparison_contract_sha256="c2"),
    }
    result = quality_bench._compare_summaries(base, other)
    assert result["comparable"] is False
    assert "generation_request_contract_sha256" in result["mismatched_fields"]

def test_rescore_only_preserves_existing_live_metadata(tmp_path):
    quality_bench = _load_quality_bench_module()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "m.txt").write_text("顾沉推门，门后传来脚步声。" * 80, encoding="utf-8")
    (run_dir / "m.json").write_text(json.dumps({
        "mission_id": "m", "content_file": "m.txt", "chapter_mission": {},
        "target_word_count": 1200, "min_word_count": 900,
    }, ensure_ascii=False), encoding="utf-8")
    (run_dir / "rescore-summary.json").write_text(json.dumps({
        "status": "failed", "provider": {"model": "test-model"},
        "probe": {"ready": True}, "live_calls": [{"mission_id": "m"}],
        "live_failures": [{"mission_id": "other", "error": "empty"}],
    }, ensure_ascii=False), encoding="utf-8")
    summary = quality_bench.rescore_run(run_dir)
    assert summary["status"] == "failed"
    assert summary["provider"] == {"model": "test-model"}
    assert summary["live_failures"][0]["mission_id"] == "other"

def test_live_generation_collects_sse_chunks_and_records_transport():
    import asyncio

    quality_bench = _load_quality_bench_module()
    content, meta = asyncio.run(quality_bench._generate_live_content(
        _FakeSSEProviderClient(),
        {"api_key": "secret-for-test", "base_url": "https://provider.example/v1", "model": "test-model"},
        {"target_word_count": 1200, "min_word_count": 900, "chapter_mission": {}},
        timeout=10,
    ))
    assert content == "顾沉推开门，锁芯已经被人换过。"
    assert meta["response_transport"] == "sse"
    assert meta["total_tokens"] == 28

def test_live_generation_retries_empty_sse_once_and_records_attempts():
    import asyncio

    quality_bench = _load_quality_bench_module()
    client = _FlakySSEProviderClient()
    content, meta = asyncio.run(quality_bench._generate_live_content(
        client,
        {"api_key": "secret-for-test", "base_url": "https://provider.example/v1", "model": "test-model"},
        {"target_word_count": 1200, "min_word_count": 900, "chapter_mission": {}},
        timeout=10,
    ))
    assert content
    assert client.calls == 2
    assert meta["attempts"] == 2
    assert meta["retry_events"][0]["attempt"] == 1
    assert meta["retry_events"][0]["retryable"] is True
    assert "空正文" in meta["retry_events"][0]["reason"]

def test_live_generation_retries_http_429_once_and_records_attempts():
    import asyncio

    quality_bench = _load_quality_bench_module()
    client = _RateLimitedSSEProviderClient()
    content, meta = asyncio.run(quality_bench._generate_live_content(
        client,
        {"api_key": "secret-for-test", "base_url": "https://provider.example/v1", "model": "test-model"},
        {"target_word_count": 1200, "min_word_count": 900, "chapter_mission": {}},
        timeout=10,
    ))
    assert content
    assert client.calls == 2
    assert meta["attempts"] == 2
    assert meta["retry_events"][0]["attempt"] == 1
    assert meta["retry_events"][0]["retryable"] is True
    assert "429" in meta["retry_events"][0]["reason"]

def test_quality_bench_records_long_chapter_density_metric():
    quality_bench = _load_quality_bench_module()
    metrics = {"score": 10, "word_count": 7000, "long_chapter_density_passed": False}
    record = quality_bench._compact_record(
        {"mission_id": "long", "target_word_count": 7000, "min_word_count": 6300}, metrics
    )
    assert record["long_chapter_density_passed"] is False
    assert "long_chapter_density_passed" in quality_bench.METRIC_FIELDS

    source = Path(quality_bench.__file__).read_text(encoding="utf-8")
    metric_sequence = '    "long_chapter_density_passed", "state_change_interval_passed"'
    assert metric_sequence in source
    sabotaged = source.replace(metric_sequence, '    "removed_long_chapter_density_passed", "state_change_interval_passed"', 1)
    with pytest.raises(AssertionError):
        assert metric_sequence in sabotaged


def test_quality_bench_aggregate_exposes_auditable_quality_rates():
    quality_bench = _load_quality_bench_module()
    aggregate = quality_bench._quality_aggregate([
        {
            "score": 10, "word_count": 900, "min_word_count": 900,
            "ending_pressure_passed": True, "event_density_passed": False,
            "long_chapter_density_passed": False, "state_change_interval_passed": None,
            "quality_issue_codes": ["ending_pressure_missing"],
        },
        {
            "score": 30, "word_count": 800, "min_word_count": 900,
            "ending_pressure_passed": False, "event_density_passed": True,
            "state_change_interval_passed": True, "quality_issue_codes": [],
        },
    ])
    assert aggregate["minimum_word_count"] == {"eligible": 2, "met": 1, "rate": 0.5}
    assert aggregate["ending_pressure"] == {"evaluated": 2, "passed": 1, "rate": 0.5}
    assert aggregate["event_density"] == {"evaluated": 2, "passed": 1, "rate": 0.5}
    assert aggregate["long_chapter_density"] == {"evaluated": 1, "passed": 0, "rate": 0.0}
    assert aggregate["state_change_interval"] == {"evaluated": 1, "passed": 1, "rate": 1.0}
    assert aggregate["quality_issue_record_count"] == 1

def test_retry_after_is_capped_and_recorded_in_retry_contract():
    import asyncio

    quality_bench = _load_quality_bench_module()
    class LongRetryAfterClient(_RateLimitedSSEProviderClient):
        def stream(self, method, url, headers, json, timeout):
            self.calls += 1
            if self.calls == 1:
                class RateLimitedResponse(_FakeSSEResponse):
                    status_code = 429
                    headers = {"Retry-After": "999"}
                return RateLimitedResponse()
            return super(_RateLimitedSSEProviderClient, self).stream(method, url, headers, json, timeout)

    client = LongRetryAfterClient()
    async def no_sleep(_seconds):
        return None
    original_sleep = quality_bench.asyncio.sleep
    quality_bench.asyncio.sleep = no_sleep
    try:
        content, meta = asyncio.run(quality_bench._generate_live_content(
        client,
        {"api_key": "secret-for-test", "base_url": "https://provider.example/v1", "model": "test-model"},
        {"target_word_count": 1200, "min_word_count": 900, "chapter_mission": {}},
        timeout=10,
    ))
        assert content
        assert meta["attempts"] == 2
    finally:
        quality_bench.asyncio.sleep = original_sleep


def test_live_provider_config_uses_production_model_alias_resolution():
    quality_bench = _load_quality_bench_module()
    config = quality_bench.resolve_live_provider_config({
        "OPENAI_API_KEY": "secret-for-test",
        "OPENAI_API_BASE_URL": "https://api.xzxyuan.ccwu.cc/v1",
        "OPENAI_MODEL_NAME": "deepseek-v4-flash-free",
    })
    assert config["configured_model"] == "deepseek-v4-flash-free"
    assert config["model"] == "deepseek/deepseek-v4-flash-free"
    assert config["provider_host"] == "api.xzxyuan.ccwu.cc"


def test_live_provider_alias_resolution_makes_probe_use_actual_model_id():
    import asyncio
    quality_bench = _load_quality_bench_module()
    config = quality_bench.resolve_live_provider_config({
        "OPENAI_API_KEY": "secret-for-test",
        "OPENAI_API_BASE_URL": "https://api.xzxyuan.ccwu.cc/v1",
        "OPENAI_MODEL_NAME": "deepseek-v4-flash-free",
    })

    class _NamespacedModelClient(_FakeProviderClient):
        async def get(self, url, headers):
            return _FakeProviderResponse(200, {"data": [{"id": "deepseek/deepseek-v4-flash-free"}]})

    probe = asyncio.run(quality_bench.probe_live_provider(config, client_factory=lambda **_kwargs: _NamespacedModelClient()))
    assert probe["ready"] is True
    assert probe["model_listed"] is True

def test_quality_bench_fixed_missions_use_chinese_story_contract_fields():
    quality_bench = _load_quality_bench_module()
    required_scene_fields = ("goal", "conflict", "turn", "end_hook")
    for mission_path in sorted(quality_bench.MISSIONS_DIR.glob("*.json")):
        payload = json.loads(mission_path.read_text(encoding="utf-8"))
        mission = payload["chapter_mission"]
        values = [mission["chapter_purpose"]]
        values.extend(mission["scene_list"][0][field] for field in required_scene_fields)
        assert all(any("\u4e00" <= char <= "\u9fff" for char in value) for value in values), mission_path.name


def test_rescore_compact_record_includes_all_observable_quality_dimensions(tmp_path):
    quality_bench = _load_quality_bench_module()
    metrics = {
        "score": 10,
        "word_count": 1200,
        "reversal_signal_count": 2,
        "reversal_in_late_section": True,
        "dialogue_ratio": 0.3,
        "action_ratio": 0.4,
        "description_ratio": 0.3,
        "speaker_count": 2,
        "dominant_speaker_ratio": 0.6,
        "hard_scene_cut_count": 1,
        "summary_scene_cut_count": 1,
        "scene_transition_warning": True,
        "mission_quality_codes": ["mission_scene_too_few"],
        "quality_issue_codes": ["ending_pressure_missing"],
    }
    record = quality_bench._compact_record(
        {"mission_id": "dimensions", "target_word_count": 1500, "min_word_count": 1200},
        metrics,
    )
    for key, value in metrics.items():
        assert record[key] == value

def test_live_generation_retries_transport_interruption_once():
    import asyncio

    quality_bench = _load_quality_bench_module()
    client = _TransportFlakySSEProviderClient()
    async def no_sleep(_seconds):
        return None
    original_sleep = quality_bench.asyncio.sleep
    quality_bench.asyncio.sleep = no_sleep
    try:
        content, meta = asyncio.run(quality_bench._generate_live_content(
            client,
            {"api_key": "secret-for-test", "base_url": "https://provider.example/v1", "model": "test-model"},
            {"target_word_count": 1200, "min_word_count": 900, "chapter_mission": {}},
            timeout=10,
        ))
    finally:
        quality_bench.asyncio.sleep = original_sleep
    assert content
    assert client.calls == 2
    assert meta["attempts"] == 2
    assert meta["retry_events"][0]["attempt"] == 1
    assert meta["retry_events"][0]["retryable"] is True
    assert "transport" in meta["retry_events"][0]["reason"]

def test_comparison_fingerprint_is_invariant_to_payload_order():
    quality_bench = _load_quality_bench_module()
    def payload(mission_id):
        return {
            "mission_id": mission_id, "target_word_count": 1200, "min_word_count": 900,
            "chapter_mission": {"scene_list": []}, "source": "provider_live_direct_completion",
            "provider_host": "provider.example", "model": "test-model",
            "request_contract": {"prompt_contract_version": "v3", "temperature": 0.8, "max_tokens": 2400},
        }
    first = quality_bench._comparison_fingerprint([payload("b"), payload("a")])
    second = quality_bench._comparison_fingerprint([payload("a"), payload("b")])
    assert first["mission_contract_sha256"] == second["mission_contract_sha256"]
    assert first["generation_request_contract_sha256"] == second["generation_request_contract_sha256"]
    assert first["comparison_contract_sha256"] == second["comparison_contract_sha256"]


def test_nonproduction_prompt_variants_are_explicit_and_contract_bound():
    quality_bench = _load_quality_bench_module()
    mission = {"target_word_count": 1200, "min_word_count": 900, "chapter_mission": {"scene_list": []}}
    baseline_messages = quality_bench._live_request_messages(mission)
    candidate_messages = quality_bench._live_request_messages(mission, prompt_variant="candidate")
    baseline_contract = quality_bench._live_request_contract(mission)
    candidate_contract = quality_bench._live_request_contract(mission, prompt_variant="candidate")

    assert baseline_messages[0]["content"] == quality_bench.LIVE_SYSTEM_PROMPT
    assert baseline_messages[1]["content"] == quality_bench._mission_prompt(mission)
    assert candidate_messages != baseline_messages
    assert baseline_contract["prompt_variant"] == "baseline"
    assert candidate_contract["prompt_variant"] == "candidate"
    assert baseline_contract["prompt_sha256"] == quality_bench._sha256_canonical(baseline_messages)
    assert candidate_contract["prompt_sha256"] == quality_bench._sha256_canonical(candidate_messages)
    assert baseline_contract["prompt_sha256"] != candidate_contract["prompt_sha256"]
    assert candidate_contract["user_prompt_sha256"] == hashlib.sha256(
        candidate_messages[1]["content"].encode("utf-8")
    ).hexdigest()


def test_nonproduction_prompt_variant_rejects_unsafe_or_nonlive_selection(tmp_path):
    quality_bench = _load_quality_bench_module()
    with pytest.raises(ValueError, match="unsupported non-production prompt variant"):
        quality_bench._live_request_contract({}, prompt_variant="production")
    with pytest.raises(SystemExit):
        quality_bench.main(["--smoke", "--prompt-variant", "candidate", "--output-dir", str(tmp_path / "runs")])

