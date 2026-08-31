"""Canonical, reviewable contracts for the Agent tool catalog.

This module deliberately captures executable-tool semantics rather than raw
Provider module paths.  It is used to freeze a reviewed migration baseline and
to detect accidental manifest, handler, risk, or source drift as Providers are
introduced incrementally.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .schemas import ToolManifest

CATALOG_CONTRACT_SCHEMA_VERSION = 1
CATALOG_CONTRACT_ID = "agent-catalog-contract-v1"


def _provider_sources(provider_health: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, str | None]]:
    sources: dict[str, dict[str, str | None]] = {}
    for provider in provider_health:
        if provider.get("status") != "loaded":
            continue
        source = str(provider.get("source") or "").strip()
        provider_id = str(provider.get("provider_id") or "").strip()
        if source not in {"builtin", "configured"} or not provider_id:
            continue
        provider_version = str(provider.get("provider_version") or "").strip() or None
        for raw_name in provider.get("tools", []):
            name = str(raw_name or "").strip()
            if name:
                sources[name] = {
                    "source": source,
                    "provider_id": provider_id,
                    "provider_version": provider_version,
                }
    return sources


def _handler_identity(handler: Any) -> str | None:
    if handler is None:
        return None
    module = str(getattr(handler, "__module__", "") or "").strip()
    qualname = str(getattr(handler, "__qualname__", "") or "").strip()
    return f"{module}:{qualname}" if module and qualname else None


def canonical_tool_contract(
    tool: ToolManifest,
    handler: Any,
    *,
    source_metadata: Mapping[str, str | None] | None = None,
) -> dict[str, Any]:
    """Return JSON-stable tool contract data without Provider import paths."""
    metadata = source_metadata or {}
    return {
        **tool.model_dump(mode="json"),
        "provider_id": metadata.get("provider_id"),
        "provider_version": metadata.get("provider_version"),
        "source": metadata.get("source") or "legacy",
        "handler_identity": _handler_identity(handler),
    }


def build_catalog_contract(
    registry: Any,
    provider_health: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build the full reviewed contract for a Registry instance."""
    sources = _provider_sources(provider_health)
    tools = [
        canonical_tool_contract(tool, handler, source_metadata=sources.get(tool.name))
        for tool, handler in registry.registrations()
    ]
    tools.sort(key=lambda item: str(item["name"]))
    return {
        "schema_version": CATALOG_CONTRACT_SCHEMA_VERSION,
        "catalog_id": CATALOG_CONTRACT_ID,
        "tool_count": len(tools),
        "tools": tools,
    }
