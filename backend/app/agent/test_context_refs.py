from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agent.context_refs import (
    ContextRefValidationError,
    ResolvedAgentContext,
    project_plan_arguments,
    resolve_agent_context_refs,
)
from app.agent.policy import ProjectScopeViolation
from app.agent.registry import AgentToolRegistry, DEFAULT_TOOL_REGISTRY
from app.agent.schemas import AgentContextRef, AgentMessageCreateRequest, AgentRiskLevel, ToolContextBinding, ToolManifest
from app.models import BlueprintCharacter, Chapter, ChapterVersion, CharacterNode, Faction, Foreshadowing, NovelProject, User
from app.models.research import ResearchArtifact
from app.models.agent import AgentArtifactRef, AgentRun, AgentSession
from app.models.agent_quality import QualityFinding, QualityResult
from app.agent.tool_adapters import execute_entity_inspect, execute_quality_finding_inspect


async def _seed_context_project(task_session, *, owner_id: int, project_id: str, chapter_number: int = 7):
    owner = User(
        id=owner_id,
        username=f"context-owner-{owner_id}",
        email=f"context-owner-{owner_id}@example.com",
        hashed_password="x",
        is_active=True,
    )
    project = NovelProject(id=project_id, user_id=owner.id, title="Context project")
    chapter = Chapter(project_id=project.id, chapter_number=chapter_number, status="generated")
    task_session.add_all([owner, project, chapter])
    await task_session.flush()
    first = ChapterVersion(chapter_id=chapter.id, content="old", status="candidate")
    second = ChapterVersion(chapter_id=chapter.id, content="new", status="accepted")
    task_session.add_all([first, second])
    await task_session.flush()
    chapter.selected_version_id = second.id
    await task_session.commit()
    return owner, project, chapter, first, second


def test_context_ref_schema_is_identifier_only_and_strict():
    payload = AgentMessageCreateRequest(
        content="检查当前章节",
        context_refs=[
            {"kind": "project", "project_id": "project-a"},
            {
                "kind": "chapter_version",
                "project_id": "project-a",
                "chapter_number": 7,
                "version_id": 12,
            },
        ],
    )
    assert [ref.kind for ref in payload.context_refs] == ["project", "chapter_version"]
    with pytest.raises(ValidationError):
        AgentMessageCreateRequest(
            content="bad",
            context_refs=[
                {
                    "kind": "chapter",
                    "project_id": "project-a",
                    "chapter_number": 7,
                    "content": "MUST_NOT_BE_ACCEPTED",
                }
            ],
        )


@pytest.mark.asyncio
async def test_context_refs_resolve_owned_version_and_project_independent_arguments(task_session):
    owner, project, chapter, first, second = await _seed_context_project(
        task_session,
        owner_id=3101,
        project_id="context-projection-project",
    )
    resolved = await resolve_agent_context_refs(
        session=task_session,
        user_id=owner.id,
        session_project_id=project.id,
        refs=[
            AgentContextRef(kind="project", project_id=project.id),
            AgentContextRef(
                kind="chapter_version",
                project_id=project.id,
                chapter_number=chapter.chapter_number,
                version_id=second.id,
            ),
        ],
    )
    assert resolved.selected_chapter_number == chapter.chapter_number
    assert resolved.selected_version_id == second.id
    assert resolved.planner_context()["has_comparison_versions"] is False
    assert all("content" not in ref for ref in resolved.canonical_refs())

    tools = [
        DEFAULT_TOOL_REGISTRY.get("project.context"),
        DEFAULT_TOOL_REGISTRY.get("chapter.inspect"),
        DEFAULT_TOOL_REGISTRY.get("quality.retest"),
    ]
    projected = project_plan_arguments(
        tools=tools,
        context=resolved,
        legacy_arguments={},
        tool_arguments={},
    )
    assert projected == {
        "project.context": {},
        "chapter.inspect": {"chapter_number": chapter.chapter_number},
        "quality.retest": {
            "chapter_number": chapter.chapter_number,
            "version_id": second.id,
        },
    }
    for tool in tools:
        DEFAULT_TOOL_REGISTRY.validate_planned_input(tool.name, projected[tool.name])


