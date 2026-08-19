import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import GlobalNavBar from './GlobalNavBar.vue'

const { pushMock, routeName, query, authState, novelStoreMock, taskRuntimeMock } = vi.hoisted(() => ({
  pushMock: vi.fn(),
  routeName: { value: 'workspace-entry' as string },
  query: { value: {} as Record<string, string> },
  authState: { value: { isAdmin: false } },
  novelStoreMock: {
    currentProject: null as Record<string, unknown> | null,
    loadProject: vi.fn(),
  },
  taskRuntimeMock: {
    listTasks: vi.fn(),
    cancelTask: vi.fn(),
    retryTask: vi.fn(),
  },
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: pushMock, back: vi.fn() }),
  useRoute: () => ({ name: routeName.value, query: query.value, params: {}, fullPath: '/' }),
}))

vi.mock('@/composables/useLocale', () => ({
  pick: (zh: string, _en: string) => zh,
  useLocale: () => ({ languageLabel: '中文', switchLabel: '切换到英文', toggleLocale: vi.fn() }),
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => authState.value,
}))

vi.mock('@/stores/novel', () => ({
  useNovelStore: () => novelStoreMock,
}))

vi.mock('@/api/task-runtime', () => ({
  TaskRuntimeAPI: taskRuntimeMock,
}))

vi.mock('@/utils/safeNavigation', () => ({
  navigateBackOrFallback: vi.fn(),
}))

const mountComponent = () => mount(GlobalNavBar)
const mountedWrappers: Array<{ unmount: () => void }> = []

const mountTrackedComponent = () => {
  const wrapper = mountComponent()
  mountedWrappers.push(wrapper)
  return wrapper
}

describe('GlobalNavBar', () => {
  afterEach(() => {
    mountedWrappers.splice(0).forEach((wrapper) => wrapper.unmount())
  })

  beforeEach(() => {
    pushMock.mockReset()
    routeName.value = 'workspace-entry'
    query.value = {}
    authState.value = { isAdmin: false }
    novelStoreMock.currentProject = null
    novelStoreMock.loadProject.mockReset()
    novelStoreMock.loadProject.mockResolvedValue(undefined)
    taskRuntimeMock.listTasks.mockReset()
    taskRuntimeMock.listTasks.mockResolvedValue([])
    taskRuntimeMock.cancelTask.mockReset()
    taskRuntimeMock.retryTask.mockReset()
    localStorage.clear()
  })

  it('核心入口会导航到对应工作区', async () => {
    const wrapper = mountTrackedComponent()

    await wrapper.get('button[title="项目"]').trigger('click')
    await wrapper.get('button[title="灵感与蓝图"]').trigger('click')
    await wrapper.get('button[title="文风中心"]').trigger('click')
    await wrapper.get('button[title="模型配置"]').trigger('click')
    await wrapper.get('button[title="设置"]').trigger('click')

    expect(pushMock).toHaveBeenNthCalledWith(1, { name: 'novel-workspace' })
    expect(pushMock).toHaveBeenNthCalledWith(2, { name: 'inspiration-mode' })
    expect(pushMock).toHaveBeenNthCalledWith(3, { name: 'style-center' })
    expect(pushMock).toHaveBeenNthCalledWith(4, { name: 'llm-settings' })
    expect(pushMock).toHaveBeenNthCalledWith(5, { name: 'settings' })
  })

  it('项目类页面统一高亮项目并输出 aria-current', () => {
    routeName.value = 'writing-desk'
    const wrapper = mountTrackedComponent()
    const projectButton = wrapper.get('button[title="项目"]')

    expect(projectButton.classes()).toContain('global-nav-item--active')
    expect(projectButton.attributes('aria-current')).toBe('page')
  })

  it('只有管理员看到运行监控入口', async () => {
    const normalWrapper = mountTrackedComponent()
    expect(normalWrapper.find('button[title="运行监控"]').exists()).toBe(false)

    authState.value = { isAdmin: true }
    const adminWrapper = mountTrackedComponent()
    await flushPromises()
    expect(adminWrapper.find('button[title="运行监控"]').exists()).toBe(true)
    await adminWrapper.get('button[title="运行监控"]').trigger('click')
    expect(pushMock).toHaveBeenCalledWith({ name: 'admin' })
  })

  it('进度条提供任务名称和可读数值语义', () => {
    novelStoreMock.currentProject = {
      id: 'project-1',
      title: '星河旧梦',
      chapters: [{
        id: 'chapter-1',
        chapter_number: 1,
        generation_status: 'generating',
        generation_runtime: {
          status: 'running',
          progress_percent: 42,
          progress_stage: 'writing',
          progress_message: '正在写作',
        },
      }],
    }
    const wrapper = mountTrackedComponent()
    const progressbar = wrapper.find('[role="progressbar"]')

    expect(progressbar.exists()).toBe(true)
    expect(progressbar.attributes('aria-label')).toContain('生成进度')
    expect(progressbar.attributes('aria-valuenow')).toBe('42')
  })

  it('优先显示持久化任务，并能取消运行中的任务', async () => {
    taskRuntimeMock.listTasks.mockResolvedValue([{
      task_id: 'runtime-1',
      project_id: 'project-1',
      task_type: 'research',
      status: 'running',
      stage: 'running',
      progress: 37,
      message: '正在收集资料',
      retry_count: 0,
      max_retries: 2,
      event_cursor: 3,
      created_at: '2026-08-14T10:00:00.000Z',
      updated_at: '2026-08-14T10:00:01.000Z',
    }])
    taskRuntimeMock.cancelTask.mockResolvedValue({
      task_id: 'runtime-1',
      project_id: 'project-1',
      task_type: 'research',
      status: 'cancelling',
      stage: 'cancelling',
      progress: 37,
      message: '正在取消',
      retry_count: 0,
      max_retries: 2,
      event_cursor: 4,
      created_at: '2026-08-14T10:00:00.000Z',
      updated_at: '2026-08-14T10:00:02.000Z',
    })
    novelStoreMock.currentProject = { id: 'project-1', title: '星河旧梦', chapters: [] }
    const wrapper = mountTrackedComponent()
    await flushPromises()

    expect(wrapper.get('.global-task-mini__title').text()).toContain('资料收集')
    expect(wrapper.get('[role="progressbar"]').attributes('aria-valuenow')).toBe('37')
    await wrapper.get('button').trigger('click')
    const cancelButton = wrapper.get('.global-task-mini__actions button:nth-child(2)')
    expect(cancelButton.text()).toContain('取消任务')
    await cancelButton.trigger('click')
    expect(taskRuntimeMock.cancelTask).toHaveBeenCalledWith('runtime-1')
  })
})
