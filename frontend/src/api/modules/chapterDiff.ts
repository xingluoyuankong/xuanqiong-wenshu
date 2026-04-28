import { API_BASE_URL, API_PREFIX } from '@/api/config'

const PATCH_DIFF_BASE = `${API_BASE_URL}${API_PREFIX}`

const request = async <T>(url: string, options?: RequestInit): Promise<T> => {
  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...(options?.headers || {}),
    },
    ...options,
  })

  if (!response.ok) {
    let message = `请求失败，状态码: ${response.status}`
    try {
      const payload = await response.json()
      message = payload?.detail?.message || payload?.detail || payload?.message || message
    } catch {
      const text = await response.text().catch(() => '')
      if (text.trim()) {
        message = text.trim().slice(0, 220)
      }
    }
    throw new Error(message)
  }

  return response.json() as Promise<T>
}

export interface ChapterDiffLine {
  line_number: number
  original_line: string | null
  patched_line: string | null
  change_type: 'added' | 'modified' | 'deleted' | 'unchanged'
}

export interface ChapterDiffResult {
  chapter_number: number
  diff_lines: ChapterDiffLine[]
  summary: {
    total_lines: number
    added: number
    deleted: number
    modified: number
    unchanged: number
  }
}

export interface ChapterPatchApplyResult {
  status: string
  message: string
  patch_id: number
  chapter_number: number
}

export interface ChapterVersionDiffResult {
  chapter_number: number
  version1_id: number
  version2_id: number
  diff_lines: ChapterDiffLine[]
  summary: {
    total_lines: number
    added: number
    deleted: number
    modified: number
    unchanged: number
  }
}

export const getChapterDiff = (
  projectId: string,
  chapterNumber: number,
  original: string,
  patched: string
) => request<ChapterDiffResult>(`${PATCH_DIFF_BASE}/projects/${projectId}/chapters/${chapterNumber}/diff`, {
  method: 'POST',
  body: JSON.stringify({
    original_text: original,
    patched_text: patched,
  }),
})

export const applyChapterPatch = (
  projectId: string,
  chapterNumber: number,
  original: string,
  patched: string
) => request<ChapterPatchApplyResult>(`${PATCH_DIFF_BASE}/projects/${projectId}/chapters/${chapterNumber}/patch/apply`, {
  method: 'POST',
  body: JSON.stringify({
    original_text: original,
    patched_text: patched,
  }),
})

export const getChapterVersionDiff = (
  projectId: string,
  chapterNumber: number,
  v1: number,
  v2: number
) => request<ChapterVersionDiffResult>(`${PATCH_DIFF_BASE}/projects/${projectId}/chapters/${chapterNumber}/versions/${v1}/vs/${v2}`)
