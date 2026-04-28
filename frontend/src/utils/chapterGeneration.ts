import { computed, type ComputedRef } from 'vue'
import type { Chapter, GenerationRuntime, NovelProject } from '@/api/novel'

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
  'prepare_context',
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
  'optimizer',
  'enrichment',
  'persist_versions',
])

const STAGE_LABEL_MAP: Record<string, string> = {
  queued: '排队中',
  prepare_context: '准备上下文',
  generate_mission: '生成任务',
  generate_variants: '生成候选版本',
  review: 'AI 评审',
  diagnose_once: '问题诊断',
  diagnose_previous_chapter: '检查上一章',
  diagnose_context_bundle: '检查上下文',
  diagnose_structural: '结构诊断',
  diagnose_character: '角色诊断',
  diagnose_delivery: '表达诊断',
  optimize_content: '内容优化',
  optimize_structural: '结构优化',
  optimize_character: '角色优化',
  optimize_delivery: '表达优化',
  consistency: '一致性检查',
  persist_versions: '保存候选版本',
  selecting: '等待选择',
  waiting_for_confirm: '等待确认',
  ready: '已就绪',
  successful: '已完成',
  failed: '失败',
  evaluation_failed: '评审失败',
}

type BackendStageDefinition = {
  key: string
  label: string
  milestone: number
  aliases?: string[]
}

const BACKEND_STAGE_DEFINITIONS: BackendStageDefinition[] = [
  { key: 'queued', label: '排队中', milestone: 4, aliases: ['already_generating', 'running', 'in_progress'] },
  { key: 'prepare_context', label: '准备上下文', milestone: 8 },
  { key: 'generate_mission', label: '生成任务', milestone: 18 },
  { key: 'generate_variants', label: '生成候选版本', milestone: 34, aliases: ['generating'] },
  { key: 'review', label: 'AI 评审', milestone: 62, aliases: ['ai_review'] },
  { key: 'diagnose_once', label: '问题诊断', milestone: 70 },
  { key: 'diagnose_previous_chapter', label: '检查上一章', milestone: 72 },
  { key: 'diagnose_context_bundle', label: '检查上下文', milestone: 74 },
  { key: 'diagnose_structural', label: '结构诊断', milestone: 76 },
  { key: 'diagnose_character', label: '角色诊断', milestone: 78 },
  { key: 'diagnose_delivery', label: '表达诊断', milestone: 79 },
  { key: 'optimize_content', label: '内容优化', milestone: 80, aliases: ['self_critique', 'optimizer'] },
  { key: 'optimize_structural', label: '结构优化', milestone: 83 },
  { key: 'optimize_character', label: '角色优化', milestone: 86, aliases: ['reader_simulator'] },
  { key: 'optimize_delivery', label: '表达优化', milestone: 88, aliases: ['enrichment'] },
  { key: 'consistency', label: '一致性检查', milestone: 90 },
  { key: 'persist_versions', label: '保存候选版本', milestone: 92 },
  { key: 'waiting_for_confirm', label: '等待确认', milestone: 97, aliases: ['selecting'] },
  { key: 'successful', label: '已完成', milestone: 100, aliases: ['ready'] },
  { key: 'failed', label: '失败', milestone: 100, aliases: ['evaluation_failed'] },
]

const DEFAULT_PIPELINE_SEQUENCE = [
  'queued',
  'prepare_context',
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
  'persist_versions',
  'waiting_for_confirm',
] as const

const STAGE_META_MAP = new Map<string, BackendStageDefinition>()
for (const definition of BACKEND_STAGE_DEFINITIONS) {
  STAGE_META_MAP.set(definition.key, definition)
  for (const alias of definition.aliases || []) STAGE_META_MAP.set(alias, definition)
}

const STAGE_STALL_THRESHOLDS: Record<string, number> = {
  queued: 2 * 60_000,
  prepare_context: 3 * 60_000,
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
  persist_versions: 3 * 60_000,
  waiting_for_confirm: 30 * 60_000,
}

export const normalizeRuntimeStage = (rawStage: unknown): string => {
  const stage = String(rawStage || '').trim().toLowerCase()
  if (!stage) return 'queued'
  return STAGE_META_MAP.get(stage)?.key || stage
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
  return RUNTIME_BUSY_STAGES.has(stage) || ['waiting_for_confirm', 'ready', 'successful', 'failed', 'evaluation_failed'].includes(stage)
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

  if (hours > 0) return `${hours}小时 ${minutes}分`
  if (minutes > 0) return `${minutes}分 ${seconds}秒`
  return `${seconds}秒`
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
  if (stage.startsWith('optimize_') && typeof runtimeRecord.optimization_stage_label === 'string') {
    return String(runtimeRecord.optimization_stage_label)
  }
  if (stage === 'review' && typeof runtimeRecord.progress_message === 'string') {
    const message = String(runtimeRecord.progress_message)
    if (message.includes('综合') || message.includes('总评') || message.includes('对比')) return 'AI 综合评审'
    if (message.includes('等待确认') || message.includes('确认最终版本')) return '等待确认'
    if (message.includes('选择') || message.includes('候选版本')) return '候选版本评审'
  }
  return STAGE_LABEL_MAP[stage] || getStageDefinition(stage)?.label || '未知阶段'
}

