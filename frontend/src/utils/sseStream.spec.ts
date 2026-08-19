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

})
