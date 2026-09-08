from __future__ import annotations

import ast
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import event, inspect, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.exc import IntegrityError
from app.db.base import Base
from fastapi import HTTPException

from app.models import (
    AgentArtifactRef, AgentEventRecord, AgentJob, AgentRun, AgentRunCommand, AgentRunStep, AgentSession,
    AgentApproval, ArtifactLineage, QualityGate, QualityResult, NovelProject, ProjectMember, ProjectMemberRole,
    TaskRuntime, TaskRuntimeEvent, User,
    Chapter, BlueprintCharacter,
    AgentMessage, AgentRunReasoningChunk, AgentCapabilityExecution,
    AgentRunCapabilitySnapshot, AgentCatalogRelease, ContextSnapshot,
    ContextSnapshotRef, PlanRevision, ConversationSummary, QualityFinding,
)
from app.models.clue_tracker import StoryClue, ClueChapterLink, ClueThread
from app.models.token_budget import TokenBudget, TokenUsage, TokenBudgetAlert
from app.models.knowledge_graph import CharacterNode, EventEdge, KnowledgeGraphMetadata
from app.models.research import ProjectResearchConfig, ResearchArtifact
from app.schemas.novel import NovelSectionType
from app.agent.jobs import AgentJobService
from app.services.agent_runtime import AgentRuntimeService
from app.services.novel_service import NovelService


pytestmark = pytest.mark.asyncio


async def _seed_project_access(task_session):
    owner = User(id=9401, username="novel-service-owner", hashed_password="x", is_active=True)
    editor = User(id=9402, username="novel-service-editor", hashed_password="x", is_active=True)
    viewer = User(id=9403, username="novel-service-viewer", hashed_password="x", is_active=True)
    outsider = User(id=9404, username="novel-service-outsider", hashed_password="x", is_active=True)
    project = NovelProject(
        id="novel-service-member-project",
        user_id=owner.id,
        title="NovelService member semantics",
        initial_prompt="seed",
    )
    task_session.add_all(
        [
            owner,
            editor,
            viewer,
            outsider,
            project,
            ProjectMember(
                project_id=project.id,
                user_id=editor.id,
                role=ProjectMemberRole.editor.value,
            ),
            ProjectMember(
                project_id=project.id,
                user_id=viewer.id,
                role=ProjectMemberRole.viewer.value,
            ),
        ]
    )
    await task_session.commit()
    return owner, editor, viewer, outsider, project


def _owner_gate_callers() -> list[str]:
    source = __import__("inspect").getsource(NovelService)
    tree = ast.parse(source)
    callers: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        if node.name == "ensure_project_owner":
            continue
        if any(
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "ensure_project_owner"
            for call in ast.walk(node)
        ):
            callers.append(node.name)
    return callers


async def test_ensure_project_owner_inventory_keeps_only_delete_owner_gate():
    assert _owner_gate_callers() == ["delete_projects"]


async def test_member_read_helpers_do_not_reenter_legacy_owner_gate(task_session, monkeypatch):
    _owner, editor, _viewer, outsider, project = await _seed_project_access(task_session)
    service = NovelService(task_session)

    async def fail_if_legacy_owner_gate_is_used(*_args, **_kwargs):
        raise AssertionError("member read path must not call ensure_project_owner")

    monkeypatch.setattr(service, "ensure_project_owner", fail_if_legacy_owner_gate_is_used)
    monkeypatch.setattr(service, "_serialize_project", AsyncMock(return_value="serialized-project"))
    monkeypatch.setattr(
        service,
        "_build_section_response",
        lambda _project, section: ("section", section),
    )
    monkeypatch.setattr(
        service,
        "_build_chapter_schema",
        lambda _project, chapter_number, **_kwargs: ("chapter", chapter_number),
    )

    assert await service.get_project_schema(project.id, editor.id) == "serialized-project"
    assert await service.get_section_data(project.id, editor.id, NovelSectionType.OVERVIEW) == (
        "section",
        NovelSectionType.OVERVIEW,
    )
    assert await service.get_chapter_schema(project.id, editor.id, 1) == ("chapter", 1)

    with pytest.raises(HTTPException) as denied:
        await service.get_project_schema(project.id, outsider.id)
    assert denied.value.status_code == 403


