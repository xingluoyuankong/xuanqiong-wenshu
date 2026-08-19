import { computed, type ComputedRef } from 'vue'
import type { Chapter, GenerationRuntime, GenerationRuntimeEvent, NovelProject } from '@/api/novel'
import { pick } from '@/composables/useLocale'

const SEQUENTIAL_BLOCKING_STATUSES = new Set<Chapter['generation_status']>([
  'not_generated',
  'generating',
  'evaluating',
  'selecting',
  'waiting_for_confirm'
])

const BUSY_CHAPTER_STATUSES = new Set<Chapter['generation_status']>([
  'generating',
  'evaluating',
  'selecting'
])
const RECOVERABLE_VERSION_STATUSES = new Set<Chapter['generation_status']>([
  'selecting',
  'waiting_for_confirm',
  'evaluation_failed'
])
const RUNTIME_BUSY_STAGES = new Set([
  'queued',
  'generating',
  'evaluating',
  'selecting',
  'already_generating',
  'running',
  'in_progress',
  'outline_context_audit',
  'outline_setting_lock',
  'outline_cast_plan',
  'outline_plot_threads',
  'outline_foreshadowing_plan',
  'outline_chapter_skeleton',
  'outline_quality_gate',
  'blueprint_concept',
  'blueprint_setting_lock',
  'blueprint_cast_plan',
  'blueprint_plot_threads',
  'blueprint_foreshadowing',
  'blueprint_chapter_plan',
  'prepare_context',
  'audit_context',
  'cast_plan',
  'foreshadowing_plan',
  'longform_context',
  'generate_mission',
  'generate_variants',
  'review',
  'diagnose_once',
  'diagnose_previous_chapter',
  'diagnose_context_bundle',
  'diagnose_structural',
  'diagnose_character',
  'diagnose_delivery',
  'optimize_content',
  'optimize_structural',
  'optimize_character',
  'optimize_delivery',
  'consistency',
  'continuity_gate',
  'optimizer',
  'enrichment',
  'persist_versions',
  'finalize',
  'ledger_memory',
  'ledger_foreshadowing',
  'ledger_graph',
])

// stage 键是后端下发的英文枚举（内部真源），值是展示文案；用函数惰性求值，切换语言后重新取值
const STAGE_LABEL_MAP: Record<string, () => string> = {
  queued: () => pick('排队中', 'Queued'),
  outline_context_audit: () => pick('大纲上下文审计', 'Outline context audit'),
  outline_setting_lock: () => pick('大纲设定锁定', 'Outline setting lock'),
  outline_cast_plan: () => pick('大纲角色规模', 'Outline cast scale'),
  outline_plot_threads: () => pick('大纲主支线', 'Outline plot threads'),
  outline_foreshadowing_plan: () => pick('大纲伏笔规划', 'Outline foreshadowing plan'),
  outline_chapter_skeleton: () => pick('大纲章节骨架', 'Outline chapter skeleton'),
  outline_quality_gate: () => pick('大纲质量门', 'Outline quality gate'),
  blueprint_concept: () => pick('蓝图概念整理', 'Blueprint concept'),
  blueprint_setting_lock: () => pick('蓝图设定锁定', 'Blueprint setting lock'),
  blueprint_cast_plan: () => pick('蓝图角色规划', 'Blueprint cast plan'),
  blueprint_plot_threads: () => pick('蓝图主支线', 'Blueprint plot threads'),
  blueprint_foreshadowing: () => pick('蓝图伏笔系统', 'Blueprint foreshadowing'),
  blueprint_chapter_plan: () => pick('蓝图章节规划', 'Blueprint chapter plan'),
  prepare_context: () => pick('准备上下文', 'Preparing context'),
  audit_context: () => pick('审计长篇上下文', 'Auditing long-form context'),
  cast_plan: () => pick('角色规划', 'Cast plan'),
  foreshadowing_plan: () => pick('伏笔规划', 'Foreshadowing plan'),
  longform_context: () => pick('长篇上下文包', 'Long-form context bundle'),
  generate_mission: () => pick('生成任务', 'Generation mission'),
  generate_variants: () => pick('生成正文', 'Writing the draft'),
  review: () => pick('AI 评审', 'AI review'),
  diagnose_once: () => pick('问题诊断', 'Issue diagnosis'),
  diagnose_previous_chapter: () => pick('前章依据', 'Previous-chapter basis'),
  diagnose_context_bundle: () => pick('关联上下文', 'Related context'),
  diagnose_structural: () => pick('结构诊断', 'Structural diagnosis'),
  diagnose_character: () => pick('角色诊断', 'Character diagnosis'),
  diagnose_delivery: () => pick('表达诊断', 'Delivery diagnosis'),
  optimize_content: () => pick('分阶段优化', 'Staged optimization'),
  optimize_structural: () => pick('结构优化', 'Structural optimization'),
  optimize_character: () => pick('人物优化', 'Character optimization'),
  optimize_delivery: () => pick('表达优化', 'Delivery optimization'),
  consistency: () => pick('一致性检查', 'Consistency check'),
  continuity_gate: () => pick('长篇连续性检查', 'Long-form continuity gate'),
  persist_versions: () => pick('保存候选版本', 'Saving candidates'),
  finalize: () => pick('定稿快照', 'Final snapshot'),
  ledger_memory: () => pick('记忆层更新', 'Memory ledger update'),
  ledger_foreshadowing: () => pick('伏笔闭环', 'Foreshadowing closure'),
  ledger_graph: () => pick('线索/图谱同步', 'Clue and graph sync'),
  finalized: () => pick('定稿完成', 'Finalized'),
  selecting: () => pick('等待选择', 'Awaiting selection'),
  waiting_for_confirm: () => pick('等待确认', 'Awaiting confirmation'),
  ready: () => pick('已就绪', 'Ready'),
  successful: () => pick('已完成', 'Done'),
  failed: () => pick('失败', 'Failed'),
  evaluation_failed: () => pick('评审未通过', 'Review not passed'),
}

type BackendStageDefinition = {
  key: string
  label: () => string
  milestone: number
  aliases?: string[]
}

