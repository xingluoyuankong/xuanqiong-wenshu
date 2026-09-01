from __future__ import annotations

import asyncio
import json
import os
import socket
import time
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ...agent.executor import UnknownAgentTool, build_agent_plan
from ...agent.execution import launch_agent_execution, recover_agent_execution
from ...agent.jobs import AgentJobError, AgentJobNotFound, AgentJobService
from ...agent.orchestrator import AgentOrchestrator
from ...agent.policy import ProjectScopeViolation
from ...agent.registry import DEFAULT_TOOL_REGISTRY, get_default_tool_catalog, get_default_tool_provider_health
from ...agent.runner import cancel_visible_response, get_cancel_event, is_visible_response_active, launch_visible_response, release_cancel_event, recover_visible_response
from ...agent.state_projection import AgentStateProjectionService
from ...agent.write_executor import accept_candidate_artifact, diff_artifact_with_chapter_version, diff_artifacts, execute_approved_write, list_artifact_quality_blockers, list_artifact_rewrite_instructions, read_artifact_content
from ...agent.context_refs import ContextRefValidationError, project_plan_arguments, resolve_agent_context_refs
from ...agent.tool_adapters import execute_read_tool
from ...agent.schemas import (
    AgentApprovalDecisionRequest, AgentApprovalRead, AgentArtifactAcceptRequest, AgentArtifactDiffRead, AgentArtifactRead, AgentArtifactVersionDiffRead, AgentEventRead, AgentMessageCreateRequest,
    AgentAuditRecordRead, AgentJobRead, AgentRewriteInstructionRead, AgentMessageRead, AgentPlan, AgentPlanRequest, AgentPlanStep, AgentQualityBlockerRead, AgentArtifactQualityRead, AgentArtifactLineageRead, AgentArtifactLineageEdgeRead, AgentArtifactLineageArtifactRead, AgentQualityFindingRead, AgentQualityGateRead, AgentQualityResultRead, AgentRunRead, AgentRunStepRead, AgentTimelineEventRead,
    AgentSessionCreateRequest, AgentSessionDetail, AgentSessionRead, AgentToolCatalog, AgentToolHealthRead,
    AgentRunCommandRequest, AgentRunCommandRead, AgentContextSnapshotRead, AgentPlanRevisionRead, AgentConversationSummaryRead, AgentProviderProvenanceRead, AgentProjectEntitySummariesRead,
)
from ...core.config import settings
from ...core.dependencies import get_current_admin, get_current_user
from ...db.session import AsyncSessionLocal, get_session
from ...models.agent import AgentArtifactRef, AgentRun
from ...schemas.user import UserInDB
from ...services.llm_service import LLMService
from ...services.agent_context_service import AgentContextService
from ...services.agent_plan_service import AgentPlanService
from ...services.agent_conversation_service import AgentConversationService
from ...services.agent_quality_query_service import AgentQualityQueryService
from ...services.agent_entity_context_service import AgentEntityContextService
from ...services.agent_runtime import (
    AgentConflict, AgentNotFound, AgentRuntimeError, AgentRuntimeService, AgentScopeViolation,
)

router = APIRouter(prefix="/api/agent", tags=["agent"])
_STEP_WORKER_ID = f"api:{socket.gethostname()}:{os.getpid()}"[:128]
# AgentEventRecord.sequence is a signed SQL INTEGER; keep untrusted SSE
# cursors inside that range before they reach the database driver.
MAX_AGENT_STREAM_CURSOR = 2_147_483_647


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, ContextRefValidationError):
        return HTTPException(status_code=422, detail={"code": "AGENT_CONTEXT_REF_INVALID", "message": str(exc)})
    if isinstance(exc, AgentNotFound):
        return HTTPException(status_code=404, detail={"code": "AGENT_NOT_FOUND", "message": str(exc)})
    if isinstance(exc, (AgentScopeViolation, ProjectScopeViolation)):
        return HTTPException(status_code=403, detail={"code": "AGENT_SCOPE_VIOLATION", "message": str(exc)})
    if isinstance(exc, SQLAlchemyError):
        return HTTPException(
            status_code=503,
            detail={
                "code": "AGENT_EVENT_LEDGER_UNAVAILABLE",
                "message": "Agent 事件账本暂时不可用，请稍后重连。",
            },
        )
    if isinstance(exc, AgentJobNotFound):
        return HTTPException(status_code=404, detail={"code": "AGENT_JOB_NOT_FOUND", "message": str(exc)})
    if isinstance(exc, AgentJobError):
        return HTTPException(status_code=409, detail={"code": "AGENT_JOB_CONFLICT", "message": str(exc)})
    return HTTPException(status_code=409, detail={"code": "AGENT_CONFLICT", "message": str(exc)})


async def _execute_registered_approval(*, approval_id: str, session: AsyncSession, user_id: int):
    approval = await AgentRuntimeService(session).get_approval(approval_id=approval_id, user_id=user_id)
    arguments = dict(approval.request_json or {})
    arguments["_approval_id"] = approval.id
    result = await DEFAULT_TOOL_REGISTRY.execute(
        approval.tool_name,
        session=session,
        user_id=user_id,
        project_id=approval.project_id,
        arguments=arguments,
    )
    artifact = result.get("artifact") if isinstance(result, dict) else None
    if artifact is None:
        raise AgentConflict("write handler did not return an artifact")
    return artifact



def _lineage_artifact_read(artifact: AgentArtifactRef) -> AgentArtifactLineageArtifactRead:
    return AgentArtifactLineageArtifactRead.model_validate(artifact)


def _lineage_edge_read(edge) -> AgentArtifactLineageEdgeRead:
    return AgentArtifactLineageEdgeRead(
        id=edge.id,
        lineage_id=edge.lineage_id,
        run_id=edge.run_id,
        correlation_id=edge.correlation_id,
        transaction_id=edge.transaction_id,
        relation_type=edge.relation_type,
        operation=edge.operation,
        input_digest=edge.input_digest,
        output_digest=edge.output_digest,
        metadata_json=dict(edge.metadata_json or {}),
        created_at=edge.created_at,
        source_artifact=_lineage_artifact_read(edge.source_artifact_ref),
        derived_artifact=_lineage_artifact_read(edge.derived_artifact_ref),
    )

