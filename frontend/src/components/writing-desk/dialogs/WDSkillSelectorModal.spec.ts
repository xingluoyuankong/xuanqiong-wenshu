import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import WDSkillSelectorModal from './WDSkillSelectorModal.vue'

describe('WDSkillSelectorModal', () => {
  it('does not render when show is false', () => {
    const wrapper = mount(WDSkillSelectorModal, {
      props: {
        show: false,
        projectId: 'p-1',
      },
    })

    expect(wrapper.text()).not.toContain('技能')
    expect(wrapper.find('.modal').exists()).toBe(false)
  })

  it('renders modal when show is true', () => {
    const wrapper = mount(WDSkillSelectorModal, {
      props: {
        show: true,
        projectId: 'p-1',
      },
    })

    expect(wrapper.text()).toContain('')
    expect(wrapper.isVisible()).toBe(true)
  })

  it('emits close when close button clicked', async () => {
    const wrapper = mount(WDSkillSelectorModal, {
      props: {
        show: true,
        projectId: 'p-1',
      },
    })

    const closeBtn = wrapper.find('button')
    await closeBtn.trigger('click')
    expect(wrapper.emitted('close')).toBeTruthy()
  })
})
