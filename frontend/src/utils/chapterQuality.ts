import type { Chapter, ChapterVersion, GenerationRuntime } from '@/api/novel'
import { pick } from '@/composables/useLocale'

export interface ChapterQualityMetrics {
  word_count?: number
  word_count_below_min?: boolean | null
  word_count_far_above_target?: boolean | null
  word_count_far_below_target?: boolean | null
  word_requirement_met?: boolean | null
  scene_fulfillment_rate?: number | null
  fulfilled_scene_count?: number
  scene_count?: number
  // T-13 / T-14：这些判定在后端是**三态**（true 通过 / false 不通过 / null 不适用或未评估），
  // 不是 boolean。类型必须带 null，否则 `=== false` 的写法会被误读成「非 true 即 false」，
  // 后续维护很容易改成 `!metrics.x` —— 那会把 null 当失败显示成风险。
  dialogue_changes_state?: boolean | null
  // 本章任务书是否声明过对话预期；null 判定的含义靠它解释（没要求 + 正文无对话 = 不适用）
  dialogue_expectation_declared?: boolean | null
  dialogue_state_applicable?: boolean | null
  ending_pressure_passed?: boolean | null
  static_description_risk?: boolean | null
  // 事件密度三态 + 「有没有评估过」标记。样本短于 800 字时后端不评估，三个 passed 均为 null。
  event_density_evaluated?: boolean | null
  event_density_skip_reason?: string | null
  event_density_passed?: boolean | null
  state_change_interval_passed?: boolean | null
  long_chapter_density_passed?: boolean | null
  quality_issue_labels?: string[]
  quality_issue_codes?: string[]
  quality_issue_summary?: {
    tone?: 'success' | 'warning' | 'danger'
    labels?: string[]
    codes?: string[]
    count?: number
  }
  [key: string]: unknown
}

export interface ChapterQualitySummary {
  metrics: ChapterQualityMetrics
  label: string
  tone: 'success' | 'warning' | 'danger'
  issues: string[]
}

const readRecord = (value: unknown): Record<string, any> | null =>
  value && typeof value === 'object' ? value as Record<string, any> : null

const readMetrics = (value: unknown): ChapterQualityMetrics | null => {
  const record = readRecord(value)
  return record ? record as ChapterQualityMetrics : null
}

const mergeMetrics = (...candidates: Array<ChapterQualityMetrics | null>): ChapterQualityMetrics | null => {
  const merged: Record<string, unknown> = {}
  for (const candidate of candidates) {
    if (!candidate) continue
    for (const [key, value] of Object.entries(candidate)) {
      // An explicit null is a real tri-state value and must remain authoritative;
      // only an absent field may be filled from a legacy/fallback snapshot.
      if (!(key in merged)) merged[key] = value
    }
  }
  return Object.keys(merged).length ? merged as ChapterQualityMetrics : null
}

const hasMetricData = (metrics: ChapterQualityMetrics | null): metrics is ChapterQualityMetrics =>
  Boolean(metrics && Object.keys(metrics).length)

const hasQualitySignal = (metrics: ChapterQualityMetrics): boolean => {
  const scalarKeys = [
    'score',
    'scene_fulfillment_rate',
    'dialogue_changes_state',
    'ending_pressure_passed',
    'static_description_risk',
    'event_density_passed',
    'state_change_interval_passed',
    'long_chapter_density_passed',
  ]
  // Presence alone is not a quality result: backend tri-state fields may be
  // explicitly null when the dimension was not applicable/evaluated. Keep
  // valid false/0 values as real signals, but do not turn null into "passed".
  // Presence alone is not a quality result: backend tri-state fields may be
  // explicitly null when the dimension was not applicable/evaluated. Keep
  // valid false/0 values as real signals, but do not turn null into "passed".
  if (scalarKeys.some((key) => metrics[key] != null)) return true
  if ('quality_gate_passed' in metrics && metrics.quality_gate_passed != null) return true
  return (
    (Array.isArray(metrics.quality_issue_codes) && metrics.quality_issue_codes.length > 0) ||
    (Array.isArray(metrics.quality_issue_labels) && metrics.quality_issue_labels.length > 0) ||
    Boolean(metrics.quality_issue_summary && Object.keys(metrics.quality_issue_summary).length)
  )
}

const getVersionMetrics = (version?: ChapterVersion | null): ChapterQualityMetrics | null => {
  const metadata = readRecord(version?.metadata)
  if (!metadata) return null
  const candidates = [
    readMetrics(metadata.quality_metrics),
    readMetrics(metadata.review_summaries?.final_quality_metrics),
    readMetrics(metadata.story_progression_guard?.quality_metric_snapshot),
  ]
  return mergeMetrics(...candidates.filter(hasMetricData))
}

export const resolveChapterQualityMetrics = (
  chapter?: Chapter | null,
  runtime?: GenerationRuntime | Record<string, any> | null
): ChapterQualityMetrics | null => {
  const runtimeMetrics = readMetrics(runtime?.quality_metrics)
  const versions = Array.isArray(chapter?.versions) ? chapter!.versions : []
  const selectedVersionId = chapter?.selected_version_id
  const selectedVersion = selectedVersionId
    ? versions.find((version) => version.id === selectedVersionId)
    : null
  const versionMetrics = versions.length
    ? getVersionMetrics(selectedVersion) || getVersionMetrics(versions[versions.length - 1])
    : null
  return mergeMetrics(hasMetricData(runtimeMetrics) ? runtimeMetrics : null, versionMetrics)
}

