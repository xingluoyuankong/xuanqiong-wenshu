// AIMETA P=更新API客户端_更新日志接口|R=更新日志查询|NR=不含UI逻辑|E=api:updates|X=internal|A=updatesApi对象|D=axios|S=net|RD=./README.ai
// Using a relative path to avoid potential alias issues
import { buildAuthHeaders } from '@/stores/auth'
import { API_BASE_URL } from './config';
const authFetch = (input: RequestInfo | URL, init: RequestInit = {}) => fetch(input, { ...init, headers: buildAuthHeaders(init.headers) })

// A simplified request function for public endpoints that don't require authentication.
const publicRequest = async (url: string, options: RequestInit = {}) => {
  const response = await authFetch(url, { ...options });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Request failed, status code: ${response.status}`);
  }

  // For DELETE requests which might not have a body
  if (response.status === 204) {
    return;
  }

  return response.json();
};

export interface UpdateLog {
  id: number;
  content: string;
  created_at: string;
}

export const getLatestUpdates = (): Promise<UpdateLog[]> => {
  return publicRequest(`${API_BASE_URL}/api/updates/latest`);
};
// ===== 任务运行日志/进度流客户端（持久化 TaskRuntime SSE）=====
// 后端 /api/updates/stream/{task_id} 的 SSE frame：
//   event: log | progress | diagnostic | task_completed | task_failed | task_cancelled | ...
//   data : { task_id, event_id, event_type, status, stage, progress, message,
//            timestamp, channel, event_sequence, payload, level, metadata }
// 正文 content_delta 事件不会进入日志流（后端已排除），此处按频道严格分流。

import { connectSSE } from '@/utils/sseStream'
import type { SSEController } from '@/utils/sseStream'

export type TaskStreamChannel = 'content' | 'log' | 'progress' | 'diagnostic' | 'terminal' | 'task_runtime'

export interface TaskStreamEnvelope {
  task_id: string
  event_id: number
  event_type: string
  status: string | null
  stage: string | null
  progress: number | null
  message: string
  timestamp: string | null
  channel: TaskStreamChannel
  event_sequence: number
  payload: Record<string, unknown>
  level: string
  metadata: Record<string, unknown>
}

export interface TaskStreamCallbacks {
  onLog?: (envelope: TaskStreamEnvelope) => void
  onProgress?: (envelope: TaskStreamEnvelope) => void
  onDiagnostic?: (envelope: TaskStreamEnvelope) => void
  onTerminal?: (envelope: TaskStreamEnvelope) => void
  onEvent?: (eventType: string, envelope: TaskStreamEnvelope) => void
  onError?: (message: string) => void
}

const TERMINAL_EVENT_TYPES = new Set(['task_completed', 'task_failed', 'task_cancelled', 'task_stale'])

export function isTerminalStreamEvent(eventType: string): boolean {
  return TERMINAL_EVENT_TYPES.has(eventType)
}

export function isTaskStreamEnvelope(value: unknown): value is TaskStreamEnvelope {
  if (!value || typeof value !== 'object') return false
  const record = value as Record<string, unknown>
  return (
    typeof record.task_id === 'string' &&
    typeof record.event_id === 'number' &&
    typeof record.event_type === 'string' &&
    typeof record.event_sequence === 'number'
  )
}

export function streamTaskUrl(taskId: string, cursor = 0): string {
  const url = new URL(`${API_BASE_URL}/api/updates/stream/${encodeURIComponent(taskId)}`, window.location.origin)
  if (cursor > 0) url.searchParams.set('after_event_id', String(cursor))
  return url.toString()
}

export function connectTaskStream(
  taskId: string,
  callbacks: TaskStreamCallbacks,
  cursor = 0,
  maxRetries = 3,
): SSEController {
  return connectSSE(
    streamTaskUrl(taskId, cursor),
    {
      onRawEvent(eventType, raw) {
        if (!isTaskStreamEnvelope(raw)) return
        callbacks.onEvent?.(eventType, raw)
        // 终态以 event_type 为准：后端旧日志终态事件 channel 可能是 log，不能漏判。
        if (isTerminalStreamEvent(raw.event_type)) callbacks.onTerminal?.(raw)
        else if (raw.channel === 'log') callbacks.onLog?.(raw)
        else if (raw.channel === 'progress') callbacks.onProgress?.(raw)
        else if (raw.channel === 'diagnostic') callbacks.onDiagnostic?.(raw)
      },
      onError: (message) => callbacks.onError?.(message),
    },
    maxRetries,
  )
}

export interface ActiveTaskStream {
  task_id: string
  status: string
  stage: string | null
  progress: number
  message: string | null
  event_cursor: number
  updated_at: string | null
}

export const listActiveTaskStreams = async (): Promise<ActiveTaskStream[]> => {
  const data = await publicRequest(`${API_BASE_URL}/api/updates/stream/tasks`)
  return Array.isArray(data?.tasks) ? (data.tasks as ActiveTaskStream[]) : []
}

export const appendTaskStreamLog = async (
  taskId: string,
  message: string,
  level = 'info',
): Promise<{ success: boolean; task_id: string; status: string; event_cursor: number }> => {
  const params = new URLSearchParams({ message, level })
  return publicRequest(
    `${API_BASE_URL}/api/updates/stream/${encodeURIComponent(taskId)}/log?${params.toString()}`,
    { method: 'POST' },
  )
}

export const completeTaskStream = async (
  taskId: string,
): Promise<{ success: boolean; task_id: string; status: string }> => {
  return publicRequest(
    `${API_BASE_URL}/api/updates/stream/${encodeURIComponent(taskId)}/complete`,
    { method: 'POST' },
  )
}

export const createTaskStream = async (
  taskId?: string,
): Promise<{ task_id: string; status: string }> => {
  const query = taskId ? `?task_id=${encodeURIComponent(taskId)}` : ''
  return publicRequest(`${API_BASE_URL}/api/updates/stream/create${query}`, { method: 'POST' })
}

