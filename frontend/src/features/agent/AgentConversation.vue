<template>
  <XqPanel tone="ink" title="创作对话" subtitle="展示目标、公开轨迹、Provider reasoning、Assistant 正文、工具调用和结果摘要。">
    <div class="session-bar">
      <span data-testid="agent-session-status">{{ sessionLabel }}</span>
      <small v-if="sessionLoading">正在恢复历史…</small>
      <small v-else-if="streamConnectionState === 'live'">实时运行流已连接</small>
      <small v-else-if="streamConnectionState === 'connecting'">正在连接实时运行流…</small>
      <small v-else-if="streamConnectionState === 'reconnecting'">实时运行流正在重连…</small>
      <small v-else-if="streamConnectionState === 'disconnected'" class="error">实时运行流已断开，可手动重连</small>
      <small v-else-if="sessionError" class="error">{{ sessionError }}</small>
    </div>
    <section v-if="latestProgressMessage" class="current-progress" data-testid="agent-current-progress" aria-live="polite">
      <strong>当前进度</strong>
      <span>{{ latestProgressMessage }}</span>
      <small v-if="latestProgressPhase">阶段：{{ latestProgressPhase }}</small>
      <small v-if="latestProgressActionId">动作：{{ latestProgressActionId }}</small>
      <small v-if="latestProgress !== undefined">{{ Math.round(latestProgress) }}%</small>
      <progress
        v-if="latestProgress !== undefined"
        class="current-progress-meter"
        data-testid="agent-progress-meter"
        max="100"
        :value="latestProgress"
        :aria-label="`当前进度 ${Math.round(latestProgress)}%`"
      />
    </section>
    <section
      v-if="!latestProgressMessage && latestWorkTrace"
      class="current-progress current-progress--trace"
      data-testid="agent-live-trace"
      aria-live="polite"
    >
      <strong>实时活动</strong>
      <span>{{ latestWorkTrace.message }}</span>
      <small>阶段：{{ latestWorkTrace.phase }}</small>
      <small v-if="latestWorkTrace.actionId">动作：{{ latestWorkTrace.actionId }}</small>
      <small v-if="latestWorkTrace.resultRef">结果：{{ latestWorkTrace.resultRef }}</small>
      <small v-if="latestWorkTrace.progress !== undefined">{{ Math.round(latestWorkTrace.progress) }}%</small>
      <progress
        v-if="latestWorkTrace.progress !== undefined"
        class="current-progress-meter"
        data-testid="agent-live-trace-meter"
        max="100"
        :value="latestWorkTrace.progress"
        :aria-label="`实时活动进度 ${Math.round(latestWorkTrace.progress)}%`"
      />
    </section>
    <div v-if="messages.length" class="messages" data-testid="agent-message-list">
      <article v-for="message in messages" :key="message.id" class="message" :class="`message-${message.role}`">
        <b>{{ message.role === 'user' ? '你' : 'Agent' }}</b><p>{{ message.content }}</p>
      </article>
    </div>
    <p v-else class="empty-chat" data-testid="agent-empty-chat">请选择项目并发送目标，Agent 的历史消息会显示在这里。</p>
    <AgentReasoningCard
      :chunks="reasoningChunks"
      :text="reasoningText"
      :status="reasoningStatus"
      :has-previous="reasoningHasPrevious"
      :loading-previous="reasoningLoadingPrevious"
      :previous-error="reasoningPreviousError"
      @load-previous="emit('load-previous-reasoning')"
    />
    <article v-if="streamingAssistant" class="message message-assistant message-streaming" data-testid="agent-streaming-message">
      <b>Agent</b><p>{{ streamingAssistant }}</p>
    </article>
    <XqPanel v-if="artifactPreviewLoading || artifactPreviewError || artifactPreview" title="候选正文预览" data-testid="agent-artifact-preview">
      <small v-if="artifactPreviewArtifactId" class="muted" data-testid="agent-artifact-preview-artifact">当前 Artifact：{{ artifactPreviewArtifactId.slice(0, 8) }}</small>
      <p v-if="artifactPreviewLoading" class="muted" data-testid="agent-artifact-preview-loading">正在读取候选正文…</p>
      <p v-else-if="artifactPreviewError" class="error" data-testid="agent-artifact-preview-error">候选正文读取失败：{{ artifactPreviewError }}</p>
      <template v-else>
        <pre class="artifact-preview">{{ artifactPreview }}</pre>
        <XqButton variant="secondary" size="sm" @click="emit('close-artifact-preview')">关闭预览</XqButton>
      </template>
    </XqPanel>
    <AgentPublicWorkSummary
      v-if="publicWorkSummary"
      :summary="publicWorkSummary"
      :work-trace-deltas="workTraceDeltas"
      :latest-work-trace="latestWorkTrace"
      :has-sequence-gap="hasSequenceGap"
      :replay-required="replayRequired"
      :pending-sequences="pendingSequences"
    />
    <form class="composer" @submit.prevent="emit('submit')">
      <AgentContextChips :refs="contextRefs" :project-title="projectTitle || undefined" :chapter-title="chapterTitle || undefined" @remove="emit('remove-context-ref', $event)" />
      <label class="sr-only" for="agent-goal">给小说 Agent 的指令</label>
      <textarea id="agent-goal" :value="goal" data-testid="agent-message-input" rows="4" placeholder="例如：检查当前项目第三章的质量风险，并给出不改正文的计划" @input="updateGoal" />
      <div>
        <small>{{ runtimeSupported ? '消息会写入当前会话，并接收真实运行事件。' : '当前测试/兼容模式只生成计划，不执行写入。' }}</small>
        <XqButton type="submit" data-testid="agent-plan-submit" :loading="sending || planning" :disabled="!goal.trim() || sessionLoading">{{ runtimeSupported ? '发送给 Agent' : '生成执行计划' }}</XqButton>
      </div>
    </form>
  </XqPanel>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AgentContextRef, AgentMessage, AgentPublicWorkSummary as AgentPublicWorkSummaryType } from '@/api/agent'
