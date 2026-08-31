import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AgentRunInspector from './AgentRunInspector.vue'

const run = { id: 'run-inspector', session_id: 's', user_id: 1, status: 'running', current_step: 1, progress: 42, created_at: '2026-08-28T00:00:00Z' } as any

describe('AgentRunInspector', () => {
  it('renders run state, control and checkpoints', () => {
    const wrapper = mount(AgentRunInspector, { props: { run, state: { correlation_id: 'corr-inspector', capability_snapshot: { generation: 2, tools: [] }, allowed_commands: ['pause'], commands: [], progress: 42, current_step: 1 } as any, steps: [{ id: 'step-1', step_order: 1, tool_name: 'project.context', status: 'completed', attempt_count: 1, output_json: {} } as any], toolResults: [], connectionState: 'live' } })
    expect(wrapper.get('[data-testid="agent-run-inspector"]')).toBeTruthy()
    expect(wrapper.get('[data-testid="agent-run-status"]').text()).toContain('正在执行')
    expect(wrapper.get('[data-testid="agent-step-panel"]').text()).toContain('project.context')
  })

  it('emits control events', async () => {
    const wrapper = mount(AgentRunInspector, { props: { run: { ...run, status: 'paused', current_phase: 'recovery_ready' }, state: null, steps: [], toolResults: [], connectionState: 'disconnected' } })
    await wrapper.get('[data-testid="agent-recover-run-button"]').trigger('click')
    await wrapper.get('[data-testid="agent-reconnect-stream-button"]').trigger('click')
    expect(wrapper.emitted('recover')).toHaveLength(1)
    expect(wrapper.emitted('reconnect')).toHaveLength(1)
  })
})
