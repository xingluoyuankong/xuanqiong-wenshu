<template>
  <aside class="global-nav-shell" :aria-label="pick('主导航', 'Main navigation')">
    <button
      class="global-nav-brand"
      type="button"
      :title="pick('返回工作台', 'Back to workspace')"
      :aria-label="pick('返回工作台', 'Back to workspace')"
      @click="goHome"
    >
      玄
    </button>

    <nav class="global-nav-group" :aria-label="pick('工作区导航', 'Workspace navigation')">
      <button
        v-if="canGoBack"
        class="global-nav-item"
        type="button"
        :title="pick('返回上一页', 'Go back')"
        :aria-label="pick('返回上一页', 'Go back')"
        @click="goBack"
      >
        <ChevronLeft class="global-nav-icon" aria-hidden="true" />
      </button>
      <button
        v-for="item in primaryNavItems"
        :key="item.name"
        :class="navItemClass(item.name)"
        type="button"
        :title="item.title"
        :aria-label="item.title"
        :aria-current="isNavActive(item.name) ? 'page' : undefined"
        @click="goRoute(item.name)"
      >
        <component :is="item.icon" class="global-nav-icon" aria-hidden="true" />
      </button>
    </nav>

    <div class="global-nav-footer">
      <button
        v-if="lastProjectId"
        class="global-nav-item"
        type="button"
        :title="pick('继续最近项目', 'Resume latest project')"
        :aria-label="pick('继续最近项目', 'Resume latest project')"
        @click="continueWriting"
      >
        <PenLine class="global-nav-icon" aria-hidden="true" />
      </button>
      <button
        v-if="!isWritingDeskRoute"
        class="global-nav-item"
        type="button"
        :title="switchLabel"
        :aria-label="switchLabel"
        @click="toggleLocale"
      >
        <Languages class="global-nav-icon" aria-hidden="true" />
      </button>
      <button
        :class="navItemClass('settings')"
        type="button"
        :title="pick('设置', 'Settings')"
        :aria-label="pick('设置', 'Settings')"
        :aria-current="isNavActive('settings') ? 'page' : undefined"
        @click="goRoute('settings')"
      >
        <Settings class="global-nav-icon" aria-hidden="true" />
      </button>
    </div>

    <div
      v-if="globalTaskVisible"
      class="global-task-mini"
      aria-live="polite"
      :aria-label="pick('后台任务进度', 'Background task progress')"
    >
      <div class="global-task-mini__head">
        <span>{{ pick('后台任务', 'Background task') }}</span>
        <strong>{{ currentTaskTotalProgressLabel }}</strong>
      </div>
      <strong class="global-task-mini__title">{{ currentTaskTitle }}</strong>
      <div class="global-task-mini__stage">
        <span>{{ currentTaskStageLabel }}</span>
        <span>{{ currentTaskStageProgressLabel }}</span>
      </div>
      <div
        class="global-task-mini__track"
        role="progressbar"
        :aria-label="pick(`${currentTaskTitle}生成进度`, `${currentTaskTitle} generation progress`)"
        :aria-valuenow="currentTaskProgress"
        aria-valuemin="0"
        aria-valuemax="100"
      >
        <span :style="{ width: `${currentTaskProgress}%` }"></span>
      </div>
      <p class="global-task-mini__message">{{ currentTaskMessage }}</p>
      <p class="global-task-mini__eta">{{ currentTaskEtaLabel }}</p>
      <p v-if="currentTaskWarning" class="global-task-mini__warning">{{ currentTaskWarning }}</p>
      <div class="global-task-mini__actions">
        <button type="button" @click="continueWriting">{{ pick('打开工作区', 'Open workspace') }}</button>
        <button v-if="canCancelCurrentTask" type="button" :disabled="taskActionPending" @click="cancelCurrentTask">
          {{ taskActionPending ? pick('处理中…', 'Working…') : pick('取消任务', 'Cancel task') }}
        </button>
        <button v-else-if="canRetryCurrentTask" type="button" :disabled="taskActionPending" @click="retryCurrentTask">
          {{ taskActionPending ? pick('处理中…', 'Working…') : pick('重试任务', 'Retry task') }}
        </button>
        <button type="button" @click="openRuntimeLogs">{{ pick('查看日志', 'View logs') }}</button>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Activity,
  ChevronLeft,
  Cpu,
  Languages,
  LayoutGrid,
  PenLine,
  Settings,
  Sparkles,
  Type,
} from 'lucide-vue-next'
import { useLocale } from '@/composables/useLocale'
import { useAuthStore } from '@/stores/auth'
import { useNovelStore } from '@/stores/novel'
import { TaskRuntimeAPI, type TaskRuntimeRead } from '@/api/task-runtime'
import { buildChapterTaskUiModel, isBusyTask, isTrackableTask, normalizeRuntimeStage, resolveProjectTaskContext } from '@/utils/chapterGeneration'
import { stripThinkTags } from '@/utils/safeMarkdown'
import { navigateBackOrFallback } from '@/utils/safeNavigation'

