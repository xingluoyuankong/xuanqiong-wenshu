<template>
  <div class="cg-shell">
    <section class="cg-hero">
      <div class="cg-hero__main">
        <p class="cg-kicker">章节处理中心</p>
        <h3 class="cg-title">{{ title }}</h3>
        <p class="cg-summary">{{ stageDescription }}</p>

        <div class="cg-stage-row">
          <span :class="['cg-stage-pill', `cg-stage-pill--${stageTone}`]">{{ stageLabel }}</span>
          <span v-if="elapsedLabel" class="cg-stage-note">已等待 {{ elapsedLabel }}</span>
          <span v-if="updatedLabel" class="cg-stage-note">最近更新 {{ updatedLabel }}</span>
          <span v-if="estimatedRemainingLabel" class="cg-stage-note cg-stage-note--accent">
            预计剩余 {{ estimatedRemainingLabel }}
          </span>
        </div>

        <div class="cg-progress" aria-label="generation-progress">
          <div class="cg-progress__track">
            <div :class="['cg-progress__bar', `cg-progress__bar--${stageTone}`]" :style="{ width: `${stageProgress}%` }" />
            <span class="cg-progress__runner" :style="{ left: `${stageProgress}%` }">{{ runnerEmoji }}</span>
          </div>
          <div class="cg-progress__meta">
            <span>{{ progressPercentLabel }}</span>
            <span>{{ progressHint }}</span>
          </div>
        </div>
      </div>

      <div class="cg-badge">
        <div :class="['cg-badge__icon', `cg-badge__icon--${stageTone}`]">
          <Loader2 v-if="stageTone === 'active'" class="h-6 w-6 animate-spin" aria-hidden="true" />
          <AlertCircle v-else-if="stageTone === 'danger'" class="h-6 w-6" aria-hidden="true" />
          <CheckCircle2 v-else class="h-6 w-6" aria-hidden="true" />
        </div>

        <div>
          <p class="cg-badge__title">{{ stageBadgeTitle }}</p>
          <p class="cg-badge__desc">{{ stageBadgeDesc }}</p>
        </div>
      </div>
    </section>

    <section class="cg-grid">
      <article class="cg-card">
        <p class="cg-card__title">当前状态</p>
        <div class="cg-message">
          <p>{{ progressMessageText }}</p>
          <p v-if="statusFetchWarning" class="cg-stuck">{{ statusFetchWarning }}</p>
          <p v-if="lastErrorSummary" class="cg-error">{{ lastErrorSummary }}</p>
          <div v-if="diagnosticsSummary.length" class="cg-diagnostics">
            <p class="cg-diagnostics__title">诊断信息</p>
            <ul class="cg-diagnostics__list">
              <li v-for="item in diagnosticsSummary" :key="item.label"><strong>{{ item.label }}：</strong>{{ item.value }}</li>
            </ul>
          </div>
          <p v-if="stalledWarning" class="cg-stuck">{{ stalledWarning }}</p>
        </div>

        <div class="cg-actions">
          <button type="button" class="cg-action-btn" @click="$emit('fetchStatusNow')">
            <RefreshCw class="cg-action-icon" aria-hidden="true" />
            立即刷新
          </button>
          <button
            v-if="canTerminate"
            type="button"
            class="cg-action-btn cg-action-btn--danger"
            :disabled="isTerminating"
            @click="$emit('terminateChapter', chapterNumber)"
          >
            <Square class="cg-action-icon" aria-hidden="true" />
            {{ isTerminating ? '终止中...' : '终止处理' }}
          </button>
          <button
            v-if="canRetry"
            type="button"
            class="cg-action-btn cg-action-btn--strong"
            @click="$emit('regenerateChapter', chapterNumber)"
          >
            <RotateCcw class="cg-action-icon" aria-hidden="true" />
            重新生成
          </button>
        </div>
      </article>

      <article class="cg-card">
        <p class="cg-card__title">任务摘要</p>
        <div class="cg-metadata">
          <span v-if="runtime.requested_preset">请求预设：{{ runtime.requested_preset }}</span>
          <span v-if="runtime.actual_preset">实际预设：{{ runtime.actual_preset }}</span>
          <span v-if="runtime.generation_mode">模式：{{ runtime.generation_mode }}</span>
          <span v-if="runtime.version_count">候选版本：{{ runtime.version_count }}</span>
          <span v-if="runtime.target_word_count">目标字数：{{ runtime.target_word_count }}</span>
          <span v-if="runtime.min_word_count">最低字数：{{ runtime.min_word_count }}</span>
          <span v-if="runtime.actual_word_count">当前字数：{{ runtime.actual_word_count }}</span>
          <span v-if="runtime.diagnosis_stage_label">诊断阶段：{{ runtime.diagnosis_stage_label }}</span>
          <span v-if="runtime.diagnosis_dimensions?.length">诊断维度：{{ runtime.diagnosis_dimensions.join('、') }}</span>
          <span v-if="runtime.optimization_stage_label">优化阶段：{{ runtime.optimization_stage_label }}</span>
          <span v-if="runtime.optimization_dimensions?.length">当前维度：{{ runtime.optimization_dimensions.join('、') }}</span>
          <span v-if="taskUiModel.critiqueSummary">批判摘要：{{ taskUiModel.critiqueSummary }}</span>
          <span v-if="runtimeQueued">状态：已排队执行</span>
        </div>

        <div v-if="runtime.preset_downgraded && runtime.downgraded_capabilities?.length" class="cg-preset-downgrade">
          <p class="cg-preset-downgrade__title">质量降级提示</p>
          <p class="cg-preset-downgrade__desc">
            生成遇到不稳定，已从「{{ runtime.requested_preset || '未知' }}」降级到「{{ runtime.actual_preset || 'stable' }}」。
            以下能力被临时关闭以保障基础生成：
          </p>
          <div class="cg-preset-downgrade__tags">
            <span v-for="cap in runtime.downgraded_capabilities" :key="cap" class="cg-preset-downgrade__tag">{{ cap }}</span>
          </div>
        </div>

        <div v-if="runtime.consistency_violation_count" class="cg-consistency-warning">
          <p class="cg-consistency-warning__title">一致性校验警告</p>
          <p class="cg-consistency-warning__desc">
            一致性校验发现 {{ runtime.consistency_violation_count }} 项未解决问题，可能影响剧情连贯性。
          </p>
          <ul v-if="runtime.consistency_violation_summary?.length" class="cg-consistency-warning__list">
            <li v-for="(item, idx) in runtime.consistency_violation_summary" :key="idx">
              <span :class="['cg-consistency-warning__badge', `cg-consistency-warning__badge--${item.severity}`]">{{ item.severity }}</span>
              <span v-if="item.category" class="cg-consistency-warning__category">{{ item.category }}</span>
              <span class="cg-consistency-warning__text">{{ item.description }}</span>
            </li>
          </ul>
        </div>

        <div v-if="runtime.token_budget_warning" :class="['cg-budget-warning', `cg-budget-warning--${runtime.token_budget_warning.level}`]">
          <p class="cg-budget-warning__title">Token 预算提示</p>
          <p class="cg-budget-warning__desc">{{ runtime.token_budget_warning.message }}</p>
        </div>

        <div v-if="taskUiModel.critiqueHighlights.length || taskUiModel.degradedSummary || optimizationLogs.length" class="cg-critique-panel">
          <p class="cg-critique-panel__title">批判优化进展</p>
          <ul v-if="taskUiModel.critiqueHighlights.length" class="cg-critique-panel__list">
            <li v-for="(item, index) in taskUiModel.critiqueHighlights" :key="`${item}-${index}`">{{ item }}</li>
          </ul>
          <ul v-if="optimizationLogs.length" class="cg-critique-panel__list">
            <li v-for="(item, index) in optimizationLogs" :key="`${item.stage}-${index}`">
              {{ item.label }}：{{ item.summary }}
            </li>
          </ul>
          <p v-if="taskUiModel.degradedSummary" class="cg-critique-panel__degraded">{{ taskUiModel.degradedSummary }}</p>
        </div>

        <ul class="cg-list">
          <li>你现在可以切去别的章节，不需要在这里空等。</li>
          <li>一旦进入可确认阶段，页面会直接切到版本确认区。</li>
          <li>如果长时间卡住，可直接“终止处理”，不再只能刷新。</li>
        </ul>
      </article>

      <article v-if="latestContentPreview" class="cg-card cg-card--preview">
        <p class="cg-card__title">最新草稿片段</p>
        <p class="cg-card__subtitle">这里直接显示后台正在产出的正文内容，不再只看程序日志。</p>
        <pre class="cg-live-preview">{{ latestContentPreview }}</pre>
      </article>

      <article v-if="allRuntimeEvents.length" class="cg-card cg-card--logs">
        <div class="cg-card__head">
          <div>
            <p class="cg-card__title">生成状态日志</p>
            <p class="cg-card__subtitle">显示正文片段、评审、修复和连续性检查；原始程序字段收在开发者详情里。</p>
          </div>
          <button
            v-if="hiddenRuntimeEventCount > 0 || showAllRuntimeEvents"
            type="button"
            class="cg-log-toggle"
            @click="showAllRuntimeEvents = !showAllRuntimeEvents"
          >
            {{ showAllRuntimeEvents ? '收起日志' : `展开全部（+${hiddenRuntimeEventCount}）` }}
          </button>
        </div>
        <div class="cg-log-tabs" role="tablist" aria-label="generation-log-tabs">
          <button
            v-for="tab in runtimeLogTabs"
            :key="tab.key"
            type="button"
            :class="['cg-log-tab', { 'is-active': selectedRuntimeLogTab === tab.key }]"
            @click="selectedRuntimeLogTab = tab.key"
          >
            <span>{{ tab.icon }}</span>
            {{ tab.label }}
          </button>
        </div>
        <ul class="cg-log-list">
          <li v-for="(event, index) in runtimeEvents" :key="`${event.at || 'event'}-${index}`" class="cg-log-item">
            <div class="cg-log-item__head">
              <span class="cg-log-item__kind">{{ formatEventKindIcon(event) }}</span>
              <span class="cg-log-item__time">{{ formatEventTime(event.at) }}</span>
              <span :class="['cg-log-item__level', `cg-log-item__level--${event.level || 'info'}`]">{{ formatEventLevel(event.level) }}</span>
              <span v-if="event.kind" class="cg-log-item__stage">{{ formatEventKindLabel(event.kind) }}</span>
              <span v-if="event.stage" class="cg-log-item__stage">{{ event.stage }}</span>
            </div>
            <p v-if="eventTitle(event)" class="cg-log-item__title">{{ eventTitle(event) }}</p>
            <p class="cg-log-item__message">
              {{ eventSummary(event) }}
              <span v-if="eventDurationLabel(event)" class="cg-log-item__duration">（{{ eventDurationLabel(event) }}）</span>
            </p>
            <div v-if="eventContinuityNotice(event)" class="cg-log-item__notice">
              {{ eventContinuityNotice(event) }}
            </div>
            <pre v-if="event.content_preview" class="cg-log-item__preview">{{ event.content_preview }}</pre>
            <div v-if="eventPatchSuggestions(event).length" class="cg-log-item__patches">
              <p class="cg-log-item__patch-title">局部补丁建议</p>
              <ul>
                <li v-for="(patch, patchIndex) in eventPatchSuggestions(event)" :key="`${patch.problem}-${patchIndex}`">
                  <span v-if="patch.scope" class="cg-log-item__patch-scope">{{ patch.scope }}</span>
                  <strong>{{ patch.problem }}</strong>
                  <span v-if="patch.suggestion">{{ patch.suggestion }}</span>
                  <small v-if="patch.requirement">执行要求：{{ patch.requirement }}</small>
                </li>
              </ul>
            </div>
            <details v-if="event.metrics && Object.keys(event.metrics).length" class="cg-log-item__meta">
              <summary>生成指标</summary>
              <pre>{{ formatEventMetadata(event.metrics) }}</pre>
            </details>
            <details v-if="event.artifact_refs && formatEventMetadata(event.artifact_refs)" class="cg-log-item__meta">
              <summary>产物引用</summary>
              <pre>{{ formatEventMetadata(event.artifact_refs) }}</pre>
            </details>
            <details v-if="event.metadata && Object.keys(event.metadata).length" class="cg-log-item__meta">
              <summary>开发者详情</summary>
              <pre>{{ formatEventMetadata(event.metadata) }}</pre>
            </details>
          </li>
        </ul>
        <p v-if="!runtimeEvents.length" class="cg-log-empty">这个分组暂时没有日志，切到“简略日志”可以看全部阶段。</p>
      </article>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { AlertCircle, CheckCircle2, Loader2, RefreshCw, RotateCcw, Square } from 'lucide-vue-next'
