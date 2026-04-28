<template>
  <header class="wd-header-shell">
    <template v-if="props.headerCollapsed">
      <div class="wd-header-collapsed-bar">
        <div class="wd-header-collapsed-bar__summary">
          <strong>{{ collapsedTitle }}</strong>
          <span>{{ collapsedSubtitle }}</span>
        </div>
        <div class="wd-header-collapsed-bar__progress">
          <div class="progress-row">
            <span>{{ currentTaskStageProgressLabel }}</span>
            <strong>{{ currentTaskStageProgress }}%</strong>
          </div>
          <div class="progress-track">
            <div class="progress-bar progress-bar--phase" :style="{ width: `${currentTaskStageProgress}%` }"></div>
          </div>
          <div class="progress-row progress-row--secondary">
            <span>{{ currentTaskTotalProgressLabel }}</span>
            <strong>{{ currentTaskProgress }}%</strong>
          </div>
          <div class="progress-track">
            <div class="progress-bar" :style="{ width: `${currentTaskProgress}%` }"></div>
          </div>
        </div>
        <button type="button" class="wd-utility-btn wd-utility-btn--accent" @click="$emit('toggleHeaderCollapse')">展开顶部</button>
      </div>
    </template>

    <template v-else>
      <div class="wd-header-main">
        <div class="wd-header-lead">
          <button type="button" class="wd-icon-btn" title="返回项目列表" @click="$emit('goBack')">
            <svg class="h-5 w-5" fill="currentColor" viewBox="0 0 20 20">
              <path
                fill-rule="evenodd"
                d="M9.707 16.707a1 1 0 01-1.414 0l-6-6a1 1 0 010-1.414l6-6a1 1 0 111.414 1.414L4.414 9H17a1 1 0 110 2H4.414l5.293 5.293a1 1 0 010 1.414z"
                clip-rule="evenodd"
              />
            </svg>
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
          <button type="button" class="wd-utility-btn wd-utility-btn--accent" @click="$emit('toggleHeaderCollapse')">收起顶部</button>
          <button type="button" class="wd-utility-btn" @click="$emit('viewProjectDetail')">项目详情</button>
          <button v-if="isAdmin" type="button" class="wd-utility-btn" @click="$emit('openRuntimeLogs')">运行日志</button>
          <button v-if="isAdmin" type="button" class="wd-utility-btn" @click="$emit('openAdminPanel')">管理后台</button>
          <button type="button" class="wd-utility-btn" @click="$emit('openSkills')">写作技能</button>
          <button type="button" class="wd-utility-btn" @click="$emit('toggleShortcutHelp')">
            快捷键
            <span class="wd-shortcut-hint">?</span>
          </button>
          <button
            type="button"
            class="wd-utility-btn wd-utility-btn--accent"
            :title="sidebarOpen ? '收起目录' : '展开目录'"
            @click="$emit('toggleSidebar')"
          >
            {{ sidebarOpen ? '收起目录' : '展开目录' }}
          </button>
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
        <div class="wd-task-panel__progress-grid">
          <div>
            <div class="progress-row">
              <span>{{ currentTaskStageProgressLabel }}</span>
              <strong>{{ currentTaskStageProgress }}%</strong>
            </div>
            <div class="progress-track" aria-label="current-stage-progress">
              <div class="progress-bar progress-bar--phase" :style="{ width: `${currentTaskStageProgress}%` }"></div>
            </div>
          </div>
          <div>
            <div class="progress-row progress-row--secondary">
              <span>{{ currentTaskTotalProgressLabel }}</span>
              <strong>{{ currentTaskProgress }}%</strong>
            </div>
            <div class="progress-track" aria-label="current-total-progress">
              <div class="progress-bar" :style="{ width: `${currentTaskProgress}%` }"></div>
            </div>
          </div>
        </div>
      </div>

      <div class="wd-command-bar">
        <div class="wd-command-copy">
          <div class="wd-command-copy__item">
            <span class="wd-command-copy__label">当前焦点</span>
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
          <button type="button" class="wd-action wd-action--nav" :disabled="!canPrevChapter" @click="$emit('prevChapter')">上一章</button>
          <button type="button" class="wd-action wd-action--nav" :disabled="!canNextChapter" @click="$emit('nextChapter')">下一章</button>
          <button v-if="canOpenVersionsCurrent" type="button" class="wd-action wd-action--ghost" @click="$emit('openVersionsCurrent')">候选版本区</button>
          <button
            v-if="reviewActionVisible"
            type="button"
            class="wd-action wd-action--ghost"
            @click="reviewActionMode === 'all' ? $emit('reviewAllVersionsCurrent') : $emit('evaluateCurrent')"
          >
            {{ reviewActionLabel }}
          </button>
          <button v-if="canConfirmCurrent" type="button" class="wd-action wd-action--tonal" @click="$emit('confirmCurrent')">确认版本</button>
          <button v-if="canTerminateCurrent" type="button" class="wd-action wd-action--danger" @click="$emit('terminateCurrent')">终止处理</button>
          <button v-if="canGenerateCurrent && !canConfirmCurrent" type="button" class="wd-action wd-action--primary" @click="$emit('generateCurrent')">
            {{ primaryActionLabel }}
          </button>

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
import { computed } from 'vue'
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

