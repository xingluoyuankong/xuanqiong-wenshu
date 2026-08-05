<template>
  <div>
    <aside
      :class="[
        'wd-sidebar',
        sidebarOpen ? 'wd-sidebar--open' : 'wd-sidebar--closed',
      ]"
    >
      <div class="wd-sidebar wd-sidebar--left__panel">
        <!-- Compact Brand Row -->
        <div class="wd-sidebar wd-sidebar--left__brand">
          <span class="wd-sidebar wd-sidebar--left__brand-icon">📖</span>
          <span class="wd-sidebar wd-sidebar--left__brand-text">玄穹文枢</span>
          <button type="button" class="wd-sidebar wd-sidebar--left__close lg:hidden" @click="$emit('closeSidebar')">
            <X class="wd-btn-icon" aria-hidden="true" />
          </button>
        </div>

        <!-- Tab Navigation -->
        <nav class="wd-sidebar wd-sidebar--left__nav">
          <template v-for="tab in navTabs" :key="tab.key">
            <div v-if="tab.type === 'divider'" class="wd-nav-divider" />
            <a v-else-if="tab.href" :href="tab.href" class="wd-nav-item">
              <span class="wd-nav-item__icon">{{ tab.icon }}</span>
              <span class="wd-nav-item__label">{{ tab.label }}</span>
            </a>
            <button
              v-else
              type="button"
              :class="['wd-nav-item', activeTab === tab.key ? 'wd-nav-item--active' : '']"
              @click="activeTab = tab.key; $emit('navChange', tab.key)"
            >
              <span class="wd-nav-item__icon">{{ tab.icon }}</span>
              <span class="wd-nav-item__label">{{ tab.label }}</span>
            </button>
          </template>
        </nav>

        <!-- Story Summary (compact) -->
        <div class="wd-story-card">
          <div class="wd-story-card__row">
            <span class="wd-story-card__title">{{ project.blueprint?.style || '未定义风格' }}</span>
            <span class="wd-story-card__badge">{{ workspaceSummary?.total_chapters || 0 }}章</span>
          </div>
          <p class="wd-story-card__summary">
            {{ project.blueprint?.one_sentence_summary || '还没有故事概括，可以先完善蓝图。' }}
          </p>
        </div>

        <!-- Current Chapter (compact) -->
        <section v-if="selectedOutline" class="wd-current-card">
          <div class="wd-current-card__head">
            <span class="wd-current-card__eyebrow">当前章节</span>
            <span :class="['wd-status-pill', 'wd-status-pill--sm', statusClass(selectedOutline.chapter_number)]">
              {{ statusText(selectedOutline.chapter_number) }}
            </span>
          </div>
          <h3 class="wd-current-card__title">
            第 {{ selectedOutline.chapter_number }} 章 · {{ selectedOutline.title || `章节 ${selectedOutline.chapter_number}` }}
          </h3>
          <p class="wd-current-card__summary">
            {{ selectedOutline.summary || '当前章节还没有摘要。' }}
          </p>
        </section>

        <div v-else class="wd-empty">
          请从正文区章节条中选择章节
        </div>

        <!-- Bottom Action -->
        <div class="wd-bottom">
          <button
            type="button"
            class="wd-outline-btn wd-outline-btn--sm"
            :disabled="isGeneratingOutline"
            @click="$emit('generateOutline')"
          >
            <FilePlus class="wd-btn-icon wd-btn-icon--sm" aria-hidden="true" />
            {{ isGeneratingOutline ? '生成中...' : '生成后续大纲' }}
          </button>
        </div>
      </div>
    </aside>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { FilePlus, X } from 'lucide-vue-next'
import { globalAlert } from '@/composables/useAlert'
import type { ChapterOutline, NovelProject, WorkspaceSummary } from '@/api/novel'
import { resolveChapterActionDecision } from '@/utils/chapterGeneration'
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

const activeTab = ref('write')

