<template>
  <header :class="['global-nav-shell xq-topbar xq-topbar--global', { 'global-nav-shell--writing': isWritingDeskRoute }]">
    <div class="global-nav-main">
      <div class="left-actions">
        <button v-if="canGoBack" class="nav-btn" @click="goBack">返回</button>
        <button class="brand" @click="goHome">玄穹文枢</button>
      </div>

      <nav class="nav-links" aria-label="全局导航">
        <span class="nav-brand-text">玄穹文枢 — AI 小说创作平台</span>
      </nav>

<div class="right-actions">
        <button class="locale-btn" :title="switchLabel" @click="toggleLocale">{{ languageLabel }}</button>
        <button v-if="lastProjectId" class="continue-btn" @click="continueWriting">继续写作</button>
      
      <router-link to="/inspiration" class="nav-btn nav-btn--new" title="快速新建小说">
        <span class="nav-btn-icon">+</span>
        <span class="nav-btn-label">新建</span>
      </router-link>
    </div>
    </div>

        <div v-if="globalTaskVisible" class="global-task-mini">
      <span class="global-task-mini__icon">⚡</span>
      <span class="global-task-mini__text">后台任务进行中</span>
      <button class="global-task-mini__btn" @click="continueWriting">回到写作页</button>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useLocale } from '@/composables/useLocale'
import { useNovelStore } from '@/stores/novel'
import { buildChapterTaskUiModel, isBusyTask, isTrackableTask, normalizeRuntimeStage, resolveProjectTaskContext } from '@/utils/chapterGeneration'
import { stripThinkTags } from '@/utils/safeMarkdown'
import { navigateBackOrFallback } from '@/utils/safeNavigation'

const router = useRouter()
const route = useRoute()
const novelStore = useNovelStore()
const { languageLabel, switchLabel, toggleLocale } = useLocale()

const lastProjectId = ref<string | null>(null)
const pollingTimer = ref<number | null>(null)
const LAST_PROJECT_KEY = 'xuanqiong_wenshu_last_project_id'
const PROJECT_POLLING_INTERVAL = 60000
let loadingProjectId: string | null = null
let loadingProjectPromise: Promise<void> | null = null

const canGoBack = computed(() => route.name !== 'workspace-entry')
const isWritingDeskRoute = computed(() => route.name === 'writing-desk')
const currentProject = computed(() => novelStore.currentProject)
const taskContext = computed(() => resolveProjectTaskContext(currentProject.value || null))
const currentTaskChapter = computed(() => taskContext.value.chapter)
const currentTaskRuntime = computed(() => taskContext.value.runtime)

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
    currentProject.value?.id &&
    currentTaskChapter.value?.chapter_number &&
    isTrackableTask(currentTaskChapter.value, currentTaskRuntime.value) &&
    (currentTaskIsBusy.value || currentTaskNeedsAction.value)
  )
)

const currentTaskProjectTitle = computed(() => currentProject.value?.title || '当前项目')
const currentTaskChapterNumber = computed(() => currentTaskChapter.value?.chapter_number || '-')
const currentTaskStageLabel = computed(() => taskUiModel.value.stageLabel)
const currentTaskTitle = computed(() => `《${currentTaskProjectTitle.value}》第 ${currentTaskChapterNumber.value} 章`)
const currentTaskProgress = computed(() => taskUiModel.value.totalProgress)
const currentTaskStageProgress = computed(() => taskUiModel.value.stageProgress)
const currentTaskStageProgressLabel = computed(() => taskUiModel.value.stageProgressLabel)
const currentTaskTotalProgressLabel = computed(() => taskUiModel.value.totalProgressLabel)
const currentTaskEta = computed(() => taskUiModel.value.etaLabel)
const currentTaskWarning = computed(() => taskUiModel.value.isLikelyStalled ? `当前步骤 ${taskUiModel.value.currentStep}/${taskUiModel.value.totalSteps} 长时间未更新` : '')
const currentTaskMessage = computed(() => stripThinkTags(taskUiModel.value.displayMessage) || '后台正在处理')

function linkClass(name: string) {
  const isActive =
    route.name === name ||
    (name === 'admin' && route.name === 'admin' && !route.query.tab)
  return ['nav-link', isActive ? 'nav-link--active' : '']
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
  syncPolling()
}, { immediate: true })

watch(isWritingDeskRoute, () => {
  syncPolling()
  void ensureProjectLoaded()
}, { immediate: true })

const handleVisibilityChange = () => {
  syncPolling()
}

onMounted(async () => {
  lastProjectId.value = localStorage.getItem(LAST_PROJECT_KEY)
  document.addEventListener('visibilitychange', handleVisibilityChange)
  await ensureProjectLoaded()
})

onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', handleVisibilityChange)
  stopPolling()
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

async function goBack() {
  await navigateBackOrFallback(router, route.fullPath, { name: 'workspace-entry' })
}

function goHome() {
  router.push({ name: 'workspace-entry' })
}

function goProjects() {
  router.push({ name: 'novel-workspace' })
}

function goInspiration() {
  router.push({ name: 'inspiration-mode' })
}

function goStyleCenter() {
  router.push({ name: 'style-center' })
}

function goAdmin() {
  router.push({ name: 'admin' })
}

function goSystemSettings() {
  router.push({ name: 'settings' })
}

function goLLMSettings() {
  router.push({ name: 'llm-settings' })
}

function continueWriting() {
  if (lastProjectId.value) {
    router.push({ name: 'writing-desk', params: { id: lastProjectId.value } })
  }
}

function openRuntimeLogs() {
  const query: Record<string, string> = { tab: 'runtime-logs' }
  if (currentProject.value?.id) query.project_id = currentProject.value.id
  if (currentTaskChapter.value?.chapter_number) query.chapter = String(currentTaskChapter.value.chapter_number)
  router.push({ name: 'admin', query })
}
</script>

<style scoped>
.global-nav-shell--writing { opacity: 0.3; transition: opacity 0.4s; }
.global-nav-shell--writing:hover { opacity: 1; }

/* Slim global nav */
.xq-topbar--global {
  height: 55px !important;
  min-height: 55px !important;
}
.global-nav-shell {
  height: 55px;
}

.global-nav-shell {
  position: sticky;
  top: 0;
  z-index: 40;
  display: grid;
  gap: 0;
  border-bottom: 1px solid #e5e7eb;
  background: rgba(255, 255, 255, 0.96);
}
.global-nav-main,
.left-actions,
.nav-links,
.right-actions,

/* 极简任务通知条 */
.global-task-mini {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 16px;
  background: linear-gradient(135deg, #fff7ed, #fef3c7);
  border-bottom: 1px solid #fcd34d;
  font-size: 0.82rem;
  color: #92400e;
}
.global-task-mini__icon { font-size: 1.1rem; }
.global-task-mini__text { flex: 1; }
.global-task-mini__btn {
  padding: 4px 12px;
  border-radius: 6px;
  border: 1px solid #f59e0b;
  background: #fff;
  color: #92400e;
  font-size: 0.78rem;
  cursor: pointer;
  transition: all 0.15s;
}
.global-task-mini__btn:hover {
  background: #fef3c7;
}
</style>
