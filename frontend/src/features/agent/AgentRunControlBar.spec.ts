import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AgentRunControlBar from './AgentRunControlBar.vue'

const createRun = (status: string, current_phase = 'tool_execution') => ({
  id: 'run-control',
  correlation_id: 'correlation-control',
  session_id: 'session-control',
  user_id: 1,
  status,
  current_phase,
  current_step: 2,
  progress: 40,
  created_at: 'now',
})

describe('AgentRunControlBar', () => {
  it('为可运行状态提供暂停和取消控制', async () => {
    const wrapper = mount(AgentRunControlBar, { props: { run: createRun('running'), allowedCommands: ['pause', 'cancel'] } })

    expect(wrapper.get('[data-testid="agent-pause-run-button"]').text()).toContain('暂停')
    expect(wrapper.get('[data-testid="agent-cancel-run-button"]').text()).toContain('取消运行')
    expect(wrapper.find('[data-testid="agent-resume-run-button"]').exists()).toBe(false)

    await wrapper.get('[data-testid="agent-pause-run-button"]').trigger('click')
    await wrapper.get('[data-testid="agent-cancel-run-button"]').trigger('click')
    expect(wrapper.emitted('command')).toEqual([['pause'], ['cancel']])
  })

  it('仅为用户暂停的运行提供继续控制，并把 recovery_ready 交给恢复流程', async () => {
    const paused = mount(AgentRunControlBar, { props: { run: createRun('paused', 'paused'), allowedCommands: ['resume', 'cancel'] } })
    expect(paused.get('[data-testid="agent-resume-run-button"]').text()).toContain('继续')
    await paused.get('[data-testid="agent-resume-run-button"]').trigger('click')
    expect(paused.emitted('command')).toEqual([['resume']])

    const recovery = mount(AgentRunControlBar, {
      props: { run: createRun('paused', 'recovery_ready'), allowedCommands: ['cancel'] },
    })
    expect(recovery.find('[data-testid="agent-resume-run-button"]').exists()).toBe(false)
    expect(recovery.find('[data-testid="agent-cancel-run-button"]').exists()).toBe(true)
  })

  it('不为终态运行渲染控制条', () => {
    expect(mount(AgentRunControlBar, { props: { run: createRun('completed') } })
      .find('[data-testid="agent-run-control-bar"]').exists()).toBe(false)
  })
})
