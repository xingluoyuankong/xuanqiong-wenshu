import { API_BASE_URL } from '@/api/config'
import { buildAuthHeaders } from '@/stores/auth'

const TASK_RUNTIME_BASE = `${API_BASE_URL}/api/task-runtime`

export type TaskRuntimeStatus =
  | 'queued'
  | 'running'
  | 'cancelling'
  | 'cancelled'
  | 'succeeded'
  | 'failed'
  | 'stale'
  | string

export interface TaskRuntimeRead {
  task_id: string
  owner_user_id?: number | null
  project_id?: string | null
  chapter_id?: string | null
  task_type: string
  idempotency_key?: string | null
  status: TaskRuntimeStatus
  stage?: string | null
  progress: number
  message?: string | null
  event_cursor: number
  retry_count: number
  max_retries: number
  lease_owner?: string | null
  heartbeat_at?: string | null
  started_at?: string | null
  finished_at?: string | null
  elapsed_ms?: number | null
  input_tokens?: number | null
  output_tokens?: number | null
  total_tokens?: number | null
  error_code?: string | null
  error_detail?: string | null
  result_ref?: string | null
  payload?: Record<string, unknown> | null
  created_at: string
  updated_at: string
}

export interface TaskRuntimeEventRead {
  event_id: number
  task_id: string
  event_type: string
  status?: TaskRuntimeStatus | null
  stage?: string | null
  progress?: number | null
  message?: string | null
  idempotency_key?: string | null
  payload?: Record<string, unknown> | null
  created_at: string
}

const request = async <T>(url: string, init: RequestInit = {}): Promise<T> => {
  const response = await fetch(url, {
    credentials: 'include',
    ...init,
    headers: {
      Accept: 'application/json',
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      ...buildAuthHeaders(init.headers),
    },
  })
  if (!response.ok) {
    throw new Error(`任务状态请求失败（HTTP ${response.status}）`)
  }
  return response.json() as Promise<T>
}


export const TaskRuntimeAPI = {
  listTasks(filters: { projectId?: string; chapterId?: string; status?: TaskRuntimeStatus; limit?: number } = {}): Promise<TaskRuntimeRead[]> {
    const query = new URLSearchParams()
    if (filters.projectId) query.set('project_id', filters.projectId)
    if (filters.chapterId) query.set('chapter_id', filters.chapterId)
    if (filters.status) query.set('status', filters.status)
    query.set('limit', String(Math.min(500, Math.max(1, filters.limit ?? 100))))
    return request<TaskRuntimeRead[]>(`${TASK_RUNTIME_BASE}/tasks?${query.toString()}`)
  },

  getTask(taskId: string): Promise<TaskRuntimeRead> {
    return request<TaskRuntimeRead>(`${TASK_RUNTIME_BASE}/tasks/${encodeURIComponent(taskId)}`)
  },

  cancelTask(taskId: string): Promise<TaskRuntimeRead> {
    return request<TaskRuntimeRead>(`${TASK_RUNTIME_BASE}/tasks/${encodeURIComponent(taskId)}/cancel`, { method: 'POST' })
  },

  retryTask(taskId: string, idempotencyKey?: string): Promise<TaskRuntimeRead> {
    return request<TaskRuntimeRead>(`${TASK_RUNTIME_BASE}/tasks/${encodeURIComponent(taskId)}/retry`, {
      method: 'POST',
      body: JSON.stringify({ idempotency_key: idempotencyKey }),
    })
  },

  listEvents(taskId: string, afterEventId = 0, limit = 500): Promise<TaskRuntimeEventRead[]> {
    const query = new URLSearchParams({
      after_event_id: String(Math.max(0, afterEventId)),
      limit: String(Math.min(500, Math.max(1, limit))),
    })
    return request<TaskRuntimeEventRead[]>(
      `${TASK_RUNTIME_BASE}/tasks/${encodeURIComponent(taskId)}/events?${query.toString()}`
    )
  },

  streamUrl(taskId: string, afterEventId = 0): string {
    const query = new URLSearchParams({ after_event_id: String(Math.max(0, afterEventId)) })
    return `${TASK_RUNTIME_BASE}/tasks/${encodeURIComponent(taskId)}/stream?${query.toString()}`
  },
}
