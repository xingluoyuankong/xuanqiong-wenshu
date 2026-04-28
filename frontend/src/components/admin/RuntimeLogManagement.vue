<template>
  <n-card :bordered="false" class="runtime-card">
    <template #header>
      <div class="runtime-card__header">
        <div>
          <span class="runtime-card__title">运行日志</span>
          <p class="runtime-card__subtitle">左边简略日志显示全部关键阶段，并补充每步用时；右边直接显示后台流水。</p>
        </div>
        <n-space>
          <n-button tertiary size="small" @click="refreshNow" :loading="loading">刷新</n-button>
          <n-button tertiary size="small" @click="autoRefresh = !autoRefresh">{{ autoRefresh ? '停止自动刷新' : '开启自动刷新' }}</n-button>
        </n-space>
      </div>
    </template>

    <n-space vertical size="large">
      <n-alert v-if="error" type="error" closable @close="error = null">{{ error }}</n-alert>
      <n-alert v-if="focusedProjectId" type="info" :bordered="false">当前已从小说入口定位到：{{ focusedProjectTitle }}。<n-button text type="primary" @click="clearFocus">查看全部</n-button></n-alert>

      <n-spin :show="loading">
        <n-empty v-if="!visibleProjects.length && !loading" description="暂无可展示的运行日志" />

        <div v-else class="runtime-layout">
          <aside class="project-rail">
            <button v-for="project in visibleProjects" :key="project.project_id" class="project-rail__item" :class="{ 'project-rail__item--active': selectedProjectId === project.project_id }" @click="selectProject(project.project_id)">
              <strong>{{ project.project_title }}</strong>
              <span>{{ project.chapters.length }} 章 · {{ formatDateTime(project.updated_at) }}</span>
            </button>
          </aside>

          <section v-if="selectedProject && selectedChapter" class="runtime-main">
            <div class="runtime-main__head">
              <div>
                <h3>{{ selectedProject.project_title }}</h3>
                <p>项目 ID：{{ selectedProject.project_id }} · 最近更新：{{ formatDateTime(selectedProject.updated_at) }}</p>
              </div>
              <div class="runtime-main__head-tags">
                <n-tag type="primary" round>第 {{ selectedChapter.chapter_number }} 章</n-tag>
                <n-tag size="small" :type="tagTypeByStatus(selectedChapter.generation_status)" round>{{ selectedChapter.generation_status }}</n-tag>
              </div>
            </div>

            <div class="chapter-switcher">
              <button v-for="chapter in selectedProject.chapters" :key="chapter.chapter_number" :class="{ active: selectedChapterNumber === chapter.chapter_number }" @click="selectedChapterNumber = chapter.chapter_number">第 {{ chapter.chapter_number }} 章</button>
            </div>

            <div class="runtime-content">
              <aside class="brief-panel">
                <div class="brief-panel__header">
                  <div>
                    <div class="section-title">简略日志</div>
                    <p class="brief-panel__tip">显示全部关键阶段节点，并补充“本步用时 / 累计用时”。</p>
                  </div>
                  <n-button text type="primary" @click="briefExpanded = !briefExpanded">
                    {{ briefExpanded ? '收起列表' : `显示全部（${briefLogs.length} 条）` }}
                  </n-button>
                </div>

                <ul v-if="visibleBriefLogs.length" class="brief-log-list">
                  <li v-for="(item, index) in visibleBriefLogs" :key="`${item.at || 'brief'}-${index}`" class="brief-log-item">
                    <div class="brief-log-item__top">
                      <span class="brief-log-item__time">{{ formatDateTime(item.at) }}</span>
                      <span v-if="item.stateLabel" class="brief-log-item__badge" :class="item.stateClass">{{ item.stateLabel }}</span>
                    </div>
                    <strong>{{ item.message }}</strong>
                    <div class="brief-log-item__meta">
                      <small v-if="item.stage">{{ item.stage }}</small>
                      <small v-if="item.stepDurationLabel">本步用时：{{ item.stepDurationLabel }}</small>
                      <small v-if="item.totalDurationLabel">累计：{{ item.totalDurationLabel }}</small>
                    </div>
                  </li>
                </ul>
                <n-empty v-else size="small" description="当前没有可归纳的关键阶段日志" />

                <div class="brief-summary">
                  <div class="section-title section-title--small">摘要参数</div>
                  <dl class="summary-grid">
                    <template v-for="item in buildSummaryEntries(selectedChapter)" :key="item.label"><dt>{{ item.label }}</dt><dd>{{ item.value }}</dd></template>
                  </dl>
                </div>
              </aside>

              <section class="backend-panel">
                <div class="section-title">详细后台运行日志</div>
                <p class="backend-panel__tip">这里直接按后台流水显示：时间、阶段、级别、消息、metadata、runtime snapshot。</p>
                <div ref="backendConsoleRef" class="backend-console">
                  <div v-for="(line, index) in backendLines" :key="`${line.at || 'line'}-${index}`" class="backend-line">
                    <div class="backend-line__meta">
                      <span>{{ formatDateTime(line.at) }}</span>
                      <span>[{{ formatLevelCode(line.level) }}]</span>
                      <span v-if="line.stage">[{{ line.stage }}]</span>
                      <span v-if="line.stateLabel" class="backend-line__badge" :class="line.stateClass">{{ line.stateLabel }}</span>
                    </div>
                    <div class="backend-line__message">{{ line.message || '后台状态更新' }}</div>
                    <pre v-if="line.metadata && Object.keys(line.metadata).length" class="backend-line__extra">{{ formatJson(line.metadata) }}</pre>
                  </div>

                  <div v-if="runtimeSnapshotText" class="backend-snapshot">
                    <div class="backend-snapshot__title">runtime snapshot</div>
                    <pre>{{ runtimeSnapshotText }}</pre>
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

