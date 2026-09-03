import type { SafeAgentEvent } from '@/utils/agentEventSafety'

export interface AgentDisplayEvent {
  id: string
  label: string
  detail: string
  sequence: number
  eventType: string
  phase?: string
  actionId?: string
  resultRef?: string
  progress?: number
}

interface AssistantDelta {
  sequence: number
  content: string
}

export interface AgentReasoningChunk {
  sequence: number
  chunkIndex: number
  content: string
  createdAt?: string
  id?: string
  runId?: string
}

export type AgentReasoningStatus = 'idle' | 'streaming' | 'completed' | 'failed'

export interface AgentWorkTraceDelta {
  sequence: number
  traceId: string
  phase: string
  actionId?: string
  kind: string
  message: string
  progress?: number
  capabilityId?: string
  resultRef?: string
}

export interface AgentRunEventProjection {
  events: AgentDisplayEvent[]
  seenEventKeys: string[]
  assistantDeltas: AssistantDelta[]
  assistantText: string
  workTraceDeltas: AgentWorkTraceDelta[]
  latestWorkTrace: AgentWorkTraceDelta | null
  reasoningChunks: AgentReasoningChunk[]
  reasoningText: string
  reasoningStatus: AgentReasoningStatus
  latestProgressMessage: string
  latestProgressActionId?: string
  latestProgressPhase?: string
  latestProgress?: number
  lastSequence: number
  lastContiguousSequence: number
  pendingSequences: number[]
  hasSequenceGap: boolean
  replayRequired: boolean
}

export interface AgentRunPatch {
  progress?: number
  current_phase?: string
  current_step?: number
  status?: 'completed' | 'failed' | 'cancelled'
}

export interface AgentEventReduction {
  projection: AgentRunEventProjection
  accepted: boolean
  isLatest: boolean
  runPatch: AgentRunPatch
}

export const MAX_AGENT_ACTIVITY_ITEMS = 240
export const MAX_AGENT_EVENT_KEYS = 4_096
export const MAX_AGENT_PENDING_SEQUENCES = 4_096
export const MAX_AGENT_ASSISTANT_DELTA_SEGMENTS = 1_024
export const MAX_AGENT_ASSISTANT_CHARACTERS = 48_000
export const MAX_AGENT_WORK_TRACE_DELTAS = 512
export const MAX_AGENT_REASONING_CHUNKS = 4096
export const MAX_AGENT_REASONING_CHARACTERS = 200_000

export const agentEventLabel = (type: string) =>
  ({
    run_started: '运行已启动',
    planner_started: '正在规划',
    context_resolved: '上下文已关联',
    public_work_summary: '当前工作摘要',
    plan_created: '计划已生成',
    plan_revised: '计划已调整',
    plan_step_pending: '计划步骤等待中',
    plan_step_started: '计划步骤开始',
    plan_step_completed: '计划步骤完成',
    plan_step_failed: '计划步骤失败',
    step_reused: '已复用已完成步骤',
    step_lease_expired: '执行租约已过期',
    run_recovery_ready: '运行已进入可恢复状态',
    tool_call_started: '工具调用开始',
    tool_call_progress: '工具调用进度',
    tool_call_result: '工具调用结果',
    tool_call_failed: '工具调用失败',
    tool_call_completed: '工具调用已完成',
    tool_cancelled: '工具调用已取消',
    approval_required: '等待审批',
    approval_granted: '审批已批准',
    approval_rejected: '审批已拒绝',
    progress_update: '运行进度',
    artifact_created: '结果已生成',
    artifact_accepted: '结果已接受',
    assistant_queued: '回复已排队',
    assistant_started: 'Agent 开始回复',
    assistant_delta: 'Agent 正在输出',
    assistant_reasoning_started: 'Provider reasoning 开始',
    assistant_reasoning_chunk: 'Provider reasoning 分片',
    assistant_reasoning_completed: 'Provider reasoning 完成',
    assistant_reasoning_failed: 'Provider reasoning 失败',
    work_trace_delta: '公开工作轨迹',
    assistant_completed: 'Agent 回复完成',
    warning: '运行警告',
    error: '运行错误',
    run_paused: '运行已暂停',
    run_cancelled: '运行已取消',
    run_resumed: '运行已恢复',
    run_completed: '运行已完成',
    run_failed: '运行失败',
  })[type] || type