@pytest.mark.asyncio
async def test_context_refs_reject_cross_project_version_before_planning(task_session):
    owner, project, chapter, first, second = await _seed_context_project(
        task_session,
        owner_id=3102,
        project_id="context-owned-project",
    )
    _, foreign_project, foreign_chapter, _, foreign_version = await _seed_context_project(
        task_session,
        owner_id=3103,
        project_id="context-foreign-project",
    )
    with pytest.raises(ProjectScopeViolation):
        await resolve_agent_context_refs(
            session=task_session,
            user_id=owner.id,
            session_project_id=project.id,
            refs=[
                AgentContextRef(kind="project", project_id=project.id),
                AgentContextRef(
                    kind="chapter_version",
                    project_id=project.id,
                    chapter_number=chapter.chapter_number,
                    version_id=foreign_version.id,
                ),
            ],
        )


@pytest.mark.asyncio
async def test_context_refs_reject_mismatched_chapter_version(task_session):
    owner, project, chapter, first, second = await _seed_context_project(
        task_session,
        owner_id=3104,
        project_id="context-mismatch-project",
    )
    other_chapter = Chapter(project_id=project.id, chapter_number=8, status="generated")
    task_session.add(other_chapter)
    await task_session.flush()
    other_version = ChapterVersion(chapter_id=other_chapter.id, content="other", status="candidate")
    task_session.add(other_version)
    await task_session.commit()
    with pytest.raises(ProjectScopeViolation):
        await resolve_agent_context_refs(
            session=task_session,
            user_id=owner.id,
            session_project_id=project.id,
            refs=[
                AgentContextRef(kind="project", project_id=project.id),
                AgentContextRef(
                    kind="chapter_version",
                    project_id=project.id,
                    chapter_number=chapter.chapter_number,
                    version_id=other_version.id,
                ),
            ],
        )


def test_context_projector_rejects_legacy_argument_broadcast_and_conflicts():
    context = ResolvedAgentContext(
        project_id="project-a",
        refs=(AgentContextRef(kind="project", project_id="project-a"),),
        selected_chapter_number=7,
    )
    with pytest.raises(ContextRefValidationError, match="single-tool"):
        project_plan_arguments(
            tools=[
                DEFAULT_TOOL_REGISTRY.get("project.context"),
                DEFAULT_TOOL_REGISTRY.get("chapter.inspect"),
            ],
            context=context,
            legacy_arguments={"chapter_number": 7},
            tool_arguments={},
        )
    with pytest.raises(ContextRefValidationError, match="conflicts"):
        project_plan_arguments(
            tools=[DEFAULT_TOOL_REGISTRY.get("chapter.inspect")],
            context=context,
            legacy_arguments={},
            tool_arguments={"chapter.inspect": {"chapter_number": 9}},
        )


def test_context_projector_requires_comparison_bindings_and_does_not_inject_project_id():
    context = ResolvedAgentContext(
        project_id="project-a",
        refs=(AgentContextRef(kind="project", project_id="project-a"),),
        selected_chapter_number=7,
    )
    with pytest.raises(ContextRefValidationError, match="comparison_chapter_number"):
        project_plan_arguments(
            tools=[DEFAULT_TOOL_REGISTRY.get("chapter.version.diff")],
            context=context,
            legacy_arguments={},
            tool_arguments={},
        )
    projected = project_plan_arguments(
        tools=[DEFAULT_TOOL_REGISTRY.get("chapter.inspect")],
        context=context,
        legacy_arguments={},
        tool_arguments={},
    )
    assert projected["chapter.inspect"] == {"chapter_number": 7}
    assert "project_id" not in projected["chapter.inspect"]


