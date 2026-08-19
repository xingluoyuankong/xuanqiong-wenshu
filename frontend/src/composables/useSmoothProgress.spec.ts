import { effectScope, nextTick, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { GENERATION_STAGE_ORDER, GENERATION_STAGE_POINTS } from '@/utils/chapterGeneration'
import { advance, stepProgress, useSmoothProgress } from './useSmoothProgress'

/** 反复推进若干帧，返回最终值与整条轨迹，便于断言单调性。 */
const run = (
  from: number,
  input: Parameters<typeof stepProgress>[1],
  frames: number,
  dtMs = 120,
): { value: number; trail: number[] } => {
  let value = from
  const trail: number[] = []
  for (let i = 0; i < frames; i += 1) {
    value = stepProgress(value, input, dtMs)
    trail.push(value)
  }
  return { value, trail }
}

const isMonotonic = (trail: number[]) => trail.every((item, index) => index === 0 || item >= trail[index - 1])

describe('阶段进度区间表', () => {
  it('流水线区间单调递增且互相衔接', () => {
    let previousStart = -1
    let previousEnd = -1
    for (const stage of GENERATION_STAGE_ORDER) {
      const point = GENERATION_STAGE_POINTS[stage]
      expect(point, `缺少阶段区间：${stage}`).toBeDefined()
      expect(point.end).toBeGreaterThanOrEqual(point.start)
      expect(point.start).toBeGreaterThanOrEqual(previousStart)
      expect(point.end).toBeGreaterThanOrEqual(previousEnd)
      previousStart = point.start
      previousEnd = point.end
    }
  })

  it('覆盖浮动进度卡片会用到的全部阶段与状态', () => {
    const required = [
      'queued', 'prepare_context', 'audit_context', 'cast_plan', 'foreshadowing_plan',
      'foreshadowing_chapter_task', 'longform_context', 'enhanced_context', 'generate_mission',
      'generate_variants', 'generate_variants_candidate', 'ai_review', 'optimize_content',
      'reader_simulator', 'consistency', 'enrichment', 'continuity_gate', 'persist_versions',
      'diagnose_once', 'diagnose_structural', 'diagnose_character', 'diagnose_previous_chapter',
      'diagnose_context_bundle', 'diagnose_continuity', 'optimize_character', 'generating',
      'evaluating', 'selecting', 'waiting_for_confirm', 'successful', 'failed', 'evaluation_failed',
    ]
    for (const stage of required) {
      expect(GENERATION_STAGE_POINTS[stage], `缺少阶段区间：${stage}`).toBeDefined()
    }
  })

  it('写正文区间最宽，占 25–35 个百分点', () => {
    const writing = GENERATION_STAGE_POINTS.generate_variants
    const width = writing.end - writing.start
    expect(width).toBeGreaterThanOrEqual(25)
    expect(width).toBeLessThanOrEqual(35)
    for (const stage of GENERATION_STAGE_ORDER) {
      if (stage === 'generate_variants' || stage === 'generate_variants_candidate') continue
      const point = GENERATION_STAGE_POINTS[stage]
      expect(point.end - point.start).toBeLessThan(width)
    }
  })
})

describe('advance 饱和爬升', () => {
  it('单调靠近目标但永不越过', () => {
    let value = 0
    for (let i = 0; i < 500; i += 1) {
      const next = advance(value, 56, 120, 30_000)
      expect(next).toBeGreaterThanOrEqual(value)
      expect(next).toBeLessThanOrEqual(56)
      value = next
    }
    expect(value).toBeGreaterThan(55)
  })

  it('目标不高于当前值时不回退', () => {
    expect(advance(60, 40, 500)).toBe(60)
    expect(advance(60, 60, 500)).toBe(60)
  })

  it('dt 为 0 时不动', () => {
    expect(advance(10, 90, 0)).toBe(10)
  })
})

describe('stepProgress 阶段插值', () => {
  it('在阶段区间内均匀爬升且不越过上界', () => {
    const { value, trail } = run(0, { stage: 'generate_variants', status: 'generating' }, 4000)
    expect(isMonotonic(trail)).toBe(true)
    expect(value).toBeLessThanOrEqual(GENERATION_STAGE_POINTS.generate_variants.end)
    expect(value).toBeGreaterThan(50)
  })

  it('阶段切换时向上衔接到新区间，不回退', () => {
    const beforeSwitch = run(0, { stage: 'generate_variants', status: 'generating' }, 200).value
    expect(beforeSwitch).toBeLessThan(GENERATION_STAGE_POINTS.ai_review.start)

    const { value, trail } = run(beforeSwitch, { stage: 'ai_review', status: 'evaluating' }, 400)
    expect(isMonotonic(trail)).toBe(true)
    expect(trail[0]).toBeGreaterThanOrEqual(beforeSwitch)
    expect(value).toBeGreaterThanOrEqual(GENERATION_STAGE_POINTS.ai_review.start)
    expect(value).toBeLessThanOrEqual(GENERATION_STAGE_POINTS.ai_review.end)
  })

  it('回到更早的阶段也不会倒退', () => {
    const value = stepProgress(70, { stage: 'prepare_context', status: 'generating' }, 500)
    expect(value).toBe(70)
  })

  it('未知阶段保持当前值、不跳变', () => {
    expect(stepProgress(42, { stage: 'brand_new_stage', status: 'generating' }, 1000)).toBe(42)
  })

  it('未知阶段但后端给出更高进度时平滑跟上', () => {
    const { value, trail } = run(42, { stage: 'brand_new_stage', rawPercent: 80 }, 200)
    expect(isMonotonic(trail)).toBe(true)
    expect(value).toBeGreaterThan(42)
    expect(value).toBeLessThanOrEqual(80)
  })

  it('后端进度落在区间内时作为下限快速补齐', () => {
    const { value, trail } = run(0, { stage: 'generate_variants', rawPercent: 44 }, 300)
    expect(isMonotonic(trail)).toBe(true)
    expect(value).toBeGreaterThanOrEqual(44)
    expect(value).toBeLessThanOrEqual(GENERATION_STAGE_POINTS.generate_variants.end)
  })

  it('后端粗糙兜底值被夹在阶段区间内，不会冲过上界', () => {
    // 调用方在缺少 progress_percent 时可能给出统一的兜底值（例如 30），
    // 阶段表比它更可信，必须夹回区间。
    const value = run(0, { stage: 'cast_plan', rawPercent: 30 }, 500).value
    expect(value).toBeGreaterThanOrEqual(GENERATION_STAGE_POINTS.cast_plan.start)
    expect(value).toBeLessThanOrEqual(GENERATION_STAGE_POINTS.cast_plan.end)
  })

  it('successful 精确到 100', () => {
    expect(stepProgress(37, { status: 'successful' }, 0)).toBe(100)
    expect(stepProgress(37, { stage: 'finalized', status: 'generating' }, 0)).toBe(100)
  })

  it('failed 停在当前值，不再继续爬', () => {
    const { value, trail } = run(57, { stage: 'generate_variants', status: 'failed' }, 100)
    expect(value).toBe(57)
    expect(new Set(trail).size).toBe(1)
    expect(stepProgress(57, { status: 'evaluation_failed' }, 10_000)).toBe(57)
  })

  it('刷新后直接落在失败态时用后端值补一个起点', () => {
    expect(stepProgress(0, { status: 'failed', rawPercent: 62 }, 120)).toBe(62)
  })

  it('非终态永远不会显示 100', () => {
    const value = run(0, { stage: 'ledger_graph', status: 'generating' }, 5000).value
    expect(value).toBeLessThanOrEqual(99)
  })
})

describe('useSmoothProgress 组合式', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('随定时器均匀推进，并在阶段切换后继续上升', async () => {
    const scope = effectScope()
    const stage = ref('generate_variants')
    const status = ref('generating')

    const handle = scope.run(() => useSmoothProgress({ stage, status, active: true }))!

    expect(handle.percent.value).toBe(0)
    vi.advanceTimersByTime(1_000)
    const first = handle.percent.value
    expect(first).toBeGreaterThan(0)

    vi.advanceTimersByTime(5_000)
    const second = handle.percent.value
    expect(second).toBeGreaterThan(first)
    expect(second).toBeLessThanOrEqual(GENERATION_STAGE_POINTS.generate_variants.end)

    stage.value = 'consistency'
    status.value = 'evaluating'
    await nextTick()
    vi.advanceTimersByTime(5_000)
    expect(handle.percent.value).toBeGreaterThanOrEqual(second)
    expect(handle.percent.value).toBeGreaterThanOrEqual(GENERATION_STAGE_POINTS.consistency.start)

    status.value = 'successful'
    await nextTick()
    expect(handle.percent.value).toBe(100)

    scope.stop()
  })

  it('失败后即使定时器继续跑也停在当前值', async () => {
    const scope = effectScope()
    const status = ref('generating')
    const handle = scope.run(() => useSmoothProgress({ stage: 'generate_variants', status }))!

    vi.advanceTimersByTime(3_000)
    const frozen = handle.percent.value
    expect(frozen).toBeGreaterThan(0)

    status.value = 'failed'
    await nextTick()
    vi.advanceTimersByTime(30_000)
    expect(handle.percent.value).toBe(frozen)

    scope.stop()
  })

  it('换任务号后归零重新推进', async () => {
    const scope = effectScope()
    const taskId = ref('task-a')
    const handle = scope.run(() => useSmoothProgress({ stage: 'generate_variants', status: 'generating', taskId }))!

    vi.advanceTimersByTime(4_000)
    expect(handle.percent.value).toBeGreaterThan(0)

    taskId.value = 'task-b'
    await nextTick()
    expect(handle.percent.value).toBe(0)

    scope.stop()
  })

  it('active 为 false 时不推进，reset 可手动归零', async () => {
    const scope = effectScope()
    const active = ref(false)
    const handle = scope.run(() => useSmoothProgress({ stage: 'generate_variants', status: 'generating', active }))!

    vi.advanceTimersByTime(5_000)
    expect(handle.percent.value).toBe(0)

    active.value = true
    await nextTick()
    vi.advanceTimersByTime(5_000)
    expect(handle.percent.value).toBeGreaterThan(0)

    handle.reset()
    expect(handle.percent.value).toBe(0)

    scope.stop()
  })

  it('作用域销毁后清理定时器', () => {
    const scope = effectScope()
    scope.run(() => useSmoothProgress({ stage: 'generate_variants', status: 'generating' }))
    expect(vi.getTimerCount()).toBeGreaterThan(0)

    scope.stop()
    expect(vi.getTimerCount()).toBe(0)
  })
})