const BACKEND_STAGE_DEFINITIONS: BackendStageDefinition[] = [
  { key: 'queued', label: () => pick('排队中', 'Queued'), milestone: 4 },
  { key: 'outline_context_audit', label: () => pick('大纲上下文审计', 'Outline context audit'), milestone: 6 },
  { key: 'outline_setting_lock', label: () => pick('大纲设定锁定', 'Outline setting lock'), milestone: 9 },
  { key: 'outline_cast_plan', label: () => pick('大纲角色规模', 'Outline cast scale'), milestone: 12 },
  { key: 'outline_plot_threads', label: () => pick('大纲主支线', 'Outline plot threads'), milestone: 15 },
  { key: 'outline_foreshadowing_plan', label: () => pick('大纲伏笔规划', 'Outline foreshadowing plan'), milestone: 18 },
  { key: 'outline_chapter_skeleton', label: () => pick('大纲章节骨架', 'Outline chapter skeleton'), milestone: 22 },
  { key: 'outline_quality_gate', label: () => pick('大纲质量门', 'Outline quality gate'), milestone: 28 },
  { key: 'blueprint_concept', label: () => pick('蓝图概念整理', 'Blueprint concept'), milestone: 6 },
  { key: 'blueprint_setting_lock', label: () => pick('蓝图设定锁定', 'Blueprint setting lock'), milestone: 10 },
  { key: 'blueprint_cast_plan', label: () => pick('蓝图角色规划', 'Blueprint cast plan'), milestone: 14 },
  { key: 'blueprint_plot_threads', label: () => pick('蓝图主支线', 'Blueprint plot threads'), milestone: 18 },
  { key: 'blueprint_foreshadowing', label: () => pick('蓝图伏笔系统', 'Blueprint foreshadowing'), milestone: 22 },
  { key: 'blueprint_chapter_plan', label: () => pick('蓝图章节规划', 'Blueprint chapter plan'), milestone: 28 },
  { key: 'prepare_context', label: () => pick('准备上下文', 'Preparing context'), milestone: 8 },
  { key: 'audit_context', label: () => pick('审计长篇上下文', 'Auditing long-form context'), milestone: 11 },
  { key: 'cast_plan', label: () => pick('角色规划', 'Cast plan'), milestone: 14 },
  { key: 'foreshadowing_plan', label: () => pick('伏笔规划', 'Foreshadowing plan'), milestone: 17 },
  { key: 'longform_context', label: () => pick('长篇上下文包', 'Long-form context bundle'), milestone: 20 },
  { key: 'generate_mission', label: () => pick('生成任务', 'Generation mission'), milestone: 22 },
  { key: 'generate_variants', label: () => pick('生成候选版本', 'Generating candidates'), milestone: 34, aliases: ['generating', 'already_generating', 'running', 'in_progress'] },
  { key: 'review', label: () => pick('AI 评审', 'AI review'), milestone: 62, aliases: ['ai_review'] },
  { key: 'diagnose_once', label: () => pick('问题诊断', 'Issue diagnosis'), milestone: 70 },
  { key: 'diagnose_previous_chapter', label: () => pick('检查上一章', 'Checking the previous chapter'), milestone: 72 },
  { key: 'diagnose_context_bundle', label: () => pick('检查上下文', 'Checking the context'), milestone: 74 },
  { key: 'diagnose_structural', label: () => pick('结构诊断', 'Structural diagnosis'), milestone: 76 },
  { key: 'diagnose_character', label: () => pick('角色诊断', 'Character diagnosis'), milestone: 78 },
  { key: 'diagnose_delivery', label: () => pick('表达诊断', 'Delivery diagnosis'), milestone: 79 },
  { key: 'optimize_content', label: () => pick('内容优化', 'Content optimization'), milestone: 80, aliases: ['self_critique', 'optimizer'] },
  { key: 'optimize_structural', label: () => pick('结构优化', 'Structural optimization'), milestone: 83 },
  { key: 'optimize_character', label: () => pick('角色优化', 'Character optimization'), milestone: 86, aliases: ['reader_simulator'] },
  { key: 'optimize_delivery', label: () => pick('表达优化', 'Delivery optimization'), milestone: 88, aliases: ['enrichment'] },
  { key: 'consistency', label: () => pick('一致性检查', 'Consistency check'), milestone: 90 },
  { key: 'continuity_gate', label: () => pick('长篇连续性检查', 'Long-form continuity gate'), milestone: 91 },
  { key: 'persist_versions', label: () => pick('保存候选版本', 'Saving candidates'), milestone: 92 },
  { key: 'waiting_for_confirm', label: () => pick('等待确认', 'Awaiting confirmation'), milestone: 97, aliases: ['selecting'] },
  { key: 'finalize', label: () => pick('定稿快照', 'Final snapshot'), milestone: 98 },
  { key: 'ledger_memory', label: () => pick('记忆层更新', 'Memory ledger update'), milestone: 99 },
  { key: 'ledger_foreshadowing', label: () => pick('伏笔闭环', 'Foreshadowing closure'), milestone: 99 },
  { key: 'ledger_graph', label: () => pick('线索/图谱同步', 'Clue and graph sync'), milestone: 100 },
  { key: 'finalized', label: () => pick('定稿完成', 'Finalized'), milestone: 100 },
  { key: 'successful', label: () => pick('已完成', 'Done'), milestone: 100, aliases: ['ready'] },
  { key: 'failed', label: () => pick('失败', 'Failed'), milestone: 100, aliases: [] },
  { key: 'evaluation_failed', label: () => pick('评审未通过', 'Review not passed'), milestone: 97, aliases: [] },
  { key: 'enhanced_context', label: () => pick('增强上下文装配', 'Enhanced context assembly'), milestone: 19 },
  { key: 'multi_round_continuation', label: () => pick('多轮续写补充', 'Multi-round continuation'), milestone: 60 },
  { key: 'reader_simulation', label: () => pick('读者视角模拟', 'Reader-perspective simulation'), milestone: 65 },
]

const DEFAULT_PIPELINE_SEQUENCE = [
  'queued',
  'prepare_context',
  'audit_context',
  'cast_plan',
  'foreshadowing_plan',
  'longform_context',
  'generate_mission',
  'generate_variants',
  'review',
  'diagnose_once',
  'diagnose_previous_chapter',
  'diagnose_context_bundle',
  'diagnose_structural',
  'diagnose_character',
  'diagnose_delivery',
  'optimize_content',
  'optimize_structural',
  'optimize_character',
  'optimize_delivery',
  'consistency',
  'continuity_gate',
  'persist_versions',
  'waiting_for_confirm',
  'finalize',
  'ledger_memory',
  'ledger_foreshadowing',
  'ledger_graph',
  'finalized',
] as const

