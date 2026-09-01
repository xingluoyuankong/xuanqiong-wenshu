"""Agent 会话运行时持久化服务。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import and_, case, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from ..models.agent import AgentApproval, AgentArtifactRef, AgentEventRecord, AgentJob, AgentMessage, AgentRun, AgentRunCommand, AgentRunStep, AgentSession
from ..agent.schemas import AgentPublicWorkSummary
from ..agent.state_machine import (
    InvalidRunStatus,
    InvalidRunTransition,
    CLAIMABLE_RUN_STATUSES as STATE_CLAIMABLE_RUN_STATUSES,
    RECOVERY_READY_PHASE,
    RUN_STATUSES as AGENT_RUN_STATUSES,
    TERMINAL_RUN_STATUSES as STATE_TERMINAL_RUN_STATUSES,
    validate_transition,
)
from ..models.novel import NovelProject


TERMINAL_RUN_STATUSES = set(STATE_TERMINAL_RUN_STATUSES)
VALID_RUN_STATUSES = set(AGENT_RUN_STATUSES)
CLAIMABLE_RUN_STATUSES = set(STATE_CLAIMABLE_RUN_STATUSES)
VALID_RUN_COMMAND_TYPES = {"pause", "resume", "cancel"}
_RUN_COMMAND_ORDER = ("pause", "resume", "cancel")
_RUN_COMMAND_TERMINAL_STATUSES = {"applied", "rejected", "failed"}
_FORBIDDEN_KEYS = {"thought", "reasoning", "chain_of_thought", "private_reasoning", "system_prompt", "provider_secret"}
_PROVIDER_PROVENANCE_KEYS = {
    "planner_provider_called",
    "planner_provider_fallback_reason",
    "response_provider_called",
    "response_provider_fallback_reason",
    "response_provider_attempts",
    "planner_provider_attempts",
    "candidate_writer_provider_called",
    "candidate_writer_provider_fallback_reason",
    "candidate_writer_model_ref",
    "candidate_writer_provider_attempts",
}

# Event payloads are a public, replayed UI contract. Keep this allowlist flat
# and deliberately smaller than the run-context/artifact compatibility cleaner:
# an arbitrary Provider response must never become an event payload by accident.
_VISIBLE_EVENT_KEYS: dict[str, set[str]] = {
    "run_started": {"phase"},
    "planner_started": {"phase"},
    "context_resolved": {"context_count", "context_kinds", "phase"},
    "novel_context_snapshot_created": {"phase", "selection_digest", "budget_text_units", "estimated_text_units", "selected_count", "excluded_count", "compressed_count"},
    "work_trace_delta": {"trace_id", "phase", "action_id", "kind", "message", "progress", "capability_id", "result_ref"},
    "plan_created": {"step_count", "mode", "provider_called", "fallback_reason", "planner_fallback_reason", "planner_provider_called", "planner_provider_fallback_reason"},
    "plan_revised": {"revision", "step_count", "phase", "provider_called", "fallback_reason", "planner_provider_called", "planner_provider_fallback_reason"},
    "plan_step_started": {"step", "tool_name", "phase"},
    "plan_step_completed": {"step", "tool_name", "phase"},
    "plan_step_failed": {"step", "tool_name", "error_type", "phase"},
    "plan_step_pending": {"step", "tool_name", "phase"},
    "approval_required": {"approval_id", "tool_name", "risk_level"},
    "approval_granted": {"approval_id", "tool_name", "status"},
    "approval_rejected": {"approval_id", "tool_name", "status"},
    "tool_call_started": {"tool_name", "step", "phase"},
    "tool_call_progress": {"tool_name", "step", "progress", "phase", "progress_message"},
    "progress_update": {"tool_name", "step", "progress", "phase", "action_id", "progress_message"},
    "tool_call_completed": {"tool_name", "step", "result_keys", "phase"},
    "tool_call_result": {"tool_name", "step", "result_keys", "phase"},
    "tool_call_failed": {"tool_name", "step", "error_type", "phase"},
    "tool_cancelled": {"tool_name", "step", "phase"},
    "step_reused": {"tool_name", "step", "phase"},
    "step_lease_expired": {"tool_name", "step", "phase", "attempt_count"},
    "run_paused": {"approval_count", "phase"},
    "run_resumed": {"phase"},
    "run_cancelling": {"phase", "active_job_count", "pending_approval_count"},
    "run_recovery_ready": {"phase"},
    "job_replayed": {"job_id", "attempt_count", "operator_id"},
    "run_cancelled": {"phase", "active_job_count", "cancelled_approval_count"},
    "approval_cancelled": {"approval_id", "tool_name", "status"},
    "cancellation_side_effect_failed": {"error_type", "phase"},
    "run_command_requested": {"command_id", "command_type", "phase"},
    "run_command_applied": {"command_id", "command_type", "phase", "status"},
    "run_command_rejected": {"command_id", "command_type", "phase", "error_type"},
    "assistant_queued": {"phase", "provider_called", "planner_provider_called", "planner_provider_fallback_reason"},
    "assistant_started": {"phase", "response_provider_called", "response_provider_fallback_reason"},
    "assistant_delta": {"content", "phase", "response_provider_called"},
    "assistant_completed": {"phase", "length", "response_provider_called", "response_provider_fallback_reason"},
    "conversation_summary_created": {"phase", "summary_id", "start_message_sequence", "end_message_sequence", "message_count"},
    "conversation_summary_failed": {"phase", "final_message_sequence", "error_type"},
    "write_execution_started": {"approval_id", "tool_name", "chapter_number", "candidate_writer_provider_called", "candidate_writer_provider_fallback_reason", "candidate_writer_model_ref"},
    "write_candidate_progress": {"approval_id", "characters", "candidate_writer_provider_called"},
    "write_execution_failed": {"approval_id", "error_type", "candidate_writer_provider_called", "candidate_writer_provider_fallback_reason"},
    "artifact_created": {"artifact_id", "kind", "chapter_number", "candidate_writer_provider_called", "candidate_writer_provider_fallback_reason", "candidate_writer_model_ref"},
    "artifact_accepted": {"artifact_id", "chapter_number", "version_id"},
    "quality_check_failed": {"artifact_id", "error_type"},
    "quality_check_blocked": {"artifact_id", "quality_issue_codes", "blocker_count"},
    "quality_check_completed": {"artifact_id", "quality_status"},
    "run_failed": {"error_type", "reason", "phase", "response_provider_called", "response_provider_fallback_reason"},
    "run_completed": {"artifact_id", "version_id", "phase", "provider_called", "response_provider_called", "response_provider_fallback_reason"},
    "public_work_summary": {
        "action_id", "phase", "current_action", "completed_action",
        "input_scope_kinds", "input_scope_count", "selected_capability",
        "decision_summary", "next_action", "expected_output", "step", "revision",
    },
}


def allowed_commands_for_run(status: str, current_phase: str | None = None) -> list[str]:
    """Return the lifecycle commands valid for the current Run state."""
    normalized = str(status or "").strip().lower()
    if normalized == "created":
        return ["cancel"]
    if normalized in {"planning", "running", "awaiting_approval"}:
        return ["pause", "cancel"]
    if normalized == "paused":
        return ["resume", "cancel"]
    return []


def _command_payload_hash(
    *,
    command_type: str,
    reason: str | None,
    payload: dict[str, Any],
    expected_state_version: int | None,
) -> str:
    canonical = {
        "command_type": command_type,
        "reason": reason,
        "payload_json": payload,
        "expected_state_version": expected_state_version,
    }
    encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def command_projection(command: AgentRunCommand) -> dict[str, Any]:
    """Project one durable command for State API consumers."""
    return {
        "id": command.id,
        "run_id": command.run_id,
        "correlation_id": command.correlation_id,
        "user_id": command.user_id,
        "command_type": command.command_type,
        "status": command.status,
        "reason": command.reason,
        "idempotency_key": command.idempotency_key,
        "payload_hash": command.payload_hash or "",
        "expected_state_version": command.expected_state_version,
        "payload_json": dict(command.payload_json or {}),
        "result_json": dict(command.result_json or {}),
        "error_type": command.error_type,
        "error_detail": command.error_detail,
        "attempt_count": int(command.attempt_count or 0),
        "lease_owner": command.lease_owner,
        "lease_expires_at": command.lease_expires_at,
        "requested_at": command.requested_at,
        "started_at": command.started_at,
        "finished_at": command.finished_at,
        "applied_at": command.applied_at,
    }


def _is_event_sequence_conflict(exc: IntegrityError) -> bool:
    message = str(getattr(exc, "orig", exc)).lower()
    return "agent_events" in message and ("sequence" in message or "uq_agent_event" in message)


class AgentRuntimeError(Exception):
    pass


class AgentNotFound(AgentRuntimeError):
    pass


class AgentScopeViolation(AgentRuntimeError):
    pass


class AgentConflict(AgentRuntimeError):
    pass


def _clean_data(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _clean_data(v) for k, v in value.items() if str(k).lower() not in _FORBIDDEN_KEYS}
    if isinstance(value, list):
        return [_clean_data(item) for item in value]
    return value


def _provider_attempt_text(value: Any, limit: int) -> str | None:
    text = str(value or "").strip()
    return text[:limit] or None


def _provider_attempt_int(value: Any, *, default: int | None = None, minimum: int = 0, maximum: int = 2_147_483_647) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if minimum <= number <= maximum else default


def clean_provider_attempt_snapshot(value: Any) -> dict[str, Any]:
    """Return the bounded, redacted ProviderAttemptLedger wire contract.

    Context can outlive implementation versions, so the API applies this cleaner
    again instead of trusting historical JSON merely because it is Run-owned.
    """
    raw = value if isinstance(value, dict) else {}
    records = raw.get("provider_attempts") if isinstance(raw.get("provider_attempts"), list) else []
    cleaned: list[dict[str, Any]] = []
    categories = {"AUTHENTICATION", "RATE_LIMIT", "TRANSIENT_5XX", "NETWORK_DISCONNECT", "TIMEOUT", "EMPTY_STREAM", "INVALID_RESPONSE", "CANCELLED", "BUDGET_EXHAUSTED", "POLICY_REJECTED", "UNKNOWN"}
    statuses = {"running", "succeeded", "failed"}
    for index, raw_record in enumerate(records[:16], start=1):
        if not isinstance(raw_record, dict):
            continue
        attempt = _provider_attempt_int(raw_record.get("attempt"), default=index, minimum=1, maximum=64) or index
        record: dict[str, Any] = {
            "attempt": attempt,
            "role": _provider_attempt_text(raw_record.get("role"), 80) or "unknown",
            "status": str(raw_record.get("status") or "unknown").strip().lower(),
        }
        if record["status"] not in statuses:
            record["status"] = "unknown"
        for key, limit in (("provider_ref", 200), ("model_ref", 200), ("started_at", 64), ("first_token_at", 64), ("finished_at", 64), ("output_digest", 128)):
            item = _provider_attempt_text(raw_record.get(key), limit)
            if item is not None:
                record[key] = item
        category = _provider_attempt_text(raw_record.get("error_category"), 40)
        if category in categories:
            record["error_category"] = category
        http_status = _provider_attempt_int(raw_record.get("http_status"), minimum=100, maximum=599)
        if http_status is not None:
            record["http_status"] = http_status
        retry_index = _provider_attempt_int(raw_record.get("retry_index"), default=0, minimum=0, maximum=64)
        record["retry_index"] = retry_index if retry_index is not None else 0
        fallback_from = _provider_attempt_int(raw_record.get("fallback_from_attempt"), minimum=1, maximum=64)
        if fallback_from is not None:
            record["fallback_from_attempt"] = fallback_from
        record["cancel_observed"] = bool(raw_record.get("cancel_observed"))
        cleaned.append(record)
    valid_attempts = {item["attempt"] for item in cleaned}
    selected = _provider_attempt_int(raw.get("selected_provider_attempt"), minimum=1, maximum=64)
    return {
        "provider_attempts": cleaned,
        "selected_provider_attempt": selected if selected in valid_attempts else None,
        "fallback_used": bool(raw.get("fallback_used")),
    }


def _visible_event_data(event_type: str, value: Any) -> dict[str, Any]:
    """Return only flat, explicitly allowed, user-visible event fields."""
    if not isinstance(value, dict):
        return {}
    allowed = _VISIBLE_EVENT_KEYS.get(event_type, set())
    result: dict[str, Any] = {}
    for key, item in value.items():
        name = str(key)
        if name not in allowed or name.lower() in _FORBIDDEN_KEYS:
            continue
        if isinstance(item, (str, int, float, bool)) or item is None:
            result[name] = item
        elif isinstance(item, list) and all(isinstance(entry, (str, int, float, bool)) or entry is None for entry in item):
            result[name] = item[:100]
    return result


class AgentRuntimeService:
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _normalize_datetime(value: Optional[datetime]) -> Optional[datetime]:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    async def _session(self, session_id: str, user_id: int) -> AgentSession:
        item = (await self.session.execute(select(AgentSession).where(AgentSession.id == session_id, AgentSession.user_id == user_id))).scalar_one_or_none()
        if item is None:
            raise AgentNotFound("agent session not found")
        return item

    async def _run(self, run_id: str, user_id: int) -> AgentRun:
        item = (await self.session.execute(select(AgentRun).where(AgentRun.id == run_id, AgentRun.user_id == user_id))).scalar_one_or_none()
        if item is None:
            raise AgentNotFound("agent run not found")
        return item

    async def _locked_command(self, command_id: str, user_id: int) -> AgentRunCommand:
        item = (await self.session.execute(
            select(AgentRunCommand)
            .where(AgentRunCommand.id == command_id, AgentRunCommand.user_id == user_id)
            .with_for_update()
        )).scalar_one_or_none()
        if item is None:
            raise AgentNotFound("agent run command not found")
        return item

    async def _locked_run(self, run_id: str, user_id: int) -> AgentRun:
        """Lock one Run before allocating a visible event sequence or progress checkpoint."""
        item = (
            await self.session.execute(
                select(AgentRun)
                .where(AgentRun.id == run_id, AgentRun.user_id == user_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if item is None:
            raise AgentNotFound("agent run not found")
        return item

    def _new_visible_event(
        self,
        *,
        run: AgentRun,
        event_type: str,
        summary: str,
        data: Optional[dict[str, Any]] = None,
    ) -> AgentEventRecord:
        run.event_sequence = max(0, int(run.event_sequence or 0)) + 1
        event = AgentEventRecord(
            id=str(uuid4()),
            run_id=run.id,
            correlation_id=run.correlation_id,
            transaction_id=run.transaction_id,
            user_id=run.user_id,
            event_type=event_type,
            sequence=run.event_sequence,
            summary=summary[:1000],
            data_json=_visible_event_data(event_type, data or {}),
        )
        self.session.add(event)
        return event

    async def verify_project(self, project_id: Optional[str], user_id: int) -> None:
        if not project_id:
            return
        project = (await self.session.execute(select(NovelProject.id).where(NovelProject.id == project_id, NovelProject.user_id == user_id))).scalar_one_or_none()
        if project is None:
            raise AgentScopeViolation("project is not accessible")

    async def create_session(self, *, user_id: int, project_id: Optional[str] = None, title: Optional[str] = None) -> AgentSession:
        await self.verify_project(project_id, user_id)
        item = AgentSession(id=str(uuid4()), user_id=user_id, project_id=project_id, title=(title or "新建创作会话")[:255], status="active")
        self.session.add(item)
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def list_sessions(self, *, user_id: int, project_id: Optional[str] = None, limit: int = 50) -> list[AgentSession]:
        stmt = select(AgentSession).where(AgentSession.user_id == user_id).order_by(AgentSession.updated_at.desc()).limit(min(max(limit, 1), 100))
        if project_id is not None:
            stmt = stmt.where(AgentSession.project_id == project_id)
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_session(self, session_id: str, user_id: int) -> AgentSession:
        return await self._session(session_id, user_id)

    async def archive_session(self, *, session_id: str, user_id: int) -> AgentSession:
        item = await self._session(session_id, user_id)
        item.status = "archived"
        await self.session.commit()
        await self.session.refresh(item)
        return item


    async def append_message(self, *, session_id: str, user_id: int, role: str, content: str, commit: bool = True) -> AgentMessage:
        item = await self._session(session_id, user_id)
        if role not in {"user", "assistant", "system_summary"}:
            raise AgentConflict("unsupported message role")
        if not content.strip() or len(content) > 200000:
            raise AgentConflict("message content is invalid")
        max_seq = (await self.session.execute(select(func.max(AgentMessage.sequence)).where(AgentMessage.session_id == session_id))).scalar()
        message = AgentMessage(id=str(uuid4()), session_id=session_id, user_id=user_id, role=role, content=content, sequence=int(max_seq or 0) + 1)
        self.session.add(message)
        item.updated_at = self._now()
        if commit:
            await self.session.commit()
            await self.session.refresh(message)
        return message

    async def finalize_visible_response(
        self,
        *,
        run_id: str,
        user_id: int,
        session_id: str,
        content: str,
        completion_data: dict[str, Any],
    ) -> AgentMessage:
        """Atomically persist one final assistant reply and its terminal Run facts.

        A worker may die after this commit but before it acknowledges its Job.
        The Run-scoped marker makes a later recovery return the existing message
        instead of generating another final response.
        """
        run = await self._locked_run(run_id, user_id)
        if run.session_id != session_id:
            raise AgentConflict("visible response session does not match run")
        context = dict(run.context_json or {})
        marker_id = str(context.get("visible_response_final_message_id") or "").strip()
        if marker_id:
            existing = (await self.session.execute(
                select(AgentMessage).where(
                    AgentMessage.id == marker_id,
                    AgentMessage.session_id == session_id,
                    AgentMessage.user_id == user_id,
                    AgentMessage.role == "assistant",
                )
            )).scalar_one_or_none()
            if existing is None:
                raise AgentConflict("visible response final message marker is invalid")
            return existing
        if run.status in TERMINAL_RUN_STATUSES:
            raise AgentConflict("terminal run has no visible response final marker")
        message = await self.append_message(
            session_id=session_id,
            user_id=user_id,
            role="assistant",
            content=content,
            commit=False,
        )
        context["visible_response_final_message_id"] = message.id
        context["visible_response_final_message_sequence"] = message.sequence
        run.context_json = context
        await self.update_run(
            run_id=run_id,
            user_id=user_id,
            status="completed",
            phase="summary",
            progress=100,
            commit=False,
        )
        await self.append_event(
            run_id=run_id,
            user_id=user_id,
            event_type="assistant_completed",
            summary="Agent 回复已完成",
            data=completion_data,
            commit=False,
        )
        await self.append_event(
            run_id=run_id,
            user_id=user_id,
            event_type="run_completed",
            summary="Agent 运行已完成",
            data=completion_data,
            commit=False,
        )
        await self.session.commit()
        await self.session.refresh(message)
        return message
    async def list_messages(self, *, session_id: str, user_id: int, limit: int = 200) -> list[AgentMessage]:
        await self._session(session_id, user_id)
        stmt = select(AgentMessage).where(AgentMessage.session_id == session_id, AgentMessage.user_id == user_id).order_by(AgentMessage.sequence.asc()).limit(min(max(limit, 1), 500))
        return list((await self.session.execute(stmt)).scalars().all())

    async def _build_novel_context_inputs(
        self,
        *,
        project_id: str,
        context_payload: dict[str, Any],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
        """Build bounded novel context inputs for the immutable Run snapshot.

        This is an additive bridge: legacy runs still keep their original context,
        while project-scoped runs receive selected plan/version refs before planning.
        """
        from ..models.novel import Chapter, NovelProject
        from .novel_context_snapshot_service import (
            ContextSelectionRequest,
            ContextSnapshotBuilder,
            snapshot_to_agent_context_inputs,
        )

        target_chapter = context_payload.get("target_chapter") or context_payload.get("chapter_number")
        try:
            target_chapter = int(target_chapter) if target_chapter is not None else None
        except (TypeError, ValueError):
            target_chapter = None
        project = (await self.session.execute(
            select(NovelProject)
            .where(NovelProject.id == project_id)
            .options(
                selectinload(NovelProject.blueprint),
                selectinload(NovelProject.outlines),
                selectinload(NovelProject.chapters).selectinload(Chapter.selected_version),
            )
        )).scalar_one_or_none()
        if project is None:
            return None

        records: list[dict[str, Any]] = [
            {
                "project_id": project.id,
                "ref_type": "project",
                "ref_key": project.id,
                "reason_code": "current_scope",
                "title": project.title,
            }
        ]
        for outline in project.outlines:
            if target_chapter is not None and outline.chapter_number > target_chapter:
                continue
            records.append({
                "project_id": project.id,
                "ref_type": "chapter_plan",
                "ref_key": f"chapter-plan:{outline.chapter_number}",
                "chapter_number": outline.chapter_number,
                "reason_code": "current_scope" if outline.chapter_number == target_chapter else "recent_continuity",
                "title": outline.title,
                "summary": outline.summary,
            })
        for chapter in project.chapters:
            if target_chapter is not None and chapter.chapter_number > target_chapter:
                continue
            version = chapter.selected_version
            if version is None:
                continue
            text = str(version.content or "")
            records.append({
                "project_id": project.id,
                "ref_type": "chapter_version",
                "ref_key": f"chapter-version:{version.id}",
                "chapter_number": chapter.chapter_number,
                "reason_code": "current_scope" if chapter.chapter_number == target_chapter else "recent_continuity",
                "version_id": version.id,
                "text_units": sum(1 for char in text if not char.isspace()),
                "content_digest": version.content_hash,
            })

        selection = ContextSnapshotBuilder(
            ContextSelectionRequest(
                project_id=project.id,
                target_chapter=target_chapter,
                max_text_units=max(1, int(context_payload.get("max_context_text_units") or 20_000)),
                max_refs=128,
            )
        ).build(records, snapshot_id=f"run-selection:{project.id}:{target_chapter or 'project'}")
        return snapshot_to_agent_context_inputs(selection)

    async def create_run(self, *, session_id: str, user_id: int, project_id: Optional[str] = None, context: Optional[dict[str, Any]] = None, commit: bool = True) -> AgentRun:
        item = await self._session(session_id, user_id)
        if item.project_id != project_id:
            raise AgentScopeViolation("run project does not match session project")
        context_payload = _clean_data(context or {})
        from ..agent.registry import get_default_tool_registry_snapshot
        from ..agent.catalog_release import build_catalog_release
        from ..agent.capability_resolver import resolve_capabilities
        registry_snapshot = get_default_tool_registry_snapshot()
        catalog_release = build_catalog_release(registry_snapshot)
        requested_capabilities = context_payload.get("requested_tools")
        resolved_capabilities = resolve_capabilities(
            catalog_release,
            user_id=user_id,
            project_id=project_id,
            requested_capabilities=requested_capabilities if isinstance(requested_capabilities, list) and requested_capabilities else None,
        )
        # Keep the legacy registry snapshot for existing executor compatibility,
        # while binding every new Run to immutable release and resolver records.
        context_payload["capability_snapshot"] = registry_snapshot
        context_payload["catalog_release"] = catalog_release.to_dict()
        context_payload["capability_resolution"] = resolved_capabilities.to_dict()
        context_payload["catalog_release_id"] = catalog_release.release_id
        context_payload["capability_resolution_id"] = resolved_capabilities.snapshot_id
        run = AgentRun(id=str(uuid4()), correlation_id=str(uuid4()), transaction_id=str(uuid4()), session_id=session_id, user_id=user_id, project_id=project_id, status="created", context_json=context_payload)
        self.session.add(run)
        # New Runs persist the immutable release and resolver decision in
        # relational rows before the transaction becomes visible. JSON remains
        # only as the compatibility payload for legacy workers/recovery paths.
        await self.session.flush()
        from .agent_catalog_service import AgentCatalogService

        relational_snapshot = await AgentCatalogService(self.session).persist_run_resolution(
            run=run,
            catalog_release=catalog_release,
            resolver_snapshot=resolved_capabilities,
        )
        # The JSON payload remains the compatibility/recovery contract for
        # existing workers.  Project-scoped Runs additionally receive a bounded,
        # explainable novel selection before any planner executes.
        from .agent_context_service import AgentContextService

        snapshot_context = dict(context_payload)
        snapshot_refs = context_payload.get("context_refs") if isinstance(context_payload.get("context_refs"), list) else []
        if project_id:
            try:
                novel_inputs = await self._build_novel_context_inputs(
                    project_id=project_id,
                    context_payload=context_payload,
                )
            except Exception as exc:
                novel_inputs = None
                snapshot_context["novel_context_selection_error"] = type(exc).__name__
            if novel_inputs is not None:
                novel_context_json, novel_refs = novel_inputs
                snapshot_context["novel_context_selection"] = novel_context_json
                snapshot_refs = list(snapshot_refs) + novel_refs
                snapshot_context["novel_context_selection_digest"] = novel_context_json.get("selection_digest")

        initial_context = await AgentContextService(self.session).create_snapshot(
            run=run,
            session=item,
            context_json=snapshot_context,
            refs=snapshot_refs,
            context_kind="run_initial_context",
        )
        context_payload = snapshot_context
        context_payload["relational_catalog_release_id"] = relational_snapshot.catalog_release_id
        context_payload["relational_capability_snapshot_id"] = relational_snapshot.id
        context_payload["relational_capability_snapshot_key"] = relational_snapshot.snapshot_id
        context_payload["relational_context_snapshot_id"] = initial_context.id
        context_payload["relational_context_snapshot_key"] = initial_context.snapshot_id
        novel_selection = context_payload.get("novel_context_selection") if isinstance(context_payload, dict) else None
        if isinstance(novel_selection, dict) and int(novel_selection.get("selected_count") or 0) > 1:
            await self.append_event(
                run_id=run.id,
                user_id=user_id,
                event_type="novel_context_snapshot_created",
                summary="项目上下文快照已创建",
                data={
                    "phase": "context",
                    "selection_digest": novel_selection.get("selection_digest"),
                    "budget_text_units": novel_selection.get("budget_text_units"),
                    "estimated_text_units": novel_selection.get("estimated_text_units"),
                    "selected_count": novel_selection.get("selected_count"),
                    "excluded_count": len(novel_selection.get("excluded") or []),
                    "compressed_count": len(novel_selection.get("compressed") or []),
                },
                commit=False,
            )
        run.context_json = dict(context_payload)
        flag_modified(run, "context_json")
        if commit:
            await self.session.commit()
            await self.session.refresh(run)
        return run

    async def get_run(self, run_id: str, user_id: int) -> AgentRun:
        return await self._run(run_id, user_id)

    async def set_run_context(self, *, run_id: str, user_id: int, context: dict[str, Any], commit: bool = True) -> AgentRun:
        run = await self._run(run_id, user_id)
        context_payload = _clean_data(context)
        existing_context = run.context_json if isinstance(run.context_json, dict) else {}
        existing_snapshot = existing_context.get("capability_snapshot")
        existing_release = existing_context.get("catalog_release")
        existing_resolution = existing_context.get("capability_resolution")
        if existing_snapshot is not None:
            context_payload["capability_snapshot"] = existing_snapshot
        else:
            from ..agent.registry import get_default_tool_registry_snapshot
            context_payload["capability_snapshot"] = get_default_tool_registry_snapshot()
        if existing_release is not None:
            context_payload["catalog_release"] = existing_release
        if existing_resolution is not None:
            context_payload["capability_resolution"] = existing_resolution
        # Catalog/Resolver bindings never change for a Run. Context and Plan facts
        # may advance during an explicit replan, so inherit their locators only
        # when the caller did not provide a newer immutable fact.
        for key in (
            "catalog_release_id",
            "capability_resolution_id",
            "relational_catalog_release_id",
            "relational_capability_snapshot_id",
            "relational_capability_snapshot_key",
        ):
            if key in existing_context:
                context_payload[key] = existing_context[key]
        for key in (
            "relational_context_snapshot_id",
            "relational_context_snapshot_key",
            "relational_plan_revision_id",
            "relational_plan_revision_key",
        ):
            if key not in context_payload and key in existing_context:
                context_payload[key] = existing_context[key]
        run.context_json = dict(context_payload)
        flag_modified(run, "context_json")
        if commit:
            await self.session.commit()
            await self.session.refresh(run)
        return run

    async def update_run_provider_provenance(
        self,
        *,
        run_id: str,
        user_id: int,
        updates: dict[str, Any],
    ) -> AgentRun:
        """Merge safe, stage-specific Provider facts without replacing unrelated Run context."""
        unknown = set(updates) - _PROVIDER_PROVENANCE_KEYS
        if unknown:
            raise AgentConflict(f"unknown provider provenance fields: {', '.join(sorted(unknown))}")
        run = await self._run(run_id, user_id)
        context = dict(run.context_json or {})
        for key, value in updates.items():
            if key.endswith("_called"):
                context[key] = bool(value) if value is not None else None
            elif key.endswith("_fallback_reason"):
                context[key] = str(value)[:160] if value else None
            elif key == "candidate_writer_model_ref":
                context[key] = str(value)[:200] if value else None
            elif key.endswith("_provider_attempts"):
                context[key] = clean_provider_attempt_snapshot(value)
        return await self.set_run_context(run_id=run_id, user_id=user_id, context=context)

    async def ensure_step(
        self,
        *,
        run_id: str,
        user_id: int,
        step_order: int,
        tool_name: str,
        idempotency_key: str,
        input_payload: Optional[dict[str, Any]] = None,
    ) -> AgentRunStep:
        run = await self._run(run_id, user_id)
        existing = (
            await self.session.execute(
                select(AgentRunStep).where(
                    AgentRunStep.run_id == run_id,
                    AgentRunStep.user_id == user_id,
                    AgentRunStep.step_order == step_order,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            if existing.tool_name != tool_name or existing.idempotency_key != idempotency_key:
                raise AgentConflict("step checkpoint identity does not match")
            return existing
        step = AgentRunStep(
            run_id=run_id,
            correlation_id=run.correlation_id,
            transaction_id=run.transaction_id,
            user_id=user_id,
            step_order=step_order,
            tool_name=tool_name,
            idempotency_key=idempotency_key,
            input_json=_clean_data(input_payload or {}),
            output_json={},
            status="pending",
        )
        self.session.add(step)
        await self.session.commit()
        await self.session.refresh(step)
        return step

    async def list_steps(self, *, run_id: str, user_id: int) -> list[AgentRunStep]:
        await self._run(run_id, user_id)
        stmt = select(AgentRunStep).where(AgentRunStep.run_id == run_id, AgentRunStep.user_id == user_id).order_by(AgentRunStep.step_order.asc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def claim_step(self, *, step_id: str, user_id: int, lease_owner: str, lease_seconds: int = 120) -> AgentRunStep:
        owner = str(lease_owner or "").strip()[:128]
        if not owner:
            raise AgentConflict("step lease_owner is required")
        now = self._now()
        expires_at = now + timedelta(seconds=min(max(lease_seconds, 1), 900))
        step = (await self.session.execute(select(AgentRunStep).where(AgentRunStep.id == step_id, AgentRunStep.user_id == user_id))).scalar_one_or_none()
        if step is None:
            raise AgentNotFound("agent run step not found")
        if step.status == "completed":
            return step
        result = await self.session.execute(
            update(AgentRunStep)
            .where(
                AgentRunStep.id == step_id,
                AgentRunStep.user_id == user_id,
                AgentRunStep.status != "completed",
                or_(
                    AgentRunStep.lease_owner.is_(None),
                    AgentRunStep.lease_expires_at.is_(None),
                    AgentRunStep.lease_expires_at <= now,
                    AgentRunStep.lease_owner == owner,
                ),
            )
            .values(
                status="running",
                lease_owner=owner,
                lease_expires_at=expires_at,
                started_at=step.started_at or now,
                finished_at=None,
                error_type=None,
                attempt_count=AgentRunStep.attempt_count + 1,
                lease_generation=AgentRunStep.lease_generation + 1,
            )
        )
        if result.rowcount != 1:
            raise AgentConflict("step lease is held by another worker")
        await self.session.commit()
        return await self._step(step_id, user_id)

    async def _step(self, step_id: str, user_id: int) -> AgentRunStep:
        step = (await self.session.execute(select(AgentRunStep).where(AgentRunStep.id == step_id, AgentRunStep.user_id == user_id))).scalar_one_or_none()
        if step is None:
            raise AgentNotFound("agent run step not found")
        return step

    async def start_step(self, *, step_id: str, user_id: int) -> AgentRunStep:
        return await self.claim_step(step_id=step_id, user_id=user_id, lease_owner=f"legacy:{user_id}")

    async def complete_step(self, *, step_id: str, user_id: int, output: Optional[dict[str, Any]] = None, lease_owner: str | None = None, lease_generation: int | None = None) -> AgentRunStep:
        step = await self._step(step_id, user_id)
        if step.status == "completed":
            return step
        if step.status != "running":
            raise AgentConflict("only running step can be completed")
        if lease_owner and step.lease_owner != lease_owner:
            raise AgentConflict("step lease belongs to another worker")
        if lease_generation is not None and int(step.lease_generation or 0) != int(lease_generation):
            raise AgentConflict("step lease generation is stale")
        step.status = "completed"
        step.output_json = _clean_data(output or {})
        step.finished_at = self._now()
        step.lease_owner = None
        step.lease_expires_at = None
        await self.session.commit()
        await self.session.refresh(step)
        return step

    async def fail_step(self, *, step_id: str, user_id: int, error_type: str, lease_owner: str | None = None, lease_generation: int | None = None) -> AgentRunStep:
        step = await self._step(step_id, user_id)
        if lease_owner and step.lease_owner != lease_owner:
            raise AgentConflict("step lease belongs to another worker")
        if lease_generation is not None and int(step.lease_generation or 0) != int(lease_generation):
            raise AgentConflict("step lease generation is stale")
        step.status = "failed"
        step.error_type = str(error_type)[:160]
        step.finished_at = self._now()
        step.lease_owner = None
        step.lease_expires_at = None
        await self.session.commit()
        await self.session.refresh(step)
        return step

    async def cancel_step(self, *, step_id: str, user_id: int, lease_owner: str | None = None, lease_generation: int | None = None) -> AgentRunStep:
        step = await self._step(step_id, user_id)
        if lease_owner and step.lease_owner != lease_owner:
            raise AgentConflict("step lease belongs to another worker")
        if lease_generation is not None and int(step.lease_generation or 0) != int(lease_generation):
            raise AgentConflict("step lease generation is stale")
        if step.status not in {"completed", "cancelled"}:
            step.status = "cancelled"
            step.finished_at = self._now()
            step.lease_owner = None
            step.lease_expires_at = None
            await self.session.commit()
            await self.session.refresh(step)
        return step

    async def reconcile_stale_steps(self) -> list[AgentRunStep]:
        """Release expired step leases without silently re-running Provider work."""
        now = self._now()
        candidates = list(
            (
                await self.session.execute(
                    select(AgentRunStep)
                    .join(AgentRun, AgentRun.id == AgentRunStep.run_id)
                    .where(
                        AgentRunStep.status == "running",
                        AgentRunStep.lease_expires_at.is_not(None),
                        AgentRunStep.lease_expires_at <= now,
                        AgentRun.status.notin_(TERMINAL_RUN_STATUSES),
                    )
                    .order_by(AgentRunStep.lease_expires_at.asc())
                )
            ).scalars().all()
        )
        released: list[AgentRunStep] = []
        for step in candidates:
            result = await self.session.execute(
                update(AgentRunStep)
                .where(
                    AgentRunStep.id == step.id,
                    AgentRunStep.status == "running",
                    AgentRunStep.lease_expires_at.is_not(None),
                    AgentRunStep.lease_expires_at <= now,
                )
                .values(status="pending", lease_owner=None, lease_expires_at=None, error_type="LeaseExpiredRecovery")
            )
            if result.rowcount != 1:
                continue
            await self.session.commit()
            refreshed = await self._step(step.id, step.user_id)
            released.append(refreshed)
            await self.append_event(
                run_id=refreshed.run_id,
                user_id=refreshed.user_id,
                event_type="step_lease_expired",
                summary=f"步骤 {refreshed.tool_name} 的执行租约已过期，等待安全恢复",
                data={"tool_name": refreshed.tool_name, "step": refreshed.step_order, "phase": "stale_recovery", "attempt_count": refreshed.attempt_count},
            )
        return released

    async def _append_event_uncommitted(
        self,
        *,
        run_id: str,
        user_id: int,
        event_type: str,
        summary: str,
        data: Optional[dict[str, Any]] = None,
    ) -> AgentEventRecord:
        """Build one event inside the caller's transaction without committing."""
        run = await self._locked_run(run_id, user_id)
        event = self._new_visible_event(
            run=run,
            event_type=event_type,
            summary=summary,
            data=data,
        )
        return event

    async def append_event(
        self,
        *,
        run_id: str,
        user_id: int,
        event_type: str,
        summary: str,
        data: Optional[dict[str, Any]] = None,
        commit: bool = True,
    ) -> AgentEventRecord:
        """Append one event with optimistic retry for sequence races.

        ``commit=False`` lets a higher-level Run transaction persist the Run
        mutation, command row, and lifecycle event together.
        """
        if not commit:
            return await self._append_event_uncommitted(
                run_id=run_id, user_id=user_id, event_type=event_type,
                summary=summary, data=data,
            )
        last_conflict: IntegrityError | None = None
        for _attempt in range(5):
            event = await self._append_event_uncommitted(
                run_id=run_id, user_id=user_id, event_type=event_type,
                summary=summary, data=data,
            )
            try:
                await self.session.commit()
            except IntegrityError as exc:
                await self.session.rollback()
                if not _is_event_sequence_conflict(exc):
                    raise
                last_conflict = exc
                continue
            await self.session.refresh(event)
            return event
        raise AgentConflict("unable to allocate a unique Agent event sequence") from last_conflict

    async def append_work_trace_delta(
        self,
        *,
        run_id: str,
        user_id: int,
        trace_id: str,
        phase: str,
        kind: str,
        message: str,
        progress: float | None = None,
        action_id: str | None = None,
        capability_id: str | None = None,
        result_ref: str | None = None,
        commit: bool = True,
    ) -> AgentEventRecord:
        """Persist one bounded public work-trace delta in the durable event ledger."""
        from ..agent.work_trace_contract import WorkTraceDelta

        event_data = WorkTraceDelta(
            trace_id=trace_id,
            run_id=run_id,
            phase=phase,
            action_id=action_id,
            kind=kind,
            message=message,
            progress=progress,
            capability_id=capability_id,
            result_ref=result_ref,
        )
        return await self.append_event(
            run_id=run_id,
            user_id=user_id,
            event_type="work_trace_delta",
            summary=event_data.message,
            data=event_data.model_dump(mode="json"),
            commit=commit,
        )

    async def append_public_work_summary(
        self,
        *,
        run_id: str,
        user_id: int,
        summary: AgentPublicWorkSummary | dict[str, Any],
        commit: bool = True,
    ) -> AgentEventRecord:
        """Persist one bounded public work summary and its Run-level checkpoint.

        The activity ledger remains append-only.  The checkpoint exists solely so
        state recovery does not need to read an unbounded event history to tell the
        author what the Agent is doing now.
        """
        validated = (
            summary
            if isinstance(summary, AgentPublicWorkSummary)
            else AgentPublicWorkSummary.model_validate(summary)
        )
        last_conflict: IntegrityError | None = None
        for _attempt in range(5):
            run = await self._locked_run(run_id, user_id)
            event = self._new_visible_event(
                run=run,
                event_type="public_work_summary",
                summary=validated.current_action,
                data=validated.event_data(),
            )
            run.latest_public_summary_json = validated.model_dump(mode="json")
            run.latest_public_summary_sequence = event.sequence
            run.latest_public_summary_at = self._now()
            if not commit:
                return event
            try:
                await self.session.commit()
            except IntegrityError as exc:
                await self.session.rollback()
                if not _is_event_sequence_conflict(exc):
                    raise
                last_conflict = exc
                continue
            await self.session.refresh(event)
            return event
        raise AgentConflict("unable to allocate a unique Agent public summary sequence") from last_conflict

    async def list_timeline(
        self,
        *,
        user_id: int,
        project_id: str | None = None,
        session_id: str | None = None,
        run_id: str | None = None,
        event_type: str | None = None,
        run_status: str | None = None,
        tool_name: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[tuple[AgentEventRecord, str, str | None, str]]:
        """List a user-scoped, cross-session visible event projection."""
        stmt = (
            select(AgentEventRecord, AgentRun.session_id, AgentRun.project_id, AgentRun.status)
            .join(AgentRun, AgentRun.id == AgentEventRecord.run_id)
            .join(AgentSession, AgentSession.id == AgentRun.session_id)
            .where(
                AgentEventRecord.user_id == user_id,
                AgentRun.user_id == user_id,
                AgentSession.user_id == user_id,
            )
        )
        if project_id:
            stmt = stmt.where(AgentRun.project_id == project_id)
        if session_id:
            stmt = stmt.where(AgentRun.session_id == session_id)
        if run_id:
            stmt = stmt.where(AgentRun.id == run_id)
        if event_type:
            stmt = stmt.where(AgentEventRecord.event_type == event_type)
        if run_status:
            stmt = stmt.where(AgentRun.status == run_status)
        if tool_name:
            stmt = stmt.where(func.json_extract(AgentEventRecord.data_json, '$.tool_name') == tool_name)
        stmt = (
            stmt.order_by(AgentEventRecord.created_at.desc(), AgentEventRecord.id.desc())
            .offset(max(0, int(offset)))
            .limit(min(max(1, int(limit)), 200))
        )
        rows = (await self.session.execute(stmt)).all()
        return [(event, str(session_id_value), project_id_value, str(status)) for event, session_id_value, project_id_value, status in rows]

    async def list_audit_ledger(
        self,
        *,
        user_id: int,
        project_id: str | None = None,
        session_id: str | None = None,
        run_id: str | None = None,
        event_type: str | None = None,
        run_status: str | None = None,
        tool_name: str | None = None,
        approval_id: str | None = None,
        artifact_id: str | None = None,
        source_version_id: int | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return a normalized audit projection without exposing private payloads.

        AgentEventRecord remains the append-only source of visible execution
        facts. This projection joins session/run scope and artifact metadata so
        a user can trace tool -> approval -> artifact -> accepted/source version
        without granting access to arbitrary rows or hidden Provider data.
        """
        rows = await self.list_timeline(
            user_id=user_id,
            project_id=project_id,
            session_id=session_id,
            run_id=run_id,
            event_type=event_type,
            run_status=run_status,
            tool_name=tool_name,
            # Fetch a bounded window before the relation filters are applied;
            # the public API caps limit at 200 and callers can paginate.
            offset=0,
            limit=200,
        )
        if not rows:
            return []

        run_ids = {event.run_id for event, *_ in rows}
        artifact_rows = list((await self.session.execute(
            select(AgentArtifactRef).where(
                AgentArtifactRef.user_id == user_id,
                AgentArtifactRef.run_id.in_(run_ids),
            )
        )).scalars().all())
        artifact_by_id = {item.id: item for item in artifact_rows}

        approval_rows = list((await self.session.execute(
            select(AgentApproval).where(
                AgentApproval.user_id == user_id,
                AgentApproval.run_id.in_(run_ids),
            )
        )).scalars().all())
        approval_by_id = {item.id: item for item in approval_rows}

        projected: list[dict[str, Any]] = []
        for event, resolved_session_id, resolved_project_id, resolved_run_status in rows:
            data = dict(event.data_json or {})
            event_approval_id = data.get("approval_id")
            event_artifact_id = data.get("artifact_id")
            artifact = artifact_by_id.get(str(event_artifact_id)) if event_artifact_id else None
            metadata = dict(artifact.metadata_json or {}) if artifact else {}
            resolved_source = data.get("source_version_id", metadata.get("source_version_id"))
            resolved_accepted = data.get("accepted_version_id", metadata.get("accepted_version_id", data.get("version_id")))
            try:
                resolved_source = int(resolved_source) if resolved_source is not None else None
            except (TypeError, ValueError):
                resolved_source = None
            try:
                resolved_accepted = int(resolved_accepted) if resolved_accepted is not None else None
            except (TypeError, ValueError):
                resolved_accepted = None
            if approval_id and str(event_approval_id) != approval_id:
                # Keep approval lifecycle rows discoverable even when the
                # event payload is intentionally minimal.
                if event.event_type not in {"approval_granted", "approval_rejected"} or approval_id not in approval_by_id:
                    continue
            if artifact_id and str(event_artifact_id) != artifact_id:
                continue
            if source_version_id is not None and resolved_source != source_version_id:
                continue
            projected.append({
                "event_id": event.id,
                "session_id": resolved_session_id,
                "run_id": event.run_id,
                "user_id": event.user_id,
                "project_id": resolved_project_id,
                "run_status": resolved_run_status,
                "event_type": event.event_type,
                "sequence": event.sequence,
                "summary": event.summary,
                "tool_name": data.get("tool_name"),
                "approval_id": str(event_approval_id) if event_approval_id else None,
                "artifact_id": str(event_artifact_id) if event_artifact_id else None,
                "source_version_id": resolved_source,
                "accepted_version_id": resolved_accepted,
                "data_json": data,
                "created_at": event.created_at,
            })
        projected.sort(key=lambda item: (item["created_at"], item["event_id"]), reverse=True)
        return projected[max(0, int(offset)):max(0, int(offset)) + min(max(1, int(limit)), 200)]

    async def list_events(self, *, run_id: str, user_id: int, after_sequence: int = 0, limit: int = 500) -> list[AgentEventRecord]:
        await self._run(run_id, user_id)
        stmt = select(AgentEventRecord).where(AgentEventRecord.run_id == run_id, AgentEventRecord.user_id == user_id, AgentEventRecord.sequence > max(0, after_sequence)).order_by(AgentEventRecord.sequence.asc()).limit(min(max(limit, 1), 500))
        return list((await self.session.execute(stmt)).scalars().all())

    async def claim_run(self, *, run_id: str, user_id: int, lease_owner: str, lease_seconds: int = 120, lease_generation: int | None = None) -> AgentRun:
        owner = str(lease_owner or "").strip()[:128]
        if not owner:
            raise AgentConflict("lease_owner is required")
        now = self._now()
        expires_at = now + timedelta(seconds=max(1, min(int(lease_seconds), 3600)))
        # Conditional UPDATE is the lease fence. It prevents two workers that
        # read the same free row concurrently from both claiming it.
        result = await self.session.execute(
            update(AgentRun)
            .where(
                AgentRun.id == run_id,
                AgentRun.user_id == user_id,
                AgentRun.cancel_requested_at.is_(None),
                or_(lease_generation is None, AgentRun.lease_generation == int(lease_generation or 0)),
                or_(
                    AgentRun.status.in_(CLAIMABLE_RUN_STATUSES),
                    and_(AgentRun.status == "paused", AgentRun.current_phase == RECOVERY_READY_PHASE),
                ),
                or_(
                    AgentRun.lease_owner.is_(None),
                    AgentRun.lease_expires_at.is_(None),
                    AgentRun.lease_expires_at <= now,
                    AgentRun.lease_owner == owner,
                ),
            )
            .values(
                lease_owner=owner,
                lease_expires_at=expires_at,
                lease_generation=case(
                    (
                        and_(AgentRun.lease_owner == owner, AgentRun.lease_expires_at > now),
                        AgentRun.lease_generation,
                    ),
                    else_=AgentRun.lease_generation + 1,
                ),
            )
        )
        if result.rowcount != 1:
            raise AgentConflict("run lease is held by another worker or run is terminal")
        await self.session.commit()
        return await self._run(run_id, user_id)

    async def release_run(self, *, run_id: str, user_id: int, lease_owner: str, lease_generation: int | None = None) -> AgentRun:
        run = await self._run(run_id, user_id)
        if lease_generation is not None and int(run.lease_generation or 0) != int(lease_generation):
            raise AgentConflict("run lease generation is stale")
        if run.lease_owner and run.lease_owner != lease_owner:
            raise AgentConflict("run lease belongs to another worker")
        run.lease_owner = None
        run.lease_expires_at = None
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def update_run(
        self,
        *,
        run_id: str,
        user_id: int,
        status: str,
        phase: Optional[str] = None,
        step: Optional[int] = None,
        progress: Optional[float] = None,
        pause_reason: str | None = None,
        resume_target_status: str | None = None,
        commit: bool = True,
    ) -> AgentRun:
        run = await self._run(run_id, user_id)
        try:
            _, normalized_status = validate_transition(run.status, status)
        except (InvalidRunStatus, InvalidRunTransition) as exc:
            raise AgentConflict(str(exc)) from exc
        status = normalized_status
        previous_status = run.status
        previous_pause_reason = run.pause_reason
        previous_resume_target = run.resume_target_status
        run.status = status
        if phase is not None: run.current_phase = phase[:80]
        if step is not None: run.current_step = max(0, step)
        if pause_reason is not None or status != "paused":
            run.pause_reason = pause_reason[:32] if pause_reason else None
        if resume_target_status is not None or status != "paused":
            run.resume_target_status = resume_target_status[:24] if resume_target_status else None
        if progress is not None:
            target_progress = min(100.0, max(0.0, float(progress)))
            run.progress = 100.0 if status == "completed" else max(float(run.progress or 0), target_progress)
        elif status == "completed":
            run.progress = 100.0
        if status == "running" and run.started_at is None: run.started_at = self._now()
        if status in TERMINAL_RUN_STATUSES: run.finished_at = self._now()
        if (
            previous_status != run.status
            or previous_pause_reason != run.pause_reason
            or previous_resume_target != run.resume_target_status
        ):
            run.state_version = max(0, int(run.state_version or 0)) + 1
        if commit:
            await self.session.commit()
            await self.session.refresh(run)
        return run

    async def publish_progress(
        self,
        *,
        run_id: str,
        user_id: int,
        progress: float,
        phase: str,
        step: int | None = None,
        tool_name: str | None = None,
        action_id: str | None = None,
        progress_message: str,
        status: str | None = None,
        commit: bool = True,
    ) -> AgentRun:
        """Atomically persist a monotonic progress checkpoint and visible event.

        The same optimistic event-sequence retry as append_event protects an API
        approval racing an inline/Worker progress checkpoint on SQLite.
        """
        last_conflict: IntegrityError | None = None
        for _attempt in range(5):
            run = await self._locked_run(run_id, user_id)
            if run.status in TERMINAL_RUN_STATUSES:
                return run
            requested_status = str(status or run.status).strip().lower()
            if requested_status not in VALID_RUN_STATUSES or requested_status in TERMINAL_RUN_STATUSES:
                raise AgentConflict("invalid progress status")
            # Progress callbacks are late and can race user controls. They may
            # advance the normal planning/execution path, but never revive a
            # paused, approval-waiting, cancelling, or terminal Run.
            if run.status in {"paused", "awaiting_approval", "cancelling"}:
                target_status = run.status
            elif run.status in TERMINAL_RUN_STATUSES:
                return run
            elif requested_status in {run.status, "planning", "running", "awaiting_approval"}:
                target_status = requested_status
            else:
                target_status = run.status
            previous_status = run.status
            target_progress = max(float(run.progress or 0), min(99.0, max(0.0, float(progress))))
            run.status = target_status
            run.current_phase = phase[:80]
            if step is not None:
                run.current_step = max(0, step)
            run.progress = target_progress
            if target_status == "running" and run.started_at is None:
                run.started_at = self._now()
            if previous_status != target_status:
                run.state_version = max(0, int(run.state_version or 0)) + 1
            resolved_action_id = str(action_id or f"{run.current_phase}:{run.current_step if step is not None else 'run'}").strip()[:160]
            data: dict[str, Any] = {
                "progress": round(target_progress, 2),
                "phase": run.current_phase,
                "action_id": resolved_action_id or "run:unknown",
                "progress_message": progress_message[:500],
            }
            if step is not None:
                data["step"] = run.current_step
            if tool_name:
                data["tool_name"] = tool_name[:120]
            event = self._new_visible_event(
                run=run,
                event_type="progress_update",
                summary=progress_message,
                data=data,
            )
            if not commit:
                return run
            try:
                await self.session.commit()
            except IntegrityError as exc:
                await self.session.rollback()
                if not _is_event_sequence_conflict(exc):
                    raise
                last_conflict = exc
                continue
            await self.session.refresh(run)
            await self.session.refresh(event)
            return run
        raise AgentConflict("unable to allocate a unique Agent progress sequence") from last_conflict


    async def _apply_pause_run(self, *, run_id: str, user_id: int, commit: bool = True) -> AgentRun:
        run = await self._run(run_id, user_id)
        if run.status not in {"planning", "running", "awaiting_approval"}:
            raise AgentConflict("run cannot be paused in its current status")
        run = await self.update_run(
            run_id=run_id,
            user_id=user_id,
            status="paused",
            phase="paused",
            pause_reason="user",
            resume_target_status=run.status,
            commit=commit,
        )
        if commit:
            await self.append_event(run_id=run_id, user_id=user_id, event_type="run_paused", summary="Agent 运行已暂停", data={"phase": "paused"})
        else:
            await self._append_event_uncommitted(run_id=run_id, user_id=user_id, event_type="run_paused", summary="Agent 运行已暂停", data={"phase": "paused"})
        return run

    async def _apply_resume_run(self, *, run_id: str, user_id: int, commit: bool = True) -> AgentRun:
        run = await self._run(run_id, user_id)
        if run.status != "paused":
            raise AgentConflict("only paused runs can be resumed")
        target = run.resume_target_status if run.resume_target_status in {"planning", "running", "awaiting_approval"} else "running"
        run = await self.update_run(
            run_id=run_id,
            user_id=user_id,
            status=target,
            phase="resumed",
            pause_reason=None,
            resume_target_status=None,
            commit=commit,
        )
        if commit:
            await self.append_event(run_id=run_id, user_id=user_id, event_type="run_resumed", summary="Agent 运行已恢复", data={"phase": "resumed"})
        else:
            await self._append_event_uncommitted(run_id=run_id, user_id=user_id, event_type="run_resumed", summary="Agent 运行已恢复", data={"phase": "resumed"})
        return run

    async def _apply_cancel_run(self, *, run_id: str, user_id: int, reason: str | None = None, commit: bool = True) -> AgentRun:
        run = await self._run(run_id, user_id)
        if run.status in TERMINAL_RUN_STATUSES:
            raise AgentConflict("terminal run cannot be cancelled")
        run.cancel_requested_at = self._now()
        run.cancel_reason = (reason or "user_requested")[:255]
        run = await self.update_run(
            run_id=run_id,
            user_id=user_id,
            status="cancelling",
            phase="cancelling",
            pause_reason=None,
            resume_target_status=None,
            commit=commit,
        )
        active_jobs = int((await self.session.scalar(
            select(func.count(AgentJob.id)).where(
                AgentJob.run_id == run_id,
                AgentJob.user_id == user_id,
                AgentJob.status.in_({"queued", "running"}),
            )
        )) or 0)
        pending_approval_count = int((await self.session.scalar(
            select(func.count(AgentApproval.id)).where(
                AgentApproval.run_id == run_id,
                AgentApproval.user_id == user_id,
                AgentApproval.status == "pending",
            )
        )) or 0)
        if active_jobs or pending_approval_count:
            if commit:
                await self.append_event(run_id=run_id, user_id=user_id, event_type="run_cancelling", summary="Agent 运行正在等待 Job 收敛后取消", data={"phase": "cancelling", "active_job_count": active_jobs, "pending_approval_count": pending_approval_count})
            else:
                await self._append_event_uncommitted(run_id=run_id, user_id=user_id, event_type="run_cancelling", summary="Agent 运行正在等待 Job 收敛后取消", data={"phase": "cancelling", "active_job_count": active_jobs, "pending_approval_count": pending_approval_count})
            return run
        run = await self.update_run(
            run_id=run_id,
            user_id=user_id,
            status="cancelled",
            phase="cancelled",
            pause_reason=None,
            resume_target_status=None,
            commit=commit,
        )
        if commit:
            await self.append_event(run_id=run_id, user_id=user_id, event_type="run_cancelled", summary="Agent 运行已取消", data={"phase": "cancelled"})
        else:
            await self._append_event_uncommitted(run_id=run_id, user_id=user_id, event_type="run_cancelled", summary="Agent 运行已取消", data={"phase": "cancelled"})
        return run

    async def finalize_cancellation(
        self,
        *,
        run_id: str,
        user_id: int,
        commit: bool = True,
        visible_response_active: bool = False,
    ) -> AgentRun:
        """Move a cancelling Run to cancelled only after durable work settles.

        Job cancellation and in-process task cancellation are separate side
        effects.  This method is the single convergence point used after those
        effects finish; late workers therefore observe a terminal Run and are
        fenced by the existing completion guards.
        """
        run = await self._locked_run(run_id, user_id)
        if run.status != "cancelling":
            return run
        if visible_response_active:
            return run
        active_jobs = int((await self.session.scalar(
            select(func.count(AgentJob.id)).where(
                AgentJob.run_id == run_id,
                AgentJob.user_id == user_id,
                ~AgentJob.status.in_({"succeeded", "failed", "cancelled", "dead_letter"}),
            )
        )) or 0)
        if active_jobs:
            return run
        pending_approvals = list((await self.session.execute(
            select(AgentApproval).where(
                AgentApproval.run_id == run_id,
                AgentApproval.user_id == user_id,
                AgentApproval.status == "pending",
            )
        )).scalars().all())
        now = self._now()
        for approval in pending_approvals:
            approval.status = "cancelled"
            approval.decision_at = now
            approval.reason = (run.cancel_reason or "run_cancelled")[:255]
        run = await self.update_run(
            run_id=run_id,
            user_id=user_id,
            status="cancelled",
            phase="cancelled",
            pause_reason=None,
            resume_target_status=None,
            commit=False,
        )
        for approval in pending_approvals:
            await self._append_event_uncommitted(
                run_id=run_id,
                user_id=user_id,
                event_type="approval_cancelled",
                summary="运行取消后，待审批动作已关闭",
                data={
                    "approval_id": approval.id,
                    "tool_name": approval.tool_name,
                    "status": approval.status,
                },
            )
        await self._append_event_uncommitted(
            run_id=run_id,
            user_id=user_id,
            event_type="run_cancelled",
            summary="Agent 运行已完成取消收敛",
            data={
                "phase": "cancelled",
                "active_job_count": 0,
                "cancelled_approval_count": len(pending_approvals),
            },
        )
        if commit:
            await self.session.commit()
            await self.session.refresh(run)
        return run


    async def get_run_command(self, *, command_id: str, user_id: int) -> AgentRunCommand:
        command = (
            await self.session.execute(
                select(AgentRunCommand).where(
                    AgentRunCommand.id == command_id,
                    AgentRunCommand.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if command is None:
            raise AgentNotFound("agent run command not found")
        return command

    async def list_run_commands(self, *, run_id: str, user_id: int, limit: int = 100) -> list[AgentRunCommand]:
        await self._run(run_id, user_id)
        stmt = (
            select(AgentRunCommand)
            .where(AgentRunCommand.run_id == run_id, AgentRunCommand.user_id == user_id)
            .order_by(AgentRunCommand.requested_at.asc(), AgentRunCommand.id.asc())
            .limit(min(max(int(limit), 1), 200))
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def request_run_command(
        self,
        *,
        run_id: str,
        user_id: int,
        command_type: str,
        reason: str | None = None,
        payload: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        expected_state_version: int | None = None,
    ) -> AgentRunCommand:
        run = await self._run(run_id, user_id)
        normalized_type = str(command_type or "").strip().lower()
        if normalized_type not in VALID_RUN_COMMAND_TYPES:
            raise AgentConflict("unsupported Agent Run command")
        normalized_reason = str(reason).strip()[:255] if reason and str(reason).strip() else None
        normalized_payload = _clean_data(payload or {})
        normalized_key = str(idempotency_key or "").strip()[:255] or f"legacy:{uuid4()}"
        expected = int(run.state_version or 0) if expected_state_version is None else int(expected_state_version)
        payload_hash = _command_payload_hash(
            command_type=normalized_type,
            reason=normalized_reason,
            payload=normalized_payload,
            expected_state_version=expected,
        )
        run_id_value = run.id
        correlation_id_value = run.correlation_id
        phase_value = run.current_phase or "run_control"
        for _attempt in range(5):
            existing = (await self.session.execute(
                select(AgentRunCommand).where(
                    AgentRunCommand.run_id == run_id_value,
                    AgentRunCommand.user_id == user_id,
                    AgentRunCommand.idempotency_key == normalized_key,
                )
            )).scalar_one_or_none()
            if existing is not None:
                if (existing.payload_hash or "") != payload_hash:
                    raise AgentConflict("idempotency key was already used with a different payload")
                return existing
            command = AgentRunCommand(
                id=str(uuid4()),
                run_id=run_id_value,
                correlation_id=correlation_id_value,
                transaction_id=run.transaction_id,
                user_id=user_id,
                command_type=normalized_type,
                status="requested",
                reason=normalized_reason,
                idempotency_key=normalized_key,
                payload_hash=payload_hash,
                expected_state_version=expected,
                payload_json=normalized_payload,
                result_json={},
                requested_at=self._now(),
            )
            self.session.add(command)
            try:
                await self._append_event_uncommitted(
                    run_id=run_id_value,
                    user_id=user_id,
                    event_type="run_command_requested",
                    summary=f"已记录 Agent 运行{ {'pause': '暂停', 'resume': '继续', 'cancel': '取消'}[normalized_type] }请求",
                    data={
                        "command_id": command.id,
                        "command_type": normalized_type,
                        "phase": phase_value,
                    },
                )
                await self.session.commit()
            except IntegrityError as exc:
                await self.session.rollback()
                # Rollback expires any Run instance already held by this
                # session, including callers that created the Run fixture.
                # Rehydrate it before the next retry or return path.
                refreshed_run = await self._run(run_id_value, user_id)
                await self.session.refresh(refreshed_run)
                existing = (await self.session.execute(
                    select(AgentRunCommand).where(
                        AgentRunCommand.run_id == run_id_value,
                        AgentRunCommand.user_id == user_id,
                        AgentRunCommand.idempotency_key == normalized_key,
                    )
                )).scalar_one_or_none()
                if existing is not None:
                    if (existing.payload_hash or "") != payload_hash:
                        raise AgentConflict("idempotency key was already used with a different payload") from exc
                    return existing
                if _is_event_sequence_conflict(exc):
                    continue
                raise AgentConflict("unable to persist idempotent Agent Run command") from exc
            await self.session.refresh(command)
            return command
        raise AgentConflict("unable to allocate a unique Agent command event sequence")

    async def apply_run_command(self, *, command_id: str, user_id: int) -> AgentRunCommand:
        last_conflict: IntegrityError | None = None
        for _attempt in range(5):
            command = await self._locked_command(command_id=command_id, user_id=user_id)
            if command.status != "requested":
                return command
            command_run_id = command.run_id
            run = await self._locked_run(command_run_id, user_id)
            expected = command.expected_state_version
            try:
                if expected is not None and int(run.state_version or 0) != int(expected):
                    command.status = "rejected"
                    command.error_type = "AgentStateVersionConflict"
                    command.error_detail = f"expected state_version={expected}, current={run.state_version}"
                    command.applied_at = self._now()
                    await self._append_event_uncommitted(
                        run_id=command_run_id,
                        user_id=user_id,
                        event_type="run_command_rejected",
                        summary="Agent 运行控制请求的状态版本已过期",
                        data={
                            "command_id": command.id,
                            "command_type": command.command_type,
                            "phase": "run_control",
                            "error_type": command.error_type,
                        },
                    )
                else:
                    if command.command_type == "pause":
                        run = await self._apply_pause_run(run_id=command_run_id, user_id=user_id, commit=False)
                    elif command.command_type == "resume":
                        run = await self._apply_resume_run(run_id=command_run_id, user_id=user_id, commit=False)
                    elif command.command_type == "cancel":
                        run = await self._apply_cancel_run(run_id=command_run_id, user_id=user_id, reason=command.reason, commit=False)
                    else:
                        raise AgentConflict("unsupported Agent Run command")
                    command.status = "applied"
                    command.applied_at = self._now()
                    command.error_type = None
                    command.error_detail = None
                    command.result_json = {
                        "run_status": run.status,
                        "state_version": int(run.state_version or 0),
                    }
                    await self._append_event_uncommitted(
                        run_id=run.id,
                        user_id=user_id,
                        event_type="run_command_applied",
                        summary="Agent 运行控制请求已应用",
                        data={
                            "command_id": command.id,
                            "command_type": command.command_type,
                            "phase": run.current_phase or "run_control",
                            "status": command.status,
                        },
                    )
            except AgentRuntimeError as exc:
                # _apply_* validates the lifecycle precondition before mutating
                # the Run. Avoid a session-wide rollback here: it would expire
                # unrelated same-session ORM objects owned by the caller.
                run = await self._run(command_run_id, user_id)
                await self.session.refresh(run)
                command = await self.get_run_command(command_id=command_id, user_id=user_id)
                command.status = "rejected"
                command.error_type = type(exc).__name__
                command.error_detail = str(exc)[:1000]
                command.applied_at = self._now()
                await self._append_event_uncommitted(
                    run_id=command_run_id,
                    user_id=user_id,
                    event_type="run_command_rejected",
                    summary="Agent 运行控制请求未在当前状态应用",
                    data={
                        "command_id": command.id,
                        "command_type": command.command_type,
                        "phase": "run_control",
                        "error_type": command.error_type,
                    },
                )
            try:
                await self.session.commit()
            except IntegrityError as exc:
                await self.session.rollback()
                if not _is_event_sequence_conflict(exc):
                    raise
                # Restore the external Run identity map entry before retrying.
                refreshed_run = await self._run(command_run_id, user_id)
                await self.session.refresh(refreshed_run)
                last_conflict = exc
                continue
            await self.session.refresh(command)
            return command
        raise AgentConflict("unable to allocate a unique Agent command event sequence") from last_conflict

    async def submit_run_command(
        self,
        *,
        run_id: str,
        user_id: int,
        command_type: str,
        reason: str | None = None,
        payload: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        expected_state_version: int | None = None,
        apply: bool = True,
    ) -> AgentRunCommand:
        command = await self.request_run_command(
            run_id=run_id,
            user_id=user_id,
            command_type=command_type,
            reason=reason,
            payload=payload,
            idempotency_key=idempotency_key,
            expected_state_version=expected_state_version,
        )
        if not apply:
            return command
        return await self.apply_run_command(command_id=command.id, user_id=user_id)

    async def pause_run(self, *, run_id: str, user_id: int) -> AgentRun:
        command = await self.submit_run_command(run_id=run_id, user_id=user_id, command_type="pause")
        if command.status != "applied":
            raise AgentConflict(command.error_detail or "pause command was rejected")
        return await self._run(run_id, user_id)

    async def resume_run(self, *, run_id: str, user_id: int) -> AgentRun:
        command = await self.submit_run_command(run_id=run_id, user_id=user_id, command_type="resume")
        if command.status != "applied":
            raise AgentConflict(command.error_detail or "resume command was rejected")
        return await self._run(run_id, user_id)

    async def cancel_run(self, *, run_id: str, user_id: int, reason: str | None = None) -> AgentRun:
        command = await self.submit_run_command(
            run_id=run_id,
            user_id=user_id,
            command_type="cancel",
            reason=reason,
        )
        if command.status != "applied":
            raise AgentConflict(command.error_detail or "cancel command was rejected")
        return await self._run(run_id, user_id)

    async def is_cancel_requested(self, *, run_id: str, user_id: int) -> bool:
        run = await self._run(run_id, user_id)
        return run.cancel_requested_at is not None or run.status in {"cancelling", "cancelled"}

    async def reconcile_stale_runs(self) -> list[str]:
        now = self._now()
        rows = list((await self.session.execute(select(AgentRun).where(AgentRun.status.in_({"planning", "running"}), AgentRun.lease_expires_at.is_not(None), AgentRun.lease_expires_at <= now, AgentRun.cancel_requested_at.is_(None)))).scalars().all())
        recovered: list[str] = []
        for run in rows:
            run.status = "paused"
            run.current_phase = "recovery_ready"
            run.pause_reason = "lease_expired"
            run.resume_target_status = "running"
            run.state_version = max(0, int(run.state_version or 0)) + 1
            run.lease_owner = None
            run.lease_expires_at = None
            recovered.append(run.id)
        if rows:
            await self.session.commit()
            for run in rows:
                await self.append_event(run_id=run.id, user_id=run.user_id, event_type="run_recovery_ready", summary="Agent 执行器租约过期，运行已进入可恢复状态", data={"phase": "recovery_ready"})
        return recovered

    async def request_approval(self, *, run_id: str, user_id: int, tool_name: str, project_id: Optional[str], arguments: Optional[dict[str, Any]] = None, step_id: str | None = None) -> AgentApproval:
        run = await self._run(run_id, user_id)
        if run.project_id != project_id:
            raise AgentScopeViolation("approval project does not match run")
        if step_id:
            step = await self._step(step_id, user_id)
            if step.run_id != run_id or step.tool_name != tool_name:
                raise AgentScopeViolation("approval step does not match run or tool")
            existing = (
                await self.session.execute(select(AgentApproval).where(AgentApproval.run_id == run_id, AgentApproval.step_id == step_id))
            ).scalar_one_or_none()
            if existing is not None:
                return existing
        approval = AgentApproval(id=str(uuid4()), run_id=run_id, correlation_id=run.correlation_id, transaction_id=run.transaction_id, step_id=step_id, user_id=user_id, project_id=project_id, tool_name=tool_name, status="pending", request_json=_clean_data(arguments or {}))
        self.session.add(approval)
        await self.session.commit()
        await self.session.refresh(approval)
        return approval

    async def list_approvals(self, *, run_id: str, user_id: int) -> list[AgentApproval]:
        await self._run(run_id, user_id)
        stmt = select(AgentApproval).where(AgentApproval.run_id == run_id, AgentApproval.user_id == user_id).order_by(AgentApproval.decision_at.asc().nullsfirst(), AgentApproval.id.asc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_approval(self, *, approval_id: str, user_id: int) -> AgentApproval:
        approval = (await self.session.execute(select(AgentApproval).where(AgentApproval.id == approval_id, AgentApproval.user_id == user_id))).scalar_one_or_none()
        if approval is None:
            raise AgentNotFound("approval not found")
        return approval

    async def mark_approval_executed(self, *, approval_id: str, user_id: int, status: str = "executed") -> AgentApproval:
        approval = await self.get_approval(approval_id=approval_id, user_id=user_id)
        if approval.status != "executing":
            raise AgentConflict("approval must be claimed before execution can finish")
        if status not in {"executed", "execution_failed"}:
            raise AgentConflict("invalid approval execution terminal status")
        approval.status = status
        await self.session.commit()
        await self.session.refresh(approval)
        return approval

    async def claim_approval_execution(self, *, approval_id: str, user_id: int) -> AgentApproval:
        result = await self.session.execute(
            update(AgentApproval)
            .where(AgentApproval.id == approval_id, AgentApproval.user_id == user_id, AgentApproval.status == "approved")
            .values(status="executing")
        )
        if result.rowcount != 1:
            raise AgentConflict("approval is not available for execution")
        await self.session.commit()
        return await self.get_approval(approval_id=approval_id, user_id=user_id)

    async def decide_approval(self, *, approval_id: str, user_id: int, approved: bool, reason: Optional[str] = None) -> AgentApproval:
        approval = (await self.session.execute(select(AgentApproval).where(AgentApproval.id == approval_id, AgentApproval.user_id == user_id))).scalar_one_or_none()
        if approval is None: raise AgentNotFound("approval not found")
        if approval.status != "pending": raise AgentConflict("approval already decided")
        # Event/public-summary persistence can retry after a transaction
        # rollback. SQLAlchemy expires ORM instances on rollback even when
        # expire_on_commit=False, so snapshot every scalar needed after the
        # first commit before entering those retrying paths.
        approval_id_value = approval.id
        run_id_value = approval.run_id
        tool_name_value = approval.tool_name
        decision_status = "approved" if approved else "rejected"
        approval.status = decision_status
        approval.reason = (reason or "")[:2000] or None
        approval.decision_at = self._now()
        await self.session.commit()
        await self.session.refresh(approval)
        await self.append_event(
            run_id=run_id_value,
            user_id=user_id,
            event_type="approval_granted" if approved else "approval_rejected",
            summary=f"工具 {tool_name_value} 已" + ("批准" if approved else "拒绝"),
            data={"approval_id": approval_id_value, "tool_name": tool_name_value, "status": decision_status},
        )
        await self.append_public_work_summary(
            run_id=run_id_value,
            user_id=user_id,
            summary={
                "action_id": f"approval:{approval_id_value}",
                "phase": "approval",
                "current_action": (
                    f"已批准 {tool_name_value} 的候选执行。"
                    if approved
                    else f"已拒绝 {tool_name_value} 的候选执行。"
                ),
                "completed_action": "已记录作者审批决定。",
                "selected_capability": tool_name_value,
                "next_action": (
                    "生成候选 Artifact 并执行质量检查。"
                    if approved
                    else "保留当前正文，等待新的创作指令。"
                ),
                "expected_output": "候选结果或保持当前版本。",
            },
        )
        # A retrying event/summary write may have rolled back the Session and
        # expired this ORM instance. Rehydrate it asynchronously before the
        # route/Pydantic response serializer reads scalar fields.
        await self.session.refresh(approval)
        return approval

    async def list_artifacts(self, *, run_id: str, user_id: int) -> list[AgentArtifactRef]:
        await self._run(run_id, user_id)
        stmt = select(AgentArtifactRef).where(AgentArtifactRef.run_id == run_id, AgentArtifactRef.user_id == user_id).order_by(AgentArtifactRef.created_at.asc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def add_artifact(self, *, run_id: str, user_id: int, project_id: Optional[str], kind: str, uri: str, sha256: Optional[str] = None, metadata: Optional[dict[str, Any]] = None) -> AgentArtifactRef:
        run = await self._run(run_id, user_id)
        if run.project_id != project_id: raise AgentScopeViolation("artifact project does not match run")
        artifact = AgentArtifactRef(id=str(uuid4()), run_id=run_id, correlation_id=run.correlation_id, transaction_id=run.transaction_id, user_id=user_id, project_id=project_id, kind=kind[:64], uri=uri[:500], sha256=sha256, metadata_json=_clean_data(metadata or {}))
        self.session.add(artifact)
        await self.session.commit()
        await self.session.refresh(artifact)
        await self.append_public_work_summary(
            run_id=run_id,
            user_id=user_id,
            summary={
                "action_id": f"artifact:{artifact.id}",
                "phase": "artifact",
                "current_action": "已创建候选 Artifact，正在等待质量检查或作者查看。",
                "completed_action": f"已生成 {artifact.kind} 候选。",
                "input_scope": [{"kind": "artifact", "artifact_id": artifact.id}],
                "next_action": "查看候选、质量结果与版本差异。",
                "expected_output": "可接受的新版本或后续修订任务。",
            },
        )
        return artifact

