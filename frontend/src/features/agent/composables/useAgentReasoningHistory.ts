import { computed, ref } from 'vue'
import { AgentAPI, type AgentReasoningChunk as ApiReasoningChunk } from '@/api/agent'
import type { AgentReasoningChunk } from '../reducers/agentEventReducer'

const LAST_SEQUENCE = 2_147_483_647
const PAGE_SIZE = 100

const toDisplayChunk = (item: ApiReasoningChunk): AgentReasoningChunk => ({
  id: item.id,
  runId: item.run_id,
  sequence: item.sequence,
  chunkIndex: item.chunk_index,
  content: item.content,
  createdAt: item.created_at,
})

export function useAgentReasoningHistory() {
  const runId = ref<string | null>(null)
  const chunks = ref<AgentReasoningChunk[]>([])
  const previousCursor = ref<number | null>(null)
  const hasPrevious = ref(false)
  const loading = ref(false)
  const error = ref('')

  const reset = () => {
    runId.value = null
    chunks.value = []
    previousCursor.value = null
    hasPrevious.value = false
    loading.value = false
    error.value = ''
  }

  const merge = (incoming: AgentReasoningChunk[], prepend = false) => {
    const bySequence = new Map<number, AgentReasoningChunk>()
    for (const item of prepend ? [...incoming, ...chunks.value] : [...chunks.value, ...incoming]) bySequence.set(item.sequence, item)
    chunks.value = [...bySequence.values()].sort((left, right) => left.sequence - right.sequence)
  }

  const load = async (nextRunId: string | null) => {
    reset()
    if (!nextRunId || typeof AgentAPI.listRunReasoning !== 'function') return
    runId.value = nextRunId
    loading.value = true
    try {
      const page = await AgentAPI.listRunReasoning(nextRunId, { beforeSequence: LAST_SEQUENCE, limit: PAGE_SIZE })
      merge(page.items.map(toDisplayChunk))
      previousCursor.value = page.previous_cursor ?? null
      hasPrevious.value = Boolean(page.has_previous && page.previous_cursor !== null && page.previous_cursor !== undefined)
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : 'reasoning 历史读取失败'
    } finally {
      loading.value = false
    }
  }

  const loadPrevious = async () => {
    if (!runId.value || !hasPrevious.value || previousCursor.value === null || loading.value || typeof AgentAPI.listRunReasoning !== 'function') return
    loading.value = true
    error.value = ''
    try {
      const page = await AgentAPI.listRunReasoning(runId.value, { beforeSequence: previousCursor.value, limit: PAGE_SIZE })
      merge(page.items.map(toDisplayChunk), true)
      previousCursor.value = page.previous_cursor ?? null
      hasPrevious.value = Boolean(page.has_previous && page.previous_cursor !== null && page.previous_cursor !== undefined)
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : '更早 reasoning 读取失败'
    } finally {
      loading.value = false
    }
  }

  return {
    chunks,
    hasPrevious: computed(() => hasPrevious.value),
    loading,
    error,
    load,
    loadPrevious,
  }
}
