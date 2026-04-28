// AIMETA P=管理员API客户端_管理接口调用|R=用户管理_系统配置_统计|NR=不含UI逻辑|E=api:admin|X=internal|A=adminApi对象|D=axios|S=net|RD=./README.ai
import type { NovelSectionResponse, NovelSectionType } from '@/api/novel'
import { API_BASE_URL, ADMIN_API_PREFIX } from '@/api/config'

// API 配置

// 统一请求封装
const resolveErrorDetail = (payload: unknown): string | undefined => {
  if (!payload) return undefined
  if (typeof payload === 'string') return payload.trim() || undefined
  if (typeof payload !== 'object') return undefined
  const record = payload as Record<string, unknown>
  const detail = record.detail
  if (typeof detail === 'string' && detail.trim()) return detail.trim()
  if (detail && typeof detail === 'object') {
    const detailRecord = detail as Record<string, unknown>
    const message = detailRecord.message
    if (typeof message === 'string' && message.trim()) return message.trim()
  }
  const message = record.message
  if (typeof message === 'string' && message.trim()) return message.trim()
  return undefined
}

const toReadableError = (status: number, detail?: string): string => {
  if (detail) return detail
  if (status === 429) return '请求过于频繁，请稍后重试'
  if (status === 503) return 'AI 服务暂时不可用，请稍后重试'
  if (status >= 500) return '服务暂时不可用，请稍后重试'
  return `请求失败，状态码: ${status}`
}

const request = async (url: string, options: RequestInit = {}) => {
  const headers = new Headers({
    'Content-Type': 'application/json',
    ...options.headers
  })

  let response: Response
  try {
    response = await fetch(url, { ...options, headers })
  } catch {
    throw new Error('网络连接失败，请检查网络后重试')
  }

  if (!response.ok) {
    const requestId = response.headers.get('X-Request-ID') || undefined
    const rawText = await response.text().catch(() => '')
    let errorData: unknown = {}
    let responseSnippet: string | undefined
    try {
      errorData = rawText ? JSON.parse(rawText) : {}
    } catch {
      const trimmed = rawText.trim()
      responseSnippet = trimmed ? trimmed.slice(0, 220) : undefined
    }
    const detail = resolveErrorDetail(errorData)
    const lines = [toReadableError(response.status, detail)]
    const record = (errorData && typeof errorData === 'object') ? (errorData as Record<string, any>) : null
    const rawDetail = record?.detail && typeof record.detail === 'object' ? (record.detail as Record<string, any>) : null
    const code = typeof rawDetail?.code === 'string' ? rawDetail.code.trim() : ''
    const hint = typeof rawDetail?.hint === 'string' ? rawDetail.hint.trim() : ''
    const rootCause = typeof rawDetail?.root_cause === 'string' ? rawDetail.root_cause.trim() : ''
    const requestIdFromBody =
      typeof rawDetail?.request_id === 'string' ? rawDetail.request_id.trim() : ''
    if (rootCause) lines.push(`根因: ${rootCause}`)
    if (code) lines.push(`错误码: ${code}`)
    if (requestIdFromBody || requestId) lines.push(`请求ID: ${requestIdFromBody || requestId}`)
    if (hint) lines.push(`建议: ${hint}`)
    if (responseSnippet) lines.push(`响应片段: ${responseSnippet}`)
    throw new Error(lines.join('\n'))
  }

  if (response.status === 204) {
    return
  }

  return response.json()
}

const adminRequest = (path: string, options: RequestInit = {}) =>
  request(`${API_BASE_URL}${ADMIN_API_PREFIX}${path}`, options)

// 类型定义
export interface Statistics {
  novel_count: number
  api_request_count: number
}

export interface RootCauseIncident {
  occurred_at: string
  source_log: string
  error_type: string
  error_message: string
  root_cause?: string | null
  request_id?: string | null
  path?: string | null
  status_code?: number | null
  stack_excerpt?: string | null
  hint?: string | null
  confidence: number
}

export interface RootCauseDiagnosticsResponse {
  generated_at: string
  scanned_logs: string[]
  primary_error_type: string
  primary_error_message: string
  root_cause?: string | null
  request_id?: string | null
  path?: string | null
  status_code?: number | null
  occurred_at?: string | null
  source_log?: string | null
  stack_excerpt?: string | null
  hint?: string | null
  confidence: number
  incidents: RootCauseIncident[]
}

export interface NovelProjectSummary {
  id: string
  title: string
  genre: string
  last_edited: string
  completed_chapters: number
  total_chapters: number
}

export interface AdminNovelSummary extends NovelProjectSummary {
  owner_id: number
  owner_username: string
}

export interface Chapter {
  chapter_number: number
  title: string
  summary: string
  content?: string | null
  status?: string
  version_id?: string | number | null
  versions?: any[]
  word_count?: number
}

export interface NovelProject {
  id: string
  user_id: number
  title: string
  initial_prompt: string
  conversation_history: any[]
  blueprint?: any
  chapters: Chapter[]
}