import { buildChapterTaskUiModel, canCancelGeneration, normalizeRuntimeStage } from '@/utils/chapterGeneration'
import { stripThinkTags } from '@/utils/safeMarkdown'

const props = defineProps<{
  chapterNumber?: number
  chapterTitle?: string
  generationRuntime?: Record<string, any>
  status?: string
  progressStage?: string
  progressMessage?: string | null
  startedAt?: string | null
  updatedAt?: string | null
  allowedActions?: string[]
  lastErrorSummary?: string | null
  statusFetchFailureCount?: number
  selectedChapterOutline?: { title?: string }
  isTerminating?: boolean
}>()

defineEmits<{
  (e: 'fetchStatusNow'): void
  (e: 'regenerateChapter', chapterNumber?: number): void
  (e: 'terminateChapter', chapterNumber?: number): void
}>()

const now = ref(Date.now())
let timer: number | null = null

const runtime = computed(() => props.generationRuntime || {})
const runtimeQueued = computed(() => Boolean(runtime.value.queued))
const showAllRuntimeEvents = ref(false)
type RuntimeLogTabKey = 'summary' | 'progress' | 'content' | 'review' | 'ledger' | 'diagnostics'
const selectedRuntimeLogTab = ref<RuntimeLogTabKey>('summary')
const runtimeLogTabs: Array<{ key: RuntimeLogTabKey; label: string; icon: string }> = [
  { key: 'summary', label: '简略日志', icon: '✨' },
  { key: 'progress', label: '生成进展', icon: '⏳' },
  { key: 'content', label: '草稿预览', icon: '✍' },
  { key: 'review', label: '评审/修复', icon: '✓' },
  { key: 'ledger', label: '账本闭环', icon: '☘' },
  { key: 'diagnostics', label: '诊断详情', icon: '⚙' },
]
const allRuntimeEvents = computed(() => {
  const events = Array.isArray(runtime.value.events) ? runtime.value.events : []
  return [...events].reverse()
})
const latestContentPreview = computed(() => {
  const event = allRuntimeEvents.value.find((item) => typeof item?.content_preview === 'string' && item.content_preview.trim())
  return event ? stripThinkTags(String(event.content_preview)).trim() : ''
})
const filteredRuntimeEvents = computed(() => {
  const tab = selectedRuntimeLogTab.value
  if (tab === 'summary') return allRuntimeEvents.value
  return allRuntimeEvents.value.filter((event) => {
    const kind = String(event?.kind || '').toLowerCase()
    const stageKey = String(event?.stage || '').toLowerCase()
    if (tab === 'progress') return !kind || kind === 'status' || ['prepare_context', 'cast_plan', 'foreshadowing_plan', 'longform_context', 'generate_mission', 'generate_variants', 'persist_versions'].includes(stageKey)
    if (tab === 'content') return kind === 'content' || kind === 'save' || Boolean(event?.content_preview)
    if (tab === 'review') return ['review', 'continuity', 'error'].includes(kind) || stageKey.includes('review') || stageKey.includes('optimize') || stageKey.includes('diagnose') || stageKey.includes('continuity')
    if (tab === 'ledger') return kind === 'ledger' || stageKey.includes('ledger') || ['finalize', 'finalized'].includes(stageKey)
    if (tab === 'diagnostics') return Boolean(event?.metadata || event?.metrics || event?.artifact_refs)
    return true
  })
})
const runtimeEventLimit = computed(() => (showAllRuntimeEvents.value ? filteredRuntimeEvents.value.length : 8))
const runtimeEvents = computed(() => filteredRuntimeEvents.value.slice(0, runtimeEventLimit.value))
const hiddenRuntimeEventCount = computed(() => Math.max(0, filteredRuntimeEvents.value.length - runtimeEvents.value.length))

