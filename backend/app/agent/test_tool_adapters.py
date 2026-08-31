from __future__ import annotations

import asyncio
import hashlib
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from app.agent.tool_adapters import execute_read_tool
from app.agent.write_executor import _ARTIFACT_ROOT
from app.agent.registry import AgentToolRegistry, DEFAULT_TOOL_PROVIDER_HEALTH, DEFAULT_TOOL_REGISTRY, ToolContractViolation, ToolExecutionCancelled, ToolExecutionTimeout, ToolProviderLoadError, load_tool_provider
from app.agent.schemas import AgentRiskLevel, ToolManifest
from app.models import Chapter, ChapterOutline, ChapterVersion, NovelProject, User
from app.models.research import ResearchArtifact
from app.models.project_memory import ProjectMemory
from app.models.user_style_library import UserStyleLibrary
from app.services.agent_runtime import AgentRuntimeService


@pytest.mark.asyncio
async def test_project_list_adapter_uses_user_scoped_domain_service(task_session):
    owner = User(id=801, username="adapter-owner", email="adapter-owner@example.com", hashed_password="x", is_active=True)
    other = User(id=802, username="adapter-other", email="adapter-other@example.com", hashed_password="x", is_active=True)
    task_session.add_all([owner, other, NovelProject(id="adapter-owned", user_id=owner.id, title="Owned"), NovelProject(id="adapter-other", user_id=other.id, title="Other")])
    await task_session.flush()
    result = await execute_read_tool(tool_name="project.list", session=task_session, user_id=owner.id, project_id=None)
    ids = {item["id"] for item in result["projects"]}
    assert ids == {"adapter-owned"}


@pytest.mark.asyncio
async def test_project_context_adapter_rejects_foreign_project(task_session):
    owner = User(id=803, username="adapter-owner-2", email="adapter-owner-2@example.com", hashed_password="x", is_active=True)
    other = User(id=804, username="adapter-other-2", email="adapter-other-2@example.com", hashed_password="x", is_active=True)
    task_session.add_all([owner, other, NovelProject(id="adapter-owned-2", user_id=owner.id, title="Owned")])
    await task_session.flush()
    with pytest.raises(Exception):
        await execute_read_tool(tool_name="project.context", session=task_session, user_id=other.id, project_id="adapter-owned-2")


@pytest.mark.asyncio
async def test_knowledge_inspect_rejects_foreign_project(task_session):
    owner = User(id=809, username="knowledge-owner", email="knowledge-owner@example.com", hashed_password="x", is_active=True)
    other = User(id=810, username="knowledge-other", email="knowledge-other@example.com", hashed_password="x", is_active=True)
    project = NovelProject(id="knowledge-scope-project", user_id=owner.id, title="Knowledge scope")
    task_session.add_all([owner, other, project])
    await task_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await execute_read_tool(tool_name="knowledge.inspect", session=task_session, user_id=other.id, project_id=project.id)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_foreshadowing_inspect_rejects_foreign_project(task_session):
    owner = User(id=811, username="foreshadow-owner", email="foreshadow-owner@example.com", hashed_password="x", is_active=True)
    other = User(id=812, username="foreshadow-other", email="foreshadow-other@example.com", hashed_password="x", is_active=True)
    project = NovelProject(id="foreshadow-scope-project", user_id=owner.id, title="Foreshadow scope")
    task_session.add_all([owner, other, project])
    await task_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await execute_read_tool(tool_name="foreshadowing.inspect", session=task_session, user_id=other.id, project_id=project.id)
    assert exc_info.value.status_code == 403


