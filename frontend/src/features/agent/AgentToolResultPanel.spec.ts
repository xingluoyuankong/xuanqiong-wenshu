import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import AgentToolResultPanel from './AgentToolResultPanel.vue'

describe('AgentToolResultPanel', () => {
  it('renders a bounded safe projection for supported tool results', () => {
    const wrapper = mount(AgentToolResultPanel, {
      props: {
        results: [{
          tool_name: 'chapter.version.list',
          result: {
            count: 1,
            versions: [{
              chapter_number: 3,
              version_id: 12,
              status: 'candidate',
              word_count: 920,
              content: 'SECRET_CHAPTER_PROSE',
            }],
          },
        }],
      },
    })

    expect(wrapper.get('[data-testid="agent-tool-result-0"]').text()).toContain('第3章 v12')
    expect(wrapper.get('[data-testid="agent-tool-result-0"]').text()).toContain('920字')
    expect(wrapper.text()).not.toContain('SECRET_CHAPTER_PROSE')
    expect(wrapper.text()).toContain('版本正文不会在工具结果面板中渲染')
  })

  it('redacts prose, prompt, reasoning and secret-like values even in allowed summaries', () => {
    const wrapper = mount(AgentToolResultPanel, {
      props: {
        results: [{
          tool_name: 'research.inspect',
          result: {
            count: 1,
            artifacts: [{
              scope: 'chapter',
              status: 'finished',
              summary: '这是一个很长的研究摘要，api_key=do-not-render-this-value',
              source_text: 'SECRET_SOURCE_PROSE',
              prompt_context: 'SECRET_PROMPT',
            }],
          },
        }],
      },
    })

    const text = wrapper.text()
    expect(text).toContain('这是一个很长的研究摘要，[已脱敏]')
    expect(text).not.toContain('do-not-render-this-value')
    expect(text).not.toContain('SECRET_SOURCE_PROSE')
    expect(text).not.toContain('SECRET_PROMPT')
  })

  it('does not render unknown tool payloads', () => {
    const wrapper = mount(AgentToolResultPanel, {
      props: {
        results: [{ tool_name: 'provider.private_dump', result: { arbitrary: 'SECRET_UNKNOWN_PAYLOAD' } }],
      },
    })

    expect(wrapper.get('[data-testid="agent-tool-result-0"]').text()).toContain('未支持')
    expect(wrapper.get('[data-testid="agent-tool-result-0"]').text()).toContain('原始数据不会在界面中回显')
    expect(wrapper.text()).not.toContain('SECRET_UNKNOWN_PAYLOAD')
  })

  it('bounds result count and list items', () => {
    const wrapper = mount(AgentToolResultPanel, {
      props: {
        maxResults: 1,
        maxListItems: 1,
        maxFieldsPerResult: 2,
        maxTextLength: 12,
        results: [
          {
            tool_name: 'project.list',
            result: {
              projects: [
                { id: 'p1', title: '项目一' },
                { id: 'p2', title: '项目二' },
              ],
              description: '这段不应作为原始对象被无界渲染',
            },
          },
          { tool_name: 'statistics.project', result: { project: { title: '不应展示的第二项' } } },
        ],
      },
    })

    expect(wrapper.findAll('.tool-result-card').length).toBe(1)
    expect(wrapper.get('[data-testid="agent-tool-result-truncated"]').text()).toContain('还有 1 个工具结果未展示')
    expect(wrapper.text()).toContain('另有 1 项未展示')
    expect(wrapper.text()).not.toContain('不应展示的第二项')
  })

  it('shows an explicit empty state', () => {
    const wrapper = mount(AgentToolResultPanel, { props: { results: [] } })
    expect(wrapper.get('[data-testid="agent-tool-result-empty"]').text()).toContain('没有可展示的工具结果')
  })
})