type RuntimeLine = {
  at?: string | null
  stage?: string
  level?: string
  message: string
  metadata: Record<string, any>
  stateLabel?: string
  stateClass?: string
  syntheticKey?: string
  stepDurationMs?: number | null
  totalDurationMs?: number | null
}

const route = useRoute()
const router = useRouter()
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
  const events = backendLines.value.filter(event => event.message && shouldShowAsBriefLog(event.message, String(event.stage || ''), event.stateLabel))
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

function shouldShowAsBriefLog(message: string, stage: string, stateLabel?: string) {
  const text = `${stage} ${message} ${stateLabel || ''}`
  return /候选版本|阶段完成|等待确认|正在调用模型|正在写入|开始|完成|失败|评估|优化|补字数|落库|一致性|诊断/i.test(text)
}

function normalizeStageLabel(stage: string) {
  const map: Record<string, string> = {
    review: '评审阶段',
    ai_review: 'AI 评审',
    optimize_content: '分阶段优化',
    consistency: '一致性校验',
    persist_versions: '候选版本落库',
    waiting_for_confirm: '等待确认',
  }
  return map[stage] || stage || '未知阶段'
}

function buildSyntheticBackendLines(chapter: ChapterRuntimeLogItem) {
  const runtime = chapter.runtime_snapshot || {}
  const lines: RuntimeLine[] = []
  const timestamp = chapter.updated_at || chapter.started_at || new Date().toISOString()

  if (runtime.review_status === 'skipped_single_version') {
    lines.push({
      at: timestamp,
      stage: 'review',
      level: 'warning',
      message: 'AI 评审已跳过：当前只有 1 个候选版本，无法执行版本对比评审。',
      metadata: {
        review_status: runtime.review_status,
        review_skip_reason: runtime.review_skip_reason || 'single_version',
      },
      stateLabel: '已跳过',
      stateClass: 'state-skip',
    })
  }

  const degradedStages = Array.isArray(runtime.degraded_stages) ? runtime.degraded_stages : []
  degradedStages.forEach((item, index) => {
    const stage = String(item?.stage || 'unknown')
    lines.push({
      at: timestamp,
      stage,
      level: 'warning',
      message: `${normalizeStageLabel(stage)}已降级失败：本步骤未正常完成，系统跳过后继续执行后续流程。`,
      metadata: {
        degraded_stage: stage,
        degraded_reason: item?.reason || '未记录原因',
      },
      stateLabel: '降级失败',
      stateClass: 'state-degraded',
      syntheticKey: `${stage}-${index}`,
    })
  })

  return lines
}

