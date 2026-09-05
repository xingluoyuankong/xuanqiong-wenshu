"""Regression coverage for the standalone OpenAPI smoke authentication setup."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def _load_smoke_routes_module() -> ModuleType:
    path = Path(__file__).resolve().parents[3] / "tools" / "smoke_api_routes.py"
    spec = importlib.util.spec_from_file_location("xq_smoke_api_routes_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_openapi_smoke_anonymous_auth_has_defined_mode_and_clears_stale_headers(monkeypatch):
    monkeypatch.delenv("XUANQIONG_WENSHU_SMOKE_TOKEN", raising=False)
    monkeypatch.delenv("XUANQIONG_WENSHU_SMOKE_USERNAME", raising=False)
    monkeypatch.delenv("XUANQIONG_WENSHU_SMOKE_PASSWORD", raising=False)
    smoke = _load_smoke_routes_module()
    smoke.AUTH_HEADERS = {"Authorization": "Bearer stale-token"}
    smoke.AUTH_MODE = "bearer-token"

    ok, mode = smoke.configure_auth()

    assert ok is True
    assert mode == "anonymous"
    assert smoke.AUTH_MODE == "anonymous"
    assert smoke.AUTH_HEADERS == {}
