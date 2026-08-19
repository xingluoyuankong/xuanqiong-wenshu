<template>
  <header class="wd-header">
    <div class="wd-header__lead">
      <button
        type="button"
        class="wd-header__icon"
        :title="pick('返回项目列表', 'Back to projects')"
        :aria-label="pick('返回项目列表', 'Back to projects')"
        @click="emit('goBack')"
      >
        <ArrowLeft class="wd-header__icon-glyph" aria-hidden="true" />
      </button>
      <button
        type="button"
        class="wd-header__icon"
        :title="sidebarToggleLabel"
        :aria-label="sidebarToggleLabel"
        :aria-pressed="props.sidebarOpen"
        @click="emit('toggleSidebar')"
      >
        <PanelLeftClose v-if="props.sidebarOpen" class="wd-header__icon-glyph" aria-hidden="true" />
        <PanelLeftOpen v-else class="wd-header__icon-glyph" aria-hidden="true" />
      </button>

      <div class="wd-header__identity">
        <h1 class="wd-header__title">{{ projectTitle }}</h1>
        <p class="wd-header__meta">{{ metaText }}</p>
      </div>

      <span v-if="statusTone" :class="['wd-header__status', `wd-header__status--${statusTone}`]">
        <i class="wd-header__status-dot" aria-hidden="true"></i>
        {{ statusText }}
      </span>
    </div>

    <div class="wd-header__actions">
      <button
        type="button"
        class="wd-header__icon"
        :title="switchLabel"
        :aria-label="switchLabel"
        @click="toggleLocale"
      >
        <Languages class="wd-header__icon-glyph" aria-hidden="true" />
      </button>

      <PixelMascotPicker />

      <details ref="moreMenuRef" class="wd-header__more" @keydown.esc="closeMoreMenu">
        <summary class="wd-header__icon wd-header__more-summary" :title="pick('更多操作', 'More actions')">
          <MoreHorizontal class="wd-header__icon-glyph" aria-hidden="true" />
        </summary>
        <div class="wd-header__menu" role="menu">
          <p class="wd-header__menu-note">{{ activeStyleText }}</p>
          <button type="button" class="wd-header__menu-item" :disabled="!props.canPrevChapter" @click="runMenu('prevChapter')">
            {{ pick('上一章', 'Previous chapter') }}
          </button>
          <button type="button" class="wd-header__menu-item" :disabled="!props.canNextChapter" @click="runMenu('nextChapter')">
            {{ pick('下一章', 'Next chapter') }}
          </button>
          <span class="wd-header__menu-line" aria-hidden="true"></span>
          <button
            v-if="props.canOpenVersionsCurrent && primaryKind !== 'versions'"
            type="button"
            class="wd-header__menu-item"
            @click="runMenu('openVersionsCurrent')"
          >
            {{ pick('查看候选版本', 'View candidates') }}
          </button>
          <button
            v-if="reviewActionMode && primaryKind !== 'review'"
            type="button"
            class="wd-header__menu-item"
            @click="runMenu(reviewActionMode === 'all' ? 'reviewAllVersionsCurrent' : 'evaluateCurrent')"
          >
            {{ reviewActionLabel }}
          </button>
          <button
            v-if="props.canGenerateCurrent && primaryKind !== 'generate'"
            type="button"
            class="wd-header__menu-item"
            @click="runMenu('generateCurrent')"
          >
            {{ generateLabel }}
          </button>
          <button
            v-if="props.canTerminateCurrent"
            type="button"
            class="wd-header__menu-item wd-header__menu-item--danger"
            @click="runMenu('terminateCurrent')"
          >
            {{ pick('终止后台处理', 'Stop background task') }}
          </button>
          <span class="wd-header__menu-line" aria-hidden="true"></span>
          <button type="button" class="wd-header__menu-item" @click="runMenu('viewProjectDetail')">
            {{ pick('项目详情', 'Project details') }}
          </button>
          <button type="button" class="wd-header__menu-item" @click="runMenu('openSkills')">
            {{ pick('写作技能', 'Writing skills') }}
          </button>
          <button type="button" class="wd-header__menu-item" @click="runMenu('toggleShortcutHelp')">
            {{ pick('快捷键', 'Shortcuts') }}
          </button>
          <template v-if="props.isAdmin">
            <span class="wd-header__menu-line" aria-hidden="true"></span>
            <button type="button" class="wd-header__menu-item" @click="runMenu('openRuntimeLogs')">
              {{ pick('运行日志', 'Runtime logs') }}
            </button>
            <button type="button" class="wd-header__menu-item" @click="runMenu('openAdminPanel')">
              {{ pick('管理后台', 'Admin panel') }}
            </button>
          </template>
        </div>
      </details>

      <button v-if="primaryKind" type="button" class="wd-header__primary" @click="handlePrimary">
        {{ primaryLabel }}
      </button>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ArrowLeft, Languages, MoreHorizontal, PanelLeftClose, PanelLeftOpen } from 'lucide-vue-next'
