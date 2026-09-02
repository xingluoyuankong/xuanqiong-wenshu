<script setup lang="ts">
import { computed } from 'vue'
import type { AgentExecutionFact, AgentProviderAttemptSnapshot, AgentProviderProvenance, AgentRun, AgentRunCommandType, AgentRunStep, AgentStateProjection, AgentToolResult } from '@/api/agent'
import type { SSEConnectionState } from '@/utils/sseStream'
import AgentRunControlBar from '@/features/agent/AgentRunControlBar.vue'
import AgentRunCommandHistory from '@/features/agent/AgentRunCommandHistory.vue'
import AgentToolResultPanel from '@/features/agent/AgentToolResultPanel.vue'
import { XqButton, XqPanel } from '@/shared/ui'

const props = withDefaults(defineProps<{
  run: AgentRun | null
  state: AgentStateProjection | null
  steps: AgentRunStep[]
  toolResults: AgentToolResult[]
  executionFacts?: AgentExecutionFact[]
  executionFactsError?: string | null
  provenance?: AgentProviderProvenance | null
  hasSequenceGap?: boolean
  gapRepairState?: 'idle' | 'repairing' | 'repaired' | 'failed'
  connectionState: SSEConnectionState
  controlPending?: boolean
  progressMessage?: string | null
  selectedActionRef?: string | null
  selectedResultRef?: string | null
}>(), {
  selectedActionRef: null,
  selectedResultRef: null,
  executionFacts: () => [],
  executionFactsError: null,
})

const emit = defineEmits<{
  command: [command: AgentRunCommandType]
  recover: []
  reconnect: []
}>()

const runStatus = (status?: string | null) => ({
  completed: '已完成', failed: '失败', cancelled: '已取消', paused: '已暂停',
  cancelling: '正在取消', running: '正在执行', planning: '正在规划', awaiting_approval: '等待审批',
})[status || ''] || status || 'idle'
const stepStatus = (status: string) => ({
  pending: '等待执行', running: '正在执行', completed: '已完成', failed: '执行失败',
  cancelled: '已取消', awaiting_approval: '等待审批',
})[status] || status
const stepErrorLabel = (error: string) => error === 'LeaseExpiredRecovery' ? '执行器失联，已释放为可恢复步骤' : error
const gapStatus = (state?: 'idle' | 'repairing' | 'repaired' | 'failed') => ({
  repairing: '正在补齐事件账本',
  repaired: '事件账本已补齐',
  failed: '事件账本仍有缺口，请重新连接',
  idle: '检测到事件账本缺口',
})[state || 'idle']
const providerStatus = (called?: boolean | null, fallback?: string | null) =>
  called === true
    ? '已调用 Provider'
    : fallback
      ? `已降级：${fallback}`
      : called === false
        ? '未调用 Provider'
        : '尚无运行事实'
const refId = (value: string | null | undefined, prefix: string) =>
  value?.startsWith(prefix) ? value.slice(prefix.length) : ''
const selectedStep = computed(() => {
  const actionStepId = refId(props.selectedActionRef, 'step:')
  const resultStepId = refId(props.selectedResultRef, 'step:')
  const executionId = refId(props.selectedResultRef, 'execution:')
  return props.steps.find((step) =>
    (actionStepId && step.id === actionStepId) ||
    (resultStepId && step.id === resultStepId) ||
    (executionId && String(step.output_json?.execution_id || '') === executionId),
  ) || null
})
const hasSelectedResult = computed(() =>
  Boolean(props.selectedResultRef && props.toolResults.some((item) => item.result_ref === props.selectedResultRef)),
)
const selectedExecutionFact = computed(() => props.executionFacts.find((fact) =>
  fact.result_ref === props.selectedResultRef || fact.action_id === props.selectedActionRef
) || null)
const selectedLocation = computed(() => props.selectedResultRef || props.selectedActionRef || null)
const locationStatus = computed(() => {
  if (!selectedLocation.value) return 'none'
  if (selectedStep.value || hasSelectedResult.value || selectedExecutionFact.value) return 'located'
  return 'stale'
})

const providerOutcome = (called?: boolean | null, snapshot?: AgentProviderAttemptSnapshot | null) => {
  const attempts = snapshot?.provider_attempts || []
  if (attempts.some((item) => item.status === 'failed')) return '本次调用失败'
  if (attempts.some((item) => item.status === 'succeeded')) return '本次调用成功'
  if (called === false) return '本次未调用'
  if (called === true) return '本次调用进行中'
  return '本次状态未知'
}
const providerAttemptSummary = (snapshot?: AgentProviderAttemptSnapshot | null) => {
  const attempts = snapshot?.provider_attempts || []
  if (!attempts.length) return ''
  const last = attempts[attempts.length - 1] || {}
  const selected = snapshot?.selected_provider_attempt
  const parts = [`${attempts.length} 次调用`]
  if (typeof selected === 'number') parts.push(`已选 #${selected}`)
  if (snapshot?.fallback_used) parts.push('含 fallback')
  const errorCategory = typeof last.error_category === 'string' ? last.error_category : ''
  if (last.status === 'failed' && errorCategory) parts.push(`最后失败：${errorCategory}`)
  return parts.join(' · ')
}
</script>