@router.get("/tools", response_model=AgentToolCatalog)
async def list_agent_tools(current_user: UserInDB = Depends(get_current_user)) -> AgentToolCatalog:
    del current_user
    return AgentToolCatalog(**get_default_tool_catalog())


@router.get("/tools/health", response_model=AgentToolHealthRead)
async def list_agent_tool_health(current_admin: UserInDB = Depends(get_current_admin)) -> AgentToolHealthRead:
    del current_admin
    providers = get_default_tool_provider_health()
    return {
        "registry_status": "healthy" if not any(item.get("status") == "failed" for item in providers) else "degraded",
        "provider_count": len(providers),
        "providers": providers,
    }


@router.post("/plan", response_model=AgentPlan)
async def create_agent_plan(payload: AgentPlanRequest, current_user: UserInDB = Depends(get_current_user)) -> AgentPlan:
    try:
        return build_agent_plan(payload, user_id=current_user.id)
    except UnknownAgentTool as exc:
        raise HTTPException(status_code=404, detail={"code": "AGENT_TOOL_NOT_FOUND", "message": str(exc)}) from exc
    except ProjectScopeViolation as exc:
        raise HTTPException(status_code=403, detail={"code": "AGENT_PROJECT_SCOPE_VIOLATION", "message": str(exc)}) from exc


@router.post("/sessions", response_model=AgentSessionRead, status_code=status.HTTP_201_CREATED)
async def create_agent_session(payload: AgentSessionCreateRequest, session: AsyncSession = Depends(get_session), current_user: UserInDB = Depends(get_current_user)) -> AgentSessionRead:
    try:
        return await AgentRuntimeService(session).create_session(user_id=current_user.id, project_id=payload.project_id, title=payload.title)
    except (AgentRuntimeError, SQLAlchemyError) as exc:
        raise _error(exc) from exc


