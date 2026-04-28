// AIMETA P=小说API客户端_小说和章节接口|R=小说CRUD_章节管理_生成|NR=不含UI逻辑|E=api:novel|X=internal|A=novelApi对象|D=axios|S=net|RD=./README.ai
import { API_BASE_URL, API_PREFIX } from '@/api/config'
import { normalizeChapterContent } from '@/utils/chapterContent'

const readText = (value: unknown): string | undefined => {
  if (typeof value !== 'string') return undefined
  const trimmed = value.trim()
  return trimmed || undefined
}

export interface ApiErrorDetail {
  status: number
  message: string
  code?: string
  hint?: string
  rootCause?: string
  requestId?: string
  retryable?: boolean
  responseSnippet?: string
}

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
    responseSnippet: readText(responseSnippet)
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
      evaluation: typeof record.evaluation === 'string' ? record.evaluation : undefined
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

// 类型定义
export interface NovelProject {
  id: string
  title: string
  initial_prompt: string
  blueprint?: Blueprint
  chapters: Chapter[]
  conversation_history: ConversationMessage[]
  generation_runtime?: GenerationRuntime
  workspace_summary?: WorkspaceSummary
}

export interface NovelProjectSummary {
  id: string
  title: string
  genre: string
  last_edited: string
  completed_chapters: number
  total_chapters: number
}

export interface Blueprint {
  title?: string
  target_audience?: string
  genre?: string
  style?: string
  tone?: string
  one_sentence_summary?: string
  full_synopsis?: string
  world_setting?: Record<string, any>
  characters?: Character[]
  relationships?: Relationship[]
  story_arcs?: Array<Record<string, any>>
  volume_plan?: Array<Record<string, any>>
  foreshadowing_system?: Array<Record<string, any>>
  chapter_outline?: ChapterOutline[]
}

export interface Character {
  name: string
  description?: string
  summary?: string
  role?: string
  identity?: string
  archetype?: string
  personality?: string
  goals?: string
  core_motivation?: string
  fear_or_wound?: string
  external_goal?: string
  hidden_secret?: string
  growth_arc?: string
  first_highlight_chapter?: number | string
  relationship_hook?: string
  importance?: 'protagonist' | 'core' | 'supporting' | 'minor' | string
  tags?: string[]
  abilities?: string
  relationship_to_protagonist?: string
  extra?: Record<string, any>
}

export interface Relationship {
  character_from: string
  character_to: string
  description: string
  relation_type?: string
  relationship_type?: string
  status?: string
  current_state?: string
  core_conflict?: string
  tension?: string
  direction?: string
  expected_change?: string
  trigger_event?: string
  key_trigger?: string
  importance?: number
  extra?: Record<string, any>
}

export interface ChapterOutline {
  chapter_number: number
  title: string
  summary: string
  narrative_phase?: string
  chapter_role?: string
  suspense_hook?: string
  emotional_progression?: string
  character_focus?: string[]
  conflict_escalation?: string[]
  continuity_notes?: string[]
  foreshadowing?: {
    plant?: string[]
    payoff?: string[]
  }
  metadata?: Record<string, any>
}

export interface ChapterVersion {
  id?: number
  content: string
  style?: string
  evaluation?: string
  metadata?: Record<string, any>
}

export interface Chapter {
  chapter_number: number
  title: string
  summary: string
  content: string | null
  versions: ChapterVersion[] | null
  evaluation: string | null
  generation_status: 'not_generated' | 'generating' | 'evaluating' | 'selecting' | 'failed' | 'evaluation_failed' | 'waiting_for_confirm' | 'successful'
  word_count?: number  // 字数统计
  progress_stage?: 'queued' | 'generating' | 'evaluating' | 'selecting' | 'ready' | 'failed' | string
  progress_message?: string | null
  started_at?: string | null
  updated_at?: string | null
  allowed_actions?: string[]
  last_error_summary?: string | null
  generation_runtime?: GenerationRuntime
}

export interface GenerationRuntimeEvent {
  at?: string
  stage?: string
  level?: 'info' | 'warning' | 'error' | string
  message?: string
  metadata?: Record<string, any>
}

export interface GenerationRuntime {
  queued?: boolean
  generation_mode?: string
  preset?: string
  version_count?: number
  target_word_count?: number
  min_word_count?: number
  progress_stage?: string
  progress_message?: string
  progress_percent?: number
  estimated_remaining_seconds?: number
  started_at?: string | null
  updated_at?: string | null
  chapter_number?: number
  allowed_actions?: string[]
  last_error_summary?: string | null
  events?: GenerationRuntimeEvent[]
  [key: string]: any
}

