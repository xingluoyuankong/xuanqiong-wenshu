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
              ending_pressure_passed: false,
              static_description_risk: false,
            }
          }
        }
      }
    })

    expect(wrapper.text()).toContain('质量快照')
    expect(wrapper.text()).toContain('字数：3200')
    expect(wrapper.text()).toContain('场景兑现：75%')
    expect(wrapper.text()).toContain('对白改局势：通过')
    expect(wrapper.text()).toContain('章末递压：未通过')
  })
})
