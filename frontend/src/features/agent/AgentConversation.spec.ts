import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import AgentConversation from './AgentConversation.vue'

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
    expect(wrapper.find('[data-testid="agent-process-stream"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('实时运行流已连接')

    await wrapper.get('[data-testid="agent-message-input"]').setValue('改写第三章开头')
    expect(wrapper.emitted('update:goal')?.at(-1)).toEqual(['改写第三章开头'])

    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')).toHaveLength(1)
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

})