const title = computed(() => {
  if (props.chapterTitle) return props.chapterTitle
  if (props.selectedChapterOutline?.title) return props.selectedChapterOutline.title
  if (props.chapterNumber) return `第 ${props.chapterNumber} 章`
  return '章节处理任务'
})

const rawStage = computed(() => String(props.progressStage || runtime.value.progress_stage || runtime.value.status || props.status || '').toLowerCase())
const stage = computed(() =>
  normalizeRuntimeStage(rawStage.value)
)

const stageDescriptionMap: Record<string, string> = {
  queued: '任务已经进入后台队列，正在等待分配执行槽位。',
  prepare_context: '系统正在整理蓝图、历史章节、角色约束和上下文材料。',
  audit_context: '系统正在审计长期记忆、章节快照、时间线和知识图谱。',
  cast_plan: '系统正在装配角色规模、登场层级、势力归属和动态角色规则。',
  foreshadowing_plan: '系统正在规划本章伏笔回收、强化、禁忘和可新增线索。',
  longform_context: '系统正在把长篇上下文压成写前约束包。',
  generate_mission: '系统正在构建本章写作任务、约束和生成计划。',
  generate_variants: '系统正在正式生成正文草稿，这通常是最耗时的阶段。',
  review: '正文草稿已产出，系统正在做首轮评审、筛选和增强准备。',
  diagnose_once: '系统正在启动单次诊断流程，并准备按阶段聚合问题。',
  diagnose_previous_chapter: '系统正在整理前一章依据包，提取摘要、结尾锚点与关键片段。',
  diagnose_context_bundle: '系统正在整理关联上下文，汇总章节目标、长期记忆与剧情线索。',
  diagnose_structural: '系统正在做结构诊断，聚合检查逻辑、承接与视角问题。',
  diagnose_character: '系统正在做人物诊断，聚合检查角色、关系、情绪与对话问题。',
  diagnose_delivery: '系统正在做表达诊断，聚合检查节奏、场景、悬念与文风问题。',
  optimize_content: '系统正在按诊断结果执行分阶段优化。',
  optimize_structural: '正在处理结构层问题：逻辑、承接、视角。',
  optimize_character: '正在处理人物层问题：角色、关系、情绪、对话。',
  optimize_delivery: '正在处理表现层问题：节奏、场景、悬念、文风。',
  consistency: '系统正在校验剧情设定、前后文和伏笔一致性。',
  continuity_gate: '系统正在检查跨章节、伏笔、角色状态和知识边界。',
  optimizer: '系统正在做定向优化，强化最重要的问题维度。',
  enrichment: '系统正在补字数、强化细节和做最终质量增强。',
  persist_versions: '系统正在写入候选版本并整理确认结果。',
  finalize: '系统正在确认定稿，写入章节摘要和快照。',
  ledger_memory: '系统正在把正文更新进角色状态、时间线和因果账本。',
  ledger_foreshadowing: '系统正在判断本章伏笔回收、强化和新埋设情况。',
  ledger_graph: '系统正在同步线索和知识图谱。',
  finalized: '定稿闭环已完成，正文和故事账本都已处理。',
  generating: '系统正在写正文草稿，完成后会自动进入评估或确认阶段。',
  evaluating: '正文已生成，系统正在评估候选版本可用性。',
  selecting: '候选版本已就绪，即将切换到版本确认界面。',
  waiting_for_confirm: '候选版本已准备好，可直接确认并继续下一章。',
  ready: '这一章已经处理完成，可以继续阅读、确认或推进下一章。',
  failed: '这一章处理失败，请查看错误摘要后重试。',
  evaluation_failed: '评审阶段出了问题，但已有候选版本仍可查看、确认或重新评审。'
}