def test_registry_rejects_context_binding_missing_from_input_schema():
    invalid = ToolManifest(
        name="context.invalid",
        description="invalid context binding",
        risk_level=AgentRiskLevel.READ,
        requires_confirmation=False,
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        output_schema={"type": "object"},
        context_bindings=(
            ToolContextBinding(source="selected_chapter_number", argument_name="chapter_number"),
        ),
    )
    with pytest.raises(ValueError, match="context binding"):
        AgentToolRegistry([invalid])


@pytest.mark.asyncio
async def test_entity_context_refs_are_owned_project_scoped_and_manifest_bound(task_session):
    owner, project, chapter, _, _ = await _seed_context_project(
        task_session,
        owner_id=3110,
        project_id="entity-context-project",
    )
    character = BlueprintCharacter(project_id=project.id, name="沈星河", identity="主角")
    faction = Faction(project_id=project.id, name="玄穹司", faction_type="组织")
    foreshadowing = Foreshadowing(
        project_id=project.id,
        chapter_id=chapter.id,
        chapter_number=chapter.chapter_number,
        content="失落的星图",
        type="hint",
        name="星图",
    )
    node = CharacterNode(project_id=project.id, name="沈星河", role_type="主角")
    research = ResearchArtifact(
        project_id=project.id,
        user_id=owner.id,
        run_id="research-context-run",
        scope="global",
        status="completed",
        trigger="manual",
        summary="研究摘要",
    )
    task_session.add_all([character, faction, foreshadowing, node, research])
    await task_session.commit()
    await task_session.refresh(character)
    await task_session.refresh(faction)
    await task_session.refresh(foreshadowing)
    await task_session.refresh(node)
    await task_session.refresh(research)

    refs = [
        AgentContextRef(kind="character", project_id=project.id, entity_id=character.id),
        AgentContextRef(kind="faction", project_id=project.id, entity_id=faction.id),
        AgentContextRef(kind="foreshadowing", project_id=project.id, entity_id=foreshadowing.id),
        AgentContextRef(kind="knowledge_node", project_id=project.id, entity_id=node.id),
        AgentContextRef(kind="research_artifact", project_id=project.id, entity_id=research.id),
    ]
    resolved = await resolve_agent_context_refs(
        session=task_session,
        user_id=owner.id,
        session_project_id=project.id,
        refs=refs,
    )

    assert resolved.planner_context()["entity_context_count"] == 5
    assert resolved.planner_context()["entity_context_kinds"] == [
        "character", "faction", "foreshadowing", "knowledge_node", "research_artifact",
    ]
    entity_tool = DEFAULT_TOOL_REGISTRY.get("entity.inspect")
    projected = project_plan_arguments(
        tools=[entity_tool], context=resolved, legacy_arguments={}, tool_arguments={}
    )
    assert projected["entity.inspect"]["entity_refs"] == [
        {"kind": ref.kind, "entity_id": ref.entity_id} for ref in refs
    ]
    result = await execute_entity_inspect(
        session=task_session,
        user_id=owner.id,
        project_id=project.id,
        arguments=projected["entity.inspect"],
    )
    assert result["tool_name"] == "entity.inspect"
    assert [(item["kind"], item["entity_id"]) for item in result["entities"]] == [
        (ref.kind, ref.entity_id) for ref in refs
    ]
    assert "沈星河" in result["entities"][0]["summary"]["name"]