const navTabs = [
  { key: 'write', icon: '✍️', label: '写作' },
  { key: 'outline', icon: '📋', label: '大纲' },
  { key: 'characters', icon: '👥', label: '角色' },
  { key: 'versions', icon: '📑', label: '版本' },
  { key: 'settings', icon: '⚙️', label: '设置' },
  { key: 'divider', icon: '', label: '—', type: 'divider' },
  { key: 'home', icon: '🏠', label: '主页', href: '/' },
  { key: 'projects', icon: '📚', label: '小说项目', href: '/projects' },
  { key: 'inspiration', icon: '💡', label: '灵感模式', href: '/inspiration' },
  { key: 'style-center', icon: '🎨', label: '文风中心', href: '/style-center' },
  { key: 'admin', icon: '⚡', label: '管理台', href: '/admin' },
  { key: 'llm-settings', icon: '🔧', label: 'LLM配置', href: '/llm-settings' },
]

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
const currentQualitySummary = computed(() => buildChapterQualitySummary(
  currentChapter.value,
  currentChapter.value?.generation_runtime,
))

const getChapter = (chapterNumber: number) =>
  props.project.chapters.find((chapter) => chapter.chapter_number === chapterNumber)

const getChapterStatus = (chapterNumber: number) =>
  getChapter(chapterNumber)?.generation_status || 'not_generated'

const isChapterCompleted = (chapterNumber: number) => getChapterStatus(chapterNumber) === 'successful'

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

const currentActionGuidance = computed(() => {
  if (!selectedOutline.value) return '生成、确认、终止等主操作统一放到顶部命令栏。'
  const decision = resolveChapterActionDecision(props.project, selectedOutline.value.chapter_number, {
    generatingChapter: props.generatingChapter,
    evaluatingChapter: props.evaluatingChapter,
  })
  if (!decision) return '主操作已收口到顶部命令栏。'
  if (decision.canOpenResult) return '当前章已有候选版本，请在顶部命令栏继续。'
  if (decision.mode === 'running') return '当前章仍在后台处理中，先看顶部任务栏进度。'
  if (decision.mode === 'disabled') return '当前章暂时没有可执行的主动作。'
  return `主操作已收口到顶部命令栏：${decision.label}。`
})
</script>

<style scoped>
/* --- LEFT SIDEBAR LAYOUT --- */
.wd-sidebar--left {
  position: fixed;
  left: 0;
  top: 55px;
  bottom: 0;
  width: 220px;
  z-index: 40;
  background: rgba(255,255,255,0.97);
  border-right: 1px solid rgba(148,163,184,0.12);
  overflow-y: auto;
  padding: 12px 8px;
}

.wd-sidebar__fixed {
  position: fixed;
  left: 0;
  top: 55px;
  bottom: 0;
  width: 220px;
  z-index: 40;
  background: rgba(255,255,255,0.98);
  backdrop-filter: blur(12px);
  border-right: 1px solid rgba(148,163,184,0.10);
  overflow-y: auto;
  padding: 10px 6px;
  transition: transform 0.3s ease;
}

.wd-sidebar__fixed.collapsed {
  transform: translateX(-180px);
}

.wd-sidebar {
  flex: none;
  min-width: 200px;
  width: clamp(200px, 16vw, 260px);
  flex-basis: clamp(200px, 16vw, 260px);
  opacity: 1;
  pointer-events: auto;
  overflow: visible;
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
    width: clamp(200px, 16vw, 260px);
    flex-basis: clamp(200px, 16vw, 260px);
  }

  .wd-sidebar--closed {
    width: 0;
    flex-basis: 0;
  }
}

@media (max-width: 1023px) {
  .wd-sidebar {
    position: relative;
    width: 100%;
    flex-basis: auto;
    transform: none;
    transition: opacity 0.2s ease;
  }

  .wd-sidebar--open {
    width: 100%;
    flex-basis: auto;
    opacity: 1;
    pointer-events: auto;
  }

  .wd-sidebar--closed {
    display: none;
  }
}

.wd-sidebar__panel {
  width: 100%;
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px;
  border-radius: 8px;
  background: linear-gradient(180deg, rgba(252, 254, 255, 0.98), rgba(241, 247, 255, 0.96));
  border: 1px solid rgba(156, 183, 220, 0.2);
  box-shadow: 0 12px 32px rgba(92, 130, 182, 0.1);
  overflow: auto;
}

