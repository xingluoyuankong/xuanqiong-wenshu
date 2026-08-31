"""Immutable, content-addressed capability catalog releases.

The first release slice deliberately has no persistence or runtime wiring.  It
freezes the current AgentToolRegistry contract into deterministic Python value
objects so a later Run can bind to an auditable capability set without reading
live Registry state again.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from hashlib import sha256
import json
import math
from types import MappingProxyType
from typing import Any

CATALOG_RELEASE_SCHEMA_VERSION = 1
CATALOG_RELEASE_ID = "agent-catalog-release-v1"


class CatalogReleaseError(ValueError):
    """Raised when a Registry snapshot cannot form a valid release."""


def _freeze_json(value: Any, *, path: str = "$") -> Any:
    """Recursively convert JSON values to immutable values."""
    if isinstance(value, Mapping):
        frozen: dict[str, Any] = {}
        for raw_key, child in value.items():
            if not isinstance(raw_key, str):
                raise CatalogReleaseError(f"{path}: JSON object keys must be strings")
            frozen[raw_key] = _freeze_json(child, path=f"{path}.{raw_key}")
        return MappingProxyType(dict(sorted(frozen.items())))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(child, path=f"{path}[{index}]") for index, child in enumerate(value))
    if isinstance(value, (set, frozenset)):
        raise CatalogReleaseError(f"{path}: sets are not JSON serializable")
    if isinstance(value, float) and not math.isfinite(value):
        raise CatalogReleaseError(f"{path}: non-finite numbers are not supported")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise CatalogReleaseError(f"{path}: unsupported JSON value {type(value).__name__}")


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(child) for child in value]
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _string_tuple(values: Iterable[Any], *, field_name: str) -> tuple[str, ...]:
    normalized = tuple(sorted({str(value).strip() for value in values if str(value).strip()}))
    if any(not value for value in normalized):
        raise CatalogReleaseError(f"{field_name} contains an empty value")
    return normalized


@dataclass(frozen=True, slots=True)
class ContextBindingRelease:
    source: str
    argument_name: str
    required: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "argument_name": self.argument_name,
            "required": self.required,
        }


@dataclass(frozen=True, slots=True)
class ProviderRelease:
    provider_id: str
    provider_version: str | None
    status: str
    source: str
    tools: tuple[str, ...] = ()
    failure_code: str | None = None
    api_version: str | None = None
    capability_tags: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.provider_id.strip():
            raise CatalogReleaseError("provider_id must not be empty")
        object.__setattr__(self, "tools", _string_tuple(self.tools, field_name="provider.tools"))
        object.__setattr__(self, "capability_tags", _string_tuple(self.capability_tags, field_name="provider.capability_tags"))
        object.__setattr__(self, "dependencies", _string_tuple(self.dependencies, field_name="provider.dependencies"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "provider_version": self.provider_version,
            "status": self.status,
            "source": self.source,
            "tools": list(self.tools),
            "failure_code": self.failure_code,
            "api_version": self.api_version,
            "capability_tags": list(self.capability_tags),
            "dependencies": list(self.dependencies),
        }


@dataclass(frozen=True, slots=True)
class ToolRelease:
    name: str
    description: str
    input_schema: Mapping[str, Any]
    output_schema: Mapping[str, Any]
    risk_level: str
    requires_confirmation: bool
    project_scoped: bool
    supports_stream: bool
    idempotency_key: str | None
    manifest_version: str
    timeout_seconds: int
    cancellation_policy: str
    idempotency_policy: str
    audit_event_type: str
    context_bindings: tuple[ContextBindingRelease, ...]
    provider_id: str | None
    provider_version: str | None
    source: str
    capability_tags: tuple[str, ...] = ()
    handler_identity: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise CatalogReleaseError("tool.name must not be empty")
        if not isinstance(self.input_schema, Mapping) or not isinstance(self.output_schema, Mapping):
            raise CatalogReleaseError(f"tool {self.name}: schemas must be JSON objects")
        object.__setattr__(self, "input_schema", _freeze_json(dict(self.input_schema), path=f"tools.{self.name}.input_schema"))
        object.__setattr__(self, "output_schema", _freeze_json(dict(self.output_schema), path=f"tools.{self.name}.output_schema"))
        object.__setattr__(self, "context_bindings", tuple(self.context_bindings))
        object.__setattr__(self, "capability_tags", _string_tuple(self.capability_tags, field_name=f"tools.{self.name}.capability_tags"))
        if self.timeout_seconds < 1:
            raise CatalogReleaseError(f"tool {self.name}: timeout_seconds must be positive")

    @classmethod
    def from_contract(
        cls,
        contract: Mapping[str, Any],
        *,
        snapshot_metadata: Mapping[str, Any] | None = None,
        capability_tags: Iterable[str] = (),
    ) -> "ToolRelease":
        metadata = snapshot_metadata or {}
        raw_bindings = contract.get("context_bindings", ())
        bindings: list[ContextBindingRelease] = []
        for index, raw_binding in enumerate(raw_bindings):
            if not isinstance(raw_binding, Mapping):
                raise CatalogReleaseError(f"tool {contract.get('name')}: context_bindings[{index}] must be an object")
            try:
                bindings.append(
                    ContextBindingRelease(
                        source=str(raw_binding["source"]),
                        argument_name=str(raw_binding["argument_name"]),
                        required=bool(raw_binding.get("required", False)),
                    )
                )
            except KeyError as exc:
                raise CatalogReleaseError(f"tool {contract.get('name')}: missing binding field {exc.args[0]}") from exc
        return cls(
            name=str(contract.get("name", "")),
            description=str(contract.get("description", "")),
            input_schema=contract.get("input_schema", {}),
            output_schema=contract.get("output_schema", {}),
            risk_level=str(contract.get("risk_level", "")),
            requires_confirmation=bool(contract.get("requires_confirmation", False)),
            project_scoped=bool(contract.get("project_scoped", True)),
            supports_stream=bool(contract.get("supports_stream", False)),
            idempotency_key=contract.get("idempotency_key"),
            manifest_version=str(contract.get("manifest_version", "")),
            timeout_seconds=int(contract.get("timeout_seconds", 0)),
            cancellation_policy=str(contract.get("cancellation_policy", "")),
            idempotency_policy=str(contract.get("idempotency_policy", "")),
            audit_event_type=str(contract.get("audit_event_type", "")),
            context_bindings=tuple(bindings),
            provider_id=metadata.get("provider_id", contract.get("provider_id")),
            provider_version=metadata.get("provider_version", contract.get("provider_version")),
            source=str(metadata.get("source", contract.get("source", "legacy"))),
            capability_tags=tuple(capability_tags),
            handler_identity=contract.get("handler_identity"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": _thaw_json(self.input_schema),
            "output_schema": _thaw_json(self.output_schema),
            "risk_level": self.risk_level,
            "requires_confirmation": self.requires_confirmation,
            "project_scoped": self.project_scoped,
            "supports_stream": self.supports_stream,
            "idempotency_key": self.idempotency_key,
            "manifest_version": self.manifest_version,
            "timeout_seconds": self.timeout_seconds,
            "cancellation_policy": self.cancellation_policy,
            "idempotency_policy": self.idempotency_policy,
            "audit_event_type": self.audit_event_type,
            "context_bindings": [binding.to_dict() for binding in self.context_bindings],
            "provider_id": self.provider_id,
            "provider_version": self.provider_version,
            "source": self.source,
            "capability_tags": list(self.capability_tags),
            "handler_identity": self.handler_identity,
        }


@dataclass(frozen=True, slots=True)
class CatalogRelease:
    schema_version: int
    catalog_id: str
    generation: int
    providers: tuple[ProviderRelease, ...]
    tools: tuple[ToolRelease, ...]
    digest: str = field(init=False)
    release_id: str = field(init=False)

    def __post_init__(self) -> None:
        if self.schema_version < 1:
            raise CatalogReleaseError("schema_version must be positive")
        if self.generation < 1:
            raise CatalogReleaseError("generation must be positive")
        providers = tuple(sorted(self.providers, key=lambda item: item.provider_id))
        tools = tuple(sorted(self.tools, key=lambda item: item.name))
        if len({item.provider_id for item in providers}) != len(providers):
            raise CatalogReleaseError("provider IDs must be unique")
        if len({item.name for item in tools}) != len(tools):
            raise CatalogReleaseError("tool names must be unique")
        object.__setattr__(self, "providers", providers)
        object.__setattr__(self, "tools", tools)
        payload = self._payload()
        digest = sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
        object.__setattr__(self, "digest", digest)
        object.__setattr__(self, "release_id", f"{self.catalog_id}:{digest[:16]}")

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "catalog_id": self.catalog_id,
            "generation": self.generation,
            "providers": [provider.to_dict() for provider in self.providers],
            "tools": [tool.to_dict() for tool in self.tools],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._payload(),
            "release_id": self.release_id,
            "digest": self.digest,
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.to_dict())

    def get_tool(self, name: str) -> ToolRelease:
        for tool in self.tools:
            if tool.name == name:
                return tool
        raise KeyError(f"unknown released capability: {name}")



def _validate_registry_snapshot(snapshot: Mapping[str, Any]) -> tuple[int, list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    if not isinstance(snapshot, Mapping):
        raise CatalogReleaseError("registry_snapshot must be an object")
    generation = snapshot.get("generation")
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
        raise CatalogReleaseError("registry_snapshot.generation must be a positive integer")
    raw_tools = snapshot.get("tools")
    raw_providers = snapshot.get("providers", [])
    if not isinstance(raw_tools, (list, tuple)) or not isinstance(raw_providers, (list, tuple)):
        raise CatalogReleaseError("registry_snapshot.tools/providers must be arrays")
    tools: list[Mapping[str, Any]] = []
    for index, raw_tool in enumerate(raw_tools):
        if not isinstance(raw_tool, Mapping) or not str(raw_tool.get("name", "")).strip():
            raise CatalogReleaseError(f"registry_snapshot.tools[{index}] must contain a name")
        tools.append(raw_tool)
    providers: list[Mapping[str, Any]] = []
    for index, raw_provider in enumerate(raw_providers):
        if not isinstance(raw_provider, Mapping) or not str(raw_provider.get("provider_id", "")).strip():
            raise CatalogReleaseError(f"registry_snapshot.providers[{index}] must contain provider_id")
        providers.append(raw_provider)
    if len({str(item["name"]) for item in tools}) != len(tools):
        raise CatalogReleaseError("registry_snapshot contains duplicate tool names")
    return generation, tools, providers


def _provider_releases(raw_providers: Iterable[Mapping[str, Any]]) -> tuple[ProviderRelease, ...]:
    result: list[ProviderRelease] = []
    for raw in raw_providers:
        result.append(
            ProviderRelease(
                provider_id=str(raw.get("provider_id", "")).strip(),
                provider_version=(str(raw["provider_version"]).strip() or None) if raw.get("provider_version") is not None else None,
                status=str(raw.get("status", "unknown")),
                source=str(raw.get("source", "unknown")),
                tools=tuple(raw.get("tools", ())),
                failure_code=(str(raw["failure_code"]) if raw.get("failure_code") is not None else None),
                api_version=(str(raw["api_version"]) if raw.get("api_version") is not None else None),
                capability_tags=tuple(raw.get("capability_tags", ())),
                dependencies=tuple(raw.get("dependencies", ())),
            )
        )
    return tuple(result)


def build_catalog_release(
    registry_snapshot: Mapping[str, Any] | None = None,
    *,
    registry: Any | None = None,
    provider_health: Iterable[Mapping[str, Any]] | None = None,
) -> CatalogRelease:
    """Freeze a Registry snapshot plus its full reviewed manifests.

    ``registry_snapshot`` should normally be the value returned by
    ``get_default_tool_registry_snapshot``.  The live Registry is read only
    while constructing the release; the returned object contains no live
    Registry references.  Passing a custom Registry is supported for tests and
    future tenant-specific catalogs.
    """
    if registry is None:
        from .registry import DEFAULT_TOOL_REGISTRY

        registry = DEFAULT_TOOL_REGISTRY
    if registry_snapshot is None:
        from .registry import get_default_tool_registry_snapshot

        registry_snapshot = get_default_tool_registry_snapshot()
    generation, snapshot_tools, snapshot_providers = _validate_registry_snapshot(registry_snapshot)
    health = list(provider_health) if provider_health is not None else snapshot_providers

    from .catalog_contract import build_catalog_contract

    contract = build_catalog_contract(registry, health)
    contract_by_name = {str(item["name"]): item for item in contract["tools"]}
    snapshot_by_name = {str(item["name"]): item for item in snapshot_tools}
    if set(contract_by_name) != set(snapshot_by_name):
        missing = sorted(set(contract_by_name) - set(snapshot_by_name))
        extra = sorted(set(snapshot_by_name) - set(contract_by_name))
        raise CatalogReleaseError(f"Registry snapshot/tool contract mismatch; missing={missing}, extra={extra}")

    provider_by_id = {provider.provider_id: provider for provider in _provider_releases(snapshot_providers)}
    tools: list[ToolRelease] = []
    for name in sorted(contract_by_name):
        snapshot_metadata = snapshot_by_name[name]
        contract_item = contract_by_name[name]
        provider_id = snapshot_metadata.get("provider_id", contract_item.get("provider_id"))
        provider = provider_by_id.get(str(provider_id)) if provider_id else None
        tools.append(
            ToolRelease.from_contract(
                contract_item,
                snapshot_metadata=snapshot_metadata,
                capability_tags=provider.capability_tags if provider is not None else (),
            )
        )
    return CatalogRelease(
        schema_version=CATALOG_RELEASE_SCHEMA_VERSION,
        catalog_id=CATALOG_RELEASE_ID,
        generation=generation,
        providers=_provider_releases(snapshot_providers),
        tools=tuple(tools),
    )


# Explicit alias for callers that prefer the verb used by the product plan.
create_catalog_release = build_catalog_release
