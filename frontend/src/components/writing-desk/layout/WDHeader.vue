<template>
  <header class="wd-header-shell xq-topbar xq-topbar--desk">
    <template v-if="props.headerCollapsed">
      <div class="wd-header-collapsed-bar">
        <div class="wd-header-collapsed-bar__summary">
          <strong>{{ collapsedTitle }}</strong>
          <span>{{ collapsedSubtitle }}</span>
        </div>
        <button type="button" class="wd-utility-btn wd-utility-btn--accent" @click="$emit('toggleHeaderCollapse')">展开顶部</button>
      </div></template>

    <template v-else>
      <div class="wd-header-main">
        <div class="wd-header-lead">
          <button type="button" class="wd-icon-btn" title="返回项目列表" @click="$emit('goBack')">
            <ArrowLeft class="h-5 w-5" aria-hidden="true" />
          </button>

          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-2">
              <span class="wd-brand-pill">玄穹文枢</span>
              <span v-if="isCurrentChapterBusy" class="wd-state-pill wd-state-pill--warning">后台处理中</span>
              <span v-else-if="workspaceSummary?.failed_chapters" class="wd-state-pill wd-state-pill--danger">有异常章节待处理</span>
            </div>

            <h1 class="mt-1 text-lg font-semibold tracking-tight text-slate-950 sm:text-[1.25rem]">
              {{ project?.title || '正在加载项目...' }}
            </h1>

            <div class="mt-2 flex flex-wrap items-center gap-2 text-[12px] text-slate-600">
              <span class="wd-meta-pill">{{ genreText }}</span>
              <span class="wd-meta-pill">完成 {{ completedChapters }}/{{ totalChapters || '未定' }} 章</span>
              <span class="wd-meta-pill">总字数 {{ totalWordCount }}</span>
              <span v-if="workspaceSummary?.in_progress_chapters" class="wd-meta-pill">处理中 {{ workspaceSummary.in_progress_chapters }} 章</span>
              <span v-if="workspaceSummary?.next_chapter_to_generate" class="wd-meta-pill wd-meta-pill--accent">建议推进第 {{ workspaceSummary.next_chapter_to_generate }} 章</span>
            </div>
          </div>
        </div>

        <div class="wd-header-actions">
          <button type="button" class="wd-utility-btn wd-utility-btn--accent" @click="$emit('toggleHeaderCollapse')">
            <PanelTopClose class="wd-btn-icon" aria-hidden="true" />
            收起顶部
          </button>
          <button
            type="button"
            class="wd-utility-btn wd-utility-btn--accent"
            :title="sidebarOpen ? '收起目录' : '展开目录'"
            @click="$emit('toggleSidebar')"
          >
            <PanelLeftClose v-if="sidebarOpen" class="wd-btn-icon" aria-hidden="true" />
            <PanelLeftOpen v-else class="wd-btn-icon" aria-hidden="true" />
            {{ sidebarOpen ? '收起目录' : '展开目录' }}
          </button>
          <details ref="utilityMenuRef" class="wd-utility-menu" @keydown.esc="closeUtilityMenu">
            <summary class="wd-utility-btn wd-utility-menu__summary">
              更多工具
              <span class="wd-shortcut-hint">⋯</span>
            </summary>
            <div class="wd-utility-menu__panel">
              <button type="button" class="wd-utility-menu__item" @click="emit('viewProjectDetail'); closeUtilityMenu()">项目详情</button>
              <button type="button" class="wd-utility-menu__item" @click="emit('openSkills'); closeUtilityMenu()">写作技能</button>
              <button type="button" class="wd-utility-menu__item" @click="emit('toggleShortcutHelp'); closeUtilityMenu()">快捷键</button>
              <button v-if="isAdmin" type="button" class="wd-utility-menu__item" @click="emit('openRuntimeLogs'); closeUtilityMenu()">运行日志</button>
              <button v-if="isAdmin" type="button" class="wd-utility-menu__item" @click="emit('openAdminPanel'); closeUtilityMenu()">管理后台</button>
            </div>
          </details>
        </div>
      </div>

      <div v-if="currentTaskVisible" class="wd-task-panel">
        <div class="wd-task-panel__head">
          <div>
            <strong>{{ currentTaskTitle }}</strong>
            <p class="wd-task-panel__message">{{ currentTaskMessage }}</p>
          </div>
          <div class="wd-task-panel__chips">
            <span class="wd-meta-pill">{{ currentTaskStageLabel }}</span>
            <span class="wd-meta-pill">第 {{ taskUiModel.currentStep }}/{{ taskUiModel.totalSteps }} 步</span>
            <span v-if="currentTaskEta" class="wd-meta-pill">预计剩余 {{ currentTaskEta }}</span>
            <span v-else-if="currentTaskWarning" class="wd-meta-pill wd-meta-pill--warn">{{ currentTaskWarning }}</span>
          </div>
        </div>
        </div>

      <div class="wd-command-bar">
        <div class="wd-command-copy">
          <div class="wd-command-copy__item">
            <span class="wd-command-copy__label">选中章节</span>
            <strong>{{ focusText }}</strong>
          </div>
          <div class="wd-command-copy__item">
            <span class="wd-command-copy__label">下一步</span>
            <strong>{{ nextStepText }}</strong>
          </div>
          <div v-if="runtimeSummary" class="wd-command-copy__item">
            <span class="wd-command-copy__label">后台状态</span>
            <strong>{{ runtimeSummary }}</strong>
          </div>
          <div class="wd-command-copy__item">
            <span class="wd-command-copy__label">当前文风</span>
            <strong>{{ activeStyleText }}</strong>
          </div>
        </div>

        <div class="wd-command-actions">
          <div class="wd-command-group wd-command-group--nav">
            <button type="button" class="wd-action wd-action--nav" :disabled="!canPrevChapter" @click="$emit('prevChapter')">
              <ChevronLeft class="wd-btn-icon" aria-hidden="true" />
              上一章
            </button>
            <button type="button" class="wd-action wd-action--nav" :disabled="!canNextChapter" @click="$emit('nextChapter')">
              下一章
              <ChevronRight class="wd-btn-icon" aria-hidden="true" />
            </button>
          </div>

          <div class="wd-command-group wd-command-group--core">
            <button v-if="canOpenVersionsCurrent" type="button" class="wd-action wd-action--panel" @click="$emit('openVersionsCurrent')">
              <Files class="wd-btn-icon" aria-hidden="true" />
              查看候选版本
            </button>
            <button
              v-if="reviewActionVisible"
              type="button"
              class="wd-action wd-action--accent"
              @click="reviewActionMode === 'all' ? $emit('reviewAllVersionsCurrent') : $emit('evaluateCurrent')"
            >
              <ListChecks class="wd-btn-icon" aria-hidden="true" />
              {{ reviewActionLabel }}
            </button>
            <button v-if="canConfirmCurrent" type="button" class="wd-action wd-action--tonal wd-action--key" @click="$emit('confirmCurrent')">
              <Check class="wd-btn-icon" aria-hidden="true" />
              确认版本
            </button>
            <button v-if="canTerminateCurrent" type="button" class="wd-action wd-action--danger" @click="$emit('terminateCurrent')">
              <Square class="wd-btn-icon" aria-hidden="true" />
              终止处理
            </button>
            <button v-if="canGenerateCurrent" type="button" class="wd-action wd-action--primary wd-action--key" @click="$emit('generateCurrent')">
              <Play class="wd-btn-icon" aria-hidden="true" />
              {{ primaryActionLabel }}
            </button>
          </div>

          <div v-if="!hasDirectAction" class="wd-action-note">
            <span class="wd-action-note__title">{{ actionNoteTitle }}</span>
            <span>{{ actionNoteText }}</span>
          </div>
        </div>
      </div>
    </template>
  </header>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  ArrowLeft,
  Check,
  ChevronLeft,
  ChevronRight,
  Files,
  ListChecks,
  PanelLeftClose,
  PanelLeftOpen,
  PanelTopClose,
  Play,
  Square,
} from 'lucide-vue-next'
import type { GenerationRuntime, NovelProject, WorkspaceSummary } from '@/api/novel'
import { stripThinkTags } from '@/utils/safeMarkdown'
import { buildChapterTaskUiModel, normalizeRuntimeStage } from '@/utils/chapterGeneration'

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

