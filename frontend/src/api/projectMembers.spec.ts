import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  buildAuthHeaders: vi.fn(() => ({ Authorization: 'Bearer member-test' })),
}))
vi.mock('@/stores/auth', () => ({ buildAuthHeaders: mocks.buildAuthHeaders }))

import { ProjectMembersAPI } from '@/api/projectMembers'

describe('ProjectMembersAPI', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    mocks.buildAuthHeaders.mockClear()
    vi.stubGlobal('fetch', fetchMock)
  })

  it('encodes project IDs and sends authenticated JSON mutations', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ members: [], count: 0 }),
    })
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: 'm-2', project_id: 'project/a', user_id: 2, role: 'editor' }),
    })

    await ProjectMembersAPI.list('project/a')
    await ProjectMembersAPI.add('project/a', { user_id: 2, role: 'editor' })

    expect(fetchMock.mock.calls[0][0]).toContain('/projects/project%2Fa/members')
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ credentials: 'include' })
    expect(fetchMock.mock.calls[1][1]).toMatchObject({
      method: 'POST',
      body: JSON.stringify({ user_id: 2, role: 'editor' }),
      headers: expect.objectContaining({
        Authorization: 'Bearer member-test',
        'Content-Type': 'application/json',
      }),
    })
  })

  it('surfaces the server detail for rejected membership mutations', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 422,
      json: async () => ({ detail: '项目所有者不可降级' }),
    })

    await expect(ProjectMembersAPI.updateRole('p', 1, { role: 'viewer' }))
      .rejects.toThrow('项目所有者不可降级')
  })
})
