<template>
  <div class="cg-shell">
    <!-- 主区：一屏唯一视觉焦点 = 标题 + 进度 + 正文流 -->
    <section class="cg-main">
      <header class="cg-head">
        <div class="cg-head__text">
          <h3 class="cg-head__title">{{ title }}</h3>
          <p class="cg-head__stage">{{ progressMessageText }}</p>
        </div>
        <div class="cg-head__aside">
          <span :class="['cg-state', `cg-state--${stageTone}`]">
            <i :class="['cg-state__dot', { 'is-live': stageTone === 'active' }]" aria-hidden="true" />
            {{ stageLabel }}
          </span>
          <PixelMascotPicker />
        </div>
      </header>

      <div class="cg-progress">
        <div
          class="cg-progress__track"
          role="progressbar"
          aria-valuemin="0"
          aria-valuemax="100"
          :aria-valuenow="stageProgress"
          :aria-label="pick('章节生成进度', 'Chapter generation progress')"
        >
          <div :class="['cg-progress__fill', `cg-progress__fill--${stageTone}`]" :style="{ width: `${stageProgress}%` }" />
          <span class="cg-progress__runner" :style="{ left: `${stageProgress}%` }">
            <PixelMascot :mascot-id="mascotId" :color="color" :size="32" :moving="mascotMoving" />
          </span>
        </div>
        <ul class="cg-progress__meta">
          <li v-for="item in progressMetaItems" :key="item.key">{{ item.text }}</li>
        </ul>
      </div>

      <!-- 正文实时流：页面最大的阅读块 -->
      <section class="cg-draft">
        <div class="cg-draft__head">
          <h4 class="cg-draft__title">{{ draftTitle }}</h4>
          <span v-if="draftWordCountLabel" class="cg-draft__count">{{ draftWordCountLabel }}</span>
        </div>
        <pre v-if="latestContentPreview" ref="draftRef" class="cg-live-preview" @scroll="handleDraftScroll">{{ latestContentPreview }}</pre>
        <p v-else class="cg-draft__empty">{{ pick('正文还没有开始推送，产出第一段后会实时显示在这里。', 'No draft yet. The first segment will stream in here.') }}</p>
      </section>
    </section>
    <!-- 次区：一行操作，主操作全屏只有 1 个 -->
    <div class="cg-actions">
      <button
        v-if="primaryAction === 'confirm'"
        type="button"
        class="cg-btn cg-btn--primary"
        @click="$emit('fetchStatusNow')"
      >
        <ArrowRight class="cg-btn__icon" aria-hidden="true" />{{ pick('去确认', 'Go to confirm') }}
      </button>
      <button
        v-else-if="primaryAction === 'retry'"
        type="button"
        class="cg-btn cg-btn--primary"
        @click="$emit('regenerateChapter', chapterNumber)"
      >
        <RotateCcw class="cg-btn__icon" aria-hidden="true" />{{ pick('重新生成', 'Generate again') }}
      </button>
      <button
        v-if="primaryAction !== 'confirm'"
        type="button"
        class="cg-btn"
        @click="$emit('fetchStatusNow')"
      >
        <RefreshCw class="cg-btn__icon" aria-hidden="true" />{{ pick('立即刷新', 'Refresh now') }}
      </button>
      <button
        v-if="canTerminate"
        type="button"
        class="cg-btn cg-btn--weak"
        :disabled="isTerminating"
        @click="$emit('terminateChapter', chapterNumber)"
      >
        <Square class="cg-btn__icon" aria-hidden="true" />{{ isTerminating ? pick('终止中', 'Stopping') : pick('终止处理', 'Stop task') }}
      </button>
    </div>
    <!-- 折叠区：任务详情 / 注意事项 / 生成日志 默认全部收起 -->
    <section class="cg-advanced">
      <button
        type="button"
        class="cg-advanced__toggle"
        :aria-expanded="advancedOpen"
        @click="advancedOpen = !advancedOpen"
      >
        <span class="cg-advanced__label">{{ pick('高级信息', 'Advanced details') }}</span>
        <span v-if="alerts.length" :class="['cg-advanced__count', `cg-advanced__count--${alertTone}`]">{{ alerts.length }}</span>
        <span class="cg-advanced__hint">{{ advancedOpen ? pick('收起', 'Hide') : pick('展开', 'Show') }}</span>
        <ChevronDown :class="['cg-advanced__chevron', { 'is-open': advancedOpen }]" aria-hidden="true" />
      </button>

      <div v-show="advancedOpen" class="cg-advanced__body">
        <section v-if="alerts.length" class="cg-group">
          <h5 class="cg-group__title">{{ pick('注意事项', 'Attention') }}</h5>
          <div class="cg-alerts">
            <article v-for="alert in alerts" :key="alert.key" :class="['cg-alert', `cg-alert--${alert.tone}`]">
              <p class="cg-alert__title">{{ alert.title }}</p>
              <p v-if="alert.desc" class="cg-alert__desc">{{ alert.desc }}</p>
              <ul v-if="alert.rows.length" class="cg-alert__rows">
                <li v-for="(row, rowIndex) in alert.rows" :key="`${alert.key}-row-${rowIndex}`">
                  <i :class="['cg-alert__dot', `cg-alert__dot--${row.tone}`]" role="img" :aria-label="row.toneLabel" :title="row.toneLabel" />
                  <span>{{ row.text }}</span>
                </li>
              </ul>
              <ul v-if="alert.tags.length" class="cg-alert__tags">
                <li v-for="(tag, tagIndex) in alert.tags" :key="`${alert.key}-tag-${tagIndex}`">{{ tag }}</li>
              </ul>
            </article>
          </div>
        </section>
        <section v-if="detailItems.length || critiqueItems.length" class="cg-group">
          <h5 class="cg-group__title">{{ pick('任务详情', 'Task details') }}</h5>
          <dl v-if="detailItems.length" class="cg-defs">
            <div v-for="item in detailItems" :key="item.key" class="cg-defs__item">
              <dt class="cg-defs__label">{{ item.label }}<span class="cg-defs__sep" aria-hidden="true">{{ labelSeparator }}</span></dt>
              <dd class="cg-defs__value">{{ item.value }}</dd>
            </div>
          </dl>
          <ul v-if="critiqueItems.length" class="cg-plain-list">
            <li v-for="(item, index) in critiqueItems" :key="`critique-${index}`">{{ item }}</li>
          </ul>
        </section>
        <section v-if="allRuntimeEvents.length" class="cg-group cg-group--logs">
          <div class="cg-group__head">
            <h5 class="cg-group__title">{{ pick('生成日志', 'Generation log') }}</h5>
            <button
              v-if="hiddenRuntimeEventCount > 0 || showAllRuntimeEvents"
              type="button"
              class="cg-log-toggle"
              @click="showAllRuntimeEvents = !showAllRuntimeEvents"
            >
              {{ showAllRuntimeEvents ? pick('收起日志', 'Collapse log') : `${pick('展开全部（+', 'Show all (+')}${hiddenRuntimeEventCount}${pick('）', ')')}` }}
            </button>
          </div>
          <div class="cg-log-tabs" role="tablist" :aria-label="pick('生成日志分组', 'Generation log groups')">
            <button
              v-for="tab in runtimeLogTabs"
              :key="tab.key"
              type="button"
              role="tab"
              :aria-selected="selectedRuntimeLogTab === tab.key"
              :class="['cg-log-tab', { 'is-active': selectedRuntimeLogTab === tab.key }]"
              @click="selectedRuntimeLogTab = tab.key"
            >
              {{ tab.label }}
            </button>
          </div>
          <ul v-if="runtimeEvents.length" class="cg-log-list">
            <li v-for="(event, index) in runtimeEvents" :key="`${event.at || 'event'}-${index}`" class="cg-log-item">
              <div class="cg-log-item__head">
                <i
                  :class="['cg-log-item__level', `cg-log-item__level--${event.level || 'info'}`]"
                  role="img"
                  :aria-label="formatEventLevel(event.level)"
                  :title="formatEventLevel(event.level)"
                />
                <span class="cg-log-item__time">{{ formatEventTime(event.at) }}</span>
                <span v-if="event.kind" class="cg-log-item__tag">{{ formatEventKindLabel(event.kind) }}</span>
                <span v-if="eventDurationLabel(event)" class="cg-log-item__duration">{{ eventDurationLabel(event) }}</span>
              </div>
              <p v-if="eventTitle(event)" class="cg-log-item__title">{{ eventTitle(event) }}</p>
              <p class="cg-log-item__message">{{ eventSummary(event) }}</p>
              <p v-if="eventNotice(event)" class="cg-log-item__notice">{{ eventNotice(event) }}</p>
              <pre v-if="eventContentPreview(event)" class="cg-log-item__preview">{{ eventContentPreview(event) }}</pre>
              <div v-if="eventPatchSuggestions(event).length" class="cg-log-item__patches">
                <p class="cg-log-item__patch-title">{{ pick('局部补丁建议', 'Local patch suggestions') }}</p>
                <ul>
                  <li v-for="(patch, patchIndex) in eventPatchSuggestions(event)" :key="`patch-${index}-${patchIndex}`">
                    <span v-if="patch.scope" class="cg-log-item__patch-scope">{{ patch.scope }}</span>
                    <strong v-if="patch.problem">{{ patch.problem }}</strong>
                    <span v-if="patch.suggestion">{{ patch.suggestion }}</span>
                    <small v-if="patch.requirement">{{ pick('执行要求', 'Execution requirement') }}{{ labelSeparator }}{{ patch.requirement }}</small>
                  </li>
                </ul>
              </div>
              <details v-if="eventDetailRows(event).length" class="cg-log-item__meta">
                <summary>{{ pick('开发者详情', 'Developer details') }}</summary>
                <pre>{{ eventDetailText(event) }}</pre>
              </details>
            </li>
          </ul>
          <p v-else class="cg-log-empty">{{ pick('这个分组暂时没有日志，切到「简略日志」可以看全部阶段。', 'No entries in this group yet. Switch to "Brief log" to see every stage.') }}</p>
        </section>

        <p class="cg-advanced__foot">{{ pick('生成在后台继续，可以先去写其它章节；进入可确认阶段后回到本页即可挑选版本。长时间没有新进展时用「终止处理」结束任务。', 'Generation continues in the background, so you can work on other chapters. Come back to pick a version once candidates are ready. Use "Stop task" if progress stalls for a long time.') }}</p>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { ArrowRight, ChevronDown, RefreshCw, RotateCcw, Square } from 'lucide-vue-next'