@pytest.fixture
async def chapter_tool_sqlite_fixture(task_session):
    """固定内存 SQLite 数据集：两个章节、两个同章版本和一个跨章节版本。"""
    owner = User(id=981, username="chapter-tool-owner", email="chapter-tool-owner@example.com", hashed_password="x", is_active=True)
    other = User(id=982, username="chapter-tool-other", email="chapter-tool-other@example.com", hashed_password="x", is_active=True)
    project = NovelProject(id="chapter-tool-sqlite-fixture", user_id=owner.id, title="Chapter tool fixture")
    chapter_seven = Chapter(project_id=project.id, chapter_number=7, status="generated")
    chapter_eight = Chapter(project_id=project.id, chapter_number=8, status="generated")
    task_session.add_all([owner, other, project, chapter_seven, chapter_eight])
    await task_session.flush()

    base_version = ChapterVersion(
        chapter_id=chapter_seven.id,
        version_label="fixture-v1",
        provider="fixture",
        content="anchor\nold\nremove\ntail",
        content_hash="fixture-hash-v1",
        status="candidate",
    )
    revised_version = ChapterVersion(
        chapter_id=chapter_seven.id,
        version_label="fixture-v2",
        provider="fixture",
        content="anchor\nnew\ntail\nadd",
        content_hash="fixture-hash-v2",
        status="accepted",
    )
    cross_chapter_version = ChapterVersion(
        chapter_id=chapter_eight.id,
        version_label="fixture-v3",
        provider="fixture",
        content="other chapter",
        content_hash="fixture-hash-v3",
        status="candidate",
    )
    task_session.add_all([base_version, revised_version, cross_chapter_version])
    await task_session.flush()
    await task_session.commit()
    return SimpleNamespace(
        session=task_session,
        owner=owner,
        other=other,
        project=project,
        chapter_seven=chapter_seven,
        chapter_eight=chapter_eight,
        base_version=base_version,
        revised_version=revised_version,
        cross_chapter_version=cross_chapter_version,
    )


@pytest.mark.asyncio
async def test_chapter_inspect_fixed_sqlite_fixture_filters_owner_and_rejects_foreign_user(chapter_tool_sqlite_fixture):
    fixture = chapter_tool_sqlite_fixture
    result = await execute_read_tool(
        tool_name="chapter.inspect",
        session=fixture.session,
        user_id=fixture.owner.id,
        project_id=fixture.project.id,
        arguments={"chapter_number": 7},
    )
    assert result["tool_name"] == "chapter.inspect"
    assert [item["chapter_number"] for item in result["result"]["data"]["chapters"]] == [7]

    with pytest.raises(HTTPException) as exc_info:
        await execute_read_tool(
            tool_name="chapter.inspect",
            session=fixture.session,
            user_id=fixture.other.id,
            project_id=fixture.project.id,
            arguments={"chapter_number": 7},
        )
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_chapter_inspect_fixed_sqlite_fixture_rejects_invalid_chapter_number(chapter_tool_sqlite_fixture):
    fixture = chapter_tool_sqlite_fixture
    with pytest.raises(ToolContractViolation):
        await execute_read_tool(
            tool_name="chapter.inspect",
            session=fixture.session,
            user_id=fixture.owner.id,
            project_id=fixture.project.id,
            arguments={"chapter_number": "seven"},
        )


@pytest.mark.asyncio
async def test_chapter_version_list_returns_safe_metadata_and_respects_owner_scope(task_session):
    owner = User(id=805, username="version-owner", email="version-owner@example.com", hashed_password="x", is_active=True)
    other = User(id=806, username="version-other", email="version-other@example.com", hashed_password="x", is_active=True)
    project = NovelProject(id="version-project", user_id=owner.id, title="Versions")
    chapter = Chapter(project_id=project.id, chapter_number=1, status="generated")
    task_session.add_all([owner, other, project, chapter])
    await task_session.flush()
    first = ChapterVersion(chapter_id=chapter.id, version_label="v1", provider="test", content="正文一", content_hash="hash-1", status="candidate")
    second = ChapterVersion(chapter_id=chapter.id, version_label="v2", provider="test", content="正文二", content_hash="hash-2", status="accepted", parent_version_id=None)
    task_session.add_all([first, second])
    await task_session.flush()
    chapter.selected_version_id = second.id
    await task_session.commit()

    result = await execute_read_tool(tool_name="chapter.version.list", session=task_session, user_id=owner.id, project_id=project.id, arguments={"chapter_number": 1})
    assert result["count"] == 2
    assert {item["version_id"] for item in result["versions"]} == {first.id, second.id}
    assert [item["selected"] for item in result["versions"]].count(True) == 1
    assert all("content" not in item for item in result["versions"])
    assert all(item["word_count"] > 0 for item in result["versions"])

    foreign = await execute_read_tool(tool_name="chapter.version.list", session=task_session, user_id=other.id, project_id=project.id, arguments={})
    assert foreign["count"] == 0


