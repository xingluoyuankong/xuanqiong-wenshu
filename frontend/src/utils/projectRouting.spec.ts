import { describe, expect, it } from 'vitest'
import type { NovelProject, NovelProjectSummary } from '@/api/novel'
import {
  resolveProjectWritingEntry,
  resolveProjectWritingEntryFromSummary,
  shouldResumeInspirationFromProject,
} from './projectRouting'

const buildProject = (overrides: Partial<NovelProject> = {}): NovelProject => ({
  id: 'proj-1',
  title: '测试项目',
  initial_prompt: 'prompt',
  blueprint: undefined,
  chapters: [],
  conversation_history: [],
  ...overrides,
})

const buildSummary = (overrides: Partial<NovelProjectSummary> = {}): NovelProjectSummary => ({
  id: 'proj-1',
  title: '测试项目',
  genre: '玄幻',
  last_edited: '2026-05-04T00:00:00Z',
  completed_chapters: 0,
  total_chapters: 1,
  ...overrides,
})

describe('projectRouting', () => {
  it('将已回退但仍保留正文的蓝图项目送回灵感页', () => {
    const project = buildProject({
      chapters: [{ chapter_number: 1, content: '已写正文' } as any],
      blueprint: {
        title: '异海开拓史',
        one_sentence_summary: '在异海求生并建立新文明',
        characters: [{ name: '林渡', role: '主角' } as any],
        novel_outline: [],
        chapter_outline: [],
      },
    })

    expect(shouldResumeInspirationFromProject(project)).toBe(true)
    expect(resolveProjectWritingEntry(project)).toBe('/inspiration?project_id=proj-1')
  })

  it('将已有章节大纲的正式项目送回写作页', () => {
    const project = buildProject({
      chapters: [{ chapter_number: 1, content: '已写正文' } as any],
      blueprint: {
        title: '异海开拓史',
        novel_outline: [{ stage: 1, title: '孤岛立足' } as any],
        chapter_outline: [{ chapter_number: 1, title: '第1章', summary: '摘要' } as any],
      },
    })

    expect(shouldResumeInspirationFromProject(project)).toBe(false)
    expect(resolveProjectWritingEntry(project)).toBe('/novel/proj-1')
  })

  it('工作区摘要仍按零章节项目进入灵感页', () => {
    const summary = buildSummary({ total_chapters: 0 })

    expect(resolveProjectWritingEntryFromSummary(summary)).toBe('/inspiration?project_id=proj-1')
  })
})