const OUTLINE_PIPELINE_SEQUENCE = [
  'queued',
  'outline_context_audit',
  'outline_setting_lock',
  'outline_cast_plan',
  'outline_plot_threads',
  'outline_foreshadowing_plan',
  'outline_chapter_skeleton',
  'outline_quality_gate',
  'successful',
] as const

const BLUEPRINT_PIPELINE_SEQUENCE = [
  'queued',
  'blueprint_concept',
  'blueprint_setting_lock',
  'blueprint_cast_plan',
  'blueprint_plot_threads',
  'blueprint_foreshadowing',
  'blueprint_chapter_plan',
  'successful',
] as const

const STAGE_META_MAP = new Map<string, BackendStageDefinition>()
for (const definition of BACKEND_STAGE_DEFINITIONS) {
  STAGE_META_MAP.set(definition.key, definition)
  for (const alias of definition.aliases || []) STAGE_META_MAP.set(alias, definition)
}

const STAGE_STALL_THRESHOLDS: Record<string, number> = {
  queued: 2 * 60_000,
  outline_context_audit: 3 * 60_000,
  outline_setting_lock: 4 * 60_000,
  outline_cast_plan: 4 * 60_000,
  outline_plot_threads: 5 * 60_000,
  outline_foreshadowing_plan: 4 * 60_000,
  outline_chapter_skeleton: 8 * 60_000,
  outline_quality_gate: 4 * 60_000,
  blueprint_concept: 4 * 60_000,
  blueprint_setting_lock: 4 * 60_000,
  blueprint_cast_plan: 5 * 60_000,
  blueprint_plot_threads: 6 * 60_000,
  blueprint_foreshadowing: 5 * 60_000,
  blueprint_chapter_plan: 8 * 60_000,
  prepare_context: 3 * 60_000,
  audit_context: 3 * 60_000,
  cast_plan: 3 * 60_000,
  foreshadowing_plan: 3 * 60_000,
  longform_context: 3 * 60_000,
  generate_mission: 4 * 60_000,
  generate_variants: 12 * 60_000,
  review: 5 * 60_000,
  diagnose_once: 3 * 60_000,
  diagnose_previous_chapter: 3 * 60_000,
  diagnose_context_bundle: 3 * 60_000,
  diagnose_structural: 4 * 60_000,
  diagnose_character: 4 * 60_000,
  diagnose_delivery: 4 * 60_000,
  optimize_content: 6 * 60_000,
  optimize_structural: 4 * 60_000,
  optimize_character: 4 * 60_000,
  optimize_delivery: 4 * 60_000,
  consistency: 5 * 60_000,
  continuity_gate: 3 * 60_000,
  persist_versions: 3 * 60_000,
  finalize: 4 * 60_000,
  ledger_memory: 4 * 60_000,
  ledger_foreshadowing: 3 * 60_000,
  ledger_graph: 3 * 60_000,
  waiting_for_confirm: 30 * 60_000,
}

export const normalizeRuntimeStage = (rawStage: unknown): string => {
  const stage = String(rawStage || '').trim().toLowerCase()
  if (!stage) return 'queued'
  return STAGE_META_MAP.get(stage)?.key || stage
}

const normalizeDisplayStage = (rawStage: unknown): string => {
  const stage = String(rawStage || '').trim().toLowerCase()
  if (!stage) return 'queued'
  return STAGE_META_MAP.get(stage)?.key || stage
}

/**
 * 单个阶段占用的进度区间。
 * - start / end：百分比区间（0–100），沿 GENERATION_STAGE_ORDER 单调不减；
 * - weight：该阶段的预估耗时（秒），只用于决定区间内的爬升速度，不影响边界；
 * - hold：该状态不再自动爬升（失败态停在当前值），start/end 仅作为兜底展示范围。
 */
export type GenerationStagePoint = {
  start: number
  end: number
  weight?: number
  hold?: boolean
}

/**
 * 细粒度阶段进度表。
 *
 * 后端只在切换 stage 时上报一次 progress_percent，前端直接渲染就会出现「10% 跳 60%」
 * 或「长时间卡在同一数字」。这里把整条链路切成互不重叠、单调递增的窄区间，
 * 由 useSmoothProgress 在区间内按时间插值爬升，保证观感均匀。
 *
 * 区间宽度按真实耗时分配：generate_variants（写正文）最宽（28 点），
 * 准备类阶段各 2–4 点，诊断/优化/收尾类各 1–3 点。
 */
const STAGE_POINT_PIPELINE: ReadonlyArray<readonly [string, number, number, number]> = [
  // 准备段
  ['queued', 0, 3, 10],
  ['prepare_context', 3, 7, 15],
  ['audit_context', 7, 10, 12],
  ['cast_plan', 10, 13, 12],
  ['foreshadowing_plan', 13, 16, 12],
  ['foreshadowing_chapter_task', 16, 18, 8],
  ['longform_context', 18, 22, 15],
  ['enhanced_context', 22, 25, 12],
  ['generate_mission', 25, 28, 20],
  // 写正文：整条链路里最慢的一段，占 28 个百分点
  ['generate_variants', 28, 56, 210],
  ['generate_variants_candidate', 30, 58, 150],
  ['multi_round_continuation', 58, 60, 60],
  // 评审与诊断
  ['ai_review', 60, 67, 60],
  ['reader_simulation', 67, 69, 30],
  ['diagnose_once', 69, 71, 20],
  ['diagnose_previous_chapter', 71, 73, 18],
  ['diagnose_context_bundle', 73, 75, 18],
  ['diagnose_structural', 75, 77, 20],
  ['diagnose_character', 77, 79, 20],
  ['diagnose_delivery', 79, 80, 18],
  ['diagnose_continuity', 80, 81, 18],
  // 优化
  ['optimize_content', 81, 84, 45],
  ['optimize_structural', 84, 86, 30],
  ['optimize_character', 86, 88, 30],
  ['optimize_delivery', 88, 89, 30],
  ['enrichment', 89, 91, 60],
  // 收尾
  ['consistency', 91, 93, 30],
  ['continuity_gate', 93, 95, 20],
  ['persist_versions', 95, 96, 10],
  ['selecting', 96, 97, 20],
  ['waiting_for_confirm', 97, 98, 30],
  ['finalize', 98, 99, 15],
  ['ledger_memory', 99, 99.3, 8],
  ['ledger_foreshadowing', 99.3, 99.6, 8],
  ['ledger_graph', 99.6, 99.9, 8],
  ['finalized', 100, 100, 0],
]

