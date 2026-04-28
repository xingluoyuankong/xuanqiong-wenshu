<template>
  <div>
    <div
      v-if="sidebarOpen"
      class="fixed inset-0 z-40 bg-slate-950/18 backdrop-blur-sm lg:hidden"
      @click="$emit('closeSidebar')"
    ></div>

    <aside
      :class="[
        'wd-sidebar',
        sidebarOpen ? 'wd-sidebar--open' : 'wd-sidebar--closed',
      ]"
    >
      <div class="wd-sidebar__panel">
        <div class="wd-sidebar__head">
          <div>
            <p class="wd-section-label">项目面板</p>
            <h2 class="wd-section-title">当前章节操作</h2>
          </div>
          <button type="button" class="wd-mini-btn lg:hidden" @click="$emit('closeSidebar')">
            {{ closeLabel }}
          </button>
        </div>

        <div class="wd-story-card">
          <div class="flex items-start justify-between gap-3">
            <div>
              <p class="wd-story-card__title">{{ project.blueprint?.style || '未定义风格' }}</p>
              <p class="wd-story-card__summary">
                {{ project.blueprint?.one_sentence_summary || '还没有故事概括，可以先完善蓝图。' }}
              </p>
            </div>
            <span class="wd-story-card__badge">{{ workspaceSummary?.total_chapters || 0 }} 章</span>
          </div>

          <div class="wd-story-stats">
            <div>
              <strong>{{ project.blueprint?.characters?.length || 0 }}</strong>
              <span>角色</span>
            </div>
            <div>
              <strong>{{ project.blueprint?.relationships?.length || 0 }}</strong>
              <span>关系</span>
            </div>
            <div>
              <strong>{{ workspaceSummary?.failed_chapters || 0 }}</strong>
              <span>异常</span>
            </div>
          </div>
        </div>

        <div v-if="workspaceSummary?.next_chapter_to_generate" class="wd-callout">
          <div>
            <p class="wd-callout__label">建议动作</p>
            <p class="wd-callout__text">
              优先推进第 {{ workspaceSummary.next_chapter_to_generate }} 章，保持上下文连续。
            </p>
          </div>
          <button type="button" class="wd-mini-btn wd-mini-btn--primary" @click="$emit('selectChapter', workspaceSummary.next_chapter_to_generate)">
            定位到该章
          </button>
        </div>

        <section v-if="selectedOutline" class="wd-current-card">
          <div class="wd-current-card__head">
            <div>
              <p class="wd-current-card__eyebrow">当前焦点</p>
              <h3>第 {{ selectedOutline.chapter_number }} 章 · {{ selectedOutline.title || `章节 ${selectedOutline.chapter_number}` }}</h3>
            </div>
            <span :class="['wd-status-pill', statusClass(selectedOutline.chapter_number)]">
              {{ statusText(selectedOutline.chapter_number) }}
            </span>
          </div>

          <p class="wd-current-card__summary">
            {{ selectedOutline.summary || '当前章节还没有摘要，可以先补全大纲后再继续创作。' }}
          </p>

          <div class="wd-current-meta">
            <span>正文字数：{{ currentChapter?.word_count || 0 }}</span>
            <span>候选版本：{{ currentChapter?.versions?.length || 0 }}</span>
            <span v-if="currentChapter?.generation_status">后台状态：{{ statusText(selectedOutline.chapter_number) }}</span>
          </div>

          <div class="wd-current-actions">
            <button
              type="button"
              :class="chapterAction(selectedOutline.chapter_number).mode === 'action' ? 'wd-mini-btn wd-mini-btn--primary' : 'wd-mini-btn'"
              :disabled="chapterAction(selectedOutline.chapter_number).disabled"
              :title="chapterAction(selectedOutline.chapter_number).reason"
              @click="handleChapterAction(selectedOutline.chapter_number)"
            >
              {{ chapterAction(selectedOutline.chapter_number).label }}
            </button>
            <button
              v-if="!isChapterCompleted(selectedOutline.chapter_number)"
              type="button"
              class="wd-mini-btn"
              @click="$emit('editChapter', selectedOutline)"
            >
              编辑当前大纲
            </button>
            <button
              v-if="canDeleteSelectedChapter"
              type="button"
              class="wd-mini-btn wd-mini-btn--danger"
              @click="handleDeleteCurrentChapter"
            >
              删除当前章
            </button>
          </div>

          <p v-if="chapterAction(selectedOutline.chapter_number).reason" class="wd-current-card__hint">
            {{ chapterAction(selectedOutline.chapter_number).reason }}
          </p>
        </section>

        <div v-else class="wd-empty">
          当前还没有选中章节，请先在正文区顶部的横向章节条中选择。
        </div>

        <div class="wd-bottom">
          <button
            type="button"
            class="wd-outline-btn"
            :disabled="isGeneratingOutline"
            @click="$emit('generateOutline')"
          >
            {{ isGeneratingOutline ? '正在生成大纲...' : '生成后续大纲' }}
          </button>
        </div>
      </div>
    </aside>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { globalAlert } from '@/composables/useAlert'
