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
})
