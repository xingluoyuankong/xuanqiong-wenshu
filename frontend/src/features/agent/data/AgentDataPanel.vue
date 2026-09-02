<template>
  <section class="agent-data-panel" data-testid="agent-data-panel">
    <XqPanel
      v-if="isAdmin"
      title="Provider 健康状态"
      subtitle="管理员可见的脱敏注册状态。"
      data-testid="agent-provider-health-panel"
    >
      <p v-if="providerHealthLoading" class="muted">正在读取 Provider 状态…</p>
      <p v-else-if="providerHealthError" class="error">{{ providerHealthError }}</p>
      <template v-else-if="providerHealth">
        <p :class="providerHealth.registry_status === 'healthy' ? 'muted' : 'error'">
          注册表：{{ providerHealth.registry_status }} · {{ providerHealth.provider_count }} 个 Provider
        </p>
        <ul class="tool-list">
          <li v-for="provider in providerHealth.providers" :key="provider.provider_id">
            <strong>{{ provider.provider_id }}</strong>
            <span>{{ provider.status }}</span>
            <small>
              {{ provider.tools.length }} 个工具 · {{ provider.source }}
              <span v-if="provider.provider_version"> · v{{ provider.provider_version }}</span>
              <span v-if="provider.capability_tags?.length"> · {{ provider.capability_tags.join('、') }}</span>
            </small>
          </li>
        </ul>
      </template>
      <p v-else class="muted">暂无 Provider 健康数据。</p>
    </XqPanel>

    <XqPanel title="当前 Run Provider 调用" subtitle="只显示本次运行的脱敏计数，不展示请求或输出正文。" data-testid="agent-provider-usage-panel">
      <p v-if="!activeRunId" class="muted">暂无选中的 Run。</p>
      <p v-else-if="providerUsageSummaryLoading" class="muted">正在读取本次调用统计…</p>
      <p v-else-if="providerUsageSummaryError" class="error">{{ providerUsageSummaryError }}</p>
      <template v-else-if="providerUsageSummary">
        <p class="muted" data-testid="agent-provider-usage-run">Run {{ providerUsageSummary.run_id.slice(0, 8) }}</p>
        <dl class="usage-summary-grid">
          <div><dt>总调用</dt><dd>{{ providerUsageSummary.total_attempts }}</dd></div>
          <div><dt>成功</dt><dd>{{ providerUsageSummary.succeeded_attempts }}</dd></div>
          <div><dt>失败</dt><dd>{{ providerUsageSummary.failed_attempts }}</dd></div>
          <div><dt>fallback</dt><dd>{{ providerUsageSummary.fallback_attempts }}</dd></div>
          <div><dt>首 token</dt><dd>{{ providerUsageSummary.first_token_attempts }}</dd></div>
          <div><dt>输出指纹</dt><dd>{{ providerUsageSummary.digest_attempts }}</dd></div>
          <div><dt>已选 attempt</dt><dd>{{ providerUsageSummary.selected_attempts }}</dd></div>
        </dl>
        <p v-if="providerUsageSummary.last_error_category" class="muted">最近错误：{{ providerUsageSummary.last_error_category }}</p>
        <p v-if="providerUsageSummary.latest_first_token_at" class="muted">最近首 token：{{ providerUsageSummary.latest_first_token_at }}</p>
      </template>
      <p v-else class="muted">本次 Run 暂无 Provider attempt 记录。</p>
    </XqPanel>

    <XqPanel title="项目 Agent 时间线" subtitle="跨会话查看当前项目的可见执行摘要。" data-testid="agent-timeline-panel">
      <div class="timeline-filters">
        <select :value="timelineEventType" aria-label="时间线事件类型" @change="emit('update:timeline-event-type', selectValue($event))">
          <option value="">全部事件</option>
          <option value="tool_call_completed">工具完成</option>
          <option value="tool_call_failed">工具失败</option>
          <option value="approval_granted">审批通过</option>
          <option value="run_completed">运行完成</option>
        </select>
        <select :value="timelineRunStatus" aria-label="时间线运行状态" @change="emit('update:timeline-run-status', selectValue($event))">
          <option value="">全部运行状态</option>
          <option value="completed">已完成</option>
          <option value="failed">失败</option>
          <option value="awaiting_approval">等待审批</option>
        </select>
      </div>
      <p v-if="timelineLoading" class="muted">正在读取跨会话时间线…</p>
      <ol v-else class="timeline-list">
        <li v-for="item in timeline" :key="item.id">
          <strong>{{ eventLabel(item.event_type) }}</strong>
          <span>{{ item.summary }}</span>
          <small>{{ item.tool_name || '项目事件' }} · {{ item.run_status }} · {{ item.session_id.slice(0, 8) }}</small>
        </li>
        <li v-if="!timeline.length" class="muted">暂无符合条件的项目事件。</li>
      </ol>
    </XqPanel>

    <XqPanel title="持久化 Agent Job" subtitle="已接入独立 Worker；未启动时 Job 会保留在队列，重启后可继续领取。" data-testid="agent-job-panel">
      <p v-if="jobsLoading" class="muted">正在读取 Job…</p>
      <ol v-else class="timeline-list">
        <li v-for="job in jobs.slice(0, 12)" :key="job.id">
          <strong>{{ job.kind }} · {{ jobStatusLabel(job.status) }}</strong>
          <span>状态码 {{ job.status }} · attempt {{ job.attempt_count }}/{{ job.max_attempts }} · {{ job.id.slice(0, 8) }}</span>
          <small v-if="job.error_type">{{ job.error_type }}</small>
          <XqButton
            v-if="canCancelJob(job)"
            variant="secondary"
            size="sm"
            @click="emit('cancel-job', job)"
          >请求取消</XqButton>
        </li>
        <li v-if="!jobs.length" class="muted">暂无持久化 Job。</li>
      </ol>
    </XqPanel>

    <XqPanel
      v-if="isAdmin && canListDeadLetters"
      title="死信 Job（管理员）"
      subtitle="只允许管理员重新排队；原失败次数和审计事件保留。"
      data-testid="agent-dead-letter-panel"
    >
      <p v-if="deadLettersLoading" class="muted">正在读取死信 Job…</p>
      <ol v-else class="timeline-list">
        <li v-for="job in deadLetters.slice(0, 12)" :key="job.id">
          <strong>{{ job.kind }} · {{ job.error_type || '需人工复核' }}</strong>
          <span>attempt {{ job.attempt_count }}/{{ job.max_attempts }} · {{ job.id.slice(0, 8) }}</span>
          <small>{{ job.error_detail || '无错误摘要' }}</small>
          <XqButton variant="secondary" size="sm" @click="emit('replay-dead-letter', job)">重新排队</XqButton>
        </li>
        <li v-if="!deadLetters.length" class="muted">暂无死信 Job。</li>
      </ol>
    </XqPanel>

    <XqPanel title="Agent 审计账本" subtitle="把工具、审批、候选和版本关系串成可回溯证据链。" data-testid="agent-audit-panel">
      <p v-if="auditLoading" class="muted">正在读取审计账本…</p>
      <ol v-else class="timeline-list">
        <li v-for="item in auditLedger.slice(0, 12)" :key="item.event_id">
          <strong>{{ eventLabel(item.event_type) }}</strong>
          <span>{{ item.summary }}</span>
          <small>
            {{ item.tool_name || '项目事件' }} ·
            {{ item.artifact_id ? `artifact ${item.artifact_id.slice(0, 8)}` : '无 artifact' }}
            <span v-if="item.source_version_id"> · source v{{ item.source_version_id }}</span>
            <span v-if="item.accepted_version_id"> · accepted v{{ item.accepted_version_id }}</span>
          </small>
        </li>
        <li v-if="!auditLedger.length" class="muted">暂无可回溯审计记录。</li>
      </ol>
    </XqPanel>
  </section>
