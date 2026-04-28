import { flushPromises, shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const {
  pushMock,
  novelStoreMock,
  optimizerMocks,
  alertMocks,
} = vi.hoisted(() => ({
  pushMock: vi.fn(),
  novelStoreMock: {
    currentProject: null as any,
    currentConversationState: {},
    isLoading: false,
    error: null as string | null,
    loadProject: vi.fn(),
    generateChapter: vi.fn(),
    cancelChapterGeneration: vi.fn(),
    evaluateChapter: vi.fn(),
    evaluateAllVersions: vi.fn(),
    optimizeChapterVersion: vi.fn(),
    selectChapterVersion: vi.fn(),
    deleteChapterVersion: vi.fn(),
    deleteProjects: vi.fn(),
    updateChapterOutline: vi.fn(),
    rewriteChapterOutline: vi.fn(),
    deleteChapter: vi.fn(),
    generateChapterOutline: vi.fn(),
    editChapterContent: vi.fn(),
    clearError: vi.fn(),
    setCurrentProject: vi.fn(),
  },
  optimizerMocks: {
    getActiveStyleProfile: vi.fn(),
    applyOptimization: vi.fn(),
  },
  alertMocks: {
    showConfirm: vi.fn(),
    showError: vi.fn(),
    showSuccess: vi.fn(),
    showInfo: vi.fn(),
  },
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: pushMock }),
}))

vi.mock('@/stores/novel', () => ({
  useNovelStore: () => novelStoreMock,
}))

const chapterWorkflowMocks = vi.hoisted(() => ({
  getChapterGenerationStatus: vi.fn(),
}))

vi.mock('@/api/novel', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/novel')>()
  return {
    ...actual,
    OptimizerAPI: optimizerMocks,
  }
})

vi.mock('@/api/modules/chapterWorkflow', () => chapterWorkflowMocks)

vi.mock('@/composables/useAlert', () => ({
  globalAlert: alertMocks,
}))

vi.mock('@/components/writing-desk', () => ({
  WDHeader: {
    name: 'WDHeader',
    props: [
      'statusFetchFailureCount',
      'isCurrentChapterBusy',
      'isCurrentChapterTrackable',
      'taskChapterNumber',
      'taskTrackable',
      'canOpenVersionsCurrent',
      'canReviewAllVersionsCurrent',
    ],
    emits: ['evaluate-current', 'open-versions-current', 'review-all-versions-current'],
    template: `
      <div
        class="header-stub"
        :data-status-fetch-failure-count="String(statusFetchFailureCount ?? 0)"
        :data-is-current-chapter-busy="String(isCurrentChapterBusy)"
        :data-is-current-chapter-trackable="String(isCurrentChapterTrackable)"
        :data-task-chapter-number="String(taskChapterNumber ?? '')"
        :data-task-trackable="String(taskTrackable)"
        :data-can-open-versions-current="String(canOpenVersionsCurrent)"
        :data-can-review-all-versions-current="String(canReviewAllVersionsCurrent)"
      >
        <button class="header-evaluate" @click="$emit('evaluate-current')">evaluate</button>
        <button class="header-open-versions" @click="$emit('open-versions-current')">open-versions</button>
        <button class="header-review-all" @click="$emit('review-all-versions-current')">review-all</button>
      </div>
    `,
  },
  WDSidebar: {
    name: 'WDSidebar',
    template: '<div class="sidebar-stub">sidebar</div>',
  },
  WDWorkspace: {
    name: 'WDWorkspace',
    props: ['project', 'showVersionSelector', 'selectedVersionIndex'],
    emits: ['evaluateChapter', 'evaluateVersion', 'evaluateAllVersions', 'chapterUpdated', 'update:selectedVersionIndex'],
    methods: {
      openPrimaryReader() {},
      openVersionSelector() {},
    },
    template: `
      <div
        class="workspace-stub"
        :data-show-version-selector="String(showVersionSelector)"
        :data-selected-version-index="String(selectedVersionIndex)"
      >
        <button class="workspace-evaluate" @click="$emit('evaluateChapter')">evaluate</button>
        <button class="workspace-evaluate-all" @click="$emit('evaluateAllVersions')">evaluate-all</button>
        <button class="workspace-evaluate-version" @click="$emit('evaluateVersion', 0)">evaluate-version</button>
        <button
          class="workspace-update-chapter"
          @click="$emit('chapterUpdated', { chapter_number: 1, title: '第一章', summary: '更新摘要', content: '更新正文', versions: [], evaluation: null, generation_status: 'successful', word_count: 4 })"
        >
          update
        </button>
      </div>
    `,
  },
  WDGenerateOutlineModal: {
    name: 'WDGenerateOutlineModal',
    template: '<div class="generate-outline-modal-stub"></div>',
  },
}))