import { buildChapterTaskUiModel, canCancelGeneration, normalizeRuntimeStage } from '@/utils/chapterGeneration'
import { stripThinkTags } from '@/utils/safeMarkdown'
import { useLocale } from '@/composables/useLocale'
import { usePixelMascot } from '@/composables/usePixelMascot'
import PixelMascot from '@/components/shared/PixelMascot.vue'
import PixelMascotPicker from '@/components/shared/PixelMascotPicker.vue'

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

const { pick } = useLocale()
const { mascotId, color, beginRun, endRun } = usePixelMascot()

// 中英标点分离：所有「标签 + 值」拼接统一走这个分隔符
const labelSeparator = computed(() => pick('：', ': '))
const listSeparator = computed(() => pick('、', ', '))

const now = ref(Date.now())
let timer: number | null = null

const advancedOpen = ref(false)
const showAllRuntimeEvents = ref(false)
const runtime = computed(() => props.generationRuntime || {})
const runtimeQueued = computed(() => Boolean(runtime.value.queued))
type RuntimeLogTabKey = 'summary' | 'progress' | 'content' | 'review' | 'ledger' | 'diagnostics'
const selectedRuntimeLogTab = ref<RuntimeLogTabKey>('summary')

const runtimeLogTabs = computed<Array<{ key: RuntimeLogTabKey; label: string }>>(() => [
  { key: 'summary', label: pick('简略日志', 'Brief log') },
  { key: 'progress', label: pick('生成进展', 'Progress') },
  { key: 'content', label: pick('草稿预览', 'Draft') },
  { key: 'review', label: pick('评审/修复', 'Review') },
  { key: 'ledger', label: pick('账本闭环', 'Ledger') },
  { key: 'diagnostics', label: pick('诊断详情', 'Diagnostics') },
])

// 事件倒序：最新的排在最前面
const allRuntimeEvents = computed(() => {
  const events = Array.isArray(runtime.value.events) ? runtime.value.events : []
  return [...events].reverse()
})

// 长篇分段正文按段号累积；同一段重复推送时保留最新一次（倒序遍历，先遇到的即最新）
const streamedChapterBody = computed(() => {
  const segments = new Map<number, string>()
  let fallbackIndex = -1
  for (const event of allRuntimeEvents.value) {
    if (!event || typeof event !== 'object') continue
    if (event.content_is_preview === true) continue
    const delta = typeof event.content_delta === 'string' ? event.content_delta : ''
    if (!delta.trim()) continue
    const rawIndex = Number(event.segment_index)
    const index = Number.isFinite(rawIndex) ? Math.floor(rawIndex) : fallbackIndex--
    if (segments.has(index)) continue
    segments.set(index, stripThinkTags(delta).trim())
  }
  if (!segments.size) return ''
  return [...segments.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([, text]) => text)
    .join('\n\n')
})

// 没有正式分段正文时，退回展示最近一次预览片段
const latestContentPreview = computed(() => {
  if (streamedChapterBody.value) return streamedChapterBody.value
  const event = allRuntimeEvents.value.find((item) => typeof item?.content_preview === 'string' && item.content_preview.trim())
  return event ? stripThinkTags(String(event.content_preview)).trim() : ''
})

const draftTitle = computed(() => (streamedChapterBody.value ? pick('正文实时流', 'Live draft stream') : pick('最新草稿片段', 'Latest draft excerpt')))
const draftWordCount = computed(() => latestContentPreview.value.replace(/\s+/g, '').length)
const draftWordCountLabel = computed(() => (draftWordCount.value ? `${draftWordCount.value.toLocaleString()}${pick(' 字', ' chars')}` : ''))
// 正文流自动滚到底部；用户手动上翻后不再强制拉回
const draftRef = ref<HTMLElement | null>(null)
const draftPinnedToBottom = ref(true)
const handleDraftScroll = () => {
  const el = draftRef.value
  if (!el) return
  draftPinnedToBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < 48
}
watch(latestContentPreview, async () => {
  if (!draftPinnedToBottom.value) return
  await nextTick()
  const el = draftRef.value
  if (el) el.scrollTop = el.scrollHeight
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
  if (props.chapterNumber) return pick(`第 ${props.chapterNumber} 章`, `Chapter ${props.chapterNumber}`)
  return pick('章节处理任务', 'Chapter task')
})

