<template>
  <section
    v-if="refs.length"
    class="agent-context-chips"
    data-testid="agent-context-chips"
    aria-label="当前 Agent 上下文"
  >
    <span class="context-title">当前上下文</span>
    <span
      v-for="ref in refs"
      :key="contextRefKey(ref)"
      class="context-chip"
      :data-testid="chipTestId(ref)"
    >
      <span>{{ contextRefLabel(ref, { projectTitle, chapterTitle }) }}</span>
      <button
        v-if="ref.kind !== 'project'"
        type="button"
        class="context-chip-remove"
        :data-testid="chipTestId(ref) + '-remove'"
        :aria-label="'移除' + contextRefLabel(ref, { projectTitle, chapterTitle })"
        @click="$emit('remove', ref)"
      >
        ×
      </button>
    </span>
  </section>
</template>

<script setup lang="ts">
import type { AgentContextRef } from '@/api/agent'
import { contextRefKey, contextRefLabel } from './contextRefs'

defineProps<{
  refs: AgentContextRef[]
  projectTitle?: string
  chapterTitle?: string
}>()

defineEmits<{
  (event: 'remove', ref: AgentContextRef): void
}>()

const chipTestId = (ref: AgentContextRef): string =>
  'agent-context-chip-' + ref.kind.replace('_', '-')
</script>

<style scoped>
.agent-context-chips {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.45rem;
  margin: 0.2rem 0 0.1rem;
}
.context-title {
  color: rgba(255, 255, 255, 0.72);
  font-size: 0.78rem;
  font-weight: 800;
}
.context-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.24rem 0.45rem;
  border: 1px solid rgba(255, 255, 255, 0.28);
  border-radius: 999px;
  background: rgba(61, 143, 125, 0.18);
  color: rgba(255, 255, 255, 0.94);
  font-size: 0.78rem;
  line-height: 1.25;
}
.context-chip-remove {
  width: 1.2rem;
  height: 1.2rem;
  padding: 0;
  border: 0;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.2);
  color: inherit;
  font: inherit;
  line-height: 1;
  cursor: pointer;
}
.context-chip-remove:hover {
  background: rgba(239, 68, 68, 0.55);
}
</style>