const statusFetchFailureCount = computed(() => {
  const parsed = Number(props.statusFetchFailureCount || 0)
  return Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : 0
})
const taskUiModel = computed(() => buildChapterTaskUiModel(runtime.value, {
  progressMessage: props.progressMessage || runtime.value.progress_message,
  status: props.progressStage || runtime.value.progress_stage || runtime.value.status || props.status,
  nowMs: now.value,
  statusFetchFailureCount: statusFetchFailureCount.value,
}))
const stageLabel = computed(() => taskUiModel.value.stageLabel)
const stageDescription = computed(() => stageDescriptionMap[rawStage.value] || stageDescriptionMap[stage.value] || '系统正在处理这一章。')
const progressMessageText = computed(() => {
  const cleaned = stripThinkTags(taskUiModel.value.displayMessage || '')
  return cleaned || stageDescription.value
})
const estimatedRemainingLabel = computed(() => taskUiModel.value.etaLabel)
const isLikelyStalled = computed(() => taskUiModel.value.isLikelyStalled)
const statusFetchWarning = computed(() => {
  if (statusFetchFailureCount.value <= 0) return ''
  if (statusFetchFailureCount.value === 1) return '刚刚有一次状态同步失败，页面会继续自动重试。'
  return `状态同步已连续失败 ${statusFetchFailureCount.value} 次，建议优先终止处理后再重试。`
})
const stalledWarning = computed(() => {
  if (!isLikelyStalled.value) return ''
  return '状态长时间无更新，任务可能卡住。建议立即“终止处理”，然后查看根因诊断再重试。'
})

const stageTone = computed(() => {
  if (stage.value === 'failed' || stage.value === 'evaluation_failed' || isLikelyStalled.value) return 'danger'
  if (['ready', 'successful', 'waiting_for_confirm', 'selecting'].includes(stage.value)) return 'success'
  return 'active'
})

const progressHintMap: Record<string, string> = {
  queued: '后台已接单，正在准备上下文和模型。',
  generating: '正文生成中，通常这是耗时最长的一步。',
  evaluating: '正文已产出，正在做版本评估和筛选。',
  selecting: '候选版本已就绪，即将进入确认阶段。',
  waiting_for_confirm: '现在可以直接确认版本继续推进。',
  ready: '这一章已经可以阅读或继续创作。',
  successful: '这一章已经可以阅读或继续创作。',
  failed: '当前任务已终止，请查看错误摘要后重试。',
  evaluation_failed: '评审阶段失败，但候选版本仍应保留，可继续查看或确认。'
}

