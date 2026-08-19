import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/utils/sseStream', () => ({
  connectSSE: vi.fn(() => ({ close: vi.fn() })),
}))

import { connectSSE } from '@/utils/sseStream'
import {
  connectTaskStream,
  isTaskStreamEnvelope,
  isTerminalStreamEvent,
  streamTaskUrl,
  type TaskStreamEnvelope,
} from './updates'

const envelope = (eventType: string, channel: TaskStreamEnvelope['channel'] = 'log'): TaskStreamEnvelope => ({
  task_id: 'task-1',
  event_id: 10,
  event_type: eventType,
  status: 'running',
  stage: 'draft',
  progress: 33,
  message: 'm',
  timestamp: null,
  channel,
  event_sequence: 10,
  payload: {},
  level: 'info',
  metadata: {},
})

describe('task stream client', () => {
  beforeEach(() => vi.clearAllMocks())

  it('distinguishes terminal events regardless of channel', () => {
    const onTerminal = vi.fn()
    const onLog = vi.fn()
    connectTaskStream('task-1', { onTerminal, onLog })
    const options = vi.mocked(connectSSE).mock.calls[0][1] as unknown as {
      onRawEvent?: (eventType: string, data: unknown) => void
    }
    options.onRawEvent?.('task_completed', envelope('task_completed', 'log'))
    expect(onTerminal).toHaveBeenCalledTimes(1)
    expect(onLog).not.toHaveBeenCalled()
  })

  it('routes log/progress/diagnostic by channel', () => {
    const callbacks = { onLog: vi.fn(), onProgress: vi.fn(), onDiagnostic: vi.fn() }
    connectTaskStream('task-1', callbacks)
    const options = vi.mocked(connectSSE).mock.calls[0][1] as unknown as {
      onRawEvent?: (eventType: string, data: unknown) => void
    }
    options.onRawEvent?.('log', envelope('log', 'log'))
    options.onRawEvent?.('progress', envelope('progress', 'progress'))
    options.onRawEvent?.('diagnostic', envelope('diagnostic', 'diagnostic'))
    expect(callbacks.onLog).toHaveBeenCalledTimes(1)
    expect(callbacks.onProgress).toHaveBeenCalledTimes(1)
    expect(callbacks.onDiagnostic).toHaveBeenCalledTimes(1)
  })

  it('builds stream url with resume cursor', () => {
    const url = streamTaskUrl('task/1', 17)
    expect(url).toContain('/api/updates/stream/task%2F1')
    expect(url).toContain('after_event_id=17')
    expect(streamTaskUrl('task/1')).not.toContain('after_event_id')
  })

  it('validates envelope shape and terminal event type', () => {
    expect(isTaskStreamEnvelope(envelope('log'))).toBe(true)
    expect(isTaskStreamEnvelope({ event_id: 1 })).toBe(false)
    expect(isTerminalStreamEvent('task_failed')).toBe(true)
    expect(isTerminalStreamEvent('log')).toBe(false)
  })
})
