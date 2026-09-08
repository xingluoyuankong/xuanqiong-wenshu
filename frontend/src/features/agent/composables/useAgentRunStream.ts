import { ref, shallowRef } from 'vue'
import type { AgentEvent } from '@/api/agent'
import {
  connectSSE,
  type SSEConnectionState,
  type SSEController,
  type StreamErrorData,
} from '@/utils/sseStream'

export interface AgentRunStreamStartOptions {
  sessionId: string
  runId: string
  initialStatus?: string | null
  /** Resume only after a cursor already covered by the local event projection. */
  initialAfterSequence?: number
  loadHistory: () => Promise<AgentEvent[]>
  streamUrl: (afterSequence: number) => string
  isCurrent?: () => boolean
  onEvent: (event: AgentEvent, source: 'history' | 'live') => void
  onConnectionState?: (state: SSEConnectionState) => void
  onTerminal?: (eventType: string, payload: unknown) => void
  /** Non-durable transport control event; never feed it into AgentEvent reducers. */
  onStreamError?: (data: StreamErrorData) => void
  onError?: (message: string) => void
}

const DEFAULT_TERMINAL_EVENTS = new Set(['run_completed', 'run_failed', 'run_cancelled'])
const DEFAULT_TERMINAL_RUN_STATUSES = new Set(['completed', 'failed', 'cancelled'])

/**
 * Owns exactly one Agent Run SSE lifecycle at a time.  Durable history replay
 * and live events use the same callback, and every callback is fenced by a
 * generation token so a late response from an older Run is discarded.
 */
export function useAgentRunStream() {
  const controller = shallowRef<SSEController | null>(null)
  const connectionState = ref<SSEConnectionState>('closed')
  const activeRunId = ref('')
  let generation = 0

  const close = () => {
    generation += 1
    controller.value?.close()
    controller.value = null
    activeRunId.value = ''
    connectionState.value = 'closed'
  }

  const start = async (options: AgentRunStreamStartOptions): Promise<void> => {
    const runGeneration = ++generation
    controller.value?.close()
    controller.value = null
    activeRunId.value = options.runId
    connectionState.value = 'connecting'
    options.onConnectionState?.('connecting')
    const terminalEvents = DEFAULT_TERMINAL_EVENTS
    let terminalSeen = false
    // A run-scoped URL supplies ownership only for legacy objects that OMIT run_id.
    // Explicit null/empty/non-string owners remain invalid, not legacy defaults.
    const normalizeEvent = (payload: unknown, eventType?: string): AgentEvent | null => {
      if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return null
      const record = payload as Record<string, unknown>
      if ('run_id' in record && record.run_id !== options.runId) return null
      if (!Number.isSafeInteger(record.sequence) || (record.sequence as number) <= 0) return null
      if (typeof record.event_type !== 'string' || !record.event_type) return null
      if (eventType !== undefined && record.event_type !== eventType) return null
      return { ...record, run_id: options.runId } as unknown as AgentEvent
    }
    const requestedCursor = Number(options.initialAfterSequence)
    const initialCursor = Number.isSafeInteger(requestedCursor) && requestedCursor >= 0 ? requestedCursor : 0
    // Compact contiguous prefix; retain only out-of-order identities above it.
    let contiguous = initialCursor
    const pending = new Set<number>()
    const wasSeen = (sequence: number) => sequence <= contiguous || pending.has(sequence)
    const deliver = (event: AgentEvent, source: 'history' | 'live') => {
      if (wasSeen(event.sequence)) return false
      options.onEvent(event, source)
      pending.add(event.sequence)
      while (pending.delete(contiguous + 1)) contiguous += 1
      return true
    }
    const isCurrent = () =>
      generation === runGeneration &&
      activeRunId.value === options.runId &&
      (options.isCurrent?.() ?? true)

    try {
      const history = (await options.loadHistory())
        .map(event => normalizeEvent(event))
        .filter((event): event is AgentEvent => event !== null)
        .sort((left, right) => left.sequence - right.sequence)
      if (!isCurrent()) return

      for (const event of history) {
        if (!isCurrent()) return
        deliver(event, 'history')
      }
      if (!isCurrent()) return
      const historyCursor = history.reduce((max, event) => Math.max(max, event.sequence), 0)
      const cursor = Math.max(initialCursor, historyCursor)
      const historyTerminal = history.find((event) => terminalEvents.has(event.event_type))
      if (historyTerminal || DEFAULT_TERMINAL_RUN_STATUSES.has(String(options.initialStatus || ''))) {
        connectionState.value = 'terminal'
        options.onConnectionState?.('terminal')
        if (historyTerminal) options.onTerminal?.(historyTerminal.event_type, historyTerminal)
        return
      }

      const nextController = connectSSE(
        options.streamUrl(cursor),
        {
          acceptEvent: (eventType, payload, eventId) => {
            if (!isCurrent() || terminalSeen) return false
            if (eventType === 'stream_error') {
              if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return false
              const record = payload as Record<string, unknown>
              return !('run_id' in record) || record.run_id === options.runId
            }
            const event = normalizeEvent(payload, eventType)
            return event !== null && !wasSeen(event.sequence) && (eventId === null || eventId === event.sequence)
          },
          isTerminalEvent: (eventType, payload) =>
            isCurrent() && normalizeEvent(payload, eventType) !== null && terminalEvents.has(eventType),
          onConnectionState: (state) => {
            if (!isCurrent() || terminalSeen) return
            connectionState.value = state
            options.onConnectionState?.(state)
          },
          onRawEvent: (eventType, payload) => {
            if (!isCurrent() || terminalSeen) return
            const event = normalizeEvent(payload, eventType)
            if (!event || !deliver(event, 'live')) return
            if (!isCurrent()) return
            if (terminalEvents.has(eventType)) {
              terminalSeen = true
              connectionState.value = 'terminal'
              options.onConnectionState?.('terminal')
              options.onTerminal?.(eventType, event)
            }
          },
          onStreamError: (data) => {
            if (isCurrent() && !terminalSeen && (!('run_id' in data) || data.run_id === options.runId)) options.onStreamError?.(data)
          },
          onError: (message) => {
            if (isCurrent()) options.onError?.(message)
          },
        },
        3,
        { cursorParam: 'after_sequence' },
      )
      if (!isCurrent()) {
        nextController.close()
        return
      }
      controller.value = nextController
    } catch (error) {
      if (!isCurrent()) return
      connectionState.value = 'disconnected'
      options.onConnectionState?.('disconnected')
      options.onError?.(error instanceof Error ? error.message : '无法读取运行事件')
    }
  }

  return {
    controller,
    connectionState,
    activeRunId,
    start,
    close,
  }
}

export type AgentRunStream = ReturnType<typeof useAgentRunStream>