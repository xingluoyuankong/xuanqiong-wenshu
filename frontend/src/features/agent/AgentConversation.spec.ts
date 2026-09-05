import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import AgentConversation from './AgentConversation.vue'
import conversationSource from './AgentConversation.vue?raw'

const message = {
  id: 'message-1',
  session_id: 'session-1',
  user_id: 1,
  role: 'assistant',
  content: '我已经整理了第三章的质量风险。',
  sequence: 1,
  created_at: '2026-08-28T00:00:00Z',
}

describe('AgentConversation', () => {
  it('展示会话消息和公开进度，同时把输入和提交事件交还父工作台', async () => {
    const wrapper = mount(AgentConversation, {
      props: {
        messages: [message],
        sessionTitle: '第三章质量审查',
        streamConnectionState: 'live',
        runtimeSupported: true,
        latestProgressMessage: '正在检查第三章质量',
        latestProgressActionId: 'tool:quality.inspect',
        latestProgressPhase: 'tool_execution',
        latestProgress: 42,
        goal: '检查第三章',
        publicWorkSummary: {
          action_id: 'planner:1',
          phase: 'planning',
          current_action: '正在建立创作计划。',
          input_scope: [],
          revision: 0,
        },
      },
    })

    expect(wrapper.get('[data-testid="agent-session-status"]').text()).toContain('会话：第三章质量审查')
    expect(wrapper.get('[data-testid="agent-message-list"]').text()).toContain(message.content)
    expect(wrapper.get('[data-testid="agent-public-work-summary"]').text()).toContain('正在建立创作计划。')
    expect(wrapper.get('[data-testid="agent-current-progress"]').text()).toContain('正在检查第三章质量')
    expect(wrapper.get('[data-testid="agent-current-progress"]').text()).toContain('tool:quality.inspect')
    expect(wrapper.get('[data-testid="agent-current-progress"]').text()).toContain('42%')
    expect((wrapper.get('[data-testid="agent-progress-meter"]').element as HTMLProgressElement).value).toBe(42)
    expect(wrapper.get('[data-testid="agent-current-progress"]').attributes('aria-live')).toBe('polite')
    expect(wrapper.find('[data-testid="agent-process-stream"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('实时运行流已连接')

    await wrapper.get('[data-testid="agent-message-input"]').setValue('改写第三章开头')
    expect(wrapper.emitted('update:goal')?.at(-1)).toEqual(['改写第三章开头'])

    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')).toHaveLength(1)
  })

  it('仅收到公开工作轨迹时也在中央聊天显示实时活动', () => {
    const wrapper = mount(AgentConversation, {
      props: {
        messages: [],
        goal: '',
        latestWorkTrace: {
          sequence: 7,
          traceId: 'trace-7',
          phase: 'act',
          actionId: 'tool:content.search',
          kind: 'tool',
          message: '正在读取项目章节索引',
          progress: 38,
          resultRef: 'execution:search-7',
        },
      },
    })

    const activity = wrapper.get('[data-testid="agent-live-trace"]')
    expect(activity.text()).toContain('正在读取项目章节索引')
    expect(activity.text()).toContain('阶段：act')
    expect(activity.text()).toContain('动作：tool:content.search')
    expect(activity.text()).toContain('38%')
    expect((wrapper.get('[data-testid="agent-live-trace-meter"]').element as HTMLProgressElement).value).toBe(38)
  })

  it('当前进度摘要在浅色背景上使用高对比度文本', () => {
    const block = conversationSource.match(/\.current-progress \{[\s\S]*?\n\}/)?.[0] || ''
    expect(block).toContain('color: var(--xq-ink);')
    expect(conversationSource).toContain('.current-progress span {')
    expect(conversationSource).toContain('.current-progress small { color: var(--xq-ink-muted);')
  })

  it('转发上下文移除和候选预览关闭事件，并在空输入时禁用提交', async () => {
    const wrapper = mount(AgentConversation, {
      props: {
        messages: [],
        goal: '',
        artifactPreview: '候选正文',
        contextRefs: [
          {
            kind: 'chapter_version',
            project_id: 'project-a',
            chapter_number: 3,
            version_id: 8,
            role: 'selected',
          },
        ],
      },
    })

    expect(wrapper.get('[data-testid="agent-empty-chat"]').text()).toContain('请选择项目')
    expect(wrapper.get('[data-testid="agent-plan-submit"]').attributes('disabled')).toBeDefined()

    await wrapper.get('[data-testid="agent-context-chip-chapter-version-remove"]').trigger('click')
    expect(wrapper.emitted('remove-context-ref')?.[0]).toEqual([
      {
        kind: 'chapter_version',
        project_id: 'project-a',
        chapter_number: 3,
        version_id: 8,
        role: 'selected',
      },
    ])

    await wrapper.get('[data-testid="agent-artifact-preview"] button').trigger('click')
    expect(wrapper.emitted('close-artifact-preview')).toHaveLength(1)
  })

  it('显示候选预览的读取中与失败状态', () => {
    const loading = mount(AgentConversation, {
      props: { messages: [], goal: '', artifactPreviewLoading: true },
    })
    expect(loading.get('[data-testid="agent-artifact-preview-loading"]').text()).toContain('正在读取候选正文')

    const failed = mount(AgentConversation, {
      props: { messages: [], goal: '', artifactPreviewError: 'preview failed' },
    })
    expect(failed.get('[data-testid="agent-artifact-preview-error"]').text()).toContain('preview failed')
  })

  it('在 Assistant 正文之前独立展示 Provider 原始 reasoning', () => {
    const wrapper = mount(AgentConversation, {
      props: {
        messages: [message],
        streamingAssistant: '可见正文',
        reasoningText: 'Provider 的原始 reasoning\n第二行',
        reasoningStatus: 'streaming',
        reasoningChunks: [{ sequence: 2, chunkIndex: 0, content: 'Provider 的原始 reasoning\n第二行' }],
      },
    })
    expect(wrapper.get('[data-testid="agent-reasoning-card"]').text()).toContain('Provider 原始 reasoning')
    expect(wrapper.get('[data-testid="agent-reasoning-body"] pre').text()).toContain('第二行')
    expect(wrapper.get('[data-testid="agent-streaming-message"]').text()).toContain('可见正文')
    expect(wrapper.find('[data-testid="agent-reasoning-body"]').element.compareDocumentPosition(wrapper.get('[data-testid="agent-streaming-message"]').element) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })


  it('长会话只渲染尾部窗口，并在加载更早消息后保持滚动锚点', async () => {
    const messages = Array.from({ length: 125 }, (_, index) => ({
      ...message,
      id: `message-${index + 1}`,
      sequence: index + 1,
      content: `历史消息 ${index + 1}`,
    }))
    const wrapper = mount(AgentConversation, {
      props: { messages, goal: '' },
    })
    const list = wrapper.get('[data-testid="agent-message-list"]')
    const listElement = list.element as HTMLElement & { scrollTo?: (options: ScrollToOptions) => void }
    let scrollHeight = 0
    Object.defineProperty(listElement, 'clientHeight', { configurable: true, value: 400 })
    Object.defineProperty(listElement, 'scrollHeight', {
      configurable: true,
      get: () => {
        scrollHeight += 1
        return list.findAll('.message').length * 100
      },
    })
    listElement.scrollTop = 800
    const scrollTo = vi.fn()
    listElement.scrollTo = scrollTo

    expect(list.findAll('.message')).toHaveLength(60)
    expect(list.find('.message').text()).toContain('历史消息 66')
    expect(list.findAll('.message').at(-1)?.text()).toContain('历史消息 125')
    expect(wrapper.get('[data-testid="agent-load-older-messages"]').text()).toContain('加载更早消息')

    await wrapper.get('[data-testid="agent-load-older-messages"]').trigger('click')

    expect(list.findAll('.message')).toHaveLength(120)
    expect(list.find('.message').text()).toContain('历史消息 6')
    expect(list.findAll('.message').at(-1)?.text()).toContain('历史消息 125')
    expect(scrollHeight).toBeGreaterThan(0)
    expect(scrollTo).toHaveBeenCalledWith(expect.objectContaining({ behavior: 'auto' }))
    expect(scrollTo.mock.lastCall?.[0].top).toBeGreaterThan(800)
  })


  it('同一会话刷新首条消息后保留已展开的窗口', async () => {
    const messages = Array.from({ length: 125 }, (_, index) => ({
      ...message,
      id: `refresh-${index + 1}`,
      session_id: 'session-refresh',
      sequence: index + 1,
      content: `刷新前消息 ${index + 1}`,
    }))
    const wrapper = mount(AgentConversation, {
      props: { messages, goal: '' },
    })

    await wrapper.get('[data-testid="agent-load-older-messages"]').trigger('click')
    expect(wrapper.findAll('[data-testid="agent-message-list"] .message')).toHaveLength(120)

    const refreshedMessages = messages.map((item, index) =>
      index === 0 ? { ...item, id: 'refresh-rehydrated-first', content: '刷新后首条消息' } : item,
    )
    await wrapper.setProps({ messages: refreshedMessages })

    expect(wrapper.findAll('[data-testid="agent-message-list"] .message')).toHaveLength(120)
  })

  it('快速重复点击加载按钮时只扩展一个窗口', async () => {
    const messages = Array.from({ length: 125 }, (_, index) => ({
      ...message,
      id: `double-click-${index + 1}`,
      session_id: 'session-double-click',
      sequence: index + 1,
      content: `重复点击消息 ${index + 1}`,
    }))
    const wrapper = mount(AgentConversation, {
      props: { messages, goal: '' },
    })
    const button = wrapper.get('[data-testid="agent-load-older-messages"]')

    const firstClick = button.trigger('click')
    const secondClick = button.trigger('click')
    await Promise.all([firstClick, secondClick])

    expect(wrapper.findAll('[data-testid="agent-message-list"] .message')).toHaveLength(120)
  })

  it('切换会话后重新从尾部窗口开始渲染', async () => {
    const firstSessionMessages = Array.from({ length: 125 }, (_, index) => ({
      ...message,
      id: `first-${index + 1}`,
      session_id: 'session-first',
      sequence: index + 1,
      content: `第一会话消息 ${index + 1}`,
    }))
    const wrapper = mount(AgentConversation, {
      props: { messages: firstSessionMessages, goal: '' },
    })

    await wrapper.get('[data-testid="agent-load-older-messages"]').trigger('click')
    expect(wrapper.findAll('[data-testid="agent-message-list"] .message')).toHaveLength(120)

    const secondSessionMessages = Array.from({ length: 125 }, (_, index) => ({
      ...message,
      id: `second-${index + 1}`,
      session_id: 'session-second',
      sequence: index + 1,
      content: `第二会话消息 ${index + 1}`,
    }))
    await wrapper.setProps({ messages: secondSessionMessages })

    expect(wrapper.findAll('[data-testid="agent-message-list"] .message')).toHaveLength(60)
    expect(wrapper.get('[data-testid="agent-message-list"] .message').text()).toContain('第二会话消息 66')
  })

})
