<template>
  <div class="wd-sidebar-root">
    <div
      v-if="sidebarOpen"
      class="wd-sidebar__scrim"
      role="presentation"
      @click="emit('closeSidebar')"
    ></div>

    <aside :class="['wd-sidebar', sidebarOpen ? 'is-open' : 'is-closed']" :aria-hidden="!sidebarOpen">
      <div class="wd-sidebar__head">
        <span class="wd-sidebar__group-title">{{ pick('章节目录', 'Chapters') }}</span>
        <span class="wd-sidebar__count">{{ outlineItems.length }}</span>
        <button
          type="button"
          class="wd-sidebar__close"
          :title="pick('收起目录', 'Hide list')"
          :aria-label="pick('收起目录', 'Hide list')"
          @click="emit('closeSidebar')"
        >
          <X class="wd-sidebar__icon" aria-hidden="true" />
        </button>
      </div>

      <nav class="wd-sidebar__list" :aria-label="pick('章节列表', 'Chapter list')">
        <button
          v-for="item in outlineItems"
          :key="item.chapter_number"
          type="button"
          :class="['wd-chapter', item.chapter_number === selectedChapterNumber ? 'is-active' : '']"
          :aria-current="item.chapter_number === selectedChapterNumber ? 'true' : undefined"
          @click="emit('selectChapter', item.chapter_number)"
        >
          <span class="wd-chapter__no">{{ formatChapterNo(item.chapter_number) }}</span>
          <span class="wd-chapter__title">{{ item.title || pick(`第 ${item.chapter_number} 章`, `Chapter ${item.chapter_number}`) }}</span>
          <i
            :class="['wd-chapter__dot', `wd-chapter__dot--${statusTone(item.chapter_number)}`]"
            :title="statusText(item.chapter_number)"
          ></i>
        </button>
        <p v-if="!outlineItems.length" class="wd-sidebar__empty">
          {{ pick('还没有章节大纲，先生成一批大纲再开始写作。', 'No outline yet. Generate chapter outlines first.') }}
        </p>
      </nav>

      <section v-if="selectedOutline" class="wd-sidebar__current">
        <div class="wd-sidebar__current-head">
          <span class="wd-sidebar__group-title">{{ pick('当前章节', 'Current chapter') }}</span><span :class="['wd-sidebar__state', `wd-sidebar__state--${statusTone(selectedOutline.chapter_number)}`]">{{ statusText(selectedOutline.chapter_number) }}</span>
        </div>
        <h3 class="wd-sidebar__current-title">
          {{ pick(`第 ${selectedOutline.chapter_number} 章`, `Chapter ${selectedOutline.chapter_number}`) }}
          <span v-if="selectedOutline.title">{{ punct.colon }}{{ selectedOutline.title }}</span>
        </h3>
        <p class="wd-sidebar__current-summary">
          {{ selectedOutline.summary || pick('这一章还没有摘要。', 'No summary for this chapter yet.') }}
        </p>
        <p v-if="currentQualitySummary" :class="['wd-sidebar__quality', `wd-sidebar__quality--${currentQualitySummary.tone}`]">
          {{ currentQualitySummary.label }}
          <span v-if="currentQualitySummary.issues.length">{{ punct.paren(currentQualitySummary.issues.join(punct.comma)) }}</span>
        </p>
        <div class="wd-sidebar__current-actions">
          <button type="button" class="wd-sidebar__link" @click="emit('editChapter', selectedOutline.chapter_number)">
            {{ pick('编辑大纲', 'Edit outline') }}
          </button>
          <button
            v-if="canDeleteSelectedChapter"
            type="button"
            class="wd-sidebar__link wd-sidebar__link--danger"
            @click="handleDeleteCurrentChapter"
          >
            {{ pick('删除本章', 'Delete chapter') }}
          </button>
        </div>
      </section>

      <div class="wd-sidebar__foot">
        <button
          type="button"
          class="wd-sidebar__outline-btn"
          :disabled="isGeneratingOutline"
          @click="emit('generateOutline')"
        >
          <FilePlus class="wd-sidebar__icon" aria-hidden="true" />{{ isGeneratingOutline ? pick('生成中…', 'Generating…') : pick('生成后续大纲', 'Generate more outline') }}
        </button>
      </div>
    </aside>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { FilePlus, X } from 'lucide-vue-next'