type PickFn = <T>(zh: T, en: T) => T

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const novelStore = useNovelStore()
const localeApi = useLocale()
const { switchLabel, toggleLocale } = localeApi
/** 兜底：部分单测只 mock 了 useLocale 的语言切换能力，缺 pick 时按中文渲染，保证组件可独立挂载。 */
const fallbackPick: PickFn = (zh) => zh
const pick: PickFn = localeApi.pick ?? fallbackPick

const lastProjectId = ref<string | null>(null)
const pollingTimer = ref<number | null>(null)
const taskPollingTimer = ref<number | null>(null)
const durableTasks = ref<TaskRuntimeRead[]>([])
const taskActionPending = ref(false)
const LAST_PROJECT_KEY = 'xuanqiong_wenshu_last_project_id'
const PROJECT_POLLING_INTERVAL = 60000
const TASK_POLLING_INTERVAL = 20000
let loadingProjectId: string | null = null
let loadingProjectPromise: Promise<void> | null = null
let loadingTasksPromise: Promise<void> | null = null

const canGoBack = computed(() => route.name !== 'workspace-entry')
const isWritingDeskRoute = computed(() => route.name === 'writing-desk')
const isAgentWorkspaceRoute = computed(() => route.name === 'agent-workspace')
const currentProject = computed(() => novelStore.currentProject)
const taskContext = computed(() => resolveProjectTaskContext(currentProject.value || null))
const currentTaskChapter = computed(() => taskContext.value.chapter)
const currentTaskRuntime = computed(() => taskContext.value.runtime)
const durableTask = computed(() => {
  const currentProjectId = String(currentProject.value?.id || '')
  return durableTasks.value
    .filter((task) => ['queued', 'running', 'cancelling', 'failed', 'stale'].includes(String(task.status)))
    .sort((left, right) => {
      const leftProject = currentProjectId && left.project_id === currentProjectId ? 1 : 0
      const rightProject = currentProjectId && right.project_id === currentProjectId ? 1 : 0
      if (leftProject !== rightProject) return rightProject - leftProject
      const leftBusy = ['queued', 'running', 'cancelling'].includes(String(left.status)) ? 1 : 0
      const rightBusy = ['queued', 'running', 'cancelling'].includes(String(right.status)) ? 1 : 0
      if (leftBusy !== rightBusy) return rightBusy - leftBusy
      return String(right.updated_at || '').localeCompare(String(left.updated_at || ''))
    })[0] || null
})

const taskUiModel = computed(() => buildChapterTaskUiModel(currentTaskRuntime.value, {
  progressMessage: currentTaskRuntime.value?.progress_message,
  status: currentTaskRuntime.value?.progress_stage || currentTaskRuntime.value?.status,
}))

