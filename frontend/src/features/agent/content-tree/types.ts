import type { Chapter, ChapterOutline } from '@/api/novel'

export interface AgentContentChapter {
  chapterNumber: number
  title: string
  summary: string
  generationStatus: string
  wordCount?: number
  outline?: ChapterOutline
  volumeNumber?: number
  volumeTitle?: string
}

export interface AgentContentVolume {
  id: string
  label: string
  volumeNumber?: number
  volumeTitle?: string
  chapters: AgentContentChapter[]
}

export interface AgentContentTreeSelection {
  chapterNumber?: number
  versionId?: number
}

export interface AgentContentTreeSnapshot {
  projectId?: string
  volumes: AgentContentVolume[]
  selectedChapterNumber?: number
  selectedVersionId?: number
  selectedChapter?: Chapter | null
  loading: boolean
  loadingChapter: boolean
  error?: string
}
