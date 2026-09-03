import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { describe, expect, it } from 'vitest'
import AgentReasoningCard from './AgentReasoningCard.vue'

describe('AgentReasoningCard', () => {
  it('将 reasoning 独立于正文显示，并在流式期间展开、完成后折叠', async () => {
    const wrapper = mount(AgentReasoningCard, {
      props: { text: '先读取项目上下文\n再调用工具', status: 'streaming', chunks: [{ sequence: 1, chunkIndex: 0, content: '先读取项目上下文\n' }, { sequence: 2, chunkIndex: 1, content: '再调用工具' }] },
    })
    expect(wrapper.get('[data-testid="agent-reasoning-card"]').text()).toContain('Provider 原始 reasoning')
    expect(wrapper.get('[data-testid="agent-reasoning-body"]').isVisible()).toBe(true)
    expect(wrapper.get('[data-testid="agent-reasoning-body"]').text()).toContain('再调用工具')
    await wrapper.setProps({ status: 'completed' })
    expect(wrapper.get('[data-testid="agent-reasoning-body"]').attributes('style')).toContain('display: none')
    await wrapper.get('[data-testid="agent-reasoning-toggle"]').trigger('click')
    expect(wrapper.get('[data-testid="agent-reasoning-body"]').isVisible()).toBe(true)
  })

  it('保留换行并显示失败状态', () => {
    const wrapper = mount(AgentReasoningCard, { props: { text: 'line-1\nline-2', status: 'failed' } })
    expect(wrapper.get('[data-testid="agent-reasoning-body"]').attributes('style')).toContain('display: none')
    expect(wrapper.get('[data-testid="agent-reasoning-card"]').text()).toContain('失败')
  })
})