<template>
  <section class="agent-run-inspector" data-testid="agent-run-inspector" aria-label="Agent运行检查器">
    <XqPanel title="当前运行">
      <p v-if="executionFactsError" class="execution-facts-error error" data-testid="agent-execution-facts-error">{{ executionFactsError }}</p>
      <p class="selected-location" data-testid="agent-selected-location">
        <template v-if="locationStatus === 'located'">已定位：{{ selectedLocation }}</template>
        <template v-else-if="locationStatus === 'stale'">引用暂不可用：{{ selectedLocation }}（正在恢复执行事实）</template>
        <template v-else>尚未定位动作或结果</template>
      </p>
      <div v-if="selectedResultRef && (selectedStep || selectedExecutionFact)" class="execution-fact" data-testid="agent-execution-fact">
        <strong>执行事实</strong>
        <span>{{ selectedExecutionFact?.tool_name || selectedStep?.tool_name }} · {{ stepStatus(selectedExecutionFact?.status || selectedStep?.status || '') }} · 第 {{ selectedExecutionFact?.attempt || selectedStep?.attempt_count }} 次</span>
        <small>{{ selectedExecutionFact?.result_ref || selectedResultRef }}</small>
        <small v-if="selectedExecutionFact?.started_at || selectedExecutionFact?.finished_at || selectedStep?.started_at || selectedStep?.finished_at">{{ selectedExecutionFact?.started_at || selectedStep?.started_at || '—' }} → {{ selectedExecutionFact?.finished_at || selectedStep?.finished_at || '进行中' }}</small>
      </div>
      <dl class="run-summary">
        <dt>状态</dt><dd data-testid="agent-run-status">{{ run?.status || 'idle' }}</dd>
        <dt v-if="state">关联</dt><dd v-if="state" data-testid="agent-correlation-id">{{ state.correlation_id.slice(0, 8) }}</dd>
        <dt v-if="state?.capability_snapshot">能力目录</dt>
        <dd v-if="state?.capability_snapshot" data-testid="agent-capability-generation">第 {{ state.capability_snapshot.generation }} 代 · {{ state.capability_snapshot.tools.length }} 项</dd>
        <dt>阶段</dt><dd>{{ run?.current_phase || '等待指令' }}</dd>
        <dt>进度</dt><dd data-testid="agent-run-progress">{{ run ? Math.round(run.progress) + '%' : '—' }}</dd>
        <dt v-if="progressMessage">动态</dt><dd v-if="progressMessage" data-testid="agent-run-progress-message" aria-live="polite">{{ progressMessage }}</dd>
        <dt>步骤</dt><dd>{{ run ? run.current_step : '—' }}</dd>
        <template v-if="hasSequenceGap || gapRepairState === 'repairing' || gapRepairState === 'failed'">
          <dt>事件账本</dt><dd data-testid="agent-sequence-gap-status">{{ gapStatus(gapRepairState) }}</dd>
        </template>
        <template v-if="provenance">
          <dt>规划 Provider</dt><dd data-testid="agent-planner-provider-provenance">{{ providerStatus(provenance.planner_provider_called, provenance.planner_provider_fallback_reason) }}<span class="provider-outcome" data-testid="agent-planner-provider-outcome">{{ providerOutcome(provenance.planner_provider_called, provenance.planner_provider_attempts) }}</span><span v-if="providerAttemptSummary(provenance.planner_provider_attempts)" class="provider-attempt-summary" data-testid="agent-planner-provider-attempts">{{ providerAttemptSummary(provenance.planner_provider_attempts) }}</span></dd>
          <dt>回复 Provider</dt><dd data-testid="agent-response-provider-provenance">{{ providerStatus(provenance.response_provider_called, provenance.response_provider_fallback_reason) }}<span class="provider-outcome" data-testid="agent-response-provider-outcome">{{ providerOutcome(provenance.response_provider_called, provenance.response_provider_attempts) }}</span><span v-if="providerAttemptSummary(provenance.response_provider_attempts)" class="provider-attempt-summary" data-testid="agent-response-provider-attempts">{{ providerAttemptSummary(provenance.response_provider_attempts) }}</span></dd>
          <dt>候选正文 Provider</dt><dd data-testid="agent-candidate-writer-provider-provenance">{{ providerStatus(provenance.candidate_writer_provider_called, provenance.candidate_writer_provider_fallback_reason) }}<span class="provider-outcome" data-testid="agent-candidate-writer-provider-outcome">{{ providerOutcome(provenance.candidate_writer_provider_called, provenance.candidate_writer_provider_attempts) }}</span><span v-if="provenance.candidate_writer_model_ref" class="provider-model-ref">{{ provenance.candidate_writer_model_ref }}</span><span v-if="providerAttemptSummary(provenance.candidate_writer_provider_attempts)" class="provider-attempt-summary" data-testid="agent-candidate-writer-provider-attempts">{{ providerAttemptSummary(provenance.candidate_writer_provider_attempts) }}</span></dd>
        </template>
      </dl>
      <AgentRunControlBar :run="run" :pending="Boolean(run && controlPending)" :allowed-commands="state?.allowed_commands || run?.allowed_commands || []" @command="emit('command', $event)" />
      <AgentRunCommandHistory :commands="state?.commands || []" :run-id="run?.id" />
      <XqButton v-if="run?.status === 'paused' && run?.current_phase === 'recovery_ready'" variant="secondary" size="sm" data-testid="agent-recover-run-button" @click="emit('recover')">恢复运行</XqButton>
      <XqButton v-if="run && connectionState === 'disconnected'" variant="secondary" size="sm" data-testid="agent-reconnect-stream-button" @click="emit('reconnect')">重新连接</XqButton>
    </XqPanel>
    <AgentToolResultPanel v-if="run" :results="toolResults" :selected-result-ref="selectedResultRef" title="当前运行工具结果" subtitle="由当前 Run 响应或持久化步骤投影；正文、提示词与密钥不会回显。" />
    <XqPanel v-if="steps.length" title="执行检查点" subtitle="持久化步骤状态与恢复依据。" data-testid="agent-step-panel">
      <ol class="step-list"><li v-for="step in steps" :key="step.id" :class="{ 'step-list__item--selected': selectedStep?.id === step.id }" :data-testid="`agent-step-${step.id}`" :data-location-ref="`step:${step.id}`" :data-result-ref="typeof step.output_json.execution_id === 'string' ? `execution:${step.output_json.execution_id}` : undefined"><b>{{ step.step_order }}. {{ step.tool_name }}</b><span>{{ stepStatus(step.status) }} · 第 {{ step.attempt_count }} 次</span><small v-if="selectedStep?.id === step.id" class="step-list__selection">已定位到此动作</small><small v-if="step.lease_owner">当前执行器：{{ step.lease_owner }}</small><small v-if="step.error_type" :class="{ error: step.status === 'failed' }">{{ stepErrorLabel(step.error_type) }}</small><small v-else-if="step.status === 'completed' && Object.keys(step.output_json).length">已复用/保存结果</small></li></ol>
    </XqPanel>
  </section>
