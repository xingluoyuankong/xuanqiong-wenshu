"""Configuration-gated loading for reviewed Agent capability providers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable, Literal, Mapping

from .provider_catalog import BUILTIN_PROVIDER_IDS, PROVIDER_CATALOG, PROVIDER_MANIFESTS
from .registry import AgentToolRegistry, ToolProviderLoadError, load_tool_provider


class ProviderConfigurationError(ValueError):
    """A deployment-selected Provider violates the reviewed catalog contract."""


@dataclass(frozen=True)
class ProviderHealth:
    provider_id: str
    path: str | None
    status: Literal["loaded", "disabled", "skipped", "failed"]
    source: Literal["builtin", "configured"]
    tools: tuple[str, ...] = ()
    failure_code: str | None = None
    provider_version: str | None = None
    api_version: str | None = None
    capability_tags: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["tools"] = list(self.tools)
        result["capability_tags"] = list(self.capability_tags)
        result["dependencies"] = list(self.dependencies)
        return result


def _normalize_provider_ids(provider_ids: Iterable[str], *, max_count: int, catalog: Mapping[str, str]) -> tuple[str, ...]:
    values = tuple(str(value).strip() for value in provider_ids)
    if any(not value for value in values):
        raise ProviderConfigurationError("Agent Tool Provider ID 不能为空")
    if len(values) > max_count:
        raise ProviderConfigurationError("Agent Tool Provider 数量超过配置上限")
    if len(set(values)) != len(values):
        raise ProviderConfigurationError("Agent Tool Provider ID 不允许重复")
    unknown = [value for value in values if value not in catalog]
    if unknown:
        raise ProviderConfigurationError("Agent Tool Provider 未在代码目录中审核")
    return values


def _clone_registry(registry: AgentToolRegistry) -> AgentToolRegistry:
    cloned = AgentToolRegistry()
    for tool, handler in registry.registrations():
        cloned.register(tool, handler=handler)
    return cloned


def _replace_registry_contents(registry: AgentToolRegistry, staged: AgentToolRegistry) -> None:
    """Commit a validated snapshot while preserving the Registry object identity."""
    # AgentToolRegistry intentionally exposes no public bulk-replace operation.  The
    # copies are prepared before either attribute is changed, so all validation and
    # Provider loading has completed before the live object is updated.
    tools = dict(staged._tools)
    handlers = dict(staged._handlers)
    registry._tools = tools
    registry._handlers = handlers


def load_configured_tool_providers(
    registry: AgentToolRegistry,
    *,
    enabled: bool,
    provider_ids: Iterable[str],
    max_count: int = 16,
    startup_policy: Literal["fail_closed", "skip_invalid"] = "fail_closed",
    catalog: Mapping[str, str] | None = None,
) -> tuple[ProviderHealth, ...]:
    """Atomically add reviewed configured Providers without replacing registry identity."""
    if max_count < 0:
        raise ProviderConfigurationError("Agent Tool Provider 上限不能为负数")
    if startup_policy not in {"fail_closed", "skip_invalid"}:
        raise ProviderConfigurationError("Agent Tool Provider 启动策略无效")
    selected_catalog = PROVIDER_CATALOG if catalog is None else catalog
    ids = _normalize_provider_ids(provider_ids, max_count=max_count, catalog=selected_catalog)
    def metadata(provider_id: str) -> dict[str, object]:
        manifest = PROVIDER_MANIFESTS.get(provider_id)
        if manifest is None:
            return {}
        return {
            "provider_version": manifest.provider_version,
            "api_version": manifest.api_version,
            "capability_tags": manifest.capability_tags,
            "dependencies": manifest.dependencies,
        }
    if not enabled:
        return tuple(
            ProviderHealth(
                provider_id=provider_id,
                path=selected_catalog[provider_id],
                status="disabled",
                source="configured",
                **metadata(provider_id),
            )
            for provider_id in ids
        )
    staged = _clone_registry(registry)
    original_names = {tool.name for tool in registry.list_tools()}
    health: list[ProviderHealth] = []
    for provider_id in ids:
        path = selected_catalog[provider_id]
        if provider_id in BUILTIN_PROVIDER_IDS:
            health.append(ProviderHealth(provider_id=provider_id, path=path, status="skipped", source="configured", **metadata(provider_id)))
            continue
        provider_staged = _clone_registry(staged)
        before_provider_names = {tool.name for tool in provider_staged.list_tools()}
        try:
            tools = tuple(load_tool_provider(provider_staged, path))
        except (ToolProviderLoadError, ValueError):
            failure = ProviderHealth(
                provider_id=provider_id,
                path=path,
                status="failed",
                source="configured",
                failure_code="provider_contract_violation",
                **metadata(provider_id),
            )
            if startup_policy == "fail_closed":
                raise ProviderConfigurationError(f"Agent Tool Provider 加载失败：{provider_id}") from None
            health.append(failure)
            continue
        duplicate_names = sorted(set(tools).intersection(before_provider_names))
        if duplicate_names:
            failure = ProviderHealth(
                provider_id=provider_id,
                path=path,
                status="failed",
                source="configured",
                failure_code="duplicate_tool_name",
                **metadata(provider_id),
            )
            if startup_policy == "fail_closed":
                raise ProviderConfigurationError(
                    "Agent Tool Provider 不得覆盖现有工具：" + ",".join(duplicate_names)
                )
            health.append(failure)
            continue
        registered_names = {tool.name for tool in provider_staged.list_tools()}
        missing_names = sorted(set(tools) - registered_names)
        if missing_names:
            failure = ProviderHealth(
                provider_id=provider_id,
                path=path,
                status="failed",
                source="configured",
                failure_code="provider_tool_listing_mismatch",
                **metadata(provider_id),
            )
            if startup_policy == "fail_closed":
                raise ProviderConfigurationError(
                    f"Agent Tool Provider 工具清单不一致：{provider_id}"
                )
            health.append(failure)
            continue
        staged = provider_staged
        health.append(ProviderHealth(provider_id=provider_id, path=path, status="loaded", source="configured", tools=tools, **metadata(provider_id)))
    staged_names = [tool.name for tool in staged.list_tools()]
    if len(staged_names) != len(set(staged_names)):
        raise ProviderConfigurationError("Agent Tool Provider 注册了重复工具")
    extra_registrations = tuple(
        (tool, handler)
        for tool, handler in staged.registrations()
        if tool.name not in original_names
    )
    candidate = _clone_registry(registry)
    try:
        for tool, handler in extra_registrations:
            candidate.register(tool, handler=handler)
    except Exception as exc:
        raise ProviderConfigurationError("Agent Tool Provider 合并失败，Registry 未完成加载") from exc
    _replace_registry_contents(registry, candidate)
    return tuple(health)