import type { GenerationRuntime, NovelProject, WorkspaceSummary } from '@/api/novel'
import { useLocale } from '@/composables/useLocale'
import PixelMascotPicker from '@/components/shared/PixelMascotPicker.vue'

const props = defineProps<{
  project: NovelProject | null
  progress: number
  completedChapters: number
  totalChapters: number
  workspaceSummary?: WorkspaceSummary | null
  generationRuntime?: GenerationRuntime | null
  selectedChapterNumber: number | null
  sidebarOpen: boolean
  canGenerateCurrent: boolean
  generateCurrentLabel?: string
  canEvaluateCurrent: boolean
  canConfirmCurrent: boolean
  canTerminateCurrent: boolean
  canOpenVersionsCurrent: boolean
  canReviewAllVersionsCurrent: boolean
  canPrevChapter: boolean
  canNextChapter: boolean
  isCurrentChapterBusy: boolean
  isCurrentChapterTrackable: boolean
  taskChapterNumber: number | null
  taskGenerationRuntime?: GenerationRuntime | null
  taskTrackable: boolean
  statusFetchFailureCount?: number
  activeStyleProfile?: { name?: string; source_ids?: string[]; profile_type?: string } | null
  isAdmin?: boolean
  headerCollapsed?: boolean
}>()

const emit = defineEmits([
  'goBack',
  'viewProjectDetail',
  'toggleSidebar',
  'prevChapter',
  'nextChapter',
  'generateCurrent',
  'evaluateCurrent',
  'reviewAllVersionsCurrent',
  'openVersionsCurrent',
  'confirmCurrent',
  'terminateCurrent',
  'toggleShortcutHelp',
  'openSkills',
  'openAdminPanel',
  'openRuntimeLogs',
  'toggleHeaderCollapse',
])
const { pick, switchLabel, toggleLocale, formatWords } = useLocale()

/** 「更多」下拉用原生 details 实现，不引入额外依赖 */
const moreMenuRef = ref<HTMLDetailsElement | null>(null)
const closeMoreMenu = () => {
  if (moreMenuRef.value) moreMenuRef.value.open = false
}

type MenuEvent =
  | 'prevChapter'
  | 'nextChapter'
  | 'openVersionsCurrent'
  | 'reviewAllVersionsCurrent'
  | 'evaluateCurrent'
  | 'generateCurrent'
  | 'terminateCurrent'
  | 'viewProjectDetail'
  | 'openSkills'
  | 'toggleShortcutHelp'
  | 'openRuntimeLogs'
  | 'openAdminPanel'

/** 菜单项统一走这里：先派发事件再收起面板 */
function runMenu(event: MenuEvent) {
  emit(event)
  closeMoreMenu()
}

const projectTitle = computed(() => props.project?.title || pick('正在加载项目…', 'Loading project…'))
const sidebarToggleLabel = computed(() => props.sidebarOpen ? pick('收起章节目录', 'Hide chapter list') : pick('展开章节目录', 'Show chapter list'))

const chapterText = computed(() => {
  const target = props.selectedChapterNumber || props.workspaceSummary?.active_chapter || props.workspaceSummary?.next_chapter_to_generate
  if (!target) return pick('未选择章节', 'No chapter selected')
  return pick(`第 ${target} 章`, `Chapter ${target}`)
})

