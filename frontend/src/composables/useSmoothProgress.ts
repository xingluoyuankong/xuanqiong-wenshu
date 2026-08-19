import {
  computed,
  getCurrentScope,
  onScopeDispose,
  ref,
  toValue,
  watch,
  type MaybeRefOrGetter,
} from 'vue'

import { resolveStageProgressWindow } from '@/utils/chapterGeneration'

/** 默认刷新间隔：120ms 足够顺滑，又不会让主线程忙于重排。 */
export const SMOOTH_PROGRESS_TICK_MS = 120

/** 补齐到新区间起点（或后端进度）的时间常数：几百毫秒内滑到位，而不是瞬间跳。 */
const CATCH_UP_MS = 2000

/** 阶段缺少耗时预估时的兜底时长（秒）。 */
const DEFAULT_STAGE_SECONDS = 30

/** 未完成时的上限：只有真正成功才允许显示 100%。 */
const MAX_BEFORE_DONE = 99

const COMPLETED_KEYS = new Set(['successful', 'succeeded', 'ready', 'finalized'])
const FAILED_KEYS = new Set(['failed', 'evaluation_failed', 'cancelled', 'canceled', 'stale'])

const clampPercent = (value: unknown): number => {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return 0
  return Math.min(100, Math.max(0, numeric))
}

const normalizeKey = (value: unknown): string => String(value ?? '').trim().toLowerCase()

/** 后端进度：无效值返回 -1，表示「没有可用的下限」。 */
const readRawFloor = (value: unknown): number => {
  if (value === null || value === undefined || value === '') return -1
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return -1
  return clampPercent(numeric)
}

/**
 * 饱和爬升：按时间常数向 target 逼近，越接近越慢，永不越过，也绝不回退。
 * durationMs 是这段区间的预估耗时；tau 取其 1/3，约一个预估时长走完剩余距离的 95%。
 */
export const advance = (current: number, target: number, dtMs: number, durationMs = 30_000): number => {
  const from = clampPercent(current)
  const to = clampPercent(target)
  if (to <= from) return from
  const dt = Math.max(0, Number(dtMs) || 0)
  if (dt <= 0) return from
  const tau = Math.max(200, (Number(durationMs) || 30_000) / 3)
  const ratio = 1 - Math.exp(-dt / tau)
  return Math.min(to, from + (to - from) * ratio)
}

export type SmoothProgressInput = {
  stage?: string | null
  status?: string | null
  rawPercent?: number | null
}

/**
 * 计算下一帧的平滑进度。纯函数，规则集中在这里：
 * 1. 成功 → 精确 100；
 * 2. 失败 → 停在当前值（只有一次进度都没有时才采纳后端值）；
 * 3. 未知阶段 → 保持当前值，只有后端给出更高进度时才平滑跟上；
 * 4. 已知阶段 → 先补齐到区间内的下限，再向区间终点减速爬升，绝不越界。
 *
 * 已知阶段下，后端百分比只用来在区间内定位（会被夹进 [start, end]）：
 * 阶段表比调用方拼出来的粗糙兜底值更可信，不能让 `?? 30` 这类值冲过细粒度区间。
 */
export const stepProgress = (current: number, input: SmoothProgressInput, dtMs: number): number => {
  const from = clampPercent(current)
  const status = normalizeKey(input.status)
  const stageKey = normalizeKey(input.stage) || status
  const raw = readRawFloor(input.rawPercent)

  if (COMPLETED_KEYS.has(status) || COMPLETED_KEYS.has(stageKey)) return 100

  const isFailed = FAILED_KEYS.has(status) || FAILED_KEYS.has(stageKey)
  const window = resolveStageProgressWindow(stageKey)

  if (isFailed || window?.hold) {
    // 失败后不再推进；刷新页面直接落在失败态时才用后端值补一个起点。
    if (from > 0) return from
    return raw > 0 ? Math.min(MAX_BEFORE_DONE, raw) : from
  }

  if (!window) {
    if (raw <= from) return from
    return advance(from, Math.min(raw, MAX_BEFORE_DONE), dtMs, CATCH_UP_MS)
  }

  const floor = Math.min(MAX_BEFORE_DONE, Math.max(window.start, Math.min(raw, window.end)))
  const ceiling = Math.min(MAX_BEFORE_DONE, Math.max(window.end, floor))
  const stageSeconds = window.weight && window.weight > 0 ? window.weight : DEFAULT_STAGE_SECONDS

  let next = from
  if (next < floor) next = advance(next, floor, dtMs, CATCH_UP_MS)
  next = advance(next, ceiling, dtMs, stageSeconds * 1000)
  return Math.max(from, next)
}

