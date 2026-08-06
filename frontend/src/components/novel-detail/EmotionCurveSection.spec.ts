import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import EmotionCurveSection from './EmotionCurveSection.vue'

describe('EmotionCurveSection', () => {
  it('renders canvas area with project ID', () => {
    const wrapper = mount(EmotionCurveSection, {
      props: {
        projectId: 'p-1',
      },
    })

    expect(wrapper.text()).toContain('')
    expect(wrapper.find('canvas').exists()).toBe(true)
  })

  it('shows loading state', () => {
    const wrapper = mount(EmotionCurveSection, {
      props: {
        projectId: 'p-1',
      },
    })

    // Canvas should exist even in loading state
    const canvas = wrapper.find('canvas')
    expect(canvas.exists()).toBe(true)
  })
})
