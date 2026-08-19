<template>
  <n-card :bordered="false" class="runtime-card">
    <template #header>
      <div class="runtime-card__header">
        <div>
          <span class="runtime-card__title">{{ pick('运行日志', 'Runtime logs') }}</span>
          <p class="runtime-card__subtitle">{{ pick(
            '左边用短句和小图案看关键阶段；右边直接看生成状态、草稿片段、质量门和修补建议。',
            'The left rail summarises milestones with short lines and small glyphs; the right side shows generation state, draft excerpts, quality gates, and patch suggestions.'
          ) }}</p>
        </div>
        <n-space>
          <n-button tertiary size="small" @click="refreshNow" :loading="loading">{{ pick('刷新', 'Refresh') }}</n-button>
          <n-button tertiary size="small" @click="autoRefresh = !autoRefresh">{{ autoRefresh ? pick('停止自动刷新', 'Stop auto refresh') : pick('开启自动刷新', 'Start auto refresh') }}</n-button>
        </n-space>
      </div>
    </template>

    <n-space vertical size="large">
      <n-alert v-if="error" type="error" closable @close="error = null">{{ error }}</n-alert>
      <n-alert v-if="focusedProjectId" type="info" :bordered="false">{{ pick('当前已从小说入口定位到：', 'Focused from the novel entry: ') }}{{ focusedProjectTitle }}{{ punct.period }}<n-button text type="primary" @click="clearFocus">{{ pick('查看全部', 'View all') }}</n-button></n-alert>

      <n-spin :show="loading">
        <n-empty v-if="!visibleProjects.length && !loading" :description="pick('暂无可展示的运行日志', 'No runtime logs to show yet')" />

        <div v-else class="runtime-layout">
          <aside class="project-rail">
            <button v-for="project in visibleProjects" :key="project.project_id" class="project-rail__item" :class="{ 'project-rail__item--active': selectedProjectId === project.project_id }" @click="selectProject(project.project_id)">
              <strong>{{ project.project_title }}</strong>
              <span>{{ pick(`${project.chapters.length} 章`, `${project.chapters.length} ch.`) }} · {{ formatDateTime(project.updated_at) }}</span>
            </button>
          </aside>

          <section v-if="selectedProject && selectedChapter" class="runtime-main">
            <div class="runtime-main__head">
              <div>
                <h3>{{ selectedProject.project_title }}</h3>
                <p>{{ pick('项目 ID：', 'Project ID: ') }}{{ selectedProject.project_id }} · {{ pick('最近更新：', 'Updated: ') }}{{ formatDateTime(selectedProject.updated_at) }}</p>
              </div>
              <div class="runtime-main__head-tags">
                <n-tag type="primary" round>{{ pick(`第 ${selectedChapter.chapter_number} 章`, `Chapter ${selectedChapter.chapter_number}`) }}</n-tag>
                <n-tag size="small" :type="tagTypeByStatus(selectedChapter.generation_status)" round>{{ selectedChapter.generation_status }}</n-tag>
              </div>
            </div>

            <div class="chapter-switcher">
              <button v-for="chapter in selectedProject.chapters" :key="chapter.chapter_number" :class="{ active: selectedChapterNumber === chapter.chapter_number }" @click="selectedChapterNumber = chapter.chapter_number">{{ pick(`第 ${chapter.chapter_number} 章`, `Ch. ${chapter.chapter_number}`) }}</button>
            </div>

            <div class="runtime-content">
              <aside class="brief-panel">
                <div class="brief-panel__header">
                  <div>
                    <div class="section-title">{{ pick('简略日志', 'Brief log') }}</div>
                    <p class="brief-panel__tip">{{ pick(
                      '显示关键阶段节点，并补充“本步用时 / 累计用时”，快速判断任务卡在哪一步。',
                      'Shows milestone nodes with step and cumulative durations so you can spot where a run stalls.'
                    ) }}</p>
                  </div>
                  <n-button text type="primary" @click="briefExpanded = !briefExpanded">
                    {{ briefExpanded
                      ? pick('收起列表', 'Collapse')
                      : pick(`显示全部（${briefLogs.length} 条）`, `Show all (${briefLogs.length})`) }}
                  </n-button>
                </div>

                <ul v-if="visibleBriefLogs.length" class="brief-log-list">
                  <li v-for="(item, index) in visibleBriefLogs" :key="`${item.at || 'brief'}-${index}`" class="brief-log-item">
                    <div class="brief-log-item__top">
                      <span class="brief-log-item__time"><span class="brief-log-item__icon">{{ briefIcon(item) }}</span>{{ formatDateTime(item.at) }}</span>
                      <span v-if="item.stateLabel" class="brief-log-item__badge" :class="item.stateClass">{{ item.stateLabel }}</span>
                    </div>
                    <strong>{{ item.title || item.message }}</strong>
                    <p v-if="item.summary && item.summary !== item.message" class="brief-log-item__summary">{{ item.summary }}</p>
                    <div class="brief-log-item__meta">
                      <small v-if="item.stage">{{ item.stage }}</small>
                      <small v-if="item.kind">{{ kindLabel(item.kind) }}</small>
                      <small v-if="item.stepDurationLabel">{{ pick('本步用时：', 'Step: ') }}{{ item.stepDurationLabel }}</small>
                      <small v-if="item.totalDurationLabel">{{ pick('累计：', 'Total: ') }}{{ item.totalDurationLabel }}</small>
                    </div>
                  </li>
                </ul>
                <n-empty v-else size="small" :description="pick('当前没有可归纳的关键阶段日志', 'No milestone entries to summarise yet')" />

                <div class="brief-summary">
                  <div class="section-title section-title--small">{{ pick('摘要参数', 'Summary fields') }}</div>
                  <dl class="summary-grid">
                    <template v-for="item in buildSummaryEntries(selectedChapter)" :key="item.label"><dt>{{ item.label }}</dt><dd>{{ item.value }}</dd></template>
                  </dl>
                </div>
              </aside>

              <section class="backend-panel">
                <div class="section-title">{{ pick('详细生成状态日志', 'Detailed generation log') }}</div>
                <p class="backend-panel__tip">{{ pick(
                  '这里优先显示小说生成本身：当前阶段、草稿预览、质量门、局部补丁和保存结果；原始 metadata 收进开发者详情。',
                  'This side leads with the generation itself: current stage, draft preview, quality gates, local patches, and save results. Raw metadata is tucked into developer details.'
                ) }}</p>
                <div ref="backendConsoleRef" class="backend-console">
                  <div v-for="(line, index) in backendLines" :key="`${line.at || 'line'}-${index}`" class="backend-line">
                    <div class="backend-line__meta">
                      <span class="backend-line__kind">{{ kindIcon(line) }} {{ kindLabel(line.kind) }}</span>
                      <span>{{ formatDateTime(line.at) }}</span>
                      <span>[{{ formatLevelCode(line.level) }}]</span>
                      <span v-if="line.stage">[{{ line.stage }}]</span>
                      <span v-if="line.stateLabel" class="backend-line__badge" :class="line.stateClass">{{ line.stateLabel }}</span>
                    </div>
                    <div class="backend-line__message">{{ line.title || line.message || pick('生成状态更新', 'Generation status update') }}</div>
                    <p v-if="line.summary && line.summary !== line.message && line.summary !== line.title" class="backend-line__summary">{{ line.summary }}</p>

                    <div v-if="line.metrics.length" class="metric-chips">
                      <span v-for="metric in line.metrics" :key="metric.label" class="metric-chip">
                        <strong>{{ metric.label }}</strong>{{ metric.value }}
                      </span>
                    </div>

                    <div v-if="line.contentPreview" class="content-preview">
                      <span>{{ pick('生成内容预览', 'Generated content preview') }}</span>
                      <p>{{ line.contentPreview }}</p>
                    </div>

                    <div v-if="patchSuggestions(line).length" class="patch-suggestions">
                      <span>{{ pick('局部补丁建议', 'Local patch suggestions') }}</span>
                      <ul>
                        <li v-for="(patch, patchIndex) in patchSuggestions(line)" :key="`${line.at || 'patch'}-${patchIndex}`">
                          {{ patch }}
                        </li>
                      </ul>
                    </div>

                    <div v-if="artifactRefs(line).length" class="artifact-refs">
                      <span>{{ pick('产物引用', 'Artifact references') }}</span>
                      <code v-for="(artifact, artifactIndex) in artifactRefs(line)" :key="`${line.at || 'artifact'}-${artifactIndex}`">{{ artifact }}</code>
                    </div>

                    <details v-if="line.metadata && Object.keys(line.metadata).length" class="developer-details">
                      <summary>{{ pick('开发者详情：metadata', 'Developer details: metadata') }}</summary>
                      <pre>{{ formatJson(line.metadata) }}</pre>
                    </details>
                  </div>

                  <div v-if="runtimeSnapshotText" class="backend-snapshot">
                    <details>
                      <summary class="backend-snapshot__title">{{ pick('开发者详情：runtime snapshot', 'Developer details: runtime snapshot') }}</summary>
                      <pre>{{ runtimeSnapshotText }}</pre>
                    </details>
                  </div>
                </div>
              </section>
            </div>
          </section>
        </div>
      </n-spin>
    </n-space>
  </n-card>
