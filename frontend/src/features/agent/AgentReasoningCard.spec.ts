import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import AgentReasoningCard from './AgentReasoningCard.vue'

describe('AgentReasoningCard', () => {
  it('将 reasoning 独立于正文显示，并在流式期间展开、完成后折叠', async () => {
    const wrapper = mount(AgentReasoningCard, {
      props: { text: '先读取项目上下文\n再调用工具', status: 'streaming', chunks: [{ sequence: 1, chunkIndex: 0, content: '先读取项目上下文\n' }, { sequence: 2, chunkIndex: 1, content: '再调用工具' }] },
    })
    expect(wrapper.get('[data-testid="agent-reasoning-card"]').text()).toContain('Provider 原始 reasoning')
    expect(wrapper.get('[data-testid="agent-reasoning-body"]').isVisible()).toBe(true)
    expect(wrapper.get('[data-testid="agent-reasoning-body"]').text()).toContain('再调用工具')
    await wrapper.setProps({ status: 'completed' })
    expect(wrapper.get('[data-testid="agent-reasoning-body"]').attributes('style')).toContain('display: none')
    await wrapper.get('[data-testid="agent-reasoning-toggle"]').trigger('click')
    expect(wrapper.get('[data-testid="agent-reasoning-body"]').isVisible()).toBe(true)
  })

  it('保留换行并显示失败状态', () => {
    const wrapper = mount(AgentReasoningCard, { props: { text: 'line-1\nline-2', status: 'failed' } })
    expect(wrapper.get('[data-testid="agent-reasoning-body"]').attributes('style')).toContain('display: none')
    expect(wrapper.get('[data-testid="agent-reasoning-card"]').text()).toContain('失败')
  })
})

  it('2000段历史只渲染有界窗口，同时保留完整复制内容', async () => {
    const chunks = Array.from({ length: 2000 }, (_, index) => ({
      id: `chunk-${index}`,
      runId: 'run-window',
      sequence: index + 1,
      chunkIndex: index,
      content: `reasoning-${index}`,
    }))
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
    const wrapper = mount(AgentReasoningCard, { props: { chunks, status: 'completed' } })
    await wrapper.get('[data-testid="agent-reasoning-toggle"]').trigger('click')
    await nextTick()
    const body = wrapper.get('[data-testid="agent-reasoning-body"]')
    expect(body.findAll('pre').length).toBeLessThan(40)
    expect(body.findAll('pre').length).toBeGreaterThan(0)
    expect(body.get('[data-testid="agent-reasoning-virtual-list"]').attributes('style')).toContain('min-height')

    await wrapper.get('[data-testid="agent-reasoning-copy"]').trigger('click')
    expect(writeText).toHaveBeenCalledTimes(1)
    expect(writeText.mock.calls[0][0]).toBe(chunks.map((chunk) => chunk.content).join(''))
    wrapper.unmount()
  })

  it('滚动窗口后只切换可见段，不改变历史总高度', async () => {
    const chunks = Array.from({ length: 120 }, (_, index) => ({
      id: `scroll-${index}`,
      runId: 'run-scroll',
      sequence: index + 1,
      chunkIndex: index,
      content: `scroll-reasoning-${index}`,
    }))
    const wrapper = mount(AgentReasoningCard, { props: { chunks, status: 'completed' } })
    await wrapper.get('[data-testid="agent-reasoning-toggle"]').trigger('click')
    await nextTick()
    const body = wrapper.get('[data-testid="agent-reasoning-body"]').element as HTMLElement
    const list = wrapper.get('[data-testid="agent-reasoning-virtual-list"]').element as HTMLElement
    const totalHeight = list.style.minHeight
    Object.defineProperty(body, 'clientHeight', { configurable: true, value: 200 })
    Object.defineProperty(body, 'scrollHeight', { configurable: true, value: 5000 })
    Object.defineProperty(body, 'scrollTop', { configurable: true, writable: true, value: 2500 })
    await wrapper.get('[data-testid="agent-reasoning-body"]').trigger('scroll')
    await nextTick()
    expect(list.style.minHeight).toBe(totalHeight)
    expect(wrapper.findAll('pre').length).toBeLessThan(40)
    expect(wrapper.text()).toContain('scroll-reasoning-')
    wrapper.unmount()
  })


const history = (start = 0, count = 120) => Array.from({ length: count }, (_, offset) => ({
  id: `stable-${start + offset}`, runId: 'run-a', sequence: start + offset,
  chunkIndex: start + offset, content: `entry-${start + offset}`,
}))
const settle = async () => { for (let i = 0; i < 8; i++) await nextTick() }

