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
})
