import { shallowMount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ChapterContent from './ChapterContent.vue'

const chapter = (allowedActions: string[] = []) => ({
  chapter_number: 3,
  title: '第三章',
  content: '正文内容',
  versions: [],
  allowed_actions: allowedActions,
}) as any

describe('ChapterContent finalize recovery', () => {
  it('定稿账本降级后显示真实可点击的重试入口', async () => {
    const wrapper = shallowMount(ChapterContent, {
      props: { selectedChapter: chapter(['refresh_status', 'retry_finalize']) },
    })

    const button = wrapper.findAll('button').find((item) => item.text().includes('重试账本同步'))
    expect(button).toBeTruthy()
    await button!.trigger('click')
    expect(wrapper.emitted('retryFinalize')).toEqual([[3]])
  })

  it('正常定稿不显示账本重试入口', () => {
    const wrapper = shallowMount(ChapterContent, {
      props: { selectedChapter: chapter(['refresh_status', 'view_versions']) },
    })
    expect(wrapper.text()).not.toContain('重试账本同步')
  })
})