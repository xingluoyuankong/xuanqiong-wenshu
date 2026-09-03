import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it } from 'vitest'
import shellSource from './AgentWorkspaceShell.vue?raw'
import AgentWorkspaceShell from './AgentWorkspaceShell.vue'

describe('AgentWorkspaceShell', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  const slots = {
    sidebar: '<div data-testid="shell-sidebar-slot">sidebar</div>',
    main: '<div data-testid="shell-main-slot">main</div>',
    activity: '<div data-testid="shell-activity-slot">activity</div>',
  }

  it('保留工作台根节点、布局插槽和未选项目状态说明', () => {
    const wrapper = mount(AgentWorkspaceShell, { slots })
    expect(wrapper.get('[data-testid="agent-workspace"]').attributes('data-testid')).toBe('agent-workspace')
    expect(wrapper.get('[data-testid="agent-status"]').text()).toContain('尚未选择小说项目')
    expect(wrapper.get('[data-testid="agent-status"]').text()).toContain('选择项目后，Agent 会限制在该项目范围内工作')
    expect(wrapper.get('[data-testid="shell-sidebar-slot"]').text()).toBe('sidebar')
    expect(wrapper.get('[data-testid="shell-main-slot"]').text()).toBe('main')
    expect(wrapper.get('[data-testid="shell-activity-slot"]').text()).toBe('activity')
  })

  it('提供左右图标窄轨道、中央聊天栏和保留挂载的侧面板', () => {
    const wrapper = mount(AgentWorkspaceShell, { slots })
    expect(wrapper.find('[data-testid="agent-left-rail"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="agent-right-rail"]').exists()).toBe(true)
    expect(wrapper.find('.agent-main').exists()).toBe(true)
    expect(wrapper.find('.agent-sidebar').exists()).toBe(true)
    expect(wrapper.find('.agent-activity').exists()).toBe(true)
    expect(wrapper.get('[data-testid="agent-left-panel"]').classes()).not.toContain('agent-panel-open')
    expect(wrapper.get('[data-testid="agent-right-panel"]').classes()).not.toContain('agent-panel-open')
  })

  it('点击左侧和右侧轨道时只展开对应面板，重复点击可关闭', async () => {
    const wrapper = mount(AgentWorkspaceShell, { slots })
    await wrapper.get('[data-testid="agent-rail-panel-left-project"]').trigger('click')
    expect(wrapper.get('[data-testid="agent-left-panel"]').classes()).toContain('agent-panel-open')
    expect(wrapper.get('[data-testid="agent-right-panel"]').classes()).not.toContain('agent-panel-open')
    expect(wrapper.get('[data-testid="agent-workspace"]').get('.agent-layout').classes()).toContain('has-left-panel')

    await wrapper.get('[data-testid="agent-rail-panel-right-log"]').trigger('click')
    expect(wrapper.get('[data-testid="agent-left-panel"]').classes()).toContain('agent-panel-open')
    expect(wrapper.get('[data-testid="agent-right-panel"]').classes()).toContain('agent-panel-open')

    await wrapper.get('[data-testid="agent-rail-panel-right-log"]').trigger('click')
    expect(wrapper.get('[data-testid="agent-right-panel"]').classes()).not.toContain('agent-panel-open')
  })

  it('支持忙碌状态和会话恢复状态', () => {
    const wrapper = mount(AgentWorkspaceShell, {
      props: { busy: true, projectTitle: '星河旧梦', sessionStatus: 'active', hasSelectedProject: true },
      slots,
    })
    expect(wrapper.get('[data-testid="agent-status"]').text()).toContain('星河旧梦')
    expect(wrapper.get('[data-testid="agent-status"]').text()).toContain('会话已恢复 · active')
    expect(wrapper.find('.status-dot.busy').exists()).toBe(true)
  })

  it('面板状态可以在重新挂载后恢复，并提供可访问性属性', async () => {
    const first = mount(AgentWorkspaceShell, { slots })
    await first.get('[data-testid="agent-rail-panel-left-tools"]').trigger('click')
    expect(first.get('[data-testid="agent-rail-panel-left-tools"]').attributes('aria-pressed')).toBe('true')
    first.unmount()

    const second = mount(AgentWorkspaceShell, { slots })
    expect(second.get('[data-testid="agent-left-panel"]').classes()).toContain('agent-panel-open')
    expect(second.get('[data-testid="agent-side-panel-close-left"]').attributes('aria-label')).toBe('关闭项目资源面板')
  })

  it('桌面和移动端布局契约以窄轨道、抽屉与安全区为核心', () => {
    expect(shellSource).toContain('grid-template-columns: 3.5rem 0 minmax(0, 1fr) 0 3.5rem;')
    expect(shellSource).toContain('agent-panel-open')
    expect(shellSource).toContain('@media (max-width: 960px)')
    expect(shellSource).toContain('position: fixed;')
    expect(shellSource).toContain('env(safe-area-inset-bottom)')
    expect(shellSource).toContain('min-width: 0')
    expect(shellSource).toContain('min-height: 0')
  })
})