async def test_list_projects_for_user_uses_member_visible_repository_scope(task_session):
    _owner, editor, _viewer, outsider, project = await _seed_project_access(task_session)
    service = NovelService(task_session)

    summaries = await service.list_projects_for_user(editor.id)
    assert [summary.id for summary in summaries] == [project.id]
    assert await service.list_projects_for_user(outsider.id) == []


async def test_delete_projects_preserves_true_owner_only_compatibility(task_session, monkeypatch):
    owner, editor, _viewer, _outsider, project = await _seed_project_access(task_session)
    service = NovelService(task_session)
    service._vector_store.delete_by_project = AsyncMock()

    with pytest.raises(HTTPException) as denied:
        await service.delete_projects([project.id], editor.id)
    assert denied.value.status_code == 403

    agent_session = AgentSession(
        user_id=owner.id,
        project_id=project.id,
        title="delete-project-agent-session",
    )
    task_session.add(agent_session)
    await task_session.flush()

    runtime = TaskRuntime(
        task_id="delete-project-runtime-task",
        owner_user_id=owner.id,
        project_id=project.id,
        task_type="chapter_generation",
        status="cancelling",
    )
    task_session.add(runtime)
    await task_session.flush()
    task_session.add(
        TaskRuntimeEvent(
            task_id=runtime.task_id,
            event_type="task_cancel_requested",
            status="cancelling",
            message="fixture",
        )
    )
    await task_session.commit()

    await service.delete_projects([project.id], owner.id)
    service._vector_store.delete_by_project.assert_awaited_once_with(project.id)
    assert await service.repo.get_by_id(project.id) is None
    assert await task_session.get(TaskRuntime, runtime.task_id) is None
    assert await task_session.get(AgentSession, agent_session.id) is None
    assert (await task_session.execute(select(TaskRuntimeEvent).where(TaskRuntimeEvent.task_id == runtime.task_id))).scalars().all() == []


