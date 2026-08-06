import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ChaptersSection from './ChaptersSection.vue'

const mockChapters = [
  { chapter_number: 1, title: '第一章·雾起', summary: '林七踏入雾港', word_count: 2500 },
  { chapter_number: 2, title: '第二章·暗流', summary: '发现盐痕线索', word_count: 3100 },
]

describe('ChaptersSection', () => {
  it('renders chapter list with correct count', () => {
    const wrapper = mount(ChaptersSection, {
      props: {
        projectId: 'p-1',
        chapters: mockChapters,
        selectedChapter: null,
      },
    })

    expect(wrapper.text()).toContain('第一章')
    expect(wrapper.text()).toContain('第二章')
    expect(wrapper.text()).toContain('篇')
  })

  it('shows export buttons', () => {
    const wrapper = mount(ChaptersSection, {
      props: {
        projectId: 'p-1',
        chapters: mockChapters,
        selectedChapter: null,
      },
    })

    const buttons = wrapper.findAll('button')
    const txtBtn = buttons.find(b => b.text().includes('TXT'))
    const docxBtn = buttons.find(b => b.text().includes('DOCX'))
    expect(txtBtn).toBeTruthy()
    expect(docxBtn).toBeTruthy()
  })

  it('emits selectChapter when chapter clicked', async () => {
    const wrapper = mount(ChaptersSection, {
      props: {
        projectId: 'p-1',
        chapters: mockChapters,
        selectedChapter: null,
      },
    })

    const chapterButtons = wrapper.findAll('button')
    const ch1Btn = chapterButtons.find(b => b.text().includes('第一章'))
    expect(ch1Btn).toBeTruthy()
    await ch1Btn!.trigger('click')
    expect(wrapper.emitted('selectChapter')).toBeTruthy()
  })
})