</template>

<script setup lang="ts">

import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NAlert, NButton, NCard, NEmpty, NSpace, NSpin, NTag } from 'naive-ui'
import { AdminAPI, type ChapterRuntimeLogItem, type NovelRuntimeLogItem } from '@/api/admin'
import { useLocale } from '@/composables/useLocale'
// SSE ready: import { connectSSE } from '@/utils/sseStream'

type RuntimeLine = {
  at?: string | null
  stage?: string
  level?: string
  kind: string
  title: string
  summary: string
  contentPreview: string
  metrics: Array<{ label: string; value: string }>
  artifactRefs: string[]
  message: string
  metadata: Record<string, any>
  stateLabel?: string
  stateClass?: string
  /** 是否属于「关键阶段」，进简略日志。语言无关，避免翻译后匹配失效 */
  brief?: boolean
  syntheticKey?: string
  stepDurationMs?: number | null
  totalDurationMs?: number | null
}

const route = useRoute()
const router = useRouter()
const { pick, punct, formatNumber: formatLocaleNumber } = useLocale()
const projects = ref<NovelRuntimeLogItem[]>([])
const loading = ref(false)
const refreshing = ref(false)
const error = ref<string | null>(null)
const autoRefresh = ref(true)
const briefExpanded = ref(false)
const selectedProjectId = ref<string | null>(null)
const selectedChapterNumber = ref<number | null>(null)
const backendConsoleRef = ref<HTMLElement | null>(null)
let refreshTimer: number | null = null

const focusedProjectId = computed(() => typeof route.query.project_id === 'string' ? route.query.project_id : '')
const visibleProjects = computed(() => projects.value.filter(project => Array.isArray(project.chapters) && project.chapters.length > 0).filter(project => !focusedProjectId.value || project.project_id === focusedProjectId.value))
const selectedProject = computed(() => visibleProjects.value.find(project => project.project_id === selectedProjectId.value) || visibleProjects.value[0] || null)
const selectedChapter = computed(() => selectedProject.value?.chapters.find(chapter => chapter.chapter_number === selectedChapterNumber.value) || selectedProject.value?.chapters[0] || null)
const focusedProjectTitle = computed(() => selectedProject.value?.project_title || focusedProjectId.value)

const backendLines = computed<RuntimeLine[]>(() => {
  const chapter = selectedChapter.value
  if (!chapter) return []
  return [...normalizeEvents(chapter.runtime_events || []), ...buildSyntheticBackendLines(chapter)]
    .sort((a, b) => String(a.at || '').localeCompare(String(b.at || '')))
})

const briefLogs = computed<Array<RuntimeLine & { stepDurationLabel: string; totalDurationLabel: string; index: number }>>(() => {
  const events = backendLines.value.filter(event => event.message && event.brief)
  return events.map((event, index) => ({
    ...event,
    stepDurationLabel: formatDuration(event.stepDurationMs),
    totalDurationLabel: formatDuration(event.totalDurationMs),
    index,
  })).reverse()
})

const visibleBriefLogs = computed(() => briefExpanded.value ? briefLogs.value : briefLogs.value.slice(0, 12))

const runtimeSnapshotText = computed(() => {
  const snapshot = selectedChapter.value?.runtime_snapshot || {}
  return Object.keys(snapshot).length ? formatJson(snapshot) : ''
})

