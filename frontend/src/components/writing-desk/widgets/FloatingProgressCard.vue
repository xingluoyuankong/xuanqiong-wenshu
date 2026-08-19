<template>
  <Transition name="float-card">
    <aside
      v-if="visible"
      class="floating-progress-card"
      :class="statusToneClass"
      role="status"
      aria-live="polite"
    >
      <header class="floating-progress-card__header">
        <div class="floating-progress-card__heading">
          <strong class="floating-progress-card__title">{{ titleText }}</strong>
          <span class="floating-progress-card__stage">{{ stageLabel }}</span>
        </div>
        <button
          type="button"
          class="floating-progress-card__close"
          :aria-label="closeLabel"
          :title="closeLabel"
          @click="$emit('close')"
        >×</button>
      </header>

      <div class="floating-progress-card__meter">
        <div
          class="floating-progress-card__track"
          role="progressbar"
          :aria-label="progressLabel"
          :aria-valuenow="displayPercent"
          aria-valuemin="0"
          aria-valuemax="100"
        >
          <div class="floating-progress-card__bar" :class="barClass" :style="barStyle"></div>
          <span class="floating-progress-card__mascot" :style="mascotStyle">
            <PixelMascot :mascot-id="mascotId" :color="mascotColor" :size="26" :moving="isRunning" />
          </span>
        </div>
        <strong class="floating-progress-card__percent">{{ displayPercent }}%</strong>
      </div>

      <p v-if="metaLine" class="floating-progress-card__meta">{{ metaLine }}</p>
      <p v-if="funMessage" class="floating-progress-card__fun">{{ funMessage }}</p>
      <p v-if="detailText" class="floating-progress-card__detail">{{ detailText }}</p>
    </aside>
  </Transition>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

import PixelMascot from '@/components/shared/PixelMascot.vue'
import { useLocale } from '@/composables/useLocale'
import { usePixelMascot } from '@/composables/usePixelMascot'
import { useSmoothProgress } from '@/composables/useSmoothProgress'
import { normalizeRuntimeStage } from '@/utils/chapterGeneration'

const props = defineProps<{
  visible: boolean
  title?: string
  stage?: string
  progressPercent?: number
  wordCount?: number
  status?: string
  detailMessage?: string
  taskId?: string | null
  taskStatus?: string | null
  retryCount?: number | null
  taskRecovered?: boolean
}>()

defineEmits<{
  close: []
}>()

const { pick } = useLocale()
const { mascotId, color: mascotColor, beginRun, endRun } = usePixelMascot()

const statusTone = computed(() => {
  if (props.status === 'successful') return 'success'
  if (props.status === 'failed' || props.status === 'evaluation_failed') return 'error'
  if (props.status === 'generating' || props.status === 'evaluating') return 'active'
  return 'neutral'
})

const isComplete = computed(() => statusTone.value === 'success')
const isError = computed(() => statusTone.value === 'error')
const isRunning = computed(() => !isComplete.value && !isError.value)

// 后端按阶段跳变上报，这里换成按时间均匀插值的百分比。
const { percent: displayPercent } = useSmoothProgress({
  stage: () => props.stage,
  status: () => props.status,
  rawPercent: () => props.progressPercent,
  active: () => props.visible,
  taskId: () => props.taskId,
})

const statusToneClass = computed(() => `floating-progress-card--${statusTone.value}`)
const barClass = computed(() => `floating-progress-card__bar--${statusTone.value}`)
const barStyle = computed(() => ({ width: `${Math.max(displayPercent.value, 2)}%` }))
const mascotStyle = computed(() => ({ left: `${displayPercent.value}%` }))

/** 卡片可见且任务仍在推进时，吉祥物才动；进入该状态随机换一种可爱姿态 */
const mascotAdvancing = computed(() => props.visible && isRunning.value)
let mascotCounted = false

watch(
  mascotAdvancing,
  (advancing) => {
    if (advancing && !mascotCounted) {
      mascotCounted = true
      beginRun()
    } else if (!advancing && mascotCounted) {
      mascotCounted = false
      endRun()
    }
  },
  { immediate: true },
)

const titleText = computed(() => props.title || pick('生成进度', 'Generation progress'))
const closeLabel = computed(() => pick('关闭进度卡片', 'Close progress card'))
const detailText = computed(() => (isRunning.value ? String(props.detailMessage || '').trim() : ''))

const progressLabel = computed(() => {
  if (isComplete.value) return pick('生成完成', 'Generation complete')
  if (isError.value) return pick('生成遇到问题', 'Generation needs attention')
  return pick('生成进度', 'Generation progress')
})
const taskStatusLabel = computed<string>(() => {
  const labels: Record<string, string> = {
    queued: pick('已排队', 'Queued'),
    running: pick('运行中', 'Running'),
    cancelling: pick('取消中', 'Cancelling'),
    cancelled: pick('已取消', 'Cancelled'),
    succeeded: pick('已完成', 'Completed'),
    failed: pick('失败', 'Failed'),
    stale: pick('已中断', 'Stale'),
  }
  const status = String(props.taskStatus || '').trim()
  return labels[status] || status
})

