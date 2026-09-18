<template>
  <div class="wd-workspace-root">
    <div class="wd-workspace-card">
      <header v-if="selectedChapterNumber" class="wd-workspace-head">
        <div class="wd-workspace-head__main">
          <div class="wd-workspace-head__eyebrow">
            <span class="wd-workspace-head__number">第 {{ selectedChapterNumber }} 章</span>
            <span :class="['wd-workspace-head__state', chapterStateClass]">{{ selectedChapterStatusText }}</span>
            <span v-if="chapterIsBusy" class="wd-workspace-head__tag wd-workspace-head__tag--warning">
              后台任务
            </span>
          </div>

          <div class="wd-workspace-head__title">
            <h2>{{ selectedChapterOutline?.title || '未命名章节' }}</h2>
          </div>
        </div>

        <div class="wd-workspace-head__side">
          <div class="wd-workspace-head__meta">
            <span v-if="selectedChapter?.word_count">正文 {{ selectedChapter.word_count }} 字</span>
            <span v-if="selectedChapter?.versions?.length">候选 {{ selectedChapter.versions.length }} 版</span>
            <span v-if="chapterWordGoalText">{{ chapterWordGoalText }}</span>
            <span v-if="chapterWordExecutionText" :class="['wd-workspace-head__meta-pill', chapterWordExecutionClass]">{{ chapterWordExecutionText }}</span>
            <span v-if="chapterWordStatusHint" :class="['wd-workspace-head__meta-pill', chapterWordExecutionClass]">{{ chapterWordStatusHint }}</span>
            <span v-if="chapterQualitySummary" :class="['wd-workspace-head__meta-pill', chapterQualityClass]" :title="chapterQualitySummary.issues.join('；')">
              {{ chapterQualitySummary.label }}
            </span>
            <span v-if="generationRuntime?.enrichment_triggered" class="wd-workspace-head__meta-pill wd-workspace-head__meta-pill--warning">已触发补字数</span>
            <span v-if="lastStatusSyncText">更新 {{ lastStatusSyncText }}</span>
          </div>

          <div class="wd-workspace-head__actions">
            <span class="wd-workspace-tool-label">内容工具</span>
            <button type="button" class="md-btn md-btn-text md-ripple m3-action-btn m3-action-btn--quiet" @click="$emit('fetchChapterStatus')">
              <RefreshCw class="wd-btn-icon" aria-hidden="true" />
              刷新状态
            </button>
            <button
              v-if="canOpenReader"
              type="button"
              class="md-btn md-btn-text md-ripple m3-action-btn m3-action-btn--quiet"
              @click="openPrimaryReader"
            >
              <BookOpen class="wd-btn-icon" aria-hidden="true" />
              全文阅读
            </button>
            <button
              v-if="selectedChapterNumber !== null && isChapterCompleted(selectedChapterNumber)"
              type="button"
              class="md-btn md-btn-tonal md-ripple m3-action-btn m3-action-btn--strong"
              @click="openEditModal"
            >
              <Pencil class="wd-btn-icon" aria-hidden="true" />
              正文编辑
            </button>
            <button
              v-if="selectedChapterNumber !== null && isChapterCompleted(selectedChapterNumber)"
              type="button"
              class="md-btn md-btn-outlined md-ripple m3-action-btn"
              @click="openPatchDiffModal"
            >
              <Wrench class="wd-btn-icon" aria-hidden="true" />
              精细编辑
            </button>
          </div>
        </div>
      </header>

      <section v-if="project" class="wd-health-panel" aria-label="项目健康检查">
        <div class="wd-health-panel__lead">
          <div>
            <p class="wd-strip-kicker">项目体检</p>
            <h3>{{ projectHealthTitle }}</h3>
            <p v-if="healthPanelOpen">{{ projectHealthHint }}</p>
          </div>
          <button type="button" class="wd-health-toggle" @click="healthPanelOpen = !healthPanelOpen">
            {{ healthPanelOpen ? '收起' : '展开' }}
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
            <p class="wd-strip-kicker">章节总览</p>
            <h3>横向切换章节</h3>
            <p class="wd-strip-note">直接点章节卡切换；上一章 / 下一章 已收口到顶部，避免这里再放一套重复导航。</p>
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
            <strong>第 {{ item.chapterNumber }} 章</strong>
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
        返回顶部
      </button>
    </div>

    <div v-if="showEditModal" class="md-dialog-overlay" @click.self="closeEditModal">
      <div class="md-dialog w-full max-w-5xl m3-editor-dialog flex flex-col">
        <div class="flex items-center justify-between border-b p-6" style="border-bottom-color: var(--md-outline-variant);">
          <h3 class="md-title-large font-semibold">编辑第 {{ selectedChapterNumber }} 章正文</h3>
          <button type="button" class="md-icon-btn md-ripple" @click="closeEditModal">
            <X class="h-6 w-6" aria-hidden="true" />
          </button>
        </div>

        <div class="min-h-0 flex-1 overflow-y-auto p-6">
          <div class="flex h-full flex-col">
            <label class="md-text-field-label mb-2">章节正文</label>
            <textarea
              v-model="editingContent"
              class="md-textarea flex-1 w-full resize-none"
              placeholder="请输入章节正文..."
              :disabled="isSaving"
            />
            <div class="md-body-small md-on-surface-variant mt-2">字数统计：{{ editingContent.length }}</div>
          </div>
        </div>

        <div
          class="shrink-0 flex items-center justify-end gap-3 border-t p-6"
          style="border-top-color: var(--md-outline-variant); background-color: var(--md-surface-container-low);"
        >
          <button type="button" class="md-btn md-btn-outlined md-ripple disabled:opacity-50" :disabled="isSaving" @click="closeEditModal">
            取消
          </button>
          <button
            type="button"
            class="md-btn md-btn-filled md-ripple flex items-center gap-2 disabled:opacity-50"
            :disabled="isSaving || !editingContent.trim()"
            @click="saveEditedContent"
          >
            <Loader2 v-if="isSaving" class="h-4 w-4 animate-spin" aria-hidden="true" />
            {{ isSaving ? '保存中...' : '保存' }}
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
import type { Chapter, ChapterGenerationResponse, ChapterVersion, NovelProject } from '@/api/novel'
import { normalizeChapterContent } from '@/utils/chapterContent'
import {
  isBusyChapterStatus,
  isRecoverableVersionStatus,
  resolveChapterActionDecision,
  resolveChapterRuntime,
} from '@/utils/chapterGeneration'
import { buildChapterQualitySummary } from '@/utils/chapterQuality'

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
  generationRuntime?: Record<string, any> | null
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
  if (projectHealth.value.blocked > 0) return '存在导出阻断，先修复章节状态'
  if (projectHealth.value.missingDraft > 0) return '大纲已准备，正文仍需推进'
  return '章节链路完整，可以继续精修或导出'
})

