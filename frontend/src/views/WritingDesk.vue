<template>
  <div class="m3-shell min-h-screen flex flex-col overflow-x-hidden">
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

    <main class="m3-main min-h-0 flex-1 w-full px-1 pb-2 pt-1 sm:px-2 lg:px-3">
      <div v-if="novelStore.isLoading" class="skeleton-workspace h-full flex gap-3 px-2 pb-3 pt-2 sm:px-3 lg:px-4">
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

      <div v-else-if="novelStore.error" class="text-center py-20">
        <div class="md-card md-card-outlined mx-auto max-w-md p-8" style="border-radius: var(--md-radius-xl);">
          <div class="mb-4 flex h-12 w-12 items-center justify-center rounded-full mx-auto" style="background-color: var(--md-error-container);">
            <svg class="w-6 h-6" style="color: var(--md-error);" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path>
            </svg>
          </div>
          <h3 class="md-title-large mb-2" style="color: var(--md-on-surface);">鍔犺浇澶辫触</h3>
          <p class="md-body-medium mb-4" style="color: var(--md-error);">{{ novelStore.error }}</p>
          <button @click="loadProject" class="md-btn md-btn-tonal md-ripple">閲嶆柊鍔犺浇</button>
        </div>
      </div>

      <div
        v-else-if="project"
        :class="[
          'm3-workspace min-h-0 flex flex-col lg:flex-row',
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
            <button class="md-icon-btn md-ripple" @click="showShortcutHelp = false">脳</button>
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
              <input v-model="shortcutConfig.primaryAction" class="md-text-field-input" type="text" placeholder="渚嬪 Ctrl/Cmd + Enter">
            </div>
            <div class="m3-shortcut-config__row">
              <label>生成章节</label>
              <input v-model="shortcutConfig.generateChapter" class="md-text-field-input" type="text" placeholder="渚嬪 Ctrl/Cmd + Shift + G">
            </div>
            <div class="m3-shortcut-config__row">
              <label>展开全文</label>
              <input v-model="shortcutConfig.openReader" class="md-text-field-input" type="text" placeholder="渚嬪 Ctrl/Cmd + Shift + F">
            </div>
            <div class="m3-shortcut-config__row">
              <label>刷新状态</label>
              <input v-model="shortcutConfig.refreshStatus" class="md-text-field-input" type="text" placeholder="渚嬪 Ctrl/Cmd + .">
            </div>
            <div class="m3-shortcut-config__row">
              <label>上一章</label>
              <input v-model="shortcutConfig.prevChapter" class="md-text-field-input" type="text" placeholder="渚嬪 Alt + P">
            </div>
            <div class="m3-shortcut-config__row">
              <label>下一章</label>
              <input v-model="shortcutConfig.nextChapter" class="md-text-field-input" type="text" placeholder="渚嬪 Alt + N">
            </div>
            <div class="m3-shortcut-config__row">
              <label>打开面板</label>
              <input v-model="shortcutConfig.openShortcuts" class="md-text-field-input" type="text" placeholder="渚嬪 ?">
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
      :show="showVersionDetailModal"
      :detail-version-index="detailVersionIndex"
      :version="availableVersions[detailVersionIndex] || null"
      :is-current="isCurrentVersion(detailVersionIndex)"
      @close="closeVersionDetail"
      @select-version="selectVersionFromDetail"
    />
    <WDEvaluationDetailModal
      :show="showEvaluationDetailModal"
      :evaluation="evaluationToShow"
      @regenerate="handleRegenerateFromEvaluation"
      @optimize="handleOptimizeFromEvaluation"
      @close="showEvaluationDetailModal = false"
    />
    <WDEditChapterModal
      :show="showEditChapterModal"
      :chapter="editingChapter"
      :is-rewriting="isRewritingOutline"
      @close="showEditChapterModal = false"
      @save="saveChapterChanges"
      @rewrite="rewriteChapterSummary"
    />
    <WDGenerateOutlineModal
      :show="showGenerateOutlineModal"
      @close="showGenerateOutlineModal = false"
      @generate="handleGenerateOutline"
    />
    <WDGenerateChapterModal
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
      :show="showPatchDiffModal"
      :project-id="project?.id || ''"
      :chapter-number="patchDiffChapterNumber || selectedChapterNumber || 1"
      :initial-original="patchDiffInitialOriginal"
      :initial-patched="patchDiffInitialPatched"
      @close="closePatchDiffModal"
      @applied="handlePatchApplied"
    />
    <WDSkillSelectorModal
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
              脳
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
              鍙栨秷
            </button>
            <button
              type="button"
              class="md-btn md-btn-filled md-ripple"
              :disabled="isOptimizingCandidateVersion"
              @click="generateCandidateOptimization"
            >
              {{ isOptimizingCandidateVersion ? '鐢熸垚涓?..' : '鐢熸垚浼樺寲棰勮' }}
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
              脳
            </button>
          </div>
          <div class="wd-candidate-optimize-result__body">{{ candidateOptimizedContent }}</div>
          <div class="wd-candidate-optimize-result__foot">
            <button
              type="button"
              class="md-btn md-btn-outlined md-ripple"
              @click="resetCandidateOptimizationState"
            >
              鍙栨秷
            </button>
            <button
              type="button"
              class="md-btn md-btn-filled md-ripple"
              :disabled="isApplyingCandidateOptimization"
              @click="applyCandidateOptimization"
            >
              {{ isApplyingCandidateOptimization ? '搴旂敤涓?..' : '搴旂敤浼樺寲缁撴灉' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, onUnmounted, ref, watch, watchEffect } from 'vue'
import { useRouter } from 'vue-router'
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
}

