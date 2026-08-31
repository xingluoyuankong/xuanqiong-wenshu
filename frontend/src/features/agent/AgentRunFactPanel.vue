<script setup lang="ts">
import type {
  AgentContextSnapshot,
  AgentConversationSummary,
  AgentPlanRevision,
} from '@/api/agent'

withDefaults(defineProps<{
  contextSnapshot?: AgentContextSnapshot | null
  planRevision?: AgentPlanRevision | null
  conversationSummaries?: AgentConversationSummary[]
}>(), {
  contextSnapshot: null,
  planRevision: null,
  conversationSummaries: () => [],
})

const shortDigest = (value?: string | null) => (value ? `${value.slice(0, 12)}…` : '—')
</script>

<template>
  <section
    v-if="contextSnapshot || planRevision || conversationSummaries.length"
    class="agent-run-fact-panel"
    data-testid="agent-run-fact-panel"
    aria-label="当前运行冻结事实"
  >
    <header>
      <strong>运行冻结事实</strong>
      <small>可恢复、可校验、按当前 Run 隔离</small>
    </header>
    <dl v-if="contextSnapshot">
      <dt>上下文快照</dt>
      <dd>
        {{ contextSnapshot.context_kind }} · {{ contextSnapshot.refs.length }} 条引用 ·
        <code :title="contextSnapshot.digest">{{ shortDigest(contextSnapshot.digest) }}</code>
      </dd>
    </dl>
    <dl v-if="planRevision">
      <dt>计划修订</dt>
      <dd>
        r{{ planRevision.revision_number }} · {{ planRevision.status }}
        <span v-if="planRevision.parent_revision_id"> · 有父修订</span>
        <code :title="planRevision.digest">{{ shortDigest(planRevision.digest) }}</code>
      </dd>
    </dl>
    <dl v-if="conversationSummaries.length">
      <dt>会话摘要</dt>
      <dd>共 {{ conversationSummaries.length }} 条 · 最近消息区间 {{ conversationSummaries.at(-1)?.start_message_sequence }}–{{ conversationSummaries.at(-1)?.end_message_sequence }}</dd>
    </dl>
  </section>
</template>

<style scoped>
.agent-run-fact-panel { display: grid; gap: .45rem; margin: .75rem 0; padding: .8rem 1rem; border: 1px solid color-mix(in srgb, var(--xq-jade, #0f766e) 28%, var(--xq-border)); border-radius: var(--xq-radius-md); background: color-mix(in srgb, var(--xq-jade-pale, #e7f6f2) 55%, transparent); }
header { display: flex; justify-content: space-between; gap: .75rem; color: var(--xq-jade, #0f766e); }
header small, dt { color: var(--xq-text-muted); }
dl { display: grid; grid-template-columns: auto 1fr; gap: .35rem .7rem; margin: 0; font-size: .88rem; }
dd { margin: 0; }
code { font-size: .78rem; overflow-wrap: anywhere; }
</style>
