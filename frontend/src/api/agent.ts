import { API_BASE_URL, API_PREFIX } from '@/api/config'
import { buildAuthHeaders } from '@/stores/auth'

export type AgentRiskLevel = 'read' | 'suggest' | 'write' | 'destructive'
export type AgentContextRef =
  | { kind: 'project'; project_id: string }
  | { kind: 'chapter'; project_id: string; chapter_number: number }
  | {
      kind: 'chapter_version'
      project_id: string
      chapter_number: number
      version_id: number
      role?: 'selected' | 'from' | 'to'
    }
  | { kind: 'artifact'; project_id: string; artifact_id: string }
  | { kind: 'character' | 'faction' | 'foreshadowing' | 'knowledge_node' | 'research_artifact'; project_id: string; entity_id: number }
  | { kind: 'quality_finding'; project_id: string; finding_id: string }

export type AgentEntityContextKind = 'character' | 'faction' | 'foreshadowing' | 'knowledge_node' | 'research_artifact'

export interface AgentEntitySummary {
  kind: AgentEntityContextKind
  entity_id: number
  label: string
  status?: string | null
  detail?: string | null
}

export interface AgentProjectEntitySummaries {
  project_id: string
  entities: AgentEntitySummary[]
}
export interface AgentMessageCreateInput {
  content: string
  context_refs?: AgentContextRef[]
  tool_arguments?: Record<string, Record<string, unknown>>
}
export interface AgentProviderHealth {
  provider_id: string
  path?: string | null
  status: 'loaded' | 'disabled' | 'skipped' | 'failed'
  source: 'builtin' | 'configured'
  tools: string[]
  failure_code?: string | null
  provider_version?: string | null
  api_version?: string | null
  capability_tags?: string[]
  dependencies?: string[]
}
export interface AgentToolHealth {
  registry_status: 'healthy' | 'degraded'
  provider_count: number
  providers: AgentProviderHealth[]
}
export interface AgentToolDescriptor {
  name: string
  description: string
  risk_level: AgentRiskLevel
  requires_confirmation: boolean
  supports_stream: boolean
  manifest_version?: string
  timeout_seconds?: number
  cancellation_policy?: 'cooperative' | 'not_supported'
  idempotency_policy?: 'safe_read' | 'required' | 'not_applicable'
  audit_event_type?: string
  provider_id?: string | null
  provider_version?: string | null
  source?: 'builtin' | 'configured' | 'legacy'
}
export interface AgentPlanStep {
  step_id?: string
  order: number
  tool_name: string
  description: string
  risk_level: AgentRiskLevel
  requires_confirmation: boolean
  intent?: string | null
  expected_result?: string | null
  depends_on?: number[]
  planner_arguments?: Record<string, unknown>
  status?: string
}
export interface AgentSession {
  id: string
  user_id: number
  project_id?: string | null
  title?: string | null
  status: string
  created_at: string
  updated_at: string
}
export interface AgentMessage {
  id: string
  session_id: string
  user_id: number
  role: string
  content: string
  sequence: number
  created_at: string
}
export interface AgentProviderAttemptSnapshot {
  provider_attempts: Array<Record<string, unknown>>
  selected_provider_attempt?: number | null
  fallback_used?: boolean
}

const normalizeProviderAttemptSnapshot = (value: unknown): AgentProviderAttemptSnapshot | null => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const raw = value as Record<string, unknown>
  if (!Array.isArray(raw.provider_attempts)) return null
  const provider_attempts = raw.provider_attempts
    .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === 'object' && !Array.isArray(item)))
    .slice(0, 16)
    .map((item) => {
      const record: Record<string, unknown> = {}
      if (typeof item.attempt === 'number' && Number.isInteger(item.attempt) && item.attempt > 0) record.attempt = item.attempt
      if (typeof item.role === 'string') record.role = item.role.slice(0, 80)
      if (typeof item.status === 'string' && ['running', 'succeeded', 'failed'].includes(item.status)) record.status = item.status
      if (typeof item.error_category === 'string') record.error_category = item.error_category.slice(0, 40)
      if (typeof item.retry_index === 'number' && Number.isInteger(item.retry_index) && item.retry_index >= 0) record.retry_index = item.retry_index
      if (typeof item.fallback_from_attempt === 'number' && Number.isInteger(item.fallback_from_attempt) && item.fallback_from_attempt > 0) record.fallback_from_attempt = item.fallback_from_attempt
      if (typeof item.cancel_observed === 'boolean') record.cancel_observed = item.cancel_observed
      return record
    })
  const attempts = new Set(provider_attempts
    .map((item, index) => typeof item.attempt === 'number' ? item.attempt : index + 1))
  const selected = raw.selected_provider_attempt
  return {
    provider_attempts,
    selected_provider_attempt: typeof selected === 'number' && Number.isInteger(selected) && attempts.has(selected) ? selected : null,
    fallback_used: raw.fallback_used === true,
  }
}

