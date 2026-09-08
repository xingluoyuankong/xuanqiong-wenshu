import { computed, ref } from 'vue'
import { AgentAPI, type AgentReasoningChunk as ApiReasoningChunk } from '@/api/agent'
import type { AgentReasoningChunk } from '../reducers/agentEventReducer'

const LAST_SEQUENCE = 2_147_483_647
const PAGE_SIZE = 100

type ReasoningRequest = Readonly<{
  generation: number
  runId: string
  beforeSequence: number
}>

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
  let generation = 0
  let activeRequest: ReasoningRequest | null = null

  const reset = () => {
    // A reload of the same Run (including A -> B -> A) owns a new generation.
    generation += 1
    activeRequest = null
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

  const isCurrent = (request: ReasoningRequest) =>
    activeRequest === request && generation === request.generation && runId.value === request.runId

  const loadPage = async (beforeSequence: number, prepend: boolean) => {
    if (!runId.value || loading.value || typeof AgentAPI.listRunReasoning !== 'function') return
    const request: ReasoningRequest = { generation, runId: runId.value, beforeSequence }
    activeRequest = request
    loading.value = true
    error.value = ''
    try {
      const page = await AgentAPI.listRunReasoning(request.runId, { beforeSequence: request.beforeSequence, limit: PAGE_SIZE })
      if (!isCurrent(request)) return
      // Validate the complete page before writing any chunks or pagination state.
      if (page.run_id !== request.runId) throw new Error('reasoning 历史分页的 Run 与当前请求不匹配')
      if (page.items.some((item) => item.run_id !== request.runId)) throw new Error('reasoning 历史条目的 Run 与当前请求不匹配')
      merge(page.items.map(toDisplayChunk), prepend)
      previousCursor.value = page.previous_cursor ?? null
      hasPrevious.value = Boolean(page.has_previous && page.previous_cursor !== null && page.previous_cursor !== undefined)
    } catch (cause) {
      if (!isCurrent(request)) return
      error.value = cause instanceof Error ? cause.message : (prepend ? '更早 reasoning 读取失败' : 'reasoning 历史读取失败')
    } finally {
      // An old completion must not unlock or clear a newer request's state.
      if (isCurrent(request)) {
        activeRequest = null
        loading.value = false
      }
    }
  }

  const load = async (nextRunId: string | null) => {
    reset()
    if (!nextRunId || typeof AgentAPI.listRunReasoning !== 'function') return
    runId.value = nextRunId
    await loadPage(LAST_SEQUENCE, false)
  }

  const loadPrevious = async () => {
    if (!hasPrevious.value || previousCursor.value === null) return
    await loadPage(previousCursor.value, true)
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
