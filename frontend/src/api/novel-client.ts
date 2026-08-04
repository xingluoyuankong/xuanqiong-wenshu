// AIMETA P=小说API客户端_小说和章节接口|R=小说CRUD_章节管理_生成|NR=不含UI逻辑|E=api:novel-client|X=internal|A=novelApi对象|D=fetch|S=net|RD=./README.ai
// Phase 5.2 重构：从 novel.ts 提取的 API 客户端代码（工具函数 + API 类）
// 类型定义从 @/api/types/novel 导入

import { API_BASE_URL, API_PREFIX } from '@/api/config'
import { normalizeChapterContent } from '@/utils/chapterContent'
import type {
  ApiErrorDetail,
  NovelProject,
  NovelProjectSummary,
  Chapter,
  ChapterVersion,
  Blueprint,
  BlueprintGenerationResponse,
  BlueprintGenerationJobResponse,
  BlueprintGenerationError,
  OutlineGenerationJobResponse,
  StyleProfileJobResponse,
  StyleSourceUploadJobResponse,
  NovelImportJobResponse,
  NovelSectionType,
  NovelSectionResponse,
  ConverseResponse,
  UIControl,
  ChapterGenerationResponse,
  DeleteNovelsResponse,
  OptimizeRequest,
  OptimizeResponse,
  ApplyOptimizationResponse,
  EnhancedEmotionPoint,
  StoryTrajectoryAnalysis,
  CreativeGuidanceAnalysis,
  ComprehensiveAnalysis,
  ForeshadowingItem,
  ResearchConfig,
  ResearchArtifact,
  ResearchRunStatus} from '@/api/types/novel'

// ============================================================================
// 错误处理
// ============================================================================

export class ApiError extends Error {
  status: number
  detail: ApiErrorDetail

  constructor(detail: ApiErrorDetail) {
    super(formatApiErrorMessage(detail))
    this.name = 'ApiError'
    this.status = detail.status
    this.detail = detail
  }
}

// re-export ApiErrorDetail for backward compatibility
export type { ApiErrorDetail } from '@/api/types/novel'

const readText = (value: unknown): string | undefined => {
  if (typeof value !== 'string') return undefined
  const trimmed = value.trim()
  return trimmed || undefined
}

const getFallbackMessage = (status: number): string => {
  if (status === 429) return '请求过于频繁，请稍后重试'
  if (status === 503) return 'AI 服务暂时不可用，请稍后重试'
  if (status >= 500) return '服务暂时不可用，请稍后重试'
  return `请求失败，状态码: ${status}`
}

const buildApiErrorDetail = (
  status: number,
  payload: unknown,
  requestIdFromHeader?: string,
  responseSnippet?: string
): ApiErrorDetail => {
  const fallbackMessage = getFallbackMessage(status)
  if (!payload || typeof payload !== 'object') {
    return {
      status,
      message: fallbackMessage,
      requestId: readText(requestIdFromHeader),
      responseSnippet: readText(responseSnippet)
    }
  }

  const record = payload as Record<string, unknown>
  const rawDetail = (record.detail && typeof record.detail === 'object') ? record.detail as Record<string, unknown> : null
  const message =
    readText(rawDetail?.message) ??
    readText(record.detail) ??
    readText(record.message) ??
    readText((record.error as Record<string, unknown> | undefined)?.message) ??
    fallbackMessage

  return {
    status,
    message,
    code: readText(rawDetail?.code),
    hint: readText(rawDetail?.hint),
    rootCause: readText(rawDetail?.root_cause) ?? readText(rawDetail?.rootCause),
    requestId: readText(rawDetail?.request_id) ?? readText(rawDetail?.requestId) ?? readText(requestIdFromHeader),
    retryable: typeof rawDetail?.retryable === 'boolean' ? rawDetail.retryable : undefined,
    responseSnippet: readText(responseSnippet),
    rejectionSummary: rawDetail?.rejection_summary && typeof rawDetail.rejection_summary === 'object'
      ? rawDetail.rejection_summary as Record<string, any>
      : undefined,
    missingChapters: Array.isArray(rawDetail?.missing_chapters)
      ? rawDetail.missing_chapters.filter((item): item is number => typeof item === 'number')
      : undefined
  }
}

const formatApiErrorMessage = (detail: ApiErrorDetail): string => {
  const lines = [detail.message || getFallbackMessage(detail.status)]
  if (detail.rootCause) lines.push(`根因: ${detail.rootCause}`)
  if (detail.code) lines.push(`错误码: ${detail.code}`)
  if (detail.requestId) lines.push(`请求ID: ${detail.requestId}`)
  if (detail.hint) lines.push(`建议: ${detail.hint}`)
  if (detail.responseSnippet) lines.push(`响应片段: ${detail.responseSnippet}`)
  return lines.join('\n')
}