// 指标名是展示文案，用函数惰性求值，切换语言后 buildMetrics 会重新取到新语言
const METRIC_LABELS: Record<string, () => string> = {
  target_word_count: () => pick('目标字数', 'Target words'),
  min_word_count: () => pick('最低字数', 'Minimum words'),
  actual_word_count: () => pick('实际字数', 'Actual words'),
  word_count: () => pick('字数', 'Word count'),
  version_count: () => pick('候选数', 'Candidates'),
  quality_score: () => pick('质量分', 'Quality score'),
  event_density_score: () => pick('事件密度', 'Event density'),
  event_density_per_1000: () => pick('每千字推进', 'Progress per 1k words'),
  progression_unit_count: () => pick('推进单元', 'Progression units'),
  blocker_count: () => pick('阻断项', 'Blockers'),
  warning_count: () => pick('警告项', 'Warnings'),
  stagewide_deferred_count: () => pick('延后整章候选', 'Deferred whole-chapter candidates'),
  manual_stagewide_confirmation_required: () => pick('需人工确认', 'Manual confirmation required'),
  word_requirement_met: () => pick('字数达标', 'Word target met'),
  review_status: () => pick('评审状态', 'Review status'),
  optimization_strategy: () => pick('优化策略', 'Optimization strategy'),
  optimization_strategy_phase: () => pick('策略阶段', 'Strategy phase'),
  generated_version_count: () => pick('候选数', 'Candidates'),
  candidate_count: () => pick('候选数', 'Candidates'),
  best_version_index: () => pick('推荐版本', 'Recommended version'),
  token_budget_records: () => pick('预算记录', 'Budget records'),
  estimated_generation_tokens: () => pick('估算 Token', 'Estimated tokens'),
  record_count: () => pick('记录数', 'Records'),
  total_tokens: () => pick('总 Token', 'Total tokens'),
  estimated_cost: () => pick('估算成本', 'Estimated cost'),
  active_profile_name: () => pick('当前 Provider', 'Active provider'),
  recommended_profile_name: () => pick('推荐 Provider', 'Recommended provider'),
  planned_character_count: () => pick('计划角色', 'Planned characters'),
  target_character_count: () => pick('目标角色', 'Target characters'),
  must_resolve_count: () => pick('必须回收', 'Must resolve'),
  should_reinforce_count: () => pick('应强化', 'Should reinforce'),
  avoid_forgetting_count: () => pick('禁忘', 'Do not forget'),
  active_clue_count: () => pick('活跃线索', 'Active clues'),
  timeout_seconds: () => pick('超时秒数', 'Timeout (s)'),
  max_tokens: () => pick('最大 Token', 'Max tokens'),
}

const PREVIEW_KEYS = [
  'content_preview',
  'draft_preview',
  'draft_excerpt',
  'content_excerpt',
  'tail_excerpt',
  'preview',
  'sample',
  'text_excerpt',
]

const PATCH_KEYS = [
  'manual_patch_suggestions',
  'patch_suggestions',
  'patches',
  'suggestions',
  'blockers',
  'warnings',
]

/**
 * 判断一条后端事件是否属于「关键阶段」。
 * 匹配的是后端下发的中文原文（数据），不随界面语言变化；
 * `degraded` 状态原来靠展示文案「降级失败」命中「失败」，这里改成显式判断。
 */
function isBriefWorthyEvent(stage: string, rawMessage: string, degradedKind: '' | 'skip' | 'degraded') {
  if (degradedKind === 'degraded') return true
  const text = `${stage} ${rawMessage}`
  return /候选版本|阶段完成|等待确认|正在调用模型|正在写入|开始|完成|失败|评估|优化|补字数|落库|一致性|诊断/i.test(text)
}

function normalizeStageLabel(stage: string) {
  const map: Record<string, () => string> = {
    review: () => pick('评审阶段', 'Review stage'),
    ai_review: () => pick('AI 评审', 'AI review'),
    optimize_content: () => pick('分阶段优化', 'Staged optimization'),
    consistency: () => pick('一致性校验', 'Consistency check'),
    persist_versions: () => pick('候选版本落库', 'Persist candidates'),
    waiting_for_confirm: () => pick('等待确认', 'Awaiting confirmation'),
  }
  return map[stage]?.() || stage || pick('未知阶段', 'Unknown stage')
}

function normalizeText(value: unknown, maxLength = 420): string {
  if (value === null || typeof value === 'undefined') return ''
  if (Array.isArray(value)) {
    return value.map(item => normalizeText(item, Math.max(80, Math.floor(maxLength / 2)))).filter(Boolean).join('；').slice(0, maxLength)
  }
  if (typeof value === 'object') {
    const record = value as Record<string, unknown>
    const priority = ['title', 'summary', 'message', 'problem', 'suggestion', 'reason', 'description', 'content', 'text']
    const picked = priority.map(key => normalizeText(record[key], maxLength)).find(Boolean)
    if (picked) return picked
    try {
      return JSON.stringify(value).slice(0, maxLength)
    } catch {
      return String(value).slice(0, maxLength)
    }
  }
  const text = String(value).replace(/\s+/g, ' ').trim()
  return text.length > maxLength ? `${text.slice(0, maxLength)}...` : text
}

function firstText(record: Record<string, any>, keys: string[], maxLength = 420): string {
  for (const key of keys) {
    const text = normalizeText(record[key], maxLength)
    if (text) return text
  }
  return ''
}

function inferKind(stage: string, level: string, message: string, metadata: Record<string, any>) {
  const text = `${stage} ${level} ${message} ${JSON.stringify(metadata).slice(0, 500)}`.toLowerCase()
  // 下面的中文关键词来自后端日志文本，是数据匹配，不随界面语言变化
  if (level === 'error' || /失败|error|failed/.test(text)) return 'error'
  if (/草稿|正文|片段|content|draft|preview/.test(text)) return 'content'
  if (/评审|质量|quality|review|blocker|warning/.test(text)) return 'review'
  if (/连续|一致|伏笔|线索|角色状态|continuity|foreshadow|clue/.test(text)) return 'continuity'
  if (/补丁|局部|优化|patch|optimiz/.test(text)) return 'patch'
  if (/保存|落库|候选|version|persist|final/.test(text)) return 'save'
  return 'status'
}

function kindLabel(kind?: string) {
  const map: Record<string, () => string> = {
    status: () => pick('状态', 'Status'),
    content: () => pick('正文片段', 'Draft excerpt'),
    review: () => pick('质量检查', 'Quality check'),
    continuity: () => pick('连续性', 'Continuity'),
    patch: () => pick('局部修补', 'Local patch'),
    save: () => pick('保存产物', 'Saved artifact'),
    error: () => pick('异常', 'Error'),
  }
  return map[String(kind || '')]?.() || String(kind || pick('状态', 'Status'))
}

