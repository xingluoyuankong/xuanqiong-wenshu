import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ConversationInput from './ConversationInput.vue'

describe('ConversationInput', () => {
  it('supports selecting multiple options for multi_choice controls', async () => {
    const wrapper = mount(ConversationInput, {
      props: {
        loading: false,
        uiControl: {
          type: 'multi_choice',
          options: [
            { id: 'sea', label: '海洋世界' },
            { id: 'survival', label: '极限生存' },
            { id: 'civilization', label: '文明体系' },
          ],
          placeholder: '继续补充你的灵感',
        },
      },
    })

    const optionButtons = wrapper.findAll('.ci-option')
    await optionButtons[0].trigger('click')
    await optionButtons[1].trigger('click')
    await wrapper.find('form').trigger('submit.prevent')

    expect(wrapper.emitted('submit')).toBeTruthy()
    expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({
      id: 'multi_choice',
      selected_ids: ['sea', 'survival'],
      value: '海洋世界，极限生存',
    })
  })

  it('keeps single_choice controls exclusive', async () => {
    const wrapper = mount(ConversationInput, {
      props: {
        loading: false,
        uiControl: {
          type: 'single_choice',
          options: [
            { id: 'a', label: '方案A' },
            { id: 'b', label: '方案B' },
          ],
        },
      },
    })

    const optionButtons = wrapper.findAll('.ci-option')
    await optionButtons[0].trigger('click')
    await optionButtons[1].trigger('click')
    await wrapper.find('form').trigger('submit.prevent')

    expect(wrapper.emitted('submit')).toBeTruthy()
    expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({
      id: 'b',
      selected_ids: ['b'],
      value: '方案B',
    })
  })
})
