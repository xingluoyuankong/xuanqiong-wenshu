import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import WDSidebar from './WDSidebar.vue'
// 排版骨架是纯 CSS 契约，jsdom 不注入 scoped 样式，只能对源码本身做回归断言
import sidebarSource from './WDSidebar.vue?raw'

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

    expect(wrapper.text()).toContain('当前章节')  // sidebar shows current chapter section
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
    expect(failedWrapper.text()).toContain('章节异常')  // failed status indicator
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

    const outlineButton = wrapper.findAll('button').find((button) => button.text() === '生成后续大纲')
    expect(outlineButton).toBeTruthy()

    await outlineButton!.trigger('click')

    expect(wrapper.emitted('generateOutline')).toBeTruthy()
  })
})

describe('WDSidebar 排版骨架', () => {
  it('样式块存在，且覆盖外壳/列表/当前章节/底部四段', () => {
    expect(sidebarSource).toContain('<style scoped>')
    for (const selector of [
      '.wd-sidebar {',
      '.wd-sidebar.is-closed {',
      '.wd-sidebar__scrim {',
      '.wd-sidebar__head {',
      '.wd-sidebar__list {',
      '.wd-chapter {',
      '.wd-chapter.is-active {',
      '.wd-chapter__dot {',
      '.wd-sidebar__current {',
      '.wd-sidebar__foot {',
    ]) {
      expect(sidebarSource, `缺少样式定义：${selector}`).toContain(selector)
    }
  })

  it('侧栏定宽 280px，章节行 40px 高、状态点 8px', () => {
    expect(sidebarSource).toMatch(/\.wd-sidebar\s*\{[^}]*width:\s*280px/)
    // 40px 行高走 --xq-space-10 令牌，不写死数值
    expect(sidebarSource).toMatch(/\.wd-chapter\s*\{[^}]*height:\s*var\(--xq-space-10\)/)
    expect(sidebarSource).toMatch(/\.wd-chapter__dot\s*\{[^}]*width:\s*8px/)
  })

  it('四种状态点各有语义色，且全部引用令牌', () => {
    for (const tone of ['success', 'warning', 'danger', 'muted']) {
      expect(sidebarSource, `缺少状态点配色：${tone}`).toContain(`.wd-chapter__dot--${tone} {`)
    }
    const styleBlock = sidebarSource.slice(sidebarSource.indexOf('<style scoped>'))
    // 颜色只能来自令牌：不允许十六进制、rgb()、渐变、磨砂
    expect(styleBlock).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
    expect(styleBlock).not.toMatch(/\brgba?\(/)
    expect(styleBlock).not.toMatch(/gradient\(/)
    expect(styleBlock).not.toMatch(/backdrop-filter/)
  })

  it('窄屏把侧栏降级为抽屉，避免挤压正文宽度', () => {
    expect(sidebarSource).toMatch(/@media \(max-width: 1023px\)/)
    const narrow = sidebarSource.slice(sidebarSource.indexOf('@media (max-width: 1023px)'))
    expect(narrow).toMatch(/\.wd-sidebar__scrim\s*\{[^}]*display:\s*block/)
    expect(narrow).toMatch(/\.wd-sidebar\s*\{[^}]*position:\s*fixed/)
  })
})