const currentTaskNeedsAction = computed(() => {
  const runtimeStage = normalizeRuntimeStage(currentTaskRuntime.value?.progress_stage || currentTaskRuntime.value?.status)
  const chapterStatus = String(currentTaskChapter.value?.generation_status || '')
  return ['waiting_for_confirm', 'failed', 'evaluation_failed'].includes(runtimeStage)
    || ['waiting_for_confirm', 'failed', 'evaluation_failed'].includes(chapterStatus)
})

const currentTaskIsBusy = computed(() => isBusyTask(currentTaskChapter.value, currentTaskRuntime.value))

const globalTaskVisible = computed(() =>
  Boolean(
    !isWritingDeskRoute.value &&
    !isAgentWorkspaceRoute.value &&
    (durableTask.value || (
      currentProject.value?.id &&
      currentTaskChapter.value?.chapter_number &&
      isTrackableTask(currentTaskChapter.value, currentTaskRuntime.value) &&
      (currentTaskIsBusy.value || currentTaskNeedsAction.value)
    ))
  )
)

const taskPayload = computed(() => durableTask.value?.payload || {})
const taskPayloadText = (key: string) => {
  const value = taskPayload.value[key]
  return typeof value === 'string' || typeof value === 'number' ? String(value) : ''
}
/** 任务类型文案表：值一律走 pick，避免裸中文。 */
const taskTypeLabels = computed<Record<string, string>>(() => ({
  chapter_generation: pick('正文生成', 'Draft generation'),
  chapter_outline_generation: pick('章节大纲', 'Chapter outline'),
  chapter_outline_rewrite: pick('章节大纲优化', 'Outline refinement'),
  blueprint_generation: pick('小说总纲', 'Story blueprint'),
  research: pick('资料收集', 'Research'),
  style_profile: pick('文风提取', 'Style extraction'),
  novel_import: pick('旧稿导入', 'Draft import'),
  novel_export: pick('小说导出', 'Novel export'),
}))
const taskStageLabels = computed<Record<string, string>>(() => ({
  queued: pick('排队等待执行', 'Queued'),
  running: pick('正在执行', 'Running'),
  cancelling: pick('正在取消', 'Cancelling'),
  generating: pick('正在生成正文', 'Writing draft'),
  evaluating: pick('正在评审候选', 'Reviewing candidates'),
  failed: pick('任务失败', 'Task failed'),
  stale: pick('等待恢复', 'Waiting for recovery'),
}))
const currentTaskTypeLabel = computed(() => taskTypeLabels.value[String(durableTask.value?.task_type || '')] || String(durableTask.value?.task_type || pick('后台任务', 'Background task')))
const currentTaskProjectTitle = computed(() => taskPayloadText('project_title') || currentProject.value?.title || pick('当前项目', 'Current project'))
const currentTaskChapterNumber = computed(() => taskPayloadText('chapter_number') || currentTaskChapter.value?.chapter_number || '-')
const currentTaskStageLabel = computed(() => {
  const stage = String(durableTask.value?.stage || '')
  return taskStageLabels.value[stage] || (stage ? stage.replace(/_/g, ' ') : taskUiModel.value.stageLabel)
})
const currentTaskTitle = computed(() => {
  const project = currentTaskProjectTitle.value
  const chapter = currentTaskChapterNumber.value
  if (!durableTask.value) return pick(`《${project}》第 ${chapter} 章`, `${project} · Ch.${chapter}`)
  if (durableTask.value.task_type === 'chapter_generation' && chapter !== '-') {
    return pick(`《${project}》第 ${chapter} 章 · ${currentTaskTypeLabel.value}`, `${project} · Ch.${chapter} · ${currentTaskTypeLabel.value}`)
  }
  return pick(`《${project}》${currentTaskTypeLabel.value}`, `${project} · ${currentTaskTypeLabel.value}`)
})
const currentTaskProgress = computed(() => {
  const value = durableTask.value ? Number(durableTask.value.progress) : taskUiModel.value.totalProgress
  return Math.max(0, Math.min(100, Math.round(Number.isFinite(value) ? value : 0)))
})
const currentTaskStageProgressLabel = computed(() => durableTask.value ? pick(`任务阶段 · ${currentTaskProgress.value}%`, `Stage · ${currentTaskProgress.value}%`) : taskUiModel.value.stageProgressLabel)
const currentTaskTotalProgressLabel = computed(() => durableTask.value ? pick(`总流程完成度 ${currentTaskProgress.value}%`, `Overall ${currentTaskProgress.value}%`) : taskUiModel.value.totalProgressLabel)
const currentTaskEta = computed(() => {
  const seconds = Number(taskPayload.value.estimated_remaining_seconds || 0)
  if (Number.isFinite(seconds) && seconds > 0) {
    return seconds >= 60
      ? pick(`${Math.ceil(seconds / 60)} 分钟`, `${Math.ceil(seconds / 60)} min`)
      : pick(`${Math.ceil(seconds)} 秒`, `${Math.ceil(seconds)} s`)
  }
  return taskUiModel.value.etaLabel
})
/** 剩余时间行：有预估显示预估值，无预估显示"正在计算"。 */
const currentTaskEtaLabel = computed(() => currentTaskEta.value
  ? pick(`预计${currentTaskEta.value}`, `About ${currentTaskEta.value} left`)
  : pick('正在计算剩余时间', 'Estimating time left'))
