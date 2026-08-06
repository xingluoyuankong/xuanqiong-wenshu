import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import KnowledgeGraphView from './KnowledgeGraphView.vue'

const { getFullGraphMock, analyzePlotThreadsMock } = vi.hoisted(() => ({
  getFullGraphMock: vi.fn(),
  analyzePlotThreadsMock: vi.fn(),
}))

vi.mock('@/api/novel', () => ({
  KnowledgeGraphAPI: {
    getFullGraph: getFullGraphMock,
    analyzePlotThreads: analyzePlotThreadsMock,
  },
}))

describe('KnowledgeGraphView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getFullGraphMock.mockResolvedValue({
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
    })
    analyzePlotThreadsMock.mockResolvedValue([
      {
        thread_id: 't1',
        title: '主线',
        characters: ['林七'],
        key_events: ['废桥对峙'],
      },
    ])
  })

  it('通过 getFullGraph 请求加载图谱和剧情线', async () => {
    const wrapper = mount(KnowledgeGraphView, {
      props: { projectId: 'project-1' },
    })

    await flushPromises()

    expect(getFullGraphMock).toHaveBeenCalledTimes(1)
    expect(getFullGraphMock).toHaveBeenCalledWith('project-1')
    expect(analyzePlotThreadsMock).toHaveBeenCalled()
    expect(wrapper.text()).toContain('林七')
    expect(wrapper.text()).toContain('1')  // node_count displayed
  })
})