const inferCurrentStepIndex = (currentStage: string) => {
  const index = DEFAULT_PIPELINE_SEQUENCE.indexOf(currentStage as any)
  return index >= 0 ? index : 0
}

const inferStageProgress = (runtimeRecord: Record<string, any>, currentStage: string, nowMs: number): number => {
  if (['ready', 'successful', 'failed', 'evaluation_failed', 'waiting_for_confirm'].includes(currentStage)) return 100

  const currentMilestone = getStageMilestone(currentStage)
  const currentIndex = DEFAULT_PIPELINE_SEQUENCE.indexOf(currentStage as any)
  const previousStage = currentIndex > 0 ? DEFAULT_PIPELINE_SEQUENCE[currentIndex - 1] : null
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
  const stage = normalizeRuntimeStage(options?.status || runtimeRecord.progress_stage || runtimeRecord.status)
  const nowMs = options?.nowMs || Date.now()
  const updatedAtMs = getRuntimeTimestamp(runtimeRecord)
  const sinceUpdateMs = updatedAtMs ? Math.max(0, nowMs - updatedAtMs) : 0
  const statusFetchFailureCount = Math.max(0, Math.floor(Number(options?.statusFetchFailureCount || 0) || 0))
  const totalProgress = ['ready', 'successful'].includes(stage)
    ? 100
    : clampPercent(Number(runtimeRecord.progress_percent || getStageMilestone(stage) || 0) || 0)
  const totalSteps = DEFAULT_PIPELINE_SEQUENCE.length
  const currentStepIndex = ['ready', 'successful', 'failed', 'evaluation_failed'].includes(stage)
    ? totalSteps - 1
    : inferCurrentStepIndex(stage)
  const currentStep = Math.min(totalSteps, currentStepIndex + 1)
  const currentStepLabel = getStageDisplayLabel(runtimeRecord, stage)
  const stageProgress = inferStageProgress(runtimeRecord, stage, nowMs)
  const estimatedRemainingMs = Math.max(0, Number(runtimeRecord.estimated_remaining_seconds || 0) || 0) * 1000
  const stallThresholdMs = STAGE_STALL_THRESHOLDS[stage] || 180_000
  const isBusy = RUNTIME_BUSY_STAGES.has(stage) || stage === 'selecting'
  const isLikelyStalled = Boolean(isBusy && sinceUpdateMs >= stallThresholdMs && statusFetchFailureCount >= 2)

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
  const degradedSummary = degradedStages.length
    ? `降级阶段：${degradedStages.map((item) => {
      if (!item || typeof item !== 'object') return '未知步骤'
      const record = item as Record<string, any>
      return getStageDisplayLabel(runtimeRecord, normalizeRuntimeStage(record.stage))
    }).join('、')}`
    : ''

  const critiqueSummaryParts = [
    typeof runtimeRecord.self_critique_final_score === 'number' ? `评分 ${runtimeRecord.self_critique_final_score}` : '',
    typeof runtimeRecord.self_critique_improvement === 'number' && runtimeRecord.self_critique_improvement !== 0 ? `提升 ${runtimeRecord.self_critique_improvement}` : '',
    typeof runtimeRecord.self_critique_critical_count === 'number' && runtimeRecord.self_critique_critical_count > 0 ? `严重问题 ${runtimeRecord.self_critique_critical_count}` : '',
    typeof runtimeRecord.self_critique_major_count === 'number' && runtimeRecord.self_critique_major_count > 0 ? `主要问题 ${runtimeRecord.self_critique_major_count}` : '',
    runtimeRecord.review_status ? `评审状态 ${runtimeRecord.review_status}` : '',
  ].filter(Boolean)
  const critiqueSummary = critiqueSummaryParts.join(' · ')

  const displayMessage = baseMessage
    || critiqueHighlights[0]
    || degradedSummary
    || (isLikelyStalled
      ? `当前执行到第 ${currentStep}/${totalSteps} 步：${currentStepLabel}，长时间没有收到新日志`
      : `当前执行到第 ${currentStep}/${totalSteps} 步：${currentStepLabel}`)

  return {
    stage,
    stageLabel: getStageDisplayLabel(runtimeRecord, stage),
    progress: totalProgress,
    totalProgress,
    stageProgress,
    stageProgressLabel: `当前阶段完成度 ${stageProgress}% · 第 ${currentStep}/${totalSteps} 步`,
    totalProgressLabel: `总流程完成度 ${totalProgress}%`,
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
      label: '生成中...',
      reason: '这一章已经在后台生成，先等结果回来。',
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
      label: '查看当前结果',
      reason: '这一章已经有候选结果了，先进去看评估或确认版本。',
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
      label: `先去第 ${blockingChapterNumber} 章`,
      reason: `要先完成第 ${blockingChapterNumber} 章，这一章才能开始写。`,
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
      label: '重写',
      reason: '当前正文已经完成，如需重写可以从这里重新生成。',
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
      label: '重试',
      reason: '这一章上次失败了，可以直接重试，或先进去看异常。',
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
    label: '创作',
    reason: '',
    targetChapterNumber: chapterNumber,
    canGenerate,
    shouldConfirm: false,
    shouldEvaluate: false,
    canOpenResult: false,
    isRetry: false,
  }
}