const currentTaskWarning = computed(() => {
  if (durableTask.value?.status === 'stale') return pick('任务已被标记为中断，可重试恢复', 'Task marked as interrupted; retry to resume')
  if (!taskUiModel.value.isLikelyStalled) return ''
  const { currentStep, totalSteps } = taskUiModel.value
  return pick(`当前步骤 ${currentStep}/${totalSteps} 长时间未更新`, `Step ${currentStep}/${totalSteps} has not updated for a while`)
})
const currentTaskMessage = computed(() => stripThinkTags(durableTask.value?.error_detail || durableTask.value?.message || '') || stripThinkTags(taskUiModel.value.displayMessage) || pick('后台正在处理', 'Working in the background'))
const canCancelCurrentTask = computed(() => Boolean(durableTask.value && ['queued', 'running'].includes(String(durableTask.value.status))))
const canRetryCurrentTask = computed(() => Boolean(durableTask.value && ['failed', 'stale'].includes(String(durableTask.value.status)) && durableTask.value.retry_count < durableTask.value.max_retries))

/** 主导航项：图标 + 标题，标题同时用于 title/aria-label，避免文字标签把 72px 栏塞满。 */
const primaryNavItems = computed(() => {
  const items = [
    { name: 'novel-workspace', icon: LayoutGrid, title: pick('项目', 'Projects') },
    { name: 'inspiration-mode', icon: Sparkles, title: pick('灵感与蓝图', 'Inspiration') },
    { name: 'style-center', icon: Type, title: pick('文风中心', 'Style center') },
    { name: 'llm-settings', icon: Cpu, title: pick('模型配置', 'Models') },
  ]
  if (authStore.isAdmin) {
    items.push({ name: 'admin', icon: Activity, title: pick('运行监控', 'Monitoring') })
  }
  return items
})

function navItemClass(name: string) {
  return ['global-nav-item', isNavActive(name) ? 'global-nav-item--active' : '']
}

function isNavActive(name: string) {
  if (name === 'novel-workspace') {
    return ['novel-workspace', 'novel-detail', 'writing-desk', 'novel-full-reader'].includes(String(route.name))
  }
  if (name === 'admin') {
    return ['admin', 'admin-novel-detail'].includes(String(route.name))
  }
  return route.name === name
}

watch(() => route.params.id, (newId) => {
  if (newId && typeof newId === 'string') {
    lastProjectId.value = newId
    localStorage.setItem(LAST_PROJECT_KEY, newId)
  }
}, { immediate: true })

watch(lastProjectId, () => {
  void ensureProjectLoaded()
})