export const buildChapterQualitySummary = (
  chapter?: Chapter | null,
  runtime?: GenerationRuntime | Record<string, any> | null
): ChapterQualitySummary | null => {
  const metrics = resolveChapterQualityMetrics(chapter, runtime)
  if (!metrics) return null
  if (!hasQualitySignal(metrics)) {
    return {
      metrics,
      label: pick('质量未评估', 'Quality not assessed'),
      tone: 'warning',
      issues: [],
    }
  }

  const issues: string[] = []
  const directBackendLabels = Array.isArray(metrics.quality_issue_labels)
    ? metrics.quality_issue_labels.filter((item): item is string => typeof item === 'string' && Boolean(item.trim()))
    : []
  const summaryBackendLabels = Array.isArray(metrics.quality_issue_summary?.labels)
    ? metrics.quality_issue_summary.labels.filter((item): item is string => typeof item === 'string' && Boolean(item.trim()))
    : []
  const directBackendCodes = Array.isArray(metrics.quality_issue_codes)
    ? metrics.quality_issue_codes.filter((item): item is string => typeof item === 'string' && Boolean(item.trim()))
    : []
  const summaryBackendCodes = Array.isArray(metrics.quality_issue_summary?.codes)
    ? metrics.quality_issue_summary.codes.filter((item): item is string => typeof item === 'string' && Boolean(item.trim()))
    : []
  const backendCodes = directBackendCodes.length ? directBackendCodes : summaryBackendCodes
  // Legacy payloads may carry an empty direct array while the nested summary
  // still contains the real labels; an empty array must not mask that fallback.
  const backendLabels = directBackendLabels.length ? directBackendLabels : summaryBackendLabels
  // 后端下发的 label 已是成文文案，前端不再二次翻译；只有本地推导的兜底文案走 pick
  if (backendLabels.length) issues.push(...backendLabels)
  const sceneRate = metrics.scene_fulfillment_rate == null
    ? Number.NaN
    : Number(metrics.scene_fulfillment_rate)
  if (!backendLabels.length) {
    if (Number.isFinite(sceneRate) && sceneRate < 0.75) {
      const percent = Math.round(sceneRate * 100)
      issues.push(pick(`场景兑现 ${percent}%`, `Scene fulfillment ${percent}%`))
    }
    if (metrics.word_count_below_min === true) issues.push(pick('低于字数下限', 'Below minimum word count'))
    if (metrics.word_count_far_below_target === true && metrics.word_count_below_min !== true) {
      issues.push(pick('字数显著低于目标', 'Far below target word count'))
    }
    if (metrics.word_count_far_above_target === true) issues.push(pick('字数远超目标', 'Far above target word count'))
    if (metrics.word_requirement_met === false && metrics.word_count_below_min !== true) {
      issues.push(pick('未满足字数要求', 'Word requirement unmet'))
    }
    // 全部用 `=== false` 严格比较，不能写 `!metrics.x`：三态里的 null 表示
    // 「该维度不适用 / 未评估」，把它显示成质量风险就是凭「没测」报红。
    if (metrics.dialogue_changes_state === false) issues.push(pick('对白未改局势', 'Dialogue does not shift the situation'))
    if (metrics.ending_pressure_passed === false) issues.push(pick('章末未递压', 'Chapter ending adds no pressure'))
    if (metrics.static_description_risk === true) issues.push(pick('静态描写偏高', 'Static description too high'))
    // D-22：事件密度原本是 5 个维度里唯一没有兜底文案的一个。后端正常会下发
    // quality_issue_labels，但老章节 metadata 和漏写 labels 的路径会走到这里，
    // 那时事件密度不达标在前端完全不可见 —— 而它恰是核心维度。
    if (metrics.event_density_evaluated !== false && metrics.event_density_passed === false) issues.push(pick('事件密度不足', 'Event density too low'))
    if (metrics.event_density_evaluated !== false && metrics.state_change_interval_passed === false) issues.push(pick('局势变化间隔过长', 'State changes too far apart'))
    if (metrics.event_density_evaluated !== false && metrics.long_chapter_density_passed === false) issues.push(pick('长章推进不足', 'Long chapter lacks progression'))
    if (!issues.length && metrics.quality_gate_passed === false) {
      issues.push(pick('质量门未通过', 'Quality gate failed'))
    }
    if (!issues.length && backendCodes.length) {
      issues.push(...backendCodes.map((code) => pick(`质量问题 ${code}`, `Quality issue ${code}`)))
    }
    if (!issues.length && metrics.quality_issue_summary?.tone === 'danger') {
      issues.push(pick('质量摘要存在风险', 'Quality summary reports risk'))
    }
  }

  if (!issues.length) {
    const percent = Math.round(sceneRate * 100)
    return {
      metrics,
      label: Number.isFinite(sceneRate)
        ? pick(`质量通过 · 场景 ${percent}%`, `Quality passed · scenes ${percent}%`)
        : pick('质量通过', 'Quality passed'),
      tone: 'success',
      issues,
    }
  }

  return {
    metrics,
    label: issues.length > 1
      ? pick(`质量风险 ${issues.length} 项`, `${issues.length} quality risks`)
      : issues[0],
    tone: metrics.quality_issue_summary?.tone || (metrics.quality_gate_passed === false || issues.length >= 2 || metrics.static_description_risk === true ? 'danger' : 'warning'),
    issues,
  }
}
