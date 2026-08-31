from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import ContextSnapshot, ContextSnapshotRef, PlanRevision, ConversationSummary, User
from app.models.agent_context import AgentImmutableFactError
from app.services.agent_context_service import AgentContextIntegrityError, AgentContextService
from app.services.agent_conversation_service import AgentConversationIntegrityError, AgentConversationService
from app.services.agent_plan_service import AgentPlanIntegrityError, AgentPlanService
from app.services.agent_runtime import AgentRuntimeService


async def _run_with_messages(task_session, *, user_id: int = 2850):
    user = User(
        id=user_id,
        username=f"p1a-{user_id}",
        email=f"p1a-{user_id}@example.com",
        hashed_password="x",
        is_active=True,
    )
    task_session.add(user)
    await task_session.flush()
    runtime = AgentRuntimeService(task_session)
    session = await runtime.create_session(user_id=user.id, title="P1-A")
    run = await runtime.create_run(session_id=session.id, user_id=user.id)
    for role, content in (("user", "规划第一章"), ("assistant", "先建立冲突。"), ("user", "保留悬念。")):
        await runtime.append_message(session_id=session.id, user_id=user.id, role=role, content=content)
    return user, session, run


@pytest.mark.asyncio
async def test_context_snapshot_plan_revision_and_conversation_summary_are_persisted(task_session):
    user, session, run = await _run_with_messages(task_session)
    context_service = AgentContextService(task_session)
    context = await context_service.create_snapshot(
        run=run,
        session=session,
        context_json={"goal": "改写第一章", "constraints": {"pov": "第三人称"}},
        refs=[
            {"kind": "project", "project_id": "project-1", "role": "scope"},
            {"kind": "chapter", "chapter_id": "chapter-1", "version": "v3", "role": "target"},
        ],
    )
    assert context.run_id == run.id
    assert context.session_id == session.id
    assert len(context.refs) == 2
    assert [ref.ref_key for ref in context.refs] == ["project-1", "chapter-1"]
    await context_service.verify_snapshot(context)

    plan_service = AgentPlanService(task_session)
    initial = await plan_service.create_revision(
        run=run,
        session=session,
        context_snapshot=context,
        plan_json={"steps": [{"tool_name": "chapter.rewrite", "order": 1}]},
        planner_id="provider:planner",
        rationale="先诊断后重写",
    )
    revised = await plan_service.create_revision(
        run=run,
        session=session,
        context_snapshot=context,
        parent_revision=initial,
        plan_json={"steps": [{"tool_name": "chapter.rewrite", "order": 1}, {"tool_name": "quality.check", "order": 2}]},
        planner_id="provider:planner",
        rationale="补充质量门",
    )
    assert (initial.revision_number, revised.revision_number) == (1, 2)
    assert revised.parent_revision_id == initial.id
    assert revised.context_snapshot_id == context.id
    await plan_service.verify_revision(revised)

    conversation_service = AgentConversationService(task_session)
    summary = await conversation_service.create_summary(
        session=session,
        run=run,
        start_message_sequence=1,
        end_message_sequence=3,
        summary_text="用户要改写第一章，并要求保留悬念。",
        summary_json={"goals": ["改写", "悬念"]},
        summarizer_id="provider:summary",
    )
    assert summary.message_count == 3
    assert summary.run_id == run.id
    assert summary.correlation_id == run.correlation_id
    await conversation_service.verify_summary(summary, verify_source=True)

    assert await context_service.get_snapshot(context.snapshot_id) is context
    assert await plan_service.get_revision(revised.revision_id) is revised
    assert await conversation_service.get_summary(summary.summary_id) is summary
    assert user.id == context.user_id


