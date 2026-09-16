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


  it('正文已保留但保障降级时展示定稿风险与后续动作', () => {
    const wrapper = shallowMount(ChapterContent, {
      props: {
        selectedChapter: chapter(['refresh_status', 'retry_ledger_sync']),
        generationRuntime: {
          review_status: 'skipped',
          consistency_status: 'warning',
          review_skip_reason: '本次运行未启用评审',
          degraded_stages: [{ stage: 'ledger_memory', reason: '记忆账本同步超时' }],
          allowed_actions: ['refresh_status', 'retry_ledger_sync'],
        },
      },
    })

    expect(wrapper.find('[data-testid="chapter-assurance-card"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('正文已保留')
    expect(wrapper.text()).toContain('记忆层')
    expect(wrapper.text()).toContain('记忆账本同步超时')
    expect(wrapper.text()).toContain('重试保障流程')
  })

  it('质量正常且无降级时不显示定稿风险卡', () => {
    const wrapper = shallowMount(ChapterContent, {
      props: { selectedChapter: chapter(['refresh_status']), generationRuntime: { review_status: 'passed', consistency_status: 'passed', word_requirement_met: true } },
    })

    expect(wrapper.find('[data-testid="chapter-assurance-card"]').exists()).toBe(false)
  })

  it('包含操作按钮', () => {
    const wrapper = shallowMount(ChapterContent, {
      props: { selectedChapter: chapter(['refresh_status', 'view_versions']) },
    })

    const buttons = wrapper.findAll('button')
    expect(buttons.length).toBeGreaterThan(0)
  })
})