const request = async (url: string, options: RequestInit = {}) => {
  const headers = new Headers({
    'Content-Type': 'application/json',
    ...options.headers
  })

  if (options.body instanceof FormData) {
    headers.delete('Content-Type')
  }

  let response: Response
  try {
    response = await fetch(url, { ...options, headers })
  } catch {
    throw new Error('网络连接失败，请检查网络后重试')
  }

  if (!response.ok) {
    const requestIdFromHeader = response.headers.get('X-Request-ID') || undefined
    const rawText = await response.text().catch(() => '')
    let errorData: unknown = {}
    let responseSnippet: string | undefined
    try {
      errorData = rawText ? JSON.parse(rawText) : {}
    } catch {
      const trimmed = rawText.trim()
      responseSnippet = trimmed ? trimmed.slice(0, 220) : undefined
    }
    throw new ApiError(buildApiErrorDetail(response.status, errorData, requestIdFromHeader, responseSnippet))
  }

  return response.json()
}

// ============================================================================
// 数据规范化
// ============================================================================

const normalizeChapterVersion = (value: unknown): ChapterVersion => {
  if (typeof value === 'string') {
    return {
      id: undefined,
      content: normalizeChapterContent(value),
      style: '标准'
    }
  }

  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>
    const rawContent = typeof record.content === 'string'
      ? record.content
      : normalizeChapterContent(record)
    return {
      id: typeof record.id === 'number' ? record.id : undefined,
      content: normalizeChapterContent(rawContent),
      style: typeof record.style === 'string' ? record.style : '标准',
      evaluation: typeof record.evaluation === 'string' ? record.evaluation : undefined,
      metadata: record.metadata && typeof record.metadata === 'object'
        ? record.metadata as Record<string, any>
        : undefined
    }
  }

  return {
    id: undefined,
    content: '',
    style: '标准'
  }
}

const normalizeChapter = (chapter: Chapter): Chapter => ({
  ...chapter,
  content: chapter.content === null ? null : normalizeChapterContent(chapter.content),
  versions: Array.isArray(chapter.versions)
    ? chapter.versions.map((version) => normalizeChapterVersion(version))
    : null
})

const normalizeProject = (project: NovelProject): NovelProject => ({
  ...project,
  chapters: Array.isArray(project.chapters)
    ? project.chapters.map((chapter) => normalizeChapter(chapter))
    : []
})

const requestProject = async (url: string, options?: RequestInit): Promise<NovelProject> => {
  const project = await request(url, options)
  return normalizeProject(project as NovelProject)
}

const requestChapter = async (url: string, options?: RequestInit): Promise<Chapter> => {
  const chapter = await request(url, options)
  return normalizeChapter(chapter as Chapter)
}

// ============================================================================
// API 常量
// ============================================================================

const NOVELS_BASE = `${API_BASE_URL}${API_PREFIX}/novels`
const PROJECTS_BASE = `${API_BASE_URL}${API_PREFIX}/projects`
const PATCH_DIFF_BASE = `${API_BASE_URL}${API_PREFIX}`
const WRITER_PREFIX = '/api/writer'
const WRITER_BASE = `${API_BASE_URL}${WRITER_PREFIX}/novels`
const BLUEPRINT_LEGACY_POLL_INTERVAL_MS = 2000
const BLUEPRINT_LEGACY_MAX_POLL_ATTEMPTS = 900
const STYLE_PROFILE_POLL_INTERVAL_MS = 2000
const STYLE_PROFILE_MAX_POLL_ATTEMPTS = 900
const STYLE_SOURCE_UPLOAD_POLL_INTERVAL_MS = 2000
const STYLE_SOURCE_UPLOAD_MAX_POLL_ATTEMPTS = 900
const NOVEL_IMPORT_POLL_INTERVAL_MS = 2000
const NOVEL_IMPORT_MAX_POLL_ATTEMPTS = 900

const delay = (ms: number) => new Promise((resolve) => globalThis.setTimeout(resolve, ms))

const readBlueprintJobError = (status: BlueprintGenerationJobResponse): string => {
  const rawError = status.error
  if (!rawError) return status.progress_message || '蓝图生成失败，请稍后重试'
  if (typeof rawError === 'string') return rawError
  return rawError.detail || rawError.message || status.progress_message || '蓝图生成失败，请稍后重试'
}

const readStyleProfileJobError = (status: StyleProfileJobResponse): string => {
  const rawError = status.error
  if (!rawError) return status.progress_message || '文风画像生成失败，请稍后重试'
  if (typeof rawError === 'string') return rawError
  return rawError.detail || rawError.message || status.progress_message || '文风画像生成失败，请稍后重试'
}

const readStyleSourceUploadJobError = (status: StyleSourceUploadJobResponse): string => {
  const rawError = status.error
  if (!rawError) return status.progress_message || '文风素材导入失败，请稍后重试'
  if (typeof rawError === 'string') return rawError
  return rawError.detail || rawError.message || status.progress_message || '文风素材导入失败，请稍后重试'
}

