import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ProjectContentTree from './ProjectContentTree.vue'

describe('ProjectContentTree', () => {
  const baseProps = {
    volumes: [{ id: 'volume:1', label: '第1卷 · 初入玄门', volumeNumber: 1, chapters: [{ chapterNumber: 7, title: '试炼', summary: '进入试炼', generationStatus: 'successful', wordCount: 700 }] }],
    selectedChapterNumber: 7,
    selectedVersionId: 22,
    selectedChapter: { chapter_number: 7, title: '试炼', summary: '进入试炼', content: 'SAFE_PREVIEW_TEXT', selected_version_id: 22, versions: [{ id: 21, content: '旧版本' }, { id: 22, content: 'SAFE_PREVIEW_TEXT' }], evaluation: null, generation_status: 'successful' as const },
  }

  it('renders lightweight tree, emits selection, and bounds chapter preview', async () => {
    const wrapper = mount(ProjectContentTree, { props: { ...baseProps, previewLimit: 200 } })
    expect(wrapper.get('[data-testid="agent-content-chapter-7"]').text()).toContain('第 7 章 · 试炼')
    expect(wrapper.get('[data-testid="agent-content-version-22"]').classes()).toContain('selected')
    expect(wrapper.get('[data-testid="agent-content-preview-text"]').text()).toContain('SAFE_PREVIEW_TEXT')
    await wrapper.get('[data-testid="agent-content-chapter-7"]').trigger('click')
    await wrapper.get('[data-testid="agent-content-version-21"]').trigger('click')
    await wrapper.get('[data-testid="agent-content-open-writing-desk"]').trigger('click')
    expect(wrapper.emitted('select-chapter')).toEqual([[7]])
    expect(wrapper.emitted('select-version')).toEqual([[21]])
    expect(wrapper.emitted('open-writing-desk')).toHaveLength(1)
  })

  it('does not show full preview when no selected chapter content is loaded', () => {
    const wrapper = mount(ProjectContentTree, { props: { volumes: baseProps.volumes, selectedChapterNumber: 7 } })
    expect(wrapper.get('[data-testid="agent-content-preview"]').text()).toContain('仅在点击章节后读取详情')
    expect(wrapper.find('[data-testid="agent-content-preview-text"]').exists()).toBe(false)
  })
})