const projectHealthHint = computed(() => {
  if (projectHealth.value.running > 0) return `有 ${projectHealth.value.running} 个章节仍在处理或待确认，请优先完成确认/终止。`
  if (projectHealth.value.failed > 0) return `有 ${projectHealth.value.failed} 个异常章节，需要重新生成或手动修复。`
  if (projectHealth.value.blocked > 0) return `当前 ${projectHealth.value.blocked} 个章节缺少成功状态或选中正文，导出会被后端拦截。`
  return '大纲、章节、候选版本与选中正文关系正常。'
})

const projectHealthItems = computed(() => [
  { label: '大纲', value: projectHealth.value.outlines, hint: '故事路线', tone: projectHealth.value.outlines ? 'info' : 'warn' },
  { label: '章节', value: projectHealth.value.chapters, hint: '已建正文位', tone: projectHealth.value.chapters ? 'info' : 'warn' },
  { label: '候选版本', value: projectHealth.value.versions, hint: '可评审稿件', tone: projectHealth.value.versions ? 'success' : 'warn' },
  { label: '可导出章节', value: projectHealth.value.withSelectedContent, hint: '成功且有正文', tone: projectHealth.value.blocked ? 'warn' : 'success' },
  { label: '导出阻断', value: projectHealth.value.blocked, hint: '需处理', tone: projectHealth.value.blocked ? 'danger' : 'success' },
  { label: '处理中', value: projectHealth.value.running, hint: '后台/待确认', tone: projectHealth.value.running ? 'warn' : 'success' }
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
      title: outline?.title || chapter?.title || `第 ${chapterNumber} 章`,
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
  if (min && target) return `最低 ${min} / 目标 ${target} 字`
  if (target) return `目标 ${target} 字`
  if (min) return `最低 ${min} 字`
  return ''
})
const chapterWordRequirementReasonLabelMap: Record<string, string> = {
  target_met: '已达到目标字数',
  close_to_target: '已接近目标字数',
  minimum_met: '已达到最低字数',
  minimum_met_but_below_target: '已过最低字数，但仍低于目标',
  below_minimum_after_enrichment: '补字数后仍低于最低要求',
  below_minimum: '低于最低要求'
}