const utilityMenuRef = ref<HTMLDetailsElement | null>(null)

const closeUtilityMenu = () => {
  if (utilityMenuRef.value) {
    utilityMenuRef.value.open = false
  }
}

const genreText = computed(() => props.project?.blueprint?.genre || '未设定题材')
const totalWordCount = computed(() => props.workspaceSummary?.total_word_count || 0)
const hasDirectAction = computed(() => props.canGenerateCurrent || props.canEvaluateCurrent || props.canConfirmCurrent || props.canTerminateCurrent)
const reviewActionMode = computed<'all' | 'single' | null>(() => props.canReviewAllVersionsCurrent ? 'all' : (props.canEvaluateCurrent ? 'single' : null))
const reviewActionVisible = computed(() => reviewActionMode.value !== null)
const reviewActionLabel = computed(() => reviewActionMode.value === 'all' ? 'AI 综合评审' : 'AI 复评正文')

const focusText = computed(() => {
  if (props.selectedChapterNumber) return `第 ${props.selectedChapterNumber} 章`
  if (props.workspaceSummary?.active_chapter) return `第 ${props.workspaceSummary.active_chapter} 章`
  if (props.workspaceSummary?.next_chapter_to_generate) return `建议先写第 ${props.workspaceSummary.next_chapter_to_generate} 章`
  return '先从目录选择章节'
})

