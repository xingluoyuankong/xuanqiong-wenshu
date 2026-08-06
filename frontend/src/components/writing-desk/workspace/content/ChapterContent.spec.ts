import { shallowMount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ChapterContent from './ChapterContent.vue'

const chapter = (allowedActions: string[] = []) => ({
  chapter_number: 3,
  title: '第三章',
  content: '正文内容',
  versions: [],
  allowed_actions: allowedActions,
  generation_status: 'successful',
}) as any

describe('ChapterContent', () => {
  it('渲染章节正文内容', () => {
    const wrapper = shallowMount(ChapterContent, {
      props: { selectedChapter: chapter(['refresh_status', 'view_versions']) },
    })

    expect(wrapper.text()).toContain('正文内容')
    expect(wrapper.text()).toContain('第三章')
  })

  it('包含操作按钮', () => {
    const wrapper = shallowMount(ChapterContent, {
      props: { selectedChapter: chapter(['refresh_status', 'view_versions']) },
    })

    const buttons = wrapper.findAll('button')
    expect(buttons.length).toBeGreaterThan(0)
  })
})
