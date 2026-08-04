// SSE流式连接工具 - 用于实时接收后端进度推送

export interface SSECallback {
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

export function connectSSE(
  url: string,
  callbacks: SSECallback,
  maxRetries = 3
): SSEController {
  let retryCount = 0
  let aborted = false
  let reader: ReadableStreamDefaultReader<Uint8Array> | null = null

  const controller = new AbortController()

  const connect = async () => {
    try {
      const response = await fetch(url, {
        signal: controller.signal,
        headers: { Accept: 'text/event-stream' },
      })

      if (!response.ok) {
        callbacks.onError?.(`SSE连接失败: HTTP ${response.status}`)
        return
      }

      reader = response.body?.getReader() ?? null
      if (!reader) {
        callbacks.onError?.('SSE: 无法获取响应流')
        return
      }

      const decoder = new TextDecoder()
      let buffer = ''

      while (!aborted) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        let eventType = ''
        let dataBuffer = ''

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            eventType = line.slice(7).trim()
          } else if (line.startsWith('data: ')) {
            dataBuffer += line.slice(6)
          } else if (line === '' && dataBuffer) {
            try {
              const parsed = JSON.parse(dataBuffer)
              callbacks.onRawEvent?.(eventType, parsed)

              if (eventType === 'status_update') {
                callbacks.onStatusUpdate?.(parsed as StreamStatusData)
              } else if (eventType === 'complete') {
                callbacks.onComplete?.(parsed as StreamCompleteData)
              }
            } catch {
              // skip unparseable events
            }
            eventType = ''
            dataBuffer = ''
          }
        }
      }
    } catch (err: unknown) {
      if (!aborted) {
        const message = err instanceof Error ? err.message : '未知SSE错误'
        callbacks.onError?.(message)

        if (retryCount < maxRetries) {
          retryCount++
          setTimeout(connect, 2000 * retryCount)
        }
      }
    }
  }

  connect()

  return {
    close: () => {
      aborted = true
      controller.abort()
      reader?.cancel().catch(() => {})
    },
  }
}

