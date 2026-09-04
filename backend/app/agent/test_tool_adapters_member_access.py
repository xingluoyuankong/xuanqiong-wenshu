from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Awaitable, Callable

import pytest
from fastapi import HTTPException

from app.agent import tool_adapters as adapters
from app.models import Chapter, ChapterVersion, NovelProject, ProjectMember, User
from app.models.project_member import ProjectMemberRole
from app.models.research import ResearchArtifact


ReadTool = Callable[..., Awaitable[dict[str, Any]]]


async def _seed_project(task_session) -> SimpleNamespace:
    owner = User(id=7101, username="tool-owner-7101", hashed_password="x", is_active=True)
    viewer = User(id=7102, username="tool-viewer-7102", hashed_password="x", is_active=True)
    editor = User(id=7103, username="tool-editor-7103", hashed_password="x", is_active=True)
    outsider = User(id=7104, username="tool-outsider-7104", hashed_password="x", is_active=True)
    project = NovelProject(id="tool-adapter-member-project", user_id=owner.id, title="共享只读工具项目")
    task_session.add_all([
        owner,
        viewer,
        editor,
        outsider,
        project,
        ProjectMember(project_id=project.id, user_id=owner.id, role=ProjectMemberRole.owner.value),
        ProjectMember(project_id=project.id, user_id=viewer.id, role=ProjectMemberRole.viewer.value),
        ProjectMember(project_id=project.id, user_id=editor.id, role=ProjectMemberRole.editor.value),
    ])
    await task_session.flush()

    chapter = Chapter(project_id=project.id, chapter_number=1, status="successful", word_count=9)
    task_session.add(chapter)
    await task_session.flush()
    first = ChapterVersion(
        chapter_id=chapter.id,
        version_label="v1",
        provider="fixture",
        content="旧行\n保留行",
        content_hash="first-hash",
        status="selected",
    )
    second = ChapterVersion(
        chapter_id=chapter.id,
        version_label="v2",
        provider="fixture",
        content="新行\n保留行",
        content_hash="second-hash",
        status="candidate",
    )
    task_session.add_all([first, second])
    await task_session.flush()
    chapter.selected_version_id = second.id
    task_session.add(ResearchArtifact(
        run_id="tool-adapter-research-run",
        project_id=project.id,
        user_id=owner.id,
        scope="global",
        status="completed",
        trigger="manual",
        summary="Owner 生成的共享研究摘要",
        sources=[{"title": "fixture"}],
        category_payload={"categories": {"world": ["fixture"]}},
    ))
    await task_session.commit()
    return SimpleNamespace(
        owner=owner,
        viewer=viewer,
        editor=editor,
        outsider=outsider,
        project=project,
        chapter=chapter,
        first=first,
        second=second,
    )


