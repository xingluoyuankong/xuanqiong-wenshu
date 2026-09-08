import { createApp, h, ref } from 'vue'
import { useAgentRunStream } from '../../src/features/agent/composables/useAgentRunStream'
import { createAgentRunEventProjection, reduceAgentRunEvent } from '../../src/features/agent/reducers/agentEventReducer'
import { toSafeAgentEvent } from '../../src/utils/agentEventSafety'
createApp({ setup() {
  const stream = useAgentRunStream(), projection = ref(createAgentRunEventProjection())
  const accepted = ref<number[]>([]), owners = ref<string[]>([]), terminal = ref(0), states = ref<string[]>([])
  const run = ref('run-a')
  const start = async (key: string, selected = 'run-a') => {
    run.value = selected; accepted.value = []; owners.value = []; terminal.value = 0; projection.value = createAgentRunEventProjection()
    await stream.start({ sessionId: 'fixture-session', runId: selected, loadHistory: async () => [],
      streamUrl: cursor => `/__sse/stream?key=${key}&run=${selected}&after_sequence=${cursor}`,
      onEvent: event => { accepted.value.push(event.sequence); owners.value.push(event.run_id); projection.value = reduceAgentRunEvent(projection.value, toSafeAgentEvent(event)).projection },
      onTerminal: () => terminal.value++, onConnectionState: state => states.value.push(state),
    })
  }
  return () => h('main', { style: 'max-width:900px;margin:32px auto;font:16px sans-serif;overflow-wrap:anywhere' }, [
    h('h1', 'Agent SSE 实际网络流验收'),
    h('button', { 'data-testid': 'long', onClick: () => start('long') }, '开始 60 秒续接验收'),
    h('button', { 'data-testid': 'switch-a', onClick: () => start('switch-a') }, '运行 A'),
    h('button', { 'data-testid': 'restart-a', onClick: () => start('switch-a-restart') }, '同 ID 重启'),
    h('button', { 'data-testid': 'switch-b', onClick: () => start('switch-b', 'run-b') }, '切换 B'),
    h('p', { 'data-testid': 'status' }, stream.connectionState.value),
    h('p', { 'data-testid': 'run' }, run.value),
    h('p', { 'data-testid': 'count' }, String(accepted.value.length)),
    h('p', { 'data-testid': 'terminal' }, String(terminal.value)),
    h('pre', { 'data-testid': 'sequences' }, JSON.stringify(accepted.value)),
    h('pre', { 'data-testid': 'owners' }, JSON.stringify([...new Set(owners.value)])),
    h('pre', { 'data-testid': 'states' }, JSON.stringify(states.value)),
    h('article', { 'data-testid': 'text' }, projection.value.assistantText),
  ])
} }).mount('#app')