export interface PromptItem {
  id: number
  name: string
  title?: string | null
  content: string
  tags?: string[] | null
}

export interface PromptCreatePayload {
  name: string
  content: string
  title?: string
  tags?: string[]
}

export type PromptUpdatePayload = Partial<Omit<PromptCreatePayload, 'name'>>

export interface UpdateLog {
  id: number
  content: string
  created_at: string
  created_by?: string | null
  is_pinned: boolean
}

export interface UpdateLogPayload {
  content?: string
  is_pinned?: boolean
}

export interface ChapterRuntimeLogItem {
  chapter_number: number
  chapter_title?: string | null
  generation_status: string
  word_count: number
  run_id?: string | null
  progress_stage: string
  progress_message: string
  started_at?: string | null
  updated_at?: string | null
  summary_snapshot: Record<string, any>
  runtime_snapshot: Record<string, any>
  runtime_events: Array<Record<string, any>>
}

export interface NovelRuntimeLogItem {
  project_id: string
  project_title: string
  user_id: number
  chapter_count: number
  active_chapter?: number | null
  updated_at?: string | null
  chapters: ChapterRuntimeLogItem[]
}

export interface DailyRequestLimit {
  limit: number
}

export interface SystemConfig {
  key: string
  value: string
  description?: string | null
}

export interface SystemConfigUpsertPayload {
  value: string
  description?: string | null
}

export type SystemConfigUpdatePayload = Partial<SystemConfigUpsertPayload>

export class AdminAPI {
  private static request(path: string, options: RequestInit = {}) {
    return adminRequest(path, options)
  }

  // Overview
  static getStatistics(): Promise<Statistics> {
    return this.request('/stats')
  }

  static getRootCauseDiagnostics(): Promise<RootCauseDiagnosticsResponse> {
    return this.request('/diagnostics/root-cause')
  }

  // Novels
  static listNovels(): Promise<AdminNovelSummary[]> {
    return this.request('/novel-projects')
  }

  static getNovelDetails(projectId: string): Promise<NovelProject> {
    return this.request(`/novel-projects/${projectId}`)
  }

  static getNovelSection(projectId: string, section: NovelSectionType): Promise<NovelSectionResponse> {
    return this.request(`/novel-projects/${projectId}/sections/${section}`)
  }

  static getNovelChapter(projectId: string, chapterNumber: number): Promise<Chapter> {
    return this.request(`/novel-projects/${projectId}/chapters/${chapterNumber}`)
  }

  // Prompts
  static listPrompts(): Promise<PromptItem[]> {
    return this.request('/prompts')
  }

  static createPrompt(payload: PromptCreatePayload): Promise<PromptItem> {
    return this.request('/prompts', {
      method: 'POST',
      body: JSON.stringify(payload)
    })
  }

  static getPrompt(id: number): Promise<PromptItem> {
    return this.request(`/prompts/${id}`)
  }

  static updatePrompt(id: number, payload: PromptUpdatePayload): Promise<PromptItem> {
    return this.request(`/prompts/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload)
    })
  }

  static deletePrompt(id: number): Promise<void> {
    return this.request(`/prompts/${id}`, {
      method: 'DELETE'
    })
  }

  // Update logs
  static listUpdateLogs(): Promise<UpdateLog[]> {
    return this.request('/update-logs')
  }

  static createUpdateLog(payload: UpdateLogPayload & { content: string }): Promise<UpdateLog> {
    return this.request('/update-logs', {
      method: 'POST',
      body: JSON.stringify(payload)
    })
  }

  static updateUpdateLog(id: number, payload: UpdateLogPayload): Promise<UpdateLog> {
    return this.request(`/update-logs/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload)
    })
  }

  static deleteUpdateLog(id: number): Promise<void> {
    return this.request(`/update-logs/${id}`, {
      method: 'DELETE'
    })
  }

  static listRuntimeLogs(): Promise<NovelRuntimeLogItem[]> {
    return this.request('/runtime-logs')
  }

  // Settings
  static getDailyRequestLimit(): Promise<DailyRequestLimit> {
    return this.request('/settings/daily-request-limit')
  }

  static setDailyRequestLimit(limit: number): Promise<DailyRequestLimit> {
    return this.request('/settings/daily-request-limit', {
      method: 'PUT',
      body: JSON.stringify({ limit })
    })
  }

  static listSystemConfigs(): Promise<SystemConfig[]> {
    return this.request('/system-configs')
  }

  static upsertSystemConfig(key: string, payload: SystemConfigUpsertPayload): Promise<SystemConfig> {
    return this.request(`/system-configs/${key}`, {
      method: 'PUT',
      body: JSON.stringify({ key, ...payload })
    })
  }

  static patchSystemConfig(key: string, payload: SystemConfigUpdatePayload): Promise<SystemConfig> {
    return this.request(`/system-configs/${key}`, {
      method: 'PATCH',
      body: JSON.stringify(payload)
    })
  }

  static deleteSystemConfig(key: string): Promise<void> {
    return this.request(`/system-configs/${key}`, {
      method: 'DELETE'
    })
  }

}
