from __future__ import annotations

import pytest

from app.agent.provider_runtime import ProviderConfigurationError, load_configured_tool_providers
from app.agent.registry import AgentToolRegistry, ToolProviderLoadError
from app.agent.schemas import AgentRiskLevel, ToolManifest


def _manifest(name: str) -> ToolManifest:
    return ToolManifest(
        name=name,
        description="Provider runtime test tool",
        risk_level=AgentRiskLevel.READ,
        requires_confirmation=False,
        project_scoped=False,
        input_schema={"type": "object", "additionalProperties": False},
        output_schema={"type": "object"},
    )


def test_configured_provider_is_not_imported_when_disabled(monkeypatch):
    registry = AgentToolRegistry()

    def unexpected(*args, **kwargs):
        raise AssertionError("disabled Provider must not be imported")

    monkeypatch.setattr("app.agent.provider_runtime.load_tool_provider", unexpected)
    health = load_configured_tool_providers(
        registry,
        enabled=False,
        provider_ids=["safe"],
        catalog={"safe": "app.agent.providers.safe:register_agent_tools"},
    )
    assert [item.status for item in health] == ["disabled"]
    assert registry.list_tools() == []


def test_configured_provider_batch_is_atomic_when_fail_closed(monkeypatch):
    registry = AgentToolRegistry()
    registry.register(_manifest("core.read"))

    def fake_load(target, path):
        if path.endswith("bad:register_agent_tools"):
            target.register(_manifest("extension.partial"))
            raise ToolProviderLoadError("bad provider")
        target.register(_manifest("extension.safe"))
        return ("extension.safe",)

    monkeypatch.setattr("app.agent.provider_runtime.load_tool_provider", fake_load)
    with pytest.raises(ProviderConfigurationError):
        load_configured_tool_providers(
            registry,
            enabled=True,
            provider_ids=["safe", "bad"],
            catalog={
                "safe": "app.agent.providers.safe:register_agent_tools",
                "bad": "app.agent.providers.bad:register_agent_tools",
            },
        )
    assert [tool.name for tool in registry.list_tools()] == ["core.read"]


def test_configured_provider_adds_only_new_tools_to_existing_registry(monkeypatch):
    registry = AgentToolRegistry()
    registry.register(_manifest("core.read"))

    def fake_load(target, path):
        target.register(_manifest("extension.safe"))
        return ("extension.safe",)

    monkeypatch.setattr("app.agent.provider_runtime.load_tool_provider", fake_load)
    health = load_configured_tool_providers(
        registry,
        enabled=True,
        provider_ids=["safe"],
        catalog={"safe": "app.agent.providers.safe:register_agent_tools"},
    )

    assert [item.status for item in health] == ["loaded"]
    assert health[0].tools == ("extension.safe",)
    assert [tool.name for tool in registry.list_tools()] == ["core.read", "extension.safe"]


def test_configured_provider_skip_invalid_commits_only_valid_providers(monkeypatch):
    registry = AgentToolRegistry()
    registry.register(_manifest("core.read"))

    def fake_load(target, path):
        if path.endswith("bad:register_agent_tools"):
            raise ToolProviderLoadError("bad provider")
        target.register(_manifest("extension.safe"))
        return ("extension.safe",)

    monkeypatch.setattr("app.agent.provider_runtime.load_tool_provider", fake_load)
    health = load_configured_tool_providers(
        registry,
        enabled=True,
        provider_ids=["safe", "bad"],
        startup_policy="skip_invalid",
        catalog={
            "safe": "app.agent.providers.safe:register_agent_tools",
            "bad": "app.agent.providers.bad:register_agent_tools",
        },
    )
    assert [item.status for item in health] == ["loaded", "failed"]
    assert [tool.name for tool in registry.list_tools()] == ["core.read", "extension.safe"]


def test_configured_provider_rejects_unknown_or_duplicate_ids():
    registry = AgentToolRegistry()
    with pytest.raises(ProviderConfigurationError):
        load_configured_tool_providers(registry, enabled=True, provider_ids=["unknown"], catalog={})
    with pytest.raises(ProviderConfigurationError):
        load_configured_tool_providers(
            registry,
            enabled=True,
            provider_ids=["safe", "safe"],
            catalog={"safe": "app.agent.providers.safe:register_agent_tools"},
        )


def test_builtin_provider_id_is_not_loaded_twice(monkeypatch):
    registry = AgentToolRegistry()

    def unexpected(*args, **kwargs):
        raise AssertionError("builtin Provider must not be dynamically loaded twice")

    monkeypatch.setattr("app.agent.provider_runtime.load_tool_provider", unexpected)
    health = load_configured_tool_providers(registry, enabled=True, provider_ids=["project-read"])
    assert [item.status for item in health] == ["skipped"]
    assert registry.list_tools() == []


def test_configured_provider_duplicate_tool_keeps_registry_unchanged(monkeypatch):
    registry = AgentToolRegistry()
    registry.register(_manifest("core.read"))

    def fake_load(target, path):
        target.register(_manifest("extension.partial"))
        target._tools["core.read"] = _manifest("core.read")
        return ("extension.partial", "core.read")

    monkeypatch.setattr("app.agent.provider_runtime.load_tool_provider", fake_load)
    with pytest.raises(ProviderConfigurationError):
        load_configured_tool_providers(
            registry,
            enabled=True,
            provider_ids=["duplicate"],
            catalog={"duplicate": "app.agent.providers.duplicate:register_agent_tools"},
        )
    assert [tool.name for tool in registry.list_tools()] == ["core.read"]


def test_disabled_provider_still_requires_reviewed_id():
    with pytest.raises(ProviderConfigurationError):
        load_configured_tool_providers(AgentToolRegistry(), enabled=False, provider_ids=["unknown"], catalog={})
