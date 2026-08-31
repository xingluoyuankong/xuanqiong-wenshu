import type { AgentEvent } from '@/api/agent'

export type SafeAgentEventData = Record<string, string | number | boolean>

export interface SafeAgentEvent {
  id: string
  run_id: string
  sequence: number
  event_type: string
  summary: string
  created_at?: string
  data: SafeAgentEventData
}

const KNOWN_EVENT_TYPES = new Set([
  'run_started',
  'planner_started',
  'context_resolved',
  'progress_update',
  'public_work_summary',
  'work_trace_delta',
  'plan_created',
  'plan_revised',
  'plan_step_pending',
  'plan_step_started',
  'plan_step_completed',
  'plan_step_failed',
  'approval_required',
  'approval_granted',
  'approval_rejected',
  'tool_call_started',
  'tool_call_progress',
  'tool_call_completed',
  'tool_call_failed',
  'tool_cancelled',
  'assistant_queued',
  'assistant_delta',
  'assistant_completed',
  'artifact_created',
  'artifact_accepted',
  'quality_check_completed',
  'quality_check_blocked',
  'quality_check_failed',
  'run_completed',
  'run_failed',
  'run_cancelled',
  'run_paused',
  'run_resumed',
  'run_recovery_ready',
  'step_reused',
  'step_lease_expired',
  'job_replayed',
  'write_execution_started',
  'write_candidate_progress',
  'write_execution_failed',
])

const TEXT_KEYS = new Set([
  'message',
  'progress_message',
  'phase',
  'tool_name',
  'approval_id',
  'artifact_id',
  'risk_level',
  'status',
  'error_type',
  'recovery',
  'context_kinds',
  'fallback_reason',
  'action_id',
  'current_action',
  'completed_action',
  'selected_capability',
  'decision_summary',
  'next_action',
  'expected_output',
])
const PROVIDER_EVENT_KEYS: Record<string, readonly string[]> = {
  plan_created: ['planner_provider_called', 'planner_provider_fallback_reason'],
  plan_revised: ['planner_provider_called', 'planner_provider_fallback_reason'],
  assistant_queued: ['planner_provider_called', 'planner_provider_fallback_reason'],
  assistant_started: ['response_provider_called', 'response_provider_fallback_reason'],
  assistant_delta: ['response_provider_called'],
  assistant_completed: ['response_provider_called', 'response_provider_fallback_reason'],
  run_failed: ['response_provider_called', 'response_provider_fallback_reason'],
  run_completed: ['response_provider_called', 'response_provider_fallback_reason'],
  write_execution_started: [
    'candidate_writer_provider_called',
    'candidate_writer_provider_fallback_reason',
    'candidate_writer_model_ref',
  ],
  write_candidate_progress: ['candidate_writer_provider_called'],
  write_execution_failed: ['candidate_writer_provider_called', 'candidate_writer_provider_fallback_reason'],
  artifact_created: [
    'candidate_writer_provider_called',
    'candidate_writer_provider_fallback_reason',
    'candidate_writer_model_ref',
  ],
}
const PROVIDER_BOOLEAN_KEYS = new Set([
  'planner_provider_called',
  'response_provider_called',
  'candidate_writer_provider_called',
])
const PROVIDER_TEXT_KEYS = new Set([
  'planner_provider_fallback_reason',
  'response_provider_fallback_reason',
  'candidate_writer_provider_fallback_reason',
  'candidate_writer_model_ref',
])
const INTEGER_KEYS = new Set([
  'step',
  'attempt_count',
  'blocker_count',
  'accepted_version_id',
  'version_id',
  'context_count',
  'step_count',
  'revision',
  'input_scope_count',
])
const PROGRESS_KEYS = new Set(['progress', 'percent'])
const UNKNOWN_EVENT_TYPE = 'unknown'
const UNKNOWN_EVENT_SUMMARY = '收到未识别运行事件'
const GENERIC_EVENT_SUMMARY = '收到运行事件'
const SENSITIVE_SUMMARY_PATTERN = /(?:reasoning|thought|chain[ _-]?of[ _-]?thought|prompt|system[ _-]?message|secret|api[ _-]?key|token|authorization|bearer|provider[ _-]?metadata|source[ _-]?text)/i


