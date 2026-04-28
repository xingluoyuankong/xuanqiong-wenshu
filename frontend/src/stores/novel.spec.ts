import { setActivePinia, createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  editChapterContent: vi.fn(),
  getNovel: vi.fn(),
}))

vi.mock('@/api/novel', () => ({
  NovelAPI: {
    getNovel: apiMocks.getNovel,
  },
  OptimizerAPI: {},
}))

vi.mock('@/api/modules/chapterEditing', () => ({
  editChapterContent: apiMocks.editChapterContent,
}))

vi.mock('@/stores/notification', () => ({
  useNotificationStore: () => ({
    success: vi.fn(),
    error: vi.fn(),
  }),
}))

import { useNovelStore } from './novel'

const buildProject = () => ({
  id: 'project-1',
  title: '测试项目',
  initial_prompt: 'prompt',
  conversation_history: [],
  chapters: [
    {
      chapter_number: 1,
      title: '第一章',
      summary: '摘要',
      content: '旧内容',
      versions: [
        { id: 1, content: '旧内容', style: '标准' },
        { id: 2, content: '旧备选', style: '标准' },
      ],
      evaluation: null,
      generation_status: 'successful' as const,
      word_count: 3,
    },
  ],
})

describe('novel store loadProject', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setActivePinia(createPinia())
  })

  it('旧项目请求后返回时不会覆盖新项目', async () => {
    const store = useNovelStore()

    let resolveFirst: ((value: any) => void) | undefined
    let resolveSecond: ((value: any) => void) | undefined

    apiMocks.getNovel
      .mockImplementationOnce(() => new Promise(resolve => { resolveFirst = resolve }))
      .mockImplementationOnce(() => new Promise(resolve => { resolveSecond = resolve }))

    const firstPromise = store.loadProject('project-old')
    const secondPromise = store.loadProject('project-new')

    if (resolveSecond) resolveSecond({ id: 'project-new', title: '新项目', chapters: [] })
    await secondPromise

    expect(store.currentProject?.id).toBe('project-new')
    expect(store.isLoading).toBe(false)

    if (resolveFirst) resolveFirst({ id: 'project-old', title: '旧项目', chapters: [] })
    await firstPromise

    expect(store.currentProject?.id).toBe('project-new')
    expect(store.error).toBeNull()
    expect(store.isLoading).toBe(false)
  })

  it('旧项目请求失败后返回时不会污染当前错误状态', async () => {
    const store = useNovelStore()

    let rejectFirst: ((reason?: any) => void) | undefined
    let resolveSecond: ((value: any) => void) | undefined

    apiMocks.getNovel
      .mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectFirst = reject }))
      .mockImplementationOnce(() => new Promise(resolve => { resolveSecond = resolve }))

    const firstPromise = store.loadProject('project-old', false, true).catch(error => error)
    const secondPromise = store.loadProject('project-new')

    if (resolveSecond) resolveSecond({ id: 'project-new', title: '新项目', chapters: [] })
    await secondPromise

    if (rejectFirst) rejectFirst(new Error('old load failed'))
    const staleError = await firstPromise

    expect(staleError).toBeUndefined()
    expect(store.currentProject?.id).toBe('project-new')
    expect(store.error).toBeNull()
    expect(store.isLoading).toBe(false)
  })
})

describe('novel store editChapterContent', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setActivePinia(createPinia())
  })

  it('旧请求返回时不会覆盖后发编辑结果', async () => {
    const store = useNovelStore()
    store.setCurrentProject(buildProject() as any)

    let resolveFirst: ((value: any) => void) | undefined
    let resolveSecond: ((value: any) => void) | undefined

    apiMocks.editChapterContent
      .mockImplementationOnce(() => new Promise(resolve => { resolveFirst = resolve }))
      .mockImplementationOnce(() => new Promise(resolve => { resolveSecond = resolve }))

    const firstPromise = store.editChapterContent('project-1', 1, '第一次内容')
    const secondPromise = store.editChapterContent('project-1', 1, '第二次内容')

    expect(store.currentProject?.chapters[0].content).toBe('第二次内容')

    if (resolveFirst) resolveFirst({
      chapter_number: 1,
      title: '第一章',
      summary: '摘要',
      content: '服务端旧返回',
      versions: [{ id: 3, content: '服务端旧返回', style: '标准' }],
      evaluation: null,
      generation_status: 'successful',
      word_count: 6,
    })
    await firstPromise

    expect(store.currentProject?.chapters[0].content).toBe('第二次内容')

    if (resolveSecond) resolveSecond({
      chapter_number: 1,
      title: '第一章',
      summary: '摘要',
      content: '服务端最新返回',
      versions: [{ id: 4, content: '服务端最新返回', style: '标准' }],
      evaluation: null,
      generation_status: 'successful',
      word_count: 7,
    })
    await secondPromise

    expect(store.currentProject?.chapters[0].content).toBe('服务端最新返回')
  })

  it('最新请求失败时仅回滚到该次请求前的快照', async () => {
    const store = useNovelStore()
    store.setCurrentProject(buildProject() as any)

    let resolveFirst: ((value: any) => void) | undefined
    let rejectSecond: ((reason?: any) => void) | undefined

    apiMocks.editChapterContent
      .mockImplementationOnce(() => new Promise(resolve => { resolveFirst = resolve }))
      .mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectSecond = reject }))

    const firstPromise = store.editChapterContent('project-1', 1, '第一次内容')
    const secondPromise = store.editChapterContent('project-1', 1, '第二次内容').catch((error) => error)

    if (resolveFirst) resolveFirst({
      chapter_number: 1,
      title: '第一章',
      summary: '摘要',
      content: '服务端第一次返回',
      versions: [{ id: 3, content: '服务端第一次返回', style: '标准' }],
      evaluation: null,
      generation_status: 'successful',
      word_count: 8,
    })
    await firstPromise

    if (rejectSecond) rejectSecond(new Error('save failed'))
    const error = await secondPromise

    expect(error).toBeInstanceOf(Error)
    expect(store.currentProject?.chapters[0].content).toBe('第一次内容')
    expect(store.currentProject?.chapters[0].versions?.[0].content).toBe('第一次内容')
  })
})
