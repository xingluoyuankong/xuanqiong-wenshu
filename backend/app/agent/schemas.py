"""Serializable contracts for the first Agent runtime slice."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import re
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AgentRiskLevel(str, Enum):
    READ = "read"
    SUGGEST = "suggest"
    WRITE = "write"
    DESTRUCTIVE = "destructive"


class AgentToolDefinition(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=500)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    risk_level: AgentRiskLevel
    requires_confirmation: bool
    project_scoped: bool = True
    supports_stream: bool = False
    idempotency_key: str | None = Field(default=None, max_length=120)

    model_config = ConfigDict(frozen=True)


class ToolContextBinding(BaseModel):
    """A manifest-declared projection from a resolved ContextRef into one tool argument."""

    source: Literal[
        "selected_chapter_number",
        "selected_version_id",
        "comparison_chapter_number",
        "from_version_id",
        "to_version_id",
        "artifact_id",
        "selected_entity_refs",
        "selected_quality_finding_refs",
    ]
    argument_name: str = Field(min_length=1, max_length=120)
    required: bool = False

    model_config = ConfigDict(frozen=True)


class AgentContextRef(BaseModel):
    """A small, user-selected project reference; it never carries prose or prompts."""

    kind: Literal["project", "chapter", "chapter_version", "artifact", "character", "faction", "foreshadowing", "knowledge_node", "research_artifact", "quality_finding"]
    project_id: str = Field(min_length=1, max_length=120)
    chapter_number: int | None = Field(default=None, ge=1, le=1_000_000)
    version_id: int | None = Field(default=None, ge=1)
    artifact_id: str | None = Field(default=None, min_length=1, max_length=36)
    entity_id: int | None = Field(default=None, ge=1)
    finding_id: str | None = Field(default=None, min_length=1, max_length=36)
    role: Literal["selected", "from", "to"] = "selected"

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_kind_fields(self) -> "AgentContextRef":
        entity_kinds = {"character", "faction", "foreshadowing", "knowledge_node", "research_artifact"}
        if self.kind == "project":
            if any(value is not None for value in (self.chapter_number, self.version_id, self.artifact_id, self.entity_id, self.finding_id)):
                raise ValueError("project context ref must not contain chapter, version, artifact, or entity fields")
        elif self.kind == "chapter":
            if self.chapter_number is None or any(value is not None for value in (self.version_id, self.artifact_id, self.entity_id, self.finding_id)):
                raise ValueError("chapter context ref requires chapter_number only")
        elif self.kind == "chapter_version":
            if self.chapter_number is None or self.version_id is None or any(value is not None for value in (self.artifact_id, self.entity_id, self.finding_id)):
                raise ValueError("chapter_version context ref requires chapter_number and version_id")
        elif self.kind == "artifact":
            if self.artifact_id is None or any(value is not None for value in (self.chapter_number, self.version_id, self.entity_id, self.finding_id)):
                raise ValueError("artifact context ref requires artifact_id only")
        elif self.kind in entity_kinds:
            if self.entity_id is None or self.finding_id is not None or any(value is not None for value in (self.chapter_number, self.version_id, self.artifact_id)) or self.role != "selected":
                raise ValueError("entity context ref requires entity_id with selected role only")
        elif self.kind == "quality_finding":
            if self.finding_id is None or self.entity_id is not None or any(value is not None for value in (self.chapter_number, self.version_id, self.artifact_id)) or self.role != "selected":
                raise ValueError("quality finding context ref requires finding_id with selected role only")
        return self


class ToolManifest(AgentToolDefinition):
    """Executable, versioned contract exposed by the project tool registry."""

    manifest_version: str = Field(default="1.0", min_length=1, max_length=32)
    timeout_seconds: int = Field(default=30, ge=1, le=900)
    cancellation_policy: Literal["cooperative", "not_supported"] = "cooperative"
    idempotency_policy: Literal["safe_read", "required", "not_applicable"] = "safe_read"
    audit_event_type: str = Field(default="tool_execution", min_length=1, max_length=120)
    context_bindings: tuple[ToolContextBinding, ...] = ()


class AgentToolCatalog(BaseModel):
    tools: list["AgentToolCatalogItem"]
    count: int
    generation: int = Field(ge=1)


class AgentToolCatalogItem(AgentToolDefinition):
    """User-visible, sanitized source metadata for one executable tool."""

    context_bindings: tuple[ToolContextBinding, ...] = ()
    provider_id: str | None = Field(default=None, max_length=120)
    provider_version: str | None = Field(default=None, max_length=64)
    source: Literal["builtin", "configured", "legacy"]


class AgentToolProviderHealthRead(BaseModel):
    provider_id: str
    path: str | None = None
    status: Literal["loaded", "disabled", "skipped", "failed"]
    source: Literal["builtin", "configured"]
    tools: list[str] = Field(default_factory=list)
    failure_code: str | None = None
    provider_version: str | None = None
    api_version: str | None = None
    capability_tags: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)


class AgentToolHealthRead(BaseModel):
    registry_status: Literal["healthy", "degraded"]
    provider_count: int = Field(ge=0)
    providers: list[AgentToolProviderHealthRead] = Field(default_factory=list)


class AgentEntitySummaryRead(BaseModel):
    """Minimal project entity row used only to select an Agent ContextRef."""

    kind: Literal["character", "faction", "foreshadowing", "knowledge_node", "research_artifact"]
    entity_id: int = Field(ge=1)
    label: str = Field(min_length=1, max_length=255)
    status: str | None = Field(default=None, max_length=128)
    detail: str | None = Field(default=None, max_length=255)


class AgentProjectEntitySummariesRead(BaseModel):
    project_id: str = Field(min_length=1, max_length=120)
    entities: list[AgentEntitySummaryRead] = Field(default_factory=list)

class AgentPlanRequest(BaseModel):
    """User intent for planning; no provider prompt or hidden reasoning is stored."""

    goal: str = Field(min_length=1, max_length=2000)
    project_id: str | None = Field(default=None, min_length=1, max_length=120)
    tools: list[str] = Field(default_factory=list, max_length=16)
    mode: Literal["explore", "strict"] = "explore"


class AgentPlanStep(BaseModel):
    step_id: UUID = Field(default_factory=uuid4)
    order: int = Field(ge=1)
    tool_name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=500)
    risk_level: AgentRiskLevel
    requires_confirmation: bool
    # Public planning metadata. It is a bounded execution contract, never a
    # hidden reasoning trace and never an unvalidated tool payload.
    intent: str | None = Field(default=None, max_length=500)
    expected_result: str | None = Field(default=None, max_length=500)
    depends_on: list[int] = Field(default_factory=list, max_length=8)
    planner_arguments: dict[str, Any] = Field(default_factory=dict)
    status: Literal["pending", "blocked"] = "pending"

    @model_validator(mode="after")
    def validate_dependencies(self) -> "AgentPlanStep":
        normalized = [int(value) for value in self.depends_on]
        if any(value < 1 or value >= self.order for value in normalized):
            raise ValueError("plan step dependencies must reference earlier steps")
        if len(set(normalized)) != len(normalized):
            raise ValueError("plan step dependencies must be unique")
        self.depends_on = normalized
        return self


class AgentEvent(BaseModel):
    """Visible execution summary, never a hidden chain-of-thought record."""

    event_id: UUID = Field(default_factory=uuid4)
    sequence: int = Field(ge=1)
    event_type: Literal["plan_created", "plan_step_pending", "approval_required"]
    phase: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=500)
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentPlan(BaseModel):
    # Legacy Runs may predate relational PlanRevision persistence.
    plan_id: UUID | None = None
    goal: str
    project_id: str | None = None
    mode: Literal["explore", "strict"]
    created_by_user_id: int
    steps: list[AgentPlanStep]
    events: list[AgentEvent]
    # This is an execution provenance flag, not an instruction to expose model
    # reasoning. The planner may be deterministic, Provider-backed, or fall
    # back to deterministic planning after a Provider failure.
    provider_called: bool = False
    planner_fallback_reason: str | None = Field(default=None, max_length=160)



class AgentSessionCreateRequest(BaseModel):
    project_id: str | None = Field(default=None, min_length=1, max_length=120)
    title: str | None = Field(default=None, max_length=255)


class AgentSessionRead(BaseModel):
    id: str
    user_id: int
    project_id: str | None = None
    title: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentMessageCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=200000)
    tools: list[str] = Field(default_factory=list, max_length=16)
    # Legacy single-tool payload. It is rejected for multi-tool plans so a
    # shared argument object can no longer be broadcast across incompatible schemas.
    arguments: dict[str, Any] = Field(default_factory=dict)
    context_refs: list[AgentContextRef] = Field(default_factory=list, max_length=16)
    tool_arguments: dict[str, dict[str, Any]] = Field(default_factory=dict)


class AgentMessageRead(BaseModel):
    id: str
    session_id: str
    user_id: int
    role: str
    content: str
    sequence: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentJobRead(BaseModel):
    id: str
    run_id: str
    correlation_id: str
    transaction_id: str | None = None
    user_id: int
    project_id: str | None = None
    kind: str
    status: str
    idempotency_key: str
    payload_json: dict[str, Any] = Field(default_factory=dict)
    result_json: dict[str, Any] = Field(default_factory=dict)
    error_type: str | None = None
    error_detail: str | None = None
    attempt_count: int
    max_attempts: int
    available_at: datetime
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    lease_generation: int = Field(default=0, ge=0)
    cancel_requested_at: datetime | None = None
    cancel_reason: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class AgentRunRead(BaseModel):
    id: str
    correlation_id: str
    transaction_id: str | None = None
    session_id: str
    user_id: int
    project_id: str | None = None
    status: str
    current_phase: str | None = None
    current_step: int
    progress: float
    state_version: int = Field(default=0, ge=0)
    lease_generation: int = Field(default=0, ge=0)
    pause_reason: str | None = None
    resume_target_status: str | None = None
    allowed_commands: list[Literal["pause", "resume", "cancel"]] = Field(default_factory=list)
    active_command: dict[str, Any] | None = None
    cancel_requested_at: datetime | None = None
    cancel_reason: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def derive_allowed_commands(self) -> "AgentRunRead":
        if self.allowed_commands:
            return self
        if self.status == "created":
            self.allowed_commands = ["cancel"]
        elif self.status in {"planning", "running", "awaiting_approval"}:
            self.allowed_commands = ["pause", "cancel"]
        elif self.status == "paused":
            self.allowed_commands = ["resume", "cancel"]
        else:
            self.allowed_commands = []
        return self


class AgentProviderProvenanceRead(BaseModel):
    """Stage-scoped Provider facts; no model reasoning, prompts, or credentials."""

    planner_provider_called: bool | None = None
    planner_provider_fallback_reason: str | None = Field(default=None, max_length=160)
    response_provider_called: bool | None = None
    response_provider_fallback_reason: str | None = Field(default=None, max_length=160)
    planner_provider_attempts: dict[str, Any] | None = None
    response_provider_attempts: dict[str, Any] | None = None
    candidate_writer_provider_called: bool | None = None
    candidate_writer_provider_fallback_reason: str | None = Field(default=None, max_length=160)
    candidate_writer_model_ref: str | None = Field(default=None, max_length=200)
    candidate_writer_provider_attempts: dict[str, Any] | None = None


class AgentRunCommandRequest(BaseModel):
    command_type: Literal["pause", "resume", "cancel"]
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=255)
    expected_state_version: int | None = Field(default=None, ge=0)
    reason: str | None = Field(default=None, max_length=255)
    payload_json: dict[str, Any] = Field(default_factory=dict)
    execution_mode: Literal["inline", "queued"] = "inline"

    model_config = ConfigDict(extra="forbid")


class AgentRunCommandRead(BaseModel):
    id: str
    run_id: str
    correlation_id: str
    transaction_id: str | None = None
    user_id: int
    command_type: Literal["pause", "resume", "cancel"]
    status: Literal["requested", "applying", "applied", "rejected", "failed"]
    reason: str | None = None
    idempotency_key: str | None = None
    payload_hash: str = ""
    expected_state_version: int | None = None
    payload_json: dict[str, Any] = Field(default_factory=dict)
    result_json: dict[str, Any] = Field(default_factory=dict)
    error_type: str | None = None
    error_detail: str | None = None
    attempt_count: int = 0
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    lease_generation: int = Field(default=0, ge=0)
    requested_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    applied_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class AgentRunStepRead(BaseModel):
    id: str
    run_id: str
    correlation_id: str
    transaction_id: str | None = None
    user_id: int
    step_order: int
    tool_name: str
    idempotency_key: str
    status: str
    attempt_count: int
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    lease_generation: int = Field(default=0, ge=0)
    output_json: dict[str, Any] = Field(default_factory=dict)
    error_type: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class AgentProviderUsageSummaryRead(BaseModel):
    run_id: str
    total_attempts: int = Field(ge=0)
    succeeded_attempts: int = Field(ge=0)
    failed_attempts: int = Field(ge=0)
    fallback_attempts: int = Field(ge=0)
    first_token_attempts: int = Field(ge=0)
    digest_attempts: int = Field(ge=0)
    selected_attempts: int = Field(ge=0)
    last_error_category: str | None = None
    latest_first_token_at: str | None = None

    model_config = ConfigDict(extra='forbid')


class AgentExecutionFactRead(BaseModel):
    execution_id: str
    run_id: str
    step_id: str | None = None
    action_id: str | None = None
    result_ref: str
    tool_name: str
    status: str
    attempt: int = Field(ge=1)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    error_type: str | None = None
    output_digest: str | None = None
    has_output: bool = False

    model_config = ConfigDict(extra='forbid')


class AgentPublicWorkScope(BaseModel):
    """A compact input reference that is safe to expose in work summaries."""

    kind: Literal["project", "chapter", "chapter_version", "artifact", "plan", "tool_result"]
    project_id: str | None = Field(default=None, min_length=1, max_length=120)
    chapter_number: int | None = Field(default=None, ge=1, le=1_000_000)
    version_id: int | None = Field(default=None, ge=1)
    artifact_id: str | None = Field(default=None, min_length=1, max_length=36)

    model_config = ConfigDict(extra="forbid", frozen=True)


_PUBLIC_WORK_SECRET_VALUE = re.compile(
    r"""(?ix)
    (?:
        \b(?:api[_-]?key|token|password|secret|authorization)\s*[:=]\s*[^\s,;]{4,}
        |\bbearer\s+[a-z0-9._~+/=-]{12,}
        |\b(?:sk|pk)-[a-z0-9_-]{12,}
    )
    """
)
_PUBLIC_WORK_PRIVATE_VALUE = re.compile(
    r"""(?isx)
    (?:
        \b(?:reasoning|chain[_ -]?of[_ -]?thought|private[_ -]?reasoning|system[_ -]?prompt
        |raw[_ -]?(?:response|provider|text)|source[_ -]?text|prompt[_ -]?context)\s*[:=]\s*[^\r\n]*
        |<\s*(?:analysis|thinking|reasoning|system|prompt)\b[^>]*>.*?</\s*(?:analysis|thinking|reasoning|system|prompt)\s*>
        |```.*?```
    )
    """
)
_PUBLIC_WORK_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]+")


def _sanitize_public_work_text(value: str) -> str:
    """Keep bounded operational prose while removing marker-shaped private payloads.

    This is a defence-in-depth boundary for the explicitly public Activity contract;
    trusted publishers still must supply operational status rather than raw Provider
    output. It intentionally does not impose a novel-content vocabulary or a fixed
    list of Agent actions.
    """
    normalized = _PUBLIC_WORK_CONTROL_CHARS.sub(" ", value).strip()
    normalized = _PUBLIC_WORK_SECRET_VALUE.sub("[已脱敏]", normalized)
    normalized = _PUBLIC_WORK_PRIVATE_VALUE.sub("[已脱敏]", normalized)
    return normalized.strip()


class AgentPublicWorkSummary(BaseModel):
    """Durable, user-visible description of the Agent's current work.

    It deliberately contains no provider response, raw prose, hidden reasoning,
    prompt, credential, or arbitrary JSON payload.
    """

    action_id: str = Field(min_length=1, max_length=120)
    phase: str = Field(min_length=1, max_length=80)
    current_action: str = Field(min_length=1, max_length=500)
    completed_action: str | None = Field(default=None, max_length=500)
    input_scope: list[AgentPublicWorkScope] = Field(default_factory=list, max_length=16)
    selected_capability: str | None = Field(default=None, max_length=120)
    decision_summary: str | None = Field(default=None, max_length=500)
    next_action: str | None = Field(default=None, max_length=500)
    expected_output: str | None = Field(default=None, max_length=500)
    step_order: int | None = Field(default=None, ge=0, le=1_000_000)
    revision: int = Field(default=0, ge=0, le=1_000_000)

    @field_validator(
        "current_action",
        "completed_action",
        "decision_summary",
        "next_action",
        "expected_output",
        mode="before",
    )
    @classmethod
    def sanitize_public_text_fields(cls, value: Any) -> Any:
        if value is None or not isinstance(value, str):
            return value
        return _sanitize_public_work_text(value)

    model_config = ConfigDict(extra="forbid", frozen=True)

    def event_data(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "phase": self.phase,
            "current_action": self.current_action,
            "completed_action": self.completed_action,
            "input_scope_kinds": [item.kind for item in self.input_scope],
            "input_scope_count": len(self.input_scope),
            "selected_capability": self.selected_capability,
            "decision_summary": self.decision_summary,
            "next_action": self.next_action,
            "expected_output": self.expected_output,
            "step": self.step_order,
            "revision": self.revision,
        }


class AgentEventRead(BaseModel):
    id: str
    run_id: str
    correlation_id: str
    transaction_id: str | None = None
    user_id: int
    event_type: str
    sequence: int
    summary: str
    data_json: dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentTimelineEventRead(BaseModel):
    id: str
    session_id: str
    run_id: str
    user_id: int
    project_id: str | None = None
    run_status: str
    event_type: str
    sequence: int
    summary: str
    tool_name: str | None = None
    data_json: dict[str, Any]
    created_at: datetime


class AgentAuditRecordRead(BaseModel):
    """统一的、用户可查询的 Agent 执行审计投影。"""

    event_id: str
    session_id: str
    run_id: str
    user_id: int
    project_id: str | None = None
    run_status: str
    event_type: str
    sequence: int
    summary: str
    tool_name: str | None = None
    approval_id: str | None = None
    artifact_id: str | None = None
    source_version_id: int | None = None
    accepted_version_id: int | None = None
    data_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class AgentSessionDetail(AgentSessionRead):
    messages: list[AgentMessageRead] = Field(default_factory=list)
    runs: list[AgentRunRead] = Field(default_factory=list)


class AgentApprovalDecisionRequest(BaseModel):
    approved: bool
    reason: str | None = Field(default=None, max_length=2000)


class AgentApprovalRead(BaseModel):
    id: str
    run_id: str
    correlation_id: str
    transaction_id: str | None = None
    step_id: str | None = None
    user_id: int
    project_id: str | None = None
    tool_name: str
    status: str
    expires_at: datetime | None = None
    decision_at: datetime | None = None
    reason: str | None = None
    request_json: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class AgentArtifactDiffLine(BaseModel):
    line_number: int
    original_line: str | None = None
    patched_line: str | None = None
    change_type: Literal['added', 'modified', 'deleted', 'unchanged']


class AgentArtifactDiffRead(BaseModel):
    artifact_id: str
    against_artifact_id: str
    diff_lines: list[AgentArtifactDiffLine]
    summary: dict[str, int]


class AgentArtifactVersionDiffRead(BaseModel):
    artifact_id: str
    project_id: str
    chapter_number: int
    version_id: int
    diff_lines: list[AgentArtifactDiffLine]
    summary: dict[str, int]
    deep_link: str


class AgentQualityBlockerRead(BaseModel):
    artifact_id: str
    project_id: str | None = None
    chapter_number: int | None = None
    version_id: int | None = None
    code: str
    severity: str
    message: str
    source: str
    snippet: str | None = None
    start_char: int | None = None
    end_char: int | None = None
    text_hash: str | None = None
    anchor_status: str
    deep_link: str | None = None


class AgentQualityFindingRead(BaseModel):
    id: str
    finding_id: str
    code: str
    category: str | None = None
    severity: str
    status: str
    message: str
    fingerprint: str
    location_json: dict[str, Any] = Field(default_factory=dict)
    evidence_json: dict[str, Any] = Field(default_factory=dict)
    remediation_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentQualityResultRead(BaseModel):
    id: str
    result_id: str
    run_id: str
    artifact_ref_id: str | None = None
    correlation_id: str
    transaction_id: str | None = None
    user_id: int
    project_id: str | None = None
    assessor_id: str
    rubric_version: str | None = None
    status: str
    score: float | None = None
    summary: str | None = None
    metrics_json: dict[str, Any] = Field(default_factory=dict)
    input_digest: str | None = None
    result_digest: str | None = None
    evaluated_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentQualityGateRead(BaseModel):
    id: str
    gate_id: str
    quality_result_id: str
    run_id: str
    artifact_ref_id: str | None = None
    correlation_id: str
    transaction_id: str | None = None
    gate_name: str
    gate_version: str | None = None
    decision: str
    blocker_count: int
    rationale: str | None = None
    policy_json: dict[str, Any] = Field(default_factory=dict)
    evaluated_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentArtifactQualityRead(BaseModel):
    artifact_id: str
    quality_result: AgentQualityResultRead | None = None
    findings: list[AgentQualityFindingRead] = Field(default_factory=list)
    gate: AgentQualityGateRead | None = None


class AgentArtifactLineageArtifactRead(BaseModel):
    id: str
    run_id: str
    project_id: str | None = None
    kind: str
    sha256: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentArtifactLineageEdgeRead(BaseModel):
    id: str
    lineage_id: str
    run_id: str
    correlation_id: str
    transaction_id: str | None = None
    relation_type: str
    operation: str | None = None
    input_digest: str | None = None
    output_digest: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    source_artifact: AgentArtifactLineageArtifactRead
    derived_artifact: AgentArtifactLineageArtifactRead


class AgentArtifactLineageRead(BaseModel):
    artifact_id: str
    upstream_edges: list[AgentArtifactLineageEdgeRead] = Field(default_factory=list)
    downstream_edges: list[AgentArtifactLineageEdgeRead] = Field(default_factory=list)


class AgentRewriteInstructionRead(BaseModel):
    artifact_id: str
    project_id: str | None = None
    chapter_number: int | None = None
    source_version_id: int | None = None
    code: str
    severity: str
    message: str
    source: str
    snippet: str | None = None
    start_char: int | None = None
    end_char: int | None = None
    anchor_status: str
    instruction: str
    rewrite_arguments: dict[str, Any] = Field(default_factory=dict)


class AgentArtifactRead(BaseModel):
    id: str
    run_id: str
    correlation_id: str
    transaction_id: str | None = None
    user_id: int
    project_id: str | None = None
    kind: str
    uri: str
    sha256: str | None = None
    metadata_json: dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentContextSnapshotRefRead(BaseModel):
    ref_order: int = Field(ge=0)
    ref_type: str
    ref_key: str
    ref_version: str | None = None
    role: str | None = None
    payload_json: dict[str, Any] = Field(default_factory=dict)
    digest: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentContextSnapshotRead(BaseModel):
    id: str
    snapshot_id: str
    run_id: str
    session_id: str
    user_id: int
    project_id: str | None = None
    correlation_id: str
    transaction_id: str | None = None
    schema_version: int = Field(ge=1)
    context_kind: str
    context_json: dict[str, Any] = Field(default_factory=dict)
    digest: str
    created_at: datetime
    refs: list[AgentContextSnapshotRefRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class AgentPlanRevisionRead(BaseModel):
    id: str
    revision_id: str
    run_id: str
    session_id: str
    context_snapshot_id: str
    parent_revision_id: str | None = None
    revision_number: int = Field(ge=1)
    user_id: int
    project_id: str | None = None
    correlation_id: str
    transaction_id: str | None = None
    planner_id: str | None = None
    status: str
    rationale: str | None = None
    plan_json: dict[str, Any] = Field(default_factory=dict)
    digest: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentConversationSummaryRead(BaseModel):
    id: str
    summary_id: str
    session_id: str
    run_id: str | None = None
    user_id: int
    project_id: str | None = None
    correlation_id: str | None = None
    transaction_id: str | None = None
    summary_kind: str
    summarizer_id: str | None = None
    start_message_sequence: int = Field(ge=1)
    end_message_sequence: int = Field(ge=1)
    message_count: int = Field(ge=1)
    source_digest: str
    summary_text: str
    summary_json: dict[str, Any] = Field(default_factory=dict)
    digest: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentArtifactAcceptRequest(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