const stageLabel = computed<string>(() => {
  const labels: Record<string, string> = {
    queued: pick('排队等候', 'Queued'),
    prepare_context: pick('整理上下文', 'Preparing context'),
    audit_context: pick('审计长期记忆', 'Auditing memory'),
    cast_plan: pick('装配角色阵容', 'Planning cast'),
    foreshadowing_plan: pick('规划伏笔回收', 'Planning foreshadowing'),
    foreshadowing_chapter_task: pick('检测伏笔线索', 'Checking clues'),
    longform_context: pick('装配长篇上下文', 'Preparing long-form context'),
    enhanced_context: pick('装配增强约束', 'Preparing constraints'),
    generate_mission: pick('编写导演脚本', 'Building writing plan'),
    generate_variants: pick('正在生成正文', 'Writing draft'),
    generate_variants_candidate: pick('生成候选稿', 'Generating candidate'),
    multi_round_continuation: pick('多轮续写', 'Continuing draft'),
    ai_review: pick('正在评审', 'Reviewing draft'),
    review: pick('正在评审', 'Reviewing draft'),
    reader_simulation: pick('读者视角模拟', 'Simulating reader'),
    reader_simulator: pick('读者模拟中', 'Simulating reader'),
    diagnose_once: pick('单次诊断', 'Running diagnosis'),
    diagnose_previous_chapter: pick('回溯前章', 'Reviewing previous chapter'),
    diagnose_context_bundle: pick('汇总上下文', 'Collecting context'),
    diagnose_structural: pick('结构诊断', 'Structural diagnosis'),
    diagnose_character: pick('角色诊断', 'Character diagnosis'),
    diagnose_delivery: pick('表达诊断', 'Delivery diagnosis'),
    diagnose_continuity: pick('连续性诊断', 'Continuity diagnosis'),
    optimize_content: pick('正在优化', 'Optimizing'),
    optimize_structural: pick('结构优化', 'Optimizing structure'),
    optimize_character: pick('角色优化', 'Optimizing characters'),
    optimize_delivery: pick('表达优化', 'Optimizing delivery'),
    enrichment: pick('字数扩写', 'Enriching draft'),
    consistency: pick('一致性检查', 'Checking consistency'),
    continuity_gate: pick('连续性校验', 'Checking continuity'),
    persist_versions: pick('保存版本', 'Saving versions'),
    finalize: pick('定稿快照', 'Finalizing'),
    ledger_memory: pick('记忆层更新', 'Updating memory'),
    ledger_foreshadowing: pick('伏笔闭环', 'Closing foreshadowing'),
    ledger_graph: pick('线索图谱同步', 'Syncing knowledge graph'),
    finalized: pick('定稿完成', 'Finalized'),
    generating: pick('正在生成', 'Generating'),
    evaluating: pick('正在评审', 'Evaluating'),
    selecting: pick('等待选择', 'Waiting for selection'),
    waiting_for_confirm: pick('等待确认', 'Waiting for confirmation'),
    successful: pick('已完成', 'Completed'),
    ready: pick('已就绪', 'Ready'),
    failed: pick('生成失败', 'Generation failed'),
    evaluation_failed: pick('评审未通过', 'Review failed'),
  }
  const raw = String(props.stage || props.status || '').trim().toLowerCase()
  if (!raw) return pick('处理中', 'Working')
  return labels[raw] || labels[normalizeRuntimeStage(raw)] || pick('处理中', 'Working')
})
// 字数、任务号、任务状态、重试次数合并成一行，避免卡片被碎片信息撑开。
const metaLine = computed<string>(() => {
  const parts: string[] = []
  const words = props.wordCount ?? 0
  if (words > 0) parts.push(`${words.toLocaleString()} ${pick('字', 'chars')}`)
  if (props.taskId) parts.push(`${pick('任务', 'Task')} ${props.taskId.slice(0, 8)}`)
  if (taskStatusLabel.value) parts.push(taskStatusLabel.value)
  if (typeof props.retryCount === 'number' && props.retryCount > 0) {
    parts.push(`${pick('重试', 'Retries')} ${props.retryCount}`)
  }
  if (props.taskRecovered) parts.push(pick('已恢复', 'Recovered'))
  return parts.join(' · ')
})

const FUN_MESSAGES: ReadonlyArray<readonly [string, string]> = [
  ['奋笔疾书中', 'Writing at full speed'],
  ['文思泉涌', 'Ideas are flowing'],
  ['正在埋伏笔', 'Planting a hint'],
  ['角色自己演起来了', 'Characters take over'],
  ['冲突升温中', 'Tension is rising'],
  ['反转正在酝酿', 'A twist is brewing'],
  ['线索开始收束', 'Threads converging'],
  ['画面逐渐清晰', 'The scene comes into focus'],
]

const messageIndex = ref(0)
let messageTimer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  messageTimer = setInterval(() => {
    messageIndex.value = (messageIndex.value + 1) % FUN_MESSAGES.length
  }, 3600)
})

onUnmounted(() => {
  if (messageTimer) clearInterval(messageTimer)
  messageTimer = null
  if (mascotCounted) {
    mascotCounted = false
    endRun()
  }
})

