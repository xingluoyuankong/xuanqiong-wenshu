<script setup lang="ts">
import type { AgentPublicWorkSummary } from '@/api/agent'
import type { AgentWorkTraceDelta } from './reducers/agentEventReducer'

withDefaults(defineProps<{
  summary: AgentPublicWorkSummary
  workTraceDeltas?: AgentWorkTraceDelta[]
  latestWorkTrace?: AgentWorkTraceDelta | null
  hasSequenceGap?: boolean
  replayRequired?: boolean
  pendingSequences?: number[]
}>(), {
  workTraceDeltas: () => [],
  latestWorkTrace: null,
  hasSequenceGap: false,
  replayRequired: false,
  pendingSequences: () => [],
})

const scopeLabel = (scope: AgentPublicWorkSummary['input_scope'][number]) => {
  if (scope.kind === 'project') return '当前项目'
  if (scope.kind === 'chapter') return `第 ${scope.chapter_number || '?'} 章`
  if (scope.kind === 'chapter_version') return `第 ${scope.chapter_number || '?'} 章 · 版本 ${scope.version_id || '?'}`
  if (scope.kind === 'artifact') return `候选 ${scope.artifact_id?.slice(0, 8) || ''}`
  if (scope.kind === 'plan') return '执行计划'
  return '工具结果'
}
</script>

<template>
  <section class="public-work-summary" data-testid="agent-public-work-summary" aria-live="polite">
    <header>
      <span>Agent 当前工作</span>
      <small>{{ summary.phase }}<template v-if="summary.step_order !== null && summary.step_order !== undefined"> · 步骤 {{ summary.step_order }}</template><template v-if="summary.revision !== null && summary.revision !== undefined"> · 修订 {{ summary.revision }}</template></small>
    </header>
    <p class="current">{{ summary.current_action }}</p>
    <dl>
      <template v-if="summary.completed_action">
        <dt>已完成</dt><dd>{{ summary.completed_action }}</dd>
      </template>
      <template v-if="summary.selected_capability">
        <dt>能力</dt><dd>{{ summary.selected_capability }}</dd>
      </template>
      <template v-if="summary.decision_summary">
        <dt>判断</dt><dd>{{ summary.decision_summary }}</dd>
      </template>
      <template v-if="summary.next_action">
        <dt>下一步</dt><dd>{{ summary.next_action }}</dd>
      </template>
      <template v-if="summary.expected_output">
        <dt>预期输出</dt><dd>{{ summary.expected_output }}</dd>
      </template>
    </dl>
    <div v-if="summary.input_scope.length" class="scope" aria-label="输入范围">
      <span v-for="(item, index) in summary.input_scope" :key="[item.kind, item.project_id, item.chapter_number, item.version_id, item.artifact_id, index].join(':')">
        {{ scopeLabel(item) }}
      </span>
    </div>
    <section v-if="latestWorkTrace || workTraceDeltas.length || hasSequenceGap" class="trace-panel" data-testid="agent-work-trace-panel">
      <header class="trace-header">
        <span>公开工作轨迹</span>
        <small v-if="latestWorkTrace">{{ latestWorkTrace.phase }} · {{ latestWorkTrace.kind }}</small>
      </header>
      <p v-if="replayRequired" class="trace-gap" data-testid="agent-replay-required">
        事件序列存在缺口，正在请求补发{{ pendingSequences.length ? `：${pendingSequences.join('、')}` : '' }}。
      </p>
      <details v-if="workTraceDeltas.length" class="trace-details">
        <summary data-testid="agent-work-trace-toggle">查看轨迹（{{ workTraceDeltas.length }}）</summary>
        <ol class="trace-list" data-testid="agent-work-trace-list">
          <li v-for="trace in workTraceDeltas" :key="`${trace.traceId}:${trace.sequence}`">
            <span class="trace-meta">#{{ trace.sequence }} · {{ trace.phase }} · {{ trace.kind }}</span>
            <span>{{ trace.message }}</span>
            <small v-if="trace.progress !== undefined">{{ Math.round(trace.progress) }}%</small>
          </li>
        </ol>
      </details>
    </section>
  </section>
</template>

<style scoped>
.public-work-summary {
  margin: .75rem 0;
  padding: .85rem 1rem;
  border: 1px solid color-mix(in srgb, var(--xq-gold-deep) 35%, var(--xq-border));
  border-radius: var(--xq-radius-md);
  background: color-mix(in srgb, var(--xq-gold-pale, #fff8dc) 72%, transparent);
}
header { display: flex; justify-content: space-between; gap: .75rem; color: var(--xq-gold-deep); font-weight: 800; }
header small { color: var(--xq-text-muted); font-weight: 600; }
.current { margin: .5rem 0; font-weight: 700; }
dl { display: grid; grid-template-columns: auto 1fr; gap: .28rem .65rem; margin: 0; font-size: .9rem; }
dt { color: var(--xq-text-muted); }
dd { margin: 0; }
.scope { display: flex; flex-wrap: wrap; gap: .35rem; margin-top: .65rem; }
.scope span { padding: .15rem .45rem; border-radius: 999px; background: color-mix(in srgb, var(--xq-gold-deep) 10%, transparent); font-size: .8rem; }
.trace-panel { margin-top: .8rem; padding-top: .7rem; border-top: 1px solid color-mix(in srgb, var(--xq-gold-deep) 22%, transparent); }
.trace-header { color: var(--xq-gold-deep); }
.trace-header small { font-weight: 600; }
.trace-gap { margin: .5rem 0 0; color: #a33a25; font-size: .85rem; }
.trace-details { margin-top: .55rem; }
.trace-details summary { cursor: pointer; color: var(--xq-gold-deep); font-weight: 700; }
.trace-list { display: grid; gap: .45rem; margin: .55rem 0 0; padding-left: 1.2rem; font-size: .86rem; }
.trace-list li { display: grid; gap: .1rem; }
.trace-meta, .trace-list small { color: var(--xq-text-muted); }
</style>