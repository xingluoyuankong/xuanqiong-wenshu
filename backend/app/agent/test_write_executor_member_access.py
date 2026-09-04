from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.agent import write_executor
from app.agent.write_executor import (
    accept_candidate_artifact,
    diff_artifact_with_chapter_version,
    diff_artifacts,
    list_artifact_quality_blockers,
    list_artifact_rewrite_instructions,
    read_artifact_content,
)
from app.models import Chapter, ChapterVersion, NovelProject, ProjectMember, User
from app.models.agent import AgentArtifactRef
from app.models.project_member import ProjectMemberRole
from app.services.agent_quality_service import AgentQualityService
from app.services.agent_runtime import AgentNotFound, AgentRuntimeService


@dataclass(frozen=True)
class WriteExecutorMemberFixture:
    owner: User
    editor: User
    viewer: User
    outsider: User
    projectless_owner: User
    projectless_reader: User
    project: NovelProject
    chapter_version: ChapterVersion
    blocked_candidate: AgentArtifactRef
    comparison_artifact: AgentArtifactRef
    accepted_candidate: AgentArtifactRef
    projectless_artifact: AgentArtifactRef
    artifact_content: str


async def _create_user(session, *, user_id: int, label: str) -> User:
    user = User(
        id=user_id,
        username=f"write-executor-{label}",
        email=f"write-executor-{label}@example.com",
        hashed_password="x",
        is_active=True,
    )
    session.add(user)
    return user


async def _create_artifact(
    session,
    *,
    root: Path,
    run_id: str,
    correlation_id: str,
    transaction_id: str,
    user_id: int,
    project_id: str | None,
    content: str,
    label: str,
    chapter_number: int = 1,
    source_version_id: int | None = None,
    blocker: bool = False,
) -> AgentArtifactRef:
    storage_key = f"{label}-{uuid4()}.txt"
    artifact_path = root / storage_key
    artifact_path.write_text(content, encoding="utf-8")
    metadata: dict[str, object] = {
        "status": "candidate",
        "storage_key": storage_key,
        "chapter_number": chapter_number,
    }
    if source_version_id is not None:
        metadata["source_version_id"] = source_version_id
    artifact = AgentArtifactRef(
        id=str(uuid4()),
        run_id=run_id,
        correlation_id=correlation_id,
        transaction_id=transaction_id,
        user_id=user_id,
        project_id=project_id,
        kind="chapter_candidate",
        uri=f"file://agent-artifacts/{storage_key}",
        sha256=sha256(content.encode("utf-8")).hexdigest(),
        metadata_json=metadata,
    )
    session.add(artifact)
    await session.flush()

    quality_gate = {
        "passed": not blocker,
        "blockers": (
            [
                {
                    "code": "story_progression_stall",
                    "message": "本章冲突没有推进。",
                    "source": "story_progression_guard",
                    "snippet": "门仍然锁着",
                    "start_char": 0,
                    "end_char": 6,
                    "remediation": {"instruction": "让主角做出不可逆选择。"},
                }
            ]
            if blocker
            else []
        ),
    }
    await AgentQualityService(session).evaluate_candidate(
        artifact=artifact,
        content=content,
        summaries={"quality_score": 91 if not blocker else 42},
        quality_gate=quality_gate,
    )
    await session.flush()
    return artifact