interface VersionOption {
  originalIndex: number
  version: ChapterVersion
}

const props = defineProps<Props>()
const router = useRouter()
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

const DEFAULT_MIN_WORD_COUNT = 2400
const DEFAULT_TARGET_WORD_COUNT = 3200
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
  } catch {
    return { ...DEFAULT_SHORTCUT_CONFIG }
  }
}

const saveShortcutConfig = (config: ShortcutConfig) => {
  const normalized = normalizeShortcutConfig(config)
  shortcutConfig.value = normalized
  try {
    localStorage.setItem(shortcutConfigStorageKey, JSON.stringify(normalized))
    globalAlert.showSuccess('蹇嵎閿樉绀洪厤缃凡淇濆瓨', '淇濆瓨鎴愬姛')
  } catch {
    globalAlert.showError('淇濆瓨蹇嵎閿厤缃け璐ワ紝璇锋鏌ユ祻瑙堝櫒瀛樺偍鏉冮檺', '淇濆瓨澶辫触')
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
  if (!selectedChapter.value?.content || !availableVersions.value[versionIndex]?.content) return false
  return (
    normalizeChapterContent(selectedChapter.value.content) ===
    normalizeChapterContent(availableVersions.value[versionIndex].content)
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
  if (options.includeRootCause && diagnostics.rootCause) lines.push(`鏍瑰洜锛?{diagnostics.rootCause}`)
  if (options.includeRequestId && diagnostics.requestId) lines.push(`璇锋眰ID锛?{diagnostics.requestId}`)
  if (options.includeHint && diagnostics.hint) lines.push(`寤鸿锛?{diagnostics.hint}`)
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
    const diagnostics = normalizeUiDiagnostics(error, '鍔犺浇椤圭洰澶辫触锛岃绋嶅悗閲嶈瘯', '鍔犺浇澶辫触')
    setLatestDiagnostics(diagnostics)
    console.error('鍔犺浇椤圭洰澶辫触:', diagnostics)
    globalAlert.showError(
      formatUiDiagnosticsMessage(diagnostics, { includeRootCause: true, includeRequestId: true, includeHint: true }),
      diagnostics.title || '鍔犺浇澶辫触'
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
  const delay = stage === 'generating' ? 1800 : stage === 'evaluating' || stage === 'selecting' ? 1200 : 2500
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
    globalAlert.showError(message, '鐢熸垚鍙楅檺')
    return
  }

  try {
    generatingChapter.value = chapterNumber
    selectedChapterNumber.value = chapterNumber

    await novelStore.generateChapter(chapterNumber, {
      writingNotes: options?.writingNotes,
      qualityRequirements: options?.qualityRequirements,
      minWordCount: options?.minWordCount ?? DEFAULT_MIN_WORD_COUNT,
      targetWordCount: options?.targetWordCount ?? DEFAULT_TARGET_WORD_COUNT
    })

    clearLatestDiagnostics()
    resetVersionSelectionState()
    markProjectSynced()
  } catch (error) {
    const diagnostics = normalizeUiDiagnostics(error, '鐢熸垚绔犺妭澶辫触锛岃绋嶅悗閲嶈瘯', '鐢熸垚澶辫触')
    setLatestDiagnostics(diagnostics)
    console.error('鐢熸垚绔犺妭澶辫触:', diagnostics)
    try {
      await syncSingleChapterStatus(chapterNumber)
      } catch (syncError) {
        const syncDiagnostics = normalizeUiDiagnostics(syncError, '生成失败后同步项目状态失败')
        console.warn('生成失败后同步项目状态失败:', syncDiagnostics)
      }
    generatingChapter.value = null
    globalAlert.showError(
      formatUiDiagnosticsMessage(diagnostics, { includeRootCause: true, includeRequestId: true, includeHint: true }),
      diagnostics.title || '鐢熸垚澶辫触'
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
    targetWordCount: payload.targetWordCount
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
    `杩欎細灏嗙 ${target} 绔犲綋鍓嶅悗鍙颁换鍔℃爣璁颁负澶辫触骞跺仠姝㈠墠绔户缁瓑寰咃紱鑻ユ湇鍔＄浠诲姟宸叉帴杩戝畬鎴愶紝浠嶅彲鑳藉湪鐭椂闂村唴鍥炲啓缁撴灉銆傛槸鍚︾户缁紵`,
    '纭缁堟鍚庡彴澶勭悊'
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
    const diagnostics = normalizeUiDiagnostics(error, '缁堟鍚庡彴澶勭悊澶辫触锛岃绋嶅悗閲嶈瘯', '缁堟澶辫触')
    setLatestDiagnostics(diagnostics)
    console.error('缁堟绔犺妭鍚庡彴浠诲姟澶辫触:', diagnostics)
    globalAlert.showError(
      formatUiDiagnosticsMessage(diagnostics, { includeRootCause: true, includeRequestId: true, includeHint: true }),
      diagnostics.title || '缁堟澶辫触'
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
  if (selectedChapterNumber.value === null || !availableVersions.value[versionIndex]?.content) return
  const chapterNumber = selectedChapterNumber.value
  const originalVersionIndex = getOriginalVersionIndex(versionIndex)
  if (originalVersionIndex === undefined) return
  try {
    await withVersionSelectionPreview(versionIndex, async () => {
      await novelStore.selectChapterVersion(chapterNumber, originalVersionIndex)
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
    const diagnostics = normalizeUiDiagnostics(error, '閫夋嫨绔犺妭鐗堟湰澶辫触锛岃绋嶅悗閲嶈瘯', '閫夋嫨澶辫触')
    setLatestDiagnostics(diagnostics)
    console.error('閫夋嫨绔犺妭鐗堟湰澶辫触:', diagnostics)
    globalAlert.showError(
      formatUiDiagnosticsMessage(diagnostics, { includeRootCause: true, includeRequestId: true, includeHint: true }),
      diagnostics.title || '閫夋嫨澶辫触'
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

  // 闃叉鍒犻櫎褰撳墠姝ｅ湪鏌ョ湅鐨勭増鏈?
  const versionToCheck = availableVersions.value[versionIndex]
  if (!versionToCheck?.content) return

  // 浠呭湪绔犺妭宸茬粡纭鎴愬姛鏃讹紝鎵嶆妸褰撳墠姝ｆ枃瑙嗕负涓嶅彲鍒犻櫎鐨勭敓鏁堢増鏈€?
  // waiting_for_confirm 闃舵铏界劧浼氬洖濉竴涓瑙堟鏂囷紝浣嗛偅鍙槸鍊欓€夊洖鏄撅紝涓嶈兘鎹閿佹鍒犻櫎銆?
  const chapterStatus = selectedChapter.value?.generation_status
  const currentContent = selectedChapter.value?.content?.trim() || ''
  const versionContent = versionToCheck.content.trim()
  if (chapterStatus === 'successful' && currentContent && currentContent === versionContent) {
    globalAlert.showError('不能删除当前生效的版本', '删除失败')
    return
  }

  // 鑷冲皯淇濈暀涓€涓増鏈?
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
    await novelStore.deleteChapterVersion(selectedChapterNumber.value, originalVersionIndex)
    clearLatestDiagnostics()
    selectedVersionIndex.value = nextSelectedVersionIndex
    if (compareVersionIndex.value === versionIndex) {
      compareVersionIndex.value = null
    } else if ((compareVersionIndex.value ?? -1) > versionIndex) {
      compareVersionIndex.value = (compareVersionIndex.value ?? 0) - 1
    }
    globalAlert.showSuccess('版本已删除', '操作成功')
  } catch (error) {
    const diagnostics = normalizeUiDiagnostics(error, '鍒犻櫎鐗堟湰澶辫触锛岃绋嶅悗閲嶈瘯', '鍒犻櫎澶辫触')
    setLatestDiagnostics(diagnostics)
    console.error('鍒犻櫎鐗堟湰澶辫触:', diagnostics)
    globalAlert.showError(
      formatUiDiagnosticsMessage(diagnostics, { includeRootCause: true, includeRequestId: true, includeHint: true }),
      diagnostics.title || '鍒犻櫎澶辫触'
    )
  } finally {
    deletingVersionIndex.value = null
  }
}

const openEditChapterModal = (chapter: ChapterOutline) => {
  editingChapter.value = chapter
  showEditChapterModal.value = true
}

const saveChapterChanges = async (updatedChapter: ChapterOutline) => {
  try {
    await novelStore.updateChapterOutline(updatedChapter)
    clearLatestDiagnostics()
    globalAlert.showSuccess('章节大纲已更新', '保存成功')
  } catch (error) {
    const diagnostics = normalizeUiDiagnostics(error, '鏇存柊绔犺妭澶х翰澶辫触锛岃绋嶅悗閲嶈瘯', '淇濆瓨澶辫触')
    setLatestDiagnostics(diagnostics)
    console.error('鏇存柊绔犺妭澶х翰澶辫触:', diagnostics)
    globalAlert.showError(
      formatUiDiagnosticsMessage(diagnostics, { includeRootCause: true, includeRequestId: true, includeHint: true }),
      diagnostics.title || '淇濆瓨澶辫触'
    )
  } finally {
    showEditChapterModal.value = false
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
    globalAlert.showSuccess('绔犺妭鎽樿宸查€氳繃 AI 閲嶅啓', '閲嶅啓鎴愬姛')
  } catch (error) {
    const diagnostics = normalizeUiDiagnostics(error, 'AI 閲嶅啓绔犺妭鎽樿澶辫触锛岃绋嶅悗閲嶈瘯', '閲嶅啓澶辫触')
    setLatestDiagnostics(diagnostics)
    console.error('AI 閲嶅啓绔犺妭鎽樿澶辫触:', diagnostics)
    globalAlert.showError(
      formatUiDiagnosticsMessage(diagnostics, { includeRootCause: true, includeRequestId: true, includeHint: true }),
      diagnostics.title || '閲嶅啓澶辫触'
    )
  } finally {
    isRewritingOutline.value = false
  }
}

const evaluateChapter = async (versionIndex?: number) => {
  if (selectedChapterNumber.value === null) return
  const chapterNumber = selectedChapterNumber.value
  let originalVersionIndex: number | undefined
  try {
    if (typeof versionIndex === 'number') {
      originalVersionIndex = getOriginalVersionIndex(versionIndex)
      if (originalVersionIndex === undefined) return
      evaluatingVersionIndex.value = versionIndex
      selectedVersionIndex.value = versionIndex
    }

    await withChapterStatusRollback(chapterNumber, async () => {
      await novelStore.evaluateChapter(chapterNumber, originalVersionIndex)
      markProjectSynced()
    })

    // 璇勪及瀹屾垚鍚庯紝濡傛灉鏄拡瀵圭壒瀹氱増鏈殑锛岃嚜鍔ㄦ墦寮€璇ョ増鏈殑璇勪及璇︽儏
    if (typeof originalVersionIndex === 'number') {
       const updatedChapter = project.value?.chapters.find((item) => item.chapter_number === chapterNumber)
       const version = updatedChapter?.versions?.[originalVersionIndex]
       if (version?.evaluation) {
         handleShowEvaluationDetail(version.evaluation)
       }
    } else {
       globalAlert.showSuccess('章节评估结果已生成', '评估成功')
    }
  } catch (error) {
    const diagnostics = normalizeUiDiagnostics(error, '璇勪及绔犺妭澶辫触锛岃绋嶅悗閲嶈瘯', '璇勪及澶辫触')
    setLatestDiagnostics(diagnostics)
    console.error('璇勪及绔犺妭澶辫触:', diagnostics)
    globalAlert.showError(
      formatUiDiagnosticsMessage(diagnostics, { includeRootCause: true, includeRequestId: true, includeHint: true }),
      diagnostics.title || '璇勪及澶辫触'
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

    // 澶氱増鏈瘎瀹″畬鎴愬悗锛岃嚜鍔ㄦ墦寮€璇勪及璇︽儏
    const updatedChapter = project.value?.chapters.find((item) => item.chapter_number === chapterNumber)
    if (updatedChapter?.evaluation) {
      handleShowEvaluationDetail(updatedChapter.evaluation)
    } else {
      globalAlert.showSuccess('澶氱増鏈姣旇瘎瀹＄粨鏋滃凡鐢熸垚', '璇勫鎴愬姛')
    }
  } catch (error) {
    const diagnostics = normalizeUiDiagnostics(error, '多版本评审失败，请稍后重试', '评审失败')
    setLatestDiagnostics(diagnostics)
    console.error('多版本评审失败:', diagnostics)
    globalAlert.showError(
      formatUiDiagnosticsMessage(diagnostics, { includeRootCause: true, includeRequestId: true, includeHint: true }),
      diagnostics.title || '璇勫澶辫触'
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
      candidateSelectedDimension.value,
      candidateAdditionalNotes.value
    )

    candidateOptimizedContent.value = result.optimized_content
    candidateOptimizeResultNotes.value = normalizeOptimizationNotes(result.optimization_notes)
    closeCandidateOptimizeDialog()
    showCandidateOptimizeResultModal.value = true
    globalAlert.showSuccess('优化结果已生成，请确认是否应用', '优化完成')
  } catch (error) {
    const diagnostics = normalizeUiDiagnostics(error, '浼樺寲澶辫触锛岃绋嶅悗閲嶈瘯', '浼樺寲澶辫触')
    setLatestDiagnostics(diagnostics)
    console.error('浼樺寲鐗堟湰澶辫触:', diagnostics)
    globalAlert.showError(
      formatUiDiagnosticsMessage(diagnostics, { includeRootCause: true, includeRequestId: true, includeHint: true }),
      diagnostics.title || '浼樺寲澶辫触'
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
    globalAlert.showSuccess('鍊欓€夌増鏈紭鍖栫粨鏋滃凡搴旂敤', '鎿嶄綔鎴愬姛')
  } catch (error) {
    const diagnostics = normalizeUiDiagnostics(error, '应用候选版本优化失败，请稍后重试', '应用失败')
    setLatestDiagnostics(diagnostics)
    console.error('应用候选版本优化失败:', diagnostics)
    globalAlert.showError(
      formatUiDiagnosticsMessage(diagnostics, { includeRootCause: true, includeRequestId: true, includeHint: true }),
      diagnostics.title || '搴旂敤澶辫触'
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
    const diagnostics = normalizeUiDiagnostics(error, '鍒犻櫎绔犺妭澶辫触锛岃绋嶅悗閲嶈瘯', '鍒犻櫎澶辫触')
    setLatestDiagnostics(diagnostics)
    console.error('鍒犻櫎绔犺妭澶辫触:', diagnostics)
    globalAlert.showError(
      formatUiDiagnosticsMessage(diagnostics, { includeRootCause: true, includeRequestId: true, includeHint: true }),
      diagnostics.title || '鍒犻櫎澶辫触'
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
    throw new Error('褰撳墠鏈姞杞介」鐩紝鏃犳硶淇濆瓨绔犺妭鍐呭')
  }
  try {
    await novelStore.editChapterContent(project.value.id, data.chapterNumber, data.content)
    clearLatestDiagnostics()
    markProjectSynced()
    globalAlert.showSuccess('章节内容已更新', '保存成功')
  } catch (error) {
    const diagnostics = normalizeUiDiagnostics(error, '缂栬緫绔犺妭鍐呭澶辫触锛岃绋嶅悗閲嶈瘯', '淇濆瓨澶辫触')
    setLatestDiagnostics(diagnostics)
    console.error('缂栬緫绔犺妭鍐呭澶辫触:', diagnostics)
    globalAlert.showError(
      formatUiDiagnosticsMessage(diagnostics, { includeRootCause: true, includeRequestId: true, includeHint: true }),
      diagnostics.title || '淇濆瓨澶辫触'
    )
    throw error
  }
}

const handleGenerateOutline = async (payload: GenerateOutlinePayload) => {
  if (!project.value) return
  isGeneratingOutline.value = true
  try {
    const existingTotalChapters = project.value.blueprint?.chapter_outline?.length || 0
    const startChapter = existingTotalChapters + 1
    await novelStore.generateChapterOutline(startChapter, payload.numChapters, {
      targetTotalChapters: payload.targetTotalChapters,
      targetTotalWords: payload.targetTotalWords,
      chapterWordTarget: payload.chapterWordTarget
    })
    clearLatestDiagnostics()
    markProjectSynced()
    globalAlert.showSuccess('新的章节大纲已生成（新增 ' + payload.numChapters + ' 章）', '操作成功')
  } catch (error) {
    const diagnostics = normalizeUiDiagnostics(error, '鐢熸垚澶х翰澶辫触锛岃绋嶅悗閲嶈瘯', '鐢熸垚澶辫触')
    setLatestDiagnostics(diagnostics)
    console.error('鐢熸垚澶х翰澶辫触:', diagnostics)
    globalAlert.showError(
      formatUiDiagnosticsMessage(diagnostics, { includeRootCause: true, includeRequestId: true, includeHint: true }),
      diagnostics.title || '鐢熸垚澶辫触'
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
  loadProject()
})

onUnmounted(() => {
  clearStatusPolling()
  document.body.classList.remove('m3-novel')
  window.removeEventListener('keydown', handleKeydown)
  window.removeEventListener('resize', handleWindowResize)
})
</script>

<style scoped>
/* 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?
   鏂囧叿鎵嬭处椋庢牸 - 宸ヤ綔鍙版牱寮?
   鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?*/
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

/* 涓诲鍣?- 绾稿紶璐ㄦ劅鑳屾櫙 */
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

/* 蹇嵎閿璇濇 */
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