function kindIcon(line: Pick<RuntimeLine, 'kind' | 'level'> | string) {
  const kind = typeof line === 'string' ? line : line.kind
  const level = typeof line === 'string' ? '' : line.level
  if (level === 'error' || kind === 'error') return '⚠'
  const map: Record<string, string> = {
    status: '✦',
    content: '✎',
    review: '◇',
    continuity: '♢',
    patch: '✚',
    save: '✓',
  }
  return map[String(kind || '')] || '•'
}

function briefIcon(line: RuntimeLine) {
  if (line.stateClass === 'state-degraded') return '!'
  if (line.stateClass === 'state-skip') return '↷'
  return kindIcon(line)
}

function buildMetrics(event: Record<string, any>, metadata: Record<string, any>) {
  const source: Record<string, unknown> = {}
  if (event.metrics && typeof event.metrics === 'object') Object.assign(source, event.metrics)
  Object.keys(METRIC_LABELS).forEach(key => {
    if (Object.prototype.hasOwnProperty.call(metadata, key)) source[key] = metadata[key]
    if (Object.prototype.hasOwnProperty.call(event, key)) source[key] = event[key]
  })
  return Object.entries(source)
    .map(([key, value]) => ({ label: METRIC_LABELS[key]?.() || key, value: normalizeText(value, 120) }))
    .filter(item => item.value)
    .slice(0, 8)
}

function asRecord(value: unknown): Record<string, any> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, any> : {}
}

function asArray(value: unknown): any[] {
  return Array.isArray(value) ? value : []
}

function formatNumber(value: unknown): string {
  const number = Number(value)
  if (!Number.isFinite(number)) return normalizeText(value, 80)
  return formatLocaleNumber(number)
}

function formatCost(value: unknown): string {
  const number = Number(value)
  if (!Number.isFinite(number) || number <= 0) return '0'
  return pick(`约 ¥${number.toFixed(number >= 1 ? 2 : 4)}`, `approx. ¥${number.toFixed(number >= 1 ? 2 : 4)}`)
}

function buildProviderAdvice(preflight: Record<string, any>) {
  if (!preflight || !Object.keys(preflight).length) return ''
  if (preflight.auto_switched) {
    const from = preflight.current_profile_name || pick('原 Provider', 'the previous provider')
    const to = preflight.active_profile_name || preflight.recommended_profile_name || pick('可用 Provider', 'an available provider')
    return pick(
      `已从 ${from} 切到 ${to}，继续生成。`,
      `Switched from ${from} to ${to} and continued generating.`,
    )
  }
  if (preflight.checked === false && preflight.reason === 'single_profile_locked_skip_preflight') {
    const only = preflight.active_profile_name || preflight.current_profile_name || pick('未命名配置', 'an unnamed profile')
    return pick(
      `当前只有一个启用 Provider：${only}，已跳过切换预检。`,
      `Only one provider is enabled (${only}), so the switch preflight was skipped.`,
    )
  }
  if (preflight.reason === 'preflight_error') {
    return pick(
      `预检失败但未阻断生成，后续调用会继续使用运行时重试和降级：${normalizeText(preflight.error, 160)}`,
      `Preflight failed without blocking generation; later calls keep using runtime retries and fallbacks: ${normalizeText(preflight.error, 160)}`,
    )
  }
  if (preflight.has_usable_profile === false) {
    return pick(
      '未找到可用 Provider，需在设置页修复 Key、额度或 base_url。',
      'No usable provider was found. Fix the key, quota, or base_url on the settings page.',
    )
  }
  if (preflight.checked) {
    const active = preflight.active_profile_name || preflight.current_profile_name || pick('未命名配置', 'an unnamed profile')
    return pick(
      `预检完成，当前可用 Provider 为 ${active}。`,
      `Preflight finished; the usable provider is ${active}.`,
    )
  }
  return pick('Provider 预检信息已记录。', 'Provider preflight details were recorded.')
}

function normalizeArtifactRefs(value: unknown): string[] {
  if (!value) return []
  const items = Array.isArray(value) ? value : [value]
  return items.map(item => normalizeText(item, 160)).filter(Boolean).slice(0, 6)
}

function enrichRuntimeLine(raw: RuntimeLine): RuntimeLine {
  const metadata = raw.metadata && typeof raw.metadata === 'object' ? raw.metadata : {}
  const kind = String(raw.kind || metadata.kind || inferKind(String(raw.stage || ''), String(raw.level || ''), raw.message, metadata))
  const title = firstText(
    { ...metadata, title: raw.title, message: raw.message },
    ['title', 'display_title', 'message'],
    180,
  ) || pick('生成状态更新', 'Generation status update')
  const summary = firstText(
    { ...metadata, summary: raw.summary },
    ['summary', 'reason', 'decision', 'progress_message', 'message'],
    320,
  )
  const contentPreview = raw.contentPreview || firstText(
    { ...metadata },
    PREVIEW_KEYS,
    900,
  )
  const artifactSource = raw.artifactRefs?.length ? raw.artifactRefs : normalizeArtifactRefs(raw.metadata?.artifact_refs || raw.metadata?.artifacts)
  return {
    ...raw,
    kind,
    title,
    summary,
    contentPreview,
    metrics: raw.metrics?.length ? raw.metrics : buildMetrics({ ...raw }, metadata),
    artifactRefs: artifactSource,
  }
}