/** 副标题只保留三段最关键的进度信息，其余细节交给侧栏与工作区 */
const metaText = computed(() => {
  const total = props.totalChapters || 0
  const progressText = total
    ? pick(`完成 ${props.completedChapters}/${total} 章`, `${props.completedChapters}/${total} chapters done`)
    : pick(`完成 ${props.completedChapters} 章`, `${props.completedChapters} chapters done`)
  const words = formatWords(props.workspaceSummary?.total_word_count || 0)
  return [chapterText.value, progressText, words].join(pick(' · ', ' · '))
})

const statusTone = computed<'warning' | 'danger' | ''>(() => {
  if (props.isCurrentChapterBusy) return 'warning'
  if (props.workspaceSummary?.failed_chapters) return 'danger'
  return ''
})

const statusText = computed(() => {
  if (statusTone.value === 'warning') return pick('后台处理中', 'Working')
  if (statusTone.value === 'danger') return pick('有异常章节', 'Needs attention')
  return ''
})

const activeStyleText = computed(() => {
  const profile = props.activeStyleProfile
  if (!profile) return pick('未启用外部文风', 'No external style applied')
  const sourceCount = Array.isArray(profile.source_ids) ? profile.source_ids.length : 0
  const name = profile.name || pick('外部参考文风', 'External style')
  return sourceCount > 0
    ? pick(`当前文风：${name}（来源 ${sourceCount} 条）`, `Style: ${name} (${sourceCount} sources)`)
    : pick(`当前文风：${name}`, `Style: ${name}`)
})

const reviewActionMode = computed<'all' | 'single' | null>(() => {
  if (props.canReviewAllVersionsCurrent) return 'all'
  return props.canEvaluateCurrent ? 'single' : null
})
const reviewActionLabel = computed(() => reviewActionMode.value === 'all'
  ? pick('AI 综合评审', 'AI batch review')
  : pick('AI 复评正文', 'AI re-review'))

const generateLabel = computed(() => props.generateCurrentLabel
  || (props.selectedChapterNumber ? pick(`生成第 ${props.selectedChapterNumber} 章`, `Generate chapter ${props.selectedChapterNumber}`) : pick('开始创作', 'Start writing')))

/** 一屏只允许 1 个实心主操作，按紧急度选出唯一那个，其余全部降级进「更多」 */
const primaryKind = computed<'confirm' | 'generate' | 'review' | 'versions' | ''>(() => {
  if (props.canConfirmCurrent) return 'confirm'
  if (props.canGenerateCurrent) return 'generate'
  if (reviewActionMode.value) return 'review'
  if (props.canOpenVersionsCurrent) return 'versions'
  return ''
})

const primaryLabel = computed(() => {
  if (primaryKind.value === 'confirm') return pick('确认版本', 'Confirm version')
  if (primaryKind.value === 'generate') return generateLabel.value
  if (primaryKind.value === 'review') return reviewActionLabel.value
  if (primaryKind.value === 'versions') return pick('查看候选版本', 'View candidates')
  return ''
})

function handlePrimary() {
  if (primaryKind.value === 'confirm') return emit('confirmCurrent')
  if (primaryKind.value === 'generate') return emit('generateCurrent')
  if (primaryKind.value === 'review') {
    return reviewActionMode.value === 'all' ? emit('reviewAllVersionsCurrent') : emit('evaluateCurrent')
  }
  if (primaryKind.value === 'versions') return emit('openVersionsCurrent')
}
</script>

<style scoped>
.wd-header {
  display: flex;
  height: var(--xq-header-height);
  align-items: center;
  justify-content: space-between;
  gap: var(--xq-space-4);
  padding: 0 var(--xq-space-4);
  border-bottom: 1px solid var(--xq-border);
  background: var(--xq-surface);
  font-family: var(--xq-font-sans);
}

.wd-header__lead {
  display: flex;
  min-width: 0;
  flex: 1;
  align-items: center;
  gap: var(--xq-space-2);
}

.wd-header__identity {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 2px;
  margin-left: var(--xq-space-1);
}