@pytest.mark.asyncio
async def test_chapter_version_diff_is_bounded_and_project_scoped(task_session):
    owner = User(id=807, username="diff-owner", email="diff-owner@example.com", hashed_password="x", is_active=True)
    other = User(id=808, username="diff-other", email="diff-other@example.com", hashed_password="x", is_active=True)
    project = NovelProject(id="diff-project", user_id=owner.id, title="Diffs")
    chapter = Chapter(project_id=project.id, chapter_number=2, status="generated")
    task_session.add_all([owner, other, project, chapter])
    await task_session.flush()
    first = ChapterVersion(chapter_id=chapter.id, version_label="v1", content="第一行\n旧行\n末行", content_hash="hash-a", status="candidate")
    second = ChapterVersion(chapter_id=chapter.id, version_label="v2", content="第一行\n新行\n末行\n新增", content_hash="hash-b", status="accepted")
    task_session.add_all([first, second])
    await task_session.flush()

    result = await execute_read_tool(
        tool_name="chapter.version.diff",
        session=task_session,
        user_id=owner.id,
        project_id=project.id,
        arguments={"chapter_number": 2, "from_version_id": first.id, "to_version_id": second.id, "max_lines": 1},
    )
    assert result["from_version_id"] == first.id
    assert result["to_version_id"] == second.id
    assert result["summary"]["modified"] == 1
    assert len(result["diff_lines"]) == 1
    assert "content" not in result

    with pytest.raises(ValueError):
        await execute_read_tool(
            tool_name="chapter.version.diff", session=task_session, user_id=owner.id,
            project_id=project.id, arguments={"chapter_number": 2, "from_version_id": first.id, "to_version_id": first.id},
        )
    with pytest.raises(ValueError):
        await execute_read_tool(
            tool_name="chapter.version.diff", session=task_session, user_id=other.id,
            project_id=project.id, arguments={"chapter_number": 2, "from_version_id": first.id, "to_version_id": second.id},
        )


@pytest.mark.asyncio
async def test_chapter_version_diff_fixed_sqlite_fixture_rejects_cross_chapter_ids_and_has_bounded_summary(chapter_tool_sqlite_fixture):
    fixture = chapter_tool_sqlite_fixture
    full = await execute_read_tool(
        tool_name="chapter.version.diff",
        session=fixture.session,
        user_id=fixture.owner.id,
        project_id=fixture.project.id,
        arguments={
            "chapter_number": 7,
            "from_version_id": fixture.base_version.id,
            "to_version_id": fixture.revised_version.id,
        },
    )
    assert full["summary"] == {"added": 1, "deleted": 1, "modified": 1, "unchanged": 2}
    assert full["diff_lines"] == [
        {"line_number": 2, "original_line": "old", "patched_line": "new", "change_type": "modified"},
        {"line_number": 3, "original_line": "remove", "patched_line": None, "change_type": "deleted"},
        {"line_number": 4, "original_line": None, "patched_line": "add", "change_type": "added"},
    ]

    bounded = await execute_read_tool(
        tool_name="chapter.version.diff",
        session=fixture.session,
        user_id=fixture.owner.id,
        project_id=fixture.project.id,
        arguments={
            "chapter_number": 7,
            "from_version_id": fixture.base_version.id,
            "to_version_id": fixture.revised_version.id,
            "max_lines": 2,
        },
    )
    assert bounded["summary"] == full["summary"]
    assert bounded["diff_lines"] == full["diff_lines"][:2]
    assert len(bounded["diff_lines"]) == 2

    with pytest.raises(ValueError, match="same accessible chapter"):
        await execute_read_tool(
            tool_name="chapter.version.diff",
            session=fixture.session,
            user_id=fixture.owner.id,
            project_id=fixture.project.id,
            arguments={
                "chapter_number": 7,
                "from_version_id": fixture.base_version.id,
                "to_version_id": fixture.cross_chapter_version.id,
            },
        )