function buildSyntheticBackendLines(chapter: ChapterRuntimeLogItem) {
  const runtime = chapter.runtime_snapshot || {}
  const lines: RuntimeLine[] = []
  const timestamp = chapter.updated_at || chapter.started_at || new Date().toISOString()
  const providerPreflight = asRecord(runtime.provider_preflight)
  const tokenBudgetUsage = asRecord(runtime.token_budget_usage)
  const longformContext = asRecord(runtime.longform_context)
  const castPlan = asRecord(longformContext.cast_plan)
  const foreshadowingTask = asRecord(longformContext.foreshadowing_task)
  const draftContract = asRecord(runtime.chapter_draft_contract)
  const generationLimits = asRecord(runtime.chapter_generation_limits)

  if (Object.keys(providerPreflight).length) {
    const providerWarning = providerPreflight.reason === 'preflight_error' || providerPreflight.has_usable_profile === false
    const title = providerPreflight.auto_switched
      ? pick('Provider 已自动切换', 'Provider switched automatically')
      : providerWarning
        ? pick('Provider 预检需要关注', 'Provider preflight needs attention')
        : providerPreflight.checked
          ? pick('Provider 预检完成', 'Provider preflight finished')
          : pick('Provider 预检已记录', 'Provider preflight recorded')
    lines.push({
      at: chapter.started_at || timestamp,
      stage: 'provider_preflight',
      level: providerWarning ? 'warning' : 'info',
      kind: providerWarning ? 'error' : 'status',
      title,
      summary: buildProviderAdvice(providerPreflight),
      contentPreview: '',
      metrics: buildMetrics(
        {
          active_profile_name: providerPreflight.active_profile_name,
          recommended_profile_name: providerPreflight.recommended_profile_name,
        },
        providerPreflight,
      ),
      artifactRefs: [],
      message: title,
      metadata: providerPreflight,
      stateLabel: providerPreflight.auto_switched
        ? pick('已切换', 'Switched')
        : providerWarning
          ? pick('需关注', 'Needs attention')
          : pick('已记录', 'Recorded'),
      stateClass: providerWarning ? 'state-degraded' : '',
      // 预检完成（非切换、非告警）才算关键阶段节点，与改造前的行为一致
      brief: Boolean(providerPreflight.checked) && !providerPreflight.auto_switched && !providerWarning,
      syntheticKey: 'provider-preflight',
    })
  }

  if (Object.keys(draftContract).length || Object.keys(generationLimits).length) {
    const tier = normalizeText(draftContract.tier || draftContract.label || draftContract.mode, 80)
    lines.push({
      at: chapter.started_at || timestamp,
      stage: 'chapter_draft_contract',
      level: 'info',
      kind: 'status',
      title: pick('正文长度契约已生效', 'Draft length contract active'),
      summary: tier
        ? pick(
            `本章按“${tier}”策略生成：内部可用场景组规划，但最终仍输出连贯整章。`,
            `This chapter follows the “${tier}” strategy: scene groups may be planned internally, but the output stays one coherent chapter.`,
          )
        : pick(
            '本章已记录目标字数、最低字数、超时和 max_tokens，用于首稿质量门与失败归因。',
            'Target words, minimum words, timeout, and max_tokens are recorded for the first-draft quality gate and failure attribution.',
          ),
      contentPreview: '',
      metrics: buildMetrics(
        {
          target_word_count: runtime.target_word_count,
          min_word_count: runtime.min_word_count,
          timeout_seconds: generationLimits.timeout_seconds,
          max_tokens: generationLimits.max_tokens,
        },
        { ...draftContract, ...generationLimits },
      ),
      artifactRefs: [],
      message: pick('正文长度契约已生效', 'Draft length contract active'),
      metadata: { chapter_draft_contract: draftContract, chapter_generation_limits: generationLimits },
      brief: false,
      syntheticKey: 'chapter-draft-contract',
    })
  }

  if (Object.keys(longformContext).length) {
    const focusNames = asArray(castPlan.chapter_focus_names).map(item => normalizeText(item, 80)).filter(Boolean)
    const mustResolve = asArray(foreshadowingTask.must_resolve)
    const shouldReinforce = asArray(foreshadowingTask.should_reinforce)
    const avoidForgetting = asArray(foreshadowingTask.avoid_forgetting)
    const activeClues = asArray(foreshadowingTask.active_clues)
    lines.push({
      at: chapter.started_at || timestamp,
      stage: 'longform_context',
      level: 'info',
      kind: 'continuity',
      title: pick('长期上下文已装配', 'Long-form context assembled'),
      summary: [
        focusNames.length
          ? pick(`本章关注角色：${focusNames.slice(0, 5).join('、')}`, `Focus characters: ${focusNames.slice(0, 5).join(', ')}`)
          : '',
        mustResolve.length
          ? pick(`必须回收 ${mustResolve.length} 个伏笔/线索`, `${mustResolve.length} setups/clues must be resolved`)
          : '',
        shouldReinforce.length
          ? pick(`应强化 ${shouldReinforce.length} 个伏笔/线索`, `${shouldReinforce.length} setups/clues should be reinforced`)
          : '',
        avoidForgetting.length
          ? pick(`禁忘 ${avoidForgetting.length} 个长期信息`, `${avoidForgetting.length} long-term facts must not be dropped`)
          : '',
      ].filter(Boolean).join(pick('；', '; ')) || pick(
        '已注入角色状态、伏笔/线索账本、记忆摘要、时间线和知识图谱摘要。',
        'Character states, the setup/clue ledger, memory digest, timeline, and knowledge-graph digest were all injected.',
      ),
      contentPreview: normalizeText([
        ...mustResolve.slice(0, 3),
        ...shouldReinforce.slice(0, 2),
      ], 520),
      metrics: buildMetrics(
        {
          planned_character_count: castPlan.planned_character_count,
          target_character_count: castPlan.target_character_count,
          must_resolve_count: mustResolve.length,
          should_reinforce_count: shouldReinforce.length,
          avoid_forgetting_count: avoidForgetting.length,
          active_clue_count: activeClues.length,
        },
        {},
      ),
      artifactRefs: [],
      message: pick('长期上下文已装配', 'Long-form context assembled'),
      metadata: {
        cast_plan: castPlan,
        foreshadowing_task: foreshadowingTask,
        memory_digest: longformContext.memory_digest,
        timeline_digest: longformContext.timeline_digest,
        knowledge_digest: longformContext.knowledge_digest,
      },
      brief: false,
      syntheticKey: 'longform-context',
    })
  }

  if (runtime.review_status === 'skipped_single_version') {
    lines.push({
      at: timestamp,
      stage: 'review',
      level: 'warning',
      kind: 'review',
      title: pick('AI 评审已跳过', 'AI review skipped'),
      summary: pick(
        '当前只有 1 个候选版本，无法执行版本对比评审。',
        'There is only one candidate version, so a comparative review cannot run.',
      ),
      contentPreview: '',
      metrics: [],
      artifactRefs: [],
      message: pick(
        'AI 评审已跳过：当前只有 1 个候选版本，无法执行版本对比评审。',
        'AI review skipped: there is only one candidate version, so a comparative review cannot run.',
      ),
      metadata: {
        review_status: runtime.review_status,
        review_skip_reason: runtime.review_skip_reason || 'single_version',
      },
      stateLabel: pick('已跳过', 'Skipped'),
      stateClass: 'state-skip',
      brief: true,
    })
  }

  const degradedStages = Array.isArray(runtime.degraded_stages) ? runtime.degraded_stages : []
  degradedStages.forEach((item, index) => {
    const stage = String(item?.stage || 'unknown')
    lines.push({
      at: timestamp,
      stage,
      level: 'warning',
      kind: 'error',
      title: pick(`${normalizeStageLabel(stage)}降级失败`, `${normalizeStageLabel(stage)} degraded`),
      summary: pick(
        '本步骤未正常完成，系统跳过后继续执行后续流程。',
        'This step did not finish normally; the pipeline skipped it and continued.',
      ),
      contentPreview: '',
      metrics: [],
      artifactRefs: [],
      message: pick(
        `${normalizeStageLabel(stage)}已降级失败：本步骤未正常完成，系统跳过后继续执行后续流程。`,
        `${normalizeStageLabel(stage)} degraded: this step did not finish normally; the pipeline skipped it and continued.`,
      ),
      metadata: {
        degraded_stage: stage,
        degraded_reason: item?.reason || pick('未记录原因', 'No reason recorded'),
      },
      stateLabel: pick('降级失败', 'Degraded'),
      stateClass: 'state-degraded',
      brief: true,
      syntheticKey: `${stage}-${index}`,
    })
  })

  if (Object.keys(tokenBudgetUsage).length) {
    const hasError = Boolean(tokenBudgetUsage.error)
    const recordCount = Number(tokenBudgetUsage.record_count || 0)
    const totalTokens = Number(tokenBudgetUsage.total_tokens || 0)
    lines.push({
      at: timestamp,
      stage: 'token_budget',
      level: hasError ? 'warning' : 'info',
      kind: hasError ? 'error' : 'save',
      title: hasError
        ? pick('Token 预算记录失败', 'Token budget recording failed')
        : (recordCount > 0
            ? pick('Token 预算已记录', 'Token budget recorded')
            : pick('Token 预算无需记录', 'No token budget to record')),
      summary: hasError
        ? pick(
            `预算入账未成功，但章节生成结果已保留：${normalizeText(tokenBudgetUsage.error, 180)}`,
            `Budget accounting failed, but the chapter output was kept: ${normalizeText(tokenBudgetUsage.error, 180)}`,
          )
        : recordCount > 0
          ? pick(
              `已把本章候选生成的估算消耗写入预算账本：${formatNumber(totalTokens)} token，${formatCost(tokenBudgetUsage.estimated_cost)}。`,
              `Estimated usage for this chapter's candidates was written to the budget ledger: ${formatNumber(totalTokens)} tokens, ${formatCost(tokenBudgetUsage.estimated_cost)}.`,
            )
          : pick(
              '本章候选没有可估算的生成调用 token，因此没有新增预算记录。',
              'No estimable generation tokens for this chapter, so no budget record was added.',
            ),
      contentPreview: '',
      metrics: buildMetrics(
        {
          record_count: tokenBudgetUsage.record_count,
          total_tokens: tokenBudgetUsage.total_tokens,
          estimated_cost: formatCost(tokenBudgetUsage.estimated_cost),
          module: tokenBudgetUsage.module,
        },
        tokenBudgetUsage,
      ),
      artifactRefs: normalizeArtifactRefs(tokenBudgetUsage.usage_ids),
      message: pick('Token 预算已同步到生成日志', 'Token budget synced to the generation log'),
      metadata: tokenBudgetUsage,
      stateLabel: hasError ? pick('需关注', 'Needs attention') : pick('已入账', 'Recorded'),
      stateClass: hasError ? 'state-degraded' : '',
      brief: false,
      syntheticKey: 'token-budget',
    })
  }

  return lines
}