defineEmits([
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

const genreText = computed(() => props.project?.blueprint?.genre || '未设定题材')
const totalWordCount = computed(() => props.workspaceSummary?.total_word_count || 0)
const hasDirectAction = computed(() => props.canGenerateCurrent || props.canEvaluateCurrent || props.canConfirmCurrent || props.canTerminateCurrent)
const reviewActionMode = computed<'all' | 'single' | null>(() => props.canReviewAllVersionsCurrent ? 'all' : (props.canEvaluateCurrent ? 'single' : null))
const reviewActionVisible = computed(() => reviewActionMode.value !== null)
const reviewActionLabel = computed(() => reviewActionMode.value === 'all' ? 'AI评审候选版本' : 'AI复评当前正文')

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

const primaryActionLabel = computed(() => props.selectedChapterNumber ? `生成第 ${props.selectedChapterNumber} 章` : '开始创作')

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
}

.wd-header-main,
.wd-header-lead,
.wd-header-actions,
.wd-command-bar,
.wd-command-copy,
.wd-command-actions,
.wd-task-panel__head,
.wd-task-panel__chips,
.progress-row,
.wd-header-collapsed-bar {
  display: flex;
  gap: 8px;
}

.wd-header-main,
.wd-command-bar,
.wd-task-panel__head,
.wd-header-collapsed-bar,
.progress-row {
  justify-content: space-between;
  align-items: center;
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
.wd-state-pill--warning { background: rgba(245, 158, 11, 0.14); color: #92400e; }
.wd-state-pill--danger { background: rgba(239, 68, 68, 0.12); color: #b91c1c; }
.wd-meta-pill { background: rgba(15, 23, 42, 0.05); color: #475569; }
.wd-meta-pill--accent { background: rgba(37, 99, 235, 0.12); color: #1d4ed8; }
.wd-meta-pill--warn { background: rgba(245, 158, 11, 0.14); color: #b45309; }

.wd-utility-btn,
.wd-action {
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 0.74rem;
  font-weight: 700;
}

.wd-utility-btn { background: #fff; color: #334155; border: 1px solid rgba(148, 163, 184, 0.25); }
.wd-utility-btn--accent { background: rgba(79, 70, 229, 0.1); color: #4338ca; }
.wd-shortcut-hint { margin-left: 6px; min-height: 18px; padding: 0 7px; background: rgba(15, 23, 42, 0.08); color: #475569; }

.wd-task-panel,
.wd-header-collapsed-bar {
  border: 1px solid rgba(99, 102, 241, 0.15);
  border-radius: 16px;
  background: linear-gradient(180deg, rgba(245, 247, 255, 0.98), rgba(238, 244, 255, 0.95));
  padding: 8px 10px;
}

.wd-task-panel__head { align-items: flex-start; gap: 12px; }
.wd-task-panel__head strong,
.wd-header-collapsed-bar__summary strong { display: block; color: #0f172a; font-size: 0.84rem; }
.wd-task-panel__message,
.wd-header-collapsed-bar__summary span { margin: 3px 0 0; color: #475569; font-size: 0.75rem; line-height: 1.4; }
.wd-task-panel__progress-grid,
.wd-header-collapsed-bar__progress { display: grid; gap: 8px; flex: 1; min-width: 0; }
.wd-header-collapsed-bar { gap: 16px; align-items: center; }
.wd-header-collapsed-bar__summary { min-width: 220px; }

.progress-row { color: #334155; font-size: 0.72rem; font-weight: 700; }
.progress-row--secondary { margin-top: 2px; }
.progress-track { width: 100%; height: 6px; overflow: hidden; border-radius: 999px; background: rgba(148, 163, 184, 0.2); }
.progress-bar { height: 100%; border-radius: 999px; background: linear-gradient(90deg, #3b82f6, #6366f1, #10b981); transition: width 0.25s ease; }
.progress-bar--phase { background: linear-gradient(90deg, #8b5cf6, #3b82f6); }

.wd-command-copy__item { display: grid; gap: 3px; min-width: 120px; }
.wd-command-copy__label { width: fit-content; }
.wd-action--nav, .wd-action--ghost { background: #fff; color: #334155; border: 1px solid rgba(148, 163, 184, 0.24); }
.wd-action--tonal { background: rgba(59, 130, 246, 0.12); color: #1d4ed8; }
.wd-action--danger { background: rgba(239, 68, 68, 0.12); color: #b91c1c; }
.wd-action--primary { background: #111827; color: #fff; }
.wd-action-note { display: inline-grid; gap: 2px; color: #475569; font-size: 0.72rem; }
.wd-action-note__title { color: #0f172a; font-weight: 700; }

@media (max-width: 960px) {
  .wd-header-main,
  .wd-command-bar,
  .wd-task-panel__head,
  .wd-header-collapsed-bar { align-items: stretch; flex-direction: column; }
  .wd-header-collapsed-bar__summary { min-width: 0; }
}
</style>





