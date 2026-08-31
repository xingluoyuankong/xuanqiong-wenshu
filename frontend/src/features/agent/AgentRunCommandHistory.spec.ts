import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AgentRunCommandHistory from './AgentRunCommandHistory.vue'

const commands = [
  {
    id: 'command-pause',
    command_type: 'pause' as const,
    status: 'applied' as const,
    reason: '作者检查当前计划',
    requested_at: '2026-08-27T00:00:00Z',
    applied_at: '2026-08-27T00:00:01Z',
  },
  {
    id: 'command-resume',
    command_type: 'resume' as const,
    status: 'rejected' as const,
    reason: '运行已经结束',
    error_type: 'AgentConflict',
    requested_at: '2026-08-27T00:00:02Z',
    applied_at: '2026-08-27T00:00:03Z',
  },
]

describe('AgentRunCommandHistory', () => {
  it('展示 selected Run 的控制类型、状态、原因和错误摘要', () => {
    const wrapper = mount(AgentRunCommandHistory, { props: { commands } })

    expect(wrapper.get('[data-testid="agent-run-command-history"]').text()).toContain('暂停')
    expect(wrapper.text()).toContain('已应用')
    expect(wrapper.text()).toContain('作者检查当前计划')
    expect(wrapper.text()).toContain('继续')
    expect(wrapper.text()).toContain('已拒绝')
    expect(wrapper.text()).toContain('AgentConflict')
  })

  it('没有 durable command 时不渲染空面板', () => {
    const wrapper = mount(AgentRunCommandHistory, { props: { commands: [] } })

    expect(wrapper.find('[data-testid="agent-run-command-history"]').exists()).toBe(false)
  })
})
