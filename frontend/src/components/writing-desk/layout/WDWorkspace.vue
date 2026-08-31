<template>
  <div class="wd-workspace-root">
    <FloatingProgressCard
      :visible="floatingProgressVisible"
      :title="floatingProgressTitle"
      :stage="floatingProgressStage"
      :progress-percent="floatingProgressPercent"
      :word-count="floatingProgressWordCount"
      :status="floatingProgressStatus"
      :task-id="chapterRuntime?.task_id || chapterRuntime?.run_id"
      :task-status="chapterRuntime?.task_status"
      :retry-count="chapterRuntime?.retry_count"
      :task-recovered="Boolean(chapterRuntime?.recovered_from_reload)"
      @close="showFloatingProgress = false"
    
      :detail-message="floatingProgressDetail"
    />
    <div class="wd-workspace-card">
      <header v-if="selectedChapterNumber" class="wd-workspace-head">
        <div class="wd-workspace-head__main">
          <div class="wd-workspace-head__eyebrow">
            <span class="wd-workspace-head__number">{{ pick(`第 ${selectedChapterNumber} 章`, `Chapter ${selectedChapterNumber}`) }}</span>
            <span :class="['wd-workspace-head__state', chapterStateClass]">{{ selectedChapterStatusText }}</span>
            <span v-if="chapterIsBusy" class="wd-workspace-head__tag wd-workspace-head__tag--warning">
              {{ pick('后台任务', 'Background task') }}
            </span>
          </div>

          <div class="wd-workspace-head__title">
            <h2>{{ selectedChapterOutline?.title || pick('未命名章节', 'Untitled chapter') }}</h2>
          </div>
        </div>

        <div class="wd-workspace-head__side">
          <div class="wd-workspace-head__meta">
            <span v-if="selectedChapter?.word_count != null">{{ pick(`正文 ${selectedChapter.word_count} 字`, `Draft: ${selectedChapter.word_count} words`) }}</span>
            <span v-if="selectedChapter?.versions?.length">{{ pick(`候选 ${selectedChapter.versions.length} 版`, `${selectedChapter.versions.length} candidates`) }}</span>
            <span v-if="chapterWordGoalText">{{ chapterWordGoalText }}</span>
            <span v-if="chapterWordExecutionText" :class="['wd-workspace-head__meta-pill', chapterWordExecutionClass]">{{ chapterWordExecutionText }}</span>
            <span v-if="chapterWordStatusHint" :class="['wd-workspace-head__meta-pill', chapterWordExecutionClass]">{{ chapterWordStatusHint }}</span>
            <span v-if="chapterQualitySummary" :class="['wd-workspace-head__meta-pill', chapterQualityClass]" :title="chapterQualitySummary.issues.join(pick('；', '; '))">
              {{ chapterQualitySummary.label }}
            </span>
            <span v-if="generationRuntime?.enrichment_triggered" class="wd-workspace-head__meta-pill wd-workspace-head__meta-pill--warning">{{ pick('已触发补字数', 'Word-count top-up triggered') }}</span>
            <span v-if="lastStatusSyncText">{{ pick(`更新 ${lastStatusSyncText}`, `Updated ${lastStatusSyncText}`) }}</span>
          </div>

          <div class="wd-workspace-head__actions">
            <span class="wd-workspace-tool-label">{{ pick('内容工具', 'Content tools') }}</span>
            <button type="button" class="md-btn md-btn-text md-ripple m3-action-btn m3-action-btn--quiet" @click="$emit('fetchChapterStatus')">
              <RefreshCw class="wd-btn-icon" aria-hidden="true" />
              {{ pick('刷新状态', 'Refresh status') }}
            </button>
            <button
              v-if="canOpenReader"
              type="button"
              class="md-btn md-btn-text md-ripple m3-action-btn m3-action-btn--quiet"
              @click="openPrimaryReader"
            >
              <BookOpen class="wd-btn-icon" aria-hidden="true" />
              {{ pick('全文阅读', 'Read full text') }}
            </button>
            <button
              v-if="selectedChapterNumber !== null && isChapterCompleted(selectedChapterNumber)"
              type="button"
              class="md-btn md-btn-tonal md-ripple m3-action-btn m3-action-btn--strong"
              @click="openEditModal"
            >
              <Pencil class="wd-btn-icon" aria-hidden="true" />
              {{ pick('正文编辑', 'Edit draft') }}
            </button>
            <button
              v-if="selectedChapterNumber !== null && isChapterCompleted(selectedChapterNumber)"
              type="button"
              class="md-btn md-btn-outlined md-ripple m3-action-btn"
              @click="openPatchDiffModal"
            >
              <Wrench class="wd-btn-icon" aria-hidden="true" />
              {{ pick('精细编辑', 'Fine-tune') }}
            </button>
          </div>
        </div>
      </header>

      <section v-if="project" class="wd-health-panel" :aria-label="pick('项目健康检查', 'Project health check')">
        <div class="wd-health-panel__lead">
          <div>
            <p class="wd-strip-kicker">{{ pick('项目体检', 'Project checkup') }}</p>
            <h3>{{ projectHealthTitle }}</h3>
            <p v-if="healthPanelOpen">{{ projectHealthHint }}</p>
          </div>
          <button type="button" class="wd-health-toggle" @click="healthPanelOpen = !healthPanelOpen">
            {{ healthPanelOpen ? pick('收起', 'Collapse') : pick('展开', 'Expand') }}
          </button>
        </div>
        <div v-if="healthPanelOpen" class="wd-health-grid">
          <div
            v-for="item in projectHealthItems"
            :key="item.label"
            :class="['wd-health-item', `wd-health-item--${item.tone}`]"
          >
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
            <em>{{ item.hint }}</em>
          </div>
        </div>
      </section>

      <section v-if="chapterOverviewItems.length" class="wd-chapter-strip">
        <div class="wd-strip-head">
          <div>
            <p class="wd-strip-kicker">{{ pick('章节总览', 'Chapter overview') }}</p>
            <h3>{{ pick('横向切换章节', 'Switch chapters horizontally') }}</h3>
            <p class="wd-strip-note">{{ pick(
              '直接点章节卡切换；上一章 / 下一章 已收口到顶部，避免这里再放一套重复导航。',
              'Click a chapter card to switch. Previous / next now live at the top, so this strip does not duplicate that navigation.'
            ) }}</p>
          </div>
        </div>

        <div class="wd-strip-scroll">
          <button
            v-for="item in chapterOverviewItems"
            :key="item.chapterNumber"
            type="button"
            :class="['wd-strip-chip', item.chapterNumber === selectedChapterNumber ? 'wd-strip-chip--active' : '', `wd-strip-chip--${item.statusTone}`]"
            @click="$emit('selectChapter', item.chapterNumber)"
          >
            <strong>{{ pick(`第 ${item.chapterNumber} 章`, `Chapter ${item.chapterNumber}`) }}</strong>
            <span>{{ item.title }}</span>
          </button>
        </div>
      </section>

      <div ref="workspaceBodyRef" class="md-card-content wd-workspace-body">
        <component
          :is="currentComponent"
          v-bind="currentComponentProps"
          @hideVersionSelector="hideVersionSelectorLocally"
          @update:selectedVersionIndex="$emit('update:selectedVersionIndex', $event)"
          @update:compareVersionIndex="$emit('update:compareVersionIndex', $event)"
          @openVersionDiff="$emit('openVersionDiff', $event)"
          @openReader="handleOpenReader"
          @confirmVersionSelection="$emit('confirmVersionSelection')"
          @generateChapter="$emit('generateChapter', $event)"
          @showVersionSelector="handleShowVersionSelector"
          @regenerateChapter="$emit('regenerateChapter', $event)"
          @evaluateChapter="$emit('evaluateChapter')"
          @evaluateAllVersions="$emit('evaluateAllVersions')"
          @consumeOptimizerSuggestion="$emit('consumeOptimizerSuggestion')"
          @chapterUpdated="$emit('chapterUpdated', $event)"
          @fetchStatusNow="$emit('fetchChapterStatus')"
          @terminateChapter="$emit('terminateChapter', $event)"
          @openPatchDiff="$emit('openPatchDiff')"
          @deleteVersion="$emit('deleteVersion', $event)"
          @evaluateVersion="handleEvaluateVersion"
          @showEvaluationDetail="handleShowEvaluationDetail"
          @showVersionDetail="$emit('showVersionDetail', $event)"
          @optimizeVersion="handleOptimizeVersion"
        />
      </div>

      <button
        v-if="showWorkspaceScrollTop"
        type="button"
        class="wd-workspace-scroll-top"
        @click="scrollWorkspaceToTop"
      >
        {{ pick('返回顶部', 'Back to top') }}
      </button>
    </div>

    <div v-if="showEditModal" class="md-dialog-overlay" @click.self="closeEditModal">
      <div class="md-dialog w-full max-w-5xl m3-editor-dialog flex flex-col">
        <div class="flex items-center justify-between border-b p-6" style="border-bottom-color: var(--md-outline-variant);">
          <h3 class="md-title-large font-semibold">{{ pick(`编辑第 ${selectedChapterNumber} 章正文`, `Edit the draft of chapter ${selectedChapterNumber}`) }}</h3>
          <button type="button" class="md-icon-btn md-ripple" @click="closeEditModal">
            <X class="h-6 w-6" aria-hidden="true" />
          </button>
        </div>

        <div class="min-h-0 flex-1 overflow-y-auto p-6">
          <div class="flex h-full flex-col">
            <label class="md-text-field-label mb-2">{{ pick('章节正文', 'Chapter draft') }}</label>
            <textarea
              v-model="editingContent"
              class="md-textarea flex-1 w-full resize-none"
              :placeholder="pick('请输入章节正文...', 'Enter the chapter draft…')"
              :disabled="isSaving"
            />
            <div class="md-body-small md-on-surface-variant mt-2">{{ pick(`字数统计：${editingContent.length}`, `Word count: ${editingContent.length}`) }}</div>
          </div>
        </div>

        <div
          class="shrink-0 flex items-center justify-end gap-3 border-t p-6"
          style="border-top-color: var(--md-outline-variant); background-color: var(--md-surface-container-low);"
        >
          <button type="button" class="md-btn md-btn-outlined md-ripple disabled:opacity-50" :disabled="isSaving" @click="closeEditModal">
            {{ pick('取消', 'Cancel') }}
          </button>
          <button
            type="button"
            class="md-btn md-btn-filled md-ripple flex items-center gap-2 disabled:opacity-50"
            :disabled="isSaving || !editingContent.trim()"
            @click="saveEditedContent"
          >
            <Loader2 v-if="isSaving" class="h-4 w-4 animate-spin" aria-hidden="true" />
            {{ isSaving ? pick('保存中...', 'Saving…') : pick('保存', 'Save') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { BookOpen, Loader2, Pencil, RefreshCw, Wrench, X } from 'lucide-vue-next'
import { globalAlert } from '@/composables/useAlert'
import type { Chapter, ChapterGenerationResponse, ChapterVersion, GenerationRuntime, NovelProject } from '@/api/novel'
import { normalizeChapterContent } from '@/utils/chapterContent'
import {
  isBusyChapterStatus,
  isRecoverableVersionStatus,
  resolveChapterActionDecision,
  resolveActualWordCount,
  resolveChapterRuntime,
  resolveStageProgressWindow,
} from '@/utils/chapterGeneration'
import { buildChapterQualitySummary } from '@/utils/chapterQuality'
import { useLocale } from '@/composables/useLocale'
import FloatingProgressCard from '../widgets/FloatingProgressCard.vue'

const WorkspaceInitial = defineAsyncComponent(() => import('../workspace/states/WorkspaceInitial.vue'))
const ChapterGenerating = defineAsyncComponent(() => import('../workspace/states/ChapterGenerating.vue'))
const VersionSelector = defineAsyncComponent(() => import('../workspace/review/VersionSelector.vue'))
const ChapterContent = defineAsyncComponent(() => import('../workspace/content/ChapterContent.vue'))
const ChapterFailed = defineAsyncComponent(() => import('../workspace/states/ChapterFailed.vue'))
const ChapterEmpty = defineAsyncComponent(() => import('../workspace/states/ChapterEmpty.vue'))

interface Props {
  project: NovelProject | null
  selectedChapterNumber: number | null
  generatingChapter: number | null
  evaluatingChapter: number | null
  showVersionSelector: boolean
  chapterGenerationResult: ChapterGenerationResponse | null
  selectedVersionIndex: number
  compareVersionIndex?: number | null
  availableVersions: ChapterVersion[]
  isSelectingVersion?: boolean
  evaluatingVersionIndex?: number | null
  deletingVersionIndex?: number | null
  optimizerSuggestionNotes?: string
  generationRuntime?: GenerationRuntime | null
  lastStatusSyncAt?: string | null
  terminatingChapter?: number | null
  statusFetchFailureCount?: number
  sidebarOpen: boolean
  saveChapterContent: (payload: { chapterNumber: number; content: string }) => Promise<void>
}

interface ReaderPayload {
  title: string
  content: string
  subtitle?: string
  source?: string
  chapterNumber?: number
  versionIndex?: number
}

const props = defineProps<Props>()
const router = useRouter()

const { pick } = useLocale()

const emit = defineEmits<{
  (e: 'regenerateChapter', value: number): void
  (e: 'evaluateChapter'): void
  (e: 'evaluateAllVersions'): void
  (e: 'hideVersionSelector'): void
  (e: 'update:selectedVersionIndex', value: number): void
  (e: 'update:compareVersionIndex', value: number | null): void
  (e: 'openVersionDiff', payload: { baseVersionIndex: number; compareVersionIndex: number }): void
  (e: 'openReader', payload: ReaderPayload): void
  (e: 'confirmVersionSelection'): void
  (e: 'generateChapter', value: number): void
  (e: 'showVersionSelector', value?: boolean): void
  (e: 'showEvaluationDetail', value?: string): void
  (e: 'showVersionDetail', value: number): void
  (e: 'fetchChapterStatus'): void
  (e: 'consumeOptimizerSuggestion'): void
  (e: 'chapterUpdated', value: Chapter): void
  (e: 'terminateChapter', value: number): void
  (e: 'toggleSidebar'): void
  (e: 'selectChapter', value: number): void
  (e: 'deleteVersion', value: number): void
  (e: 'evaluateVersion', value: number): void
  (e: 'optimizeVersion', value: number): void
  (e: 'openPatchDiff'): void
}>()

// 浮动进度卡片状态
const showFloatingProgress = ref(false)

const showEditModal = ref(false)
const editingContent = ref('')
const isSaving = ref(false)
const workspaceBodyRef = ref<HTMLElement | null>(null)
const showWorkspaceScrollTop = ref(false)
const healthPanelOpen = ref(false)
const forceVersionSelector = ref(false)
const versionSelectorDismissed = ref(false)
const workspaceScrollRafId = ref<number | null>(null)


const selectedChapter = computed(() => {
  if (!props.project || props.selectedChapterNumber === null) return null
  return props.project.chapters.find((chapter) => chapter.chapter_number === props.selectedChapterNumber) || null
})

const projectHealth = computed(() => {
  const outlines = props.project?.blueprint?.chapter_outline || []
  const chapters = props.project?.chapters || []
  const withSelectedContent = chapters.filter((chapter) => chapter.generation_status === 'successful' && normalizeChapterContent(chapter.content || '').length > 0).length
  const blocked = chapters.filter((chapter) => chapter.generation_status !== 'successful' || !normalizeChapterContent(chapter.content || '')).length
  const failed = chapters.filter((chapter) => ['failed', 'evaluation_failed'].includes(chapter.generation_status || '')).length
  const running = chapters.filter((chapter) => ['generating', 'evaluating', 'selecting', 'waiting_for_confirm'].includes(chapter.generation_status || '')).length
  const missingDraft = Math.max(0, outlines.length - withSelectedContent)
  const versions = chapters.reduce((sum, chapter) => sum + (chapter.versions?.length || 0), 0)
  return {
    outlines: outlines.length,
    chapters: chapters.length,
    versions,
    withSelectedContent,
    blocked,
    failed,
    running,
    missingDraft
  }
})

const projectHealthTitle = computed(() => {
  if (projectHealth.value.blocked > 0) return pick('存在导出阻断，先修复章节状态', 'Export is blocked — fix the chapter statuses first')
  if (projectHealth.value.missingDraft > 0) return pick('大纲已准备，正文仍需推进', 'The outline is ready, but the drafts still need work')
  return pick('章节链路完整，可以继续精修或导出', 'The chapter chain is complete — polish or export')
})

const projectHealthHint = computed(() => {
  if (projectHealth.value.running > 0) return pick(
    `有 ${projectHealth.value.running} 个章节仍在处理或待确认，请优先完成确认/终止。`,
    `${projectHealth.value.running} chapters are still running or awaiting confirmation — confirm or stop them first.`
  )
  if (projectHealth.value.failed > 0) return pick(
    `有 ${projectHealth.value.failed} 个异常章节，需要重新生成或手动修复。`,
    `${projectHealth.value.failed} chapters are in an error state and need regeneration or a manual fix.`
  )
  if (projectHealth.value.blocked > 0) return pick(
    `当前 ${projectHealth.value.blocked} 个章节缺少成功状态或选中正文，导出会被后端拦截。`,
    `${projectHealth.value.blocked} chapters lack a successful status or a selected draft, so the backend will block the export.`
  )
  return pick('大纲、章节、候选版本与选中正文关系正常。', 'Outline, chapters, candidates, and selected drafts all line up.')
})

const projectHealthItems = computed(() => [
  { label: pick('大纲', 'Outline'), value: projectHealth.value.outlines, hint: pick('故事路线', 'Story route'), tone: projectHealth.value.outlines ? 'info' : 'warn' },
  { label: pick('章节', 'Chapters'), value: projectHealth.value.chapters, hint: pick('已建正文位', 'Draft slots created'), tone: projectHealth.value.chapters ? 'info' : 'warn' },
  { label: pick('候选版本', 'Candidates'), value: projectHealth.value.versions, hint: pick('可评审稿件', 'Drafts ready for review'), tone: projectHealth.value.versions ? 'success' : 'warn' },
  { label: pick('可导出章节', 'Exportable chapters'), value: projectHealth.value.withSelectedContent, hint: pick('成功且有正文', 'Successful with a draft'), tone: projectHealth.value.blocked ? 'warn' : 'success' },
  { label: pick('导出阻断', 'Export blockers'), value: projectHealth.value.blocked, hint: pick('需处理', 'Needs attention'), tone: projectHealth.value.blocked ? 'danger' : 'success' },
  { label: pick('处理中', 'In progress'), value: projectHealth.value.running, hint: pick('后台/待确认', 'Background / awaiting confirmation'), tone: projectHealth.value.running ? 'warn' : 'success' }
])

const selectedChapterOutline = computed(() => {
  if (!props.project?.blueprint?.chapter_outline || props.selectedChapterNumber === null) return null
  return props.project.blueprint.chapter_outline.find((chapter) => chapter.chapter_number === props.selectedChapterNumber) || null
})

const orderedChapterNumbers = computed(() =>
  [
    ...new Set(
      [
        ...(props.project?.blueprint?.chapter_outline?.map(chapter => chapter.chapter_number) || []),
        ...(props.project?.chapters?.map(chapter => chapter.chapter_number) || []),
      ].filter((value): value is number => typeof value === 'number')
    ),
  ].sort((a, b) => a - b)
)

const chapterOverviewItems = computed(() =>
  orderedChapterNumbers.value.map((chapterNumber) => {
    const chapter = props.project?.chapters?.find(item => item.chapter_number === chapterNumber)
    const outline = props.project?.blueprint?.chapter_outline?.find(item => item.chapter_number === chapterNumber)
    const status = String(chapter?.generation_status || 'not_generated')
    const statusTone =
      status === 'successful'
        ? 'success'
        : ['failed', 'evaluation_failed'].includes(status)
          ? 'danger'
          : ['generating', 'evaluating', 'selecting', 'waiting_for_confirm'].includes(status)
            ? 'warning'
            : 'neutral'

    return {
      chapterNumber,
      title: outline?.title || chapter?.title || pick(`第 ${chapterNumber} 章`, `Chapter ${chapterNumber}`),
      statusTone,
    }
  })
)

const activeVersion = computed(() => props.availableVersions?.[props.selectedVersionIndex] || null)
const activeVersionContent = computed(() => normalizeChapterContent(activeVersion.value?.content || ''))
const selectedChapterContent = computed(() => normalizeChapterContent(selectedChapter.value?.content || ''))
const hasSelectedChapterContent = computed(() => selectedChapterContent.value.length > 0)
const chapterRuntime = computed(() => resolveChapterRuntime(selectedChapter.value, props.generationRuntime))
const chapterQualitySummary = computed(() => buildChapterQualitySummary(selectedChapter.value, chapterRuntime.value))
const chapterWordGoalText = computed(() => {
  const min = chapterRuntime.value?.min_word_count
  const target = chapterRuntime.value?.target_word_count
  if (min && target) return pick(`最低 ${min} / 目标 ${target} 字`, `Min ${min} / target ${target} words`)
  if (target) return pick(`目标 ${target} 字`, `Target ${target} words`)
  if (min) return pick(`最低 ${min} 字`, `Min ${min} words`)
  return ''
})
// 键是后端 word_requirement_reason 枚举保持原文
const chapterWordRequirementReasonLabelMap = (): Record<string, string> => ({
  target_met: pick('已达到目标字数', 'Target word count reached'),
  close_to_target: pick('已接近目标字数', 'Close to the target word count'),
  minimum_met: pick('已达到最低字数', 'Minimum word count reached'),
  minimum_met_but_below_target: pick('已过最低字数，但仍低于目标', 'Above the minimum but below the target'),
  below_minimum_after_enrichment: pick('补字数后仍低于最低要求', 'Still below the minimum after the top-up'),
  below_minimum: pick('低于最低要求', 'Below the minimum')
})

const chapterWordExecutionText = computed(() => {
  const actual = resolveActualWordCount(chapterRuntime.value, selectedChapter.value?.word_count)
  if (actual !== null) return pick(`实际 ${actual} 字`, `Actual ${actual} words`)
  return ''
})
const chapterWordStatusHint = computed(() => {
  const met = chapterRuntime.value?.word_requirement_met
  const reason = chapterRuntime.value?.word_requirement_reason
  if (typeof met !== 'boolean' && !reason) return ''
  const reasonLabels = chapterWordRequirementReasonLabelMap()
  if (reason && reasonLabels[reason]) return reasonLabels[reason]
  if (met === true) return pick('已达到最低字数', 'Minimum word count reached')
  if (met === false) return pick('未达到最低要求', 'Minimum not reached')
  return ''
})
const chapterWordExecutionClass = computed(() => {
  const met = chapterRuntime.value?.word_requirement_met
  const reason = chapterRuntime.value?.word_requirement_reason
  if (met === false || reason === 'below_minimum_after_enrichment' || reason === 'below_minimum') {
    return 'wd-workspace-head__meta-pill--danger'
  }
  if (reason === 'target_met' || reason === 'close_to_target') {
    return 'wd-workspace-head__meta-pill--success'
  }
  if (met === true || reason === 'minimum_met' || reason === 'minimum_met_but_below_target') {
    return 'wd-workspace-head__meta-pill--warning'
  }
  return ''
})
const chapterQualityClass = computed(() => {
  if (chapterQualitySummary.value?.tone === 'success') return 'wd-workspace-head__meta-pill--success'
  if (chapterQualitySummary.value?.tone === 'danger') return 'wd-workspace-head__meta-pill--danger'
  return 'wd-workspace-head__meta-pill--warning'
})
const hasPreviewableVersions = computed(() => {
  if (!props.availableVersions?.length) return false
  return props.availableVersions.some((version) => normalizeChapterContent(version.content).length > 0)
})

const floatingProgressVisible = computed(() => {
  const status = selectedChapter.value?.generation_status
  return status === 'generating' || status === 'evaluating' || status === 'selecting'
})
const floatingProgressTitle = computed(() => pick(`第 ${props.selectedChapterNumber} 章`, `Chapter ${props.selectedChapterNumber}`))
const floatingProgressStage = computed(() => (props.generationRuntime ?? chapterRuntime.value)?.progress_stage || selectedChapter.value?.generation_status || '')
const floatingProgressPercent = computed(() => {
  const runtime = props.generationRuntime ?? chapterRuntime.value
  const pct = runtime?.progress_percent
  if (typeof pct === 'number') return Math.max(0, Math.min(100, Math.round(pct)))
  // 后端没给百分比时改用统一的阶段区间表，和主进度条共用同一套刻度，
  // 不再用手写 stageMap（未知阶段一律 30 会让进度来回跳）。
  const stageWindow = resolveStageProgressWindow(floatingProgressStage.value)
    ?? resolveStageProgressWindow(selectedChapter.value?.generation_status)
  return stageWindow ? stageWindow.start : 0
})
const floatingProgressWordCount = computed(() => selectedChapter.value?.word_count || 0)
const floatingProgressStatus = computed(() => selectedChapter.value?.generation_status || '')
const floatingProgressDetail = computed(() => (props.generationRuntime ?? chapterRuntime.value)?.progress_message || '')
const chapterIsBusy = computed(() => isBusyChapterStatus(selectedChapter.value?.generation_status))
const isTerminatingCurrent = computed(
  () => props.selectedChapterNumber !== null && props.terminatingChapter === props.selectedChapterNumber
)
const canOpenReader = computed(() => Boolean(activeVersionContent.value || selectedChapterContent.value))
const shouldShowVersionSelector = computed(() => {
  if (!props.selectedChapterNumber) return false
  const status = selectedChapter.value?.generation_status
  const allowsRecoverableStatus = isRecoverableVersionStatus(status)
  const shouldFallbackFromMissingContent = status === 'successful' && !hasSelectedChapterContent.value && hasPreviewableVersions.value
  if (!hasPreviewableVersions.value && !allowsRecoverableStatus) return false
  if (versionSelectorDismissed.value && !shouldFallbackFromMissingContent) return false
  if (forceVersionSelector.value || props.showVersionSelector) return true
  return allowsRecoverableStatus || shouldFallbackFromMissingContent
})

const lastStatusSyncText = computed(() => {
  if (!props.lastStatusSyncAt) return ''
  const date = new Date(props.lastStatusSyncAt)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
})

const isChapterCompleted = (chapterNumber: number) => {
  const chapter = props.project?.chapters.find((item) => item.chapter_number === chapterNumber)
  return chapter?.generation_status === 'successful'
}

const isChapterFailed = (chapterNumber: number) => {
  const chapter = props.project?.chapters.find((item) => item.chapter_number === chapterNumber)
  return chapter?.generation_status === 'failed'
}

const isChapterEvaluationFailed = (chapterNumber: number) => {
  const chapter = props.project?.chapters.find((item) => item.chapter_number === chapterNumber)
  return chapter?.generation_status === 'evaluation_failed'
}

const selectedChapterAction = computed(() => {
  if (props.selectedChapterNumber === null) return null
  return resolveChapterActionDecision(props.project, props.selectedChapterNumber, {
    generatingChapter: props.generatingChapter,
    evaluatingChapter: props.evaluatingChapter,
  })
})

const selectedChapterStatusText = computed(() => {
  const status = selectedChapter.value?.generation_status
  if (status === 'successful') return pick('正文已确认', 'Draft confirmed')
  if (status === 'generating') return pick('正在生成', 'Generating')
  if (status === 'evaluating') return pick('正在评估', 'Reviewing')
  if (status === 'selecting') return pick('准备确认', 'Ready to confirm')
  if (status === 'waiting_for_confirm') return pick('等待你确认', 'Awaiting your confirmation')
  if (status === 'evaluation_failed') return pick('评审异常（候选版本可继续确认）', 'Review error (candidates can still be confirmed)')
  if (status === 'failed') return pick('生成失败', 'Generation failed')
  return pick('尚未开始', 'Not started')
})

const chapterStateClass = computed(() => {
  const status = selectedChapter.value?.generation_status
  if (status === 'successful') return 'wd-workspace-head__state--success'
  if (status === 'failed') return 'wd-workspace-head__state--danger'
  if (status === 'evaluation_failed' || status === 'generating' || status === 'evaluating' || status === 'selecting') return 'wd-workspace-head__state--warning'
  return 'wd-workspace-head__state--neutral'
})

const currentComponent = computed(() => {
  if (!props.selectedChapterNumber) return WorkspaceInitial
  if (shouldShowVersionSelector.value) return VersionSelector

  const status = selectedChapter.value?.generation_status
  if (status === 'generating' || status === 'evaluating') return ChapterGenerating
  if (hasSelectedChapterContent.value) return ChapterContent
  if (isChapterFailed(props.selectedChapterNumber)) return ChapterFailed
  return ChapterEmpty
})

const canGenerateCurrent = computed(() => Boolean(selectedChapterAction.value?.canGenerate))

const hideVersionSelectorLocally = () => {
  forceVersionSelector.value = false
  versionSelectorDismissed.value = true
  emit('hideVersionSelector')
}

const handleShowVersionSelector = (value = true) => {
  forceVersionSelector.value = Boolean(value)
  versionSelectorDismissed.value = false
}

const buildVersionReaderPayload = (versionIndex: number): ReaderPayload | null => {
  const version = props.availableVersions?.[versionIndex]
  if (!version?.content) return null

  return {
    title: selectedChapter.value?.title?.trim() || pick(`第 ${props.selectedChapterNumber} 章`, `Chapter ${props.selectedChapterNumber}`),
    subtitle: version.style
      ? pick(`候选版本 · ${version.style}`, `Candidate · ${version.style}`)
      : pick(`候选版本 ${versionIndex + 1}`, `Candidate ${versionIndex + 1}`),
    content: normalizeChapterContent(version.content),
    source: 'candidate-version',
    chapterNumber: props.selectedChapterNumber || undefined,
    versionIndex
  }
}

const openEditModal = () => {
  if (selectedChapter.value?.content) {
    editingContent.value = selectedChapterContent.value
    showEditModal.value = true
  }
}

const closeEditModal = () => {
  showEditModal.value = false
  editingContent.value = ''
  isSaving.value = false
}

const openPatchDiffModal = () => {
  emit('openPatchDiff')
}

const handleOpenReader = (payload: ReaderPayload) => {
  const readerKey = `xqws-reader-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  const chips: string[] = []
  if (payload.chapterNumber !== undefined) chips.push(pick(`第 ${payload.chapterNumber} 章`, `Chapter ${payload.chapterNumber}`))
  if (payload.source === 'chapter-content') chips.push(pick('当前正文', 'Current draft'))
  if (payload.source === 'candidate-version') chips.push(pick('候选版本', 'Candidate'))
  if (typeof payload.versionIndex === 'number') chips.push(pick(`第 ${payload.versionIndex + 1} 版`, `Version ${payload.versionIndex + 1}`))

  sessionStorage.setItem(readerKey, JSON.stringify({
    title: payload.title,
    subtitle: payload.subtitle || '',
    content: payload.content,
    chips,
  }))

  router.push({
    name: 'novel-full-reader',
    params: { id: props.project?.id || '' },
    query: { reader_key: readerKey },
  })

  emit('openReader', payload)
}

const handleEvaluateVersion = (index: number) => {
  emit('evaluateVersion', index)
}

const handleOptimizeVersion = (index: number) => {
  emit('optimizeVersion', index)
}

const handleShowEvaluationDetail = (index?: number) => {
  // 如果提供了索引，尝试从该版本中提取评估
  if (typeof index === 'number' && props.availableVersions?.[index]?.evaluation) {
     emit('showEvaluationDetail', props.availableVersions[index].evaluation)
  } else {
     emit('showEvaluationDetail')
  }
}

const openPrimaryReader = () => {
  if (shouldShowVersionSelector.value && activeVersionContent.value) {
    const versionPayload = buildVersionReaderPayload(props.selectedVersionIndex)
    if (versionPayload) {
      handleOpenReader(versionPayload)
      return
    }
  }

  if (selectedChapterContent.value) {
    handleOpenReader({
      title: selectedChapter.value?.title?.trim() || pick(`第 ${props.selectedChapterNumber} 章正文`, `Chapter ${props.selectedChapterNumber} draft`),
      subtitle: selectedChapter.value?.summary?.trim() || pick('当前章节正文', 'Current chapter draft'),
      content: selectedChapterContent.value,
      source: 'chapter-content',
      chapterNumber: props.selectedChapterNumber || undefined
    })
    return
  }

  const firstAvailableVersionIndex = props.availableVersions.findIndex(
    (version) => normalizeChapterContent(version.content).length > 0
  )
  if (firstAvailableVersionIndex >= 0) {
    const versionPayload = buildVersionReaderPayload(firstAvailableVersionIndex)
    if (versionPayload) {
      handleOpenReader(versionPayload)
    }
  }
}

const openVersionSelector = () => {
  if (!props.selectedChapterNumber || !hasPreviewableVersions.value) return
  handleShowVersionSelector(true)
  if (props.selectedVersionIndex >= props.availableVersions.length) {
    emit('update:selectedVersionIndex', 0)
  }
  emit('update:compareVersionIndex', null)
}


const saveEditedContent = async () => {
  if (!props.selectedChapterNumber || !editingContent.value.trim()) return

  isSaving.value = true
  try {
    await props.saveChapterContent({
      chapterNumber: props.selectedChapterNumber,
      content: editingContent.value
    })
    closeEditModal()
  } catch (error) {
    console.error(pick('保存章节内容失败:', 'Failed to save the chapter content:'), error)
    await globalAlert.showError(
      error instanceof Error ? error.message : pick('保存章节内容失败，请稍后重试。', 'Failed to save the chapter content — please retry later.'),
      pick('保存失败', 'Save failed')
    )
  } finally {
    isSaving.value = false
  }
}

const updateWorkspaceScrollTopVisibility = () => {
  const element = workspaceBodyRef.value
  if (!element) {
    showWorkspaceScrollTop.value = false
    return
  }

  const isScrollable = element.scrollHeight - element.clientHeight > 8
  showWorkspaceScrollTop.value = isScrollable && element.scrollTop > 240
}

const scheduleWorkspaceScrollTopVisibilityUpdate = () => {
  if (workspaceScrollRafId.value !== null) return
  workspaceScrollRafId.value = window.requestAnimationFrame(() => {
    workspaceScrollRafId.value = null
    updateWorkspaceScrollTopVisibility()
  })
}

const handleWorkspaceScroll = () => {
  scheduleWorkspaceScrollTopVisibilityUpdate()
}

const scrollWorkspaceToTop = () => {
  workspaceBodyRef.value?.scrollTo({ top: 0, behavior: 'smooth' })
  window.setTimeout(updateWorkspaceScrollTopVisibility, 220)
}


watch(
  () => props.selectedChapterNumber,
  async () => {
    forceVersionSelector.value = false
    versionSelectorDismissed.value = false
      await nextTick()
    updateWorkspaceScrollTopVisibility()
  }
)

watch(
  () => selectedChapter.value?.generation_status,
  async (status) => {
    if (status === 'successful' || status === 'failed' || status === 'not_generated') {
      forceVersionSelector.value = false
      versionSelectorDismissed.value = false
    }
    await nextTick()
    updateWorkspaceScrollTopVisibility()
  }
)

watch(
  () => [props.sidebarOpen, props.showVersionSelector, props.availableVersions.length, selectedChapter.value?.content, currentComponent.value],
  async () => {
    await nextTick()
    updateWorkspaceScrollTopVisibility()
  },
  { flush: 'post' }
)

watch(
  workspaceBodyRef,
  (element, previous) => {
    previous?.removeEventListener('scroll', handleWorkspaceScroll)
    element?.addEventListener('scroll', handleWorkspaceScroll, { passive: true })
    updateWorkspaceScrollTopVisibility()
  },
  { flush: 'post' }
)

// 浮动进度卡片可见性
watch(floatingProgressVisible, (val) => {
  showFloatingProgress.value = val
}, { immediate: true })

onUnmounted(() => {
  workspaceBodyRef.value?.removeEventListener('scroll', handleWorkspaceScroll)
  if (workspaceScrollRafId.value !== null) {
    window.cancelAnimationFrame(workspaceScrollRafId.value)
    workspaceScrollRafId.value = null
  }
})

const currentComponentProps = computed(() => {
  if (!props.selectedChapterNumber) return {}

  const status = selectedChapter.value?.generation_status
  if (shouldShowVersionSelector.value) {
    return {
      selectedChapter: selectedChapter.value,
      chapterGenerationResult: props.chapterGenerationResult,
      availableVersions: props.availableVersions,
      selectedVersionIndex: props.selectedVersionIndex,
      compareVersionIndex: props.compareVersionIndex,
      isSelectingVersion: props.isSelectingVersion,
      evaluatingVersionIndex: props.evaluatingVersionIndex,
      deletingVersionIndex: props.deletingVersionIndex,
      evaluatingChapter: props.evaluatingChapter,
      isEvaluationFailed: isChapterEvaluationFailed(props.selectedChapterNumber)
    }
  }

  if (status === 'generating' || status === 'evaluating') {
    return {
      chapterNumber: props.selectedChapterNumber,
      status,
      chapterTitle: selectedChapterOutline.value?.title || '',
      generationRuntime: props.generationRuntime,
      progressStage: selectedChapter.value?.progress_stage,
      progressMessage: selectedChapter.value?.progress_message,
      startedAt: selectedChapter.value?.started_at,
      updatedAt: selectedChapter.value?.updated_at,
      allowedActions: selectedChapter.value?.allowed_actions,
      lastErrorSummary: selectedChapter.value?.last_error_summary,
      statusFetchFailureCount: props.statusFetchFailureCount || 0,
      isTerminating: isTerminatingCurrent.value,
      selectedChapterOutline: selectedChapterOutline.value
    }
  }

  if (hasSelectedChapterContent.value) {
    return {
      selectedChapter: selectedChapter.value,
      projectId: props.project?.id,
      optimizerSuggestionNotes: props.optimizerSuggestionNotes
    }
  }

  if (isChapterFailed(props.selectedChapterNumber)) {
    return {
      chapterNumber: props.selectedChapterNumber,
      generatingChapter: props.generatingChapter,
      chapter: selectedChapter.value,
      generationRuntime: chapterRuntime.value,
      lastErrorSummary: selectedChapter.value?.last_error_summary
    }
  }

  return {
    chapterNumber: props.selectedChapterNumber,
    generatingChapter: props.generatingChapter,
    canGenerate: canGenerateCurrent.value
  }
})

defineExpose({
  openPrimaryReader,
  openVersionSelector
})
</script>

<style scoped>
.wd-workspace-root {
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.wd-workspace-card {
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: rgba(255, 255, 255, 0.6);
  border-radius: 8px;
  border: 1px solid rgba(148, 163, 184, 0.1);
  overflow: hidden;
}

.wd-workspace-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 14px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.08);
  background: rgba(248, 250, 252, 0.5);
}

.wd-workspace-head__main {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.wd-workspace-head__eyebrow {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.wd-workspace-head__number {
  font-size: 11px;
  font-weight: 700;
  color: #6366f1;
  letter-spacing: 0.02em;
}

.wd-workspace-head__state {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.1);
  color: #64748b;
}

.wd-workspace-head__state--success {
  background: rgba(16, 185, 129, 0.1);
  color: #059669;
}

.wd-workspace-head__state--active {
  background: rgba(59, 130, 246, 0.1);
  color: #2563eb;
}

.wd-workspace-head__state--error {
  background: rgba(239, 68, 68, 0.1);
  color: #dc2626;
}

.wd-workspace-head__tag {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 5px;
  border-radius: 4px;
}

.wd-workspace-head__tag--warning {
  background: rgba(245, 158, 11, 0.1);
  color: #d97706;
}

.wd-workspace-head__title h2 {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
  line-height: 1.3;
}

.wd-workspace-head__side {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: flex-end;
}

.wd-workspace-head__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  justify-content: flex-end;
}

.wd-workspace-head__meta span {
  font-size: 10px;
  color: #64748b;
  padding: 1px 5px;
  background: rgba(148, 163, 184, 0.06);
  border-radius: 4px;
}

.wd-workspace-head__meta-pill {
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 999px;
  font-size: 10px;
}

.wd-workspace-head__meta-pill--success {
  background: rgba(16, 185, 129, 0.1);
  color: #059669;
}

.wd-workspace-head__meta-pill--warning {
  background: rgba(245, 158, 11, 0.1);
  color: #d97706;
}

.wd-workspace-head__meta-pill--danger {
  background: rgba(239, 68, 68, 0.1);
  color: #dc2626;
}

.wd-workspace-head__actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.wd-workspace-tool-label {
  font-size: 10px;
  color: #94a3b8;
  margin-right: 2px;
}

.wd-workspace-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 8px;
}

/* Health Panel */
.wd-health-panel {
  display: grid;
  gap: 6px;
  padding: 6px 8px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.08);
  background: rgba(248, 250, 252, 0.4);
}

.wd-health-panel__lead {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 4px 6px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.6);
  border: 1px solid rgba(148, 163, 184, 0.1);
}

.wd-health-panel__lead h3 {
  margin: 0;
  color: #0f172a;
  font-size: 12px;
  font-weight: 700;
}

.wd-health-panel__lead p {
  margin: 0;
  color: #64748b;
  font-size: 10px;
  line-height: 1.4;
}

.wd-health-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 24px;
  padding: 0 8px;
  border-radius: 4px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  background: #fff;
  color: #334155;
  font-size: 10px;
  font-weight: 600;
}

.wd-health-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(60px, 1fr));
  gap: 6px;
}

.wd-health-item {
  display: grid;
  gap: 1px;
  min-height: 48px;
  padding: 6px 8px;
  border-radius: 6px;
  border: 1px solid rgba(148, 163, 184, 0.1);
  background: rgba(255, 255, 255, 0.7);
}

.wd-health-item span {
  color: #94a3b8;
  font-size: 10px;
  font-weight: 600;
}

.wd-health-item strong {
  color: #0f172a;
  font-size: 14px;
  line-height: 1;
  font-weight: 800;
}

.wd-health-item em {
  color: #94a3b8;
  font-size: 9px;
  font-style: normal;
}

.wd-health-item--success {
  border-color: rgba(34, 197, 94, 0.2);
  background: linear-gradient(180deg, rgba(240, 253, 244, 0.8), rgba(255, 255, 255, 0.7));
}

.wd-health-item--warn {
  border-color: rgba(14, 165, 233, 0.25);
  background: linear-gradient(180deg, rgba(255, 251, 235, 0.8), rgba(255, 255, 255, 0.7));
}

.wd-health-item--danger {
  border-color: rgba(239, 68, 68, 0.2);
  background: linear-gradient(180deg, rgba(254, 242, 242, 0.8), rgba(255, 255, 255, 0.7));
}

/* Chapter Strip */
.wd-chapter-strip {
  display: grid;
  gap: 4px;
  padding: 4px 8px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.08);
  background: rgba(248, 250, 252, 0.4);
}

.wd-strip-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.wd-strip-kicker {
  margin: 0;
  font-size: 10px;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: #6366f1;
  font-weight: 700;
}

.wd-strip-head h3 {
  margin: 0;
  font-size: 11px;
  font-weight: 700;
  color: #0f172a;
}

.wd-strip-note {
  margin: 0;
  color: #94a3b8;
  font-size: 10px;
  line-height: 1.4;
}

.wd-strip-scroll {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: minmax(120px, 160px);
  gap: 6px;
  overflow-x: auto;
  padding-bottom: 6px;
}

.wd-strip-chip {
  display: grid;
  gap: 2px;
  min-height: 44px;
  padding: 6px 10px;
  text-align: left;
  border-radius: 6px;
  border: 1px solid rgba(148, 163, 184, 0.15);
  background: #fff;
  cursor: pointer;
  transition: transform 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
}

.wd-strip-chip strong {
  color: #0f172a;
  font-size: 11px;
}

.wd-strip-chip span {
  color: #94a3b8;
  font-size: 10px;
  line-height: 1.3;
  display: -webkit-box;
  overflow: hidden;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.wd-strip-chip:hover {
  transform: translateY(-1px);
}

.wd-strip-chip--active {
  border-color: rgba(79, 70, 229, 0.4);
  box-shadow: 0 4px 12px rgba(79, 70, 229, 0.1);
  background: rgba(238, 242, 255, 0.8);
}

.wd-strip-chip--success {
  border-left: 3px solid rgba(22, 163, 74, 0.6);
}

.wd-strip-chip--warning {
  border-left: 3px solid rgba(14, 165, 233, 0.6);
}

.wd-strip-chip--danger {
  border-left: 3px solid rgba(239, 68, 68, 0.6);
}

/* Scroll to top button */
.wd-workspace-scroll-top {
  position: absolute;
  right: 10px;
  bottom: 10px;
  min-height: 32px;
  padding: 0 10px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 6px;
  background: rgba(53, 94, 147, 0.9);
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  box-shadow: 0 4px 12px rgba(53, 94, 147, 0.15);
  cursor: pointer;
  z-index: 4;
}

/* Icon Button */
.wd-btn-icon {
  width: 12px;
  height: 12px;
  flex: 0 0 auto;
}

/* Editor Dialog */
.m3-editor-dialog {
  max-height: min(90vh, 800px);
}

@media (max-width: 1024px) {
  .wd-health-grid {
    grid-template-columns: repeat(3, minmax(70px, 1fr));
  }
}

@media (max-width: 768px) {
  .wd-workspace-head {
    padding: 8px 10px;
  }

  .wd-workspace-body {
    padding: 6px;
  }

  .wd-health-grid {
    grid-template-columns: repeat(3, minmax(60px, 1fr));
  }
}

@media (max-width: 640px) {
  .wd-health-grid {
    grid-template-columns: repeat(2, minmax(60px, 1fr));
  }

  .wd-strip-scroll {
    grid-auto-columns: minmax(100px, 140px);
  }
}
</style>






