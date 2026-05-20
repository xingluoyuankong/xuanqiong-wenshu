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
    expect(wrapper.text()).toContain('请使用顶部主命令栏开始生成')
    expect(wrapper.find('button.ce-primary').exists()).toBe(false)
    expect(wrapper.emitted('generateChapter')).toBeUndefined()
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
