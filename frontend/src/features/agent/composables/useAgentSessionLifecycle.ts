import { ref, type ComputedRef, type Ref } from 'vue'
import { AgentAPI, type AgentMessage, type AgentRun, type AgentSession, type AgentSessionDetail } from '@/api/agent'
import type { AgentRunProjectionStore } from '@/features/agent/stores/agentRunProjection'

export interface AgentSessionRouteIntent {
  sessionId?: string
  runId?: string
  artifactId?: string
}

export interface AgentSessionLifecycleOptions {
  selectedProjectId: Ref<string>
  selectedProjectTitle: ComputedRef<string | undefined>
  runtimeSupported: ComputedRef<boolean>
  routeIntent: ComputedRef<AgentSessionRouteIntent>
  runProjection: AgentRunProjectionStore
  sessionLoading: Ref<boolean>
  sessionError: Ref<string>
  session: Ref<AgentSession | AgentSessionDetail | null>
  sessions: Ref<AgentSession[]>
  selectedSessionId: Ref<string>
  messages: Ref<AgentMessage[]>
  resetRuntime: () => void
  appendMessages: (items: AgentMessage[]) => void
  hydrateSelectedRun: (
    detail: AgentSessionDetail,
    requestedRunId?: string,
    requestedArtifactId?: string,
  ) => Promise<{ runId?: string; artifactId?: string }>
  syncRoute: (overrides: AgentSessionRouteIntent) => void
  addActivity: (label: string, detail: string) => void
}

/**
 * Owns session list/detail selection and its lifecycle fence. The page shell
 * keeps layout and routes; run/artifact hydration stays injected so this module
 * never owns domain-specific view state.
 */
