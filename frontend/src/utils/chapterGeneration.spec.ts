import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

import {
  buildChapterTaskUiModel,
  canCancelGeneration,
  getBlockingChapterNumber,
  isBusyChapterStatus,
  normalizeRuntimeStage,
  resolveActualWordCount,
  resolveChapterActionDecision,
  resolveChapterRuntime,
  taskRuntimeEventToChapterEvent,
} from './chapterGeneration'

describe('chapterGeneration utils', () => {
  it('GenerationRuntime 类型显式保留质量运行字段，而非仅依赖索引签名', () => {
    const source = readFileSync('src/api/types/novel.ts', 'utf8')
    expect(source).toContain('quality_metrics?: Record<string, unknown> | null')
    expect(source).toContain('story_progression_guard?: Record<string, unknown> | null')
    expect(source).toContain('generation_call_metrics?: Array<Record<string, unknown>> | null')
    expect(source).toContain('enrichment_triggered?: boolean | null')
  })

  it('GenerationRuntime 显式声明字数三态字段', () => {
    const runtime: import('@/api/types/novel').GenerationRuntime = {
      actual_word_count: 0,
      word_requirement_met: null,
      word_requirement_reason: 'below_minimum',
      quality_metrics: { event_density_passed: null },
      story_progression_guard: { quality_metric_snapshot: {} },
      generation_call_metrics: [{ label: 'draft_candidate_1' }],
      enrichment_triggered: false,
    }
    expect(runtime.actual_word_count).toBe(0)
    expect(runtime.word_requirement_met).toBeNull()
  })

  it('保留实际字数 0，不把合法数值误判为缺失', () => {
    expect(resolveActualWordCount({ actual_word_count: 0 }, 1200)).toBe(0)
    expect(resolveActualWordCount({}, 0)).toBe(0)
    expect(resolveActualWordCount({ actual_word_count: null }, undefined)).toBeNull()
  })

  it('将 selecting 识别为忙状态', () => {
    expect(isBusyChapterStatus('selecting')).toBe(true)
  })

  it('优先合并章节级运行时信息，避免丢失当前章状态', () => {
    expect(
      resolveChapterRuntime(
        {
          progress_stage: 'selecting',
          progress_message: '正在整理候选版本',
          allowed_actions: ['cancel_generation'],
        },
        {
          progress_stage: 'generating',
          progress_message: '项目级状态较旧',
          min_word_count: 1800,
          target_word_count: 2400,
        }
      )
    ).toMatchObject({
      progress_stage: 'selecting',
      progress_message: '正在整理候选版本',
      allowed_actions: ['cancel_generation'],
      min_word_count: 1800,
      target_word_count: 2400,
    })
  })

  it('在 selecting 阶段允许终止当前章生成', () => {
    expect(
      canCancelGeneration(
        {
          generation_status: 'selecting',
          allowed_actions: ['cancel_generation'],
        },
        {
          queued: true,
          progress_stage: 'selecting',
        }
      )
    ).toBe(true)
  })

  it('优先使用后端返回的进度和剩余时间', () => {
    expect(
      buildChapterTaskUiModel({
        progress_stage: 'generate_variants',
        progress_percent: 34,
        estimated_remaining_seconds: 125,
      }, {
        status: 'generating',
      })
    ).toMatchObject({
      stageLabel: '生成正文',
      progress: 34,
      etaLabel: '2分 5秒',
    })
  })

  it('归一化兼容运行中阶段别名', () => {
    expect(normalizeRuntimeStage('already_generating')).toBe('generate_variants')
    expect(normalizeRuntimeStage('in_progress')).toBe('generate_variants')
    expect(normalizeRuntimeStage('generate_variants')).toBe('generate_variants')
    expect(normalizeRuntimeStage('review')).toBe('review')
    expect(normalizeRuntimeStage('diagnose_once')).toBe('diagnose_once')
    expect(normalizeRuntimeStage('optimize_delivery')).toBe('optimize_delivery')
    expect(normalizeRuntimeStage('persist_versions')).toBe('persist_versions')
    expect(normalizeRuntimeStage('ledger_foreshadowing')).toBe('ledger_foreshadowing')
    expect(normalizeRuntimeStage('finalized')).toBe('finalized')
  })

  it('展示定稿后账本闭环阶段', () => {
    expect(
      buildChapterTaskUiModel({
        progress_stage: 'ledger_foreshadowing',
        progress_percent: 99,
        progress_message: '伏笔回收和新伏笔抽取完成',
      })
    ).toMatchObject({
      stageLabel: '伏笔闭环',
      progress: 99,
      displayMessage: '伏笔回收和新伏笔抽取完成',
    })

    expect(
      buildChapterTaskUiModel({
        progress_stage: 'finalized',
        progress_percent: 100,
      })
    ).toMatchObject({
      stageLabel: '定稿完成',
      progress: 100,
    })
  })

  it('为分阶段优化生成正确标签与摘要', () => {
    expect(
      buildChapterTaskUiModel({
        progress_stage: 'optimize_character',
        self_critique_final_score: 82,
        self_critique_major_count: 2,
        optimization_logs: [
          { stage: 'structural', issue_count: 3, changed: true },
          { stage: 'character', issue_count: 2, changed: true },
        ],
      })
    ).toMatchObject({
      stageLabel: '人物优化',
      critiqueSummary: '评分 82 · 主要问题 2 · 分批优化 2 段',
    })
  })

  it('为前章依据与关联上下文阶段生成正确标签与进度', () => {
    expect(
      buildChapterTaskUiModel({
        progress_stage: 'diagnose_previous_chapter',
        progress_percent: 72,
        progress_message: '正在整理前一章依据包',
      })
    ).toMatchObject({
      stageLabel: '前章依据',
      progress: 72,
      displayMessage: '正在整理前一章依据包',
    })

    expect(
      buildChapterTaskUiModel({
        progress_stage: 'diagnose_context_bundle',
        progress_percent: 74,
        progress_message: '正在整理关联上下文',
      })
    ).toMatchObject({
      stageLabel: '关联上下文',
      progress: 74,
      displayMessage: '正在整理关联上下文',
    })
  })

  it('复用既有诊断时展示复用提示而不是卡住', () => {
    expect(
      buildChapterTaskUiModel({
        progress_stage: 'optimize_content',
        progress_message: '总览变更较小，已复用既有诊断结果并跳过重复诊断/优化',
        optimization_stage_label: '复用既有诊断',
        chapter_overview_reuse: {
          change_level: 'light',
          changed_fields: ['previous_summary'],
          reused: true,
        },
      })
    ).toMatchObject({
      stageLabel: '分阶段优化',
      displayMessage: '总览变更较小，已复用既有诊断结果并跳过重复诊断/优化',
    })
  })

  it('返回阻塞当前章的上一章编号', () => {
    expect(
      getBlockingChapterNumber(
        {
          blueprint: {
            chapter_outline: [
              { chapter_number: 1 },
              { chapter_number: 2 },
              { chapter_number: 3 },
            ],
          },
          chapters: [
            { chapter_number: 1, generation_status: 'waiting_for_confirm' },
            { chapter_number: 2, generation_status: 'not_generated' },
            { chapter_number: 3, generation_status: 'not_generated' },
          ],
        } as any,
        3
      )
    ).toBe(1)
  })

  it('为等待确认章节返回查看候选版本动作', () => {
    expect(
      resolveChapterActionDecision(
        {
          blueprint: {
            chapter_outline: [{ chapter_number: 1 }],
          },
          chapters: [
            { chapter_number: 1, generation_status: 'waiting_for_confirm' },
          ],
        } as any,
        1
      )
    ).toMatchObject({
      mode: 'navigate',
      label: '查看候选版本',
      shouldConfirm: true,
      canOpenResult: true,
      canGenerate: false,
    })
  })

  it('为失败章节返回重新生成动作', () => {
    expect(
      resolveChapterActionDecision(
        {
          blueprint: {
            chapter_outline: [{ chapter_number: 1 }],
          },
          chapters: [
            { chapter_number: 1, generation_status: 'failed' },
          ],
        } as any,
        1
      )
    ).toMatchObject({
      mode: 'action',
      label: '重新生成',
      isRetry: true,
      canGenerate: true,
    })
  })

  it('marks backend-stale generation runtime as likely stalled without requiring fetch failures', () => {
    const nowMs = Date.parse('2026-04-28T12:20:00.000Z')
    const updatedAt = '2026-04-28T12:00:00.000Z'

    expect(
      buildChapterTaskUiModel({
        progress_stage: 'generate_variants',
        updated_at: updatedAt,
        stale: true,
      }, {
        nowMs,
        statusFetchFailureCount: 0,
      })
    ).toMatchObject({
      isLikelyStalled: true,
    })
  })

})
describe('taskRuntimeEventToChapterEvent 正文与日志分流', () => {
  it('把 content_delta 事件的正文提升为独立字段并可渲染', () => {
    const event = taskRuntimeEventToChapterEvent({
      event_id: 5,
      event_type: 'content_delta',
      status: 'running',
      stage: 'segment_generation',
      progress: 40,
      payload: { delta: '第一段正文。', preview: false, segment_index: 0 },
      created_at: '2026-04-21T08:00:00Z',
    })

    expect(event.content_delta).toBe('第一段正文。')
    expect(event.content_preview).toBe('第一段正文。')
    expect(event.content_is_preview).toBe(false)
    expect(event.segment_index).toBe(0)
    expect(event.kind).toBe('content')
  })

  it('优先使用后端已提升的 content_delta 字段', () => {
    const event = taskRuntimeEventToChapterEvent({
      event_id: 6,
      event_type: 'content_delta',
      content_delta: '已提升正文。',
      payload: { delta: '兜底正文。' },
    })

    expect(event.content_delta).toBe('已提升正文。')
  })

  it('日志事件即使 payload 夹带 delta 也不得冒充正文', () => {
    const event = taskRuntimeEventToChapterEvent({
      event_id: 7,
      event_type: 'log',
      message: '后端运行日志',
      payload: { delta: '这是日志不是正文', content_delta: '这也是日志', log: '后端运行日志' },
    })

    expect(event.content_delta).toBeUndefined()
    expect(event.content_preview).toBeUndefined()
    expect(event.message).toBe('后端运行日志')
  })

  it('progress 事件不产生正文字段', () => {
    const event = taskRuntimeEventToChapterEvent({
      event_id: 8,
      event_type: 'progress',
      stage: 'generate_variants',
      progress: 55,
      payload: { content: '不应被当作正文' },
    })

    expect(event.content_delta).toBeUndefined()
    expect(event.progress_percent).toBe(55)
  })

  it('标记预览分片，避免整章预览被当成分段正文累积', () => {
    const event = taskRuntimeEventToChapterEvent({
      event_id: 9,
      event_type: 'content_delta',
      payload: { delta: '整章预览。', preview: true },
    })

    expect(event.content_is_preview).toBe(true)
    expect(event.segment_index).toBeUndefined()
  })

  it('失败与僵尸事件标记为 error 级别', () => {
    expect(
      taskRuntimeEventToChapterEvent({ event_id: 10, event_type: 'task_failed', status: 'failed' }).level
    ).toBe('error')
    expect(
      taskRuntimeEventToChapterEvent({ event_id: 11, event_type: 'task_stale', status: 'stale' }).level
    ).toBe('error')
  })
})


describe('TaskRuntime SSE 任务绑定', () => {
  it('拒绝旧任务迟到事件写入新任务', async () => {
    const { isTaskEventForCurrentTask } = await import('./chapterGeneration')
    expect(isTaskEventForCurrentTask('old-task', 'new-task')).toBe(false)
    expect(isTaskEventForCurrentTask('new-task', 'new-task')).toBe(true)
    expect(isTaskEventForCurrentTask('', 'new-task')).toBe(false)
  })
})
