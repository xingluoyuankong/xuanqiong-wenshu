"""Project-scoped memory and knowledge reading capabilities."""

from __future__ import annotations

from ..provider_catalog import PROVIDER_MANIFESTS
from ..registry import AgentToolRegistry, build_tool_manifest
from ..schemas import AgentRiskLevel
from ..tool_adapters import execute_knowledge_inspect

PROVIDER_PATH = "app.agent.providers.memory_read:register_agent_tools"
PROVIDER_MANIFEST = PROVIDER_MANIFESTS["memory-read"]


def register_agent_tools(registry: AgentToolRegistry) -> None:
    """Register bounded project knowledge reads; ownership is enforced by the adapter."""
    registry.register(
        build_tool_manifest(
            "knowledge.inspect",
            "读取项目知识图谱和关联信息。",
            AgentRiskLevel.READ,
        ),
        handler=execute_knowledge_inspect,
    )