.wd-header__title {
  margin: 0;
  overflow: hidden;
  color: var(--xq-text);
  font-size: var(--xq-text-md);
  font-weight: var(--xq-weight-semibold);
  line-height: var(--xq-leading-tight);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wd-header__meta {
  margin: 0;
  overflow: hidden;
  color: var(--xq-text-muted);
  font-size: var(--xq-text-sm);
  font-variant-numeric: tabular-nums;
  line-height: var(--xq-leading-tight);
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* 状态徽标：pill + soft 背景 + 同色系 1px 描边 + 状态圆点 */
.wd-header__status {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  gap: var(--xq-space-1);
  height: 22px;
  padding: 0 var(--xq-space-2);
  border: 1px solid var(--xq-border);
  border-radius: var(--xq-radius-pill);
  font-size: var(--xq-text-2xs);
  white-space: nowrap;
}

.wd-header__status-dot {
  width: 6px;
  height: 6px;
  border-radius: var(--xq-radius-pill);
  background: currentColor;
}

.wd-header__status--warning {
  border-color: var(--xq-warning-border);
  background: var(--xq-warning-soft);
  color: var(--xq-warning-text);
}

.wd-header__status--danger {
  border-color: var(--xq-danger-border);
  background: var(--xq-danger-soft);
  color: var(--xq-danger-text);
}

.wd-header__actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: var(--xq-space-2);
}

.wd-header__icon {
  display: inline-flex;
  width: 32px;
  height: 32px;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: var(--xq-radius-md);
  background: transparent;
  color: var(--xq-text-muted);
  cursor: pointer;
  transition: background var(--xq-fast), color var(--xq-fast);
}

.wd-header__icon:hover {
  background: var(--xq-surface-hover);
  color: var(--xq-text);
}

.wd-header__icon-glyph {
  width: 16px;
  height: 16px;
}
.wd-header__more {
  position: relative;
}

.wd-header__more-summary {
  list-style: none;
}

.wd-header__more-summary::-webkit-details-marker {
  display: none;
}

.wd-header__more[open] .wd-header__more-summary {
  background: var(--xq-surface-hover);
  color: var(--xq-text);
}

.wd-header__menu {
  position: absolute;
  right: 0;
  top: calc(100% + var(--xq-space-2));
  z-index: 60;
  display: grid;
  width: 216px;
  gap: 2px;
  padding: var(--xq-space-2);
  border: 1px solid var(--xq-border);
  border-radius: var(--xq-radius-md);
  background: var(--xq-surface);
  box-shadow: var(--xq-shadow-md);
}

.wd-header__menu-note {
  margin: 0;
  padding: var(--xq-space-1) var(--xq-space-2) var(--xq-space-2);
  color: var(--xq-text-faint);
  font-size: var(--xq-text-2xs);
  line-height: var(--xq-leading-snug);
}

.wd-header__menu-line {
  height: 1px;
  margin: var(--xq-space-1) 0;
  background: var(--xq-border-soft);
}

.wd-header__menu-item {
  min-height: 32px;
  padding: 0 var(--xq-space-2);
  border: 0;
  border-radius: var(--xq-radius-sm);
  background: transparent;
  color: var(--xq-text-body);
  font-family: inherit;
  font-size: var(--xq-text-sm);
  text-align: left;
  cursor: pointer;
}

.wd-header__menu-item:hover:not(:disabled) {
  background: var(--xq-surface-hover);
  color: var(--xq-text);
}

.wd-header__menu-item:disabled {
  color: var(--xq-text-faint);
  cursor: not-allowed;
}

.wd-header__menu-item--danger {
  color: var(--xq-danger-text);
}
/* 全屏唯一的实心主操作 */
.wd-header__primary {
  display: inline-flex;
  height: 32px;
  max-width: 200px;
  align-items: center;
  justify-content: center;
  padding: 0 var(--xq-space-4);
  overflow: hidden;
  border: 0;
  border-radius: var(--xq-radius-md);
  background: var(--xq-accent);
  color: var(--xq-text-inverse);
  font-family: inherit;
  font-size: var(--xq-text-sm);
  font-weight: var(--xq-weight-medium);
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
  transition: background var(--xq-fast);
}

.wd-header__primary:hover {
  background: var(--xq-accent-hover);
}

.wd-header button:focus-visible,
.wd-header summary:focus-visible {
  outline: none;
  box-shadow: var(--xq-ring);
}

@media (max-width: 860px) {
  .wd-header {
    gap: var(--xq-space-2);
    padding: 0 var(--xq-space-3);
  }

  .wd-header__meta,
  .wd-header__status {
    display: none;
  }
}
</style>

