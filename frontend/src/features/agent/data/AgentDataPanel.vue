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

    <XqPanel title="持久化 Agent Job" subtitle="当前为可恢复 Job 契约；独立 worker 仍在建设中。" data-testid="agent-job-panel">
      <p v-if="jobsLoading" class="muted">正在读取 Job…</p>
      <ol v-else class="timeline-list">
        <li v-for="job in jobs.slice(0, 12)" :key="job.id">
          <strong>{{ job.kind }} · {{ job.status }}</strong>
          <span>attempt {{ job.attempt_count }}/{{ job.max_attempts }} · {{ job.id.slice(0, 8) }}</span>
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
import type { AgentAuditRecord, AgentJob, AgentTimelineEvent, AgentToolHealth } from '@/api/agent'
import { agentEventLabel as eventLabel } from '@/features/agent/reducers/agentEventReducer'
import { XqButton, XqPanel } from '@/shared/ui'

withDefaults(defineProps<{
  isAdmin: boolean
  providerHealth: AgentToolHealth | null
  providerHealthLoading: boolean
  providerHealthError: string
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
const canCancelJob = (job: AgentJob) => !['succeeded', 'failed', 'cancelled', 'dead_letter'].includes(job.status)
</script>
