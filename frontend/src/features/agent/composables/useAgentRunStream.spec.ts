import { describe, expect, it, vi } from 'vitest'
import type { AgentEvent } from '@/api/agent'
import { useAgentRunStream } from './useAgentRunStream'

const { connectMock } = vi.hoisted(() => ({ connectMock: vi.fn() }))
vi.mock('@/utils/sseStream', async () => {
  const actual = await vi.importActual<typeof import('@/utils/sseStream')>('@/utils/sseStream')
  return { ...actual, connectSSE: connectMock }
})

const event = (runId: string, sequence: number, eventType = 'progress_update'): AgentEvent => ({
  id: `${runId}-${sequence}`,
  run_id: runId,
  sequence,
  event_type: eventType,
  summary: `${runId}-${sequence}`,
  data: {},
  created_at: null,
})

describe('useAgentRunStream', () => {
  it('replays history in sequence order and starts SSE after the highest cursor', async () => {
    const stream = useAgentRunStream()
    const received: string[] = []
    const close = vi.fn()
    connectMock.mockReset().mockImplementation((_url: string, callbacks: { onConnectionState?: (state: string) => void }) => {
      callbacks.onConnectionState?.('live')
      return { close }
    })

    await stream.start({
      sessionId: 'session-1',
      runId: 'run-1',
      loadHistory: async () => [event('run-1', 3), event('run-1', 1), event('run-1', 2)],
      streamUrl: (cursor) => `/stream?cursor=${cursor}`,
      onEvent: (item, source) => received.push(`${source}:${item.sequence}`),
    })

    expect(received).toEqual(['history:1', 'history:2', 'history:3'])
    expect(connectMock).toHaveBeenCalledWith(
      '/stream?cursor=3',
      expect.any(Object),
      3,
      { cursorParam: 'after_sequence' },
    )
    expect(stream.activeRunId.value).toBe('run-1')
    expect(stream.connectionState.value).toBe('live')
    expect(close).not.toHaveBeenCalled()
  })

  it('does not open a live stream after a terminal history event', async () => {
    const stream = useAgentRunStream()
    const terminal = event('run-1', 4, 'run_completed')
    connectMock.mockReset()

    await stream.start({
      sessionId: 'session-1',
      runId: 'run-1',
      loadHistory: async () => [terminal],
      streamUrl: () => '/stream',
      onEvent: vi.fn(),
      onTerminal: vi.fn(),
    })

    expect(connectMock).not.toHaveBeenCalled()
    expect(stream.connectionState.value).toBe('terminal')
  })

  it('does not open a live stream when the durable Run status is already terminal', async () => {
    const stream = useAgentRunStream()
    connectMock.mockReset()

    await stream.start({
      sessionId: 'session-1',
      runId: 'run-1',
      initialStatus: 'completed',
      loadHistory: async () => [],
      streamUrl: () => '/stream',
      onEvent: vi.fn(),
    })

    expect(connectMock).not.toHaveBeenCalled()
    expect(stream.connectionState.value).toBe('terminal')
  })


  it('keeps the stream terminal after a terminal event and ignores later reconnect state', async () => {
    const stream = useAgentRunStream()
    let callbacks: { onRawEvent?: (eventType: string, payload: unknown) => void; onConnectionState?: (state: string) => void } = {}
    connectMock.mockReset().mockImplementation((_url: string, nextCallbacks: typeof callbacks) => {
      callbacks = nextCallbacks
      callbacks.onConnectionState?.('live')
      return { close: vi.fn() }
    })

    await stream.start({
      sessionId: 'session-1',
      runId: 'run-terminal',
      loadHistory: async () => [],
      streamUrl: () => '/stream',
      onEvent: vi.fn(),
    })
    callbacks.onRawEvent?.('run_completed', event('run-terminal', 1, 'run_completed'))
    callbacks.onConnectionState?.('reconnecting')

    expect(stream.connectionState.value).toBe('terminal')
  })

  it('forwards stream_error through its dedicated callback without reducing it as a live AgentEvent', async () => {
    const stream = useAgentRunStream()
    let callbacks: {
      onRawEvent?: (eventType: string, payload: unknown) => void
      onStreamError?: (data: { error_code: string; retryable: boolean; cursor?: number }) => void
    } = {}
    const events = vi.fn()
    const streamError = vi.fn()
    connectMock.mockReset().mockImplementation((_url: string, nextCallbacks: typeof callbacks) => {
      callbacks = nextCallbacks
      return { close: vi.fn() }
    })

    await stream.start({
      sessionId: 'session-1',
      runId: 'run-1',
      loadHistory: async () => [],
      streamUrl: () => '/stream',
      onEvent: events,
      onStreamError: streamError,
    })

    callbacks.onStreamError?.({
      error_code: 'AGENT_EVENT_LEDGER_UNAVAILABLE',
      retryable: true,
      cursor: 9,
    })

    expect(streamError).toHaveBeenCalledWith({
      error_code: 'AGENT_EVENT_LEDGER_UNAVAILABLE',
      retryable: true,
      cursor: 9,
    })
    expect(events).not.toHaveBeenCalled()
  })

  it('fences a late history response when a newer Run starts', async () => {
    const stream = useAgentRunStream()
    let resolveFirstHistory: (value: AgentEvent[]) => void = () => undefined
    const firstHistory = new Promise<AgentEvent[]>((resolve) => {
      resolveFirstHistory = resolve
    })
    const received: string[] = []
    connectMock.mockReset().mockReturnValue({ close: vi.fn() })

    const first = stream.start({
      sessionId: 'session-1',
      runId: 'run-old',
      loadHistory: () => firstHistory,
      streamUrl: () => '/old-stream',
      onEvent: (item) => received.push(item.run_id),
    })
    await stream.start({
      sessionId: 'session-1',
      runId: 'run-new',
      loadHistory: async () => [],
      streamUrl: () => '/new-stream',
      onEvent: (item) => received.push(item.run_id),
    })
    resolveFirstHistory([event('run-old', 1)])
    await first

    expect(received).toEqual([])
    expect(stream.activeRunId.value).toBe('run-new')
  })

  it('在没有新增历史事件时也从显式初始恢复游标启动 SSE', async () => {
    const stream = useAgentRunStream()
    connectMock.mockReset().mockReturnValue({ close: vi.fn() })

    await stream.start({
      sessionId: 'session-1',
      runId: 'run-1',
      initialAfterSequence: 7,
      loadHistory: async () => [],
      streamUrl: (cursor) => `/stream?cursor=${cursor}`,
      onEvent: vi.fn(),
    })

    expect(connectMock).toHaveBeenCalledWith(
      '/stream?cursor=7',
      expect.any(Object),
      3,
      { cursorParam: 'after_sequence' },
    )
  })

})
