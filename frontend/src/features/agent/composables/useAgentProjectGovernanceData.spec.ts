import { computed, nextTick, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const {
  listTimelineMock,
  listAuditMock,
  listJobsMock,
  listDeadLettersMock,
} = vi.hoisted(() => ({
  listTimelineMock: vi.fn(),
  listAuditMock: vi.fn(),
  listJobsMock: vi.fn(),
  listDeadLettersMock: vi.fn(),
}))

vi.mock('@/api/agent', () => ({
  AgentAPI: {
    listTimeline: listTimelineMock,
    listAudit: listAuditMock,
    listJobs: listJobsMock,
    listDeadLetters: listDeadLettersMock,
  },
}))

import { useAgentProjectGovernanceData } from './useAgentProjectGovernanceData'

const deferred = <T,>() => {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((next) => { resolve = next })
  return { promise, resolve }
}

const createData = (admin = false) => {
  const selectedProjectId = ref('project-a')
  const timeline = ref<any[]>([])
  const timelineLoading = ref(false)
  const timelineEventType = ref('')
  const timelineRunStatus = ref('')
  const auditLedger = ref<any[]>([])
  const auditLoading = ref(false)
  const jobs = ref<any[]>([])
  const jobsLoading = ref(false)
  const deadLetters = ref<any[]>([])
  const deadLettersLoading = ref(false)
  const addActivity = vi.fn()
  const data = useAgentProjectGovernanceData({
    selectedProjectId,
    isAdmin: computed(() => admin),
    timeline,
    timelineLoading,
    timelineEventType,
    timelineRunStatus,
    auditLedger,
    auditLoading,
    jobs,
    jobsLoading,
    deadLetters,
    deadLettersLoading,
    addActivity,
  })
  return {
    data, selectedProjectId, timeline, timelineLoading, timelineEventType,
    auditLedger, auditLoading, jobs, jobsLoading, deadLetters, deadLettersLoading, addActivity,
  }
}

describe('useAgentProjectGovernanceData', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('drops an old project timeline response after the project lifecycle is cleared', async () => {
    const state = createData()
    const pending = deferred<any[]>()
    listTimelineMock.mockReturnValueOnce(pending.promise)

    const loading = state.data.loadTimeline()
    state.selectedProjectId.value = 'project-b'
    state.data.clear()
    pending.resolve([{ id: 'old-event', session_id: 'old', run_id: 'old', sequence: 1 }])
    await loading

    expect(state.timeline.value).toEqual([])
    expect(state.timelineLoading.value).toBe(false)
    expect(state.addActivity).not.toHaveBeenCalled()
  })

  it('drops an old project response as soon as v-model changes project before the switch handler clears data', async () => {
    const state = createData()
    const pending = deferred<any[]>()
    listTimelineMock.mockReturnValueOnce(pending.promise)

    const loading = state.data.loadTimeline()
    state.selectedProjectId.value = 'project-b'
    pending.resolve([{ id: 'old-v-model-event', session_id: 'old', run_id: 'old', sequence: 1 }])
    await loading

    expect(state.timeline.value).toEqual([])
    expect(state.timelineLoading.value).toBe(false)
  })

  it('keeps all parallel project read models when reload starts independent request fences', async () => {
    const state = createData()
    listTimelineMock.mockResolvedValue([{ id: 'timeline-a' }])
    listAuditMock.mockResolvedValue([{ event_id: 'audit-a' }])
    listJobsMock.mockResolvedValue([{ id: 'job-a', status: 'queued' }])

    await state.data.reload()

    expect(listTimelineMock).toHaveBeenCalledWith({
      projectId: 'project-a', eventType: undefined, runStatus: undefined, limit: 100,
    })
    expect(listAuditMock).toHaveBeenCalledWith({ projectId: 'project-a', limit: 100 })
    expect(listJobsMock).toHaveBeenCalledWith('project-a')
    expect(state.timeline.value).toEqual([{ id: 'timeline-a' }])
    expect(state.auditLedger.value).toEqual([{ event_id: 'audit-a' }])
    expect(state.jobs.value).toEqual([{ id: 'job-a', status: 'queued' }])
  })

  it('lets the latest timeline filter request win over a delayed older filter response', async () => {
    const state = createData()
    const first = deferred<any[]>()
    listTimelineMock
      .mockReturnValueOnce(first.promise)
      .mockResolvedValueOnce([{ id: 'latest-filter' }])

    const firstLoad = state.data.loadTimeline()
    state.timelineEventType.value = 'tool_call_failed'
    await nextTick()
    first.resolve([{ id: 'old-filter' }])
    await firstLoad
    await nextTick()

    expect(state.timeline.value).toEqual([{ id: 'latest-filter' }])
    expect(listTimelineMock).toHaveBeenLastCalledWith({
      projectId: 'project-a', eventType: 'tool_call_failed', runStatus: undefined, limit: 100,
    })
  })
})
