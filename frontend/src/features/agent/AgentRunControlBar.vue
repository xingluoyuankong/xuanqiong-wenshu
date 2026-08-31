<script setup lang="ts">
import { computed } from 'vue'
import type { AgentRun, AgentRunCommandType } from '@/api/agent'
import { XqButton } from '@/shared/ui'

const props = withDefaults(
  defineProps<{
    run: AgentRun | null
    allowedCommands?: AgentRunCommandType[]
    pending?: boolean
  }>(),
  {
    allowedCommands: () => [],
    pending: false,
  },
)

const emit = defineEmits<{
  command: [command: AgentRunCommandType]
}>()

const terminal = computed(() =>
  ['completed', 'failed', 'cancelled'].includes(String(props.run?.status || '')),
)
const allowed = computed(() => new Set(props.allowedCommands))
const canPause = computed(() => allowed.value.has('pause'))
const canResume = computed(() => allowed.value.has('resume'))
const canCancel = computed(() => allowed.value.has('cancel'))

const emitCommand = (command: AgentRunCommandType) => {
  if (!allowed.value.has(command) || terminal.value || !props.run) return
  emit('command', command)
}
</script>

<template>
  <section
    v-if="run && !terminal"
    class="run-control-bar"
    data-testid="agent-run-control-bar"
    aria-label="当前运行控制"
  >
    <p class="muted" aria-live="polite">
      {{
        pending
          ? '正在提交运行控制命令…'
          : allowedCommands.length
            ? '控制当前所选运行；可用操作由服务端状态投影决定。'
            : '服务端当前未允许运行控制操作。'
      }}
    </p>
    <div v-if="allowedCommands.length" class="actions">
      <XqButton
        v-if="canPause"
        variant="secondary"
        size="sm"
        :disabled="pending"
        data-testid="agent-pause-run-button"
        @click="emitCommand('pause')"
      >暂停</XqButton>
      <XqButton
        v-if="canResume"
        variant="secondary"
        size="sm"
        :disabled="pending"
        data-testid="agent-resume-run-button"
        @click="emitCommand('resume')"
      >继续</XqButton>
      <XqButton
        v-if="canCancel"
        variant="danger"
        size="sm"
        :disabled="pending"
        data-testid="agent-cancel-run-button"
        @click="emitCommand('cancel')"
      >取消运行</XqButton>
    </div>
  </section>
</template>

<style scoped>
.run-control-bar {
  display: grid;
  gap: .5rem;
  margin-top: .8rem;
  padding-top: .8rem;
  border-top: 1px solid var(--xq-border);
}
.run-control-bar p { margin: 0; }
.actions { display: flex; flex-wrap: wrap; gap: .5rem; }
</style>
