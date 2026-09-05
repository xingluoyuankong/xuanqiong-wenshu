import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { AgentMessage } from '@/api/agent'
import AgentConversation from './AgentConversation.vue'

const baseMessage = (index: number, overrides: Partial<AgentMessage> = {}): AgentMessage => ({
  id: `message-${index}`,
  session_id: 'session-performance',
  user_id: 1,
  role: index % 2 ? 'user' : 'assistant',
  content: `消息 ${index}`,
  sequence: index,
  created_at: `2026-09-05T00:00:${String(index % 60).padStart(2, '0')}Z`,
  ...overrides,
})

const makeMessages = (count: number, overrides: (index: number) => Partial<AgentMessage> = () => ({})) =>
  Array.from({ length: count }, (_, index) => baseMessage(index + 1, overrides(index + 1)))

const messageNodes = (wrapper: ReturnType<typeof mount>) =>
  wrapper.findAll('[data-testid="agent-message-list"] .message')

const setViewport = (width: number, height: number) => {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: width })
  Object.defineProperty(window, 'innerHeight', { configurable: true, value: height })
}

afterEach(() => {
  setViewport(1024, 768)
})

describe('AgentConversation long-history performance boundaries', () => {
  it('空列表保持空态，不创建消息滚动容器或历史加载控件', () => {
    const wrapper = mount(AgentConversation, { props: { messages: [], goal: '' } })

    expect(wrapper.find('[data-testid="agent-empty-chat"]').exists()).toBe(true)
    expect(wrapper.findAll('[data-testid="agent-message-history"]')).toHaveLength(0)
    expect(wrapper.findAll('[data-testid="agent-message-list"]')).toHaveLength(0)
    expect(wrapper.findAll('[data-testid="agent-load-older-messages"]')).toHaveLength(0)
  })

  it('追加消息后仍限制在 60 个 DOM 节点，并保留最新消息', async () => {
    const wrapper = mount(AgentConversation, {
      props: { messages: makeMessages(60), goal: '' },
    })

    await wrapper.setProps({ messages: makeMessages(61) })

    expect(messageNodes(wrapper)).toHaveLength(60)
    expect(messageNodes(wrapper)[0].text()).toContain('消息 2')
    expect(messageNodes(wrapper).at(-1)?.text()).toContain('消息 61')
    expect(wrapper.findAll('[data-testid="agent-load-older-messages"]')).toHaveLength(1)
  })

  it('重复 ID 和乱序 sequence 不被静默去重，渲染顺序遵循输入数组顺序', () => {
    const messages = [
      baseMessage(30, { id: 'duplicate-id', sequence: 30, content: '输入顺序 A' }),
      baseMessage(10, { id: 'duplicate-id', sequence: 10, content: '输入顺序 B' }),
      baseMessage(20, { id: 'message-20', sequence: 20, content: '输入顺序 C' }),
    ]
    const wrapper = mount(AgentConversation, { props: { messages, goal: '' } })

    expect(messageNodes(wrapper)).toHaveLength(3)
    expect(messageNodes(wrapper).map((node) => node.text())).toEqual([
      expect.stringContaining('输入顺序 A'),
      expect.stringContaining('输入顺序 B'),
      expect.stringContaining('输入顺序 C'),
    ])
  })

  it('极长正文不会突破消息窗口，且尾部正文完整保留', () => {
    const longContent = '玄穹文枢·'.repeat(50_000)
    const startedAt = performance.now()
    const wrapper = mount(AgentConversation, {
      props: {
        messages: makeMessages(2_000, (index) =>
          index === 2_000 ? { content: longContent } : {},
        ),
        goal: '',
      },
    })
    const renderDuration = performance.now() - startedAt

    expect(messageNodes(wrapper)).toHaveLength(60)
    expect(messageNodes(wrapper).at(-1)?.text()).toContain(longContent)
    expect(longContent).toHaveLength(250_000)
    expect(renderDuration).toBeLessThan(2_000)
  })

  it('375px 移动视口加载更早消息时保持滚动锚点', async () => {
    setViewport(375, 667)
    const wrapper = mount(AgentConversation, {
      props: { messages: makeMessages(125), goal: '' },
    })
    const list = wrapper.get('[data-testid="agent-message-list"]')
    const listElement = list.element as HTMLElement & { scrollTo?: (options: ScrollToOptions) => void }
    Object.defineProperty(listElement, 'clientWidth', { configurable: true, value: 343 })
    Object.defineProperty(listElement, 'clientHeight', { configurable: true, value: 480 })
    Object.defineProperty(listElement, 'scrollHeight', {
      configurable: true,
      get: () => list.findAll('.message').length * 120,
    })
    listElement.scrollTop = 240
    const scrollTo = vi.fn()
    listElement.scrollTo = scrollTo

    await wrapper.get('[data-testid="agent-load-older-messages"]').trigger('click')

    expect(window.innerWidth).toBe(375)
    expect(listElement.clientWidth).toBe(343)
    expect(messageNodes(wrapper)).toHaveLength(120)
    expect(messageNodes(wrapper).at(-1)?.text()).toContain('消息 125')
    expect(scrollTo).toHaveBeenCalledWith({ top: 7_440, behavior: 'auto' })
  })
})