@pytest.mark.asyncio
async def test_quality_retest_is_read_only_and_project_scoped(task_session):
    owner = User(id=809, username="quality-owner", email="quality-owner@example.com", hashed_password="x", is_active=True)
    other = User(id=810, username="quality-other", email="quality-other@example.com", hashed_password="x", is_active=True)
    project = NovelProject(id="quality-tool-project", user_id=owner.id, title="Quality Tool")
    chapter = Chapter(project_id=project.id, chapter_number=3, status="successful")
    task_session.add_all([owner, other, project, chapter])
    await task_session.flush()
    version = ChapterVersion(
        chapter_id=chapter.id,
        version_label="v-quality",
        content="顾棠推开门。门后传来脚步声。她握紧刀柄。",
        content_hash="quality-hash",
        status="selected",
        metadata_={"target_word_count": 20, "min_word_count": 1},
    )
    task_session.add(version)
    await task_session.flush()
    chapter.selected_version_id = version.id
    await task_session.commit()

    result = await execute_read_tool(
        tool_name="quality.retest", session=task_session, user_id=owner.id,
        project_id=project.id, arguments={"chapter_number": 3, "version_id": version.id},
    )
    assert result["tool_name"] == "quality.retest"
    assert result["version_id"] == version.id
    assert result["content_hash"] == "quality-hash"
    assert "content" not in result
    assert "quality_gate" in result
    assert result["quality_gate"]["blocker_count"] >= 0

    refreshed = await task_session.get(ChapterVersion, version.id)
    assert refreshed is not None
    assert refreshed.metadata_ == {"target_word_count": 20, "min_word_count": 1}

    with pytest.raises(ValueError):
        await execute_read_tool(
            tool_name="quality.retest", session=task_session, user_id=other.id,
            project_id=project.id, arguments={"chapter_number": 3, "version_id": version.id},
        )


