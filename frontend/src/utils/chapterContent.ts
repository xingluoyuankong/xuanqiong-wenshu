import { stripThinkTags } from '@/utils/safeMarkdown'

const CHAPTER_CONTENT_KEYS = ['content', 'chapter_content', 'chapter_text', 'text', 'body', 'story'] as const

const looksLikeJsonPayload = (value: string): boolean => {
  const trimmed = value.trim()
  return (
    (trimmed.startsWith('{') && trimmed.endsWith('}')) ||
    (trimmed.startsWith('[') && trimmed.endsWith(']')) ||
    (trimmed.startsWith('"') && trimmed.endsWith('"'))
  )
}

export const extractChapterText = (value: unknown): string | null => {
  if (typeof value === 'string') {
    return value
  }

  if (Array.isArray(value)) {
    for (const item of value) {
      const nested = extractChapterText(item)
      if (nested) {
        return nested
      }
    }
    return null
  }

  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>
    for (const key of CHAPTER_CONTENT_KEYS) {
      if (record[key] !== undefined && record[key] !== null) {
        const nested = extractChapterText(record[key])
        if (nested) {
          return nested
        }
      }
    }
  }

  return null
}

export const normalizeChapterContent = (value: unknown): string => {
  if (value === null || value === undefined) {
    return ''
  }

  let rawText = ''
  if (typeof value === 'string') {
    rawText = value
  } else {
    rawText = extractChapterText(value) || ''
  }

  const trimmed = rawText.trim()
  if (trimmed && looksLikeJsonPayload(trimmed)) {
    try {
      const parsed = JSON.parse(trimmed)
      const extracted = extractChapterText(parsed)
      if (extracted) {
        rawText = extracted
      } else if (typeof parsed === 'string') {
        rawText = parsed
      }
    } catch {
      // Keep original text when JSON parsing fails.
    }
  }

  let normalized = rawText.replace(/^"|"$/g, '')
  normalized = normalized.replace(/\\r\\n/g, '\n')
  normalized = normalized.replace(/\\n/g, '\n')
  normalized = normalized.replace(/\\"/g, '"')
  normalized = normalized.replace(/\\t/g, '\t')
  normalized = normalized.replace(/\\\\/g, '\\')
  return stripThinkTags(normalized)
}

export const buildChapterPreview = (value: unknown, limit = 360): string => {
  const normalized = normalizeChapterContent(value)
  if (!normalized) return ''

  const paragraphs = normalized
    .split(/\n{2,}/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean)

  if (!paragraphs.length) {
    return normalized.length > limit ? `${normalized.slice(0, limit).trimEnd()}...` : normalized
  }

  let preview = ''
  for (const paragraph of paragraphs) {
    const candidate = preview ? `${preview}\n\n${paragraph}` : paragraph
    if (candidate.length > limit && preview) break
    preview = candidate
    if (preview.length >= limit) break
  }

  if (!preview) {
    preview = paragraphs[0].slice(0, limit)
  }

  return preview.length < normalized.length ? `${preview.trimEnd()}...` : preview
}