const nextStepText = computed(() => {
  if (props.canConfirmCurrent) return '先确认当前版本'
  if (props.canTerminateCurrent) return '可先终止后台处理，再重新生成'
  if (props.canEvaluateCurrent) return '可以先看 AI 评估'
  if (props.isCurrentChapterBusy && props.selectedChapterNumber) return `第 ${props.selectedChapterNumber} 章正在后台处理中`
  if (props.workspaceSummary?.failed_chapters) return '先处理异常章节'
  if (props.workspaceSummary?.next_chapter_to_generate) return `继续第 ${props.workspaceSummary.next_chapter_to_generate} 章`
  return '可以继续扩写后续章节'
})

const runtimeSummary = computed(() => {
  if (!props.generationRuntime?.queued) return ''
  const mode = props.generationRuntime.preset || props.generationRuntime.generation_mode || 'stable'
  const message = stripThinkTags(props.generationRuntime.progress_message)
  const stage = props.generationRuntime.progress_stage
  if (message) return `${mode} 路 ${message}`
  if (stage) return `${mode} 路 ${stage}`
  return `${mode} 路 正在后台执行`
})

const effectiveTaskRuntime = computed(() => props.taskGenerationRuntime || props.generationRuntime || null)
const taskUiModel = computed(() => buildChapterTaskUiModel(effectiveTaskRuntime.value, {
  progressMessage: effectiveTaskRuntime.value?.progress_message,
  status: effectiveTaskRuntime.value?.progress_stage || effectiveTaskRuntime.value?.status,
  statusFetchFailureCount: props.statusFetchFailureCount,
}))

const currentTaskVisible = computed(() => Boolean(props.taskTrackable && props.taskChapterNumber))
const currentTaskStageLabel = computed(() => taskUiModel.value.stageLabel)
const currentTaskTitle = computed(() => props.taskChapterNumber ? `第 ${props.taskChapterNumber} 章任务` : '当前任务')
const currentTaskMessage = computed(() => {
  const cleaned = stripThinkTags(taskUiModel.value.displayMessage)
  if (cleaned) return cleaned
  if (taskUiModel.value.critiqueSummary) return taskUiModel.value.critiqueSummary
  if (taskUiModel.value.degradedSummary) return taskUiModel.value.degradedSummary
  return nextStepText.value
})
const currentTaskProgress = computed(() => taskUiModel.value.totalProgress)
const currentTaskStageProgress = computed(() => taskUiModel.value.stageProgress)
const currentTaskStageProgressLabel = computed(() => taskUiModel.value.stageProgressLabel)
const currentTaskTotalProgressLabel = computed(() => taskUiModel.value.totalProgressLabel)
const currentTaskEta = computed(() => taskUiModel.value.etaLabel)
const currentTaskWarning = computed(() => {
  if (taskUiModel.value.isLikelyStalled) {
    return `当前停留在第 ${taskUiModel.value.currentStep}/${taskUiModel.value.totalSteps} 步`
  }
  return ''
})