const readNovelImportJobError = (status: NovelImportJobResponse): string => {
  const rawError = status.error
  if (!rawError) return status.progress_message || '旧稿导入失败，请稍后重试'
  if (typeof rawError === 'string') return rawError
  return rawError.detail || rawError.message || status.progress_message || '旧稿导入失败，请稍后重试'
}

// ============================================================================
// NovelAPI
// ============================================================================

export class NovelAPI {
  static async createNovel(title: string, initialPrompt: string): Promise<NovelProject> {
    return requestProject(NOVELS_BASE, {
      method: 'POST',
      body: JSON.stringify({ title, initial_prompt: initialPrompt })
    })
  }

  static async importNovel(file: File): Promise<{ id: string }> {
    let status = await NovelAPI.startNovelImport(file)

    for (let attempt = 0; attempt < NOVEL_IMPORT_MAX_POLL_ATTEMPTS; attempt += 1) {
      if (status.status === 'successful' && status.project_id) {
        return { id: status.project_id }
      }
      if (status.status === 'failed') {
        throw new Error(readNovelImportJobError(status))
      }
      if (status.status === 'cancelled') {
        throw new Error(status.progress_message || '旧稿导入已取消')
      }

      await delay(NOVEL_IMPORT_POLL_INTERVAL_MS)
      status = await NovelAPI.getNovelImportStatus(status.run_id)
    }

    throw new Error('旧稿导入后台任务等待超时，请稍后刷新项目列表查看结果。')
  }

  static async startNovelImport(file: File): Promise<NovelImportJobResponse> {
    const formData = new FormData()
    formData.append('file', file)
    return request(`${NOVELS_BASE}/import/start`, {
      method: 'POST',
      body: formData,
      headers: {
        // 让 browser 自动设置 Content-Type 为 multipart/form-data，不手动设置
      }
    })
  }

  static async getNovelImportStatus(runId?: string): Promise<NovelImportJobResponse> {
    const query = runId ? `?run_id=${encodeURIComponent(runId)}` : ''
    return request(`${NOVELS_BASE}/import/status${query}`)
  }

  static async cancelNovelImport(runId?: string): Promise<NovelImportJobResponse> {
    const query = runId ? `?run_id=${encodeURIComponent(runId)}` : ''
    return request(`${NOVELS_BASE}/import/cancel${query}`, { method: 'POST' })
  }

  static async getNovel(projectId: string): Promise<NovelProject> {
    return requestProject(`${NOVELS_BASE}/${projectId}`)
  }

  /**
   * 获取项目的所有章节
   */
  static async getChapters(projectId: string): Promise<{ chapters: Chapter[] }> {
    const project = await requestProject(`${NOVELS_BASE}/${projectId}`)
    return { chapters: Array.isArray(project.chapters) ? project.chapters : [] }
  }

  static async getChapter(projectId: string, chapterNumber: number): Promise<Chapter> {
    return requestChapter(`${NOVELS_BASE}/${projectId}/chapters/${chapterNumber}`)
  }

  static async getSection(projectId: string, section: NovelSectionType): Promise<NovelSectionResponse> {
    return request(`${NOVELS_BASE}/${projectId}/sections/${section}`)
  }

  static async converseConcept(
    projectId: string,
    userInput: any,
    conversationState: any = {}
  ): Promise<ConverseResponse> {
    const formattedUserInput = userInput || { id: null, value: null }
    return request(`${NOVELS_BASE}/${projectId}/concept/converse`, {
      method: 'POST',
      body: JSON.stringify({
        user_input: formattedUserInput,
        conversation_state: conversationState
      })
    })
  }

  static async generateBlueprint(projectId: string): Promise<BlueprintGenerationResponse> {
    const initialStatus = await NovelAPI.startBlueprintGeneration(projectId)
    let status = initialStatus

    for (let attempt = 0; attempt < BLUEPRINT_LEGACY_MAX_POLL_ATTEMPTS; attempt += 1) {
      if (status.status === 'successful' && status.blueprint) {
        return {
          blueprint: status.blueprint,
          ai_message: status.ai_message || '蓝图已生成，请确认后进入写作阶段。'
        }
      }
      if (status.status === 'failed') {
        throw new Error(readBlueprintJobError(status))
      }
      if (status.status === 'cancelled') {
        throw new Error(status.progress_message || '蓝图生成已取消')
      }

      await delay(BLUEPRINT_LEGACY_POLL_INTERVAL_MS)
      status = await NovelAPI.getBlueprintGenerationStatus(projectId)
    }

    throw new Error('蓝图后台任务等待超时，请稍后到生成状态中刷新结果。')
  }

  static async startBlueprintGeneration(
    projectId: string,
    options: { forceStage?: 'novel_outline' | 'chapter_outline' } = {}
  ): Promise<BlueprintGenerationJobResponse> {
    return request(`${NOVELS_BASE}/${projectId}/blueprint/generate/start`, {
      method: 'POST',
      body: JSON.stringify({
        force_stage: options.forceStage,
      })
    })
  }

