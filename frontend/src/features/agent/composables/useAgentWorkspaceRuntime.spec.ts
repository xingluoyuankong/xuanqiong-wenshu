import { computed, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const {
  getRunProviderProvenanceMock,
  getRunContextSnapshotMock,
  getRunPlanRevisionMock,
  listRunConversationSummariesMock,
  getArtifactQualityMock,
  getArtifactLineageMock,
  listArtifactQualityBlockersMock,
  getArtifactDiffMock,
  getArtifactVersionDiffMock,
  getArtifactContentMock,
  listArtifactRewriteInstructionsMock,
  listEventsMock,
  listRunActivityMock,
  sessionStreamUrlMock,
} = vi.hoisted(() => ({
  getRunProviderProvenanceMock: vi.fn(),
  getRunContextSnapshotMock: vi.fn(),
  getRunPlanRevisionMock: vi.fn(),
  listRunConversationSummariesMock: vi.fn(),
  getArtifactQualityMock: vi.fn(),
  getArtifactLineageMock: vi.fn(),
  listArtifactQualityBlockersMock: vi.fn(),
  getArtifactDiffMock: vi.fn(),
  getArtifactVersionDiffMock: vi.fn(),
  getArtifactContentMock: vi.fn(),
  listArtifactRewriteInstructionsMock: vi.fn(),
  listEventsMock: vi.fn(),
  listRunActivityMock: vi.fn(),
  sessionStreamUrlMock: vi.fn(),
}))

vi.mock('@/api/agent', () => ({
  AgentAPI: {
    getRunProviderProvenance: getRunProviderProvenanceMock,
    getRunContextSnapshot: getRunContextSnapshotMock,
    getRunPlanRevision: getRunPlanRevisionMock,
    listRunConversationSummaries: listRunConversationSummariesMock,
    getArtifactQuality: getArtifactQualityMock,
    getArtifactLineage: getArtifactLineageMock,
    listArtifactQualityBlockers: listArtifactQualityBlockersMock,
    getArtifactDiff: getArtifactDiffMock,
    getArtifactVersionDiff: getArtifactVersionDiffMock,
    getArtifactContent: getArtifactContentMock,
    listArtifactRewriteInstructions: listArtifactRewriteInstructionsMock,
    listEvents: listEventsMock,
    listRunActivity: listRunActivityMock,
    sessionStreamUrl: sessionStreamUrlMock,
  },
}))

import { useAgentWorkspaceRuntime } from './useAgentWorkspaceRuntime'
import type { AgentArtifactLineage, AgentArtifactQuality, AgentQualityBlocker } from '@/api/agent'
import { useAgentRunProjection } from '@/features/agent/stores/agentRunProjection'

const run = {
  id: 'runtime-run', correlation_id: 'corr', session_id: 'session', user_id: 1,
  project_id: 'project', status: 'running', current_phase: 'planning', current_step: 0,
  progress: 10, created_at: '2026-08-30T00:00:00Z',
}
const artifact = {
  id: 'artifact-runtime', run_id: run.id, correlation_id: 'corr', user_id: 1,
  project_id: 'project', kind: 'chapter_candidate', uri: 'agent-artifact://runtime',
  sha256: 'a'.repeat(64), metadata_json: { status: 'candidate' }, created_at: run.created_at,
}

describe('useAgentWorkspaceRuntime', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    getRunProviderProvenanceMock.mockResolvedValue({
      planner_provider_called: true, planner_provider_fallback_reason: null,
      response_provider_called: false, response_provider_fallback_reason: 'TimeoutError',
      candidate_writer_provider_called: null, candidate_writer_provider_fallback_reason: null,
      candidate_writer_model_ref: null,
    })
    getRunContextSnapshotMock.mockResolvedValue(null)
    getRunPlanRevisionMock.mockResolvedValue(null)
    listRunConversationSummariesMock.mockResolvedValue([])
    getArtifactQualityMock.mockResolvedValue({ artifact_id: artifact.id, quality_result: null, findings: [], gate: { decision: 'passed', blocker_count: 0 } })
    getArtifactLineageMock.mockResolvedValue({ artifact_id: artifact.id, upstream_edges: [], downstream_edges: [] })
    listArtifactQualityBlockersMock.mockResolvedValue([])
    getArtifactDiffMock.mockResolvedValue({ artifact_id: artifact.id, lines: [] })
    getArtifactVersionDiffMock.mockResolvedValue({ artifact_id: artifact.id, lines: [] })
    getArtifactContentMock.mockResolvedValue('')
    listArtifactRewriteInstructionsMock.mockResolvedValue([])
    listEventsMock.mockResolvedValue([])
    listRunActivityMock.mockResolvedValue([])
    sessionStreamUrlMock.mockImplementation((sessionId: string, runId: string, afterSequence: number) => `/stream/${sessionId}/${runId}/${afterSequence}`)
  })

  const createRuntime = () => {
    const projection = useAgentRunProjection()
    projection.upsertRun(run, { select: true })
    const selectedProjectId = ref('project')
    const session = ref<{ id: string } | null>(null)
    const streaming = ref(false)
    const stream = { close: vi.fn(), start: vi.fn().mockResolvedValue(undefined) }
    const onTerminalRefresh = vi.fn()
    const addActivity = vi.fn()
    const tools = ref([])
    const runtime = useAgentWorkspaceRuntime({
      runProjection: projection,
      activeRun: projection.activeRun,
      plan: computed(() => projection.activePlan.value),
      artifacts: computed(() => projection.activeArtifacts.value),
      approvals: computed(() => projection.activeApprovals.value),
      selectedProjectId,
      session: session as never,
      selectedRunId: projection.selectedRunId,
      streaming,
      stream: stream as never,
      tools,
      addActivity,
      onTerminalRefresh,
    })
    return { runtime, projection, session, streaming, stream, addActivity, onTerminalRefresh }
  }

  it('loads stage-separated provenance into the selected Run without event-stream inference', async () => {
    const { runtime } = createRuntime()
    await runtime.loadRunFacts(run.id)

    expect(getRunProviderProvenanceMock).toHaveBeenCalledWith(run.id)
    expect(runtime.providerProvenanceByRunId.value[run.id]).toMatchObject({
      planner_provider_called: true,
      response_provider_called: false,
      response_provider_fallback_reason: 'TimeoutError',
    })
  })

  it('drops stale artifact blockers after switching the selected Run and keeps the new Run isolated', async () => {
    const { runtime, projection, addActivity } = createRuntime()
    const runB = { ...run, id: 'runtime-run-b' }
    const artifactB = { ...artifact, id: 'artifact-runtime-b', run_id: runB.id }
    let resolveOld: (value: AgentQualityBlocker[]) => void = () => undefined
    const oldBlockers = new Promise<AgentQualityBlocker[]>((resolve) => { resolveOld = resolve })
    const oldBlocker = { artifact_id: artifact.id, code: 'A-QUALITY-001', message: 'Run-A blocker' } as AgentQualityBlocker
    const newBlocker = { artifact_id: artifactB.id, code: 'B-QUALITY-001', message: 'Run-B blocker' } as AgentQualityBlocker
    listArtifactQualityBlockersMock
      .mockReturnValueOnce(oldBlockers)
      .mockResolvedValueOnce([newBlocker])

    const staleRequest = runtime.loadQualityBlockers(artifact)
    await vi.waitFor(() => expect(listArtifactQualityBlockersMock).toHaveBeenCalledWith(artifact.id))
    projection.upsertRun(runB, { select: true })
    runtime.resetArtifactFacts()
    resolveOld([oldBlocker])
    await staleRequest

    expect(runtime.qualityBlockers.value).toEqual([])
    expect(runtime.qualityBlockersLoading.value).toBe(false)
    expect(addActivity).not.toHaveBeenCalledWith('质量阻断定位已载入', expect.anything())

    await runtime.loadQualityBlockers(artifactB)
    expect(runtime.qualityBlockers.value).toEqual([newBlocker])
    expect(addActivity).toHaveBeenCalledWith('质量阻断定位已载入', '1 项阻断')
  })

  it('drops late Artifact facts after the selected Run is reset', async () => {
    const { runtime, projection } = createRuntime()
    let resolveQuality: (value: AgentArtifactQuality) => void = () => undefined
    let resolveLineage: (value: AgentArtifactLineage) => void = () => undefined
    const qualityPromise = new Promise<AgentArtifactQuality>((resolve) => { resolveQuality = resolve })
    const lineagePromise = new Promise<AgentArtifactLineage>((resolve) => { resolveLineage = resolve })
    getArtifactQualityMock.mockReturnValueOnce(qualityPromise)
    getArtifactLineageMock.mockReturnValueOnce(lineagePromise)

    const request = runtime.loadArtifactFacts(artifact)
    expect(runtime.artifactQualityFactsLoading.value[artifact.id]).toBe(true)

    projection.reset()
    runtime.resetArtifactFacts()
    resolveQuality({ artifact_id: artifact.id, quality_result: null, findings: [], gate: { decision: 'passed', blocker_count: 0 } } as unknown as AgentArtifactQuality)
    resolveLineage({ artifact_id: artifact.id, upstream_edges: [], downstream_edges: [] })
    await request

    expect(runtime.artifactQualityFacts.value).toEqual({})
    expect(runtime.artifactLineageFacts.value).toEqual({})
    expect(runtime.artifactQualityFactsLoading.value).toEqual({})
    expect(runtime.artifactQualityFactsErrors.value).toEqual({})
  })
  it('invalidates late Artifact facts when the facts state is explicitly reset', async () => {
    const { runtime } = createRuntime()
    let resolveQuality: (value: AgentArtifactQuality) => void = () => undefined
    let resolveLineage: (value: AgentArtifactLineage) => void = () => undefined
    const qualityPromise = new Promise<AgentArtifactQuality>((resolve) => { resolveQuality = resolve })
    const lineagePromise = new Promise<AgentArtifactLineage>((resolve) => { resolveLineage = resolve })
    getArtifactQualityMock.mockReturnValueOnce(qualityPromise)
    getArtifactLineageMock.mockReturnValueOnce(lineagePromise)

    const request = runtime.loadArtifactFacts(artifact)
    runtime.resetArtifactFacts()
    resolveQuality({ artifact_id: artifact.id, quality_result: null, findings: [], gate: { decision: 'passed', blocker_count: 0 } } as unknown as AgentArtifactQuality)
    resolveLineage({ artifact_id: artifact.id, upstream_edges: [], downstream_edges: [] })
    await request

    expect(runtime.artifactQualityFacts.value).toEqual({})
    expect(runtime.artifactLineageFacts.value).toEqual({})
    expect(runtime.artifactQualityFactsLoading.value).toEqual({})
  })
  it('keeps the latest quality facts when duplicate requests resolve out of order', async () => {
    const { runtime } = createRuntime()
    let resolveFirst: (value: AgentArtifactQuality) => void = () => undefined
    const firstPromise = new Promise<AgentArtifactQuality>((resolve) => { resolveFirst = resolve })
    const secondFacts = { artifact_id: artifact.id, quality_result: null, findings: [], gate: { decision: 'passed', blocker_count: 0 } } as unknown as AgentArtifactQuality
    const firstFacts = { artifact_id: artifact.id, quality_result: null, findings: [], gate: { decision: 'waived', blocker_count: 0 } } as unknown as AgentArtifactQuality
    getArtifactQualityMock.mockReturnValueOnce(firstPromise).mockResolvedValueOnce(secondFacts)

    const firstRequest = runtime.loadArtifactFacts(artifact)
    const secondRequest = runtime.loadArtifactFacts(artifact)
    await secondRequest
    resolveFirst(firstFacts)
    await firstRequest

    expect(runtime.artifactQualityFacts.value[artifact.id]).toEqual(secondFacts)
    expect(runtime.artifactQualityFactsErrors.value[artifact.id]).toBe('')
    expect(runtime.artifactQualityFactsLoading.value[artifact.id]).toBe(false)
  })

  it('does not let an older failed quality request poison a newer success', async () => {
    const { runtime } = createRuntime()
    let rejectFirst: (reason?: unknown) => void = () => undefined
    const firstPromise = new Promise<AgentArtifactQuality>((_resolve, reject) => { rejectFirst = reject })
    const secondFacts = { artifact_id: artifact.id, quality_result: null, findings: [], gate: { decision: 'passed', blocker_count: 0 } } as unknown as AgentArtifactQuality
    getArtifactQualityMock.mockReturnValueOnce(firstPromise).mockResolvedValueOnce(secondFacts)

    const firstRequest = runtime.loadArtifactFacts(artifact)
    const secondRequest = runtime.loadArtifactFacts(artifact)
    await secondRequest
    rejectFirst(new Error('older quality request failed'))
    await expect(firstRequest).rejects.toThrow('older quality request failed')

    expect(runtime.artifactQualityFacts.value[artifact.id]).toEqual(secondFacts)
    expect(runtime.artifactQualityFactsErrors.value[artifact.id]).toBe('')
    expect(runtime.artifactQualityFactsLoading.value[artifact.id]).toBe(false)
  })
  it('exposes lineage loading and errors independently from quality facts', async () => {
    const { runtime } = createRuntime()
    getArtifactLineageMock.mockRejectedValueOnce(new Error('lineage transport failed'))

    const request = runtime.loadArtifactFacts(artifact)
    expect(runtime.artifactLineageFactsLoading.value[artifact.id]).toBe(true)
    await expect(request).resolves.toBeUndefined()

    expect(runtime.artifactQualityFacts.value[artifact.id]).toBeDefined()
    expect(runtime.artifactLineageFactsLoading.value[artifact.id]).toBe(false)
    expect(runtime.artifactLineageFactsErrors.value[artifact.id]).toBe('lineage transport failed')
  })

  it('still loads quality blockers when optional lineage facts fail', async () => {
    const { runtime } = createRuntime()
    const blocker = { artifact_id: artifact.id, code: 'QUALITY-001', message: '质量阻断' } as AgentQualityBlocker
    getArtifactLineageMock.mockRejectedValueOnce(new Error('lineage unavailable'))
    listArtifactQualityBlockersMock.mockResolvedValueOnce([blocker])

    await runtime.loadQualityBlockers(artifact)

    expect(listArtifactQualityBlockersMock).toHaveBeenCalledWith(artifact.id)
    expect(runtime.qualityBlockers.value).toEqual([blocker])
  })
  it('clears the previous blocker result and attributes failures to the current Artifact', async () => {
    const { runtime } = createRuntime()
    const artifactB = { ...artifact, id: 'artifact-runtime-b' }
    const oldBlocker = { artifact_id: artifact.id, code: 'A-QUALITY-001', message: '旧阻断' } as AgentQualityBlocker
    listArtifactQualityBlockersMock.mockResolvedValueOnce([oldBlocker]).mockRejectedValueOnce(new Error('current blocker failed'))

    await runtime.loadQualityBlockers(artifact)
    await runtime.loadQualityBlockers(artifactB)

    expect(runtime.qualityBlockers.value).toEqual([])
    expect(runtime.qualityBlockersArtifactId.value).toBe(artifactB.id)
    expect(runtime.qualityBlockersError.value).toBe('current blocker failed')
    expect(runtime.qualityBlockersLoading.value).toBe(false)
    expect(runtime.qualityBlockersLoadingByArtifact.value[artifactB.id]).toBe(false)
  })
  it('keeps an Artifact fail-closed while authority facts are loading or unavailable', async () => {
    const { runtime } = createRuntime()
    const promise = runtime.loadArtifactFacts(artifact)
    expect(runtime.artifactQualityFactsLoading.value[artifact.id]).toBe(true)
    await promise
    expect(runtime.artifactQualityFactsLoading.value[artifact.id]).toBe(false)
    expect(runtime.artifactQualityFacts.value[artifact.id].gate?.decision).toBe('passed')

    getArtifactQualityMock.mockRejectedValueOnce(new Error('quality transport failed'))
    await expect(runtime.loadArtifactFacts(artifact)).rejects.toThrow('quality transport failed')
    expect(runtime.artifactQualityFactsErrors.value[artifact.id]).toBe('quality transport failed')
  })

  it('repairs an observed sequence gap from durable after_sequence activity without changing the selected Run', async () => {
    const { runtime, session } = createRuntime()
    session.value = { id: 'session' }
    listRunActivityMock.mockResolvedValueOnce([
      { id: 'event-2', run_id: run.id, sequence: 2, event_type: 'progress_update', summary: '补洞', data: { progress: 20 }, created_at: run.created_at },
    ])

    runtime.applyEvent({ id: 'event-1', run_id: run.id, sequence: 1, event_type: 'progress_update', summary: 'first', data: { progress: 10 }, created_at: run.created_at })
    runtime.applyEvent({ id: 'event-3', run_id: run.id, sequence: 3, event_type: 'progress_update', summary: 'third', data: { progress: 30 }, created_at: run.created_at })
    await Promise.resolve()
    await Promise.resolve()

    expect(listRunActivityMock).toHaveBeenCalledWith(run.id, 1, 500)
    expect(runtime.gapRepairStateByRunId.value[run.id]).toBe('repaired')
  })

  it('pages durable activity until a long sequence gap is repaired', async () => {
    const { runtime, session } = createRuntime()
    session.value = { id: 'session' }
    const pageOne = Array.from({ length: 500 }, (_, index) => ({
      id: `event-${index + 2}`,
      run_id: run.id,
      sequence: index + 2,
      event_type: 'progress_update',
      summary: 'repair page one',
      data: { progress: 20 },
      created_at: run.created_at,
    }))
    const pageTwo = Array.from({ length: 501 }, (_, index) => ({
      id: `event-${index + 502}`,
      run_id: run.id,
      sequence: index + 502,
      event_type: 'progress_update',
      summary: 'repair page two',
      data: { progress: 40 },
      created_at: run.created_at,
    }))
    listRunActivityMock
      .mockResolvedValueOnce(pageOne)
      .mockResolvedValueOnce(pageTwo)

    runtime.applyEvent({ id: 'event-1', run_id: run.id, sequence: 1, event_type: 'progress_update', summary: 'first', data: { progress: 10 }, created_at: run.created_at })
    runtime.applyEvent({ id: 'event-1003', run_id: run.id, sequence: 1003, event_type: 'progress_update', summary: 'last', data: { progress: 90 }, created_at: run.created_at })

    await vi.waitFor(() => expect(runtime.gapRepairStateByRunId.value[run.id]).toBe('repaired'))
    expect(listRunActivityMock).toHaveBeenNthCalledWith(1, run.id, 1, 500)
    expect(listRunActivityMock).toHaveBeenNthCalledWith(2, run.id, 501, 500)
  })

  it('fails closed when a gap repair page makes no contiguous cursor progress', async () => {
    const { runtime, session } = createRuntime()
    session.value = { id: 'session' }
    listRunActivityMock.mockResolvedValueOnce([
      { id: 'event-3-replayed', run_id: run.id, sequence: 3, event_type: 'progress_update', summary: 'duplicate', data: { progress: 30 }, created_at: run.created_at },
    ])

    runtime.applyEvent({ id: 'event-1', run_id: run.id, sequence: 1, event_type: 'progress_update', summary: 'first', data: { progress: 10 }, created_at: run.created_at })
    runtime.applyEvent({ id: 'event-3', run_id: run.id, sequence: 3, event_type: 'progress_update', summary: 'third', data: { progress: 30 }, created_at: run.created_at })

    await vi.waitFor(() => expect(runtime.gapRepairStateByRunId.value[run.id]).toBe('failed'))
    expect(listRunActivityMock).toHaveBeenCalledTimes(1)
  })

  it('repairs a prefix gap by replaying from after_sequence zero', async () => {
    const { runtime, session } = createRuntime()
    session.value = { id: 'session' }
    listRunActivityMock.mockResolvedValueOnce([
      { id: 'event-1', run_id: run.id, sequence: 1, event_type: 'progress_update', summary: 'first', data: { progress: 10 }, created_at: run.created_at },
      { id: 'event-2', run_id: run.id, sequence: 2, event_type: 'progress_update', summary: 'second', data: { progress: 20 }, created_at: run.created_at },
    ])

    runtime.applyEvent({ id: 'event-3', run_id: run.id, sequence: 3, event_type: 'progress_update', summary: 'third', data: { progress: 30 }, created_at: run.created_at })

    await vi.waitFor(() => expect(runtime.gapRepairStateByRunId.value[run.id]).toBe('repaired'))
    expect(listRunActivityMock).toHaveBeenCalledWith(run.id, 0, 500)
  })

  it('projects a stream_error only into the right-side activity log without mutating AgentEvent state', async () => {
    const { runtime, session, stream, addActivity } = createRuntime()
    session.value = { id: 'session' }
    await runtime.loadEventsAndStream(session.value as never, run)

    const streamOptions = stream.start.mock.calls[0][0]
    streamOptions.onStreamError({
      run_id: run.id,
      error_code: 'AGENT_EVENT_LEDGER_UNAVAILABLE',
      retryable: true,
      cursor: 7,
    })

    expect(addActivity).toHaveBeenCalledWith(
      '事件账本暂时不可用',
      'AGENT_EVENT_LEDGER_UNAVAILABLE；连接将从最近确认位置重试；将从游标 7 重连',
      'stream-error:runtime-run:AGENT_EVENT_LEDGER_UNAVAILABLE:7',
      0,
      'stream_error',
    )
    expect(runtime.applyEvent({
      id: 'event-1', run_id: run.id, sequence: 1, event_type: 'assistant_delta', summary: '正文',
      data: { content: '正文内容' }, created_at: run.created_at,
    })).not.toBeNull()
  })

  it('fences one Run stream lifecycle and refreshes the session only after the selected Run reaches terminal state', async () => {
    const { runtime, session, streaming, stream, onTerminalRefresh } = createRuntime()
    session.value = { id: 'session' }

    await runtime.loadEventsAndStream(session.value as never, run)

    expect(stream.start).toHaveBeenCalledTimes(1)
    const options = stream.start.mock.calls[0][0]
    expect(options.streamUrl(7)).toBe('/stream/session/runtime-run/7')
    options.onConnectionState('live')
    expect(streaming.value).toBe(true)
    options.onTerminal('run_completed')
    expect(streaming.value).toBe(false)
    expect(onTerminalRefresh).toHaveBeenCalledTimes(1)
    runtime.closeRunLifecycle()
    expect(stream.close).toHaveBeenCalledTimes(1)
  })

})
