import { API_BASE_URL } from '@/api/config'
import {
  ApiError,
  type CancelChapterOptions,
  type Chapter,
  type ChapterOutline,
  type GenerateChapterOptions,
  type GenerateOutlineOptions,
  type NovelProject,
  type OutlineGenerationJobResponse,
  type RewriteChapterOutlineOptions,
} from '@/api/novel'
import { normalizeChapterContent } from '@/utils/chapterContent'

const WRITER_PREFIX = '/api/writer'
const WRITER_BASE = `${API_BASE_URL}${WRITER_PREFIX}/novels`
const OUTLINE_POLL_INTERVAL_MS = 2000
const OUTLINE_MAX_POLL_ATTEMPTS = 900

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

const request = async (url: string, options: RequestInit = {}) => {
  const headers = new Headers({
    'Content-Type': 'application/json',
    ...options.headers,
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

    const fallbackMessage = getFallbackMessage(response.status)
    const record = errorData && typeof errorData === 'object'
      ? (errorData as Record<string, unknown>)
      : null
    const rawDetail = record?.detail && typeof record.detail === 'object'
      ? (record.detail as Record<string, unknown>)
      : null

    throw new ApiError({
      status: response.status,
      message:
        readText(rawDetail?.message) ??
        readText(record?.detail) ??
        readText(record?.message) ??
        readText((record?.error as Record<string, unknown> | undefined)?.message) ??
        fallbackMessage,
      code: readText(rawDetail?.code),
      hint: readText(rawDetail?.hint),
      rootCause: readText(rawDetail?.root_cause) ?? readText(rawDetail?.rootCause),
      requestId:
        readText(rawDetail?.request_id) ??
        readText(rawDetail?.requestId) ??
        readText(requestIdFromHeader),
      retryable: typeof rawDetail?.retryable === 'boolean' ? rawDetail.retryable : undefined,
      responseSnippet: readText(responseSnippet),
      rejectionSummary: rawDetail?.rejection_summary && typeof rawDetail.rejection_summary === 'object'
        ? rawDetail.rejection_summary as Record<string, any>
        : undefined,
      missingChapters: Array.isArray(rawDetail?.missing_chapters)
        ? rawDetail.missing_chapters.filter((item): item is number => typeof item === 'number')
        : undefined,
    })
  }

  return response.json()
}

const normalizeChapterVersion = (value: unknown) => {
  if (typeof value === 'string') {
    return {
      id: undefined,
      content: normalizeChapterContent(value),
      style: '标准',
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
        : undefined,
    }
  }

  return {
    id: undefined,
    content: '',
    style: '标准',
  }
}

const normalizeChapter = (chapter: Chapter): Chapter => ({
  ...chapter,
  content: chapter.content === null ? null : normalizeChapterContent(chapter.content),
  versions: Array.isArray(chapter.versions)
    ? chapter.versions.map((version) => normalizeChapterVersion(version))
    : null,
})

const normalizeProject = (project: NovelProject): NovelProject => ({
  ...project,
  chapters: Array.isArray(project.chapters)
    ? project.chapters.map((chapter) => normalizeChapter(chapter))
    : [],
})

const delay = (ms: number) => new Promise((resolve) => globalThis.setTimeout(resolve, ms))

const readOutlineJobError = (status: OutlineGenerationJobResponse): string => {
  const rawError = status.error
  if (!rawError) return status.progress_message || '章节大纲生成失败，请稍后重试'
  if (typeof rawError === 'string') return rawError
  return rawError.detail || rawError.message || status.progress_message || '章节大纲生成失败，请稍后重试'
}

const requestProject = async (url: string, options?: RequestInit): Promise<NovelProject> => {
  const project = await request(url, options)
  return normalizeProject(project as NovelProject)
}

const requestChapter = async (url: string, options?: RequestInit): Promise<Chapter> => {
  const chapter = await request(url, options)
  return normalizeChapter(chapter as Chapter)
}

const buildVersionSelectorPayload = (
  versionIndex?: number,
  versionId?: number,
): { version_index?: number; version_id?: number } => {
  if (typeof versionId === 'number') return { version_id: versionId }
  if (typeof versionIndex === 'number') return { version_index: versionIndex }
  return {}
}

export const getChapterGenerationStatus = (
  projectId: string,
  chapterNumber: number,
) => requestChapter(`${WRITER_BASE}/${projectId}/chapters/${chapterNumber}/status`)

export const generateChapter = (
  projectId: string,
  chapterNumber: number,
  options: GenerateChapterOptions = {},
) => {
  const payload: Record<string, string | number> = {
    chapter_number: chapterNumber,
  }
  if (options.writingNotes && options.writingNotes.trim()) {
    payload.writing_notes = options.writingNotes.trim()
  }
  if (options.qualityRequirements && options.qualityRequirements.trim()) {
    payload.quality_requirements = options.qualityRequirements.trim()
  }
  if (options.minWordCount && options.minWordCount > 0) {
    payload.min_word_count = options.minWordCount
  }
  if (options.targetWordCount && options.targetWordCount > 0) {
    payload.target_word_count = options.targetWordCount
  }
  if (options.preset) {
    payload.preset = options.preset
  }

  return requestProject(`${WRITER_BASE}/${projectId}/chapters/generate`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export const cancelChapterGeneration = (
  projectId: string,
  chapterNumber: number,
  options: CancelChapterOptions = {},
) => {
  const payload: Record<string, string | number> = {
    chapter_number: chapterNumber,
  }
  if (options.reason && options.reason.trim()) {
    payload.reason = options.reason.trim()
  }

  return requestProject(`${WRITER_BASE}/${projectId}/chapters/cancel`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export const evaluateChapter = (
  projectId: string,
  chapterNumber: number,
  versionIndex?: number,
  versionId?: number,
  evaluateAll: boolean = false,
) => requestProject(`${WRITER_BASE}/${projectId}/chapters/evaluate`, {
  method: 'POST',
  body: JSON.stringify({
    chapter_number: chapterNumber,
    ...buildVersionSelectorPayload(versionIndex, versionId),
    evaluate_all: evaluateAll,
  }),
})

export const selectChapterVersion = (
  projectId: string,
  chapterNumber: number,
  versionIndex: number,
  versionId?: number,
) => requestProject(`${WRITER_BASE}/${projectId}/chapters/select`, {
  method: 'POST',
  body: JSON.stringify({
    chapter_number: chapterNumber,
    ...buildVersionSelectorPayload(versionIndex, versionId),
  }),
})

export const deleteChapterVersion = (
  projectId: string,
  chapterNumber: number,
  versionIndex: number,
  versionId?: number,
) => requestProject(`${WRITER_BASE}/${projectId}/chapters/delete-version`, {
  method: 'POST',
  body: JSON.stringify({
    chapter_number: chapterNumber,
    ...buildVersionSelectorPayload(versionIndex, versionId),
  }),
})

export const updateChapterOutline = (
  projectId: string,
  chapterOutline: ChapterOutline,
) => requestProject(`${WRITER_BASE}/${projectId}/chapters/update-outline`, {
  method: 'POST',
  body: JSON.stringify(chapterOutline),
})

export const startChapterOutlineRewrite = (
  projectId: string,
  chapterOutline: ChapterOutline,
  options: RewriteChapterOutlineOptions = {},
) => request(`${WRITER_BASE}/${projectId}/chapters/rewrite-outline/start`, {
  method: 'POST',
  body: JSON.stringify({
    chapter_number: chapterOutline.chapter_number,
    title: chapterOutline.title,
    summary: chapterOutline.summary,
    direction: options.direction?.trim() || undefined,
  }),
}) as Promise<OutlineGenerationJobResponse>

export const getChapterOutlineRewriteStatus = (
  projectId: string,
) => request(`${WRITER_BASE}/${projectId}/chapters/rewrite-outline/status`) as Promise<OutlineGenerationJobResponse>

export const cancelChapterOutlineRewrite = (
  projectId: string,
) => request(`${WRITER_BASE}/${projectId}/chapters/rewrite-outline/cancel`, {
  method: 'POST',
}) as Promise<OutlineGenerationJobResponse>

export const rewriteChapterOutline = async (
  projectId: string,
  chapterOutline: ChapterOutline,
  options: RewriteChapterOutlineOptions = {},
) => {
  let status = await startChapterOutlineRewrite(projectId, chapterOutline, options)

  for (let attempt = 0; attempt < OUTLINE_MAX_POLL_ATTEMPTS; attempt += 1) {
    if (status.status === 'successful' && status.project) {
      return normalizeProject(status.project)
    }
    if (status.status === 'failed') {
      throw new Error(readOutlineJobError(status))
    }
    if (status.status === 'cancelled') {
      throw new Error(status.progress_message || '章节大纲重写已取消')
    }

    await delay(OUTLINE_POLL_INTERVAL_MS)
    status = await getChapterOutlineRewriteStatus(projectId)
  }

  throw new Error('章节大纲重写后台任务等待超时，请稍后刷新项目查看结果。')
}

export const deleteChapter = (
  projectId: string,
  chapterNumbers: number[],
) => requestProject(`${WRITER_BASE}/${projectId}/chapters/delete`, {
  method: 'POST',
  body: JSON.stringify({ chapter_numbers: chapterNumbers }),
})

const buildOutlinePayload = (
  startChapter: number,
  numChapters: number,
  options: GenerateOutlineOptions = {},
): Record<string, number> => {
  const payload: Record<string, number> = {
    start_chapter: startChapter,
    num_chapters: numChapters,
  }
  if (options.targetTotalChapters && options.targetTotalChapters > 0) {
    payload.target_total_chapters = options.targetTotalChapters
  }
  if (options.targetTotalWords && options.targetTotalWords > 0) {
    payload.target_total_words = options.targetTotalWords
  }
  if (options.chapterWordTarget && options.chapterWordTarget > 0) {
    payload.chapter_word_target = options.chapterWordTarget
  }
  return payload
}

export const startChapterOutlineGeneration = (
  projectId: string,
  startChapter: number,
  numChapters: number,
  options: GenerateOutlineOptions = {},
) => {
  return request(`${WRITER_BASE}/${projectId}/chapters/outline/start`, {
    method: 'POST',
    body: JSON.stringify(buildOutlinePayload(startChapter, numChapters, options)),
  }) as Promise<OutlineGenerationJobResponse>
}

export const getChapterOutlineGenerationStatus = (
  projectId: string,
) => request(`${WRITER_BASE}/${projectId}/chapters/outline/status`) as Promise<OutlineGenerationJobResponse>

export const cancelChapterOutlineGeneration = (
  projectId: string,
) => request(`${WRITER_BASE}/${projectId}/chapters/outline/cancel`, {
  method: 'POST',
}) as Promise<OutlineGenerationJobResponse>

export const generateChapterOutline = async (
  projectId: string,
  startChapter: number,
  numChapters: number,
  options: GenerateOutlineOptions = {},
) => {
  let status = await startChapterOutlineGeneration(projectId, startChapter, numChapters, options)

  for (let attempt = 0; attempt < OUTLINE_MAX_POLL_ATTEMPTS; attempt += 1) {
    if (status.status === 'successful' && status.project) {
      return normalizeProject(status.project)
    }
    if (status.status === 'failed') {
      throw new Error(readOutlineJobError(status))
    }
    if (status.status === 'cancelled') {
      throw new Error(status.progress_message || '章节大纲生成已取消')
    }

    await delay(OUTLINE_POLL_INTERVAL_MS)
    status = await getChapterOutlineGenerationStatus(projectId)
  }

  throw new Error('章节大纲后台任务等待超时，请稍后刷新项目查看结果。')
}
