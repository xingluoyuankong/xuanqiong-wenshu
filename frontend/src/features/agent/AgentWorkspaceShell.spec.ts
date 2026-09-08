import { enableAutoUnmount, mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

enableAutoUnmount(afterEach)
import shellSource from './AgentWorkspaceShell.vue?raw'
import AgentWorkspaceShell from './AgentWorkspaceShell.vue'

describe('AgentWorkspaceShell', () => {
  beforeEach(() => {
    window.localStorage.clear()
    Object.defineProperty(window, 'innerWidth', { configurable: true, writable: true, value: 1024 })
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


  it('窄屏抽屉互斥、持久化双开归一化并支持 Escape 关闭', async () => {
    Object.defineProperty(window, 'innerWidth', { configurable: true, writable: true, value: 390 })
    window.localStorage.setItem('xuanqiong-wenshu:agent-workspace-panels', JSON.stringify({ left: 'project', right: 'log' }))
    const wrapper = mount(AgentWorkspaceShell, { slots: {
      sidebar: '<div>sidebar</div>',
      main: '<div>main</div>',
      activity: '<div>activity</div>',
    } })
    expect(wrapper.get('[data-testid="agent-left-panel"]').classes()).toContain('agent-panel-open')
    expect(wrapper.get('[data-testid="agent-right-panel"]').classes()).not.toContain('agent-panel-open')
    await wrapper.get('[data-testid="agent-rail-panel-right-quality"]').trigger('click')
    expect(wrapper.get('[data-testid="agent-left-panel"]').classes()).not.toContain('agent-panel-open')
    expect(wrapper.get('[data-testid="agent-right-panel"]').classes()).toContain('agent-panel-open')
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await nextTick()
    expect(wrapper.get('[data-testid="agent-right-panel"]').classes()).not.toContain('agent-panel-open')
    wrapper.unmount()
  })


describe('AgentWorkspaceShell DOM focus follow-up', () => {
  const storageKey = 'xuanqiong-wenshu:agent-workspace-panels'
  let host: HTMLDivElement
  let originalWidth: number
  const resize = async (width: number) => {
    Object.defineProperty(window, 'innerWidth', { configurable: true, writable: true, value: width })
    window.dispatchEvent(new Event('resize'))
    await nextTick()
  }
  const mountShell = () => mount(AgentWorkspaceShell, {
    attachTo: host,
    slots: {
      sidebar: '<input data-testid="left-input" aria-label="项目搜索" />',
      main: '<button data-testid="main-action">聊天操作</button>',
      activity: '<input data-testid="right-input" aria-label="日志搜索" />',
    },
  })
  const selector = (id: string) => `[data-testid="${id}"]`

  beforeEach(() => {
    originalWidth = window.innerWidth
    window.localStorage.clear()
    Object.defineProperty(window, 'innerWidth', { configurable: true, writable: true, value: 650 })
    host = document.createElement('div')
    document.body.append(host)
  })
  afterEach(() => {
    host.remove()
    window.localStorage.clear()
    Object.defineProperty(window, 'innerWidth', { configurable: true, writable: true, value: originalWidth })
  })

  it.each(['left', 'right'] as const)('650px %s 打开聚焦关闭按钮，显式关闭返回准确触发按钮', async (side) => {
    const wrapper = mountShell()
    const id = side === 'left' ? 'tools' : 'quality'
    const trigger = wrapper.get<HTMLButtonElement>(selector(`agent-rail-panel-${side}-${id}`))
    trigger.element.focus()
    await trigger.trigger('click')
    const close = wrapper.get<HTMLButtonElement>(selector(`agent-side-panel-close-${side}`))
    expect(document.activeElement).toBe(close.element)
    expect(wrapper.get(selector(`agent-${side}-panel`)).attributes('aria-hidden')).toBe('false')
    await close.trigger('click')
    expect(document.activeElement).toBe(trigger.element)
    expect(wrapper.get(selector(`agent-${side}-panel`)).attributes('aria-hidden')).toBe('true')
  })

  it.each(['left', 'right'] as const)('%s 输入框内 Escape 关闭并返回当前面板触发按钮', async (side) => {
    const wrapper = mountShell()
    const id = side === 'left' ? 'characters' : 'progress'
    const trigger = wrapper.get<HTMLButtonElement>(selector(`agent-rail-panel-${side}-${id}`))
    await trigger.trigger('click')
    const input = wrapper.get<HTMLInputElement>(selector(`${side}-input`))
    input.element.focus()
    await input.trigger('keydown', { key: 'Escape' })
    expect(document.activeElement).toBe(trigger.element)
    expect(wrapper.get(selector(`agent-${side}-panel`)).attributes('aria-hidden')).toBe('true')
  })

  it('同侧切换与跨侧互斥后焦点进入新抽屉，关闭返回最新触发按钮', async () => {
    const wrapper = mountShell()
    await wrapper.get(selector('agent-rail-panel-left-project')).trigger('click')
    const tools = wrapper.get<HTMLButtonElement>(selector('agent-rail-panel-left-tools'))
    tools.element.focus()
    await tools.trigger('click')
    expect(document.activeElement).toBe(wrapper.get(selector('agent-side-panel-close-left')).element)
    const quality = wrapper.get<HTMLButtonElement>(selector('agent-rail-panel-right-quality'))
    quality.element.focus()
    await quality.trigger('click')
    expect(wrapper.get(selector('agent-left-panel')).attributes('aria-hidden')).toBe('true')
    expect(document.activeElement).toBe(wrapper.get(selector('agent-side-panel-close-right')).element)
    await wrapper.get(selector('agent-side-panel-close-right')).trigger('click')
    expect(document.activeElement).toBe(quality.element)
  })

  it('resize 651→650 双开归一化，隐藏右面板内的真实焦点返回右轨道', async () => {
    await resize(651)
    const wrapper = mountShell()
    await wrapper.get(selector('agent-rail-panel-left-project')).trigger('click')
    const right = wrapper.get<HTMLButtonElement>(selector('agent-rail-panel-right-log'))
    await right.trigger('click')
    expect(wrapper.get(selector('agent-left-panel')).attributes('aria-hidden')).toBe('false')
    expect(wrapper.get(selector('agent-right-panel')).attributes('aria-hidden')).toBe('false')
    wrapper.get<HTMLInputElement>(selector('right-input')).element.focus()
    await resize(650)
    expect(wrapper.get(selector('agent-left-panel')).attributes('aria-hidden')).toBe('false')
    expect(wrapper.get(selector('agent-right-panel')).attributes('aria-hidden')).toBe('true')
    expect(document.activeElement).toBe(right.element)
  })

  it.each(['main-action', 'left-input'])('resize 自动关闭右抽屉不抢走 %s 的焦点', async (focusedId) => {
    await resize(960)
    const wrapper = mountShell()
    await wrapper.get(selector('agent-rail-panel-left-project')).trigger('click')
    await wrapper.get(selector('agent-rail-panel-right-log')).trigger('click')
    const focused = wrapper.get<HTMLElement>(selector(focusedId))
    focused.element.focus()
    await resize(650)
    expect(wrapper.get(selector('agent-right-panel')).attributes('aria-hidden')).toBe('true')
    expect(document.activeElement).toBe(focused.element)
  })

  it('恢复持久化抽屉不抢焦点，Escape 可从内部返回对应轨道', async () => {
    window.localStorage.setItem(storageKey, JSON.stringify({ left: 'materials', right: 'log' }))
    const outside = document.createElement('button')
    host.append(outside)
    outside.focus()
    const wrapper = mountShell()
    await nextTick()
    expect(document.activeElement).toBe(outside)
    expect(wrapper.get(selector('agent-right-panel')).attributes('aria-hidden')).toBe('true')
    const input = wrapper.get<HTMLInputElement>(selector('left-input'))
    input.element.focus()
    await input.trigger('keydown', { key: 'Escape' })
    expect(document.activeElement).toBe(wrapper.get(selector('agent-rail-panel-left-materials')).element)
  })

  it('非模态 drawer 不拦截 Tab/Shift+Tab，不阻止聚焦主栏和对侧轨道', async () => {
    const wrapper = mountShell()
    await wrapper.get(selector('agent-rail-panel-left-project')).trigger('click')
    const input = wrapper.get<HTMLInputElement>(selector('left-input'))
    for (const shiftKey of [false, true]) {
      input.element.focus()
      const event = new KeyboardEvent('keydown', { key: 'Tab', shiftKey, bubbles: true, cancelable: true })
      expect(input.element.dispatchEvent(event)).toBe(true)
      expect(event.defaultPrevented).toBe(false)
    }
    for (const id of ['main-action', 'agent-rail-panel-right-log']) {
      const target = wrapper.get<HTMLElement>(selector(id))
      target.element.focus()
      await nextTick()
      expect(document.activeElement).toBe(target.element)
    }
    expect(wrapper.find('[aria-modal="true"]').exists()).toBe(false)
  })

  it('重复轨道关闭保留触发按钮焦点', async () => {
    const wrapper = mountShell()
    const trigger = wrapper.get<HTMLButtonElement>(selector('agent-rail-panel-left-project'))
    await trigger.trigger('click')
    trigger.element.focus()
    await trigger.trigger('click')
    expect(document.activeElement).toBe(trigger.element)
    expect(wrapper.get(selector('agent-left-panel')).attributes('aria-hidden')).toBe('true')
  })

  it('宽屏双开时 Escape 关闭焦点所在左侧而非无关右侧', async () => {
    await resize(960)
    const wrapper = mountShell()
    await wrapper.get(selector('agent-rail-panel-left-tools')).trigger('click')
    await wrapper.get(selector('agent-rail-panel-right-log')).trigger('click')
    const input = wrapper.get<HTMLInputElement>(selector('left-input'))
    input.element.focus()
    await input.trigger('keydown', { key: 'Escape' })
    expect(wrapper.get(selector('agent-left-panel')).attributes('aria-hidden')).toBe('true')
    expect(wrapper.get(selector('agent-right-panel')).attributes('aria-hidden')).toBe('false')
    expect(document.activeElement).toBe(wrapper.get(selector('agent-rail-panel-left-tools')).element)
  })
})
