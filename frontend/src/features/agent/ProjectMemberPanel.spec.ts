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

const member = (userId: number, role: 'owner' | 'editor' | 'viewer') => ({
  id: `${role}-member-${userId}`,
  project_id: 'project-members',
  user_id: userId,
  role,
  created_at: '2026-09-04T00:00:00Z',
  updated_at: '2026-09-04T00:00:00Z',
  deleted_at: null,
})

const owner = member(1, 'owner')
const editor = member(2, 'editor')
const viewer = member(3, 'viewer')
const listResponse = (access_role: 'owner' | 'editor' | 'viewer' | 'admin', can_manage: boolean, members = [owner, editor, viewer]) => ({
  members,
  count: members.length,
  access_role,
  can_manage,
})

describe('ProjectMemberPanel', () => {
  beforeEach(() => {
    api.list.mockReset()
    api.add.mockReset()
    api.updateRole.mockReset()
    api.remove.mockReset()
  })

  it.each([
    ['owner', true],
    ['editor', true],
    ['admin', true],
    ['viewer', false],
  ] as const)('按服务端 can_manage 正确呈现 %s 的管理矩阵', async (accessRole, canManage) => {
    api.list.mockResolvedValue(listResponse(accessRole, canManage))
    const wrapper = mount(ProjectMemberPanel, { props: { projectId: 'project-members' } })
    await flushPromises()

    expect(wrapper.find('[data-testid="project-members-readonly"]').exists()).toBe(!canManage)
    expect((wrapper.get('[data-testid="project-members-user-id"]').element as HTMLInputElement).disabled).toBe(!canManage)
    expect((wrapper.get('[data-testid="project-members-new-role"]').element as HTMLSelectElement).disabled).toBe(!canManage)
    await wrapper.get('[data-testid="project-members-user-id"]').setValue('99')
    expect((wrapper.get('[data-testid="project-members-add"]').element as HTMLButtonElement).disabled).toBe(!canManage)
    expect((wrapper.get('[data-testid="project-members-role-1"]').element as HTMLSelectElement).disabled).toBe(true)
    expect((wrapper.get('[data-testid="project-members-remove-1"]').element as HTMLButtonElement).disabled).toBe(true)
    expect((wrapper.get('[data-testid="project-members-role-2"]').element as HTMLSelectElement).disabled).toBe(!canManage)
    expect((wrapper.get('[data-testid="project-members-remove-2"]').element as HTMLButtonElement).disabled).toBe(!canManage)
    expect((wrapper.get('[data-testid="project-members-role-3"]').element as HTMLSelectElement).disabled).toBe(!canManage)
  })

  it('加载失败显示 403/404/通用错误，并可通过刷新恢复成员列表', async () => {
    for (const reason of [
      new Error('项目成员请求失败（HTTP 403）'),
      new Error('项目不存在（HTTP 404）'),
      new Error('网关暂时不可用'),
    ]) {
      api.list.mockRejectedValueOnce(reason).mockResolvedValueOnce(listResponse('owner', true, [owner]))
      const wrapper = mount(ProjectMemberPanel, { props: { projectId: 'project-members' } })
      await flushPromises()

      expect(wrapper.get('[data-testid="project-members-error"]').text()).toContain(reason.message)
      await wrapper.get('[data-testid="project-members-refresh"]').trigger('click')
      await flushPromises()
      expect(wrapper.find('[data-testid="project-members-error"]').exists()).toBe(false)
      expect(wrapper.find('[data-member-user-id="1"]').exists()).toBe(true)
      wrapper.unmount()
    }
  })

  it('添加成员失败后保留输入并可重试成功', async () => {
    api.list.mockResolvedValue(listResponse('owner', true, [owner]))
    api.add.mockRejectedValueOnce(new Error('添加成员被拒绝（HTTP 403）')).mockResolvedValueOnce(viewer)
    const wrapper = mount(ProjectMemberPanel, { props: { projectId: 'project-members' } })
    await flushPromises()

    await wrapper.get('[data-testid="project-members-user-id"]').setValue('3')
    await wrapper.get('[data-testid="project-members-new-role"]').setValue('viewer')
    await wrapper.get('[data-testid="project-members-add-form"]').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[data-testid="project-members-error"]').text()).toContain('添加成员被拒绝')
    expect((wrapper.get('[data-testid="project-members-user-id"]').element as HTMLInputElement).value).toBe('3')

    await wrapper.get('[data-testid="project-members-add-form"]').trigger('submit')
    await flushPromises()
    expect(api.add).toHaveBeenNthCalledWith(2, 'project-members', { user_id: 3, role: 'viewer' })
    expect(wrapper.find('[data-member-user-id="3"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="project-members-error"]').exists()).toBe(false)
  })

  it('角色更新失败后可重试成功并保留当前列表投影', async () => {
    api.list.mockResolvedValue(listResponse('editor', true, [owner, viewer]))
    api.updateRole.mockRejectedValueOnce(new Error('角色更新失败（HTTP 404）')).mockResolvedValueOnce({ ...viewer, role: 'editor' as const })
    const wrapper = mount(ProjectMemberPanel, { props: { projectId: 'project-members' } })
    await flushPromises()

    await wrapper.get('[data-testid="project-members-role-3"]').setValue('editor')
    await flushPromises()
    expect(wrapper.get('[data-testid="project-members-error"]').text()).toContain('角色更新失败')
    expect((wrapper.get('[data-testid="project-members-role-3"]').element as HTMLSelectElement).value).toBe('viewer')

    await wrapper.get('[data-testid="project-members-role-3"]').setValue('editor')
    await flushPromises()
    expect(api.updateRole).toHaveBeenNthCalledWith(2, 'project-members', 3, { role: 'editor' })
    expect((wrapper.get('[data-testid="project-members-role-3"]').element as HTMLSelectElement).value).toBe('editor')
    expect(wrapper.find('[data-testid="project-members-error"]').exists()).toBe(false)
  })

  it('移除成员失败后可重试成功，并在随后刷新 403 时收口为错误态', async () => {
    api.list.mockResolvedValueOnce(listResponse('owner', true, [owner, editor]))
    api.remove.mockRejectedValueOnce(new Error('移除成员失败（HTTP 403）')).mockResolvedValueOnce(editor)
    const wrapper = mount(ProjectMemberPanel, { props: { projectId: 'project-members' } })
    await flushPromises()

    await wrapper.get('[data-testid="project-members-remove-2"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="project-members-error"]').text()).toContain('移除成员失败')
    expect(wrapper.find('[data-member-user-id="2"]').exists()).toBe(true)

    await wrapper.get('[data-testid="project-members-remove-2"]').trigger('click')
    await flushPromises()
    expect(api.remove).toHaveBeenNthCalledWith(2, 'project-members', 2)
    expect(wrapper.find('[data-member-user-id="2"]').exists()).toBe(false)

    api.list.mockRejectedValueOnce(new Error('成员关系已失效（HTTP 403）'))
    await wrapper.get('[data-testid="project-members-refresh"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="project-members-error"]').text()).toContain('成员关系已失效')
    expect(wrapper.find('[data-member-user-id="2"]').exists()).toBe(false)
  })

  it('无项目时保持空状态且不请求服务', async () => {
    const wrapper = mount(ProjectMemberPanel, { props: { projectId: null } })
    await flushPromises()

    expect(api.list).not.toHaveBeenCalled()
    expect(wrapper.find('[data-testid="project-members-no-project"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="project-members-refresh"]').attributes('disabled')).toBeDefined()
  })
})