const stageBadgeTitle = computed(() => {
  if (stageTone.value === 'danger') return '需要处理'
  if (stageTone.value === 'success') return '可继续操作'
  return '后台处理中'
})

const stageBadgeDesc = computed(() => {
  if (stageTone.value === 'danger') return '下面会直接显示主错误，避免盲目重试。'
  if (stageTone.value === 'success') return '完成后会自动回到可确认或可阅读状态。'
  return '状态会持续刷新，不需要反复重进页面。'
})

const lastErrorSummary = computed(() => props.lastErrorSummary || runtime.value.last_error_summary || runtime.value?.diagnostics?.message || '')
const diagnosticsSummary = computed(() => {
  const diagnostics = runtime.value?.diagnostics
  if (!diagnostics || typeof diagnostics !== 'object') return []
  const entries = [
    diagnostics.requestId ? { label: '请求ID', value: String(diagnostics.requestId) } : null,
    diagnostics.rootCause ? { label: '根因', value: String(diagnostics.rootCause) } : null,
    diagnostics.code ? { label: '错误码', value: String(diagnostics.code) } : null,
    typeof diagnostics.status === 'number' ? { label: '状态码', value: String(diagnostics.status) } : null,
    diagnostics.retryable === true ? { label: '建议', value: '可直接重试' } : null,
    diagnostics.retryable === false ? { label: '建议', value: '不建议直接重试，请先排查根因' } : null,
    diagnostics.hint ? { label: '提示', value: String(diagnostics.hint) } : null,
  ].filter(Boolean)
  return entries as Array<{ label: string; value: string }>
})
const optimizationLogs = computed(() => {
  const raw = runtime.value?.optimization_logs || runtime.value?.self_critique_optimization_logs
  if (!Array.isArray(raw)) return []
  const labelMap: Record<string, string> = {
    structural: '结构优化',
    character: '人物优化',
    delivery: '表达优化',
  }
  return raw
    .filter((item) => item && typeof item === 'object')
    .map((item) => {
      const record = item as Record<string, any>
      const stage = String(record.stage || '').trim()
      const dimensions = Array.isArray(record.dimensions)
        ? record.dimensions.map((value) => String(value)).filter(Boolean)
        : []
      return {
        stage,
        label: labelMap[stage] || stage || '阶段优化',
        summary: `问题 ${Number(record.issue_count || 0)} 项 · ${record.changed ? '已输出修改' : '未改动正文'}${dimensions.length ? ` · 维度：${dimensions.join('、')}` : ''}`,
      }
    })
})
const canRetry = computed(() => (props.allowedActions || []).includes('retry_generation') || stage.value === 'failed' || stage.value === 'evaluation_failed')
const canTerminate = computed(() => {
  const runtimeRecord = runtime.value || null
  const chapterLike = {
    generation_status: (props.status || stage.value || 'not_generated') as any,
    allowed_actions: props.allowedActions || runtimeRecord?.allowed_actions || [],
  }
  return canCancelGeneration(chapterLike, runtimeRecord)
})
const isTerminating = computed(() => Boolean(props.isTerminating))
const stageProgress = computed(() => taskUiModel.value.progress)
const progressPercentLabel = computed(() => `${stageProgress.value}%`)

const runnerEmoji = computed(() => {
  const p = stageProgress.value
  if (stage.value === "completed" || stage.value === "successful" || stage.value === "finalized") return "✅"
  if (stage.value === "failed") return "❌"
  if (p >= 90) return "🚀"
  if (p >= 70) return "🏃"
  if (p >= 40) return "🚶"
  if (p >= 20) return "🐾"
  return "📝"
})

const progressHint = computed(() => {
  if (isLikelyStalled.value) {
    return '已超过预估耗时，可能卡住。请终止处理并查看根因诊断。'
  }
  const base = progressHintMap[stage.value] || '状态刷新后会自动推进到下一阶段。'
  const hasBackendEta = typeof runtime.value?.estimated_remaining_seconds === 'number' && runtime.value.estimated_remaining_seconds >= 0
  if (estimatedRemainingLabel.value) {
    return hasBackendEta ? `${base} 后端预计还需 ${estimatedRemainingLabel.value}` : `${base} 预计还需 ${estimatedRemainingLabel.value}`
  }
  return base
})

const elapsedLabel = computed(() => {
  const startedAt = props.startedAt || runtime.value.started_at
  if (!startedAt) return ''
  const startedTime = new Date(/(?:Z|[+\-]\d{2}:\d{2})$/.test(String(startedAt)) ? String(startedAt) : `${String(startedAt)}Z`).getTime()
  if (Number.isNaN(startedTime)) return ''
  const totalSeconds = Math.max(0, Math.floor((now.value - startedTime) / 1000))
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  if (hours > 0) return `${hours}小时 ${minutes}分`
  if (minutes > 0) return `${minutes}分 ${seconds}秒`
  return `${seconds}秒`
})

const updatedLabel = computed(() => {
  const updatedAt = props.updatedAt || runtime.value.updated_at
  if (!updatedAt) return ''
  const raw = String(updatedAt).trim()
  if (!raw) return ''
  const date = new Date(/(?:Z|[+\-]\d{2}:\d{2})$/.test(raw) ? raw : `${raw}Z`)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
})