const rawStage = computed(() => String(props.progressStage || runtime.value.progress_stage || runtime.value.status || props.status || '').toLowerCase())
const stage = computed(() => normalizeRuntimeStage(rawStage.value))
// 阶段兜底描述：后端没给 message 时用它当主区那句话
const stageDescriptionMap = computed<Record<string, string>>(() => ({
  queued: pick('任务已经进入后台队列，正在等待分配执行槽位。', 'The task is queued and waiting for an execution slot.'),
  prepare_context: pick('系统正在整理蓝图、历史章节、角色约束和上下文材料。', 'Collecting the blueprint, earlier chapters, cast constraints and context.'),
  audit_context: pick('系统正在审计长期记忆、章节快照、时间线和知识图谱。', 'Auditing long-term memory, chapter snapshots, timeline and knowledge graph.'),
  cast_plan: pick('系统正在装配角色规模、登场层级、势力归属和动态角色规则。', 'Assembling cast size, appearance tiers, factions and dynamic cast rules.'),
  foreshadowing_plan: pick('系统正在规划本章伏笔回收、强化、禁忘和可新增线索。', 'Planning which foreshadowing to resolve, reinforce, keep alive or add.'),
  longform_context: pick('系统正在把长篇上下文压成写前约束包。', 'Compressing long-form context into a pre-writing constraint pack.'),
  generate_mission: pick('系统正在构建本章写作任务、约束和生成计划。', 'Building the writing mission, constraints and generation plan.'),
  generate_variants: pick('系统正在正式生成正文草稿，这通常是最耗时的阶段。', 'Generating draft candidates. This is usually the longest stage.'),
  review: pick('正文草稿已产出，系统正在做首轮评审、筛选和增强准备。', 'Drafts are ready; running the first review and enhancement pass.'),
  diagnose_once: pick('系统正在启动单次诊断流程，并准备按阶段聚合问题。', 'Running a single diagnosis pass and grouping issues by stage.'),
  diagnose_previous_chapter: pick('系统正在整理前一章依据包，提取摘要、结尾锚点与关键片段。', 'Building the previous-chapter evidence pack: summary, ending anchors, key excerpts.'),
  diagnose_context_bundle: pick('系统正在整理关联上下文，汇总章节目标、长期记忆与剧情线索。', 'Assembling related context: chapter goals, long-term memory and plot clues.'),
  diagnose_structural: pick('系统正在做结构诊断，聚合检查逻辑、承接与视角问题。', 'Structural diagnosis: logic, hand-off and point-of-view issues.'),
  diagnose_character: pick('系统正在做人物诊断，聚合检查角色、关系、情绪与对话问题。', 'Character diagnosis: cast, relationships, emotion and dialogue issues.'),
  diagnose_delivery: pick('系统正在做表达诊断，聚合检查节奏、场景、悬念与文风问题。', 'Delivery diagnosis: pacing, scenes, suspense and style issues.'),
  optimize_content: pick('系统正在按诊断结果执行分阶段优化。', 'Applying staged optimization based on the diagnosis.'),
  optimize_structural: pick('正在处理结构层问题：逻辑、承接、视角。', 'Fixing structural issues: logic, hand-off, point of view.'),
  optimize_character: pick('正在处理人物层问题：角色、关系、情绪、对话。', 'Fixing character issues: cast, relationships, emotion, dialogue.'),
  optimize_delivery: pick('正在处理表现层问题：节奏、场景、悬念、文风。', 'Fixing delivery issues: pacing, scenes, suspense, style.'),
  consistency: pick('系统正在校验剧情设定、前后文和伏笔一致性。', 'Checking settings, continuity and foreshadowing consistency.'),
  continuity_gate: pick('系统正在检查跨章节、伏笔、角色状态和知识边界。', 'Checking cross-chapter continuity, foreshadowing, cast state and knowledge limits.'),
  optimizer: pick('系统正在做定向优化，强化最重要的问题维度。', 'Running targeted optimization on the most important dimensions.'),
  enrichment: pick('系统正在补字数、强化细节和做最终质量增强。', 'Filling word count, sharpening detail and doing the final quality pass.'),
  persist_versions: pick('系统正在写入候选版本并整理确认结果。', 'Persisting candidate versions and preparing the confirmation view.'),
  finalize: pick('系统正在确认定稿，写入章节摘要和快照。', 'Finalizing: writing the chapter summary and snapshot.'),
  ledger_memory: pick('系统正在把正文更新进角色状态、时间线和因果账本。', 'Updating cast state, timeline and causal ledger from the draft.'),
  ledger_foreshadowing: pick('系统正在判断本章伏笔回收、强化和新埋设情况。', 'Resolving, reinforcing and planting foreshadowing for this chapter.'),
  ledger_graph: pick('系统正在同步线索和知识图谱。', 'Syncing clues and the knowledge graph.'),
  finalized: pick('定稿闭环已完成，正文和故事账本都已处理。', 'Finalization is complete: draft and story ledger are both updated.'),
  generating: pick('系统正在写正文草稿，完成后会自动进入评估或确认阶段。', 'Writing the draft. It will move to evaluation or confirmation automatically.'),
  evaluating: pick('正文已生成，系统正在评估候选版本可用性。', 'Draft is ready; evaluating candidate versions.'),
  selecting: pick('候选版本已就绪，即将切换到版本确认界面。', 'Candidates are ready; switching to version confirmation shortly.'),
  waiting_for_confirm: pick('候选版本已准备好，可直接确认并继续下一章。', 'Candidates are ready. Confirm one and move to the next chapter.'),
  ready: pick('这一章已经处理完成，可以继续阅读、确认或推进下一章。', 'This chapter is done. Read it, confirm it, or move on.'),
  failed: pick('这一章处理失败，请查看错误摘要后重试。', 'This chapter failed. Check the error summary before retrying.'),
  evaluation_failed: pick('评审阶段出了问题，但已有候选版本仍可查看、确认或重新评审。', 'Review failed, but existing candidates can still be inspected or confirmed.'),
}))
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
const stageLabel = computed(() => taskUiModel.value.stageLabel || pick('处理中', 'Working'))
const stageDescription = computed(() => stageDescriptionMap.value[rawStage.value] || stageDescriptionMap.value[stage.value] || pick('系统正在处理这一章。', 'Working on this chapter.'))
const progressMessageText = computed(() => {
  const cleaned = stripThinkTags(taskUiModel.value.displayMessage || '')
  return cleaned || stageDescription.value
})
const estimatedRemainingLabel = computed(() => taskUiModel.value.etaLabel)
const isLikelyStalled = computed(() => taskUiModel.value.isLikelyStalled)
const statusFetchWarning = computed(() => {
  if (statusFetchFailureCount.value <= 0) return ''
  if (statusFetchFailureCount.value === 1) return pick('刚刚有一次状态同步失败，页面会继续自动重试。', 'One status sync just failed. The page keeps retrying automatically.')
  return pick(
    `状态同步已连续失败 ${statusFetchFailureCount.value} 次，建议优先终止处理后再重试。`,
    `Status sync failed ${statusFetchFailureCount.value} times in a row. Stop the task before retrying.`,
  )
})
const stalledWarning = computed(() => {
  if (!isLikelyStalled.value) return ''
  return pick(
    '状态长时间没有更新，任务可能卡住。建议先「终止处理」，再看根因诊断后重试。',
    'No updates for a long time; the task may be stuck. Stop it, check the diagnostics, then retry.',
  )
})

const stageTone = computed(() => {
  if (stage.value === 'failed' || stage.value === 'evaluation_failed' || isLikelyStalled.value) return 'danger'
  if (['ready', 'successful', 'waiting_for_confirm', 'selecting'].includes(stage.value)) return 'success'
  return 'active'
})

