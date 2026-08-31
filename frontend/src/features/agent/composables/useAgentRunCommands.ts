import { computed, ref, type ComputedRef, type Ref } from 'vue'
import {
  AgentAPI,
  buildAgentRunCommandIdempotencyKey,
  type AgentRun,
  type AgentRunCommandType,
  type AgentSession,
  type AgentStateProjection,
} from '@/api/agent'
import type { AgentRunStream } from '@/features/agent/composables/useAgentRunStream'
import type { AgentRunProjectionStore } from '@/features/agent/stores/agentRunProjection'

export interface AgentRunCommandsOptions {
  activeRun: ComputedRef<AgentRun | null>
  runState: ComputedRef<AgentStateProjection | null>
  session: Ref<AgentSession | null>
  selectedRunId: Ref<string>
  streaming: Ref<boolean>
  runProjection: AgentRunProjectionStore
  stream: Pick<AgentRunStream, 'close'>
  loadRunState: (runId: string) => Promise<AgentStateProjection | null>
  loadEventsAndStream: (session: AgentSession, run: AgentRun) => Promise<unknown>
  addActivity: (label: string, detail: string, key?: string, sequence?: number, eventType?: string) => void
  runStatus: (status: string) => string
}

const terminalStatuses = new Set(['completed', 'failed', 'cancelled'])

/**
 * Executes the durable pause/resume/cancel/recover commands for the selected Run.
 *
 * The workspace owns routing and presentation, while this composable owns the
 * command request contract, optimistic projection refresh and stream lifecycle.
 * It intentionally keeps the existing cooperative-cancel behavior: SSE stays
 * connected until a durable terminal event arrives.
 */
export function useAgentRunCommands(options: AgentRunCommandsOptions) {
  const loadingByRunId = ref<Record<string, boolean>>({})
  const anyPending = computed(() => Object.values(loadingByRunId.value).some(Boolean))

  const recoverRunAction = async (run: AgentRun) => {
    if (typeof AgentAPI.recoverRun !== 'function') return
    try {
      const recovered = await AgentAPI.recoverRun(run.id)
      options.runProjection.upsertRun(recovered, { select: true })
      options.addActivity('运行恢复请求已提交', `${run.id.slice(0, 8)} · 已重新连接持久化执行流`)
      if (options.session.value) await options.loadEventsAndStream(options.session.value, recovered)
    } catch (error) {
      options.addActivity('运行恢复失败', error instanceof Error ? error.message : '无法恢复运行')
    }
  }

  const runControlAction = async (command: AgentRunCommandType) => {
    const run = options.activeRun.value
    if (!run || loadingByRunId.value[run.id] || typeof AgentAPI.submitRunCommand !== 'function') return

    const runId = run.id
    const currentSession = options.session.value
    const expectedStateVersion = Math.max(
      0,
      Number(options.runState.value?.state_version ?? run.state_version ?? 0),
    )
    const idempotencyKey = buildAgentRunCommandIdempotencyKey(
      runId,
      command,
      expectedStateVersion,
    )
    loadingByRunId.value = { ...loadingByRunId.value, [runId]: true }
    try {
      const commandResult = await AgentAPI.submitRunCommand(runId, {
        command_type: command,
        idempotency_key: idempotencyKey,
        expected_state_version: expectedStateVersion,
        reason: command === 'cancel' ? '作者停止当前运行' : '作者从 Chat 控制当前运行',
        payload_json: {},
      })
      const state = await options.loadRunState(runId)
      const projectedRun = options.runProjection.runsById.value[runId] || run
      const updated: AgentRun = state
        ? {
            ...projectedRun,
            status: state.status || projectedRun.status,
            current_phase: state.phase || projectedRun.current_phase,
            progress: state.progress,
            current_step: state.current_step,
            state_version: state.state_version ?? projectedRun.state_version,
            allowed_commands: state.allowed_commands ?? projectedRun.allowed_commands,
          }
        : projectedRun
      options.runProjection.upsertRun(updated, { select: options.selectedRunId.value === runId })
      const labels = {
        pause: '运行暂停命令已提交',
        resume: '运行恢复命令已提交',
        cancel: '运行取消命令已提交',
      }
      options.addActivity(labels[command], `${runId.slice(0, 8)} · ${commandResult.status} · ${options.runStatus(updated.status)}`)

      const stillSelected =
        currentSession?.id === options.session.value?.id && options.selectedRunId.value === runId
      if (!stillSelected) return
      if (command === 'resume' && currentSession && updated.status !== 'paused') {
        await options.loadEventsAndStream(currentSession, updated)
        return
      }
      if (command === 'cancel' && !terminalStatuses.has(updated.status)) {
        return
      }
      if (updated.status === 'paused' || terminalStatuses.has(updated.status)) {
        options.stream.close()
        options.runProjection.setConnectionState(runId, 'closed')
        options.streaming.value = false
      }
    } catch (error) {
      const labels = {
        pause: '暂停命令失败',
        resume: '恢复命令失败',
        cancel: '取消命令失败',
      }
      options.addActivity(labels[command], error instanceof Error ? error.message : '运行控制命令失败')
    } finally {
      loadingByRunId.value = { ...loadingByRunId.value, [runId]: false }
    }
  }

  return {
    loadingByRunId,
    anyPending,
    recoverRunAction,
    runControlAction,
  }
}
