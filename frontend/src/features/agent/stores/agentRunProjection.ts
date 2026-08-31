import { computed, ref } from 'vue'
import type {
  AgentApproval,
  AgentArtifact,
  AgentContextSnapshot,
  AgentConversationSummary,
  AgentEvent,
  AgentPlanResponse,
  AgentPlanRevision,
  AgentRun,
  AgentRunStep,
  AgentStateProjection,
  AgentToolResult,
} from '@/api/agent'
import type { SafeAgentEvent } from '@/utils/agentEventSafety'
import {
  MAX_AGENT_ACTIVITY_ITEMS,
  createAgentRunEventProjection,
  reduceAgentRunEvent,
  type AgentDisplayEvent,
  type AgentEventReduction,
  type AgentRunEventProjection,
  type AgentWorkTraceDelta,
} from '@/features/agent/reducers/agentEventReducer'
import type { SSEConnectionState } from '@/utils/sseStream'

const sortRuns = (items: AgentRun[]) =>
  [...items].sort((left, right) => left.created_at.localeCompare(right.created_at))

const recordOf = <T>(value: Record<string, T>, key: string, fallback: T): T => value[key] ?? fallback

/**
 * Run-scoped projection state for the Chat-first Agent workspace.
 *
 * Network results, SSE data and durable snapshots may arrive in different orders;
 * every value below is keyed by run_id so switching a route/deep-link cannot let a
 * late response from a previous Run overwrite the selected Run's view.
 */
