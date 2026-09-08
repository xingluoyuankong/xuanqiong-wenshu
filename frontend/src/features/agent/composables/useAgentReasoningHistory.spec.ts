import { flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AgentReasoningChunk, AgentReasoningPage } from '@/api/agent'
import { useAgentReasoningHistory } from './useAgentReasoningHistory'

const { listRunReasoning } = vi.hoisted(() => ({ listRunReasoning: vi.fn() }))
vi.mock('@/api/agent', () => ({ AgentAPI: { listRunReasoning } }))

describe('useAgentReasoningHistory', () => {
  beforeEach(() => listRunReasoning.mockReset())
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

const deferredPage = () => {
  let resolve!: (page: AgentReasoningPage) => void
  let reject!: (error: Error) => void
  const promise = new Promise<AgentReasoningPage>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

const chunk = (runId: string, sequence: number, content = `${runId}:${sequence}`): AgentReasoningChunk => ({
  id: `${runId}:${sequence}`,
  run_id: runId,
  user_id: 1,
  sequence,
  chunk_index: sequence,
  content,
  content_hash: 'hash',
  created_at: '2026-09-06T00:00:00Z',
})

const page = (runId: string, sequences: number[], cursor: number | null = null): AgentReasoningPage => ({
  run_id: runId,
  items: sequences.map((sequence) => chunk(runId, sequence)),
  previous_cursor: cursor,
  has_previous: cursor !== null,
  has_more: false,
})

const snapshot = (history: ReturnType<typeof useAgentReasoningHistory>) => ({
  chunks: history.chunks.value.map((item) => ({ ...item })),
  hasPrevious: history.hasPrevious.value,
  loading: history.loading.value,
  error: history.error.value,
})

// Control completion order explicitly: no timers, sleeps or real network.
describe('reasoning request ownership', () => {
  beforeEach(() => listRunReasoning.mockReset())

  it.each(['success', 'failure'] as const)('ignores old initial %s and finally while the new Run is loading', async (outcome) => {
    const old = deferredPage()
    const current = deferredPage()
    listRunReasoning.mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise)
    const history = useAgentReasoningHistory()
    const oldLoad = history.load('A')
    const currentLoad = history.load('B')
    const pendingState = snapshot(history)
    if (outcome === 'success') old.resolve(page('A', [50], 50))
    else old.reject(new Error('old failure'))
    await oldLoad
    expect(snapshot(history)).toEqual(pendingState)
    expect(history.loading.value).toBe(true)
    await history.loadPrevious()
    expect(listRunReasoning).toHaveBeenCalledTimes(2)
    current.resolve(page('B', [100], 100))
    await currentLoad
    expect(history.chunks.value.map((item) => item.runId)).toEqual(['B'])
    expect(history.loading.value).toBe(false)
    expect(history.error.value).toBe('')
  })

  it.each(['success', 'failure'] as const)('ignores old initial %s after a newer success and retains its cursor', async (outcome) => {
    const old = deferredPage()
    listRunReasoning.mockReturnValueOnce(old.promise).mockResolvedValueOnce(page('B', [100], 100))
    const history = useAgentReasoningHistory()
    const oldLoad = history.load('A')
    await history.load('B')
    const currentState = snapshot(history)
    if (outcome === 'success') old.resolve(page('A', [100, 150], 150))
    else old.reject(new Error('old failure'))
    await oldLoad
    expect(snapshot(history)).toEqual(currentState)
    listRunReasoning.mockResolvedValueOnce(page('B', [90]))
    await history.loadPrevious()
    expect(listRunReasoning).toHaveBeenLastCalledWith('B', { beforeSequence: 100, limit: 100 })
    expect(history.chunks.value.map((item) => item.content)).toEqual(['B:90', 'B:100'])
    expect(history.hasPrevious.value).toBe(false)
  })

  it.each(['success', 'failure'] as const)('does not replace a current error with old initial %s', async (outcome) => {
    const old = deferredPage()
    listRunReasoning.mockReturnValueOnce(old.promise).mockRejectedValueOnce(new Error('current failure'))
    const history = useAgentReasoningHistory()
    const oldLoad = history.load('A')
    await history.load('B')
    const currentState = snapshot(history)
    if (outcome === 'success') old.resolve(page('A', [50], 50))
    else old.reject(new Error('old failure'))
    await oldLoad
    expect(snapshot(history)).toEqual(currentState)
    expect(history.error.value).toBe('current failure')
    listRunReasoning.mockResolvedValueOnce(page('B', [100]))
    await history.load('B')
    expect(history.error.value).toBe('')
    expect(history.chunks.value.map((item) => item.content)).toEqual(['B:100'])
  })

  it('fences A/B/A loads by generation rather than Run ID alone', async () => {
    const oldA = deferredPage()
    const oldB = deferredPage()
    listRunReasoning.mockReturnValueOnce(oldA.promise).mockReturnValueOnce(oldB.promise).mockResolvedValueOnce(page('A', [300], 300))
    const history = useAgentReasoningHistory()
    const loadA = history.load('A')
    const loadB = history.load('B')
    await history.load('A')
    const latest = snapshot(history)
    oldA.resolve(page('A', [100], 100))
    oldB.resolve(page('B', [200], 200))
    await Promise.all([loadA, loadB])
    expect(snapshot(history)).toEqual(latest)
    listRunReasoning.mockResolvedValueOnce(page('A', [250]))
    await history.loadPrevious()
    expect(listRunReasoning).toHaveBeenLastCalledWith('A', { beforeSequence: 300, limit: 100 })
    expect(history.chunks.value.map((item) => item.content)).toEqual(['A:250', 'A:300'])
  })

  it.each(['success', 'failure'] as const)('keeps the latest same-Run reload when an earlier load returns %s', async (outcome) => {
    const old = deferredPage()
    listRunReasoning.mockReturnValueOnce(old.promise).mockResolvedValueOnce(page('A', [300], 300))
    const history = useAgentReasoningHistory()
    const oldLoad = history.load('A')
    await history.load('A')
    const latest = snapshot(history)
    if (outcome === 'success') old.resolve(page('A', [100], 100))
    else old.reject(new Error('superseded reload failed'))
    await oldLoad
    expect(snapshot(history)).toEqual(latest)
    listRunReasoning.mockResolvedValueOnce(page('A', [250]))
    await history.loadPrevious()
    expect(listRunReasoning).toHaveBeenLastCalledWith('A', { beforeSequence: 300, limit: 100 })
  })

  it.each(['success', 'failure'] as const)('load(null) invalidates an initial request returning %s', async (outcome) => {
    const pending = deferredPage()
    listRunReasoning.mockReturnValueOnce(pending.promise)
    const history = useAgentReasoningHistory()
    const load = history.load('A')
    await history.load(null)
    if (outcome === 'success') pending.resolve(page('A', [100], 100))
    else pending.reject(new Error('old failure'))
    await load
    expect(snapshot(history)).toEqual({ chunks: [], hasPrevious: false, loading: false, error: '' })
    await history.loadPrevious()
    expect(listRunReasoning).toHaveBeenCalledTimes(1)
  })

  it.each(['success', 'failure'] as const)('drops an old previous-page %s after switching Runs', async (outcome) => {
    const previous = deferredPage()
    listRunReasoning.mockResolvedValueOnce(page('A', [100], 100)).mockReturnValueOnce(previous.promise).mockResolvedValueOnce(page('B', [300], 300))
    const history = useAgentReasoningHistory()
    await history.load('A')
    const older = history.loadPrevious()
    expect(listRunReasoning).toHaveBeenLastCalledWith('A', { beforeSequence: 100, limit: 100 })
    await history.load('B')
    const latest = snapshot(history)
    if (outcome === 'success') previous.resolve(page('A', [50], 50))
    else previous.reject(new Error('old page failure'))
    await older
    expect(snapshot(history)).toEqual(latest)
    listRunReasoning.mockResolvedValueOnce(page('B', [250]))
    await history.loadPrevious()
    expect(listRunReasoning).toHaveBeenLastCalledWith('B', { beforeSequence: 300, limit: 100 })
    expect(history.chunks.value.map((item) => item.content)).toEqual(['B:250', 'B:300'])
  })

  it.each(['success', 'failure'] as const)('old page %s/finally does not release a new page loading lock', async (outcome) => {
    const old = deferredPage()
    const current = deferredPage()
    listRunReasoning.mockResolvedValueOnce(page('A', [100], 100)).mockReturnValueOnce(old.promise).mockResolvedValueOnce(page('B', [300], 300)).mockReturnValueOnce(current.promise)
    const history = useAgentReasoningHistory()
    await history.load('A')
    const oldPage = history.loadPrevious()
    await history.load('B')
    const currentPage = history.loadPrevious()
    const latest = snapshot(history)
    if (outcome === 'success') old.resolve(page('A', [50], 50))
    else old.reject(new Error('old page failure'))
    await oldPage
    expect(snapshot(history)).toEqual(latest)
    expect(history.loading.value).toBe(true)
    await history.loadPrevious()
    expect(listRunReasoning).toHaveBeenCalledTimes(4)
    current.resolve(page('B', [250], 250))
    await currentPage
    expect(history.loading.value).toBe(false)
    expect(history.chunks.value.map((item) => item.content)).toEqual(['B:250', 'B:300'])
  })

  it('invalidates a previous page through A/B/A even when its Run ID matches again', async () => {
    const previous = deferredPage()
    listRunReasoning.mockResolvedValueOnce(page('A', [100], 100)).mockReturnValueOnce(previous.promise).mockResolvedValueOnce(page('B', [200], 200)).mockResolvedValueOnce(page('A', [300], 300))
    const history = useAgentReasoningHistory()
    await history.load('A')
    const older = history.loadPrevious()
    await history.load('B')
    await history.load('A')
    const latest = snapshot(history)
    previous.resolve(page('A', [50], 50))
    await older
    expect(snapshot(history)).toEqual(latest)
    listRunReasoning.mockResolvedValueOnce(page('A', [250]))
    await history.loadPrevious()
    expect(listRunReasoning).toHaveBeenLastCalledWith('A', { beforeSequence: 300, limit: 100 })
  })

  it('invalidates a pending previous page when the same Run reloads', async () => {
    const previous = deferredPage()
    listRunReasoning.mockResolvedValueOnce(page('A', [100], 100)).mockReturnValueOnce(previous.promise).mockResolvedValueOnce(page('A', [300], 300))
    const history = useAgentReasoningHistory()
    await history.load('A')
    const older = history.loadPrevious()
    await history.load('A')
    const latest = snapshot(history)
    previous.resolve(page('A', [50], 50))
    await older
    expect(snapshot(history)).toEqual(latest)
  })

  it.each(['success', 'failure'] as const)('load(null) invalidates a previous page returning %s', async (outcome) => {
    const previous = deferredPage()
    listRunReasoning.mockResolvedValueOnce(page('A', [100], 100)).mockReturnValueOnce(previous.promise)
    const history = useAgentReasoningHistory()
    await history.load('A')
    const older = history.loadPrevious()
    await history.load(null)
    if (outcome === 'success') previous.resolve(page('A', [50], 50))
    else previous.reject(new Error('old page failure'))
    await older
    expect(snapshot(history)).toEqual({ chunks: [], hasPrevious: false, loading: false, error: '' })
    await history.loadPrevious()
    expect(listRunReasoning).toHaveBeenCalledTimes(2)
  })

  it('deduplicates double clicks, retains all merged history, and stops at the terminal page', async () => {
    const previous = deferredPage()
    listRunReasoning.mockResolvedValueOnce(page('A', [101, 102], 101)).mockReturnValueOnce(previous.promise)
    const history = useAgentReasoningHistory()
    await history.load('A')
    const firstClick = history.loadPrevious()
    const secondClick = history.loadPrevious()
    expect(listRunReasoning).toHaveBeenCalledTimes(2)
    expect(history.loading.value).toBe(true)
    const older = page('A', [100, 99, 101], 99)
    older.items[2] = chunk('A', 101, 'overlapping older copy')
    previous.resolve(older)
    await Promise.all([firstClick, secondClick])
    expect(history.chunks.value.map((item) => item.content)).toEqual(['A:99', 'A:100', 'A:101', 'A:102'])
    expect(history.loading.value).toBe(false)
    listRunReasoning.mockResolvedValueOnce(page('A', [98]))
    await history.loadPrevious()
    expect(listRunReasoning).toHaveBeenLastCalledWith('A', { beforeSequence: 99, limit: 100 })
    expect(history.chunks.value.map((item) => item.sequence)).toEqual([98, 99, 100, 101, 102])
    await history.loadPrevious()
    expect(listRunReasoning).toHaveBeenCalledTimes(3)
  })

  it('retains the last successful history and cursor when the current page fails, then retries', async () => {
    listRunReasoning.mockResolvedValueOnce(page('A', [100], 100)).mockRejectedValueOnce(new Error('page failed')).mockResolvedValueOnce(page('A', [90]))
    const history = useAgentReasoningHistory()
    await history.load('A')
    await history.loadPrevious()
    expect(history.chunks.value.map((item) => item.content)).toEqual(['A:100'])
    expect(history.hasPrevious.value).toBe(true)
    expect(history.error.value).toBe('page failed')
    expect(history.loading.value).toBe(false)
    await history.loadPrevious()
    expect(listRunReasoning).toHaveBeenLastCalledWith('A', { beforeSequence: 100, limit: 100 })
    expect(history.chunks.value.map((item) => item.content)).toEqual(['A:90', 'A:100'])
    expect(history.error.value).toBe('')
  })
})

describe('reasoning page Run identity', () => {
  beforeEach(() => listRunReasoning.mockReset())

  it.each(['page', 'item'] as const)('rejects a foreign %s Run on the initial page without partial writes', async (identity) => {
    const invalid = page('A', [100, 101], 100)
    if (identity === 'page') invalid.run_id = 'B'
    else invalid.items[1] = chunk('B', 101)
    listRunReasoning.mockResolvedValueOnce(invalid)
    const history = useAgentReasoningHistory()
    await history.load('A')
    expect(history.chunks.value).toEqual([])
    expect(history.hasPrevious.value).toBe(false)
    expect(history.error.value).not.toBe('')
    expect(history.loading.value).toBe(false)
    await history.loadPrevious()
    expect(listRunReasoning).toHaveBeenCalledTimes(1)
    listRunReasoning.mockResolvedValueOnce(page('A', [100], 100))
    await history.load('A')
    expect(history.error.value).toBe('')
    expect(history.chunks.value.map((item) => item.runId)).toEqual(['A'])
  })

  it.each(['page', 'item'] as const)('rejects a foreign %s Run on an older page while retaining history and retry cursor', async (identity) => {
    const invalid = page('A', [50, 51], 50)
    if (identity === 'page') invalid.run_id = 'B'
    else invalid.items[1] = chunk('B', 51)
    listRunReasoning.mockResolvedValueOnce(page('A', [100], 100)).mockResolvedValueOnce(invalid)
    const history = useAgentReasoningHistory()
    await history.load('A')
    const initial = history.chunks.value.map((item) => ({ ...item }))
    await history.loadPrevious()
    expect(history.chunks.value).toEqual(initial)
    expect(history.hasPrevious.value).toBe(true)
    expect(history.error.value).not.toBe('')
    expect(history.loading.value).toBe(false)
    listRunReasoning.mockResolvedValueOnce(page('A', [90]))
    await history.loadPrevious()
    expect(listRunReasoning).toHaveBeenLastCalledWith('A', { beforeSequence: 100, limit: 100 })
    expect(history.chunks.value.map((item) => item.content)).toEqual(['A:90', 'A:100'])
    expect(history.error.value).toBe('')
  })
})