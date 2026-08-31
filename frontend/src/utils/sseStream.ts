import { getAccessToken } from '@/stores/auth'
// SSE 流式连接工具：支持鉴权、断线重连与 Last-Event-ID 游标续接。

export type SSEConnectionState = 'connecting' | 'live' | 'reconnecting' | 'disconnected' | 'terminal' | 'closed'

export interface SSECallback {
  /** Return true for a terminal event; terminal events stop automatic reconnect. */
  isTerminalEvent?: (event: string, data: unknown) => boolean
  onConnectionState?: (state: SSEConnectionState, retryCount: number) => void
  onStatusUpdate?: (data: StreamStatusData) => void
  onComplete?: (data: StreamCompleteData) => void
  onError?: (error: string) => void
  onRawEvent?: (event: string, data: unknown) => void
}

export interface StreamStatusData {
  status: string
  progress_message: string
  progress_stage: string
  word_count: number
  updated_at: string | null
  runtime: Record<string, unknown>
}

export interface StreamCompleteData {
  status: string
  word_count: number
  updated_at: string | null
}

export interface SSEController {
  close: () => void
}

/**
 * A stream endpoint owns its replay cursor name. Most legacy task streams use
 * after_event_id; the Agent event ledger uses its monotonic event sequence.
 */
export interface SSEOptions {
  cursorParam?: 'after_event_id' | 'after_sequence'
}

const withCursor = (url: string, cursor: number, cursorParam: SSEOptions['cursorParam'] = 'after_event_id'): string => {
  if (!cursor) return url
  const resolved = new URL(url, window.location.origin)
  resolved.searchParams.set(cursorParam, String(cursor))
  return resolved.toString()
}

export function connectSSE(url: string, callbacks: SSECallback, maxRetries = 3, options: SSEOptions = {}): SSEController {
  const cursorParam = options.cursorParam || 'after_event_id'
  let retryCount = 0
  let aborted = false
  let reader: ReadableStreamDefaultReader<Uint8Array> | null = null
  let lastEventId = 0
  let retryTimer: number | null = null
  let activeController: AbortController | null = null

  const scheduleReconnect = (message: string) => {
    if (aborted) return
    callbacks.onError?.(message)
    if (retryCount >= maxRetries) {
      callbacks.onConnectionState?.('disconnected', retryCount)
      return
    }
    retryCount += 1
    callbacks.onConnectionState?.('reconnecting', retryCount)
    retryTimer = window.setTimeout(() => {
      retryTimer = null
      void connect()
    }, 2000 * retryCount)
  }

  const connect = async (): Promise<void> => {
    if (aborted) return
    callbacks.onConnectionState?.(retryCount ? 'reconnecting' : 'connecting', retryCount)
    const controller = new AbortController()
    activeController = controller
    try {
      const response = await fetch(withCursor(url, lastEventId, cursorParam), {
        signal: controller.signal,
        credentials: 'include',
        headers: {
          Accept: 'text/event-stream',
          ...(lastEventId ? { 'Last-Event-ID': String(lastEventId) } : {}),
          ...(getAccessToken() ? { Authorization: `Bearer ${getAccessToken()}` } : {}),
        },
      })

      if (!response.ok) {
        scheduleReconnect(`SSE连接失败: HTTP ${response.status}`)
        return
      }

      reader = response.body?.getReader() ?? null
      if (!reader) {
        scheduleReconnect('SSE: 无法获取响应流')
        return
      }
      callbacks.onConnectionState?.('live', retryCount)

      const decoder = new TextDecoder()
      let buffer = ''
      let eventType = ''
      let dataBuffer = ''
      let pendingEventId: number | null = null
      let terminalSeen = false

      const dispatch = () => {
        if (!dataBuffer) {
          eventType = ''
          pendingEventId = null
          return
        }
        try {
          const parsed = JSON.parse(dataBuffer)
          if (pendingEventId !== null) lastEventId = Math.max(lastEventId, pendingEventId)
          // 只有真正收到可解析事件才算连接有效，避免空流断开时无限重连。
          retryCount = 0
          callbacks.onRawEvent?.(eventType, parsed)
          if (eventType === 'status_update') callbacks.onStatusUpdate?.(parsed as StreamStatusData)
          else if (eventType === 'complete') callbacks.onComplete?.(parsed as StreamCompleteData)
          if (callbacks.isTerminalEvent?.(eventType, parsed)) {
            terminalSeen = true
            aborted = true
            callbacks.onConnectionState?.('terminal', retryCount)
          }
        } catch {
          // 忽略单个不可解析事件，继续保持连接与游标。
        }
        eventType = ''
        dataBuffer = ''
        pendingEventId = null
      }

      while (!aborted) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''
        for (const rawLine of lines) {
          const line = rawLine.endsWith('\r') ? rawLine.slice(0, -1) : rawLine
          if (line.startsWith('id:')) {
            const parsedId = Number(line.slice(3).trim())
            if (Number.isFinite(parsedId) && parsedId >= 0) pendingEventId = parsedId
          } else if (line.startsWith('event:')) {
            eventType = line.slice(6).trim()
          } else if (line.startsWith('data:')) {
            const part = line.slice(5).trimStart()
            dataBuffer += dataBuffer ? `\n${part}` : part
          } else if (line === '') {
            dispatch()
          }
        }
      }
      // Some proxies close a stream without sending the final blank line.
      // Parse all remaining complete fields before dispatching the final event.
      if (buffer && !aborted) {
        for (const rawLine of buffer.split('\n')) {
          const line = rawLine.endsWith('\r') ? rawLine.slice(0, -1) : rawLine
          if (line.startsWith('id:')) {
            const parsedId = Number(line.slice(3).trim())
            if (Number.isFinite(parsedId) && parsedId >= 0) pendingEventId = parsedId
          } else if (line.startsWith('event:')) {
            eventType = line.slice(6).trim()
          } else if (line.startsWith('data:')) {
            const part = line.slice(5).trimStart()
            dataBuffer += dataBuffer ? `\n${part}` : part
          }
        }
      }
      if (!aborted) {
        dispatch()
        if (!terminalSeen) scheduleReconnect('SSE连接已断开，正在尝试续接')
      }
    } catch (err: unknown) {
      if (!aborted) scheduleReconnect(err instanceof Error ? err.message : '未知SSE错误')
    } finally {
      if (activeController === controller) activeController = null
    }
  }

  void connect()

  return {
    close: () => {
      aborted = true
      callbacks.onConnectionState?.('closed', retryCount)
      if (retryTimer !== null) window.clearTimeout(retryTimer)
      retryTimer = null
      activeController?.abort()
      if (reader && typeof reader.cancel === 'function') {
        void reader.cancel()
      }
    },
  }
}
