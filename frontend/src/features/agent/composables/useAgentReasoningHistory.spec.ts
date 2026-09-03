import { flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { useAgentReasoningHistory } from './useAgentReasoningHistory'

const { listRunReasoning } = vi.hoisted(() => ({ listRunReasoning: vi.fn() }))
vi.mock('@/api/agent', () => ({ AgentAPI: { listRunReasoning } }))

describe('useAgentReasoningHistory', () => {
  it('加载最新分页并可继续读取更早 reasoning', async () => {
    listRunReasoning
      .mockResolvedValueOnce({ run_id: 'run-1', items: [{ id: 'b', run_id: 'run-1', sequence: 2, chunk_index: 1, content: '后', content_hash: 'h', created_at: 'now' }], previous_cursor: 2, has_previous: true, has_more: false })
      .mockResolvedValueOnce({ run_id: 'run-1', items: [{ id: 'a', run_id: 'run-1', sequence: 1, chunk_index: 0, content: '前', content_hash: 'h', created_at: 'now' }], previous_cursor: null, has_previous: false, has_more: false })
    const history = useAgentReasoningHistory()
    await history.load('run-1')
    await flushPromises()
    expect(listRunReasoning).toHaveBeenCalledWith('run-1', { beforeSequence: 2_147_483_647, limit: 100 })
    expect(history.chunks.value.map((item) => item.content)).toEqual(['后'])
    expect(history.hasPrevious.value).toBe(true)
    await history.loadPrevious()
    expect(history.chunks.value.map((item) => item.content)).toEqual(['前', '后'])
    expect(history.hasPrevious.value).toBe(false)
  })
})
