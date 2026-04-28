<template>
  <div class="wd-workspace-root">
    <div class="wd-workspace-card md-card md-card-elevated" style="border-radius: var(--md-radius-xl);">
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
            <span v-if="generationRuntime?.enrichment_triggered" class="wd-workspace-head__meta-pill wd-workspace-head__meta-pill--warning">已触发补字数</span>
            <span v-if="lastStatusSyncText">更新 {{ lastStatusSyncText }}</span>
          </div>

          <div class="wd-workspace-head__actions">
            <button type="button" class="md-btn md-btn-text md-ripple m3-action-btn" @click="$emit('fetchChapterStatus')">
              刷新
            </button>
            <button
              v-if="canOpenReader"
              type="button"
              class="md-btn md-btn-text md-ripple m3-action-btn"
              @click="openPrimaryReader"
            >
              展开全文
            </button>
            <button
              v-if="availableVersions.length > 0"
              type="button"
              class="md-btn md-btn-text md-ripple m3-action-btn"
              @click="handleShowVersionSelector(true)"
            >
              查看候选版本
            </button>
            <button
              v-if="availableVersions.length > 1 && !chapterIsBusy"
              type="button"
              class="md-btn md-btn-text md-ripple m3-action-btn"
              @click="handleShowVersionSelector(true); $emit('evaluateAllVersions')"
            >
              对比评审全部版本
            </button>
            <button
              v-if="selectedChapterNumber !== null && isChapterCompleted(selectedChapterNumber)"
              type="button"
              class="md-btn md-btn-tonal md-ripple m3-action-btn"
              @click="openEditModal"
            >
              手动编辑
            </button>
            <button
              v-if="selectedChapterNumber !== null && isChapterCompleted(selectedChapterNumber)"
              type="button"
              class="md-btn md-btn-outlined md-ripple m3-action-btn"
              @click="openPatchDiffModal"
            >
              精细编辑
            </button>
            <button
              v-if="canTerminateCurrent"
              type="button"
              class="md-btn md-btn-outlined md-ripple disabled:opacity-50 m3-action-btn"
              :disabled="isTerminatingCurrent"
              @click="requestTerminateChapter"
            >
              {{ isTerminatingCurrent ? '终止中...' : '终止处理' }}
            </button>
            <button
              type="button"
              class="md-btn md-btn-filled md-ripple disabled:opacity-50 m3-action-btn"
              :disabled="chapterIsBusy"
              :title="chapterIsBusy ? '当前章节正在处理中，暂时不能重新生成。' : '重新生成当前章节'"
              @click="confirmRegenerateChapter"
            >
              {{ chapterIsBusy ? '处理中...' : '重新生成' }}
            </button>
          </div>
        </div>
      </header>

      <section v-if="chapterOverviewItems.length" class="wd-chapter-strip">
        <div class="wd-strip-head">
          <div>
            <p class="wd-strip-kicker">章节总览</p>
            <h3>横向切换章节</h3>
          </div>
          <div class="wd-strip-actions">
            <button type="button" class="wd-strip-btn" :disabled="!hasPrevChapter" @click="goPrevChapter">上一章</button>
            <button type="button" class="wd-strip-btn" :disabled="!hasNextChapter" @click="goNextChapter">下一章</button>
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
            <svg class="h-6 w-6" fill="currentColor" viewBox="0 0 20 20">
              <path
                fill-rule="evenodd"
                d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
                clip-rule="evenodd"
              />
            </svg>
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
            <svg v-if="isSaving" class="h-4 w-4 animate-spin" fill="currentColor" viewBox="0 0 20 20">
              <path
                fill-rule="evenodd"
                d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z"
                clip-rule="evenodd"
              />
            </svg>
            {{ isSaving ? '保存中...' : '保存' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { globalAlert } from '@/composables/useAlert'
import type { Chapter, ChapterGenerationResponse, ChapterVersion, NovelProject } from '@/api/novel'
import { normalizeChapterContent } from '@/utils/chapterContent'
import {
  canCancelGeneration,
  isBusyChapterStatus,
  isRecoverableVersionStatus,
  resolveChapterActionDecision,
  resolveChapterRuntime,
} from '@/utils/chapterGeneration'
import {
  WorkspaceInitial,
  ChapterGenerating,
  VersionSelector,
  ChapterContent,
  ChapterFailed,
  ChapterEmpty
} from '../workspace'

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
const forceVersionSelector = ref(false)
const versionSelectorDismissed = ref(false)


const selectedChapter = computed(() => {
  if (!props.project || props.selectedChapterNumber === null) return null
  return props.project.chapters.find((chapter) => chapter.chapter_number === props.selectedChapterNumber) || null
})

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
const hasPreviewableVersions = computed(() => {
  if (!props.availableVersions?.length) return false
  return props.availableVersions.some((version) => normalizeChapterContent(version.content).length > 0)
})
const chapterIsBusy = computed(() => isBusyChapterStatus(selectedChapter.value?.generation_status))
const canTerminateCurrent = computed(() => canCancelGeneration(selectedChapter.value, chapterRuntime.value))
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

const currentChapterIndex = computed(() => orderedChapterNumbers.value.findIndex(item => item === props.selectedChapterNumber))
const hasPrevChapter = computed(() => currentChapterIndex.value > 0)
const hasNextChapter = computed(() =>
  currentChapterIndex.value >= 0 && currentChapterIndex.value < orderedChapterNumbers.value.length - 1
)

const goPrevChapter = () => {
  if (!hasPrevChapter.value) return
  emit('selectChapter', orderedChapterNumbers.value[currentChapterIndex.value - 1])
}

const goNextChapter = () => {
  if (!hasNextChapter.value) return
  emit('selectChapter', orderedChapterNumbers.value[currentChapterIndex.value + 1])
}

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
  if (payload.chapterNumber !== undefined) chips.push(`? ${payload.chapterNumber} ?`)
  if (payload.source === 'chapter-content') chips.push('???')
  if (payload.source === 'candidate-version') chips.push('???')
  if (typeof payload.versionIndex === 'number') chips.push(`?? ${payload.versionIndex + 1}`)

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

const confirmRegenerateChapter = async () => {
  const confirmed = await globalAlert.showConfirm(
    '重新生成会覆盖当前章节的现有内容，是否继续？',
    '确认重新生成'
  )
  if (confirmed && props.selectedChapterNumber !== null) {
    emit('regenerateChapter', props.selectedChapterNumber)
  }
}

const requestTerminateChapter = () => {
  if (props.selectedChapterNumber === null) return
  emit('terminateChapter', props.selectedChapterNumber)
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

const handleWorkspaceScroll = () => {
  updateWorkspaceScrollTopVisibility()
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
    element?.addEventListener('scroll', handleWorkspaceScroll)
    updateWorkspaceScrollTopVisibility()
  },
  { flush: 'post' }
)

onUnmounted(() => {
  workspaceBodyRef.value?.removeEventListener('scroll', handleWorkspaceScroll)
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
      generatingChapter: props.generatingChapter
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
  background: rgba(245, 158, 11, 0.16) !important;
  color: #92400e !important;
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

.wd-workspace-body {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 8px;
}

.wd-chapter-strip {
  display: grid;
  gap: 6px;
  padding: 6px 8px 0;
  border-bottom: 1px solid rgba(161, 186, 220, 0.16);
  background: rgba(247, 250, 255, 0.88);
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

.wd-strip-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.wd-strip-btn {
  min-height: 28px;
  padding: 0 9px;
  border-radius: 999px;
  border: 1px solid rgba(148, 163, 184, 0.3);
  background: #fff;
  color: #334155;
  font-weight: 700;
  font-size: 0.76rem;
  cursor: pointer;
}

.wd-strip-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
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
  border-radius: 18px;
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
  border-left: 4px solid rgba(245, 158, 11, 0.72);
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
  border: none;
  border-radius: 999px;
  background: rgba(53, 94, 147, 0.82);
  color: #fff;
  font-size: 0.82rem;
  font-weight: 700;
  box-shadow: 0 12px 26px rgba(53, 94, 147, 0.24);
  backdrop-filter: blur(10px);
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

