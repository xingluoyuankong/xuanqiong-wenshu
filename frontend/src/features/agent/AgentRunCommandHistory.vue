<script setup lang="ts">
import { computed } from 'vue'
import type {
  AgentRunCommandStatus,
  AgentRunCommandSummary,
  AgentRunCommandType,
} from '@/api/agent'

const props = defineProps<{
  commands: AgentRunCommandSummary[]
  runId?: string | null
}>()

const visibleCommands = computed(() =>
  props.commands
    .filter((command) => !command.run_id || !props.runId || command.run_id === props.runId)
    .slice()
    .sort((left, right) => {
      const timeOrder = left.requested_at.localeCompare(right.requested_at)
      return timeOrder || left.id.localeCompare(right.id)
    }),
)

const commandLabel = (type: AgentRunCommandType) =>
  ({ pause: '暂停', resume: '继续', cancel: '取消' })[type] || type

const statusLabel = (status: AgentRunCommandStatus) =>
  ({
    requested: '已请求',
    applying: '处理中',
    applied: '已应用',
    rejected: '已拒绝',
    failed: '失败',
  })[status] || status

const formatTimestamp = (value?: string | null) => {
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}
</script>

<template>
  <section
    v-if="visibleCommands.length"
    class="run-command-history"
    data-testid="agent-run-command-history"
    aria-label="当前运行控制记录"
  >
    <header>
      <strong>运行控制记录</strong>
      <small>{{ visibleCommands.length }} 条</small>
    </header>
    <ol>
      <li v-for="command in visibleCommands" :key="command.id">
        <div class="command-title">
          <b>{{ commandLabel(command.command_type) }}</b>
          <span :class="`command-status command-status--${command.status}`">
            {{ statusLabel(command.status) }}
          </span>
        </div>
        <small v-if="command.reason">原因：{{ command.reason }}</small>
        <small v-if="command.expected_state_version !== null && command.expected_state_version !== undefined">
          提交状态版本：{{ command.expected_state_version }}
        </small>
        <small v-if="command.idempotency_key" class="command-key" :title="command.idempotency_key">
          幂等键：{{ command.idempotency_key }}
        </small>
        <small v-if="command.requested_at">请求：{{ formatTimestamp(command.requested_at) }}</small>
        <small v-if="command.applied_at">处理：{{ formatTimestamp(command.applied_at) }}</small>
        <small v-if="command.error_type" class="error">错误：{{ command.error_type }}</small>
        <small v-if="command.error_detail" class="error">{{ command.error_detail }}</small>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.run-command-history {
  display: grid;
  gap: .55rem;
  margin-top: .8rem;
  padding-top: .8rem;
  border-top: 1px solid var(--xq-border);
}
.run-command-history header,
.command-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: .6rem;
}
.run-command-history header { color: var(--xq-gold-deep); }
.run-command-history header small,
.run-command-history li small { color: var(--xq-text-muted); }
.run-command-history ol { display: grid; gap: .45rem; margin: 0; padding-left: 1.2rem; }
.run-command-history li { padding-left: .15rem; }
.command-status { font-size: .78rem; font-weight: 700; }
.command-status--applied { color: var(--xq-jade); }
.command-status--rejected,
.command-status--failed { color: var(--xq-danger, #b42318); }
.command-status--requested { color: var(--xq-gold-deep); }
.run-command-history li small { display: block; margin-top: .18rem; }
.command-key { overflow-wrap: anywhere; }
.error { color: var(--xq-danger, #b42318) !important; }
</style>