export function createAgentRunEventProjection(): AgentRunEventProjection {
  return {
    events: [],
    seenEventKeys: [],
    assistantDeltas: [],
    assistantText: '',
    workTraceDeltas: [],
    latestWorkTrace: null,
    reasoningChunks: [],
    reasoningText: '',
    reasoningStatus: 'idle',
    latestProgressMessage: '',
    latestProgressActionId: undefined,
    latestProgressPhase: undefined,
    latestProgress: undefined,
    lastSequence: 0,
    lastContiguousSequence: 0,
    pendingSequences: [],
    hasSequenceGap: false,
    replayRequired: false,
  }
}

export const agentEventKey = (event: Pick<SafeAgentEvent, 'run_id' | 'sequence'>) =>
  `${event.run_id}:${event.sequence}`

const boundedProgress = (value: unknown): number | undefined => {
  const numeric = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(numeric) ? Math.max(0, Math.min(100, numeric)) : undefined
}

const positiveInteger = (value: unknown): number | undefined => {
  const numeric = typeof value === 'number' ? value : Number(value)
  return Number.isInteger(numeric) && numeric >= 0 ? numeric : undefined
}

const detailFor = (event: SafeAgentEvent): string => {
  const data = event.data
  return event.summary || String(data.message || data.progress_message || '收到运行事件')
}

const advanceContiguousSequence = (
  lastContiguousSequence: number,
  pendingSequences: number[],
  sequence: number,
): { lastContiguousSequence: number; pendingSequences: number[] } => {
  const pending = new Set(pendingSequences.filter((value) => value > lastContiguousSequence))
  if (sequence > lastContiguousSequence) pending.add(sequence)
  let cursor = lastContiguousSequence
  while (pending.has(cursor + 1)) {
    pending.delete(cursor + 1)
    cursor += 1
  }
  return {
    lastContiguousSequence: cursor,
    pendingSequences: [...pending]
      .filter((value) => value > cursor)
      .sort((left, right) => left - right)
      .slice(0, MAX_AGENT_PENDING_SEQUENCES),
  }
}

const mergeAssistantText = (deltas: AssistantDelta[]): string => {
  const merged = deltas
    .slice()
    .sort((left, right) => left.sequence - right.sequence)
    .map((item) => item.content)
    .join('')
  return merged.length > MAX_AGENT_ASSISTANT_CHARACTERS
    ? merged.slice(-MAX_AGENT_ASSISTANT_CHARACTERS)
    : merged
}

/**
 * Applies a browser-safe durable Agent event without relying on arrival order.
 * The reducer intentionally uses `(run_id, sequence)` rather than event type for
 * deduplication because sequence is the durable event identity inside one Run.
 */
