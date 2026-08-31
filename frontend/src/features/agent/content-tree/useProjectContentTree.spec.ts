import { describe, expect, it, vi } from 'vitest'

import type { NovelSectionResponse, NovelSectionType } from '@/api/novel'
import { useProjectContentTree } from './useProjectContentTree'

const chapterDetail = (chapterNumber: number, selectedVersionId = 22) => ({
  chapter_number: chapterNumber,
  title: `第${chapterNumber}章`,
  summary: '章节摘要',
  content: '正文只在点击章节后按需获取。',
  selected_version_id: selectedVersionId,
  versions: [
    { id: 21, content: '旧版本' },
    { id: 22, content: '新版本' },
  ],
  evaluation: null,
  generation_status: 'successful' as const,
})

const response = (section: 'chapters' | 'chapter_outline', data: Record<string, unknown>) => ({
  section,
  data,
})

describe('useProjectContentTree', () => {
  it('uses lightweight sections, groups volumes, and lazy-loads selected chapter once', async () => {
    const getSection = vi.fn(
      async (_projectId: string, section: 'chapters' | 'chapter_outline') => {
        if (section === 'chapters')
          return response('chapters', {
            chapters: [
              {
                chapter_number: 7,
                title: '七章',
                summary: '七章摘要',
                generation_status: 'successful',
                word_count: 700,
                content: 'MUST_NOT_USE_SECTION_CONTENT',
              },
              {
                chapter_number: 8,
                title: '八章',
                summary: '八章摘要',
                generation_status: 'not_generated',
                word_count: 0,
              },
            ],
          })
        return response('chapter_outline', {
          chapter_outline: [
            {
              chapter_number: 7,
              title: '七章大纲',
              summary: '大纲',
              metadata: { volume_number: 1, volume_title: '初入玄门' },
            },
          ],
        })
      },
    )
    const getChapter = vi.fn(async (_projectId: string, chapterNumber: number) =>
      chapterDetail(chapterNumber),
    )
    const tree = useProjectContentTree({
      getSection: getSection as (
        projectId: string,
        section: NovelSectionType,
      ) => Promise<NovelSectionResponse>,
      getChapter,
    })

    await tree.loadProject('project-a', { chapterNumber: 7, versionId: 22 })

    expect(getSection).toHaveBeenCalledWith('project-a', 'chapters')
    expect(getSection).toHaveBeenCalledWith('project-a', 'chapter_outline')
    expect(getChapter).toHaveBeenCalledTimes(1)
    expect(tree.volumes.value.map((volume) => volume.label)).toEqual(['第1卷 · 初入玄门', '未分卷'])
    expect(tree.volumes.value[0].chapters[0]).toMatchObject({
      chapterNumber: 7,
      wordCount: 700,
      volumeNumber: 1,
    })
    expect(JSON.stringify(tree.volumes.value)).not.toContain('MUST_NOT_USE_SECTION_CONTENT')
    expect(tree.selectedChapterNumber.value).toBe(7)
    expect(tree.selectedVersionId.value).toBe(22)
    expect(tree.loading.value).toBe(false)
    expect(tree.loadingChapter.value).toBe(false)

    await tree.selectChapter(7, 21)
    expect(getChapter).toHaveBeenCalledTimes(1)
    expect(tree.selectedVersionId.value).toBe(21)
  })

  it('falls back to the selected version or first version when deep-link version is absent', async () => {
    const getSection = vi.fn(async (_projectId: string, section: 'chapters' | 'chapter_outline') =>
      section === 'chapters'
        ? response('chapters', {
            chapters: [
              { chapter_number: 3, title: '三章', summary: '', generation_status: 'successful' },
            ],
          })
        : response('chapter_outline', { chapter_outline: [] }),
    )
    const getChapter = vi.fn(async (_projectId: string, chapterNumber: number) =>
      chapterDetail(chapterNumber, 22),
    )
    const tree = useProjectContentTree({
      getSection: getSection as (
        projectId: string,
        section: NovelSectionType,
      ) => Promise<NovelSectionResponse>,
      getChapter,
    })

    await tree.loadProject('project-b', { chapterNumber: 3, versionId: 999 })

    expect(tree.selectedVersionId.value).toBe(22)
  })

  it('drops stale project responses instead of overwriting the latest selected project', async () => {
    let resolveOldChapters: ((value: ReturnType<typeof response>) => void) | undefined
    let resolveOldOutline: ((value: ReturnType<typeof response>) => void) | undefined
    const getSection = vi.fn((projectId: string, section: 'chapters' | 'chapter_outline') => {
      if (projectId === 'old') {
        return new Promise((resolve) => {
          if (section === 'chapters') resolveOldChapters = resolve as typeof resolveOldChapters
          else resolveOldOutline = resolve as typeof resolveOldOutline
        })
      }
      return Promise.resolve(
        section === 'chapters'
          ? response('chapters', {
              chapters: [
                {
                  chapter_number: 9,
                  title: '新项目章节',
                  summary: '',
                  generation_status: 'successful',
                },
              ],
            })
          : response('chapter_outline', { chapter_outline: [] }),
      )
    })
    const getChapter = vi.fn()
    const tree = useProjectContentTree({
      getSection: getSection as (
        projectId: string,
        section: NovelSectionType,
      ) => Promise<NovelSectionResponse>,
      getChapter,
    })

    const oldLoad = tree.loadProject('old')
    await Promise.resolve()
    const newLoad = tree.loadProject('new')
    resolveOldChapters?.(
      response('chapters', {
        chapters: [
          { chapter_number: 1, title: '旧项目章节', summary: '', generation_status: 'successful' },
        ],
      }),
    )
    resolveOldOutline?.(response('chapter_outline', { chapter_outline: [] }))
    await Promise.all([oldLoad, newLoad])

    expect(tree.projectId.value).toBe('new')
    expect(
      tree.volumes.value.flatMap((volume) => volume.chapters).map((chapter) => chapter.title),
    ).toEqual(['新项目章节'])
  })

  it('clears version or chapter selection without reviving a fallback version', async () => {
    const getSection = vi.fn(async (_projectId: string, section: 'chapters' | 'chapter_outline') =>
      section === 'chapters'
        ? response('chapters', {
            chapters: [
              { chapter_number: 4, title: '四章', summary: '', generation_status: 'successful' },
            ],
          })
        : response('chapter_outline', { chapter_outline: [] }),
    )
    const getChapter = vi.fn(async (_projectId: string, chapterNumber: number) =>
      chapterDetail(chapterNumber, 22),
    )
    const tree = useProjectContentTree({
      getSection: getSection as (
        projectId: string,
        section: NovelSectionType,
      ) => Promise<NovelSectionResponse>,
      getChapter,
    })

    await tree.loadProject('project-clear', { chapterNumber: 4, versionId: 22 })
    tree.clearVersionSelection()
    expect(tree.selectedChapterNumber.value).toBe(4)
    expect(tree.selectedVersionId.value).toBeUndefined()

    tree.clearChapterSelection()
    expect(tree.selectedChapterNumber.value).toBeUndefined()
    expect(tree.selectedVersionId.value).toBeUndefined()
    expect(tree.selectedChapter.value).toBeNull()
  })
})