@pytest.mark.asyncio
async def test_quality_rewrite_instructions_are_project_scoped_prose_free_and_read_only(task_session):
    owner = User(id=817, username="rewrite-instruction-owner", email="rewrite-instruction-owner@example.com", hashed_password="x", is_active=True)
    other = User(id=818, username="rewrite-instruction-other", email="rewrite-instruction-other@example.com", hashed_password="x", is_active=True)
    project = NovelProject(id="rewrite-instruction-project", user_id=owner.id, title="Rewrite Instructions")
    other_project = NovelProject(id="rewrite-instruction-other-project", user_id=owner.id, title="Other Project")
    task_session.add_all([owner, other, project, other_project])
    await task_session.flush()
    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=owner.id, project_id=project.id)
    run = await runtime.create_run(session_id=agent_session.id, user_id=owner.id, project_id=project.id)
    secret_prose = "SECRET_ARTIFACT_PROSE_不得泄漏给规划器"
    storage_key = f"{uuid4()}.md"
    _ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    artifact_path = _ARTIFACT_ROOT / storage_key
    artifact_path.write_text(secret_prose, encoding="utf-8")
    artifact = await runtime.add_artifact(
        run_id=run.id,
        user_id=owner.id,
        project_id=project.id,
        kind="chapter_candidate",
        uri=f"agent-artifact://{storage_key}",
        sha256=hashlib.sha256(secret_prose.encode("utf-8")).hexdigest(),
        metadata={
            "storage_key": storage_key,
            "chapter_number": 9,
            "source_version_id": 42,
            "status": "candidate",
            "quality_gate": {
                "passed": False,
                "blockers": [{
                    "code": "dialogue_does_not_change_state",
                    "severity": "blocker",
                    "message": "对话没有改变状态",
                    "source": "story_progression_guard",
                    "snippet": secret_prose,
                }],
            },
        },
    )
    before_metadata = dict(artifact.metadata_json)
    before_file = artifact_path.read_text(encoding="utf-8")
    before_versions = list((await task_session.execute(select(ChapterVersion))).scalars().all())
    try:
        result = await execute_read_tool(
            tool_name="quality.rewrite_instructions",
            session=task_session,
            user_id=owner.id,
            project_id=project.id,
            arguments={"artifact_id": artifact.id},
        )
        assert result["tool_name"] == "quality.rewrite_instructions"
        assert result["artifact_id"] == artifact.id
        assert result["instruction_count"] == 1
        instruction = result["instructions"][0]
        assert instruction["code"] == "dialogue_does_not_change_state"
        assert instruction["anchor_status"] == "redacted"
        assert "snippet" not in instruction
        assert secret_prose not in json.dumps(result, ensure_ascii=False)
        assert "定位片段" not in instruction["instruction"]
        assert instruction["rewrite_arguments"]["source_version_id"] == 42

        refreshed = await task_session.get(type(artifact), artifact.id)
        assert refreshed is not None
        assert refreshed.metadata_json == before_metadata
        assert artifact_path.read_text(encoding="utf-8") == before_file
        assert list((await task_session.execute(select(ChapterVersion))).scalars().all()) == before_versions

        with pytest.raises(ValueError):
            await execute_read_tool(
                tool_name="quality.rewrite_instructions",
                session=task_session,
                user_id=owner.id,
                project_id=other_project.id,
                arguments={"artifact_id": artifact.id},
            )
        with pytest.raises(ValueError):
            await execute_read_tool(
                tool_name="quality.rewrite_instructions",
                session=task_session,
                user_id=other.id,
                project_id=project.id,
                arguments={"artifact_id": artifact.id},
            )
    finally:
        artifact_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_research_inspect_reads_safe_summaries_without_starting_research(task_session):
    owner = User(id=811, username="research-owner", email="research-owner@example.com", hashed_password="x", is_active=True)
    other = User(id=812, username="research-other", email="research-other@example.com", hashed_password="x", is_active=True)
    project = NovelProject(id="research-tool-project", user_id=owner.id, title="Research Tool")
    task_session.add_all([owner, other, project])
    await task_session.flush()
    artifact = ResearchArtifact(
        run_id="research-run-1",
        project_id=project.id,
        user_id=owner.id,
        scope="chapter",
        chapter_number=4,
        status="successful",
        trigger="manual",
        query_plan=[{"category": "history"}],
        sources=[{"url": "https://example.invalid/private-source"}],
        category_payload={"summary": "研究摘要", "categories": {"history": [{"insight": "安全摘要"}]}},
        summary="研究摘要",
        provider_metadata={"api_key": "must-not-return"},
        error={"code": "research_failed", "message": "sensitive detail", "retryable": True},
    )
    task_session.add(artifact)
    await task_session.commit()

    result = await execute_read_tool(
        tool_name="research.inspect", session=task_session, user_id=owner.id,
        project_id=project.id, arguments={"scope": "chapter", "chapter_number": 4},
    )
    assert result["count"] == 1
    row = result["artifacts"][0]
    assert row["artifact_id"] == artifact.id
    assert row["summary"] == "研究摘要"
    assert row["source_count"] == 1
    assert row["category_keys"] == ["history"]
    assert row["error_code"] == "research_failed"
    assert "url" not in row
    assert "api_key" not in str(result)
    assert "sensitive detail" not in str(result)

    foreign = await execute_read_tool(
        tool_name="research.inspect", session=task_session, user_id=other.id,
        project_id=project.id, arguments={},
    )
    assert foreign["count"] == 0


