import { ref, type ComputedRef, type Ref } from 'vue'
import {
  AgentAPI,
  type AgentApproval,
  type AgentArtifact,
  type AgentArtifactDiff,
  type AgentArtifactLineage,
  type AgentArtifactQuality,
  type AgentContextSnapshot,
  type AgentEvent,
  type AgentPlanResponse,
  type AgentPlanRevision,
  type AgentProviderProvenance,
  type AgentQualityBlocker,
  type AgentRewriteInstruction,
  type AgentRun,
  type AgentRunStep,
  type AgentSession,
  type AgentStateProjection,
  type AgentToolDescriptor,
} from '@/api/agent'
import { toSafeAgentEvent } from '@/utils/agentEventSafety'
import type { AgentRunProjectionStore } from '@/features/agent/stores/agentRunProjection'
import type { AgentRunStream } from '@/features/agent/composables/useAgentRunStream'
import type { SSEConnectionState, StreamErrorData } from '@/utils/sseStream'

export interface AgentWorkspaceRuntimeOptions {
  runProjection: AgentRunProjectionStore
  activeRun: ComputedRef<AgentRun | null>
  plan: ComputedRef<AgentPlanResponse | null>
  artifacts: ComputedRef<AgentArtifact[]>
  approvals: ComputedRef<AgentApproval[]>
  selectedProjectId: Ref<string>
  session: Ref<AgentSession | null>
  selectedRunId: Ref<string>
  streaming: Ref<boolean>
  stream: AgentRunStream
  tools: Ref<AgentToolDescriptor[]>
  addActivity: (label: string, detail: string, key?: string, sequence?: number, eventType?: string) => void
  onTerminalRefresh: () => void
}

/**
 * Read-model and Artifact coordination for the Chat-first Agent workspace.
 * It owns durable facts, safe event reductions and artifact quality/lineage state;
 * the page remains responsible for layout, session routing and author intent.
 */