  static async getBlueprintGenerationStatus(projectId: string): Promise<BlueprintGenerationJobResponse> {
    return request(`${NOVELS_BASE}/${projectId}/blueprint/generate/status`)
  }

  static async cancelBlueprintGeneration(projectId: string): Promise<BlueprintGenerationJobResponse> {
    return request(`${NOVELS_BASE}/${projectId}/blueprint/generate/cancel`, {
      method: 'POST'
    })
  }

  static async saveBlueprint(projectId: string, blueprint: Blueprint): Promise<NovelProject> {
    return requestProject(`${NOVELS_BASE}/${projectId}/blueprint/save`, {
      method: 'POST',
      body: JSON.stringify(blueprint)
    })
  }


  static async getAllNovels(): Promise<NovelProjectSummary[]> {
    return request(NOVELS_BASE)
  }

  static async deleteNovels(projectIds: string[]): Promise<DeleteNovelsResponse> {
    return request(NOVELS_BASE, {
      method: 'DELETE',
      body: JSON.stringify(projectIds)
    })
  }


  static async updateBlueprint(projectId: string, data: Record<string, any>): Promise<NovelProject> {
    return requestProject(`${NOVELS_BASE}/${projectId}/blueprint`, {
      method: 'PATCH',
      body: JSON.stringify(data)
    })
  }

  static async getFactions(projectId: string): Promise<{
    project_id: string
    factions: Array<Record<string, any>>
  }> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/factions`)
  }

  static async updateFactions(
    projectId: string,
    factions: Array<Record<string, any>>
  ): Promise<{
    project_id: string
    factions: Array<Record<string, any>>
  }> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/factions`, {
      method: 'PUT',
      body: JSON.stringify(factions)
    })
  }

  static async applyPatch(
    projectId: string,
    chapterNumber: number,
    original: string,
    patched: string
  ): Promise<{
    status: string
    message: string
    patch_id: number
    chapter_number: number
  }> {
    return request(`${PATCH_DIFF_BASE}/projects/${projectId}/chapters/${chapterNumber}/patch/apply`, {
      method: 'POST',
      body: JSON.stringify({
        original_text: original,
        patched_text: patched,
      })
    })
  }

  static async getDiff(
    projectId: string,
    chapterNumber: number,
    original: string,
    patched: string
  ): Promise<{
    chapter_number: number
    diff_lines: Array<{
      line_number: number
      original_line: string | null
      patched_line: string | null
      change_type: 'added' | 'modified' | 'deleted' | 'unchanged'
    }>
    summary: {
      total_lines: number
      added: number
      deleted: number
      modified: number
      unchanged: number
    }
  }> {
    return request(`${PATCH_DIFF_BASE}/projects/${projectId}/chapters/${chapterNumber}/diff`, {
      method: 'POST',
      body: JSON.stringify({
        original_text: original,
        patched_text: patched,
      })
    })
  }

  static async getVersionDiff(
    projectId: string,
    chapterNumber: number,
    v1: number,
    v2: number
  ): Promise<{
    chapter_number: number
    version1_id: number
    version2_id: number
    diff_lines: Array<{
      line_number: number
      original_line: string | null
      patched_line: string | null
      change_type: 'added' | 'modified' | 'deleted' | 'unchanged'
    }>
    summary: {
      total_lines: number
      added: number
      deleted: number
      modified: number
      unchanged: number
    }
  }> {
    return request(`${PATCH_DIFF_BASE}/projects/${projectId}/chapters/${chapterNumber}/versions/${v1}/vs/${v2}`)
  }
}

// ============================================================================
// 优化API
// ============================================================================

const OPTIMIZER_BASE = `${API_BASE_URL}${API_PREFIX}/optimizer`

export class OptimizerAPI {
  /**
   * 对章节内容进行分层优化
   */
  static async optimizeChapter(optimizeReq: OptimizeRequest): Promise<OptimizeResponse> {
    return request(`${OPTIMIZER_BASE}/optimize`, {
      method: 'POST',
      body: JSON.stringify(optimizeReq)
    })
  }

  /**
   * 应用优化后的内容到章节
   */
  static async applyOptimization(
    projectId: string,
    chapterNumber: number,
    optimizedContent: string
  ): Promise<ApplyOptimizationResponse> {
    return request(`${OPTIMIZER_BASE}/apply-optimization`, {
      method: 'POST',
      body: JSON.stringify({
        project_id: projectId,
        chapter_number: chapterNumber,
        optimized_content: optimizedContent
      })
    })
  }

  // ========== CoLong 动态记忆回写 API ==========