export function useAgentSessionLifecycle(options: AgentSessionLifecycleOptions) {
  let lifecycleGeneration = 0
  const messageHistoryHasMore = ref(false)
  const messageHistoryLoading = ref(false)
  const messageHistoryError = ref('')
  const messageHistoryCursor = ref<number | null>(null)
  const messageHistoryTotal = ref<number | null>(null)
  const runHistoryHasMore = ref(false)
  const runHistoryLoading = ref(false)
  const runHistoryError = ref('')
  const runHistoryCursor = ref<{ createdAt: string; id: string } | null>(null)
  const runHistoryTotal = ref<number | null>(null)

  const isCurrent = (generation: number, projectId: string) =>
    lifecycleGeneration === generation && options.selectedProjectId.value === projectId

  const sortRuns = (items: AgentRun[]) =>
    [...items].sort((left, right) => {
      const createdAtOrder = left.created_at.localeCompare(right.created_at)
      return createdAtOrder || left.id.localeCompare(right.id)
    })

  const clear = () => {
    options.session.value = null
    options.sessions.value = []
    options.selectedSessionId.value = ''
    options.messages.value = []
    messageHistoryHasMore.value = false
    messageHistoryLoading.value = false
    messageHistoryError.value = ''
    messageHistoryCursor.value = null
    messageHistoryTotal.value = null
    runHistoryHasMore.value = false
    runHistoryLoading.value = false
    runHistoryError.value = ''
    runHistoryCursor.value = null
    runHistoryTotal.value = null
  }

  const invalidate = () => {
    lifecycleGeneration += 1
    options.sessionLoading.value = false
  }

  const applyLegacyMessageDetail = (legacy: AgentSessionDetail) => {
    messageHistoryHasMore.value = false
    messageHistoryCursor.value = null
    messageHistoryTotal.value = legacy.messages.length
    messageHistoryError.value = ''
    return { ...legacy, runs: sortRuns(legacy.runs) }
  }

  const hydrateSessionMessages = async (
    detail: AgentSessionDetail,
    generation: number,
    projectId: string,
  ): Promise<AgentSessionDetail | null> => {
    if (typeof AgentAPI.listSessionMessagesPage !== 'function') {
      return applyLegacyMessageDetail(detail)
    }
    try {
      messageHistoryLoading.value = true
      messageHistoryError.value = ''
      const page = await AgentAPI.listSessionMessagesPage(detail.id, { limit: 60 })
      if (!page || !Array.isArray(page.items)) {
        throw new Error('历史消息分页响应格式无效')
      }
      if (!isCurrent(generation, projectId)) return null
      messageHistoryCursor.value = page.next_cursor ?? null
      messageHistoryHasMore.value = Boolean(page.has_more && page.next_cursor)
      messageHistoryTotal.value = page.total ?? page.items.length
      return { ...detail, messages: page.items }
    } catch (error) {
      if (!isCurrent(generation, projectId)) return null
      try {
        const legacy = await AgentAPI.getSession(detail.id)
        if (!legacy || !Array.isArray(legacy.messages)) throw new Error('完整会话响应格式无效')
        if (!isCurrent(generation, projectId)) return null
        return applyLegacyMessageDetail(legacy)
      } catch (fallbackError) {
        messageHistoryError.value = fallbackError instanceof Error
          ? fallbackError.message
          : error instanceof Error
            ? error.message
            : '历史消息读取失败'
        return null
      }
    } finally {
      if (isCurrent(generation, projectId)) messageHistoryLoading.value = false
    }
  }

  const applyLegacyRunDetail = (legacy: AgentSessionDetail) => {
    runHistoryHasMore.value = false
    runHistoryCursor.value = null
    runHistoryTotal.value = legacy.runs.length
    runHistoryError.value = ''
    return legacy
  }

  const hydrateSessionRuns = async (
    detail: AgentSessionDetail,
    generation: number,
    projectId: string,
    requestedRunId?: string,
  ): Promise<AgentSessionDetail | null> => {
    if (typeof AgentAPI.listSessionRunsPage !== 'function' || detail.runs.length > 0) {
      return applyLegacyRunDetail(detail)
    }
    try {
      runHistoryLoading.value = true
      runHistoryError.value = ''
      let page = await AgentAPI.listSessionRunsPage(detail.id, { limit: 50 })
      if (!page || !Array.isArray(page.items)) throw new Error('运行历史分页响应格式无效')
      let items = [...page.items]
      const updatePageState = () => {
        runHistoryCursor.value = page.next_before_created_at && page.next_before_id
          ? { createdAt: page.next_before_created_at, id: page.next_before_id }
          : null
        runHistoryHasMore.value = Boolean(page.has_more && runHistoryCursor.value)
        runHistoryTotal.value = page.total ?? items.length
      }
      if (!isCurrent(generation, projectId)) return null
      updatePageState()
      while (requestedRunId && !items.some((item) => item.id === requestedRunId) && runHistoryHasMore.value && runHistoryCursor.value) {
        const cursor = runHistoryCursor.value
        page = await AgentAPI.listSessionRunsPage(detail.id, {
          limit: 50,
          beforeCreatedAt: cursor.createdAt,
          beforeId: cursor.id,
        })
        if (!page || !Array.isArray(page.items)) throw new Error('运行历史分页响应格式无效')
        if (!isCurrent(generation, projectId)) return null
        const nextCursor = page.next_before_created_at && page.next_before_id
          ? { createdAt: page.next_before_created_at, id: page.next_before_id }
          : null
        if (nextCursor && nextCursor.createdAt === cursor.createdAt && nextCursor.id === cursor.id && !page.items.some((item) => item.id === requestedRunId)) {
          throw new Error('运行历史分页游标未推进')
        }
        const byId = new Map(items.map((item) => [item.id, item]))
        page.items.forEach((item) => byId.set(item.id, item))
        items = [...byId.values()]
        updatePageState()
      }
      if (!isCurrent(generation, projectId)) return null
      return { ...detail, runs: sortRuns(items) }
    } catch (error) {
      if (!isCurrent(generation, projectId)) return null
      try {
        const legacy = await AgentAPI.getSession(detail.id)
        if (!legacy || !Array.isArray(legacy.runs)) throw new Error('完整会话运行响应格式无效')
        if (!isCurrent(generation, projectId)) return null
        return applyLegacyRunDetail(legacy)
      } catch (fallbackError) {
        runHistoryError.value = fallbackError instanceof Error
          ? fallbackError.message
          : error instanceof Error
            ? error.message
            : '运行历史读取失败'
        return null
      }
    } finally {
      if (isCurrent(generation, projectId)) runHistoryLoading.value = false
    }
  }

  const loadOlderRuns = async () => {
    const projectId = options.selectedProjectId.value
    const sessionId = options.selectedSessionId.value
    const cursor = runHistoryCursor.value
    if (typeof AgentAPI.listSessionRunsPage !== 'function' || !projectId || !sessionId || !cursor || !runHistoryHasMore.value || runHistoryLoading.value) return
    const generation = lifecycleGeneration
    runHistoryLoading.value = true
    runHistoryError.value = ''
    try {
      const page = await AgentAPI.listSessionRunsPage(sessionId, {
        limit: 50,
        beforeCreatedAt: cursor.createdAt,
        beforeId: cursor.id,
      })
      if (!isCurrent(generation, projectId) || options.selectedSessionId.value !== sessionId) return
      const byId = new Map(options.runProjection.runs.value.map((item) => [item.id, item]))
      page.items.forEach((item) => byId.set(item.id, item))
      const merged = sortRuns([...byId.values()])
      options.runProjection.replaceRuns(merged)
      if (options.session.value && 'runs' in options.session.value) {
        options.session.value = { ...options.session.value, runs: merged }
      }
      runHistoryCursor.value = page.next_before_created_at && page.next_before_id
        ? { createdAt: page.next_before_created_at, id: page.next_before_id }
        : null
      runHistoryHasMore.value = Boolean(page.has_more && runHistoryCursor.value)
      runHistoryTotal.value = page.total ?? runHistoryTotal.value
    } catch (error) {
      if (isCurrent(generation, projectId) && options.selectedSessionId.value === sessionId) {
        runHistoryError.value = error instanceof Error ? error.message : '更早运行读取失败'
      }
    } finally {
      if (isCurrent(generation, projectId) && options.selectedSessionId.value === sessionId) runHistoryLoading.value = false
    }
  }

  const loadOlderMessages = async () => {
    const projectId = options.selectedProjectId.value
    const sessionId = options.selectedSessionId.value
    const cursor = messageHistoryCursor.value
    if (typeof AgentAPI.listSessionMessagesPage !== 'function' || !projectId || !sessionId || cursor === null || !messageHistoryHasMore.value || messageHistoryLoading.value) return
    const generation = lifecycleGeneration
    messageHistoryLoading.value = true
    messageHistoryError.value = ''
    try {
      const page = await AgentAPI.listSessionMessagesPage(sessionId, { limit: 60, beforeSequence: cursor })
      if (!isCurrent(generation, projectId) || options.selectedSessionId.value !== sessionId) return
      options.appendMessages(page.items)
      messageHistoryCursor.value = page.next_cursor ?? null
      messageHistoryHasMore.value = Boolean(page.has_more && page.next_cursor)
      messageHistoryTotal.value = page.total ?? messageHistoryTotal.value
    } catch (error) {
      if (isCurrent(generation, projectId) && options.selectedSessionId.value === sessionId) {
        messageHistoryError.value = error instanceof Error ? error.message : '更早消息读取失败'
      }
    } finally {
      if (isCurrent(generation, projectId) && options.selectedSessionId.value === sessionId) messageHistoryLoading.value = false
    }
  }

  const applyDetail = async (
    detail: AgentSessionDetail,
    generation: number,
    projectId: string,
    requestedRunId?: string,
    requestedArtifactId?: string,
  ) => {
    if (!isCurrent(generation, projectId)) return null
    options.session.value = detail
    options.selectedSessionId.value = detail.id
    options.appendMessages(detail.messages || [])
    options.messages.value = detail.messages || []
    options.runProjection.replaceRuns(detail.runs || [], requestedRunId)
    const resolved = await options.hydrateSelectedRun(detail, requestedRunId, requestedArtifactId)
    if (!isCurrent(generation, projectId)) return null
    options.syncRoute({
      sessionId: detail.id,
      runId: resolved.runId,
      artifactId: resolved.artifactId,
    })
    return resolved
  }

  const getSessionDetail = (sessionId: string) => {
    const optionsForDetail = {
      ...(typeof AgentAPI.listSessionMessagesPage === 'function' ? { includeMessages: false } : {}),
      ...(typeof AgentAPI.listSessionRunsPage === 'function' ? { includeRuns: false } : {}),
    }
    return Object.keys(optionsForDetail).length
      ? AgentAPI.getSession(sessionId, optionsForDetail)
      : AgentAPI.getSession(sessionId)
  }

  const restoreSession = async () => {
    const projectId = options.selectedProjectId.value
    const generation = ++lifecycleGeneration
    clear()
    options.resetRuntime()
    if (!projectId || !options.runtimeSupported.value) return
    options.sessionLoading.value = true
    options.sessionError.value = ''
    try {
      const listed = await AgentAPI.listSessions(projectId)
      if (!isCurrent(generation, projectId)) return
      options.sessions.value = listed
      const requestedSessionId = options.routeIntent.value.sessionId
      const requestedSession = requestedSessionId
        ? listed.find((item) => item.id === requestedSessionId)
        : undefined
      const existing = requestedSession || listed.find((item) => item.status !== 'archived') || listed[0]
      if (requestedSessionId && !requestedSession) {
        options.addActivity('会话深链不可用', '请求的会话不属于当前项目，已安全降级为可访问会话。')
      }
      const detail = existing
        ? await getSessionDetail(existing.id)
        : await AgentAPI.createSession({
            project_id: projectId,
            title: options.selectedProjectTitle.value
              ? `${options.selectedProjectTitle.value} · Agent`
              : undefined,
          }).then((created) => {
            options.sessions.value = [created]
            return { ...created, messages: [], runs: [] }
          })
      if (!isCurrent(generation, projectId)) return
      const requestedRunId = options.routeIntent.value.runId
      const requestedArtifactId = options.routeIntent.value.artifactId
      const hydratedMessages = await hydrateSessionMessages(detail, generation, projectId)
      if (!hydratedMessages) return
      const hydratedDetail = await hydrateSessionRuns(hydratedMessages, generation, projectId, requestedRunId)
      if (!hydratedDetail) return
      const resolved = await applyDetail(hydratedDetail, generation, projectId, requestedRunId, requestedArtifactId)
      if (!resolved || !isCurrent(generation, projectId)) return
      options.addActivity('会话已恢复', `${messageHistoryTotal.value ?? hydratedDetail.messages.length} 条历史消息，${hydratedDetail.runs.length} 次运行记录。`)
    } catch (error) {
      if (!isCurrent(generation, projectId)) return
      options.sessionError.value = error instanceof Error ? error.message : '会话不可用'
      options.addActivity('会话恢复失败', options.sessionError.value)
    } finally {
      if (isCurrent(generation, projectId)) options.sessionLoading.value = false
    }
  }

  const loadSelectedSession = async () => {
    const projectId = options.selectedProjectId.value
    const sessionId = options.selectedSessionId.value
    if (!projectId || !sessionId || !options.runtimeSupported.value) return
    const generation = ++lifecycleGeneration
    options.sessionLoading.value = true
    options.sessionError.value = ''
    try {
      const detail = await getSessionDetail(sessionId)
      if (!isCurrent(generation, projectId) || options.selectedSessionId.value !== sessionId) return
      const hydratedMessages = await hydrateSessionMessages(detail, generation, projectId)
      if (!hydratedMessages) return
      const hydratedDetail = await hydrateSessionRuns(hydratedMessages, generation, projectId)
      if (!hydratedDetail) return
      options.runProjection.reset()
      await applyDetail(hydratedDetail, generation, projectId)
    } catch (error) {
      if (!isCurrent(generation, projectId) || options.selectedSessionId.value !== sessionId) return
      options.addActivity('会话切换失败', error instanceof Error ? error.message : '无法切换会话')
    } finally {
      if (isCurrent(generation, projectId) && options.selectedSessionId.value === sessionId) {
        options.sessionLoading.value = false
      }
    }
  }

  const createNewSession = async () => {
    const projectId = options.selectedProjectId.value
    if (!projectId || typeof AgentAPI.createSession !== 'function') return
    try {
      const created = await AgentAPI.createSession({
        project_id: projectId,
        title: options.selectedProjectTitle.value ? `${options.selectedProjectTitle.value} · Agent` : undefined,
      })
      if (projectId !== options.selectedProjectId.value) return
      options.sessions.value = [created, ...options.sessions.value]
      options.selectedSessionId.value = created.id
      await loadSelectedSession()
      options.addActivity('新会话已创建', created.title || created.id)
    } catch (error) {
      options.addActivity('新会话创建失败', error instanceof Error ? error.message : '创建失败')
    }
  }

  const archiveCurrentSession = async () => {
    const current = options.session.value
    if (!current || typeof AgentAPI.archiveSession !== 'function') return
    try {
      const archived = await AgentAPI.archiveSession(current.id)
      if (options.session.value?.id !== current.id) return
      options.sessions.value = options.sessions.value.map((item) => (item.id === archived.id ? archived : item))
      options.session.value = { ...options.session.value, ...archived }
      options.addActivity('会话已归档', archived.title || archived.id)
    } catch (error) {
      options.addActivity('会话归档失败', error instanceof Error ? error.message : '归档失败')
    }
  }

  return {
    restoreSession,
    loadSelectedSession,
    createNewSession,
    archiveCurrentSession,
    loadOlderMessages,
    loadOlderRuns,
    runHistoryHasMore,
    runHistoryLoading,
    runHistoryError,
    runHistoryTotal,
    messageHistoryHasMore,
    messageHistoryLoading,
    messageHistoryError,
    messageHistoryTotal,
    invalidate,
  }
}
