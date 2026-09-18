import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { describe, expect, it, beforeEach } from 'vitest'

import WDGenerateChapterModal from './WDGenerateChapterModal.vue'

const buildWrapper = () => mount(WDGenerateChapterModal, {
  props: {
    show: true,
    projectId: 'project-1',
    chapterNumber: 3,
  },
  global: {
    stubs: {
      TransitionRoot: { template: '<div><slot /></div>' },
      TransitionChild: { template: '<div><slot /></div>' },
      Dialog: { template: '<div><slot /></div>' },
      DialogPanel: { template: '<div><slot /></div>' },
      DialogTitle: { template: '<div><slot /></div>' },
    },
  },
})

describe('WDGenerateChapterModal', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('初次挂载且 show=true 时会立即读取本章已保存配置', async () => {
    window.localStorage.setItem(
      'xuanqiong_wenshu:chapter_generation:project-1:3',
      JSON.stringify({
        writingNotes: '推进主线冲突',
        qualityRequirements: '对白更有张力',
        minWordCount: 3100,
        targetWordCount: 3600,
      })
    )

    const wrapper = buildWrapper()
    await nextTick()

    const textareas = wrapper.findAll('textarea')
    const numberInputs = wrapper.findAll('input[type="number"]')

    expect((textareas[0].element as HTMLTextAreaElement).value).toBe('推进主线冲突')
    expect((textareas[1].element as HTMLTextAreaElement).value).toBe('对白更有张力')
    expect((numberInputs[0].element as HTMLInputElement).value).toBe('3100')
    expect((numberInputs[1].element as HTMLInputElement).value).toBe('3600')
    expect(wrapper.text()).toContain('已加载本章配置（浏览器本地）')
  })
})
