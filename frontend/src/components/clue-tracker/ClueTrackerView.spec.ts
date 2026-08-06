import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ClueTrackerView from './ClueTrackerView.vue'

const { getProjectCluesMock, analyzeClueThreadsMock } = vi.hoisted(() => ({
  getProjectCluesMock: vi.fn(),
  analyzeClueThreadsMock: vi.fn(),
}))

vi.mock('@/api/novel', () => ({
  ClueTrackerAPI: {
    getProjectClues: getProjectCluesMock,
    analyzeClueThreads: analyzeClueThreadsMock,
  },
}))

describe('ClueTrackerView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getProjectCluesMock.mockResolvedValue([
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
    ])
    analyzeClueThreadsMock.mockResolvedValue({
      project_id: 'project-1',
      total_clues: 1,
      type_counts: { key_evidence: 1 },
      status_counts: { active: 1 },
      red_herring_count: 0,
      unresolved_count: 1,
      threads: [{ thread_type: 'key_evidence', clue_count: 1, clue_ids: [11] }],
    })
  })

  it('通过 getProjectClues + analyzeClueThreads 请求加载线索列表和分析', async () => {
    const wrapper = mount(ClueTrackerView, {
      props: { projectId: 'project-1' },
    })

    await flushPromises()

    expect(getProjectCluesMock).toHaveBeenCalledTimes(1)
    expect(getProjectCluesMock).toHaveBeenCalledWith('project-1')
    expect(analyzeClueThreadsMock).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('盐痕账册')
    expect(wrapper.text()).toContain('1')
  })
})