export function useAgentWorkspaceRuntime(options: AgentWorkspaceRuntimeOptions) {
  const qualityBlockers = ref<AgentQualityBlocker[]>([])
  const qualityBlockersLoading = ref(false)
  const qualityBlockersArtifactId = ref<string | null>(null)
  const qualityBlockersError = ref('')
  const qualityBlockersLoadingByArtifact = ref<Record<string, boolean>>({})
  const rewriteInstructions = ref<Record<string, AgentRewriteInstruction[]>>({})
  const rewriteLoading = ref<Record<string, boolean>>({})
  const artifactDiff = ref<AgentArtifactDiff | null>(null)
  const artifactDiffLoading = ref(false)
  const artifactPreview = ref('')
  const artifactQualityFacts = ref<Record<string, AgentArtifactQuality>>({})
  const artifactQualityFactsLoading = ref<Record<string, boolean>>({})
  const artifactQualityFactsErrors = ref<Record<string, string>>({})
  const artifactLineageFacts = ref<Record<string, AgentArtifactLineage>>({})
  const artifactLineageFactsLoading = ref<Record<string, boolean>>({})
  const artifactLineageFactsErrors = ref<Record<string, string>>({})
  const providerProvenanceByRunId = ref<Record<string, AgentProviderProvenance | null>>({})
  const gapRepairStateByRunId = ref<Record<string, 'idle' | 'repairing' | 'repaired' | 'failed'>>({})
  const GAP_REPAIR_PAGE_LIMIT = 500
  const GAP_REPAIR_MAX_PAGES = 8
  let lifecycleGeneration = 0
  let artifactViewGeneration = 0
  const artifactFactsRequestGeneration = new Map<string, number>()
  const artifactFactsRequestKey = (artifact: AgentArtifact) => `${artifact.run_id}:${artifact.id}`
  const qualityBlockerRequestGeneration = new Map<string, number>()
  const qualityBlockerRequestKey = (artifact: AgentArtifact) => `quality-blockers:${artifact.run_id}:${artifact.id}`
  type ArtifactViewRequest = { generation: number; runId: string; artifactId: string }
  const beginArtifactViewRequest = (artifact: AgentArtifact): ArtifactViewRequest => ({
    generation: ++artifactViewGeneration,
    runId: artifact.run_id,
    artifactId: artifact.id,
  })
  const isCurrentArtifactContext = (generation: number, runId: string) =>
    generation === artifactViewGeneration &&
    options.selectedRunId.value === runId
  const isCurrentArtifactRequest = (request: ArtifactViewRequest) =>
    isCurrentArtifactContext(request.generation, request.runId)

  const materializePlanSteps = (loaded: AgentRunStep[]) =>
    loaded
      .slice()
      .sort((left, right) => left.step_order - right.step_order)
      .map((step) => {
        const descriptor = options.tools.value.find((tool) => tool.name === step.tool_name)
        return {
          order: step.step_order,
          tool_name: step.tool_name,
          description: descriptor?.description || '项目内能力执行步骤',
          risk_level: descriptor?.risk_level || 'read',
          requires_confirmation: Boolean(descriptor?.requires_confirmation),
          status: step.status,
        }
      })

  const loadRunSteps = async (runId: string) => {
    if (typeof AgentAPI.listRunSteps !== 'function') return
    try {
      const loaded = await AgentAPI.listRunSteps(runId)
      if (!options.runProjection.hasRun(runId)) return
      options.runProjection.setRunSteps(runId, loaded)
      if (options.activeRun.value?.id === runId && options.plan.value && loaded.length) {
        options.runProjection.setRunPlan(runId, {
          ...options.plan.value,
          steps: materializePlanSteps(loaded),
        })
      }
    } catch {
      /* Step checkpoint data supplements the durable chat flow. */
    }
  }

  const loadRunPlan = async (runId: string) => {
    if (typeof AgentAPI.getRunPlan !== 'function') return
    try {
      const loaded = await AgentAPI.getRunPlan(runId)
      if (options.runProjection.hasRun(runId)) options.runProjection.setRunPlan(runId, loaded)
    } catch {
      /* Steps remain available through the durable step projection. */
    }
  }

  const loadRunState = async (runId: string): Promise<AgentStateProjection | null> => {
    if (typeof AgentAPI.getRunState !== 'function') return null
    try {
      const state = await AgentAPI.getRunState(runId)
      if (!options.runProjection.hasRun(runId)) return null
      options.runProjection.setRunState(runId, state)
      return state
    } catch {
      return null
    }
  }

  const loadRunFacts = async (runId: string) => {
    if (!options.runProjection.hasRun(runId)) return
    const loads: Promise<void>[] = []
    if (typeof AgentAPI.getRunProviderProvenance === 'function') {
      loads.push(AgentAPI.getRunProviderProvenance(runId)
        .then((item) => {
          if (options.runProjection.hasRun(runId)) {
            providerProvenanceByRunId.value = { ...providerProvenanceByRunId.value, [runId]: item }
          }
        })
        .catch(() => {
          if (options.runProjection.hasRun(runId)) {
            providerProvenanceByRunId.value = { ...providerProvenanceByRunId.value, [runId]: null }
          }
        }))
    }
    if (typeof AgentAPI.getRunContextSnapshot === 'function') {
      loads.push(AgentAPI.getRunContextSnapshot(runId)
        .then((item: AgentContextSnapshot | null) => {
          if (options.runProjection.hasRun(runId)) options.runProjection.setRunContextSnapshot(runId, item)
        })
        .catch(() => undefined))
    }
    if (typeof AgentAPI.getRunPlanRevision === 'function') {
      loads.push(AgentAPI.getRunPlanRevision(runId)
        .then((item: AgentPlanRevision | null) => {
          if (options.runProjection.hasRun(runId)) options.runProjection.setRunPlanRevision(runId, item)
        })
        .catch(() => undefined))
    }
    if (typeof AgentAPI.listRunConversationSummaries === 'function') {
      loads.push(AgentAPI.listRunConversationSummaries(runId)
        .then((items) => {
          if (options.runProjection.hasRun(runId)) options.runProjection.setRunConversationSummaries(runId, items)
        })
        .catch(() => undefined))
    }
    await Promise.all(loads)
  }

  const repairSequenceGap = async (runId: string, afterSequence: number) => {
    const currentSession = options.session.value
    if (!currentSession || options.selectedRunId.value !== runId || afterSequence < 0) return
    if (gapRepairStateByRunId.value[runId] === 'repairing') return
    gapRepairStateByRunId.value = { ...gapRepairStateByRunId.value, [runId]: 'repairing' }
    const generation = lifecycleGeneration
    const stillCurrent = () =>
      lifecycleGeneration === generation &&
      options.session.value?.id === currentSession.id &&
      options.selectedRunId.value === runId
    let cursor = afterSequence
    try {
      for (let page = 0; page < GAP_REPAIR_MAX_PAGES; page += 1) {
        const events = typeof AgentAPI.listRunActivity === 'function'
          ? await AgentAPI.listRunActivity(runId, cursor, GAP_REPAIR_PAGE_LIMIT)
          : await AgentAPI.listEvents(currentSession.id, runId, cursor)
        if (!stillCurrent()) return
        for (const event of events) applyEvent(event)
        if (!stillCurrent()) return
        const projection = options.runProjection.activeEventProjection.value
        if (!projection.hasSequenceGap) {
          gapRepairStateByRunId.value = { ...gapRepairStateByRunId.value, [runId]: 'repaired' }
          return
        }
        const nextCursor = projection.lastContiguousSequence
        // Empty/repeated pages cannot heal the gap. Stop instead of issuing an
        // unbounded replay loop against a truncated or stale activity ledger.
        if (!events.length || nextCursor <= cursor) {
          gapRepairStateByRunId.value = { ...gapRepairStateByRunId.value, [runId]: 'failed' }
          return
        }
        cursor = nextCursor
      }
      if (stillCurrent()) {
        gapRepairStateByRunId.value = { ...gapRepairStateByRunId.value, [runId]: 'failed' }
      }
    } catch {
      if (stillCurrent()) {
        gapRepairStateByRunId.value = { ...gapRepairStateByRunId.value, [runId]: 'failed' }
      }
    }
  }

  const applyEvent = (raw: AgentEvent) => {
    const safe = toSafeAgentEvent(raw)
    const reduction = options.runProjection.applyEvent(safe)
    if (!reduction?.accepted) return
    if (safe.run_id === options.selectedRunId.value && reduction.projection.hasSequenceGap) {
      void repairSequenceGap(safe.run_id, reduction.projection.lastContiguousSequence)
    }
    if (safe.event_type === 'public_work_summary') void loadRunState(safe.run_id)
    if (safe.event_type === 'conversation_summary_created') void loadRunFacts(safe.run_id)
    if (['plan_created', 'plan_revised', 'tool_call_completed', 'tool_call_failed', 'approval_required'].includes(safe.event_type)) {
      void loadRunSteps(safe.run_id)
      if (safe.event_type === 'plan_created' || safe.event_type === 'plan_revised') {
        void loadRunPlan(safe.run_id)
        void loadRunFacts(safe.run_id)
      }
      if (safe.event_type === 'approval_required' && typeof AgentAPI.listApprovals === 'function') {
        void AgentAPI.listApprovals(safe.run_id).then((items) => {
          options.runProjection.setRunApprovals(safe.run_id, items)
        }).catch(() => undefined)
      }
    }
  }

  const loadArtifactFacts = async (artifact: AgentArtifact, generation = artifactViewGeneration) => {
    const requestKey = artifactFactsRequestKey(artifact)
    const requestGeneration = (artifactFactsRequestGeneration.get(requestKey) || 0) + 1
    artifactFactsRequestGeneration.set(requestKey, requestGeneration)
    const isCurrent = () =>
      isCurrentArtifactContext(generation, artifact.run_id) &&
      artifactFactsRequestGeneration.get(requestKey) === requestGeneration
    const tasks: Promise<void>[] = []
    let qualityTaskIndex: number | null = null
    if (typeof AgentAPI.getArtifactQuality === 'function') {
      qualityTaskIndex = tasks.length
      artifactQualityFactsLoading.value = { ...artifactQualityFactsLoading.value, [artifact.id]: true }
      artifactQualityFactsErrors.value = { ...artifactQualityFactsErrors.value, [artifact.id]: '' }
      tasks.push(AgentAPI.getArtifactQuality(artifact.id).then((value) => {
        if (isCurrent()) {
          artifactQualityFacts.value = { ...artifactQualityFacts.value, [artifact.id]: value }
          artifactQualityFactsErrors.value = { ...artifactQualityFactsErrors.value, [artifact.id]: '' }
        }
      }).catch((error) => {
        if (isCurrent()) {
          artifactQualityFactsErrors.value = {
            ...artifactQualityFactsErrors.value,
            [artifact.id]: error instanceof Error ? error.message : '请求失败',
          }
        }
        throw error
      }).finally(() => {
        if (isCurrent()) artifactQualityFactsLoading.value = { ...artifactQualityFactsLoading.value, [artifact.id]: false }
      }))
    }
    if (typeof AgentAPI.getArtifactLineage === 'function') {
      artifactLineageFactsLoading.value = { ...artifactLineageFactsLoading.value, [artifact.id]: true }
      artifactLineageFactsErrors.value = { ...artifactLineageFactsErrors.value, [artifact.id]: '' }
      tasks.push(AgentAPI.getArtifactLineage(artifact.id).then((value) => {
        if (isCurrent()) {
          artifactLineageFacts.value = { ...artifactLineageFacts.value, [artifact.id]: value }
          artifactLineageFactsErrors.value = { ...artifactLineageFactsErrors.value, [artifact.id]: '' }
        }
      }).catch((error) => {
        if (isCurrent()) {
          artifactLineageFactsErrors.value = {
            ...artifactLineageFactsErrors.value,
            [artifact.id]: error instanceof Error ? error.message : '请求失败',
          }
        }
      }).finally(() => {
        if (isCurrent()) artifactLineageFactsLoading.value = { ...artifactLineageFactsLoading.value, [artifact.id]: false }
      }))
    }
    const results = await Promise.allSettled(tasks)
    const qualityResult = qualityTaskIndex === null ? null : results[qualityTaskIndex]
    if (qualityResult?.status === 'rejected') {
      throw qualityResult.reason
    }
  }

  const loadArtifactsWithFacts = async (runId: string) => {
    if (typeof AgentAPI.listArtifacts !== 'function') return []
    const artifacts = await AgentAPI.listArtifacts(runId)
    if (!options.runProjection.hasRun(runId)) return artifacts
    options.runProjection.setRunArtifacts(runId, artifacts)
    await Promise.all(artifacts.map((artifact) => loadArtifactFacts(artifact).catch(() => undefined)))
    return artifacts
  }

  const loadQualityBlockers = async (artifact: AgentArtifact) => {
    if (typeof AgentAPI.listArtifactQualityBlockers !== 'function') return
    const request = beginArtifactViewRequest(artifact)
    const requestKey = qualityBlockerRequestKey(artifact)
    const requestGeneration = (qualityBlockerRequestGeneration.get(requestKey) || 0) + 1
    qualityBlockerRequestGeneration.set(requestKey, requestGeneration)
    const isCurrentBlockerRequest = () =>
      isCurrentArtifactRequest(request) &&
      qualityBlockerRequestGeneration.get(requestKey) === requestGeneration
    qualityBlockersArtifactId.value = artifact.id
    qualityBlockersError.value = ''
    qualityBlockers.value = []
    qualityBlockersLoading.value = true
    qualityBlockersLoadingByArtifact.value = { ...qualityBlockersLoadingByArtifact.value, [artifact.id]: true }
    try {
      await loadArtifactFacts(artifact, request.generation)
      const blockers = await AgentAPI.listArtifactQualityBlockers(artifact.id)
      if (!isCurrentBlockerRequest()) return
      qualityBlockers.value = blockers
      options.addActivity('质量阻断定位已载入', `${blockers.length} 项阻断`)
    } catch (error) {
      if (isCurrentBlockerRequest()) {
        qualityBlockers.value = []
        qualityBlockersError.value = error instanceof Error ? error.message : '无法读取质量阻断'
        options.addActivity('质量阻断读取失败', qualityBlockersError.value)
      }
    } finally {
      if (qualityBlockerRequestGeneration.get(requestKey) === requestGeneration) {
        qualityBlockersLoadingByArtifact.value = { ...qualityBlockersLoadingByArtifact.value, [artifact.id]: false }
      }
      if (isCurrentBlockerRequest()) qualityBlockersLoading.value = false
    }
  }

  const loadRewriteInstructions = async (artifact: AgentArtifact) => {
    if (typeof AgentAPI.listArtifactRewriteInstructions !== 'function') return
    const request = beginArtifactViewRequest(artifact)
    rewriteLoading.value = { ...rewriteLoading.value, [artifact.id]: true }
    try {
      const instructions = await AgentAPI.listArtifactRewriteInstructions(artifact.id)
      if (!isCurrentArtifactRequest(request)) return
      rewriteInstructions.value = { ...rewriteInstructions.value, [artifact.id]: instructions }
      options.addActivity('修复指令已生成', `${artifact.id.slice(0, 8)} 已生成结构化 rewrite instruction`)
    } catch (error) {
      if (isCurrentArtifactRequest(request)) options.addActivity('修复指令生成失败', error instanceof Error ? error.message : '无法生成修复指令')
    } finally {
      if (isCurrentArtifactRequest(request)) rewriteLoading.value = { ...rewriteLoading.value, [artifact.id]: false }
    }
  }

  const compareArtifact = async (artifact: AgentArtifact) => {
    const against = options.artifacts.value.find((item) => item.id !== artifact.id)
    if (!against || typeof AgentAPI.getArtifactDiff !== 'function') return
    const request = beginArtifactViewRequest(artifact)
    artifactDiffLoading.value = true
    try {
      const diff = await AgentAPI.getArtifactDiff(artifact.id, against.id)
      if (!isCurrentArtifactRequest(request)) return
      artifactDiff.value = diff
      options.addActivity('候选差异已载入', `${artifact.id.slice(0, 8)} 与 ${against.id.slice(0, 8)} 已完成比较`)
    } catch (error) {
      if (isCurrentArtifactRequest(request)) options.addActivity('候选差异读取失败', error instanceof Error ? error.message : '无法读取候选差异')
    } finally {
      if (isCurrentArtifactRequest(request)) artifactDiffLoading.value = false
    }
  }

  const compareArtifactWithVersion = async (artifact: AgentArtifact) => {
    if (!options.selectedProjectId.value || typeof AgentAPI.getArtifactVersionDiff !== 'function') return
    const metadata = artifact.metadata_json || {}
    const chapterNumber = Number(metadata.chapter_number)
    const versionId = Number(metadata.source_version_id)
    if (!Number.isInteger(chapterNumber) || chapterNumber < 1 || !Number.isInteger(versionId) || versionId < 1) {
      options.addActivity('正式版本比较不可用', '候选没有受控来源版本，无法建立正式版本差异。')
      return
    }
    const request = beginArtifactViewRequest(artifact)
    artifactDiffLoading.value = true
    try {
      const diff = await AgentAPI.getArtifactVersionDiff(artifact.id, {
        projectId: options.selectedProjectId.value, chapterNumber, versionId,
      })
      if (!isCurrentArtifactRequest(request)) return
      artifactDiff.value = diff
      options.addActivity('正式版本差异已载入', `${artifact.id.slice(0, 8)} 与第 ${chapterNumber} 章版本 ${versionId} 已完成比较`)
    } catch (error) {
      if (isCurrentArtifactRequest(request)) options.addActivity('正式版本差异读取失败', error instanceof Error ? error.message : '无法读取正式版本差异')
    } finally {
      if (isCurrentArtifactRequest(request)) artifactDiffLoading.value = false
    }
  }

  const previewArtifact = async (artifact: AgentArtifact) => {
    if (typeof AgentAPI.getArtifactContent !== 'function') return
    const request = beginArtifactViewRequest(artifact)
    try {
      const content = await AgentAPI.getArtifactContent(artifact.id)
      if (isCurrentArtifactRequest(request)) artifactPreview.value = content
    } catch (error) {
      if (isCurrentArtifactRequest(request)) options.addActivity('候选预览失败', error instanceof Error ? error.message : '无法读取候选正文')
    }
  }

  const loadDurableRunActivity = async (currentSession: AgentSession, runId: string) => {
    const sessionEvents = await AgentAPI.listEvents(currentSession.id, runId, 0)
    if (typeof AgentAPI.listRunActivity !== 'function') return sessionEvents
    try {
      const activityEvents = await AgentAPI.listRunActivity(runId, 0, 500)
      const byIdentity = new Map<string, AgentEvent>()
      for (const event of [...sessionEvents, ...activityEvents]) {
        byIdentity.set(event.id || `${event.run_id}:${event.sequence}`, event)
      }
      return [...byIdentity.values()].sort((left, right) => left.sequence - right.sequence)
    } catch {
      return sessionEvents
    }
  }

  const closeRunLifecycle = () => {
    lifecycleGeneration += 1
    options.streaming.value = false
    options.stream.close()
  }

  const loadEventsAndStream = async (currentSession: AgentSession, run: AgentRun) => {
    if (typeof AgentAPI.listEvents !== 'function' || typeof AgentAPI.sessionStreamUrl !== 'function') return
    if (!options.runProjection.selectRun(run.id)) return
    const generation = ++lifecycleGeneration
    options.runProjection.clearAssistantText(run.id)
    options.streaming.value = true
    const isCurrentFeed = () =>
      lifecycleGeneration === generation &&
      options.session.value?.id === currentSession.id &&
      options.selectedRunId.value === run.id
    await Promise.all([loadRunSteps(run.id), loadRunState(run.id), loadRunFacts(run.id)])
    if (!isCurrentFeed()) return
    await options.stream.start({
      sessionId: currentSession.id,
      runId: run.id,
      initialStatus: options.activeRun.value?.status || run.status,
      loadHistory: () => loadDurableRunActivity(currentSession, run.id),
      streamUrl: (afterSequence) => AgentAPI.sessionStreamUrl(currentSession.id, run.id, afterSequence),
      isCurrent: isCurrentFeed,
      onEvent: (event) => applyEvent(event),
      onConnectionState: (state: SSEConnectionState) => {
        if (!isCurrentFeed()) return
        options.runProjection.setConnectionState(run.id, state)
        options.streaming.value = ['connecting', 'live', 'reconnecting'].includes(state)
      },
      onTerminal: (eventType) => {
        if (!isCurrentFeed()) return
        if (['run_completed', 'run_failed', 'run_cancelled'].includes(eventType)) {
          options.streaming.value = false
          options.runProjection.clearAssistantText(run.id)
          options.onTerminalRefresh()
        }
      },
      onStreamError: (data: StreamErrorData) => {
        if (!isCurrentFeed()) return
        const cursor = Number.isSafeInteger(data.cursor) && (data.cursor as number) >= 0
          ? `；将从游标 ${data.cursor} 重连`
          : ''
        options.addActivity(
          '事件账本暂时不可用',
          `${data.error_code}${data.retryable ? '；连接将从最近确认位置重试' : '；请重新打开本次运行'}${cursor}`,
          `stream-error:${run.id}:${data.error_code}:${data.cursor ?? 'unknown'}`,
          0,
          'stream_error',
        )
      },
      onError: (error) => {
        if (isCurrentFeed()) options.addActivity('运行流暂时中断', error)
      },
    })
  }

  const executeApprovalAction = async (approval: AgentApproval) => {
    if (typeof AgentAPI.executeApproval !== 'function') return
    try {
      const artifact = await AgentAPI.executeApproval(approval.id)
      options.runProjection.setRunArtifacts(approval.run_id, [...options.artifacts.value, artifact])
      await loadArtifactFacts(artifact).catch(() => undefined)
      options.runProjection.setRunApprovals(
        approval.run_id,
        options.approvals.value.map((item) => (item.id === approval.id ? { ...item, status: 'executed' } : item)),
      )
      options.addActivity('候选 artifact 已生成', artifact.uri)
    } catch (error) {
      options.addActivity('候选生成失败', error instanceof Error ? error.message : '执行失败')
    }
  }

  const acceptArtifactAction = async (artifact: AgentArtifact) => {
    if (typeof AgentAPI.acceptArtifact !== 'function') return
    try {
      const accepted = await AgentAPI.acceptArtifact(artifact.id)
      options.runProjection.setRunArtifacts(
        artifact.run_id,
        options.artifacts.value.map((item) => (item.id === accepted.id ? accepted : item)),
      )
      await loadArtifactFacts(accepted).catch(() => undefined)
      options.addActivity('候选已接受', '已保存为新的章节版本。')
    } catch (error) {
      options.addActivity('候选接受失败', error instanceof Error ? error.message : '保存失败')
    }
  }

  const resetArtifactFacts = () => {
    artifactViewGeneration += 1
    qualityBlockers.value = []
    qualityBlockersArtifactId.value = null
    qualityBlockersError.value = ''
    qualityBlockersLoadingByArtifact.value = {}
    qualityBlockersLoading.value = false
    rewriteInstructions.value = {}
    rewriteLoading.value = {}
    artifactDiff.value = null
    artifactDiffLoading.value = false
    artifactPreview.value = ''
    artifactFactsRequestGeneration.clear()
    qualityBlockerRequestGeneration.clear()
    artifactQualityFacts.value = {}
    artifactQualityFactsLoading.value = {}
    artifactQualityFactsErrors.value = {}
    artifactLineageFacts.value = {}
    artifactLineageFactsLoading.value = {}
    artifactLineageFactsErrors.value = {}
    providerProvenanceByRunId.value = {}
    gapRepairStateByRunId.value = {}
  }

  return {
    qualityBlockers,
    qualityBlockersArtifactId,
    qualityBlockersError,
    qualityBlockersLoadingByArtifact,
    qualityBlockersLoading,
    rewriteInstructions,
    rewriteLoading,
    artifactDiff,
    artifactDiffLoading,
    artifactPreview,
    artifactQualityFacts,
    artifactQualityFactsLoading,
    artifactQualityFactsErrors,
    artifactLineageFacts,
    artifactLineageFactsLoading,
    artifactLineageFactsErrors,
    providerProvenanceByRunId,
    gapRepairStateByRunId,
    materializePlanSteps,
    loadRunSteps,
    loadRunPlan,
    loadRunState,
    loadRunFacts,
    applyEvent,
    repairSequenceGap,
    loadArtifactFacts,
    loadArtifactsWithFacts,
    loadQualityBlockers,
    loadRewriteInstructions,
    compareArtifact,
    compareArtifactWithVersion,
    previewArtifact,
    loadDurableRunActivity,
    loadEventsAndStream,
    closeRunLifecycle,
    executeApprovalAction,
    acceptArtifactAction,
    resetArtifactFacts,
  }
}