function normalizeEvents(events: Array<Record<string, any>>): RuntimeLine[] {
  const sortedEvents = [...events]
    .map(event => {
      const rawMessage = String(event.message || '')
      // 降级/跳过状态用内部枚举承载，展示文案与配色都从它派生，翻译后不会失配
      const degradedKind: '' | 'skip' | 'degraded' = event.level === 'warning' && /降级|跳过/i.test(rawMessage)
        ? (/跳过/i.test(rawMessage) ? 'skip' : 'degraded')
        : ''
      const stage = String(event.stage || '')
      return {
        at: event.at,
        stage: event.stage,
        level: event.level || 'info',
        kind: String(event.kind || ''),
        title: String(event.title || ''),
        summary: String(event.summary || ''),
        contentPreview: String(event.content_preview || ''),
        metrics: [],
        artifactRefs: normalizeArtifactRefs(event.artifact_refs),
        message: rawMessage,
        metadata: {
          ...(event.metadata && typeof event.metadata === 'object' ? event.metadata : {}),
          ...(event.developer_detail && typeof event.developer_detail === 'object'
            ? { developer_detail: event.developer_detail }
            : {}),
        },
        stateLabel: degradedKind === 'skip'
          ? pick('已跳过', 'Skipped')
          : degradedKind === 'degraded'
            ? pick('降级失败', 'Degraded')
            : '',
        stateClass: degradedKind === 'skip'
          ? 'state-skip'
          : degradedKind === 'degraded'
            ? 'state-degraded'
            : '',
        brief: isBriefWorthyEvent(stage, rawMessage, degradedKind),
      }
    })
    .sort((a, b) => String(a.at || '').localeCompare(String(b.at || '')))

  let previousAt: number | null = null
  let firstAt: number | null = null
  return sortedEvents.map((event) => {
    const currentAt = event.at ? new Date(event.at).getTime() : NaN
    const validCurrentAt = Number.isNaN(currentAt) ? null : currentAt
    if (firstAt === null && validCurrentAt !== null) firstAt = validCurrentAt
    const stepDurationMs = previousAt !== null && validCurrentAt !== null ? Math.max(0, validCurrentAt - previousAt) : null
    const totalDurationMs = firstAt !== null && validCurrentAt !== null ? Math.max(0, validCurrentAt - firstAt) : null
    if (validCurrentAt !== null) previousAt = validCurrentAt
    return enrichRuntimeLine({
      ...event,
      stepDurationMs,
      totalDurationMs,
    })
  })
}

function patchSuggestions(line: RuntimeLine): string[] {
  const metadata = line.metadata || {}
  const values = PATCH_KEYS.flatMap(key => {
    const value = metadata[key]
    if (!value) return []
    return Array.isArray(value) ? value : [value]
  })
  return values
    .map(value => normalizeText(value, 260))
    .filter(Boolean)
    .slice(0, 5)
}

function artifactRefs(line: RuntimeLine): string[] {
  return line.artifactRefs?.length ? line.artifactRefs : normalizeArtifactRefs(line.metadata?.artifact_refs || line.metadata?.artifacts)
}

