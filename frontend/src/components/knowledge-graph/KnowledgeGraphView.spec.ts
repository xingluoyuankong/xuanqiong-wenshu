import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import KnowledgeGraphView from './KnowledgeGraphView.vue'

const { getOverviewMock } = vi.hoisted(() => ({
  getOverviewMock: vi.fn(),
}))

vi.mock('@/api/novel', () => ({
  KnowledgeGraphAPI: {
    getOverview: getOverviewMock,
  },
}))

describe('KnowledgeGraphView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getOverviewMock.mockResolvedValue({
      project_id: 'project-1',
      graph: {
        project_id: 'project-1',
        nodes: [
          {
            id: 1,
            name: '林七',
            role_type: 'protagonist',
            description: '主角',
            lifecycle: 'active',
            first_chapter: 1,
            latest_chapter: 3,
            confidence: 90,
            relationship_count: 1,
            fact_source: 'blueprint_character',
            fact_source_label: '蓝图角色',
          },
        ],
        edges: [
          {
            id: 2,
            source_id: 1,
            target_id: 1,
            source_name: '林七',
            target_name: '林七',
            event_type: 'conflict',
            description: '废桥对峙',
            importance: 8,
            fact_source: 'timeline_event',
            fact_source_label: '时间线事件',
          },
        ],
        node_count: 1,
        edge_count: 1,
      },
      threads: [
        {
          thread_id: 't1',
          title: '主线',
          characters: ['林七'],
          events: [{ description: '废桥对峙' }],
          chapter_range: [1, 3],
        },
      ],
      thread_count: 1,
      sync: { created_nodes: 0 },
    })
  })

  it('通过一次 overview 快照加载图谱和剧情线，避免重复同步', async () => {
    const wrapper = mount(KnowledgeGraphView, {
      props: { projectId: 'project-1' },
    })

    await flushPromises()

    expect(getOverviewMock).toHaveBeenCalledTimes(1)
    expect(getOverviewMock).toHaveBeenCalledWith('project-1')
    expect(wrapper.text()).toContain('林七')
    expect(wrapper.text()).toContain('1')  // node_count displayed
  })
})