function recordOf(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {}
}

function text(value: unknown, maxLength = 1000): string | undefined {
  if (typeof value !== 'string') return undefined
  const normalized = value.replace(/[\u0000-\u001F]/g, ' ').trim()
  return normalized ? normalized.slice(0, maxLength) : undefined
}

function publicSummary(value: unknown, knownEvent: boolean): string {
  if (!knownEvent) return UNKNOWN_EVENT_SUMMARY
  const summary = text(value, 1000)
  return summary && !SENSITIVE_SUMMARY_PATTERN.test(summary)
    ? summary
    : GENERIC_EVENT_SUMMARY
}

function integer(value: unknown): number | undefined {
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isInteger(parsed) && parsed >= 0 && parsed <= 1_000_000 ? parsed : undefined
}

function progress(value: unknown): number | undefined {
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(parsed) ? Math.max(0, Math.min(100, parsed)) : undefined
}

/**
 * Browser-side defence in depth for the public SSE contract. Unknown event data
 * is discarded rather than rendered; this must not replace backend redaction.
 */
export function toSafeAgentEvent(raw: AgentEvent): SafeAgentEvent {
  const source = recordOf(raw.data || raw.data_json)
  const data: SafeAgentEventData = {}
  const rawEventType = text(raw.event_type, 120) || UNKNOWN_EVENT_TYPE
  const knownEvent = KNOWN_EVENT_TYPES.has(rawEventType)
  const eventType = knownEvent ? rawEventType : UNKNOWN_EVENT_TYPE
  if (knownEvent) {
    for (const key of TEXT_KEYS) {
      const value = text(
        source[key],
        key === 'message' || key === 'progress_message' ||
        key === 'current_action' || key === 'completed_action' ||
        key === 'decision_summary' || key === 'next_action' || key === 'expected_output'
          ? 500
          : 120,
      )
      if (value !== undefined) data[key] = value
    }
    for (const key of INTEGER_KEYS) {
      const value = integer(source[key])
      if (value !== undefined) data[key] = value
    }
    for (const key of PROGRESS_KEYS) {
      const value = progress(source[key])
      if (value !== undefined) data[key] = value
    }
    if (eventType === 'assistant_delta') {
      const value = text(source.content, 4000)
      if (value !== undefined) data.content = value
    }
    if (eventType === 'work_trace_delta') {
      for (const key of ['trace_id', 'capability_id', 'result_ref']) {
        const value = text(source[key], 160)
        if (value !== undefined) data[key] = value
      }
      const kind = text(source.kind, 40)
      if (kind !== undefined) data.kind = kind
      const message = text(source.message, 1000)
      if (message !== undefined && !SENSITIVE_SUMMARY_PATTERN.test(message)) data.message = message
      else delete data.message
    }
    if (typeof source.provider_called === 'boolean') data.provider_called = source.provider_called
    for (const key of PROVIDER_EVENT_KEYS[eventType] || []) {
      if (PROVIDER_BOOLEAN_KEYS.has(key) && typeof source[key] === 'boolean') {
        data[key] = source[key] as boolean
      }
      if (PROVIDER_TEXT_KEYS.has(key)) {
        const value = text(source[key], key === 'candidate_writer_model_ref' ? 200 : 160)
        if (value !== undefined) data[key] = value
      }
    }
  }
  return {
    id: text(raw.id, 120) || '',
    run_id: text(raw.run_id, 120) || '',
    sequence: integer(raw.sequence) || 0,
    event_type: eventType,
    summary: publicSummary(raw.summary, knownEvent),
    created_at: text(raw.created_at, 80),
    data,
  }
}