function syncSelection() {
  const firstProject = visibleProjects.value[0]
  if (!firstProject) {
    selectedProjectId.value = null
    selectedChapterNumber.value = null
    return
  }
  if (!selectedProjectId.value || !visibleProjects.value.some(project => project.project_id === selectedProjectId.value)) selectedProjectId.value = firstProject.project_id
  const chapterFromQuery = Number(route.query.chapter)
  const currentProject = selectedProject.value
  if (currentProject) {
    const preferredChapter = Number.isFinite(chapterFromQuery) && currentProject.chapters.some(ch => ch.chapter_number === chapterFromQuery) ? chapterFromQuery : (currentProject.active_chapter || currentProject.chapters[0]?.chapter_number)
    if (!selectedChapterNumber.value || !currentProject.chapters.some(ch => ch.chapter_number === selectedChapterNumber.value)) selectedChapterNumber.value = preferredChapter || null
  }
}

function selectProject(projectId: string) {
  selectedProjectId.value = projectId
  selectedChapterNumber.value = null
  syncSelection()
}

function clearFocus() {
  router.replace({ name: 'admin', query: { tab: 'runtime-logs' } })
}

function isBackendConsoleNearBottom() {
  const element = backendConsoleRef.value
  if (!element) return true
  return element.scrollHeight - element.scrollTop - element.clientHeight < 72
}

async function restoreBackendConsoleScroll(shouldStickBottom: boolean) {
  await nextTick()
  const element = backendConsoleRef.value
  if (!element || !shouldStickBottom) return
  element.scrollTop = element.scrollHeight
}

async function fetchLogs(options: { silent?: boolean } = {}) {
  const { silent = false } = options
  const shouldStickBottom = isBackendConsoleNearBottom()
  if (!silent) loading.value = true
  else refreshing.value = true
  error.value = null
  try {
    projects.value = await AdminAPI.listRuntimeLogs()
    syncSelection()
    await restoreBackendConsoleScroll(shouldStickBottom)
  } catch (err) {
    error.value = err instanceof Error ? err.message : pick('获取运行日志失败', 'Failed to load the runtime logs')
  } finally {
    if (!silent) loading.value = false
    else refreshing.value = false
  }
}

function refreshNow() {
  void fetchLogs()
}

function startAutoRefresh() {
  if (refreshTimer) return
  refreshTimer = window.setInterval(() => {
    if (autoRefresh.value && !loading.value && !refreshing.value) void fetchLogs({ silent: true })
  }, 15000)  // 降低轮询频率，减轻后端压力
}