watch(globalTaskVisible, () => {
  syncPolling()
}, { immediate: true })

watch(() => currentProject.value?.id, () => {
  void refreshDurableTasks()
  syncTaskPolling()
  syncPolling()
}, { immediate: true })

watch(isWritingDeskRoute, () => {
  syncPolling()
  void ensureProjectLoaded()
}, { immediate: true })

const handleVisibilityChange = () => {
  syncPolling()
  syncTaskPolling()
}

onMounted(async () => {
  lastProjectId.value = localStorage.getItem(LAST_PROJECT_KEY)
  document.addEventListener('visibilitychange', handleVisibilityChange)
  await ensureProjectLoaded()
  await refreshDurableTasks()
})

onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', handleVisibilityChange)
  stopPolling()
  stopTaskPolling()
})

async function ensureProjectLoaded() {
  if (isWritingDeskRoute.value) return

  const targetId = lastProjectId.value
  if (!targetId || currentProject.value?.id === targetId) return

  if (loadingProjectPromise && loadingProjectId === targetId) {
    await loadingProjectPromise
    return
  }

  loadingProjectId = targetId
  loadingProjectPromise = (async () => {
    try {
      await novelStore.loadProject(targetId, true)
    } catch {
      // ignore
    } finally {
      if (loadingProjectId === targetId) {
        loadingProjectId = null
        loadingProjectPromise = null
      }
    }
  })()

  await loadingProjectPromise
}

function stopPolling() {
  if (pollingTimer.value !== null) {
    window.clearInterval(pollingTimer.value)
    pollingTimer.value = null
  }
}

function stopTaskPolling() {
  if (taskPollingTimer.value !== null) {
    window.clearInterval(taskPollingTimer.value)
    taskPollingTimer.value = null
  }
}

async function refreshDurableTasks() {
  if (document.hidden || loadingTasksPromise) return loadingTasksPromise
  loadingTasksPromise = (async () => {
    try {
      durableTasks.value = await TaskRuntimeAPI.listTasks({ projectId: currentProject.value?.id, limit: 100 })
    } catch {
      // Chapter snapshots remain the compatibility fallback when TaskRuntime is unavailable.
    } finally {
      loadingTasksPromise = null
    }
  })()
  return loadingTasksPromise
}

function syncTaskPolling() {
  stopTaskPolling()
  if (document.hidden || isWritingDeskRoute.value) return
  taskPollingTimer.value = window.setInterval(() => {
    void refreshDurableTasks()
  }, TASK_POLLING_INTERVAL)
}

function syncPolling() {
  stopPolling()
  if (isWritingDeskRoute.value || document.hidden || !currentProject.value?.id || !globalTaskVisible.value) return

  pollingTimer.value = window.setInterval(async () => {
    if (document.hidden || !currentProject.value?.id) return
    try {
      await novelStore.loadProject(currentProject.value.id, true)
    } catch {
      // ignore
    }
  }, PROJECT_POLLING_INTERVAL)
}

async function cancelCurrentTask() {
  const taskId = durableTask.value?.task_id
  if (!taskId || taskActionPending.value) return
  taskActionPending.value = true
  try {
    const updated = await TaskRuntimeAPI.cancelTask(taskId)
    durableTasks.value = durableTasks.value.map((task) => task.task_id === taskId ? updated : task)
  } catch {
    await refreshDurableTasks()
  } finally {
    taskActionPending.value = false
  }
}

async function retryCurrentTask() {
  const task = durableTask.value
  if (!task || taskActionPending.value) return
  taskActionPending.value = true
  try {
    const updated = await TaskRuntimeAPI.retryTask(task.task_id, `${task.task_id}:retry:${task.retry_count + 1}`)
    durableTasks.value = durableTasks.value.map((item) => item.task_id === task.task_id ? updated : item)
  } catch {
    await refreshDurableTasks()
  } finally {
    taskActionPending.value = false
  }
}

