"""Stage-eight pure frozen-plan contract; no enqueue, ORM lazy load or IO.

Callers supply fully loaded rows and independently verified context/capability
content. This contract verifies plan content plus all available row bindings;
it does not attest write-execution facts, artifact validity or current access.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from hashlib import sha256
import json
import math
import re
from types import MappingProxyType
from typing import Any


class ContinuationPlanError(ValueError):
    """A fixed contract field, never input material, identifies the failure."""

    def __init__(self, field: str):
        self.field = field
        super().__init__(f"continuation plan contract mismatch for {field}")


@dataclass(frozen=True, slots=True)
class FrozenContinuationStep:
    order: int
    tool_name: str
    depends_on: tuple[int, ...]
    arguments: Mapping[str, Any]
    planner_arguments: Mapping[str, Any]
    risk_level: str


@dataclass(frozen=True, slots=True)
class FrozenContinuationPlan:
    steps: tuple[FrozenContinuationStep, ...]
    payload: Mapping[str, Any] = field(repr=False)

    def to_payload(self) -> dict[str, Any]:
        """Return a detached JSON object containing locator/digest scalars only."""
        return dict(self.payload)


# Matches agent_plan_service.plan_revision_material (including all its metadata;
# neither the SQL row id nor its own digest participates in that material).
_PLAN_FIELDS = (
    "revision_id", "run_id", "session_id", "context_snapshot_id", "parent_revision_id",
    "revision_number", "user_id", "project_id", "correlation_id", "transaction_id",
    "planner_id", "status", "rationale", "plan_json",
)
_OUTCOMES = frozenset({"executed", "rejected", "execution_failed"})
_RISKS = frozenset({"read", "suggest", "write", "destructive", "manage"})


def _fail(name: str) -> None:
    raise ContinuationPlanError(name)


def _attr(row: Any, key: str, prefix: str) -> Any:
    # vars reads loaded ORM scalars only; getattr could start SQL via an expired
    # attribute/relationship. Slots-only adapters should expose loaded records.
    try:
        values = vars(row)
    except TypeError:
        _fail(prefix)
    if key not in values:
        _fail(f"{prefix}.{key}")
    return values[key]


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(name)
    return value


def _positive(value: Any, name: str) -> int:
    if type(value) is not int or value <= 0:
        _fail(name)
    return value


def _json(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        result = {}
        for key, child in value.items():
            if not isinstance(key, str):
                _fail(name)
            result[key] = _json(child, name)
        return result
    if isinstance(value, (list, tuple)):
        return [_json(child, name) for child in value]
    if value is None or type(value) in (str, int, bool):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    _fail(name)


def _canonical(value: Any, name: str) -> str:
    try:
        return json.dumps(_json(value, name), ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, RecursionError, OverflowError):
        _fail(name)


def _same(actual: Any, expected: Any, name: str) -> None:
    if _canonical(actual, name) != _canonical(expected, name):
        _fail(name)


def _object(value: Any, name: str) -> dict:
    if not isinstance(value, Mapping):
        _fail(name)
    # Validate/copy even values not selected below; never silently stringify them.
    try:
        return json.loads(_canonical(value, name))
    except (ValueError, RecursionError):
        _fail(name)


def _array(value: Any, name: str) -> list:
    if not isinstance(value, (list, tuple)):
        _fail(name)
    return list(value)


def _digest(value: Any, name: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        _fail(name)
    return value


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(child) for key, child in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(child) for child in value)
    return value


def load_continuation_plan(
    *, run, revision, context_snapshot, capability_snapshot, approval,
    approval_step, source_job, expected_actor_user_id: int | None = None,
) -> FrozenContinuationPlan:
    """Freeze one terminal approval against the current persisted PlanRevision.

    No source-job ACK gate is imposed here. Only executed requires a completed
    approval step; consumers must also validate successful write facts/artifacts.
    Extra actor_user_id requires an independent trusted actor; all other fields
    must exactly equal the producer's {goal: plan_goal, **frozen_arguments}.
    """
    run_id = _text(_attr(run, "id", "run"), "run.id")
    scope = {key: _attr(run, key, "run") for key in
             ("user_id", "project_id", "session_id", "correlation_id", "transaction_id")}
    _positive(scope["user_id"], "run.user_id")
    for key in ("session_id", "correlation_id"):
        _text(scope[key], f"run.{key}")
    for key in ("project_id", "transaction_id"):
        if scope[key] is not None:
            _text(scope[key], f"run.{key}")
    rows = (("revision", revision), ("context_snapshot", context_snapshot),
            ("capability_snapshot", capability_snapshot), ("approval", approval),
            ("approval_step", approval_step), ("source_job", source_job))
    ids = {}
    for prefix, row in rows:
        ids[prefix] = _text(_attr(row, "id", prefix), f"{prefix}.id")
        _same(_attr(row, "run_id", prefix), run_id, f"{prefix}.run_id")
        # These are actual schema fields, not fabricated session/correlation
        # columns on capability rows or project/session columns on step rows.
        keys = ["user_id", "transaction_id"]
        if prefix != "approval_step": keys.append("project_id")
        if prefix != "capability_snapshot": keys.append("correlation_id")
        if prefix in {"revision", "context_snapshot"}: keys.append("session_id")
        for key in keys:
            _same(_attr(row, key, prefix), scope[key], f"{prefix}.{key}")

    context = _object(_attr(run, "context_json", "run"), "run.context_json")
    material = {key: _attr(revision, key, "revision") for key in _PLAN_FIELDS}
    plan_digest = _digest(_attr(revision, "digest", "revision"), "revision.digest")
    try:
        computed = sha256(_canonical(material, "revision.digest").encode("utf-8")).hexdigest()
    except UnicodeError:
        _fail("revision.digest")
    _same(plan_digest, computed, "revision.digest")
    plan = _object(material["plan_json"], "revision.plan_json")
    _same(plan.get("schema_version"), 1, "revision.plan_json.schema_version")
    _positive(material["revision_number"], "revision.revision_number")
    revision_key = _text(material["revision_id"], "revision.revision_id")
    _same(material["context_snapshot_id"], ids["context_snapshot"], "revision.context_snapshot_id")
    context_key = _text(_attr(context_snapshot, "snapshot_id", "context_snapshot"), "context_snapshot.snapshot_id")
    context_digest = _digest(_attr(context_snapshot, "digest", "context_snapshot"), "context_snapshot.digest")
    _same(_attr(context_snapshot, "schema_version", "context_snapshot"), 1, "context_snapshot.schema_version")
    phase = plan.get("phase")
    if phase not in ("planning", "replanning"):
        _fail("revision.plan_json.phase")
    _same(_attr(context_snapshot, "context_kind", "context_snapshot"),
          "run_initial_context" if phase == "planning" else "replan_context", "context_snapshot.context_kind")
    if phase == "replanning":
        _text(material["parent_revision_id"], "revision.parent_revision_id")
        if material["parent_revision_id"] == ids["revision"]:
            _fail("revision.parent_revision_id")
    elif material["parent_revision_id"] is not None:
        _fail("revision.parent_revision_id")

    capability_digest = _digest(_attr(capability_snapshot, "digest", "capability_snapshot"), "capability_snapshot.digest")
    capability_key = _text(_attr(capability_snapshot, "snapshot_id", "capability_snapshot"), "capability_snapshot.snapshot_id")
    resolver_version = _positive(_attr(capability_snapshot, "resolver_schema_version", "capability_snapshot"), "capability_snapshot.resolver_schema_version")
    _same(capability_key, f"resolver-v{resolver_version}:{capability_digest[:16]}:run:{run_id}", "capability_snapshot.snapshot_id")
    bindings = {
        "relational_plan_revision_id": ids["revision"], "relational_plan_revision_key": revision_key,
        "relational_context_snapshot_id": ids["context_snapshot"], "relational_context_snapshot_key": context_key,
        "relational_capability_snapshot_id": ids["capability_snapshot"],
        "relational_capability_snapshot_key": capability_key, "relational_capability_snapshot_digest": capability_digest,
    }
    for key, expected in bindings.items():
        _same(context.get(key), expected, f"run.context_json.{key}")

    selected = _array(_attr(capability_snapshot, "selected_capability_ids_json", "capability_snapshot"), "capability_snapshot.selected_capability_ids_json")
    for name in selected: _text(name, "capability_snapshot.selected_capability_ids_json")
    if len(selected) != len(set(selected)):
        _fail("capability_snapshot.selected_capability_ids_json")
    projected = _object(plan.get("tool_arguments"), "revision.plan_json.tool_arguments")
    raw_steps = _array(plan.get("steps"), "revision.plan_json.steps")
    if not raw_steps: _fail("revision.plan_json.steps")
    steps = []
    seen = set()
    last_order = 0
    for raw in raw_steps:
        item = _object(raw, "revision.plan_json.steps")
        order = _positive(item.get("order"), "plan_step.order")
        if order <= last_order: _fail("plan_step.order")
        name = _text(item.get("tool_name"), "plan_step.tool_name")
        if name not in selected: _fail("plan_step.tool_name")
        risk = _text(item.get("risk_level"), "plan_step.risk_level")
        if risk not in _RISKS: _fail("plan_step.risk_level")
        deps = _array(item.get("depends_on"), "plan_step.depends_on")
        for dep in deps:
            _positive(dep, "plan_step.depends_on")
            if dep not in seen: _fail("plan_step.depends_on")
        if len(deps) != len(set(deps)): _fail("plan_step.depends_on")
        suggestions = _object(item.get("planner_arguments"), "plan_step.planner_arguments")
        arguments = _object(projected.get(name), "plan_step.arguments")
        steps.append(FrozenContinuationStep(order, name, tuple(deps), _freeze(arguments), _freeze(suggestions), risk))
        seen.add(order)
        last_order = order

    _same(_attr(approval, "step_id", "approval"), ids["approval_step"], "approval.step_id")
    step_order = _positive(_attr(approval_step, "step_order", "approval_step"), "approval_step.step_order")
    frozen_step = next((item for item in steps if item.order == step_order), None)
    if frozen_step is None: _fail("approval_step.step_order")
    for prefix, row in (("approval", approval), ("approval_step", approval_step)):
        _same(_attr(row, "tool_name", prefix), frozen_step.tool_name, f"{prefix}.tool_name")
    if frozen_step.risk_level in {"read", "suggest"}: _fail("approval_step.risk_level")
    _same(_attr(approval_step, "idempotency_key", "approval_step"),
          f"{run_id}:step:{step_order}:{frozen_step.tool_name}", "approval_step.idempotency_key")
    goal = _text(plan.get("goal"), "revision.plan_json.goal")
    stored_input = _object(_attr(approval_step, "input_json", "approval_step"), "approval_step.input_json")
    bound_source = stored_input.get("approval_source_job_id")
    if "approval_source_job_id" in stored_input:
        _text(bound_source, "approval_step.input_json.approval_source_job_id")
        _same(bound_source, ids["source_job"], "approval_step.input_json.approval_source_job_id")
    _same(stored_input.get("goal"), goal, "approval_step.input_json.goal")
    _same(stored_input.get("tool_arguments"), frozen_step.arguments, "approval_step.input_json.tool_arguments")
    arguments = _object(_attr(approval, "request_json", "approval"), "approval.request_json")
    expected = {"goal": goal, **dict(frozen_step.arguments)}
    if expected_actor_user_id is not None:
        _positive(expected_actor_user_id, "expected_actor_user_id")
    if "actor_user_id" in expected:
        _positive(expected["actor_user_id"], "approval.actor_user_id")
        if expected_actor_user_id is not None:
            _same(expected["actor_user_id"], expected_actor_user_id, "approval.actor_user_id")
    elif "actor_user_id" in arguments:
        if expected_actor_user_id is None: _fail("approval.actor_user_id")
        expected["actor_user_id"] = expected_actor_user_id
    _same(arguments, expected, "approval.request_json")
    outcome = _attr(approval, "status", "approval")
    if not isinstance(outcome, str) or outcome not in _OUTCOMES: _fail("approval.status")
    if outcome == "executed":
        _same(_attr(approval_step, "status", "approval_step"), "completed", "approval_step.status")

    payload = {
        "schema_version": 1, "run_id": run_id, "source_job_id": ids["source_job"],
        "plan_revision_id": ids["revision"], "plan_revision_key": revision_key, "plan_revision_digest": plan_digest,
        "context_snapshot_id": ids["context_snapshot"], "context_snapshot_key": context_key, "context_snapshot_digest": context_digest,
        "capability_snapshot_id": ids["capability_snapshot"], "capability_snapshot_key": capability_key, "capability_snapshot_digest": capability_digest,
        "approval_id": ids["approval"], "step_id": ids["approval_step"], "outcome": outcome,
    }
    kind = _attr(source_job, "kind", "source_job")
    if kind not in ("agent_execution", "agent_continuation"): _fail("source_job.kind")
    source_payload = _object(_attr(source_job, "payload_json", "source_job"), "source_job.payload_json")
    # Legacy programmatic initial jobs may have payload={}; their row scope,
    # current execution locator and exact initial planner_id still bind them.
    # A present value (including null) is never treated as an omitted field.
    if kind != "agent_execution" or phase != "planning" or "run_id" in source_payload:
        _same(source_payload.get("run_id"), run_id, "source_job.payload_json.run_id")
    if kind == "agent_continuation":
        for key in ("schema_version", "run_id", "plan_revision_id", "plan_revision_key", "plan_revision_digest",
                    "context_snapshot_id", "context_snapshot_key", "context_snapshot_digest",
                    "capability_snapshot_id", "capability_snapshot_key", "capability_snapshot_digest"):
            _same(source_payload.get(key), payload[key], f"source_job.payload_json.{key}")
    else:
        # The checkpoint is the per-approval source binding. The mutable latest
        # execution pointer is only the compatibility fence for older checkpoints.
        if bound_source is None:
            _same(context.get("execution_job_id"), ids["source_job"], "run.context_json.execution_job_id")
        if phase == "planning":
            _same(material["planner_id"], f"agent_execution:{ids['source_job']}:initial", "revision.planner_id")
        else:
            frozen_context = _object(_attr(context_snapshot, "context_json", "context_snapshot"), "context_snapshot.context_json")
            _same(frozen_context.get("execution_job_id"), ids["source_job"], "source_job.replan_context")
            _same(source_payload.get("phase"), "replanning", "source_job.payload_json.phase")
            number = _positive(source_payload.get("revision"), "source_job.payload_json.revision")
            planner_id = _text(material["planner_id"], "revision.planner_id")
            if re.fullmatch(r"agent_execution:[^:]+:replan:" + str(number), planner_id) is None:
                _fail("revision.planner_id")
    return FrozenContinuationPlan(tuple(steps), MappingProxyType(payload))
