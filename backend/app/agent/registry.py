"""Runtime-discoverable project tool registry for Agent Phase 1."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
from importlib import import_module
from typing import Any, Awaitable, Callable

from .policy import requires_confirmation
from .schemas import AgentRiskLevel, ToolContextBinding, ToolManifest

AgentToolHandler = Callable[..., Awaitable[dict[str, Any]]]
AgentToolProvider = Callable[['AgentToolRegistry'], None]
_PROVIDER_PACKAGE_PREFIX = 'app.agent.providers.'
_PROVIDER_ENTRYPOINT = 'register_agent_tools'


class ToolContractViolation(ValueError):
    pass


class ToolExecutionTimeout(ToolContractViolation):
    pass


class ToolExecutionCancelled(ToolContractViolation):
    pass


class ToolProviderLoadError(ToolContractViolation):
    pass


def load_tool_provider(registry: 'AgentToolRegistry', provider_path: str) -> tuple[str, ...]:
    """Load one reviewed Provider atomically under the normal ToolManifest policy."""
    module_name, separator, attribute = provider_path.partition(':')
    if (
        not separator
        or not module_name.startswith(_PROVIDER_PACKAGE_PREFIX)
        or attribute != _PROVIDER_ENTRYPOINT
    ):
        raise ToolProviderLoadError(
            'tool provider must use app.agent.providers.<module>:register_agent_tools'
        )
    try:
        provider = getattr(import_module(module_name), attribute)
    except (ImportError, AttributeError) as exc:
        raise ToolProviderLoadError(f'cannot load tool provider: {provider_path}') from exc
    if not callable(provider):
        raise ToolProviderLoadError(f'tool provider is not callable: {provider_path}')
    staged_registry = AgentToolRegistry()
    try:
        provider(staged_registry)
    except Exception as exc:
        raise ToolProviderLoadError(f'tool provider failed: {provider_path}') from exc
    registered_names: list[str] = []
    for tool, handler in staged_registry.registrations():
        registry.register(tool, handler=handler)
        registered_names.append(tool.name)
    return tuple(registered_names)


def _validate_schema(value: Any, schema: dict[str, Any], path: str = "$", *, output: bool = False) -> None:
    expected = schema.get("type")
    matches = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
    }
    if expected in matches and not matches[expected]:
        raise ToolContractViolation(f"{path}: expected {expected}")
    if isinstance(value, dict):
        required = schema.get("required", [])
        missing = [name for name in required if name not in value]
        if missing:
            raise ToolContractViolation(f"{path}: missing required field(s): {', '.join(missing)}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            unknown = [name for name in value if name not in properties]
            if unknown:
                raise ToolContractViolation(f"{path}: unknown field(s): {', '.join(unknown)}")
        for name, child in properties.items():
            if name in value and isinstance(child, dict):
                _validate_schema(value[name], child, f"{path}.{name}", output=output)
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(value[:100]):
            _validate_schema(item, schema["items"], f"{path}[{index}]")


class AgentToolRegistry:
    def __init__(self, tools: Iterable[ToolManifest] = ()) -> None:
        self._tools: dict[str, ToolManifest] = {}
        self._handlers: dict[str, AgentToolHandler] = {}
        for tool in tools:
            self.register(tool)

    def register(self, tool: ToolManifest, *, handler: AgentToolHandler | None = None) -> None:
        if tool.name in self._tools:
            raise ValueError(f"duplicate agent tool: {tool.name}")
        if tool.requires_confirmation != requires_confirmation(tool.risk_level):
            raise ValueError(f"confirmation policy mismatch for tool: {tool.name}")
        properties = tool.input_schema.get("properties", {}) if isinstance(tool.input_schema, dict) else {}
        for binding in getattr(tool, "context_bindings", ()):
            if binding.argument_name not in properties:
                raise ValueError(
                    f"context binding {binding.source}->{binding.argument_name} is not declared by tool input schema: {tool.name}"
                )
        self._tools[tool.name] = tool
        if handler is not None:
            self._handlers[tool.name] = handler

    def get(self, name: str) -> ToolManifest:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"unknown agent tool: {name}") from exc

    def list_tools(self) -> list[ToolManifest]:
        return list(self._tools.values())

    def registrations(self) -> tuple[tuple[ToolManifest, AgentToolHandler | None], ...]:
        """Return immutable registration records for safe staged Provider loading."""
        return tuple((tool, self._handlers.get(name)) for name, tool in self._tools.items())

    def get_handler(self, name: str) -> AgentToolHandler:
        self.get(name)
        try:
            return self._handlers[name]
        except KeyError as exc:
            raise KeyError(f"tool has no registered handler: {name}") from exc

    def get_handler_identity(self, name: str) -> str:
        """Return the immutable callable identity captured by a Catalog Release."""
        handler = self.get_handler(name)
        module = str(getattr(handler, "__module__", "") or "").strip()
        qualname = str(getattr(handler, "__qualname__", "") or "").strip()
        if not module or not qualname:
            raise ToolContractViolation(f"tool handler has no stable identity: {name}")
        return f"{module}:{qualname}"

    def validate_planned_input(self, name: str, arguments: dict[str, Any] | None = None) -> None:
        """Validate a planned tool input before a write approval has a real ID."""
        manifest = self.get(name)
        payload = dict(arguments or {})
        required = manifest.input_schema.get("required", []) if isinstance(manifest.input_schema, dict) else []
        if manifest.requires_confirmation and "_approval_id" in required and "_approval_id" not in payload:
            payload["_approval_id"] = "__planned__"
        _validate_schema(payload, manifest.input_schema)

    async def execute(
        self,
        name: str,
        *,
        session,
        user_id: int,
        project_id: str | None,
        arguments: dict[str, Any] | None = None,
        cancel_event: asyncio.Event | None = None,
    ) -> dict[str, Any]:
        from .policy import enforce_tool_scope

        manifest = self.get(name)
        enforce_tool_scope(manifest, project_id)
        payload = arguments or {}
        _validate_schema(payload, manifest.input_schema)
        handler_task = asyncio.create_task(self.get_handler(name)(session=session, user_id=user_id, project_id=project_id, arguments=payload))
        cancel_task: asyncio.Task[bool] | None = None
        try:
            if cancel_event is not None and manifest.cancellation_policy == "cooperative":
                if cancel_event.is_set():
                    handler_task.cancel()
                    await asyncio.gather(handler_task, return_exceptions=True)
                    raise ToolExecutionCancelled(f"tool {name} was cancelled before execution")
                cancel_task = asyncio.create_task(cancel_event.wait())
                done, _ = await asyncio.wait({handler_task, cancel_task}, timeout=manifest.timeout_seconds, return_when=asyncio.FIRST_COMPLETED)
                if cancel_task in done and not handler_task.done():
                    handler_task.cancel()
                    await asyncio.gather(handler_task, return_exceptions=True)
                    raise ToolExecutionCancelled(f"tool {name} was cancelled")
                if not done:
                    handler_task.cancel()
                    await asyncio.gather(handler_task, return_exceptions=True)
                    raise ToolExecutionTimeout(f"tool {name} exceeded {manifest.timeout_seconds}s timeout")
            else:
                try:
                    await asyncio.wait_for(asyncio.shield(handler_task), timeout=manifest.timeout_seconds)
                except asyncio.TimeoutError as exc:
                    handler_task.cancel()
                    await asyncio.gather(handler_task, return_exceptions=True)
                    raise ToolExecutionTimeout(f"tool {name} exceeded {manifest.timeout_seconds}s timeout") from exc
            result = await handler_task
        finally:
            if cancel_task is not None:
                cancel_task.cancel()
                await asyncio.gather(cancel_task, return_exceptions=True)
        _validate_schema(result, manifest.output_schema, output=True)
        return result

    def __contains__(self, name: str) -> bool:
        return name in self._tools


class RunBoundToolRegistry:
    """Expose only the live handlers that match one immutable Run snapshot."""

    def __init__(
        self,
        registry: AgentToolRegistry,
        *,
        allowed_names: Iterable[str],
        handler_identities: Mapping[str, str] | None = None,
    ) -> None:
        self._registry = registry
        self._allowed_names = frozenset(str(name).strip() for name in allowed_names if str(name).strip())
        self._handler_identities = {
            str(name).strip(): str(identity).strip()
            for name, identity in (handler_identities or {}).items()
            if str(name).strip() and str(identity).strip()
        }

    @classmethod
    def from_context(cls, registry: AgentToolRegistry, context: Mapping[str, Any]) -> "RunBoundToolRegistry":
        resolution = context.get("capability_resolution") if isinstance(context, Mapping) else None
        resolution_tools = resolution.get("tools") if isinstance(resolution, Mapping) else None
        release = context.get("catalog_release") if isinstance(context, Mapping) else None
        release_tools = release.get("tools") if isinstance(release, Mapping) else None
        release_tools = release_tools if isinstance(release_tools, list) else []
        release_identities = {
            str(item.get("name") or "").strip(): str(item.get("handler_identity") or "").strip()
            for item in release_tools
            if isinstance(item, Mapping) and str(item.get("name") or "").strip()
        }
        if isinstance(resolution_tools, list):
            allowed = [
                str(item.get("name") or "").strip()
                for item in resolution_tools
                if isinstance(item, Mapping) and str(item.get("name") or "").strip()
            ]
        else:
            allowed = list(release_identities)
        return cls(registry, allowed_names=allowed, handler_identities=release_identities)

    def _manifest(self, name: str) -> ToolManifest:
        normalized = str(name or "").strip()
        if normalized not in self._allowed_names:
            raise ToolContractViolation(f"tool {normalized or '<empty>'} is outside the Run capability snapshot")
        manifest = self._registry.get(normalized)
        expected = self._handler_identities.get(normalized)
        if expected and self._registry.get_handler_identity(normalized) != expected:
            raise ToolContractViolation(f"tool {normalized} handler identity differs from the Run capability snapshot")
        return manifest

    def assert_compatible(self) -> None:
        for name in sorted(self._allowed_names):
            self._manifest(name)

    def get(self, name: str) -> ToolManifest:
        return self._manifest(name)

    def list_tools(self) -> list[ToolManifest]:
        self.assert_compatible()
        return [self._registry.get(name) for name in sorted(self._allowed_names)]

    def validate_planned_input(self, name: str, arguments: dict[str, Any] | None = None) -> None:
        self._manifest(name)
        self._registry.validate_planned_input(name, arguments)

    async def execute(
        self,
        name: str,
        *,
        session,
        user_id: int,
        project_id: str | None,
        arguments: dict[str, Any] | None = None,
        cancel_event: asyncio.Event | None = None,
    ) -> dict[str, Any]:
        self._manifest(name)
        return await self._registry.execute(
            name,
            session=session,
            user_id=user_id,
            project_id=project_id,
            arguments=arguments,
            cancel_event=cancel_event,
        )


def bind_run_tool_registry(registry: AgentToolRegistry, context: Mapping[str, Any]) -> AgentToolRegistry | RunBoundToolRegistry:
    if not isinstance(context, Mapping) or not isinstance(context.get("capability_resolution"), Mapping):
        return registry
    bound = RunBoundToolRegistry.from_context(registry, context)
    bound.assert_compatible()
    return bound


def build_tool_manifest(
    name: str,
    description: str,
    risk_level: AgentRiskLevel,
    *,
    project_scoped: bool = True,
    supports_stream: bool = False,
    input_schema: dict[str, Any] | None = None,
    timeout_seconds: int | None = None,
    context_bindings: tuple[ToolContextBinding, ...] = (),
) -> ToolManifest:
    return ToolManifest(
        name=name,
        description=description,
        risk_level=risk_level,
        requires_confirmation=requires_confirmation(risk_level),
        project_scoped=project_scoped,
        supports_stream=supports_stream,
        input_schema=input_schema or {"type": "object", "additionalProperties": False},
        output_schema={"type": "object"},
        idempotency_key=f"agent:{name}",
        manifest_version="1.0",
        timeout_seconds=timeout_seconds or (30 if risk_level in {AgentRiskLevel.READ, AgentRiskLevel.SUGGEST} else 120),
        cancellation_policy="cooperative",
        idempotency_policy="safe_read" if risk_level in {AgentRiskLevel.READ, AgentRiskLevel.SUGGEST} else "required",
        audit_event_type="agent_tool_call",
        context_bindings=context_bindings,
    )


from .tool_adapters import (
    execute_quality_finding_inspect,
    execute_quality_inspect,
    execute_quality_retest,
    execute_quality_rewrite_instructions,
    execute_style_inspect,
    execute_chapter_generate_candidate,
    execute_chapter_rewrite_candidate,
    execute_chapter_version_accept,
)


from .providers.project_read import PROVIDER_PATH as _PROJECT_READ_PROVIDER_PATH
from .providers.memory_read import PROVIDER_PATH as _MEMORY_READ_PROVIDER_PATH
from .providers.foreshadowing_read import PROVIDER_PATH as _FORESHADOWING_READ_PROVIDER_PATH
from .providers.structure_read import PROVIDER_PATH as _STRUCTURE_READ_PROVIDER_PATH
from .provider_catalog import PROVIDER_MANIFESTS


DEFAULT_TOOL_REGISTRY = AgentToolRegistry()
DEFAULT_TOOL_PROVIDER_HEALTH: list[dict[str, Any]] = []
_DEFAULT_TOOL_REGISTRY_GENERATION = 1
_CONFIGURED_PROVIDER_SIGNATURE: tuple[bool, tuple[str, ...], int, str] | None = None


def _load_builtin_provider(provider_id: str, provider_path: str) -> tuple[str, ...]:
    tools = load_tool_provider(DEFAULT_TOOL_REGISTRY, provider_path)
    manifest = PROVIDER_MANIFESTS[provider_id]
    DEFAULT_TOOL_PROVIDER_HEALTH.append({
        "provider_id": manifest.provider_id,
        "path": provider_path,
        "status": "loaded",
        "source": "builtin",
        "tools": list(tools),
        "provider_version": manifest.provider_version,
        "api_version": manifest.api_version,
        "capability_tags": list(manifest.capability_tags),
        "dependencies": list(manifest.dependencies),
    })
    return tools


_load_builtin_provider("project-read", _PROJECT_READ_PROVIDER_PATH)
_load_builtin_provider("memory-read", _MEMORY_READ_PROVIDER_PATH)
_load_builtin_provider("foreshadowing-read", _FORESHADOWING_READ_PROVIDER_PATH)
_load_builtin_provider("structure-read", _STRUCTURE_READ_PROVIDER_PATH)
for _definition, _handler in (
    (build_tool_manifest("quality.finding.inspect", "读取作者选中的关系化质量发现摘要，不返回证据正文或候选正文。", AgentRiskLevel.READ, input_schema={"type": "object", "required": ["quality_finding_refs"], "properties": {"quality_finding_refs": {"type": "array"}}, "additionalProperties": False}, context_bindings=(ToolContextBinding(source="selected_quality_finding_refs", argument_name="quality_finding_refs", required=True),)), execute_quality_finding_inspect),
    (build_tool_manifest("quality.inspect", "分析项目质量指标并返回建议。", AgentRiskLevel.SUGGEST), execute_quality_inspect),
    (build_tool_manifest("quality.retest", "重新运行指定章节版本的结构质量门，不写入正文。", AgentRiskLevel.SUGGEST, input_schema={"type": "object", "required": ["chapter_number", "version_id"], "properties": {"chapter_number": {"type": "integer"}, "version_id": {"type": "integer"}}, "additionalProperties": False}, context_bindings=(ToolContextBinding(source="selected_chapter_number", argument_name="chapter_number", required=True), ToolContextBinding(source="selected_version_id", argument_name="version_id", required=True))), execute_quality_retest),
    (build_tool_manifest("quality.rewrite_instructions", "读取候选 Artifact 的质量阻断改写建议，不返回候选正文、不执行改写。", AgentRiskLevel.SUGGEST, input_schema={"type": "object", "required": ["artifact_id"], "properties": {"artifact_id": {"type": "string", "minLength": 1, "maxLength": 36}}, "additionalProperties": False}, context_bindings=(ToolContextBinding(source="artifact_id", argument_name="artifact_id", required=True),)), execute_quality_rewrite_instructions),
    (build_tool_manifest("style.inspect", "读取当前项目可用和已应用的文风摘要，不提取或生成文风。", AgentRiskLevel.READ), execute_style_inspect),
):
    DEFAULT_TOOL_REGISTRY.register(_definition, handler=_handler)
_write_input_schema = {
    "type": "object",
    "required": ["_approval_id", "chapter_number"],
    "properties": {
        "_approval_id": {"type": "string"}, "chapter_number": {"type": "integer"}, "source_version_id": {"type": "integer"},
        "goal": {"type": "string"}, "instruction": {"type": "string"}, "source_text": {"type": "string"},
        "target_word_count": {"type": "integer"}, "min_word_count": {"type": "integer"},
        "chapter_mission": {"type": "object"}, "writing_notes": {"type": "string"},
        "style": {"type": "string"}, "preset": {"type": "string"}, "segment_word_limit": {"type": "integer"},
        "generation_timeout_seconds": {"type": "integer"},
    },
    "additionalProperties": False,
}
_version_accept_input_schema = {
    "type": "object",
    "required": ["_approval_id", "artifact_id"],
    "properties": {
        "_approval_id": {"type": "string"},
        "artifact_id": {"type": "string", "minLength": 1, "maxLength": 36},
        "note": {"type": "string", "maxLength": 2000},
    },
    "additionalProperties": False,
}
for _definition, _handler in (
    (build_tool_manifest("chapter.generate", "生成章节候选，审批后写入 artifact，不直接覆盖正文。", AgentRiskLevel.WRITE, supports_stream=True, input_schema=_write_input_schema, timeout_seconds=300, context_bindings=(ToolContextBinding(source="selected_chapter_number", argument_name="chapter_number", required=True),)), execute_chapter_generate_candidate),
    (build_tool_manifest("chapter.rewrite", "生成章节改写候选，审批后写入 artifact，不直接覆盖正文。", AgentRiskLevel.WRITE, supports_stream=True, input_schema=_write_input_schema, timeout_seconds=300, context_bindings=(ToolContextBinding(source="selected_chapter_number", argument_name="chapter_number", required=True), ToolContextBinding(source="selected_version_id", argument_name="source_version_id"))), execute_chapter_rewrite_candidate),
    (build_tool_manifest("chapter.version.accept", "接受已通过质量门的章节候选并创建新版本，旧版本保留。", AgentRiskLevel.WRITE, input_schema=_version_accept_input_schema, timeout_seconds=120, context_bindings=(ToolContextBinding(source="artifact_id", argument_name="artifact_id", required=True),)), execute_chapter_version_accept),
):
    DEFAULT_TOOL_REGISTRY.register(_definition, handler=_handler)
# Destructive project deletion is intentionally not advertised until its
# confirmation, archival, rollback, and handler contract are implemented.


def initialize_configured_tool_providers(*, enabled: bool, provider_ids: Iterable[str], max_count: int = 16, startup_policy: str = "fail_closed") -> tuple[dict[str, Any], ...]:
    """Install deployment-selected reviewed Providers while retaining registry identity."""
    from .provider_runtime import ProviderConfigurationError, load_configured_tool_providers

    global _CONFIGURED_PROVIDER_SIGNATURE
    signature = (bool(enabled), tuple(str(item).strip() for item in provider_ids), int(max_count), str(startup_policy))
    if _CONFIGURED_PROVIDER_SIGNATURE is not None:
        if _CONFIGURED_PROVIDER_SIGNATURE != signature:
            raise ProviderConfigurationError("运行中的默认 Agent Tool Registry 不允许热切换 Provider 配置")
        return tuple(item for item in DEFAULT_TOOL_PROVIDER_HEALTH if item.get("source") == "configured")
    health = load_configured_tool_providers(
        DEFAULT_TOOL_REGISTRY,
        enabled=enabled,
        provider_ids=signature[1],
        max_count=max_count,
        startup_policy=startup_policy,
    )
    serialized = tuple(item.to_dict() for item in health)
    DEFAULT_TOOL_PROVIDER_HEALTH.extend(serialized)
    _CONFIGURED_PROVIDER_SIGNATURE = signature
    global _DEFAULT_TOOL_REGISTRY_GENERATION
    if serialized:
        _DEFAULT_TOOL_REGISTRY_GENERATION += 1
    return serialized


def get_default_tool_provider_health() -> tuple[dict[str, Any], ...]:
    """Return sanitized Provider load state for the Agent control plane."""
    return tuple({**item, "tools": list(item.get("tools", []))} for item in DEFAULT_TOOL_PROVIDER_HEALTH)


def get_default_tool_catalog() -> dict[str, Any]:
    """Return executable tools with safe source metadata for planners and UI."""
    provider_by_tool: dict[str, dict[str, str]] = {}
    for provider in get_default_tool_provider_health():
        if provider.get("status") != "loaded":
            continue
        provider_id = str(provider.get("provider_id") or "").strip()
        source = str(provider.get("source") or "").strip()
        if not provider_id or source not in {"builtin", "configured"}:
            continue
        provider_version = str(provider.get("provider_version") or "").strip()
        for tool_name in provider.get("tools", []):
            name = str(tool_name or "").strip()
            if name:
                provider_by_tool[name] = {
                    "provider_id": provider_id,
                    "provider_version": provider_version,
                    "source": source,
                }
    tools: list[dict[str, Any]] = []
    for tool in DEFAULT_TOOL_REGISTRY.list_tools():
        source_metadata = provider_by_tool.get(tool.name)
        tools.append({
            **tool.model_dump(),
            "provider_id": source_metadata["provider_id"] if source_metadata else None,
            "provider_version": source_metadata["provider_version"] or None if source_metadata else None,
            "source": source_metadata["source"] if source_metadata else "legacy",
        })
    return {
        "generation": _DEFAULT_TOOL_REGISTRY_GENERATION,
        "tools": tools,
        "count": len(tools),
    }


def get_default_tool_registry_snapshot() -> dict[str, Any]:
    """Return a sanitized, immutable-at-call-time capability snapshot for a Run."""
    catalog = get_default_tool_catalog()
    return {
        "generation": catalog["generation"],
        "providers": list(get_default_tool_provider_health()),
        "tools": [
            {
                "name": tool.name,
                "risk_level": tool.risk_level.value,
                "manifest_version": tool.manifest_version,
                "supports_stream": tool.supports_stream,
                "provider_id": item["provider_id"],
                "provider_version": item["provider_version"],
                "source": item["source"],
                "handler_identity": DEFAULT_TOOL_REGISTRY.get_handler_identity(tool.name),
            }
            for tool, item in zip(DEFAULT_TOOL_REGISTRY.list_tools(), catalog["tools"], strict=True)
        ],
    }