const chapterWordExecutionText = computed(() => {
  const actual = chapterRuntime.value?.actual_word_count ?? selectedChapter.value?.word_count
  if (actual) return `实际 ${actual} 字`
  return ''
})
const chapterWordStatusHint = computed(() => {
  const met = chapterRuntime.value?.word_requirement_met
  const reason = chapterRuntime.value?.word_requirement_reason
  if (typeof met !== 'boolean' && !reason) return ''
  if (reason && chapterWordRequirementReasonLabelMap[reason]) return chapterWordRequirementReasonLabelMap[reason]
  if (met === true) return '已达到最低字数'
  if (met === false) return '未达到最低要求'
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
  if (status === 'successful') return '正文已确认'
  if (status === 'generating') return '正在生成'
  if (status === 'evaluating') return '正在评估'
  if (status === 'selecting') return '准备确认'
  if (status === 'waiting_for_confirm') return '等待你确认'
  if (status === 'evaluation_failed') return '评审异常（候选版本可继续确认）'
  if (status === 'failed') return '生成失败'
  return '尚未开始'
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
    title: selectedChapter.value?.title?.trim() || `第 ${props.selectedChapterNumber} 章`,
    subtitle: version.style ? `候选版本 · ${version.style}` : `候选版本 ${versionIndex + 1}`,
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
  if (payload.chapterNumber !== undefined) chips.push(`第 ${payload.chapterNumber} 章`)
  if (payload.source === 'chapter-content') chips.push('当前正文')
  if (payload.source === 'candidate-version') chips.push('候选版本')
  if (typeof payload.versionIndex === 'number') chips.push(`第 ${payload.versionIndex + 1} 版`)

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
      title: selectedChapter.value?.title?.trim() || `第 ${props.selectedChapterNumber} 章正文`,
      subtitle: selectedChapter.value?.summary?.trim() || '当前章节正文',
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
    console.error('保存章节内容失败:', error)
    await globalAlert.showError(
      error instanceof Error ? error.message : '保存章节内容失败，请稍后重试。',
      '保存失败'
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
  min-width: 0;
  min-height: 0;
  height: 100%;
}

.wd-workspace-card {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(244, 248, 254, 0.96)),
    rgba(250, 253, 255, 0.96);
  border: 1px solid rgba(148, 175, 220, 0.15);
  box-shadow: 0 8px 24px rgba(107, 155, 235, 0.08);
  overflow: hidden;
  border-radius: 8px;
}

.wd-workspace-head {
  display: flex;
  flex-wrap: wrap;
  align-items: start;
  justify-content: space-between;
  gap: 6px;
  padding: 4px 8px 2px;
  border-bottom: 1px solid rgba(161, 186, 220, 0.2);
  background:
    linear-gradient(135deg, rgba(252, 254, 255, 0.96), rgba(237, 245, 255, 0.94)),
    rgba(248, 252, 255, 0.95);
}

.wd-workspace-head__main {
  min-width: 0;
  flex: 1;
  display: grid;
  gap: 4px;
}

.wd-workspace-head__eyebrow {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.wd-workspace-head__number,
.wd-workspace-head__state,
.wd-workspace-head__tag,
.wd-workspace-head__meta span {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 8px;
  border-radius: 999px;
  background: rgba(107, 155, 235, 0.15);
  color: #4A7DD4;
  font-size: 0.74rem;
  font-weight: 700;
}

.wd-workspace-head__state--success {
  background: rgba(22, 163, 74, 0.12);
  color: #166534;
}

.wd-workspace-head__state--warning {
  background: rgba(171, 202, 243, 0.34);
  color: #355e93;
}

.wd-workspace-head__state--danger {
  background: rgba(239, 68, 68, 0.12);
  color: #b91c1c;
}

.wd-workspace-head__state--neutral {
  background: rgba(154, 194, 245, 0.34);
  color: #315f9d;
}

.wd-workspace-head__meta-pill--success {
  background: rgba(22, 163, 74, 0.12) !important;
  color: #166534 !important;
}

.wd-workspace-head__meta-pill--warning {
  background: rgba(14, 165, 233, 0.16) !important;
  color: #1d4ed8 !important;
}

.wd-workspace-head__meta-pill--danger {
  background: rgba(239, 68, 68, 0.12) !important;
  color: #b91c1c !important;
}

.wd-workspace-head__tag--warning {
  background: rgba(171, 202, 243, 0.34);
  color: #355e93;
}

.wd-workspace-head__title {
  display: grid;
  gap: 0;
}

.wd-workspace-head__title h2 {
  color: #0f172a;
  font-size: clamp(0.96rem, 1.2vw, 1.34rem);
  font-weight: 800;
  line-height: 1.1;
  margin: 0;
}

.wd-workspace-head__side {
  min-width: min(100%, 220px);
  display: grid;
  gap: 6px;
  align-content: start;
}

.wd-workspace-head__meta,
.wd-workspace-head__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.wd-workspace-head__actions {
  align-items: center;
}

.wd-btn-icon {
  width: 16px;
  height: 16px;
  flex: 0 0 auto;
}

.wd-workspace-tool-label {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(79, 70, 229, 0.1);
  color: #4338ca;
  font-size: 0.76rem;
  font-weight: 900;
  letter-spacing: 0.04em;
}

.m3-action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  min-height: 40px;
  padding: 0 16px;
  border-radius: 8px;
  font-size: 0.86rem;
  font-weight: 850;
}

.m3-action-btn--quiet {
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(148, 163, 184, 0.22);
}

.m3-action-btn--strong {
  box-shadow: 0 12px 24px rgba(79, 70, 229, 0.12);
}

.wd-workspace-body {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 8px;
}

.wd-health-panel {
  display: grid;
  grid-template-columns: 1fr;
  gap: 10px;
  padding: 8px;
  border-bottom: 1px solid rgba(161, 186, 220, 0.16);
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.94), rgba(240, 247, 255, 0.9));
}

