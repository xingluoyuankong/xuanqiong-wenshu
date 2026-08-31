import { watch, type ComputedRef, type Ref } from 'vue'
import { AgentAPI, type AgentAuditRecord, type AgentJob, type AgentTimelineEvent } from '@/api/agent'

export interface AgentProjectGovernanceDataOptions {
  selectedProjectId: Ref<string>
  isAdmin: ComputedRef<boolean>
  timeline: Ref<AgentTimelineEvent[]>
  timelineLoading: Ref<boolean>
  timelineEventType: Ref<string>
  timelineRunStatus: Ref<string>
  auditLedger: Ref<AgentAuditRecord[]>
  auditLoading: Ref<boolean>
  jobs: Ref<AgentJob[]>
  jobsLoading: Ref<boolean>
  deadLetters: Ref<AgentJob[]>
  deadLettersLoading: Ref<boolean>
  addActivity: (label: string, detail: string) => void
}

/** Project-scoped read models with one stale fence for the Chat Shell side panels. */
export function useAgentProjectGovernanceData(options: AgentProjectGovernanceDataOptions) {
  let lifecycleGeneration = 0
  let timelineRequestGeneration = 0
  let auditRequestGeneration = 0
  let jobsRequestGeneration = 0
  let deadLetterRequestGeneration = 0

  const isCurrent = (projectGeneration: number, requestGeneration: number, currentRequestGeneration: number, projectId: string) =>
    lifecycleGeneration === projectGeneration &&
    currentRequestGeneration === requestGeneration &&
    options.selectedProjectId.value === projectId

  const clear = () => {
    lifecycleGeneration += 1
    options.timeline.value = []
    options.auditLedger.value = []
    options.jobs.value = []
    options.deadLetters.value = []
    options.timelineLoading.value = false
    options.auditLoading.value = false
    options.jobsLoading.value = false
    options.deadLettersLoading.value = false
  }

  const loadTimeline = async () => {
    const projectId = options.selectedProjectId.value
    if (typeof AgentAPI.listTimeline !== 'function' || !projectId) return
    const projectGeneration = lifecycleGeneration
    const requestGeneration = ++timelineRequestGeneration
    options.timelineLoading.value = true
    try {
      const result = await AgentAPI.listTimeline({
        projectId,
        eventType: options.timelineEventType.value || undefined,
        runStatus: options.timelineRunStatus.value || undefined,
        limit: 100,
      })
      if (!isCurrent(projectGeneration, requestGeneration, timelineRequestGeneration, projectId)) return
      options.timeline.value = result
    } catch (error) {
      if (isCurrent(projectGeneration, requestGeneration, timelineRequestGeneration, projectId)) {
        options.addActivity('项目时间线读取失败', error instanceof Error ? error.message : '无法读取跨会话时间线')
      }
    } finally {
      if (requestGeneration === timelineRequestGeneration) options.timelineLoading.value = false
    }
  }

  const loadAudit = async () => {
    const projectId = options.selectedProjectId.value
    if (typeof AgentAPI.listAudit !== 'function' || !projectId) return
    const projectGeneration = lifecycleGeneration
    const requestGeneration = ++auditRequestGeneration
    options.auditLoading.value = true
    try {
      const result = await AgentAPI.listAudit({ projectId, limit: 100 })
      if (!isCurrent(projectGeneration, requestGeneration, auditRequestGeneration, projectId)) return
      options.auditLedger.value = result
    } catch (error) {
      if (isCurrent(projectGeneration, requestGeneration, auditRequestGeneration, projectId)) {
        options.addActivity('审计账本读取失败', error instanceof Error ? error.message : '无法读取 Agent 审计账本')
      }
    } finally {
      if (requestGeneration === auditRequestGeneration) options.auditLoading.value = false
    }
  }

  const loadJobs = async () => {
    const projectId = options.selectedProjectId.value
    if (typeof AgentAPI.listJobs !== 'function' || !projectId) return
    const projectGeneration = lifecycleGeneration
    const requestGeneration = ++jobsRequestGeneration
    options.jobsLoading.value = true
    try {
      const result = await AgentAPI.listJobs(projectId)
      if (!isCurrent(projectGeneration, requestGeneration, jobsRequestGeneration, projectId)) return
      options.jobs.value = result
    } catch (error) {
      if (isCurrent(projectGeneration, requestGeneration, jobsRequestGeneration, projectId)) {
        options.addActivity('Job 列表读取失败', error instanceof Error ? error.message : '无法读取持久化 Job')
      }
    } finally {
      if (requestGeneration === jobsRequestGeneration) options.jobsLoading.value = false
    }
  }

  const loadDeadLetters = async () => {
    const projectId = options.selectedProjectId.value
    if (!options.isAdmin.value || typeof AgentAPI.listDeadLetters !== 'function' || !projectId) return
    const projectGeneration = lifecycleGeneration
    const requestGeneration = ++deadLetterRequestGeneration
    options.deadLettersLoading.value = true
    try {
      const result = await AgentAPI.listDeadLetters(100)
      if (!isCurrent(projectGeneration, requestGeneration, deadLetterRequestGeneration, projectId)) return
      options.deadLetters.value = result
    } catch (error) {
      if (isCurrent(projectGeneration, requestGeneration, deadLetterRequestGeneration, projectId)) {
        options.addActivity('死信 Job 读取失败', error instanceof Error ? error.message : '无法读取死信 Job')
      }
    } finally {
      if (requestGeneration === deadLetterRequestGeneration) options.deadLettersLoading.value = false
    }
  }

  const reload = async () => {
    await Promise.all([loadTimeline(), loadAudit(), loadJobs(), loadDeadLetters()])
  }

  const replayDeadLetterAction = async (job: AgentJob) => {
    if (typeof AgentAPI.replayDeadLetter !== 'function') return
    try {
      await AgentAPI.replayDeadLetter(job.id, 'Agent 工作台管理员重放')
      options.deadLetters.value = options.deadLetters.value.filter((item) => item.id !== job.id)
      options.jobs.value = options.jobs.value.map((item) =>
        item.id === job.id
          ? {
              ...item,
              status: 'queued',
              finished_at: null,
              lease_owner: null,
              lease_expires_at: null,
            }
          : item,
      )
      options.addActivity('死信 Job 已重新排队', `${job.kind} · ${job.id.slice(0, 8)}`)
    } catch (error) {
      options.addActivity('死信 Job 重放失败', error instanceof Error ? error.message : '无法重放死信 Job')
    }
  }

  watch([options.timelineEventType, options.timelineRunStatus], () => {
    void loadTimeline()
  })

  return { clear, loadTimeline, loadAudit, loadJobs, loadDeadLetters, reload, replayDeadLetterAction }
}