/**
 * 只有章节状态、没有 stage 时的保守兜底区间。
 * generating 故意停在准备段末尾：真实 stage 事件一到就能继续向前，绝不会先冲高再卡住。
 */
const STAGE_POINT_STATUS_FALLBACK: Record<string, GenerationStagePoint> = {
  generating: { start: 3, end: 28, weight: 90 },
  evaluating: { start: 60, end: 67, weight: 60 },
  successful: { start: 100, end: 100, weight: 0 },
  ready: { start: 100, end: 100, weight: 0 },
  failed: { start: 0, end: 100, weight: 0, hold: true },
  evaluation_failed: { start: 0, end: 97, weight: 0, hold: true },
}

/** 后端别名 → 主键，复用同一个区间对象。 */
const STAGE_POINT_ALIASES: Record<string, string> = {
  review: 'ai_review',
  self_critique: 'optimize_content',
  optimizer: 'optimize_content',
  reader_simulator: 'optimize_character',
  already_generating: 'generate_variants',
  running: 'generate_variants',
  in_progress: 'generate_variants',
}

/** 流水线顺序（不含状态兜底与别名），用于校验区间单调递增。 */
export const GENERATION_STAGE_ORDER: readonly string[] = STAGE_POINT_PIPELINE.map(([stage]) => stage)

export const GENERATION_STAGE_POINTS: Record<string, GenerationStagePoint> = (() => {
  const table: Record<string, GenerationStagePoint> = {}
  for (const [stage, start, end, weight] of STAGE_POINT_PIPELINE) {
    table[stage] = { start, end, weight }
  }
  for (const [stage, point] of Object.entries(STAGE_POINT_STATUS_FALLBACK)) {
    table[stage] = point
  }
  for (const [alias, target] of Object.entries(STAGE_POINT_ALIASES)) {
    if (table[target]) table[alias] = table[target]
  }
  return table
})()

/**
 * 解析某个 stage/状态对应的进度区间。
 * 顺序：原始键 → 归一化后的键 → 其它流水线（大纲/蓝图）按里程碑推导窄区间 → null。
 * 返回 null 表示未知阶段，调用方应保持当前值、不要跳变。
 */
export const resolveStageProgressWindow = (rawStage: unknown): GenerationStagePoint | null => {
  const key = String(rawStage ?? '').trim().toLowerCase()
  if (!key) return null
  const direct = GENERATION_STAGE_POINTS[key]
  if (direct) return direct
  const normalized = normalizeRuntimeStage(key)
  const mapped = GENERATION_STAGE_POINTS[normalized]
  if (mapped) return mapped
  const milestone = STAGE_META_MAP.get(normalized)?.milestone || 0
  if (milestone > 0) return { start: Math.max(0, milestone - 4), end: milestone, weight: 30 }
  return null
}

export const blocksSequentialGeneration = (status?: Chapter['generation_status'] | null) =>
  SEQUENTIAL_BLOCKING_STATUSES.has((status || 'not_generated') as Chapter['generation_status'])

export const canGenerateAfterPreviousStatus = (status?: Chapter['generation_status'] | null) =>
  !blocksSequentialGeneration(status)

export const isBusyChapterStatus = (status?: Chapter['generation_status'] | null) =>
  BUSY_CHAPTER_STATUSES.has((status || 'not_generated') as Chapter['generation_status'])

export const isRecoverableVersionStatus = (status?: Chapter['generation_status'] | null) =>
  RECOVERABLE_VERSION_STATUSES.has((status || 'not_generated') as Chapter['generation_status'])

export const resolveChapterRuntime = (
  chapter?: Partial<Chapter> | null,
  fallbackRuntime?: GenerationRuntime | null
): GenerationRuntime | null => {
  const chapterRuntime: GenerationRuntime = {}

  if (chapter?.progress_stage) chapterRuntime.progress_stage = chapter.progress_stage
  if (typeof chapter?.progress_message === 'string') chapterRuntime.progress_message = chapter.progress_message
  if (typeof chapter?.started_at !== 'undefined') chapterRuntime.started_at = chapter.started_at
  if (typeof chapter?.updated_at !== 'undefined') chapterRuntime.updated_at = chapter.updated_at
  if (Array.isArray(chapter?.allowed_actions)) chapterRuntime.allowed_actions = chapter.allowed_actions
  if (typeof chapter?.last_error_summary === 'string') chapterRuntime.last_error_summary = chapter.last_error_summary
  if (chapter?.generation_runtime && typeof chapter.generation_runtime === 'object') {
    Object.assign(chapterRuntime, chapter.generation_runtime)
  }

  const hasChapterRuntime = Object.keys(chapterRuntime).length > 0
  if (!hasChapterRuntime) return fallbackRuntime || null

  return {
    ...(fallbackRuntime || {}),
    ...chapterRuntime,
  }
}

export const resolveChapterActions = (
  chapter?: Pick<Chapter, 'allowed_actions'> | null,
  runtime?: GenerationRuntime | null
): string[] => {
  if (Array.isArray(chapter?.allowed_actions)) return chapter.allowed_actions
  if (Array.isArray(runtime?.allowed_actions)) return runtime.allowed_actions
  return []
}

export const canCancelGeneration = (
  chapter?: Pick<Chapter, 'generation_status' | 'allowed_actions'> | null,
  runtime?: GenerationRuntime | null
): boolean => {
  if (isBusyChapterStatus(chapter?.generation_status)) {
    return resolveChapterActions(chapter, runtime).includes('cancel_generation')
  }

  if (!runtime?.queued) return false
  if (resolveChapterActions(chapter, runtime).includes('cancel_generation')) return true

  const runtimeStage = normalizeRuntimeStage(runtime.progress_stage || runtime.status)
  return RUNTIME_BUSY_STAGES.has(runtimeStage)
}