const lastErrorSummary = computed(() => props.lastErrorSummary || runtime.value.last_error_summary || runtime.value?.diagnostics?.message || '')
const stageProgress = computed(() => taskUiModel.value.progress)
const progressPercentLabel = computed(() => `${stageProgress.value}%`)
const isTerminating = computed(() => Boolean(props.isTerminating))
const elapsedLabel = computed(() => {
  const startedAt = props.startedAt || runtime.value.started_at
  if (!startedAt) return ''
  const startedTime = new Date(/(?:Z|[+\-]\d{2}:\d{2})$/.test(String(startedAt)) ? String(startedAt) : `${String(startedAt)}Z`).getTime()
  if (Number.isNaN(startedTime)) return ''
  const totalSeconds = Math.max(0, Math.floor((now.value - startedTime) / 1000))
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  if (hours > 0) return pick(`${hours}小时 ${minutes}分`, `${hours}h ${minutes}m`)
  if (minutes > 0) return pick(`${minutes}分 ${seconds}秒`, `${minutes}m ${seconds}s`)
  return pick(`${seconds}秒`, `${seconds}s`)
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

// 进度条下方那一行紧凑元信息：百分比 · 已等待 · 预计剩余 · 已生成字数
const progressMetaItems = computed(() => {
  const items: Array<{ key: string; text: string }> = [{ key: 'percent', text: progressPercentLabel.value }]
  if (elapsedLabel.value) items.push({ key: 'elapsed', text: `${pick('已等待', 'Elapsed')} ${elapsedLabel.value}` })
  if (estimatedRemainingLabel.value) items.push({ key: 'eta', text: `${pick('预计剩余', 'Remaining')} ${estimatedRemainingLabel.value}` })
  if (draftWordCountLabel.value) items.push({ key: 'words', text: `${pick('已生成', 'Drafted')} ${draftWordCountLabel.value.trim()}` })
  return items
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
// 候选已就绪时，唯一主操作是「去确认」：刷新一次状态后父级会自动切到版本确认区
const canConfirmCandidates = computed(() => {
  const actions = props.allowedActions || runtime.value.allowed_actions || []
  return actions.includes('confirm_version') || actions.includes('review_versions')
})
const primaryAction = computed<'confirm' | 'retry' | 'none'>(() => {
  if (canConfirmCandidates.value) return 'confirm'
  if (canRetry.value) return 'retry'
  return 'none'
})
const diagnosticsSummary = computed(() => {
  const diagnostics = runtime.value?.diagnostics
  if (!diagnostics || typeof diagnostics !== 'object') return []
  const entries = [
    diagnostics.requestId ? { label: pick('请求ID', 'Request ID'), value: String(diagnostics.requestId) } : null,
    diagnostics.rootCause ? { label: pick('根因', 'Root cause'), value: String(diagnostics.rootCause) } : null,
    diagnostics.code ? { label: pick('错误码', 'Error code'), value: String(diagnostics.code) } : null,
    typeof diagnostics.status === 'number' ? { label: pick('状态码', 'HTTP status'), value: String(diagnostics.status) } : null,
    diagnostics.retryable === true ? { label: pick('建议', 'Advice'), value: pick('可直接重试', 'Safe to retry') } : null,
    diagnostics.retryable === false ? { label: pick('建议', 'Advice'), value: pick('不建议直接重试，请先排查根因', 'Do not retry yet; investigate the root cause first') } : null,
    diagnostics.hint ? { label: pick('提示', 'Hint'), value: String(diagnostics.hint) } : null,
  ].filter(Boolean)
  return entries as Array<{ label: string; value: string }>
})

const optimizationLogs = computed(() => {
  const raw = runtime.value?.optimization_logs || runtime.value?.self_critique_optimization_logs
  if (!Array.isArray(raw)) return []
  const labelMap: Record<string, string> = {
    structural: pick('结构优化', 'Structure pass'),
    character: pick('人物优化', 'Character pass'),
    delivery: pick('表达优化', 'Delivery pass'),
  }
  return raw
    .filter((item) => item && typeof item === 'object')
    .map((item) => {
      const record = item as Record<string, any>
      const stageKey = String(record.stage || '').trim()
      const dimensions = Array.isArray(record.dimensions)
        ? record.dimensions.map((value: unknown) => String(value)).filter(Boolean)
        : []
      const issues = pick(`问题 ${Number(record.issue_count || 0)} 项`, `${Number(record.issue_count || 0)} issues`)
      const changed = record.changed ? pick('已输出修改', 'draft updated') : pick('未改动正文', 'draft unchanged')
      const dimensionText = dimensions.length
        ? ` · ${pick('维度', 'Dimensions')}${labelSeparator.value}${dimensions.join(listSeparator.value)}`
        : ''
      return {
        stage: stageKey,
        label: labelMap[stageKey] || stageKey || pick('阶段优化', 'Stage pass'),
        summary: `${issues} · ${changed}${dimensionText}`,
      }
    })
})

// 批判优化进展：高亮 + 分阶段优化日志，收进折叠区
const critiqueItems = computed(() => {
  const highlights = Array.isArray(taskUiModel.value.critiqueHighlights) ? taskUiModel.value.critiqueHighlights : []
  return [
    ...highlights.map((item) => String(item)),
    ...optimizationLogs.value.map((item) => `${item.label}${labelSeparator.value}${item.summary}`),
  ]
})
// 任务详情：原来平铺的 20 多个 span 收敛成两列定义列表
const detailItems = computed(() => {
  const source = runtime.value
  const items: Array<{ key: string; label: string; value: string }> = []
  const push = (key: string, label: string, value: unknown) => {
    if (value === null || typeof value === 'undefined' || value === '') return
    items.push({ key, label, value: String(value) })
  }
  push('requested_preset', pick('请求预设', 'Requested preset'), source.requested_preset)
  push('actual_preset', pick('实际预设', 'Actual preset'), source.actual_preset)
  push('generation_mode', pick('模式', 'Mode'), source.generation_mode)
  push('version_count', pick('候选版本', 'Candidates'), source.version_count)
  push('target_word_count', pick('目标字数', 'Target words'), source.target_word_count)
  push('min_word_count', pick('最低字数', 'Minimum words'), source.min_word_count)
  push('actual_word_count', pick('当前字数', 'Current words'), source.actual_word_count)
  push('stable_retry_used', pick('是否切换稳定模式', 'Switched to stable mode'), source.stable_retry_used)
  push('word_requirement_met', pick('是否达到字数要求', 'Word requirement met'), source.word_requirement_met)
  push('stagewide_allowed', pick('允许整章候选', 'Full-chapter candidate allowed'), source.stagewide_allowed)
  push('diagnosis_stage_label', pick('诊断阶段', 'Diagnosis stage'), source.diagnosis_stage_label)
  if (Array.isArray(source.diagnosis_dimensions) && source.diagnosis_dimensions.length) {
    push('diagnosis_dimensions', pick('诊断维度', 'Diagnosis dimensions'), source.diagnosis_dimensions.join(listSeparator.value))
  }
  push('optimization_stage_label', pick('优化阶段', 'Optimization stage'), source.optimization_stage_label)
  if (Array.isArray(source.optimization_dimensions) && source.optimization_dimensions.length) {
    push('optimization_dimensions', pick('当前维度', 'Current dimensions'), source.optimization_dimensions.join(listSeparator.value))
  }
  push('critique_summary', pick('批判摘要', 'Critique summary'), taskUiModel.value.critiqueSummary)
  if (runtimeQueued.value) push('queued', pick('状态', 'State'), pick('已排队执行', 'Queued'))
  push('elapsed', pick('已等待', 'Elapsed'), elapsedLabel.value)
  push('updated', pick('最近更新', 'Updated'), updatedLabel.value)
  push('retry_count', pick('重试次数', 'Retries'), source.retry_count)
  push('event_cursor', pick('事件游标', 'Event cursor'), source.event_cursor)
  push('task_id', pick('任务', 'Task'), source.task_id || source.job_id)
  push('task_status', pick('持久任务', 'Persistent task'), source.task_status)
  return items
})
type AlertTone = 'danger' | 'warning' | 'info'
type AlertRow = { tone: AlertTone; toneLabel: string; text: string }
type CgAlert = { key: string; tone: AlertTone; title: string; desc: string; tags: string[]; rows: AlertRow[] }

const ALERT_RANK: Record<AlertTone, number> = { danger: 0, warning: 1, info: 2 }
const toneLabelOf = (tone: AlertTone) => {
  if (tone === 'danger') return pick('严重', 'Critical')
  if (tone === 'warning') return pick('主要', 'Major')
  return pick('次要', 'Minor')
}
const severityToneOf = (severity: unknown): AlertTone => {
  const key = String(severity || '').toLowerCase()
  if (['critical', 'blocker', 'fatal'].includes(key)) return 'danger'
  if (['major', 'high', 'warning'].includes(key)) return 'warning'
  return 'info'
}

// 所有告警统一成一种 Alert 形态，按严重度排序后收进折叠区
const alerts = computed<CgAlert[]>(() => {
  const source = runtime.value
  const list: CgAlert[] = []
  const add = (alert: Partial<CgAlert> & { key: string; tone: AlertTone; title: string }) => {
    list.push({ desc: '', tags: [], rows: [], ...alert })
  }

  if (lastErrorSummary.value) {
    add({ key: 'error', tone: 'danger', title: pick('错误摘要', 'Error summary'), desc: String(lastErrorSummary.value) })
  }
  if (stalledWarning.value) {
    add({ key: 'stalled', tone: 'danger', title: pick('任务可能卡住', 'Task may be stuck'), desc: stalledWarning.value })
  }
  if (statusFetchWarning.value) {
    add({ key: 'status-sync', tone: 'warning', title: pick('状态同步异常', 'Status sync issue'), desc: statusFetchWarning.value })
  }
  if (Number(source.consistency_violation_count || 0) > 0) {
    const rawRows = Array.isArray(source.consistency_violation_summary) ? source.consistency_violation_summary : []
    const rows: AlertRow[] = rawRows.map((item: Record<string, any>) => {
      const tone = severityToneOf(item?.severity)
      const category = item?.category ? `${String(item.category)}${labelSeparator.value}` : ''
      return { tone, toneLabel: toneLabelOf(tone), text: `${category}${String(item?.description || '')}` }
    })
    add({
      key: 'consistency',
      tone: rows.some((row) => row.tone === 'danger') ? 'danger' : 'warning',
      title: pick('一致性校验警告', 'Continuity check warning'),
      desc: pick(
        `一致性校验发现 ${Number(source.consistency_violation_count)} 项未解决问题，可能影响剧情连贯性。`,
        `${Number(source.consistency_violation_count)} unresolved continuity issues may affect the storyline.`,
      ),
      rows,
    })
  }
  if (source.preset_downgraded && Array.isArray(source.downgraded_capabilities) && source.downgraded_capabilities.length) {
    const from = String(source.requested_preset || pick('未知', 'unknown'))
    const to = String(source.actual_preset || 'stable')
    add({
      key: 'preset-downgrade',
      tone: 'warning',
      title: pick('质量降级提示', 'Quality downgrade'),
      desc: pick(
        `生成遇到不稳定，已从「${from}」降级到「${to}」，以下能力被临时关闭以保障基础生成：`,
        `Generation was unstable, so it fell back from "${from}" to "${to}". These capabilities are temporarily off:`,
      ),
      tags: source.downgraded_capabilities.map((item: unknown) => String(item)),
    })
  }
  if (source.token_budget_warning?.message) {
    const level = String(source.token_budget_warning.level || '').toLowerCase()
    add({
      key: 'token-budget',
      tone: level === 'exceeded' ? 'danger' : level === 'warning' ? 'warning' : 'info',
      title: pick('Token 预算提示', 'Token budget notice'),
      desc: String(source.token_budget_warning.message),
    })
  }
  if (diagnosticsSummary.value.length) {
    add({
      key: 'diagnostics',
      tone: 'info',
      title: pick('诊断信息', 'Diagnostics'),
      rows: diagnosticsSummary.value.map((item) => ({
        tone: 'info' as AlertTone,
        toneLabel: toneLabelOf('info'),
        text: `${item.label}${labelSeparator.value}${item.value}`,
      })),
    })
  }
  if (taskUiModel.value.degradedSummary) {
    add({ key: 'degraded', tone: 'info', title: pick('阶段降级', 'Degraded stages'), desc: String(taskUiModel.value.degradedSummary) })
  }
  if (source.recovered_from_reload) {
    add({
      key: 'recovered',
      tone: 'info',
      title: pick('已恢复任务状态', 'Task state recovered'),
      desc: pick('已从后端任务中心恢复状态，断线后会继续续接。', 'Restored from the task center; it will resume after a disconnect.'),
    })
  }
  return list.sort((a, b) => ALERT_RANK[a.tone] - ALERT_RANK[b.tone])
})

const alertTone = computed<AlertTone>(() => alerts.value[0]?.tone || 'info')
const formatEventTime = (value: unknown) => {
  const fallback = pick('刚刚', 'just now')
  if (!value) return fallback
  const raw = String(value).trim()
  if (!raw) return fallback
  const date = new Date(/(?:Z|[+\-]\d{2}:\d{2})$/.test(raw) ? raw : `${raw}Z`)
  if (Number.isNaN(date.getTime())) return fallback
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

const formatEventLevel = (level: unknown) => {
  if (level === 'warning') return pick('警告', 'Warning')
  if (level === 'error') return pick('错误', 'Error')
  return pick('信息', 'Info')
}

const formatEventKindLabel = (kind: unknown) => {
  const key = String(kind || '').toLowerCase()
  const labels: Record<string, string> = {
    status: pick('状态', 'Status'),
    content: pick('正文', 'Draft'),
    review: pick('评审', 'Review'),
    continuity: pick('连续性', 'Continuity'),
    save: pick('保存', 'Save'),
    ledger: pick('账本', 'Ledger'),
    error: pick('异常', 'Error'),
  }
  return labels[key] || String(kind || pick('状态', 'Status'))
}

const stageLabelFallback = computed<Record<string, string>>(() => ({
  prepare_context: pick('上下文准备', 'Context prep'),
  cast_plan: pick('角色规划', 'Cast plan'),
  foreshadowing_plan: pick('伏笔规划', 'Foreshadowing plan'),
  longform_context: pick('长期上下文包', 'Long-form context'),
  generate_mission: pick('章节任务生成', 'Chapter mission'),
  generate_variants: pick('正文候选生成', 'Draft candidates'),
  review: pick('AI 评审', 'AI review'),
  continuity_gate: pick('连续性检查', 'Continuity gate'),
  persist_versions: pick('保存候选版本', 'Save candidates'),
  finalize: pick('定稿快照', 'Finalize snapshot'),
  ledger_memory: pick('记忆层更新', 'Memory update'),
  ledger_foreshadowing: pick('伏笔闭环', 'Foreshadowing closure'),
  ledger_graph: pick('线索/图谱同步', 'Clue & graph sync'),
  finalized: pick('定稿完成', 'Finalized'),
}))

const eventTitle = (event: Record<string, any>) => {
  const eventName = String(event?.title || '').trim()
  if (eventName) return eventName
  if (event?.stage) return stageLabelFallback.value[String(event.stage)] || ''
  return ''
}
const eventSummary = (event: Record<string, any>) => {
  const summary = String(event?.summary || event?.message || '').trim()
  if (summary) return summary
  if (event?.content_preview) return pick('已记录一段生成内容预览', 'Recorded a draft preview')
  return pick('已记录状态更新', 'Recorded a status update')
}

const eventContentPreview = (event: Record<string, any>) => {
  const raw = typeof event?.content_preview === 'string' ? event.content_preview : ''
  return raw.trim() ? stripThinkTags(raw).trim() : ''
}

const eventNotice = (event: Record<string, any>) => {
  const metadata = event?.metadata && typeof event.metadata === 'object' ? event.metadata as Record<string, any> : {}
  if (metadata.manual_stagewide_confirmation_required) {
    return pick(
      '整章候选没有自动套用：当前流程优先保留原文顺序和前后锚点，只给出局部补丁；确需整章候选时必须人工确认。',
      'The whole-chapter candidate was not applied automatically: the pipeline keeps the original order and anchors and only suggests local patches. A full replacement needs manual confirmation.',
    )
  }
  if (metadata.stagewide_deferred || metadata.stagewide_deferred_count) {
    return pick(
      '已延后整章候选，继续按局部窗口修补，避免破坏章节连续性。',
      'The whole-chapter candidate was deferred; local patches continue so continuity is preserved.',
    )
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
  if (Array.isArray(value)) return value.map((item: unknown) => stringifyPatchField(item)).filter(Boolean).join(listSeparator.value)
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
    .flatMap((value) => (Array.isArray(value) ? value : value ? [value] : []))
    .map((item) => normalizePatchSuggestion(item))
    .filter((item): item is PatchSuggestionView => Boolean(item))
    .slice(0, 5)
}

const formatDurationMs = (value: unknown) => {
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || parsed <= 0) return ''
  if (parsed < 1000) return `${Math.round(parsed)}ms`
  const seconds = (parsed / 1000).toFixed(parsed >= 10_000 ? 0 : 2)
  return pick(`${seconds}秒`, `${seconds}s`)
}

const eventDurationLabel = (event: Record<string, any>) => {
  const metadata = event?.metadata
  if (!metadata || typeof metadata !== 'object') return ''
  return formatDurationMs((metadata as Record<string, unknown>).stage_duration_ms)
}

// 开发者详情：指标 / 产物引用 / 原始 metadata 合并成一份纯文本，默认折叠
const eventDetailRows = (event: Record<string, any>) => {
  const groups = [event?.metrics, event?.artifact_refs, event?.metadata]
  const rows: string[] = []
  for (const group of groups) {
    if (!group || typeof group !== 'object') continue
    for (const [key, value] of Object.entries(group as Record<string, unknown>)) {
      if (value === null || typeof value === 'undefined' || value === '') continue
      const label = metadataLabelMap.value[key] || key
      const renderedValue = typeof value === 'boolean'
        ? (value ? pick('是', 'Yes') : pick('否', 'No'))
        : Array.isArray(value)
          ? value.map((item) => (typeof item === 'object' ? JSON.stringify(item) : String(item))).join(listSeparator.value)
          : typeof value === 'object'
            ? JSON.stringify(value)
            : String(value)
      rows.push(`- ${label}${labelSeparator.value}${renderedValue}`)
    }
  }
  return rows
}
const eventDetailText = (event: Record<string, any>) => eventDetailRows(event).join('\n')

onMounted(() => {
  // 计时器只负责刷新“已等待/预计剩余”，SSE 与轮询由上层 store 负责
  timer = window.setInterval(() => {
    now.value = Date.now()
  }, 1000)
})

onUnmounted(() => {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
  if (mascotRunning) {
    mascotRunning = false
    endRun()
  }
})

/** 吉祥物是否在推进：任务处于活跃态且未满进度；进入该状态时随机换一种姿态 */
const mascotMoving = computed(() => stageTone.value === 'active' && stageProgress.value < 100)
let mascotRunning = false

watch(
  mascotMoving,
  (moving) => {
    if (moving && !mascotRunning) {
      mascotRunning = true
      beginRun()
    } else if (!moving && mascotRunning) {
      mascotRunning = false
      endRun()
    }
  },
  { immediate: true },
)
// 日志字段中文/英文标签表（值必须走 pick，不允许裸中文）
const metadataLabelMap = computed<Record<string, string>>(() => ({
  target_word_count: pick('目标字数', 'Target words'),
  min_word_count: pick('最低字数', 'Minimum words'),
  actual_word_count: pick('当前字数', 'Current words'),
  generation_mode: pick('生成模式', 'Generation mode'),
  generated_version_count: pick('候选版本数', 'Candidates generated'),
  version_count: pick('请求版本数', 'Candidates requested'),
  stable_retry_used: pick('是否切换稳定模式', 'Switched to stable mode'),
  requested_preset: pick('请求预设', 'Requested preset'),
  actual_preset: pick('实际预设', 'Actual preset'),
  preset_downgraded: pick('预设已降级', 'Preset downgraded'),
  downgraded_capabilities: pick('降级关闭的能力', 'Disabled capabilities'),
  introduced_character_count: pick('已登场角色数', 'Introduced characters'),
  allowed_new_character_count: pick('允许新角色数', 'Allowed new characters'),
  best_version_index: pick('推荐版本序号', 'Recommended version'),
  word_requirement_met: pick('是否达到字数要求', 'Word requirement met'),
  word_requirement_reason: pick('字数结果', 'Word count result'),
  attempt_count: pick('尝试轮次', 'Attempts'),
  successful_versions: pick('成功版本数', 'Successful versions'),
  required_success_count: pick('最低成功门槛', 'Required successes'),
  generation_attempt_duration_ms: pick('本轮总耗时', 'Attempt duration (ms)'),
  generation_attempt_duration_seconds: pick('本轮总耗时(秒)', 'Attempt duration (s)'),
  generation_phase_total_ms: pick('正文生成耗时', 'Draft phase (ms)'),
  guardrail_check_total_ms: pick('护栏检查耗时', 'Guardrail checks (ms)'),
  guardrail_rewrite_total_ms: pick('自动修复耗时', 'Auto repair (ms)'),
  version_total_ms: pick('版本累计耗时', 'Version total (ms)'),
  stage_duration_ms: pick('阶段耗时', 'Stage duration (ms)'),
  stage_duration_seconds: pick('阶段耗时(秒)', 'Stage duration (s)'),
  diagnosis_stage: pick('诊断阶段键', 'Diagnosis stage key'),
  diagnosis_stage_label: pick('诊断阶段', 'Diagnosis stage'),
  optimization_stage: pick('优化阶段键', 'Optimization stage key'),
  optimization_stage_label: pick('优化阶段', 'Optimization stage'),
  optimization_issue_count: pick('优化问题数', 'Optimization issues'),
  optimization_dimensions: pick('当前维度', 'Current dimensions'),
  optimization_strategy: pick('优化策略', 'Optimization strategy'),
  optimization_strategy_phase: pick('策略阶段', 'Strategy phase'),
  optimization_aggregate_issue_count: pick('聚合问题数', 'Aggregated issues'),
  optimization_retry_reason: pick('重试原因', 'Retry reason'),
  repair_attempt_count: pick('局部修复尝试数', 'Local repair attempts'),
  unresolved_consistency_issues: pick('未解决一致性问题数', 'Unresolved continuity issues'),
  auto_fix_accepted: pick('自动局部修复已采纳', 'Auto patch accepted'),
  repair_attempts: pick('修复尝试记录', 'Repair attempt log'),
  full_chapter_fallback_deferred: pick('整章兜底已延后', 'Full-chapter fallback deferred'),
  consistency_violation_count: pick('一致性违规数', 'Continuity violations'),
  consistency_violation_summary: pick('一致性违规摘要', 'Continuity violation summary'),
  token_budget_warning: pick('Token 预算提示', 'Token budget notice'),
  stagewide_requested: pick('请求整章候选', 'Full-chapter candidate requested'),
  stagewide_allowed: pick('允许整章候选', 'Full-chapter candidate allowed'),
  stagewide_deferred_count: pick('延后整章候选数', 'Deferred full-chapter candidates'),
  manual_stagewide_confirmation_required: pick('整章候选需人工确认', 'Manual confirmation required'),
  manual_patch_suggestions: pick('局部补丁建议', 'Local patch suggestions'),
  patch_suggestions: pick('局部补丁建议', 'Local patch suggestions'),
  execution_requirement: pick('执行要求', 'Execution requirement'),
  event_density_passed: pick('事件密度达标', 'Event density passed'),
  long_chapter_density_passed: pick('长章密度达标', 'Long-chapter density passed'),
  state_change_interval_passed: pick('状态变化间隔达标', 'State-change interval passed'),
  // T-14：这两个字段解释上面三个「达标」为什么可能整行不显示——
  // eventDetailRows 会跳过 null 值，所以样本过短时三个 passed 不出现，
  // 取而代之出现「事件密度已评估：否 / 跳过原因：sample_too_short」。
  event_density_evaluated: pick('事件密度已评估', 'Event density evaluated'),
  event_density_skip_reason: pick('事件密度跳过原因', 'Event density skip reason'),
  // T-13：同理，对话维度三态的两个解释字段。
  dialogue_expectation_declared: pick('任务书声明对话预期', 'Dialogue expectation declared'),
  dialogue_state_applicable: pick('对话维度适用', 'Dialogue dimension applicable'),
  progression_unit_count: pick('推进单元数', 'Progression units'),
  event_density_per_1000: pick('每千字推进密度', 'Events per 1000 chars'),
  scene_structure_rate: pick('场景结构兑现率', 'Scene structure rate'),
  structure_passed_scene_count: pick('结构通过场景数', 'Scenes passing structure'),
  resolved: pick('回收伏笔数', 'Foreshadowing resolved'),
  reinforced: pick('强化伏笔数', 'Foreshadowing reinforced'),
  unresolved_due_ids: pick('逾期未回收伏笔', 'Overdue foreshadowing'),
  character_states_updated: pick('更新角色状态数', 'Character states updated'),
  timeline_events_added: pick('新增时间线事件数', 'Timeline events added'),
  causal_chains_added: pick('新增因果链数', 'Causal chains added'),
  dynamic_characters_created: pick('动态角色入池数', 'Dynamic characters created'),
  dynamic_character_names: pick('动态入池角色', 'Dynamic character names'),
  selected_version_id: pick('确认版本ID', 'Confirmed version ID'),
  memory_success: pick('记忆层成功', 'Memory update ok'),
  foreshadowing_success: pick('伏笔闭环成功', 'Foreshadowing closure ok'),
  ledger_sync_success: pick('账本同步成功', 'Ledger sync ok'),
}))
</script>

<style scoped>
/* 页面外壳：24px 呼吸空间，卡片间距统一 --xq-space-4 */
.cg-shell { display: flex; flex-direction: column; gap: var(--xq-space-4); padding: var(--xq-space-6); min-height: 0; color: var(--xq-text-body); font-family: var(--xq-font-sans); }

/* ---------- 主区 ---------- */
.cg-main { display: flex; flex-direction: column; gap: var(--xq-space-5); }
.cg-head { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--xq-space-4); }
.cg-head__text { display: flex; flex-direction: column; gap: var(--xq-space-1); min-width: 0; }
.cg-head__title { margin: 0; color: var(--xq-text); font-size: var(--xq-text-xl); font-weight: var(--xq-weight-semibold); line-height: var(--xq-leading-tight); }
.cg-head__stage { margin: 0; max-width: var(--xq-reading-max); color: var(--xq-text-muted); font-size: var(--xq-text-base); line-height: var(--xq-leading-snug); }
.cg-head__aside { display: flex; flex: 0 0 auto; align-items: center; gap: var(--xq-space-2); }
.cg-state { display: inline-flex; align-items: center; gap: var(--xq-space-2); height: 24px; padding: 0 var(--xq-space-3); border: 1px solid var(--xq-accent-border); border-radius: var(--xq-radius-pill); background: var(--xq-accent-soft); color: var(--xq-accent-text); font-size: var(--xq-text-xs); font-weight: var(--xq-weight-medium); white-space: nowrap; }
.cg-state--danger { border-color: var(--xq-danger-border); background: var(--xq-danger-soft); color: var(--xq-danger-text); }
.cg-state--success { border-color: var(--xq-success-border); background: var(--xq-success-soft); color: var(--xq-success-text); }
.cg-state__dot { flex: 0 0 auto; width: 6px; height: 6px; border-radius: var(--xq-radius-pill); background: currentColor; }
.cg-state__dot.is-live { animation: cg-pulse 1.6s var(--xq-ease) infinite; }

/* ---------- 进度条：吉祥物骑在进度点上 ---------- */
.cg-progress { display: flex; flex-direction: column; gap: var(--xq-space-3); }
.cg-progress__track { position: relative; height: 12px; border-radius: var(--xq-radius-pill); background: var(--xq-surface-3); }
.cg-progress__fill { height: 100%; border-radius: var(--xq-radius-pill); background: var(--xq-accent); transition: width 300ms linear; }
.cg-progress__fill--danger { background: var(--xq-danger); }
.cg-progress__fill--success { background: var(--xq-success); }
.cg-progress__runner { position: absolute; top: 50%; display: grid; place-items: center; transform: translate(-50%, -50%); transition: left 300ms linear; animation: cg-runner-bob 900ms var(--xq-ease) infinite alternate; }
.cg-progress__meta { display: flex; flex-wrap: wrap; align-items: center; gap: var(--xq-space-3); margin: 0; padding: 0; list-style: none; color: var(--xq-text-muted); font-size: var(--xq-text-xs); font-variant-numeric: tabular-nums; }
.cg-progress__meta li { display: inline-flex; align-items: center; gap: var(--xq-space-3); }
.cg-progress__meta li:first-child { color: var(--xq-text); font-weight: var(--xq-weight-semibold); }
.cg-progress__meta li + li::before { content: "·"; color: var(--xq-text-faint); }

/* ---------- 正文实时流：页面最大的阅读块 ---------- */
.cg-draft { display: flex; flex-direction: column; gap: var(--xq-space-3); padding: var(--xq-space-5); border: 1px solid var(--xq-border); border-radius: var(--xq-radius-lg); background: var(--xq-surface); box-shadow: var(--xq-shadow-xs); }
.cg-draft__head { display: flex; align-items: baseline; justify-content: space-between; gap: var(--xq-space-3); }
.cg-draft__title { margin: 0; color: var(--xq-text); font-size: var(--xq-text-sm); font-weight: var(--xq-weight-semibold); }
.cg-draft__count { color: var(--xq-text-muted); font-size: var(--xq-text-2xs); font-variant-numeric: tabular-nums; }
.cg-live-preview { margin: 0; max-width: var(--xq-reading-max); max-height: clamp(280px, 46vh, 620px); overflow: auto; color: var(--xq-text-body); font-family: var(--xq-font-serif); font-size: var(--xq-text-md); line-height: var(--xq-leading-relaxed); white-space: pre-wrap; word-break: break-word; }
.cg-draft__empty { margin: 0; color: var(--xq-text-faint); font-size: var(--xq-text-sm); }
/* ---------- 次区：按钮严格三级，统一 32px 高 ---------- */
.cg-actions { display: flex; flex-wrap: wrap; align-items: center; gap: var(--xq-space-2); }
.cg-btn { display: inline-flex; align-items: center; justify-content: center; gap: var(--xq-space-2); height: 32px; padding: 0 var(--xq-space-4); border: 1px solid var(--xq-border); border-radius: var(--xq-radius-md); background: var(--xq-surface); color: var(--xq-text-body); font-family: inherit; font-size: var(--xq-text-sm); font-weight: var(--xq-weight-medium); cursor: pointer; transition: background var(--xq-fast), border-color var(--xq-fast), color var(--xq-fast); }
.cg-btn:hover { background: var(--xq-surface-hover); }
.cg-btn:focus-visible { outline: none; box-shadow: var(--xq-ring); }
.cg-btn:disabled { cursor: not-allowed; opacity: 0.55; }
.cg-btn__icon { flex: 0 0 auto; width: 14px; height: 14px; }
.cg-btn--primary { border-color: var(--xq-accent); background: var(--xq-accent); color: var(--xq-text-inverse); }
.cg-btn--primary:hover { border-color: var(--xq-accent-hover); background: var(--xq-accent-hover); }
.cg-btn--weak { border-color: transparent; background: transparent; color: var(--xq-danger-text); }
.cg-btn--weak:hover { background: var(--xq-danger-soft); }
.cg-btn--weak:focus-visible { box-shadow: var(--xq-ring-danger); }

/* ---------- 折叠区 ---------- */
.cg-advanced { border: 1px solid var(--xq-border); border-radius: var(--xq-radius-lg); background: var(--xq-surface); }
.cg-advanced__toggle { display: flex; width: 100%; align-items: center; gap: var(--xq-space-3); padding: var(--xq-space-3) var(--xq-space-5); border: 0; border-radius: var(--xq-radius-lg); background: transparent; color: var(--xq-text-body); font-family: inherit; font-size: var(--xq-text-sm); font-weight: var(--xq-weight-medium); text-align: left; cursor: pointer; transition: background var(--xq-fast); }
.cg-advanced__toggle:hover { background: var(--xq-surface-2); }
.cg-advanced__toggle:focus-visible { outline: none; box-shadow: var(--xq-ring); }
.cg-advanced__label { color: var(--xq-text); }
.cg-advanced__count { display: inline-flex; align-items: center; height: 18px; padding: 0 var(--xq-space-2); border: 1px solid var(--xq-info-border); border-radius: var(--xq-radius-pill); background: var(--xq-info-soft); color: var(--xq-info-text); font-size: var(--xq-text-2xs); font-variant-numeric: tabular-nums; }
.cg-advanced__count--warning { border-color: var(--xq-warning-border); background: var(--xq-warning-soft); color: var(--xq-warning-text); }
.cg-advanced__count--danger { border-color: var(--xq-danger-border); background: var(--xq-danger-soft); color: var(--xq-danger-text); }
.cg-advanced__hint { margin-left: auto; color: var(--xq-text-faint); font-size: var(--xq-text-2xs); }
.cg-advanced__chevron { width: 14px; height: 14px; color: var(--xq-text-faint); transition: transform var(--xq-normal); }
.cg-advanced__chevron.is-open { transform: rotate(180deg); }
.cg-advanced__body { display: flex; flex-direction: column; gap: var(--xq-space-6); padding: var(--xq-space-5); border-top: 1px solid var(--xq-border-soft); }
.cg-advanced__foot { margin: 0; color: var(--xq-text-faint); font-size: var(--xq-text-2xs); line-height: var(--xq-leading-normal); }

/* ---------- 折叠区内部分组 ---------- */
.cg-group { display: flex; flex-direction: column; gap: var(--xq-space-3); }
.cg-group__head { display: flex; align-items: center; justify-content: space-between; gap: var(--xq-space-3); }
.cg-group__title { margin: 0; color: var(--xq-text-muted); font-size: var(--xq-text-2xs); font-weight: var(--xq-weight-semibold); letter-spacing: 0.06em; }
/* ---------- 统一 Alert 形态：soft 底 + 3px 左侧语义色条 ---------- */
.cg-alerts { display: flex; flex-direction: column; gap: var(--xq-space-2); }
.cg-alert { display: flex; flex-direction: column; gap: var(--xq-space-2); padding: var(--xq-space-3) var(--xq-space-4); border-left: 3px solid var(--xq-info); border-radius: var(--xq-radius-sm); background: var(--xq-info-soft); }
.cg-alert--warning { border-left-color: var(--xq-warning); background: var(--xq-warning-soft); }
.cg-alert--danger { border-left-color: var(--xq-danger); background: var(--xq-danger-soft); }
.cg-alert__title { margin: 0; color: var(--xq-text); font-size: var(--xq-text-sm); font-weight: var(--xq-weight-semibold); }
.cg-alert__desc { margin: 0; color: var(--xq-text-muted); font-size: var(--xq-text-xs); line-height: var(--xq-leading-normal); }
.cg-alert__rows { display: flex; flex-direction: column; gap: var(--xq-space-1); margin: 0; padding: 0; list-style: none; }
.cg-alert__rows li { display: flex; align-items: flex-start; gap: var(--xq-space-2); color: var(--xq-text-body); font-size: var(--xq-text-xs); line-height: var(--xq-leading-normal); }
.cg-alert__dot { flex: 0 0 auto; width: 8px; height: 8px; margin-top: var(--xq-space-1); border-radius: var(--xq-radius-pill); background: var(--xq-info); }
.cg-alert__dot--warning { background: var(--xq-warning); }
.cg-alert__dot--danger { background: var(--xq-danger); }
.cg-alert__tags { display: flex; flex-wrap: wrap; gap: var(--xq-space-2); margin: 0; padding: 0; list-style: none; }
.cg-alert__tags li { display: inline-flex; align-items: center; height: 20px; padding: 0 var(--xq-space-2); border: 1px solid var(--xq-border); border-radius: var(--xq-radius-pill); background: var(--xq-surface); color: var(--xq-text-muted); font-size: var(--xq-text-2xs); }

/* ---------- 任务详情：两列定义列表，label 在上 value 在下 ---------- */
.cg-defs { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--xq-space-3) var(--xq-space-5); margin: 0; }
.cg-defs__item { display: flex; flex-direction: column; gap: var(--xq-space-1); min-width: 0; }
.cg-defs__label { display: flex; align-items: baseline; color: var(--xq-text-muted); font-size: var(--xq-text-2xs); white-space: nowrap; }
.cg-defs__sep { color: var(--xq-text-faint); }
.cg-defs__value { margin: 0; color: var(--xq-text-body); font-size: var(--xq-text-sm); line-height: var(--xq-leading-snug); font-variant-numeric: tabular-nums; word-break: break-word; }
.cg-plain-list { display: flex; flex-direction: column; gap: var(--xq-space-1); margin: 0; padding: 0; list-style: none; color: var(--xq-text-body); font-size: var(--xq-text-xs); line-height: var(--xq-leading-normal); }
.cg-plain-list li { position: relative; padding-left: var(--xq-space-3); }
.cg-plain-list li::before { content: ""; position: absolute; top: 7px; left: 0; width: 4px; height: 4px; border-radius: var(--xq-radius-pill); background: var(--xq-text-faint); }
/* ---------- 生成日志：分隔线取代卡片，色点取代彩色徽标 ---------- */
.cg-log-toggle { padding: 0; border: 0; background: transparent; color: var(--xq-accent); font-family: inherit; font-size: var(--xq-text-xs); cursor: pointer; }
.cg-log-toggle:hover { color: var(--xq-accent-hover); text-decoration: underline; }
.cg-log-toggle:focus-visible { outline: none; box-shadow: var(--xq-ring); }
.cg-log-tabs { display: flex; flex-wrap: wrap; gap: var(--xq-space-1); border-bottom: 1px solid var(--xq-border); }
.cg-log-tab { padding: var(--xq-space-2) var(--xq-space-3); border: 0; border-bottom: 2px solid transparent; background: transparent; color: var(--xq-text-muted); font-family: inherit; font-size: var(--xq-text-xs); cursor: pointer; transition: color var(--xq-fast), border-color var(--xq-fast); }
.cg-log-tab:hover { color: var(--xq-text-body); }
.cg-log-tab.is-active { border-bottom-color: var(--xq-accent); color: var(--xq-accent-text); font-weight: var(--xq-weight-medium); }
.cg-log-list { display: flex; flex-direction: column; margin: 0; padding: 0; list-style: none; }
.cg-log-item { display: flex; flex-direction: column; gap: var(--xq-space-2); padding: var(--xq-space-3) 0; border-top: 1px solid var(--xq-border-soft); }
.cg-log-item:first-child { border-top: 0; padding-top: 0; }
.cg-log-item__head { display: flex; flex-wrap: wrap; align-items: center; gap: var(--xq-space-2); }
.cg-log-item__level { flex: 0 0 auto; width: 8px; height: 8px; border-radius: var(--xq-radius-pill); background: var(--xq-info); }
.cg-log-item__level--warning { background: var(--xq-warning); }
.cg-log-item__level--error { background: var(--xq-danger); }
.cg-log-item__time { color: var(--xq-text-faint); font-family: var(--xq-font-mono); font-size: var(--xq-text-2xs); font-variant-numeric: tabular-nums; }
.cg-log-item__tag { color: var(--xq-text-muted); font-size: var(--xq-text-2xs); }
.cg-log-item__duration { margin-left: auto; color: var(--xq-text-faint); font-family: var(--xq-font-mono); font-size: var(--xq-text-2xs); font-variant-numeric: tabular-nums; }
.cg-log-item__title { margin: 0; color: var(--xq-text); font-size: var(--xq-text-sm); font-weight: var(--xq-weight-medium); }
.cg-log-item__message { margin: 0; color: var(--xq-text-body); font-size: var(--xq-text-xs); line-height: var(--xq-leading-normal); }
.cg-log-item__notice { margin: 0; padding: var(--xq-space-2) var(--xq-space-3); border-left: 3px solid var(--xq-warning); border-radius: var(--xq-radius-sm); background: var(--xq-warning-soft); color: var(--xq-text-body); font-size: var(--xq-text-xs); line-height: var(--xq-leading-normal); }
.cg-log-item__preview { margin: 0; max-height: 200px; overflow: auto; padding: var(--xq-space-3); border-radius: var(--xq-radius-sm); background: var(--xq-surface-2); color: var(--xq-text-muted); font-family: var(--xq-font-mono); font-size: var(--xq-text-xs); line-height: var(--xq-leading-normal); white-space: pre-wrap; word-break: break-word; }
/* @@STYLE_NEXT@@ */
</style>