export interface WorkspaceSummary {
  total_chapters: number
  completed_chapters: number
  failed_chapters: number
  in_progress_chapters: number
  total_word_count: number
  active_chapter?: number | null
  first_incomplete_chapter?: number | null
  next_chapter_to_generate?: number | null
  can_generate_next: boolean
  available_actions: string[]
}

export interface ConversationMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface ConverseResponse {
  ai_message: string
  ui_control: UIControl
  conversation_state: any
  is_complete: boolean
  ready_for_blueprint?: boolean  // 新增：表示准备生成蓝图
}

export interface BlueprintGenerationResponse {
  blueprint: Blueprint
  ai_message: string
}

export interface UIControl {
  type: 'single_choice' | 'text_input'
  options?: Array<{ id: string; label: string }>
  placeholder?: string
}

export interface ChapterGenerationResponse {
  versions: ChapterVersion[] // Renamed from chapter_versions for consistency
  evaluation: string | null
  ai_message: string
  chapter_number: number
  generation_runtime?: GenerationRuntime
}

export interface GenerateOutlineOptions {
  targetTotalChapters?: number
  targetTotalWords?: number
  chapterWordTarget?: number
}

export interface GenerateChapterOptions {
  writingNotes?: string
  qualityRequirements?: string
  minWordCount?: number
  targetWordCount?: number
}

export interface CancelChapterOptions {
  reason?: string
}

export interface RewriteChapterOutlineOptions {
  direction?: string
}

export interface DeleteNovelsResponse {
  status: string
  message: string
}

// 内容型Section（对应后端NovelSectionType枚举）
export type NovelSectionType = 'overview' | 'world_setting' | 'characters' | 'relationships' | 'chapter_outline' | 'chapters'

// 分析型Section（不属于NovelSectionType，使用独立的analytics API）
export type AnalysisSectionType =
  | 'emotion_curve'
  | 'foreshadowing'
  | 'knowledge_graph'
  | 'story_trajectory'
  | 'creative_guidance'
  | 'comprehensive_analysis'
  | 'clue_tracker'

// 功能入口（不加载数据，只触发弹窗）
export type FeatureEntryType = 'style_learning' | 'memory_management' | 'token_budget'

// 所有Section的联合类型
export type AllSectionType = NovelSectionType | AnalysisSectionType | FeatureEntryType

export interface NovelSectionResponse {
  section: NovelSectionType
  data: Record<string, any>
}

// API 函数
const NOVELS_BASE = `${API_BASE_URL}${API_PREFIX}/novels`
const PATCH_DIFF_BASE = `${API_BASE_URL}${API_PREFIX}`
const WRITER_PREFIX = '/api/writer'
const WRITER_BASE = `${API_BASE_URL}${WRITER_PREFIX}/novels`

export class NovelAPI {
  static async createNovel(title: string, initialPrompt: string): Promise<NovelProject> {
    return requestProject(NOVELS_BASE, {
      method: 'POST',
      body: JSON.stringify({ title, initial_prompt: initialPrompt })
    })
  }