@pytest.mark.asyncio
async def test_style_inspect_returns_safe_profile_summary_without_mutating_library(task_session):
    owner = User(id=813, username="style-owner", email="style-owner@example.com", hashed_password="x", is_active=True)
    other = User(id=814, username="style-other", email="style-other@example.com", hashed_password="x", is_active=True)
    project = NovelProject(id="style-tool-project", user_id=owner.id, title="Style Tool")
    profile_payload = [{
        "id": "style-profile-1", "name": "冷峻悬疑", "profile_type": "external",
        "source_ids": ["source-1"], "summary": {"tone": "冷峻", "rhythm": "短促"},
        "style_feature": {"narrative_voice": {"tone": "克制"}, "rhythm_pacing": {"variation": "多变"}},
        "prompt_context": "SECRET_STYLE_PROMPT", "quality_metrics": {"coverage": 0.8},
        "extra": {"source_titles": ["私有参考书"]}, "created_at": "2026-08-26T00:00:00+00:00",
        "updated_at": "2026-08-26T00:00:00+00:00", "active": False,
    }]
    library = UserStyleLibrary(user_id=owner.id, style_sources_json=json.dumps([{"id": "source-1", "content_text": "SECRET_SOURCE_PROSE"}], ensure_ascii=False), style_profiles_json=json.dumps(profile_payload, ensure_ascii=False), global_active_profile_id=None)
    memory = ProjectMemory(project_id=project.id, version=1, extra={"applied_style_profile_id": "style-profile-1"})
    task_session.add_all([owner, other, project, library, memory])
    await task_session.commit()

    result = await execute_read_tool(tool_name="style.inspect", session=task_session, user_id=owner.id, project_id=project.id)
    assert result["profile_count"] == 1
    assert result["applied_profile_id"] == "style-profile-1"
    row = result["profiles"][0]
    assert row["applied_to_project"] is True
    assert row["summary"]["tone"] == "冷峻"
    assert set(row["feature_dimensions"]) == {"narrative_voice", "rhythm_pacing"}
    assert "prompt_context" not in row
    assert "SECRET_STYLE_PROMPT" not in str(result)
    assert "SECRET_SOURCE_PROSE" not in str(result)

    refreshed_library = await task_session.get(UserStyleLibrary, owner.id)
    refreshed_memory = (await task_session.execute(select(ProjectMemory).where(ProjectMemory.project_id == project.id))).scalar_one_or_none()
    assert refreshed_library is not None and refreshed_library.style_profiles_json == json.dumps(profile_payload, ensure_ascii=False)
    assert refreshed_memory is not None and refreshed_memory.extra == {"applied_style_profile_id": "style-profile-1"}

    with pytest.raises(Exception):
        await execute_read_tool(tool_name="style.inspect", session=task_session, user_id=other.id, project_id=project.id)


@pytest.mark.asyncio
async def test_statistics_project_aggregates_selected_versions_without_exposing_prose(task_session):
    owner = User(id=815, username="stats-owner", email="stats-owner@example.com", hashed_password="x", is_active=True)
    other = User(id=816, username="stats-other", email="stats-other@example.com", hashed_password="x", is_active=True)
    project = NovelProject(id="stats-tool-project", user_id=owner.id, title="Stats Tool", status="draft")
    chapter_one = Chapter(project_id=project.id, chapter_number=1, status="successful", word_count=1200)
    chapter_two = Chapter(project_id=project.id, chapter_number=2, status="failed", word_count=0)
    outline = ChapterOutline(project_id=project.id, chapter_number=1, title="第一章")
    task_session.add_all([owner, other, project, chapter_one, chapter_two, outline])
    await task_session.flush()
    version = ChapterVersion(
        chapter_id=chapter_one.id, content="SECRET_CHAPTER_PROSE", content_hash="stats-hash", status="selected",
        metadata_={"quality_gate": {"passed": False, "blockers": [{"code": "event_density_weak"}, {"code": "event_density_weak"}]}},
    )
    task_session.add(version)
    await task_session.flush()
    chapter_one.selected_version_id = version.id
    await task_session.commit()

    result = await execute_read_tool(tool_name="statistics.project", session=task_session, user_id=owner.id, project_id=project.id)
    assert result["project"]["title"] == "Stats Tool"
    assert result["chapters"] == {
        "chapter_count": 2,
        "outline_count": 1,
        "selected_version_count": 1,
        "total_word_count": 1200,
        "status_counts": {"failed": 1, "successful": 1},
        "latest_chapter_number": 2,
    }
    assert result["quality"]["blocked_count"] == 1
    assert result["quality"]["top_blocker_counts"] == {"event_density_weak": 2}
    assert "SECRET_CHAPTER_PROSE" not in str(result)

    with pytest.raises(ValueError):
        await execute_read_tool(tool_name="statistics.project", session=task_session, user_id=other.id, project_id=project.id)


