import { describe, expect, it } from 'vitest'

import {
  buildChapterTaskUiModel,
  canCancelGeneration,
  getBlockingChapterNumber,
  isBusyChapterStatus,
  normalizeRuntimeStage,
  resolveChapterActionDecision,
  resolveChapterRuntime,
} from './chapterGeneration'

describe('chapterGeneration utils', () => {
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
    expect(normalizeRuntimeStage('already_generating')).toBe('generating')
    expect(normalizeRuntimeStage('in_progress')).toBe('generating')
    expect(normalizeRuntimeStage('generate_variants')).toBe('generating')
    expect(normalizeRuntimeStage('review')).toBe('evaluating')
    expect(normalizeRuntimeStage('diagnose_once')).toBe('evaluating')
    expect(normalizeRuntimeStage('optimize_delivery')).toBe('evaluating')
    expect(normalizeRuntimeStage('persist_versions')).toBe('selecting')
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

  it('为等待确认章节返回查看结果动作', () => {
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
      label: '查看当前结果',
      shouldConfirm: true,
      canOpenResult: true,
      canGenerate: false,
    })
  })

  it('为失败章节返回重试动作', () => {
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
      label: '重试',
      isRetry: true,
      canGenerate: true,
    })
  })
})