it('超出估计总高度仍只渲染末尾窗口，保留7000超界回归', async () => {
  const wrapper = mount(AgentReasoningCard, { props: { chunks: history(), status: 'completed' } })
  await wrapper.get('[data-testid="agent-reasoning-toggle"]').trigger('click')
  const body = wrapper.get('[data-testid="agent-reasoning-body"]')
  Object.defineProperties(body.element, {
    clientHeight: { configurable: true, value: 200 },
    scrollTop: { configurable: true, writable: true, value: 7000 },
  })
  await body.trigger('scroll'); await settle()
  expect(wrapper.findAll('pre').length).toBeLessThan(40)
  expect(wrapper.findAll('pre').map(row => row.text())).toContain('entry-119')
  expect(wrapper.findAll('pre').map(row => row.text())).not.toContain('entry-0')
  wrapper.unmount()
})

it('text-only 展开后真正显示正文与换行', async () => {
  const wrapper = mount(AgentReasoningCard, { props: { text: 'line-1\nline-2', status: 'failed' } })
  await wrapper.get('[data-testid="agent-reasoning-toggle"]').trigger('click'); await settle()
  expect(wrapper.get('pre').element.textContent).toBe('line-1\nline-2')
  wrapper.unmount()
})

it('折叠回收正文节点，折叠中复制仍完整，重开仍可读', async () => {
  const chunks = history(0, 2000)
  const writeText = vi.fn().mockResolvedValue(undefined)
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
  const wrapper = mount(AgentReasoningCard, { props: { chunks, status: 'completed' } })
  expect(wrapper.findAll('pre')).toHaveLength(0)
  await wrapper.get('[data-testid="agent-reasoning-toggle"]').trigger('click'); await settle()
  expect(wrapper.findAll('pre').length).toBeGreaterThan(0)
  await wrapper.get('[data-testid="agent-reasoning-toggle"]').trigger('click'); await settle()
  expect(wrapper.findAll('pre')).toHaveLength(0)
  await wrapper.get('[data-testid="agent-reasoning-copy"]').trigger('click')
  expect(writeText).toHaveBeenCalledWith(chunks.map(chunk => chunk.content).join(''))
  await wrapper.get('[data-testid="agent-reasoning-toggle"]').trigger('click'); await settle()
  expect(wrapper.get('pre').text()).toBe('entry-0')
  wrapper.unmount()
})

it('前插历史保留相同段内偏移而非保留旧scrollTop', async () => {
  const chunks = history(50, 120)
  const wrapper = mount(AgentReasoningCard, { props: { chunks, status: 'completed' } })
  await wrapper.get('[data-testid="agent-reasoning-toggle"]').trigger('click'); await settle()
  const body = wrapper.get('[data-testid="agent-reasoning-body"]')
  Object.defineProperty(body.element, 'clientHeight', { configurable: true, value: 200 })
  ;(body.element as HTMLElement).scrollTop = 1000
  await body.trigger('scroll'); await settle()
  const oldHeight = parseFloat((wrapper.get('[data-testid="agent-reasoning-virtual-list"]').element as HTMLElement).style.minHeight)
  await wrapper.setProps({ chunks: [...history(0, 50), ...chunks] }); await settle()
  const newHeight = parseFloat((wrapper.get('[data-testid="agent-reasoning-virtual-list"]').element as HTMLElement).style.minHeight)
  expect((body.element as HTMLElement).scrollTop).toBeCloseTo(1000 + newHeight - oldHeight, 1)
  wrapper.unmount()
})

it('ResizeObserver重测变化行、释放卸载元素，折叠重开保留中段锚点', async () => {
  let notify: ResizeObserverCallback = () => {}
  const observed = new Set<Element>()
  const unobserve = vi.fn((element: Element) => observed.delete(element))
  const disconnect = vi.fn(() => observed.clear())
  vi.stubGlobal('ResizeObserver', class {
    constructor(callback: ResizeObserverCallback) { notify = callback }
    observe(element: Element) { observed.add(element) }
    unobserve = unobserve
    disconnect = disconnect
  })
  const wrapper = mount(AgentReasoningCard, { props: { chunks: history(), status: 'completed' } })
  try {
    await wrapper.get('[data-testid="agent-reasoning-toggle"]').trigger('click'); await settle()
    const rows = wrapper.findAll('pre')
    const first = rows[0]!.element
    vi.spyOn(first, 'getBoundingClientRect').mockReturnValue({ height: 100 } as DOMRect)
    notify([], {} as ResizeObserver); await settle()
    expect((wrapper.findAll('pre')[1]!.element as HTMLElement).style.top).toBe('109px')
    const body = wrapper.get('[data-testid="agent-reasoning-body"]')
    Object.defineProperties(body.element, {
      clientHeight: { configurable: true, value: 200 },
      scrollHeight: { configurable: true, value: 5000 },
    })
    ;(body.element as HTMLElement).scrollTop = 1700
    await body.trigger('scroll'); await settle()
    expect(observed.has(first)).toBe(false)
    expect(unobserve).toHaveBeenCalledWith(first)
    const texts = wrapper.findAll('pre').map(row => row.text())
    await wrapper.get('[data-testid="agent-reasoning-toggle"]').trigger('click'); await settle()
    expect(wrapper.findAll('pre')).toHaveLength(0)
    expect([...observed].filter(element => element.tagName === 'PRE')).toHaveLength(0)
    await wrapper.get('[data-testid="agent-reasoning-toggle"]').trigger('click'); await settle()
    expect(wrapper.findAll('pre').map(row => row.text())).toEqual(texts)
  } finally { wrapper.unmount(); vi.unstubAllGlobals() }
  expect(disconnect).toHaveBeenCalledOnce()
})

