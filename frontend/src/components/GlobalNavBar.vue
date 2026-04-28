<template>
  <header class="global-nav-shell">
    <div class="global-nav-main">
      <div class="left-actions">
        <button v-if="canGoBack" class="nav-btn" @click="goBack">返回</button>
        <button class="brand" @click="goHome">玄穹文枢</button>
      </div>

      <nav class="nav-links" aria-label="全局导航">
        <button :class="linkClass('workspace-entry')" @click="goHome">主页</button>
        <button :class="linkClass('novel-workspace')" @click="goProjects">小说项目</button>
        <button :class="linkClass('inspiration-mode')" @click="goInspiration">灵感模式</button>
        <button :class="linkClass('style-center')" @click="goStyleCenter">文风中心</button>
        <button :class="linkClass('admin')" @click="goAdmin">管理台</button>
        <button :class="linkClass('settings')" @click="goSystemSettings">系统配置</button>
        <button :class="linkClass('llm-settings')" @click="goLLMSettings">LLM 配置</button>
      </nav>

      <div class="right-actions">
        <button class="locale-btn" :title="switchLabel" @click="toggleLocale">{{ languageLabel }}</button>
        <button v-if="lastProjectId" class="continue-btn" @click="continueWriting">继续写作</button>
      </div>
    </div>

    <div v-if="globalTaskVisible" class="global-task-band">
      <div class="global-task-band__head">
        <div class="global-task-band__meta">
          <span class="task-chip task-chip--primary">章节处理中心</span>
          <span class="task-chip">{{ currentTaskProjectTitle }}</span>
          <span class="task-chip">第 {{ currentTaskChapterNumber }} 章</span>
          <span class="task-chip">{{ currentTaskStageLabel }}</span>
          <span class="task-chip">第 {{ taskUiModel.currentStep }}/{{ taskUiModel.totalSteps }} 步</span>
          <span v-if="currentTaskEta" class="task-chip">预计剩余 {{ currentTaskEta }}</span>
          <span v-else-if="currentTaskWarning" class="task-chip task-chip--warn">{{ currentTaskWarning }}</span>
        </div>
        <div class="global-task-band__actions">
          <button class="task-btn task-btn--ghost" @click="openRuntimeLogs">运行日志</button>
          <button class="task-btn" @click="continueWriting">回到写作页</button>
        </div>
      </div>

      <div class="global-task-band__body">
        <div class="global-task-band__summary">
          <strong>{{ currentTaskTitle }}</strong>
          <p>{{ currentTaskMessage }}</p>
        </div>

        <div class="global-task-band__progress">
          <div>
            <div class="progress-row">
              <span>{{ currentTaskStageProgressLabel }}</span>
              <strong>{{ currentTaskStageProgress }}%</strong>
            </div>
            <div class="progress-track" aria-label="stage-progress">
              <div class="progress-bar progress-bar--phase" :style="{ width: `${currentTaskStageProgress}%` }"></div>
            </div>
          </div>

          <div>
            <div class="progress-row progress-row--secondary">
              <span>{{ currentTaskTotalProgressLabel }}</span>
              <strong>{{ currentTaskProgress }}%</strong>
            </div>
            <div class="progress-track" aria-label="total-progress">
              <div class="progress-bar" :style="{ width: `${currentTaskProgress}%` }"></div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useLocale } from '@/composables/useLocale'
import { useNovelStore } from '@/stores/novel'
import { buildChapterTaskUiModel, isTrackableTask, resolveProjectTaskContext } from '@/utils/chapterGeneration'
import { stripThinkTags } from '@/utils/safeMarkdown'

const router = useRouter()
const route = useRoute()
const novelStore = useNovelStore()
const { languageLabel, switchLabel, toggleLocale } = useLocale()

const lastProjectId = ref<string | null>(null)
const pollingTimer = ref<number | null>(null)
const LAST_PROJECT_KEY = 'xuanqiong_wenshu_last_project_id'

const canGoBack = computed(() => route.name !== 'workspace-entry')
const currentProject = computed(() => novelStore.currentProject)
const taskContext = computed(() => resolveProjectTaskContext(currentProject.value || null))
const currentTaskChapter = computed(() => taskContext.value.chapter)
const currentTaskRuntime = computed(() => taskContext.value.runtime)

const taskUiModel = computed(() => buildChapterTaskUiModel(currentTaskRuntime.value, {
  progressMessage: currentTaskRuntime.value?.progress_message,
  status: currentTaskRuntime.value?.progress_stage || currentTaskRuntime.value?.status,
}))