  static async importNovel(file: File): Promise<{ id: string }> {
    const formData = new FormData()
    formData.append('file', file)
    return request(`${NOVELS_BASE}/import`, {
      method: 'POST',
      body: formData,
      headers: {
        // 让 browser 自动设置 Content-Type 为 multipart/form-data，不手动设置
      }
    })
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
    return request(`${NOVELS_BASE}/${projectId}/blueprint/generate`, {
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


// 优化相关类型定义
export interface EmotionBeat {
  primary_emotion: string
  intensity: number
  curve: {
    start: number
    peak: number
    end: number
  }
  turning_point: string
}

export interface OptimizeRequest {
  project_id: string
  chapter_number: number
  dimension:
    | 'dialogue'
    | 'environment'
    | 'psychology'
    | 'rhythm'
  additional_notes?: string
  version_index?: number
}

export interface OptimizeResponse {
  optimized_content: string
  optimization_notes: string | string[]
  dimension: string
}

export interface ApplyOptimizationResponse {
  status: string
  message: string
  chapter: Chapter
}

// 优化API
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
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/style/profiles`, {
      method: 'POST',
      body: JSON.stringify(payload)
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
    const formData = new FormData()
    formData.append('file', payload.file)
    if (payload.title) formData.append('title', payload.title)
    if (payload.source_type) formData.append('source_type', payload.source_type)
    if (payload.extra) formData.append('extra', JSON.stringify(payload.extra))
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/style/sources/upload`, {
      method: 'POST',
      body: formData
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

// ========== 分析型详情页 API ==========

export interface EnhancedEmotionPoint {
  chapter_number: number
  chapter_id: string
  title: string
  primary_emotion: string
  primary_intensity: number
  secondary_emotions: Array<[string, number]>
  narrative_phase: string
  pace: string
  is_turning_point: boolean
  turning_point_type?: string | null
  description: string
}

export interface StoryTrajectoryAnalysis {
  project_id: string
  project_title: string
  shape: string
  shape_confidence: number
  total_chapters: number
  avg_intensity: number
  intensity_range: [number, number]
  volatility: number
  peak_chapters: number[]
  valley_chapters: number[]
  turning_points: number[]
  description: string
  recommendations: string[]
}

export interface GuidanceItemAnalysis {
  type: string
  priority: string
  title: string
  description: string
  specific_suggestions: string[]
  affected_chapters: number[]
  examples: string[]
}

export interface CreativeGuidanceAnalysis {
  project_id: string
  project_title: string
  current_chapter: number
  overall_assessment: string
  strengths: string[]
  weaknesses: string[]
  guidance_items: GuidanceItemAnalysis[]
  next_chapter_suggestions: string[]
  long_term_planning: string[]
}

export interface ComprehensiveAnalysis {
  project_id: string
  project_title: string
  emotion_points: EnhancedEmotionPoint[]
  trajectory: StoryTrajectoryAnalysis
  guidance: CreativeGuidanceAnalysis
}

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

// ========== Token 预算管理 API ==========

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
}

// ========== 线索追踪 API ==========

export interface ForeshadowingItem {
  id: number
  chapter_number: number
  content: string
  type: string
  status: string
  resolved_chapter_number: number | null
  is_manual: boolean
  ai_confidence: number | null
  author_note: string | null
  created_at: string
}

export interface ForeshadowingListResponse {
  total: number
  limit: number
  offset: number
  data: ForeshadowingItem[]
}

export interface ForeshadowingCreateRequest {
  chapter_id: number
  chapter_number: number
  content: string
  type: string
  keywords?: string[]
  author_note?: string
}

export interface ForeshadowingCreateResponse extends ForeshadowingItem {
  project_id: string
}

export interface ForeshadowingResolveRequest {
  resolved_chapter_id: number
  resolved_chapter_number: number
  resolution_text: string
  resolution_type?: string
  quality_score?: number
}

export interface ForeshadowingResolveResponse {
  status: string
  message: string
  resolution_id: number
}

export interface ForeshadowingReminderItem {
  id: number
  foreshadowing_id: number
  reminder_type: string
  message: string
  status: string
  created_at: string
}

export interface ForeshadowingRemindersResponse {
  total: number
  data: ForeshadowingReminderItem[]
}

export interface ForeshadowingAnalysisResponse {
  total_foreshadowings: number
  resolved_count: number
  unresolved_count: number
  abandoned_count: number
  avg_resolution_distance: number | null
  unresolved_ratio: number | null
  overall_quality_score: number | null
  recommendations: string[]
  pattern_analysis: Record<string, any>
  analyzed_at: string
}

// ─── ForeshadowingAPI ───────────────────────────────────────────────────────────
export class ForeshadowingAPI {
  static async getForeshadowings(projectId: string): Promise<ForeshadowingListResponse> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/foreshadowings`)
  }

  static async createForeshadowing(
    projectId: string,
    data: ForeshadowingCreateRequest
  ): Promise<ForeshadowingCreateResponse> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/foreshadowings`, {
      method: 'POST',
      body: JSON.stringify(data)
    })
  }

  static async resolveForeshadowing(
    projectId: string,
    foreshadowingId: number,
    resolveData: ForeshadowingResolveRequest
  ): Promise<ForeshadowingResolveResponse> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/foreshadowings/${foreshadowingId}/resolve`, {
      method: 'POST',
      body: JSON.stringify(resolveData)
    })
  }

  static async getReminders(projectId: string): Promise<ForeshadowingRemindersResponse> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/foreshadowings/reminders`)
  }