import { globalAlert } from '@/composables/useAlert'
import { useLocale } from '@/composables/useLocale'
import type { ChapterOutline, NovelProject, WorkspaceSummary } from '@/api/novel'
import { buildChapterQualitySummary } from '@/utils/chapterQuality'

interface Props {
  project: NovelProject
  sidebarOpen: boolean
  selectedChapterNumber: number | null
  generatingChapter: number | null
  evaluatingChapter: number | null
  isGeneratingOutline: boolean
  workspaceSummary?: WorkspaceSummary | null
}

const props = defineProps<Props>()

const emit = defineEmits([
  'closeSidebar',
  'selectChapter',
  'editChapter',
  'deleteChapter',
  'generateOutline',
  'navChange',
])

const { pick, punct } = useLocale()

/** 章号定宽两位，配合 tabular-nums 让列表左列不抖动 */
const formatChapterNo = (chapterNumber: number) => String(chapterNumber).padStart(2, '0')

const outlineItems = computed<ChapterOutline[]>(() => {
  const explicitOutlines = props.project.blueprint?.chapter_outline
  if (explicitOutlines?.length) {
    return [...explicitOutlines].sort((a, b) => a.chapter_number - b.chapter_number)
  }

  return [...props.project.chapters]
    .sort((a, b) => a.chapter_number - b.chapter_number)
    .map((chapter) => ({
      chapter_number: chapter.chapter_number,
      title: chapter.title || pick(`第 ${chapter.chapter_number} 章`, `Chapter ${chapter.chapter_number}`),
      summary: chapter.summary || '',
    }))
})

const selectedOutline = computed(() => {
  if (props.selectedChapterNumber === null) return outlineItems.value[0] || null
  return outlineItems.value.find((chapter) => chapter.chapter_number === props.selectedChapterNumber) || null
})

const currentChapter = computed(() => {
  if (!selectedOutline.value) return null
  return props.project.chapters.find((chapter) => chapter.chapter_number === selectedOutline.value?.chapter_number) || null
})

const currentQualitySummary = computed(() => buildChapterQualitySummary(
  currentChapter.value,
  currentChapter.value?.generation_runtime,
))

const getChapter = (chapterNumber: number) =>
  props.project.chapters.find((chapter) => chapter.chapter_number === chapterNumber)

const getChapterStatus = (chapterNumber: number) =>
  getChapter(chapterNumber)?.generation_status || 'not_generated'

const isChapterCompleted = (chapterNumber: number) => getChapterStatus(chapterNumber) === 'successful'

const isChapterRunning = (chapterNumber: number) =>
  props.generatingChapter === chapterNumber || props.evaluatingChapter === chapterNumber

const statusText = (chapterNumber: number) => {
  const status = getChapterStatus(chapterNumber)
  if (status === 'successful') return pick('已完成', 'Done')
  if (status === 'generating') return pick('生成中', 'Writing')
  if (status === 'evaluating') return pick('评估中', 'Reviewing')
  if (status === 'selecting' || status === 'waiting_for_confirm') return pick('待确认', 'To confirm')
  if (status === 'failed' || status === 'evaluation_failed') return pick('异常', 'Failed')
  if (isChapterRunning(chapterNumber)) return pick('处理中', 'Working')
  return pick('未开始', 'Not started')
}

/** 状态只用 8px 圆点表达，避免整列彩色 pill 抢视觉 */
const statusTone = (chapterNumber: number): 'success' | 'warning' | 'danger' | 'muted' => {
  const status = getChapterStatus(chapterNumber)
  if (status === 'successful') return 'success'
  if (status === 'failed' || status === 'evaluation_failed') return 'danger'
  if (['generating', 'evaluating', 'selecting', 'waiting_for_confirm'].includes(status)) return 'warning'
  return isChapterRunning(chapterNumber) ? 'warning' : 'muted'
}

const canDeleteSelectedChapter = computed(() => {
  if (!selectedOutline.value) return false
  const chapterNumber = selectedOutline.value.chapter_number
  if (isChapterCompleted(chapterNumber)) return false
  const chapterNumbers = outlineItems.value.map((chapter) => chapter.chapter_number)
  return chapterNumber === Math.max(...chapterNumbers)
})

