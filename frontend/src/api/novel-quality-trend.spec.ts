import { afterEach, describe, expect, it, vi } from 'vitest'
import { NovelAPI } from './novel-client'

describe('NovelAPI quality trend', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('GETs the project quality-trend endpoint and returns the typed aggregate', async () => {
    const payload = {
      project_id: 'project-9',
      chapter_count: 1,
      chapters: [
        {
          chapter_number: 1,
          status: 'successful',
          score: 860,
          word_count: 3000,
          event_density_passed: true,
          ending_pressure_passed: true,
          dialogue_changes_state: true,
          static_description_risk: false,
          blocker_codes: [],
          exemptions: [],
          critique_exemption_applied: [],
        },
      ],
      blocker_counts: {},
      exemption_counts: {},
    }
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(String(input)).toMatch(/\/api\/novels\/project-9\/quality-trend$/)
      expect(init?.method).toBeUndefined()
      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await NovelAPI.getQualityTrend('project-9')

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(result).toEqual(payload)
  })
})