async def test_delete_projects_cleans_agent_artifact_graph(task_session):
    owner, _editor, _viewer, _outsider, project = await _seed_project_access(task_session)
    service = NovelService(task_session)
    service._vector_store.delete_by_project = AsyncMock()

    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=owner.id, project_id=project.id)
    run = await runtime.create_run(
        session_id=agent_session.id,
        user_id=owner.id,
        project_id=project.id,
    )
    await runtime.update_run(run_id=run.id, user_id=owner.id, status="running")
    step = await runtime.ensure_step(
        run_id=run.id,
        user_id=owner.id,
        step_order=1,
        tool_name="chapter.generate",
        idempotency_key=f"delete-artifact-step-{run.id}",
        input_payload={"chapter_number": 1},
    )
    approval = await runtime.request_approval(
        run_id=run.id,
        user_id=owner.id,
        step_id=step.id,
        tool_name="chapter.generate",
        project_id=project.id,
        arguments={"chapter_number": 1},
    )
    command = await runtime.request_run_command(
        run_id=run.id,
        user_id=owner.id,
        command_type="cancel",
        idempotency_key=f"delete-artifact-command-{run.id}",
        expected_state_version=int((await runtime.get_run(run.id, owner.id)).state_version or 0),
    )
    job = await AgentJobService(task_session).create_job(
        run_id=run.id,
        user_id=owner.id,
        project_id=project.id,
        kind="agent_execution",
        idempotency_key=f"delete-artifact-job-{run.id}",
    )
    source = await runtime.add_artifact(
        run_id=run.id,
        user_id=owner.id,
        project_id=project.id,
        kind="chapter_candidate",
        uri="agent-artifact://delete-source.md",
        sha256="a" * 64,
        metadata={"status": "candidate"},
    )
    derived = await runtime.add_artifact(
        run_id=run.id,
        user_id=owner.id,
        project_id=project.id,
        kind="chapter_version",
        uri="chapter-version://delete-derived",
        sha256="b" * 64,
        metadata={"status": "accepted"},
    )
    result = QualityResult(
        result_id="delete-project-quality-result",
        run_id=run.id,
        artifact_ref_id=source.id,
        correlation_id=run.correlation_id,
        transaction_id=run.transaction_id,
        user_id=owner.id,
        project_id=project.id,
        assessor_id="test",
        status="completed",
        score=90,
        summary="fixture",
        metrics_json={},
    )
    task_session.add(result)
    await task_session.flush()
    gate = QualityGate(
        gate_id="delete-project-quality-gate",
        quality_result_id=result.id,
        run_id=run.id,
        artifact_ref_id=source.id,
        correlation_id=run.correlation_id,
        transaction_id=run.transaction_id,
        gate_name="fixture",
        decision="passed",
        blocker_count=0,
        policy_json={},
    )
    lineage = ArtifactLineage(
        lineage_id="delete-project-lineage",
        run_id=run.id,
        source_artifact_ref_id=source.id,
        derived_artifact_ref_id=derived.id,
        correlation_id=run.correlation_id,
        transaction_id=run.transaction_id,
        relation_type="accepted_as_version",
        operation="fixture",
        input_digest=source.sha256,
        output_digest=derived.sha256,
        metadata_json={},
    )
    task_session.add_all([gate, lineage])
    await runtime.append_event(
        run_id=run.id,
        user_id=owner.id,
        event_type="fixture_event",
        summary="fixture",
        data={"source": source.id},
    )
    await task_session.commit()

    await service.delete_projects([project.id], owner.id)

    for model, identity in [
        (AgentSession, agent_session.id),
        (AgentRun, run.id),
        (AgentRunStep, step.id),
        (AgentApproval, approval.id),
        (AgentRunCommand, command.id),
        (AgentJob, job.id),
        (AgentArtifactRef, source.id),
        (AgentArtifactRef, derived.id),
        (QualityResult, result.id),
    ]:
        assert await task_session.get(model, identity) is None
    assert (await task_session.execute(select(ArtifactLineage))).scalars().all() == []
    assert (await task_session.execute(select(QualityGate))).scalars().all() == []
    assert (await task_session.execute(select(AgentEventRecord).where(AgentEventRecord.run_id == run.id))).scalars().all() == []