  static async getAnalysis(projectId: string): Promise<ForeshadowingAnalysisResponse> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/foreshadowings/analysis`)
  }
}

export class KnowledgeGraphAPI {
  static async createGraphNode(projectId: string, nodeData: Record<string, any>): Promise<any> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/knowledge-graph/nodes`, {
      method: 'POST',
      body: JSON.stringify(nodeData)
    })
  }

  static async getGraphNodes(projectId: string): Promise<any[]> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/knowledge-graph/nodes`)
  }

  static async updateGraphNode(projectId: string, nodeId: number, data: Record<string, any>): Promise<any> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/knowledge-graph/nodes/${nodeId}`, {
      method: 'PUT',
      body: JSON.stringify(data)
    })
  }

  static async deleteGraphNode(projectId: string, nodeId: number): Promise<any> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/knowledge-graph/nodes/${nodeId}`, {
      method: 'DELETE'
    })
  }

  static async createGraphEdge(projectId: string, edgeData: Record<string, any>): Promise<any> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/knowledge-graph/edges`, {
      method: 'POST',
      body: JSON.stringify(edgeData)
    })
  }

  static async getGraphEdges(projectId: string): Promise<any[]> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/knowledge-graph/edges`)
  }

  static async deleteGraphEdge(projectId: string, edgeId: number): Promise<any> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/knowledge-graph/edges/${edgeId}`, {
      method: 'DELETE'
    })
  }

  static async getFullGraph(projectId: string): Promise<any> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/knowledge-graph`)
  }

  static async getCharacterTimeline(projectId: string, characterId: number): Promise<any> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/knowledge-graph/character/${characterId}/timeline`)
  }

  static async getConnectedCharacters(projectId: string, characterId: number, depth = 1): Promise<any> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/knowledge-graph/connected/${characterId}?depth=${depth}`)
  }

  static async analyzePlotThreads(projectId: string): Promise<any> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/knowledge-graph/threads`)
  }

  static async exportGraph(projectId: string, format = 'json'): Promise<any> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/knowledge-graph/export?format=${format}`)
  }
}

export class ClueTrackerAPI {
  static async getProjectClues(projectId: string): Promise<any[]> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/clues`)
  }

  static async analyzeClueThreads(projectId: string): Promise<any> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/clues/threads`)
  }

  static async createClue(projectId: string, data: Record<string, any>): Promise<any> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/clues`, {
      method: 'POST',
      body: JSON.stringify(data)
    })
  }

  static async getClue(projectId: string, clueId: number): Promise<any> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/clues/${clueId}`)
  }

  static async updateClue(projectId: string, clueId: number, data: Record<string, any>): Promise<any> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/clues/${clueId}`, {
      method: 'PUT',
      body: JSON.stringify(data)
    })
  }

  static async deleteClue(projectId: string, clueId: number): Promise<any> {
    return request(`${API_BASE_URL}${API_PREFIX}/projects/${projectId}/clues/${clueId}`, {
      method: 'DELETE'
    })
  }
}

export interface WritingSkillItem {
  id: string
  name: string
  description?: string
  overview?: string
  category?: string
  version: string
  author?: string
  source_url?: string
  use_cases?: string[]
  input_guide?: string
  output_format?: string[]
  tips?: string[]
  example_prompt?: string
  tags?: string[]
  installed?: boolean
}

export interface WritingSkillExecutionResult {
  skill_id: string
  skill_name: string
  project_id?: string
  chapter_number?: number
  result: {
    summary: string
    suggestion: string
    mode: string
  }
  executed_at: string
}

export class WritingSkillsAPI {
  static async getSkillCatalog(): Promise<WritingSkillItem[]> {
    return request(`${API_BASE_URL}${API_PREFIX}/skills/catalog`)
  }

  static async installSkill(skillId: string, data: Record<string, any>): Promise<WritingSkillItem> {
    return request(`${API_BASE_URL}${API_PREFIX}/skills/${skillId}/install`, {
      method: 'POST',
      body: JSON.stringify(data)
    })
  }

  static async uninstallSkill(skillId: string): Promise<any> {
    return request(`${API_BASE_URL}${API_PREFIX}/skills/${skillId}/uninstall`, {
      method: 'DELETE'
    })
  }

  static async executeSkill(skillId: string, data: Record<string, any>): Promise<WritingSkillExecutionResult> {
    return request(`${API_BASE_URL}${API_PREFIX}/skills/${skillId}/execute`, {
      method: 'POST',
      body: JSON.stringify(data)
    })
  }
}