const activeStyleText = computed(() => {
  const profile = props.activeStyleProfile
  if (!profile) return '未启用外部文风'
  const sourceCount = Array.isArray(profile.source_ids) ? profile.source_ids.length : 0
  const sourceLabel = sourceCount > 0 ? `来源 ${sourceCount} 条` : '外部参考'
  return `${profile.name || '外部参考文风'} · ${sourceLabel}`
})

const primaryActionLabel = computed(() => props.generateCurrentLabel || (props.selectedChapterNumber ? `生成第 ${props.selectedChapterNumber} 章` : '开始创作'))

const actionNoteTitle = computed(() => {
  if (props.isCurrentChapterBusy) return '后台处理中'
  if (props.workspaceSummary?.failed_chapters) return '有异常章节'
  return '当前无直接动作'
})

const actionNoteText = computed(() => {
  if (props.isCurrentChapterBusy) return stripThinkTags(props.generationRuntime?.progress_message) || '先看正文或切换章节，不要反复点生成。'
  if (props.workspaceSummary?.failed_chapters) return '先在目录中定位异常章节，再重试生成或查看错误。'
  return '这一屏先阅读内容或切换章节，避免出现一排不能点的按钮。'
})

const collapsedTitle = computed(() => currentTaskVisible.value ? currentTaskTitle.value : (props.project?.title || '当前项目'))
const collapsedSubtitle = computed(() => {
  if (currentTaskVisible.value) return `${currentTaskStageLabel.value} · ${currentTaskMessage.value}`
  return `已完成 ${props.completedChapters}/${props.totalChapters || 0} 章`
})
</script>

<style scoped>
.wd-header-shell {
  display: grid;
  gap: 6px;
  padding: 6px 8px 4px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.16);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(246, 250, 255, 0.94));
  overflow: visible;
}

.wd-header-main,
.wd-header-lead,
.wd-header-actions,
.wd-command-bar,
.wd-command-copy,
.wd-command-actions,
.wd-task-panel__head,
.wd-task-panel__chips,


.wd-header-main,
.wd-command-bar,
.wd-task-panel__head,
.wd-header-collapsed-bar,

.wd-header-main,
.wd-header-actions,
.wd-utility-menu {
  position: relative;
  overflow: visible;
}

.wd-header-main {
  z-index: 40;
}

.wd-command-bar,
.wd-task-panel {
  position: relative;
  z-index: 1;
}

.wd-header-lead {
  min-width: 0;
  flex: 1;
  align-items: flex-start;
}

.wd-header-actions,
.wd-command-actions,
.wd-command-copy,
.wd-task-panel__chips {
  flex-wrap: wrap;
  align-items: center;
}

.wd-header-actions {
  justify-content: flex-end;
}

.wd-command-actions {
  align-items: flex-start;
}

.wd-command-group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.wd-command-group--core {
  flex: 1;
}

.wd-icon-btn,
.wd-utility-btn,
.wd-action {
  border: none;
  cursor: pointer;
}

.wd-icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.05);
  color: #0f172a;
}

.wd-btn-icon {
  width: 16px;
  height: 16px;
  flex: 0 0 auto;
}

.wd-brand-pill,
.wd-state-pill,
.wd-meta-pill,
.wd-shortcut-hint,
.wd-command-copy__label {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  font-size: 0.7rem;
  font-weight: 700;
}