export function useAgentRunProjection() {
  const runs = ref<AgentRun[]>([])
  const selectedRunId = ref('')
  const statesByRunId = ref<Record<string, AgentStateProjection>>({})
  const stepsByRunId = ref<Record<string, AgentRunStep[]>>({})
  const plansByRunId = ref<Record<string, AgentPlanResponse>>({})
  const contextSnapshotsByRunId = ref<Record<string, AgentContextSnapshot | null>>({})
  const planRevisionsByRunId = ref<Record<string, AgentPlanRevision | null>>({})
  const conversationSummariesByRunId = ref<Record<string, AgentConversationSummary[]>>({})
  const approvalsByRunId = ref<Record<string, AgentApproval[]>>({})
  const artifactsByRunId = ref<Record<string, AgentArtifact[]>>({})
  const toolResultsByRunId = ref<Record<string, AgentToolResult[]>>({})
  const eventsByRunId = ref<Record<string, AgentRunEventProjection>>({})
  const connectionByRunId = ref<Record<string, SSEConnectionState>>({})

  const runsById = computed<Record<string, AgentRun>>(() =>
    Object.fromEntries(runs.value.map((run) => [run.id, run])),
  )
  const activeRun = computed<AgentRun | null>(() =>
    selectedRunId.value ? runsById.value[selectedRunId.value] || null : null,
  )
  const activeRunState = computed<AgentStateProjection | null>(() =>
    activeRun.value ? statesByRunId.value[activeRun.value.id] || null : null,
  )
  const activeRunSteps = computed<AgentRunStep[]>(() =>
    activeRun.value ? recordOf(stepsByRunId.value, activeRun.value.id, []) : [],
  )
  const activePlan = computed<AgentPlanResponse | null>(() =>
    activeRun.value ? plansByRunId.value[activeRun.value.id] || null : null,
  )
  const activeContextSnapshot = computed<AgentContextSnapshot | null>(() =>
    activeRun.value ? recordOf(contextSnapshotsByRunId.value, activeRun.value.id, null) : null,
  )
  const activePlanRevision = computed<AgentPlanRevision | null>(() =>
    activeRun.value ? recordOf(planRevisionsByRunId.value, activeRun.value.id, null) : null,
  )
  const activeConversationSummaries = computed<AgentConversationSummary[]>(() =>
    activeRun.value ? recordOf(conversationSummariesByRunId.value, activeRun.value.id, []) : [],
  )
  const activeApprovals = computed<AgentApproval[]>(() =>
    activeRun.value ? recordOf(approvalsByRunId.value, activeRun.value.id, []) : [],
  )
  const activeArtifacts = computed<AgentArtifact[]>(() =>
    activeRun.value ? recordOf(artifactsByRunId.value, activeRun.value.id, []) : [],
  )
  const activeToolResults = computed<AgentToolResult[]>(() =>
    activeRun.value ? recordOf(toolResultsByRunId.value, activeRun.value.id, []) : [],
  )
  const activeEventProjection = computed<AgentRunEventProjection>(() =>
    activeRun.value
      ? recordOf(eventsByRunId.value, activeRun.value.id, createAgentRunEventProjection())
      : createAgentRunEventProjection(),
  )
  const activeWorkTraceDeltas = computed<AgentWorkTraceDelta[]>(() => activeEventProjection.value.workTraceDeltas)
  const latestWorkTrace = computed<AgentWorkTraceDelta | null>(() => activeEventProjection.value.latestWorkTrace)
  const replayRequired = computed(() => activeEventProjection.value.replayRequired)
  const activeConnectionState = computed<SSEConnectionState>(() =>
    activeRun.value ? recordOf(connectionByRunId.value, activeRun.value.id, 'closed') : 'closed',
  )

  const hasRun = (runId: string) => Boolean(runsById.value[runId])

  const ensureSelectedRun = (preferredRunId?: string) => {
    if (preferredRunId && hasRun(preferredRunId)) {
      selectedRunId.value = preferredRunId
      return selectedRunId.value
    }
    if (selectedRunId.value && hasRun(selectedRunId.value)) return selectedRunId.value
    selectedRunId.value = runs.value.at(-1)?.id || ''
    return selectedRunId.value
  }

  const replaceRuns = (items: AgentRun[], preferredRunId?: string) => {
    const currentById = runsById.value
    runs.value = sortRuns(items).map((item) => ({ ...currentById[item.id], ...item }))
    ensureSelectedRun(preferredRunId)
  }

  const upsertRun = (run: AgentRun, options: { select?: boolean } = {}) => {
    const index = runs.value.findIndex((item) => item.id === run.id)
    if (index >= 0) {
      const next = [...runs.value]
      next[index] = { ...next[index], ...run }
      runs.value = sortRuns(next)
    } else {
      runs.value = sortRuns([...runs.value, run])
    }
    if (options.select || !selectedRunId.value) selectedRunId.value = run.id
  }

  const selectRun = (runId?: string) => {
    if (!runId || !hasRun(runId)) return false
    selectedRunId.value = runId
    return true
  }

  const updateRun = (runId: string, patch: Partial<AgentRun>) => {
    const current = runsById.value[runId]
    if (!current) return
    upsertRun({ ...current, ...patch })
  }

  const setRunState = (runId: string, state: AgentStateProjection) => {
    if (!hasRun(runId)) return
    statesByRunId.value = { ...statesByRunId.value, [runId]: state }
    updateRun(runId, {
      progress: Math.max(0, Math.min(100, Number(state.progress) || 0)),
      current_phase: state.phase || undefined,
      current_step: state.current_step,
      ...(state.status ? { status: state.status } : {}),
      ...(state.terminal_status ? { status: state.terminal_status } : {}),
      ...(state.state_version !== undefined ? { state_version: state.state_version } : {}),
      ...(state.allowed_commands ? { allowed_commands: state.allowed_commands } : {}),
    })
  }

  const setRunSteps = (runId: string, steps: AgentRunStep[]) => {
    if (!hasRun(runId)) return
    stepsByRunId.value = {
      ...stepsByRunId.value,
      [runId]: [...steps].sort((left, right) => left.step_order - right.step_order),
    }
  }

  const setRunPlan = (runId: string, plan: AgentPlanResponse | null) => {
    if (!hasRun(runId)) return
    const next = { ...plansByRunId.value }
    if (plan) next[runId] = plan
    else delete next[runId]
    plansByRunId.value = next
  }

  const setRunContextSnapshot = (runId: string, snapshot: AgentContextSnapshot | null) => {
    if (!hasRun(runId)) return
    contextSnapshotsByRunId.value = { ...contextSnapshotsByRunId.value, [runId]: snapshot }
  }

  const setRunPlanRevision = (runId: string, revision: AgentPlanRevision | null) => {
    if (!hasRun(runId)) return
    planRevisionsByRunId.value = { ...planRevisionsByRunId.value, [runId]: revision }
  }

  const setRunConversationSummaries = (runId: string, summaries: AgentConversationSummary[]) => {
    if (!hasRun(runId)) return
    conversationSummariesByRunId.value = { ...conversationSummariesByRunId.value, [runId]: [...summaries] }
  }

  const setRunApprovals = (runId: string, approvals: AgentApproval[]) => {
    if (!hasRun(runId)) return
    approvalsByRunId.value = { ...approvalsByRunId.value, [runId]: [...approvals] }
  }

  const setRunArtifacts = (runId: string, artifacts: AgentArtifact[]) => {
    if (!hasRun(runId)) return
    artifactsByRunId.value = { ...artifactsByRunId.value, [runId]: [...artifacts] }
  }

  const setRunToolResults = (runId: string, results: AgentToolResult[]) => {
    if (!hasRun(runId)) return
    toolResultsByRunId.value = { ...toolResultsByRunId.value, [runId]: [...results] }
  }

  const setConnectionState = (runId: string, state: SSEConnectionState) => {
    if (!hasRun(runId)) return
    connectionByRunId.value = { ...connectionByRunId.value, [runId]: state }
  }

  const appendLocalActivity = (
    runId: string,
    label: string,
    detail: string,
    key?: string,
    eventType = 'local',
  ) => {
    if (!hasRun(runId)) return false
    const current = recordOf(eventsByRunId.value, runId, createAgentRunEventProjection())
    const id = key || `local:${runId}:${Date.now()}:${current.events.length}`
    if (current.events.some((item) => item.id === id)) return false
    const event: AgentDisplayEvent = {
      id,
      label,
      detail,
      sequence: current.lastSequence,
      eventType,
    }
    eventsByRunId.value = {
      ...eventsByRunId.value,
      [runId]: {
        ...current,
        events: [...current.events, event].slice(-MAX_AGENT_ACTIVITY_ITEMS),
      },
    }
    return true
  }

  const clearAssistantText = (runId: string) => {
    if (!hasRun(runId)) return
    const current = recordOf(eventsByRunId.value, runId, createAgentRunEventProjection())
    eventsByRunId.value = {
      ...eventsByRunId.value,
      [runId]: { ...current, assistantDeltas: [], assistantText: '' },
    }
  }

  const applyEvent = (event: SafeAgentEvent): AgentEventReduction | null => {
    if (!hasRun(event.run_id)) return null
    const current = recordOf(eventsByRunId.value, event.run_id, createAgentRunEventProjection())
    const reduction = reduceAgentRunEvent(current, event)
    if (!reduction.accepted) return reduction
    eventsByRunId.value = { ...eventsByRunId.value, [event.run_id]: reduction.projection }
    if (reduction.isLatest && Object.keys(reduction.runPatch).length) {
      updateRun(event.run_id, reduction.runPatch)
    }
    return reduction
  }

  const reset = () => {
    runs.value = []
    selectedRunId.value = ''
    statesByRunId.value = {}
    stepsByRunId.value = {}
    plansByRunId.value = {}
    contextSnapshotsByRunId.value = {}
    planRevisionsByRunId.value = {}
    conversationSummariesByRunId.value = {}
    approvalsByRunId.value = {}
    artifactsByRunId.value = {}
    toolResultsByRunId.value = {}
    eventsByRunId.value = {}
    connectionByRunId.value = {}
  }

  return {
    runs,
    runsById,
    selectedRunId,
    activeRun,
    activeRunState,
    activeRunSteps,
    activePlan,
    activeContextSnapshot,
    activePlanRevision,
    activeConversationSummaries,
    activeApprovals,
    activeArtifacts,
    activeToolResults,
    activeEventProjection,
    activeWorkTraceDeltas,
    latestWorkTrace,
    replayRequired,
    activeConnectionState,
    hasRun,
    ensureSelectedRun,
    replaceRuns,
    upsertRun,
    selectRun,
    updateRun,
    setRunState,
    setRunSteps,
    setRunPlan,
    setRunContextSnapshot,
    setRunPlanRevision,
    setRunConversationSummaries,
    setRunApprovals,
    setRunArtifacts,
    setRunToolResults,
    setConnectionState,
    appendLocalActivity,
    clearAssistantText,
    applyEvent,
    reset,
  }
}

export type AgentRunProjectionStore = ReturnType<typeof useAgentRunProjection>
export type AgentRunRawEvent = AgentEvent