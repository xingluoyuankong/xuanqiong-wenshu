"""Pure integrity checks for persisted approval catalog/resolver contracts.

No database access, live registry lookup, or mutation of the supplied objects.
Only declared canonical payload fields contribute to each content digest.
"""
from collections.abc import Mapping
from hashlib import sha256
import json
import math
import re
from typing import Any


class ApprovalSnapshotIntegrityError(ValueError):
    """A stable field identifies the violated contract; messages contain no data."""

    def __init__(self, field: str):
        self.field = field
        super().__init__("approval snapshot integrity mismatch")


_CATALOG_FIELDS = ("schema_version", "catalog_id", "generation", "providers", "tools")
_RESOLVER_FIELDS = ("resolver_schema_version", "release_id", "release_digest", "generation",
                    "request", "tools", "exclusions")
_MISSING = object()


def _fail(field: str) -> None:
    raise ApprovalSnapshotIntegrityError(field)


def _json_value(value: Any, field: str) -> Any:
    # Normalize containers, not array order, values, or policy decisions. Keep
    # field fixed through recursion so arbitrary payload keys never leak.
    if isinstance(value, Mapping):
        result = {}
        for key, child in value.items():
            if not isinstance(key, str):
                _fail(field)
            result[key] = _json_value(child, field)
        return result
    if isinstance(value, (list, tuple)):
        return [_json_value(child, field) for child in value]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    _fail(field)


def _canonical(value: Any, field: str) -> str:
    try:
        return json.dumps(_json_value(value, field), ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, OverflowError, RecursionError):
        _fail(field)


def _object(value: Any, field: str) -> Mapping:
    if not isinstance(value, Mapping):
        _fail(field)
    return value


def _array(value: Any, field: str) -> list:
    if not isinstance(value, (list, tuple)):
        _fail(field)
    return list(value)


