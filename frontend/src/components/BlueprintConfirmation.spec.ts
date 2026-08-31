import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import BlueprintConfirmation from './BlueprintConfirmation.vue'

const { novelStoreMock, alertMock } = vi.hoisted(() => ({
  novelStoreMock: {
    startBlueprintGeneration: vi.fn(),
    getBlueprintGenerationStatus: vi.fn(),
    cancelBlueprintGeneration: vi.fn(),
  },
  alertMock: {
    showError: vi.fn(),
    showInfo: vi.fn(),
  },
}))

vi.mock('@/stores/novel', () => ({
  useNovelStore: () => novelStoreMock,
}))

vi.mock('@/composables/useAlert', () => ({
  globalAlert: alertMock,
}))

const job = (overrides: Record<string, unknown>) => ({
  run_id: 'run-1',
  project_id: 'project-1',
  status: 'queued',
  progress_stage: 'queued',
  progress_message: '排队中',
  blueprint: null,
  ai_message: null,
  error: null,
  ...overrides,
})

const mountComponent = (props: Record<string, unknown> = {}) => mount(BlueprintConfirmation, {
  props: { aiMessage: '确认生成蓝图', ...props },
  global: {
    stubs: {
      XqButton: {
        props: ['disabled', 'loading'],
        emits: ['click'],
        template: '<button :disabled="disabled || loading" @click="$emit(\'click\')"><slot /></button>',
      },
      XqPanel: {
        template: '<section><slot name="kicker" /><slot name="actions" /><slot /></section>',
      },
      XqStatCard: {
        props: ['label', 'value', 'hint'],
        template: '<article>{{ label }}{{ value }}{{ hint }}</article>',
      },
    },
  },
})

describe('BlueprintConfirmation', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.runOnlyPendingTimers()
    vi.useRealTimers()
  })

  it('蓝图后台任务失败时展示结构化错误信息', async () => {
    novelStoreMock.startBlueprintGeneration.mockResolvedValueOnce(job({ status: 'queued' }))
    novelStoreMock.getBlueprintGenerationStatus.mockResolvedValueOnce(job({
      status: 'failed',
      progress_stage: 'failed',
      progress_message: '生成失败',
      error: { code: 'blueprint_generation_failed', message: 'LLM 超时', retryable: true },
    }))

    const wrapper = mountComponent()
    await wrapper.findAll('button').find((button) => button.text().includes('确认蓝图并生成大纲'))!.trigger('click')
    await flushPromises()
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()

    expect(alertMock.showError).toHaveBeenCalledWith(expect.stringContaining('LLM 超时'), '生成失败')
  })

  it('forceStage 传入时会按指定层级启动重生成', async () => {
    novelStoreMock.startBlueprintGeneration.mockResolvedValueOnce(job({
      status: 'successful',
      progress_stage: 'successful',
      blueprint: { title: '新总纲' },
      ai_message: '已重生成',
    }))

    const wrapper = mountComponent({ forceStage: 'novel_outline' })
    await wrapper.findAll('button').find((button) => button.text().includes('确认蓝图并生成大纲'))!.trigger('click')
    await flushPromises()

    expect(novelStoreMock.startBlueprintGeneration).toHaveBeenCalledWith({ forceStage: 'novel_outline' })
  })

  it('chapter_outline forceStage 会在进入页面后自动启动后台任务', async () => {
    novelStoreMock.startBlueprintGeneration.mockResolvedValueOnce(job({ status: 'queued', progress_message: '蓝图生成任务已入队' }))
    novelStoreMock.getBlueprintGenerationStatus
      .mockResolvedValueOnce(job({ status: 'generating', progress_stage: 'generating', progress_message: '正在生成可执行章节大纲（第 1/3 批，第 1-4 章）' }))
      .mockResolvedValueOnce(job({ status: 'successful', progress_stage: 'successful', progress_message: '蓝图生成完成', blueprint: { title: '章节大纲', chapter_outline: [{ chapter_number: 1, title: '第1章', summary: '摘要' }] }, ai_message: '完成' }))

    mountComponent({ forceStage: 'chapter_outline' })
    await flushPromises()
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()

    expect(novelStoreMock.startBlueprintGeneration).toHaveBeenCalledWith({ forceStage: 'chapter_outline' })
  })

  it('生成中点击取消会调用取消接口并提示已取消', async () => {
    novelStoreMock.startBlueprintGeneration.mockResolvedValueOnce(job({ status: 'generating' }))
    novelStoreMock.getBlueprintGenerationStatus.mockImplementation(() => new Promise(() => {}))
    novelStoreMock.cancelBlueprintGeneration.mockResolvedValueOnce(job({
      status: 'cancelled',
      progress_stage: 'cancelled',
      progress_message: '蓝图生成任务已取消',
    }))

    const wrapper = mountComponent()
    await wrapper.findAll('button').find((button) => button.text().includes('确认蓝图并生成大纲'))!.trigger('click')
    await flushPromises()

    await wrapper.findAll('button').find((button) => button.text().includes('取消生成'))!.trigger('click')
    await flushPromises()

    expect(novelStoreMock.cancelBlueprintGeneration).toHaveBeenCalledTimes(1)
    expect(alertMock.showInfo).toHaveBeenCalledWith('蓝图生成任务已取消', '已取消')
  })

  it('等待超过十五分钟时只提示而不会自动取消任务', async () => {
    novelStoreMock.startBlueprintGeneration.mockResolvedValueOnce(job({ status: 'generating' }))
    novelStoreMock.getBlueprintGenerationStatus.mockImplementation(() => new Promise(() => {}))

    const wrapper = mountComponent()
    await wrapper.findAll('button').find((button) => button.text().includes('确认蓝图并生成大纲'))!.trigger('click')
    await flushPromises()

    // This scenario deliberately leaves the first polling request pending.  Advancing
    // timers asynchronously makes Vitest await that pending poll promise before it
    // reaches the independent fifteen-minute notice timer.  Synchronous advancement
    // verifies the same user-visible timeout contract without turning the test into a
    // fake-timer deadlock.
    vi.advanceTimersByTime(900000)
    await flushPromises()

    expect(novelStoreMock.cancelBlueprintGeneration).not.toHaveBeenCalled()
    expect(alertMock.showInfo).toHaveBeenCalledWith(
      '蓝图生成耗时较长，但后台任务仍会继续执行，不会被前端自动取消。你可以继续等待，或手动点击“取消生成”。',
      '仍在生成',
    )
  })

  it('会把大纲生成阶段日志显示在顶部进度条中', async () => {
    novelStoreMock.startBlueprintGeneration.mockResolvedValueOnce(job({ status: 'queued', progress_message: '蓝图生成任务已入队' }))
    novelStoreMock.getBlueprintGenerationStatus
      .mockResolvedValueOnce(job({ status: 'generating', progress_stage: 'generating', progress_message: '正在生成小说总大纲' }))
      .mockResolvedValueOnce(job({ status: 'polishing', progress_stage: 'polishing', progress_message: '正在细化小说总大纲（第 1/3 段）' }))
      .mockResolvedValueOnce(job({ status: 'successful', progress_stage: 'successful', progress_message: '蓝图生成完成', blueprint: { title: '蓝图' }, ai_message: '完成' }))

    const wrapper = mountComponent()
    await wrapper.findAll('button').find((button) => button.text().includes('确认蓝图并生成大纲'))!.trigger('click')
    await flushPromises()
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()

    expect(wrapper.text()).toContain('正在生成小说总大纲')
    expect(wrapper.text()).toContain('正在细化小说总大纲（第 1/3 段）')
  })
})