const formatEventTime = (value: unknown) => {
  if (!value) return '刚刚'
  const raw = String(value).trim()
  if (!raw) return '刚刚'
  const date = new Date(/(?:Z|[+\-]\d{2}:\d{2})$/.test(raw) ? raw : `${raw}Z`)
  if (Number.isNaN(date.getTime())) return '刚刚'
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

const formatEventLevel = (level: unknown) => {
  if (level === 'warning') return '警告'
  if (level === 'error') return '错误'
  return '信息'
}

const formatEventKindIcon = (event: Record<string, any>) => {
  const kind = String(event?.kind || '').toLowerCase()
  if (event?.level === 'error' || kind === 'error') return '⚠'
  if (kind === 'content') return '✍'
  if (kind === 'review') return '✓'
  if (kind === 'continuity') return '⌁'
  if (kind === 'save') return '▣'
  if (kind === 'ledger') return '☘'
  return '✨'
}

const formatEventKindLabel = (kind: unknown) => {
  const key = String(kind || '').toLowerCase()
  const labels: Record<string, string> = {
    status: '状态',
    content: '正文',
    review: '评审',
    continuity: '连续性',
    save: '保存',
    ledger: '账本',
    error: '异常',
  }
  return labels[key] || String(kind || '状态')
}

const eventTitle = (event: Record<string, any>) => {
  const title = String(event?.title || '').trim()
  if (title) return title
  if (event?.stage) return STAGE_LABEL_FALLBACK[String(event.stage)] || ''
  return ''
}

const eventSummary = (event: Record<string, any>) => {
  const summary = String(event?.summary || event?.message || '').trim()
  if (summary) return summary
  if (event?.content_preview) return '已记录一段生成内容预览'
  return '已记录状态更新'
}

const eventContinuityNotice = (event: Record<string, any>) => {
  const metadata = event?.metadata && typeof event.metadata === 'object' ? event.metadata as Record<string, any> : {}
  if (metadata.manual_stagewide_confirmation_required) {
    return '整章候选没有自动套用：当前流程优先保留原文顺序和前后锚点，只给出局部补丁；确需整章候选时必须人工确认。'
  }
  if (metadata.stagewide_deferred || metadata.stagewide_deferred_count) {
    return '已延后整章候选，继续按局部窗口修补，避免破坏章节连续性。'
  }
  return ''
}

type PatchSuggestionView = {
  scope: string
  problem: string
  suggestion: string
  requirement: string
}

const stringifyPatchField = (value: unknown): string => {
  if (value === null || typeof value === 'undefined') return ''
  if (Array.isArray(value)) return value.map((item: unknown) => stringifyPatchField(item)).filter(Boolean).join('、')
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value).trim()
}

const normalizePatchSuggestion = (item: unknown): PatchSuggestionView | null => {
  if (!item || typeof item !== 'object') {
    const text = stringifyPatchField(item)
    return text ? { scope: '', problem: text, suggestion: '', requirement: '' } : null
  }
  const record = item as Record<string, unknown>
  const scopeParts = [
    stringifyPatchField(record.stage),
    stringifyPatchField(record.strategy),
    stringifyPatchField(record.dimension),
    stringifyPatchField(record.location),
  ].filter(Boolean)
  const problem = stringifyPatchField(record.problem || record.description || record.issue || record.reason)
  const suggestion = stringifyPatchField(record.suggestion || record.suggested_fix || record.patch || record.action)
  const requirement = stringifyPatchField(record.execution_requirement || record.requirement)
  if (!problem && !suggestion && !requirement) return null
  return {
    scope: scopeParts.join(' · '),
    problem: problem || suggestion || requirement,
    suggestion: problem ? suggestion : '',
    requirement,
  }
}

const eventPatchSuggestions = (event: Record<string, any>) => {
  const metadata = event?.metadata && typeof event.metadata === 'object' ? event.metadata as Record<string, unknown> : {}
  const candidates = [
    event?.manual_patch_suggestions,
    event?.patch_suggestions,
    metadata.manual_patch_suggestions,
    metadata.patch_suggestions,
  ]
  return candidates
    .flatMap((value) => Array.isArray(value) ? value : value ? [value] : [])
    .map((item) => normalizePatchSuggestion(item))
    .filter((item): item is PatchSuggestionView => Boolean(item))
    .slice(0, 5)
}

const STAGE_LABEL_FALLBACK: Record<string, string> = {
  prepare_context: '上下文准备',
  cast_plan: '角色规划',
  foreshadowing_plan: '伏笔规划',
  longform_context: '长期上下文包',
  generate_mission: '章节任务生成',
  generate_variants: '正文候选生成',
  review: 'AI 评审',
  continuity_gate: '连续性检查',
  persist_versions: '保存候选版本',
  finalize: '定稿快照',
  ledger_memory: '记忆层更新',
  ledger_foreshadowing: '伏笔闭环',
  ledger_graph: '线索/图谱同步',
  finalized: '定稿完成',
}

const formatDurationMs = (value: unknown) => {
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || parsed <= 0) return ''
  if (parsed < 1000) return `${Math.round(parsed)}ms`
  return `${(parsed / 1000).toFixed(parsed >= 10_000 ? 0 : 2)}秒`
}

const eventDurationLabel = (event: Record<string, any>) => {
  const metadata = event?.metadata
  if (!metadata || typeof metadata !== 'object') return ''
  return formatDurationMs((metadata as Record<string, unknown>).stage_duration_ms)
}

