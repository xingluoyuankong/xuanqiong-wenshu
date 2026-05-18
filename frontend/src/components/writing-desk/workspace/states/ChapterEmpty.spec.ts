import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ChapterEmpty from './ChapterEmpty.vue'

describe('ChapterEmpty', () => {
  it('可生成时展示生成路径并发出章节号', async () => {
    const wrapper = mount(ChapterEmpty, {
      props: {
        chapterNumber: 3,
        generatingChapter: null,
        canGenerate: true
      }
    })

    expect(wrapper.text()).toContain('第 3 章还没有正文')
    expect(wrapper.text()).toContain('开始生成第 3 章')

    await wrapper.get('button.ce-primary').trigger('click')
    expect(wrapper.emitted('generateChapter')?.[0]).toEqual([3])
  })

  it('未解锁时不展示生成按钮', () => {
    const wrapper = mount(ChapterEmpty, {
      props: {
        chapterNumber: 4,
        generatingChapter: null,
        canGenerate: false
      }
    })

    expect(wrapper.text()).toContain('请按顺序推进章节')
    expect(wrapper.find('button.ce-primary').exists()).toBe(false)
  })
})