@pytest.fixture(params=[False, True], ids=["fk-off", "fk-on"])
async def deletion_graph_session(request):
    """A fresh in-memory DB, never the application DB or task_session's engine."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)

    @event.listens_for(engine.sync_engine, "connect")
    def configure_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute(f"PRAGMA foreign_keys={int(request.param)}")
        cursor.close()

    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            assert await session.scalar(text("PRAGMA foreign_keys")) == int(request.param)
            yield session
    finally:
        await engine.dispose()


_DELETION_GRAPH_MODELS = (
    AgentSession, AgentMessage, AgentRun, AgentRunStep, AgentApproval,
    AgentRunCommand, AgentJob, AgentArtifactRef, AgentEventRecord,
    AgentRunReasoningChunk, AgentRunCapabilitySnapshot, AgentCapabilityExecution,
    ContextSnapshot, ContextSnapshotRef, PlanRevision, ConversationSummary,
    ArtifactLineage, QualityResult, QualityFinding, QualityGate,
)


async def _seed_deletion_graph(session, owner, project, *, with_artifacts):
    runtime = AgentRuntimeService(session)
    conversation = await runtime.create_session(user_id=owner.id, project_id=project.id)
    run = await runtime.create_run(
        session_id=conversation.id, user_id=owner.id, project_id=project.id,
    )
    common = dict(run_id=run.id, correlation_id=run.correlation_id)
    step = await runtime.ensure_step(
        run_id=run.id, user_id=owner.id, step_order=1, tool_name="chapter.generate",
        idempotency_key="delete-graph-step", input_payload={"chapter_number": 1},
    )
    await runtime.request_approval(
        run_id=run.id, user_id=owner.id, step_id=step.id,
        tool_name="chapter.generate", project_id=project.id, arguments={},
    )
    await runtime.request_run_command(
        run_id=run.id, user_id=owner.id, command_type="cancel",
        idempotency_key="delete-graph-command", expected_state_version=run.state_version,
    )
    await AgentJobService(session).create_job(
        run_id=run.id, user_id=owner.id, project_id=project.id,
        kind="agent_execution", idempotency_key="delete-graph-job",
    )
    snapshot = await session.get(ContextSnapshot, run.context_json["relational_context_snapshot_id"])
    revision = PlanRevision(
        revision_id=run.id, **common, session_id=conversation.id,
        context_snapshot_id=snapshot.id, revision_number=1,
        user_id=owner.id, project_id=project.id, digest="d" * 64,
    )
    session.add(revision)
    await session.flush()
    session.add_all([
        PlanRevision(
            revision_id=f"child-{run.id}"[:36], **common, session_id=conversation.id,
            context_snapshot_id=snapshot.id, parent_revision_id=revision.id,
            revision_number=2, user_id=owner.id, project_id=project.id, digest="e" * 64,
        ),
        ContextSnapshotRef(
            context_snapshot_id=snapshot.id, ref_order=10000,
            ref_type="project", ref_key=project.id, digest="f" * 64,
        ),
        AgentMessage(session_id=conversation.id, user_id=owner.id,
                     role="user", content="deletion fixture", sequence=1),
        ConversationSummary(
            summary_id=run.id, **common, session_id=conversation.id,
            user_id=owner.id, project_id=project.id, start_message_sequence=1,
            end_message_sequence=1, message_count=1, source_digest="a" * 64,
            summary_text="fixture", digest="b" * 64,
        ),
        AgentRunReasoningChunk(
            run_id=run.id, user_id=owner.id, project_id=project.id,
            sequence=1, chunk_index=0, content="fixture", content_hash="c" * 64,
        ),
        AgentCapabilityExecution(
            execution_id=run.id, **common, step_id=step.id,
            snapshot_id=run.context_json["relational_capability_snapshot_id"],
            capability_id="chapter.generate", idempotency_key="delete-graph-execution",
        ),
    ])
    # Always seed a complete NULL-artifact quality tree, even for artifact runs.
    artifact_refs = [None]
    if with_artifacts:
        artifacts = [await runtime.add_artifact(
            run_id=run.id, user_id=owner.id, project_id=project.id,
            kind="chapter_candidate", uri=f"agent-artifact://{run.id}-{i}.md",
            sha256=str(i) * 64, metadata={},
        ) for i in range(2)]
        artifact_refs.append(artifacts[0].id)
        session.add(ArtifactLineage(
            lineage_id=run.id, **common, source_artifact_ref_id=artifacts[0].id,
            derived_artifact_ref_id=artifacts[1].id, relation_type="derived_from",
        ))
    for artifact_id in artifact_refs:
        result = QualityResult(
            result_id=f"{len(artifact_refs)}-{artifact_id or run.id}"[:36], **common,
            user_id=owner.id, project_id=project.id if artifact_id else None,
            artifact_ref_id=artifact_id, status="completed", score=90,
        )
        session.add(result)
        await session.flush()
        session.add_all([
            QualityFinding(quality_result_id=result.id, finding_id=result.id,
                           code="fixture", message="fixture", fingerprint=result.id),
            QualityGate(quality_result_id=result.id, gate_id=result.id, **common,
                        artifact_ref_id=artifact_id, gate_name="fixture", decision="passed"),
        ])
    await session.commit()
    return run


async def _prepare_deletion_graph(session, with_artifacts):
    owner = User(username="graph-delete-owner", hashed_password="x", is_active=True)
    session.add(owner)
    await session.flush()
    target = NovelProject(id="graph-delete-target", user_id=owner.id, title="target", initial_prompt="seed")
    survivor = NovelProject(id="graph-delete-survivor", user_id=owner.id, title="survivor", initial_prompt="seed")
    session.add_all([target, survivor])
    await session.commit()
    await _seed_deletion_graph(session, owner, survivor, with_artifacts=True)
    # Strong references deliberately keep every survivor and target in the same
    # identity map. Snapshot all columns to catch changes as well as row loss.
    retained = {}
    for model in _DELETION_GRAPH_MODELS:
        retained[model] = list((await session.scalars(select(model))).all())
        assert retained[model], f"missing survivor coverage: {model.__name__}"
    await _seed_deletion_graph(session, owner, target, with_artifacts=with_artifacts)
    deleted = {}
    preserved_rows = {}
    for model in _DELETION_GRAPH_MODELS:
        rows = list((await session.scalars(select(model))).all())
        kept_ids = {obj.id for obj in retained[model]}
        deleted[model] = [obj for obj in rows if obj.id not in kept_ids]
        if with_artifacts or model not in (AgentArtifactRef, ArtifactLineage):
            assert deleted[model], f"missing target coverage: {model.__name__}"
        preserved_rows[model] = {
            obj.id: {column.key: getattr(obj, column.key) for column in inspect(model).columns}
            for obj in retained[model]
        }
    catalogs = list((await session.scalars(select(AgentCatalogRelease))).all())
    return owner, target, survivor, retained, deleted, preserved_rows, catalogs


async def _assert_deletion_graph(session, state):
    owner, target, survivor, retained, deleted, preserved_rows, catalogs = state
    service = NovelService(session)
    service._vector_store.delete_by_project = AsyncMock()
    deleted_tables = []

    def capture_delete(_conn, _cursor, statement, _params, _context, _many):
        if statement.startswith("DELETE FROM "):
            deleted_tables.append(statement.split()[2])

    engine = session.bind.sync_engine
    event.listen(engine, "before_cursor_execute", capture_delete)
    try:
        await service.delete_projects([target.id], owner.id)
    finally:
        event.remove(engine, "before_cursor_execute", capture_delete)
    service._vector_store.delete_by_project.assert_awaited_once_with(target.id)
    assert await session.get(NovelProject, target.id) is None
    assert await session.get(NovelProject, survivor.id) is survivor
    for model in _DELETION_GRAPH_MODELS:
        for obj in deleted[model]:
            # Assert identity behavior before issuing SQL (which could mask it).
            assert await session.get(model, obj.id) is None, f"stale identity: {model.__name__}"
        for obj in retained[model]:
            assert await session.get(model, obj.id) is obj
        rows = (await session.execute(select(model.__table__))).mappings().all()
        assert {row["id"]: dict(row) for row in rows} == preserved_rows[model], model.__name__
    assert set((await session.scalars(select(AgentCatalogRelease.id))).all()) == {obj.id for obj in catalogs}
    assert (await session.execute(text("PRAGMA foreign_key_check"))).all() == []
    # Verify actual DML order, not just the cascade-dependent final row counts.
    positions = {name: deleted_tables.index(name) for name in deleted_tables}
    for model in _DELETION_GRAPH_MODELS:
        child = model.__tablename__
        for fk in model.__table__.foreign_keys:
            parent = fk.column.table.name
            if child != parent and child in positions and parent in positions:
                assert positions[child] < positions[parent], f"delete order: {child} before {parent}"


@pytest.mark.parametrize("with_artifacts", [False, True], ids=["no-artifacts", "artifacts-and-null-quality"])
async def test_delete_projects_agent_graph_fk_identity_and_cross_project(deletion_graph_session, with_artifacts):
    state = await _prepare_deletion_graph(deletion_graph_session, with_artifacts)
    await _assert_deletion_graph(deletion_graph_session, state)


@pytest.mark.parametrize("mutation", ["null-quality", "snapshot-first", "run-first", "identity-sync"])
async def test_delete_projects_agent_graph_negative_controls(deletion_graph_session, monkeypatch, mutation):
    """Mutate only the live method in this test process, never workspace source."""
    import inspect as python_inspect
    import textwrap

    state = await _prepare_deletion_graph(deletion_graph_session, with_artifacts=True)
    original = NovelService.delete_projects
    source = textwrap.dedent(python_inspect.getsource(original))
    if mutation == "null-quality":
        source = source.replace("(QualityResult.project_id == pid)", "QualityResult.id.in_([])").replace(
            "| QualityResult.run_id.in_(agent_run_ids)", "| False",
        )
    elif mutation == "identity-sync":
        source = source.replace('synchronize_session="fetch"', 'synchronize_session=False')
    else:
        model = "ContextSnapshot" if mutation == "snapshot-first" else "AgentRun"
        source = source.replace(
            "for model, predicate in graph_deletes:",
            f"graph_deletes.insert(0, graph_deletes.pop(next(i for i, (m, _) in enumerate(graph_deletes) if m is {model})))\n"
            "        for model, predicate in graph_deletes:",
        )
    assert source != textwrap.dedent(python_inspect.getsource(original))
    namespace = dict(original.__globals__)
    exec(compile(source, "<project-delete-negative-control>", "exec"), namespace)
    monkeypatch.setattr(NovelService, "delete_projects", namespace["delete_projects"])
    with pytest.raises(
        (AssertionError, IntegrityError),
        match="stale identity:|delete order:|FOREIGN KEY constraint failed",
    ):
        await _assert_deletion_graph(deletion_graph_session, state)


_WRITING_FACT_MODELS = (
    StoryClue, ClueChapterLink, ClueThread,
    TokenBudget, TokenUsage, TokenBudgetAlert,
    CharacterNode, EventEdge, KnowledgeGraphMetadata,
    ProjectResearchConfig, ResearchArtifact,
)


async def _seed_project_writing_facts(session, owner, project_id):
    project = NovelProject(id=project_id, user_id=owner.id, title=project_id, initial_prompt="fixture")
    session.add(project)
    await session.flush()
    chapter = Chapter(project_id=project_id, chapter_number=1)
    character = BlueprintCharacter(project_id=project_id, name="fixture character")
    clue = StoryClue(project_id=project_id, name="fixture clue", clue_type="key_evidence")
    session.add_all([chapter, character, clue])
    await session.flush()
    nodes = [CharacterNode(project_id=project_id, name=f"node-{i}",
                           blueprint_character_id=character.id) for i in range(2)]
    session.add_all(nodes)
    await session.flush()
    rows = [
        project, chapter, character, clue, *nodes,
        ClueChapterLink(clue_id=clue.id, chapter_id=chapter.id, chapter_number=1,
                        appearance_type="mention", content_excerpt=project_id),
        ClueThread(project_id=project_id, thread_name="fixture thread", clue_ids=[clue.id]),
        TokenBudget(project_id=project_id, total_budget=130, extra={"sentinel": project_id}),
        TokenUsage(project_id=project_id, chapter_id=chapter.id, module="content", tokens_used=25),
        TokenBudgetAlert(project_id=project_id, alert_type="warning", threshold_percent=80,
                         current_usage=104, budget_limit=130),
        EventEdge(project_id=project_id, source_node_id=nodes[0].id, target_node_id=nodes[1].id,
                  event_type="meeting", description=project_id),
        KnowledgeGraphMetadata(project_id=project_id, node_count=2, edge_count=1,
                               plot_threads_cache={"sentinel": project_id}),
        ProjectResearchConfig(project_id=project_id, mode="manual", preferred_domains=["example.test"],
                              extra={"sentinel": project_id}),
        ResearchArtifact(project_id=project_id, user_id=owner.id, run_id=project_id,
                         scope="chapter", status="completed", summary=project_id),
    ]
    session.add_all(rows)
    await session.commit()
    return rows


async def _database_rows(session):
    # Full row snapshots (not just counts) make survivor mutations visible.
    result = {}
    for table in Base.metadata.tables.values():
        primary_keys = [column.name for column in table.primary_key]
        rows = (await session.execute(select(table))).mappings().all()
        result[table.name] = {
            tuple(row[key] for key in primary_keys): dict(row) for row in rows
        }
    return result


async def _prepare_writing_fact_deletion(session):
    owner = User(username="writing-delete-owner", hashed_password="x", is_active=True)
    session.add(owner)
    await session.flush()
    survivors = await _seed_project_writing_facts(session, owner, "writing-keep")
    before = await _database_rows(session)
    targets = await _seed_project_writing_facts(session, owner, "writing-delete")
    seeded = await _database_rows(session)
    for model in _WRITING_FACT_MODELS:
        assert len(seeded[model.__tablename__]) > len(before[model.__tablename__]) > 0
    assert (await session.execute(text("PRAGMA foreign_key_check"))).all() == []
    return owner, survivors, targets, before


async def _assert_writing_fact_deletion(session, state):
    owner, survivors, targets, before = state
    service = NovelService(session)
    service._vector_store.delete_by_project = AsyncMock()
    identities = [(type(obj), inspect(obj).identity) for obj in targets]
    deleted_tables = []

    def capture_delete(_conn, _cursor, statement, _params, _context, _many):
        if statement.startswith("DELETE FROM "):
            deleted_tables.append(statement.split()[2])

    engine = session.bind.sync_engine
    event.listen(engine, "before_cursor_execute", capture_delete)
    try:
        await service.delete_projects(["writing-delete"], owner.id)
    finally:
        event.remove(engine, "before_cursor_execute", capture_delete)
    service._vector_store.delete_by_project.assert_awaited_once_with("writing-delete")
    for model, identity in identities:
        assert await session.get(model, identity) is None, f"writing stale identity: {model.__name__}"
    for obj in survivors:
        assert await session.get(type(obj), inspect(obj).identity) is obj
    after = await _database_rows(session)
    assert after == before, {
        table: (before[table], after[table]) for table in before if before[table] != after[table]
    }
    assert (await session.execute(text("PRAGMA foreign_key_check"))).all() == []
    positions = {table: deleted_tables.index(table) for table in deleted_tables}
    for model in _WRITING_FACT_MODELS:
        child = model.__tablename__
        assert child in positions, f"missing explicit writing delete: {child}"
        for fk in model.__table__.foreign_keys:
            parent = fk.column.table.name
            if parent in positions:
                assert positions[child] < positions[parent], f"writing delete order: {child} before {parent}"


async def test_delete_projects_cleans_smoke_writing_domains(deletion_graph_session):
    state = await _prepare_writing_fact_deletion(deletion_graph_session)
    await _assert_writing_fact_deletion(deletion_graph_session, state)


@pytest.mark.parametrize("omitted_model", _WRITING_FACT_MODELS, ids=lambda model: model.__name__)
async def test_delete_projects_writing_domain_negative_controls(deletion_graph_session, monkeypatch, omitted_model):
    """Each explicit child-table cleanup is necessary, even with FK CASCADE."""
    import inspect as python_inspect
    import textwrap

    state = await _prepare_writing_fact_deletion(deletion_graph_session)
    original = NovelService.delete_projects
    source = textwrap.dedent(python_inspect.getsource(original))
    marker = "for model, predicate in writing_deletes:"
    assert source.count(marker) == 1
    source = source.replace(
        marker,
        f"writing_deletes = [(m, p) for m, p in writing_deletes if m.__name__ != {omitted_model.__name__!r}]\n"
        "        for model, predicate in writing_deletes:",
    )
    namespace = dict(original.__globals__)
    exec(compile(source, "<writing-delete-negative-control>", "exec"), namespace)
    monkeypatch.setattr(NovelService, "delete_projects", namespace["delete_projects"])
    with pytest.raises(AssertionError, match="writing stale identity:"):
        await _assert_writing_fact_deletion(deletion_graph_session, state)