.wd-health-panel__lead {
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 10px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.7);
  border: 1px solid rgba(148, 163, 184, 0.18);
}

.wd-health-panel__lead h3 {
  margin: 2px 0 4px;
  color: #0f172a;
  font-size: 0.98rem;
  font-weight: 850;
}

.wd-health-panel__lead p {
  margin: 0;
  color: #52627a;
  font-size: 0.78rem;
  line-height: 1.5;
}

.wd-health-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 30px;
  padding: 0 12px;
  border-radius: 8px;
  border: 1px solid rgba(148, 163, 184, 0.24);
  background: #fff;
  color: #334155;
  font-size: 0.78rem;
  font-weight: 800;
}

.wd-health-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(72px, 1fr));
  gap: 8px;
}

.wd-health-item {
  display: grid;
  gap: 2px;
  min-height: 74px;
  padding: 10px;
  border-radius: 8px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(255, 255, 255, 0.8);
  box-shadow: 0 10px 24px rgba(107, 155, 235, 0.08);
}

.wd-health-item span {
  color: #64748b;
  font-size: 0.72rem;
  font-weight: 800;
}

.wd-health-item strong {
  color: #0f172a;
  font-size: 1.24rem;
  line-height: 1;
  font-weight: 900;
}

.wd-health-item em {
  color: #64748b;
  font-size: 0.68rem;
  font-style: normal;
}

