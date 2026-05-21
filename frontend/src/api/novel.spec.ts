import { afterEach, describe, expect, it, vi } from 'vitest'
import { NovelAPI, OptimizerAPI } from './novel'

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

  it('routes legacy blueprint generation through the background job endpoint', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      expect(url).toContain('/blueprint/generate/start')
      expect(url).not.toMatch(/\/blueprint\/generate$/)
      return new Response(JSON.stringify({
        run_id: 'run-1',
        project_id: 'project-1',
        status: 'successful',
        progress_stage: 'done',
        progress_message: '蓝图生成完成',
        blueprint: {
          title: '测试长篇',
          chapter_outline: [],
        },
        ai_message: '蓝图已生成',
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    })
    vi.stubGlobal('fetch', fetchMock)

    const response = await NovelAPI.generateBlueprint('project-1')

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(response.blueprint.title).toBe('测试长篇')
    expect(response.ai_message).toBe('蓝图已生成')
  })

  it('routes style profile creation through the background job endpoint', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      expect(url).toContain('/style/profiles/start')
      expect(url).not.toMatch(/\/style\/profiles$/)
      const body = JSON.parse(String(init?.body || '{}'))
      expect(body).toMatchObject({ source_ids: ['src-1'], name: '冷峻叙事' })
      return new Response(JSON.stringify({
        run_id: 'style-run-1',
        project_id: 'project-1',
        status: 'successful',
        progress_stage: 'successful',
        progress_message: '文风画像生成完成',
        profile: { id: 'profile-1', name: '冷峻叙事' },
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    })
    vi.stubGlobal('fetch', fetchMock)

    const response = await OptimizerAPI.createStyleProfile('project-1', {
      source_ids: ['src-1'],
      name: '冷峻叙事',
    })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(response.profile.id).toBe('profile-1')
  })
})