vi.mock('@/components/writing-desk/dialogs/WDEvaluationDetailModal.vue', () => ({
  default: { name: 'WDEvaluationDetailModal', template: '<div />' },
}))
vi.mock('@/components/writing-desk/dialogs/WDEditChapterModal.vue', () => ({
  default: { name: 'WDEditChapterModal', template: '<div />' },
}))
vi.mock('@/components/writing-desk/dialogs/WDGenerateChapterModal.vue', () => ({
  default: { name: 'WDGenerateChapterModal', template: '<div />' },
}))
vi.mock('@/components/writing-desk/dialogs/WDSkillSelectorModal.vue', () => ({
  default: { name: 'WDSkillSelectorModal', template: '<div />' },
}))
vi.mock('@/components/writing-desk/dialogs/WDVersionDetailModal.vue', () => ({
  default: { name: 'WDVersionDetailModal', template: '<div />' },
}))
vi.mock('@/components/writing-desk/dialogs/WDVersionDiffModal.vue', () => ({
  default: { name: 'WDVersionDiffModal', template: '<div />' },
}))
vi.mock('@/components/writing-desk/dialogs/WDPatchDiffModal.vue', () => ({
  default: { name: 'WDPatchDiffModal', template: '<div />' },
}))

import WritingDesk from './WritingDesk.vue'

const buildProject = (status: 'successful' | 'evaluation_failed' | 'evaluating' | 'waiting_for_confirm' | 'selecting' | 'failed' = 'successful') => ({
  id: 'project-1',
  title: '测试项目',
  initial_prompt: 'prompt',
  conversation_history: [],
  workspace_summary: {
    total_chapters: 1,
    completed_chapters: status === 'successful' ? 1 : 0,
    failed_chapters: 0,
    in_progress_chapters: status === 'evaluating' ? 1 : 0,
    total_word_count: 4,
    active_chapter: 1,
    first_incomplete_chapter: 1,
    next_chapter_to_generate: 1,
    can_generate_next: true,
    available_actions: [],
  },
  blueprint: {
    chapter_outline: [
      {
        chapter_number: 1,
        title: '第一章',
        summary: '摘要',
      },
    ],
  },
  chapters: [
    {
      chapter_number: 1,
      title: '第一章',
      summary: '摘要',
      content: '正文',
      versions: [{ id: 1, content: '候选正文', style: '标准' }],
      evaluation: null,
      generation_status: status,
      word_count: 4,
    },
  ],
})

const mountView = async () => {
  const wrapper = shallowMount(WritingDesk, {
    props: { id: 'project-1' },
    global: {
      stubs: {
        Teleport: true,
      },
    },
  })
  await flushPromises()
  return wrapper
}