  /**
   * 增量更新记忆 - 追加而非全量替换
   */
  static async updateMemoryIncremental(
    projectId: string,
    update: {
      chapter_number: number
      new_global_summary?: string
      new_plot_arcs?: Record<string, any>
      new_timeline_events?: Array<Record<string, any>>
      character_states?: Record<string, any>
    }
  ): Promise<{ project_id: string; result: any }> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/memory/incremental`, {
      method: 'POST',
      body: JSON.stringify(update)
    })
  }

  /**
   * 获取记忆快照历史
   */
  static async getMemorySnapshots(
    projectId: string,
    chapterNumber?: number,
    limit: number = 10
  ): Promise<{
    project_id: string
    snapshots: Array<{ id: number; chapter_number: number; summary: string; created_at: string }>
    current_memory_version: number
    current_snapshot_id: number | null
  }> {
    const params = new URLSearchParams({ limit: String(limit) })
    if (chapterNumber !== undefined) {
      params.append('chapter_number', String(chapterNumber))
    }
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/memory/snapshots?${params}`)
  }

  /**
   * 压缩记忆
   */
  static async compressMemory(
    projectId: string,
    preserveChapters: number = 5
  ): Promise<{ project_id: string; result: any }> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/memory/compress`, {
      method: 'POST',
      body: JSON.stringify({ preserve_chapters: preserveChapters })
    })
  }

  /**
   * 回滚记忆到指定版本
   */
  static async rollbackMemory(
    projectId: string,
    targetVersion: number
  ): Promise<{ project_id: string; result: any }> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/memory/rollback`, {
      method: 'POST',
      body: JSON.stringify({ target_version: targetVersion })
    })
  }

  // ========== 2.2 风格学习 RAG API ==========

  /**
   * 从章节提取写作风格特征
   */
  static async extractStyle(
    projectId: string,
    chapterNumbers: number[]
  ): Promise<{ success: boolean; message: string; style_summary: any }> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/style/extract`, {
      method: 'POST',
      body: JSON.stringify({ chapter_numbers: chapterNumbers })
    })
  }

  /**
   * 获取项目当前风格配置
   */
  static async getProjectStyle(
    projectId: string
  ): Promise<{ has_style: boolean; summary: any; source?: any }> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/style`)
  }

  /**
   * 获取外部文风来源列表
   */
  static async listStyleSources(
    projectId: string
  ): Promise<{ sources: any[] }> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/style/sources`)
  }

  static async getStyleLibrary(
    projectId: string
  ): Promise<{ sources: any[]; profiles: any[]; project_active_profile: any | null; global_active_profile: any | null }> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/style/library`)
  }

  /**
   * 创建外部文风来源
   */
  static async createStyleSource(
    projectId: string,
    payload: {
      title: string
      content_text: string
      source_type?: string
      extra?: Record<string, any>
    }
  ): Promise<{ success: boolean; source: any }> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/style/sources`, {
      method: 'POST',
      body: JSON.stringify(payload)
    })
  }

  /**
   * 删除外部文风来源
   */
  static async deleteStyleSource(
    projectId: string,
    sourceId: string
  ): Promise<{ success: boolean }> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/style/sources/${sourceId}`, {
      method: 'DELETE'
    })
  }

  /**
   * 获取文风画像列表
   */
  static async listStyleProfiles(
    projectId: string
  ): Promise<{ profiles: any[] }> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/style/profiles`)
  }

  /**
   * 从来源创建文风画像
   */
  static async createStyleProfile(
    projectId: string,
    payload: { source_ids: string[]; name?: string; append_to_profile_id?: string }
  ): Promise<{ success: boolean; profile: any }> {
    let status = await OptimizerAPI.startStyleProfileGeneration(projectId, payload)

    for (let attempt = 0; attempt < STYLE_PROFILE_MAX_POLL_ATTEMPTS; attempt += 1) {
      if (status.status === 'successful' && status.profile) {
        return { success: true, profile: status.profile }
      }
      if (status.status === 'failed') {
        throw new Error(readStyleProfileJobError(status))
      }
      if (status.status === 'cancelled') {
        throw new Error(status.progress_message || '文风画像生成已取消')
      }

      await delay(STYLE_PROFILE_POLL_INTERVAL_MS)
      status = await OptimizerAPI.getStyleProfileGenerationStatus(projectId)
    }

    throw new Error('文风画像后台任务等待超时，请稍后刷新文风中心查看结果。')
  }

  static async startStyleProfileGeneration(
    projectId: string,
    payload: { source_ids: string[]; name?: string; append_to_profile_id?: string }
  ): Promise<StyleProfileJobResponse> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/style/profiles/start`, {
      method: 'POST',
      body: JSON.stringify(payload)
    })
  }

  static async getStyleProfileGenerationStatus(projectId: string): Promise<StyleProfileJobResponse> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/style/profiles/status`)
  }

  static async cancelStyleProfileGeneration(projectId: string): Promise<StyleProfileJobResponse> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/style/profiles/cancel`, {
      method: 'POST'
    })
  }

  static async uploadStyleSource(
    projectId: string,
    payload: {
      file: File
      title?: string
      source_type?: string
      extra?: Record<string, any>
    }
  ): Promise<{ success: boolean; source: any }> {
    let status = await OptimizerAPI.startStyleSourceUpload(projectId, payload)

    for (let attempt = 0; attempt < STYLE_SOURCE_UPLOAD_MAX_POLL_ATTEMPTS; attempt += 1) {
      if (status.status === 'successful' && status.source) {
        return { success: true, source: status.source }
      }
      if (status.status === 'failed') {
        throw new Error(readStyleSourceUploadJobError(status))
      }
      if (status.status === 'cancelled') {
        throw new Error(status.progress_message || '文风素材导入已取消')
      }

      await delay(STYLE_SOURCE_UPLOAD_POLL_INTERVAL_MS)
      status = await OptimizerAPI.getStyleSourceUploadStatus(projectId, status.run_id)
    }

    throw new Error('文风素材导入后台任务等待超时，请稍后刷新文风中心查看结果。')
  }

  static async startStyleSourceUpload(
    projectId: string,
    payload: {
      file: File
      title?: string
      source_type?: string
      extra?: Record<string, any>
    }
  ): Promise<StyleSourceUploadJobResponse> {
    const formData = new FormData()
    formData.append('file', payload.file)
    if (payload.title) formData.append('title', payload.title)
    if (payload.source_type) formData.append('source_type', payload.source_type)
    if (payload.extra) formData.append('extra', JSON.stringify(payload.extra))
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/style/sources/upload/start`, {
      method: 'POST',
      body: formData
    })
  }

  static async getStyleSourceUploadStatus(
    projectId: string,
    runId: string
  ): Promise<StyleSourceUploadJobResponse> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/style/sources/upload/status?run_id=${encodeURIComponent(runId)}`)
  }

  static async cancelStyleSourceUpload(
    projectId: string,
    runId: string
  ): Promise<StyleSourceUploadJobResponse> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/style/sources/upload/${encodeURIComponent(runId)}/cancel`, {
      method: 'POST'
    })
  }

  static async updateStyleProfile(
    projectId: string,
    profileId: string,
    payload: {
      name?: string
      summary?: Record<string, string>
      extra?: Record<string, any>
    }
  ): Promise<{ success: boolean; profile: any }> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/style/profiles/${profileId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload)
    })
  }

  /**
   * 获取当前激活的文风画像
   */
  static async getActiveStyleProfile(
    projectId: string
  ): Promise<{ has_active_style: boolean; profile: any | null; scope: 'global' | 'project' | null }> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/style/active`)
  }

  /**
   * 应用指定文风画像到全局或当前项目
   */
  static async activateStyleProfile(
    projectId: string,
    profileId: string,
    scope: 'global' | 'project' = 'project'
  ): Promise<{ success: boolean; profile: any; scope: 'global' | 'project' }> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/style/apply`, {
      method: 'POST',
      body: JSON.stringify({ profile_id: profileId, scope })
    })
  }

  /**
   * 清除全局或当前项目的文风应用
   */
  static async clearActiveStyleProfile(
    projectId: string,
    scope: 'global' | 'project' = 'project'
  ): Promise<{ success: boolean }> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/style/active?scope=${scope}`, {
      method: 'DELETE'
    })
  }

  /**
   * 清除项目的风格配置
   */
  static async clearProjectStyle(
    projectId: string
  ): Promise<{ success: boolean; message: string }> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/style`, {
      method: 'DELETE'
    })
  }

  /**
   * 带风格上下文的续写生成
   */
  static async generateWithStyle(
    projectId: string,
    existingContent: string,
    direction: string,
    maxTokens: number = 2000
  ): Promise<{ content: string; style_applied: boolean }> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/style/generate`, {
      method: 'POST',
      body: JSON.stringify({
        existing_content: existingContent,
        direction: direction,
        max_tokens: maxTokens
      })
    })
  }

  // ========== 2.3 剧情推演 API ==========

  /**
   * 生成剧情演进选项
   */
  static async evolveOutline(
    projectId: string,
    chapterNumber: number,
    numOptions: number = 3
  ): Promise<{ alternatives: any[]; batch_id: string; chapter_number: number }> {
    return request(`${NOVELS_BASE}/${projectId}/outline/evolve`, {
      method: 'POST',
      body: JSON.stringify({
        chapter_number: chapterNumber,
        num_options: numOptions
      })
    })
  }

  /**
   * 选择某个演进选项并更新大纲
   */
  static async selectAlternative(
    projectId: string,
    optionId: number,
    chapterNumber: number
  ): Promise<{ success: boolean; message: string; updated_outline: any }> {
    return request(`${NOVELS_BASE}/${projectId}/outline/next`, {
      method: 'POST',
      body: JSON.stringify({
        option_id: optionId,
        chapter_number: chapterNumber
      })
    })
  }

  /**
   * 获取当前章节的所有可能走向
   */
  static async getOutlineAlternatives(
    projectId: string,
    chapterNumber: number,
    statusFilter?: string
  ): Promise<{ alternatives: any[]; chapter_number: number; total: number }> {
    const params = new URLSearchParams({ chapter_number: String(chapterNumber) })
    if (statusFilter) params.append('status_filter', statusFilter)
    return request(`${NOVELS_BASE}/${projectId}/outline/alternatives?${params}`)
  }

  /**
   * 获取演进历史
   */
  static async getOutlineHistory(
    projectId: string,
    chapterNumber?: number,
    limit: number = 20
  ): Promise<{ history: any[]; total: number }> {
    const params = new URLSearchParams({ limit: String(limit) })
    if (chapterNumber !== undefined) params.append('chapter_number', String(chapterNumber))
    return request(`${NOVELS_BASE}/${projectId}/outline/history?${params}`)
  }

  // ========== 知识图谱 API ==========

  // ========== Patch+Diff 精细编辑 API ==========

  /**
   * 应用 Patch 到章节内容
   */


  /**
   * 获取章节的 Patch 历史
   */
  static async getPatchHistory(
    projectId: string,
    chapterNumber: number
  ): Promise<{
    chapter_number: number
    patches: Array<{
      id: number
      chapter_id: number
      original_text: string
      patched_text: string
      patch_operations: any
      from_version_id: number | null
      to_version_id: number | null
      description: string | null
      created_at: string
    }>
    total: number
  }> {
    return request(`${PATCH_DIFF_BASE}/projects/${projectId}/chapters/${chapterNumber}/patch/history`)
  }

  /**
   * 撤销指定 Patch
   */
  static async revertPatch(
    projectId: string,
    chapterNumber: number,
    patchId: number
  ): Promise<{
    status: string
    message: string
    original_text: string
  }> {
    return request(`${PATCH_DIFF_BASE}/projects/${projectId}/chapters/${chapterNumber}/patch/revert`, {
      method: 'POST',
      body: JSON.stringify({ patch_id: patchId })
    })
  }
}