const normalizeAgentProviderProvenance = (value: unknown): AgentProviderProvenance => {
  const raw = value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
  return {
    planner_provider_called: typeof raw.planner_provider_called === 'boolean' ? raw.planner_provider_called : null,
    planner_provider_fallback_reason: typeof raw.planner_provider_fallback_reason === 'string' ? raw.planner_provider_fallback_reason.slice(0, 160) || null : null,
    planner_provider_attempts: normalizeProviderAttemptSnapshot(raw.planner_provider_attempts),
    response_provider_called: typeof raw.response_provider_called === 'boolean' ? raw.response_provider_called : null,
    response_provider_fallback_reason: typeof raw.response_provider_fallback_reason === 'string' ? raw.response_provider_fallback_reason.slice(0, 160) || null : null,
    response_provider_attempts: normalizeProviderAttemptSnapshot(raw.response_provider_attempts),
    candidate_writer_provider_called: typeof raw.candidate_writer_provider_called === 'boolean' ? raw.candidate_writer_provider_called : null,
    candidate_writer_provider_fallback_reason: typeof raw.candidate_writer_provider_fallback_reason === 'string' ? raw.candidate_writer_provider_fallback_reason.slice(0, 160) || null : null,
    candidate_writer_model_ref: typeof raw.candidate_writer_model_ref === 'string' ? raw.candidate_writer_model_ref.slice(0, 200) || null : null,
    candidate_writer_provider_attempts: normalizeProviderAttemptSnapshot(raw.candidate_writer_provider_attempts),
  }
}

export interface AgentProviderProvenance {
  planner_provider_called: boolean | null
  planner_provider_fallback_reason: string | null
  planner_provider_attempts?: AgentProviderAttemptSnapshot | null
  response_provider_called: boolean | null
  response_provider_fallback_reason: string | null
  response_provider_attempts?: AgentProviderAttemptSnapshot | null
  candidate_writer_provider_called: boolean | null
  candidate_writer_provider_fallback_reason: string | null
  candidate_writer_model_ref: string | null
  candidate_writer_provider_attempts?: AgentProviderAttemptSnapshot | null
}

export interface AgentRun {
  id: string
  correlation_id?: string
  transaction_id?: string
  session_id: string
  user_id: number
  project_id?: string | null
  status: string
  current_phase?: string | null
  current_step: number
  progress: number
  state_version?: number
  pause_reason?: string | null
  resume_target_status?: string | null
  allowed_commands?: AgentRunCommandType[]
  created_at: string
  started_at?: string | null
  finished_at?: string | null
}
export type AgentRunCommandType = 'pause' | 'resume' | 'cancel'
export type AgentRunCommandStatus = 'requested' | 'applying' | 'applied' | 'rejected' | 'failed'

export interface AgentRunCommand {
  id: string
  run_id: string
  correlation_id: string
  transaction_id?: string
  user_id: number
  command_type: AgentRunCommandType
  status: AgentRunCommandStatus
  reason?: string | null
  idempotency_key?: string | null
  expected_state_version?: number | null
  payload_json: Record<string, unknown>
  error_type?: string | null
  error_detail?: string | null
  requested_at: string
  applied_at?: string | null
  lease_generation?: number
}

