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

  it('does not let an empty runtime snapshot hide version quality metrics', () => {
    const metrics = resolveChapterQualityMetrics(
      {
        chapter_number: 1,
        title: 'Chapter 1',
        summary: '',
        content: null,
        versions: [{
          id: 1,
          content: 'content',
          metadata: { quality_metrics: { scene_fulfillment_rate: 0.25 } },
        }],
        evaluation: null,
        generation_status: 'waiting_for_confirm',
      },
      { quality_metrics: {} },
    )

    expect(metrics?.scene_fulfillment_rate).toBe(0.25)
  })

  it('merges partial runtime metrics with missing version fields without overriding explicit null', () => {
    const metrics = resolveChapterQualityMetrics(
      {
        chapter_number: 1,
        title: 'Chapter 1',
        summary: '',
        content: null,
        versions: [{
          id: 1,
          content: 'content',
          metadata: {
            quality_metrics: {
              ending_pressure_passed: false,
              event_density_passed: false,
            },
          },
        }],
        evaluation: null,
        generation_status: 'waiting_for_confirm',
      },
      {
        quality_metrics: {
          word_count: 1200,
          ending_pressure_passed: null,
        },
      },
    )

    expect(metrics?.word_count).toBe(1200)
    expect(metrics?.event_density_passed).toBe(false)
    expect(metrics?.ending_pressure_passed).toBeNull()
  })

  it('falls through empty version snapshots to final quality metrics', () => {
    const metrics = resolveChapterQualityMetrics(
      {
        chapter_number: 1,
        title: 'Chapter 1',
        summary: '',
        content: null,
        versions: [{
          id: 1,
          content: 'content',
          metadata: {
            quality_metrics: {},
            review_summaries: { final_quality_metrics: { scene_fulfillment_rate: 0.4 } },
          },
        }],
        evaluation: null,
        generation_status: 'waiting_for_confirm',
      },
      null,
    )

    expect(metrics?.scene_fulfillment_rate).toBe(0.4)
  })

  it('merges partial direct version metrics with nested final quality metrics', () => {
    const metrics = resolveChapterQualityMetrics(
      {
        chapter_number: 1,
        title: 'Chapter 1',
        summary: '',
        content: null,
        versions: [{
          id: 1,
          content: 'content',
          metadata: {
            quality_metrics: { word_count: 1800 },
            review_summaries: {
              final_quality_metrics: {
                ending_pressure_passed: false,
                event_density_passed: true,
              },
            },
          },
        }],
        evaluation: null,
        generation_status: 'waiting_for_confirm',
      },
      null,
    )

    expect(metrics?.word_count).toBe(1800)
    expect(metrics?.ending_pressure_passed).toBe(false)
    expect(metrics?.event_density_passed).toBe(true)
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

  it('does not turn a null scene fulfillment rate into a zero-percent risk', () => {
    const summary = buildChapterQualitySummary(
      {
        chapter_number: 1,
        title: 'Legacy chapter',
        summary: '',
        content: null,
        versions: [{
          id: 1,
          content: 'content',
          metadata: { quality_metrics: { scene_fulfillment_rate: null } },
        }],
        evaluation: null,
        generation_status: 'waiting_for_confirm',
      },
      null,
    )

    expect(summary?.issues).toEqual([])
    expect(summary?.label).toBe('质量未评估')
    expect(summary?.tone).toBe('warning')
  })

  it('does not treat a word-count-only snapshot as a quality pass', () => {
    const summary = buildChapterQualitySummary(
      {
        chapter_number: 1,
        title: 'Legacy word-only chapter',
        summary: '',
        content: null,
        versions: [{
          id: 1,
          content: 'content',
          metadata: { quality_metrics: { word_count: 3200 } },
        }],
        evaluation: null,
        generation_status: 'waiting_for_confirm',
      },
      null,
    )

    expect(summary?.label).toBe('质量未评估')
    expect(summary?.tone).toBe('warning')
    expect(summary?.issues).toEqual([])
  })

  it('surfaces a quality gate failure when no detailed metric is available', () => {
    const summary = buildChapterQualitySummary(
      {
        chapter_number: 1,
        title: 'Gate-only failure',
        summary: '',
        content: null,
        versions: [{ id: 1, content: 'content', metadata: { quality_metrics: { quality_gate_passed: false } } }],
        evaluation: null,
        generation_status: 'evaluation_failed',
      },
      null,
    )

    expect(summary?.label).toBe('质量门未通过')
    expect(summary?.tone).toBe('danger')
  })

  it('surfaces backend issue codes when labels and detailed metrics are absent', () => {
    const summary = buildChapterQualitySummary(
      {
        chapter_number: 1,
        title: 'Code-only failure',
        summary: '',
        content: null,
        versions: [{ id: 1, content: 'content', metadata: { quality_metrics: { quality_issue_codes: ['ending_pressure_missing'] } } }],
        evaluation: null,
        generation_status: 'evaluation_failed',
      },
      null,
    )

    expect(summary?.issues).toEqual(['质量问题 ending_pressure_missing'])
    expect(summary?.tone).toBe('warning')
  })

  it('surfaces nested summary codes when direct labels are missing', () => {
    const summary = buildChapterQualitySummary(
      {
        chapter_number: 1,
        title: 'Nested code-only failure',
        summary: '',
        content: null,
        versions: [{
          id: 1,
          content: 'content',
          metadata: {
            quality_metrics: {
              quality_issue_summary: { tone: 'danger', codes: ['critical_consistency_unresolved'] },
            },
          },
        }],
        evaluation: null,
        generation_status: 'evaluation_failed',
      },
      null,
    )

    expect(summary?.issues).toEqual(['质量问题 critical_consistency_unresolved'])
    expect(summary?.tone).toBe('danger')
  })

  it('keeps a null quality gate state as not assessed', () => {
    const summary = buildChapterQualitySummary(
      {
        chapter_number: 1,
        title: 'Unknown gate state',
        summary: '',
        content: null,
        versions: [{ id: 1, content: 'content', metadata: { quality_metrics: { quality_gate_passed: null } } }],
        evaluation: null,
        generation_status: 'waiting_for_confirm',
      },
      null,
    )

    expect(summary?.label).toBe('质量未评估')
    expect(summary?.tone).toBe('warning')
  })

  it('does not treat an evaluation-skip marker alone as a quality pass', () => {
    const summary = buildChapterQualitySummary(
      {
        chapter_number: 1,
        title: 'Legacy skipped-density chapter',
        summary: '',
        content: null,
        versions: [{
          id: 1,
          content: 'content',
          metadata: {
            quality_metrics: {
              event_density_evaluated: false,
              event_density_skip_reason: 'sample_too_short',
            },
          },
        }],
        evaluation: null,
        generation_status: 'waiting_for_confirm',
      },
      null,
    )

    expect(summary?.label).toBe('质量未评估')
    expect(summary?.tone).toBe('warning')
  })

  it('does not treat only-null tri-state metrics as a quality pass', () => {
    const summary = buildChapterQualitySummary(
      {
        chapter_number: 1,
        title: '未评估短章',
        summary: '',
        content: null,
        versions: [{
          id: 1,
          content: 'content',
          metadata: {
            quality_metrics: {
              dialogue_changes_state: null,
              ending_pressure_passed: null,
              event_density_evaluated: false,
              event_density_passed: null,
              state_change_interval_passed: null,
              long_chapter_density_passed: null,
              event_density_skip_reason: 'sample_too_short',
            },
          },
        }],
        evaluation: null,
        generation_status: 'waiting_for_confirm',
      },
      null,
    )

    expect(summary?.label).toBe('质量未评估')
    expect(summary?.tone).toBe('warning')
    expect(summary?.issues).toEqual([])
  })

  it('falls back from an empty direct label array to nested summary labels', () => {
    const summary = buildChapterQualitySummary(
      {
        chapter_number: 1,
        title: 'Legacy label snapshot',
        summary: '',
        content: null,
        versions: [{
          id: 1,
          content: 'content',
          metadata: {
            quality_metrics: {
              scene_fulfillment_rate: 0.9,
              quality_issue_labels: [],
              quality_issue_summary: {
                tone: 'warning',
                labels: ['嵌套旧字段问题'],
              },
            },
          },
        }],
        evaluation: null,
        generation_status: 'waiting_for_confirm',
      },
      null,
    )

    expect(summary?.issues).toEqual(['嵌套旧字段问题'])
    expect(summary?.tone).toBe('warning')
  })

  it('keeps empty direct labels from masking nested summary labels', () => {
    const source = String(buildChapterQualitySummary)
    const guard = 'directBackendLabels.length ? directBackendLabels : summaryBackendLabels'
    expect(source).toContain(guard)
    const sabotaged = source.replace(guard, 'directBackendLabels')
    expect(sabotaged).not.toContain(guard)
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

  it('surfaces explicit word-contract failures instead of reporting quality passed', () => {
    const summary = buildChapterQualitySummary(
      {
        chapter_number: 1,
        title: 'Word contract snapshot',
        summary: '',
        content: null,
        versions: [{
          id: 1,
          content: 'content',
          metadata: {
            quality_metrics: {
              scene_fulfillment_rate: 0.9,
              word_count_below_min: false,
              word_count_far_below_target: true,
              word_count_far_above_target: true,
              word_requirement_met: false,
            },
          },
        }],
        evaluation: null,
        generation_status: 'waiting_for_confirm',
      },
      null,
    )

    expect(summary?.issues).toEqual([
      '字数显著低于目标',
      '字数远超目标',
      '未满足字数要求',
    ])
    expect(summary?.tone).toBe('danger')
  })

  it('ignores stale density failures when the sample was not evaluated', () => {
    const summary = buildChapterQualitySummary(
      {
        chapter_number: 1,
        title: 'Short chapter',
        summary: '',
        content: null,
        versions: [{
          id: 1,
          content: 'content',
          metadata: {
            quality_metrics: {
              scene_fulfillment_rate: 0.9,
              event_density_evaluated: false,
              event_density_passed: false,
              state_change_interval_passed: false,
              long_chapter_density_passed: false,
            },
          },
        }],
        evaluation: null,
        generation_status: 'waiting_for_confirm',
      },
      null,
    )

    expect(summary?.issues).toEqual([])
    expect(summary?.tone).toBe('success')
  })

  it('chapter quality density guard remains wired to evaluated state', () => {
    const source = String(buildChapterQualitySummary)
    const guard = 'event_density_evaluated !== false && metrics.event_density_passed === false'
    expect(source).toContain(guard)
    const sabotaged = source.replace(guard, 'metrics.event_density_passed === false')
    expect(sabotaged).not.toContain(guard)
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
