import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ChapterFailed from './ChapterFailed.vue'

describe('ChapterFailed', () => {
  it('展示章节失败状态并提示主操作已收口到顶部', () => {
    const wrapper = mount(ChapterFailed, {
      props: {
        chapterNumber: 2,
        generatingChapter: null
      }
    })

    expect(wrapper.text()).toContain('第 2 章处理失败')
    expect(wrapper.text()).toContain('章节异常恢复')
    expect(wrapper.text()).toContain('主操作已收口到顶部')
    expect(wrapper.text()).toContain('去顶部操作')
    expect(wrapper.get('.cf-hint').classes()).not.toContain('cf-hint--busy')
  })

  it('当前章节正在重试时展示顶部处理中提示', () => {
    const wrapper = mount(ChapterFailed, {
      props: {
        chapterNumber: 2,
        generatingChapter: 2
      }
    })

    expect(wrapper.text()).toContain('顶部主操作执行中')
    expect(wrapper.text()).toContain('处理中')
    expect(wrapper.get('.cf-hint').classes()).toContain('cf-hint--busy')
  })

  it('展示后端失败摘要和诊断 metadata', () => {
    const wrapper = mount(ChapterFailed, {
      props: {
        chapterNumber: 3,
        generatingChapter: null,
        lastErrorSummary: '大纲硬筛未通过：第 3 章缺少冲突推进',
        generationRuntime: {
          diagnostics: {
            code: 'OUTLINE_GENERATION_QUALITY_REJECTED',
            rootCause: '章节缺少目标、阻碍、转折',
            requestId: 'req-123',
            retryable: true,
            hint: '重写章节导演脚本'
          },
          events: [
            {
              level: 'error',
              metadata: {
                missing_chapters: [3],
                rejection_summary: { retry_count: 3 }
              }
            }
          ]
        }
      }
    })

    expect(wrapper.text()).toContain('后端错误摘要')
    expect(wrapper.text()).toContain('大纲硬筛未通过')
    expect(wrapper.text()).toContain('OUTLINE_GENERATION_QUALITY_REJECTED')
    expect(wrapper.text()).toContain('req-123')
    expect(wrapper.text()).toContain('章节缺少目标')
    expect(wrapper.text()).toContain('重写章节导演脚本')
  })

  it('把可重试诊断和章节动作投影为直接重试语义', () => {
    const wrapper = mount(ChapterFailed, {
      props: {
        chapterNumber: 4,
        generatingChapter: null,
        chapter: { allowed_actions: ['refresh_status', 'retry_generation'] } as any,
        generationRuntime: { diagnostics: { retryable: true } }
      }
    })

    expect(wrapper.text()).toContain('可直接重试')
    expect(wrapper.text()).toContain('重新生成')
    expect(wrapper.text()).not.toContain('请先处理根因')
    wrapper.get('.cf-action').trigger('click')
    expect(wrapper.emitted('refreshStatus')).toHaveLength(1)
  })

  it('候选恢复动作优先于重新生成并支持打开候选版本', async () => {
    const wrapper = mount(ChapterFailed, {
      props: {
        chapterNumber: 5,
        generatingChapter: null,
        chapter: { allowed_actions: ['refresh_status', 'confirm_version', 'review_versions', 'retry_generation'] } as any,
        generationRuntime: { diagnostics: { retryable: true } }
      }
    })

    expect(wrapper.text()).toContain('候选正文仍可恢复')
    expect(wrapper.text()).toContain('可确认候选版本')
    expect(wrapper.text()).toContain('可重新评审候选')
    await wrapper.get('.cf-recovery__actions .cf-action:nth-child(2)').trigger('click')
    expect(wrapper.emitted('openVersionSelector')).toHaveLength(1)
  })

  it('章节级动作覆盖运行态 fallback，且不可重试时提示先处理根因', () => {
    const wrapper = mount(ChapterFailed, {
      props: {
        chapterNumber: 6,
        generatingChapter: null,
        chapter: { allowed_actions: ['refresh_status'] } as any,
        generationRuntime: { allowed_actions: ['retry_generation'], diagnostics: { retryable: false, rootCause: '任务书缺少冲突' } }
      }
    })

    expect(wrapper.text()).toContain('请先处理根因')
    expect(wrapper.text()).not.toContain('可直接重试')
    expect(wrapper.text()).toContain('任务书缺少冲突')
  })

})