export interface AgentRunCommandRequest {
  command_type: AgentRunCommandType
  reason?: string
  idempotency_key: string
  expected_state_version: number
  payload_json?: Record<string, unknown>
  execution_mode?: 'inline' | 'queued'
}

export interface AgentRunCommandSummary {
  id: string
  run_id?: string | null
  command_type: AgentRunCommandType
  status: AgentRunCommandStatus
  reason?: string | null
  idempotency_key?: string | null
  expected_state_version?: number | null
  error_type?: string | null
  error_detail?: string | null
  requested_at: string
  applied_at?: string | null
  lease_generation?: number
}

export const buildAgentRunCommandIdempotencyKey = (
  runId: string,
  commandType: AgentRunCommandType,
  expectedStateVersion: number,
): string => {
  const normalizedRunId = String(runId || '').trim()
  const normalizedVersion = Number.isInteger(expectedStateVersion) && expectedStateVersion >= 0
    ? expectedStateVersion
    : 0
  return `agent-run-command:${normalizedRunId}:${commandType}:state-${normalizedVersion}`
}

export interface AgentRunStep {
  id: string
  run_id: string
  correlation_id?: string
  user_id: number
  step_order: number
  tool_name: string
  idempotency_key: string
  status: string
  attempt_count: number
  lease_owner?: string | null
  lease_expires_at?: string | null
  lease_generation?: number
  output_json: Record<string, unknown>
  error_type?: string | null
  started_at?: string | null
  finished_at?: string | null
}
export interface AgentEvent {
  id: string
  run_id: string
  correlation_id?: string
  sequence: number
  event_type: string
  summary: string
  data?: Record<string, unknown>
  data_json?: Record<string, unknown>
  created_at: string | null
  user_id?: number
}
export interface AgentTimelineEvent extends AgentEvent {
  session_id: string
  project_id?: string | null
  run_status: string
  tool_name?: string | null
}
export interface AgentJob {
  id: string
  run_id: string
  correlation_id?: string
  user_id: number
  project_id?: string | null
  kind: string
  status: string
  idempotency_key: string
  payload_json: Record<string, unknown>
  result_json: Record<string, unknown>
  error_type?: string | null
  error_detail?: string | null
  attempt_count: number
  max_attempts: number
  available_at: string
  lease_owner?: string | null
  lease_expires_at?: string | null
  lease_generation?: number
  cancel_requested_at?: string | null
  cancel_reason?: string | null
  created_at: string
  started_at?: string | null
  finished_at?: string | null
}
export interface AgentAuditRecord {
  event_id: string
  session_id: string
  run_id: string
  user_id: number
  project_id?: string | null
  run_status: string
  event_type: string
  sequence: number
  summary: string
  tool_name?: string | null
  approval_id?: string | null
  artifact_id?: string | null
  source_version_id?: number | null
  accepted_version_id?: number | null
  data_json: Record<string, unknown>
  created_at: string
}
export type AgentStreamEvent = AgentEvent
export interface AgentSessionDetail extends AgentSession {
  messages: AgentMessage[]
  runs: AgentRun[]
}
export interface AgentArtifact {
  id: string
  run_id: string
  correlation_id?: string
  user_id: number
  project_id?: string | null
  kind: string
  uri: string
  sha256?: string | null
  metadata_json: Record<string, unknown>
  created_at: string
}
export interface AgentContextSnapshotRef {
  ref_order: number
  ref_type: string
  ref_key: string
  ref_version?: string | null
  role?: string | null
  payload_json: Record<string, unknown>
  digest: string
  created_at: string
}

export interface AgentContextSnapshot {
  id: string
  snapshot_id: string
  run_id: string
  session_id: string
  user_id: number
  project_id?: string | null
  correlation_id: string
  transaction_id?: string | null
  schema_version: number
  context_kind: string
  context_json: Record<string, unknown>
  digest: string
  created_at: string
  refs: AgentContextSnapshotRef[]
}

export interface AgentPlanRevision {
  id: string
  revision_id: string
  run_id: string
  session_id: string
  context_snapshot_id: string
  parent_revision_id?: string | null
  revision_number: number
  user_id: number
  project_id?: string | null
  correlation_id: string
  transaction_id?: string | null
  planner_id?: string | null
  status: string
  rationale?: string | null
  plan_json: Record<string, unknown>
  digest: string
  created_at: string
}

