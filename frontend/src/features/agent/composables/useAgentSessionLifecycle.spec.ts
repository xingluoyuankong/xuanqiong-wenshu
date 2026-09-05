import { computed, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const { listSessionsMock, getSessionMock, listSessionMessagesPageMock, listSessionRunsPageMock } = vi.hoisted(() => ({
  listSessionsMock: vi.fn(),
  getSessionMock: vi.fn(),
  listSessionMessagesPageMock: vi.fn(),
  listSessionRunsPageMock: vi.fn(),
}))

vi.mock('@/api/agent', () => ({
  AgentAPI: {
    listSessions: listSessionsMock,
    getSession: getSessionMock,
    listSessionMessagesPage: listSessionMessagesPageMock,
    listSessionRunsPage: listSessionRunsPageMock,
    createSession: vi.fn(),
    archiveSession: vi.fn(),
  },
}))

import { AgentAPI } from '@/api/agent'
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
    listSessionMessagesPageMock.mockReset()
    listSessionMessagesPageMock.mockResolvedValue({ session_id: '', items: [], total: 0, limit: 60, next_cursor: null, has_more: false })
    listSessionRunsPageMock.mockReset()
    listSessionRunsPageMock.mockResolvedValue({ session_id: '', items: [], total: 0, limit: 50, next_before_created_at: null, next_before_id: null, has_more: false })
  })

  const createLifecycle = (route: Record<string, string> = {}) => {
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
      routeIntent: computed(() => route),
      runProjection,
      sessionLoading,
      sessionError,
      session,
      sessions,
      selectedSessionId,
      messages,
      resetRuntime: vi.fn(),
      appendMessages: (items) => {
        const bySequence = new Map(messages.value.map((item) => [item.sequence, item]))
        items.forEach((item) => bySequence.set(item.sequence, item))
        messages.value = [...bySequence.values()].sort((left, right) => left.sequence - right.sequence)
      },
      hydrateSelectedRun,
      syncRoute,
      addActivity,
    })
    return {
      lifecycle, selectedProjectId, sessionLoading, session, sessions, runProjection,
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

  it('loads the newest message page first and older pages through the returned cursor', async () => {
    const state = createLifecycle()
    const sessionItem = { id: 'paged-session', user_id: 1, project_id: 'project', title: 'paged', status: 'active', created_at: 'now', updated_at: 'now' }
    listSessionsMock.mockResolvedValue([sessionItem])
    getSessionMock.mockResolvedValue({ ...sessionItem, messages: [], runs: [] })
    const newest = Array.from({ length: 2 }, (_, index) => ({
      id: `message-${index + 3}`, session_id: sessionItem.id, user_id: 1, role: 'assistant', content: `新 ${index + 3}`, sequence: index + 3, created_at: 'now',
    }))
    const older = [{ id: 'message-1', session_id: sessionItem.id, user_id: 1, role: 'user', content: '旧 1', sequence: 1, created_at: 'now' }]
    listSessionMessagesPageMock
      .mockResolvedValueOnce({ session_id: sessionItem.id, items: newest, total: 3, limit: 60, next_cursor: 3, has_more: true })
      .mockResolvedValueOnce({ session_id: sessionItem.id, items: older, total: 3, limit: 60, next_cursor: null, has_more: false })

    await state.lifecycle.restoreSession()

    expect(getSessionMock).toHaveBeenCalledWith(sessionItem.id, { includeMessages: false, includeRuns: false })
    expect(listSessionMessagesPageMock).toHaveBeenCalledWith(sessionItem.id, { limit: 60 })
    expect(state.messages.value.map((item) => item.sequence)).toEqual([3, 4])
    expect(state.lifecycle.messageHistoryHasMore.value).toBe(true)
    await state.lifecycle.loadOlderMessages()

    expect(listSessionMessagesPageMock).toHaveBeenLastCalledWith(sessionItem.id, { limit: 60, beforeSequence: 3 })
    expect(state.messages.value.map((item) => item.sequence)).toEqual([1, 3, 4])
    expect(state.lifecycle.messageHistoryHasMore.value).toBe(false)
  })

  it('loads the newest run page and older run pages without reverting to the unbounded detail payload', async () => {
    const state = createLifecycle()
    const sessionItem = { id: 'run-paged-session', user_id: 1, project_id: 'project', title: 'run-paged', status: 'active', created_at: 'now', updated_at: 'now' }
    const run = (id: string, createdAt: string) => ({ id, session_id: sessionItem.id, user_id: 1, project_id: 'project', status: 'succeeded', progress: 100, created_at: createdAt, updated_at: createdAt })
    listSessionsMock.mockResolvedValue([sessionItem])
    getSessionMock.mockResolvedValue({ ...sessionItem, messages: [], runs: [] })
    listSessionMessagesPageMock.mockResolvedValue({ session_id: sessionItem.id, items: [], total: 0, limit: 60, next_cursor: null, has_more: false })
    listSessionRunsPageMock
      .mockResolvedValueOnce({ session_id: sessionItem.id, items: [run('run-2', '2026-09-05T00:00:02Z'), run('run-3', '2026-09-05T00:00:03Z')], total: 3, limit: 50, next_before_created_at: '2026-09-05T00:00:02Z', next_before_id: 'run-2', has_more: true })
      .mockResolvedValueOnce({ session_id: sessionItem.id, items: [run('run-1', '2026-09-05T00:00:01Z')], total: 3, limit: 50, next_before_created_at: null, next_before_id: null, has_more: false })

    await state.lifecycle.restoreSession()

    expect(getSessionMock).toHaveBeenCalledWith(sessionItem.id, { includeMessages: false, includeRuns: false })
    expect(listSessionRunsPageMock).toHaveBeenCalledWith(sessionItem.id, { limit: 50 })
    expect(state.session.value?.runs.map((item: any) => item.id)).toEqual(['run-2', 'run-3'])
    expect(state.lifecycle.runHistoryHasMore.value).toBe(true)
    await state.lifecycle.loadOlderRuns()
    expect(listSessionRunsPageMock).toHaveBeenLastCalledWith(sessionItem.id, { limit: 50, beforeCreatedAt: '2026-09-05T00:00:02Z', beforeId: 'run-2' })
    expect(state.session.value?.runs.map((item: any) => item.id)).toEqual(['run-1', 'run-2', 'run-3'])
    expect(state.lifecycle.runHistoryHasMore.value).toBe(false)
  })

  it('drops a stale initial run page after the project changes', async () => {
    const state = createLifecycle()
    const sessionItem = { id: 'stale-run-session', user_id: 1, project_id: 'project', title: 'stale-run', status: 'active', created_at: 'now', updated_at: 'now' }
    const pendingRuns = deferred<any>()
    listSessionsMock.mockResolvedValue([sessionItem])
    getSessionMock.mockResolvedValue({ ...sessionItem, messages: [], runs: [] })
    listSessionMessagesPageMock.mockResolvedValue({ session_id: sessionItem.id, items: [], total: 0, limit: 60, next_cursor: null, has_more: false })
    listSessionRunsPageMock.mockReturnValueOnce(pendingRuns.promise)

    const restoring = state.lifecycle.restoreSession()
    state.selectedProjectId.value = 'other-project'
    pendingRuns.resolve({
      session_id: sessionItem.id,
      items: [{ id: 'stale-run', session_id: sessionItem.id, user_id: 1, project_id: 'project', status: 'completed', progress: 100, created_at: '2026-09-05T00:00:01Z', updated_at: '2026-09-05T00:00:01Z' }],
      total: 1,
      limit: 50,
      next_before_created_at: null,
      next_before_id: null,
      has_more: false,
    })
    await restoring

    expect(state.session.value).toBeNull()
    expect(state.lifecycle.runHistoryTotal.value).toBeNull()
    expect(state.lifecycle.runHistoryHasMore.value).toBe(false)
    expect(state.hydrateSelectedRun).not.toHaveBeenCalled()
  })

  it('falls back to the full session detail when the first message page fails', async () => {
    const state = createLifecycle()
    const sessionItem = { id: 'fallback-session', user_id: 1, project_id: 'project', title: 'fallback', status: 'active', created_at: 'now', updated_at: 'now' }
    const fullDetail = {
      ...sessionItem,
      messages: [{ id: 'legacy-message', session_id: sessionItem.id, user_id: 1, role: 'assistant', content: '旧接口正文', sequence: 1, created_at: 'now' }],
      runs: [],
    }
    listSessionsMock.mockResolvedValue([sessionItem])
    getSessionMock.mockResolvedValueOnce({ ...sessionItem, messages: [], runs: [] }).mockResolvedValueOnce(fullDetail)
    listSessionMessagesPageMock.mockRejectedValueOnce(new Error('分页接口暂时不可用'))

    await state.lifecycle.restoreSession()

    expect(getSessionMock).toHaveBeenNthCalledWith(1, sessionItem.id, { includeMessages: false, includeRuns: false })
    expect(getSessionMock).toHaveBeenNthCalledWith(2, sessionItem.id)
    expect(state.messages.value.map((item) => item.content)).toEqual(['旧接口正文'])
    expect(state.lifecycle.messageHistoryHasMore.value).toBe(false)
    expect(state.lifecycle.messageHistoryError.value).toBe('')
  })

  it('分页响应格式异常时也回退到完整会话，而不是丢失首屏消息', async () => {
    const state = createLifecycle()
    const sessionItem = { id: 'malformed-page-session', user_id: 1, project_id: 'project', title: 'malformed', status: 'active', created_at: 'now', updated_at: 'now' }
    const fullDetail = {
      ...sessionItem,
      messages: [{ id: 'malformed-fallback-message', session_id: sessionItem.id, user_id: 1, role: 'user', content: '完整回退正文', sequence: 1, created_at: 'now' }],
      runs: [],
    }
    listSessionsMock.mockResolvedValue([sessionItem])
    getSessionMock.mockResolvedValueOnce({ ...sessionItem, messages: [], runs: [] }).mockResolvedValueOnce(fullDetail)
    listSessionMessagesPageMock.mockResolvedValueOnce(undefined)

    await state.lifecycle.restoreSession()

    expect(getSessionMock).toHaveBeenNthCalledWith(2, sessionItem.id)
    expect(state.messages.value.map((item) => item.content)).toEqual(['完整回退正文'])
    expect(state.lifecycle.messageHistoryError.value).toBe('')
  })

  it('resolves a deep-linked run on an older page and preserves the artifact intent', async () => {
    const state = createLifecycle({ sessionId: 'deep-link-session', runId: 'run-1', artifactId: 'artifact-7' })
    const sessionItem = { id: 'deep-link-session', user_id: 1, project_id: 'project', title: 'deep link', status: 'active', created_at: 'now', updated_at: 'now' }
    const run = (id: string, createdAt: string) => ({
      id, session_id: sessionItem.id, user_id: 1, project_id: 'project', status: 'succeeded', progress: 100,
      created_at: createdAt, updated_at: createdAt,
    })
    listSessionsMock.mockResolvedValue([sessionItem])
    getSessionMock.mockResolvedValue({ ...sessionItem, messages: [], runs: [] })
    listSessionMessagesPageMock.mockResolvedValue({ session_id: sessionItem.id, items: [], total: 0, limit: 60, next_cursor: null, has_more: false })
    listSessionRunsPageMock
      .mockResolvedValueOnce({
        session_id: sessionItem.id,
        items: [run('run-3', '2026-09-05T00:00:03Z'), run('run-2', '2026-09-05T00:00:02Z')],
        total: 3,
        limit: 50,
        next_before_created_at: '2026-09-05T00:00:02Z',
        next_before_id: 'run-2',
        has_more: true,
      })
      .mockResolvedValueOnce({
        session_id: sessionItem.id,
        items: [run('run-1', '2026-09-05T00:00:01Z')],
        total: 3,
        limit: 50,
        next_before_created_at: null,
        next_before_id: null,
        has_more: false,
      })

    await state.lifecycle.restoreSession()

    expect(listSessionRunsPageMock).toHaveBeenNthCalledWith(1, sessionItem.id, { limit: 50 })
    expect(listSessionRunsPageMock).toHaveBeenNthCalledWith(2, sessionItem.id, {
      limit: 50,
      beforeCreatedAt: '2026-09-05T00:00:02Z',
      beforeId: 'run-2',
    })
    expect(state.session.value?.runs.map((item: any) => item.id)).toEqual(['run-1', 'run-2', 'run-3'])
    expect(state.lifecycle.runHistoryHasMore.value).toBe(false)
    expect(state.hydrateSelectedRun).toHaveBeenCalledWith(
      expect.objectContaining({ runs: expect.arrayContaining([expect.objectContaining({ id: 'run-1' })]) }),
      'run-1',
      'artifact-7',
    )
    expect(state.runProjection.selectedRunId.value).toBe('run-1')
  })

  it('keeps the current message history and exposes an error when an older page is malformed', async () => {
    const state = createLifecycle()
    const sessionItem = { id: 'malformed-older-message-session', user_id: 1, project_id: 'project', title: 'messages', status: 'active', created_at: 'now', updated_at: 'now' }
    const newest = { id: 'message-2', session_id: sessionItem.id, user_id: 1, role: 'assistant', content: '最新', sequence: 2, created_at: 'now' }
    listSessionsMock.mockResolvedValue([sessionItem])
    getSessionMock.mockResolvedValue({ ...sessionItem, messages: [], runs: [] })
    listSessionMessagesPageMock
      .mockResolvedValueOnce({ session_id: sessionItem.id, items: [newest], total: 2, limit: 60, next_cursor: 2, has_more: true })
      .mockResolvedValueOnce({ session_id: sessionItem.id, items: 'not-an-array', total: 2, limit: 60, next_cursor: 1, has_more: true })

    await state.lifecycle.restoreSession()
    await state.lifecycle.loadOlderMessages()

    expect(state.messages.value.map((item) => item.sequence)).toEqual([2])
    expect(state.lifecycle.messageHistoryHasMore.value).toBe(true)
    expect(state.lifecycle.messageHistoryError.value).toBe('items.forEach is not a function')
    expect(state.lifecycle.messageHistoryLoading.value).toBe(false)
  })

  it('keeps the current run history and exposes an error when an older run page is malformed', async () => {
    const state = createLifecycle()
    const sessionItem = { id: 'malformed-older-run-session', user_id: 1, project_id: 'project', title: 'runs', status: 'active', created_at: 'now', updated_at: 'now' }
    const run = { id: 'run-2', session_id: sessionItem.id, user_id: 1, project_id: 'project', status: 'succeeded', progress: 100, created_at: '2026-09-05T00:00:02Z', updated_at: '2026-09-05T00:00:02Z' }
    listSessionsMock.mockResolvedValue([sessionItem])
    getSessionMock.mockResolvedValue({ ...sessionItem, messages: [], runs: [] })
    listSessionMessagesPageMock.mockResolvedValue({ session_id: sessionItem.id, items: [], total: 0, limit: 60, next_cursor: null, has_more: false })
    listSessionRunsPageMock
      .mockResolvedValueOnce({ session_id: sessionItem.id, items: [run], total: 2, limit: 50, next_before_created_at: run.created_at, next_before_id: run.id, has_more: true })
      .mockResolvedValueOnce({ session_id: sessionItem.id, items: undefined, total: 2, limit: 50, next_before_created_at: null, next_before_id: null, has_more: false })

    await state.lifecycle.restoreSession()
    await state.lifecycle.loadOlderRuns()

    expect(state.session.value?.runs.map((item: any) => item.id)).toEqual(['run-2'])
    expect(state.lifecycle.runHistoryHasMore.value).toBe(true)
    expect(state.lifecycle.runHistoryError.value).toBe('Cannot read properties of undefined (reading \'forEach\')')
    expect(state.lifecycle.runHistoryLoading.value).toBe(false)
  })

  it('falls back to the full session detail when the initial run page is malformed', async () => {
    const state = createLifecycle()
    const sessionItem = { id: 'run-fallback-session', user_id: 1, project_id: 'project', title: 'run fallback', status: 'active', created_at: 'now', updated_at: 'now' }
    const fullDetail = {
      ...sessionItem,
      messages: [{ id: 'fallback-message', session_id: sessionItem.id, user_id: 1, role: 'assistant', content: '完整消息', sequence: 1, created_at: 'now' }],
      runs: [{ id: 'fallback-run', session_id: sessionItem.id, user_id: 1, project_id: 'project', status: 'succeeded', progress: 100, created_at: '2026-09-05T00:00:01Z', updated_at: '2026-09-05T00:00:01Z' }],
    }
    listSessionsMock.mockResolvedValue([sessionItem])
    getSessionMock.mockResolvedValueOnce({ ...sessionItem, messages: [], runs: [] }).mockResolvedValueOnce(fullDetail)
    listSessionMessagesPageMock.mockResolvedValue({ session_id: sessionItem.id, items: [], total: 0, limit: 60, next_cursor: null, has_more: false })
    listSessionRunsPageMock.mockResolvedValueOnce({ session_id: sessionItem.id, items: 'malformed', total: 1, limit: 50, next_before_created_at: null, next_before_id: null, has_more: false })

    await state.lifecycle.restoreSession()

    expect(getSessionMock).toHaveBeenNthCalledWith(2, sessionItem.id)
    expect(state.messages.value.map((item) => item.content)).toEqual(['完整消息'])
    expect(state.session.value?.runs.map((item: any) => item.id)).toEqual(['fallback-run'])
    expect(state.lifecycle.runHistoryError.value).toBe('')
  })

  it('supports a legacy client with neither session history pager and preserves the old detail contract', async () => {
    const state = createLifecycle()
    const sessionItem = { id: 'legacy-client-session', user_id: 1, project_id: 'project', title: 'legacy', status: 'active', created_at: 'now', updated_at: 'now' }
    const legacyDetail = {
      ...sessionItem,
      messages: [{ id: 'legacy-message', session_id: sessionItem.id, user_id: 1, role: 'user', content: '旧客户端消息', sequence: 1, created_at: 'now' }],
      runs: [{ id: 'legacy-run', session_id: sessionItem.id, user_id: 1, project_id: 'project', status: 'succeeded', progress: 100, created_at: '2026-09-05T00:00:01Z', updated_at: '2026-09-05T00:00:01Z' }],
    }
    const originalMessagePager = AgentAPI.listSessionMessagesPage
    const originalRunPager = AgentAPI.listSessionRunsPage
    ;(AgentAPI as any).listSessionMessagesPage = undefined
    ;(AgentAPI as any).listSessionRunsPage = undefined
    try {
      listSessionsMock.mockResolvedValue([sessionItem])
      getSessionMock.mockResolvedValue(legacyDetail)

      await state.lifecycle.restoreSession()

      expect(getSessionMock).toHaveBeenCalledTimes(1)
      expect(getSessionMock).toHaveBeenCalledWith(sessionItem.id)
      expect(listSessionMessagesPageMock).not.toHaveBeenCalled()
      expect(listSessionRunsPageMock).not.toHaveBeenCalled()
      expect(state.messages.value.map((item) => item.content)).toEqual(['旧客户端消息'])
      expect(state.session.value?.runs.map((item: any) => item.id)).toEqual(['legacy-run'])
      expect(state.lifecycle.messageHistoryTotal.value).toBe(1)
      expect(state.lifecycle.runHistoryTotal.value).toBe(1)
    } finally {
      ;(AgentAPI as any).listSessionMessagesPage = originalMessagePager
      ;(AgentAPI as any).listSessionRunsPage = originalRunPager
    }
  })

  it('ignores a stale paged response after switching sessions', async () => {
    const state = createLifecycle()
    const firstSession = { id: 'session-1', user_id: 1, project_id: 'project', title: 'one', status: 'active', created_at: 'now', updated_at: 'now' }
    const secondSession = { id: 'session-2', user_id: 1, project_id: 'project', title: 'two', status: 'active', created_at: 'now', updated_at: 'now' }
    const pendingFirstPage = deferred<any>()
    listSessionsMock.mockResolvedValue([])
    getSessionMock.mockResolvedValueOnce({ ...firstSession, messages: [], runs: [] }).mockResolvedValueOnce({ ...secondSession, messages: [], runs: [] })
    listSessionMessagesPageMock
      .mockReturnValueOnce(pendingFirstPage.promise)
      .mockResolvedValueOnce({ session_id: secondSession.id, items: [{ id: 'session-2-message', session_id: secondSession.id, user_id: 1, role: 'assistant', content: '第二会话', sequence: 1, created_at: 'now' }], total: 1, limit: 60, next_cursor: null, has_more: false })
    listSessionRunsPageMock.mockResolvedValue({ session_id: secondSession.id, items: [], total: 0, limit: 50, next_before_created_at: null, next_before_id: null, has_more: false })

    state.selectedSessionId.value = firstSession.id
    const firstLoad = state.lifecycle.loadSelectedSession()
    await Promise.resolve()
    state.selectedSessionId.value = secondSession.id
    const secondLoad = state.lifecycle.loadSelectedSession()
    pendingFirstPage.resolve({ session_id: firstSession.id, items: [{ id: 'stale-message', session_id: firstSession.id, user_id: 1, role: 'assistant', content: '旧会话', sequence: 1, created_at: 'now' }], total: 1, limit: 60, next_cursor: null, has_more: false })
    await Promise.all([firstLoad, secondLoad])

    expect(state.session.value?.id).toBe(secondSession.id)
    expect(state.messages.value.map((item) => item.content)).toEqual(['第二会话'])
    expect(state.hydrateSelectedRun).toHaveBeenCalledTimes(1)
    expect(state.sessionLoading.value).toBe(false)
  })

  it('coalesces duplicate clicks on the older-message control while a page is in flight', async () => {
    const state = createLifecycle()
    const sessionItem = { id: 'duplicate-message-session', user_id: 1, project_id: 'project', title: 'duplicate', status: 'active', created_at: 'now', updated_at: 'now' }
    const pendingOlderPage = deferred<any>()
    listSessionsMock.mockResolvedValue([sessionItem])
    getSessionMock.mockResolvedValue({ ...sessionItem, messages: [], runs: [] })
    listSessionMessagesPageMock
      .mockResolvedValueOnce({ session_id: sessionItem.id, items: [{ id: 'message-2', session_id: sessionItem.id, user_id: 1, role: 'assistant', content: '新', sequence: 2, created_at: 'now' }], total: 2, limit: 60, next_cursor: 2, has_more: true })
      .mockReturnValueOnce(pendingOlderPage.promise)

    await state.lifecycle.restoreSession()
    const firstLoad = state.lifecycle.loadOlderMessages()
    const duplicateLoad = state.lifecycle.loadOlderMessages()
    expect(listSessionMessagesPageMock).toHaveBeenCalledTimes(2)
    expect(state.lifecycle.messageHistoryLoading.value).toBe(true)

    pendingOlderPage.resolve({ session_id: sessionItem.id, items: [{ id: 'message-1', session_id: sessionItem.id, user_id: 1, role: 'user', content: '旧', sequence: 1, created_at: 'now' }], total: 2, limit: 60, next_cursor: null, has_more: false })
    await Promise.all([firstLoad, duplicateLoad])

    expect(state.messages.value.map((item) => item.sequence)).toEqual([1, 2])
    expect(state.lifecycle.messageHistoryLoading.value).toBe(false)
    expect(state.lifecycle.messageHistoryError.value).toBe('')
  })

  it('lets the latest duplicate click for the same session win over an older delayed load', async () => {
    const state = createLifecycle()
    const pendingFirstDetail = deferred<any>()
    getSessionMock.mockReturnValueOnce(pendingFirstDetail.promise).mockResolvedValueOnce(detail('same-session'))

    state.selectedSessionId.value = 'same-session'
    const firstLoad = state.lifecycle.loadSelectedSession()
    const duplicateLoad = state.lifecycle.loadSelectedSession()
    pendingFirstDetail.resolve(detail('same-session'))
    await Promise.all([firstLoad, duplicateLoad])

    expect(getSessionMock).toHaveBeenCalledTimes(2)
    expect(getSessionMock).toHaveBeenNthCalledWith(1, 'same-session', { includeMessages: false, includeRuns: false })
    expect(getSessionMock).toHaveBeenNthCalledWith(2, 'same-session', { includeMessages: false, includeRuns: false })
    expect(state.session.value?.id).toBe('same-session')
    expect(state.hydrateSelectedRun).toHaveBeenCalledTimes(1)
    expect(state.syncRoute).toHaveBeenCalledTimes(1)
    expect(state.sessionLoading.value).toBe(false)
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
