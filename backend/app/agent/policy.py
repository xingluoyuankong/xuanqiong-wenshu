"""Explicit Agent tool boundary and confirmation policy helpers."""

from __future__ import annotations

from .schemas import AgentRiskLevel, AgentToolDefinition


class ProjectScopeViolation(ValueError):
    """A project-scoped capability lacks an exact project boundary."""


def validate_project_scope(
    requested_project_id: str | None,
    tool_project_id: str | None = None,
    *,
    project_scoped: bool = True,
) -> bool:
    """Require an exact project match for project-scoped operations."""

    if not project_scoped:
        return True
    requested = str(requested_project_id or "").strip()
    tool_project = str(tool_project_id or "").strip()
    if not requested:
        raise ProjectScopeViolation("project-scoped tool requires project_id")
    if tool_project and tool_project != requested:
        raise ProjectScopeViolation("tool project scope does not match request")
    return True


def requires_confirmation(risk_level: AgentRiskLevel) -> bool:
    return risk_level in {AgentRiskLevel.WRITE, AgentRiskLevel.DESTRUCTIVE}


def enforce_tool_scope(tool: AgentToolDefinition, project_id: str | None) -> None:
    validate_project_scope(project_id, project_scoped=tool.project_scoped)