function stopAutoRefresh() {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

const formatDateTime = (value?: string | null) => {
  if (!value) return pick('未记录', 'Not recorded')
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}:${String(date.getSeconds()).padStart(2, '0')}`
}
const tagTypeByStatus = (status: string) => ['failed', 'evaluation_failed'].includes(status) ? 'error' : ['waiting_for_confirm', 'successful'].includes(status) ? 'success' : ['generating', 'evaluating', 'selecting'].includes(status) ? 'warning' : 'default'
const formatLevelCode = (level: unknown) => level === 'warning' ? 'WARN' : level === 'error' ? 'ERROR' : 'INFO'
const formatJson = (value: Record<string, any>) => JSON.stringify(value, null, 2)
const formatDuration = (value?: number | null) => {
  if (value == null || !Number.isFinite(value) || value <= 0) return ''
  if (value < 1000) return `${Math.round(value)} ms`
  const totalSeconds = Math.floor(value / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return minutes > 0
    ? pick(`${minutes} 分 ${seconds} 秒`, `${minutes} min ${seconds} s`)
    : pick(`${seconds} 秒`, `${seconds} s`)
}
const buildSummaryEntries = (chapter: ChapterRuntimeLogItem) => {
  const runtime = chapter.runtime_snapshot || {}
  const preflight = asRecord(runtime.provider_preflight)
  const budget = asRecord(runtime.token_budget_usage)
  const context = asRecord(runtime.longform_context)
  const castPlan = asRecord(context.cast_plan)
  const foreshadowingTask = asRecord(context.foreshadowing_task)
  const foreshadowingCount =
    asArray(foreshadowingTask.must_resolve).length +
    asArray(foreshadowingTask.should_reinforce).length +
    asArray(foreshadowingTask.avoid_forgetting).length
  const notRecorded = pick('未记录', 'Not recorded')
  return [
    { label: pick('开始时间', 'Started at'), value: formatDateTime(chapter.started_at) },
    { label: pick('最近更新', 'Last updated'), value: formatDateTime(chapter.updated_at) },
    { label: pick('当前阶段', 'Current stage'), value: chapter.progress_stage || notRecorded },
    { label: pick('评审状态', 'Review status'), value: chapter.summary_snapshot.review_status || notRecorded },
    { label: pick('目标字数', 'Target words'), value: chapter.summary_snapshot.target_word_count || notRecorded },
    { label: pick('实际字数', 'Actual words'), value: chapter.summary_snapshot.actual_word_count || chapter.word_count || notRecorded },
    { label: pick('总耗时', 'Total duration'), value: chapter.summary_snapshot.pipeline_total_duration_ms ? formatDuration(chapter.summary_snapshot.pipeline_total_duration_ms) : notRecorded },
    { label: 'Provider', value: preflight.active_profile_name || preflight.current_profile_name || preflight.reason || notRecorded },
    { label: pick('Token预算', 'Token budget'), value: budget.total_tokens ? `${formatNumber(budget.total_tokens)} token / ${formatCost(budget.estimated_cost)}` : notRecorded },
    { label: pick('角色上下文', 'Character context'), value: castPlan.planned_character_count
      ? pick(
          `${castPlan.planned_character_count} 人计划 / ${asArray(castPlan.chapter_focus_names).length} 人聚焦`,
          `${castPlan.planned_character_count} planned / ${asArray(castPlan.chapter_focus_names).length} in focus`,
        )
      : notRecorded },
    { label: pick('伏笔任务', 'Setup tasks'), value: foreshadowingCount ? pick(`${foreshadowingCount} 项`, `${foreshadowingCount} items`) : notRecorded },
    { label: pick('最后错误', 'Last error'), value: chapter.summary_snapshot.last_error_summary || pick('无', 'None') },
  ]
}

watch(autoRefresh, enabled => {
  if (enabled) {
    startAutoRefresh()
    void fetchLogs({ silent: true })
  }
})
watch(() => [route.query.project_id, route.query.chapter], syncSelection)
watch(selectedChapterNumber, () => {
  briefExpanded.value = false
})
onMounted(() => {
  void fetchLogs()
  startAutoRefresh()
})
onBeforeUnmount(stopAutoRefresh)
</script>

<style scoped>
.runtime-card { width: 100%; }
.runtime-card__header, .brief-panel__header { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; flex-wrap:wrap; }
.runtime-card__title { font-size:1.25rem; font-weight:800; color:#0f172a; }
.runtime-card__subtitle { margin-top:6px; color:#64748b; font-size:.92rem; }
.runtime-layout { display:grid; grid-template-columns: 280px minmax(0,1fr); gap:16px; }
.project-rail { display:grid; align-content:start; gap:10px; }
.project-rail__item { text-align:left; border:1px solid #e2e8f0; border-radius:16px; background:#fff; padding:14px; cursor:pointer; }
.project-rail__item strong, .project-rail__item span { display:block; }
.project-rail__item span { margin-top:6px; color:#64748b; font-size:12px; }
.project-rail__item--active { border-color:#6366f1; background:#eef2ff; }
.runtime-main { min-width:0; display:grid; gap:14px; }
.runtime-main__head { display:flex; justify-content:space-between; gap:12px; align-items:flex-start; flex-wrap:wrap; border:1px solid #e2e8f0; border-radius:20px; background:#fff; padding:16px; }
.runtime-main__head h3 { margin:0; font-size:1.15rem; font-weight:800; color:#0f172a; }
.runtime-main__head p { margin:6px 0 0; color:#64748b; }
.runtime-main__head-tags { display:flex; gap:8px; flex-wrap:wrap; }
.chapter-switcher { display:flex; gap:8px; overflow:auto; padding-bottom:2px; }
.chapter-switcher button { border:1px solid #cbd5e1; background:#fff; border-radius:999px; padding:8px 12px; white-space:nowrap; cursor:pointer; }
.chapter-switcher button.active { background:#0f172a; color:#fff; border-color:#0f172a; }
.runtime-content { display:grid; grid-template-columns: 360px minmax(0,1fr); gap:16px; }
.brief-panel, .backend-panel { border:1px solid #e2e8f0; border-radius:20px; padding:16px; background:#fff; }
.section-title { font-size:1rem; font-weight:800; color:#0f172a; margin-bottom:10px; }
.section-title--small { font-size:.88rem; margin-bottom:8px; }
.brief-panel__tip, .backend-panel__tip { margin:0 0 12px; color:#64748b; line-height:1.7; font-size:.88rem; }
.brief-log-list { list-style:none; margin:0; padding:0; display:grid; gap:10px; max-height:740px; overflow:auto; }
.brief-log-item { display:grid; gap:6px; padding:12px; border-radius:14px; background:#f8fafc; border:1px solid #e2e8f0; }
.brief-log-item__top, .brief-log-item__meta { display:flex; align-items:center; justify-content:space-between; gap:8px; flex-wrap:wrap; }
.brief-log-item__time { display:inline-flex; align-items:center; gap:6px; color:#64748b; font-size:.75rem; }
.brief-log-item__icon { display:inline-flex; align-items:center; justify-content:center; width:20px; height:20px; border-radius:999px; background:#e0f2fe; color:#0369a1; font-weight:900; }
.brief-log-item__badge, .backend-line__badge { display:inline-flex; align-items:center; min-height:22px; padding:0 8px; border-radius:999px; font-size:.72rem; font-weight:800; }
.state-skip { background:rgba(14, 165, 233, .16); color:#1d4ed8; }
.state-degraded { background:rgba(239, 68, 68, .16); color:#b91c1c; }
.brief-log-item strong { color:#0f172a; line-height:1.55; }
.brief-log-item__summary { margin:0; color:#475569; line-height:1.55; font-size:.82rem; }
.brief-log-item small { color:#475569; }
.brief-summary { margin-top:14px; padding-top:14px; border-top:1px solid #e2e8f0; }
.summary-grid { display:grid; grid-template-columns:88px minmax(0,1fr); gap:8px 12px; margin:0; }
.summary-grid dt { color:#64748b; }
.summary-grid dd { margin:0; color:#0f172a; word-break:break-word; }
.backend-panel { background:#0b1220; color:#e2e8f0; }
.backend-panel .section-title { color:#fff; }
.backend-console { max-height:720px; overflow:auto; border-radius:16px; background:#020617; padding:14px; display:grid; gap:10px; }
.backend-line { padding:10px 12px; border-radius:12px; border:1px solid #1e293b; background:#0f172a; }
.backend-line__meta { display:flex; gap:8px; flex-wrap:wrap; color:#94a3b8; font-size:.78rem; margin-bottom:6px; }
.backend-line__kind { color:#fde68a; font-weight:800; }
.backend-line__message { color:#e2e8f0; line-height:1.6; white-space:pre-wrap; }
.backend-line__summary { margin:4px 0 0; color:#cbd5e1; line-height:1.65; font-size:.86rem; }
.metric-chips, .artifact-refs { display:flex; flex-wrap:wrap; gap:8px; margin-top:10px; }
.metric-chip { display:inline-flex; align-items:center; gap:6px; min-height:26px; padding:0 9px; border-radius:999px; background:#172554; color:#dbeafe; font-size:.76rem; }
.metric-chip strong { color:#bfdbfe; }
.content-preview, .patch-suggestions, .artifact-refs { margin-top:10px; border:1px solid #1e293b; border-radius:12px; background:#08111f; padding:10px 12px; }
.content-preview span, .patch-suggestions span, .artifact-refs > span { display:block; margin-bottom:6px; color:#a7f3d0; font-size:.76rem; font-weight:800; }
.content-preview p { margin:0; color:#e0f2fe; line-height:1.7; white-space:pre-wrap; }
.patch-suggestions ul { margin:0; padding-left:18px; color:#fee2e2; display:grid; gap:6px; line-height:1.65; }
.artifact-refs code { display:inline-flex; max-width:100%; padding:4px 7px; border-radius:8px; background:#020617; color:#bae6fd; word-break:break-all; }
.developer-details { margin-top:10px; }
.developer-details summary, .backend-snapshot summary { cursor:pointer; color:#93c5fd; font-size:.78rem; font-weight:800; }
.developer-details pre, .backend-snapshot pre { margin:8px 0 0; padding:10px 12px; border-radius:12px; background:#000814; color:#bae6fd; white-space:pre-wrap; word-break:break-word; font-size:.78rem; }
.backend-snapshot { margin-top:8px; padding-top:8px; border-top:1px solid #1e293b; }
.backend-snapshot__title { color:#93c5fd; font-size:.82rem; font-weight:800; }
@media (max-width: 1120px) { .runtime-layout, .runtime-content { grid-template-columns:1fr; } }
</style>