def _string(value: Any, field: str, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (not empty and not value.strip()):
        _fail(field)
    return value


def _integer(value: Any, field: str, *, minimum: int = 1) -> int:
    if type(value) is not int or value < minimum:
        _fail(field)
    return value


def _boolean(value: Any, field: str) -> None:
    if type(value) is not bool:
        _fail(field)


def _strings(value: Any, field: str) -> list[str]:
    result = _array(value, field)
    for item in result:
        _string(item, field)
    return result


def _same(actual: Any, expected: Any, field: str) -> None:
    # Canonical equality accepts tuple/list roundtrips but distinguishes True
    # from 1, unlike Python container equality.
    if _canonical(actual, field) != _canonical(expected, field):
        _fail(field)


def _attr(row: Any, name: str, field: str) -> Any:
    value = getattr(row, name, _MISSING)
    if value is _MISSING:
        _fail(field)
    return value


def _payload(value: Any, keys: tuple[str, ...], prefix: str) -> dict:
    obj = _object(value, prefix)
    for key in keys:
        if key not in obj:
            _fail(f"{prefix}.{key}")
    return {key: obj[key] for key in keys}


def _digest(payload: dict, stored: Any, field: str) -> str:
    if not isinstance(stored, str) or re.fullmatch(r"[0-9a-f]{64}", stored) is None:
        _fail(field)
    try:
        expected = sha256(_canonical(payload, field).encode("utf-8")).hexdigest()
    except UnicodeError:
        _fail(field)
    if stored != expected:
        _fail(field)
    return expected


def _ordered_unique(values: list, field: str) -> None:
    if values != sorted(values) or len(values) != len(set(values)):
        _fail(field)


def _tools(value: Any, field: str) -> list:
    tools = _array(value, field)
    names = []
    for raw in tools:
        tool = _object(raw, field)
        names.append(_string(tool.get("name"), field))
        for key in ("description", "risk_level", "manifest_version", "cancellation_policy",
                    "idempotency_policy", "audit_event_type", "source"):
            _string(tool.get(key), field, empty=key == "description")
        for key in ("provider_id", "provider_version", "idempotency_key", "handler_identity", "access_level"):
            if key not in tool:
                _fail(field)
            if tool[key] is not None:
                _string(tool[key], field, empty=True)
        for key in ("requires_confirmation", "project_scoped", "supports_stream"):
            _boolean(tool.get(key), field)
        _integer(tool.get("timeout_seconds"), field)
        for key in ("input_schema", "output_schema"):
            _object(tool.get(key), field)
        for key in ("capability_tags", "allowed_project_roles"):
            _strings(tool.get(key), field)
        for raw_binding in _array(tool.get("context_bindings"), field):
            binding = _object(raw_binding, field)
            _string(binding.get("source"), field)
            _string(binding.get("argument_name"), field)
            _boolean(binding.get("required"), field)
    _ordered_unique(names, field)
    return tools


def _providers(value: Any, field: str) -> None:
    names = []
    for raw in _array(value, field):
        provider = _object(raw, field)
        names.append(_string(provider.get("provider_id"), field))
        for key in ("status", "source"):
            _string(provider.get(key), field)
        for key in ("provider_version", "api_version", "failure_code"):
            if key not in provider:
                _fail(field)
            if provider[key] is not None:
                _string(provider[key], field, empty=True)
        for key in ("tools", "capability_tags", "dependencies"):
            _ordered_unique(_strings(provider.get(key), field), field)
    _ordered_unique(names, field)


def _request(value: Any, field: str) -> Mapping:
    request = _object(value, field)
    keys = ("user_id", "project_id", "project_role", "requested_capabilities", "user_allowed_tools",
            "project_allowed_tools", "allowed_risk_levels", "include_confirmation_required")
    for key in keys:
        if key not in request:
            _fail(f"{field}.{key}")
    user = request["user_id"]
    if isinstance(user, str):
        _string(user, f"{field}.user_id")
    else:
        _integer(user, f"{field}.user_id", minimum=0)
    for key in ("project_id", "project_role"):
        if request[key] is not None:
            _string(request[key], f"{field}.{key}")
    for key in ("requested_capabilities", "user_allowed_tools", "project_allowed_tools", "allowed_risk_levels"):
        if key == "requested_capabilities" or request[key] is not None:
            _ordered_unique(_strings(request[key], f"{field}.{key}"), f"{field}.{key}")
    _boolean(request["include_confirmation_required"], f"{field}.include_confirmation_required")
    return request


def _exclusions(value: Any, field: str) -> list:
    exclusions = _array(value, field)
    ordering = []
    for raw in exclusions:
        item = _object(raw, field)
        ordering.append((_string(item.get("tool_name"), field), _string(item.get("reason"), field)))
    # The builder sorts by (tool_name, reason); it does not deduplicate.
    if ordering != sorted(ordering):
        _fail(field)
    return exclusions


def validate_approval_snapshot_integrity(*, run, snapshot, catalog_release) -> None:
    """Validate one modern Run's frozen content and relational projection.

    Success returns None. Legacy admission is the caller's responsibility; a
    missing relation is always an error at this strict modern-content boundary.
    """
    if snapshot is None:
        _fail("snapshot")
    if catalog_release is None:
        _fail("catalog_release")
    context = _object(_attr(run, "context_json", "run.context_json"), "run.context_json")
    release = _object(context.get("catalog_release"), "catalog_release")
    catalog = _payload(release, _CATALOG_FIELDS, "catalog_release")
    _integer(catalog["schema_version"], "catalog_release.schema_version")
    _integer(catalog["generation"], "catalog_release.generation")
    _string(catalog["catalog_id"], "catalog_release.catalog_id")
    _providers(catalog["providers"], "catalog_release.providers")
    tools = _tools(catalog["tools"], "catalog_release.tools")
    catalog_digest = _digest(catalog, release.get("digest"), "catalog_release.digest")
    catalog_id = f'{catalog["catalog_id"]}:{catalog_digest[:16]}'
    _same(release.get("release_id"), catalog_id, "catalog_release.release_id")
    for key in ("catalog_id", "schema_version", "generation", "digest", "release_id"):
        _same(_attr(catalog_release, key, f"catalog_release.{key}"), release[key], f"catalog_release.{key}")
    _same(_attr(catalog_release, "manifest_json", "catalog_release.manifest_json"),
          release, "catalog_release.manifest_json")

    resolution = _object(context.get("capability_resolution"), "capability_resolution")
    resolver = _payload(resolution, _RESOLVER_FIELDS, "capability_resolution")
    _integer(resolver["resolver_schema_version"], "capability_resolution.resolver_schema_version")
    _integer(resolver["generation"], "capability_resolution.generation")
    _string(resolver["release_id"], "capability_resolution.release_id")
    _string(resolver["release_digest"], "capability_resolution.release_digest")
    request = _request(resolver["request"], "capability_resolution.request")
    selected_tools = _tools(resolver["tools"], "capability_resolution.tools")
    exclusions = _exclusions(resolver["exclusions"], "capability_resolution.exclusions")
    resolver_digest = _digest(resolver, resolution.get("digest"), "capability_resolution.digest")
    resolver_id = f'resolver-v{resolver["resolver_schema_version"]}:{resolver_digest[:16]}'
    _same(resolution.get("snapshot_id"), resolver_id, "capability_resolution.snapshot_id")
    for key, expected in (("release_id", catalog_id), ("release_digest", catalog_digest),
                          ("generation", catalog["generation"])):
        _same(resolver[key], expected, f"capability_resolution.{key}")
    for key in ("user_id", "project_id"):
        _same(request[key], _attr(run, key, f"run.{key}"), f"capability_resolution.request.{key}")
    catalog_by_name = {tool["name"]: tool for tool in tools}
    for tool in selected_tools:
        _same(tool, catalog_by_name.get(tool["name"]), "capability_resolution.tools")
    selected = [tool["name"] for tool in selected_tools]

    run_id = _string(_attr(run, "id", "run.id"), "run.id")
    qualified_id = f"{resolver_id}:run:{run_id}"
    row_catalog_id = _string(_attr(catalog_release, "id", "catalog_release.id"), "catalog_release.id")
    row_snapshot_id = _string(_attr(snapshot, "id", "snapshot.id"), "snapshot.id")
    for key, expected in (
        ("run_id", run_id), ("user_id", _attr(run, "user_id", "run.user_id")),
        ("project_id", _attr(run, "project_id", "run.project_id")),
        ("transaction_id", _attr(run, "transaction_id", "run.transaction_id")),
        ("catalog_release_id", row_catalog_id), ("generation", resolver["generation"]),
        ("resolver_schema_version", resolver["resolver_schema_version"]),
        ("resolved_version", str(resolver["resolver_schema_version"])),
        ("digest", resolver_digest), ("release_digest", catalog_digest),
        ("snapshot_id", qualified_id), ("request_json", request),
        ("selected_capability_ids_json", selected), ("exclusions_json", exclusions),
    ):
        _same(_attr(snapshot, key, f"snapshot.{key}"), expected, f"snapshot.{key}")
    scope = _object(_attr(snapshot, "resolved_scope_json", "snapshot.resolved_scope_json"),
                    "snapshot.resolved_scope_json")
    for key, expected in (("resolver_snapshot_id", resolver_id), ("release_id", catalog_id),
                          ("tool_names", selected)):
        _same(scope.get(key), expected, f"snapshot.resolved_scope_json.{key}")
    for key, expected in (
        ("catalog_release_id", catalog_id), ("capability_resolution_id", resolver_id),
        ("relational_catalog_release_id", row_catalog_id), ("relational_capability_snapshot_id", row_snapshot_id),
        ("relational_capability_snapshot_key", qualified_id), ("relational_capability_snapshot_digest", resolver_digest),
    ):
        _same(context.get(key), expected, f"run.context_json.{key}")