@router.get("/projects/{project_id}/entity-summaries", response_model=AgentProjectEntitySummariesRead)
async def list_agent_project_entity_summaries(
    project_id: str,
    per_kind_limit: Annotated[int, Query(ge=1, le=100)] = 40,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> AgentProjectEntitySummariesRead:
    """List bounded, label-only entities that the author may add as ContextRefs."""
    try:
        entities = await AgentEntityContextService(session).list_project_entity_summaries(
            project_id=project_id,
            user_id=current_user.id,
            per_kind_limit=per_kind_limit,
        )
        return AgentProjectEntitySummariesRead(project_id=project_id, entities=entities)
    except Exception as exc:
        raise _error(exc)

@router.get("/sessions", response_model=list[AgentSessionRead])
async def list_agent_sessions(project_id: str | None = Query(default=None), limit: Annotated[int, Query(ge=1, le=100)] = 50, session: AsyncSession = Depends(get_session), current_user: UserInDB = Depends(get_current_user)) -> list[AgentSessionRead]:
    try:
        return await AgentRuntimeService(session).list_sessions(user_id=current_user.id, project_id=project_id, limit=limit)
    except (AgentRuntimeError, SQLAlchemyError) as exc:
        raise _error(exc) from exc


@router.post("/sessions/{session_id}/archive", response_model=AgentSessionRead)
async def archive_agent_session(session_id: str, session: AsyncSession = Depends(get_session), current_user: UserInDB = Depends(get_current_user)) -> AgentSessionRead:
    try:
        return await AgentRuntimeService(session).archive_session(session_id=session_id, user_id=current_user.id)
    except (AgentRuntimeError, SQLAlchemyError) as exc:
        raise _error(exc) from exc


@router.get("/sessions/{session_id}", response_model=AgentSessionDetail)
async def get_agent_session(session_id: str, session: AsyncSession = Depends(get_session), current_user: UserInDB = Depends(get_current_user)) -> AgentSessionDetail:
    try:
        service = AgentRuntimeService(session)
        item = await service.get_session(session_id, current_user.id)
        messages = await service.list_messages(session_id=session_id, user_id=current_user.id)
        runs = list((await session.execute(select(AgentRun).where(AgentRun.session_id == session_id, AgentRun.user_id == current_user.id).order_by(AgentRun.created_at.asc()))).scalars().all())
        payload = {"id": item.id, "user_id": item.user_id, "project_id": item.project_id, "title": item.title, "status": item.status, "created_at": item.created_at, "updated_at": item.updated_at, "messages": messages, "runs": runs}
        return AgentSessionDetail.model_validate(payload)
    except (AgentRuntimeError, SQLAlchemyError) as exc:
        raise _error(exc) from exc


@router.post("/sessions/{session_id}/messages", response_model=dict, status_code=status.HTTP_201_CREATED)
async def post_agent_message(session_id: str, payload: AgentMessageCreateRequest, session: AsyncSession = Depends(get_session), current_user: UserInDB = Depends(get_current_user)) -> dict:
    """Persist a Run and durable execution intent before Provider planning starts.

    The browser receives the Run immediately and then observes planner/read/suggest
    work through the durable event stream.  The worker reconstructs ContextRef and
    performs manifest projection again before executing anything.
    """
    run_id_for_cleanup: str | None = None
    inline_execution_launched = False
    transaction_started = False
    try:
        service = AgentRuntimeService(session)
        item = await service.get_session(session_id, current_user.id)
        resolved_context = await resolve_agent_context_refs(
            session=session,
            user_id=current_user.id,
            session_project_id=item.project_id,
            refs=payload.context_refs,
        )
        transaction_started = True
        user_message = await service.append_message(
            session_id=session_id,
            user_id=current_user.id,
            role="user",
            content=payload.content,
            commit=False,
        )
        initial_context = {
            "goal": payload.content,
            "context_refs": resolved_context.canonical_refs(),
            "requested_tools": list(payload.tools),
            "arguments": dict(payload.arguments),
            "tool_arguments": {str(name): dict(value) for name, value in payload.tool_arguments.items()},
            "tool_results": [],
            "plan_steps": [],
        }
        run = await service.create_run(
            session_id=session_id,
            user_id=current_user.id,
            project_id=item.project_id,
            context=initial_context,
            commit=False,
        )
        run_id_for_cleanup = run.id
        await service.update_run(
            run_id=run.id,
            user_id=current_user.id,
            status="planning",
            phase="queued",
            progress=10,
            commit=False,
        )
        await service.append_event(
            run_id=run.id,
            user_id=current_user.id,
            event_type="run_started",
            summary="已接受创作目标，已排入 Agent 执行队列",
            data={"phase": "queued"},
            commit=False,
        )
        await service.publish_progress(
            run_id=run.id,
            user_id=current_user.id,
            status="planning",
            phase="queued",
            progress=10,
            progress_message="已接受创作目标，正在等待 Agent 执行器。",
            commit=False,
        )
        if resolved_context.refs:
            await service.append_event(
                run_id=run.id,
                user_id=current_user.id,
                event_type="context_resolved",
                summary=f"已关联 {len(resolved_context.refs)} 条项目上下文",
                data={
                    "context_count": len(resolved_context.refs),
                    "context_kinds": ",".join(ref.kind for ref in resolved_context.refs),
                    "phase": "queued",
                },
                commit=False,
            )
        execution_job = await AgentJobService(session).create_job(
            run_id=run.id,
            user_id=current_user.id,
            project_id=item.project_id,
            kind="agent_execution",
            idempotency_key=f"{run.id}:agent_execution",
            payload={"run_id": run.id, "phase": "planning", "transaction_id": run.correlation_id},
            commit=False,
        )
        await service.set_run_context(
            run_id=run.id,
            user_id=current_user.id,
            context={**initial_context, "execution_job_id": execution_job.id, "job_id": execution_job.id, "transaction_id": run.correlation_id},
            commit=False,
        )
        await session.commit()
        await session.refresh(user_message)
        await session.refresh(execution_job)
        run = await service.get_run(run.id, current_user.id)
        queued_plan = AgentPlan(
            goal=payload.content,
            project_id=item.project_id,
            mode="explore",
            created_by_user_id=current_user.id,
            steps=[],
            events=[],
            provider_called=False,
        )
        if settings.agent_inline_execution:
            launch_agent_execution(job_id=execution_job.id, run_id=run.id, user_id=current_user.id)
            inline_execution_launched = True
        return {
            "message": AgentMessageRead.model_validate(user_message),
            "assistant_message": None,
            "run": AgentRunRead.model_validate(run),
            "plan": queued_plan,
            "tool_results": [],
            "provider_called": False,
            "planner_fallback_reason": None,
            "approvals": [],
            "execution_job": AgentJobRead.model_validate(execution_job),
        }
    except (AgentRuntimeError, UnknownAgentTool, ProjectScopeViolation, ContextRefValidationError, SQLAlchemyError) as exc:
        if transaction_started:
            await session.rollback()
        raise _error(exc) from exc
    finally:
        if run_id_for_cleanup and not inline_execution_launched:
            release_cancel_event(run_id_for_cleanup)


@router.get('/timeline', response_model=list[AgentTimelineEventRead])
async def list_agent_timeline(
    project_id: str | None = Query(default=None, min_length=1, max_length=120),
    session_id: str | None = Query(default=None, min_length=1, max_length=36),
    run_id: str | None = Query(default=None, min_length=1, max_length=36),
    event_type: str | None = Query(default=None, min_length=1, max_length=64),
    run_status: str | None = Query(default=None, min_length=1, max_length=24),
    tool_name: str | None = Query(default=None, min_length=1, max_length=120),
    offset: Annotated[int, Query(ge=0, le=100000)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> list[AgentTimelineEventRead]:
    rows = await AgentRuntimeService(session).list_timeline(
        user_id=current_user.id,
        project_id=project_id,
        session_id=session_id,
        run_id=run_id,
        event_type=event_type,
        run_status=run_status,
        tool_name=tool_name,
        offset=offset,
        limit=limit,
    )
    return [
        AgentTimelineEventRead(
            id=event.id,
            session_id=resolved_session_id,
            run_id=event.run_id,
            user_id=event.user_id,
            project_id=resolved_project_id,
            run_status=resolved_run_status,
            event_type=event.event_type,
            sequence=event.sequence,
            summary=event.summary,
            tool_name=(event.data_json or {}).get('tool_name'),
            data_json=event.data_json,
            created_at=event.created_at,
        )
        for event, resolved_session_id, resolved_project_id, resolved_run_status in rows
    ]

@router.get('/jobs', response_model=list[AgentJobRead])
async def list_agent_jobs(
    project_id: str | None = Query(default=None, min_length=1, max_length=120),
    status: str | None = Query(default=None, min_length=1, max_length=24),
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> list[AgentJobRead]:
    try:
        rows = await AgentJobService(session).list_jobs(user_id=current_user.id, project_id=project_id, status=status)
        return [AgentJobRead.model_validate(item) for item in rows]
    except (AgentJobError, SQLAlchemyError) as exc:
        raise _error(exc) from exc


@router.post('/jobs/{job_id}/cancel', response_model=AgentJobRead)
async def cancel_agent_job(
    job_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> AgentJobRead:
    try:
        row = await AgentJobService(session).request_cancel(job_id=job_id, user_id=current_user.id)
        return AgentJobRead.model_validate(row)
    except (AgentJobError, SQLAlchemyError) as exc:
        raise _error(exc) from exc


@router.get("/dead-letters", response_model=list[AgentJobRead])
async def list_agent_dead_letters(
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    session: AsyncSession = Depends(get_session),
    _: UserInDB = Depends(get_current_admin),
) -> list[AgentJobRead]:
    try:
        rows = await AgentJobService(session).list_dead_letters(limit=limit)
        return [AgentJobRead.model_validate(item) for item in rows]
    except (AgentJobError, SQLAlchemyError) as exc:
        raise _error(exc) from exc


@router.post("/dead-letters/{job_id}/replay", response_model=AgentJobRead)
async def replay_agent_dead_letter(
    job_id: str,
    reason: str | None = Query(default=None, max_length=255),
    session: AsyncSession = Depends(get_session),
    current_admin: UserInDB = Depends(get_current_admin),
) -> AgentJobRead:
    try:
        row = await AgentJobService(session).replay_dead_letter(
            job_id=job_id,
            operator_id=current_admin.id,
            reason=reason,
        )
        return AgentJobRead.model_validate(row)
    except (AgentJobError, SQLAlchemyError) as exc:
        raise _error(exc) from exc

@router.get("/audit", response_model=list[AgentAuditRecordRead])
async def list_agent_audit(
    project_id: str | None = Query(default=None, min_length=1, max_length=120),
    session_id: str | None = Query(default=None, min_length=1, max_length=36),
    run_id: str | None = Query(default=None, min_length=1, max_length=36),
    event_type: str | None = Query(default=None, min_length=1, max_length=64),
    run_status: str | None = Query(default=None, min_length=1, max_length=24),
    tool_name: str | None = Query(default=None, min_length=1, max_length=120),
    approval_id: str | None = Query(default=None, min_length=1, max_length=36),
    artifact_id: str | None = Query(default=None, min_length=1, max_length=36),
    source_version_id: int | None = Query(default=None, ge=1),
    offset: Annotated[int, Query(ge=0, le=100000)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> list[AgentAuditRecordRead]:
    rows = await AgentRuntimeService(session).list_audit_ledger(
        user_id=current_user.id,
        project_id=project_id,
        session_id=session_id,
        run_id=run_id,
        event_type=event_type,
        run_status=run_status,
        tool_name=tool_name,
        approval_id=approval_id,
        artifact_id=artifact_id,
        source_version_id=source_version_id,
        offset=offset,
        limit=limit,
    )
    return [AgentAuditRecordRead.model_validate(item) for item in rows]


@router.get("/sessions/{session_id}/runs/{run_id}/events", response_model=list[AgentEventRead])
async def list_agent_events(session_id: str, run_id: str, after_sequence: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=500)] = 500, session: AsyncSession = Depends(get_session), current_user: UserInDB = Depends(get_current_user)) -> list[AgentEventRead]:
    try:
        service = AgentRuntimeService(session)
        item = await service.get_session(session_id, current_user.id)
        run = await service.get_run(run_id, current_user.id)
        if run.session_id != item.id:
            raise AgentScopeViolation("run does not belong to session")
        return await service.list_events(run_id=run_id, user_id=current_user.id, after_sequence=after_sequence, limit=limit)
    except (AgentRuntimeError, SQLAlchemyError) as exc:
        raise _error(exc) from exc


def resolve_agent_stream_cursor(last_event_id: str | None, after_sequence: int = 0) -> int:
    """Resolve the durable SSE cursor, preferring the browser's Last-Event-ID.

    ``Last-Event-ID`` is an HTTP header and therefore arrives as untrusted text.
    A blank, non-integer, or negative header is ignored so a reconnect can still
    fall back to the validated query cursor (or zero).
    """
    try:
        fallback = min(max(0, int(after_sequence)), MAX_AGENT_STREAM_CURSOR)
    except (TypeError, ValueError, OverflowError):
        fallback = 0
    if last_event_id is None:
        return fallback
    value = last_event_id.strip()
    if not value:
        return fallback
    if not value.isascii() or not value.isdigit():
        return fallback
    try:
        cursor = int(value, 10)
    except (TypeError, ValueError, OverflowError):
        return fallback
    return cursor if 0 <= cursor <= MAX_AGENT_STREAM_CURSOR else fallback


async def _validate_agent_stream_scope(*, session_id: str, run_id: str, user_id: int) -> None:
    """Validate stream ownership before sending response headers."""
    async with AsyncSessionLocal() as db:
        service = AgentRuntimeService(db)
        item = await service.get_session(session_id, user_id)
        run = await service.get_run(run_id, user_id)
        if run.session_id != item.id:
            raise AgentScopeViolation("run does not belong to session")


@router.get("/sessions/{session_id}/runs/{run_id}/stream")
async def stream_agent_events(session_id: str, run_id: str, request: Request, after_sequence: Annotated[int, Query(ge=0)] = 0, current_user: UserInDB = Depends(get_current_user)) -> StreamingResponse:
    user_id = current_user.id
    # A disconnected client should not trigger a database preflight.
    if not await request.is_disconnected():
        try:
            await _validate_agent_stream_scope(session_id=session_id, run_id=run_id, user_id=user_id)
        except (AgentRuntimeError, SQLAlchemyError) as exc:
            raise _error(exc) from exc
    initial_cursor = resolve_agent_stream_cursor(request.headers.get("last-event-id"), after_sequence)

    async def event_generator():
        cursor = initial_cursor
        last_heartbeat = time.monotonic()
        while not await request.is_disconnected():
            async with AsyncSessionLocal() as db:
                service = AgentRuntimeService(db)
                try:
                    item = await service.get_session(session_id, user_id)
                    run = await service.get_run(run_id, user_id)
                    if run.session_id != item.id:
                        return
                    events = await service.list_events(run_id=run_id, user_id=user_id, after_sequence=cursor, limit=500)
                except AgentRuntimeError:
                    return
                except SQLAlchemyError:
                    # Do not expose driver text or advance the durable cursor.
                    # The client can reconnect from its last acknowledged event.
                    payload = {
                        "run_id": run_id,
                        "error_code": "AGENT_EVENT_LEDGER_UNAVAILABLE",
                        "retryable": True,
                        "cursor": cursor,
                    }
                    yield f"event: stream_error\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    return
            for event in events:
                cursor = max(cursor, event.sequence)
                payload = {"id": event.id, "run_id": event.run_id, "sequence": event.sequence, "event_type": event.event_type, "summary": event.summary, "data": event.data_json, "created_at": event.created_at.isoformat() if event.created_at else None}
                yield f"id: {event.sequence}\nevent: {event.event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            if run.status in {"completed", "failed", "cancelled"}:
                # A terminal run has no future events.  When a full page was
                # returned, continue once more so a large durable history is
                # not truncated; otherwise the final event has just been sent
                # and the stream can close without another polling round.
                if not events or len(events) < 500:
                    return
            if time.monotonic() - last_heartbeat >= 15:
                yield ": keepalive\n\n"
                last_heartbeat = time.monotonic()
            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})


@router.post("/runs/{run_id}/claim", response_model=AgentRunRead)
async def claim_agent_run(run_id: str, worker_id: str = Query(min_length=1, max_length=128), lease_seconds: int = Query(default=120, ge=1, le=3600), session: AsyncSession = Depends(get_session), current_user: UserInDB = Depends(get_current_user)) -> AgentRunRead:
    try:
        return await AgentRuntimeService(session).claim_run(run_id=run_id, user_id=current_user.id, lease_owner=worker_id, lease_seconds=lease_seconds)
    except (AgentRuntimeError, SQLAlchemyError) as exc:
        raise _error(exc) from exc


@router.post("/runs/{run_id}/release", response_model=AgentRunRead)
async def release_agent_run(run_id: str, worker_id: str = Query(min_length=1, max_length=128), session: AsyncSession = Depends(get_session), current_user: UserInDB = Depends(get_current_user)) -> AgentRunRead:
    try:
        return await AgentRuntimeService(session).release_run(run_id=run_id, user_id=current_user.id, lease_owner=worker_id)
    except (AgentRuntimeError, SQLAlchemyError) as exc:
        raise _error(exc) from exc


@router.post("/runs/{run_id}/recover", response_model=AgentRunRead)
async def recover_agent_run(run_id: str, session: AsyncSession = Depends(get_session), current_user: UserInDB = Depends(get_current_user)) -> AgentRunRead:
    try:
        recovered = await recover_agent_execution(run_id=run_id, user_id=current_user.id)
        if not recovered:
            recovered = await recover_visible_response(run_id=run_id, user_id=current_user.id)
        run = await AgentRuntimeService(session).get_run(run_id, current_user.id)
        return AgentRunRead.model_validate(run)
    except (AgentRuntimeError, SQLAlchemyError) as exc:
        raise _error(exc) from exc


async def _apply_cancel_side_effects(run: AgentRun, *, session: AsyncSession, user_id: int) -> None:
    errors: list[tuple[str, str]] = []
    try:
        await AgentJobService(session).request_cancel_for_run(
            run_id=run.id,
            user_id=user_id,
            reason=run.cancel_reason or "user_requested",
        )
    except Exception as exc:
        errors.append((type(exc).__name__, str(exc)[:200]))
    try:
        cancel_visible_response(run.id)
    except Exception as exc:
        errors.append((type(exc).__name__, str(exc)[:200]))
    runtime = AgentRuntimeService(session)
    for error_type, detail in errors:
        try:
            await runtime.append_event(
                run_id=run.id,
                user_id=user_id,
                event_type="cancellation_side_effect_failed",
                summary="Agent 取消副作用执行异常，运行保留在收敛阶段",
                data={"error_type": error_type, "phase": "cancelling"},
            )
        except Exception:
            pass
    try:
        await runtime.finalize_cancellation(
            run_id=run.id,
            user_id=user_id,
            visible_response_active=is_visible_response_active(run.id),
        )
    except Exception as exc:
        try:
            await runtime.append_event(
                run_id=run.id,
                user_id=user_id,
                event_type="cancellation_side_effect_failed",
                summary="Agent 取消收敛检查失败，等待后续恢复器重试",
                data={"error_type": type(exc).__name__, "phase": "cancelling"},
            )
        except Exception:
            pass


@router.get("/runs/{run_id}/commands", response_model=list[AgentRunCommandRead])
async def list_agent_run_commands(
    run_id: str,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> list[AgentRunCommandRead]:
    try:
        commands = await AgentRuntimeService(session).list_run_commands(
            run_id=run_id,
            user_id=current_user.id,
            limit=limit,
        )
        return [AgentRunCommandRead.model_validate(item) for item in commands]
    except (AgentRuntimeError, SQLAlchemyError) as exc:
        raise _error(exc) from exc


@router.post("/runs/{run_id}/commands", response_model=AgentRunCommandRead, status_code=status.HTTP_201_CREATED)
async def submit_agent_run_command(
    run_id: str,
    request: AgentRunCommandRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> AgentRunCommandRead:
    try:
        runtime = AgentRuntimeService(session)
        command = await runtime.submit_run_command(
            run_id=run_id,
            user_id=current_user.id,
            command_type=request.command_type,
            reason=request.reason,
            payload=request.payload_json,
            idempotency_key=request.idempotency_key,
            expected_state_version=request.expected_state_version,
            apply=request.execution_mode == "inline",
        )
        if command.command_type == "cancel" and command.status == "applied":
            await _apply_cancel_side_effects(
                await runtime.get_run(run_id, current_user.id),
                session=session,
                user_id=current_user.id,
            )
        return AgentRunCommandRead.model_validate(command)
    except (AgentRuntimeError, SQLAlchemyError) as exc:
        raise _error(exc) from exc


@router.post("/runs/{run_id}/pause", response_model=AgentRunRead)
async def pause_agent_run(run_id: str, session: AsyncSession = Depends(get_session), current_user: UserInDB = Depends(get_current_user)) -> AgentRunRead:
    try:
        return await AgentRuntimeService(session).pause_run(run_id=run_id, user_id=current_user.id)
    except (AgentRuntimeError, SQLAlchemyError) as exc:
        raise _error(exc) from exc


@router.post("/runs/{run_id}/resume", response_model=AgentRunRead)
async def resume_agent_run(run_id: str, session: AsyncSession = Depends(get_session), current_user: UserInDB = Depends(get_current_user)) -> AgentRunRead:
    try:
        return await AgentRuntimeService(session).resume_run(run_id=run_id, user_id=current_user.id)
    except (AgentRuntimeError, SQLAlchemyError) as exc:
        raise _error(exc) from exc


@router.post("/runs/{run_id}/cancel", response_model=AgentRunRead)
async def cancel_agent_run(run_id: str, session: AsyncSession = Depends(get_session), current_user: UserInDB = Depends(get_current_user)) -> AgentRunRead:
    try:
        runtime = AgentRuntimeService(session)
        run = await runtime.cancel_run(run_id=run_id, user_id=current_user.id)
        await _apply_cancel_side_effects(run, session=session, user_id=current_user.id)
        return run
    except (AgentRuntimeError, SQLAlchemyError) as exc:
        raise _error(exc) from exc


@router.get("/runs/{run_id}/plan", response_model=AgentPlan)
async def get_agent_run_plan(
    run_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> AgentPlan:
    """Read the public structured PlanDraft persisted by agent_execution."""
    try:
        run = await AgentRuntimeService(session).get_run(run_id, current_user.id)
        context = dict(run.context_json or {})
        raw_steps = context.get("plan_steps") if isinstance(context.get("plan_steps"), list) else []
        steps: list[AgentPlanStep] = []
        for raw in sorted((item for item in raw_steps if isinstance(item, dict)), key=lambda item: int(item.get("order") or 0)):
            order = int(raw.get("order") or 0)
            tool_name = str(raw.get("tool_name") or "").strip()
            if order < 1 or not tool_name:
                continue
            try:
                tool = DEFAULT_TOOL_REGISTRY.get(tool_name)
            except KeyError as exc:
                raise AgentConflict(f"persisted plan references an unavailable tool: {tool_name}") from exc
            planner_arguments = raw.get("planner_arguments") if isinstance(raw.get("planner_arguments"), dict) else {}
            depends_on = raw.get("depends_on") if isinstance(raw.get("depends_on"), list) else []
            intent = str(raw.get("intent") or "").strip()[:500] or None
            expected_result = str(raw.get("expected_result") or "").strip()[:500] or None
            steps.append(
                AgentPlanStep(
                    order=order,
                    tool_name=tool.name,
                    description=intent or tool.description,
                    risk_level=tool.risk_level,
                    requires_confirmation=tool.requires_confirmation,
                    intent=intent,
                    expected_result=expected_result,
                    depends_on=depends_on,
                    planner_arguments=planner_arguments,
                )
            )
        mode = str(context.get("plan_mode") or "explore")
        if mode not in {"explore", "strict"}:
            mode = "explore"
        return AgentPlan(
            goal=str(context.get("goal") or ""),
            project_id=run.project_id,
            mode=mode,
            created_by_user_id=run.user_id,
            steps=steps,
            events=[],
            provider_called=bool(context.get("planner_provider_called")),
            planner_fallback_reason=(str(context.get("planner_fallback_reason"))[:160] if context.get("planner_fallback_reason") else None),
        )
    except (AgentRuntimeError, SQLAlchemyError) as exc:
        raise _error(exc) from exc


@router.get("/runs/{run_id}/provider-provenance", response_model=AgentProviderProvenanceRead)
async def get_agent_run_provider_provenance(
    run_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> AgentProviderProvenanceRead:
    """Return user-scoped stage provenance without asking clients to infer it from events."""
    try:
        run = await AgentRuntimeService(session).get_run(run_id, current_user.id)
        context = dict(run.context_json or {})
        return AgentProviderProvenanceRead(
            planner_provider_called=(bool(context["planner_provider_called"]) if context.get("planner_provider_called") is not None else None),
            planner_provider_fallback_reason=(str(context.get("planner_provider_fallback_reason") or context.get("planner_fallback_reason") or "")[:160] or None),
            response_provider_called=(bool(context["response_provider_called"]) if context.get("response_provider_called") is not None else None),
            response_provider_fallback_reason=(str(context.get("response_provider_fallback_reason") or "")[:160] or None),
            candidate_writer_provider_called=(bool(context["candidate_writer_provider_called"]) if context.get("candidate_writer_provider_called") is not None else None),
            candidate_writer_provider_fallback_reason=(str(context.get("candidate_writer_provider_fallback_reason") or "")[:160] or None),
            candidate_writer_model_ref=(str(context.get("candidate_writer_model_ref") or "")[:200] or None),
            candidate_writer_provider_attempts=(context.get("candidate_writer_provider_attempts") if isinstance(context.get("candidate_writer_provider_attempts"), dict) else None),
        )
    except (AgentRuntimeError, SQLAlchemyError) as exc:
        raise _error(exc) from exc


@router.get("/runs/{run_id}/context-snapshot", response_model=AgentContextSnapshotRead | None)
async def get_agent_run_context_snapshot(
    run_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> AgentContextSnapshotRead | None:
    """Return the latest persisted ContextSnapshot for a user-owned Run, or null before P1-A wiring exists."""
    try:
        run = await AgentRuntimeService(session).get_run(run_id, current_user.id)
        context = dict(run.context_json or {})
        snapshot_key = str(context.get("relational_context_snapshot_key") or "").strip()
        context_service = AgentContextService(session)
        snapshot = (
            await context_service.get_run_snapshot(run_id=run.id, snapshot_id=snapshot_key)
            if snapshot_key
            else await context_service.get_latest_snapshot_for_run(
                run_id=run.id, session_id=run.session_id, user_id=current_user.id
            )
        )
        if snapshot is not None and (snapshot.session_id != run.session_id or snapshot.user_id != current_user.id):
            snapshot = None
        return AgentContextSnapshotRead.model_validate(snapshot) if snapshot is not None else None
    except (AgentRuntimeError, SQLAlchemyError) as exc:
        raise _error(exc) from exc


@router.get("/runs/{run_id}/plan-revision", response_model=AgentPlanRevisionRead | None)
async def get_agent_run_latest_plan_revision(
    run_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> AgentPlanRevisionRead | None:
    """Return the newest persisted PlanRevision for a user-owned Run, or null for legacy/unwired Runs."""
    try:
        run = await AgentRuntimeService(session).get_run(run_id, current_user.id)
        revision = await AgentPlanService(session).get_latest_revision_for_run(
            run_id=run.id, session_id=run.session_id, user_id=current_user.id
        )
        return AgentPlanRevisionRead.model_validate(revision) if revision is not None else None
    except (AgentRuntimeError, SQLAlchemyError) as exc:
        raise _error(exc) from exc


@router.get("/runs/{run_id}/conversation-summaries", response_model=list[AgentConversationSummaryRead])
async def list_agent_run_conversation_summaries(
    run_id: str,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> list[AgentConversationSummaryRead]:
    """List immutable summaries explicitly attributed to a user-owned Run; legacy Runs return an empty list."""
    try:
        run = await AgentRuntimeService(session).get_run(run_id, current_user.id)
        summaries = await AgentConversationService(session).list_summaries_for_run(
            run_id=run.id, session_id=run.session_id, user_id=current_user.id, limit=limit
        )
        return [AgentConversationSummaryRead.model_validate(item) for item in summaries]
    except (AgentRuntimeError, SQLAlchemyError) as exc:
        raise _error(exc) from exc


@router.get("/runs/{run_id}/state")
async def get_agent_run_state(
    run_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> dict[str, object]:
    """Return the safe, read-only correlation state projection for one run."""
    try:
        return await AgentStateProjectionService(session).get_run_state(
            run_id=run_id, user_id=current_user.id
        )
    except (AgentRuntimeError, SQLAlchemyError) as exc:
        raise _error(exc) from exc


@router.get("/runs/{run_id}/activity", response_model=list[AgentEventRead])
async def list_agent_run_activity(
    run_id: str,
    after_sequence: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> list[AgentEventRead]:
    """Read the durable, replay-safe activity ledger for one user-owned Run."""
    try:
        return await AgentRuntimeService(session).list_events(
            run_id=run_id,
            user_id=current_user.id,
            after_sequence=after_sequence,
            limit=limit,
        )
    except (AgentRuntimeError, SQLAlchemyError) as exc:
        raise _error(exc) from exc


@router.get("/runs/{run_id}/approvals", response_model=list[AgentApprovalRead])
async def list_agent_approvals(run_id: str, session: AsyncSession = Depends(get_session), current_user: UserInDB = Depends(get_current_user)) -> list[AgentApprovalRead]:
    try:
        return await AgentRuntimeService(session).list_approvals(run_id=run_id, user_id=current_user.id)
    except (AgentRuntimeError, SQLAlchemyError) as exc:
        raise _error(exc) from exc


@router.get("/runs/{run_id}/steps", response_model=list[AgentRunStepRead])
async def list_agent_run_steps(run_id: str, session: AsyncSession = Depends(get_session), current_user: UserInDB = Depends(get_current_user)) -> list[AgentRunStepRead]:
    try:
        return await AgentRuntimeService(session).list_steps(run_id=run_id, user_id=current_user.id)
    except (AgentRuntimeError, SQLAlchemyError) as exc:
        raise _error(exc) from exc


@router.post("/approvals/{approval_id}/execute", response_model=AgentArtifactRead)
async def execute_agent_approval(approval_id: str, session: AsyncSession = Depends(get_session), current_user: UserInDB = Depends(get_current_user)) -> AgentArtifactRead:
    try:
        artifact = await _execute_registered_approval(approval_id=approval_id, session=session, user_id=current_user.id)
        return AgentArtifactRead.model_validate(artifact)
    except (AgentRuntimeError, SQLAlchemyError) as exc:
        raise _error(exc) from exc


@router.get('/artifacts/{artifact_id}/chapter-version-diff', response_model=AgentArtifactVersionDiffRead)
async def diff_agent_artifact_version(
    artifact_id: str,
    project_id: str = Query(min_length=1, max_length=120),
    chapter_number: int = Query(ge=1, le=1000000),
    version_id: int = Query(ge=1),
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> AgentArtifactVersionDiffRead:
    try:
        result = await diff_artifact_with_chapter_version(
            artifact_id=artifact_id,
            project_id=project_id,
            chapter_number=chapter_number,
            version_id=version_id,
            user_id=current_user.id,
            session=session,
        )
        return AgentArtifactVersionDiffRead.model_validate(result)
    except (AgentRuntimeError, SQLAlchemyError) as exc:
        raise _error(exc) from exc

@router.get('/artifacts/{artifact_id}/diff', response_model=AgentArtifactDiffRead)
async def diff_agent_artifact(
    artifact_id: str,
    against_artifact_id: str = Query(min_length=1, max_length=36),
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> AgentArtifactDiffRead:
    try:
        result = await diff_artifacts(artifact_id=artifact_id, against_artifact_id=against_artifact_id, user_id=current_user.id, session=session)
        return AgentArtifactDiffRead.model_validate(result)
    except (AgentRuntimeError, SQLAlchemyError) as exc:
        raise _error(exc) from exc

@router.get('/artifacts/{artifact_id}/quality', response_model=AgentArtifactQualityRead)
async def get_agent_artifact_quality(
    artifact_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> AgentArtifactQualityRead:
    try:
        facts = await AgentQualityQueryService(session).get_quality_facts(
            artifact_id=artifact_id,
            user_id=current_user.id,
        )
        return AgentArtifactQualityRead(
            artifact_id=facts.artifact.id,
            quality_result=(AgentQualityResultRead.model_validate(facts.result) if facts.result is not None else None),
            findings=[AgentQualityFindingRead.model_validate(item) for item in facts.findings],
            gate=(AgentQualityGateRead.model_validate(facts.gate) if facts.gate is not None else None),
        )
    except (AgentRuntimeError, SQLAlchemyError) as exc:
        raise _error(exc) from exc


@router.get('/artifacts/{artifact_id}/lineage', response_model=AgentArtifactLineageRead)
async def get_agent_artifact_lineage(
    artifact_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> AgentArtifactLineageRead:
    try:
        facts = await AgentQualityQueryService(session).get_lineage_facts(
            artifact_id=artifact_id,
            user_id=current_user.id,
        )
        return AgentArtifactLineageRead(
            artifact_id=facts.artifact.id,
            upstream_edges=[_lineage_edge_read(item) for item in facts.upstream],
            downstream_edges=[_lineage_edge_read(item) for item in facts.downstream],
        )
    except (AgentRuntimeError, SQLAlchemyError) as exc:
        raise _error(exc) from exc


@router.get('/artifacts/{artifact_id}/quality-blockers', response_model=list[AgentQualityBlockerRead])
async def list_agent_artifact_quality_blockers(
    artifact_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> list[AgentQualityBlockerRead]:
    try:
        rows = await list_artifact_quality_blockers(artifact_id=artifact_id, user_id=current_user.id, session=session)
        return [AgentQualityBlockerRead.model_validate(item) for item in rows]
    except (AgentRuntimeError, SQLAlchemyError) as exc:
        raise _error(exc) from exc

@router.get('/artifacts/{artifact_id}/rewrite-instructions', response_model=list[AgentRewriteInstructionRead])
async def list_agent_artifact_rewrite_instructions(
    artifact_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> list[AgentRewriteInstructionRead]:
    try:
        rows = await list_artifact_rewrite_instructions(artifact_id=artifact_id, user_id=current_user.id, session=session)
        return [AgentRewriteInstructionRead.model_validate(item) for item in rows]
    except (AgentRuntimeError, SQLAlchemyError) as exc:
        raise _error(exc) from exc


@router.get('/artifacts/{artifact_id}/content', response_class=PlainTextResponse)
async def read_agent_artifact_content(artifact_id: str, session: AsyncSession = Depends(get_session), current_user: UserInDB = Depends(get_current_user)) -> PlainTextResponse:
    try:
        _, content = await read_artifact_content(artifact_id=artifact_id, user_id=current_user.id, session=session)
        return PlainTextResponse(content)
    except (AgentRuntimeError, SQLAlchemyError) as exc:
        raise _error(exc) from exc


@router.post("/artifacts/{artifact_id}/accept", response_model=AgentArtifactRead)
async def accept_agent_artifact(artifact_id: str, payload: AgentArtifactAcceptRequest, session: AsyncSession = Depends(get_session), current_user: UserInDB = Depends(get_current_user)) -> AgentArtifactRead:
    """Compatibility UI endpoint: an explicit accept click becomes a registered approval execution."""
    try:
        artifact = (await session.execute(
            select(AgentArtifactRef).join(AgentRun, AgentRun.id == AgentArtifactRef.run_id).where(
                AgentArtifactRef.id == artifact_id,
                AgentArtifactRef.user_id == current_user.id,
                AgentRun.user_id == current_user.id,
            )
        )).scalar_one_or_none()
        if artifact is None:
            raise AgentNotFound("artifact not found")
        metadata = dict(artifact.metadata_json or {})
        if artifact.kind != "chapter_candidate" or not artifact.project_id:
            raise AgentConflict("artifact is not an acceptable chapter candidate")
        if metadata.get("status") == "accepted":
            return AgentArtifactRead.model_validate(artifact)
        if metadata.get("status") != "candidate":
            raise AgentConflict("artifact is not an unaccepted chapter candidate")
        runtime = AgentRuntimeService(session)
        approval = await runtime.request_approval(
            run_id=artifact.run_id,
            user_id=current_user.id,
            tool_name="chapter.version.accept",
            project_id=artifact.project_id,
            arguments={"artifact_id": artifact.id, "note": payload.note or ""},
        )
        await runtime.append_event(
            run_id=artifact.run_id,
            user_id=current_user.id,
            event_type="approval_required",
            summary="接受候选版本等待用户确认",
            data={"approval_id": approval.id, "tool_name": approval.tool_name, "artifact_id": artifact.id},
        )
        approval = await runtime.decide_approval(
            approval_id=approval.id, user_id=current_user.id, approved=True, reason="explicit_artifact_accept"
        )
        accepted = await _execute_registered_approval(approval_id=approval.id, session=session, user_id=current_user.id)
        return AgentArtifactRead.model_validate(accepted)
    except (AgentRuntimeError, SQLAlchemyError) as exc:
        raise _error(exc) from exc


@router.get("/runs/{run_id}/artifacts", response_model=list[AgentArtifactRead])
async def list_agent_artifacts(run_id: str, session: AsyncSession = Depends(get_session), current_user: UserInDB = Depends(get_current_user)) -> list[AgentArtifactRead]:
    try:
        return await AgentRuntimeService(session).list_artifacts(run_id=run_id, user_id=current_user.id)
    except (AgentRuntimeError, SQLAlchemyError) as exc:
        raise _error(exc) from exc


@router.post("/approvals/{approval_id}/decision", response_model=AgentApprovalRead)
async def decide_agent_approval(approval_id: str, payload: AgentApprovalDecisionRequest, session: AsyncSession = Depends(get_session), current_user: UserInDB = Depends(get_current_user)) -> AgentApprovalRead:
    try:
        approval = await AgentRuntimeService(session).decide_approval(approval_id=approval_id, user_id=current_user.id, approved=payload.approved, reason=payload.reason)
        return AgentApprovalRead.model_validate(approval)
    except (AgentRuntimeError, SQLAlchemyError) as exc:
        raise _error(exc) from exc



