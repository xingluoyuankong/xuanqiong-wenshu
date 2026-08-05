<template>
  <div class="m3-shell writing-desk-shell xq-page-canvas min-h-screen flex flex-col overflow-x-hidden">
    <WDHeader
      :project="project"
      :progress="progress"
      :completed-chapters="completedChapters"
      :total-chapters="totalChapters"
      :workspace-summary="workspaceSummary"
      :generation-runtime="generationRuntime"
      :selected-chapter-number="selectedChapterNumber"
      :sidebar-open="sidebarOpen"
      :can-generate-current="canGenerateSelectedChapter"
      :generate-current-label="generateCurrentLabel"
      :can-evaluate-current="canEvaluateSelectedChapter"
      :can-confirm-current="canConfirmSelectedChapter"
      :can-terminate-current="canTerminateSelectedChapter"
      :can-prev-chapter="canSelectPrevChapter"
      :can-next-chapter="canSelectNextChapter"
      :is-current-chapter-busy="isCurrentChapterBusy"
      :is-current-chapter-trackable="isCurrentChapterTrackable"
      :task-chapter-number="taskPanelChapterNumber"
      :task-generation-runtime="taskPanelRuntime"
      :task-trackable="hasTrackableTaskPanel"
      :can-open-versions-current="canOpenVersionsSelectedChapter"
      :can-review-all-versions-current="canReviewAllVersionsSelectedChapter"
      :status-fetch-failure-count="statusFetchFailureCount"
      :active-style-profile="activeStyleProfile"
      :is-admin="Boolean(authStore?.user?.is_admin)"
      :header-collapsed="headerCollapsed"
      @go-back="goBack"
      @view-project-detail="viewProjectDetail"
      @open-admin-panel="openAdminPanel"
      @open-runtime-logs="openRuntimeLogs"
      @toggle-sidebar="toggleSidebar"
      @prev-chapter="goPrevChapter"
      @next-chapter="goNextChapter"
      @generate-current="handlePrimaryGenerate"
      @evaluate-current="evaluateChapter"
      @review-all-versions-current="evaluateAllVersions"
      @open-versions-current="openVersionSelectorFromHeader"
      @confirm-current="confirmVersionSelection"
      @terminate-current="handleTerminateCurrent"
      @toggle-shortcut-help="showShortcutHelp = true"
      @open-skills="showSkillSelectorModal = true"
      @toggle-header-collapse="headerCollapsed = !headerCollapsed"
    />

    <main class="m3-main writing-desk-main min-h-0 flex-1 w-full px-1 pb-2 pt-1 sm:px-2 lg:px-3">
      <div v-if="novelStore.isLoading" class="skeleton-workspace writing-desk-loading h-full flex gap-3 px-2 pb-3 pt-2 sm:px-3 lg:px-4">
        <!-- Sidebar skeleton -->
        <div class="skeleton-sidebar w-64 flex-shrink-0 rounded-2xl animate-pulse"></div>
        <!-- Main area skeleton -->
        <div class="skeleton-main flex-1 min-w-0 flex flex-col gap-4">
          <!-- Header skeleton -->
          <div class="skeleton-header h-14 rounded-2xl animate-pulse"></div>
          <!-- Content skeleton -->
          <div class="skeleton-content flex-1 rounded-2xl animate-pulse"></div>
        </div>
      </div>

      <div v-else-if="novelStore.error" class="writing-desk-error text-center py-20">
        <div class="md-card md-card-outlined mx-auto max-w-md p-8" style="border-radius: var(--md-radius-xl);">
          <div class="mb-4 flex h-12 w-12 items-center justify-center rounded-full mx-auto" style="background-color: var(--md-error-container);">
            <svg class="w-6 h-6" style="color: var(--md-error);" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path>
            </svg>
          </div>
          <h3 class="md-title-large mb-2" style="color: var(--md-on-surface);">加载失败</h3>
          <p class="md-body-medium mb-4" style="color: var(--md-error);">{{ novelStore.error }}</p>
          <button @click="loadProject" class="md-btn md-btn-tonal md-ripple">重新加载</button>
        </div>
      </div>

      <div
        v-else-if="project"
        :class="[
          'm3-workspace writing-desk-grid min-h-0 flex flex-col lg:flex-row',
          sidebarOpen ? 'gap-2 lg:gap-3' : 'gap-1 lg:gap-0'
        ]"
      >
        <WDSidebar
          :project="project"
          :sidebar-open="sidebarOpen"
          :selected-chapter-number="selectedChapterNumber"
          :generating-chapter="generatingChapter"
          :evaluating-chapter="evaluatingChapter"
          :is-generating-outline="isGeneratingOutline"
          :workspace-summary="workspaceSummary"
          @close-sidebar="closeSidebar"
          @select-chapter="selectChapter"
          @generate-chapter="openGenerateChapterModal"
          @edit-chapter="openEditChapterModal"
          @delete-chapter="deleteChapter"
          @generate-outline="generateOutline"
        />

        <div class="m3-workspace__pane min-w-0 min-h-0 flex-1">
          <WDWorkspace
            ref="workspaceRef"
            :project="project"
            :selected-chapter-number="selectedChapterNumber"
            :generating-chapter="generatingChapter"
            :evaluating-chapter="evaluatingChapter"
            :show-version-selector="showVersionSelector"
            :chapter-generation-result="chapterGenerationResult"
            :selected-version-index="selectedVersionIndex"
            :compare-version-index="compareVersionIndex"
            :available-versions="availableVersions"
            :is-selecting-version="isSelectingVersion"
            :deleting-version-index="deletingVersionIndex"
            :optimizer-suggestion-notes="optimizerSuggestionNotes"
            :generation-runtime="generationRuntime"
            :last-status-sync-at="lastStatusSyncAt"
            :terminating-chapter="terminatingChapter"
            :status-fetch-failure-count="statusFetchFailureCount"
            :sidebar-open="sidebarOpen"
            :evaluating-version-index="evaluatingVersionIndex"
            :save-chapter-content="editChapterContent"
            @regenerate-chapter="regenerateChapter"
            @evaluate-chapter="evaluateChapter"
            @evaluate-all-versions="evaluateAllVersions"
            @evaluate-version="evaluateChapter"
            @optimize-version="optimizeVersion"
            @terminate-chapter="terminateChapter"
            @hide-version-selector="hideVersionSelector"
            @update:selected-version-index="selectedVersionIndex = $event"
            @update:compare-version-index="compareVersionIndex = $event"
            @open-version-diff="handleOpenVersionDiff"
            @show-version-detail="showVersionDetail"
            @confirm-version-selection="confirmVersionSelection"
            @delete-version="deleteVersion"
            @generate-chapter="openGenerateChapterModal"
            @show-evaluation-detail="handleShowEvaluationDetail"
            @fetch-chapter-status="fetchChapterStatus"
            @chapter-updated="syncUpdatedChapter"
            @consume-optimizer-suggestion="optimizerSuggestionNotes = ''"
            @toggle-sidebar="toggleSidebar"
            @select-chapter="selectChapter"
            @openPatchDiff="openPatchDiffModal"
          />
        </div>
      </div>
    </main>

    <Teleport to="body">
      <div v-if="showShortcutHelp" class="md-dialog-overlay" @click.self="showShortcutHelp = false">
        <div class="md-dialog m3-shortcut-dialog">
          <div class="flex items-center justify-between mb-5 gap-4">
            <div>
              <h3 class="md-title-large font-semibold">工作台快捷键</h3>
              <p class="md-body-small md-on-surface-variant mt-1">支持自定义显示方案；当前快捷键会避免在输入框和编辑器里误触发。</p>
            </div>
            <button class="md-icon-btn md-ripple" @click="showShortcutHelp = false">×</button>
          </div>
          <div class="m3-shortcut-grid">
            <div v-for="item in shortcutItems" :key="item.label" class="m3-shortcut-item">
              <kbd>{{ item.key }}</kbd>
              <span>{{ item.label }}</span>
            </div>
          </div>
          <div class="m3-shortcut-config">
            <div class="m3-shortcut-config__row">
              <label>主动作</label>
              <input v-model="shortcutConfig.primaryAction" class="md-text-field-input" type="text" placeholder="例如 Ctrl/Cmd + Enter">
            </div>
            <div class="m3-shortcut-config__row">
              <label>生成章节</label>
              <input v-model="shortcutConfig.generateChapter" class="md-text-field-input" type="text" placeholder="例如 Ctrl/Cmd + Shift + G">
            </div>
            <div class="m3-shortcut-config__row">
              <label>展开全文</label>
              <input v-model="shortcutConfig.openReader" class="md-text-field-input" type="text" placeholder="例如 Ctrl/Cmd + Shift + F">
            </div>
            <div class="m3-shortcut-config__row">
              <label>刷新状态</label>
              <input v-model="shortcutConfig.refreshStatus" class="md-text-field-input" type="text" placeholder="例如 Ctrl/Cmd + .">
            </div>
            <div class="m3-shortcut-config__row">
              <label>上一章</label>
              <input v-model="shortcutConfig.prevChapter" class="md-text-field-input" type="text" placeholder="例如 Alt + P">
            </div>
            <div class="m3-shortcut-config__row">
              <label>下一章</label>
              <input v-model="shortcutConfig.nextChapter" class="md-text-field-input" type="text" placeholder="例如 Alt + N">
            </div>
            <div class="m3-shortcut-config__row">
              <label>打开面板</label>
              <input v-model="shortcutConfig.openShortcuts" class="md-text-field-input" type="text" placeholder="例如 ?">
            </div>
            <div class="m3-shortcut-config__actions">
              <button class="md-btn md-btn-outlined md-ripple" @click="saveShortcutConfig({ ...DEFAULT_SHORTCUT_CONFIG })">恢复默认</button>
              <button class="md-btn md-btn-filled md-ripple" @click="saveShortcutConfig(shortcutConfig)">保存显示配置</button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <WDVersionDetailModal
      v-if="showVersionDetailModal"
      :show="showVersionDetailModal"
      :detail-version-index="detailVersionIndex"
      :version="availableVersions[detailVersionIndex] || null"
      :is-current="isCurrentVersion(detailVersionIndex)"
      @close="closeVersionDetail"
      @select-version="selectVersionFromDetail"
    />
    <WDEvaluationDetailModal
      v-if="showEvaluationDetailModal"
      :show="showEvaluationDetailModal"
      :evaluation="evaluationToShow"
      @regenerate="handleRegenerateFromEvaluation"
      @optimize="handleOptimizeFromEvaluation"
      @close="showEvaluationDetailModal = false"
    />
    <WDEditChapterModal
      v-if="showEditChapterModal"
      :show="showEditChapterModal"
      :chapter="editingChapter"
      :is-rewriting="isRewritingOutline"
      :is-saving="isSavingOutline"
      @close="showEditChapterModal = false"
      @save="saveChapterChanges"
      @rewrite="rewriteChapterSummary"
    />
    <WDGenerateOutlineModal
      v-if="showGenerateOutlineModal"
      :show="showGenerateOutlineModal"
      @close="showGenerateOutlineModal = false"
      @generate="handleGenerateOutline"
    />
    <WDGenerateChapterModal
      v-if="showGenerateChapterModal"
      :show="showGenerateChapterModal"
      :project-id="project?.id"
      :chapter-number="pendingGenerateChapterNumber"
      :initial-writing-notes="generateChapterSeed.writingNotes"
      :initial-quality-requirements="generateChapterSeed.qualityRequirements"
      :initial-min-word-count="generateChapterSeed.minWordCount"
      :initial-target-word-count="generateChapterSeed.targetWordCount"
      @close="closeGenerateChapterModal"
      @generate="handleGenerateChapter"
    />
    <WDVersionDiffModal
      v-if="showVersionDiffModal"
      :show="showVersionDiffModal"
      :project-id="project?.id || ''"
      :chapter-number="selectedChapterNumber || 1"
      :base-version-id="versionDiffBaseVersionId"
      :compare-version-id="versionDiffCompareVersionId"
      :base-label="versionDiffBaseLabel"
      :compare-label="versionDiffCompareLabel"
      @close="closeVersionDiffModal"
    />
    <WDPatchDiffModal
      v-if="showPatchDiffModal"
      :show="showPatchDiffModal"
      :project-id="project?.id || ''"
      :chapter-number="patchDiffChapterNumber || selectedChapterNumber || 1"
      :initial-original="patchDiffInitialOriginal"
      :initial-patched="patchDiffInitialPatched"
      @close="closePatchDiffModal"
      @applied="handlePatchApplied"
    />
    <WDSkillSelectorModal
      v-if="showSkillSelectorModal"
      :show="showSkillSelectorModal"
      :project-id="project?.id || ''"
      :chapter-number="selectedChapterNumber"
      @close="showSkillSelectorModal = false"
    />

    <Teleport to="body">
      <div
        v-if="showCandidateOptimizeDialog"
        class="md-dialog-overlay"
        @click.self="closeCandidateOptimizeDialog()"
      >
        <div class="md-dialog wd-candidate-optimize-dialog">
          <div class="wd-candidate-optimize-result__head">
            <div>
              <h3 class="md-title-large font-semibold">优化候选版本</h3>
              <p class="md-body-small md-on-surface-variant mt-1">
                先选择一个优化维度，再补充你想强化的方向；生成后会先显示预览，不会直接覆盖正文。
              </p>
            </div>
            <button
              type="button"
              class="md-icon-btn md-ripple"
              @click="closeCandidateOptimizeDialog()"
            >
              ×
            </button>
          </div>
          <div class="wd-candidate-optimize-dialog__body">
            <div class="wd-candidate-optimize-grid">
              <button
                v-for="dim in OPTIMIZE_DIMENSIONS"
                :key="dim.key"
                type="button"
                :class="['wd-candidate-optimize-option', candidateSelectedDimension === dim.key ? 'wd-candidate-optimize-option--active' : '']"
                @click="candidateSelectedDimension = dim.key"
              >
                <strong>{{ dim.label }}</strong>
                <span>{{ dim.description }}</span>
              </button>
            </div>
            <textarea
              v-model="candidateAdditionalNotes"
              rows="4"
              class="md-textarea w-full resize-none mt-5"
              placeholder="补充你想强化的效果，例如：增强压迫感、让潜台词更尖锐、把环境描写再压暗一点。"
            ></textarea>
          </div>
          <div class="wd-candidate-optimize-result__foot">
            <button
              type="button"
              class="md-btn md-btn-outlined md-ripple"
              @click="closeCandidateOptimizeDialog()"
            >
              取消
            </button>
            <button
              type="button"
              class="md-btn md-btn-filled md-ripple"
              :disabled="isOptimizingCandidateVersion"
              @click="generateCandidateOptimization"
            >
              {{ isOptimizingCandidateVersion ? '生成中...' : '生成优化预览' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div
        v-if="showCandidateOptimizeResultModal"
        class="md-dialog-overlay"
        @click.self="resetCandidateOptimizationState"
      >
        <div class="md-dialog wd-candidate-optimize-result">
          <div class="wd-candidate-optimize-result__head">
            <div>
              <h3 class="md-title-large font-semibold">候选版本优化结果预览</h3>
              <p class="md-body-small md-on-surface-variant mt-1">
                {{ candidateOptimizeResultNotes || '已生成优化稿，请确认是否应用为新的章节版本。' }}
              </p>
            </div>
            <button
              type="button"
              class="md-icon-btn md-ripple"
              @click="resetCandidateOptimizationState"
            >
              ×
            </button>
          </div>
          <div class="wd-candidate-optimize-result__body">{{ candidateOptimizedContent }}</div>
          <div class="wd-candidate-optimize-result__foot">
            <button
              type="button"
              class="md-btn md-btn-outlined md-ripple"
              @click="resetCandidateOptimizationState"
            >
              取消
            </button>
            <button
              type="button"
              class="md-btn md-btn-filled md-ripple"
              :disabled="isApplyingCandidateOptimization"
              @click="applyCandidateOptimization"
            >
              {{ isApplyingCandidateOptimization ? '应用中...' : '应用优化结果' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onMounted, onUnmounted, ref, watch, watchEffect } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getActivePinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'
import { useNovelStore } from '@/stores/novel'
import {
  ApiError,
  type ApiErrorDetail,
  type Chapter,
  type ChapterGenerationResponse,
  type ChapterOutline,
  type ChapterVersion,
  type OptimizeResponse,
} from '@/api/novel'
import { normalizeChapterContent } from '@/utils/chapterContent'
import { OptimizerAPI } from '@/api/novel'
import {
  canCancelGeneration,
  getBlockingChapterNumber,
  isBusyChapterStatus,
  isBusyTask,
  isRecoverableVersionStatus,
  isTrackableTask,
  normalizeRuntimeStage,
  resolveChapterActionDecision,
  resolveChapterRuntime,
  resolveProjectTaskContext,
} from '@/utils/chapterGeneration'
import { globalAlert } from '@/composables/useAlert'
import { getChapterGenerationStatus } from '@/api/modules/chapterWorkflow'
import {
  WDHeader,
  WDSidebar,
  WDWorkspace,
  WDGenerateOutlineModal
} from '@/components/writing-desk'

const WDEvaluationDetailModal = defineAsyncComponent(() => import('@/components/writing-desk/dialogs/WDEvaluationDetailModal.vue'))
const WDEditChapterModal = defineAsyncComponent(() => import('@/components/writing-desk/dialogs/WDEditChapterModal.vue'))
const WDGenerateChapterModal = defineAsyncComponent(() => import('@/components/writing-desk/dialogs/WDGenerateChapterModal.vue'))
const WDSkillSelectorModal = defineAsyncComponent(() => import('@/components/writing-desk/dialogs/WDSkillSelectorModal.vue'))
const WDVersionDetailModal = defineAsyncComponent(() => import('@/components/writing-desk/dialogs/WDVersionDetailModal.vue'))
const WDVersionDiffModal = defineAsyncComponent(() => import('@/components/writing-desk/dialogs/WDVersionDiffModal.vue'))
const WDPatchDiffModal = defineAsyncComponent(() => import('@/components/writing-desk/dialogs/WDPatchDiffModal.vue'))

interface Props {
  id: string
}

interface GenerateOutlinePayload {
  numChapters: number
  targetTotalChapters?: number
  targetTotalWords?: number
  chapterWordTarget?: number
}

interface GenerateChapterPayload {
  chapterNumber: number
  writingNotes?: string
  qualityRequirements?: string
  minWordCount: number
  targetWordCount: number
  preset?: 'basic' | 'enhanced' | 'longform' | 'ultimate'
}

interface VersionOption {
  originalIndex: number
  version: ChapterVersion
}

const props = defineProps<Props>()
const router = useRouter()
const route = useRoute()
const authStore = getActivePinia() ? useAuthStore() : null
const novelStore = useNovelStore()

const selectedChapterNumber = ref<number | null>(null)
const chapterGenerationResult = ref<ChapterGenerationResponse | null>(null)
const selectedVersionIndex = ref(0)
const compareVersionIndex = ref<number | null>(null)
const generatingChapter = ref<number | null>(null)
const sidebarOpen = ref(true)
const headerCollapsed = ref(false)
const showVersionDetailModal = ref(false)
const detailVersionIndex = ref(0)
const showEvaluationDetailModal = ref(false)
const evaluationToShow = ref<string | null>(null)
const showEditChapterModal = ref(false)
const editingChapter = ref<ChapterOutline | null>(null)
const showGenerateOutlineModal = ref(false)
const showGenerateChapterModal = ref(false)
const pendingGenerateChapterNumber = ref<number | null>(null)
const showShortcutHelp = ref(false)
const isGeneratingOutline = ref(false)
const isRewritingOutline = ref(false)
const isSavingOutline = ref(false)
const evaluatingVersionIndex = ref<number | null>(null)
const deletingVersionIndex = ref<number | null>(null)
const workspaceRef = ref<{
  openPrimaryReader: () => void
  openVersionSelector: () => void
} | null>(null)
const generateChapterSeed = ref<{
  writingNotes?: string
  qualityRequirements?: string
  minWordCount?: number
  targetWordCount?: number
  enableConsistency?: boolean
  enableEnrichment?: boolean
  enableSelfCritique?: boolean
  enableReaderSim?: boolean
  enableMemory?: boolean
  enableForeshadowing?: boolean
}>({})
const optimizerSuggestionNotes = ref('')
const lastStatusSyncAt = ref<string | null>(null)
const terminatingChapter = ref<number | null>(null)
const lastStatusFetchErrorAt = ref(0)
const statusFetchFailureCount = ref(0)
const statusPollingTimer = ref<number | null>(null)
const showPatchDiffModal = ref(false)

interface UiDiagnostics {
  message: string
  title?: string
  requestId?: string
  rootCause?: string
  code?: string
  hint?: string
  status?: number
  retryable?: boolean
  responseSnippet?: string
  rejectionSummary?: Record<string, any>
  missingChapters?: number[]
}

const latestUiDiagnostics = ref<UiDiagnostics | null>(null)
const showVersionDiffModal = ref(false)
const showSkillSelectorModal = ref(false)
const patchDiffInitialOriginal = ref('')
const patchDiffInitialPatched = ref('')
const patchDiffChapterNumber = ref<number | null>(null)
const versionDiffBaseVersionId = ref<number | null>(null)
const versionDiffCompareVersionId = ref<number | null>(null)
const versionDiffBaseLabel = ref('')
const versionDiffCompareLabel = ref('')
const showCandidateOptimizeDialog = ref(false)
const showCandidateOptimizeResultModal = ref(false)
const candidateOptimizedContent = ref('')
const candidateOptimizeResultNotes = ref('')
const candidateOptimizeVersionIndex = ref<number | null>(null)
const candidateSelectedDimension = ref<'dialogue' | 'environment' | 'psychology' | 'rhythm'>('rhythm')
const candidateAdditionalNotes = ref('')
const isOptimizingCandidateVersion = ref(false)
const isApplyingCandidateOptimization = ref(false)
const shortcutConfigStorageKey = 'xuanqiong_wenshu_shortcut_config'

interface ShortcutConfig {
  primaryAction: string
  generateChapter: string
  openReader: string
  refreshStatus: string
  prevChapter: string
  nextChapter: string
  openShortcuts: string
}

const DEFAULT_MIN_WORD_COUNT = 4500
const DEFAULT_TARGET_WORD_COUNT = 5000
const OPTIMIZE_DIMENSIONS = [
  { key: 'dialogue', label: '对话', description: '让人物声音更有区分度，并强化潜台词。' },
  { key: 'environment', label: '环境', description: '增强场景氛围，让空间参与叙事。' },
  { key: 'psychology', label: '心理', description: '深入角色内心，增加真实波动。' },
  { key: 'rhythm', label: '节奏', description: '优化句式长短和段落推进感。' }
] as const
const DEFAULT_SHORTCUT_CONFIG: ShortcutConfig = {
  primaryAction: 'Ctrl/Cmd + Enter',
  generateChapter: 'Ctrl/Cmd + Shift + G',
  openReader: 'Ctrl/Cmd + Shift + F',
  refreshStatus: 'Ctrl/Cmd + .',
  prevChapter: 'Alt + P',
  nextChapter: 'Alt + N',
  openShortcuts: '?'
}

const normalizeShortcutConfig = (config: ShortcutConfig): ShortcutConfig => ({
  primaryAction: config.primaryAction?.trim() || DEFAULT_SHORTCUT_CONFIG.primaryAction,
  generateChapter: config.generateChapter?.trim() || DEFAULT_SHORTCUT_CONFIG.generateChapter,
  openReader: config.openReader?.trim() || DEFAULT_SHORTCUT_CONFIG.openReader,
  refreshStatus: config.refreshStatus?.trim() || DEFAULT_SHORTCUT_CONFIG.refreshStatus,
  prevChapter: config.prevChapter?.trim() || DEFAULT_SHORTCUT_CONFIG.prevChapter,
  nextChapter: config.nextChapter?.trim() || DEFAULT_SHORTCUT_CONFIG.nextChapter,
  openShortcuts: config.openShortcuts?.trim() || DEFAULT_SHORTCUT_CONFIG.openShortcuts,
})

const loadShortcutConfig = (): ShortcutConfig => {
  try {
    const raw = localStorage.getItem(shortcutConfigStorageKey)
    if (!raw) return { ...DEFAULT_SHORTCUT_CONFIG }
    return normalizeShortcutConfig({ ...DEFAULT_SHORTCUT_CONFIG, ...JSON.parse(raw) })
  } catch (err: unknown) {
        if (err instanceof TypeError || (err as any)?.code === 'ECONNREFUSED') {
          // Backend disconnected - show friendly message
          console.warn('[WritingDesk] Backend connection lost, will retry...')
          scheduleStatusPolling()  // Retry silently
          return
        }
    return { ...DEFAULT_SHORTCUT_CONFIG }
  }
}

const saveShortcutConfig = (config: ShortcutConfig) => {
  const normalized = normalizeShortcutConfig(config)
  shortcutConfig.value = normalized
  try {
    localStorage.setItem(shortcutConfigStorageKey, JSON.stringify(normalized))
    globalAlert.showSuccess('快捷键显示配置已保存', '保存成功')
  } catch (err: unknown) {
        if (err instanceof TypeError || (err as any)?.code === 'ECONNREFUSED') {
          // Backend disconnected - show friendly message
          console.warn('[WritingDesk] Backend connection lost, will retry...')
          scheduleStatusPolling()  // Retry silently
          return
        }
    globalAlert.showError('保存快捷键配置失败，请检查浏览器存储权限', '保存失败')
  }
}

const project = computed(() => novelStore.currentProject)
const workspaceSummary = computed(() => project.value?.workspace_summary || null)
const activeStyleProfile = ref<any | null>(null)
const selectedChapter = computed(() => {
  if (!project.value || selectedChapterNumber.value === null) return null
  return project.value.chapters.find((chapter) => chapter.chapter_number === selectedChapterNumber.value) || null
})
const generationRuntime = computed(() =>
  resolveChapterRuntime(selectedChapter.value, project.value?.generation_runtime || null)
)
const showVersionSelector = computed(() =>
  isRecoverableVersionStatus(selectedChapter.value?.generation_status)
)
const evaluatingChapter = computed(() =>
  selectedChapter.value?.generation_status === 'evaluating'
    ? selectedChapter.value.chapter_number
    : null
)
const isSelectingVersion = computed(() => selectedChapter.value?.generation_status === 'selecting')
const outlineOrChapterNumbers = computed(() => {
  const outlineNumbers = project.value?.blueprint?.chapter_outline?.map((chapter) => chapter.chapter_number) || []
  if (outlineNumbers.length) return outlineNumbers
  return (project.value?.chapters || []).map((chapter) => chapter.chapter_number)
})

const totalChapters = computed(
  () => workspaceSummary.value?.total_chapters || outlineOrChapterNumbers.value.length || 0
)
const completedChapters = computed(() => workspaceSummary.value?.completed_chapters || 0)
const progress = computed(() =>
  totalChapters.value ? Math.round((completedChapters.value / totalChapters.value) * 100) : 0
)
const versionOptions = computed<VersionOption[]>(() => {
  const sourceVersions = chapterGenerationResult.value?.versions?.length
    ? chapterGenerationResult.value.versions
    : selectedChapter.value?.versions || []

  return sourceVersions
    .map((version, originalIndex) => ({ originalIndex, version }))
    .filter(({ version }) => normalizeChapterContent(version.content).length > 0)
})

const availableVersions = computed(() => versionOptions.value.map(({ version }) => version))
const getOriginalVersionIndex = (versionIndex: number) => versionOptions.value[versionIndex]?.originalIndex
const legacyShortcutItems = [
  { key: 'Alt + P', label: '上一章' },
  { key: 'Alt + N', label: '下一章' },
  { key: 'Alt + G', label: '生成或重新生成当前章节' },
  { key: 'Alt + E', label: '评估当前章节' },
  { key: 'Alt + S', label: '确认当前版本' },
  { key: 'Alt + L', label: '显示或收起目录' },
  { key: 'Shift + ?', label: '打开快捷键帮助' },
  { key: 'Esc', label: '关闭当前弹层' }
]

const shortcutConfig = ref<ShortcutConfig>(normalizeShortcutConfig(loadShortcutConfig()))

const shortcutItems = computed(() => [
  { key: shortcutConfig.value.primaryAction, label: '执行当前主动作' },
  { key: shortcutConfig.value.generateChapter, label: '生成当前章节' },
  { key: shortcutConfig.value.openReader, label: '展开全文阅读' },
  { key: shortcutConfig.value.refreshStatus, label: '刷新当前状态' },
  { key: 'Patch+Diff', label: '对当前章节进行精细编辑' },
  { key: '写作技能', label: '打开技能市场并执行技能' },
  { key: shortcutConfig.value.openShortcuts, label: '打开快捷键面板' },
  { key: 'Esc', label: '关闭当前弹层或侧栏' }
])

const selectedChapterAction = computed(() => {
  if (selectedChapterNumber.value === null) return null
  return resolveChapterActionDecision(project.value, selectedChapterNumber.value, {
    generatingChapter: generatingChapter.value,
    evaluatingChapter: evaluatingChapter.value,
  })
})

const canGenerateSelectedChapter = computed(() => {
  const busyStatus = selectedChapter.value?.generation_status
  if (isBusyChapterStatus(busyStatus)) return false
  if (selectedChapterNumber.value !== null && ['waiting_for_confirm', 'evaluation_failed', 'failed'].includes(String(busyStatus || ''))) {
    return true
  }
  if (isRecoverableVersionStatus(busyStatus)) return false
  if (selectedChapterNumber.value === null) {
    return Boolean(workspaceSummary.value?.next_chapter_to_generate)
  }
  return Boolean(selectedChapterAction.value?.canGenerate)
})

const isCurrentChapterBusy = computed(() => {
  const status = selectedChapter.value?.generation_status
  if (isRecoverableVersionStatus(status)) return false
  return isBusyTask(selectedChapter.value, generationRuntime.value)
})
const isCurrentChapterTrackable = computed(() =>
  isTrackableTask(selectedChapter.value, generationRuntime.value)
)
const canOpenVersionsSelectedChapter = computed(() => availableVersions.value.length > 0)
const canReviewAllVersionsSelectedChapter = computed(() => availableVersions.value.length > 1 && !isCurrentChapterBusy.value)
const taskContext = computed(() => resolveProjectTaskContext(project.value || null, selectedChapter.value, latestUiDiagnostics.value))
const taskPanelChapter = computed(() => taskContext.value.chapter)
const taskPanelChapterNumber = computed(() => taskContext.value.chapterNumber)
const taskPanelRuntime = computed(() => taskContext.value.runtime)
const hasTrackableTaskPanel = computed(() =>
  Boolean(taskPanelChapterNumber.value) && isTrackableTask(taskPanelChapter.value, taskPanelRuntime.value)
)

const generateCurrentLabel = computed(() => {
  const target = selectedChapterNumber.value ?? workspaceSummary.value?.next_chapter_to_generate
  const status = String(selectedChapter.value?.generation_status || '')

  if (selectedChapterNumber.value !== null && ['waiting_for_confirm', 'evaluation_failed', 'failed', 'successful'].includes(status)) {
    return '重新生成'
  }

  if (selectedChapterAction.value?.canGenerate && selectedChapterAction.value.label) {
    return selectedChapterAction.value.label === '生成本章' && target
      ? `生成第 ${target} 章`
      : selectedChapterAction.value.label
  }
  if (target) return `生成第 ${target} 章`
  return '开始创作'
})

const canEvaluateSelectedChapter = computed(() => selectedChapter.value?.generation_status === 'successful')
const canConfirmSelectedChapter = computed(() => {
  const status = selectedChapter.value?.generation_status
  return status === 'waiting_for_confirm' || status === 'evaluation_failed'
})
const canTerminateSelectedChapter = computed(() => {
  if (selectedChapterNumber.value === null) return false
  return canCancelGeneration(selectedChapter.value, generationRuntime.value)
})

const orderedChapterNumbers = computed(() => [...outlineOrChapterNumbers.value].sort((a, b) => a - b))

const hasPrevChapter = (current: number | null) => {
  if (current === null) return false
  return orderedChapterNumbers.value.some((chapterNumber) => chapterNumber < current)
}

const hasNextChapter = (current: number | null) => {
  if (current === null) return false
  return orderedChapterNumbers.value.some((chapterNumber) => chapterNumber > current)
}

const canSelectPrevChapter = computed(() => orderedChapterNumbers.value.length > 0)
const canSelectNextChapter = computed(() => {
  if (orderedChapterNumbers.value.length > 0) return true
  if (selectedChapterNumber.value === null) return false
  if (hasNextChapter(selectedChapterNumber.value)) return true
  return Boolean(
    workspaceSummary.value?.next_chapter_to_generate &&
      workspaceSummary.value.next_chapter_to_generate !== selectedChapterNumber.value
  )
})

const isCurrentVersion = (versionIndex: number) => {
  const version = availableVersions.value[versionIndex]
  if (selectedChapter.value?.selected_version_id && version?.id) {
    return selectedChapter.value.selected_version_id === version.id
  }
  if (!selectedChapter.value?.content || !version?.content) return false
  return (
    normalizeChapterContent(selectedChapter.value.content) ===
    normalizeChapterContent(version.content)
  )
}

const goBack = () => router.push('/workspace')
const viewProjectDetail = () => {
  if (project.value) router.push(`/detail/${project.value.id}`)
}
const openAdminPanel = () => {
  router.push('/admin')
}
const openRuntimeLogs = () => {
  const query: Record<string, string> = { tab: 'runtime-logs' }
  if (project.value?.id) query.project_id = project.value.id
  if (selectedChapter.value?.chapter_number) query.chapter = String(selectedChapter.value.chapter_number)
  router.push({ path: '/admin', query })
}
const toggleSidebar = () => {
  sidebarOpen.value = !sidebarOpen.value
}
const closeSidebar = () => {
  sidebarOpen.value = false
}

const pickInitialChapter = () => {
  if (!outlineOrChapterNumbers.value.length) {
    selectedChapterNumber.value = null
    return
  }
  const validNumbers = new Set(outlineOrChapterNumbers.value)
  if (selectedChapterNumber.value !== null && validNumbers.has(selectedChapterNumber.value)) return
  selectedChapterNumber.value =
    workspaceSummary.value?.active_chapter ??
    workspaceSummary.value?.first_incomplete_chapter ??
    workspaceSummary.value?.next_chapter_to_generate ??
    orderedChapterNumbers.value[0] ??
    null
}

const resetWorkspaceState = () => {
  selectedChapterNumber.value = null
  resetVersionSelectionState()
  generatingChapter.value = null
  detailVersionIndex.value = 0
  showVersionDetailModal.value = false
  resetCandidateOptimizationState()
  showEvaluationDetailModal.value = false
  evaluationToShow.value = null
  showEditChapterModal.value = false
  editingChapter.value = null
  showGenerateOutlineModal.value = false
  showGenerateChapterModal.value = false
  pendingGenerateChapterNumber.value = null
  isGeneratingOutline.value = false
  isRewritingOutline.value = false
  isSavingOutline.value = false
  evaluatingVersionIndex.value = null
  deletingVersionIndex.value = null
  optimizerSuggestionNotes.value = ''
  lastStatusSyncAt.value = null
  terminatingChapter.value = null
  lastStatusFetchErrorAt.value = 0
  statusFetchFailureCount.value = 0
  showPatchDiffModal.value = false
  showSkillSelectorModal.value = false
  patchDiffInitialOriginal.value = ''
  patchDiffInitialPatched.value = ''
  patchDiffChapterNumber.value = null
}

const normalizeUiDiagnostics = (error: unknown, fallbackMessage: string, title?: string): UiDiagnostics => {
  if (error instanceof ApiError) {
    const detail: ApiErrorDetail = error.detail
    return {
      message: detail.message || fallbackMessage,
      title,
      requestId: detail.requestId,
      rootCause: detail.rootCause,
      code: detail.code,
      hint: detail.hint,
      status: detail.status,
      retryable: detail.retryable,
      responseSnippet: detail.responseSnippet,
      rejectionSummary: detail.rejectionSummary,
      missingChapters: detail.missingChapters,
    }
  }

  if (error instanceof Error) {
    return {
      message: error.message || fallbackMessage,
      title,
    }
  }

  return {
    message: fallbackMessage,
    title,
  }
}

const formatUiDiagnosticsMessage = (
  diagnostics: UiDiagnostics,
  options: { includeRootCause?: boolean; includeRequestId?: boolean; includeHint?: boolean } = {}
) => {
  const lines = [diagnostics.message]
  if (options.includeRootCause && diagnostics.rootCause) lines.push(`根因：${diagnostics.rootCause}`)
  if (options.includeRequestId && diagnostics.requestId) lines.push(`请求ID：${diagnostics.requestId}`)
  if (options.includeHint && diagnostics.hint) lines.push(`建议：${diagnostics.hint}`)
  if (diagnostics.missingChapters?.length) lines.push(`未通过章节：${diagnostics.missingChapters.join('、')}`)
  if (diagnostics.rejectionSummary) {
    const summary = diagnostics.rejectionSummary
    const missing = Array.isArray(summary.missing_chapters) ? summary.missing_chapters.length : undefined
    const retries = summary.retry_count ?? summary.retries
    lines.push(`硬筛摘要：${[
      missing !== undefined ? `${missing} 章未达标` : '',
      retries !== undefined ? `重试 ${retries} 次` : '',
    ].filter(Boolean).join('，') || '已返回详细拒绝原因'}`)
  }
  return lines.join('\n')
}

const setLatestDiagnostics = (diagnostics: UiDiagnostics | null) => {
  latestUiDiagnostics.value = diagnostics
}

const clearLatestDiagnostics = () => {
  latestUiDiagnostics.value = null
}

const loadActiveStyleProfile = async () => {
  if (!props.id) return
  try {
    const res = await OptimizerAPI.getActiveStyleProfile(props.id)
    activeStyleProfile.value = res.profile || null
  } catch (error) {
    const diagnostics = normalizeUiDiagnostics(error, '加载当前激活文风失败')
    console.warn('加载当前激活文风失败:', diagnostics)
    activeStyleProfile.value = null
  }
}

const markProjectSynced = () => {
  lastStatusSyncAt.value = new Date().toISOString()
}

const syncChapterStatusIntoProject = (chapterStatus: Chapter) => {
  const currentProject = project.value
  if (!currentProject) return
  const chapters = Array.isArray(currentProject.chapters) ? currentProject.chapters : []
  const index = chapters.findIndex((item) => item.chapter_number === chapterStatus.chapter_number)
  if (index >= 0) {
    const previous = chapters[index]
    chapters.splice(index, 1, {
      ...previous,
      ...chapterStatus,
      content: chapterStatus.content ?? previous?.content,
      versions: chapterStatus.versions ?? previous?.versions,
      evaluation: chapterStatus.evaluation ?? previous?.evaluation,
    })
  } else {
    chapters.push(chapterStatus)
    chapters.sort((a, b) => a.chapter_number - b.chapter_number)
  }
  novelStore.setCurrentProject({
    ...currentProject,
    chapters: [...chapters],
  })
  markProjectSynced()
}

const refreshProjectState = async (silent: boolean = true, throwOnError: boolean = true) => {
  await Promise.all([
    novelStore.loadProject(props.id, silent, throwOnError),
    loadActiveStyleProfile(),
  ])
  markProjectSynced()
}

const syncSingleChapterStatus = async (chapterNumber?: number | null) => {
  if (!project.value?.id || chapterNumber === null || chapterNumber === undefined) {
    await refreshProjectState(true, true)
    return null
  }
  const chapterStatus = await getChapterGenerationStatus(project.value.id, chapterNumber)
  syncChapterStatusIntoProject(chapterStatus)
  return chapterStatus
}

const loadProject = async () => {
  try {
    await refreshProjectState(false, true)
    clearLatestDiagnostics()
    pickInitialChapter()
  } catch (error) {
    const diagnostics = normalizeUiDiagnostics(error, '加载项目失败，请稍后重试', '加载失败')
    setLatestDiagnostics(diagnostics)
    console.error('加载项目失败:', diagnostics)
    globalAlert.showError(
      formatUiDiagnosticsMessage(diagnostics, { includeRootCause: true, includeRequestId: true, includeHint: true }),
      diagnostics.title || '加载失败'
    )
  }
}

const statusFetchPromise = ref<Promise<void> | null>(null)

const fetchChapterStatus = async () => {
  if (statusFetchPromise.value) {
    return statusFetchPromise.value
  }

  statusFetchPromise.value = (async () => {
    try {
      const targetChapterNumber = selectedChapterNumber.value ?? taskPanelChapterNumber.value
      await syncSingleChapterStatus(targetChapterNumber)
      statusFetchFailureCount.value = 0
      if (latestUiDiagnostics.value?.title === '状态同步失败') {
        clearLatestDiagnostics()
      }
    } catch (error) {
      const diagnostics = normalizeUiDiagnostics(error, '刷新状态失败，请稍后重试', '状态同步失败')
      console.warn('刷新章节状态失败:', diagnostics)
      statusFetchFailureCount.value += 1
      setLatestDiagnostics({
        ...diagnostics,
        hint: diagnostics.hint || (statusFetchFailureCount.value >= 2 ? '建议直接终止处理后再重试。' : diagnostics.hint),
      })
      const now = Date.now()
      if (now - lastStatusFetchErrorAt.value > 10_000) {
        lastStatusFetchErrorAt.value = now
        const suffix =
          statusFetchFailureCount.value >= 2
            ? `（已连续失败 ${statusFetchFailureCount.value} 次，建议直接终止处理后再重试）`
            : ''
        globalAlert.showError(
          `${formatUiDiagnosticsMessage(diagnostics, { includeRootCause: true, includeRequestId: true })}${suffix}`,
          diagnostics.title || '状态同步失败'
        )
      }
    } finally {
      statusFetchPromise.value = null
    }
  })()

  return statusFetchPromise.value
}

const clearStatusPolling = () => {
  if (statusPollingTimer.value !== null) {
    window.clearTimeout(statusPollingTimer.value)
    statusPollingTimer.value = null
  }
}

const scheduleStatusPolling = () => {
  clearStatusPolling()
  const busyChapter = project.value?.chapters?.find((chapter) =>
    isBusyTask(chapter, resolveChapterRuntime(chapter, project.value?.generation_runtime || null))
  )
  const runtime = resolveChapterRuntime(busyChapter || null, project.value?.generation_runtime || null)
  const stage = normalizeRuntimeStage(
    busyChapter?.progress_stage || runtime?.progress_stage || busyChapter?.generation_status || runtime?.status
  )
  const baseDelay = stage === 'generating' ? 1800 : stage === 'evaluating' || stage === 'selecting' ? 1200 : 2500
  const estimatedRemaining = runtime?.estimated_remaining_seconds
  const progressPercent = runtime?.progress_percent
  let delay = baseDelay
  if (typeof estimatedRemaining === 'number' && estimatedRemaining > 0) {
    if (estimatedRemaining > 120) {
      delay = Math.min(5000, baseDelay + 2000)
    } else if (estimatedRemaining > 60) {
      delay = Math.min(3500, baseDelay + 800)
    } else if (estimatedRemaining < 15) {
      delay = Math.max(800, baseDelay - 600)
    }
  } else if (typeof progressPercent === 'number' && progressPercent > 0) {
    if (progressPercent >= 85) {
      delay = Math.max(800, baseDelay - 600)
    } else if (progressPercent >= 60) {
      delay = Math.max(1200, baseDelay - 300)
    } else if (progressPercent < 25) {
      delay = Math.min(4000, baseDelay + 1200)
    }
  }
  statusPollingTimer.value = window.setTimeout(() => {
    statusPollingTimer.value = null
    void fetchChapterStatus()
  }, delay)
}

const sleep = (ms: number) => new Promise<void>((resolve) => window.setTimeout(resolve, ms))

const syncChapterAfterVersionConfirm = async (chapterNumber: number): Promise<boolean> => {
  for (let attempt = 0; attempt < 5; attempt += 1) {
    await sleep(900 + attempt * 500)
    try {
      await syncSingleChapterStatus(chapterNumber)
      const status = project.value?.chapters.find(
        (chapter) => chapter.chapter_number === chapterNumber
      )?.generation_status
      if (status && !['waiting_for_confirm', 'selecting'].includes(status)) {
        return true
      }
    } catch (error) {
      console.debug('确认版本后状态同步失败:', error)
    }
  }
  return false
}

const resetVersionSelectionState = (selectedIndex: number = 0) => {
  chapterGenerationResult.value = null
  selectedVersionIndex.value = selectedIndex
  compareVersionIndex.value = null
}

const selectChapter = (chapterNumber: number) => {
  selectedChapterNumber.value = chapterNumber
  resetVersionSelectionState()
  if (window.innerWidth < 1024) closeSidebar()
}

const selectRelativeChapter = (direction: -1 | 1) => {
  const numbers = orderedChapterNumbers.value
  if (!numbers.length) return

  const current = selectedChapterNumber.value
  if (current === null) {
    selectChapter(numbers[0])
    return
  }

  const index = numbers.findIndex((num) => num === current)
  if (index >= 0) {
    const nextIndex = Math.min(Math.max(index + direction, 0), numbers.length - 1)
    selectChapter(numbers[nextIndex])
    return
  }

  if (direction < 0) {
    const prev = [...numbers].filter((num) => num < current).pop()
    selectChapter(typeof prev === 'number' ? prev : numbers[0])
    return
  }

  const next = numbers.find((num) => num > current)
  selectChapter(typeof next === 'number' ? next : numbers[numbers.length - 1])
}

const goPrevChapter = () => {
  if (!orderedChapterNumbers.value.length) return
  if (selectedChapterNumber.value === null) {
    selectChapter(orderedChapterNumbers.value[0])
    return
  }
  if (!hasPrevChapter(selectedChapterNumber.value)) {
    selectChapter(orderedChapterNumbers.value[0])
    return
  }
  selectRelativeChapter(-1)
}

const goNextChapter = () => {
  if (!canSelectNextChapter.value) return
  if (selectedChapterNumber.value === null) {
    const suggested = workspaceSummary.value?.next_chapter_to_generate
    if (suggested) {
      selectChapter(suggested)
      return
    }
    if (orderedChapterNumbers.value.length) {
      selectChapter(orderedChapterNumbers.value[0])
    }
    return
  }
  if (hasNextChapter(selectedChapterNumber.value)) {
    selectRelativeChapter(1)
    return
  }
  const suggested = workspaceSummary.value?.next_chapter_to_generate
  if (suggested) {
    selectChapter(suggested)
  }
}

const generateChapter = async (
  chapterNumber: number,
  options?: Omit<GenerateChapterPayload, 'chapterNumber'>
) => {
  const targetChapter = project.value?.chapters?.find((item) => item.chapter_number === chapterNumber)
  const targetStatus = String(targetChapter?.generation_status || 'not_generated')
  const isRegeneratingCurrentSelectedChapter =
    selectedChapterNumber.value === chapterNumber &&
    ['waiting_for_confirm', 'evaluation_failed', 'failed'].includes(targetStatus)

  const actionDecision = resolveChapterActionDecision(project.value, chapterNumber, {
    generatingChapter: generatingChapter.value,
    evaluatingChapter: evaluatingChapter.value,
  })
  if (!actionDecision.canGenerate && !isRegeneratingCurrentSelectedChapter) {
    const blockingChapterNumber = getBlockingChapterNumber(project.value, chapterNumber)
    let message = '当前章节暂时不能直接生成。'
    if (blockingChapterNumber !== null) {
      const blockingChapter = project.value?.chapters?.find((item) => item.chapter_number === blockingChapterNumber)
      const blockingStatus = String(blockingChapter?.generation_status || 'not_generated')
      const statusLabelMap: Record<string, string> = {
        not_generated: '还没生成',
        generating: '正在生成',
        evaluating: '正在评估',
        selecting: '正在整理候选版本',
        waiting_for_confirm: '已生成候选版本，但还没有最终确认',
        failed: '生成失败',
        evaluation_failed: '评估失败'
      }
      const statusLabel = statusLabelMap[blockingStatus] || blockingStatus
      message = [
        `第 ${chapterNumber} 章现在不能直接开始，因为前面的第 ${blockingChapterNumber} 章还没收口。`,
        `当前状态：${statusLabel}。`,
        blockingStatus === 'waiting_for_confirm'
          ? '这通常表示系统已经产出了候选内容，但你还没有真正完成确认，或者你看到的是候选预览而不是最终定稿。请先点进该章查看候选版本。'
          : '请先处理前面这章，再继续往后生成。',
        chapterNumber === selectedChapterNumber.value
          ? '如果你现在操作的就是当前选中的这一章，请直接点“重新生成当前章节”；当前这次拦截本不该出现。'
          : '',
      ].filter(Boolean).join('\n')
    }
    globalAlert.showError(message, '生成受限')
    return
  }

  try {
    generatingChapter.value = chapterNumber
    selectedChapterNumber.value = chapterNumber

    await novelStore.generateChapter(chapterNumber, {
      writingNotes: options?.writingNotes,
      qualityRequirements: options?.qualityRequirements,
      minWordCount: options?.minWordCount ?? DEFAULT_MIN_WORD_COUNT,
      targetWordCount: options?.targetWordCount ?? DEFAULT_TARGET_WORD_COUNT,
      preset: options?.preset
    })

    clearLatestDiagnostics()
    resetVersionSelectionState()
    markProjectSynced()
  } catch (error) {
    const diagnostics = normalizeUiDiagnostics(error, '生成章节失败，请稍后重试', '生成失败')
    setLatestDiagnostics(diagnostics)
    console.error('生成章节失败:', diagnostics)
    try {
      await syncSingleChapterStatus(chapterNumber)
      } catch (syncError) {
        const syncDiagnostics = normalizeUiDiagnostics(syncError, '生成失败后同步项目状态失败')
        console.warn('生成失败后同步项目状态失败:', syncDiagnostics)
      }
    generatingChapter.value = null
    globalAlert.showError(
      formatUiDiagnosticsMessage(diagnostics, { includeRootCause: true, includeRequestId: true, includeHint: true }),
      diagnostics.title || '生成失败'
    )
  }
}

const openGenerateChapterModal = (
  chapterNumber: number,
  seed?: {
    writingNotes?: string
    qualityRequirements?: string
    minWordCount?: number
    targetWordCount?: number
  }
) => {
  const chapter = project.value?.chapters?.find((item) => item.chapter_number === chapterNumber)
  const runtime = resolveChapterRuntime(chapter, generationRuntime.value)
  pendingGenerateChapterNumber.value = chapterNumber
  generateChapterSeed.value = {
    writingNotes: seed?.writingNotes,
    qualityRequirements: seed?.qualityRequirements,
    minWordCount: seed?.minWordCount,
    targetWordCount: seed?.targetWordCount
  }

  if (seed?.minWordCount == null && seed?.targetWordCount == null) {
    const lastAttemptFailed = ['failed', 'evaluation_failed'].includes(String(chapter?.generation_status || ''))
    if (lastAttemptFailed) {
      generateChapterSeed.value.minWordCount = runtime?.min_word_count
      generateChapterSeed.value.targetWordCount = runtime?.target_word_count
    }
  }
  showGenerateChapterModal.value = true
}

const closeGenerateChapterModal = () => {
  showGenerateChapterModal.value = false
  generateChapterSeed.value = {}
}

const closePatchDiffModal = () => {
  showPatchDiffModal.value = false
  patchDiffChapterNumber.value = null
  patchDiffInitialOriginal.value = ''
  patchDiffInitialPatched.value = ''
}

const closeVersionDiffModal = () => {
  showVersionDiffModal.value = false
  versionDiffBaseVersionId.value = null
  versionDiffCompareVersionId.value = null
  versionDiffBaseLabel.value = ''
  versionDiffCompareLabel.value = ''
}

const handlePatchApplied = async (_data: { original: string; patched: string }) => {
  if (project.value) {
    await refreshProjectState(true, false)
    await fetchChapterStatus()
  }
}

const openPatchDiffModal = () => {
  if (selectedChapterNumber.value === null) return
  const chapterNumber = selectedChapterNumber.value
  const chapter = project.value?.chapters?.find((c) => c.chapter_number === chapterNumber)
  const normalizedContent = normalizeChapterContent(chapter?.content)
  patchDiffChapterNumber.value = chapterNumber
  patchDiffInitialOriginal.value = normalizedContent
  patchDiffInitialPatched.value = normalizedContent
  showPatchDiffModal.value = true
}

const openVersionDiffModal = (payload: {
  baseVersionId: number
  compareVersionId: number
  baseLabel: string
  compareLabel: string
}) => {
  versionDiffBaseVersionId.value = payload.baseVersionId
  versionDiffCompareVersionId.value = payload.compareVersionId
  versionDiffBaseLabel.value = payload.baseLabel
  versionDiffCompareLabel.value = payload.compareLabel
  showVersionDiffModal.value = true
}

const handleOpenVersionDiff = (payload: { baseVersionIndex: number; compareVersionIndex: number }) => {
  const baseVersion = availableVersions.value[payload.baseVersionIndex]
  const compareVersion = availableVersions.value[payload.compareVersionIndex]
  if (!baseVersion?.id || !compareVersion?.id) {
    globalAlert.showError('当前版本缺少有效标识，无法执行版本对比。请先刷新状态后重试。', '版本对比失败')
    return
  }
  openVersionDiffModal({
    baseVersionId: baseVersion.id,
    compareVersionId: compareVersion.id,
    baseLabel: `鐗堟湰 ${payload.baseVersionIndex + 1}`,
    compareLabel: `鐗堟湰 ${payload.compareVersionIndex + 1}`
  })
}

const handleGenerateChapter = async (payload: GenerateChapterPayload) => {
  generateChapterSeed.value = {}
  await generateChapter(payload.chapterNumber, {
    writingNotes: payload.writingNotes,
    qualityRequirements: payload.qualityRequirements,
    minWordCount: payload.minWordCount,
    targetWordCount: payload.targetWordCount,
    preset: payload.preset,
    enableConsistency: payload.enableConsistency,
    enableEnrichment: payload.enableEnrichment,
    enableSelfCritique: payload.enableSelfCritique,
    enableReaderSim: payload.enableReaderSim,
    enableMemory: payload.enableMemory,
    enableForeshadowing: payload.enableForeshadowing
  })
}

const handlePrimaryGenerate = () => {
  const target = selectedChapterNumber.value ?? workspaceSummary.value?.next_chapter_to_generate
  if (target === null || target === undefined) return

  const currentStatus = selectedChapter.value?.generation_status
  if (
    selectedChapterNumber.value === target &&
    ['waiting_for_confirm', 'evaluation_failed', 'failed'].includes(String(currentStatus || ''))
  ) {
    const runtime = resolveChapterRuntime(selectedChapter.value, generationRuntime.value)
    openGenerateChapterModal(target, {
      minWordCount: runtime?.min_word_count ?? DEFAULT_MIN_WORD_COUNT,
      targetWordCount: runtime?.target_word_count ?? DEFAULT_TARGET_WORD_COUNT,
    })
    return
  }

  const decision = resolveChapterActionDecision(project.value, target, {
    generatingChapter: generatingChapter.value,
    evaluatingChapter: evaluatingChapter.value,
  })
  if (decision.mode === 'navigate' && decision.targetChapterNumber) {
    selectChapter(decision.targetChapterNumber)
    return
  }
  if (!decision.canGenerate) return
  openGenerateChapterModal(target)
}

const openVersionSelectorFromHeader = () => {
  if (selectedChapterNumber.value === null || !canOpenVersionsSelectedChapter.value) return
  workspaceRef.value?.openVersionSelector?.()
  compareVersionIndex.value = null
}

const handleTerminateCurrent = () => {
  void terminateChapter(selectedChapterNumber.value ?? undefined)
}

const handlePrimaryShortcutAction = () => {
  if (canConfirmSelectedChapter.value) {
    void confirmVersionSelection()
    return
  }

  if (canGenerateSelectedChapter.value) {
    handlePrimaryGenerate()
    return
  }

  if (canEvaluateSelectedChapter.value) {
    void evaluateChapter()
  }
}

const regenerateChapter = async (chapterNumber?: number) => {
  const target = chapterNumber ?? selectedChapterNumber.value
  if (target !== null && target !== undefined) openGenerateChapterModal(target)
}

const terminateChapter = async (chapterNumber?: number) => {
  const target = chapterNumber ?? selectedChapterNumber.value
  if (target === null || target === undefined) return

  const confirmed = await globalAlert.showConfirm(
    `这会将第 ${target} 章当前后台任务标记为失败，并停止前端继续等待；如果服务端任务已经接近完成，仍可能在短时间内回写结果。是否继续？`,
    '确认终止后台处理'
  )
  if (!confirmed) return

  try {
    terminatingChapter.value = target
    await novelStore.cancelChapterGeneration(target)
    clearLatestDiagnostics()
    markProjectSynced()
    globalAlert.showSuccess(`第 ${target} 章已标记为失败，前端会停止继续等待该任务。`, '已终止')
    await fetchChapterStatus()
  } catch (error) {
    const diagnostics = normalizeUiDiagnostics(error, '终止后台处理失败，请稍后重试', '终止失败')
    setLatestDiagnostics(diagnostics)
    console.error('终止章节后台任务失败:', diagnostics)
    globalAlert.showError(
      formatUiDiagnosticsMessage(diagnostics, { includeRootCause: true, includeRequestId: true, includeHint: true }),
      diagnostics.title || '终止失败'
    )
  } finally {
    terminatingChapter.value = null
  }
}

const handleRegenerateFromEvaluation = (payload: {
  writingNotes?: string
  qualityRequirements?: string
}) => {
  if (selectedChapterNumber.value === null) {
    globalAlert.showError('当前没有选中章节，无法执行重新生成。', '操作失败')
    return
  }
  const chapter = project.value?.chapters?.find((item) => item.chapter_number === selectedChapterNumber.value)
  const runtime = resolveChapterRuntime(chapter, generationRuntime.value)
  showEvaluationDetailModal.value = false
  openGenerateChapterModal(selectedChapterNumber.value, {
    writingNotes: payload.writingNotes,
    qualityRequirements: payload.qualityRequirements,
    minWordCount: runtime?.min_word_count ?? DEFAULT_MIN_WORD_COUNT,
    targetWordCount: runtime?.target_word_count ?? DEFAULT_TARGET_WORD_COUNT
  })
}

const handleOptimizeFromEvaluation = (payload: { notes: string }) => {
  optimizerSuggestionNotes.value = payload.notes
  showEvaluationDetailModal.value = false
  globalAlert.showSuccess('优化建议已写入，可直接继续局部优化。', '建议已应用')
}

const withChapterStatusRollback = async (
  chapterNumber: number,
  task: () => Promise<void>
) => {
  const chapter = project.value?.chapters.find((item) => item.chapter_number === chapterNumber)
  const previousStatus = chapter?.generation_status
  try {
    await task()
  } catch (error) {
    if (project.value?.id) {
      try {
        await syncSingleChapterStatus(chapterNumber)
        } catch (syncError) {
          const syncDiagnostics = normalizeUiDiagnostics(syncError, '章节动作失败后同步项目状态失败')
          console.warn('章节动作失败后同步项目状态失败:', syncDiagnostics)
        const fallbackChapter = project.value?.chapters.find((item) => item.chapter_number === chapterNumber)
        if (fallbackChapter && previousStatus) fallbackChapter.generation_status = previousStatus
      }
    } else {
      const fallbackChapter = project.value?.chapters.find((item) => item.chapter_number === chapterNumber)
      if (fallbackChapter && previousStatus) fallbackChapter.generation_status = previousStatus
    }
    throw error
  }
}

const withVersionSelectionPreview = async (versionIndex: number, task: () => Promise<void>) => {
  const previousSelectedVersionIndex = selectedVersionIndex.value
  selectedVersionIndex.value = versionIndex
  try {
    await task()
  } catch (error) {
    selectedVersionIndex.value = previousSelectedVersionIndex
    throw error
  }
}

const selectVersion = async (versionIndex: number) => {
  const version = availableVersions.value[versionIndex]
  if (selectedChapterNumber.value === null || !version?.content) return
  const chapterNumber = selectedChapterNumber.value
  const originalVersionIndex = getOriginalVersionIndex(versionIndex)
  if (originalVersionIndex === undefined) return
  try {
    await withVersionSelectionPreview(versionIndex, async () => {
      await novelStore.selectChapterVersion(chapterNumber, originalVersionIndex, version.id)
      clearLatestDiagnostics()
      resetVersionSelectionState(versionIndex)
      markProjectSynced()
    })
    globalAlert.showSuccess('版本已确认', '操作成功')
    const synced = await syncChapterAfterVersionConfirm(chapterNumber)
      if (!synced) {
        const diagnostics = {
          message: '确认已提交，但后台长时间未回写新状态。请立即刷新，或直接终止处理后重试。',
          title: '状态同步提醒',
          retryable: true,
          hint: '如果再次刷新仍无回写，请终止处理并重新生成。',
      } satisfies UiDiagnostics
      setLatestDiagnostics(diagnostics)
        globalAlert.showError(
          formatUiDiagnosticsMessage(diagnostics, { includeHint: true }),
          diagnostics.title || '状态同步提醒'
        )
    }
  } catch (error) {
    const diagnostics = normalizeUiDiagnostics(error, '选择章节版本失败，请稍后重试', '选择失败')
    setLatestDiagnostics(diagnostics)
    console.error('选择章节版本失败:', diagnostics)
    globalAlert.showError(
      formatUiDiagnosticsMessage(diagnostics, { includeRootCause: true, includeRequestId: true, includeHint: true }),
      diagnostics.title || '选择失败'
    )
  }
}

const showVersionDetail = (versionIndex: number) => {
  detailVersionIndex.value = versionIndex
  showVersionDetailModal.value = true
}

const closeVersionDetail = () => {
  showVersionDetailModal.value = false
}

const selectVersionFromDetail = async () => {
  await selectVersion(detailVersionIndex.value)
  closeVersionDetail()
}

const hideVersionSelector = () => {
  resetVersionSelectionState()
}

const confirmVersionSelection = async () => {
  await selectVersion(selectedVersionIndex.value)
}

const deleteVersion = async (versionIndex: number) => {
  if (selectedChapterNumber.value === null) return

  const originalVersionIndex = getOriginalVersionIndex(versionIndex)
  if (originalVersionIndex === undefined) return

  // 防止删除当前正在查看的版本
  const versionToCheck = availableVersions.value[versionIndex]
  if (!versionToCheck?.content) return

  // 仅在章节已经确认成功时，才把当前正文视为不可删除的生效版本。
  // waiting_for_confirm 阶段回填的是候选预览，不能据此锁死删除。
  const chapterStatus = selectedChapter.value?.generation_status
  const currentContent = selectedChapter.value?.content?.trim() || ''
  const versionContent = versionToCheck.content.trim()
  const selectedVersionId = selectedChapter.value?.selected_version_id
  if (
    chapterStatus === 'successful' &&
    ((selectedVersionId && versionToCheck.id && selectedVersionId === versionToCheck.id) ||
      (!selectedVersionId && currentContent && currentContent === versionContent))
  ) {
    globalAlert.showError('不能删除当前生效的版本', '删除失败')
    return
  }

  // 至少保留一个版本
  if (availableVersions.value.length <= 1) {
    globalAlert.showError('至少需要保留一个版本', '删除失败')
    return
  }

  const nextVisibleVersionCount = availableVersions.value.length - 1
  let nextSelectedVersionIndex = selectedVersionIndex.value
  if (selectedVersionIndex.value > versionIndex) {
    nextSelectedVersionIndex = selectedVersionIndex.value - 1
  } else if (selectedVersionIndex.value >= nextVisibleVersionCount) {
    nextSelectedVersionIndex = Math.max(0, nextVisibleVersionCount - 1)
  }

  deletingVersionIndex.value = versionIndex
  try {
    await novelStore.deleteChapterVersion(selectedChapterNumber.value, originalVersionIndex, versionToCheck.id)
    clearLatestDiagnostics()
    selectedVersionIndex.value = nextSelectedVersionIndex
    if (compareVersionIndex.value === versionIndex) {
      compareVersionIndex.value = null
    } else if ((compareVersionIndex.value ?? -1) > versionIndex) {
      compareVersionIndex.value = (compareVersionIndex.value ?? 0) - 1
    }
    globalAlert.showSuccess('版本已删除', '操作成功')
  } catch (error) {
    const diagnostics = normalizeUiDiagnostics(error, '删除版本失败，请稍后重试', '删除失败')
    setLatestDiagnostics(diagnostics)
    console.error('删除版本失败:', diagnostics)
    globalAlert.showError(
      formatUiDiagnosticsMessage(diagnostics, { includeRootCause: true, includeRequestId: true, includeHint: true }),
      diagnostics.title || '删除失败'
    )
  } finally {
    deletingVersionIndex.value = null
  }
}

const openEditChapterModal = (chapter: ChapterOutline) => {
  const latestOutline = project.value?.blueprint?.chapter_outline?.find(
    (item) => item.chapter_number === chapter.chapter_number
  )
  const outlineToEdit = latestOutline || chapter

  if (!outlineToEdit) {
    globalAlert.showError('当前章节大纲不存在或尚未加载完成。', '无法编辑')
    return
  }

  editingChapter.value = { ...outlineToEdit }
  if (window.innerWidth < 1024) {
    closeSidebar()
  }
  showEditChapterModal.value = true
}

const saveChapterChanges = async (updatedChapter: ChapterOutline) => {
  try {
    isSavingOutline.value = true
    await novelStore.updateChapterOutline(updatedChapter)
    clearLatestDiagnostics()

    const latestOutline = project.value?.blueprint?.chapter_outline?.find(
      (item) => item.chapter_number === updatedChapter.chapter_number
    )
    editingChapter.value = latestOutline ? { ...latestOutline } : { ...updatedChapter }

    globalAlert.showSuccess('章节大纲已更新', '保存成功')
    showEditChapterModal.value = false
  } catch (error) {
    const diagnostics = normalizeUiDiagnostics(error, '更新章节大纲失败，请稍后重试', '保存失败')
    setLatestDiagnostics(diagnostics)
    console.error('更新章节大纲失败:', diagnostics)
    globalAlert.showError(
      formatUiDiagnosticsMessage(diagnostics, { includeRootCause: true, includeRequestId: true, includeHint: true }),
      diagnostics.title || '保存失败'
    )
  } finally {
    isSavingOutline.value = false
  }
}

const rewriteChapterSummary = async (payload: { chapter: ChapterOutline; direction?: string }) => {
  try {
    isRewritingOutline.value = true
    await novelStore.rewriteChapterOutline(payload.chapter, { direction: payload.direction })
    clearLatestDiagnostics()
    const rewritten = project.value?.blueprint?.chapter_outline?.find(
      (item) => item.chapter_number === payload.chapter.chapter_number
    )
    if (rewritten) editingChapter.value = { ...rewritten }
    globalAlert.showSuccess('章节摘要已通过 AI 重写', '重写成功')
  } catch (error) {
    const diagnostics = normalizeUiDiagnostics(error, 'AI 重写章节摘要失败，请稍后重试', '重写失败')
    setLatestDiagnostics(diagnostics)
    console.error('AI 重写章节摘要失败:', diagnostics)
    globalAlert.showError(
      formatUiDiagnosticsMessage(diagnostics, { includeRootCause: true, includeRequestId: true, includeHint: true }),
      diagnostics.title || '重写失败'
    )
  } finally {
    isRewritingOutline.value = false
  }
}

const evaluateChapter = async (versionIndex?: number) => {
  if (selectedChapterNumber.value === null) return
  const chapterNumber = selectedChapterNumber.value
  let originalVersionIndex: number | undefined
  let targetVersionId: number | undefined
  try {
    if (typeof versionIndex === 'number') {
      originalVersionIndex = getOriginalVersionIndex(versionIndex)
      if (originalVersionIndex === undefined) return
      targetVersionId = availableVersions.value[versionIndex]?.id
      evaluatingVersionIndex.value = versionIndex
      selectedVersionIndex.value = versionIndex
    }

    await withChapterStatusRollback(chapterNumber, async () => {
      await novelStore.evaluateChapter(chapterNumber, originalVersionIndex, targetVersionId)
      markProjectSynced()
    })

    // 评估完成后，如果是针对特定版本的评估，自动打开该版本的评估详情
    if (typeof originalVersionIndex === 'number') {
       const updatedChapter = project.value?.chapters.find((item) => item.chapter_number === chapterNumber)
       const version = targetVersionId
         ? updatedChapter?.versions?.find((item) => item.id === targetVersionId)
         : updatedChapter?.versions?.[originalVersionIndex]
       if (version?.evaluation) {
         handleShowEvaluationDetail(version.evaluation)
       }
    } else {
       globalAlert.showSuccess('章节评估结果已生成', '评估成功')
    }
  } catch (error) {
    const diagnostics = normalizeUiDiagnostics(error, '评估章节失败，请稍后重试', '评估失败')
    setLatestDiagnostics(diagnostics)
    console.error('评估章节失败:', diagnostics)
    globalAlert.showError(
      formatUiDiagnosticsMessage(diagnostics, { includeRootCause: true, includeRequestId: true, includeHint: true }),
      diagnostics.title || '评估失败'
    )
  } finally {
    evaluatingVersionIndex.value = null
  }
}

const evaluateAllVersions = async () => {
  if (selectedChapterNumber.value === null) return
  const chapterNumber = selectedChapterNumber.value
  try {
    await withChapterStatusRollback(chapterNumber, async () => {
      await novelStore.evaluateAllVersions(chapterNumber)
      markProjectSynced()
    })

    // 多版本评审完成后，自动打开评估详情
    const updatedChapter = project.value?.chapters.find((item) => item.chapter_number === chapterNumber)
    if (updatedChapter?.evaluation) {
      handleShowEvaluationDetail(updatedChapter.evaluation)
    } else {
      globalAlert.showSuccess('多版本对比评审结果已生成', '评审成功')
    }
  } catch (error) {
    const diagnostics = normalizeUiDiagnostics(error, '多版本评审失败，请稍后重试', '评审失败')
    setLatestDiagnostics(diagnostics)
    console.error('多版本评审失败:', diagnostics)
    globalAlert.showError(
      formatUiDiagnosticsMessage(diagnostics, { includeRootCause: true, includeRequestId: true, includeHint: true }),
      diagnostics.title || '评审失败'
    )
  }
}

const normalizeOptimizationNotes = (notes: OptimizeResponse['optimization_notes']) =>
  Array.isArray(notes) ? notes.join('\n') : notes || ''

const closeCandidateOptimizeDialog = () => {
  showCandidateOptimizeDialog.value = false
  candidateSelectedDimension.value = 'rhythm'
  candidateAdditionalNotes.value = ''
  isOptimizingCandidateVersion.value = false
  if (!showCandidateOptimizeResultModal.value) {
    candidateOptimizeVersionIndex.value = null
  }
}

const resetCandidateOptimizationState = () => {
  showCandidateOptimizeDialog.value = false
  showCandidateOptimizeResultModal.value = false
  candidateOptimizedContent.value = ''
  candidateOptimizeResultNotes.value = ''
  candidateOptimizeVersionIndex.value = null
  candidateSelectedDimension.value = 'rhythm'
  candidateAdditionalNotes.value = ''
  isOptimizingCandidateVersion.value = false
  isApplyingCandidateOptimization.value = false
}

const optimizeVersion = async (versionIndex: number) => {
  if (selectedChapterNumber.value === null || !project.value?.id) return

  const version = availableVersions.value[versionIndex]
  const originalVersionIndex = getOriginalVersionIndex(versionIndex)
  if (!version?.content || originalVersionIndex === undefined) {
    globalAlert.showError('该版本没有可优化的内容', '无法优化')
    return
  }

  resetVersionSelectionState(versionIndex)
  candidateOptimizeVersionIndex.value = versionIndex
  candidateOptimizedContent.value = ''
  candidateOptimizeResultNotes.value = ''
  showCandidateOptimizeDialog.value = true
}

const generateCandidateOptimization = async () => {
  if (
    selectedChapterNumber.value === null ||
    !project.value?.id ||
    candidateOptimizeVersionIndex.value === null
  ) {
    return
  }

  const originalVersionIndex = getOriginalVersionIndex(candidateOptimizeVersionIndex.value)
  const candidateVersion = availableVersions.value[candidateOptimizeVersionIndex.value]
  if (originalVersionIndex === undefined) {
    globalAlert.showError('未找到对应候选版本', '无法优化')
    return
  }

  isOptimizingCandidateVersion.value = true
  try {
    globalAlert.showInfo('正在生成候选版本优化稿...', '请稍候')
    const result = await novelStore.optimizeChapterVersion(
      project.value.id,
      selectedChapterNumber.value,
      originalVersionIndex,
      candidateVersion?.id,
      candidateSelectedDimension.value,
      candidateAdditionalNotes.value
    )

    candidateOptimizedContent.value = result.optimized_content
    candidateOptimizeResultNotes.value = normalizeOptimizationNotes(result.optimization_notes)
    closeCandidateOptimizeDialog()
    showCandidateOptimizeResultModal.value = true
    globalAlert.showSuccess('优化结果已生成，请确认是否应用', '优化完成')
  } catch (error) {
    const diagnostics = normalizeUiDiagnostics(error, '优化失败，请稍后重试', '优化失败')
    setLatestDiagnostics(diagnostics)
    console.error('优化版本失败:', diagnostics)
    globalAlert.showError(
      formatUiDiagnosticsMessage(diagnostics, { includeRootCause: true, includeRequestId: true, includeHint: true }),
      diagnostics.title || '优化失败'
    )
  } finally {
    isOptimizingCandidateVersion.value = false
  }
}

const applyCandidateOptimization = async () => {
  if (
    selectedChapterNumber.value === null ||
    !project.value?.id ||
    !candidateOptimizedContent.value.trim()
  ) {
    return
  }

  isApplyingCandidateOptimization.value = true
  try {
    const result = await OptimizerAPI.applyOptimization(
      project.value.id,
      selectedChapterNumber.value,
      candidateOptimizedContent.value
    )
    syncUpdatedChapter(result.chapter)
    if (candidateOptimizeVersionIndex.value !== null) {
      const preferredIndex = candidateOptimizeVersionIndex.value
      const normalizedOptimizedContent = normalizeChapterContent(candidateOptimizedContent.value)
      const nextIndex = availableVersions.value.findIndex((item, index) => {
        if (index === preferredIndex) return false
        return normalizeChapterContent(item.content) === normalizedOptimizedContent
      })
      if (nextIndex >= 0) {
        selectedVersionIndex.value = nextIndex
      }
    }
    resetCandidateOptimizationState()
    globalAlert.showSuccess('候选版本优化结果已应用', '操作成功')
  } catch (error) {
    const diagnostics = normalizeUiDiagnostics(error, '应用候选版本优化失败，请稍后重试', '应用失败')
    setLatestDiagnostics(diagnostics)
    console.error('应用候选版本优化失败:', diagnostics)
    globalAlert.showError(
      formatUiDiagnosticsMessage(diagnostics, { includeRootCause: true, includeRequestId: true, includeHint: true }),
      diagnostics.title || '应用失败'
    )
  } finally {
    isApplyingCandidateOptimization.value = false
  }
}

const handleShowEvaluationDetail = (customEvaluation?: string) => {
  if (typeof customEvaluation === 'string') {
    evaluationToShow.value = customEvaluation
  } else {
    evaluationToShow.value = selectedChapter.value?.evaluation || null
  }
  showEvaluationDetailModal.value = true
}

const deleteChapter = async (chapterNumbers: number | number[]) => {
  const numbersToDelete = Array.isArray(chapterNumbers) ? chapterNumbers : [chapterNumbers]
  const confirmationMessage = numbersToDelete.length > 1
    ? '确定删除选中的 ' + numbersToDelete.length + ' 个章节吗？此操作不可撤销。'
    : '确定删除第 ' + numbersToDelete[0] + ' 章吗？此操作不可撤销。'
  if (!window.confirm(confirmationMessage)) return

  try {
    await novelStore.deleteChapter(numbersToDelete)
    markProjectSynced()
    globalAlert.showSuccess('章节已删除', '操作成功')
    if (selectedChapterNumber.value && numbersToDelete.includes(selectedChapterNumber.value)) {
      selectedChapterNumber.value = null
      pickInitialChapter()
    }
  } catch (error) {
    const diagnostics = normalizeUiDiagnostics(error, '删除章节失败，请稍后重试', '删除失败')
    setLatestDiagnostics(diagnostics)
    console.error('删除章节失败:', diagnostics)
    globalAlert.showError(
      formatUiDiagnosticsMessage(diagnostics, { includeRootCause: true, includeRequestId: true, includeHint: true }),
      diagnostics.title || '删除失败'
    )
  }
}

const generateOutline = async () => {
  showGenerateOutlineModal.value = true
}

const syncUpdatedChapter = (updatedChapter: Chapter) => {
  if (!project.value) return
  const index = project.value.chapters.findIndex(
    (chapter) => chapter.chapter_number === updatedChapter.chapter_number
  )
  if (index >= 0) {
    project.value.chapters.splice(index, 1, updatedChapter)
  } else {
    project.value.chapters.push(updatedChapter)
    project.value.chapters.sort((a, b) => a.chapter_number - b.chapter_number)
  }
  markProjectSynced()
}

const editChapterContent = async (data: { chapterNumber: number; content: string }) => {
  if (!project.value) {
    throw new Error('当前未加载项目，无法保存章节内容')
  }
  try {
    await novelStore.editChapterContent(project.value.id, data.chapterNumber, data.content)
    clearLatestDiagnostics()
    markProjectSynced()
    globalAlert.showSuccess('章节内容已更新', '保存成功')
  } catch (error) {
    const diagnostics = normalizeUiDiagnostics(error, '编辑章节内容失败，请稍后重试', '保存失败')
    setLatestDiagnostics(diagnostics)
    console.error('编辑章节内容失败:', diagnostics)
    globalAlert.showError(
      formatUiDiagnosticsMessage(diagnostics, { includeRootCause: true, includeRequestId: true, includeHint: true }),
      diagnostics.title || '保存失败'
    )
    throw error
  }
}

const handleGenerateOutline = async (payload: GenerateOutlinePayload) => {
  if (!project.value) return
  isGeneratingOutline.value = true
  try {
    const existingOutline = project.value.blueprint?.chapter_outline ?? []
    const existingChapterNumbers = existingOutline
      .map((item) => Number(item.chapter_number))
      .filter((value) => Number.isFinite(value) && value > 0)
    const startChapter = (existingChapterNumbers.length ? Math.max(...existingChapterNumbers) : 0) + 1
    await novelStore.generateChapterOutline(startChapter, payload.numChapters, {
      targetTotalChapters: payload.targetTotalChapters,
      targetTotalWords: payload.targetTotalWords,
      chapterWordTarget: payload.chapterWordTarget
    })
    clearLatestDiagnostics()
    markProjectSynced()
    globalAlert.showSuccess('新的章节大纲已生成（新增 ' + payload.numChapters + ' 章）', '操作成功')
  } catch (error) {
    const diagnostics = normalizeUiDiagnostics(error, '生成大纲失败，请稍后重试', '生成失败')
    setLatestDiagnostics(diagnostics)
    console.error('生成大纲失败:', diagnostics)
    globalAlert.showError(
      formatUiDiagnosticsMessage(diagnostics, { includeRootCause: true, includeRequestId: true, includeHint: true }),
      diagnostics.title || '生成失败'
    )
  } finally {
    isGeneratingOutline.value = false
  }
}

const isEditableTarget = (event: KeyboardEvent) => {
  const target = event.target as HTMLElement | null
  if (!target) return false
  const tagName = target.tagName.toLowerCase()
  return tagName === 'input' || tagName === 'textarea' || target.isContentEditable
}

const hasBlockingOverlayOpen = computed(
  () =>
    showPatchDiffModal.value ||
    showSkillSelectorModal.value ||
    showGenerateChapterModal.value ||
    showVersionDetailModal.value ||
    showEvaluationDetailModal.value ||
    showEditChapterModal.value ||
    showGenerateOutlineModal.value ||
    showCandidateOptimizeDialog.value ||
    showCandidateOptimizeResultModal.value
)

const handleKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Escape') {
    if (showShortcutHelp.value) return void (showShortcutHelp.value = false)
    if (showPatchDiffModal.value) return closePatchDiffModal()
    if (showVersionDetailModal.value) return closeVersionDetail()
    if (showEvaluationDetailModal.value) return void (showEvaluationDetailModal.value = false)
    if (showEditChapterModal.value) return void (showEditChapterModal.value = false)
    if (showGenerateOutlineModal.value) return void (showGenerateOutlineModal.value = false)
    if (showGenerateChapterModal.value) return closeGenerateChapterModal()
    if (showSkillSelectorModal.value) return void (showSkillSelectorModal.value = false)
    if (showCandidateOptimizeDialog.value) return closeCandidateOptimizeDialog()
    if (showCandidateOptimizeResultModal.value) return resetCandidateOptimizationState()
    if (sidebarOpen.value && window.innerWidth < 1024) sidebarOpen.value = false
    return
  }

  if (isEditableTarget(event) || hasBlockingOverlayOpen.value) return

  const configuredShortcutHelpKey = shortcutConfig.value.openShortcuts.trim()
  const isQuestionKey = configuredShortcutHelpKey === '?'
    ? event.key === '?' || (event.shiftKey && event.key === '/')
    : event.key.toLowerCase() === configuredShortcutHelpKey.toLowerCase()
  if (isQuestionKey && !event.ctrlKey && !event.metaKey && !event.altKey) {
    event.preventDefault()
    showShortcutHelp.value = !showShortcutHelp.value
    return
  }

  const key = event.key.toLowerCase()
  const hasPrimaryModifier = event.ctrlKey || event.metaKey

  const matchesShortcut = (shortcut: string) => {
    const normalized = shortcut.trim().toLowerCase()
    if (!normalized) return false
    if (normalized === 'ctrl/cmd + enter') return hasPrimaryModifier && !event.shiftKey && event.key === 'Enter'
    if (normalized === 'ctrl/cmd + shift + g') return hasPrimaryModifier && event.shiftKey && key === 'g'
    if (normalized === 'ctrl/cmd + shift + f') return hasPrimaryModifier && event.shiftKey && key === 'f'
    if (normalized === 'ctrl/cmd + .') return hasPrimaryModifier && event.key === '.'
    if (normalized === 'alt + p') return event.altKey && !event.ctrlKey && !event.metaKey && key === 'p'
    if (normalized === 'alt + n') return event.altKey && !event.ctrlKey && !event.metaKey && key === 'n'
    return false
  }

  if (matchesShortcut(shortcutConfig.value.primaryAction)) {
    event.preventDefault()
    handlePrimaryShortcutAction()
    return
  }

  if (matchesShortcut(shortcutConfig.value.generateChapter)) {
    event.preventDefault()
    if (canGenerateSelectedChapter.value) handlePrimaryGenerate()
    return
  }

  if (matchesShortcut(shortcutConfig.value.openReader)) {
    event.preventDefault()
    workspaceRef.value?.openPrimaryReader()
    return
  }

  if (matchesShortcut(shortcutConfig.value.refreshStatus)) {
    event.preventDefault()
    void fetchChapterStatus()
    return
  }

  if (matchesShortcut(shortcutConfig.value.prevChapter)) {
    event.preventDefault()
    goPrevChapter()
    return
  }

  if (matchesShortcut(shortcutConfig.value.nextChapter)) {
    event.preventDefault()
    goNextChapter()
  }
}


const runDialogProbeIfRequested = async () => {
  if (!import.meta.env.DEV) return
  const probe = typeof route.query.dialog_probe === 'string' ? route.query.dialog_probe : ''
  if (!probe) return
  await nextTick()
  await new Promise(resolve => window.setTimeout(resolve, 1000))
  const firstVersion = selectedChapter.value?.versions?.[0]
  const secondVersion = selectedChapter.value?.versions?.[1] || firstVersion
  const openers: Record<string, () => void> = {
    'version-detail': () => showVersionDetail(0),
    'evaluation-detail': () => {
      evaluationToShow.value = JSON.stringify({
        recommended_version: 1,
        content_to_evaluate: { total_versions: Math.max(1, selectedChapter.value?.versions?.length || 1) },
        evaluation: {
          version1: {
            pros: ['Clear conflict hook', 'Readable scene rhythm'],
            cons: ['Need stronger sensory detail'],
            overall_review: 'This candidate is readable and suitable for modal validation.'
          }
        },
        optimization_suggestions: ['Tighten the ending hook', 'Add one character-specific gesture']
      }, null, 2)
      showEvaluationDetailModal.value = true
    },
    'version-diff': () => {
      versionDiffBaseVersionId.value = firstVersion?.id || null
      versionDiffCompareVersionId.value = secondVersion?.id || firstVersion?.id || null
      versionDiffBaseLabel.value = 'Candidate A'
      versionDiffCompareLabel.value = 'Candidate B'
      showVersionDiffModal.value = true
    },
    'patch-diff': () => {
      patchDiffChapterNumber.value = selectedChapterNumber.value || 1
      patchDiffInitialOriginal.value = selectedChapter.value?.content || availableVersions.value[0]?.content || 'Original paragraph for patch diff validation.'
      patchDiffInitialPatched.value = `${patchDiffInitialOriginal.value}\n\nAdded validation paragraph.`
      showPatchDiffModal.value = true
    },
    'skill-selector': () => { showSkillSelectorModal.value = true },
    'reader': () => { workspaceRef.value?.openPrimaryReader() },
    'generate-chapter': () => { pendingGenerateChapterNumber.value = selectedChapterNumber.value || 1; generateChapterSeed.value = {}; showGenerateChapterModal.value = true },
    'edit-chapter': () => {
      const outline = project.value?.blueprint?.chapter_outline?.find(item => item.chapter_number === selectedChapterNumber.value) || project.value?.blueprint?.chapter_outline?.[0]
      if (outline) openEditChapterModal(outline)
    },
    'generate-outline': () => { showGenerateOutlineModal.value = true }
  }
  openers[probe]?.()
}

const handleWindowResize = () => {
  if (window.innerWidth < 1024 && sidebarOpen.value && hasBlockingOverlayOpen.value) {
    sidebarOpen.value = false
  }
}

watch(
  () => outlineOrChapterNumbers.value.join(','),
  () => pickInitialChapter(),
  { immediate: true }
)

watch(
  () => selectedChapter.value?.generation_status,
  (status) => {
    if (
      generatingChapter.value !== null &&
      selectedChapterNumber.value !== null &&
      generatingChapter.value === selectedChapterNumber.value &&
      status &&
      !['generating', 'evaluating', 'selecting'].includes(status)
    ) {
      generatingChapter.value = null
    }
  }
)

watchEffect(() => {
  const hasBusyChapter = project.value?.chapters?.some((chapter) =>
    isBusyTask(chapter, resolveChapterRuntime(chapter, project.value?.generation_runtime || null))
  )

  if (hasBusyChapter) {
    scheduleStatusPolling()
    return
  }

  clearStatusPolling()
})

watch(
  () => props.id,
  async (newId, oldId) => {
    if (!newId || newId === oldId) return
    resetWorkspaceState()
    await loadProject()
  }
)

onMounted(() => {
  document.body.classList.add('m3-novel')
  window.addEventListener('keydown', handleKeydown)
  window.addEventListener('resize', handleWindowResize)
  handleWindowResize()
  void loadProject().then(runDialogProbeIfRequested)
})

onUnmounted(() => {
  clearStatusPolling()
  document.body.classList.remove('m3-novel')
  window.removeEventListener('keydown', handleKeydown)
  window.removeEventListener('resize', handleWindowResize)
})

// ===== SSE helpers =====
const sseController = ref<SSEController | null>(null)
const _ensureSSEConnected = () => {
  if (sseController.value || !props.id) return
  const busyCh = project.value?.chapters?.find((ch: any) =>
    isBusyTask(ch, resolveChapterRuntime(ch, project.value?.generation_runtime || null))
  )
  if (!busyCh?.chapter_number) return
  const url = '/api/writer/novels/' + props.id + '/chapters/' + busyCh.chapter_number + '/stream'
  sseController.value = connectSSE(url, {
    onStatusUpdate(data) {
      if (!project.value) return
      const idx = project.value.chapters.findIndex((c: any) => c.chapter_number === busyCh.chapter_number)
      if (idx < 0) return
      const ch = { ...project.value.chapters[idx] }
      if (data.runtime) ch.real_summary = JSON.stringify({ generation_runtime: data.runtime })
      ch.generation_status = data.status
      ch.word_count = data.word_count || ch.word_count
      project.value.chapters[idx] = ch
    },
    onComplete() { sseController.value?.close(); sseController.value = null; void fetchChapterStatus() },
    onError() { sseController.value?.close(); sseController.value = null },
  })
}
const _closeSSE = () => { sseController.value?.close(); sseController.value = null }

</script>

<style scoped>
/* 玄穹文书写作台：纸页、墨色、金线与玻璃层次统一。 */
:global(body.m3-novel) {
  --md-font-family: 'ZCOOL XiaoWei', 'Noto Serif SC', 'STKaiti', 'KaiTi', serif;
  --md-primary: #7EB8E8;
  --md-secondary: #A8C8E0;
  --md-surface-container: #F5F9FC;
  --md-on-surface-variant: #6A8A9A;
  --md-outline: #D0E0F0;
  --md-error: #E8A0A0;
  --md-error-container: #FEF0F0;
}

/* 主容器 - 纸张质感背景 */

.writing-desk-shell {
  position: relative;
  color: var(--xq-ink);
  background: linear-gradient(180deg, rgba(255, 251, 245, 0.92), rgba(248, 243, 234, 0.78));
}

.writing-desk-shell > * {
  position: relative;
  z-index: 1;
}

.writing-desk-main {
  padding-top: clamp(0.65rem, 1vw, 1rem);
}

.writing-desk-grid {
  max-width: 1780px;
  margin: 0 auto;
  border: 1px solid rgba(93, 70, 43, 0.12);
  border-radius: 28px;
  padding: clamp(0.45rem, 0.9vw, 0.85rem);
  background: rgba(255, 250, 240, 0.86);
  box-shadow: 0 14px 34px rgba(37, 28, 18, 0.08);
}

.writing-desk-loading {
  max-width: 1780px;
  margin: 0 auto;
  border: 1px solid rgba(93, 70, 43, 0.1);
  border-radius: 28px;
  background: rgba(255, 250, 240, 0.52);
  box-shadow: var(--xq-shadow-paper);
}

.writing-desk-error .md-card {
  border-color: rgba(153, 27, 27, 0.18) !important;
  background: rgba(255, 250, 240, 0.92);
  box-shadow: var(--xq-shadow-floating);
}

.writing-desk-shell :deep(.md-btn-filled),
.writing-desk-shell :deep(.md-btn-tonal) {
  border-radius: 999px;
  font-weight: 800;
}

.writing-desk-shell :deep(.md-card),
.writing-desk-shell :deep(.md-dialog) {
  border: 1px solid rgba(93, 70, 43, 0.12);
  box-shadow: var(--xq-shadow-paper);
}
.m3-shell {
  background:
    radial-gradient(ellipse 600px 300px at 5% 0%, rgba(126, 184, 232, 0.08), transparent 50%),
    radial-gradient(ellipse 500px 250px at 95% 100%, rgba(168, 200, 224, 0.08), transparent 50%),
    linear-gradient(180deg, #FAFCFE 0%, #F3F7FA 50%, #EDF4F9 100%);
}

.m3-main {
  min-height: calc(100vh - 56px);
  overflow: hidden;
}

.m3-workspace {
  min-height: calc(100vh - 112px);
  overflow: hidden;
}

.m3-workspace__pane {
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

/* 快捷键对话框 */
.m3-shortcut-dialog {
  width: min(1100px, calc(100vw - 32px));
  border-radius: 32px;
  padding: 28px;
  background: white;
  box-shadow: 0 20px 60px rgba(100, 120, 140, 0.15);
}

.m3-shortcut-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 14px;
}

.m3-shortcut-config {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
  margin-top: 18px;
}

.m3-shortcut-config__row {
  display: grid;
  gap: 6px;
}

.m3-shortcut-config__row label {
  font-size: 0.78rem;
  font-weight: 700;
  color: #475569;
}

.m3-shortcut-config__actions {
  display: flex;
  align-items: end;
  gap: 10px;
  grid-column: 1 / -1;
  flex-wrap: wrap;
}

.m3-shortcut-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 18px;
  border-radius: 20px;
  background: linear-gradient(135deg, #FAFCFE, #F5F9FC);
  border: 1px solid rgba(200, 210, 220, 0.2);
  transition: all 0.2s ease;
}

.m3-shortcut-item:hover {
  background: linear-gradient(135deg, #F5F9FC, #EEF4F8);
  border-color: rgba(126, 184, 232, 0.3);
}

.m3-shortcut-item kbd {
  min-width: 90px;
  padding: 8px 12px;
  border-radius: 14px;
  background: linear-gradient(135deg, #5A7A8A, #4A6A7A);
  color: white;
  font-size: 0.8rem;
  font-weight: 600;
  text-align: center;
  font-family: inherit;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(12px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* Skeleton shimmer animation */
@keyframes skeleton-shimmer {
  0%   { opacity: 0.55; }
  50%  { opacity: 1; }
  100% { opacity: 0.55; }
}

.skeleton-sidebar  { background: var(--md-surface-container, #f0f4f8); }
.skeleton-header   { background: var(--md-surface-container, #f0f4f8); }
.skeleton-content  { background: var(--md-surface-container, #f0f4f8); }

.animate-pulse {
  animation: skeleton-shimmer 1.6s ease-in-out infinite;
}

/* 鍝嶅簲寮?*/
@media (max-width: 1024px) {
  .m3-main {
    padding: 16px;
  }

  .m3-workspace {
    flex-direction: column;
    gap: 16px;
  }
}

.wd-candidate-optimize-dialog,
.wd-candidate-optimize-result {
  width: min(920px, calc(100vw - 32px));
  max-height: calc(100vh - 32px);
  padding: 24px;
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.98);
  box-shadow: 0 24px 60px rgba(15, 23, 42, 0.18);
}

.wd-candidate-optimize-result__head,
.wd-candidate-optimize-result__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.wd-candidate-optimize-dialog__body {
  margin-top: 20px;
}

.wd-candidate-optimize-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.wd-candidate-optimize-option {
  display: grid;
  gap: 6px;
  padding: 16px;
  text-align: left;
  border-radius: 18px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  background: rgba(248, 250, 252, 0.92);
}

.wd-candidate-optimize-option--active {
  border-color: rgba(37, 99, 235, 0.34);
  background: rgba(219, 234, 254, 0.84);
}

.wd-candidate-optimize-option span {
  color: #64748b;
  font-size: 0.84rem;
  line-height: 1.6;
}

.wd-candidate-optimize-result__body {
  margin-top: 20px;
  max-height: min(60vh, 720px);
  overflow: auto;
  white-space: pre-wrap;
  line-height: 1.9;
  color: #0f172a;
  padding: 18px;
  border-radius: 20px;
  background: rgba(248, 250, 252, 0.94);
  border: 1px solid rgba(148, 163, 184, 0.18);
}

.wd-candidate-optimize-result__foot {
  margin-top: 20px;
}

@media (max-width: 640px) {
  .m3-main {
    padding: 12px;
  }

  .wd-candidate-optimize-result__head,
  .wd-candidate-optimize-result__foot {
    flex-direction: column;
    align-items: stretch;
  }

  .wd-candidate-optimize-grid {
    grid-template-columns: 1fr;
  }
}
</style>