async def _seed_write_executor_members(task_session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> WriteExecutorMemberFixture:
    """Build one shared project plus an unrelated private Artifact boundary."""
    artifact_root = tmp_path / "agent-artifacts"
    artifact_root.mkdir()
    monkeypatch.setattr(write_executor, "_ARTIFACT_ROOT", artifact_root)

    owner = await _create_user(task_session, user_id=89101, label="owner")
    editor = await _create_user(task_session, user_id=89102, label="editor")
    viewer = await _create_user(task_session, user_id=89103, label="viewer")
    outsider = await _create_user(task_session, user_id=89104, label="outsider")
    projectless_owner = await _create_user(task_session, user_id=89105, label="projectless-owner")
    projectless_reader = await _create_user(task_session, user_id=89106, label="projectless-reader")
    project = NovelProject(id="write-executor-member-project", user_id=owner.id, title="Write executor 成员权限")
    task_session.add_all(
        [
            project,
            ProjectMember(project_id=project.id, user_id=owner.id, role=ProjectMemberRole.owner.value),
            ProjectMember(project_id=project.id, user_id=editor.id, role=ProjectMemberRole.editor.value),
            ProjectMember(project_id=project.id, user_id=viewer.id, role=ProjectMemberRole.viewer.value),
        ]
    )
    await task_session.flush()

    chapter = Chapter(project_id=project.id, chapter_number=1, status="generated")
    task_session.add(chapter)
    await task_session.flush()
    chapter_version = ChapterVersion(
        chapter_id=chapter.id,
        version_label="owner-baseline",
        provider="fixture",
        content="门仍然锁着\n雨落在石阶上",
        status="selected",
    )
    task_session.add(chapter_version)
    await task_session.flush()
    chapter.selected_version_id = chapter_version.id
    await task_session.flush()

    owner_runtime = AgentRuntimeService(task_session)
    owner_session = await owner_runtime.create_session(user_id=owner.id, project_id=project.id)
    owner_run = await owner_runtime.create_run(
        session_id=owner_session.id,
        user_id=owner.id,
        project_id=project.id,
    )
    private_session = await owner_runtime.create_session(user_id=projectless_owner.id)
    private_run = await owner_runtime.create_run(
        session_id=private_session.id,
        user_id=projectless_owner.id,
        project_id=None,
    )

    artifact_content = "门仍然锁着\n主角点燃了密信"
    blocked_candidate = await _create_artifact(
        task_session,
        root=artifact_root,
        run_id=owner_run.id,
        correlation_id=owner_run.correlation_id,
        transaction_id=owner_run.transaction_id,
        user_id=owner.id,
        project_id=project.id,
        content=artifact_content,
        label="blocked-candidate",
        source_version_id=chapter_version.id,
        blocker=True,
    )
    comparison_artifact = await _create_artifact(
        task_session,
        root=artifact_root,
        run_id=owner_run.id,
        correlation_id=owner_run.correlation_id,
        transaction_id=owner_run.transaction_id,
        user_id=owner.id,
        project_id=project.id,
        content="门仍然锁着\n主角撕毁了密信",
        label="comparison-candidate",
        source_version_id=chapter_version.id,
    )
    accepted_candidate = await _create_artifact(
        task_session,
        root=artifact_root,
        run_id=owner_run.id,
        correlation_id=owner_run.correlation_id,
        transaction_id=owner_run.transaction_id,
        user_id=owner.id,
        project_id=project.id,
        content="门仍然锁着\n主角烧毁了密信",
        label="accepted-candidate",
        source_version_id=chapter_version.id,
    )
    projectless_artifact = await _create_artifact(
        task_session,
        root=artifact_root,
        run_id=private_run.id,
        correlation_id=private_run.correlation_id,
        transaction_id=private_run.transaction_id,
        user_id=projectless_owner.id,
        project_id=None,
        content="仅创建者可读的私有候选",
        label="projectless-candidate",
    )
    await task_session.commit()

    return WriteExecutorMemberFixture(
        owner=owner,
        editor=editor,
        viewer=viewer,
        outsider=outsider,
        projectless_owner=projectless_owner,
        projectless_reader=projectless_reader,
        project=project,
        chapter_version=chapter_version,
        blocked_candidate=blocked_candidate,
        comparison_artifact=comparison_artifact,
        accepted_candidate=accepted_candidate,
        projectless_artifact=projectless_artifact,
        artifact_content=artifact_content,
    )


@pytest.mark.asyncio
async def test_viewer_can_read_owner_project_artifact_content_diffs_blockers_and_rewrite_instructions(task_session, monkeypatch, tmp_path):
    fixture = await _seed_write_executor_members(task_session, monkeypatch, tmp_path)

    artifact, content = await read_artifact_content(
        artifact_id=fixture.blocked_candidate.id,
        user_id=fixture.viewer.id,
        session=task_session,
    )
    artifact_diff = await diff_artifacts(
        artifact_id=fixture.blocked_candidate.id,
        against_artifact_id=fixture.comparison_artifact.id,
        user_id=fixture.viewer.id,
        session=task_session,
    )
    chapter_version_diff = await diff_artifact_with_chapter_version(
        artifact_id=fixture.blocked_candidate.id,
        project_id=fixture.project.id,
        chapter_number=1,
        version_id=fixture.chapter_version.id,
        user_id=fixture.viewer.id,
        session=task_session,
    )
    blockers = await list_artifact_quality_blockers(
        artifact_id=fixture.blocked_candidate.id,
        user_id=fixture.viewer.id,
        session=task_session,
    )
    instructions = await list_artifact_rewrite_instructions(
        artifact_id=fixture.blocked_candidate.id,
        user_id=fixture.viewer.id,
        session=task_session,
    )

    assert artifact.id == fixture.blocked_candidate.id
    assert content == fixture.artifact_content
    assert artifact_diff["summary"]["modified"] == 1
    assert chapter_version_diff["version_id"] == fixture.chapter_version.id
    assert chapter_version_diff["summary"]["modified"] == 1
    assert [(row["code"], row["severity"]) for row in blockers] == [
        ("story_progression_stall", "blocker")
    ]
    assert instructions[0]["artifact_id"] == fixture.blocked_candidate.id
    assert instructions[0]["rewrite_arguments"]["source_version_id"] == fixture.chapter_version.id
    assert "story_progression_stall" in instructions[0]["instruction"]


@pytest.mark.asyncio
async def test_editor_can_accept_owner_project_candidate_after_quality_gate_passes(task_session, monkeypatch, tmp_path):
    fixture = await _seed_write_executor_members(task_session, monkeypatch, tmp_path)

    accepted = await accept_candidate_artifact(
        artifact_id=fixture.accepted_candidate.id,
        user_id=fixture.editor.id,
        note="Editor 接受 Owner 的合格候选",
        session=task_session,
    )

    assert accepted.metadata_json["status"] == "accepted"
    assert accepted.metadata_json["accepted_by_user_id"] == fixture.editor.id
    chapter = (
        await task_session.execute(
            select(Chapter).where(
                Chapter.project_id == fixture.project.id,
                Chapter.chapter_number == 1,
            )
        )
    ).scalar_one()
    versions = (
        await task_session.execute(
            select(ChapterVersion).where(ChapterVersion.chapter_id == chapter.id)
        )
    ).scalars().all()
    accepted_versions = [
        version
        for version in versions
        if (version.metadata or {}).get("artifact_id") == fixture.accepted_candidate.id
    ]
    assert len(accepted_versions) == 1
    _, candidate_content = await read_artifact_content(
        artifact_id=fixture.accepted_candidate.id,
        user_id=fixture.owner.id,
        session=task_session,
    )
    assert accepted_versions[0].content == candidate_content
    assert accepted_versions[0].metadata["accepted_by_user_id"] == fixture.editor.id


@pytest.mark.asyncio
async def test_viewer_cannot_accept_owner_project_candidate(task_session, monkeypatch, tmp_path):
    fixture = await _seed_write_executor_members(task_session, monkeypatch, tmp_path)

    with pytest.raises(HTTPException) as denied:
        await accept_candidate_artifact(
            artifact_id=fixture.accepted_candidate.id,
            user_id=fixture.viewer.id,
            note="Viewer 试图接受候选",
            session=task_session,
        )

    assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_nonmember_cannot_read_project_artifact(task_session, monkeypatch, tmp_path):
    fixture = await _seed_write_executor_members(task_session, monkeypatch, tmp_path)

    with pytest.raises(HTTPException) as denied:
        await read_artifact_content(
            artifact_id=fixture.blocked_candidate.id,
            user_id=fixture.outsider.id,
            session=task_session,
        )

    assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_projectless_artifact_remains_hidden_from_noncreator(task_session, monkeypatch, tmp_path):
    fixture = await _seed_write_executor_members(task_session, monkeypatch, tmp_path)

    _, content = await read_artifact_content(
        artifact_id=fixture.projectless_artifact.id,
        user_id=fixture.projectless_owner.id,
        session=task_session,
    )
    assert content == "仅创建者可读的私有候选"

    with pytest.raises(AgentNotFound):
        await read_artifact_content(
            artifact_id=fixture.projectless_artifact.id,
            user_id=fixture.projectless_reader.id,
            session=task_session,
        )