def _install_owner_guarded_read_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Model the owner-only NovelService contract retained by legacy serializers.

    The adapter must first verify membership, then invoke the legacy serializer
    through the project's canonical owner so Viewer/Editor reads retain the same
    schema without bypassing project access.
    """

    async def project_schema(service, project_id: str, supplied_user_id: int):
        project = await service.session.get(NovelProject, project_id)
        if project is None or project.user_id != supplied_user_id:
            raise HTTPException(status_code=403, detail="legacy owner serializer rejected reader")
        return {"id": project.id, "title": project.title, "serialized_for": supplied_user_id}

    async def section_data(service, project_id: str, supplied_user_id: int, section):
        project = await service.session.get(NovelProject, project_id)
        if project is None or project.user_id != supplied_user_id:
            raise HTTPException(status_code=403, detail="legacy owner section serializer rejected reader")
        return {
            "section": str(getattr(section, "value", section)),
            "data": {"chapters": [{"chapter_number": 1, "summary": "共享章节"}]},
            "serialized_for": supplied_user_id,
        }

    class StubKnowledgeGraphService:
        def __init__(self, session):
            self.session = session

        async def get_project_graph(self, project_id: str):
            return {"project_id": project_id, "nodes": [], "edges": []}

    class StubStyleRAGService:
        def __init__(self, session, llm_service=None):
            self.session = session

        async def list_style_profiles(self, user_id: int):
            return []

        async def get_style_for_project(self, project_id: str):
            return None

    class StubForeshadowingService:
        def __init__(self, session):
            self.session = session

        async def get_foreshadowings(self, project_id: str, **kwargs):
            return [], 0

    monkeypatch.setattr(adapters.NovelService, "get_project_schema", project_schema)
    monkeypatch.setattr(adapters.NovelService, "get_section_data", section_data)
    monkeypatch.setattr(adapters, "KnowledgeGraphService", StubKnowledgeGraphService)
    monkeypatch.setattr(adapters, "StyleRAGService", StubStyleRAGService)
    monkeypatch.setattr(adapters, "ForeshadowingService", StubForeshadowingService)


READ_TOOL_NAMES = (
    "project.context",
    "chapter.inspect",
    "chapter.version.list",
    "chapter.version.diff",
    "outline.inspect",
    "statistics.project",
    "knowledge.inspect",
    "style.inspect",
    "research.inspect",
    "foreshadowing.inspect",
)


async def _read_tool(
    tool_name: str,
    session,
    user_id: int,
    fixture: SimpleNamespace,
) -> dict[str, Any]:
    project_id = fixture.project.id
    common = {"session": session, "user_id": user_id, "project_id": project_id}
    if tool_name == "project.context":
        return await adapters.execute_project_context(**common)
    if tool_name == "chapter.inspect":
        return await adapters.execute_chapter_inspect(**common, arguments={"chapter_number": 1})
    if tool_name == "chapter.version.list":
        return await adapters.execute_chapter_version_list(**common, arguments={"chapter_number": 1})
    if tool_name == "chapter.version.diff":
        return await adapters.execute_chapter_version_diff(
            **common,
            arguments={
                "chapter_number": 1,
                "from_version_id": fixture.first.id,
                "to_version_id": fixture.second.id,
            },
        )
    if tool_name == "outline.inspect":
        return await adapters.execute_outline_inspect(**common)
    if tool_name == "statistics.project":
        return await adapters.execute_statistics_project(**common)
    if tool_name == "knowledge.inspect":
        return await adapters.execute_knowledge_inspect(**common)
    if tool_name == "style.inspect":
        return await adapters.execute_style_inspect(**common)
    if tool_name == "research.inspect":
        return await adapters.execute_research_inspect(**common)
    if tool_name == "foreshadowing.inspect":
        return await adapters.execute_foreshadowing_inspect(**common)
    raise AssertionError(f"unknown fixture tool: {tool_name}")


async def _read_all_tools(session, user_id: int, fixture: SimpleNamespace) -> dict[str, dict[str, Any]]:
    return {
        tool_name: await _read_tool(tool_name, session, user_id, fixture)
        for tool_name in READ_TOOL_NAMES
    }



@pytest.mark.asyncio
@pytest.mark.parametrize("member_kind", ["viewer", "editor"])
async def test_project_members_can_read_all_shared_agent_tools(task_session, monkeypatch, member_kind: str):
    fixture = await _seed_project(task_session)
    _install_owner_guarded_read_stubs(monkeypatch)

    result = await _read_all_tools(task_session, getattr(fixture, member_kind).id, fixture)

    assert result["project.context"]["project"]["serialized_for"] == fixture.owner.id
    assert result["chapter.inspect"]["result"]["serialized_for"] == fixture.owner.id
    assert result["outline.inspect"]["result"]["serialized_for"] == fixture.owner.id
    assert result["chapter.version.list"]["count"] == 2
    assert result["chapter.version.diff"]["summary"]["modified"] == 1
    assert result["statistics.project"]["chapters"]["chapter_count"] == 1
    assert result["knowledge.inspect"]["result"]["project_id"] == fixture.project.id
    assert result["style.inspect"]["project_id"] == fixture.project.id
    assert result["research.inspect"]["count"] == 1
    assert result["research.inspect"]["artifacts"][0]["summary"] == "Owner 生成的共享研究摘要"
    assert result["foreshadowing.inspect"]["result"]["total"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", READ_TOOL_NAMES)
async def test_nonmember_is_rejected_before_each_shared_agent_read_tool(task_session, monkeypatch, tool_name: str):
    fixture = await _seed_project(task_session)
    _install_owner_guarded_read_stubs(monkeypatch)

    with pytest.raises(HTTPException) as denied:
        await _read_tool(tool_name, task_session, fixture.outsider.id, fixture)
    assert denied.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool",
    [
        adapters.execute_project_context,
        adapters.execute_chapter_inspect,
        adapters.execute_chapter_version_list,
        adapters.execute_chapter_version_diff,
        adapters.execute_outline_inspect,
        adapters.execute_statistics_project,
        adapters.execute_knowledge_inspect,
        adapters.execute_style_inspect,
        adapters.execute_research_inspect,
        adapters.execute_foreshadowing_inspect,
    ],
)
async def test_shared_read_tools_do_not_fall_back_to_projectless_data(task_session, tool: ReadTool):
    with pytest.raises(ValueError, match="project-scoped tool requires project_id"):
        await tool(session=task_session, user_id=7101, project_id=None, arguments={})
