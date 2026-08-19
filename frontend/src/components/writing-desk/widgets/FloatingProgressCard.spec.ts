import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import FloatingProgressCard from './FloatingProgressCard.vue'
import { GENERATION_STAGE_POINTS } from '@/utils/chapterGeneration'

const baseProps = {
  visible: true,
  title: '第 12 章',
  stage: 'generate_variants',
  status: 'generating',
  progressPercent: 34,
  wordCount: 1860,
}

const readPercent = (text: string): number => Number(text.replace(/[^\d]/g, ''))

describe('FloatingProgressCard 渲染与进度', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('可见时渲染标题、阶段名与进度条', () => {
    const wrapper = mount(FloatingProgressCard, { props: baseProps })

    expect(wrapper.find('.floating-progress-card').exists()).toBe(true)
    expect(wrapper.find('.floating-progress-card__title').text()).toBe('第 12 章')
    expect(wrapper.find('.floating-progress-card__stage').text()).toBe('正在生成正文')
    expect(wrapper.find('.floating-progress-card').classes()).toContain('floating-progress-card--active')
    expect(wrapper.find('.floating-progress-card__track').attributes('role')).toBe('progressbar')
    wrapper.unmount()
  })

  it('不可见时不渲染任何内容', () => {
    const wrapper = mount(FloatingProgressCard, { props: { ...baseProps, visible: false } })
    expect(wrapper.find('.floating-progress-card').exists()).toBe(false)
    wrapper.unmount()
  })

  it('进度随时间均匀爬升，且不越过当前阶段上界', async () => {
    const wrapper = mount(FloatingProgressCard, { props: baseProps })

    vi.advanceTimersByTime(1_500)
    await nextTick()
    const first = readPercent(wrapper.find('.floating-progress-card__percent').text())
    expect(first).toBeGreaterThan(0)

    vi.advanceTimersByTime(8_000)
    await nextTick()
    const second = readPercent(wrapper.find('.floating-progress-card__percent').text())
    expect(second).toBeGreaterThan(first)
    expect(second).toBeLessThanOrEqual(GENERATION_STAGE_POINTS.generate_variants.end)
    expect(wrapper.find('.floating-progress-card__track').attributes('aria-valuenow')).toBe(String(second))
    wrapper.unmount()
  })

  it('完成时精确显示 100% 并切到成功色条', async () => {
    const wrapper = mount(FloatingProgressCard, { props: baseProps })
    vi.advanceTimersByTime(2_000)

    await wrapper.setProps({ status: 'successful', stage: 'successful' })
    await nextTick()

    expect(readPercent(wrapper.find('.floating-progress-card__percent').text())).toBe(100)
    expect(wrapper.find('.floating-progress-card').classes()).toContain('floating-progress-card--success')
    expect(wrapper.find('.floating-progress-card__bar').classes()).toContain('floating-progress-card__bar--success')
    expect(wrapper.find('.floating-progress-card__fun').exists()).toBe(false)
    wrapper.unmount()
  })

  it('失败后停在当前值，不继续爬升', async () => {
    const wrapper = mount(FloatingProgressCard, { props: baseProps })
    vi.advanceTimersByTime(3_000)
    await nextTick()
    const frozen = readPercent(wrapper.find('.floating-progress-card__percent').text())

    await wrapper.setProps({ status: 'failed' })
    vi.advanceTimersByTime(30_000)
    await nextTick()

    expect(readPercent(wrapper.find('.floating-progress-card__percent').text())).toBe(frozen)
    expect(wrapper.find('.floating-progress-card__bar').classes()).toContain('floating-progress-card__bar--error')
    wrapper.unmount()
  })

  it('字数、任务号、重试次数合并成一行', () => {
    const wrapper = mount(FloatingProgressCard, {
      props: {
        ...baseProps,
        taskId: 'abcdef1234567890',
        taskStatus: 'running',
        retryCount: 2,
        taskRecovered: true,
      },
    })

    const meta = wrapper.find('.floating-progress-card__meta').text()
    expect(meta).toContain('1,860 字')
    expect(meta).toContain('任务 abcdef12')
    expect(meta).toContain('运行中')
    expect(meta).toContain('重试 2')
    expect(meta).toContain('已恢复')
    expect(meta.split('·').length).toBe(5)
    wrapper.unmount()
  })

  it('点击关闭按钮抛出 close', async () => {
    const wrapper = mount(FloatingProgressCard, { props: baseProps })
    await wrapper.find('.floating-progress-card__close').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)
    wrapper.unmount()
  })

  it('未知阶段回落到通用文案而不是裸中文兜底', () => {
    const wrapper = mount(FloatingProgressCard, { props: { ...baseProps, stage: 'brand_new_stage' } })
    expect(wrapper.find('.floating-progress-card__stage').text()).toBe('处理中')
    wrapper.unmount()
  })
})

describe('FloatingProgressCard 样式卫生', () => {
  const source = readFileSync(
    resolve(process.cwd(), 'src/components/writing-desk/widgets/FloatingProgressCard.vue'),
    'utf-8',
  )
  const styleTag = source.slice(source.indexOf('<style'))
  const css = styleTag
    .slice(styleTag.indexOf('>') + 1, styleTag.lastIndexOf('</style>'))
    .replace(/\/\*[\s\S]*?\*\//g, '')

  const selectors = css
    .split('}')
    .map((block) => block.split('{')[0])
    .filter((head) => head.includes('.'))
    .flatMap((head) => head.split(','))
    .map((item) => item.trim())
    .filter(Boolean)

  it('每个选择器只定义一次', () => {
    const seen = new Map<string, number>()
    for (const selector of selectors) {
      seen.set(selector, (seen.get(selector) || 0) + 1)
    }
    const duplicated = [...seen.entries()].filter(([, count]) => count > 1).map(([selector]) => selector)
    expect(duplicated).toEqual([])
    expect(selectors.length).toBeGreaterThan(20)
  })

  it('不使用 !important、不重复 keyframes', () => {
    expect(css).not.toContain('!important')
    expect(css).not.toContain('@keyframes')
  })

  it('不出现硬编码颜色，一律走设计令牌', () => {
    expect(css).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
    expect(css).not.toMatch(/\b(rgba?|hsla?)\(/)
    expect(css).toContain('var(--xq-accent)')
  })
})