@pytest.mark.asyncio
async def test_quality_finding_context_ref_is_relationally_scoped_and_manifest_bound(task_session):
    owner, project, _, _, _ = await _seed_context_project(
        task_session, owner_id=3115, project_id="quality-finding-context-project"
    )
    agent_session = AgentSession(user_id=owner.id, project_id=project.id, title="quality finding context")
    task_session.add(agent_session)
    await task_session.flush()
    run = AgentRun(
        session_id=agent_session.id,
        user_id=owner.id,
        project_id=project.id,
        correlation_id="quality-finding-correlation",
        transaction_id="quality-finding-transaction",
        status="completed",
    )
    task_session.add(run)
    await task_session.flush()
    artifact = AgentArtifactRef(
        id="quality-finding-artifact",
        run_id=run.id,
        correlation_id=run.correlation_id,
        transaction_id=run.transaction_id,
        user_id=owner.id,
        project_id=project.id,
        kind="chapter_candidate",
        uri="agent-artifact://quality-finding-context",
        sha256="q" * 64,
        metadata_json={"status": "candidate"},
    )
    result = QualityResult(
        result_id="quality-finding-result",
        run_id=run.id,
        artifact_ref_id=artifact.id,
        correlation_id=run.correlation_id,
        transaction_id=run.transaction_id,
        user_id=owner.id,
        project_id=project.id,
        assessor_id="test",
        status="completed",
    )
    finding = QualityFinding(
        finding_id="quality-finding-context",
        code="dialogue_static",
        category="dialogue",
        severity="blocker",
        status="open",
        message="对话没有推进状态。",
        fingerprint="f" * 64,
        evidence_json={"excerpt": "DO_NOT_EXPOSE"},
        remediation_json={"instruction": "DO_NOT_EXPOSE"},
    )
    result.findings.append(finding)
    task_session.add_all([artifact, result])
    await task_session.commit()

    ref = AgentContextRef(kind="quality_finding", project_id=project.id, finding_id=finding.finding_id)
    resolved = await resolve_agent_context_refs(
        session=task_session,
        user_id=owner.id,
        session_project_id=project.id,
        refs=[ref],
    )

    assert resolved.planner_context()["quality_finding_context_count"] == 1
    tool = DEFAULT_TOOL_REGISTRY.get("quality.finding.inspect")
    projected = project_plan_arguments(
        tools=[tool], context=resolved, legacy_arguments={}, tool_arguments={}
    )
    assert projected["quality.finding.inspect"] == {
        "quality_finding_refs": [{"finding_id": finding.finding_id}]
    }
    inspected = await execute_quality_finding_inspect(
        session=task_session,
        user_id=owner.id,
        project_id=project.id,
        arguments=projected["quality.finding.inspect"],
    )
    assert inspected == {
        "tool_name": "quality.finding.inspect",
        "findings": [{
            "finding_id": finding.finding_id,
            "code": "dialogue_static",
            "category": "dialogue",
            "severity": "blocker",
            "status": "open",
            "message": "对话没有推进状态。",
        }],
    }
    assert "DO_NOT_EXPOSE" not in str(inspected)

    mismatched_run = AgentRun(
        session_id=agent_session.id,
        user_id=owner.id,
        project_id=project.id,
        correlation_id="quality-finding-mismatched-artifact-correlation",
        transaction_id="quality-finding-mismatched-artifact-transaction",
        status="completed",
    )
    task_session.add(mismatched_run)
    await task_session.flush()
    mismatched_artifact = AgentArtifactRef(
        id="quality-finding-mismatched-artifact",
        run_id=mismatched_run.id,
        correlation_id=mismatched_run.correlation_id,
        transaction_id=mismatched_run.transaction_id,
        user_id=owner.id,
        project_id=project.id,
        kind="chapter_candidate",
        uri="agent-artifact://quality-finding-mismatched-context",
        sha256="m" * 64,
        metadata_json={"status": "candidate"},
    )
    mismatched_result = QualityResult(
        result_id="quality-finding-mismatched-result",
        run_id=run.id,
        artifact_ref_id=mismatched_artifact.id,
        correlation_id=run.correlation_id,
        transaction_id=run.transaction_id,
        user_id=owner.id,
        project_id=project.id,
        assessor_id="test",
        status="completed",
    )
    mismatched_result.findings.append(QualityFinding(
        finding_id="quality-finding-mismatched-run",
        code="mismatched_run",
        severity="blocker",
        status="open",
        message="This finding must not bridge two runs.",
        fingerprint="m" * 64,
    ))
    task_session.add_all([mismatched_artifact, mismatched_result])
    await task_session.commit()

    mismatched_ref = AgentContextRef(
        kind="quality_finding",
        project_id=project.id,
        finding_id="quality-finding-mismatched-run",
    )
    with pytest.raises(ProjectScopeViolation):
        await resolve_agent_context_refs(
            session=task_session,
            user_id=owner.id,
            session_project_id=project.id,
            refs=[mismatched_ref],
        )
    with pytest.raises(ValueError, match="quality finding is unavailable for this project"):
        await execute_quality_finding_inspect(
            session=task_session,
            user_id=owner.id,
            project_id=project.id,
            arguments={"quality_finding_refs": [{"finding_id": "quality-finding-mismatched-run"}]},
        )

    with pytest.raises(ValidationError):
        AgentContextRef(
            kind="quality_finding",
            project_id=project.id,
            finding_id=finding.finding_id,
            content="DO_NOT_EXPOSE",
        )

    _, foreign_project, _, _, _ = await _seed_context_project(
        task_session, owner_id=3116, project_id="quality-finding-foreign-project"
    )
    foreign_agent_session = AgentSession(user_id=3116, project_id=foreign_project.id, title="foreign quality")
    task_session.add(foreign_agent_session)
    await task_session.flush()
    foreign_run = AgentRun(
        session_id=foreign_agent_session.id,
        user_id=3116,
        project_id=foreign_project.id,
        correlation_id="foreign-quality-correlation",
        transaction_id="foreign-quality-transaction",
        status="completed",
    )
    task_session.add(foreign_run)
    await task_session.flush()
    foreign_artifact = AgentArtifactRef(
        id="quality-finding-foreign-artifact",
        run_id=foreign_run.id,
        correlation_id=foreign_run.correlation_id,
        transaction_id=foreign_run.transaction_id,
        user_id=3116,
        project_id=foreign_project.id,
        kind="chapter_candidate",
        uri="agent-artifact://foreign-quality-finding",
        sha256="z" * 64,
        metadata_json={"status": "candidate"},
    )
    foreign_result = QualityResult(
        result_id="quality-finding-foreign-result",
        run_id=foreign_run.id,
        artifact_ref_id=foreign_artifact.id,
        correlation_id=foreign_run.correlation_id,
        transaction_id=foreign_run.transaction_id,
        user_id=3116,
        project_id=foreign_project.id,
        assessor_id="test",
        status="completed",
    )
    foreign_result.findings.append(QualityFinding(
        finding_id="quality-finding-foreign",
        code="foreign",
        severity="warning",
        status="open",
        message="foreign",
        fingerprint="x" * 64,
    ))
    task_session.add_all([foreign_artifact, foreign_result])
    await task_session.commit()

    with pytest.raises(ProjectScopeViolation):
        await resolve_agent_context_refs(
            session=task_session,
            user_id=owner.id,
            session_project_id=project.id,
            refs=[AgentContextRef(kind="quality_finding", project_id=project.id, finding_id="quality-finding-foreign")],
        )


@pytest.mark.asyncio
async def test_entity_context_ref_rejects_cross_project_and_raw_content(task_session):
    owner, project, _, _, _ = await _seed_context_project(
        task_session, owner_id=3111, project_id="entity-owner-project"
    )
    _, foreign_project, _, _, _ = await _seed_context_project(
        task_session, owner_id=3112, project_id="entity-foreign-project"
    )
    foreign = Faction(project_id=foreign_project.id, name="外部势力")
    task_session.add(foreign)
    await task_session.commit()
    await task_session.refresh(foreign)

    with pytest.raises(ProjectScopeViolation):
        await resolve_agent_context_refs(
            session=task_session,
            user_id=owner.id,
            session_project_id=project.id,
            refs=[AgentContextRef(kind="faction", project_id=project.id, entity_id=foreign.id)],
        )
    with pytest.raises(ValidationError):
        AgentMessageCreateRequest(
            content="bad",
            context_refs=[{
                "kind": "character", "project_id": project.id, "entity_id": 1,
                "content": "MUST_NOT_BE_ACCEPTED",
            }],
        )
