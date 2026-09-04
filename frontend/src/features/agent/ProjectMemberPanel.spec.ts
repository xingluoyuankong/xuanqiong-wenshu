import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  list: vi.fn(),
  add: vi.fn(),
  updateRole: vi.fn(),
  remove: vi.fn(),
}))

vi.mock('@/api/projectMembers', () => ({ ProjectMembersAPI: api }))

import ProjectMemberPanel from './ProjectMemberPanel.vue'

const owner = {
  id: 'owner-member', project_id: 'project-members', user_id: 1, role: 'owner' as const,
  created_at: '2026-09-04T00:00:00Z', updated_at: '2026-09-04T00:00:00Z', deleted_at: null,
}
const viewer = {
  id: 'viewer-member', project_id: 'project-members', user_id: 2, role: 'viewer' as const,
  created_at: '2026-09-04T00:00:00Z', updated_at: '2026-09-04T00:00:00Z', deleted_at: null,
}

describe('ProjectMemberPanel', () => {
  beforeEach(() => {
    api.list.mockReset()
    api.add.mockReset()
    api.updateRole.mockReset()
    api.remove.mockReset()
  })

  it('loads owner-first members and keeps owner controls disabled', async () => {
    api.list.mockResolvedValue({ members: [viewer, owner], count: 2, access_role: 'owner', can_manage: true })
    const wrapper = mount(ProjectMemberPanel, { props: { projectId: 'project-members', canManage: true } })
    await flushPromises()

    expect(wrapper.get('[data-testid="project-members-list"]').text()).toMatch(/用户 #1[\s\S]*用户 #2/)
    expect((wrapper.get('[data-testid="project-members-role-1"]').element as HTMLSelectElement).disabled).toBe(true)
    expect((wrapper.get('[data-testid="project-members-remove-1"]').element as HTMLButtonElement).disabled).toBe(true)
  })

  it('disables mutations for read-only members and exposes loaded member data', async () => {
    api.list.mockResolvedValue({ members: [owner, viewer], count: 2, access_role: 'viewer', can_manage: false })
    const wrapper = mount(ProjectMemberPanel, { props: { projectId: 'project-members' } })
    await flushPromises()

    expect(wrapper.find('[data-testid="project-members-readonly"]').exists()).toBe(true)
    expect((wrapper.get('[data-testid="project-members-add"]').element as HTMLButtonElement).disabled).toBe(true)
    expect((wrapper.get('[data-testid="project-members-role-2"]').element as HTMLSelectElement).disabled).toBe(true)
    expect(wrapper.emitted('loaded')?.[0]?.[0]).toEqual([owner, viewer])
  })

  it('adds a viewer through the API and emits the changed projection', async () => {
    api.list.mockResolvedValue({ members: [owner], count: 1, access_role: 'owner', can_manage: true })
    api.add.mockResolvedValue(viewer)
    const wrapper = mount(ProjectMemberPanel, { props: { projectId: 'project-members', canManage: true } })
    await flushPromises()

    await wrapper.get('[data-testid="project-members-user-id"]').setValue('2')
    await wrapper.get('[data-testid="project-members-add-form"]').trigger('submit')
    await flushPromises()

    expect(api.add).toHaveBeenCalledWith('project-members', { user_id: 2, role: 'viewer' })
    expect(wrapper.find('[data-member-user-id="2"]').exists()).toBe(true)
    expect(wrapper.emitted('changed')?.[0]?.[0]).toEqual([owner, viewer])
  })
})
