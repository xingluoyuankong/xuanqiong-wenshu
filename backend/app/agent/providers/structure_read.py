"""Project-scoped chapter structure and version-diff capabilities."""

from __future__ import annotations

from ..provider_catalog import PROVIDER_MANIFESTS
from ..registry import AgentToolRegistry, build_tool_manifest
from ..schemas import AgentRiskLevel, ToolContextBinding
from ..tool_adapters import execute_chapter_inspect, execute_chapter_version_diff

PROVIDER_PATH = "app.agent.providers.structure_read:register_agent_tools"
PROVIDER_MANIFEST = PROVIDER_MANIFESTS["structure-read"]


def register_agent_tools(registry: AgentToolRegistry) -> None:
    """Register bounded chapter reads; adapters enforce project/version ownership."""
    for definition, handler in (
        (
            build_tool_manifest(
                "chapter.inspect",
                "读取项目章节与版本概览。",
                AgentRiskLevel.READ,
                input_schema={
                    "type": "object",
                    "properties": {"chapter_number": {"type": "integer"}},
                    "additionalProperties": False,
                },
                context_bindings=(ToolContextBinding(source="selected_chapter_number", argument_name="chapter_number"),),
            ),
            execute_chapter_inspect,
        ),
        (
            build_tool_manifest(
                "chapter.version.diff",
                "比较同一章节两个版本，返回有界差异，不改变正文。",
                AgentRiskLevel.READ,
                input_schema={
                    "type": "object",
                    "required": ["chapter_number", "from_version_id", "to_version_id"],
                    "properties": {
                        "chapter_number": {"type": "integer"},
                        "from_version_id": {"type": "integer"},
                        "to_version_id": {"type": "integer"},
                        "max_lines": {"type": "integer"},
                    },
                    "additionalProperties": False,
                },
                context_bindings=(
                    ToolContextBinding(source="comparison_chapter_number", argument_name="chapter_number", required=True),
                    ToolContextBinding(source="from_version_id", argument_name="from_version_id", required=True),
                    ToolContextBinding(source="to_version_id", argument_name="to_version_id", required=True),
                ),
            ),
            execute_chapter_version_diff,
        ),
    ):
        registry.register(definition, handler=handler)
