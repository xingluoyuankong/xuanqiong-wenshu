import { computed, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const { recoverRunMock, submitRunCommandMock } = vi.hoisted(() => ({
  recoverRunMock: vi.fn(),
  submitRunCommandMock: vi.fn(),
}))

vi.mock('@/api/agent', () => ({
  buildAgentRunCommandIdempotencyKey: (runId: string, command: string, version: number) =>
    `agent-run-command:${runId}:${command}:state-${version}`,
  AgentAPI: {
    recoverRun: recoverRunMock,
    submitRunCommand: submitRunCommandMock,
  },
}))

import type { AgentRunCommandType, AgentRun, AgentStateProjection, AgentSession } from '@/api/agent'
import { useAgentRunCommands } from './useAgentRunCommands'
import { useAgentRunProjection } from '@/features/agent/stores/agentRunProjection'

const run = (patch: Record<string, unknown> = {}): AgentRun => ({
  id: 'run-1',
  session_id: 'session-1',
  user_id: 1,
  status: 'running',
  current_phase: 'executing',
  current_step: 2,
  progress: 40,
  state_version: 4,
  allowed_commands: ['pause', 'cancel'] as AgentRunCommandType[],
  created_at: '2026-08-31T00:00:00Z',
  ...patch,
})

const state = (patch: Record<string, unknown> = {}): AgentStateProjection => ({
  correlation_id: 'correlation-1',
  run_id: 'run-1',
  user_id: 1,
  status: 'paused',
  phase: 'paused',
  progress: 40,
  current_step: 2,
  state_version: 5,
  allowed_commands: ['resume', 'cancel'] as AgentRunCommandType[],
  recoverable: false,
  cancellation_requested: false,
  last_event_sequence: 3,
  steps: [],
  approvals: [],
  artifacts: [],
  accepted_version_ids: [],
  jobs: [],
  task_runtime_refs: [],
  ...patch,
})

describe('useAgentRunCommands', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  const createCommands = () => {
    const runProjection = useAgentRunProjection()
    runProjection.upsertRun(run(), { select: true })
    const session = ref<AgentSession>({
      id: 'session-1', user_id: 1, project_id: 'project-1', status: 'active',
      created_at: '2026-08-31T00:00:00Z', updated_at: '2026-08-31T00:00:00Z',
    })
    const streaming = ref(true)
    const loadRunState = vi.fn().mockResolvedValue(state())
    const loadEventsAndStream = vi.fn().mockResolvedValue(undefined)
    const addActivity = vi.fn()
    const close = vi.fn()
    const commands = useAgentRunCommands({
      activeRun: runProjection.activeRun,
      runState: runProjection.activeRunState,
      session,
      selectedRunId: runProjection.selectedRunId,
      streaming,
      runProjection,
      stream: { close },
      loadRunState,
      loadEventsAndStream,
      addActivity,
      runStatus: (value) => ({ paused: '已暂停', running: '正在执行', cancelled: '已取消' })[value] || value,
    })
    return { runProjection, session, streaming, loadRunState, loadEventsAndStream, addActivity, close, commands }
  }

  it('submits pause with the current state version, refreshes projection, and closes the stream', async () => {
    const fixture = createCommands()
    submitRunCommandMock.mockResolvedValue({ status: 'applied' })

    await fixture.commands.runControlAction('pause')

    expect(submitRunCommandMock).toHaveBeenCalledWith('run-1', {
      command_type: 'pause',
      idempotency_key: 'agent-run-command:run-1:pause:state-4',
      expected_state_version: 4,
      reason: '作者从 Chat 控制当前运行',
      payload_json: {},
    })
    expect(fixture.runProjection.activeRun.value).toMatchObject({
      status: 'paused', current_phase: 'paused', state_version: 5, allowed_commands: ['resume', 'cancel'],
    })
    expect(fixture.close).toHaveBeenCalledTimes(1)
    expect(fixture.streaming.value).toBe(false)
    expect(fixture.commands.loadingByRunId.value).toEqual({ 'run-1': false })
    expect(fixture.addActivity).toHaveBeenCalledWith(
      '运行暂停命令已提交',
      'run-1 · applied · 已暂停',
    )
  })

  it('keeps the SSE lifecycle open while a cooperative cancel remains non-terminal', async () => {
    const fixture = createCommands()
    submitRunCommandMock.mockResolvedValue({ status: 'applied' })
    fixture.loadRunState.mockResolvedValue(state({
      status: 'cancelling', phase: 'cancelling', state_version: 5, allowed_commands: [], cancellation_requested: true,
    }))

    await fixture.commands.runControlAction('cancel')

    expect(submitRunCommandMock).toHaveBeenCalledWith('run-1', expect.objectContaining({
      command_type: 'cancel',
      reason: '作者停止当前运行',
    }))
    expect(fixture.close).not.toHaveBeenCalled()
    expect(fixture.streaming.value).toBe(true)
  })

  it('reconnects the recovered run through the current session', async () => {
    const fixture = createCommands()
    const recovered = run({ status: 'running', current_phase: 'recovery_ready' })
    recoverRunMock.mockResolvedValue(recovered)

    await fixture.commands.recoverRunAction(run({ status: 'paused', current_phase: 'recovery_ready' }))

    expect(recoverRunMock).toHaveBeenCalledWith('run-1')
    expect(fixture.loadEventsAndStream).toHaveBeenCalledWith(fixture.session.value, recovered)
    expect(fixture.addActivity).toHaveBeenCalledWith(
      '运行恢复请求已提交',
      'run-1 · 已重新连接持久化执行流',
    )
  })

  it('does not issue duplicate commands while the selected run is pending', async () => {
    const fixture = createCommands()
    let resolveCommand!: (value: { status: string }) => void
    submitRunCommandMock.mockReturnValue(new Promise((resolve) => { resolveCommand = resolve }))

    const first = fixture.commands.runControlAction('pause')
    await Promise.resolve()
    await fixture.commands.runControlAction('pause')
    resolveCommand({ status: 'applied' })
    await first

    expect(submitRunCommandMock).toHaveBeenCalledTimes(1)
  })
})
