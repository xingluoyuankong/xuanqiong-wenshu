"""Stable metadata contract for reviewed Agent capability Providers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderManifest:
    provider_id: str
    provider_version: str
    api_version: str = "agent-tool-provider/v1"
    capability_tags: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.provider_id.strip() or not self.provider_version.strip():
            raise ValueError("Provider manifest requires provider_id and provider_version")
        if self.api_version != "agent-tool-provider/v1":
            raise ValueError("unsupported Agent Tool Provider API version")