async function handleDeleteCurrentChapter() {
  if (!selectedOutline.value || !canDeleteSelectedChapter.value) return
  const chapterNumber = selectedOutline.value.chapter_number
  const confirmed = await globalAlert.showConfirm(
    pick(
      `确定删除第 ${chapterNumber} 章吗？只允许删除末尾未完成章节。`,
      `Delete chapter ${chapterNumber}? Only the last unfinished chapter can be removed.`,
    ),
    pick('确认删除', 'Confirm deletion'),
  )
  if (!confirmed) return
  emit('deleteChapter', chapterNumber)
}
</script>

<style scoped>
/* ---------- 外壳：280px 定宽侧栏，收起时不占位 ---------- */
.wd-sidebar-root {
  flex: 0 0 auto;
  min-height: 0;
}

.wd-sidebar {
  display: flex;
  flex-direction: column;
  width: 280px;
  max-height: 100%;
  overflow: hidden;
  border: 1px solid var(--xq-border);
  border-radius: var(--xq-radius-lg);
  background: var(--xq-surface);
}

.wd-sidebar.is-closed {
  display: none;
}

/* 遮罩只在窄屏抽屉态出现，桌面端常驻布局不需要 */
.wd-sidebar__scrim {
  display: none;
}

/* ---------- 头部：标题 + 计数 + 收起，32px 行高 ---------- */
.wd-sidebar__head {
  display: flex;
  align-items: center;
  gap: var(--xq-space-2);
  flex: 0 0 auto;
  height: var(--xq-space-12);
  padding: 0 var(--xq-space-3);
  border-bottom: 1px solid var(--xq-border);
}

.wd-sidebar__group-title {
  color: var(--xq-text-muted);
  font-size: var(--xq-text-2xs);
  font-weight: var(--xq-weight-semibold);
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.wd-sidebar__count {
  min-width: 20px;
  padding: 0 var(--xq-space-1);
  border-radius: var(--xq-radius-pill);
  background: var(--xq-surface-2);
  color: var(--xq-text-muted);
  font-size: var(--xq-text-2xs);
  font-variant-numeric: tabular-nums;
  text-align: center;
}

.wd-sidebar__close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  margin-left: auto;
  padding: 0;
  border: none;
  border-radius: var(--xq-radius-sm);
  background: transparent;
  color: var(--xq-text-faint);
  cursor: pointer;
  transition: background var(--xq-fast), color var(--xq-fast);
}

.wd-sidebar__close:hover {
  background: var(--xq-surface-hover);
  color: var(--xq-text-body);
}

.wd-sidebar__icon {
  width: 14px;
  height: 14px;
}
/* ---------- 章节列表：40px 行高，状态只用 8px 色点 ---------- */
.wd-sidebar__list {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  padding: var(--xq-space-2);
}

.wd-chapter {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr) 8px;
  align-items: center;
  gap: var(--xq-space-2);
  width: 100%;
  height: var(--xq-space-10);
  padding: 0 var(--xq-space-2);
  border: none;
  border-radius: var(--xq-radius-sm);
  background: transparent;
  color: var(--xq-text-body);
  font-size: var(--xq-text-sm);
  text-align: left;
  cursor: pointer;
  transition: background var(--xq-fast), color var(--xq-fast);
}

.wd-chapter:hover {
  background: var(--xq-surface-hover);
}

.wd-chapter:focus-visible {
  outline: none;
  box-shadow: var(--xq-ring);
}

.wd-chapter.is-active {
  background: var(--xq-accent-soft);
  color: var(--xq-accent-text);
  font-weight: var(--xq-weight-medium);
}

.wd-chapter__no {
  color: var(--xq-text-faint);
  font-size: var(--xq-text-2xs);
  font-variant-numeric: tabular-nums;
}

.wd-chapter.is-active .wd-chapter__no {
  color: var(--xq-accent-text);
}

.wd-chapter__title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wd-chapter__dot {
  width: 8px;
  height: 8px;
  border-radius: var(--xq-radius-pill);
  background: var(--xq-border-strong);
}

.wd-chapter__dot--success {
  background: var(--xq-success);
}

.wd-chapter__dot--warning {
  background: var(--xq-warning);
}