export const isTrackableTaskStage = (rawStage: unknown): boolean => {
  const stage = normalizeRuntimeStage(rawStage)
  return RUNTIME_BUSY_STAGES.has(stage) || ['waiting_for_confirm', 'ready', 'successful', 'finalized', 'failed', 'evaluation_failed'].includes(stage)
}

export const isTrackableTask = (
  chapter?: Pick<Chapter, 'generation_status'> | null,
  runtime?: GenerationRuntime | null
): boolean => {
  const status = (chapter?.generation_status || 'not_generated') as Chapter['generation_status']
  if (isBusyChapterStatus(status) || isRecoverableVersionStatus(status)) return true
  if (runtime?.queued) return true
  return isTrackableTaskStage(runtime?.progress_stage || runtime?.status)
}

export const isBusyTask = (
  chapter?: Pick<Chapter, 'generation_status'> | null,
  runtime?: GenerationRuntime | null
): boolean => {
  const status = (chapter?.generation_status || 'not_generated') as Chapter['generation_status']
  if (isBusyChapterStatus(status)) return true
  if (runtime?.queued) return true
  const runtimeStage = normalizeRuntimeStage(runtime?.progress_stage || runtime?.status)
  return RUNTIME_BUSY_STAGES.has(runtimeStage)
}

const formatDuration = (value: number): string => {
  const totalSeconds = Math.max(0, Math.floor(value / 1000))
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60

  if (hours > 0) return pick(`${hours}小时 ${minutes}分`, `${hours} h ${minutes} min`)
  if (minutes > 0) return pick(`${minutes}分 ${seconds}秒`, `${minutes} min ${seconds} s`)
  return pick(`${seconds}秒`, `${seconds} s`)
}

const parseTimeMs = (value: unknown): number | null => {
  if (!value) return null
  const raw = String(value).trim()
  if (!raw) return null
  const normalized = /(?:Z|[+\-]\d{2}:\d{2})$/.test(raw) ? raw : `${raw}Z`
  const parsed = new Date(normalized).getTime()
  return Number.isNaN(parsed) ? null : parsed
}

const clampPercent = (value: number) => Math.max(0, Math.min(100, Math.round(value)))

const getRuntimeTimestamp = (runtime?: Record<string, any> | null): number =>
  parseTimeMs(runtime?.heartbeat_at || runtime?.updated_at || runtime?.started_at) || 0

const getStageDefinition = (stage: string) => STAGE_META_MAP.get(stage) || STAGE_META_MAP.get(normalizeRuntimeStage(stage)) || null

const getStageMilestone = (stage: string): number => getStageDefinition(stage)?.milestone || 0

const getStageDisplayLabel = (runtimeRecord: Record<string, any>, stage: string) => {
  if (stage.startsWith('diagnose_') && typeof runtimeRecord.diagnosis_stage_label === 'string') {
    return String(runtimeRecord.diagnosis_stage_label)
  }
  if (stage.startsWith('optimize_') && stage !== 'optimize_content' && typeof runtimeRecord.optimization_stage_label === 'string') {
    return String(runtimeRecord.optimization_stage_label)
  }
  if (stage === 'review' && typeof runtimeRecord.progress_message === 'string') {
    const message = String(runtimeRecord.progress_message)
    // 下面匹配的中文关键词来自后端 progress_message，是数据匹配，不随界面语言变化
    if (message.includes('综合') || message.includes('总评') || message.includes('对比')) return pick('AI 综合评审', 'AI overall review')
    if (message.includes('等待确认') || message.includes('确认最终版本')) return pick('等待确认', 'Awaiting confirmation')
    if (message.includes('选择') || message.includes('候选版本')) return pick('候选版本评审', 'Candidate review')
  }
  return STAGE_LABEL_MAP[stage]?.() || getStageDefinition(stage)?.label() || pick('未知阶段', 'Unknown stage')
}

const getPipelineSequence = (currentStage: string) => {
  if (currentStage.startsWith('outline_')) return OUTLINE_PIPELINE_SEQUENCE
  if (currentStage.startsWith('blueprint_')) return BLUEPRINT_PIPELINE_SEQUENCE
  return DEFAULT_PIPELINE_SEQUENCE
}

const inferCurrentStepIndex = (currentStage: string) => {
  const sequence = getPipelineSequence(currentStage)
  const index = sequence.indexOf(currentStage as any)
  return index >= 0 ? index : 0
}

const inferStageProgress = (runtimeRecord: Record<string, any>, currentStage: string, nowMs: number): number => {
  if (['ready', 'successful', 'finalized', 'failed', 'evaluation_failed', 'waiting_for_confirm'].includes(currentStage)) return 100

  const currentMilestone = getStageMilestone(currentStage)
  const sequence = getPipelineSequence(currentStage)
  const currentIndex = sequence.indexOf(currentStage as any)
  const previousStage = currentIndex > 0 ? sequence[currentIndex - 1] : null
  const previousMilestone = previousStage ? getStageMilestone(previousStage) : 0
  const totalProgress = clampPercent(Number(runtimeRecord.progress_percent || currentMilestone || 0) || 0)

  if (currentMilestone > previousMilestone) {
    const normalized = ((totalProgress - previousMilestone) / (currentMilestone - previousMilestone)) * 100
    if (Number.isFinite(normalized) && normalized >= 0 && normalized <= 100) {
      return clampPercent(normalized)
    }
  }

  const lastUpdatedMs = getRuntimeTimestamp(runtimeRecord)
  const stageStartMs = parseTimeMs(runtimeRecord.stage_started_at || runtimeRecord.updated_at || runtimeRecord.heartbeat_at || runtimeRecord.started_at)
  const elapsedMs = stageStartMs ? Math.max(0, nowMs - stageStartMs) : 0
  const sinceUpdateMs = lastUpdatedMs ? Math.max(0, nowMs - lastUpdatedMs) : 0
  const stallThreshold = STAGE_STALL_THRESHOLDS[currentStage] || 180_000

  if (sinceUpdateMs > 0 && sinceUpdateMs < stallThreshold) {
    const ratio = Math.max(0.12, Math.min(0.94, elapsedMs / stallThreshold))
    return clampPercent(ratio * 100)
  }

  return currentMilestone > 0 ? 100 : 0
}

