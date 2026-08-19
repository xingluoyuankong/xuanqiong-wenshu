import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ChaptersSection from './ChaptersSection.vue'
import { setAccessToken } from '@/stores/auth'

const api = vi.hoisted(() => ({
  getChapter: vi.fn(),
}))

vi.mock('@/api/novel', () => ({ NovelAPI: api }))
vi.mock('@/api/admin', () => ({ AdminAPI: { getNovelChapter: vi.fn() } }))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: 'project-export' } }),
}))

const response = (body: unknown, blob = false) => ({
  ok: true,
  status: 200,
  json: vi.fn().mockResolvedValue(body),
  text: vi.fn().mockResolvedValue(JSON.stringify(body)),
  blob: vi.fn().mockResolvedValue(blob ? new Blob(['exported']) : new Blob()),
})

describe('ChaptersSection export authentication', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setAccessToken('test-token')
    api.getChapter.mockResolvedValue({
      chapter_number: 1,
      title: '第一章',
      content: '正文',
      versions: [],
    })
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(response({
        ready: true, total_chapters: 1, outline_chapters: 1,
        exportable_chapters: 1, total_word_count: 2,
      }))
      .mockResolvedValueOnce(response({}, true)))
    vi.stubGlobal('alert', vi.fn())
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn().mockReturnValue('blob:test'),
      revokeObjectURL: vi.fn(),
    })
  })

  it('sends Authorization on export preflight and download requests', async () => {
    const wrapper = mount(ChaptersSection, {
      props: { chapters: [{ chapter_number: 1, title: '第一章' }] },
    })
    await flushPromises()
    await wrapper.find('button[title="导出全部章节为TXT"]').trigger('click')
    await flushPromises()

    const calls = vi.mocked(fetch).mock.calls
    expect(calls).toHaveLength(2)
    expect((calls[0]?.[1] as RequestInit).headers).toBeInstanceOf(Headers)
    expect((calls[1]?.[1] as RequestInit).headers).toBeInstanceOf(Headers)
    expect(new Headers((calls[0]?.[1] as RequestInit).headers).get('Authorization')).toBe('Bearer test-token')
    expect(new Headers((calls[1]?.[1] as RequestInit).headers).get('Authorization')).toBe('Bearer test-token')
  })
})
