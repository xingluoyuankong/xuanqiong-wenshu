from __future__ import annotations

from app.agent.provider_catalog import BUILTIN_PROVIDER_IDS, PROVIDER_CATALOG, PROVIDER_MANIFESTS
from app.agent.registry import DEFAULT_TOOL_PROVIDER_HEALTH, DEFAULT_TOOL_REGISTRY, get_default_tool_registry_snapshot


def test_builtin_provider_catalog_matches_loaded_provider_health():
    expected = {
        "project-read": {"project.list", "project.context", "entity.inspect", "chapter.version.list", "outline.inspect", "research.inspect", "statistics.project"},
        "memory-read": {"knowledge.inspect"},
        "foreshadowing-read": {"foreshadowing.inspect"},
        "structure-read": {"chapter.inspect", "chapter.version.diff"},
    }
    assert BUILTIN_PROVIDER_IDS == set(expected)
    assert set(PROVIDER_CATALOG) == set(expected)
    assert set(PROVIDER_MANIFESTS) == set(expected)
    health = {item["provider_id"]: item for item in DEFAULT_TOOL_PROVIDER_HEALTH}
    assert set(health) == set(expected)
    for provider_id, tool_names in expected.items():
        assert health[provider_id]["status"] == "loaded"
        assert set(health[provider_id]["tools"]) == tool_names


def test_providerized_tools_are_unique_and_executable():
    provider_tools = [name for item in DEFAULT_TOOL_PROVIDER_HEALTH for name in item["tools"]]
    assert len(provider_tools) == len(set(provider_tools))
    assert all(callable(DEFAULT_TOOL_REGISTRY.get_handler(name)) for name in provider_tools)
    assert {tool.name for tool in DEFAULT_TOOL_REGISTRY.list_tools()} >= set(provider_tools)


def test_registry_snapshot_contains_all_providerized_tools_without_duplicates():
    snapshot = get_default_tool_registry_snapshot()
    names = [item["name"] for item in snapshot["tools"]]
    assert len(names) == len(set(names)) == 19
    provider_tools = {name for item in DEFAULT_TOOL_PROVIDER_HEALTH for name in item["tools"]}
    assert provider_tools.issubset(names)
    by_name = {item["name"]: item for item in snapshot["tools"]}
    assert by_name["project.context"] == {
        **by_name["project.context"],
        "provider_id": "project-read",
        "provider_version": "1.0.0",
        "source": "builtin",
    }
    assert by_name["knowledge.inspect"]["provider_id"] == "memory-read"
    assert by_name["foreshadowing.inspect"]["provider_id"] == "foreshadowing-read"
    assert by_name["chapter.inspect"]["provider_id"] == "structure-read"
    assert by_name["chapter.version.diff"]["provider_id"] == "structure-read"
    assert by_name["chapter.inspect"]["source"] == "builtin"