async function goBack() {
  await navigateBackOrFallback(router, route.fullPath, { name: 'workspace-entry' })
}

function goHome() {
  router.push({ name: 'workspace-entry' })
}

/** 统一路由跳转：取代原来 6 个一行一个的 go* 函数。 */
function goRoute(name: string) {
  router.push({ name })
}

function continueWriting() {
  const projectId = lastProjectId.value || durableTask.value?.project_id
  if (projectId) {
    router.push({ name: 'writing-desk', params: { id: projectId } })
  }
}

function openRuntimeLogs() {
  const query: Record<string, string> = { tab: 'runtime-logs' }
  if (durableTask.value?.task_id) query.task_id = durableTask.value.task_id
  if (durableTask.value?.task_type) query.task_type = durableTask.value.task_type
  if (durableTask.value?.project_id || currentProject.value?.id) query.project_id = durableTask.value?.project_id || String(currentProject.value?.id)
  if (currentTaskChapter.value?.chapter_number) query.chapter = String(currentTaskChapter.value.chapter_number)
  router.push({ name: 'admin', query })
}
</script>

<style scoped>
/* 把不可改文件 main.css 里写死的 88px 轨道宽重定向到设计令牌；
   html:root 特异性高于 :root，因此不依赖样式注入顺序。 */
:global(html:root) {
  --global-nav-width: var(--xq-nav-width);
  --global-nav-mobile-height: 56px;
}

.global-nav-shell {
  position: fixed;
  inset: 0 auto 0 0;
  z-index: 80;
  display: flex;
  width: var(--global-nav-width);
  flex-direction: column;
  align-items: center;
  gap: var(--xq-space-2);
  padding: var(--xq-space-3) var(--xq-space-2);
  overflow-y: auto;
  border-right: 1px solid var(--xq-border);
  background: var(--xq-surface);
  color: var(--xq-text-body);
  font-family: var(--xq-font-sans);
  scrollbar-width: none;
}

.global-nav-shell::-webkit-scrollbar {
  display: none;
}

.global-nav-brand {
  display: flex;
  width: 40px;
  height: 40px;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  margin-bottom: var(--xq-space-2);
  border: 1px solid var(--xq-accent-border);
  border-radius: var(--xq-radius-md);
  background: var(--xq-accent-soft);
  color: var(--xq-accent-text);
  font-size: var(--xq-text-lg);
  font-weight: var(--xq-weight-semibold);
  cursor: pointer;
}

.global-nav-brand:hover {
  background: var(--xq-accent-soft-hover);
}
.global-nav-group,
.global-nav-footer {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--xq-space-1);
}

.global-nav-footer {
  margin-top: auto;
  padding-top: var(--xq-space-2);
}

.global-nav-item {
  display: flex;
  width: 40px;
  height: 40px;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: var(--xq-radius-md);
  background: transparent;
  color: var(--xq-text-muted);
  cursor: pointer;
  transition: background var(--xq-fast), color var(--xq-fast);
}

.global-nav-item:hover {
  background: var(--xq-surface-hover);
  color: var(--xq-text);
}

.global-nav-item--active {
  background: var(--xq-accent-soft);
  color: var(--xq-accent);
}

.global-nav-icon {
  width: 18px;
  height: 18px;
}

.global-nav-shell button:focus-visible,
.global-task-mini button:focus-visible {
  outline: none;
  box-shadow: var(--xq-ring);
}
/* 后台任务浮卡：白底 + 1px 描边 + 单层轻阴影，不用磨砂与渐变 */
.global-task-mini {
  position: fixed;
  top: max(var(--xq-space-4), env(safe-area-inset-top));
  right: var(--xq-space-5);
  z-index: 90;
  width: min(320px, calc(100vw - 120px));
  max-height: min(420px, calc(100vh - var(--xq-space-8)));
  overflow-y: auto;
  padding: var(--xq-space-4);
  border: 1px solid var(--xq-border);
  border-radius: var(--xq-radius-lg);
  background: var(--xq-surface);
  box-shadow: var(--xq-shadow-md);
  color: var(--xq-text-body);
}

