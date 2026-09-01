import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import shellSource from './AgentWorkspaceShell.vue?raw'
import workspaceSource from '@/views/AgentWorkspace.vue?raw'

import AgentWorkspaceShell from './AgentWorkspaceShell.vue'

describe('AgentWorkspaceShell', () => {
  it('保留工作台根节点、布局插槽和未选项目状态说明', () => {
    const wrapper = mount(AgentWorkspaceShell, {
      slots: {
        sidebar: '<div data-testid="shell-sidebar-slot">sidebar</div>',
        main: '<div data-testid="shell-main-slot">main</div>',
        activity: '<div data-testid="shell-activity-slot">activity</div>',
      },
    })

    expect(wrapper.get('[data-testid="agent-workspace"]').attributes('data-testid')).toBe('agent-workspace')
    expect(wrapper.get('[data-testid="agent-status"]').text()).toContain('尚未选择小说项目')
    expect(wrapper.get('[data-testid="agent-status"]').text()).toContain('选择项目后，Agent 会限制在该项目范围内工作')
    expect(wrapper.get('[data-testid="shell-sidebar-slot"]').text()).toBe('sidebar')
    expect(wrapper.get('[data-testid="shell-main-slot"]').text()).toBe('main')
    expect(wrapper.get('[data-testid="shell-activity-slot"]').text()).toBe('activity')
  })

  it('提供窄侧栏、主聊天栏和独立活动栏的结构钩子', () => {
    const wrapper = mount(AgentWorkspaceShell, {
      slots: {
        sidebar: '<div>sidebar</div>',
        main: '<div>main</div>',
        activity: '<div>activity</div>',
      },
    })

    expect(wrapper.find('.agent-layout').exists()).toBe(true)
    expect(wrapper.find('.agent-sidebar').exists()).toBe(true)
    expect(wrapper.find('.agent-main').exists()).toBe(true)
    expect(wrapper.find('.agent-activity').exists()).toBe(true)
    expect(wrapper.find('.agent-sidebar').attributes('style')).toBeUndefined()
  })

  it('显示恢复的会话状态与忙碌标识', () => {
    const wrapper = mount(AgentWorkspaceShell, {
      props: {
        busy: true,
        projectTitle: '星河旧梦',
        sessionStatus: 'active',
        hasSelectedProject: true,
      },
    })

    expect(wrapper.get('[data-testid="agent-status"]').text()).toContain('星河旧梦')
    expect(wrapper.get('[data-testid="agent-status"]').text()).toContain('会话已恢复 · active')
    expect(wrapper.find('.status-dot.busy').exists()).toBe(true)
  })


  it('把紧凑侧栏、聊天主栏和右侧活动栏的宽度约束集中在壳层', () => {
    expect(shellSource).toContain('grid-template-columns: minmax(160px, 11rem) minmax(0, 1fr) minmax(220px, 15rem);')
    expect(shellSource).toContain('grid-template-columns: minmax(156px, 10.5rem) minmax(0, 1fr) minmax(208px, 14rem);')
    expect(workspaceSource).not.toContain('grid-template-columns: minmax(210px, 0.85fr) minmax(0, 1.8fr) minmax(210px, 0.75fr);')
    expect(workspaceSource).toContain('max-height: min(11rem, 18vh);')
    expect(workspaceSource).toContain('class="workspace-section workspace-inspector-section"')
    expect(workspaceSource).toContain('data-testid="agent-inspector-section"')
    expect(workspaceSource.indexOf('data-testid="agent-log-panel"')).toBeLessThan(
      workspaceSource.indexOf('data-testid="agent-inspector-section"'),
    )
  })

  it('把中窄与手机断点的聊天优先规则固定为 CSS contract', () => {
    expect(shellSource).toContain('@media (max-width: 880px)')
    expect(shellSource).toContain('grid-template-columns: minmax(0, 1fr);')
    expect(shellSource).toContain('.agent-main { grid-row: 1; }')
    expect(shellSource).toContain('.agent-sidebar { position: static; grid-row: 2; max-height: none; overflow: visible; }')
    expect(shellSource).toContain('.agent-activity { position: static; grid-row: 3; max-height: none; overflow: visible; }')
    expect(shellSource).toContain('@media (max-width: 650px)')
    expect(shellSource).toContain('.agent-layout { grid-template-columns: 1fr; }')
    expect(shellSource).toContain('.agent-sidebar, .agent-main, .agent-activity { grid-column: auto; position: static; max-height: none; overflow: visible; }')
    expect(shellSource).toMatch(/\.agent-main\s*\{\s*min-height: min\(72vh, 56rem\);\s*\}/)
  })
  it('把右栏运行日志限制为有界渲染窗口', () => {
    expect(workspaceSource).toContain('const LOG_RENDER_LIMIT = 120')
    expect(workspaceSource).toContain('const visibleLogEvents = computed(() => events.value.slice(-LOG_RENDER_LIMIT))')
    expect(workspaceSource).toContain('const hiddenLogEventCount = computed(() => Math.max(0, events.value.length - visibleLogEvents.value.length))')
    expect(workspaceSource).toContain('v-if="hiddenLogEventCount" class="workspace-log-window"')
    expect(workspaceSource).toContain('v-for="event in visibleLogEvents"')
  })
})
