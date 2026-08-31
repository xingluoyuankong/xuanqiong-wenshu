import { computed, ref } from 'vue'

import { NovelAPI } from '@/api/novel'
import type { Chapter, ChapterOutline, NovelSectionResponse } from '@/api/novel'
import type { AgentContentChapter, AgentContentTreeSelection, AgentContentVolume } from './types'

type SectionApi = Pick<typeof NovelAPI, 'getSection' | 'getChapter'>

const positiveInteger = (value: unknown): number | undefined => {
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isInteger(parsed) && parsed >= 1 ? parsed : undefined
}

const text = (value: unknown, fallback = ''): string =>
  typeof value === 'string' && value.trim() ? value.trim() : fallback

const record = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {}

const list = (value: unknown): unknown[] => (Array.isArray(value) ? value : [])

const asOutline = (value: unknown): ChapterOutline | undefined => {
  const raw = record(value)
  const chapterNumber = positiveInteger(raw.chapter_number)
  if (!chapterNumber) return undefined
  return {
    chapter_number: chapterNumber,
    title: text(raw.title, `第${chapterNumber}章`),
    summary: text(raw.summary),
    narrative_phase: text(raw.narrative_phase) || undefined,
    chapter_role: text(raw.chapter_role) || undefined,
    metadata: record(raw.metadata),
  }
}

const chapterFromSection = (
  value: unknown,
  outlines: Map<number, ChapterOutline>,
): AgentContentChapter | undefined => {
  const raw = record(value)
  const chapterNumber = positiveInteger(raw.chapter_number)
  if (!chapterNumber) return undefined
  const outline = outlines.get(chapterNumber)
  const metadata = record(outline?.metadata)
  const volumeNumber = positiveInteger(metadata.volume_number)
  const volumeTitle = text(metadata.volume_title)
  const wordCount = positiveInteger(raw.word_count)
  return {
    chapterNumber,
    title: text(raw.title, outline?.title || `第${chapterNumber}章`),
    summary: text(raw.summary, outline?.summary || ''),
    generationStatus: text(raw.generation_status, 'not_generated'),
    wordCount,
    outline,
    volumeNumber,
    volumeTitle: volumeTitle || undefined,
  }
}

export const groupAgentContentVolumes = (chapters: AgentContentChapter[]): AgentContentVolume[] => {
  const groups = new Map<string, AgentContentVolume>()
  for (const chapter of chapters
    .slice()
    .sort((left, right) => left.chapterNumber - right.chapterNumber)) {
    const key = chapter.volumeNumber ? `volume:${chapter.volumeNumber}` : 'unassigned'
    const current = groups.get(key) || {
      id: key,
      label: chapter.volumeNumber
        ? `第${chapter.volumeNumber}卷${chapter.volumeTitle ? ` · ${chapter.volumeTitle}` : ''}`
        : '未分卷',
      volumeNumber: chapter.volumeNumber,
      volumeTitle: chapter.volumeTitle,
      chapters: [],
    }
    current.chapters.push(chapter)
    groups.set(key, current)
  }
  return [...groups.values()].sort((left, right) => {
    if (left.volumeNumber === undefined) return 1
    if (right.volumeNumber === undefined) return -1
    return left.volumeNumber - right.volumeNumber
  })
}

