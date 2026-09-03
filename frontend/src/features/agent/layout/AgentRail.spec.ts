import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AgentRail, { type AgentRailPanelDefinition } from './AgentRail.vue'

const panels: AgentRailPanelDefinition[] = [
  { id: 'project', label: '项目', icon: 'project' },
  { id: 'content', label: '内容', icon: 'content', badge: 2 },
  { id: 'disabled', label: '禁用项', disabled: true },
]

describe('AgentRail', () => {
  it('renders an icon rail with accessible buttons and active state', () => {
    const wrapper = mount(AgentRail, {
      props: { side: 'left', panels, activePanel: 'content' },
    })

    expect(wrapper.attributes('data-side')).toBe('left')
    expect(wrapper.findAll('button')).toHaveLength(3)
    expect(wrapper.get('[data-testid="agent-rail-panel-left-content"]').attributes('aria-pressed')).toBe('true')
    expect(wrapper.get('[data-testid="agent-rail-panel-left-content"]').attributes('aria-label')).toContain('内容')
    expect(wrapper.get('.agent-rail__badge').text()).toBe('2')
    expect(wrapper.findAll('svg')).toHaveLength(3)
  })

  it('emits close events when the active panel is clicked again', async () => {
    const wrapper = mount(AgentRail, {
      props: { side: 'right', panels, activePanel: 'project' },
    })

    await wrapper.get('[data-testid="agent-rail-panel-right-project"]').trigger('click')

    expect(wrapper.emitted('toggle')).toEqual([['project']])
    expect(wrapper.emitted('select')).toEqual([['project']])
    expect(wrapper.emitted('update:activePanel')).toEqual([[null]])
    expect(wrapper.emitted('close')).toEqual([[]])
    expect(wrapper.emitted('open')).toBeUndefined()
  })

  it('emits open and update events when a different panel is clicked', async () => {
    const wrapper = mount(AgentRail, {
      props: { side: 'left', panels, activePanel: 'project' },
    })

    await wrapper.get('[data-testid="agent-rail-panel-left-content"]').trigger('click')

    expect(wrapper.emitted('toggle')).toEqual([['content']])
    expect(wrapper.emitted('update:activePanel')).toEqual([['content']])
    expect(wrapper.emitted('open')).toEqual([['content']])
    expect(wrapper.emitted('close')).toBeUndefined()
  })

  it('supports panelDefinitions as an explicit alias and ignores disabled panels', async () => {
    const wrapper = mount(AgentRail, {
      props: {
        side: 'right',
        panels: [],
        panelDefinitions: [{ id: 'log', label: '日志', icon: 'log' }],
      },
    })

    expect(wrapper.get('[data-testid="agent-rail-panel-right-log"]')).toBeTruthy()
    await wrapper.get('[data-testid="agent-rail-panel-right-log"]').trigger('click')
    expect(wrapper.emitted('open')).toEqual([['log']])

    const disabledWrapper = mount(AgentRail, { props: { side: 'left', panels } })
    await disabledWrapper.get('[data-testid="agent-rail-panel-left-disabled"]').trigger('click')
    expect(disabledWrapper.emitted('toggle')).toBeUndefined()
  })

  it('renders custom icon text without loading an icon library', () => {
    const wrapper = mount(AgentRail, {
      props: {
        side: 'left',
        panels: [{ id: 'custom', label: '自定义', icon: '◆' }],
      },
    })

    expect(wrapper.find('svg').exists()).toBe(false)
    expect(wrapper.get('.agent-rail__icon').text()).toBe('◆')
  })
})

