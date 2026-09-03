<script setup lang="ts">
import { computed, ref } from 'vue'
import type { AgentReasoningChunk, AgentReasoningStatus } from './reducers/agentEventReducer'

const props = withDefaults(defineProps<{
  chunks?: AgentReasoningChunk[]
  text?: string
  status?: AgentReasoningStatus
}>(), {
  chunks: () => [],
  text: '',
  status: 'idle',
})

const manuallyExpanded = ref(false)
const copied = ref(false)
const isStreaming = computed(() => props.status === 'streaming')
const isExpanded = computed(() => isStreaming.value || manuallyExpanded.value)
const statusLabel = computed(() => ({ idle: '待开始', streaming: '流式中', completed: '已完成', failed: '失败' })[props.status])
const displayText = computed(() => props.text || props.chunks.map((chunk) => chunk.content).join(''))

const toggle = () => {
  manuallyExpanded.value = !manuallyExpanded.value
}
const copyText = async () => {
  if (!displayText.value || typeof navigator === 'undefined' || !navigator.clipboard) return
  await navigator.clipboard.writeText(displayText.value)
  copied.value = true
  window.setTimeout(() => { copied.value = false }, 1200)
}
</script>

<template>
  <section v-if="displayText || chunks.length || status !== 'idle'" class="reasoning-card" data-testid="agent-reasoning-card" aria-live="polite">
    <header class="reasoning-card__header">
      <button type="button" class="reasoning-card__toggle" data-testid="agent-reasoning-toggle" :aria-expanded="isExpanded" @click="toggle">
        <span class="reasoning-card__title"><span aria-hidden="true">◌</span> Provider 原始 reasoning</span>
        <span class="reasoning-card__status" :class="`is-${status}`">{{ statusLabel }}<template v-if="chunks.length"> · {{ chunks.length }} 段</template></span>
      </button>
      <button v-if="displayText" type="button" class="reasoning-card__copy" data-testid="agent-reasoning-copy" @click="copyText">{{ copied ? '已复制' : '复制' }}</button>
    </header>
    <div v-show="isExpanded" class="reasoning-card__body" data-testid="agent-reasoning-body">
      <pre>{{ displayText }}</pre>
    </div>
  </section>
</template>

<style scoped>
.reasoning-card { margin: .75rem 0; border: 1px solid color-mix(in srgb, #7c3aed 34%, var(--xq-border)); border-radius: var(--xq-radius-md); background: color-mix(in srgb, #f5f3ff 88%, transparent); overflow: hidden; }
.reasoning-card__header { display: flex; align-items: stretch; justify-content: space-between; gap: .5rem; }
.reasoning-card__toggle { display: flex; align-items: center; justify-content: space-between; flex: 1; min-width: 0; gap: .6rem; padding: .65rem .8rem; border: 0; color: #5b21b6; background: transparent; text-align: left; cursor: pointer; }
.reasoning-card__title { font-weight: 800; }
.reasoning-card__status { color: #6b7280; font-size: .76rem; font-weight: 700; white-space: nowrap; }
.reasoning-card__status.is-streaming { color: #7c3aed; }
.reasoning-card__status.is-failed { color: var(--xq-cinnabar); }
.reasoning-card__copy { align-self: center; margin-right: .55rem; padding: .25rem .45rem; border: 1px solid color-mix(in srgb, #7c3aed 24%, var(--xq-border)); border-radius: .4rem; color: #6d28d9; background: white; cursor: pointer; }
.reasoning-card__body { border-top: 1px solid color-mix(in srgb, #7c3aed 18%, var(--xq-border)); padding: .7rem .8rem; max-height: 22rem; overflow: auto; }
.reasoning-card__body pre { margin: 0; color: #312e81; white-space: pre-wrap; overflow-wrap: anywhere; font: .82rem/1.65 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
</style>
