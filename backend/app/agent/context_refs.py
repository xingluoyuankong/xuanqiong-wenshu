"""Resolve user-selected Agent context references into manifest-bound tool arguments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import BlueprintCharacter, Chapter, ChapterVersion, CharacterNode, Faction, Foreshadowing
from ..models.agent import AgentArtifactRef, AgentRun
from ..models.agent_quality import QualityFinding, QualityResult
from ..models.research import ResearchArtifact
from ..services.novel_service import NovelService
from .policy import ProjectScopeViolation
from .schemas import AgentContextRef, ToolManifest


class ContextRefValidationError(ValueError):
    """The submitted ContextRef set is malformed, conflicting, or unavailable."""


def _ref_key(ref: AgentContextRef) -> tuple[str, str, int | None, int | None, str | None, int | None, str | None, str]:
    return (
        ref.kind,
        ref.project_id,
        ref.chapter_number,
        ref.version_id,
        ref.artifact_id,
        ref.entity_id,
        ref.finding_id,
        ref.role,
    )


@dataclass(frozen=True)
class ResolvedAgentContext:
    project_id: str | None
    refs: tuple[AgentContextRef, ...]
    selected_chapter_number: int | None = None
    selected_version_id: int | None = None
    comparison_chapter_number: int | None = None
    from_version_id: int | None = None
    to_version_id: int | None = None
    artifact_id: str | None = None
    entity_refs: tuple[AgentContextRef, ...] = ()
    quality_finding_refs: tuple[AgentContextRef, ...] = ()

    def canonical_refs(self) -> list[dict[str, Any]]:
        return [ref.model_dump(mode="json", exclude_none=True) for ref in self.refs]

    def planner_context(self) -> dict[str, Any]:
        """A tiny, prose-free capability summary for the Planner prompt."""
        return {
            "selected_project": bool(self.project_id),
            "selected_chapter_number": self.selected_chapter_number,
            "selected_version_id": self.selected_version_id,
            "comparison_chapter_number": self.comparison_chapter_number,
            "has_comparison_versions": self.from_version_id is not None and self.to_version_id is not None,
            "has_artifact": self.artifact_id is not None,
            "entity_context_count": len(self.entity_refs),
            "entity_context_kinds": sorted({ref.kind for ref in self.entity_refs}),
            "quality_finding_context_count": len(self.quality_finding_refs),
        }

    def context_values(self) -> dict[str, Any]:
        return {
            "selected_chapter_number": self.selected_chapter_number,
            "selected_version_id": self.selected_version_id,
            "comparison_chapter_number": self.comparison_chapter_number,
            "from_version_id": self.from_version_id,
            "to_version_id": self.to_version_id,
            "artifact_id": self.artifact_id,
            "selected_entity_refs": [
                {"kind": ref.kind, "entity_id": ref.entity_id}
                for ref in self.entity_refs
            ],
            "selected_quality_finding_refs": [
                {"finding_id": ref.finding_id}
                for ref in self.quality_finding_refs
            ],
        }

    def project_arguments(self, tool: ToolManifest, explicit: dict[str, Any] | None = None) -> dict[str, Any]:
        """Project only manifest-declared fields; reject every conflicting override."""
        arguments = dict(explicit or {})
        values = self.context_values()
        for binding in tool.context_bindings:
            value = values.get(binding.source)
            if value is None:
                if binding.required and binding.argument_name not in arguments:
                    raise ContextRefValidationError(
                        f"tool {tool.name} requires context binding {binding.source} for {binding.argument_name}"
                    )
                continue
            if binding.argument_name in arguments and arguments[binding.argument_name] != value:
                raise ContextRefValidationError(
                    f"tool {tool.name} argument {binding.argument_name} conflicts with selected context"
                )
            arguments[binding.argument_name] = value
        return arguments


def project_plan_arguments(
    *,
    tools: Sequence[ToolManifest],
    context: ResolvedAgentContext,
    legacy_arguments: dict[str, Any] | None,
    tool_arguments: dict[str, dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    """Build one independent argument object per planned tool.

    Legacy arguments retain single-tool compatibility only. Context-derived
    fields are injected exclusively when the manifest declares the binding.
    """
    legacy = dict(legacy_arguments or {})
    explicit_by_tool = {str(name): dict(value) for name, value in (tool_arguments or {}).items()}
    tool_names = [tool.name for tool in tools]
    unknown = sorted(set(explicit_by_tool) - set(tool_names))
    if unknown:
        raise ContextRefValidationError(f"tool_arguments contains tools outside the final plan: {', '.join(unknown)}")
    if legacy and explicit_by_tool:
        raise ContextRefValidationError("legacy arguments cannot be combined with tool_arguments")
    if legacy and len(tool_names) != 1:
        raise ContextRefValidationError("legacy arguments are only supported for a single-tool plan; use tool_arguments")

    projected: dict[str, dict[str, Any]] = {}
    for tool in tools:
        explicit = legacy if legacy else explicit_by_tool.get(tool.name, {})
        projected[tool.name] = context.project_arguments(tool, explicit)
    return projected


async def _assert_chapter(
    session: AsyncSession,
    *,
    project_id: str,
    chapter_number: int,
) -> None:
    chapter_id = await session.scalar(
        select(Chapter.id).where(
            Chapter.project_id == project_id,
            Chapter.chapter_number == chapter_number,
        )
    )
    if chapter_id is None:
        raise ContextRefValidationError("chapter context reference is unavailable for this project")


async def _assert_version(
    session: AsyncSession,
    *,
    project_id: str,
    chapter_number: int,
    version_id: int,
) -> None:
    candidate = await session.scalar(
        select(ChapterVersion.id)
        .join(Chapter, Chapter.id == ChapterVersion.chapter_id)
        .where(
            ChapterVersion.id == version_id,
            Chapter.project_id == project_id,
            Chapter.chapter_number == chapter_number,
        )
    )
    if candidate is None:
        raise ProjectScopeViolation("chapter version context reference is unavailable for this project chapter")


async def _assert_artifact(
    session: AsyncSession,
    *,
    project_id: str,
    user_id: int,
    artifact_id: str,
) -> None:
    candidate = await session.scalar(
        select(AgentArtifactRef.id).where(
            AgentArtifactRef.id == artifact_id,
            AgentArtifactRef.user_id == user_id,
            AgentArtifactRef.project_id == project_id,
        )
    )
    if candidate is None:
        raise ProjectScopeViolation("artifact context reference is unavailable for this project")


async def _assert_quality_finding(
    session: AsyncSession,
    *,
    project_id: str,
    user_id: int,
    finding_id: str,
) -> None:
    candidate = await session.scalar(
        select(QualityFinding.id)
        .join(QualityResult, QualityResult.id == QualityFinding.quality_result_id)
        .join(AgentArtifactRef, AgentArtifactRef.id == QualityResult.artifact_ref_id)
        .join(AgentRun, AgentRun.id == QualityResult.run_id)
        .where(
            QualityFinding.finding_id == finding_id,
            QualityResult.run_id == AgentArtifactRef.run_id,
            QualityResult.user_id == user_id,
            QualityResult.project_id == project_id,
            AgentArtifactRef.user_id == user_id,
            AgentArtifactRef.project_id == project_id,
            AgentRun.user_id == user_id,
            AgentRun.project_id == project_id,
        )
    )
    if candidate is None:
        raise ProjectScopeViolation("quality finding context reference is unavailable for this project")


async def _assert_entity(
    session: AsyncSession,
    *,
    project_id: str,
    user_id: int,
    kind: str,
    entity_id: int,
) -> None:
    model_by_kind = {
        "character": BlueprintCharacter,
        "faction": Faction,
        "foreshadowing": Foreshadowing,
        "knowledge_node": CharacterNode,
        "research_artifact": ResearchArtifact,
    }
    model = model_by_kind.get(kind)
    if model is None:
        raise ContextRefValidationError(f"unsupported entity context kind: {kind}")
    filters = [model.id == entity_id, model.project_id == project_id]
    if model is ResearchArtifact:
        filters.append(ResearchArtifact.user_id == user_id)
    candidate = await session.scalar(select(model.id).where(*filters))
    if candidate is None:
        raise ProjectScopeViolation(f"{kind} context reference is unavailable for this project")


async def resolve_agent_context_refs(
    *,
    session: AsyncSession,
    user_id: int,
    session_project_id: str | None,
    refs: Sequence[AgentContextRef] | Iterable[AgentContextRef],
) -> ResolvedAgentContext:
    """Normalize, de-duplicate, and verify ContextRefs before planning."""
    requested = tuple(refs)
    if not requested:
        return ResolvedAgentContext(project_id=session_project_id, refs=())
    if not session_project_id:
        raise ProjectScopeViolation("context references require a project-scoped Agent session")

    await NovelService(session).ensure_project_owner(session_project_id, user_id)
    canonical: list[AgentContextRef] = []
    seen: set[tuple[str, str, int | None, int | None, str | None, int | None, str | None, str]] = set()
    selected_chapter: int | None = None
    selected_version: int | None = None
    comparison_chapter: int | None = None
    from_version: int | None = None
    to_version: int | None = None
    artifact_id: str | None = None
    entity_refs: list[AgentContextRef] = []
    quality_finding_refs: list[AgentContextRef] = []

    for ref in requested:
        if ref.project_id != session_project_id:
            raise ProjectScopeViolation("context reference project_id does not match the Agent session project")
        key = _ref_key(ref)
        if key in seen:
            continue
        seen.add(key)

        if ref.kind == "project":
            canonical.append(ref)
            continue
        if ref.kind == "chapter":
            assert ref.chapter_number is not None
            await _assert_chapter(session, project_id=session_project_id, chapter_number=ref.chapter_number)
            if selected_chapter is not None and selected_chapter != ref.chapter_number:
                raise ContextRefValidationError("selected chapter context references conflict")
            selected_chapter = ref.chapter_number
        elif ref.kind == "chapter_version":
            assert ref.chapter_number is not None and ref.version_id is not None
            await _assert_version(
                session,
                project_id=session_project_id,
                chapter_number=ref.chapter_number,
                version_id=ref.version_id,
            )
            if ref.role == "selected":
                if selected_chapter is not None and selected_chapter != ref.chapter_number:
                    raise ContextRefValidationError("selected chapter and selected version context references conflict")
                if selected_version is not None and selected_version != ref.version_id:
                    raise ContextRefValidationError("selected version context references conflict")
                selected_chapter = ref.chapter_number
                selected_version = ref.version_id
            elif ref.role == "from":
                if from_version is not None and from_version != ref.version_id:
                    raise ContextRefValidationError("comparison from-version context references conflict")
                if comparison_chapter is not None and comparison_chapter != ref.chapter_number:
                    raise ContextRefValidationError("comparison versions must belong to the same chapter")
                comparison_chapter = ref.chapter_number
                from_version = ref.version_id
            elif ref.role == "to":
                if to_version is not None and to_version != ref.version_id:
                    raise ContextRefValidationError("comparison to-version context references conflict")
                if comparison_chapter is not None and comparison_chapter != ref.chapter_number:
                    raise ContextRefValidationError("comparison versions must belong to the same chapter")
                comparison_chapter = ref.chapter_number
                to_version = ref.version_id
        elif ref.kind == "artifact":
            assert ref.artifact_id is not None
            await _assert_artifact(
                session,
                project_id=session_project_id,
                user_id=user_id,
                artifact_id=ref.artifact_id,
            )
            if artifact_id is not None and artifact_id != ref.artifact_id:
                raise ContextRefValidationError("artifact context references conflict")
            artifact_id = ref.artifact_id
        elif ref.kind == "quality_finding":
            assert ref.finding_id is not None
            await _assert_quality_finding(
                session,
                project_id=session_project_id,
                user_id=user_id,
                finding_id=ref.finding_id,
            )
            quality_finding_refs.append(ref)
        else:
            assert ref.entity_id is not None
            await _assert_entity(
                session,
                project_id=session_project_id,
                user_id=user_id,
                kind=ref.kind,
                entity_id=ref.entity_id,
            )
            entity_refs.append(ref)
        canonical.append(ref)

    if (from_version is None) != (to_version is None):
        raise ContextRefValidationError("comparison context requires both from and to versions")
    if from_version is not None and from_version == to_version:
        raise ContextRefValidationError("comparison context versions must be different")

    if not any(ref.kind == "project" for ref in canonical):
        canonical.insert(0, AgentContextRef(kind="project", project_id=session_project_id))

    return ResolvedAgentContext(
        project_id=session_project_id,
        refs=tuple(canonical),
        selected_chapter_number=selected_chapter,
        selected_version_id=selected_version,
        comparison_chapter_number=comparison_chapter,
        from_version_id=from_version,
        to_version_id=to_version,
        artifact_id=artifact_id,
        entity_refs=tuple(entity_refs),
        quality_finding_refs=tuple(quality_finding_refs),
    )
