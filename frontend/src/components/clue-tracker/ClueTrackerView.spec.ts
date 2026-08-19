import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ClueTrackerView from './ClueTrackerView.vue'

const { getOverviewMock } = vi.hoisted(() => ({
  getOverviewMock: vi.fn(),
}))

vi.mock('@/api/novel', () => ({
  ClueTrackerAPI: {
    getOverview: getOverviewMock,
  },
}))

describe('ClueTrackerView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getOverviewMock.mockResolvedValue({
      project_id: 'project-1',
      clues: [
        {
          id: 11,
          name: '盐痕账册',
          clue_type: 'key_evidence',
          description: '账册上的盐痕编号',
          importance: 5,
          planted_chapter: 1,
          resolution_chapter: null,
          status: 'active',
          is_red_herring: false,
          clue_content: 'salt-code',
          hint_level: 2,
          design_intent: '后续回收',
        },
      ],
      analysis: {
        project_id: 'project-1',
        total_clues: 1,
        type_counts: { key_evidence: 1 },
        status_counts: { active: 1 },
        red_herring_count: 0,
        unresolved_count: 1,
        threads: [{ thread_type: 'key_evidence', clue_count: 1, clue_ids: [11] }],
      },
      sync: { created: 0 },
    })
  })

  it('通过一次 overview 快照加载线索列表和分析，避免状态错位', async () => {
    const wrapper = mount(ClueTrackerView, {
      props: { projectId: 'project-1' },
    })

    await flushPromises()

    expect(getOverviewMock).toHaveBeenCalledTimes(1)
    expect(getOverviewMock).toHaveBeenCalledWith('project-1')
    expect(wrapper.text()).toContain('盐痕账册')
    expect(wrapper.text()).toContain('1')
  })
})
