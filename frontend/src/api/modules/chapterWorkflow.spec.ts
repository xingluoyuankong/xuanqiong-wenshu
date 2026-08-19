import { afterEach, describe, expect, it, vi } from 'vitest'
import { deleteChapterVersion, evaluateChapter, generateChapter, generateChapterOutline, resumeChapterGeneration, rewriteChapterOutline, selectChapterVersion } from './chapterWorkflow'

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

  it('sends long-form volume params as snake_case to the outline endpoint', async () => {
    const fetchMock = vi.fn(async () => new Response(
      JSON.stringify({
        run_id: 'outline-run-2',
        project_id: 'project-1',
        status: 'successful',
        progress_stage: 'successful',
        progress_message: '章节大纲生成完成',
        project: projectPayload,
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ))
    vi.stubGlobal('fetch', fetchMock)

    // 回归：前端分卷控件曾发送 camelCase 且中途被丢弃，后端永远收不到
    await generateChapterOutline('project-1', 1, 10, {
      targetTotalWords: 1200000,
      volumeCount: 10,
      chaptersPerVolume: 25,
      longForm: true,
    })

    const body = parseFirstRequestBody(fetchMock)
    expect(body).toMatchObject({
      start_chapter: 1,
      num_chapters: 10,
      target_total_words: 1200000,
      volume_count: 10,
      chapters_per_volume: 25,
      long_form: true,
    })
    expect(body).not.toHaveProperty('volumeCount')
    expect(body).not.toHaveProperty('chaptersPerVolume')
  })

  it('omits long-form volume params when not in long-form mode', async () => {
    const fetchMock = vi.fn(async () => new Response(
      JSON.stringify({
        run_id: 'outline-run-3',
        project_id: 'project-1',
        status: 'successful',
        progress_stage: 'successful',
        progress_message: '章节大纲生成完成',
        project: projectPayload,
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ))
    vi.stubGlobal('fetch', fetchMock)

    await generateChapterOutline('project-1', 1, 10, { targetTotalChapters: 60 })

    const body = parseFirstRequestBody(fetchMock)
    expect(body).not.toHaveProperty('volume_count')
    expect(body).not.toHaveProperty('chapters_per_volume')
    expect(body).not.toHaveProperty('long_form')
  })

  it('routes chapter outline rewrite through the background job entry', async () => {
    const fetchMock = vi.fn(async () => new Response(
      JSON.stringify({
        run_id: 'outline-rewrite-run-1',
        project_id: 'project-1',
        status: 'successful',
        progress_stage: 'successful',
        progress_message: '章节大纲重写完成',
        project: projectPayload,
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ))
    vi.stubGlobal('fetch', fetchMock)

    const result = await rewriteChapterOutline(
      'project-1',
      { chapter_number: 8, title: '旧标题', summary: '旧摘要' } as any,
      { direction: '加强冲突' },
    )

    const [url] = fetchMock.mock.calls[0] as unknown as [string, RequestInit?]
    const body = parseFirstRequestBody(fetchMock)
    expect(url).toContain('/chapters/rewrite-outline/start')
    expect(body).toMatchObject({ chapter_number: 8, title: '旧标题', summary: '旧摘要', direction: '加强冲突' })
    expect(result.id).toBe('project-1')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})


describe('章节生成配置契约', () => {
  it('发送长篇分段预算与任务超时配置', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ id: 'p1', chapters: [] }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    await generateChapter('p1', 1, { segmentWordLimit: 3200, generationTimeoutSeconds: 3600 })
    const [, init] = (fetchMock.mock.calls as unknown as Array<[string, RequestInit?]>)[0]
    expect(init).toBeDefined()
    const payload = JSON.parse(String(init?.body))
    expect(payload.segment_word_limit).toBe(3200)
    expect(payload.generation_timeout_seconds).toBe(3600)
  })

  it('通过章节恢复接口复用同一个持久化任务 run_id', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ id: 'p1', chapters: [] }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    await resumeChapterGeneration('p1', 'run-longform-1')

    const [url, init] = (fetchMock.mock.calls as unknown as Array<[string, RequestInit?]>)[0]
    expect(url).toContain('/api/writer/novels/p1/chapters/resume')
    const payload = JSON.parse(String(init?.body))
    expect(payload).toEqual({ run_id: 'run-longform-1' })
  })
})
