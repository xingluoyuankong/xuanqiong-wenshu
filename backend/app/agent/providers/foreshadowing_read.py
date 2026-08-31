"""Project-scoped foreshadowing reading capabilities."""

from __future__ import annotations

from ..provider_catalog import PROVIDER_MANIFESTS
from ..registry import AgentToolRegistry, build_tool_manifest
from ..schemas import AgentRiskLevel
from ..tool_adapters import execute_foreshadowing_inspect

PROVIDER_PATH = "app.agent.providers.foreshadowing_read:register_agent_tools"
PROVIDER_MANIFEST = PROVIDER_MANIFESTS["foreshadowing-read"]


def register_agent_tools(registry: AgentToolRegistry) -> None:
    """Register bounded project foreshadowing reads; no write side effects."""
    registry.register(
        build_tool_manifest(
            "foreshadowing.inspect",
            "读取项目伏笔与回收状态。",
            AgentRiskLevel.READ,
            input_schema={
                "type": "object",
                "properties": {"limit": {"type": "integer"}},
                "additionalProperties": False,
            },
        ),
        handler=execute_foreshadowing_inspect,
    )
