from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.agent import tool_adapters as adapters
from app.models import AgentArtifactRef, Chapter, ChapterVersion, NovelProject, ProjectMember, User
from app.models.project_member import ProjectMemberRole
from app.services.agent_runtime import AgentRuntimeService


async def _seed_agent_access_fixture(task_session) -> SimpleNamespace:
    owner = User(id=78201, username="agent-sweep-owner", email="agent-sweep-owner@example.com", hashed_password="x", is_active=True)
    editor = User(id=78202, username="agent-sweep-editor", email="agent-sweep-editor@example.com", hashed_password="x", is_active=True)
    viewer = User(id=78203, username="agent-sweep-viewer", email="agent-sweep-viewer@example.com", hashed_password="x", is_active=True)
    admin = User(id=78204, username="agent-sweep-admin", email="agent-sweep-admin@example.com", hashed_password="x", is_active=True, is_admin=True)
    outsider = User(id=78205, username="agent-sweep-outsider", email="agent-sweep-outsider@example.com", hashed_password="x", is_active=True)
    project = NovelProject(id="agent-member-tool-sweep-project", user_id=owner.id, title="Agent 成员工具权限")
    task_session.add_all([
        owner,
        editor,
        viewer,
        admin,
        outsider,
        project,
        ProjectMember(project_id=project.id, user_id=owner.id, role=ProjectMemberRole.owner.value),
        ProjectMember(project_id=project.id, user_id=editor.id, role=ProjectMemberRole.editor.value),
        ProjectMember(project_id=project.id, user_id=viewer.id, role=ProjectMemberRole.viewer.value),
    ])
    await task_session.flush()

    chapter = Chapter(project_id=project.id, chapter_number=1, status="successful", word_count=12)
    task_session.add(chapter)
    await task_session.flush()
    version = ChapterVersion(
        chapter_id=chapter.id,
        version_label="v1",
        provider="fixture",
        content="章节正文用于质量复测。",
        content_hash="agent-sweep-version-hash",
        status="candidate",
    )
    task_session.add(version)
    await task_session.flush()

    runtime = AgentRuntimeService(task_session)
    owner_session = await runtime.create_session(user_id=owner.id, project_id=project.id)
    editor_session = await runtime.create_session(user_id=editor.id, project_id=project.id)
    owner_run = await runtime.create_run(
        session_id=owner_session.id,
        user_id=owner.id,
        project_id=project.id,
        context={
            "response_provider_attempts": {
                "provider_attempts": [
                    {"status": "failed", "error_category": "OWNER_PRIVATE_ERROR"},
                    {"status": "succeeded", "output_digest": "a" * 64},
                ],
                "selected_provider_attempt": 2,
            },
        },
    )
    editor_run = await runtime.create_run(
        session_id=editor_session.id,
        user_id=editor.id,
        project_id=project.id,
        context={
            "response_provider_attempts": {
                "provider_attempts": [
                    {"status": "succeeded", "output_digest": "b" * 64},
                ],
                "selected_provider_attempt": 1,
            },
        },
    )
    artifact = AgentArtifactRef(
        id="agent-sweep-artifact",
        run_id=owner_run.id,
        correlation_id=owner_run.correlation_id,
        transaction_id=owner_run.transaction_id,
        user_id=owner.id,
        project_id=project.id,
        kind="chapter_candidate",
        uri="file://agent-sweep-artifact",
        sha256="c" * 64,
        metadata_json={"chapter_number": 1, "source_version_id": version.id},
    )
    task_session.add(artifact)
    await task_session.commit()
    return SimpleNamespace(
        owner=owner,
        editor=editor,
        viewer=viewer,
        admin=admin,
        outsider=outsider,
        project=project,
        chapter=chapter,
        version=version,
        owner_run=owner_run,
        editor_run=editor_run,
        artifact=artifact,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("member_kind", ["owner", "editor", "viewer", "admin"])
async def test_project_provider_usage_summary_is_shared_by_project_members(task_session, member_kind: str):
    fixture = await _seed_agent_access_fixture(task_session)

    from app.agent.execution_facts import AgentExecutionFactService

    summary = await AgentExecutionFactService(task_session).project_provider_usage_summary(
        project_id=fixture.project.id,
        user_id=getattr(fixture, member_kind).id,
    )

    assert summary["project_id"] == fixture.project.id
    assert summary["run_count"] == 2
    assert {item["run_id"] for item in summary["runs"]} == {fixture.owner_run.id, fixture.editor_run.id}
    assert summary["attempt_count"] == 3
    assert "OWNER_PRIVATE_ERROR" in str(summary)
    assert "output_digest" not in str(summary)


@pytest.mark.asyncio
async def test_project_provider_usage_summary_rejects_nonmember_without_project_facts(task_session):
    fixture = await _seed_agent_access_fixture(task_session)

    from app.agent.execution_facts import AgentExecutionFactNotFound, AgentExecutionFactService

    with pytest.raises(AgentExecutionFactNotFound) as denied:
        await AgentExecutionFactService(task_session).project_provider_usage_summary(
            project_id=fixture.project.id,
            user_id=fixture.outsider.id,
        )
    assert "OWNER_PRIVATE_ERROR" not in str(denied.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("member_kind", ["owner", "editor", "viewer", "admin"])
async def test_quality_retest_uses_project_read_access(task_session, member_kind: str):
    fixture = await _seed_agent_access_fixture(task_session)

    result = await adapters.execute_quality_retest(
        session=task_session,
        user_id=getattr(fixture, member_kind).id,
        project_id=fixture.project.id,
        arguments={"chapter_number": 1, "version_id": fixture.version.id},
    )

    assert result["project_id"] == fixture.project.id
    assert result["version_id"] == fixture.version.id
    assert result["quality_status"] in {"passed", "blocked"}


@pytest.mark.asyncio
async def test_quality_retest_rejects_nonmember_before_version_lookup(task_session):
    fixture = await _seed_agent_access_fixture(task_session)

    with pytest.raises(HTTPException) as denied:
        await adapters.execute_quality_retest(
            session=task_session,
            user_id=fixture.outsider.id,
            project_id=fixture.project.id,
            arguments={"chapter_number": 1, "version_id": fixture.version.id},
        )
    assert denied.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("member_kind", ["owner", "editor", "viewer", "admin"])
async def test_quality_rewrite_instructions_reads_shared_artifact(task_session, monkeypatch, member_kind: str):
    fixture = await _seed_agent_access_fixture(task_session)
    seen_user_ids: list[int] = []

    async def fake_list_artifact_rewrite_instructions(*, artifact_id, user_id, session):
        seen_user_ids.append(user_id)
        assert artifact_id == fixture.artifact.id
        return [{
            "code": "shared_blocker",
            "severity": "blocker",
            "message": "共享质量问题",
            "snippet": "PRIVATE_CANDIDATE_PROSE",
            "start_char": 0,
            "end_char": 4,
            "anchor_status": "located",
        }]

    from app.agent import write_executor

    monkeypatch.setattr(write_executor, "list_artifact_rewrite_instructions", fake_list_artifact_rewrite_instructions)
    result = await adapters.execute_quality_rewrite_instructions(
        session=task_session,
        user_id=getattr(fixture, member_kind).id,
        project_id=fixture.project.id,
        arguments={"artifact_id": fixture.artifact.id},
    )

    assert seen_user_ids == [getattr(fixture, member_kind).id]
    assert result["artifact_id"] == fixture.artifact.id
    assert result["instruction_count"] == 1
    assert "PRIVATE_CANDIDATE_PROSE" not in str(result)


@pytest.mark.asyncio
async def test_quality_rewrite_instructions_rejects_nonmember_without_artifact_disclosure(task_session, monkeypatch):
    fixture = await _seed_agent_access_fixture(task_session)

    async def fail_if_called(**kwargs):
        raise AssertionError("artifact rewrite reader must not run for a non-member")

    from app.agent import write_executor

    monkeypatch.setattr(write_executor, "list_artifact_rewrite_instructions", fail_if_called)
    with pytest.raises(HTTPException) as denied:
        await adapters.execute_quality_rewrite_instructions(
            session=task_session,
            user_id=fixture.outsider.id,
            project_id=fixture.project.id,
            arguments={"artifact_id": fixture.artifact.id},
        )
    assert denied.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("member_kind", ["editor", "viewer", "admin"])
async def test_quality_inspect_and_entity_context_use_project_membership(task_session, monkeypatch, member_kind: str):
    fixture = await _seed_agent_access_fixture(task_session)

    class OwnerSerializerNovelService:
        def __init__(self, session):
            self.session = session

        async def get_section_data(self, project_id, supplied_user_id, section):
            project = await self.session.get(NovelProject, project_id)
            if project is None or supplied_user_id != project.user_id:
                raise HTTPException(status_code=403, detail="legacy owner serializer rejected reader")
            return {"data": {"chapters": [{"chapter_number": 1, "generation_status": "successful"}]}}

    monkeypatch.setattr(adapters, "NovelService", OwnerSerializerNovelService)
    quality = await adapters.execute_quality_inspect(
        session=task_session,
        user_id=getattr(fixture, member_kind).id,
        project_id=fixture.project.id,
        arguments={},
    )
    assert quality["result"]["chapter_count"] == 1

    from app.models.research import ResearchArtifact

    research = ResearchArtifact(
        run_id="agent-sweep-research-run",
        project_id=fixture.project.id,
        user_id=fixture.owner.id,
        scope="global",
        status="completed",
        trigger="manual",
        summary="共享研究摘要",
        sources=[],
        category_payload={},
    )
    task_session.add(research)
    await task_session.flush()
    result = await adapters.execute_entity_inspect(
        session=task_session,
        user_id=getattr(fixture, member_kind).id,
        project_id=fixture.project.id,
        arguments={"entity_refs": [{"kind": "research_artifact", "entity_id": research.id}]},
    )
    assert result["entities"][0]["entity_id"] == research.id


@pytest.mark.asyncio
async def test_project_scoped_context_tools_reject_nonmember_before_data_query(task_session):
    fixture = await _seed_agent_access_fixture(task_session)

    with pytest.raises(HTTPException) as denied:
        await adapters.execute_entity_inspect(
            session=task_session,
            user_id=fixture.outsider.id,
            project_id=fixture.project.id,
            arguments={"entity_refs": [{"kind": "research_artifact", "entity_id": 999999}]},
        )
    assert denied.value.status_code == 403