.global-task-mini__head,
.global-task-mini__stage,
.global-task-mini__actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--xq-space-2);
}

.global-task-mini__head {
  color: var(--xq-text-faint);
  font-size: var(--xq-text-2xs);
  letter-spacing: .06em;
}

.global-task-mini__head strong {
  color: var(--xq-text);
  font-size: var(--xq-text-xs);
  font-weight: var(--xq-weight-semibold);
  font-variant-numeric: tabular-nums;
  letter-spacing: 0;
}

.global-task-mini__title {
  display: block;
  margin-top: var(--xq-space-2);
  overflow: hidden;
  color: var(--xq-text);
  font-size: var(--xq-text-sm);
  font-weight: var(--xq-weight-medium);
  text-overflow: ellipsis;
  white-space: nowrap;
}
.global-task-mini__stage {
  margin-top: var(--xq-space-3);
  color: var(--xq-text-muted);
  font-size: var(--xq-text-xs);
  font-variant-numeric: tabular-nums;
}

.global-task-mini__track {
  height: 4px;
  margin: var(--xq-space-2) 0;
  overflow: hidden;
  border-radius: var(--xq-radius-pill);
  background: var(--xq-surface-3);
}

.global-task-mini__track span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--xq-accent);
  transition: width var(--xq-normal);
}

.global-task-mini__message {
  display: -webkit-box;
  margin: 0;
  overflow: hidden;
  color: var(--xq-text-muted);
  font-size: var(--xq-text-xs);
  line-height: var(--xq-leading-snug);
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}

.global-task-mini__eta {
  margin: var(--xq-space-1) 0 0;
  color: var(--xq-text-faint);
  font-size: var(--xq-text-2xs);
  font-variant-numeric: tabular-nums;
}

.global-task-mini__warning {
  margin: var(--xq-space-2) 0 0;
  padding-left: var(--xq-space-2);
  border-left: 3px solid var(--xq-warning);
  color: var(--xq-warning-text);
  font-size: var(--xq-text-2xs);
  line-height: var(--xq-leading-snug);
}
.global-task-mini__actions {
  flex-wrap: wrap;
  justify-content: flex-start;
  margin-top: var(--xq-space-3);
}

.global-task-mini__actions button {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--xq-accent);
  font-family: inherit;
  font-size: var(--xq-text-xs);
  cursor: pointer;
}

.global-task-mini__actions button:hover {
  color: var(--xq-accent-hover);
}

.global-task-mini__actions button:disabled {
  color: var(--xq-text-faint);
  cursor: wait;
}

.global-task-mini__actions button + button {
  padding-left: var(--xq-space-3);
  border-left: 1px solid var(--xq-border);
}

/* 窄屏：导航转为底部横条。断点与 main.css 的 720px 保持一致，
   否则 721-767px 区间会出现"导航已在底部却仍留 margin-left"的塌陷。 */
@media (max-width: 720px) {
  .global-nav-shell {
    inset: auto 0 0;
    width: auto;
    height: calc(var(--global-nav-mobile-height) + env(safe-area-inset-bottom));
    flex-direction: row;
    justify-content: center;
    gap: var(--xq-space-1);
    padding: var(--xq-space-1) var(--xq-space-3) env(safe-area-inset-bottom);
    overflow-x: auto;
    overflow-y: hidden;
    border-top: 1px solid var(--xq-border);
    border-right: 0;
  }

  .global-nav-brand {
    display: none;
  }

  .global-nav-group,
  .global-nav-footer {
    flex-direction: row;
    margin: 0;
    padding: 0;
  }

  .global-task-mini {
    top: max(var(--xq-space-3), env(safe-area-inset-top));
    right: var(--xq-space-3);
    width: min(320px, calc(100vw - var(--xq-space-6)));
    max-height: min(360px, calc(100vh - 92px));
  }
}
</style>