// ============================================================================
// 分析型详情页 API
// ============================================================================

export class AnalyticsAPI {
  static async getEmotionCurve(projectId: string): Promise<any> {
    return request(`${API_BASE_URL}${API_PREFIX}/analytics/${projectId}/emotion-curve`)
  }

  static async analyzeEmotionWithAI(projectId: string): Promise<any> {
    return request(`${API_BASE_URL}${API_PREFIX}/analytics/${projectId}/analyze-emotion-ai`, {
      method: 'POST'
    })
  }

  static async getForeshadowingOverview(projectId: string): Promise<any> {
    return request(`${API_BASE_URL}${API_PREFIX}/analytics/${projectId}/foreshadowing`)
  }

  static async getEnhancedEmotionCurve(projectId: string): Promise<EnhancedEmotionPoint[]> {
    return request(`${API_BASE_URL}${API_PREFIX}/analytics/projects/${projectId}/emotion-curve-enhanced`)
  }

  static async getStoryTrajectory(projectId: string): Promise<StoryTrajectoryAnalysis> {
    return request(`${API_BASE_URL}${API_PREFIX}/analytics/projects/${projectId}/story-trajectory`)
  }

  static async getCreativeGuidance(projectId: string): Promise<CreativeGuidanceAnalysis> {
    return request(`${API_BASE_URL}${API_PREFIX}/analytics/projects/${projectId}/creative-guidance`)
  }

