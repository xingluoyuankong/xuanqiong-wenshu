"""Low-risk project reading capabilities for the Agent registry."""

from __future__ import annotations

from ..provider_catalog import PROVIDER_MANIFESTS
from ..registry import AgentToolRegistry, build_tool_manifest
from ..schemas import AgentRiskLevel, ToolContextBinding
from ..tool_adapters import (
    execute_chapter_version_list,
    execute_entity_inspect,
    execute_outline_inspect,
    execute_project_context,
    execute_project_list,
    execute_research_inspect,
    execute_statistics_project,
)

PROVIDER_PATH = "app.agent.providers.project_read:register_agent_tools"
PROVIDER_MANIFEST = PROVIDER_MANIFESTS["project-read"]


def register_agent_tools(registry: AgentToolRegistry) -> None:
    """Register bounded, read-only project context capabilities."""
    for definition, handler in (
        (build_tool_manifest("project.list", "列出当前用户可访问的小说项目。", AgentRiskLevel.READ, project_scoped=False), execute_project_list),
        (build_tool_manifest("project.context", "读取当前小说项目的结构化上下文。", AgentRiskLevel.READ), execute_project_context),
        (build_tool_manifest("entity.inspect", "读取用户选中的人物、势力、伏笔、知识节点或研究工件摘要。", AgentRiskLevel.READ, input_schema={"type": "object", "required": ["entity_refs"], "properties": {"entity_refs": {"type": "array"}}, "additionalProperties": False}, context_bindings=(ToolContextBinding(source="selected_entity_refs", argument_name="entity_refs", required=True),)), execute_entity_inspect),
        (build_tool_manifest("chapter.version.list", "读取章节版本的安全元数据，不返回正文。", AgentRiskLevel.READ, input_schema={"type": "object", "properties": {"chapter_number": {"type": "integer"}, "limit": {"type": "integer"}}, "additionalProperties": False}, context_bindings=(ToolContextBinding(source="selected_chapter_number", argument_name="chapter_number"),)), execute_chapter_version_list),
        (build_tool_manifest("outline.inspect", "读取项目提纲与剧情结构。", AgentRiskLevel.READ), execute_outline_inspect),
        (build_tool_manifest("research.inspect", "读取项目已归档研究摘要与状态，不启动联网研究。", AgentRiskLevel.READ, input_schema={"type": "object", "properties": {"scope": {"type": "string"}, "chapter_number": {"type": "integer"}, "limit": {"type": "integer"}}, "additionalProperties": False}, context_bindings=(ToolContextBinding(source="selected_chapter_number", argument_name="chapter_number"),)), execute_research_inspect),
        (build_tool_manifest("statistics.project", "读取项目章节、字数和质量门汇总，不读取正文。", AgentRiskLevel.READ), execute_statistics_project),
    ):
        registry.register(definition, handler=handler)
