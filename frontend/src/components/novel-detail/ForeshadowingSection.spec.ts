import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ForeshadowingSection from './ForeshadowingSection.vue'

const { getForeshadowingsMock, getRemindersMock, getAnalysisMock } = vi.hoisted(() => ({
  getForeshadowingsMock: vi.fn(),
  getRemindersMock: vi.fn(),
  getAnalysisMock: vi.fn(),
}))

vi.mock('@/api/novel', () => ({
  ForeshadowingAPI: {
    getForeshadowings: getForeshadowingsMock,
    getReminders: getRemindersMock,
    getAnalysis: getAnalysisMock,
  },
}))

describe('ForeshadowingSection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getForeshadowingsMock.mockResolvedValue({
      total: 3,
      limit: 100,
      offset: 0,
      data: [
        {
          id: 1,
          name: '盐痕账册',
          chapter_number: 2,
          content: '主角在祠堂账册上看见盐痕编号。',
          type: 'mystery',
          status: 'planted',
          target_reveal_chapter: 5,
          reveal_method: '让守灯人用同一串编号打开暗柜。',
          reveal_impact: '证明账册不是旧物，而是仍在运转的控制系统。',
          related_characters: ['沈文朝', '守灯人'],
          urgency: 9,
          resolved_chapter_number: null,
          is_manual: false,
          ai_confidence: 0.9,
          author_note: null,
          created_at: '2026-05-21T02:00:00Z',
        },
        {
          id: 2,
          chapter_number: 4,
          content: '铜铃只在退潮后响。',
          type: 'hint',
          status: 'developing',
          target_reveal_chapter: 9,
          resolved_chapter_number: null,
          is_manual: false,
          ai_confidence: 0.8,
          author_note: null,
          created_at: '2026-05-21T03:00:00Z',
        },
        {
          id: 3,
          chapter_number: 1,
          content: '潮歌第二遍的歌词。',
          type: 'setup',
          status: 'resolved',
          resolved_chapter_number: 5,
          is_manual: true,
          ai_confidence: null,
          author_note: '已回收',
          created_at: '2026-05-21T01:00:00Z',
        },
      ],
    })
    getRemindersMock.mockResolvedValue({
      total: 1,
      data: [{
        id: 11,
        foreshadowing_id: 1,
        reminder_type: 'payoff_due',
        message: '盐痕账册已到回收窗口。',
        status: 'active',
        suggested_chapter_range: { start: 5, end: 6 },
        created_at: '2026-05-21T04:00:00Z',
      }],
    })
    getAnalysisMock.mockResolvedValue({
      total_foreshadowings: 3,
      resolved_count: 1,
      unresolved_count: 2,
      abandoned_count: 0,
      avg_resolution_distance: 4,
      unresolved_ratio: 0.67,
      overall_quality_score: 7.2,
      recommendations: ['优先回收盐痕账册。'],
      pattern_analysis: {},
      analyzed_at: '2026-05-21T04:00:00Z',
    })
  })

  it('把逾期和高紧迫伏笔提升为下章必须处理任务', async () => {
    const wrapper = mount(ForeshadowingSection, {
      props: { projectId: 'project-1' },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('下章必须处理')
    expect(wrapper.text()).toContain('盐痕账册')
    expect(wrapper.text()).toContain('高紧迫')
    expect(wrapper.text()).toContain('回收方式：让守灯人用同一串编号打开暗柜。')
    expect(wrapper.text()).toContain('局部补丁建议')
    expect(wrapper.text()).toContain('建议第 5-6 章处理')
    expect(wrapper.text()).toContain('下章任务')

    wrapper.unmount()
  })
})