export function useProjectContentTree(api: SectionApi = NovelAPI) {
  const projectId = ref<string>()
  const volumes = ref<AgentContentVolume[]>([])
  const selectedChapterNumber = ref<number>()
  const selectedVersionId = ref<number>()
  const selectedChapter = ref<Chapter | null>(null)
  const loading = ref(false)
  const loadingChapter = ref(false)
  const error = ref<string>()
  const detailCache = new Map<string, Chapter>()
  let treeGeneration = 0
  let chapterGeneration = 0

  const selectedVersion = computed(() => {
    const versions = Array.isArray(selectedChapter.value?.versions)
      ? selectedChapter.value!.versions
      : []
    return (
      versions.find((version) => positiveInteger(version.id) === selectedVersionId.value) || null
    )
  })

  const reset = () => {
    treeGeneration += 1
    chapterGeneration += 1
    projectId.value = undefined
    volumes.value = []
    selectedChapterNumber.value = undefined
    selectedVersionId.value = undefined
    selectedChapter.value = null
    loading.value = false
    loadingChapter.value = false
    error.value = undefined
  }

  const selectVersion = (versionId?: number) => {
    const valid = (
      Array.isArray(selectedChapter.value?.versions) ? selectedChapter.value!.versions : []
    ).some((version) => positiveInteger(version.id) === versionId)
    selectedVersionId.value = valid
      ? versionId
      : positiveInteger(selectedChapter.value?.selected_version_id) ||
        positiveInteger(selectedChapter.value?.versions?.[0]?.id)
  }

  const clearVersionSelection = () => {
    selectedVersionId.value = undefined
  }

  const clearChapterSelection = () => {
    chapterGeneration += 1
    selectedChapterNumber.value = undefined
    selectedVersionId.value = undefined
    selectedChapter.value = null
    loadingChapter.value = false
    error.value = undefined
  }

  const selectChapter = async (chapterNumber: number, versionId?: number) => {
    const activeProjectId = projectId.value
    const normalizedChapter = positiveInteger(chapterNumber)
    if (!activeProjectId || !normalizedChapter) return
    selectedChapterNumber.value = normalizedChapter
    const key = `${activeProjectId}:${normalizedChapter}`
    const cached = detailCache.get(key)
    if (cached) {
      selectedChapter.value = cached
      selectVersion(versionId)
      return
    }
    const generation = ++chapterGeneration
    loadingChapter.value = true
    error.value = undefined
    try {
      const detail = await api.getChapter(activeProjectId, normalizedChapter)
      if (generation !== chapterGeneration || activeProjectId !== projectId.value) return
      detailCache.set(key, detail)
      selectedChapter.value = detail
      selectVersion(versionId)
    } catch (reason) {
      if (generation !== chapterGeneration || activeProjectId !== projectId.value) return
      error.value = reason instanceof Error ? reason.message : '章节详情加载失败'
      selectedChapter.value = null
    } finally {
      if (generation === chapterGeneration) loadingChapter.value = false
    }
  }

  const loadProject = async (nextProjectId?: string, selection: AgentContentTreeSelection = {}) => {
    const normalizedProjectId = text(nextProjectId)
    const generation = ++treeGeneration
    chapterGeneration += 1
    projectId.value = normalizedProjectId || undefined
    volumes.value = []
    selectedChapterNumber.value = undefined
    selectedVersionId.value = undefined
    selectedChapter.value = null
    error.value = undefined
    if (!normalizedProjectId) return
    loading.value = true
    try {
      const [chaptersResponse, outlineResponse] = await Promise.all([
        api.getSection(normalizedProjectId, 'chapters'),
        api.getSection(normalizedProjectId, 'chapter_outline'),
      ])
      if (generation !== treeGeneration || normalizedProjectId !== projectId.value) return
      const outlineMap = new Map<number, ChapterOutline>()
      for (const rawOutline of list(
        (outlineResponse as NovelSectionResponse).data?.chapter_outline,
      )) {
        const outline = asOutline(rawOutline)
        if (outline) outlineMap.set(outline.chapter_number, outline)
      }
      const chapters = list((chaptersResponse as NovelSectionResponse).data?.chapters)
        .map((rawChapter) => chapterFromSection(rawChapter, outlineMap))
        .filter((chapter): chapter is AgentContentChapter => Boolean(chapter))
      volumes.value = groupAgentContentVolumes(chapters)
      const requestedChapter = positiveInteger(selection.chapterNumber)
      if (
        requestedChapter &&
        chapters.some((chapter) => chapter.chapterNumber === requestedChapter)
      ) {
        await selectChapter(requestedChapter, selection.versionId)
      }
    } catch (reason) {
      if (generation !== treeGeneration || normalizedProjectId !== projectId.value) return
      error.value = reason instanceof Error ? reason.message : '项目内容目录加载失败'
    } finally {
      if (generation === treeGeneration) loading.value = false
    }
  }

  return {
    projectId,
    volumes,
    selectedChapterNumber,
    selectedVersionId,
    selectedChapter,
    selectedVersion,
    loading,
    loadingChapter,
    error,
    reset,
    loadProject,
    selectChapter,
    selectVersion,
    clearVersionSelection,
    clearChapterSelection,
  }
}
