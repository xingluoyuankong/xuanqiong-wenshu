import { computed, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const { listSessionsMock, getSessionMock } = vi.hoisted(() => ({
  listSessionsMock: vi.fn(),
  getSessionMock: vi.fn(),
}))

vi.mock('@/api/agent', () => ({
  AgentAPI: {
    listSessions: listSessionsMock,
    getSession: getSessionMock,
    createSession: vi.fn(),
    archiveSession: vi.fn(),
  },
}))

import { useAgentSessionLifecycle } from './useAgentSessionLifecycle'
import { useAgentRunProjection } from '@/features/agent/stores/agentRunProjection'

const detail = (id: string, projectId = 'project') => ({
  id,
  user_id: 1,
  project_id: projectId,
  title: id,
  status: 'active',
  created_at: '2026-08-30T00:00:00Z',
  updated_at: '2026-08-30T00:00:00Z',
  messages: [],
  runs: [],
})

const deferred = <T,>() => {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((next) => { resolve = next })
  return { promise, resolve }
}

describe('useAgentSessionLifecycle', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  const createLifecycle = () => {
    const selectedProjectId = ref('project')
    const sessionLoading = ref(false)
    const sessionError = ref('')
    const session = ref<any>(null)
    const sessions = ref<any[]>([])
    const selectedSessionId = ref('')
    const messages = ref<any[]>([])
    const runProjection = useAgentRunProjection()
    const hydrateSelectedRun = vi.fn().mockResolvedValue({})
    const syncRoute = vi.fn()
    const addActivity = vi.fn()
    const lifecycle = useAgentSessionLifecycle({
      selectedProjectId,
      selectedProjectTitle: computed(() => '项目'),
      runtimeSupported: computed(() => true),
      routeIntent: computed(() => ({})),
      runProjection,
      sessionLoading,
      sessionError,
      session,
      sessions,
      selectedSessionId,
      messages,
      resetRuntime: vi.fn(),
      appendMessages: (items) => { messages.value = items },
      hydrateSelectedRun,
      syncRoute,
      addActivity,
    })
    return {
      lifecycle, selectedProjectId, sessionLoading, session, sessions,
      selectedSessionId, messages, hydrateSelectedRun, syncRoute, addActivity,
    }
  }

  it('drops a stale restore result after the project changes', async () => {
    const state = createLifecycle()
    const pending = deferred<any[]>()
    listSessionsMock.mockReturnValueOnce(pending.promise)

    const restoring = state.lifecycle.restoreSession()
    state.selectedProjectId.value = 'other-project'
    pending.resolve([detail('old-session')])
    await restoring

    expect(state.session.value).toBeNull()
    expect(state.sessions.value).toEqual([])
    expect(state.hydrateSelectedRun).not.toHaveBeenCalled()
    expect(state.syncRoute).not.toHaveBeenCalled()
  })

  it('lets the latest manual session selection win over an older delayed detail request', async () => {
    const state = createLifecycle()
    const first = deferred<any>()
    getSessionMock
      .mockReturnValueOnce(first.promise)
      .mockResolvedValueOnce(detail('session-2'))

    state.selectedSessionId.value = 'session-1'
    const firstLoad = state.lifecycle.loadSelectedSession()
    state.selectedSessionId.value = 'session-2'
    const secondLoad = state.lifecycle.loadSelectedSession()
    first.resolve(detail('session-1'))
    await Promise.all([firstLoad, secondLoad])

    expect(state.session.value?.id).toBe('session-2')
    expect(state.hydrateSelectedRun).toHaveBeenCalledTimes(1)
    expect(state.syncRoute).toHaveBeenCalledWith({
      sessionId: 'session-2',
      runId: undefined,
      artifactId: undefined,
    })
    expect(state.sessionLoading.value).toBe(false)
  })
})