function normalizeEvents(events: Array<Record<string, any>>): RuntimeLine[] {
  const sortedEvents = [...events]
    .map(event => ({
      at: event.at,
      stage: event.stage,
      level: event.level || 'info',
      message: String(event.message || ''),
      metadata: event.metadata && typeof event.metadata === 'object' ? event.metadata : {},
      stateLabel: event.level === 'warning' && /降级|跳过/i.test(String(event.message || ''))
        ? (/跳过/i.test(String(event.message || '')) ? '已跳过' : '降级失败')
        : '',
      stateClass: event.level === 'warning' && /跳过/i.test(String(event.message || ''))
        ? 'state-skip'
        : event.level === 'warning' && /降级/i.test(String(event.message || ''))
          ? 'state-degraded'
          : '',
    }))
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
    return {
      ...event,
      stepDurationMs,
      totalDurationMs,
    }
  })
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
    error.value = err instanceof Error ? err.message : '获取运行日志失败'
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
  }, 5000)
}

function stopAutoRefresh() {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

const formatDateTime = (value?: string | null) => {
  if (!value) return '未记录'
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
  return minutes > 0 ? `${minutes} 分 ${seconds} 秒` : `${seconds} 秒`
}
const buildSummaryEntries = (chapter: ChapterRuntimeLogItem) => [
  { label: '开始时间', value: formatDateTime(chapter.started_at) },
  { label: '最近更新', value: formatDateTime(chapter.updated_at) },
  { label: '当前阶段', value: chapter.progress_stage || '未记录' },
  { label: '评审状态', value: chapter.summary_snapshot.review_status || '未记录' },
  { label: '目标字数', value: chapter.summary_snapshot.target_word_count || '未记录' },
  { label: '实际字数', value: chapter.summary_snapshot.actual_word_count || chapter.word_count || '未记录' },
  { label: '总耗时', value: chapter.summary_snapshot.pipeline_total_duration_ms ? formatDuration(chapter.summary_snapshot.pipeline_total_duration_ms) : '未记录' },
  { label: '最后错误', value: chapter.summary_snapshot.last_error_summary || '无' },
]

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
.brief-log-item__time { color:#64748b; font-size:.75rem; }
.brief-log-item__badge, .backend-line__badge { display:inline-flex; align-items:center; min-height:22px; padding:0 8px; border-radius:999px; font-size:.72rem; font-weight:800; }
.state-skip { background:rgba(245, 158, 11, .16); color:#b45309; }
.state-degraded { background:rgba(239, 68, 68, .16); color:#b91c1c; }
.brief-log-item strong { color:#0f172a; line-height:1.55; }
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
.backend-line__message { color:#e2e8f0; line-height:1.6; white-space:pre-wrap; }
.backend-line__extra, .backend-snapshot pre { margin:8px 0 0; padding:10px 12px; border-radius:12px; background:#000814; color:#bae6fd; white-space:pre-wrap; word-break:break-word; font-size:.78rem; }
.backend-snapshot { margin-top:8px; padding-top:8px; border-top:1px solid #1e293b; }
.backend-snapshot__title { color:#f8fafc; font-size:.82rem; font-weight:800; text-transform:uppercase; letter-spacing:.08em; }
@media (max-width: 1120px) { .runtime-layout, .runtime-content { grid-template-columns:1fr; } }
</style>