export interface AgentConversationSummary {
  id: string
  summary_id: string
  session_id: string
  run_id?: string | null
  user_id: number
  project_id?: string | null
  correlation_id?: string | null
  transaction_id?: string | null
  summary_kind: string
  summarizer_id?: string | null
  start_message_sequence: number
  end_message_sequence: number
  message_count: number
  source_digest: string
  summary_text: string
  summary_json: Record<string, unknown>
  digest: string
  created_at: string
}

export interface AgentArtifactDiffLine {
  line_number: number
  original_line: string | null
  patched_line: string | null
  change_type: 'added' | 'modified' | 'deleted' | 'unchanged'
}
export interface AgentArtifactDiff {
  artifact_id: string
  against_artifact_id: string
  diff_lines: AgentArtifactDiffLine[]
  summary: Record<string, number>
}
export interface AgentArtifactVersionDiff extends AgentArtifactDiff {
  project_id: string
  chapter_number: number
  version_id: number
  deep_link: string
}
export interface AgentQualityFinding {
  id: string
  finding_id: string
  code: string
  category?: string | null
  severity: string
  status: string
  message: string
  fingerprint: string
  location_json: Record<string, unknown>
  evidence_json: Record<string, unknown>
  remediation_json: Record<string, unknown>
  created_at: string
}
export interface AgentQualityResult {
  id: string
  result_id: string
  run_id: string
  artifact_ref_id?: string | null
  correlation_id: string
  transaction_id?: string | null
  user_id: number
  project_id?: string | null
  assessor_id: string
  rubric_version?: string | null
  status: string
  score?: number | null
  summary?: string | null
  metrics_json: Record<string, unknown>
  input_digest?: string | null
  result_digest?: string | null
  evaluated_at: string
  created_at: string
}
export interface AgentQualityGate {
  id: string
  gate_id: string
  quality_result_id: string
  run_id: string
  artifact_ref_id?: string | null
  correlation_id: string
  transaction_id?: string | null
  gate_name: string
  gate_version?: string | null
  decision: 'passed' | 'blocked' | 'waived' | string
  blocker_count: number
  rationale?: string | null
  policy_json: Record<string, unknown>
  evaluated_at: string
  created_at: string
}
export interface AgentArtifactQuality {
  artifact_id: string
  quality_result: AgentQualityResult | null
  findings: AgentQualityFinding[]
  gate: AgentQualityGate | null
}
export interface AgentArtifactLineageArtifact {
  id: string
  run_id: string
  project_id?: string | null
  kind: string
  sha256?: string | null
  created_at: string
}
export interface AgentArtifactLineageEdge {
  id: string
  lineage_id: string
  run_id: string
  correlation_id: string
  transaction_id?: string | null
  relation_type: string
  operation?: string | null
  input_digest?: string | null
  output_digest?: string | null
  metadata_json: Record<string, unknown>
  created_at: string
  source_artifact: AgentArtifactLineageArtifact
  derived_artifact: AgentArtifactLineageArtifact
}
export interface AgentArtifactLineage {
  artifact_id: string
  upstream_edges: AgentArtifactLineageEdge[]
  downstream_edges: AgentArtifactLineageEdge[]
}

export interface AgentRewriteInstruction {
  artifact_id: string
  project_id?: string | null
  chapter_number?: number | null
  source_version_id?: number | null
  code: string
  severity: string
  message: string
  source: string
  snippet?: string | null
  start_char?: number | null
  end_char?: number | null
  anchor_status: string
  instruction: string
  rewrite_arguments: Record<string, unknown>
}
export interface AgentQualityBlocker {
  artifact_id: string
  project_id?: string | null
  chapter_number?: number | null
  version_id?: number | null
  code: string
  severity: string
  message: string
  source: string
  snippet?: string | null
  start_char?: number | null
  end_char?: number | null
  text_hash?: string | null
  anchor_status: string
  deep_link?: string | null
}
export interface AgentApproval {
  id: string
  run_id: string
  correlation_id?: string
  step_id?: string | null
  user_id: number
  project_id?: string | null
  tool_name: string
  status: string
  expires_at?: string | null
  decision_at?: string | null
  reason?: string | null
}
export interface AgentPublicWorkScope {
  kind: 'project' | 'chapter' | 'chapter_version' | 'artifact' | 'plan' | 'tool_result'
  project_id?: string | null
  chapter_number?: number | null
  version_id?: number | null
  artifact_id?: string | null
}