export type ProjectTaskContext = {
  chapter: Chapter | null
  chapterNumber: number | null
  runtime: GenerationRuntime | null
}

/**
 * 任务中心事件的最小形状。抽出来是为了让正文分流逻辑可以脱离视图单测，
 * 而不是把判定藏在 WritingDesk 组件内部。
 */
export type TaskRuntimeEventLike = {
  event_id: number
  task_id?: string
  event_type: string
  status?: string | null
  stage?: string | null
  progress?: number | null
  message?: string | null
  payload?: Record<string, unknown> | null
  created_at?: string
  content_delta?: unknown
}

/**
 * 旧 SSE 连接可能在重试/刷新后迟到回调；只有事件任务仍绑定当前任务时才可落地。
 */
export const isTaskEventForCurrentTask = (
  eventTaskId: unknown,
  currentTaskId: unknown,
): boolean => {
  const eventId = String(eventTaskId ?? '').trim()
  const currentId = String(currentTaskId ?? '').trim()
  return Boolean(eventId && currentId && eventId === currentId)
}

export const taskRuntimeEventKind = (eventType: string): string => {
  if (eventType.includes('content')) return 'content'
  if (eventType.includes('quality') || eventType.includes('diagnostic')) return 'review'
  if (eventType.includes('log')) return 'status'
  if (eventType.includes('cancel') || eventType.includes('fail') || eventType.includes('stale')) return 'error'
  return 'status'
}

/**
 * 严格分流：只有 event_type === 'content_delta' 才算正文。
 * 日志/进度事件即使 payload 里混进了 delta/content 字段也一律不当正文，
 * 防止运行日志冒充正文出现在草稿区。
 */
export const extractContentDelta = (event: TaskRuntimeEventLike): string => {
  if (event.event_type !== 'content_delta') return ''
  const payload = (event.payload || {}) as Record<string, unknown>
  const candidate =
    event.content_delta ?? payload.content_delta ?? payload.delta ?? payload.text ?? payload.content
  return typeof candidate === 'string' ? candidate : ''
}

export const taskRuntimeEventToChapterEvent = (event: TaskRuntimeEventLike): GenerationRuntimeEvent => {
  const payload = (event.payload || {}) as Record<string, unknown>
  const contentDelta = extractContentDelta(event)
  const segmentIndex = typeof payload.segment_index === 'number' ? payload.segment_index : undefined
  return {
    at: event.created_at,
    stage: event.stage || undefined,
    level: event.status === 'failed' || event.status === 'stale' ? 'error' : 'info',
    kind: taskRuntimeEventKind(event.event_type),
    title: event.event_type,
    summary: event.message || undefined,
    message: event.message || undefined,
    progress_percent: typeof event.progress === 'number' ? event.progress : undefined,
    // 正文进入独立字段，同时填充 content_preview 供既有草稿区渲染。
    ...(contentDelta
      ? {
          content_delta: contentDelta,
          content_preview: contentDelta,
          content_is_preview: payload.preview === true,
          ...(typeof segmentIndex === 'number' ? { segment_index: segmentIndex } : {}),
        }
      : {}),
    metadata: {
      ...payload,
      task_event_id: event.event_id,
      task_event_type: event.event_type,
    },
  }
}

export type ChapterTaskUiModel = {
  stage: string
  stageLabel: string
  progress: number
  totalProgress: number
  stageProgress: number
  stageProgressLabel: string
  totalProgressLabel: string
  etaLabel: string
  isLikelyStalled: boolean
  displayMessage: string
  critiqueSummary: string
  critiqueHighlights: string[]
  degradedSummary: string
  currentStep: number
  totalSteps: number
  currentStepLabel: string
}

export const resolveProjectTaskContext = (
  project?: Pick<NovelProject, 'generation_runtime' | 'chapters'> | null,
  preferredChapter?: Chapter | null,
  diagnostics?: Record<string, any> | null
): ProjectTaskContext => {
  const fallbackRuntime = project?.generation_runtime || null
  const candidates = [...(project?.chapters || [])]
    .map((chapter) => {
      const runtime = resolveChapterRuntime(chapter, fallbackRuntime)
      return {
        chapter,
        runtime,
        busy: isBusyTask(chapter, runtime),
        trackable: isTrackableTask(chapter, runtime),
        updatedAt: getRuntimeTimestamp(runtime),
        isPreferred: Boolean(preferredChapter && preferredChapter.chapter_number === chapter.chapter_number && isTrackableTask(chapter, runtime)),
      }
    })
    .filter((item) => item.trackable)
    .sort((a, b) => {
      if (a.isPreferred !== b.isPreferred) return a.isPreferred ? -1 : 1
      if (a.busy !== b.busy) return a.busy ? -1 : 1
      if (a.updatedAt !== b.updatedAt) return b.updatedAt - a.updatedAt
      return (b.chapter.chapter_number || 0) - (a.chapter.chapter_number || 0)
    })

  const selected = candidates[0] || null
  const candidate = selected?.chapter || null
  const runtime = selected?.runtime || fallbackRuntime || null

  if (!runtime && diagnostics) {
    return {
      chapter: candidate,
      chapterNumber: candidate?.chapter_number ?? null,
      runtime: { diagnostics, last_error_summary: diagnostics.message },
    }
  }
  if (runtime && diagnostics) {
    return {
      chapter: candidate,
      chapterNumber: candidate?.chapter_number ?? null,
      runtime: { ...runtime, diagnostics, last_error_summary: runtime.last_error_summary || diagnostics.message },
    }
  }
  return {
    chapter: candidate,
    chapterNumber: candidate?.chapter_number ?? null,
    runtime,
  }
}

