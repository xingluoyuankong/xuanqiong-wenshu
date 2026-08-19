import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PixelMascot from './PixelMascot.vue'
import PixelMascotPicker from './PixelMascotPicker.vue'
import {
  buildMascotFrames,
  MASCOT_COLOR_PRESETS,
  MASCOT_FRAME_COUNT,
  MASCOT_GAITS,
  MASCOT_GRID,
  PIXEL_MASCOTS,
  usePixelMascot,
} from '@/composables/usePixelMascot'
import { useLocale } from '@/composables/useLocale'

const MASCOT_STORAGE_KEY = 'xuanqiong_wenshu_pixel_mascot'
const COLOR_STORAGE_KEY = 'xuanqiong_wenshu_pixel_mascot_color'
const GAIT_STORAGE_KEY = 'xuanqiong_wenshu_pixel_mascot_gait'

const expectedMascotIds = [
  'cat', 'fox', 'rabbit', 'panda', 'frog', 'penguin', 'hamster', 'otter', 'duck', 'bear',
] as const

const expectedGaitIds = ['walk', 'run', 'hop', 'swim', 'waddle', 'wriggle'] as const

describe('像素吉祥物数据', () => {
  beforeEach(() => {
    localStorage.clear()
    usePixelMascot().setMascot('cat')
    usePixelMascot().setColor('#4f46e5')
    usePixelMascot().setGait('walk')
    useLocale().setLocale('zh-CN')
  })

  it('提供 10 种动物，身体均为 9 行合法像素', () => {
    expect(PIXEL_MASCOTS).toHaveLength(10)
    expect(PIXEL_MASCOTS.map((item) => item.id)).toEqual([...expectedMascotIds])

    for (const item of PIXEL_MASCOTS) {
      expect(item.nameEn).toMatch(/^[A-Za-z]+$/)
      expect(item.name).not.toBe('')
      expect(item.body).toHaveLength(9)
      expect(item.body.every((row) => row.length === MASCOT_GRID)).toBe(true)
      expect(item.body.every((row) => /^[.12456]+$/.test(row))).toBe(true)
      expect(expectedGaitIds).toContain(item.defaultGait)
    }
  })

  it('提供 6 种姿态，每种 4 帧 × 3 行下肢像素', () => {
    expect(MASCOT_GAITS.map((item) => item.id)).toEqual([...expectedGaitIds])

    for (const gait of MASCOT_GAITS) {
      expect(gait.legs).toHaveLength(MASCOT_FRAME_COUNT)
      expect(gait.frameDuration).toBeGreaterThanOrEqual(80)
      for (const frame of gait.legs) {
        expect(frame).toHaveLength(3)
        expect(frame.every((row) => row.length === MASCOT_GRID)).toBe(true)
        expect(frame.every((row) => /^[.12456]+$/.test(row))).toBe(true)
      }
    }
  })

  it('任意动物 × 任意姿态都能合成 4 帧 12×12 数据', () => {
    for (const item of PIXEL_MASCOTS) {
      for (const gait of MASCOT_GAITS) {
        const frames = buildMascotFrames(item.id, gait.id)
        expect(frames).toHaveLength(MASCOT_FRAME_COUNT)
        expect(frames.every((frame) => frame.length === MASCOT_GRID)).toBe(true)
        expect(frames.every((frame) => frame.every((row) => row.length === MASCOT_GRID))).toBe(true)
      }
    }
  })

  it('身体图案两两不同，保证 10 种动物可辨识', () => {
    const signatures = PIXEL_MASCOTS.map((item) => item.body.join('|'))
    expect(new Set(signatures).size).toBe(PIXEL_MASCOTS.length)
  })

  it('颜色预设为合法十六进制且无重复', () => {
    expect(MASCOT_COLOR_PRESETS.length).toBeGreaterThanOrEqual(6)
    expect(MASCOT_COLOR_PRESETS.every((color) => /^#[0-9a-f]{6}$/i.test(color))).toBe(true)
    expect(new Set(MASCOT_COLOR_PRESETS).size).toBe(MASCOT_COLOR_PRESETS.length)
  })
})

describe('PixelMascot 组件', () => {
  beforeEach(() => {
    localStorage.clear()
    usePixelMascot().setMascot('cat')
    usePixelMascot().setColor('#4f46e5')
    usePixelMascot().setGait('walk')
    useLocale().setLocale('zh-CN')
    vi.useRealTimers()
  })

  it('默认渲染 cat，12 行 × 12 格', () => {
    const wrapper = mount(PixelMascot)
    const rows = wrapper.findAll('.pixel-mascot__row')

    expect(usePixelMascot().mascotId.value).toBe('cat')
    expect(rows).toHaveLength(MASCOT_GRID)
    expect(rows.every((row) => row.findAll('.pixel-mascot__cell').length === MASCOT_GRID)).toBe(true)
    expect(wrapper.findAll('.pixel-mascot__cell')).toHaveLength(MASCOT_GRID * MASCOT_GRID)
  })

  it('每种动物都能挂载并保持 12×12 结构', () => {
    for (const item of PIXEL_MASCOTS) {
      const wrapper = mount(PixelMascot, { props: { mascotId: item.id, moving: false } })
      expect(wrapper.findAll('.pixel-mascot__row')).toHaveLength(MASCOT_GRID)
      expect(wrapper.findAll('.pixel-mascot__cell')).toHaveLength(MASCOT_GRID * MASCOT_GRID)
      wrapper.unmount()
    }
  })

  it('姿态 class 跟随 gait，且 moving=false 时标记静止', () => {
    const moving = mount(PixelMascot, { props: { gait: 'swim', moving: true } })
    expect(moving.classes()).toContain('pixel-mascot--swim')
    expect(moving.classes()).not.toContain('is-static')

    const still = mount(PixelMascot, { props: { gait: 'hop', moving: false } })
    expect(still.classes()).toContain('pixel-mascot--hop')
    expect(still.classes()).toContain('is-static')
  })

  it('moving=true 时按姿态帧率逐帧推进，moving=false 时不动', async () => {
    vi.useFakeTimers()
    const walkDuration = MASCOT_GAITS.find((item) => item.id === 'walk')!.frameDuration

    const wrapper = mount(PixelMascot, { props: { gait: 'walk', moving: true } })
    const firstFrame = wrapper.findAll('.pixel-mascot__cell').map((cell) => cell.attributes('data-ink'))
    vi.advanceTimersByTime(walkDuration * 2 + 10)
    await nextTick()
    const laterFrame = wrapper.findAll('.pixel-mascot__cell').map((cell) => cell.attributes('data-ink'))
    expect(laterFrame).not.toEqual(firstFrame)

    const still = mount(PixelMascot, { props: { gait: 'walk', moving: false } })
    const stillBefore = still.findAll('.pixel-mascot__cell').map((cell) => cell.attributes('data-ink'))
    vi.advanceTimersByTime(walkDuration * 5)
    await nextTick()
    expect(still.findAll('.pixel-mascot__cell').map((cell) => cell.attributes('data-ink'))).toEqual(stillBefore)
    vi.useRealTimers()
  })

  it('自定义颜色通过 CSS 变量注入，不写死颜色', () => {
    const wrapper = mount(PixelMascot, { props: { color: '#123456', size: 24, moving: false } })
    const style = wrapper.attributes('style') || ''
    expect(style).toContain('--pixel-color: #123456')
    expect(style).toContain('--pixel-size: 24px')
  })
})

describe('usePixelMascot 状态', () => {
  beforeEach(() => {
    localStorage.clear()
    usePixelMascot().setMascot('cat')
    usePixelMascot().setColor('#4f46e5')
    usePixelMascot().setGait('walk')
    useLocale().setLocale('zh-CN')
  })

  it('选择动物/颜色/姿态后写入 localStorage，并在重新加载后恢复', async () => {
    const state = usePixelMascot()
    state.setMascot('otter')
    state.setColor('#123456')
    state.setGait('swim')

    expect(localStorage.getItem(MASCOT_STORAGE_KEY)).toBe('otter')
    expect(localStorage.getItem(COLOR_STORAGE_KEY)).toBe('#123456')
    expect(localStorage.getItem(GAIT_STORAGE_KEY)).toBe('swim')

    vi.resetModules()
    const reloaded = await import('@/composables/usePixelMascot')
    const restored = reloaded.usePixelMascot()
    expect(restored.mascotId.value).toBe('otter')
    expect(restored.color.value).toBe('#123456')
    expect(restored.gaitId.value).toBe('swim')
  })

  it('拒绝非法动物 id 与非法颜色', () => {
    const state = usePixelMascot()
    state.setMascot('dragon' as never)
    expect(state.mascotId.value).toBe('cat')

    state.setColor('red')
    expect(state.color.value).toBe('#4f46e5')
  })

  it('auto 模式下 shuffleGait 每次都换成另一种姿态', () => {
    const state = usePixelMascot()
    state.setGait('auto')
    expect(state.gaitMode.value).toBe('auto')

    for (let i = 0; i < 12; i += 1) {
      const before = state.gaitId.value
      const next = state.shuffleGait()
      expect(next).not.toBe(before)
      expect(state.gaitId.value).toBe(next)
    }
  })

  it('固定姿态时 frames 与该姿态一致', () => {
    const state = usePixelMascot()
    state.setMascot('duck')
    state.setGait('waddle')
    expect(state.frames.value).toEqual(buildMascotFrames('duck', 'waddle'))
    expect(state.gait.value.id).toBe('waddle')
  })
})

describe('beginRun / endRun 推进轮次', () => {
  beforeEach(() => {
    localStorage.clear()
    usePixelMascot().setGait('walk')
    useLocale().setLocale('zh-CN')
  })

  it('auto 模式下每一轮推进开始时换一种姿态', () => {
    const state = usePixelMascot()
    state.setGait('auto')

    const first = state.gaitId.value
    state.beginRun()
    expect(state.gaitId.value).not.toBe(first)
    expect(state.isRunning.value).toBe(true)

    const during = state.gaitId.value
    state.endRun()
    expect(state.isRunning.value).toBe(false)

    state.beginRun()
    expect(state.gaitId.value).not.toBe(during)
    state.endRun()
  })

  it('同屏多个进度条共用同一姿态，全部结束后下一轮才再换', () => {
    const state = usePixelMascot()
    state.setGait('auto')

    state.beginRun()
    const shared = state.gaitId.value
    state.beginRun()
    // 第二个 runner 不得打断第一个的动作
    expect(state.gaitId.value).toBe(shared)

    state.endRun()
    expect(state.isRunning.value).toBe(true)
    expect(state.gaitId.value).toBe(shared)

    state.endRun()
    expect(state.isRunning.value).toBe(false)
  })

  it('固定姿态模式下 beginRun 不改变用户选定的姿态', () => {
    const state = usePixelMascot()
    state.setGait('swim')

    state.beginRun()
    expect(state.gaitId.value).toBe('swim')
    state.endRun()
    expect(state.gaitId.value).toBe('swim')
  })

  it('endRun 多调用不会把计数压成负数', () => {
    const state = usePixelMascot()
    state.endRun()
    state.endRun()
    expect(state.isRunning.value).toBe(false)

    state.beginRun()
    expect(state.isRunning.value).toBe(true)
    state.endRun()
    expect(state.isRunning.value).toBe(false)
  })
})

describe('PixelMascotPicker', () => {
  beforeEach(() => {
    localStorage.clear()
    usePixelMascot().setMascot('cat')
    usePixelMascot().setColor('#4f46e5')
    usePixelMascot().setGait('walk')
    useLocale().setLocale('zh-CN')
  })

  it('展开后列出 10 个动物、7 个姿态按钮与预设色板', async () => {
    useLocale().setLocale('en-US')
    const mascot = usePixelMascot()
    mascot.setMascot('fox')
    mascot.setColor('#abcdef')

    const wrapper = mount(PixelMascotPicker)
    await wrapper.get('.pixel-mascot-picker__trigger').trigger('click')

    const options = wrapper.findAll('.pixel-mascot-picker__option')
    expect(options).toHaveLength(10)
    options.forEach((option, index) => {
      expect(option.text()).toContain(PIXEL_MASCOTS[index].nameEn)
    })
    expect(wrapper.findAll('.pixel-mascot-picker__gait')).toHaveLength(MASCOT_GAITS.length + 1)
    expect(wrapper.findAll('.pixel-mascot-picker__swatch')).toHaveLength(MASCOT_COLOR_PRESETS.length)

    expect(wrapper.get('.pixel-mascot-picker__trigger').text()).toContain('Fox')
    expect(wrapper.get('.pixel-mascot-picker__option.is-active').text()).toContain('Fox')
    expect((wrapper.get('input[type="color"]').element as HTMLInputElement).value).toBe('#abcdef')
  })

  it('中文语境下显示中文名，且点击色板即时改色', async () => {
    const wrapper = mount(PixelMascotPicker)
    await wrapper.get('.pixel-mascot-picker__trigger').trigger('click')
    expect(wrapper.get('.pixel-mascot-picker__trigger').text()).toContain('小猫')

    await wrapper.findAll('.pixel-mascot-picker__swatch')[2].trigger('click')
    expect(usePixelMascot().color.value).toBe(MASCOT_COLOR_PRESETS[2])
  })

  it('点击姿态按钮切换到固定姿态，点击随机回到 auto', async () => {
    const wrapper = mount(PixelMascotPicker)
    await wrapper.get('.pixel-mascot-picker__trigger').trigger('click')

    const gaits = wrapper.findAll('.pixel-mascot-picker__gait')
    await gaits[3].trigger('click')
    expect(usePixelMascot().gaitMode.value).toBe(MASCOT_GAITS[2].id)

    await gaits[0].trigger('click')
    expect(usePixelMascot().gaitMode.value).toBe('auto')
  })

  it('选中动物后面板收起并写入选择', async () => {
    const wrapper = mount(PixelMascotPicker)
    await wrapper.get('.pixel-mascot-picker__trigger').trigger('click')
    await wrapper.findAll('.pixel-mascot-picker__option')[4].trigger('click')

    expect(usePixelMascot().mascotId.value).toBe(PIXEL_MASCOTS[4].id)
    expect(wrapper.find('.pixel-mascot-picker__panel').exists()).toBe(false)
  })
})