.wd-health-item--success {
  border-color: rgba(34, 197, 94, 0.22);
  background: linear-gradient(180deg, rgba(240, 253, 244, 0.92), rgba(255, 255, 255, 0.84));
}

.wd-health-item--warn {
  border-color: rgba(14, 165, 233, 0.28);
  background: linear-gradient(180deg, rgba(255, 251, 235, 0.94), rgba(255, 255, 255, 0.84));
}

.wd-health-item--danger {
  border-color: rgba(239, 68, 68, 0.24);
  background: linear-gradient(180deg, rgba(254, 242, 242, 0.94), rgba(255, 255, 255, 0.84));
}

.wd-chapter-strip {
  display: grid;
  gap: 6px;
  padding: 6px 8px 0;
  border-bottom: 1px solid rgba(161, 186, 220, 0.16);
  background: rgba(247, 250, 255, 0.88);
}

@media (max-width: 1024px) {
  .wd-health-panel {
    grid-template-columns: 1fr;
  }

  .wd-health-grid {
    grid-template-columns: repeat(3, minmax(90px, 1fr));
  }
}

@media (max-width: 640px) {
  .wd-health-grid {
    grid-template-columns: repeat(2, minmax(90px, 1fr));
  }
}

.wd-strip-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.wd-strip-kicker {
  margin: 0 0 2px;
  font-size: 0.68rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #4f46e5;
  font-weight: 800;
}

.wd-strip-head h3 {
  margin: 0;
  font-size: 0.9rem;
  font-weight: 800;
  color: #0f172a;
}

.wd-strip-note {
  margin: 4px 0 0;
  color: #64748b;
  font-size: 0.78rem;
  line-height: 1.55;
}

.wd-strip-scroll {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: minmax(160px, 200px);
  gap: 8px;
  overflow-x: auto;
  padding-bottom: 10px;
}

.wd-strip-chip {
  display: grid;
  gap: 4px;
  min-height: 68px;
  padding: 10px 12px;
  text-align: left;
  border-radius: 8px;
  border: 1px solid rgba(148, 163, 184, 0.24);
  background: #fff;
  cursor: pointer;
  transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
}

.wd-strip-chip strong {
  color: #0f172a;
  font-size: 0.92rem;
}

.wd-strip-chip span {
  color: #64748b;
  font-size: 0.8rem;
  line-height: 1.45;
  display: -webkit-box;
  overflow: hidden;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.wd-strip-chip:hover {
  transform: translateY(-1px);
}

.wd-strip-chip--active {
  border-color: rgba(79, 70, 229, 0.45);
  box-shadow: 0 12px 28px rgba(79, 70, 229, 0.12);
  background: rgba(238, 242, 255, 0.9);
}

.wd-strip-chip--success {
  border-left: 4px solid rgba(22, 163, 74, 0.72);
}

.wd-strip-chip--warning {
  border-left: 4px solid rgba(14, 165, 233, 0.72);
}

.wd-strip-chip--danger {
  border-left: 4px solid rgba(239, 68, 68, 0.72);
}

.wd-workspace-scroll-top {
  position: absolute;
  right: 12px;
  bottom: 12px;
  min-height: 42px;
  padding: 0 14px;
  border: 1px solid rgba(148, 163, 184, 0.24);
  border-radius: 8px;
  background: rgba(53, 94, 147, 0.94);
  color: #fff;
  font-size: 0.82rem;
  font-weight: 700;
  box-shadow: 0 8px 20px rgba(53, 94, 147, 0.18);
  cursor: pointer;
  z-index: 4;
}

.m3-editor-dialog {
  max-height: min(90vh, 900px);
}

@media (max-width: 768px) {
  .wd-workspace-head {
    padding: 12px;
  }

  .wd-workspace-body {
    padding: 12px;
  }
}
</style>
