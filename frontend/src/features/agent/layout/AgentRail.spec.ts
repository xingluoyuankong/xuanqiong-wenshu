import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import postcss from 'postcss'
import railSource from './AgentRail.vue?raw'
import shellSource from '../AgentWorkspaceShell.vue?raw'
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



// CSS contracts complement jsdom event tests; actual clipping/hit testing is
// checked by the real-browser owner, not inferred from synthetic geometry.
const mobileRule = (source: string, selector: string) => {
  const css = source.split('<style scoped>')[1]!.split('</style>')[0]!
  const declarations: Record<string, string> = {}
  postcss.parse(css).walkAtRules('media', (media) => {
    if (media.params !== '(max-width: 650px)') return
    media.walkRules((rule) => {
      if (rule.selector !== selector) return
      rule.walkDecls((decl) => { declarations[decl.prop] = decl.value })
    })
  })
  return declarations
}

describe('AgentRail mobile partition regression', () => {
  it('<=650px 每个 rail 限宽且独立横向滚动，不将按钮溢出交给相邻轨道', () => {
    const css = mobileRule(railSource, '.agent-rail')
    expect(css['overflow-x']).toBe('auto')
    expect(css['overflow-y']).toBe('hidden')
    expect(css.width).toBe('100%')
    expect(css['max-width']).toBe('100%')
    expect(css['min-width']).toBe('0')
    expect(css['justify-content']).toBe('flex-start')
    expect(css['flex-wrap']).toBe('nowrap')
    expect(css['overscroll-behavior-x']).toBe('contain')
  })

  it('移动按钮保持至少44px命中宽高，不用flex压缩塞满半屏', () => {
    const css = mobileRule(railSource, '.agent-rail__button')
    expect(css.flex).toBe('0 0 2.75rem')
    expect(css.width).toBe('2.75rem')
    expect(css['min-width']).toBe('44px')
    expect(css['min-height']).toBe('44px')
  })

  it('Shell 左右半屏分区裁剪后代溢出，保留中央间隙和底部安全区', () => {
    const common = mobileRule(shellSource, '.agent-sidebar-rail, .agent-activity-rail')
    expect(common.overflow).toBe('hidden')
    expect(common['box-sizing']).toBe('border-box')
    expect(common.bottom).toBe('calc(0.55rem + env(safe-area-inset-bottom))')
    const left = mobileRule(shellSource, '.agent-sidebar-rail')
    const right = mobileRule(shellSource, '.agent-activity-rail')
    expect(left.left).toBe('0.55rem')
    expect(right.right).toBe('0.55rem')
    expect(left.width).toBe('calc(50% - 0.8rem)')
    expect(right.width).toBe(left.width)
  })

  it('六个左按钮与五个右按钮全部保留，末尾tools和开头log分派各自事件', async () => {
    const host = document.createElement('div')
    document.body.append(host)
    const left = mount(AgentRail, { attachTo: host, props: {
      side: 'left', panels: ['project', 'content', 'characters', 'world', 'materials', 'tools']
        .map((id) => ({ id, label: id })),
    } })
    const right = mount(AgentRail, { attachTo: host, props: {
      side: 'right', panels: ['log', 'run', 'progress', 'artifact', 'quality']
        .map((id) => ({ id, label: id })),
    } })
    try {
      expect(left.findAll('button')).toHaveLength(6)
      expect(right.findAll('button')).toHaveLength(5)
      const tools = left.get<HTMLButtonElement>('[data-testid="agent-rail-panel-left-tools"]')
      const log = right.get<HTMLButtonElement>('[data-testid="agent-rail-panel-right-log"]')
      tools.element.focus()
      expect(document.activeElement).toBe(tools.element)
      await tools.trigger('click')
      expect(left.emitted('toggle')).toEqual([['tools']])
      expect(right.emitted('toggle')).toBeUndefined()
      log.element.focus()
      expect(document.activeElement).toBe(log.element)
      await log.trigger('click')
      expect(right.emitted('toggle')).toEqual([['log']])
      expect(left.emitted('toggle')).toEqual([['tools']])
    } finally {
      left.unmount()
      right.unmount()
      host.remove()
    }
  })
})