.wd-brand-pill { background: rgba(79, 70, 229, 0.12); color: #4338ca; }
.wd-state-pill--warning { background: rgba(14, 165, 233, 0.14); color: #1d4ed8; }
.wd-state-pill--danger { background: rgba(239, 68, 68, 0.12); color: #b91c1c; }
.wd-meta-pill { background: rgba(15, 23, 42, 0.05); color: #475569; }
.wd-meta-pill--accent { background: rgba(37, 99, 235, 0.12); color: #1d4ed8; }
.wd-meta-pill--warn { background: rgba(14, 165, 233, 0.14); color: #1d4ed8; }

.wd-utility-btn,
.wd-action {
  border-radius: 999px;
  font-weight: 800;
}

.wd-utility-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 32px;
  padding: 0 12px;
  font-size: 0.76rem;
  background: #fff;
  color: #334155;
  border: 1px solid rgba(148, 163, 184, 0.25);
}

.wd-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  min-height: 40px;
  padding: 0 16px;
  font-size: 0.86rem;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.06);
}

.wd-utility-btn--accent { background: rgba(79, 70, 229, 0.1); color: #4338ca; }
.wd-shortcut-hint { margin-left: 6px; min-height: 18px; padding: 0 7px; background: rgba(15, 23, 42, 0.08); color: #475569; }

.wd-utility-menu {
  position: relative;
  z-index: 50;
}

.wd-utility-menu__summary {
  display: inline-flex;
  align-items: center;
  list-style: none;
}

.wd-utility-menu__summary::-webkit-details-marker {
  display: none;
}

.wd-utility-menu[open] {
  z-index: 90;
}

.wd-utility-menu[open] .wd-utility-menu__summary {
  background: rgba(79, 70, 229, 0.1);
  color: #4338ca;
}

.wd-utility-menu__panel {
  position: absolute;
  right: 0;
  top: calc(100% + 8px);
  min-width: 180px;
  display: grid;
  gap: 6px;
  padding: 10px;
  border-radius: 8px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(255, 255, 255, 0.98);
  box-shadow: 0 18px 38px rgba(15, 23, 42, 0.12);
  backdrop-filter: blur(12px);
  pointer-events: auto;
  z-index: 120;
}

.wd-utility-menu__item {
  min-height: 36px;
  padding: 0 12px;
  border: 0;
  border-radius: 12px;
  background: #f8fafc;
  color: #334155;
  text-align: left;
  font-size: 0.78rem;
  font-weight: 750;
  cursor: pointer;
}

.wd-utility-menu__item:hover {
  background: #eef2ff;
  color: #4338ca;
}

.wd-task-panel,


.wd-task-panel__head { align-items: flex-start; gap: 12px; }
.wd-task-panel__head strong,

.wd-task-panel__message,
.wd-header-collapsed-bar__summary span { margin: 3px 0 0; color: #475569; font-size: 0.75rem; line-height: 1.4; }










.wd-command-copy__item { display: grid; gap: 3px; min-width: 120px; }
.wd-command-copy__label { width: fit-content; }
.wd-action--nav,
.wd-action--panel { background: #fff; color: #334155; border: 1px solid rgba(148, 163, 184, 0.24); }
.wd-action--accent { background: rgba(79, 70, 229, 0.12); color: #4338ca; border: 1px solid rgba(99, 102, 241, 0.18); }
.wd-action--tonal { background: rgba(37, 99, 235, 0.14); color: #1d4ed8; border: 1px solid rgba(59, 130, 246, 0.14); }
.wd-action--danger { background: rgba(239, 68, 68, 0.12); color: #b91c1c; border: 1px solid rgba(239, 68, 68, 0.14); }
.wd-action--primary { background: #111827; color: #fff; }
.wd-action--key {
  min-height: 44px;
  padding: 0 18px;
  font-size: 0.92rem;
  box-shadow: 0 16px 32px rgba(59, 130, 246, 0.14);
}
.wd-action-note { display: inline-grid; gap: 2px; color: #475569; font-size: 0.72rem; padding: 8px 2px; }
.wd-action-note__title { color: #0f172a; font-weight: 700; }

@media (max-width: 960px) {
  .wd-header-main,
  .wd-command-bar,
  .wd-task-panel__head,
  
  .wd-header-collapsed-bar__summary { min-width: 0; }
  .wd-command-group--core { flex: none; }
  .wd-header-actions { justify-content: flex-start; }
  .wd-utility-menu { width: 100%; }
  .wd-utility-menu__summary { width: 100%; justify-content: center; }
  .wd-utility-menu__panel { left: 0; right: 0; min-width: 0; }
}
</style>






