import { createApp, h, ref } from 'vue'
import AgentReasoningCard from '../src/features/agent/AgentReasoningCard.vue'
const makeChunks = (start: number, count: number) => Array.from({ length: count }, (_, offset) => ({
  id: `row-${start + offset}`, runId: 'fixture', sequence: start + offset, chunkIndex: start + offset,
  content: `row-${start + offset}\n` + '这是用于验证可变高度和换行的推理文本。'.repeat((start + offset) % 11 + 1),
}))
createApp({
  setup() {
    const chunks = ref(makeChunks(100, 2000))
    const status = ref<'completed' | 'streaming'>('completed')
    const width = ref(750)
    return () => h('main', { style: { width: `${width.value}px`, maxWidth: '100%' } }, [
      h('button', { onClick: () => { chunks.value = [...makeChunks(0, 100), ...chunks.value] } }, '前插100段'),
      h('button', { onClick: () => { status.value = 'streaming' } }, '开始流式'),
      h('button', { onClick: () => { status.value = 'completed' } }, '完成流式'),
      h('button', { onClick: () => { const last = chunks.value.at(-1)!; chunks.value = [...chunks.value.slice(0, -1), { ...last, content: last.content + '\n流式增长'.repeat(30) }] } }, '增长尾段'),
      h('button', { onClick: () => { width.value = width.value === 750 ? 330 : 750 } }, '切换宽度'),
      h(AgentReasoningCard, { chunks: chunks.value, status: status.value, contextKey: 'fixture', hasPrevious: true }),
    ])
  },
}).mount('#app')