it('流式首次尾随、同段增长尾随，上滚后追加保持阅读位置', async () => {
  const chunks = history(0, 2000)
  const wrapper = mount(AgentReasoningCard, { props: { chunks, status: 'streaming' } })
  await settle()
  expect(wrapper.findAll('pre').map(row => row.text())).toContain('entry-1999')
  const body = wrapper.get('[data-testid="agent-reasoning-body"]')
  const oldTop = (body.element as HTMLElement).scrollTop
  const grown = [...chunks.slice(0, -1), { ...chunks.at(-1)!, content: 'tail-growth\n'.repeat(100) }]
  await wrapper.setProps({ chunks: grown }); await settle()
  expect((body.element as HTMLElement).scrollTop).toBeGreaterThan(oldTop)
  expect(wrapper.findAll('pre').at(-1)!.text()).toContain('tail-growth')
  Object.defineProperties(body.element, {
    clientHeight: { configurable: true, value: 200 },
    scrollHeight: { configurable: true, value: 100000 },
  })
  ;(body.element as HTMLElement).scrollTop = 1000
  await body.trigger('scroll'); await settle()
  const oldRows = wrapper.findAll('pre').map(row => row.text())
  await wrapper.setProps({ chunks: [...grown, ...history(2000, 1)] }); await settle()
  expect((body.element as HTMLElement).scrollTop).toBe(1000)
  expect(wrapper.findAll('pre').map(row => row.text())).toEqual(oldRows)
  wrapper.unmount()
})

it('切换Run清空测量和手动展开状态，即使sequence重复也不串行高', async () => {
  const chunks = history(0, 120).map(({ id, runId, ...chunk }) => chunk)
  const wrapper = mount(AgentReasoningCard, { props: { chunks, contextKey: 'run-a', status: 'completed' } })
  await wrapper.get('[data-testid="agent-reasoning-toggle"]').trigger('click'); await settle()
  const body = wrapper.get('[data-testid="agent-reasoning-body"]')
  ;(body.element as HTMLElement).scrollTop = 1000
  await body.trigger('scroll'); await settle()
  await wrapper.setProps({ contextKey: 'run-b', chunks: chunks.map(chunk => ({ ...chunk, content: `other-${chunk.sequence}` })) }); await settle()
  expect(wrapper.findAll('pre')).toHaveLength(0)
  await wrapper.get('[data-testid="agent-reasoning-toggle"]').trigger('click'); await settle()
  expect(wrapper.get('pre').text()).toBe('other-0')
  expect((body.element as HTMLElement).scrollTop).toBe(0)
  wrapper.unmount()
})

it('复制失败给出反馈，成功计时器卸载时清理', async () => {
  vi.useFakeTimers()
  const writeText = vi.fn().mockRejectedValueOnce(new Error('denied')).mockResolvedValue(undefined)
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
  const wrapper = mount(AgentReasoningCard, { props: { text: 'copy-all', status: 'completed' } })
  try {
    const button = wrapper.get('[data-testid="agent-reasoning-copy"]')
    await button.trigger('click'); await settle()
    expect(button.text()).toContain('复制失败')
    await button.trigger('click'); await settle()
    expect(button.text()).toBe('已复制')
    expect(vi.getTimerCount()).toBe(1)
    wrapper.unmount()
    expect(vi.getTimerCount()).toBe(0)
  } finally { vi.useRealTimers() }
})

it('Ctrl+End在完成态精确到尾，Ctrl+Home离开尾随', async () => {
  const wrapper = mount(AgentReasoningCard, { props: { chunks: history(0, 2000), status: 'completed' } })
  await wrapper.get('[data-testid="agent-reasoning-toggle"]').trigger('click'); await settle()
  const body = wrapper.get('[data-testid="agent-reasoning-body"]')
  await body.trigger('keydown', { key: 'End', ctrlKey: true }); await settle()
  expect(wrapper.findAll('pre').at(-1)!.text()).toBe('entry-1999')
  expect(wrapper.findAll('pre').length).toBeLessThan(40)
  await body.trigger('keydown', { key: 'Home', ctrlKey: true }); await settle()
  expect(wrapper.get('pre').text()).toBe('entry-0')
  expect((body.element as HTMLElement).scrollTop).toBe(0)
  wrapper.unmount()
})