export function reduceAgentRunEvent(
  current: AgentRunEventProjection,
  event: SafeAgentEvent,
): AgentEventReduction {
  if (!event.run_id || event.sequence < 0) {
    return { projection: current, accepted: false, isLatest: false, runPatch: {} }
  }

  const key = agentEventKey(event)
  if (current.seenEventKeys.includes(key)) {
    return { projection: current, accepted: false, isLatest: false, runPatch: {} }
  }

  const isLatest = event.sequence >= current.lastSequence
  const sequenceState = advanceContiguousSequence(
    current.lastContiguousSequence,
    current.pendingSequences,
    event.sequence,
  )
  const display: AgentDisplayEvent = {
    id: event.id || key,
    label: agentEventLabel(event.event_type),
    detail: detailFor(event),
    sequence: event.sequence,
    eventType: event.event_type,
    ...(typeof event.data.phase === 'string' ? { phase: event.data.phase } : {}),
    ...(typeof event.data.action_id === 'string' ? { actionId: event.data.action_id } : {}),
    ...(typeof event.data.result_ref === 'string' ? { resultRef: event.data.result_ref } : {}),
    ...(boundedProgress(event.data.progress) !== undefined ? { progress: boundedProgress(event.data.progress) } : {}),
  }
  const events = [...current.events, display]
    .sort((left, right) => left.sequence - right.sequence)
    .slice(-MAX_AGENT_ACTIVITY_ITEMS)
  const seenEventKeys = [...current.seenEventKeys, key].slice(-MAX_AGENT_EVENT_KEYS)
  const content = event.event_type === 'assistant_delta' && typeof event.data.content === 'string'
    ? event.data.content
    : undefined
  const assistantDeltas = content === undefined
    ? current.assistantDeltas
    : [...current.assistantDeltas, { sequence: event.sequence, content }]
        .sort((left, right) => left.sequence - right.sequence)
        .slice(-MAX_AGENT_ASSISTANT_DELTA_SEGMENTS)
  const reasoningContent = event.event_type === 'assistant_reasoning_chunk' && typeof event.data.content === 'string'
    ? event.data.content
    : undefined
  const reasoningChunk = reasoningContent === undefined
    ? undefined
    : {
        sequence: event.sequence,
        chunkIndex: positiveInteger(event.data.chunk_index) ?? current.reasoningChunks.length,
        content: reasoningContent,
        createdAt: event.created_at,
      } satisfies AgentReasoningChunk
  const reasoningChunks = reasoningChunk
    ? [...current.reasoningChunks, reasoningChunk]
        .sort((left, right) => left.chunkIndex - right.chunkIndex || left.sequence - right.sequence)
        .slice(-MAX_AGENT_REASONING_CHUNKS)
    : current.reasoningChunks
  const reasoningText = reasoningChunks
    .map((item) => item.content)
    .join('')
    .slice(-MAX_AGENT_REASONING_CHARACTERS)
  const reasoningStatus: AgentReasoningStatus =
    event.event_type === 'assistant_reasoning_started' ? 'streaming'
      : event.event_type === 'assistant_reasoning_chunk' ? 'streaming'
      : event.event_type === 'assistant_reasoning_completed' ? 'completed'
      : event.event_type === 'assistant_reasoning_failed' || event.event_type === 'run_failed' ? 'failed'
      : event.event_type === 'run_completed' || event.event_type === 'run_cancelled' ? 'completed'
      : current.reasoningStatus
  const traceMessage = event.event_type === 'work_trace_delta' && typeof event.data.message === 'string'
    ? event.data.message
    : undefined
  const workTraceDelta = traceMessage
    ? {
        sequence: event.sequence,
        traceId: typeof event.data.trace_id === 'string' ? event.data.trace_id : event.id || key,
        phase: typeof event.data.phase === 'string' ? event.data.phase : 'unknown',
        actionId: typeof event.data.action_id === 'string' ? event.data.action_id : undefined,
        kind: typeof event.data.kind === 'string' ? event.data.kind : 'status',
        message: traceMessage,
        progress: boundedProgress(event.data.progress),
        capabilityId: typeof event.data.capability_id === 'string' ? event.data.capability_id : undefined,
        resultRef: typeof event.data.result_ref === 'string' ? event.data.result_ref : undefined,
      } satisfies AgentWorkTraceDelta
    : undefined
  const workTraceDeltas = workTraceDelta
    ? [...current.workTraceDeltas, workTraceDelta]
        .sort((left, right) => left.sequence - right.sequence)
        .slice(-MAX_AGENT_WORK_TRACE_DELTAS)
    : current.workTraceDeltas
  const data = event.data
  const runPatch: AgentRunPatch = {}
  if (isLatest) {
    const progress = boundedProgress(data.progress ?? data.percent)
    if (progress !== undefined) runPatch.progress = progress
    if (typeof data.phase === 'string') runPatch.current_phase = data.phase
    const step = positiveInteger(data.step)
    if (step !== undefined) runPatch.current_step = step
    if (event.event_type === 'run_completed') {
      runPatch.status = 'completed'
      runPatch.progress = 100
    } else if (event.event_type === 'run_failed') {
      runPatch.status = 'failed'
    } else if (event.event_type === 'run_cancelled') {
      runPatch.status = 'cancelled'
    }
  }

  return {
    accepted: true,
    isLatest,
    runPatch,
    projection: {
      events,
      seenEventKeys,
      assistantDeltas,
      assistantText: mergeAssistantText(assistantDeltas),
      workTraceDeltas,
      latestWorkTrace: workTraceDeltas.at(-1) || null,
      reasoningChunks,
      reasoningText,
      reasoningStatus,
      latestProgressMessage:
        isLatest && event.event_type === 'progress_update'
          ? typeof data.progress_message === 'string' ? data.progress_message : ''
          : current.latestProgressMessage,
      latestProgressActionId:
        isLatest && event.event_type === 'progress_update' && typeof data.action_id === 'string'
          ? data.action_id
          : isLatest && event.event_type === 'progress_update' ? undefined : current.latestProgressActionId,
      latestProgressPhase:
        isLatest && event.event_type === 'progress_update' && typeof data.phase === 'string'
          ? data.phase
          : isLatest && event.event_type === 'progress_update' ? undefined : current.latestProgressPhase,
      latestProgress:
        isLatest && event.event_type === 'progress_update'
          ? boundedProgress(data.progress ?? data.percent)
          : current.latestProgress,
      lastSequence: Math.max(current.lastSequence, event.sequence),
      lastContiguousSequence: sequenceState.lastContiguousSequence,
      pendingSequences: sequenceState.pendingSequences,
      hasSequenceGap: sequenceState.pendingSequences.length > 0,
      replayRequired: sequenceState.pendingSequences.length > 0,
    },
  }
}