</template>

<script setup lang="ts">
import type { AgentAuditRecord, AgentJob, AgentProviderUsageSummary, AgentTimelineEvent, AgentToolHealth } from '@/api/agent'
import { agentEventLabel as eventLabel } from '@/features/agent/reducers/agentEventReducer'
import { XqButton, XqPanel } from '@/shared/ui'

withDefaults(defineProps<{
  isAdmin: boolean
  providerHealth: AgentToolHealth | null
  providerHealthLoading: boolean
  providerHealthError: string
  activeRunId: string | null
  providerUsageSummary: AgentProviderUsageSummary | null
  providerUsageSummaryLoading: boolean
  providerUsageSummaryError: string
  timeline: AgentTimelineEvent[]
  timelineLoading: boolean
  timelineEventType: string
  timelineRunStatus: string
  jobs: AgentJob[]
  jobsLoading: boolean
  deadLetters: AgentJob[]
  deadLettersLoading: boolean
  auditLedger: AgentAuditRecord[]
  auditLoading: boolean
  canListDeadLetters: boolean
}>(), {
  isAdmin: false,
  providerHealth: null,
  providerHealthLoading: false,
  providerHealthError: '',
  timeline: () => [],
  timelineLoading: false,
  timelineEventType: '',
  timelineRunStatus: '',
  jobs: () => [],
  jobsLoading: false,
  deadLetters: () => [],
  deadLettersLoading: false,
  auditLedger: () => [],
  auditLoading: false,
  canListDeadLetters: false,
})

const emit = defineEmits<{
  'update:timeline-event-type': [value: string]
  'update:timeline-run-status': [value: string]
  'cancel-job': [job: AgentJob]
  'replay-dead-letter': [job: AgentJob]
}>()

const selectValue = (event: Event) => (event.target as HTMLSelectElement | null)?.value || ''
const jobStatusLabel = (status: string) => ({
  queued: '等待 Worker',
  running: '执行中',
  succeeded: '已完成',
  failed: '执行失败',
  dead_letter: '死信待处理',
  cancel_requested: '取消中',
  cancelled: '已取消',
}[status] || status)
const canCancelJob = (job: AgentJob) => !['succeeded', 'failed', 'cancelled', 'dead_letter'].includes(job.status)
</script>

<style scoped>
.usage-summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.4rem;
  margin: 0.55rem 0;
}
.usage-summary-grid div {
  min-width: 0;
  padding: 0.45rem;
  border: 1px solid var(--xq-border);
  border-radius: 0.5rem;
  background: rgba(255, 255, 255, 0.48);
}
.usage-summary-grid dt {
  color: var(--xq-ink-muted);
  font-size: 0.7rem;
}
.usage-summary-grid dd {
  margin: 0.15rem 0 0;
  font-size: 1.1rem;
  font-weight: 850;
}
@media (max-width: 1100px) {
  .usage-summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
