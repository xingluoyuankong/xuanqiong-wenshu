import type { ComputedRef, Ref } from 'vue'
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

  const isCurrent = (generation: number, projectId: string) =>
    lifecycleGeneration === generation && options.selectedProjectId.value === projectId

  const clear = () => {
    options.session.value = null
    options.sessions.value = []
    options.selectedSessionId.value = ''
    options.messages.value = []
  }

  const invalidate = () => {
    lifecycleGeneration += 1
    options.sessionLoading.value = false
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
        ? await AgentAPI.getSession(existing.id)
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
      const resolved = await applyDetail(detail, generation, projectId, requestedRunId, requestedArtifactId)
      if (!resolved || !isCurrent(generation, projectId)) return
      options.addActivity('会话已恢复', `${detail.messages.length} 条历史消息，${detail.runs.length} 次运行记录。`)
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
      const detail = await AgentAPI.getSession(sessionId)
      if (!isCurrent(generation, projectId) || options.selectedSessionId.value !== sessionId) return
      options.runProjection.reset()
      await applyDetail(detail, generation, projectId)
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
    invalidate,
  }
}