/* Brand Row */
.wd-sidebar__brand {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 6px 8px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.1);
}

.wd-sidebar__brand-icon {
  font-size: 18px;
}

.wd-sidebar__brand-text {
  flex: 1;
  font-size: 13px;
  font-weight: 700;
  color: #0f172a;
}

.wd-sidebar__close {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: #64748b;
  cursor: pointer;
  border-radius: 4px;
}

.wd-sidebar__close:hover {
  background: rgba(148, 163, 184, 0.1);
}

/* Navigation Tabs */
.wd-sidebar__nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.wd-nav-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border: none;
  background: transparent;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s ease;
  text-align: left;
}

.wd-nav-item:hover {
  background: rgba(59, 130, 246, 0.06);
}

.wd-nav-item--active {
  background: rgba(59, 130, 246, 0.1);
  color: #1d4ed8;
}

.wd-nav-item__icon {
  font-size: 14px;
  width: 20px;
  text-align: center;
}

.wd-nav-item__label {
  font-size: 12px;
  font-weight: 600;
  color: #475569;
}

.wd-nav-item--active .wd-nav-item__label {
  color: #1d4ed8;
}

/* Story Card */
.wd-story-card {
  border-radius: 6px;
  border: 1px solid rgba(148, 163, 184, 0.12);
  background: rgba(255, 255, 255, 0.9);
  padding: 10px;
}

.wd-story-card__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.wd-story-card__title {
  font-size: 12px;
  font-weight: 700;
  color: #0f172a;
}

.wd-story-card__summary {
  margin: 6px 0 0;
  color: #64748b;
  line-height: 1.5;
  font-size: 11px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.wd-story-card__badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 20px;
  padding: 0 6px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
  background: rgba(79, 70, 229, 0.1);
  color: #4338ca;
  flex-shrink: 0;
}

/* Current Chapter Card */
.wd-current-card {
  border-radius: 6px;
  border: 1px solid rgba(148, 163, 184, 0.12);
  background: rgba(255, 255, 255, 0.9);
  padding: 10px;
  display: grid;
  gap: 6px;
}

.wd-current-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.wd-current-card__eyebrow {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: #6366f1;
}

.wd-current-card__title {
  margin: 0;
  font-size: 12px;
  font-weight: 700;
  color: #0f172a;
  line-height: 1.4;
}

.wd-current-card__summary {
  margin: 0;
  color: #64748b;
  font-size: 11px;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.wd-status-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  font-weight: 700;
}

.wd-status-pill--sm {
  min-height: 18px;
  padding: 0 6px;
  font-size: 10px;
}

.wd-status-pill--success {
  background: rgba(22, 163, 74, 0.1);
  color: #15803d;
}

.wd-status-pill--error {
  background: rgba(220, 38, 38, 0.1);
  color: #b91c1c;
}

.wd-status-pill--active {
  background: rgba(14, 165, 233, 0.12);
  color: #1d4ed8;
}

.wd-status-pill--idle {
  background: rgba(148, 163, 184, 0.12);
  color: #475569;
}

/* Empty State */
.wd-empty {
  border-radius: 6px;
  border: 1px dashed rgba(148, 163, 184, 0.25);
  padding: 12px 10px;
  color: #94a3b8;
  font-size: 11px;
  line-height: 1.5;
}

/* Bottom */
.wd-bottom {
  margin-top: auto;
}

.wd-outline-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  border-radius: 6px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  background: #fff;
  color: #334155;
  font-weight: 700;
  cursor: pointer;
}

.wd-outline-btn--sm {
  min-height: 32px;
  padding: 0 10px;
  font-size: 11px;
}

.wd-outline-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.wd-btn-icon {
  width: 14px;
  height: 14px;
  flex: 0 0 auto;
}

.wd-btn-icon--sm {
  width: 12px;
  height: 12px;
}

.wd-nav-divider {
  height: 1px;
  margin: 8px 12px;
  background: linear-gradient(90deg, transparent, #cbd5e1 20%, #cbd5e1 80%, transparent);
}

</style>
