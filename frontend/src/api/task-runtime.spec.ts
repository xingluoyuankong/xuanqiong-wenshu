import { afterEach, describe, expect, it, vi } from 'vitest'
import { TaskRuntimeAPI } from './task-runtime'

const task = {
  task_id: 'task-1',
  task_type: 'chapter_generation',
  status: 'running',
  progress: 20,
  event_cursor: 3,
  retry_count: 0,
  max_retries: 3,
  created_at: '2026-08-11T00:00:00Z',
  updated_at: '2026-08-11T00:00:01Z',
}

describe('TaskRuntimeAPI', () => {
  afterEach(() => vi.restoreAllMocks())

  it('lists tasks with project and status scope', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify([task]), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await TaskRuntimeAPI.listTasks({ projectId: 'project/1', status: 'running', limit: 2 })
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toContain('/api/task-runtime/tasks?')
    expect(url).toContain('project_id=project%2F1')
    expect(url).toContain('status=running')
    expect(url).toContain('limit=2')
    expect(init.credentials).toBe('include')
    expect(result[0].task_id).toBe('task-1')
  })

  it('uses authenticated POST for cancel and retry', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(task), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    await TaskRuntimeAPI.cancelTask('task/1')
    await TaskRuntimeAPI.retryTask('task/1', 'retry-key-1')

    expect(fetchMock).toHaveBeenCalledTimes(2)
    const [, cancelInit] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    const [retryUrl, retryInit] = fetchMock.mock.calls[1] as unknown as [string, RequestInit]
    expect(cancelInit.method).toBe('POST')
    expect(retryUrl).toContain('/tasks/task%2F1/retry')
    expect(JSON.parse(String(retryInit.body))).toEqual({ idempotency_key: 'retry-key-1' })
    expect(retryInit.credentials).toBe('include')
  })
})
