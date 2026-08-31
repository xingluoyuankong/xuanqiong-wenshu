import { readFileSync } from 'node:fs'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import WDVersionDetailModal from './WDVersionDetailModal.vue'

describe('WDVersionDetailModal', () => {
  it('展示版本 metadata 中的质量指标快照', () => {
    const wrapper = mount(WDVersionDetailModal, {
      props: {
        show: true,
        detailVersionIndex: 0,
        isCurrent: true,
        version: {
          content: '门外脚步声停住。\n“你到底隐瞒了什么？”\n对方终于改口。',
          style: '标准',
          metadata: {
            quality_metrics: {
              word_count: 3200,
              scene_fulfillment_rate: 0.75,
              fulfilled_scene_count: 3,
              scene_count: 4,
              dialogue_changes_state: true,
              long_chapter_density_passed: null,
              state_change_interval_passed: true,
              ending_pressure_passed: false,
              static_description_risk: false,
            },
            generation_call_metrics: [
              {
                label: 'draft_candidate_1',
                attempts: 2,
                estimated_total_tokens: 4200,
                effective_max_tokens: 16800,
                provider_error_type: 'output_token_limit',
              },
            ],
          }
        }
      }
    })

    expect(wrapper.text()).toContain('质量快照')
    expect(wrapper.text()).toContain('字数：3200')
    expect(wrapper.text()).toContain('场景兑现：75%')
    expect(wrapper.text()).toContain('对白改局势：通过')
    expect(wrapper.text()).toContain('长章密度：不适用')
    expect(wrapper.text()).toContain('局势变化间隔：达标')
    expect(wrapper.text()).toContain('章末递压：未通过')
    expect(wrapper.text()).toContain('draft_candidate_1')
    expect(wrapper.text()).toContain('4200 tokens')
    expect(wrapper.text()).toContain('16800')
    expect(wrapper.text()).toContain('output_token_limit')
  })

  it('短样本未评估时明确显示未评估原因，而不是不适用', () => {
    const wrapper = mount(WDVersionDetailModal, {
      props: {
        show: true,
        detailVersionIndex: 0,
        isCurrent: true,
        version: {
          content: '短正文',
          metadata: {
            quality_metrics: {
              event_density_evaluated: false,
              event_density_skip_reason: 'sample_too_short',
              event_density_passed: null,
            },
          },
        },
      },
    })

    expect(wrapper.text()).toContain('事件密度：未评估（样本过短）')
    expect(wrapper.text()).not.toContain('事件密度：不适用')
  })

  it('缺失场景兑现率时显示占位符而不是 0%', () => {
    const wrapper = mount(WDVersionDetailModal, {
      props: {
        show: true,
        detailVersionIndex: 0,
        isCurrent: true,
        version: {
          content: '旧快照正文',
          metadata: { quality_metrics: { scene_fulfillment_rate: null } },
        },
      },
    })

    expect(wrapper.text()).toContain('场景兑现：—')
    expect(wrapper.text()).not.toContain('场景兑现：0%')
  })

  it('未评估标记必须压过陈旧的失败值', () => {
    const wrapper = mount(WDVersionDetailModal, {
      props: {
        show: true,
        detailVersionIndex: 0,
        isCurrent: true,
        version: {
          content: '旧短正文',
          metadata: {
            quality_metrics: {
              event_density_evaluated: false,
              event_density_skip_reason: 'sample_too_short',
              // 反向验证：旧快照若仍残留 false，不能因此被详情页误报为真实失败。
              event_density_passed: false,
            },
          },
        },
      },
    })

    expect(wrapper.text()).toContain('事件密度：未评估（样本过短）')
    expect(wrapper.text()).not.toContain('事件密度：不足')
  })

  it('三态质量字段的 null 不应被详情页误报为通过或失败', () => {
    const wrapper = mount(WDVersionDetailModal, {
      props: {
        show: true,
        detailVersionIndex: 0,
        isCurrent: true,
        version: {
          content: '未评估正文',
          metadata: {
            quality_metrics: {
              ending_pressure_passed: null,
              static_description_risk: null,
            },
          },
        },
      },
    })

    expect(wrapper.text()).toContain('章末递压：不适用')
    expect(wrapper.text()).toContain('静态描写风险：不适用')
    expect(wrapper.text()).not.toContain('章末递压：未通过')
    expect(wrapper.text()).not.toContain('静态描写风险：可控')
  })

  it('shows explicit word-contract failures in the version quality snapshot', () => {
    const wrapper = mount(WDVersionDetailModal, {
      props: {
        show: true,
        detailVersionIndex: 0,
        isCurrent: true,
        version: {
          content: '字数契约正文',
          metadata: {
            quality_metrics: {
              word_count: 9000,
              word_count_far_above_target: true,
              word_requirement_met: false,
            },
          },
        },
      },
    })

    expect(wrapper.text()).toContain('字数要求：未满足')
    expect(wrapper.text()).not.toContain('字数要求：不适用')
  })

  it('空的直接质量快照不应遮蔽后备质量快照', () => {
    const wrapper = mount(WDVersionDetailModal, {
      props: {
        show: true,
        detailVersionIndex: 0,
        isCurrent: true,
        version: {
          content: '后备快照正文',
          metadata: {
            quality_metrics: {},
            review_summaries: {
              final_quality_metrics: {
                scene_fulfillment_rate: 0.4,
              },
            },
          },
        },
      },
    })

    expect(wrapper.text()).toContain('场景兑现：40%')
  })

  it('非空但不完整的直接质量快照也不能遮蔽后备三态字段', () => {
    const wrapper = mount(WDVersionDetailModal, {
      props: {
        show: true,
        detailVersionIndex: 0,
        isCurrent: true,
        version: {
          content: '部分快照正文',
          metadata: {
            quality_metrics: { word_count: 1800 },
            review_summaries: {
              final_quality_metrics: {
                ending_pressure_passed: false,
                event_density_passed: true,
              },
            },
          },
        },
      },
    })

    expect(wrapper.text()).toContain('字数：1800')
    expect(wrapper.text()).toContain('章末递压：未通过')
    expect(wrapper.text()).toContain('事件密度：达标')
  })

  it('缺失一致性布尔字段不应被当作失败或未执行', () => {
    const wrapper = mount(WDVersionDetailModal, {
      props: {
        show: true,
        detailVersionIndex: 0,
        isCurrent: true,
        version: {
          content: '旧一致性摘要',
          metadata: {
            review_summaries: {
              consistency: {
                violations: [],
                summary: '历史摘要未记录布尔字段',
              },
            },
          },
        },
      },
    })

    expect(wrapper.text()).toContain('状态：不适用')
    expect(wrapper.text()).toContain('自动修复：不适用')
    expect(wrapper.text()).not.toContain('状态：发现问题')
    expect(wrapper.text()).not.toContain('自动修复：未执行')
  })

  it('一致性布尔字段必须经过显式三态格式化', () => {
    const source = readFileSync('src/components/writing-desk/dialogs/WDVersionDetailModal.vue', 'utf8')
    expect(source).toContain('formatTriState(consistencySummary.is_consistent')
    expect(source).toContain('formatTriState(consistencySummary.auto_fix_applied')
    expect(source).not.toContain('consistencySummary.is_consistent ? pick')
    expect(source).not.toContain('consistencySummary.auto_fix_applied ? pick')
  })

  it('保留 runtime 字数中的零值而不是静默隐藏', () => {
    const wrapper = mount(WDVersionDetailModal, {
      props: {
        show: true,
        detailVersionIndex: 0,
        isCurrent: true,
        version: {
          content: '零字数运行快照',
          metadata: {
            actual_word_count: 0,
            min_word_count: 0,
            target_word_count: 3000,
          },
        },
      },
    })

    expect(wrapper.text()).toContain('实际 0 字')
    expect(wrapper.text()).toContain('最低 0 字')
    expect(wrapper.text()).toContain('目标 3000 字')
  })

  it('runtime 字数展示必须显式判断 nullish，而不能使用真假判断', () => {
    const source = readFileSync('src/components/writing-desk/dialogs/WDVersionDetailModal.vue', 'utf8')
    expect(source).toContain('hasRuntimeWordValue(actual)')
    expect(source).toContain('hasRuntimeWordValue(min)')
    expect(source).not.toContain('if (actual) parts.push')
    expect(source).not.toContain('if (min) parts.push')
  })

  it('质量三态字段必须经过显式三态格式化', () => {
    const source = readFileSync('src/components/writing-desk/dialogs/WDVersionDetailModal.vue', 'utf8')
    expect(source).toContain('formatTriState(qualityMetrics.ending_pressure_passed')
    expect(source).toContain('formatTriState(qualityMetrics.static_description_risk')
    expect(source).not.toContain('qualityMetrics.ending_pressure_passed ? pick')
    expect(source).not.toContain('qualityMetrics.static_description_risk ? pick')
    expect(source).toContain('Object.keys(merged).length')
    expect(source).not.toContain("if (direct && typeof direct === 'object'")
  })
})
