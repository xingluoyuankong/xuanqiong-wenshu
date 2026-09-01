<script setup lang="ts">
import type { AgentProviderAttemptSnapshot, AgentProviderProvenance, AgentRun, AgentRunCommandType, AgentRunStep, AgentStateProjection, AgentToolResult } from '@/api/agent'
import type { SSEConnectionState } from '@/utils/sseStream'
import AgentRunControlBar from '@/features/agent/AgentRunControlBar.vue'
import AgentRunCommandHistory from '@/features/agent/AgentRunCommandHistory.vue'
import AgentToolResultPanel from '@/features/agent/AgentToolResultPanel.vue'
import { XqButton, XqPanel } from '@/shared/ui'

defineProps<{
  run: AgentRun | null
  state: AgentStateProjection | null
  steps: AgentRunStep[]
  toolResults: AgentToolResult[]
  provenance?: AgentProviderProvenance | null
  hasSequenceGap?: boolean
  gapRepairState?: 'idle' | 'repairing' | 'repaired' | 'failed'
  connectionState: SSEConnectionState
  controlPending?: boolean
  progressMessage?: string | null
}>()

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
          <dt>规划 Provider</dt><dd data-testid="agent-planner-provider-provenance">{{ providerStatus(provenance.planner_provider_called, provenance.planner_provider_fallback_reason) }}<span v-if="providerAttemptSummary(provenance.planner_provider_attempts)" class="provider-attempt-summary" data-testid="agent-planner-provider-attempts">{{ providerAttemptSummary(provenance.planner_provider_attempts) }}</span></dd>
          <dt>回复 Provider</dt><dd data-testid="agent-response-provider-provenance">{{ providerStatus(provenance.response_provider_called, provenance.response_provider_fallback_reason) }}<span v-if="providerAttemptSummary(provenance.response_provider_attempts)" class="provider-attempt-summary" data-testid="agent-response-provider-attempts">{{ providerAttemptSummary(provenance.response_provider_attempts) }}</span></dd>
          <dt>候选正文 Provider</dt><dd data-testid="agent-candidate-writer-provider-provenance">{{ providerStatus(provenance.candidate_writer_provider_called, provenance.candidate_writer_provider_fallback_reason) }}<span v-if="provenance.candidate_writer_model_ref" class="provider-model-ref">{{ provenance.candidate_writer_model_ref }}</span><span v-if="providerAttemptSummary(provenance.candidate_writer_provider_attempts)" class="provider-attempt-summary" data-testid="agent-candidate-writer-provider-attempts">{{ providerAttemptSummary(provenance.candidate_writer_provider_attempts) }}</span></dd>
        </template>
      </dl>
      <AgentRunControlBar :run="run" :pending="Boolean(run && controlPending)" :allowed-commands="state?.allowed_commands || run?.allowed_commands || []" @command="emit('command', $event)" />
      <AgentRunCommandHistory :commands="state?.commands || []" :run-id="run?.id" />
      <XqButton v-if="run?.status === 'paused' && run?.current_phase === 'recovery_ready'" variant="secondary" size="sm" data-testid="agent-recover-run-button" @click="emit('recover')">恢复运行</XqButton>
      <XqButton v-if="run && connectionState === 'disconnected'" variant="secondary" size="sm" data-testid="agent-reconnect-stream-button" @click="emit('reconnect')">重新连接</XqButton>
    </XqPanel>
    <AgentToolResultPanel v-if="run" :results="toolResults" title="当前运行工具结果" subtitle="由当前 Run 响应或持久化步骤投影；正文、提示词与密钥不会回显。" />
    <XqPanel v-if="steps.length" title="执行检查点" subtitle="持久化步骤状态与恢复依据。" data-testid="agent-step-panel">
      <ol class="step-list"><li v-for="step in steps" :key="step.id"><b>{{ step.step_order }}. {{ step.tool_name }}</b><span>{{ stepStatus(step.status) }} · 第 {{ step.attempt_count }} 次</span><small v-if="step.lease_owner">当前执行器：{{ step.lease_owner }}</small><small v-if="step.error_type" :class="{ error: step.status === 'failed' }">{{ stepErrorLabel(step.error_type) }}</small><small v-else-if="step.status === 'completed' && Object.keys(step.output_json).length">已复用/保存结果</small></li></ol>
    </XqPanel>
  </section>
</template>

<style scoped>
.run-summary { display: grid; grid-template-columns: auto 1fr; gap: .45rem .75rem; margin: 0; }
.run-summary dt { color: var(--xq-ink-muted); }
.run-summary dd { min-width: 0; margin: 0; overflow-wrap: anywhere; font-weight: 700; }
.provider-model-ref, .provider-attempt-summary { display: block; margin-top: .16rem; color: var(--xq-ink-muted); font-size: .78rem; font-weight: 600; line-height: 1.42; }
.step-list { display: grid; gap: .55rem; margin: 0; padding-left: 1.2rem; }
.step-list li { display: grid; gap: .15rem; }
.step-list span, .step-list small { color: var(--xq-ink-muted); }
.error { color: var(--xq-cinnabar); }
</style>