const metadataLabelMap: Record<string, string> = {
  target_word_count: '目标字数',
  min_word_count: '最低字数',
  actual_word_count: '当前字数',
  generation_mode: '生成模式',
  generated_version_count: '候选版本数',
  version_count: '请求版本数',
  stable_retry_used: '是否切换稳定模式',
  requested_preset: '请求预设',
  actual_preset: '实际预设',
  preset_downgraded: '预设已降级',
  downgraded_capabilities: '降级关闭的能力',
  introduced_character_count: '已登场角色数',
  allowed_new_character_count: '允许新角色数',
  best_version_index: '推荐版本序号',
  word_requirement_met: '是否达到字数要求',
  word_requirement_reason: '字数结果',
  attempt_count: '尝试轮次',
  successful_versions: '成功版本数',
  required_success_count: '最低成功门槛',
  generation_attempt_duration_ms: '本轮总耗时',
  generation_attempt_duration_seconds: '本轮总耗时(秒)',
  generation_phase_total_ms: '正文生成耗时',
  guardrail_check_total_ms: '护栏检查耗时',
  guardrail_rewrite_total_ms: '自动修复耗时',
  version_total_ms: '版本累计耗时',
  stage_duration_ms: '阶段耗时',
  stage_duration_seconds: '阶段耗时(秒)',
  diagnosis_stage: '诊断阶段键',
  diagnosis_stage_label: '诊断阶段',
  optimization_stage: '优化阶段键',
  optimization_stage_label: '优化阶段',
  optimization_issue_count: '优化问题数',
  optimization_dimensions: '当前维度',
  optimization_strategy: '优化策略',
  optimization_strategy_phase: '策略阶段',
  optimization_aggregate_issue_count: '聚合问题数',
  optimization_retry_reason: '重试原因',
  repair_attempt_count: '局部修复尝试数',
  unresolved_consistency_issues: '未解决一致性问题数',
  auto_fix_accepted: '自动局部修复已采纳',
  repair_attempts: '修复尝试记录',
  full_chapter_fallback_deferred: '整章兜底已延后',
  consistency_violation_count: '一致性违规数',
  consistency_violation_summary: '一致性违规摘要',
  token_budget_warning: 'Token 预算提示',
  stagewide_requested: '请求整章候选',
  stagewide_allowed: '允许整章候选',
  stagewide_deferred_count: '延后整章候选数',
  manual_stagewide_confirmation_required: '整章候选需人工确认',
  manual_patch_suggestions: '局部补丁建议',
  patch_suggestions: '局部补丁建议',
  execution_requirement: '执行要求',
  event_density_passed: '事件密度达标',
  long_chapter_density_passed: '长章密度达标',
  state_change_interval_passed: '状态变化间隔达标',
  progression_unit_count: '推进单元数',
  event_density_per_1000: '每千字推进密度',
  scene_structure_rate: '场景结构兑现率',
  structure_passed_scene_count: '结构通过场景数',
  resolved: '回收伏笔数',
  reinforced: '强化伏笔数',
  unresolved_due_ids: '逾期未回收伏笔',
  character_states_updated: '更新角色状态数',
  timeline_events_added: '新增时间线事件数',
  causal_chains_added: '新增因果链数',
  dynamic_characters_created: '动态角色入池数',
  dynamic_character_names: '动态入池角色',
  selected_version_id: '确认版本ID',
  memory_success: '记忆层成功',
  foreshadowing_success: '伏笔闭环成功',
  ledger_sync_success: '账本同步成功'
}

const formatEventMetadata = (metadata: unknown) => {
  if (!metadata || typeof metadata !== 'object') return ''
  const entries = Object.entries(metadata as Record<string, unknown>)
    .filter(([, value]) => value !== null && typeof value !== 'undefined' && value !== '')
    .map(([key, value]) => {
      const label = metadataLabelMap[key] || key
      const renderedValue = typeof value === 'boolean'
        ? (value ? '是' : '否')
        : Array.isArray(value)
          ? value.map((item) => typeof item === 'object' ? JSON.stringify(item) : String(item)).join('、')
          : typeof value === 'object'
            ? JSON.stringify(value)
            : String(value)
      return `- ${label}：${renderedValue}`
    })
  return entries.join('\n')
}

onMounted(() => {
  // SSE stream for real-time token output
  const projectId = props.projectId
  const chapterNum = props.chapterNumber
  if (projectId && chapterNum) {
    const streamUrl = `/api/novels/${projectId}/chapters/${chapterNum}/stream`
    const eventSource = new EventSource(streamUrl)
    eventSource.onmessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'token') {
          streamingText.value += data.content || ''
        } else if (data.type === 'progress') {
          progressPercent.value = data.percent ?? progressPercent.value
          stageMessage.value = data.message ?? stageMessage.value
        } else if (data.type === 'complete') {
          eventSource.close()
        }
      } catch {}
    }
    eventSource.onerror = () => eventSource.close()
    onUnmounted(() => eventSource.close())
  }

  timer = window.setInterval(() => {
    now.value = Date.now()
  }, 1000)
})

onUnmounted(() => {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
})
</script>

<style scoped>
.cg-shell {
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px;
}

.cg-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
  align-items: center;
  padding: 12px 14px;
  border-radius: 8px;
  border: 1px solid rgba(148, 163, 184, 0.12);
  background: rgba(255, 255, 255, 0.9);
}

.cg-hero__main {
  display: grid;
  gap: 6px;
  min-width: 0;
}

.cg-kicker {
  margin: 0;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: #6366f1;
}

.cg-title {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
}

.cg-summary {
  margin: 0;
  color: #64748b;
  font-size: 11px;
  line-height: 1.5;
}

.cg-stage-row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.cg-stage-pill {
  display: inline-flex;
  align-items: center;
  min-height: 20px;
  padding: 0 8px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
}

.cg-stage-pill--active {
  background: rgba(59, 130, 246, 0.1);
  color: #2563eb;
}

.cg-stage-pill--danger {
  background: rgba(239, 68, 68, 0.1);
  color: #dc2626;
}

.cg-stage-pill--success {
  background: rgba(16, 185, 129, 0.1);
  color: #059669;
}

.cg-stage-note {
  font-size: 10px;
  color: #94a3b8;
}

.cg-stage-note--accent {
  color: #2563eb;
}

.cg-progress {
  display: grid;
  gap: 4px;
}

.cg-progress__track {
  width: 100%;
  height: 6px;
  background: rgba(148, 163, 184, 0.15);
  border-radius: 999px;
  overflow: hidden;
}