import type { SSEConnectionState } from '@/utils/sseStream'
import type { AgentWorkTraceDelta } from './reducers/agentEventReducer'
import AgentContextChips from './AgentContextChips.vue'
import AgentPublicWorkSummary from './AgentPublicWorkSummary.vue'
import AgentReasoningCard from './AgentReasoningCard.vue'
import type { AgentReasoningChunk, AgentReasoningStatus } from './reducers/agentEventReducer'
import { XqButton, XqPanel } from '@/shared/ui'

const props = withDefaults(
  defineProps<{
    messages: AgentMessage[]
    sessionTitle?: string | null
    sessionLoading?: boolean
    streamConnectionState?: SSEConnectionState
    sessionError?: string
    runtimeSupported?: boolean
    sending?: boolean
    planning?: boolean
    streamingAssistant?: string
    latestProgressMessage?: string
    latestProgressActionId?: string
    latestProgressPhase?: string
    latestProgress?: number
    artifactPreview?: string
    artifactPreviewLoading?: boolean
    artifactPreviewArtifactId?: string | null
    artifactPreviewError?: string
    publicWorkSummary?: AgentPublicWorkSummaryType | null
    reasoningChunks?: AgentReasoningChunk[]
    reasoningText?: string
    reasoningStatus?: AgentReasoningStatus
    reasoningHasPrevious?: boolean
    reasoningLoadingPrevious?: boolean
    reasoningPreviousError?: string
    workTraceDeltas?: AgentWorkTraceDelta[]
    latestWorkTrace?: AgentWorkTraceDelta | null
    hasSequenceGap?: boolean
    replayRequired?: boolean
    pendingSequences?: number[]
    contextRefs?: AgentContextRef[]
    projectTitle?: string | null
    chapterTitle?: string | null
    goal?: string
  }>(),
  {
    sessionTitle: null,
    sessionLoading: false,
    streamConnectionState: 'closed',
    sessionError: '',
    runtimeSupported: false,
    sending: false,
    planning: false,
    streamingAssistant: '',
    latestProgressMessage: '',
    latestProgressActionId: undefined,
    latestProgressPhase: undefined,
    latestProgress: undefined,
    artifactPreview: '',
    artifactPreviewLoading: false,
    artifactPreviewArtifactId: null,
    artifactPreviewError: '',
    publicWorkSummary: null,
    reasoningChunks: () => [],
    reasoningText: '',
    reasoningStatus: 'idle',
    reasoningHasPrevious: false,
    reasoningLoadingPrevious: false,
    reasoningPreviousError: '',
    workTraceDeltas: () => [],
    latestWorkTrace: null,
    hasSequenceGap: false,
    replayRequired: false,
    pendingSequences: () => [],
    contextRefs: () => [],
    projectTitle: null,
    chapterTitle: null,
    goal: '',
  },
)

