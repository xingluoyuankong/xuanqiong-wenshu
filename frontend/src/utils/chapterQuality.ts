import type { Chapter, ChapterVersion, GenerationRuntime } from '@/api/novel'

export interface ChapterQualityMetrics {
  word_count?: number
  scene_fulfillment_rate?: number
  fulfilled_scene_count?: number
  scene_count?: number
  dialogue_changes_state?: boolean
  ending_pressure_passed?: boolean
  static_description_risk?: boolean
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

const getVersionMetrics = (version?: ChapterVersion | null): ChapterQualityMetrics | null => {
  const metadata = readRecord(version?.metadata)
  if (!metadata) return null
  return readMetrics(metadata.quality_metrics)
    || readMetrics(metadata.review_summaries?.final_quality_metrics)
    || readMetrics(metadata.story_progression_guard?.quality_metric_snapshot)
}

export const resolveChapterQualityMetrics = (
  chapter?: Chapter | null,
  runtime?: GenerationRuntime | Record<string, any> | null
): ChapterQualityMetrics | null => {
  const runtimeMetrics = readMetrics(runtime?.quality_metrics)
  if (runtimeMetrics) return runtimeMetrics

  const versions = Array.isArray(chapter?.versions) ? chapter!.versions : []
  if (!versions.length) return null

  const selectedVersionId = chapter?.selected_version_id
  const selectedVersion = selectedVersionId
    ? versions.find((version) => version.id === selectedVersionId)
    : null
  return getVersionMetrics(selectedVersion) || getVersionMetrics(versions[versions.length - 1])
}

export const buildChapterQualitySummary = (
  chapter?: Chapter | null,
  runtime?: GenerationRuntime | Record<string, any> | null
): ChapterQualitySummary | null => {
  const metrics = resolveChapterQualityMetrics(chapter, runtime)
  if (!metrics) return null

  const issues: string[] = []
  const backendLabels = Array.isArray(metrics.quality_issue_labels)
    ? metrics.quality_issue_labels.filter((item): item is string => typeof item === 'string' && Boolean(item.trim()))
    : Array.isArray(metrics.quality_issue_summary?.labels)
      ? metrics.quality_issue_summary.labels.filter((item): item is string => typeof item === 'string' && Boolean(item.trim()))
      : []
  if (backendLabels.length) issues.push(...backendLabels)
  const sceneRate = Number(metrics.scene_fulfillment_rate)
  if (!backendLabels.length) {
    if (Number.isFinite(sceneRate) && sceneRate < 0.75) issues.push(`场景兑现 ${Math.round(sceneRate * 100)}%`)
    if (metrics.dialogue_changes_state === false) issues.push('对白未改局势')
    if (metrics.ending_pressure_passed === false) issues.push('章末未递压')
    if (metrics.static_description_risk === true) issues.push('静态描写偏高')
  }

  if (!issues.length) {
    return {
      metrics,
      label: Number.isFinite(sceneRate) ? `质量通过 · 场景 ${Math.round(sceneRate * 100)}%` : '质量通过',
      tone: 'success',
      issues,
    }
  }

  return {
    metrics,
    label: issues.length > 1 ? `质量风险 ${issues.length} 项` : issues[0],
    tone: metrics.quality_issue_summary?.tone || (issues.length >= 2 || metrics.static_description_risk === true ? 'danger' : 'warning'),
    issues,
  }
}