.cg-progress__bar {
  height: 100%;
  border-radius: 999px;
  transition: width 0.5s ease;
}

.cg-progress__bar--active {
  background: linear-gradient(90deg, #3b82f6, #6366f1);
}

.cg-progress__runner {
  position: absolute;
  top: 50%;
  transform: translate(-50%, -50%);
  font-size: 16px;
  transition: left 0.8s ease-out;
  z-index: 2;
  animation: runner-bounce 0.5s ease-in-out infinite alternate;
}
@keyframes runner-bounce {
  0% { transform: translate(-50%, -50%) translateY(-2px); }
  100% { transform: translate(-50%, -50%) translateY(-8px); }
}
.cg-progress__bar--danger {
  background: linear-gradient(90deg, #ef4444, #f97316);
}

.cg-progress__bar--success {
  background: linear-gradient(90deg, #10b981, #34d399);
}

.cg-progress__meta {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
  color: #64748b;
}

.cg-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 8px;
  background: rgba(248, 250, 252, 0.8);
  border: 1px solid rgba(148, 163, 184, 0.1);
}

.cg-badge__icon {
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  border-radius: 6px;
  background: rgba(59, 130, 246, 0.1);
  color: #3b82f6;
}

.cg-badge__icon--active { background: rgba(59, 130, 246, 0.1); color: #3b82f6; }
.cg-badge__icon--danger { background: rgba(239, 68, 68, 0.1); color: #ef4444; }
.cg-badge__icon--success { background: rgba(16, 185, 129, 0.1); color: #10b981; }

.cg-badge__title {
  margin: 0;
  font-size: 11px;
  font-weight: 700;
  color: #0f172a;
}

.cg-badge__desc {
  margin: 0;
  font-size: 10px;
  color: #64748b;
}

.cg-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 8px;
}

.cg-card {
  padding: 12px;
  border-radius: 6px;
  border: 1px solid rgba(148, 163, 184, 0.1);
  background: rgba(255, 255, 255, 0.85);
  display: grid;
  gap: 8px;
}

.cg-card__title {
  margin: 0;
  font-size: 11px;
  font-weight: 700;
  color: #475569;
}

.cg-message {
  display: grid;
  gap: 4px;
  font-size: 11px;
  color: #475569;
  line-height: 1.5;
}

.cg-message p {
  margin: 0;
}

.cg-stuck {
  color: #d97706;
  font-weight: 600;
}

.cg-error {
  color: #dc2626;
  font-weight: 600;
}

.cg-diagnostics__title {
  font-weight: 700;
  color: #0f172a;
  margin: 0 0 4px;
}

.cg-diagnostics__list {
  margin: 0;
  padding-left: 16px;
  font-size: 11px;
}

.cg-diagnostics__list li {
  margin-bottom: 2px;
}

.cg-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.cg-action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  min-height: 28px;
  padding: 0 10px;
  border: 1px solid rgba(37, 99, 235, 0.15);
  border-radius: 4px;
  background: rgba(37, 99, 235, 0.06);
  color: #1d4ed8;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}

.cg-action-btn:hover {
  background: rgba(37, 99, 235, 0.12);
}

.cg-action-btn--strong {
  background: #2563eb;
  border-color: #2563eb;
  color: #fff;
}

.cg-action-btn--strong:hover {
  background: #1d4ed8;
}

.cg-action-btn--danger {
  background: rgba(239, 68, 68, 0.08);
  border-color: rgba(239, 68, 68, 0.2);
  color: #b91c1c;
}

.cg-action-btn--danger:hover {
  background: rgba(239, 68, 68, 0.14);
}

.cg-action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.cg-action-icon {
  width: 12px;
  height: 12px;
  flex: 0 0 auto;
}

.cg-metadata {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.cg-metadata span {
  display: inline-flex;
  align-items: center;
  min-height: 20px;
  padding: 0 6px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.04);
  color: #475569;
  font-size: 10px;
  font-weight: 600;
}

.cg-consistency-warning {
  padding: 10px;
  border-radius: 6px;
  border: 1px solid rgba(220, 38, 38, 0.15);
  background: linear-gradient(180deg, rgba(254, 242, 242, 0.9), rgba(255, 255, 255, 0.85));
  display: grid;
  gap: 6px;
}

.cg-consistency-warning__title {
  margin: 0;
  font-size: 11px;
  font-weight: 700;
  color: #b91c1c;
}

.cg-consistency-warning__desc {
  margin: 0;
  font-size: 10px;
  color: #64748b;
  line-height: 1.5;
}

.cg-consistency-warning__list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 4px;
}

.cg-consistency-warning__list li {
  display: flex;
  align-items: flex-start;
  gap: 5px;
  font-size: 10px;
  line-height: 1.4;
  color: #334155;
}

.cg-consistency-warning__badge {
  display: inline-flex;
  align-items: center;
  min-height: 16px;
  padding: 0 5px;
  border-radius: 999px;
  font-size: 9px;
  font-weight: 700;
  text-transform: uppercase;
  flex-shrink: 0;
}

.cg-consistency-warning__badge--critical {
  background: rgba(220, 38, 38, 0.12);
  color: #b91c1c;
}

.cg-consistency-warning__badge--major {
  background: rgba(245, 158, 11, 0.12);
  color: #b45309;
}

.cg-consistency-warning__badge--minor {
  background: rgba(148, 163, 184, 0.12);
  color: #475569;
}

.cg-consistency-warning__category {
  flex-shrink: 0;
  font-weight: 700;
  color: #6366f1;
}

.cg-consistency-warning__text {
  flex: 1;
  min-width: 0;
}

@media (max-width: 900px) {
  .cg-hero {
    grid-template-columns: 1fr;
  }

  .cg-badge {
    justify-content: flex-start;
  }
}
</style>