export interface AgentPublicWorkSummary {
  action_id: string
  phase: string
  current_action: string
  completed_action?: string | null
  input_scope: AgentPublicWorkScope[]
  selected_capability?: string | null
  decision_summary?: string | null
  next_action?: string | null
  expected_output?: string | null
  step_order?: number | null
  revision: number
}

export interface AgentStateProjection {
  capability_snapshot?: {
    generation: number
    providers: AgentProviderHealth[]
    tools: Array<{
      name: string
      risk_level: AgentRiskLevel
      manifest_version?: string
      supports_stream?: boolean
      provider_id?: string | null
      provider_version?: string | null
      source?: 'builtin' | 'configured' | 'legacy'
    }>
  }
  correlation_id: string
  run_id: string
  project_id?: string | null
  user_id: number
  status?: string | null
  phase?: string | null
  progress: number
  current_step: number
  state_version?: number
  pause_reason?: string | null
  resume_target_status?: string | null
  allowed_commands?: AgentRunCommandType[]
  active_command?: AgentRunCommandSummary | null
  terminal_status?: string | null
  recoverable: boolean
  cancellation_requested: boolean
  blocked_reason?: string | null
  last_event_sequence: number
  latest_public_summary?: AgentPublicWorkSummary | null
  latest_public_summary_sequence?: number
  latest_public_summary_at?: string | null
  steps: Array<{
    id: string
    order: number
    tool_name: string
    status: string
    attempt_count: number
  }>
  approvals: Array<{
    id: string
    step_id?: string | null
    tool_name: string
    status: string
    decision_at?: string | null
  }>
  artifacts: Array<{
    id: string
    kind: string
    created_at: string
    accepted_version_id?: number | null
    acceptance_approval_id?: string | null
  }>
  accepted_version_ids: number[]
  jobs: Array<{
    id: string
    kind: string
    status: string
    attempt_count: number
    max_attempts: number
    error_type?: string | null
  }>
  commands?: AgentRunCommandSummary[]
  task_runtime_refs: Array<{
    task_id: string
    task_type: string
    status: string
    stage?: string | null
    progress: number
  }>
}
export interface AgentProviderUsageSummary {
  run_id: string
  total_attempts: number
  succeeded_attempts: number
  failed_attempts: number
  fallback_attempts: number
  first_token_attempts: number
  digest_attempts: number
  selected_attempts: number
  last_error_category?: string | null
  latest_first_token_at?: string | null
}
export interface AgentExecutionFact {
  execution_id: string
  run_id: string
  step_id?: string | null
  action_id?: string | null
  result_ref: string
  tool_name: string
  status: string
  attempt: number
  started_at?: string | null
  finished_at?: string | null
  duration_ms?: number | null
  error_type?: string | null
  output_digest?: string | null
  has_output: boolean
}
export interface AgentToolResult {
  tool_name: string
  result: Record<string, unknown>
  /** Stable execution/step reference used to locate the result in a Run. */
  result_ref?: string | null
}
export interface AgentMessageResponse {
  message: AgentMessage
  assistant_message: AgentMessage | null
  run: AgentRun
  plan: AgentPlanResponse
  tool_results?: AgentToolResult[]
  provider_called?: boolean
  planner_fallback_reason?: string | null
  approvals?: AgentApproval[]
}
export interface AgentPlanResponse {
  plan_id?: string
  goal: string
  project_id?: string
  mode: 'explore' | 'strict'
  steps: AgentPlanStep[]
  events: Array<{
    event_type: string
    phase: string
    message: string
    data?: Record<string, unknown>
  }>
  provider_called: boolean
  planner_fallback_reason?: string | null
}

