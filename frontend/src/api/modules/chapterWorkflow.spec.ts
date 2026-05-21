import { afterEach, describe, expect, it, vi } from 'vitest'
import { deleteChapterVersion, evaluateChapter, generateChapterOutline, selectChapterVersion } from './chapterWorkflow'

const projectPayload = {
  id: 'project-1',
  title: '测试项目',
  initial_prompt: '写一部测试小说',
  blueprint: null,
  chapters: [],
  conversation_history: [],
}

const parseFirstRequestBody = (fetchMock: ReturnType<typeof vi.fn>) => {
  const [, init] = fetchMock.mock.calls[0] as [unknown, RequestInit?]
  return JSON.parse(String(init?.body || '{}'))
}

describe('chapter workflow version selectors', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('sends stable version_id without version_index when selecting a version', async () => {
    const fetchMock = vi.fn(async () => new Response(
      JSON.stringify(projectPayload),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ))
    vi.stubGlobal('fetch', fetchMock)

    await selectChapterVersion('project-1', 3, 0, 42)

    const body = parseFirstRequestBody(fetchMock)
    expect(body).toMatchObject({ chapter_number: 3, version_id: 42 })
    expect(body).not.toHaveProperty('version_index')
  })

  it('falls back to version_index only when no stable id is available', async () => {
    const fetchMock = vi.fn(async () => new Response(
      JSON.stringify(projectPayload),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ))
    vi.stubGlobal('fetch', fetchMock)

    await deleteChapterVersion('project-1', 3, 1)

    const body = parseFirstRequestBody(fetchMock)
    expect(body).toMatchObject({ chapter_number: 3, version_index: 1 })
    expect(body).not.toHaveProperty('version_id')
  })

  it('uses version_id as the only selector for evaluation requests', async () => {
    const fetchMock = vi.fn(async () => new Response(
      JSON.stringify(projectPayload),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ))
    vi.stubGlobal('fetch', fetchMock)

    await evaluateChapter('project-1', 3, 2, 77)

    const body = parseFirstRequestBody(fetchMock)
    expect(body).toMatchObject({ chapter_number: 3, version_id: 77, evaluate_all: false })
    expect(body).not.toHaveProperty('version_index')
  })

  it('routes chapter outline generation through the background job entry', async () => {
    const fetchMock = vi.fn(async () => new Response(
      JSON.stringify({
        run_id: 'outline-run-1',
        project_id: 'project-1',
        status: 'successful',
        progress_stage: 'successful',
        progress_message: '章节大纲生成完成',
        project: projectPayload,
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ))
    vi.stubGlobal('fetch', fetchMock)

    const result = await generateChapterOutline('project-1', 5, 8, { targetTotalChapters: 80 })

    const [url] = fetchMock.mock.calls[0] as unknown as [string, RequestInit?]
    const body = parseFirstRequestBody(fetchMock)
    expect(url).toContain('/chapters/outline/start')
    expect(body).toMatchObject({ start_chapter: 5, num_chapters: 8, target_total_chapters: 80 })
    expect(result.id).toBe('project-1')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})