def test_default_registry_has_handlers_for_all_read_tools():
    for name in {"project.list", "project.context", "entity.inspect", "chapter.inspect", "chapter.version.list", "chapter.version.diff", "outline.inspect", "quality.inspect", "quality.retest", "research.inspect", "style.inspect", "statistics.project", "knowledge.inspect", "foreshadowing.inspect"}:
        assert callable(DEFAULT_TOOL_REGISTRY.get_handler(name))


@pytest.mark.asyncio
async def test_registry_manifest_rejects_unknown_input_fields(task_session):
    with pytest.raises(ToolContractViolation):
        await DEFAULT_TOOL_REGISTRY.execute("chapter.inspect", session=task_session, user_id=801, project_id="p", arguments={"unknown": True})


@pytest.mark.asyncio
async def test_registry_manifest_rejects_handler_output_that_breaks_schema(task_session):
    async def bad_handler(**kwargs):
        return ["not-an-object"]

    registry = AgentToolRegistry()
    registry.register(
        ToolManifest(
            name="test.output",
            description="测试输出契约",
            risk_level=AgentRiskLevel.READ,
            requires_confirmation=False,
            project_scoped=False,
            input_schema={"type": "object", "additionalProperties": False},
            output_schema={"type": "object"},
        ),
        handler=bad_handler,
    )
    with pytest.raises(ToolContractViolation):
        await registry.execute("test.output", session=task_session, user_id=801, project_id=None)


def test_default_registry_exposes_only_executable_tools():
    for manifest in DEFAULT_TOOL_REGISTRY.list_tools():
        assert callable(DEFAULT_TOOL_REGISTRY.get_handler(manifest.name))


def test_builtin_project_read_provider_preserves_registered_tools_and_handlers():
    health = [item for item in DEFAULT_TOOL_PROVIDER_HEALTH if item["path"] == "app.agent.providers.project_read:register_agent_tools"]
    assert health == [{
        "provider_id": "project-read",
        "path": "app.agent.providers.project_read:register_agent_tools",
        "status": "loaded",
        "source": "builtin",
        "tools": ["project.list", "project.context", "entity.inspect", "chapter.version.list", "outline.inspect", "research.inspect", "statistics.project"],
        "provider_version": "1.0.0",
        "api_version": "agent-tool-provider/v1",
        "capability_tags": ["project-context", "outline", "research-summary", "statistics"],
        "dependencies": ["NovelService"],
    }]
    for name in health[0]["tools"]:
        assert callable(DEFAULT_TOOL_REGISTRY.get_handler(name))


def _test_manifest(name: str, *, timeout_seconds: int = 1) -> ToolManifest:
    return ToolManifest(
        name=name,
        description="测试执行约束",
        risk_level=AgentRiskLevel.READ,
        requires_confirmation=False,
        project_scoped=False,
        timeout_seconds=timeout_seconds,
        input_schema={"type": "object", "additionalProperties": False},
        output_schema={"type": "object"},
    )


