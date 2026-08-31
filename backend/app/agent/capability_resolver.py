"""Deterministic capability resolution over an immutable CatalogRelease.

Resolution is intentionally a pure control-plane operation.  It does not
execute a tool, read project content, or grant write permissions; it returns a
stable snapshot that an executor can bind to later.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from hashlib import sha256
import json
import math
from typing import Any

from .catalog_release import CatalogRelease, ToolRelease

RESOLVER_SCHEMA_VERSION = 1


class CapabilityResolutionError(ValueError):
    """Raised when a resolver request or released capability is invalid."""


class SchemaValidationError(CapabilityResolutionError):
    """Raised when tool arguments do not satisfy the released input schema."""


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _normalise_values(value: Iterable[Any] | str | None, *, field_name: str) -> tuple[str, ...] | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = (value,)
    try:
        raw_values = tuple(value)
    except TypeError as exc:
        raise CapabilityResolutionError(f"{field_name} must be a string array") from exc
    values = tuple(sorted({str(item).strip() for item in raw_values}))
    if any(not item for item in values) or any(str(item).strip() == "" for item in raw_values):
        raise CapabilityResolutionError(f"{field_name} must not contain empty values")
    return values


def _normalise_requested(value: Iterable[Any] | str | None) -> tuple[str, ...]:
    return _normalise_values(value, field_name="requested_capabilities") or ()


def _normalise_user_id(value: int | str) -> int | str:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise CapabilityResolutionError("user_id must be an integer or non-empty string")
    if isinstance(value, str):
        if not value.strip():
            raise CapabilityResolutionError("user_id must not be empty")
        return value.strip()
    if value < 0:
        raise CapabilityResolutionError("user_id must not be negative")
    return value


def _normalise_project_id(value: str | None) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result or None


@dataclass(frozen=True, slots=True)
class CapabilityResolutionRequest:
    """Stable input policy for resolving capabilities for one user/project."""

    user_id: int | str
    project_id: str | None = None
    requested_capabilities: tuple[str, ...] = ()
    user_allowed_tools: tuple[str, ...] | None = None
    project_allowed_tools: tuple[str, ...] | None = None
    allowed_risk_levels: tuple[str, ...] | None = None
    include_confirmation_required: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "user_id", _normalise_user_id(self.user_id))
        object.__setattr__(self, "project_id", _normalise_project_id(self.project_id))
        object.__setattr__(self, "requested_capabilities", _normalise_requested(self.requested_capabilities))
        object.__setattr__(self, "user_allowed_tools", _normalise_values(self.user_allowed_tools, field_name="user_allowed_tools"))
        object.__setattr__(self, "project_allowed_tools", _normalise_values(self.project_allowed_tools, field_name="project_allowed_tools"))
        object.__setattr__(self, "allowed_risk_levels", _normalise_values(self.allowed_risk_levels, field_name="allowed_risk_levels"))
        if not isinstance(self.include_confirmation_required, bool):
            raise CapabilityResolutionError("include_confirmation_required must be boolean")

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "project_id": self.project_id,
            "requested_capabilities": list(self.requested_capabilities),
            "user_allowed_tools": list(self.user_allowed_tools) if self.user_allowed_tools is not None else None,
            "project_allowed_tools": list(self.project_allowed_tools) if self.project_allowed_tools is not None else None,
            "allowed_risk_levels": list(self.allowed_risk_levels) if self.allowed_risk_levels is not None else None,
            "include_confirmation_required": self.include_confirmation_required,
        }


@dataclass(frozen=True, slots=True)
class CapabilityExclusion:
    tool_name: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {"tool_name": self.tool_name, "reason": self.reason}


@dataclass(frozen=True, slots=True)
class CapabilityResolverSnapshot:
    """Immutable result of one resolution decision."""

    resolver_schema_version: int
    release_id: str
    release_digest: str
    generation: int
    request: CapabilityResolutionRequest
    tools: tuple[ToolRelease, ...]
    exclusions: tuple[CapabilityExclusion, ...]
    digest: str = field(init=False)
    snapshot_id: str = field(init=False)

    def __post_init__(self) -> None:
        if self.resolver_schema_version < 1:
            raise CapabilityResolutionError("resolver_schema_version must be positive")
        tools = tuple(sorted(self.tools, key=lambda item: item.name))
        exclusions = tuple(sorted(self.exclusions, key=lambda item: (item.tool_name, item.reason)))
        if len({tool.name for tool in tools}) != len(tools):
            raise CapabilityResolutionError("resolved tool names must be unique")
        object.__setattr__(self, "tools", tools)
        object.__setattr__(self, "exclusions", exclusions)
        payload = self._payload()
        digest = sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
        object.__setattr__(self, "digest", digest)
        object.__setattr__(self, "snapshot_id", f"resolver-v{self.resolver_schema_version}:{digest[:16]}")

    def _payload(self) -> dict[str, Any]:
        return {
            "resolver_schema_version": self.resolver_schema_version,
            "release_id": self.release_id,
            "release_digest": self.release_digest,
            "generation": self.generation,
            "request": self.request.to_dict(),
            "tools": [tool.to_dict() for tool in self.tools],
            "exclusions": [item.to_dict() for item in self.exclusions],
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "snapshot_id": self.snapshot_id, "digest": self.digest}

    @property
    def tool_names(self) -> tuple[str, ...]:
        return tuple(tool.name for tool in self.tools)

    def get_tool(self, name: str) -> ToolRelease:
        for tool in self.tools:
            if tool.name == name:
                return tool
        raise KeyError(f"capability is not resolved: {name}")


class CapabilityResolver:
    """Resolve a release using user, project, capability and optional policy filters."""

    def __init__(self, release: CatalogRelease) -> None:
        if not isinstance(release, CatalogRelease):
            raise CapabilityResolutionError("release must be a CatalogRelease")
        self.release = release

    def resolve(
        self,
        request: CapabilityResolutionRequest | None = None,
        *,
        user_id: int | str | None = None,
        project_id: str | None = None,
        requested_capabilities: Iterable[Any] | str | None = None,
        user_allowed_tools: Iterable[Any] | str | None = None,
        project_allowed_tools: Iterable[Any] | str | None = None,
        allowed_risk_levels: Iterable[Any] | str | None = None,
        include_confirmation_required: bool = True,
    ) -> CapabilityResolverSnapshot:
        if request is not None:
            if any(value is not None for value in (user_id, project_id, requested_capabilities, user_allowed_tools, project_allowed_tools, allowed_risk_levels)):
                raise CapabilityResolutionError("pass either request or keyword filters, not both")
            effective = request
        else:
            if user_id is None:
                raise CapabilityResolutionError("user_id is required")
            effective = CapabilityResolutionRequest(
                user_id=user_id,
                project_id=project_id,
                requested_capabilities=_normalise_requested(requested_capabilities),
                user_allowed_tools=_normalise_values(user_allowed_tools, field_name="user_allowed_tools"),
                project_allowed_tools=_normalise_values(project_allowed_tools, field_name="project_allowed_tools"),
                allowed_risk_levels=_normalise_values(allowed_risk_levels, field_name="allowed_risk_levels"),
                include_confirmation_required=include_confirmation_required,
            )

        providers = {provider.provider_id: provider for provider in self.release.providers}
        selected: list[ToolRelease] = []
        exclusions: list[CapabilityExclusion] = []
        for tool in self.release.tools:
            reason = self._exclusion_reason(tool, effective, providers)
            if reason is None:
                selected.append(tool)
            else:
                exclusions.append(CapabilityExclusion(tool_name=tool.name, reason=reason))
        return CapabilityResolverSnapshot(
            resolver_schema_version=RESOLVER_SCHEMA_VERSION,
            release_id=self.release.release_id,
            release_digest=self.release.digest,
            generation=self.release.generation,
            request=effective,
            tools=tuple(selected),
            exclusions=tuple(exclusions),
        )

    @staticmethod
    def _exclusion_reason(
        tool: ToolRelease,
        request: CapabilityResolutionRequest,
        providers: Mapping[str, Any],
    ) -> str | None:
        if request.user_allowed_tools is not None and tool.name not in request.user_allowed_tools:
            return "user_tool_not_allowed"
        if tool.project_scoped and request.project_id is None:
            return "project_context_required"
        if request.project_allowed_tools is not None and tool.name not in request.project_allowed_tools:
            return "project_tool_not_allowed"
        if request.allowed_risk_levels is not None and tool.risk_level not in request.allowed_risk_levels:
            return "risk_level_not_allowed"
        if not request.include_confirmation_required and tool.requires_confirmation:
            return "confirmation_required"
        if request.requested_capabilities:
            identifiers = {tool.name}
            if tool.provider_id:
                identifiers.add(tool.provider_id)
            identifiers.update(tool.capability_tags)
            if not identifiers.intersection(request.requested_capabilities):
                return "capability_not_requested"
        if tool.provider_id:
            provider = providers.get(tool.provider_id)
            if provider is None or provider.status != "loaded":
                return "provider_unavailable"
        return None

    def validate_arguments(self, tool_name: str, arguments: Mapping[str, Any] | None, *, snapshot: CapabilityResolverSnapshot | None = None) -> None:
        tool = (snapshot or self.resolve_for_validation()).get_tool(tool_name)
        validate_tool_arguments(tool, arguments)

    def resolve_for_validation(self) -> CapabilityResolverSnapshot:
        """Return all project-scoped tools under a concrete placeholder project.

        This helper exists only for argument-contract checks when the caller has
        a ToolRelease already.  Normal resolution should always use ``resolve``.
        """
        request = CapabilityResolutionRequest(user_id="schema-validation", project_id="schema-validation")
        return self.resolve(request)


def _type_matches(value: Any, expected: str) -> bool:
    return {
        "object": isinstance(value, Mapping),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }.get(expected, False)


def _validate_schema(value: Any, schema: Mapping[str, Any], path: str) -> None:
    if not isinstance(schema, Mapping):
        raise SchemaValidationError(f"{path}: schema must be an object")
    if "$ref" in schema:
        raise SchemaValidationError(f"{path}: $ref schemas are not supported by the release validator")
    expected = schema.get("type")
    if isinstance(expected, list):
        if not any(isinstance(item, str) and _type_matches(value, item) for item in expected):
            raise SchemaValidationError(f"{path}: expected one of {expected}")
    elif isinstance(expected, str) and not _type_matches(value, expected):
        raise SchemaValidationError(f"{path}: expected {expected}")
    if "enum" in schema and value not in schema["enum"]:
        raise SchemaValidationError(f"{path}: value is not in enum")
    if "const" in schema and value != schema["const"]:
        raise SchemaValidationError(f"{path}: value does not match const")
    if isinstance(value, Mapping):
        required = schema.get("required", ())
        missing = [name for name in required if name not in value]
        if missing:
            raise SchemaValidationError(f"{path}: missing required field(s): {', '.join(map(str, missing))}")
        properties = schema.get("properties", {})
        if not isinstance(properties, Mapping):
            raise SchemaValidationError(f"{path}.properties: expected object")
        if schema.get("additionalProperties") is False:
            unknown = [name for name in value if name not in properties]
            if unknown:
                raise SchemaValidationError(f"{path}: unknown field(s): {', '.join(map(str, unknown))}")
        for name, child_schema in properties.items():
            if name in value:
                _validate_schema(value[name], child_schema, f"{path}.{name}")
    if isinstance(value, list):
        if isinstance(schema.get("items"), Mapping):
            for index, item in enumerate(value):
                _validate_schema(item, schema["items"], f"{path}[{index}]")
        if isinstance(schema.get("minItems"), int) and len(value) < schema["minItems"]:
            raise SchemaValidationError(f"{path}: expected at least {schema['minItems']} items")
        if isinstance(schema.get("maxItems"), int) and len(value) > schema["maxItems"]:
            raise SchemaValidationError(f"{path}: expected at most {schema['maxItems']} items")
    if isinstance(value, str):
        if isinstance(schema.get("minLength"), int) and len(value) < schema["minLength"]:
            raise SchemaValidationError(f"{path}: string is shorter than minLength")
        if isinstance(schema.get("maxLength"), int) and len(value) > schema["maxLength"]:
            raise SchemaValidationError(f"{path}: string is longer than maxLength")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(schema.get("minimum"), (int, float)) and value < schema["minimum"]:
            raise SchemaValidationError(f"{path}: number is below minimum")
        if isinstance(schema.get("maximum"), (int, float)) and value > schema["maximum"]:
            raise SchemaValidationError(f"{path}: number is above maximum")


def validate_tool_arguments(tool: ToolRelease, arguments: Mapping[str, Any] | None) -> None:
    """Validate arguments against the immutable input schema in a release."""
    if not isinstance(tool, ToolRelease):
        raise SchemaValidationError("tool must be a ToolRelease")
    payload: Any = {} if arguments is None else arguments
    _validate_schema(payload, tool.input_schema, f"{tool.name}.arguments")


def validate_resolved_arguments(
    snapshot: CapabilityResolverSnapshot,
    tool_name: str,
    arguments: Mapping[str, Any] | None,
) -> None:
    """Validate only a capability present in a previously resolved snapshot."""
    if not isinstance(snapshot, CapabilityResolverSnapshot):
        raise SchemaValidationError("snapshot must be a CapabilityResolverSnapshot")
    validate_tool_arguments(snapshot.get_tool(tool_name), arguments)


def resolve_capabilities(
    release: CatalogRelease,
    *,
    user_id: int | str,
    project_id: str | None = None,
    requested_capabilities: Iterable[Any] | str | None = None,
    user_allowed_tools: Iterable[Any] | str | None = None,
    project_allowed_tools: Iterable[Any] | str | None = None,
    allowed_risk_levels: Iterable[Any] | str | None = None,
    include_confirmation_required: bool = True,
) -> CapabilityResolverSnapshot:
    """Functional convenience wrapper around :class:`CapabilityResolver`."""
    return CapabilityResolver(release).resolve(
        user_id=user_id,
        project_id=project_id,
        requested_capabilities=requested_capabilities,
        user_allowed_tools=user_allowed_tools,
        project_allowed_tools=project_allowed_tools,
        allowed_risk_levels=allowed_risk_levels,
        include_confirmation_required=include_confirmation_required,
    )
