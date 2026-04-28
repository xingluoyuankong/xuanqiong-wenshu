import DOMPurify from 'dompurify'
import { marked } from 'marked'

marked.setOptions({
  gfm: true,
  breaks: true,
})

const SANITIZE_OPTIONS = {
  USE_PROFILES: { html: true },
  ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto|tel):|[^a-z]|[a-z+.-]+(?:[^a-z+.-:]|$))/i,
}

export const stripThinkTags = (raw: string | null | undefined): string => {
  if (!raw) return ''

  const text = String(raw)
  return text
    .replace(/<think\b[^>]*>[\s\S]*?<\/think>/gi, '')
    .replace(/<think\b[^>]*>[\s\S]*$/gi, '')
    .replace(/<\/?think\b[^>]*>/gi, '')
    .trim()
}

export const renderSafeMarkdown = (raw: string | null | undefined): string => {
  const cleaned = stripThinkTags(raw)
  if (!cleaned) return ''

  try {
    const html = marked.parse(cleaned, { breaks: true }) as string
    return DOMPurify.sanitize(html, SANITIZE_OPTIONS)
  } catch {
    return DOMPurify.sanitize(String(cleaned || ''), SANITIZE_OPTIONS)
  }
}