@pytest.mark.asyncio
async def test_registry_manifest_enforces_timeout(task_session):
    async def slow_handler(**kwargs):
        await asyncio.sleep(1.05)
        return {}

    registry = AgentToolRegistry()
    registry.register(_test_manifest("test.timeout"), handler=slow_handler)
    with pytest.raises(ToolExecutionTimeout):
        await registry.execute("test.timeout", session=task_session, user_id=801, project_id=None)


@pytest.mark.asyncio
async def test_registry_manifest_cancels_cooperative_handler(task_session):
    started = asyncio.Event()

    async def cancellable_handler(**kwargs):
        started.set()
        await asyncio.sleep(10)
        return {}

    registry = AgentToolRegistry()
    registry.register(_test_manifest("test.cancel"), handler=cancellable_handler)
    cancel_event = asyncio.Event()
    task = asyncio.create_task(registry.execute("test.cancel", session=task_session, user_id=801, project_id=None, cancel_event=cancel_event))
    await started.wait()
    cancel_event.set()
    with pytest.raises(ToolExecutionCancelled):
        await task


@pytest.mark.asyncio
async def test_registry_manifest_rejects_pre_cancelled_handler(task_session):
    async def handler(**kwargs):
        raise AssertionError("handler must not start")

    registry = AgentToolRegistry()
    registry.register(_test_manifest("test.pre_cancel"), handler=handler)
    cancel_event = asyncio.Event()
    cancel_event.set()
    with pytest.raises(ToolExecutionCancelled):
        await registry.execute("test.pre_cancel", session=task_session, user_id=801, project_id=None, cancel_event=cancel_event)


def test_default_registry_has_write_handlers():
    assert callable(DEFAULT_TOOL_REGISTRY.get_handler('chapter.generate'))
    assert callable(DEFAULT_TOOL_REGISTRY.get_handler('chapter.rewrite'))
    assert DEFAULT_TOOL_REGISTRY.get('chapter.generate').requires_confirmation is True
    assert DEFAULT_TOOL_REGISTRY.get('chapter.generate').timeout_seconds == 300


@pytest.mark.asyncio
async def test_write_handler_requires_approval_identity(task_session):
    with pytest.raises(ToolContractViolation):
        await DEFAULT_TOOL_REGISTRY.execute(
            'chapter.generate',
            session=task_session,
            user_id=801,
            project_id='write-project',
            arguments={'chapter_number': 3},
        )


def test_dynamic_tool_provider_requires_application_import_contract(monkeypatch):
    registry = AgentToolRegistry()
    with pytest.raises(ToolProviderLoadError):
        load_tool_provider(registry, 'not-a-provider')
    with pytest.raises(ToolProviderLoadError):
        load_tool_provider(registry, 'os.path:register_agent_tools')

    def register_agent_tools(target):
        target.register(_test_manifest('plugin.safe'))

    monkeypatch.setattr(
        'app.agent.registry.import_module',
        lambda name: SimpleNamespace(register_agent_tools=register_agent_tools),
    )
    load_tool_provider(registry, 'app.agent.providers.project_capabilities:register_agent_tools')
    assert registry.get('plugin.safe').name == 'plugin.safe'

    monkeypatch.setattr('app.agent.registry.import_module', lambda name: object())
    with pytest.raises(ToolProviderLoadError):
        load_tool_provider(AgentToolRegistry(), 'app.agent.providers.project_capabilities:register_agent_tools')


def test_dynamic_tool_provider_does_not_leak_partial_registration(monkeypatch):
    registry = AgentToolRegistry()

    def register_agent_tools(target):
        target.register(_test_manifest('plugin.partial'))
        raise RuntimeError('provider failure')

    monkeypatch.setattr(
        'app.agent.registry.import_module',
        lambda name: SimpleNamespace(register_agent_tools=register_agent_tools),
    )
    with pytest.raises(ToolProviderLoadError):
        load_tool_provider(registry, 'app.agent.providers.project_capabilities:register_agent_tools')
    with pytest.raises(KeyError):
        registry.get('plugin.partial')