</template>

<style scoped>
.selected-location {
  margin: 0 0 0.65rem;
  padding: 0.45rem 0.55rem;
  border: 1px solid color-mix(in srgb, var(--xq-gold-deep) 45%, var(--xq-border));
  border-radius: 0.5rem;
  color: var(--xq-gold-deep);
  background: rgba(214, 169, 74, 0.08);
  font-size: 0.78rem;
  line-height: 1.45;
}
.execution-fact {
  display: grid;
  gap: .16rem;
  margin: 0 0 .65rem;
  padding: .45rem .55rem;
  border-radius: .5rem;
  background: rgba(61, 143, 125, .08);
  color: var(--xq-ink);
  font-size: .76rem;
  line-height: 1.4;
}
.execution-fact span,
.execution-fact small { color: var(--xq-ink-muted); }
.run-summary { display: grid; grid-template-columns: auto 1fr; gap: .45rem .75rem; margin: 0; }
.run-summary dt { color: var(--xq-ink-muted); }
.run-summary dd { min-width: 0; margin: 0; overflow-wrap: anywhere; font-weight: 700; }
.provider-model-ref, .provider-attempt-summary, .provider-outcome { display: block; margin-top: .16rem; color: var(--xq-ink-muted); font-size: .78rem; font-weight: 600; line-height: 1.42; }
.step-list { display: grid; gap: .55rem; margin: 0; padding-left: 1.2rem; }
.step-list li { display: grid; gap: .15rem; padding: .3rem .35rem; border: 1px solid transparent; border-radius: .45rem; }
.step-list li.step-list__item--selected { border-color: var(--xq-gold-deep); background: rgba(214, 169, 74, 0.1); box-shadow: 0 0 0 2px rgba(214, 169, 74, 0.14); }
.step-list__selection { color: var(--xq-gold-deep) !important; font-weight: 800; }
.step-list span, .step-list small { color: var(--xq-ink-muted); }
.error { color: var(--xq-cinnabar); }
</style>