export type UseSmoothProgressOptions = {
  /** 当前后端阶段（progress_stage）。 */
  stage?: MaybeRefOrGetter<string | null | undefined>
  /** 当前章节状态（generating / successful / failed …）。 */
  status?: MaybeRefOrGetter<string | null | undefined>
  /** 可选的后端原始百分比，只作为下限使用。 */
  rawPercent?: MaybeRefOrGetter<number | null | undefined>
  /** 是否需要持续推进（一般绑定卡片可见性）；false 时暂停定时器。 */
  active?: MaybeRefOrGetter<boolean>
  /** 任务号变化视为换了新任务，自动归零。 */
  taskId?: MaybeRefOrGetter<string | null | undefined>
  tickMs?: number
  /** 便于测试注入时间源。 */
  now?: () => number
}

/**
 * 把后端跳变式的阶段进度，转换成严格单调、均匀爬升的百分比。
 */
export const useSmoothProgress = (options: UseSmoothProgressOptions = {}) => {
  const tickMs = Math.max(50, Number(options.tickMs) || SMOOTH_PROGRESS_TICK_MS)
  const now = options.now || (() => Date.now())
  const value = ref(0)

  let timer: ReturnType<typeof setInterval> | null = null
  let lastTickAt = now()

  const readInput = (): SmoothProgressInput => ({
    stage: toValue(options.stage) ?? null,
    status: toValue(options.status) ?? null,
    rawPercent: toValue(options.rawPercent) ?? null,
  })

  /** 只允许向上写入，任何输入抖动都不会造成回退。 */
  const applyStep = (dtMs: number) => {
    const next = stepProgress(value.value, readInput(), dtMs)
    if (next > value.value) value.value = next
  }

  const tick = () => {
    const at = now()
    const elapsed = at - lastTickAt
    lastTickAt = at
    // 后台标签页会把定时器压到 1s 以上，单帧步长设上限避免一次跨越太多。
    const dt = elapsed > 0 ? Math.min(elapsed, 1000) : tickMs
    applyStep(dt)
  }

  const start = () => {
    if (timer) return
    lastTickAt = now()
    timer = setInterval(tick, tickMs)
  }

  const stop = () => {
    if (!timer) return
    clearInterval(timer)
    timer = null
  }

  const reset = (to = 0) => {
    value.value = clampPercent(to)
    lastTickAt = now()
    applyStep(0)
  }

  watch(
    () => (options.active === undefined ? true : Boolean(toValue(options.active))),
    (isActive) => {
      if (isActive) start()
      else stop()
    },
    { immediate: true },
  )

  watch(
    () => normalizeKey(toValue(options.taskId)),
    (nextId, prevId) => {
      if (prevId && nextId && nextId !== prevId) reset()
    },
  )

  watch(
    () => normalizeKey(toValue(options.status)),
    (nextStatus, prevStatus) => {
      const wasTerminal = COMPLETED_KEYS.has(prevStatus || '') || FAILED_KEYS.has(prevStatus || '')
      const isRunning = Boolean(nextStatus) && !COMPLETED_KEYS.has(nextStatus) && !FAILED_KEYS.has(nextStatus)
      // 同一张卡片被复用于下一轮生成：终态 → 运行态时归零重来。
      if (wasTerminal && isRunning) reset()
      else applyStep(0)
    },
  )

  watch([() => normalizeKey(toValue(options.stage)), () => readRawFloor(toValue(options.rawPercent))], () => {
    applyStep(0)
  })

  if (getCurrentScope()) onScopeDispose(stop)

  return {
    /** 用于展示的整数百分比。 */
    percent: computed(() => Math.round(value.value)),
    /** 未取整的精确值，主要给动画/测试用。 */
    exactPercent: computed(() => value.value),
    reset,
    start,
    stop,
  }
}