export const buildChapterTaskUiModel = (
  runtime?: Record<string, any> | null,
  options?: {
    progressMessage?: string | null
    status?: string | null
    nowMs?: number
    statusFetchFailureCount?: number
  }
): ChapterTaskUiModel => {
  const runtimeRecord = runtime || {}
  const stage = normalizeDisplayStage(runtimeRecord.progress_stage || runtimeRecord.status || options?.status)
  const nowMs = options?.nowMs || Date.now()
  const updatedAtMs = getRuntimeTimestamp(runtimeRecord)
  const sinceUpdateMs = updatedAtMs ? Math.max(0, nowMs - updatedAtMs) : 0
  const statusFetchFailureCount = Math.max(0, Math.floor(Number(options?.statusFetchFailureCount || 0) || 0))
  const totalProgress = ['ready', 'successful'].includes(stage)
    ? 100
    : clampPercent(Number(runtimeRecord.progress_percent || getStageMilestone(stage) || 0) || 0)
  const sequence = getPipelineSequence(stage)
  const totalSteps = sequence.length
  const currentStepIndex = ['ready', 'successful', 'finalized', 'failed', 'evaluation_failed'].includes(stage)
    ? totalSteps - 1
    : inferCurrentStepIndex(stage)
  const currentStep = Math.min(totalSteps, currentStepIndex + 1)
  const currentStepLabel = getStageDisplayLabel(runtimeRecord, stage)
  const stageProgress = inferStageProgress(runtimeRecord, stage, nowMs)
  const estimatedRemainingMs = Math.max(0, Number(runtimeRecord.estimated_remaining_seconds || 0) || 0) * 1000
  const stallThresholdMs = STAGE_STALL_THRESHOLDS[stage] || 180_000
  const isBusy = RUNTIME_BUSY_STAGES.has(stage) || stage === 'selecting'
  const backendMarkedStalled = Boolean(
    runtimeRecord.stale
    || runtimeRecord.is_stale
    || runtimeRecord.stalled
    || runtimeRecord.is_stalled
    || runtimeRecord.needs_recovery
  )
  const hasRepeatedSyncFailure = statusFetchFailureCount >= 2
  const exceededStageBudget = sinceUpdateMs >= stallThresholdMs
  const exceededHardBudget = sinceUpdateMs >= stallThresholdMs * 2
  const isLikelyStalled = Boolean(
    isBusy
    && exceededStageBudget
    && (backendMarkedStalled || hasRepeatedSyncFailure || exceededHardBudget)
  )

  const baseMessage = String(options?.progressMessage || runtimeRecord.progress_message || '').trim()
  const priorityFixes = Array.isArray(runtimeRecord.self_critique_priority_fixes)
    ? runtimeRecord.self_critique_priority_fixes
    : []
  const critiqueHighlights = priorityFixes
    .map((item) => {
      if (!item || typeof item !== 'object') return ''
      const record = item as Record<string, any>
      return String(record.suggested_fix || record.description || record.dimension || '').trim()
    })
    .filter(Boolean)
    .slice(0, 3)

  const degradedStages = Array.isArray(runtimeRecord.degraded_stages) ? runtimeRecord.degraded_stages : []
  const degradedNames = degradedStages.map((item) => {
    if (!item || typeof item !== 'object') return pick('未知步骤', 'Unknown step')
    const record = item as Record<string, any>
    return getStageDisplayLabel(runtimeRecord, normalizeRuntimeStage(record.stage))
  })
  const degradedSummary = degradedNames.length
    ? pick(`降级阶段：${degradedNames.join('、')}`, `Degraded stages: ${degradedNames.join(', ')}`)
    : ''

  const optimizationLogs = Array.isArray(runtimeRecord.optimization_logs) ? runtimeRecord.optimization_logs : []
  const critiqueSummaryParts = [
    typeof runtimeRecord.self_critique_final_score === 'number' ? pick(`评分 ${runtimeRecord.self_critique_final_score}`, `Score ${runtimeRecord.self_critique_final_score}`) : '',
    typeof runtimeRecord.self_critique_improvement === 'number' && runtimeRecord.self_critique_improvement !== 0 ? pick(`提升 ${runtimeRecord.self_critique_improvement}`, `Gain ${runtimeRecord.self_critique_improvement}`) : '',
    typeof runtimeRecord.self_critique_critical_count === 'number' && runtimeRecord.self_critique_critical_count > 0 ? pick(`严重问题 ${runtimeRecord.self_critique_critical_count}`, `Critical ${runtimeRecord.self_critique_critical_count}`) : '',
    typeof runtimeRecord.self_critique_major_count === 'number' && runtimeRecord.self_critique_major_count > 0 ? pick(`主要问题 ${runtimeRecord.self_critique_major_count}`, `Major ${runtimeRecord.self_critique_major_count}`) : '',
    optimizationLogs.length > 0 ? pick(`分批优化 ${optimizationLogs.length} 段`, `${optimizationLogs.length} batched passes`) : '',
    runtimeRecord.review_status ? pick(`评审状态 ${runtimeRecord.review_status}`, `Review status ${runtimeRecord.review_status}`) : '',
  ].filter(Boolean)
  const critiqueSummary = critiqueSummaryParts.join(' · ')

  const displayMessage = baseMessage
    || critiqueHighlights[0]
    || degradedSummary
    || (isLikelyStalled
      ? pick(
          `当前执行到第 ${currentStep}/${totalSteps} 步：${currentStepLabel}，长时间没有收到新日志`,
          `Now on step ${currentStep}/${totalSteps}: ${currentStepLabel} — no new logs for a while`
        )
      : pick(
          `当前执行到第 ${currentStep}/${totalSteps} 步：${currentStepLabel}`,
          `Now on step ${currentStep}/${totalSteps}: ${currentStepLabel}`
        ))

  return {
    stage,
    stageLabel: getStageDisplayLabel(runtimeRecord, stage),
    progress: totalProgress,
    totalProgress,
    stageProgress,
    stageProgressLabel: pick(
      `当前阶段完成度 ${stageProgress}% · 第 ${currentStep}/${totalSteps} 步`,
      `Stage ${stageProgress}% complete · step ${currentStep}/${totalSteps}`
    ),
    totalProgressLabel: pick(`总流程完成度 ${totalProgress}%`, `Pipeline ${totalProgress}% complete`),
    etaLabel: estimatedRemainingMs > 0 ? formatDuration(estimatedRemainingMs) : '',
    isLikelyStalled,
    displayMessage,
    critiqueSummary,
    critiqueHighlights,
    degradedSummary,
    currentStep,
    totalSteps,
    currentStepLabel,
  }
}