const globalTaskVisible = computed(() =>
  Boolean(currentProject.value?.id && currentTaskChapter.value?.chapter_number && isTrackableTask(currentTaskChapter.value, currentTaskRuntime.value))
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

onMounted(async () => {
  lastProjectId.value = localStorage.getItem(LAST_PROJECT_KEY)
  await ensureProjectLoaded()
})

onBeforeUnmount(() => {
  stopPolling()
})

async function ensureProjectLoaded() {
  const targetId = route.name === 'writing-desk' && typeof route.params.id === 'string'
    ? route.params.id
    : lastProjectId.value

  if (!targetId || currentProject.value?.id === targetId) return

  try {
    await novelStore.loadProject(targetId, true)
  } catch {
    // ignore
  }
}

function stopPolling() {
  if (pollingTimer.value !== null) {
    window.clearInterval(pollingTimer.value)
    pollingTimer.value = null
  }
}

function syncPolling() {
  stopPolling()
  if (!currentProject.value?.id || !globalTaskVisible.value) return

  pollingTimer.value = window.setInterval(async () => {
    if (!currentProject.value?.id) return
    try {
      await novelStore.loadProject(currentProject.value.id, true)
    } catch {
      // ignore
    }
  }, 5000)
}

function goBack() {
  window.history.length > 1 ? router.back() : router.push({ name: 'workspace-entry' })
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
.global-nav-shell {
  position: sticky;
  top: 0;
  z-index: 40;
  display: grid;
  gap: 0;
  border-bottom: 1px solid #e5e7eb;
  background: rgba(255, 255, 255, 0.96);
  backdrop-filter: blur(14px);
}
.global-nav-main,
.left-actions,
.nav-links,
.right-actions,
.global-task-band__head,
.global-task-band__meta,
.global-task-band__actions,
.progress-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.global-nav-main {
  max-width: 1380px;
  margin: 0 auto;
  min-height: 44px;
  width: 100%;
  justify-content: space-between;
  padding: 0 10px;
}
.nav-links,
.right-actions,
.global-task-band__meta,
.global-task-band__actions {
  flex-wrap: wrap;
}
.brand,
.nav-btn,
.nav-link,
.continue-btn,
.locale-btn,
.task-btn {
  border: 0;
  cursor: pointer;
  font-weight: 700;
  border-radius: 999px;
}
.brand { background: #111827; color: #fff; padding: 6px 12px; font-size: 0.86rem; }
.nav-btn,
.locale-btn,
.nav-link,
.task-btn--ghost {
  background: #fff;
  color: #334155;
  border: 1px solid rgba(148, 163, 184, 0.24);
  padding: 5px 10px;
  font-size: 0.8rem;
}
.nav-link--active,
.nav-link:hover { background: #eef2ff; color: #3730a3; border-color: #c7d2fe; }
.continue-btn,
.task-btn { background: #0f172a; color: #fff; padding: 6px 12px; font-size: 0.8rem; }
.global-task-band {
  border-top: 1px solid rgba(226, 232, 240, 0.9);
  background: linear-gradient(180deg, rgba(247, 250, 255, 0.98), rgba(240, 247, 255, 0.96));
  padding: 6px 10px 8px;
}
.global-task-band__head,
.global-task-band__body {
  max-width: 1380px;
  margin: 0 auto;
}
.global-task-band__body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(360px, 520px);
  gap: 10px;
  align-items: center;
  margin-top: 6px;
}
.global-task-band__summary strong { color: #0f172a; font-size: 0.88rem; }
.global-task-band__summary p { margin: 4px 0 0; color: #475569; font-size: 0.78rem; line-height: 1.35; }
.global-task-band__progress { display: grid; gap: 6px; }
.task-chip {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.75);
  border: 1px solid rgba(148, 163, 184, 0.22);
  color: #334155;
  font-size: 0.68rem;
  font-weight: 700;
}
.task-chip--primary { background: #111827; color: #fff; border-color: #111827; }
.task-chip--warn { background: rgba(254, 242, 242, 0.9); color: #b91c1c; border-color: rgba(248, 113, 113, 0.24); }
.progress-row { justify-content: space-between; font-size: 0.72rem; color: #475569; }
.progress-track { height: 6px; }
.progress-row strong { color: #0f172a; }
.progress-row--secondary { color: #64748b; }
.progress-track { height: 8px; border-radius: 999px; background: rgba(203, 213, 225, 0.6); overflow: hidden; }
.progress-bar { height: 100%; border-radius: inherit; background: linear-gradient(90deg, #2563eb, #06b6d4); }
.progress-bar--phase { background: linear-gradient(90deg, #0f766e, #14b8a6); }
@media (max-width: 1100px) {
  .global-task-band__body { grid-template-columns: 1fr; }
}
@media (max-width: 768px) {
  .global-nav-main { min-height: auto; padding: 10px 12px; align-items: flex-start; }
  .left-actions, .nav-links, .right-actions { flex-wrap: wrap; }
}
</style>
