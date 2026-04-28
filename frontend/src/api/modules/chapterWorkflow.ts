import { API_BASE_URL } from '@/api/config'
import {
  ApiError,
  type CancelChapterOptions,
  type Chapter,
  type ChapterOutline,
  type GenerateChapterOptions,
  type GenerateOutlineOptions,
  type NovelProject,
  type RewriteChapterOutlineOptions,
} from '@/api/novel'
import { normalizeChapterContent } from '@/utils/chapterContent'

const WRITER_PREFIX = '/api/writer'
const WRITER_BASE = `${API_BASE_URL}${WRITER_PREFIX}/novels`

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

const requestProject = async (url: string, options?: RequestInit): Promise<NovelProject> => {
  const project = await request(url, options)
  return normalizeProject(project as NovelProject)
}

const requestChapter = async (url: string, options?: RequestInit): Promise<Chapter> => {
  const chapter = await request(url, options)
  return normalizeChapter(chapter as Chapter)
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
  evaluateAll: boolean = false,
) => requestProject(`${WRITER_BASE}/${projectId}/chapters/evaluate`, {
  method: 'POST',
  body: JSON.stringify({
    chapter_number: chapterNumber,
    version_index: versionIndex,
    evaluate_all: evaluateAll,
  }),
})

export const selectChapterVersion = (
  projectId: string,
  chapterNumber: number,
  versionIndex: number,
) => requestProject(`${WRITER_BASE}/${projectId}/chapters/select`, {
  method: 'POST',
  body: JSON.stringify({
    chapter_number: chapterNumber,
    version_index: versionIndex,
  }),
})

export const deleteChapterVersion = (
  projectId: string,
  chapterNumber: number,
  versionIndex: number,
) => requestProject(`${WRITER_BASE}/${projectId}/chapters/delete-version`, {
  method: 'POST',
  body: JSON.stringify({
    chapter_number: chapterNumber,
    version_index: versionIndex,
  }),
})

export const updateChapterOutline = (
  projectId: string,
  chapterOutline: ChapterOutline,
) => requestProject(`${WRITER_BASE}/${projectId}/chapters/update-outline`, {
  method: 'POST',
  body: JSON.stringify(chapterOutline),
})

export const rewriteChapterOutline = (
  projectId: string,
  chapterOutline: ChapterOutline,
  options: RewriteChapterOutlineOptions = {},
) => requestProject(`${WRITER_BASE}/${projectId}/chapters/rewrite-outline`, {
  method: 'POST',
  body: JSON.stringify({
    chapter_number: chapterOutline.chapter_number,
    title: chapterOutline.title,
    summary: chapterOutline.summary,
    direction: options.direction?.trim() || undefined,
  }),
})

export const deleteChapter = (
  projectId: string,
  chapterNumbers: number[],
) => requestProject(`${WRITER_BASE}/${projectId}/chapters/delete`, {
  method: 'POST',
  body: JSON.stringify({ chapter_numbers: chapterNumbers }),
})

export const generateChapterOutline = (
  projectId: string,
  startChapter: number,
  numChapters: number,
  options: GenerateOutlineOptions = {},
) => {
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

  return requestProject(`${WRITER_BASE}/${projectId}/chapters/outline`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}
