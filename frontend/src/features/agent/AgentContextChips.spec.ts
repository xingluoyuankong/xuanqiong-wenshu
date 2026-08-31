import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import AgentContextChips from './AgentContextChips.vue'

describe('AgentContextChips', () => {
  it('shows project and selected version context while only allowing removable selections', async () => {
    const wrapper = mount(AgentContextChips, {
      props: {
        refs: [
          { kind: 'project', project_id: 'project-a' },
          {
            kind: 'chapter_version',
            project_id: 'project-a',
            chapter_number: 7,
            version_id: 12,
            role: 'selected',
          },
        ],
        projectTitle: '星河旧梦',
      },
    })
    expect(wrapper.get('[data-testid="agent-context-chip-project"]').text()).toContain(
      '项目：星河旧梦',
    )
    expect(wrapper.get('[data-testid="agent-context-chip-chapter-version"]').text()).toContain(
      '第 7 章 · 版本 12',
    )
    expect(wrapper.find('[data-testid="agent-context-chip-project-remove"]').exists()).toBe(false)
    await wrapper.get('[data-testid="agent-context-chip-chapter-version-remove"]').trigger('click')
    expect(wrapper.emitted('remove')?.[0]).toEqual([
      {
        kind: 'chapter_version',
        project_id: 'project-a',
        chapter_number: 7,
        version_id: 12,
        role: 'selected',
      },
    ])
  })
})
