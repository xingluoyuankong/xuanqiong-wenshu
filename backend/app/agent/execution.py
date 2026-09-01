"""Durable Planner/read/suggest execution for one Agent Run.

The message route only persists a Run and this job.  Both a standalone AgentWorker
and the local development inline launcher execute the same handler, so a browser
can attach to the durable event stream before planning starts.
"""
from __future__ import annotations

import asyncio
import os
import socket
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import Settings, settings
from ..db.session import AsyncSessionLocal
from ..models.agent import AgentJob
from ..services.agent_runtime import AgentConflict, AgentRuntimeService, TERMINAL_RUN_STATUSES
from ..services.agent_execution_service import AgentExecutionService
from ..services.agent_context_service import AgentContextIntegrityError, AgentContextService
from ..services.agent_plan_service import AgentPlanIntegrityError, AgentPlanService
from ..services.llm_service import LLMService
from .context_refs import ContextRefValidationError, project_plan_arguments, resolve_agent_context_refs
from .schemas import AgentContextRef
from .jobs import AgentJobConflict, AgentJobService
from .orchestrator import AgentOrchestrator
from .registry import DEFAULT_TOOL_REGISTRY, ToolExecutionCancelled
from .runner import get_cancel_event, launch_visible_response, release_cancel_event
from .tool_adapters import execute_read_tool
from .tool_result_digest import build_tool_result_digests


_EXECUTION_TASKS: dict[str, asyncio.Task[None]] = {}


def _runtime_settings() -> Settings:
    """Resolve current environment overrides without exposing config values."""
    return Settings(_env_file=None, secret_key=settings.secret_key)


def _execution_owner(job: AgentJob) -> str:
    fallback = f"inline:{socket.gethostname()}:{os.getpid()}"
    return f"execution:{job.lease_owner or fallback}:{job.id}"[:128]


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _context_payload(
    *,
    existing: dict[str, Any],
    goal: str,
    canonical_refs: list[dict[str, Any]],
    requested_tools: list[str],
    legacy_arguments: dict[str, Any],
    tool_arguments: dict[str, dict[str, Any]],
    tool_results: list[dict[str, Any]],
    plan_steps: list[dict[str, Any]],
    execution_job_id: str,
    planner_provider_called: bool | None = None,
    planner_fallback_reason: str | None = None,
    job_id: str | None = None,
) -> dict[str, Any]:
    context = {
        **existing,
        "goal": goal,
        "context_refs": canonical_refs,
        "requested_tools": requested_tools,
        "arguments": legacy_arguments,
        "tool_arguments": tool_arguments,
        "tool_results": tool_results,
        "tool_result_digests": build_tool_result_digests(tool_results),
        "plan_steps": plan_steps,
        "execution_job_id": execution_job_id,
    }
    if planner_provider_called is not None:
        context["planner_provider_called"] = planner_provider_called
    if planner_fallback_reason is not None:
        context["planner_fallback_reason"] = planner_fallback_reason  # legacy Planner-only projection
        context["planner_provider_fallback_reason"] = planner_fallback_reason
    if job_id is not None:
        context["job_id"] = job_id
    return context


def _plan_revision_json(
    *,
    goal: str,
    plan_mode: str,
    steps: list[dict[str, Any]],
    requested_tools: list[str],
    tool_arguments: dict[str, dict[str, Any]],
    tool_results: list[dict[str, Any]],
    visible_summary: str,
    provider_called: bool,
    fallback_reason: str | None,
    phase: str,
    replan_reason: str | None = None,
) -> dict[str, Any]:
    """Canonical planner decision material retained independently of mutable Run JSON."""
    return {
        "schema_version": 1,
        "goal": goal,
        "mode": plan_mode,
        "phase": phase,
        "steps": [dict(item) for item in steps],
        "requested_tools": list(requested_tools),
        "tool_arguments": {str(name): dict(value) for name, value in tool_arguments.items()},
        "tool_result_digests": build_tool_result_digests(tool_results),
        "visible_summary": visible_summary,
        "provider_called": bool(provider_called),  # compatibility: Planner-only
        "fallback_reason": fallback_reason,
        "planner_provider_called": bool(provider_called),
        "planner_provider_fallback_reason": fallback_reason,
        "replan_reason": replan_reason,
    }


async def _relational_context_snapshot(
    *,
    context_service: AgentContextService,
    run: Any,
    context: dict[str, Any],
) -> Any | None:
    """Load and verify a new-Run ContextSnapshot without breaking legacy JSON recovery."""
    snapshot_key = str(context.get("relational_context_snapshot_key") or "").strip()
    if not snapshot_key:
        return None
    snapshot = await context_service.get_run_snapshot(run_id=run.id, snapshot_id=snapshot_key)
    if snapshot is None or snapshot.session_id != run.session_id or snapshot.user_id != run.user_id:
        return None
    try:
        await context_service.verify_snapshot(snapshot)
    except AgentContextIntegrityError:
        # The legacy executor deliberately retains its existing JSON-only
        # recovery behavior when a pre-P1-A Run has no usable relational fact.
        return None
    return snapshot


