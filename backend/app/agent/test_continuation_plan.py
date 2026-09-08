"""Stage-eight frozen continuation contract: pure checks and an in-memory Runtime fixture."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
from hashlib import sha256
import json
from types import SimpleNamespace

import pytest

from app.agent.continuation_plan import (
    ContinuationPlanError, FrozenContinuationPlan, load_continuation_plan,
)
from app.services.agent_plan_service import plan_revision_material
from app.services.agent_context_service import canonical_digest


PAYLOAD_KEYS = {
    "schema_version", "run_id", "source_job_id", "plan_revision_id", "plan_revision_key", "plan_revision_digest",
    "context_snapshot_id", "context_snapshot_key", "context_snapshot_digest",
    "capability_snapshot_id", "capability_snapshot_key", "capability_snapshot_digest",
    "approval_id", "step_id", "outcome",
}


def case(*, replan=False, outcome="executed", actor=None):
    scope = dict(run_id="run-1", user_id=11, project_id="project-1", session_id="session-1",
                 correlation_id="correlation-1", transaction_id="transaction-1")
    run = SimpleNamespace(id=scope["run_id"], **{k: v for k, v in scope.items() if k != "run_id"})
    start = 7 if replan else 1
    args = {"chapter_number": 3, "options": {"tags": ["中文", {"enabled": True}]}}
    if actor is not None:
        args["actor_user_id"] = actor
    plan = {"schema_version": 1, "goal": "生成候选再统计", "mode": "multi_step",
            "phase": "replanning" if replan else "planning",
            "steps": [
                {"order": start, "tool_name": "chapter.generate", "risk_level": "write", "depends_on": [],
                 "planner_arguments": {"chapter_number": 3, "hints": ["保留"]}, "intent": "生成", "expected_result": "候选"},
                {"order": start+1, "tool_name": "statistics.project", "risk_level": "read", "depends_on": [start],
                 "planner_arguments": {}, "intent": "统计", "expected_result": "统计"}],
            "tool_arguments": {"chapter.generate": args, "statistics.project": {"detail": [1, 2]}},
            "requested_tools": ["chapter.generate", "statistics.project"], "tool_result_digests": [],
            "visible_summary": "执行冻结计划", "provider_called": False, "fallback_reason": None,
            "planner_provider_called": False, "planner_provider_fallback_reason": None,
            "replan_reason": "tool_failure" if replan else None}
    context = SimpleNamespace(id="context-row", snapshot_id="context-key", digest="c"*64, schema_version=1,
                              context_kind="replan_context" if replan else "run_initial_context", **scope)
    cap_scope = {k: scope[k] for k in ("run_id", "user_id", "project_id", "transaction_id")}
    cap = SimpleNamespace(id="capability-row", snapshot_id="resolver-v1:"+"d"*16+":run:run-1", digest="d"*64,
                          resolver_schema_version=1, selected_capability_ids_json=["chapter.generate", "statistics.project"], **cap_scope)
    revision = SimpleNamespace(id="revision-row", revision_id="revision-key", context_snapshot_id=context.id,
                               parent_revision_id="parent-revision" if replan else None, revision_number=2 if replan else 1,
                               planner_id="agent_execution:previous-job:replan:1" if replan else "agent_execution:source-job:initial",
                               status="queued" if replan else "created", rationale=None, plan_json=plan, **scope)
    revision.digest = canonical_digest(plan_revision_material(revision))
    row_scope = {k: scope[k] for k in ("run_id", "user_id", "correlation_id", "transaction_id")}
    step = SimpleNamespace(id="step-1", step_order=start, tool_name="chapter.generate",
                           idempotency_key=f"run-1:step:{start}:chapter.generate",
                           status="completed" if outcome == "executed" else "awaiting_approval",
                           input_json={"goal": plan["goal"], "context_refs": [], "tool_arguments": deepcopy(args)}, **row_scope)
    approval = SimpleNamespace(id="approval-1", step_id=step.id, tool_name=step.tool_name, status=outcome,
                               request_json={"goal": plan["goal"], **deepcopy(args)}, project_id=run.project_id, **row_scope)
    source = SimpleNamespace(id="source-job", kind="agent_execution", status="running", project_id=run.project_id,
                             payload_json={"run_id": run.id, **({"phase": "replanning", "revision": 1} if replan else {})}, **row_scope)
    context.context_json = {"context_refs": [], "execution_job_id": source.id} if replan else {"context_refs": []}
    run.context_json = {
        "relational_plan_revision_id": revision.id, "relational_plan_revision_key": revision.revision_id,
        "relational_context_snapshot_id": context.id, "relational_context_snapshot_key": context.snapshot_id,
        "relational_capability_snapshot_id": cap.id, "relational_capability_snapshot_key": cap.snapshot_id,
        "relational_capability_snapshot_digest": cap.digest, "execution_job_id": source.id,
        "replan_base_step_order": 6 if replan else 0,
    }
    return dict(run=run, revision=revision, context_snapshot=context, capability_snapshot=cap,
                approval=approval, approval_step=step, source_job=source)


def rehash(f):
    f["revision"].digest = canonical_digest(plan_revision_material(f["revision"]))


def reject(f, field=None):
    with pytest.raises(ContinuationPlanError) as exc:
        load_continuation_plan(**f)
    if field:
        assert exc.value.field == field
    assert len(str(exc.value)) < 180
    assert "PRIVATE_SENTINEL" not in str(exc.value)
    return exc.value


@pytest.mark.parametrize("replan", [False, True])
@pytest.mark.parametrize("outcome", ["executed", "rejected", "execution_failed"])
def test_initial_and_replan_terminal_outcomes(replan, outcome):
    f = case(replan=replan, outcome=outcome)
    result = load_continuation_plan(**f)
    assert isinstance(result, FrozenContinuationPlan)
    assert isinstance(result.steps, tuple)
    start = 7 if replan else 1
    assert [s.order for s in result.steps] == [start, start+1]
    assert result.steps[1].depends_on == (start,)
    assert result.steps[0].arguments["chapter_number"] == 3
    assert result.steps[0].planner_arguments["hints"] == ("保留",)
    payload = result.to_payload()
    assert set(payload) == PAYLOAD_KEYS
    assert payload == {
        "schema_version": 1, "run_id": "run-1", "source_job_id": "source-job",
        "plan_revision_id": "revision-row", "plan_revision_key": "revision-key", "plan_revision_digest": f["revision"].digest,
        "context_snapshot_id": "context-row", "context_snapshot_key": "context-key", "context_snapshot_digest": "c"*64,
        "capability_snapshot_id": "capability-row", "capability_snapshot_key": f["capability_snapshot"].snapshot_id,
        "capability_snapshot_digest": "d"*64, "approval_id": "approval-1", "step_id": "step-1", "outcome": outcome}
    assert json.loads(json.dumps(payload)) == payload
    assert "goal" not in payload and "steps" not in payload and "arguments" not in payload


def test_frozen_nested_values_and_detached_payload():
    f = case()
    before = deepcopy(f)
    result = load_continuation_plan(**f)
    assert f == before
    with pytest.raises(FrozenInstanceError): result.steps = ()
    with pytest.raises(FrozenInstanceError): result.steps[0].order = 9
    with pytest.raises(TypeError): result.steps[0].arguments["new"] = 1
    with pytest.raises(TypeError): result.steps[0].arguments["options"]["tags"][1]["enabled"] = False
    with pytest.raises(TypeError): result.steps[0].planner_arguments["new"] = 1
    payload = result.to_payload()
    payload["run_id"] = "other"
    f["revision"].plan_json["tool_arguments"]["chapter.generate"]["options"]["tags"].append("late")
    assert result.to_payload()["run_id"] == "run-1"
    assert len(result.steps[0].arguments["options"]["tags"]) == 2


def test_json_list_tuple_and_mapping_key_order_roundtrip():
    f = case()
    f["revision"].plan_json["steps"][1]["depends_on"] = (1,)
    f["revision"].plan_json["tool_arguments"]["statistics.project"]["detail"] = (1, 2)
    rehash(f)
    result = load_continuation_plan(**f)
    f["revision"].plan_json = json.loads(json.dumps(f["revision"].plan_json))
    assert load_continuation_plan(**f) == result


@pytest.mark.parametrize("owner,field", [
    (owner, field) for owner in ("revision", "context_snapshot")
    for field in ("run_id", "user_id", "project_id", "session_id", "correlation_id", "transaction_id")
] + [(owner, field) for owner in ("approval", "source_job")
     for field in ("run_id", "user_id", "project_id", "correlation_id", "transaction_id")]
  + [("approval_step", field) for field in ("run_id", "user_id", "correlation_id", "transaction_id")]
  + [("capability_snapshot", field) for field in ("run_id", "user_id", "project_id", "transaction_id")])
def test_all_real_model_identity_fields_match_run(owner, field):
    f = case()
    setattr(f[owner], field, 99 if field == "user_id" else "PRIVATE_SENTINEL")
    if owner == "revision": rehash(f)
    reject(f, f"{owner}.{field}")


@pytest.mark.parametrize("field", ["relational_plan_revision_id", "relational_plan_revision_key", "relational_context_snapshot_id", "relational_context_snapshot_key", "relational_capability_snapshot_id", "relational_capability_snapshot_key", "relational_capability_snapshot_digest", "execution_job_id"])
@pytest.mark.parametrize("value", [None, "other"])
def test_current_run_locator_mismatch_rejected(field, value):
    f = case()
    f["run"].context_json[field] = value
    reject(f)


def test_revision_context_parent_not_only_digest():
    f = case()
    f["revision"].context_snapshot_id = "other-context"
    rehash(f)
    reject(f, "revision.context_snapshot_id")


@pytest.mark.parametrize("mutation", ["order", "tool_name", "depends_on", "planner_arguments", "tool_arguments", "goal", "status", "parent_revision_id", "rationale"])
def test_old_plan_digest_rejects_all_frozen_material_changes(mutation):
    f = case()
    plan = f["revision"].plan_json
    if mutation in {"status", "parent_revision_id", "rationale"}: setattr(f["revision"], mutation, "changed")
    elif mutation == "tool_arguments": plan[mutation]["chapter.generate"]["chapter_number"] = 99
    elif mutation == "goal": plan[mutation] = "PRIVATE_SENTINEL"
    else: plan["steps"][1][mutation] = {"order": 9, "tool_name": "chapter.generate", "depends_on": [], "planner_arguments": {"x": 1}}[mutation]
    reject(f, "revision.digest")


@pytest.mark.parametrize("owner", ["revision", "context_snapshot", "capability_snapshot"])
@pytest.mark.parametrize("digest", [None, "", "x"*64, "A"*64, "f"*63])
def test_malformed_digests_rejected(owner, digest):
    f = case()
    f[owner].digest = digest
    reject(f)


@pytest.mark.parametrize("version", [True, "1", 0, 2])
def test_plan_schema_strict(version):
    f = case()
    f["revision"].plan_json["schema_version"] = version
    rehash(f)
    reject(f, "revision.plan_json.schema_version")


@pytest.mark.parametrize("value", [float("nan"), float("inf"), object(), {1}, {1: "bad-key"}])
def test_non_json_material_is_controlled(value):
    f = case()
    f["revision"].plan_json["tool_arguments"]["statistics.project"]["bad"] = value
    reject(f)


@pytest.mark.parametrize("orders", [[1, 1], [2, 1], [True, 2], [0, 2], ["1", 2]])
def test_invalid_global_orders_rejected_after_rehash(orders):
    f = case()
    for step, order in zip(f["revision"].plan_json["steps"], orders): step["order"] = order
    rehash(f)
    reject(f)


@pytest.mark.parametrize("deps", [[2], [99], [1, 1], [True], [0], ["1"], "1"])
def test_invalid_dependency_graph_rejected_after_rehash(deps):
    f = case()
    f["revision"].plan_json["steps"][1]["depends_on"] = deps
    rehash(f)
    reject(f)


@pytest.mark.parametrize("field", ["order", "tool_name", "depends_on", "planner_arguments", "risk_level"])
def test_required_frozen_step_fields(field):
    f = case()
    del f["revision"].plan_json["steps"][0][field]
    rehash(f)
    reject(f)


def test_projected_tool_arguments_not_planner_suggestions():
    f = case()
    f["revision"].plan_json["steps"][0]["planner_arguments"]["chapter_number"] = 88
    rehash(f)
    result = load_continuation_plan(**f)
    assert result.steps[0].planner_arguments["chapter_number"] == 88
    assert result.steps[0].arguments["chapter_number"] == 3


def test_missing_per_tool_arguments_rejected():
    f = case()
    del f["revision"].plan_json["tool_arguments"]["statistics.project"]
    rehash(f)
    reject(f)


def test_plan_tool_outside_capability_snapshot_rejected():
    f = case()
    f["capability_snapshot"].selected_capability_ids_json = ["chapter.generate"]
    reject(f)


@pytest.mark.parametrize("field,value", [("step_id", "other"), ("tool_name", "statistics.project")])
def test_approval_links_exact_step(field, value):
    f = case()
    setattr(f["approval"], field, value)
    reject(f)


@pytest.mark.parametrize("field,value", [("step_order", 99), ("step_order", True), ("tool_name", "statistics.project"), ("idempotency_key", "other")])
def test_step_belongs_to_frozen_plan(field, value):
    f = case()
    setattr(f["approval_step"], field, value)
    reject(f)


@pytest.mark.parametrize("owner", ["approval", "approval_step"])
def test_arguments_must_match_frozen_projected_material(owner):
    f = case()
    args = f[owner].request_json if owner == "approval" else f[owner].input_json["tool_arguments"]
    args["chapter_number"] = 99
    reject(f)


@pytest.mark.parametrize("key,value", [("goal", "other-goal"), ("actor_user_id", 77), ("system", {}), ("token", "PRIVATE_SENTINEL")])
def test_approval_extra_system_fields_not_blindly_ignored(key, value):
    f = case()
    f["approval"].request_json[key] = value
    reject(f)


def test_approval_missing_goal_rejected():
    f = case()
    del f["approval"].request_json["goal"]
    reject(f)


@pytest.mark.parametrize("actor", [12, 11])
def test_extra_actor_requires_trusted_exact_expected_actor(actor):
    f = case()
    f["approval"].request_json["actor_user_id"] = actor
    result = load_continuation_plan(**f, expected_actor_user_id=actor)
    assert "actor_user_id" not in result.to_payload()
    assert "actor_user_id" not in result.steps[0].arguments
    with pytest.raises(ContinuationPlanError): load_continuation_plan(**f, expected_actor_user_id=99)


@pytest.mark.parametrize("actor", [True, "11", 0, -1])
def test_trusted_actor_has_strict_positive_integer_type(actor):
    f = case()
    f["approval"].request_json["actor_user_id"] = actor
    with pytest.raises(ContinuationPlanError): load_continuation_plan(**f, expected_actor_user_id=actor)


def test_frozen_actor_is_not_discarded_or_replaced():
    f = case(actor=12)
    assert load_continuation_plan(**f).steps[0].arguments["actor_user_id"] == 12
    with pytest.raises(ContinuationPlanError): load_continuation_plan(**f, expected_actor_user_id=11)
    f["approval"].request_json["actor_user_id"] = 13
    reject(f)


def test_goal_projection_matches_actual_producer_merge_order():
    f = case()
    args = f["revision"].plan_json["tool_arguments"]["chapter.generate"]
    args["goal"] = "frozen per-tool goal"
    f["approval_step"].input_json["tool_arguments"] = deepcopy(args)
    f["approval"].request_json = {"goal": f["revision"].plan_json["goal"], **deepcopy(args)}
    rehash(f)
    assert load_continuation_plan(**f).steps[0].arguments["goal"] == "frozen per-tool goal"


@pytest.mark.parametrize("status", ["pending", "approved", "executing", "cancelled", "unknown", None])
def test_only_terminal_approval_outcomes(status):
    f = case()
    f["approval"].status = status
    reject(f, "approval.status")


@pytest.mark.parametrize("status", ["running", "awaiting_approval", "failed", "cancelled"])
def test_executed_requires_completed_step(status):
    f = case()
    f["approval_step"].status = status
    reject(f, "approval_step.status")


@pytest.mark.parametrize("status", ["running", "succeeded"])
def test_source_job_need_not_be_acknowledged(status):
    f = case()
    f["source_job"].status = status
    assert load_continuation_plan(**f).to_payload()["source_job_id"] == "source-job"


def test_continuation_source_uses_bound_payload_not_initial_planner_id():
    f = case()
    previous = load_continuation_plan(**f).to_payload()
    f["source_job"].kind = "agent_continuation"
    f["source_job"].id = "continuation-source"
    f["source_job"].payload_json = previous
    f["run"].context_json["execution_job_id"] = "source-job"
    result = load_continuation_plan(**f)
    assert result.to_payload()["source_job_id"] == "continuation-source"
    f["source_job"].payload_json["plan_revision_digest"] = "f"*64
    reject(f)


@pytest.mark.parametrize("kind", ["visible_response", "unknown", None])
def test_wrong_source_kind(kind):
    f = case()
    f["source_job"].kind = kind
    reject(f, "source_job.kind")


def test_initial_source_must_have_created_revision():
    f = case()
    f["revision"].planner_id = "agent_execution:other:initial"
    rehash(f)
    reject(f)


def test_replan_source_is_new_job_not_revision_creator():
    f = case(replan=True)
    assert load_continuation_plan(**f).steps[0].order == 7
    f["context_snapshot"].context_json["execution_job_id"] = "previous-job"
    reject(f)


@pytest.mark.parametrize("kind", ["unknown", "run_initial_context"])
def test_replan_kind_must_match_plan_phase(kind):
    f = case(replan=True)
    f["context_snapshot"].context_kind = kind
    reject(f)


def test_nullable_scope_fields_preserved():
    f = case()
    for row in f.values():
        for field in ("project_id", "transaction_id"):
            if hasattr(row, field): setattr(row, field, None)
    rehash(f)
    assert load_continuation_plan(**f).to_payload()["run_id"] == "run-1"


@pytest.mark.parametrize("owner", ["run", "revision", "context_snapshot", "capability_snapshot", "approval", "approval_step", "source_job"])
def test_missing_rows_are_controlled(owner):
    f = case()
    f[owner] = None
    reject(f)


def test_real_transient_orm_rows_use_loaded_scalars_without_io():
    from app.models.agent import AgentRun, AgentApproval, AgentRunStep, AgentJob
    from app.models.agent_plan import PlanRevision
    from app.models.agent_context import ContextSnapshot
    from app.models.agent_catalog import AgentRunCapabilitySnapshot
    f = case()
    models = dict(run=AgentRun, approval=AgentApproval, approval_step=AgentRunStep, source_job=AgentJob,
                  revision=PlanRevision, context_snapshot=ContextSnapshot, capability_snapshot=AgentRunCapabilitySnapshot)
    orm = {key: models[key](**vars(row)) for key, row in f.items()}
    assert load_continuation_plan(**orm) == load_continuation_plan(**f)


def test_unloaded_attributes_fail_without_triggering_properties():
    f = case()
    class Unloaded:
        @property
        def id(self): raise AssertionError("unexpected lazy IO")
    f["revision"] = Unloaded()
    reject(f)


@pytest.mark.parametrize("payload", [{}, {"phase": "planning"}])
def test_initial_orm_source_allows_omitted_payload_run_id(payload):
    from app.models.agent import AgentJob
    f = case()
    f["source_job"].payload_json = payload
    f["source_job"] = AgentJob(**vars(f["source_job"]))
    assert load_continuation_plan(**f).to_payload()["source_job_id"] == "source-job"


@pytest.mark.parametrize("value", [None, "other-run", True, 11, ""])
def test_initial_payload_run_id_present_is_still_strict(value):
    f = case()
    f["source_job"].payload_json["run_id"] = value
    reject(f, "source_job.payload_json.run_id")


@pytest.mark.parametrize("replan", [False, True])
def test_noninitial_source_requires_payload_run_id(replan):
    f = case(replan=replan)
    if not replan:
        payload = load_continuation_plan(**f).to_payload()
        f["source_job"].kind = "agent_continuation"
        f["source_job"].payload_json = payload
    del f["source_job"].payload_json["run_id"]
    reject(f, "source_job.payload_json.run_id")


@pytest.mark.asyncio
async def test_real_runtime_and_job_service_payload_none_is_valid_initial(task_session):
    from app.models import User, NovelProject
    from app.services.agent_runtime import AgentRuntimeService
    from app.services.agent_context_service import AgentContextService
    from app.services.agent_execution_service import AgentExecutionService
    from app.services.agent_plan_service import AgentPlanService
    from app.agent.jobs import AgentJobService

    user = User(id=918811, username="continuation-contract-user", email="continuation-contract@example.test", hashed_password="x", is_active=True)
    project = NovelProject(id="continuation-contract-project", user_id=user.id, title="Continuation fixture")
    task_session.add(user)
    await task_session.flush()
    task_session.add(project)
    await task_session.flush()
    runtime = AgentRuntimeService(task_session)
    chat = await runtime.create_session(user_id=user.id, project_id=project.id)
    plan = deepcopy(case()["revision"].plan_json)
    run = await runtime.create_run(session_id=chat.id, user_id=user.id, project_id=project.id,
                                   context={"goal": plan["goal"], "context_refs": [],
                                            "requested_tools": ["chapter.generate", "statistics.project"]})
    source = await AgentJobService(task_session).create_job(
        run_id=run.id, user_id=user.id, project_id=project.id, kind="agent_execution",
        idempotency_key=f"{run.id}:agent_execution", payload=None,
    )
    assert source.payload_json == {}
    context_snapshot = await AgentContextService(task_session).get_run_snapshot(
        run_id=run.id, snapshot_id=run.context_json["relational_context_snapshot_key"])
    capability_snapshot = await AgentExecutionService(task_session).get_run_snapshot(run.id)
    revision = await AgentPlanService(task_session).create_revision(
        run=run, session=chat, context_snapshot=context_snapshot, plan_json=plan,
        planner_id=f"agent_execution:{source.id}:initial",
    )
    run_context = deepcopy(run.context_json)
    run_context.update(relational_plan_revision_id=revision.id, relational_plan_revision_key=revision.revision_id,
                       execution_job_id=source.id)
    await runtime.set_run_context(run_id=run.id, user_id=user.id, context=run_context)
    step = await runtime.ensure_step(
        run_id=run.id, user_id=user.id, step_order=1, tool_name="chapter.generate",
        idempotency_key=f"{run.id}:step:1:chapter.generate",
        input_payload={"goal": plan["goal"], "context_refs": [], "tool_arguments": plan["tool_arguments"]["chapter.generate"]},
    )
    approval = await runtime.request_approval(
        run_id=run.id, user_id=user.id, project_id=project.id, step_id=step.id,
        tool_name=step.tool_name, arguments={"goal": plan["goal"], **plan["tool_arguments"]["chapter.generate"]},
    )
    # A genuine rejection needs no writer/provider, completed step or DB tampering.
    approval = await runtime.decide_approval(approval_id=approval.id, user_id=user.id, approved=False)
    for row in (run, source, revision, context_snapshot, capability_snapshot, step, approval):
        await task_session.refresh(row)
    frozen = load_continuation_plan(run=run, revision=revision, context_snapshot=context_snapshot,
                                    capability_snapshot=capability_snapshot, approval=approval,
                                    approval_step=step, source_job=source)
    assert frozen.to_payload()["outcome"] == "rejected"
    assert frozen.to_payload()["source_job_id"] == source.id
    assert [s.order for s in frozen.steps] == [1, 2]
