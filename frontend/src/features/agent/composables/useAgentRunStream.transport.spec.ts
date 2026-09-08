import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useAgentRunStream } from './useAgentRunStream'

const e = (sequence: number, run_id: unknown = 'run-a', event_type = 'assistant_delta') => ({
  id: `e-${sequence}`, sequence, run_id, event_type, summary: '正文', data: { content: `片段${sequence}` }, created_at: null,
})
const frame = (payload: unknown, id: number, type = 'assistant_delta') => `id: ${id}\nevent: ${type}\ndata: ${JSON.stringify(payload)}\n\n`
const response = (body: string) => ({ ok: true, body: new ReadableStream<Uint8Array>({ start(c) { c.enqueue(new TextEncoder().encode(body)); c.close() } }) })
const streams: ReturnType<typeof useAgentRunStream>[] = []
async function fixture(history: unknown[] = [], initialAfterSequence = 0) {
  const stream = useAgentRunStream(); streams.push(stream)
  const onEvent = vi.fn(), onTerminal = vi.fn(), onStreamError = vi.fn()
  const options = { sessionId: 'session', runId: 'run-a', initialAfterSequence, loadHistory: async () => history as never[],
    streamUrl: (c: number) => `/stream?after_sequence=${c}`, onEvent, onTerminal, onStreamError }
  await stream.start(options)
  return { stream, onEvent, onTerminal, onStreamError, options }
}
const settle = () => vi.advanceTimersByTimeAsync(0)
describe('Run scope real fetch/SSE integration', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => { streams.splice(0).forEach(s => s.close()); vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks() })
  it('foreign terminal cannot poison the reconnect cursor or end the current Run', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(response(frame(e(1), 1) + frame(e(999, 'run-b', 'run_completed'), 999, 'run_completed'))).mockResolvedValue(response(''))
    vi.stubGlobal('fetch', fetcher)
    const f = await fixture(); await settle(); await vi.advanceTimersByTimeAsync(2000)
    expect(f.onEvent.mock.calls.map(([x]) => x.sequence)).toEqual([1])
    expect(f.onTerminal).not.toHaveBeenCalled()
    expect(fetcher).toHaveBeenCalledTimes(2)
    expect(String(fetcher.mock.calls[1][0])).toContain('after_sequence=1')
    expect(fetcher.mock.calls[1][1].headers['Last-Event-ID']).toBe('1')
  })
  it.each([null, '', 42])('explicit invalid owner %s is not a legacy owner omission', async owner => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(frame(e(1, owner), 1))))
    const f = await fixture(); await settle(); expect(f.onEvent).not.toHaveBeenCalled()
  })
  it('legacy omission is bound to the active URL Run while controls remain non-durable', async () => {
    const legacy = { ...e(1) } as Record<string, unknown>; delete legacy.run_id
    const control = { error_code: 'LEDGER_ERROR', retryable: true, cursor: 900 }
    const fetcher = vi.fn().mockResolvedValueOnce(response(frame(legacy, 1) + frame(control, 900, 'stream_error') + frame({ ...control, run_id: 'run-b' }, 900, 'stream_error'))).mockResolvedValue(response(''))
    vi.stubGlobal('fetch', fetcher)
    const f = await fixture(); await settle(); await vi.advanceTimersByTimeAsync(2000)
    expect(f.onEvent).toHaveBeenCalledWith({ ...legacy, run_id: 'run-a' }, 'live')
    expect(f.onStreamError).toHaveBeenCalledTimes(1)
    expect(fetcher.mock.calls[1][1].headers['Last-Event-ID']).toBe('1')
  })
  it('deduplicates history/reconnect and retains out of order gap events', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(response(frame(e(1), 1) + frame(e(3), 3) + frame(e(2), 2)))
      .mockResolvedValue(response(frame({ ...e(3), id: 'different-id' }, 3) + frame(e(4), 4)))
    vi.stubGlobal('fetch', fetcher)
    const f = await fixture([e(1), e(1)]); await settle(); await vi.advanceTimersByTimeAsync(2000)
    expect(f.onEvent.mock.calls.map(([x]) => x.sequence)).toEqual([1, 3, 2, 4])
  })
  it('same Run restart ignores late old fetch body and cancels that response', async () => {
    let resolveOld!: (value: ReturnType<typeof response>) => void
    const cancel = vi.fn()
    const old = new Promise<ReturnType<typeof response>>(resolve => { resolveOld = resolve })
    vi.stubGlobal('fetch', vi.fn().mockReturnValueOnce(old).mockResolvedValue(response(frame(e(2), 2))))
    const f = await fixture(); await f.stream.start(f.options); await settle()
    resolveOld({ ok: true, body: new ReadableStream<Uint8Array>({ start(c) { c.enqueue(new TextEncoder().encode(frame(e(900, 'run-a', 'run_completed'), 900, 'run_completed'))) }, cancel }) })
    await settle()
    expect(f.onEvent.mock.calls.map(([x]) => x.sequence)).toEqual([2])
    expect(f.onTerminal).not.toHaveBeenCalled()
    expect(cancel).toHaveBeenCalled()
  })
  it('frame type and id must agree with the durable envelope before cursor acknowledgement', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(response(frame(e(1), 1) + frame(e(2), 900) + frame(e(3), 3, 'run_completed'))).mockResolvedValue(response(''))
    vi.stubGlobal('fetch', fetcher)
    const f = await fixture(); await settle(); await vi.advanceTimersByTimeAsync(2000)
    expect(f.onEvent.mock.calls.map(([x]) => x.sequence)).toEqual([1])
    expect(fetcher.mock.calls[1][1].headers['Last-Event-ID']).toBe('1')
    expect(f.onTerminal).not.toHaveBeenCalled()
  })
  it('terminal cancels an open response and discards trailing same-chunk events', async () => {
    const cancel = vi.fn()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body: new ReadableStream<Uint8Array>({
      start(c) { c.enqueue(new TextEncoder().encode(frame(e(1, 'run-a', 'run_completed'), 1, 'run_completed') + frame(e(2), 2))) }, cancel,
    }) }))
    const f = await fixture(); await settle()
    expect(f.onEvent.mock.calls.map(([x]) => x.sequence)).toEqual([1])
    expect(f.onTerminal).toHaveBeenCalledTimes(1)
    expect(cancel).toHaveBeenCalledTimes(1)
  })
  it('duplicate-only reconnects exhaust the retry budget instead of resetting it indefinitely', async () => {
    const fetcher = vi.fn().mockResolvedValue(response(frame(e(1), 1))); vi.stubGlobal('fetch', fetcher)
    const f = await fixture(); await settle()
    await vi.advanceTimersByTimeAsync(30000)
    expect(fetcher).toHaveBeenCalledTimes(4)
    expect(f.onEvent).toHaveBeenCalledTimes(1)
    expect(f.stream.connectionState.value).toBe('disconnected')
  })
  it('deduplication survives 5000 sequential events without accepting an evicted old identity', async () => {
    const body = Array.from({ length: 5000 }, (_, i) => frame(e(i + 1), i + 1)).join('') + frame({ ...e(1), id: 'replayed' }, 1)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(body)))
    const f = await fixture(); await settle()
    expect(f.onEvent).toHaveBeenCalledTimes(5000)
  })
})
