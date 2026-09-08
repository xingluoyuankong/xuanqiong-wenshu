import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AgentEvent } from '@/api/agent'
import { useAgentRunStream } from './useAgentRunStream'

const { connectMock } = vi.hoisted(() => ({ connectMock: vi.fn() }))
vi.mock('@/utils/sseStream', async () => {
  const actual = await vi.importActual<typeof import('@/utils/sseStream')>('@/utils/sseStream')
  return { ...actual, connectSSE: connectMock }
})

const event = (sequence: number, run_id = 'run-a', event_type = 'assistant_delta') => ({
  id: `event-${sequence}`, run_id, sequence, event_type, summary: 'delta',
  data: { content: `片段${sequence}` }, created_at: null,
})
const frame = (payload: unknown, id = 1, type = 'assistant_delta') =>
  `id: ${id}\nevent: ${type}\ndata: ${JSON.stringify(payload)}\n\n`
const streams: ReturnType<typeof useAgentRunStream>[] = []

async function start(history: AgentEvent[] = [], initialAfterSequence = 0) {
  const stream = useAgentRunStream()
  streams.push(stream)
  const onEvent = vi.fn(), onTerminal = vi.fn(), onStreamError = vi.fn()
  const options = {
    sessionId: 'session-a',
    runId: 'run-a',
    initialAfterSequence,
    loadHistory: async () => history,
    streamUrl: (cursor: number) => `/stream?after_sequence=${cursor}`,
    onEvent,
    onTerminal,
    onStreamError,
  }
  await stream.start(options)
  return { stream, options, onEvent, onTerminal, onStreamError }
}

describe('Agent SSE live scope and durable replay', () => {
  beforeEach(() => connectMock.mockReset().mockReturnValue({ close: vi.fn() }))
  afterEach(() => { streams.splice(0).forEach((stream) => stream.close()); vi.restoreAllMocks() })

  it('rejects a foreign live terminal before it reaches the reducer or closes the current Run', async () => {
    const callbacks: { onRawEvent?: (eventType: string, payload: unknown) => void } = {}
    connectMock.mockImplementation((_url: string, nextCallbacks: typeof callbacks) => {
      callbacks.onRawEvent = nextCallbacks.onRawEvent
      return { close: vi.fn() }
    })
    const f = await start()

    callbacks.onRawEvent?.('assistant_delta', event(1))
    callbacks.onRawEvent?.('run_completed', event(999, 'run-b', 'run_completed'))

    expect(f.onEvent.mock.calls.map(([payload]) => payload.run_id)).toEqual(['run-a'])
    expect(f.onTerminal).not.toHaveBeenCalled()
    expect(f.stream.connectionState.value).toBe('connecting')
  })

  it('accepts a legacy durable payload without run_id because the stream URL owns scope', async () => {
    const callbacks: { onRawEvent?: (eventType: string, payload: unknown) => void } = {}
    connectMock.mockImplementation((_url: string, nextCallbacks: typeof callbacks) => {
      callbacks.onRawEvent = nextCallbacks.onRawEvent
      return { close: vi.fn() }
    })
    const f = await start()
    const legacyPayload = { ...event(1) }
    delete (legacyPayload as { run_id?: string }).run_id

    callbacks.onRawEvent?.('assistant_delta', legacyPayload)

    expect(f.onEvent).toHaveBeenCalledWith({ ...legacyPayload, run_id: 'run-a' }, 'live')
  })

  it('ignores a foreign stream_error but accepts a legacy stream_error without run_id', async () => {
    const callbacks: { onStreamError?: (data: { run_id?: string; error_code: string; retryable: boolean }) => void } = {}
    connectMock.mockImplementation((_url: string, nextCallbacks: typeof callbacks) => {
      callbacks.onStreamError = nextCallbacks.onStreamError
      return { close: vi.fn() }
    })
    const f = await start()

    callbacks.onStreamError?.({ run_id: 'run-b', error_code: 'FOREIGN', retryable: true })
    callbacks.onStreamError?.({ error_code: 'LEGACY', retryable: true })

    expect(f.onStreamError).toHaveBeenCalledTimes(1)
    expect(f.onStreamError).toHaveBeenCalledWith({ error_code: 'LEGACY', retryable: true })
  })

  it('deduplicates history, live replay, and reconnect by durable sequence', async () => {
    const callbacks: { onRawEvent?: (eventType: string, payload: unknown) => void } = {}
    connectMock.mockImplementation((_url: string, nextCallbacks: typeof callbacks) => {
      callbacks.onRawEvent = nextCallbacks.onRawEvent
      return { close: vi.fn() }
    })
    const f = await start([event(1), event(1)])

    callbacks.onRawEvent?.('assistant_delta', { ...event(1), id: 'replayed-with-new-id' })
    callbacks.onRawEvent?.('assistant_delta', event(2))
    callbacks.onRawEvent?.('assistant_delta', { ...event(2), id: 'replayed-again' })

    expect(f.onEvent.mock.calls.map(([payload]) => payload.sequence)).toEqual([1, 2])
  })

  it('fences a late old generation even when the next generation uses the same Run id', async () => {
    const generations: Array<{ onRawEvent?: (eventType: string, payload: unknown) => void }> = []
    connectMock.mockImplementation((_url: string, nextCallbacks: typeof generations[number]) => {
      generations.push(nextCallbacks)
      return { close: vi.fn() }
    })
    const f = await start()
    await f.stream.start(f.options)

    generations[0].onRawEvent?.('run_completed', event(900, 'run-a', 'run_completed'))
    generations[1].onRawEvent?.('assistant_delta', event(2))

    expect(f.onTerminal).not.toHaveBeenCalled()
    expect(f.onEvent.mock.calls.map(([payload]) => payload.sequence)).toEqual([2])
  })

  it('filters a foreign history terminal before calculating the replay cursor', async () => {
    const f = await start([event(999, 'run-b', 'run_completed'), event(1)])

    expect(f.onEvent.mock.calls.map(([payload]) => payload.run_id)).toEqual(['run-a'])
    expect(connectMock).toHaveBeenCalledWith(
      '/stream?after_sequence=1',
      expect.any(Object),
      3,
      { cursorParam: 'after_sequence' },
    )
  })

  it('does not treat a duplicate terminal as a second terminal callback', async () => {
    const callbacks: { onRawEvent?: (eventType: string, payload: unknown) => void } = {}
    connectMock.mockImplementation((_url: string, nextCallbacks: typeof callbacks) => {
      callbacks.onRawEvent = nextCallbacks.onRawEvent
      return { close: vi.fn() }
    })
    const f = await start()

    callbacks.onRawEvent?.('run_completed', event(3, 'run-a', 'run_completed'))
    callbacks.onRawEvent?.('run_completed', event(3, 'run-a', 'run_completed'))

    expect(f.onTerminal).toHaveBeenCalledTimes(1)
    expect(f.onEvent).toHaveBeenCalledTimes(1)
  })
})