export const useChapterTaskUiModel = (
  runtime: ComputedRef<Record<string, any> | null | undefined>,
  options: ComputedRef<{ progressMessage?: string | null; status?: string | null; statusFetchFailureCount?: number }>
) => computed(() => buildChapterTaskUiModel(runtime.value, options.value))

export type ChapterActionDecision = {
  mode: 'action' | 'navigate' | 'running' | 'disabled'
  label: string
  reason: string
  targetChapterNumber?: number | null
  canGenerate: boolean
  shouldConfirm: boolean
  shouldEvaluate: boolean
  canOpenResult: boolean
  isRetry: boolean
}

const getOrderedChapterNumbers = (project?: Pick<NovelProject, 'blueprint' | 'chapters'> | null): number[] => {
  const outlineNumbers = (project?.blueprint?.chapter_outline || [])
    .map((chapter) => chapter.chapter_number)
    .filter((value): value is number => Number.isFinite(value))
  if (outlineNumbers.length) return [...outlineNumbers].sort((a, b) => a - b)
  return [...(project?.chapters || [])].map((chapter) => chapter.chapter_number).sort((a, b) => a - b)
}

export const getBlockingChapterNumber = (
  project?: Pick<NovelProject, 'blueprint' | 'chapters'> | null,
  chapterNumber?: number | null,
): number | null => {
  if (!project || chapterNumber === null || chapterNumber === undefined) return null
  const orderedNumbers = getOrderedChapterNumbers(project)
  for (const currentNumber of orderedNumbers) {
    if (currentNumber >= chapterNumber) break
    const chapter = project.chapters.find((item) => item.chapter_number === currentNumber)
    if (!canGenerateAfterPreviousStatus(chapter?.generation_status ?? 'not_generated')) {
      return currentNumber
    }
  }
  return null
}

export const canGenerateChapterInProject = (
  project?: Pick<NovelProject, 'blueprint' | 'chapters'> | null,
  chapterNumber?: number | null,
): boolean => {
  if (!project || chapterNumber === null || chapterNumber === undefined) return false
  const orderedNumbers = getOrderedChapterNumbers(project)
  if (!orderedNumbers.length) {
    return Boolean(project.chapters.find((item) => item.chapter_number === chapterNumber))
  }
  return getBlockingChapterNumber(project, chapterNumber) === null
}

export const resolveChapterActionDecision = (
  project: Pick<NovelProject, 'blueprint' | 'chapters'> | null | undefined,
  chapterNumber: number,
  options?: {
    generatingChapter?: number | null
    evaluatingChapter?: number | null
  }
): ChapterActionDecision => {
  const chapter = project?.chapters.find((item) => item.chapter_number === chapterNumber)
  const status = (chapter?.generation_status || 'not_generated') as Chapter['generation_status']
  const blockingChapterNumber = getBlockingChapterNumber(project, chapterNumber)
  const isGenerating = options?.generatingChapter === chapterNumber || status === 'generating'
  const isEvaluating = options?.evaluatingChapter === chapterNumber || status === 'evaluating'
  const canOpenResult = isEvaluating || status === 'selecting' || status === 'waiting_for_confirm'
  const shouldConfirm = status === 'waiting_for_confirm' || status === 'evaluation_failed'
  const shouldEvaluate = status === 'successful'
  const isRetry = status === 'failed' || status === 'evaluation_failed'
  const canGenerate = canGenerateChapterInProject(project, chapterNumber) || isRetry || status === 'waiting_for_confirm'

  if (isGenerating) {
    return {
      mode: 'running',
      label: pick('生成中...', 'Generating…'),
      reason: pick(
        '这一章已经在后台生成，先等结果回来。',
        'This chapter is already generating in the background — wait for the result.'
      ),
      targetChapterNumber: chapterNumber,
      canGenerate: false,
      shouldConfirm: false,
      shouldEvaluate: false,
      canOpenResult: false,
      isRetry: false,
    }
  }

  if (canOpenResult) {
    return {
      mode: 'navigate',
      label: pick('查看候选版本', 'View candidates'),
      reason: pick(
        '这一章已经产出了候选版本，先进入候选版本区继续看评审、对比并确认版本。',
        'Candidates already exist for this chapter — open the candidate area to review, compare, and confirm a version.'
      ),
      targetChapterNumber: chapterNumber,
      canGenerate: false,
      shouldConfirm,
      shouldEvaluate: false,
      canOpenResult: true,
      isRetry,
    }
  }

  if (blockingChapterNumber !== null) {
    return {
      mode: 'navigate',
      label: pick(`先去第 ${blockingChapterNumber} 章`, `Go to chapter ${blockingChapterNumber} first`),
      reason: pick(
        `要先完成第 ${blockingChapterNumber} 章，这一章才能开始写。`,
        `Chapter ${blockingChapterNumber} has to be finished before this one can start.`
      ),
      targetChapterNumber: blockingChapterNumber,
      canGenerate: false,
      shouldConfirm: false,
      shouldEvaluate: false,
      canOpenResult: false,
      isRetry: false,
    }
  }

  if (status === 'successful') {
    return {
      mode: 'action',
      label: pick('重新生成', 'Regenerate'),
      reason: pick(
        '当前正文已经完成，如需重写可以从这里重新生成。',
        'The draft is finished — regenerate here if it needs rewriting.'
      ),
      targetChapterNumber: chapterNumber,
      canGenerate: true,
      shouldConfirm: false,
      shouldEvaluate: true,
      canOpenResult: false,
      isRetry: false,
    }
  }

  if (isRetry) {
    return {
      mode: 'action',
      label: pick('重新生成', 'Regenerate'),
      reason: pick(
        '这一章上次失败了，可以直接重新生成，或先进去看异常。',
        'The last run failed — regenerate directly, or open it to inspect the error first.'
      ),
      targetChapterNumber: chapterNumber,
      canGenerate: true,
      shouldConfirm,
      shouldEvaluate: false,
      canOpenResult: status === 'evaluation_failed',
      isRetry: true,
    }
  }

  return {
    mode: 'action',
    label: pick('生成本章', 'Generate this chapter'),
    reason: '',
    targetChapterNumber: chapterNumber,
    canGenerate,
    shouldConfirm: false,
    shouldEvaluate: false,
    canOpenResult: false,
    isRetry: false,
  }
}