describe('WritingDesk', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    chapterWorkflowMocks.getChapterGenerationStatus.mockImplementation(async (_projectId: string, chapterNumber: number) => {
      const chapter = novelStoreMock.currentProject?.chapters?.find((item: any) => item.chapter_number === chapterNumber)
      if (!chapter) {
        throw new Error('chapter not found')
      }
      return { ...chapter }
    })
    novelStoreMock.currentProject = buildProject('successful')
    novelStoreMock.isLoading = false
    novelStoreMock.error = null
    novelStoreMock.setCurrentProject.mockImplementation((project: any) => {
      novelStoreMock.currentProject = project
    })
    novelStoreMock.loadProject.mockResolvedValue(undefined)
    novelStoreMock.generateChapter.mockResolvedValue(undefined)
    novelStoreMock.cancelChapterGeneration.mockResolvedValue(undefined)
    novelStoreMock.evaluateChapter.mockResolvedValue(undefined)
    novelStoreMock.evaluateAllVersions.mockResolvedValue(undefined)
    novelStoreMock.optimizeChapterVersion.mockResolvedValue(undefined)
    novelStoreMock.selectChapterVersion.mockResolvedValue(undefined)
    novelStoreMock.deleteChapterVersion.mockResolvedValue(undefined)
    novelStoreMock.updateChapterOutline.mockResolvedValue(undefined)
    novelStoreMock.rewriteChapterOutline.mockResolvedValue(undefined)
    novelStoreMock.deleteChapter.mockResolvedValue(undefined)
    novelStoreMock.generateChapterOutline.mockResolvedValue(undefined)
    novelStoreMock.editChapterContent.mockResolvedValue(undefined)
    optimizerMocks.getActiveStyleProfile.mockResolvedValue({ profile: null })
    optimizerMocks.applyOptimization.mockResolvedValue({ chapter: buildProject('successful').chapters[0] })
    alertMocks.showConfirm.mockResolvedValue(true)
  })

  it('评估失败且同步失败时回滚章节状态，并保持版本区关闭', async () => {
    novelStoreMock.loadProject
      .mockResolvedValueOnce(undefined)
      .mockRejectedValueOnce(new Error('sync failed'))

    novelStoreMock.evaluateChapter.mockImplementationOnce(async () => {
      novelStoreMock.currentProject.chapters[0].generation_status = 'evaluating'
      throw new Error('evaluate failed')
    })

    const wrapper = await mountView()
    const workspace = wrapper.findComponent({ name: 'WDWorkspace' })

    expect(workspace.props('showVersionSelector')).toBe(false)

    workspace.vm.$emit('evaluateChapter')
    await flushPromises()

    expect(novelStoreMock.currentProject.chapters[0].generation_status).toBe('evaluating')
    expect(alertMocks.showError).toHaveBeenCalled()
    expect(wrapper.findComponent({ name: 'WDWorkspace' }).props('showVersionSelector')).toBe(false)
  })

  it('选择版本失败时回退到原选中版本索引', async () => {
    novelStoreMock.currentProject = {
      ...buildProject('evaluation_failed'),
      chapters: [
        {
          ...buildProject('evaluation_failed').chapters[0],
          content: '正文',
          versions: [
            { id: 1, content: '正文', style: '标准' },
            { id: 2, content: '候选正文', style: '标准' },
          ],
        },
      ],
    }
    novelStoreMock.selectChapterVersion.mockRejectedValueOnce(new Error('select failed'))

    const wrapper = await mountView()

    await (wrapper.vm as any).selectVersion(1)
    await flushPromises()

    expect(novelStoreMock.selectChapterVersion).toHaveBeenCalledWith(1, 1)
    expect(wrapper.findComponent({ name: 'WDWorkspace' }).props('selectedVersionIndex')).toBe(0)
    expect(alertMocks.showError).toHaveBeenCalled()
  })

  it('接收 chapter-updated 事件后同步覆盖当前章节内容', async () => {
    const wrapper = await mountView()
    const workspace = wrapper.findComponent({ name: 'WDWorkspace' })

    workspace.vm.$emit('chapterUpdated', {
      chapter_number: 1,
      title: '第一章',
      summary: '更新摘要',
      content: '更新正文',
      versions: [],
      evaluation: null,
      generation_status: 'successful',
      word_count: 4,
    })
    await flushPromises()

    const projectProp = wrapper.findComponent({ name: 'WDWorkspace' }).props('project') as ReturnType<typeof buildProject>
    expect(projectProp.chapters[0].summary).toBe('更新摘要')
    expect(projectProp.chapters[0].content).toBe('更新正文')
  })

  it('将状态拉取失败计数透传给头部任务栏', async () => {
    const wrapper = await mountView()

    ;(wrapper.vm as any).statusFetchFailureCount = 3
    await flushPromises()

    expect(wrapper.findComponent({ name: 'WDHeader' }).props('statusFetchFailureCount')).toBe(3)
  })

  it('章节状态刷新成功后应回填后端最新正文与候选版本', async () => {
    novelStoreMock.currentProject = {
      ...buildProject('evaluating'),
      chapters: [
        {
          ...buildProject('evaluating').chapters[0],
          generation_status: 'evaluating',
          content: '旧正文',
          versions: [{ id: 1, content: '旧候选', style: '标准' }],
        },
      ],
    }
    chapterWorkflowMocks.getChapterGenerationStatus.mockResolvedValueOnce({
      ...novelStoreMock.currentProject.chapters[0],
      generation_status: 'waiting_for_confirm',
      content: '新正文',
      versions: [{ id: 2, content: '新候选正文', style: '标准' }],
      progress_stage: 'ready',
    })

    const wrapper = await mountView()

    await (wrapper.vm as any).fetchChapterStatus()
    await flushPromises()

    expect(chapterWorkflowMocks.getChapterGenerationStatus).toHaveBeenCalledWith('project-1', 1)
    expect(novelStoreMock.setCurrentProject).toHaveBeenCalled()
    const latestProject = novelStoreMock.setCurrentProject.mock.calls.at(-1)?.[0]
    expect(latestProject.chapters[0].generation_status).toBe('waiting_for_confirm')
    expect(latestProject.chapters[0].content).toBe('新正文')
    expect(latestProject.chapters[0].versions).toEqual([{ id: 2, content: '新候选正文', style: '标准' }])
  })

  it('应用 patch 后应执行一次全量刷新并再次同步当前章节状态', async () => {
    const wrapper = await mountView()
    ;(wrapper.vm as any).selectedChapterNumber = 1

    chapterWorkflowMocks.getChapterGenerationStatus.mockClear()
    novelStoreMock.loadProject.mockClear()

    await (wrapper.vm as any).handlePatchApplied({ original: '旧内容', patched: '新内容' })
    await flushPromises()

    expect(novelStoreMock.loadProject).toHaveBeenCalledTimes(1)
    expect(chapterWorkflowMocks.getChapterGenerationStatus).toHaveBeenCalledTimes(1)
    expect(chapterWorkflowMocks.getChapterGenerationStatus).toHaveBeenCalledWith('project-1', 1)
  })

  it('仅剩 generation_runtime 忙状态时仍保持轮询定时器', async () => {
    novelStoreMock.currentProject = {
      ...buildProject('successful'),
      generation_runtime: {
        progress_stage: 'generating',
        queued: true,
      },
    }

    const setTimeoutSpy = vi.spyOn(window, 'setTimeout')
    const clearTimeoutSpy = vi.spyOn(window, 'clearTimeout')

    await mountView()

    expect(setTimeoutSpy).toHaveBeenCalled()
    expect(clearTimeoutSpy).not.toHaveBeenCalledWith(null)

    setTimeoutSpy.mockRestore()
    clearTimeoutSpy.mockRestore()
  })

  it('等待确认阶段不应被头部误判为后台处理中', async () => {
    novelStoreMock.currentProject = buildProject('waiting_for_confirm')

    const wrapper = await mountView()

    expect((wrapper.vm as any).isCurrentChapterBusy).toBe(false)
  })

  it('准备确认阶段不应被头部误判为后台处理中', async () => {
    novelStoreMock.currentProject = buildProject('selecting')

    const wrapper = await mountView()

    expect((wrapper.vm as any).isCurrentChapterBusy).toBe(false)
  })

  it('generation_runtime 仍在运行时头部保持忙态', async () => {
    novelStoreMock.currentProject = {
      ...buildProject('successful'),
      generation_runtime: {
        progress_stage: 'generating',
        queued: true,
      },
    }

    const wrapper = await mountView()

    expect((wrapper.vm as any).isCurrentChapterBusy).toBe(true)
  })

  it('状态刷新失败时不应提前清空仍在运行的 generation_runtime', async () => {
    novelStoreMock.currentProject = {
      ...buildProject('successful'),
      generation_runtime: {
        progress_stage: 'generating',
        queued: true,
      },
    }
    chapterWorkflowMocks.getChapterGenerationStatus.mockRejectedValueOnce(new Error('sync failed'))

    const wrapper = await mountView()

    await (wrapper.vm as any).fetchChapterStatus()
    await flushPromises()

    expect(chapterWorkflowMocks.getChapterGenerationStatus).toHaveBeenCalledWith('project-1', 1)
    expect(novelStoreMock.currentProject.generation_runtime).toEqual({
      progress_stage: 'generating',
      queued: true,
    })
    expect((wrapper.vm as any).statusFetchFailureCount).toBe(1)
    expect(alertMocks.showError).toHaveBeenCalled()
  })

  it('终止章节成功后提示成功并复位终止态', async () => {
    novelStoreMock.currentProject = {
      ...buildProject('evaluating'),
      chapters: [
        {
          ...buildProject('evaluating').chapters[0],
          generation_status: 'evaluating',
        },
      ],
    }
    novelStoreMock.cancelChapterGeneration.mockImplementationOnce(async () => {
      novelStoreMock.currentProject.chapters[0].generation_status = 'failed'
    })
    chapterWorkflowMocks.getChapterGenerationStatus.mockImplementation(async () => ({
      ...novelStoreMock.currentProject.chapters[0],
    }))

    const wrapper = await mountView()

    await (wrapper.vm as any).terminateChapter(1)
    await flushPromises()

    expect(alertMocks.showConfirm).toHaveBeenCalled()
    expect(novelStoreMock.cancelChapterGeneration).toHaveBeenCalledWith(1)
    expect(alertMocks.showSuccess).toHaveBeenCalledWith(
      '第 1 章已标记为失败，前端会停止继续等待该任务。',
      '已终止'
    )
    expect((wrapper.vm as any).terminatingChapter).toBe(null)
  })

  it('终止章节失败时提示错误并复位终止态', async () => {
    novelStoreMock.currentProject = buildProject('evaluating')
    novelStoreMock.cancelChapterGeneration.mockRejectedValueOnce(new Error('cancel failed'))

    const wrapper = await mountView()

    await (wrapper.vm as any).terminateChapter(1)
    await flushPromises()

    expect(novelStoreMock.cancelChapterGeneration).toHaveBeenCalledWith(1)
    expect(alertMocks.showError).toHaveBeenCalledWith(
      'cancel failed',
      '终止失败'
    )
    expect((wrapper.vm as any).terminatingChapter).toBe(null)
  })

  it('确认版本成功后完成状态同步并提示成功', async () => {
    vi.useFakeTimers()
    try {
      novelStoreMock.currentProject = {
        ...buildProject('waiting_for_confirm'),
        chapters: [
          {
            ...buildProject('waiting_for_confirm').chapters[0],
            content: '正文',
            versions: [
              { id: 1, content: '正文', style: '标准' },
              { id: 2, content: '候选正文', style: '标准' },
            ],
          },
        ],
      }
      let statusFetchCount = 0
      chapterWorkflowMocks.getChapterGenerationStatus.mockImplementation(async () => {
        statusFetchCount += 1
        if (statusFetchCount >= 2) {
          novelStoreMock.currentProject.chapters[0].generation_status = 'successful'
          novelStoreMock.currentProject.chapters[0].content = '候选正文'
        }
        return { ...novelStoreMock.currentProject.chapters[0] }
      })

      const wrapper = await mountView()
      ;(wrapper.vm as any).clearStatusPolling()
      ;(wrapper.vm as any).selectedVersionIndex = 1

      const confirmPromise = (wrapper.vm as any).confirmVersionSelection()
      await vi.advanceTimersByTimeAsync(7000)
      await confirmPromise
      await flushPromises()

      expect(novelStoreMock.selectChapterVersion).toHaveBeenCalledWith(1, 1)
      expect(alertMocks.showSuccess).toHaveBeenCalledWith('版本已确认', '操作成功')
      expect(alertMocks.showError).not.toHaveBeenCalledWith(
        '确认已提交，但后台长时间未回写新状态。请立即刷新，或直接终止处理后重试。',
        '状态同步提醒'
      )
    } finally {
      vi.useRealTimers()
    }
  }, 12000)

  it('确认版本后若迟迟未回写则提示同步告警', async () => {
    vi.useFakeTimers()
    try {
      novelStoreMock.currentProject = {
        ...buildProject('waiting_for_confirm'),
        chapters: [
          {
            ...buildProject('waiting_for_confirm').chapters[0],
            content: '正文',
            versions: [
              { id: 1, content: '正文', style: '标准' },
              { id: 2, content: '候选正文', style: '标准' },
            ],
          },
        ],
      }
      chapterWorkflowMocks.getChapterGenerationStatus.mockImplementation(async () => ({
        ...novelStoreMock.currentProject.chapters[0],
      }))

      const wrapper = await mountView()
      ;(wrapper.vm as any).clearStatusPolling()
      ;(wrapper.vm as any).selectedVersionIndex = 1

      const confirmPromise = (wrapper.vm as any).confirmVersionSelection()
      await vi.advanceTimersByTimeAsync(10000)
      await confirmPromise
      await flushPromises()

      expect(novelStoreMock.selectChapterVersion).toHaveBeenCalledWith(1, 1)
      expect(alertMocks.showError).toHaveBeenCalledWith(
        '确认已提交，但后台长时间未回写新状态。请立即刷新，或直接终止处理后重试。\n建议：如果再次刷新仍无回写，请终止处理并重新生成。',
        '状态同步提醒'
      )
    } finally {
      vi.useRealTimers()
    }
  }, 12000)

  it('并发刷新状态时应复用同一个进行中的请求', async () => {
    let statusFetchCount = 0
    chapterWorkflowMocks.getChapterGenerationStatus.mockImplementation(() => {
      statusFetchCount += 1
      return new Promise((resolve) => setTimeout(() => resolve({ ...novelStoreMock.currentProject.chapters[0] }), 20))
    })

    const wrapper = await mountView()
    ;(wrapper.vm as any).clearStatusPolling()

    const first = (wrapper.vm as any).fetchChapterStatus()
    const inFlight = (wrapper.vm as any).statusFetchPromise
    const second = (wrapper.vm as any).fetchChapterStatus()

    expect(inFlight).not.toBe(null)
    expect((wrapper.vm as any).statusFetchPromise).toBe(inFlight)

    await Promise.all([first, second])
    await flushPromises()

    expect(statusFetchCount).toBe(1)
    expect((wrapper.vm as any).statusFetchPromise).toBe(null)
  })

  it('前章等待确认时主生成动作应跳转到阻塞章节', async () => {
    novelStoreMock.currentProject = {
      ...buildProject('waiting_for_confirm'),
      workspace_summary: {
        ...buildProject('waiting_for_confirm').workspace_summary,
        total_chapters: 2,
        next_chapter_to_generate: 2,
      },
      blueprint: {
        chapter_outline: [
          { chapter_number: 1, title: '第一章', summary: '摘要' },
          { chapter_number: 2, title: '第二章', summary: '摘要' },
        ],
      },
      chapters: [
        {
          ...buildProject('waiting_for_confirm').chapters[0],
          chapter_number: 1,
          generation_status: 'waiting_for_confirm',
        },
        {
          chapter_number: 2,
          title: '第二章',
          summary: '摘要',
          content: '',
          versions: [],
          evaluation: null,
          generation_status: 'not_generated',
          word_count: 0,
        },
      ],
    }

    const wrapper = await mountView()
    ;(wrapper.vm as any).selectedChapterNumber = 2

    ;(wrapper.vm as any).handlePrimaryGenerate()
    await flushPromises()

    expect((wrapper.vm as any).selectedChapterNumber).toBe(1)
  })

  it('当前选中章节处于等待确认时主生成动作应直接打开重生成弹窗', async () => {
    novelStoreMock.currentProject = buildProject('waiting_for_confirm')

    const wrapper = await mountView()

    ;(wrapper.vm as any).handlePrimaryGenerate()
    await flushPromises()

    expect((wrapper.vm as any).showGenerateChapterModal).toBe(true)
  })

  it('当前选中章节处于等待确认时提交重生成不应再触发生成受限', async () => {
    novelStoreMock.currentProject = buildProject('waiting_for_confirm')

    const wrapper = await mountView()

    await (wrapper.vm as any).generateChapter(1, {
      minWordCount: 5500,
      targetWordCount: 5700,
    })
    await flushPromises()

    expect(novelStoreMock.generateChapter).toHaveBeenCalledWith(1, {
      minWordCount: 5500,
      targetWordCount: 5700,
      qualityRequirements: undefined,
      writingNotes: undefined,
    })
    expect(alertMocks.showError).not.toHaveBeenCalledWith('当前章节暂时不能直接生成。', '生成受限')
  })

  it('失败章节应允许直接重新生成', async () => {
    novelStoreMock.currentProject = buildProject('failed')

    const wrapper = await mountView()

    expect((wrapper.vm as any).canGenerateSelectedChapter).toBe(true)
  })

  it('等待确认章节也应允许直接重新生成当前章节', async () => {
    novelStoreMock.currentProject = buildProject('waiting_for_confirm')

    const wrapper = await mountView()

    expect((wrapper.vm as any).canGenerateSelectedChapter).toBe(true)
  })

  it('多版本章节应支持触发全版本对比评审', async () => {
    novelStoreMock.currentProject = {
      ...buildProject('successful'),
      chapters: [
        {
          ...buildProject('successful').chapters[0],
          versions: [
            { id: 1, content: '版本一正文', style: '标准' },
            { id: 2, content: '版本二正文', style: '克制' },
          ],
        },
      ],
    }

    const wrapper = await mountView()
    const workspace = wrapper.findComponent({ name: 'WDWorkspace' })
    workspace.vm.$emit('evaluateAllVersions')
    await flushPromises()

    expect(novelStoreMock.evaluateAllVersions).toHaveBeenCalledWith(1)
  })

  it('等待确认阶段仍应保持任务进度可见', async () => {
    novelStoreMock.currentProject = buildProject('waiting_for_confirm')

    const wrapper = await mountView()
    const header = wrapper.findComponent({ name: 'WDHeader' })

    expect((wrapper.vm as any).isCurrentChapterTrackable).toBe(true)
    expect(header.props('isCurrentChapterTrackable')).toBe(true)
  })

  it('等待确认阶段删除与预览内容相同的候选版本时不应被误拦截', async () => {
    novelStoreMock.currentProject = {
      ...buildProject('waiting_for_confirm'),
      chapters: [
        {
          ...buildProject('waiting_for_confirm').chapters[0],
          content: '候选正文A',
          versions: [
            { id: 1, content: '候选正文A', style: '标准' },
            { id: 2, content: '候选正文B', style: '克制' },
          ],
        },
      ],
    }

    const wrapper = await mountView()

    await (wrapper.vm as any).deleteVersion(0)
    await flushPromises()

    expect(novelStoreMock.deleteChapterVersion).toHaveBeenCalledWith(1, 0)
    expect(alertMocks.showError).not.toHaveBeenCalledWith('不能删除当前生效的版本', '删除失败')
  })

  it('头部任务栏应跟随当前可追踪章节而非仅看忙状态', async () => {
    novelStoreMock.currentProject = buildProject('waiting_for_confirm')

    const wrapper = await mountView()
    const header = wrapper.findComponent({ name: 'WDHeader' })

    expect(header.props('taskChapterNumber')).toBe(1)
    expect(header.props('taskTrackable')).toBe(true)
  })

  it('头部查看候选操作应走版本选择器而不是正文阅读器', async () => {
    novelStoreMock.currentProject = {
      ...buildProject('successful'),
      chapters: [
        {
          ...buildProject('successful').chapters[0],
          versions: [
            { id: 1, content: '版本一正文', style: '标准' },
            { id: 2, content: '版本二正文', style: '克制' },
          ],
        },
      ],
    }

    const wrapper = await mountView()
    const header = wrapper.findComponent({ name: 'WDHeader' })

    expect(header.props('canOpenVersionsCurrent')).toBe(true)

    header.vm.$emit('open-versions-current')
    await flushPromises()

    expect((wrapper.vm as any).compareVersionIndex).toBe(null)
    expect(wrapper.findComponent({ name: 'WDWorkspace' }).props('selectedVersionIndex')).toBe(0)
  })
})