const request = async <T>(path: string, init: RequestInit = {}): Promise<T> => {
  const response = await fetch(`${API_BASE_URL}${API_PREFIX}${path}`, {
    ...init,
    credentials: 'include',
    headers: {
      ...Object.fromEntries(buildAuthHeaders().entries()),
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      ...(init.headers || {}),
    },
  })
  if (!response.ok) throw new Error(`Agent 请求失败: HTTP ${response.status}`)
  return response.json() as Promise<T>
}

const requestText = async (path: string): Promise<string> => {
  const response = await fetch(`${API_BASE_URL}${API_PREFIX}${path}`, {
    credentials: 'include',
    headers: Object.fromEntries(buildAuthHeaders().entries()),
  })
  if (!response.ok) throw new Error(`Agent 请求失败: HTTP ${response.status}`)
  return response.text()
}

export const AgentAPI = {
  listTools: () =>
    request<{ tools: AgentToolDescriptor[]; count: number; generation: number }>('/agent/tools'),
  listProjectEntitySummaries: (projectId: string, perKindLimit = 40) =>
    request<AgentProjectEntitySummaries>(
      `/agent/projects/${encodeURIComponent(projectId)}/entity-summaries?per_kind_limit=${Math.max(1, Math.min(100, perKindLimit))}`,
    ),
  listToolHealth: () => request<AgentToolHealth>('/agent/tools/health'),
  createPlan: (input: {
    goal: string
    project_id?: string
    tools?: string[]
    mode?: 'explore' | 'strict'
  }) => request<AgentPlanResponse>('/agent/plan', { method: 'POST', body: JSON.stringify(input) }),
  createSession: (input: { project_id?: string; title?: string } = {}) =>
    request<AgentSession>('/agent/sessions', { method: 'POST', body: JSON.stringify(input) }),
  listSessions: (projectId?: string) =>
    request<AgentSession[]>(
      `/agent/sessions${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ''}`,
    ),
  archiveSession: (sessionId: string) =>
    request<AgentSession>(`/agent/sessions/${encodeURIComponent(sessionId)}/archive`, {
      method: 'POST',
    }),
  getSession: (sessionId: string) =>
    request<AgentSessionDetail>(`/agent/sessions/${encodeURIComponent(sessionId)}`),
  sendMessage: (sessionId: string, input: string | AgentMessageCreateInput) => {
    const payload: AgentMessageCreateInput = typeof input === 'string' ? { content: input } : input
    return request<AgentMessageResponse>(
      `/agent/sessions/${encodeURIComponent(sessionId)}/messages`,
      { method: 'POST', body: JSON.stringify(payload) },
    )
  },
  listEvents: (sessionId: string, runId: string, afterSequence = 0) =>
    request<AgentEvent[]>(
      `/agent/sessions/${encodeURIComponent(sessionId)}/runs/${encodeURIComponent(runId)}/events?after_sequence=${Math.max(0, afterSequence)}`,
    ),
  listRunActivity: (runId: string, afterSequence = 0, limit = 200) =>
    request<AgentEvent[]>(
      `/agent/runs/${encodeURIComponent(runId)}/activity?after_sequence=${Math.max(0, afterSequence)}&limit=${Math.max(1, Math.min(500, limit))}`,
    ),
  listTimeline: (
    filters: {
      projectId?: string
      sessionId?: string
      runId?: string
      eventType?: string
      runStatus?: string
      toolName?: string
      offset?: number
      limit?: number
    } = {},
  ) => {
    const params = new URLSearchParams()
    if (filters.projectId) params.set('project_id', filters.projectId)
    if (filters.sessionId) params.set('session_id', filters.sessionId)
    if (filters.runId) params.set('run_id', filters.runId)
    if (filters.eventType) params.set('event_type', filters.eventType)
    if (filters.runStatus) params.set('run_status', filters.runStatus)
    if (filters.toolName) params.set('tool_name', filters.toolName)
    params.set('offset', String(Math.max(0, filters.offset || 0)))
    params.set('limit', String(Math.min(200, Math.max(1, filters.limit || 100))))
    return request<AgentTimelineEvent[]>(`/agent/timeline?${params.toString()}`)
  },
  listAudit: (
    filters: {
      projectId?: string
      sessionId?: string
      runId?: string
      eventType?: string
      runStatus?: string
      toolName?: string
      approvalId?: string
      artifactId?: string
      sourceVersionId?: number
      offset?: number
      limit?: number
    } = {},
  ) => {
    const params = new URLSearchParams()
    if (filters.projectId) params.set('project_id', filters.projectId)
    if (filters.sessionId) params.set('session_id', filters.sessionId)
    if (filters.runId) params.set('run_id', filters.runId)
    if (filters.eventType) params.set('event_type', filters.eventType)
    if (filters.runStatus) params.set('run_status', filters.runStatus)
    if (filters.toolName) params.set('tool_name', filters.toolName)
    if (filters.approvalId) params.set('approval_id', filters.approvalId)
    if (filters.artifactId) params.set('artifact_id', filters.artifactId)
    if (filters.sourceVersionId) params.set('source_version_id', String(filters.sourceVersionId))
    params.set('offset', String(Math.max(0, filters.offset || 0)))
    params.set('limit', String(Math.min(200, Math.max(1, filters.limit || 100))))
    return request<AgentAuditRecord[]>(`/agent/audit?${params.toString()}`)
  },
  listJobs: (projectId?: string, status?: string) => {
    const params = new URLSearchParams()
    if (projectId) params.set('project_id', projectId)
    if (status) params.set('status', status)
    return request<AgentJob[]>(`/agent/jobs${params.toString() ? `?${params.toString()}` : ''}`)
  },
  cancelJob: (jobId: string) =>
    request<AgentJob>(`/agent/jobs/${encodeURIComponent(jobId)}/cancel`, { method: 'POST' }),
  listDeadLetters: (limit = 100) =>
    request<AgentJob[]>(`/agent/dead-letters?limit=${Math.min(200, Math.max(1, limit))}`),
  replayDeadLetter: (jobId: string, reason?: string) =>
    request<AgentJob>(
      `/agent/dead-letters/${encodeURIComponent(jobId)}/replay${reason ? `?reason=${encodeURIComponent(reason)}` : ''}`,
      { method: 'POST' },
    ),
  sessionStreamUrl: (sessionId: string, runId: string, afterSequence = 0) =>
    `${API_BASE_URL}${API_PREFIX}/agent/sessions/${encodeURIComponent(sessionId)}/runs/${encodeURIComponent(runId)}/stream?after_sequence=${Math.max(0, afterSequence)}`,
  claimRun: (runId: string, workerId: string, leaseSeconds = 120) =>
    request<AgentRun>(
      `/agent/runs/${encodeURIComponent(runId)}/claim?worker_id=${encodeURIComponent(workerId)}&lease_seconds=${leaseSeconds}`,
      { method: 'POST' },
    ),
  releaseRun: (runId: string, workerId: string) =>
    request<AgentRun>(
      `/agent/runs/${encodeURIComponent(runId)}/release?worker_id=${encodeURIComponent(workerId)}`,
      { method: 'POST' },
    ),
  recoverRun: (runId: string) =>
    request<AgentRun>(`/agent/runs/${encodeURIComponent(runId)}/recover`, { method: 'POST' }),
  listRunCommands: (runId: string, limit = 100) =>
    request<AgentRunCommand[]>(
      `/agent/runs/${encodeURIComponent(runId)}/commands?limit=${Math.max(1, Math.min(200, limit))}`,
    ),
  submitRunCommand: (runId: string, input: AgentRunCommandRequest) => {
    const payload: AgentRunCommandRequest = {
      ...input,
      idempotency_key: input.idempotency_key.trim(),
      expected_state_version: Number.isInteger(input.expected_state_version) && input.expected_state_version >= 0
        ? input.expected_state_version
        : 0,
    }
    return request<AgentRunCommand>(`/agent/runs/${encodeURIComponent(runId)}/commands`, {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },
  getRunPlan: (runId: string) =>
    request<AgentPlanResponse>(`/agent/runs/${encodeURIComponent(runId)}/plan`),
  getRunState: (runId: string) =>
    request<AgentStateProjection>(`/agent/runs/${encodeURIComponent(runId)}/state`),
  getRunProviderProvenance: async (runId: string) =>
    normalizeAgentProviderProvenance(await request<unknown>(`/agent/runs/${encodeURIComponent(runId)}/provider-provenance`)),
  getRunContextSnapshot: (runId: string) =>
    request<AgentContextSnapshot | null>(`/agent/runs/${encodeURIComponent(runId)}/context-snapshot`),
  getRunPlanRevision: (runId: string) =>
    request<AgentPlanRevision | null>(`/agent/runs/${encodeURIComponent(runId)}/plan-revision`),
  listRunConversationSummaries: (runId: string, limit = 100) =>
    request<AgentConversationSummary[]>(
      `/agent/runs/${encodeURIComponent(runId)}/conversation-summaries?limit=${Math.max(1, Math.min(500, limit))}`,
    ),
  listApprovals: (runId: string) =>
    request<AgentApproval[]>(`/agent/runs/${encodeURIComponent(runId)}/approvals`),
  listRunSteps: (runId: string) =>
    request<AgentRunStep[]>(`/agent/runs/${encodeURIComponent(runId)}/steps`),
  listExecutionFacts: (runId: string, limit = 200) =>
    request<AgentExecutionFact[]>(`/agent/runs/${encodeURIComponent(runId)}/execution-facts?limit=${Math.max(1, Math.min(500, limit))}`),
  getProviderUsageSummary: (runId: string) =>
    request<AgentProviderUsageSummary>(`/agent/runs/${encodeURIComponent(runId)}/provider-usage-summary`),
  listArtifacts: (runId: string) =>
    request<AgentArtifact[]>(`/agent/runs/${encodeURIComponent(runId)}/artifacts`),
  executeApproval: (approvalId: string) =>
    request<AgentArtifact>(`/agent/approvals/${encodeURIComponent(approvalId)}/execute`, {
      method: 'POST',
    }),
  getArtifactContent: (artifactId: string) =>
    requestText(`/agent/artifacts/${encodeURIComponent(artifactId)}/content`),
  getArtifactDiff: (artifactId: string, againstArtifactId: string) =>
    request<AgentArtifactDiff>(
      `/agent/artifacts/${encodeURIComponent(artifactId)}/diff?against_artifact_id=${encodeURIComponent(againstArtifactId)}`,
    ),
  getArtifactVersionDiff: (
    artifactId: string,
    input: { projectId: string; chapterNumber: number; versionId: number },
  ) =>
    request<AgentArtifactVersionDiff>(
      `/agent/artifacts/${encodeURIComponent(artifactId)}/chapter-version-diff?project_id=${encodeURIComponent(input.projectId)}&chapter_number=${input.chapterNumber}&version_id=${input.versionId}`,
    ),
  getArtifactQuality: (artifactId: string) =>
    request<AgentArtifactQuality>(
      `/agent/artifacts/${encodeURIComponent(artifactId)}/quality`,
    ),
  getArtifactLineage: (artifactId: string) =>
    request<AgentArtifactLineage>(
      `/agent/artifacts/${encodeURIComponent(artifactId)}/lineage`,
    ),
  listArtifactQualityBlockers: (artifactId: string) =>
    request<AgentQualityBlocker[]>(
      `/agent/artifacts/${encodeURIComponent(artifactId)}/quality-blockers`,
    ),
  listArtifactRewriteInstructions: (artifactId: string) =>
    request<AgentRewriteInstruction[]>(
      `/agent/artifacts/${encodeURIComponent(artifactId)}/rewrite-instructions`,
    ),
  acceptArtifact: (artifactId: string, note?: string) =>
    request<AgentArtifact>(`/agent/artifacts/${encodeURIComponent(artifactId)}/accept`, {
      method: 'POST',
      body: JSON.stringify({ note }),
    }),
  decideApproval: (approvalId: string, approved: boolean, reason?: string) =>
    request<AgentApproval>(`/agent/approvals/${encodeURIComponent(approvalId)}/decision`, {
      method: 'POST',
      body: JSON.stringify({ approved, reason }),
    }),
}

