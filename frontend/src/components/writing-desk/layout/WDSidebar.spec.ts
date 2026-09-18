import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import WDSidebar from './WDSidebar.vue'

const buildProject = (
  status: 'waiting_for_confirm' | 'successful' | 'failed' | 'not_generated' = 'waiting_for_confirm'
) => ({
  blueprint: {
    chapter_outline: [
      {
        chapter_number: 1,
        title: '第一章',
        summary: '章节摘要',
      },
    ],
  },
  chapters: [
    {
      chapter_number: 1,
      title: '第一章',
      summary: '章节摘要',
      word_count: 1200,
      versions: [{ id: 1, content: '候选正文' }],
      generation_status: status,
      generation_runtime: {
        quality_metrics: {
          scene_fulfillment_rate: 0.25,
          dialogue_changes_state: false,
          ending_pressure_passed: false,
          static_description_risk: true,
        }
      },
    },
  ],
})

describe('WDSidebar', () => {
  it('展示当前章节质量风险摘要', () => {
    const wrapper = mount(WDSidebar, {
      props: {
        project: buildProject('waiting_for_confirm') as any,
        sidebarOpen: true,
        selectedChapterNumber: 1,
        generatingChapter: null,
        evaluatingChapter: null,
        isGeneratingOutline: false,
        workspaceSummary: null,
      },
    })

    expect(wrapper.text()).toContain('质量风险 4 项')
  })

  it('侧栏不再重复渲染候选版本或生成类主按钮', () => {
    const waitingWrapper = mount(WDSidebar, {
      props: {
        project: buildProject('waiting_for_confirm') as any,
        sidebarOpen: true,
        selectedChapterNumber: 1,
        generatingChapter: null,
        evaluatingChapter: null,
        isGeneratingOutline: false,
        workspaceSummary: null,
      },
    })

    const failedWrapper = mount(WDSidebar, {
      props: {
        project: buildProject('failed') as any,
        sidebarOpen: true,
        selectedChapterNumber: 1,
        generatingChapter: null,
        evaluatingChapter: null,
        isGeneratingOutline: false,
        workspaceSummary: null,
      },
    })

    const waitingButtonTexts = waitingWrapper.findAll('button').map((button) => button.text())
    const failedButtonTexts = failedWrapper.findAll('button').map((button) => button.text())

    expect(waitingButtonTexts).not.toContain('查看当前结果')
    expect(waitingButtonTexts).not.toContain('查看候选结果')
    expect(failedButtonTexts).not.toContain('重新生成')
    expect(failedWrapper.text()).toContain('主操作已收口到顶部')
  })

  it('章节已完成时仍显示并允许点击“编辑当前大纲”', async () => {
    const wrapper = mount(WDSidebar, {
      props: {
        project: buildProject('successful') as any,
        sidebarOpen: true,
        selectedChapterNumber: 1,
        generatingChapter: null,
        evaluatingChapter: null,
        isGeneratingOutline: false,
        workspaceSummary: null,
      },
    })

    const editButton = wrapper.findAll('button').find((button) => button.text() === '编辑当前大纲')
    expect(editButton).toBeTruthy()

    await editButton!.trigger('click')

    expect(wrapper.emitted('editChapter')?.[0]?.[0]).toMatchObject({
      chapter_number: 1,
      title: '第一章',
    })
  })
})