const funMessage = computed(() => {
  if (!isRunning.value) return ''
  const message = FUN_MESSAGES[messageIndex.value] || FUN_MESSAGES[0]
  return pick(message[0], message[1])
})
</script>

<style scoped>
/* 整块重写：一个选择器只出现一次，不再靠尾部追加规则互相覆盖。 */
.floating-progress-card {
  position: fixed;
  top: var(--xq-space-4);
  right: var(--xq-space-4);
  z-index: 1000;
  display: flex;
  flex-direction: column;
  gap: var(--xq-space-3);
  width: min(320px, calc(100vw - var(--xq-space-8)));
  padding: var(--xq-space-4);
  border: 1px solid var(--xq-border);
  border-left: 3px solid var(--xq-border-strong);
  border-radius: var(--xq-radius-lg);
  background: var(--xq-surface);
  box-shadow: var(--xq-shadow-lg);
  color: var(--xq-text-body);
  font-family: var(--xq-font-sans);
}

/* 状态只用左侧 3px 语义色条区分，整卡保持白底。 */
.floating-progress-card--active {
  border-left-color: var(--xq-accent);
}

.floating-progress-card--success {
  border-left-color: var(--xq-success);
}

.floating-progress-card--error {
  border-left-color: var(--xq-danger);
}

.floating-progress-card--neutral {
  border-left-color: var(--xq-border-strong);
}

.floating-progress-card__header {
  display: flex;
  align-items: flex-start;
  gap: var(--xq-space-2);
}

.floating-progress-card__heading {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  gap: var(--xq-space-1);
}
.floating-progress-card__title {
  overflow: hidden;
  color: var(--xq-text);
  font-size: var(--xq-text-base);
  font-weight: var(--xq-weight-semibold);
  line-height: var(--xq-leading-tight);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.floating-progress-card__stage {
  overflow: hidden;
  color: var(--xq-text-muted);
  font-size: var(--xq-text-xs);
  line-height: var(--xq-leading-tight);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.floating-progress-card__close {
  display: inline-flex;
  width: 28px;
  height: 28px;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: none;
  border-radius: var(--xq-radius-sm);
  background: transparent;
  color: var(--xq-text-faint);
  font-size: var(--xq-text-md);
  line-height: 1;
  cursor: pointer;
  transition: background-color var(--xq-fast), color var(--xq-fast);
}

.floating-progress-card__close:hover {
  background: var(--xq-surface-hover);
  color: var(--xq-text-body);
}

.floating-progress-card__close:focus-visible {
  outline: none;
  box-shadow: var(--xq-ring);
}

.floating-progress-card__meter {
  display: flex;
  align-items: center;
  gap: var(--xq-space-3);
}
.floating-progress-card__track {
  position: relative;
  height: 10px;
  min-width: 0;
  flex: 1;
  border-radius: var(--xq-radius-pill);
  background: var(--xq-surface-3);
}

.floating-progress-card__bar {
  height: 100%;
  border-radius: inherit;
  /* linear 才是均匀推进，ease 会让每次刷新先快后慢，看起来一顿一顿。 */
  transition: width 300ms linear;
}

.floating-progress-card__bar--active {
  background: var(--xq-accent);
}

.floating-progress-card__bar--success {
  background: var(--xq-success);
}

.floating-progress-card__bar--error {
  background: var(--xq-danger);
}

.floating-progress-card__bar--neutral {
  background: var(--xq-border-strong);
}

/* 吉祥物骑在进度点上，本身就是「还在跑」的指示器，不再另加 spinner。 */
.floating-progress-card__mascot {
  position: absolute;
  top: 50%;
  display: grid;
  place-items: center;
  transform: translate(-50%, -50%);
  transition: left 300ms linear;
  pointer-events: none;
}

.floating-progress-card__percent {
  flex: 0 0 auto;
  color: var(--xq-text);
  font-size: var(--xq-text-base);
  font-weight: var(--xq-weight-bold);
  font-variant-numeric: tabular-nums;
  line-height: 1;
}
.floating-progress-card__meta {
  overflow: hidden;
  margin: 0;
  color: var(--xq-text-faint);
  font-size: var(--xq-text-2xs);
  font-variant-numeric: tabular-nums;
  line-height: var(--xq-leading-snug);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.floating-progress-card__fun {
  overflow: hidden;
  margin: 0;
  color: var(--xq-text-muted);
  font-size: var(--xq-text-2xs);
  font-style: italic;
  line-height: var(--xq-leading-snug);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.floating-progress-card__detail {
  overflow: hidden;
  margin: 0;
  color: var(--xq-text-body);
  font-size: var(--xq-text-xs);
  line-height: var(--xq-leading-snug);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.float-card-enter-active {
  transition: opacity var(--xq-normal), transform var(--xq-normal);
}

.float-card-leave-active {
  transition: opacity var(--xq-fast), transform var(--xq-fast);
}

.float-card-enter-from {
  opacity: 0;
  transform: translateX(var(--xq-space-3));
}

.float-card-leave-to {
  opacity: 0;
  transform: translateX(var(--xq-space-3));
}
</style>

