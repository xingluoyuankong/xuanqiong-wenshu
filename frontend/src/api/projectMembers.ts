import { API_BASE_URL, API_PREFIX } from '@/api/config'
import { buildAuthHeaders } from '@/stores/auth'

const PROJECTS_BASE = `${API_BASE_URL}${API_PREFIX}/projects`

export type ProjectMemberRole = 'owner' | 'editor' | 'viewer'

export interface ProjectMember {
  id: string
  project_id: string
  user_id: number
  role: ProjectMemberRole
  created_at: string
  updated_at: string
  deleted_at?: string | null
}

export interface ProjectMemberListResponse {
  members: ProjectMember[]
  count: number
  access_role: ProjectMemberRole | 'admin'
  can_manage: boolean
}

export interface CreateProjectMemberInput {
  user_id: number
  role: Exclude<ProjectMemberRole, 'owner'>
}

export interface UpdateProjectMemberRoleInput {
  role: Exclude<ProjectMemberRole, 'owner'>
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
    let detail = ''
    try {
      const body = await response.json() as { detail?: unknown }
      detail = typeof body.detail === 'string' ? body.detail.trim() : ''
    } catch {
      // Preserve a useful HTTP-level error when a gateway returns a non-JSON body.
    }
    throw new Error(detail || `项目成员请求失败（HTTP ${response.status}）`)
  }

  return response.json() as Promise<T>
}

const membersUrl = (projectId: string) =>
  `${PROJECTS_BASE}/${encodeURIComponent(projectId)}/members`

export const ProjectMembersAPI = {
  list(projectId: string): Promise<ProjectMemberListResponse> {
    return request<ProjectMemberListResponse>(membersUrl(projectId))
  },

  add(projectId: string, input: CreateProjectMemberInput): Promise<ProjectMember> {
    return request<ProjectMember>(membersUrl(projectId), {
      method: 'POST',
      body: JSON.stringify(input),
    })
  },

  updateRole(projectId: string, userId: number, input: UpdateProjectMemberRoleInput): Promise<ProjectMember> {
    return request<ProjectMember>(`${membersUrl(projectId)}/${encodeURIComponent(String(userId))}`, {
      method: 'PATCH',
      body: JSON.stringify(input),
    })
  },

  remove(projectId: string, userId: number): Promise<ProjectMember> {
    return request<ProjectMember>(`${membersUrl(projectId)}/${encodeURIComponent(String(userId))}`, {
      method: 'DELETE',
    })
  },
}