import type { ChapterOutline, NovelProject, WorkspaceSummary } from '@/api/novel'
import { resolveChapterActionDecision } from '@/utils/chapterGeneration'

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
  'generateChapter',
  'editChapter',
  'deleteChapter',
  'generateOutline',
])

const closeLabel = computed(() => (props.sidebarOpen ? '关闭' : '展开'))

const outlineItems = computed<ChapterOutline[]>(() => {
  const explicitOutlines = props.project.blueprint?.chapter_outline
  if (explicitOutlines?.length) {
    return [...explicitOutlines].sort((a, b) => a.chapter_number - b.chapter_number)
  }

  return [...props.project.chapters]
    .sort((a, b) => a.chapter_number - b.chapter_number)
    .map((chapter) => ({
      chapter_number: chapter.chapter_number,
      title: chapter.title || `第${chapter.chapter_number}章`,
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

const getChapter = (chapterNumber: number) =>
  props.project.chapters.find((chapter) => chapter.chapter_number === chapterNumber)

const getChapterStatus = (chapterNumber: number) =>
  getChapter(chapterNumber)?.generation_status || 'not_generated'

const isChapterCompleted = (chapterNumber: number) => getChapterStatus(chapterNumber) === 'successful'

const getChapterAction = (chapterNumber: number) => resolveChapterActionDecision(props.project, chapterNumber, {
  generatingChapter: props.generatingChapter,
  evaluatingChapter: props.evaluatingChapter,
})

const chapterAction = (chapterNumber: number) => {
  const decision = getChapterAction(chapterNumber)
  return {
    label: decision.label,
    disabled: decision.mode === 'running' || decision.mode === 'disabled',
    reason: decision.reason,
    mode: decision.mode,
    targetChapter: decision.targetChapterNumber ?? undefined,
  }
}

const statusText = (chapterNumber: number) => {
  const status = getChapterStatus(chapterNumber)
  if (status === 'successful') return '已完成'
  if (status === 'generating') return '生成中'
  if (status === 'evaluating') return '评估中'
  if (status === 'selecting' || status === 'waiting_for_confirm') return '待确认'
  if (status === 'failed' || status === 'evaluation_failed') return '异常'
  return '未开始'
}

const statusClass = (chapterNumber: number) => {
  const status = getChapterStatus(chapterNumber)
  if (status === 'successful') return 'wd-status-pill--success'
  if (status === 'failed' || status === 'evaluation_failed') return 'wd-status-pill--error'
  if (['generating', 'evaluating', 'selecting', 'waiting_for_confirm'].includes(status)) return 'wd-status-pill--active'
  return 'wd-status-pill--idle'
}

const canDeleteSelectedChapter = computed(() => {
  if (!selectedOutline.value) return false
  const chapterNumber = selectedOutline.value.chapter_number
  if (isChapterCompleted(chapterNumber)) return false
  const chapterNumbers = outlineItems.value.map((chapter) => chapter.chapter_number)
  return chapterNumber === Math.max(...chapterNumbers)
})

async function confirmGenerateChapter(chapterNumber: number) {
  const confirmed = await globalAlert.showConfirm(
    '重新生成会覆盖当前阶段结果，是否继续？',
    '确认生成',
  )

  if (confirmed) {
    emit('generateChapter', chapterNumber)
  }
}

function handleChapterAction(chapterNumber: number) {
  const action = chapterAction(chapterNumber)
  if (action.disabled) return

  if (action.mode === 'navigate' && action.targetChapter) {
    emit('selectChapter', action.targetChapter)
    return
  }

  void confirmGenerateChapter(chapterNumber)
}

async function handleDeleteCurrentChapter() {
  if (!selectedOutline.value || !canDeleteSelectedChapter.value) return
  const chapterNumber = selectedOutline.value.chapter_number
  const confirmed = await globalAlert.showConfirm(
    `确定删除第 ${chapterNumber} 章吗？只允许删除末尾未完成章节。`,
    '确认删除',
  )
  if (!confirmed) return
  emit('deleteChapter', chapterNumber)
}
</script>

<style scoped>
.wd-sidebar {
  flex: none;
  min-width: 0;
  width: 0;
  flex-basis: 0;
  opacity: 0;
  pointer-events: none;
  overflow: hidden;
}

.wd-sidebar--open {
  opacity: 1;
  pointer-events: auto;
}

@media (min-width: 1024px) {
  .wd-sidebar {
    position: relative;
    height: 100%;
    transition: width 0.24s ease, flex-basis 0.24s ease, opacity 0.2s ease;
  }

  .wd-sidebar--open {
    width: clamp(240px, 19vw, 300px);
    flex-basis: clamp(240px, 19vw, 300px);
  }

  .wd-sidebar--closed {
    width: 0;
    flex-basis: 0;
  }
}

@media (max-width: 1023px) {
  .wd-sidebar {
    position: fixed;
    left: 14px;
    top: 102px;
    bottom: 14px;
    width: min(24rem, calc(100vw - 24px));
    z-index: 50;
    transform: translateX(calc(-100% - 18px));
    transition: transform 0.24s ease, opacity 0.2s ease;
  }

  .wd-sidebar--open {
    transform: translateX(0);
  }
}

.wd-sidebar__panel {
  width: 100%;
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 10px;
  border-radius: 20px;
  background: linear-gradient(180deg, rgba(252, 254, 255, 0.98), rgba(241, 247, 255, 0.96));
  border: 1px solid rgba(156, 183, 220, 0.26);
  box-shadow: 0 24px 48px rgba(92, 130, 182, 0.16);
  overflow: auto;
}

.wd-sidebar__head,
.wd-story-stats,
.wd-bottom,
.wd-current-actions {
  display: grid;
  gap: 10px;
}

.wd-sidebar__head {
  grid-template-columns: 1fr auto;
  align-items: center;
}

.wd-section-label {
  margin: 0;
  font-size: 0.74rem;
  font-weight: 800;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #64748b;
}

.wd-section-title {
  margin: 4px 0 0;
  font-size: 1.08rem;
  font-weight: 800;
  color: #0f172a;
}

.wd-story-card,
.wd-current-card,
.wd-callout {
  border-radius: 18px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(255, 255, 255, 0.92);
  padding: 14px;
}

.wd-story-card__title {
  margin: 0;
  font-size: 1rem;
  font-weight: 800;
  color: #0f172a;
}

.wd-story-card__summary {
  margin: 8px 0 0;
  color: #475569;
  line-height: 1.65;
  font-size: 0.88rem;
}

.wd-story-card__badge,
.wd-status-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 0.78rem;
  font-weight: 800;
}

.wd-story-card__badge {
  background: rgba(79, 70, 229, 0.1);
  color: #4338ca;
}

.wd-story-stats {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin-top: 14px;
}

.wd-story-stats div {
  display: grid;
  gap: 4px;
  border-radius: 14px;
  background: #f8fafc;
  padding: 10px;
  text-align: center;
}

.wd-story-stats strong {
  font-size: 1rem;
  color: #0f172a;
}

.wd-story-stats span {
  color: #64748b;
  font-size: 0.78rem;
}

.wd-callout {
  display: grid;
  gap: 10px;
}

.wd-callout__label,
.wd-current-card__eyebrow {
  margin: 0;
  font-size: 0.74rem;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #6366f1;
}

.wd-callout__text,
.wd-current-card__summary,
.wd-current-card__hint {
  margin: 6px 0 0;
  color: #475569;
  line-height: 1.7;
  font-size: 0.88rem;
}

.wd-current-card {
  display: grid;
  gap: 12px;
}

.wd-current-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.wd-current-card__head h3 {
  margin: 4px 0 0;
  font-size: 1rem;
  font-weight: 800;
  color: #0f172a;
}

.wd-current-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.wd-current-meta span {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  background: #f8fafc;
  color: #475569;
  font-size: 0.78rem;
  font-weight: 700;
}

.wd-current-actions {
  grid-template-columns: 1fr;
}

.wd-status-pill--success {
  background: rgba(22, 163, 74, 0.12);
  color: #15803d;
}

.wd-status-pill--error {
  background: rgba(220, 38, 38, 0.12);
  color: #b91c1c;
}

.wd-status-pill--active {
  background: rgba(245, 158, 11, 0.14);
  color: #b45309;
}

.wd-status-pill--idle {
  background: rgba(148, 163, 184, 0.14);
  color: #475569;
}

.wd-bottom {
  margin-top: auto;
}

.wd-empty {
  border-radius: 18px;
  border: 1px dashed rgba(148, 163, 184, 0.34);
  padding: 18px 14px;
  color: #64748b;
  line-height: 1.7;
  font-size: 0.88rem;
}

.wd-mini-btn,
.wd-outline-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 38px;
  padding: 0 14px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.24);
  background: #fff;
  color: #334155;
  font-size: 0.84rem;
  font-weight: 800;
  cursor: pointer;
}

.wd-mini-btn:disabled,
.wd-outline-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.wd-mini-btn--primary,
.wd-outline-btn {
  background: #0f172a;
  color: #fff;
  border-color: #0f172a;
}

.wd-mini-btn--danger {
  background: rgba(254, 242, 242, 0.92);
  color: #b91c1c;
  border-color: rgba(248, 113, 113, 0.32);
}
</style>