const emit = defineEmits<{
  (event: 'update:goal', value: string): void
  (event: 'submit'): void
  (event: 'remove-context-ref', ref: AgentContextRef): void
  (event: 'close-artifact-preview'): void
  (event: 'load-previous-reasoning'): void
}>()

const sessionLabel = computed(() => {
  if (props.sessionTitle) return `会话：${props.sessionTitle}`
  return props.runtimeSupported ? '准备会话…' : '兼容计划预览模式'
})

const updateGoal = (event: Event) => {
  emit('update:goal', (event.target as HTMLTextAreaElement).value)
}
</script>

<style scoped>
.session-bar { display: flex; justify-content: space-between; gap: 0.75rem; margin-bottom: 0.75rem; color: rgba(255, 255, 255, 0.86); font-size: 0.82rem; }
.session-bar small { color: rgba(255, 255, 255, 0.68); }
.current-progress {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.35rem 0.65rem;
  margin: 0 0 0.75rem;
  padding: 0.55rem 0.7rem;
  border: 1px solid rgba(93, 211, 158, 0.35);
  border-radius: 0.65rem;
  background: rgba(16, 185, 129, 0.08);
  color: var(--xq-ink);
}
.current-progress strong { color: var(--xq-jade); font-size: 0.78rem; }
.current-progress span { min-width: 0; overflow-wrap: anywhere; line-height: 1.45; }
.current-progress small { color: var(--xq-ink-muted); font-size: 0.72rem; }
.current-progress-meter {
  flex: 1 0 100%;
  width: 100%;
  height: 0.45rem;
  accent-color: var(--xq-jade);
}
.messages { display: grid; gap: 0.7rem; max-height: 26rem; overflow: auto; margin-bottom: 1rem; }
.message { max-width: 88%; padding: 0.7rem 0.85rem; border-radius: 0.8rem; background: rgba(255, 255, 255, 0.1); }
.message-streaming { border-left: 3px solid var(--xq-jade); opacity: 0.92; }
.artifact-preview { max-height: 28rem; overflow: auto; white-space: pre-wrap; line-height: 1.65; margin: 0 0 0.65rem; font: inherit; }
.message p { margin: 0.25rem 0 0; white-space: pre-wrap; line-height: 1.6; }
.message-user { justify-self: end; background: rgba(8, 145, 178, 0.35); }
.message-assistant { justify-self: start; background: rgba(255, 255, 255, 0.12); }
.empty-chat { color: rgba(255, 255, 255, 0.7); line-height: 1.6; }
.composer { display: grid; gap: 0.65rem; margin-top: 1rem; }
.composer textarea { width: 100%; box-sizing: border-box; border: 1px solid var(--xq-border); border-radius: 0.7rem; padding: 0.7rem; background: rgba(255, 255, 255, 0.85); font: inherit; resize: vertical; line-height: 1.6; }
.composer > div { display: flex; justify-content: space-between; gap: 0.75rem; align-items: center; }
.composer small { color: rgba(255, 255, 255, 0.7); }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0, 0, 0, 0); }
@media (max-width: 650px) { .composer > div { align-items: flex-start; flex-direction: column; } }
</style>