  static async getComprehensiveAnalysis(projectId: string): Promise<ComprehensiveAnalysis> {
    return request(`${API_BASE_URL}${API_PREFIX}/analytics/projects/${projectId}/comprehensive-analysis`)
  }

  static async invalidateAnalysisCache(projectId: string): Promise<{ message: string; project_id: string }> {
    return request(`${API_BASE_URL}${API_PREFIX}/analytics/projects/${projectId}/invalidate-cache`, {
      method: 'POST'
    })
  }
}

// ============================================================================
// Token 预算管理 API
// ============================================================================

const TOKEN_BUDGET_BASE = `${API_BASE_URL}${API_PREFIX}/projects`

export class TokenBudgetAPI {
  /**
   * 获取项目的 Token 预算配置
   */
  static async getBudgetConfig(
    projectId: string
  ): Promise<{
    project_id: string
    total_budget: number
    chapter_budget: number
    module_allocation: Record<string, number>
    warning_threshold: number
  }> {
    return request(`${TOKEN_BUDGET_BASE}/${projectId}/token-budget`)
  }

  /**
   * 更新项目的 Token 预算配置
   */
  static async updateBudgetConfig(
    projectId: string,
    config: {
      total_budget?: number
      chapter_budget?: number
      module_allocation?: Record<string, number>
      warning_threshold?: number
    }
  ): Promise<{
    project_id: string
    total_budget: number
    chapter_budget: number
    module_allocation: Record<string, number>
    warning_threshold: number
  }> {
    return request(`${TOKEN_BUDGET_BASE}/${projectId}/token-budget`, {
      method: 'PUT',
      body: JSON.stringify(config)
    })
  }