@pytest.mark.asyncio
async def test_p1a_scope_range_parent_and_database_constraints_are_enforced(task_session):
    _user, session, run = await _run_with_messages(task_session, user_id=2851)
    runtime = AgentRuntimeService(task_session)
    other_session = await runtime.create_session(user_id=session.user_id, title="other")
    other_run = await runtime.create_run(session_id=other_session.id, user_id=session.user_id)
    context_service = AgentContextService(task_session)
    context = await context_service.create_snapshot(
        run=run, session=session, context_json={"goal": "x"},
        refs=[{"kind": "chapter", "chapter_id": "chapter-existing"}],
    )
    other_context = await context_service.create_snapshot(run=other_run, session=other_session, context_json={"goal": "y"})
    plan_service = AgentPlanService(task_session)
    initial = await plan_service.create_revision(run=run, session=session, context_snapshot=context, plan_json={"steps": []})

    with pytest.raises(AgentPlanIntegrityError):
        await plan_service.create_revision(
            run=run, session=session, context_snapshot=context, parent_revision=await plan_service.create_revision(
                run=other_run, session=other_session, context_snapshot=other_context, plan_json={"steps": []}
            ), plan_json={"steps": []}
        )
    with pytest.raises(AgentPlanIntegrityError):
        await plan_service.create_revision(
            run=run, session=session, context_snapshot=other_context, plan_json={"steps": []}
        )
    assert initial.revision_number == 1

    conversation_service = AgentConversationService(task_session)
    with pytest.raises(AgentConversationIntegrityError):
        await conversation_service.create_summary(
            session=session, start_message_sequence=1, end_message_sequence=4, summary_text="缺少消息"
        )
    with pytest.raises(AgentConversationIntegrityError):
        await conversation_service.create_summary(
            session=other_session, run=run, start_message_sequence=1, end_message_sequence=1, summary_text="越界"
        )

    session_id = session.id
    session_user_id = session.user_id
    duplicate_ref = ContextSnapshotRef(
        context_snapshot_id=context.id,
        ref_order=0,
        ref_type="chapter",
        ref_key="chapter-1",
        payload_json={},
        digest="a" * 64,
    )
    task_session.add(duplicate_ref)
    with pytest.raises(IntegrityError):
        await task_session.flush()
    await task_session.rollback()

    invalid_summary = ConversationSummary(
        summary_id="invalid-summary-2851",
        session_id=session_id,
        user_id=session_user_id,
        start_message_sequence=3,
        end_message_sequence=2,
        message_count=1,
        source_digest="a" * 64,
        summary_text="x",
        summary_json={},
        digest="b" * 64,
    )
    task_session.add(invalid_summary)
    with pytest.raises(IntegrityError):
        await task_session.flush()
    await task_session.rollback()


@pytest.mark.asyncio
async def test_p1a_digest_reverse_modification_is_detected_and_persisted_facts_reject_updates(task_session):
    _user, session, run = await _run_with_messages(task_session, user_id=2852)
    context_service = AgentContextService(task_session)
    context = await context_service.create_snapshot(
        run=run,
        session=session,
        context_json={"goal": "原始目标"},
        refs=[{"kind": "chapter", "chapter_id": "chapter-1"}],
    )
    plan_service = AgentPlanService(task_session)
    plan = await plan_service.create_revision(run=run, session=session, context_snapshot=context, plan_json={"steps": []})
    conversation_service = AgentConversationService(task_session)
    summary = await conversation_service.create_summary(
        session=session, run=run, start_message_sequence=1, end_message_sequence=3, summary_text="原始摘要"
    )

    original_context = context.context_json
    context_snapshot_id = context.snapshot_id
    plan_revision_id = plan.revision_id
    conversation_summary_id = summary.summary_id
    await task_session.commit()
    context.context_json = {"goal": "被篡改"}
    with pytest.raises(AgentContextIntegrityError, match="digest mismatch"):
        await context_service.verify_snapshot(context)
    with pytest.raises(AgentImmutableFactError):
        await task_session.flush()
    await task_session.rollback()

    context = await context_service.get_snapshot(context_snapshot_id)
    assert context is not None
    assert context.context_json == original_context
    plan = await plan_service.get_revision(plan_revision_id)
    assert plan is not None
    plan.plan_json = {"steps": [{"tool_name": "tampered"}]}
    with pytest.raises(AgentPlanIntegrityError, match="digest mismatch"):
        await plan_service.verify_revision(plan)
    with pytest.raises(AgentImmutableFactError):
        await task_session.flush()
    await task_session.rollback()

    summary = await conversation_service.get_summary(conversation_summary_id)
    assert summary is not None
    summary.summary_text = "被篡改摘要"
    with pytest.raises(AgentConversationIntegrityError, match="digest mismatch"):
        await conversation_service.verify_summary(summary)
    with pytest.raises(AgentImmutableFactError):
        await task_session.flush()
    await task_session.rollback()


def test_p1a_model_contract_declares_run_session_parent_refs_and_message_ranges():
    assert ContextSnapshot.__tablename__ == "agent_context_snapshots"
    assert ContextSnapshotRef.__tablename__ == "agent_context_snapshot_refs"
    assert PlanRevision.__tablename__ == "agent_plan_revisions"
    assert ConversationSummary.__tablename__ == "agent_conversation_summaries"
    context_targets = {fk.target_fullname for fk in ContextSnapshot.__table__.foreign_keys}
    plan_targets = {fk.target_fullname for fk in PlanRevision.__table__.foreign_keys}
    summary_targets = {fk.target_fullname for fk in ConversationSummary.__table__.foreign_keys}
    assert {"agent_runs.id", "agent_sessions.id"} <= context_targets
    assert {"agent_runs.id", "agent_sessions.id", "agent_context_snapshots.id", "agent_plan_revisions.id"} <= plan_targets
    assert {"agent_runs.id", "agent_sessions.id"} <= summary_targets
    assert "start_message_sequence" in ConversationSummary.__table__.c
    assert "end_message_sequence" in ConversationSummary.__table__.c
