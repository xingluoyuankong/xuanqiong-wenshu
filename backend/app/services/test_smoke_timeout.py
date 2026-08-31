from pathlib import Path

import pytest

from app.utils.smoke_timeout import resolve_smoke_poll_timeout_seconds


@pytest.mark.parametrize(
    ("payload", "requested", "fallback", "expected"),
    [
        ({"generation_runtime": {"timeout_seconds": 3300}}, 0, 900, 3300),
        ({"generation_runtime": {"timeout_seconds": 3300}}, 1800, 900, 1800),
        ({}, 0, 900, 900),
        ({}, 0, 0, 4 * 60 * 60),
    ],
)
def test_smoke_poll_timeout_mirrors_backend_budget(payload, requested, fallback, expected):
    assert resolve_smoke_poll_timeout_seconds(
        payload, requested_timeout_seconds=requested, fallback_timeout_seconds=fallback
    ) == expected


def test_smoke_poll_timeout_clamps_provider_or_environment_values():
    assert resolve_smoke_poll_timeout_seconds(
        {"generation_runtime": {"timeout_seconds": 999999}},
        requested_timeout_seconds=0,
        fallback_timeout_seconds=900,
    ) == 4 * 60 * 60


@pytest.mark.parametrize(
    "script_name",
    [
        "real_asgi_generation_smoke.py",
        "real_asgi_concurrent_generation_smoke.py",
        "real_asgi_multichapter_trend_smoke.py",
        "real_asgi_three_candidate_smoke.py",
    ],
)
def test_real_asgi_smokes_do_not_use_short_fixed_poll_deadlines(script_name):
    source = (Path(__file__).resolve().parents[2] / "scripts" / script_name).read_text(encoding="utf-8")
    assert "resolve_smoke_poll_timeout_seconds" in source
    assert "time.monotonic() + 360" not in source
    assert "time.monotonic() + 420" not in source
    assert "time.monotonic() + 480" not in source
