import { afterEach, describe, expect, it, vi } from 'vitest'
import { connectSSE } from './sseStream'

describe('connectSSE', () => {
  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('flushes an unterminated final event and resumes from its cursor', async () => {
    vi.useFakeTimers()
    const encoder = new TextEncoder()
    const status = vi.fn()
    const readers = [
      {
        read: vi.fn()
          .mockResolvedValueOnce({
            done: false,
            value: encoder.encode(
              'id: 7\nevent: status_update\ndata: {"status":"running","progress_message":"resume","progress_stage":"draft","word_count":12,"updated_at":null,"runtime":{}}',
            ),
          })
          .mockResolvedValueOnce({ done: true, value: undefined }),
      },
      {
        read: vi.fn().mockResolvedValueOnce({ done: true, value: undefined }),
        cancel: vi.fn(),
      },
    ]
    const fetchMock = vi.fn(async () => ({
      ok: true,
      body: { getReader: () => readers[Math.min(fetchMock.mock.calls.length - 1, 1)] },
    }))
    vi.stubGlobal('fetch', fetchMock)

    const controller = connectSSE('/api/stream/task-1', { onStatusUpdate: status })
    await vi.waitFor(() => expect(status).toHaveBeenCalledTimes(1))
    await vi.advanceTimersByTimeAsync(2000)
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))

    const [url, init] = fetchMock.mock.calls[1] as unknown as [string, RequestInit]
    expect(url).toContain('after_event_id=7')
    expect((init.headers as Record<string, string>)['Last-Event-ID']).toBe('7')
    expect(status.mock.calls[0][0].progress_stage).toBe('draft')
    controller.close()
  })

  it('resumes an Agent event ledger with after_sequence instead of the legacy event-id cursor', async () => {
    vi.useFakeTimers()
    const encoder = new TextEncoder()
    const readers = [
      {
        read: vi.fn()
          .mockResolvedValueOnce({ done: false, value: encoder.encode('id: 11\nevent: assistant_delta\ndata: {\"content\":\"第一段\"}\n\n') })
          .mockResolvedValueOnce({ done: true, value: undefined }),
      },
      { read: vi.fn().mockResolvedValueOnce({ done: true, value: undefined }), cancel: vi.fn() },
    ]
    const fetchMock = vi.fn(async () => ({
      ok: true,
      body: { getReader: () => readers[Math.min(fetchMock.mock.calls.length - 1, 1)] },
    }))
    vi.stubGlobal('fetch', fetchMock)

    const controller = connectSSE(
      '/api/agent/sessions/session-1/runs/run-1/stream?after_sequence=0',
      { onRawEvent: vi.fn() },
      3,
      { cursorParam: 'after_sequence' },
    )
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    await vi.advanceTimersByTimeAsync(2000)
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))

    const [url, init] = fetchMock.mock.calls[1] as unknown as [string, RequestInit]
    expect(url).toContain('after_sequence=11')
    expect(url).not.toContain('after_event_id=')
    expect((init.headers as Record<string, string>)['Last-Event-ID']).toBe('11')
    controller.close()
  })

  it('routes stream_error outside the durable Agent event callback and keeps the last durable cursor', async () => {
    vi.useFakeTimers()
    const encoder = new TextEncoder()
    const readers = [
      {
        read: vi.fn()
          .mockResolvedValueOnce({
            done: false,
            value: encoder.encode(
              'id: 7\nevent: assistant_delta\ndata: {"id":"event-7","run_id":"run-1","sequence":7,"event_type":"assistant_delta","summary":"正文增量","data":{"content":"第一段"}}\n\nevent: stream_error\ndata: {"run_id":"run-1","error_code":"AGENT_EVENT_LEDGER_UNAVAILABLE","retryable":true,"cursor":7}\n\n',
            ),
          })
          .mockResolvedValueOnce({ done: true, value: undefined }),
      },
      { read: vi.fn().mockResolvedValueOnce({ done: true, value: undefined }), cancel: vi.fn() },
    ]
    const fetchMock = vi.fn(async () => ({
      ok: true,
      body: { getReader: () => readers[Math.min(fetchMock.mock.calls.length - 1, 1)] },
    }))
    vi.stubGlobal('fetch', fetchMock)
    const raw = vi.fn()
    const streamError = vi.fn()

    const controller = connectSSE('/api/agent/sessions/session-1/runs/run-1/stream?after_sequence=0', {
      onRawEvent: raw,
      onStreamError: streamError,
    }, 3, { cursorParam: 'after_sequence' })

    await vi.waitFor(() => expect(streamError).toHaveBeenCalledTimes(1))
    expect(raw).toHaveBeenCalledTimes(1)
    expect(raw).toHaveBeenCalledWith('assistant_delta', expect.objectContaining({ sequence: 7 }))
    expect(streamError).toHaveBeenCalledWith({
      run_id: 'run-1',
      error_code: 'AGENT_EVENT_LEDGER_UNAVAILABLE',
      retryable: true,
      cursor: 7,
    })

    await vi.advanceTimersByTimeAsync(2000)
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    const [url, init] = fetchMock.mock.calls[1] as unknown as [string, RequestInit]
    expect(url).toContain('after_sequence=7')
    expect((init.headers as Record<string, string>)['Last-Event-ID']).toBe('7')
    controller.close()
  })

  it('honors maxRetries when the server repeatedly closes an empty stream', async () => {
    vi.useFakeTimers()
    const fetchMock = vi.fn(async () => ({
      ok: true,
      body: { getReader: () => ({ read: vi.fn().mockResolvedValue({ done: true, value: undefined }) }) },
    }))
    const error = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    connectSSE('/api/stream/empty', { onError: error }, 2)
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    await vi.advanceTimersByTimeAsync(2000)
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    await vi.advanceTimersByTimeAsync(4000)
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3))
    await vi.advanceTimersByTimeAsync(10000)

    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(error).toHaveBeenCalledTimes(3)
  })

  it('does not reconnect after an Agent terminal event', async () => {
    vi.useFakeTimers()
    const encoder = new TextEncoder()
    const fetchMock = vi.fn(async () => ({
      ok: true,
      body: { getReader: () => ({
        read: vi.fn()
          .mockResolvedValueOnce({ done: false, value: encoder.encode('id: 9\nevent: run_completed\ndata: {\"status\":\"completed\"}\n\n') })
          .mockResolvedValueOnce({ done: true, value: undefined }),
      }) },
    }))
    vi.stubGlobal('fetch', fetchMock)
    const controller = connectSSE('/api/agent/stream', {
      isTerminalEvent: (event) => event === 'run_completed',
    })
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    await vi.advanceTimersByTimeAsync(10000)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    controller.close()
  })

  it('uses a fresh abort signal after reconnecting', async () => {
    vi.useFakeTimers()
    const encoder = new TextEncoder()
    const signals: AbortSignal[] = []
    const readers = [
      { read: vi.fn().mockResolvedValueOnce({ done: true, value: undefined }) },
      {
        read: vi.fn().mockResolvedValueOnce({
          done: false,
          value: encoder.encode('event: complete\ndata: {"status":"successful","word_count":1,"updated_at":null}\n\n'),
        }).mockResolvedValueOnce({ done: true, value: undefined }),
      },
    ]
    const fetchMock = vi.fn(async (_url: string, init: RequestInit) => {
      signals.push(init.signal as AbortSignal)
      return { ok: true, body: { getReader: () => readers[Math.min(fetchMock.mock.calls.length - 1, 1)] } }
    })
    vi.stubGlobal('fetch', fetchMock)

    const complete = vi.fn()
    const controller = connectSSE('/api/stream/reconnect', { onComplete: complete })
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    await vi.advanceTimersByTimeAsync(2000)
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))

    expect(signals[0]).not.toBe(signals[1])
    expect(signals[0].aborted).toBe(false)
    expect(complete).toHaveBeenCalledTimes(1)
    controller.close()
  })


  it('reports connecting, live, and disconnected when automatic reconnect is exhausted', async () => {
    vi.useFakeTimers()
    const states: string[] = []
    const fetchMock = vi.fn(async () => ({
      ok: true,
      body: { getReader: () => ({ read: vi.fn().mockResolvedValue({ done: true, value: undefined }) }) },
    }))
    vi.stubGlobal('fetch', fetchMock)

    connectSSE('/api/stream/state', {
      onConnectionState: (state) => states.push(state),
    }, 0)
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    await vi.advanceTimersByTimeAsync(1)

    expect(states).toEqual(['connecting', 'live', 'disconnected'])
  })

})
