from __future__ import annotations

from app.core.config import Settings


def test_agent_tool_provider_settings_have_safe_defaults():
    settings = Settings(_env_file=None, secret_key="x" * 32)
    assert settings.agent_tool_providers_enabled is False
    assert settings.agent_tool_providers == []
    assert settings.agent_tool_provider_max_count == 16
    assert settings.agent_tool_provider_startup_policy == "fail_closed"


def test_agent_tool_provider_settings_parse_json_ids(monkeypatch):
    monkeypatch.setenv("AGENT_TOOL_PROVIDERS", '["project-read"]')
    settings = Settings(_env_file=None, secret_key="x" * 32)
    assert settings.agent_tool_providers == ["project-read"]


def test_production_provider_startup_policy_is_fail_closed():
    import pytest

    with pytest.raises(ValueError):
        Settings(
            _env_file=None,
            secret_key="x" * 32,
            environment="production",
            agent_tool_provider_startup_policy="skip_invalid",
        )


def test_provider_allowlist_requires_json_array_from_environment(monkeypatch):
    import pytest

    monkeypatch.setenv("AGENT_TOOL_PROVIDERS", "project-read")
    with pytest.raises(Exception):
        Settings(_env_file=None, secret_key="x" * 32)


def test_agent_runtime_tuning_settings_have_bounded_defaults():
    settings = Settings(_env_file=None, secret_key="x" * 32)
    assert settings.agent_visible_response_max_tokens == 1200
    assert settings.agent_run_lease_seconds == 120
    assert settings.agent_worker_lease_seconds == 120
    assert settings.agent_worker_poll_interval == 0.25
