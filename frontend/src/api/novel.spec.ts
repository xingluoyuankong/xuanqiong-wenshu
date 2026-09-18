import { afterEach, describe, expect, it, vi } from 'vitest'
import { NovelAPI } from './novel'

describe('NovelAPI normalization', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('preserves chapter version quality metrics metadata from API responses', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      chapter_number: 1,
      title: '第一章',
      summary: '摘要',
      content: null,
      versions: [
        {
          id: 7,
          content: '正文',
          style: '标准',
          metadata: {
            quality_metrics: {
              scene_fulfillment_rate: 0.75,
              dialogue_changes_state: true,
            }
          }
        }
      ],
      evaluation: null,
      generation_status: 'waiting_for_confirm',
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })))

    const chapter = await NovelAPI.getChapter('project-1', 1)

    expect(chapter.versions?.[0]?.metadata?.quality_metrics).toEqual({
      scene_fulfillment_rate: 0.75,
      dialogue_changes_state: true,
    })
  })
})