def _public_scope(canonical_refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    allowed = {"kind", "project_id", "chapter_number", "version_id", "artifact_id"}
    scope: list[dict[str, Any]] = []
    for raw in canonical_refs[:16]:
        if not isinstance(raw, dict) or not isinstance(raw.get("kind"), str):
            continue
        scope.append({key: raw[key] for key in allowed if key in raw})
    return scope


async def _publish_public_activity(
    runtime: AgentRuntimeService,
    *,
    run_id: str,
    user_id: int,
    action_id: str,
    phase: str,
    current_action: str,
    canonical_refs: list[dict[str, Any]],
    completed_action: str | None = None,
    selected_capability: str | None = None,
    decision_summary: str | None = None,
    next_action: str | None = None,
    expected_output: str | None = None,
    step_order: int | None = None,
    revision: int = 0,
) -> None:
    await runtime.append_public_work_summary(
        run_id=run_id,
        user_id=user_id,
        summary={
            "action_id": action_id,
            "phase": phase,
            "current_action": current_action,
            "completed_action": completed_action,
            "input_scope": _public_scope(canonical_refs),
            "selected_capability": selected_capability,
            "decision_summary": decision_summary,
            "next_action": next_action,
            "expected_output": expected_output,
            "step_order": step_order,
            "revision": revision,
        },
    )


def _resolved_capability_names(context: dict[str, Any]) -> set[str] | None:
    raw = context.get("capability_resolution")
    if not isinstance(raw, dict):
        return None
    tools = raw.get("tools")
    if not isinstance(tools, list):
        return None
    names = {str(item.get("name") or "").strip() for item in tools if isinstance(item, dict)}
    return {name for name in names if name}


def _assert_plan_uses_resolved_capabilities(plan: AgentPlan, context: dict[str, Any]) -> None:
    allowed = _resolved_capability_names(context)
    if allowed is None:
        return
    selected = [step.tool_name for step in plan.steps if step.tool_name not in allowed]
    if selected:
        raise AgentConflict(
            "planner selected capability outside the Run resolver snapshot: "
            + ", ".join(sorted(set(selected)))
        )


async def execute_agent_execution_job(job: AgentJob, session: AsyncSession) -> dict[str, Any]:
    """Run the durable planning/read/suggest phase for a previously-created Run.

    The handler deliberately reconstructs and revalidates ContextRef from the
    Run snapshot.  It never trusts arbitrary persisted arguments as a bypass for
    manifest Context Binding, and it never executes write tools.
    """
    runtime = AgentRuntimeService(session)
    run = await runtime.get_run(job.run_id, job.user_id)
    if run.status in TERMINAL_RUN_STATUSES or run.cancel_requested_at is not None:
        return {"status": "cancelled_or_terminal"}

    context = _dict(run.context_json)
    goal = str(context.get("goal") or "").strip()
    if not goal:
        raise ValueError("agent execution is missing goal")

    raw_refs = _list(context.get("context_refs"))
    requested_tools = [str(item).strip() for item in _list(context.get("requested_tools")) if str(item).strip()]
    legacy_arguments = _dict(context.get("arguments"))
    submitted_tool_arguments = {
        str(name): _dict(value)
        for name, value in _dict(context.get("tool_arguments")).items()
        if isinstance(value, dict)
    }
    replan_selected_tools = [str(item).strip() for item in _list(context.get("replan_selected_tools")) if str(item).strip()]
    is_replan = bool(replan_selected_tools)
    existing_plan_steps = [dict(item) for item in _list(context.get("plan_steps")) if isinstance(item, dict)]
    existing_results = [dict(item) for item in _list(context.get("tool_results")) if isinstance(item, dict)]
    replan_offset = int(context.get("replan_base_step_order") or 0) if is_replan else 0
    if is_replan:
        requested_tools = replan_selected_tools
        legacy_arguments = {}
        submitted_tool_arguments = {
            str(name): _dict(value)
            for name, value in _dict(context.get("replan_tool_arguments")).items()
            if isinstance(value, dict)
        }
    owner = _execution_owner(job)
    cancel_event = get_cancel_event(run.id)
    claimed_run = False
    run_generation = 0
    pending_visible_response: dict[str, Any] | None = None

    try:
        run = await runtime.claim_run(
            run_id=run.id,
            user_id=run.user_id,
            lease_owner=owner,
            lease_seconds=_runtime_settings().agent_run_lease_seconds,
        )
        claimed_run = True
        run_generation = int(run.lease_generation or 0)
        if run.status in TERMINAL_RUN_STATUSES or run.cancel_requested_at is not None or cancel_event.is_set():
            return {"status": "cancelled_or_terminal"}

        # New Runs have a relational resolver record. It is the authoritative
        # fence for planning/execution; legacy JSON remains an old-Run fallback.
        execution_facts = AgentExecutionService(session)
        context_facts = AgentContextService(session)
        plan_facts = AgentPlanService(session)
        run_session = await runtime.get_session(run.session_id, run.user_id)
        relational_context_snapshot = await _relational_context_snapshot(
            context_service=context_facts,
            run=run,
            context=context,
        )
        relational_snapshot = await execution_facts.get_run_snapshot(run.id)
        resolver_fence_context = context
        if relational_snapshot is not None:
            resolver_fence_context = {
                "capability_resolution": {
                    "tools": [
                        {"name": str(name)}
                        for name in relational_snapshot.selected_capability_ids_json
                    ]
                }
            }

        try:
            persisted_refs = [AgentContextRef.model_validate(item) for item in raw_refs]
        except Exception as exc:
            raise ContextRefValidationError("persisted Agent context references are invalid") from exc
        resolved_context = await resolve_agent_context_refs(
            session=session,
            user_id=run.user_id,
            session_project_id=run.project_id,
            refs=persisted_refs,
        )
        await runtime.update_run(
            run_id=run.id,
            user_id=run.user_id,
            status="planning",
            phase="planning",
            progress=max(10.0, float(run.progress or 0)),
        )
        await _publish_public_activity(
            runtime,
            run_id=run.id,
            user_id=run.user_id,
            action_id=f"context:{int(context.get('replan_revision') or 0)}",
            phase="planning",
            current_action="已锁定当前项目上下文，正在建立能力调用计划。",
            canonical_refs=resolved_context.canonical_refs(),
            completed_action="已解析项目、章节、版本与候选引用。",
            next_action="选择最合适的项目内能力。",
            expected_output="受控执行计划。",
            revision=int(context.get("replan_revision") or 0),
        )
        await runtime.append_event(
            run_id=run.id,
            user_id=run.user_id,
            event_type="planner_started",
            summary="正在选择受限项目内工具",
            data={"phase": "planning"},
        )
        await runtime.publish_progress(
            run_id=run.id,
            user_id=run.user_id,
            status="planning",
            phase="planning",
            progress=15,
            progress_message="正在根据目标和项目上下文选择能力。",
        )
        await _publish_public_activity(
            runtime,
            run_id=run.id,
            user_id=run.user_id,
            action_id=f"planner:{int(context.get('replan_revision') or 0)}",
            phase="planning",
            current_action="正在根据目标和项目上下文选择能力。",
            canonical_refs=resolved_context.canonical_refs(),
            completed_action="已确认可用上下文范围。",
            next_action="生成结构化执行计划。",
            expected_output="PlanDraft。",
            revision=int(context.get("replan_revision") or 0),
        )

        planner_context = resolved_context.planner_context()
        if is_replan:
            planner_context = {
                **planner_context,
                "replan_revision": int(context.get("replan_revision") or 1),
                "replan_reason": str(context.get("replan_reason") or "tool_failure")[:160],
                "completed_tool_results": context.get("tool_result_digests") if isinstance(context.get("tool_result_digests"), list) else [],
            }
        from .provider_attempt import ProviderAttemptLedger
        planner_attempts = ProviderAttemptLedger(run_id=run.id)
        decision = await AgentOrchestrator(LLMService(session)).plan(
            goal=goal,
            user_id=run.user_id,
            project_id=run.project_id,
            context_summary=planner_context,
            requested_tools=requested_tools,
            attempt_ledger=planner_attempts,
        )
        context["planner_provider_attempts"] = planner_attempts.snapshot()
        plan = decision.plan
        _assert_plan_uses_resolved_capabilities(plan, resolver_fence_context)
        if is_replan:
            metadata_by_tool = {
                str(item.get("tool_name")): item
                for item in _list(context.get("replan_plan_metadata"))
                if isinstance(item, dict) and str(item.get("tool_name") or "").strip()
            }
            for step in plan.steps:
                metadata = metadata_by_tool.get(step.tool_name, {})
                step.intent = str(metadata.get("intent") or "").strip()[:500] or None
                step.expected_result = str(metadata.get("expected_result") or "").strip()[:500] or None
                step.depends_on = [int(value) for value in _list(metadata.get("depends_on"))]
                step.planner_arguments = _dict(metadata.get("planner_arguments"))
                if step.intent:
                    step.description = step.intent
        planned_tools = [DEFAULT_TOOL_REGISTRY.get(step.tool_name) for step in plan.steps]
        planner_arguments_by_tool = {
            step.tool_name: dict(step.planner_arguments)
            for step in plan.steps
            if isinstance(step.planner_arguments, dict) and step.planner_arguments
        }
        if legacy_arguments:
            # Legacy input remains a one-tool compatibility path. User input wins
            # over Planner defaults; project_plan_arguments still rejects any
            # multi-tool broadcast before execution.
            only_defaults = planner_arguments_by_tool.get(plan.steps[0].tool_name, {}) if len(plan.steps) == 1 else {}
            effective_legacy_arguments = {**only_defaults, **legacy_arguments}
            effective_tool_arguments = submitted_tool_arguments
        else:
            effective_legacy_arguments = {}
            effective_tool_arguments = {name: dict(value) for name, value in submitted_tool_arguments.items()}
            for tool_name, planner_arguments in planner_arguments_by_tool.items():
                merged = dict(planner_arguments)
                merged.update(effective_tool_arguments.get(tool_name, {}))
                effective_tool_arguments[tool_name] = merged
        projected_tool_arguments = project_plan_arguments(
            tools=planned_tools,
            context=resolved_context,
            legacy_arguments=effective_legacy_arguments,
            tool_arguments=effective_tool_arguments,
        )
        for tool in planned_tools:
            DEFAULT_TOOL_REGISTRY.validate_planned_input(tool.name, projected_tool_arguments[tool.name])

        new_plan_steps = [
            {
                "order": replan_offset + index,
                "tool_name": step.tool_name,
                "risk_level": step.risk_level.value,
                "intent": step.intent,
                "expected_result": step.expected_result,
                "depends_on": [replan_offset + int(value) for value in step.depends_on],
                "planner_arguments": dict(step.planner_arguments),
            }
            for index, step in enumerate(plan.steps, start=1)
        ]
        plan_steps = existing_plan_steps if is_replan else new_plan_steps
        planned_context = _context_payload(
            existing=context,
            goal=goal,
            canonical_refs=resolved_context.canonical_refs(),
            requested_tools=requested_tools,
            legacy_arguments=legacy_arguments,
            tool_arguments=projected_tool_arguments,
            tool_results=existing_results if is_replan else [],
            plan_steps=plan_steps,
            execution_job_id=job.id,
            planner_provider_called=decision.provider_called,
            planner_fallback_reason=decision.fallback_reason,
        )
        displayed_plan_summary = (
            str(context.get("replan_visible_summary") or "").strip()[:500]
            if is_replan
            else decision.visible_summary
        ) or decision.visible_summary
        planned_context["planner_visible_summary"] = displayed_plan_summary
        planned_context["plan_mode"] = plan.mode
        # P1-A facts are additive: a new Run records the immutable planner
        # decision, while a legacy Run with no ContextSnapshot continues on the
        # existing JSON-only execution/recovery path unchanged.
        if not is_replan and relational_context_snapshot is not None:
            planner_id = f"agent_execution:{job.id}:initial"
            plan_revision = await plan_facts.get_revision_for_planner(
                run_id=run.id,
                planner_id=planner_id,
            )
            if plan_revision is None:
                plan_revision = await plan_facts.create_revision(
                    run=run,
                    session=run_session,
                    context_snapshot=relational_context_snapshot,
                    plan_json=_plan_revision_json(
                        goal=goal,
                        plan_mode=plan.mode,
                        steps=new_plan_steps,
                        requested_tools=requested_tools,
                        tool_arguments=projected_tool_arguments,
                        tool_results=[],
                        visible_summary=displayed_plan_summary,
                        provider_called=decision.provider_called,
                        fallback_reason=decision.fallback_reason,
                        phase="planning",
                    ),
                    planner_id=planner_id,
                    status="created",
                    rationale=displayed_plan_summary,
                )
            planned_context["relational_plan_revision_id"] = plan_revision.id
            planned_context["relational_plan_revision_key"] = plan_revision.revision_id
        await runtime.set_run_context(
            run_id=run.id,
            user_id=run.user_id,
            context=planned_context,
        )
        await runtime.append_event(
            run_id=run.id,
            user_id=run.user_id,
            event_type="plan_revised" if is_replan else "plan_created",
            summary=displayed_plan_summary,
            data=(
                {
                    "revision": int(context.get("replan_revision") or 1),
                    "step_count": len(plan.steps),
                    "phase": "replanning",
                    "provider_called": bool(context.get("replan_provider_called")),  # compatibility: Planner-only
                    "fallback_reason": context.get("replan_fallback_reason"),
                    "planner_provider_called": bool(context.get("replan_provider_called")),
                    "planner_provider_fallback_reason": context.get("replan_fallback_reason"),
                }
                if is_replan
                else {
                    "step_count": len(plan.steps),
                    "mode": plan.mode,
                    "provider_called": decision.provider_called,  # compatibility: Planner-only
                    "fallback_reason": decision.fallback_reason,
                    "planner_provider_called": decision.provider_called,
                    "planner_provider_fallback_reason": decision.fallback_reason,
                }
            ),
        )
        await _publish_public_activity(
            runtime,
            run_id=run.id,
            user_id=run.user_id,
            action_id=f"plan:{int(context.get('replan_revision') or 0)}",
            phase="replanning" if is_replan else "planning",
            current_action=("已修订后续执行计划。" if is_replan else "已生成执行计划。"),
            canonical_refs=resolved_context.canonical_refs(),
            completed_action="已完成能力选择与参数投影。",
            decision_summary=displayed_plan_summary,
            next_action="开始执行第一个受控步骤。",
            expected_output="项目内工具结果摘要。",
            revision=int(context.get("replan_revision") or 0),
        )
        for relative_index, step in enumerate(plan.steps, start=1):
            global_index = replan_offset + relative_index
            await runtime.append_event(
                run_id=run.id,
                user_id=run.user_id,
                event_type="plan_step_pending",
                summary=f"工具 {step.tool_name} 已加入执行计划",
                data={"tool_name": step.tool_name, "step": global_index, "phase": "replanning" if is_replan else "planning"},
            )
        await runtime.publish_progress(
            run_id=run.id,
            user_id=run.user_id,
            status="planning",
            phase="planning",
            progress=20,
            progress_message=f"计划已生成，准备执行 {len(plan.steps)} 个步骤。",
        )

        results: list[dict[str, Any]] = list(existing_results) if is_replan else []
        approvals = []
        failed_steps: list[dict[str, Any]] = []
        completed_step_orders: set[int] = set()
        for relative_index, step in enumerate(plan.steps, start=1):
            index = replan_offset + relative_index
            current_dependencies = [replan_offset + int(value) for value in step.depends_on]
            if cancel_event.is_set() or await runtime.is_cancel_requested(run_id=run.id, user_id=run.user_id):
                break
            step_arguments = projected_tool_arguments[step.tool_name]
            checkpoint = await runtime.ensure_step(
                run_id=run.id,
                user_id=run.user_id,
                step_order=index,
                tool_name=step.tool_name,
                idempotency_key=f"{run.id}:step:{index}:{step.tool_name}",
                input_payload={
                    "goal": goal,
                    "context_refs": resolved_context.canonical_refs(),
                    "tool_arguments": step_arguments,
                },
            )
            missing_dependencies = [dependency for dependency in current_dependencies if dependency not in completed_step_orders]
            if missing_dependencies:
                await runtime.fail_step(
                    step_id=checkpoint.id,
                    user_id=run.user_id,
                    error_type="DependencyNotCompleted",
                )
                await runtime.append_event(
                    run_id=run.id,
                    user_id=run.user_id,
                    event_type="plan_step_failed",
                    summary=f"{step.tool_name} 的前置步骤尚未完成",
                    data={"tool_name": step.tool_name, "step": index, "error_type": "DependencyNotCompleted", "phase": "planning"},
                )
                failed_steps.append({"step": index, "tool_name": step.tool_name, "error_type": "DependencyNotCompleted"})
                continue
            stored_input = _dict(checkpoint.input_json)
            stored_arguments = stored_input.get("tool_arguments")
            if isinstance(stored_arguments, dict):
                step_arguments = dict(stored_arguments)
            if checkpoint.status == "completed":
                completed_step_orders.add(index)
                results.append({"tool_name": step.tool_name, "result": _dict(checkpoint.output_json)})
                await runtime.append_event(
                    run_id=run.id,
                    user_id=run.user_id,
                    event_type="step_reused",
                    summary=f"已复用 {step.tool_name} 的已完成结果",
                    data={"tool_name": step.tool_name, "step": index, "phase": "checkpoint_replay"},
                )
                continue
            if step.risk_level.value not in {"read", "suggest"}:
                if checkpoint.status != "awaiting_approval":
                    checkpoint.status = "awaiting_approval"
                    await session.commit()
                approval = await runtime.request_approval(
                    run_id=run.id,
                    user_id=run.user_id,
                    step_id=checkpoint.id,
                    tool_name=step.tool_name,
                    project_id=run.project_id,
                    arguments={"goal": goal, **step_arguments},
                )
                approvals.append(approval)
                await runtime.append_event(
                    run_id=run.id,
                    user_id=run.user_id,
                    event_type="approval_required",
                    summary=f"工具 {step.tool_name} 等待用户审批",
                    data={"approval_id": approval.id, "tool_name": step.tool_name, "risk_level": step.risk_level.value},
                )
                continue

            step_start_progress = 20 + (relative_index - 1) * 60 / max(len(plan.steps), 1)
            await runtime.publish_progress(
                run_id=run.id,
                user_id=run.user_id,
                status="running",
                phase="tool_execution",
                step=index,
                tool_name=step.tool_name,
                progress=step_start_progress,
                progress_message=f"正在执行第 {index} 个工具：{step.tool_name}。",
            )
            await runtime.append_event(
                run_id=run.id,
                user_id=run.user_id,
                event_type="tool_call_started",
                summary=f"开始调用 {step.tool_name}",
                data={"tool_name": step.tool_name, "step": index, "phase": "tool_execution"},
            )
            await _publish_public_activity(
                runtime,
                run_id=run.id,
                user_id=run.user_id,
                action_id=f"step:{index}:started",
                phase="tool_execution",
                current_action=f"正在执行第 {index} 个项目能力：{step.tool_name}。",
                canonical_refs=resolved_context.canonical_refs(),
                completed_action="执行计划已生成。",
                selected_capability=step.tool_name,
                next_action="读取并整理该能力的受控结果。",
                expected_output=step.expected_result or "结构化工具结果。",
                step_order=index,
                revision=int(context.get("replan_revision") or 0),
            )
            capability_execution = None
            step_generation = 0
            try:
                checkpoint = await runtime.claim_step(
                    step_id=checkpoint.id,
                    user_id=run.user_id,
                    lease_owner=owner,
                    lease_seconds=_runtime_settings().agent_worker_lease_seconds,
                )
                step_generation = int(checkpoint.lease_generation or 0)
                if relational_snapshot is not None:
                    capability_execution = await execution_facts.begin_read_execution(
                        run=run,
                        step=checkpoint,
                        snapshot=relational_snapshot,
                        capability_id=step.tool_name,
                        arguments={"goal": goal, "tool_arguments": step_arguments},
                        lease_generation=step_generation,
                        idempotency_key=f"{run.id}:capability:{checkpoint.id}",
                    )
                result = await execute_read_tool(
                    tool_name=step.tool_name,
                    session=session,
                    user_id=run.user_id,
                    project_id=run.project_id,
                    arguments=step_arguments,
                    cancel_event=cancel_event,
                )
                result_payload = _dict(result)
                results.append({"tool_name": step.tool_name, "result": result_payload})
                await runtime.complete_step(
                    step_id=checkpoint.id,
                    user_id=run.user_id,
                    output=result_payload,
                    lease_owner=owner,
                    lease_generation=step_generation,
                )
                if capability_execution is not None:
                    await execution_facts.complete_read_execution(
                        execution=capability_execution,
                        lease_generation=step_generation,
                        output=result_payload,
                    )
                completed_step_orders.add(index)
                await runtime.append_event(
                    run_id=run.id,
                    user_id=run.user_id,
                    event_type="tool_call_completed",
                    summary=f"{step.tool_name} 已完成",
                    data={
                        "tool_name": step.tool_name,
                        "step": index,
                        "result_keys": list(result_payload.keys())[:20],
                        "phase": "tool_execution",
                    },
                )
                await _publish_public_activity(
                    runtime,
                    run_id=run.id,
                    user_id=run.user_id,
                    action_id=f"step:{index}:completed",
                    phase="tool_execution",
                    current_action=f"已完成第 {index} 个能力：{step.tool_name}。",
                    canonical_refs=resolved_context.canonical_refs(),
                    completed_action=f"{step.tool_name} 已返回受控结果。",
                    selected_capability=step.tool_name,
                    next_action="继续执行后续步骤或整理可见回复。",
                    expected_output="下一步执行状态或最终创作建议。",
                    step_order=index,
                    revision=int(context.get("replan_revision") or 0),
                )
                step_end_progress = 20 + relative_index * 60 / max(len(plan.steps), 1)
                await runtime.publish_progress(
                    run_id=run.id,
                    user_id=run.user_id,
                    status="running",
                    phase="tool_execution",
                    step=index,
                    tool_name=step.tool_name,
                    progress=step_end_progress,
                    progress_message=f"第 {index} 个工具已完成：{step.tool_name}。",
                )
            except ToolExecutionCancelled as exc:
                if capability_execution is not None:
                    await execution_facts.fail_read_execution(
                        execution=capability_execution,
                        lease_generation=step_generation,
                        error=exc,
                    )
                await runtime.cancel_step(step_id=checkpoint.id, user_id=run.user_id, lease_owner=owner, lease_generation=step_generation)
                await runtime.append_event(
                    run_id=run.id,
                    user_id=run.user_id,
                    event_type="tool_cancelled",
                    summary=f"{step.tool_name} 已取消",
                    data={"tool_name": step.tool_name, "step": index, "phase": "tool_execution"},
                )
                break
            except AgentConflict as exc:
                if capability_execution is not None:
                    await execution_facts.fail_read_execution(
                        execution=capability_execution,
                        lease_generation=step_generation,
                        error=exc,
                    )
                raise
            except Exception as exc:
                if capability_execution is not None:
                    await execution_facts.fail_read_execution(
                        execution=capability_execution,
                        lease_generation=step_generation,
                        error=exc,
                    )
                await runtime.fail_step(
                    step_id=checkpoint.id,
                    user_id=run.user_id,
                    error_type=type(exc).__name__,
                    lease_owner=owner,
                    lease_generation=step_generation,
                )
                await runtime.append_event(
                    run_id=run.id,
                    user_id=run.user_id,
                    event_type="tool_call_failed",
                    summary=f"{step.tool_name} 执行失败",
                    data={"tool_name": step.tool_name, "step": index, "error_type": type(exc).__name__, "phase": "tool_execution"},
                )
                await _publish_public_activity(
                    runtime,
                    run_id=run.id,
                    user_id=run.user_id,
                    action_id=f"step:{index}:failed",
                    phase="tool_execution",
                    current_action=f"第 {index} 个能力 {step.tool_name} 未成功完成。",
                    canonical_refs=resolved_context.canonical_refs(),
                    completed_action="失败步骤已被记录为可审计证据。",
                    selected_capability=step.tool_name,
                    decision_summary=f"失败类型：{type(exc).__name__}。",
                    next_action="检查是否满足一次性调整后续计划的条件。",
                    expected_output="受控重规划或明确失败说明。",
                    step_order=index,
                    revision=int(context.get("replan_revision") or 0),
                )
                failed_steps.append({"step": index, "tool_name": step.tool_name, "error_type": type(exc).__name__})

        run = await runtime.get_run(run.id, run.user_id)
        if cancel_event.is_set() or run.cancel_requested_at is not None or run.status in TERMINAL_RUN_STATUSES:
            return {"status": "cancelled", "step_count": len(plan.steps)}

        # One controlled replan is allowed only after an automatic read/suggest
        # failure.  It receives ToolResultDigest, never raw Step output, and it
        # may add only new low-risk tools.  The revision itself becomes another
        # durable agent_execution job so lease/retry/replay semantics stay intact.
        revisions = [dict(item) for item in _list(context.get("plan_revisions")) if isinstance(item, dict)]
        if (
            failed_steps
            and not is_replan
            and not requested_tools
            and not legacy_arguments
            and not approvals
            and len(revisions) < 1
        ):
            try:
                replan_context_summary = {
                    **resolved_context.planner_context(),
                    "replan": True,
                    "failed_steps": failed_steps[:8],
                    "completed_tool_results": build_tool_result_digests(results),
                }
                replan_decision = await AgentOrchestrator(LLMService(session)).plan(
                    goal=goal,
                    user_id=run.user_id,
                    project_id=run.project_id,
                    context_summary=replan_context_summary,
                    requested_tools=None,
                    attempt_ledger=planner_attempts,
                )
                known_tool_names = {str(item.get("tool_name") or "") for item in plan_steps}
                candidate_steps = list(replan_decision.plan.steps)
                _assert_plan_uses_resolved_capabilities(replan_decision.plan, resolver_fence_context)
                if (
                    candidate_steps
                    and all(step.tool_name not in known_tool_names for step in candidate_steps)
                    and all(step.risk_level.value in {"read", "suggest"} for step in candidate_steps)
                ):
                    candidate_tools = [DEFAULT_TOOL_REGISTRY.get(step.tool_name) for step in candidate_steps]
                    candidate_explicit = {
                        step.tool_name: dict(step.planner_arguments)
                        for step in candidate_steps
                        if isinstance(step.planner_arguments, dict) and step.planner_arguments
                    }
                    candidate_arguments = project_plan_arguments(
                        tools=candidate_tools,
                        context=resolved_context,
                        legacy_arguments={},
                        tool_arguments=candidate_explicit,
                    )
                    for tool in candidate_tools:
                        DEFAULT_TOOL_REGISTRY.validate_planned_input(tool.name, candidate_arguments[tool.name])
                    revision_number = len(revisions) + 1
                    base_step_order = max((int(item.get("order") or 0) for item in plan_steps), default=0)
                    revision_steps = [
                        {
                            "order": base_step_order + local_order,
                            "tool_name": step.tool_name,
                            "risk_level": step.risk_level.value,
                            "intent": step.intent,
                            "expected_result": step.expected_result,
                            "depends_on": [base_step_order + int(value) for value in step.depends_on],
                            "planner_arguments": dict(step.planner_arguments),
                        }
                        for local_order, step in enumerate(candidate_steps, start=1)
                    ]
                    replan_job = await AgentJobService(session).create_job(
                        run_id=run.id,
                        user_id=run.user_id,
                        project_id=run.project_id,
                        kind="agent_execution",
                        idempotency_key=f"{run.id}:agent_execution:revision:{revision_number}",
                        payload={"run_id": run.id, "phase": "replanning", "revision": revision_number},
                    )
                    revision_record = {
                        "revision": revision_number,
                        "reason": "tool_failure",
                        "failed_steps": failed_steps[:8],
                        "visible_summary": replan_decision.visible_summary,
                        "provider_called": replan_decision.provider_called,
                        "fallback_reason": replan_decision.fallback_reason,
                        "steps": revision_steps,
                    }
                    replan_run_context = _context_payload(
                        existing=_dict(run.context_json),
                        goal=goal,
                        canonical_refs=resolved_context.canonical_refs(),
                        requested_tools=[],
                        legacy_arguments={},
                        tool_arguments=projected_tool_arguments,
                        tool_results=results,
                        plan_steps=[*plan_steps, *revision_steps],
                        execution_job_id=replan_job.id,
                        planner_provider_called=decision.provider_called,
                        planner_fallback_reason=decision.fallback_reason,
                    )
                    replan_run_context.update(
                        {
                            "job_id": replan_job.id,
                            "plan_revisions": [*revisions, revision_record],
                            "replan_revision": revision_number,
                            "replan_reason": "tool_failure",
                            "replan_selected_tools": [step.tool_name for step in candidate_steps],
                            "replan_tool_arguments": candidate_arguments,
                            "replan_plan_metadata": [
                                {
                                    "tool_name": step.tool_name,
                                    "intent": step.intent,
                                    "expected_result": step.expected_result,
                                    "depends_on": list(step.depends_on),
                                    "planner_arguments": dict(step.planner_arguments),
                                }
                                for step in candidate_steps
                            ],
                            "replan_base_step_order": base_step_order,
                            "replan_provider_called": replan_decision.provider_called,
                            "replan_fallback_reason": replan_decision.fallback_reason,
                            "planner_visible_summary": replan_decision.visible_summary,
                            "replan_visible_summary": replan_decision.visible_summary,
                            "planner_provider_attempts": planner_attempts.snapshot(),
                        }
                    )
                    # Record the replan at the moment its durable job is
                    # created, not when that job later claims a lease.  This
                    # keeps parentage and the recoverable decision available
                    # across a worker crash/retry without changing JSON flow.
                    if relational_context_snapshot is not None:
                        replan_context_snapshot = await context_facts.create_snapshot(
                            run=run,
                            session=run_session,
                            context_json=replan_run_context,
                            refs=resolved_context.canonical_refs(),
                            context_kind="replan_context",
                        )
                        planner_id = f"agent_execution:{job.id}:replan:{revision_number}"
                        plan_revision = await plan_facts.get_revision_for_planner(
                            run_id=run.id,
                            planner_id=planner_id,
                        )
                        if plan_revision is None:
                            parent_revision = await plan_facts.get_latest_revision(run_id=run.id)
                            if parent_revision is None:
                                raise AgentPlanIntegrityError("replan requires an initial PlanRevision")
                            plan_revision = await plan_facts.create_revision(
                                run=run,
                                session=run_session,
                                context_snapshot=replan_context_snapshot,
                                parent_revision=parent_revision,
                                plan_json=_plan_revision_json(
                                    goal=goal,
                                    plan_mode=replan_decision.plan.mode,
                                    steps=revision_steps,
                                    requested_tools=[step.tool_name for step in candidate_steps],
                                    tool_arguments=candidate_arguments,
                                    tool_results=results,
                                    visible_summary=replan_decision.visible_summary,
                                    provider_called=replan_decision.provider_called,
                                    fallback_reason=replan_decision.fallback_reason,
                                    phase="replanning",
                                    replan_reason="tool_failure",
                                ),
                                planner_id=planner_id,
                                status="queued",
                                rationale="tool_failure",
                            )
                        replan_run_context["relational_context_snapshot_id"] = replan_context_snapshot.id
                        replan_run_context["relational_context_snapshot_key"] = replan_context_snapshot.snapshot_id
                        replan_run_context["relational_plan_revision_id"] = plan_revision.id
                        replan_run_context["relational_plan_revision_key"] = plan_revision.revision_id
                    await runtime.set_run_context(run_id=run.id, user_id=run.user_id, context=replan_run_context)
                    await runtime.publish_progress(
                        run_id=run.id,
                        user_id=run.user_id,
                        status="planning",
                        phase="replanning",
                        progress=75,
                        progress_message="前序工具失败，正在基于已完成结果调整后续计划。",
                    )
                    await runtime.append_event(
                        run_id=run.id,
                        user_id=run.user_id,
                        event_type="plan_revised",
                        summary=replan_decision.visible_summary,
                        data={
                            "revision": revision_number,
                            "step_count": len(candidate_steps),
                            "phase": "replanning",
                            "provider_called": replan_decision.provider_called,  # compatibility: Planner-only
                            "fallback_reason": replan_decision.fallback_reason,
                            "planner_provider_called": replan_decision.provider_called,
                            "planner_provider_fallback_reason": replan_decision.fallback_reason,
                        },
                    )
                    await _publish_public_activity(
                        runtime,
                        run_id=run.id,
                        user_id=run.user_id,
                        action_id=f"replan:{revision_number}",
                        phase="replanning",
                        current_action="前序能力失败，正在基于已完成结果调整后续计划。",
                        canonical_refs=resolved_context.canonical_refs(),
                        completed_action="已保存失败步骤和受控结果摘要。",
                        decision_summary=replan_decision.visible_summary,
                        next_action="执行修订后的低风险步骤。",
                        expected_output="新的受控工具结果。",
                        revision=revision_number,
                    )
                    return {
                        "status": "replan_queued",
                        "revision": revision_number,
                        "step_count": len(candidate_steps),
                        "agent_execution_job_id": replan_job.id,
                    }
            except Exception:
                # The original failed Step remains durable evidence. A replan
                # construction failure must not erase successful results or
                # promote an unvalidated fallback into execution.
                pass

        next_context = _context_payload(
            existing=_dict(run.context_json),
            goal=goal,
            canonical_refs=resolved_context.canonical_refs(),
            requested_tools=requested_tools,
            legacy_arguments=legacy_arguments,
            tool_arguments=projected_tool_arguments,
            tool_results=results,
            plan_steps=plan_steps,
            execution_job_id=job.id,
            planner_provider_called=decision.provider_called,
            planner_fallback_reason=decision.fallback_reason,
        )
        if approvals:
            await runtime.set_run_context(run_id=run.id, user_id=run.user_id, context=next_context)
            await runtime.publish_progress(
                run_id=run.id,
                user_id=run.user_id,
                status="awaiting_approval",
                phase="awaiting_approval",
                progress=60,
                progress_message="写入工具等待用户审批，尚未执行。",
            )
            await runtime.append_event(
                run_id=run.id,
                user_id=run.user_id,
                event_type="run_paused",
                summary="写入工具等待用户审批，尚未执行",
                data={"approval_count": len(approvals), "phase": "awaiting_approval"},
            )
            await _publish_public_activity(
                runtime,
                run_id=run.id,
                user_id=run.user_id,
                action_id="approval:pending",
                phase="awaiting_approval",
                current_action="正在等待用户批准写入候选。",
                canonical_refs=resolved_context.canonical_refs(),
                completed_action="已完成只读分析并创建写入审批。",
                selected_capability=approvals[0].tool_name if approvals else None,
                next_action="等待批准或拒绝。",
                expected_output="可执行候选或保持原正文。",
                revision=int(context.get("replan_revision") or 0),
            )
            return {"status": "awaiting_approval", "approval_count": len(approvals), "step_count": len(plan.steps)}

        await runtime.publish_progress(
            run_id=run.id,
            user_id=run.user_id,
            status="running",
            phase="assistant_response",
            progress=80,
            progress_message="工具步骤已完成，正在生成可见回复。",
        )
        visible_job = await AgentJobService(session).create_job(
            run_id=run.id,
            user_id=run.user_id,
            project_id=run.project_id,
            kind="visible_response",
            idempotency_key=f"{run.id}:visible_response",
            payload={"goal": goal, "tool_results": results},
        )
        next_context["job_id"] = visible_job.id
        next_context["visible_response_job_id"] = visible_job.id
        await runtime.set_run_context(run_id=run.id, user_id=run.user_id, context=next_context)
        await runtime.append_event(
            run_id=run.id,
            user_id=run.user_id,
            event_type="assistant_queued",
            summary="正在生成可见回复",
            data={
                "phase": "assistant_response",
                "provider_called": decision.provider_called,  # compatibility: Planner-only
                "planner_provider_called": decision.provider_called,
                "planner_provider_fallback_reason": decision.fallback_reason,
            },
        )
        await _publish_public_activity(
            runtime,
            run_id=run.id,
            user_id=run.user_id,
            action_id="response:queued",
            phase="assistant_response",
            current_action="工具步骤已完成，正在整理可见回复。",
            canonical_refs=resolved_context.canonical_refs(),
            completed_action="已完成当前计划的受控工具执行。",
            next_action="生成作者可见的综合回答。",
            expected_output="流式创作建议或项目摘要。",
            revision=int(context.get("replan_revision") or 0),
        )
        if _runtime_settings().agent_inline_visible_response:
            pending_visible_response = {
                "run_id": run.id,
                "session_id": run.session_id,
                "user_id": run.user_id,
                "goal": goal,
                "tool_results": results,
                "job_id": visible_job.id,
            }
        return {
            "status": "assistant_queued",
            "step_count": len(plan.steps),
            "tool_result_count": len(results),
            "visible_response_job_id": visible_job.id,
        }
    finally:
        if claimed_run:
            try:
                await runtime.release_run(run_id=run.id, user_id=run.user_id, lease_owner=owner, lease_generation=run_generation)
            except Exception:
                pass
        if pending_visible_response is not None:
            launch_visible_response(**pending_visible_response)
        else:
            release_cancel_event(run.id)


async def _run_inline_agent_execution(*, job_id: str, run_id: str, user_id: int) -> None:
    owner = f"inline-execution:{socket.gethostname()}:{os.getpid()}"[:128]
    try:
        async with AsyncSessionLocal() as session:
            jobs = AgentJobService(session)
            try:
                job = await jobs.claim_job(
                    job_id=job_id,
                    user_id=user_id,
                    lease_owner=owner,
                    lease_seconds=_runtime_settings().agent_worker_lease_seconds,
                )
                job_generation = int(job.lease_generation or 0)
            except AgentJobConflict:
                return
            try:
                result = await execute_agent_execution_job(job, session)
                await jobs.complete(job_id=job.id, user_id=user_id, lease_owner=owner, lease_generation=job_generation, result=result)
            except Exception as exc:
                runtime = AgentRuntimeService(session)
                try:
                    run = await runtime.get_run(run_id, user_id)
                    if run.status not in TERMINAL_RUN_STATUSES:
                        await runtime.update_run(run_id=run_id, user_id=user_id, status="failed", phase="execution_error")
                        await runtime.append_event(
                            run_id=run_id,
                            user_id=user_id,
                            event_type="run_failed",
                            summary="Agent 执行任务失败",
                            data={"error_type": type(exc).__name__, "phase": "execution_error"},
                        )
                finally:
                    await jobs.fail(
                        job_id=job.id,
                        user_id=user_id,
                        lease_owner=owner,
                        lease_generation=job_generation,
                        error_type=type(exc).__name__,
                        detail="inline agent execution failed",
                    )
    finally:
        _EXECUTION_TASKS.pop(run_id, None)
        release_cancel_event(run_id)


def launch_agent_execution(*, job_id: str, run_id: str, user_id: int) -> None:
    """Start a local durable-job claimant for development/single-process mode."""
    existing = _EXECUTION_TASKS.get(run_id)
    if existing is not None and not existing.done():
        return
    get_cancel_event(run_id)
    _EXECUTION_TASKS[run_id] = asyncio.create_task(
        _run_inline_agent_execution(job_id=job_id, run_id=run_id, user_id=user_id)
    )


async def recover_agent_execution(*, run_id: str, user_id: int) -> bool:
    """Re-launch a queued execution only when the durable job still permits claim."""
    existing = _EXECUTION_TASKS.get(run_id)
    if existing is not None and not existing.done():
        return False
    async with AsyncSessionLocal() as session:
        runtime = AgentRuntimeService(session)
        run = await runtime.get_run(run_id, user_id)
        if run.status in TERMINAL_RUN_STATUSES:
            return False
        context = _dict(run.context_json)
        job_id = str(context.get("execution_job_id") or "").strip()
        if not job_id:
            return False
        try:
            job = await AgentJobService(session).get_job(job_id=job_id, user_id=user_id)
        except Exception:
            return False
        if job.kind != "agent_execution" or job.status not in {"queued", "running"}:
            return False
        if run.status == "paused":
            await runtime.update_run(run_id=run.id, user_id=user_id, status="planning", phase="recovered", progress=max(10.0, run.progress))
        if _runtime_settings().agent_inline_execution:
            launch_agent_execution(job_id=job.id, run_id=run.id, user_id=user_id)
        # In worker-only deployments the queued/expired durable job is the
        # recovery action; do not fall through to visible-response recovery.
        return True