  /**
   * 记录一次 Token 使用
   */
  static async recordUsage(
    projectId: string,
    usage: {
      module: string
      tokens_used: number
      cost: number
      model_name?: string
      chapter_id?: number
      operation_type?: string
      description?: string
    }
  ): Promise<{
    id: number
    project_id: string
    module: string
    tokens_used: number
    cost: number
    created_at: string
  }> {
    return request(`${TOKEN_BUDGET_BASE}/${projectId}/token-budget/usage`, {
      method: 'POST',
      body: JSON.stringify(usage)
    })
  }

  /**
   * 获取项目的 Token 使用统计
   */
  static async getUsageStats(
    projectId: string,
    options?: {
      start_date?: string
      end_date?: string
      chapter_id?: number
    }
  ): Promise<{
    project_id: string
    total_budget: number
    budget_remaining: number
    usage_percent: number
    total_tokens: number
    total_cost: number
    module_stats: Record<string, { tokens: number; cost: number }>
    record_count: number
  }> {
    const params = new URLSearchParams()
    if (options?.start_date) params.append('start_date', options.start_date)
    if (options?.end_date) params.append('end_date', options.end_date)
    if (options?.chapter_id) params.append('chapter_id', String(options.chapter_id))

    const query = params.toString() ? `?${params.toString()}` : ''
    return request(`${TOKEN_BUDGET_BASE}/${projectId}/token-budget/usage${query}`)
  }

  /**
   * 获取各模块的使用量
   */
  static async getModuleUsage(
    projectId: string
  ): Promise<{
    project_id: string
    module_usage: Record<string, {
      used: number
      allocated: number
      remaining: number
      percent: number
    }>
    total_budget: number
    warning_threshold: number
  }> {
    return request(`${TOKEN_BUDGET_BASE}/${projectId}/token-budget/usage-by-module`)
  }

  /**
   * 获取项目的预算预警列表
   */
  static async getAlerts(
    projectId: string,
    includeResolved: boolean = false
  ): Promise<Array<{
    id: number
    alert_type: string
    threshold_percent: number
    current_usage: number
    budget_limit: number
    message: string
    is_resolved: boolean
    created_at: string
  }>> {
    return request(
      `${TOKEN_BUDGET_BASE}/${projectId}/token-budget/alerts?include_resolved=${includeResolved}`
    )
  }

  /**
   * 标记预警为已处理
   */
  static async resolveAlert(
    projectId: string,
    alertId: number
  ): Promise<{ status: string; message: string }> {
    return request(
      `${TOKEN_BUDGET_BASE}/${projectId}/token-budget/alerts/${alertId}/resolve`,
      { method: 'POST' }
    )
  }

  /**
   * 批量分配模块预算
   */
  static async allocateModuleBudget(
    projectId: string,
    allocations: Array<{ module: string; allocation_percent: number }>
  ): Promise<{
    status: string
    message: string
    module_allocation: Record<string, number>
  }> {
    return request(`${TOKEN_BUDGET_BASE}/${projectId}/token-budget/allocate`, {
      method: 'POST',
      body: JSON.stringify(allocations)
    })
  }

  // ===== Research APIs =====
  static async getResearchConfig(projectId: string): Promise<ResearchConfig> {
    return request(`${PROJECTS_BASE}/${projectId}/research/config`)
  }
  
  static async updateResearchConfig(projectId: string, config: ResearchConfig): Promise<ResearchConfig> {
    return request(`${PROJECTS_BASE}/${projectId}/research/config`, {
      method: 'PUT',
      body: JSON.stringify(config),
    })
  }
  
  static async startResearchRun(projectId: string, payload: { scope: string; chapter_number?: number }): Promise<{ run_id: string; status: string }> {
    return request(`${PROJECTS_BASE}/${projectId}/research/run/start`, {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  }
  
  static async getResearchJobStatus(projectId: string, runId: string): Promise<ResearchRunStatus> {
    return request(`${PROJECTS_BASE}/${projectId}/research/run/${runId}/status`)
  }
  
  static async cancelResearchRun(projectId: string, runId: string): Promise<void> {
    return request(`${PROJECTS_BASE}/${projectId}/research/run/${runId}/cancel`, {
      method: 'POST',
    })
  }
  
  static async listResearchArtifacts(projectId: string): Promise<ResearchArtifact[]> {
    return request(`${PROJECTS_BASE}/${projectId}/research/artifacts`)
  }
  
  static async createResearchPendingArtifact(projectId: string, payload: { title: string; url?: string; notes?: string }): Promise<ResearchArtifact> {
    return request(`${PROJECTS_BASE}/${projectId}/research/artifacts`, {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  }
}