.wd-chapter__dot--danger {
  background: var(--xq-danger);
}

.wd-chapter__dot--muted {
  background: var(--xq-border-strong);
}

.wd-sidebar__empty {
  margin: var(--xq-space-2);
  color: var(--xq-text-faint);
  font-size: var(--xq-text-xs);
  line-height: var(--xq-leading-snug);
}
/* ---------- 当前章节：唯一的次级信息块，用分隔线而不是卡片 ---------- */
.wd-sidebar__current {
  flex: 0 0 auto;
  padding: var(--xq-space-3);
  border-top: 1px solid var(--xq-border);
}

.wd-sidebar__current-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--xq-space-2);
  margin-bottom: var(--xq-space-2);
}

.wd-sidebar__state {
  color: var(--xq-text-muted);
  font-size: var(--xq-text-2xs);
}

.wd-sidebar__state--success {
  color: var(--xq-success-text);
}

.wd-sidebar__state--warning {
  color: var(--xq-warning-text);
}

.wd-sidebar__state--danger {
  color: var(--xq-danger-text);
}

.wd-sidebar__current-title {
  margin: 0 0 var(--xq-space-1);
  color: var(--xq-text);
  font-size: var(--xq-text-sm);
  font-weight: var(--xq-weight-semibold);
  line-height: var(--xq-leading-snug);
}

.wd-sidebar__current-summary {
  margin: 0;
  color: var(--xq-text-muted);
  font-size: var(--xq-text-xs);
  line-height: var(--xq-leading-snug);
  /* 摘要最多 3 行，避免侧栏被长文本撑开 */
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  overflow: hidden;
}

.wd-sidebar__quality {
  margin: var(--xq-space-2) 0 0;
  color: var(--xq-text-muted);
  font-size: var(--xq-text-2xs);
  line-height: var(--xq-leading-snug);
}

.wd-sidebar__quality--success {
  color: var(--xq-success-text);
}

.wd-sidebar__quality--warning {
  color: var(--xq-warning-text);
}

.wd-sidebar__quality--danger {
  color: var(--xq-danger-text);
}
.wd-sidebar__current-actions {
  display: flex;
  gap: var(--xq-space-3);
  margin-top: var(--xq-space-2);
}

/* 次级操作降级为文字链接，侧栏里不再出现第二个实心按钮 */
.wd-sidebar__link {
  padding: 0;
  border: none;
  background: none;
  color: var(--xq-accent);
  font-size: var(--xq-text-xs);
  cursor: pointer;
}

.wd-sidebar__link:hover {
  color: var(--xq-accent-hover);
  text-decoration: underline;
}

.wd-sidebar__link--danger {
  color: var(--xq-text-muted);
}

.wd-sidebar__link--danger:hover {
  color: var(--xq-danger);
}

/* ---------- 底部：侧栏唯一的主操作 ---------- */
.wd-sidebar__foot {
  flex: 0 0 auto;
  padding: var(--xq-space-3);
  border-top: 1px solid var(--xq-border);
}

.wd-sidebar__outline-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--xq-space-2);
  width: 100%;
  height: var(--xq-space-8);
  border: 1px solid var(--xq-border);
  border-radius: var(--xq-radius-sm);
  background: var(--xq-surface);
  color: var(--xq-text-body);
  font-size: var(--xq-text-xs);
  cursor: pointer;
  transition: background var(--xq-fast), border-color var(--xq-fast);
}

.wd-sidebar__outline-btn:hover:not(:disabled) {
  border-color: var(--xq-border-strong);
  background: var(--xq-surface-hover);
}

.wd-sidebar__outline-btn:disabled {
  color: var(--xq-text-faint);
  cursor: not-allowed;
}
/* ---------- 窄屏：侧栏转为抽屉，避免挤压正文阅读宽度 ---------- */
@media (max-width: 1023px) {
  .wd-sidebar__scrim {
    display: block;
    position: fixed;
    inset: 0;
    z-index: 40;
    background: var(--xq-overlay);
  }

  .wd-sidebar {
    position: fixed;
    top: 0;
    left: 0;
    bottom: 0;
    z-index: 41;
    max-height: none;
    border-width: 0 1px 0 0;
    border-radius: 0;
    box-shadow: var(--xq-shadow-lg);
  }
}
</style>
