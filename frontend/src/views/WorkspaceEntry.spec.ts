import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import WorkspaceEntry from './WorkspaceEntry.vue'

const { pushMock, novelStoreMock } = vi.hoisted(() => ({
  pushMock: vi.fn(),
  novelStoreMock: {
    projects: [] as Array<Record<string, unknown>>,
    loadProjects: vi.fn(),
  },
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: pushMock }),
}))

vi.mock('@/stores/novel', () => ({
  useNovelStore: () => novelStoreMock,
}))

const project = (overrides: Record<string, unknown> = {}) => ({
  id: 'project-1',
  title: '星河旧梦',
  last_edited: '2026-08-14T10:00:00.000Z',
  total_chapters: 12,
  completed_chapters: 4,
  ...overrides,
})

const mountComponent = () => mount(WorkspaceEntry)

describe('WorkspaceEntry', () => {
  beforeEach(() => {
    pushMock.mockReset()
    novelStoreMock.projects = []
    novelStoreMock.loadProjects.mockReset()
    novelStoreMock.loadProjects.mockResolvedValue(undefined)
  })

  it('有最近项目时把继续写作作为首屏焦点，并进入项目详情', async () => {
    novelStoreMock.projects = [project()]

    const wrapper = mountComponent()
    await flushPromises()

    expect(wrapper.get('h1').text()).toContain('可连载的完整小说工程')
    expect(wrapper.get('[data-testid="hero-next-step"]').text()).toContain('星河旧梦')
    expect(wrapper.get('[data-testid="hero-next-step"]').text()).toContain('4/12 章')

    await wrapper.get('[data-testid="hero-continue"]').trigger('click')

    expect(pushMock).toHaveBeenCalledWith('/novel/project-1')
  })

  it('没有项目时提供创建第一部小说的焦点入口', async () => {
    const wrapper = mountComponent()
    await flushPromises()

    expect(wrapper.get('[data-testid="hero-next-step"]').text()).toContain('从灵感开始')
    await wrapper.get('[data-testid="hero-create"]').trigger('click')

    expect(pushMock).toHaveBeenCalledWith('/inspiration')
  })

  it('快速入口仍按既有路由导航', async () => {
    const wrapper = mountComponent()
    await flushPromises()

    await wrapper.get('[data-testid="entry-function-style"]').trigger('click')

    expect(pushMock).toHaveBeenCalledWith('/style-center')
  })
})
