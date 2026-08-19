import { describe, expect, it } from 'vitest'
import { buildChapterQualitySummary, resolveChapterQualityMetrics } from './chapterQuality'

describe('chapterQuality utils', () => {
  it('prefers runtime quality metrics over version metadata', () => {
    const metrics = resolveChapterQualityMetrics(
      {
        chapter_number: 1,
        title: 'Chapter 1',
        summary: '',
        content: null,
        versions: [
          {
            id: 1,
            content: 'content',
            metadata: { quality_metrics: { scene_fulfillment_rate: 0.1 } },
          },
        ],
        evaluation: null,
        generation_status: 'waiting_for_confirm',
      },
      { quality_metrics: { scene_fulfillment_rate: 0.8 } },
    )

    expect(metrics?.scene_fulfillment_rate).toBe(0.8)
  })

  it('summarizes visible quality risks from raw metrics', () => {
    const summary = buildChapterQualitySummary(
      {
        chapter_number: 1,
        title: 'Chapter 1',
        summary: '',
        content: null,
        versions: [
          {
            id: 1,
            content: 'content',
            metadata: {
              quality_metrics: {
                scene_fulfillment_rate: 0.25,
                dialogue_changes_state: false,
                ending_pressure_passed: false,
                static_description_risk: true,
              },
            },
          },
        ],
        evaluation: null,
        generation_status: 'waiting_for_confirm',
      },
      null,
    )

    expect(summary?.tone).toBe('danger')
    expect(summary?.issues).toHaveLength(4)
  })

  it('prefers backend quality issue labels when present', () => {
    const summary = buildChapterQualitySummary(
      {
        chapter_number: 1,
        title: 'Chapter 1',
        summary: '',
        content: null,
        versions: [
          {
            id: 1,
            content: 'content',
            metadata: {
              quality_metrics: {
                scene_fulfillment_rate: 0.25,
                dialogue_changes_state: false,
                quality_issue_summary: {
                  tone: 'warning',
                  labels: ['场景兑现不足', '对白未改变局势'],
                },
              },
            },
          },
        ],
        evaluation: null,
        generation_status: 'waiting_for_confirm',
      },
      null,
    )

    expect(summary?.tone).toBe('warning')
    expect(summary?.issues).toEqual(['场景兑现不足', '对白未改变局势'])
    expect(summary?.label).toBe('质量风险 2 项')
  })

  // D-22：事件密度三个维度此前没有任何本地兜底文案。后端漏下发 labels 时
  // （老章节 metadata、或某条路径没写 labels），密度不达标在前端完全不可见。
  it('falls back to local event density labels when backend labels are missing', () => {
    const summary = buildChapterQualitySummary(
      {
        chapter_number: 1,
        title: 'Chapter 1',
        summary: '',
        content: null,
        versions: [
          {
            id: 1,
            content: 'content',
            metadata: {
              quality_metrics: {
                scene_fulfillment_rate: 0.9,
                event_density_passed: false,
                state_change_interval_passed: false,
                long_chapter_density_passed: false,
              },
            },
          },
        ],
        evaluation: null,
        generation_status: 'waiting_for_confirm',
      },
      null,
    )

    expect(summary?.issues).toEqual(['事件密度不足', '局势变化间隔过长', '长章推进不足'])
  })

  // T-13 / T-14：三态字段的 null 是「不适用 / 未评估」，不是失败。
  // 把它显示成质量风险等于凭「没测」报红——这是本轮修掉的核心谎报。
  it('treats null tri-state metrics as not-applicable rather than failures', () => {
    const summary = buildChapterQualitySummary(
      {
        chapter_number: 1,
        title: 'Chapter 1',
        summary: '',
        content: null,
        versions: [
          {
            id: 1,
            content: 'content',
            metadata: {
              quality_metrics: {
                scene_fulfillment_rate: 0.9,
                dialogue_changes_state: null,
                event_density_passed: null,
                state_change_interval_passed: null,
                long_chapter_density_passed: null,
                event_density_evaluated: false,
                event_density_skip_reason: 'sample_too_short',
              },
            },
          },
        ],
        evaluation: null,
        generation_status: 'waiting_for_confirm',
      },
      null,
    )

    expect(summary?.issues).toEqual([])
    expect(summary?.tone).toBe('success')
  })
})
