import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ResearchCenterSection from './ResearchCenterSection.vue'

const api = vi.hoisted(() => ({
  getResearchConfig: vi.fn(),
  listResearchArtifacts: vi.fn(),
  updateResearchConfig: vi.fn(),
  startResearchJob: vi.fn(),
  getResearchJobStatus: vi.fn(),
  cancelResearchJob: vi.fn(),
}))

vi.mock('@/api/novel', () => ({ NovelAPI: api }))

const config = {
  mode: 'auto', enabled: true, search_provider: 'tavily', reuse_writing_llm: true,
  local_model_enabled: false, global_research_enabled: true,
  enhanced_research_enabled: true, chapter_research_enabled: true,
  max_parallel_queries: 4, max_results_per_query: 5,
}

describe('ResearchCenterSection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.getResearchConfig.mockResolvedValue(config)
    api.listResearchArtifacts.mockResolvedValue([])
  })

  it('uses background job polling for manual research', async () => {
    api.startResearchJob.mockResolvedValue({ run_id: 'run-1', project_id: 'p1', scope: 'global', status: 'queued' })
    api.getResearchJobStatus.mockResolvedValue({ run_id: 'run-1', project_id: 'p1', scope: 'global', status: 'successful' })
    const wrapper = mount(ResearchCenterSection, { props: { projectId: 'p1' } })
    await flushPromises()
    await wrapper.findAll('button').find(button => button.text().includes('运行全局研究'))!.trigger('click')
    await flushPromises()
    expect(api.startResearchJob).toHaveBeenCalledWith('p1', expect.objectContaining({ scope: 'global', force: true }))
    expect(api.getResearchJobStatus).toHaveBeenCalledWith('p1', 'run-1')
    expect(wrapper.text()).toContain('研究运行完成')
  })

  it('saves category and domain lists as normalized arrays', async () => {
    api.updateResearchConfig.mockResolvedValue(config)
    const wrapper = mount(ResearchCenterSection, { props: { projectId: 'p1' } })
    await flushPromises()
    const inputs = wrapper.findAll('input')
    const category = inputs.find(input => input.attributes('placeholder')?.includes('history,culture'))!
    const preferred = inputs.find(input => input.attributes('placeholder')?.includes('gov.cn'))!
    await category.setValue('naming，history')
    await preferred.setValue('gov.cn, edu.cn')
    await wrapper.findAll('button').find(button => button.text().includes('保存配置'))!.trigger('click')
    await flushPromises()
    expect(api.updateResearchConfig).toHaveBeenCalledWith('p1', expect.objectContaining({
      category_preferences: ['naming', 'history'],
      preferred_domains: ['gov.cn', 'edu.cn'],
      local_model_enabled: false,
    }))
  })

  it('renders source credibility without exposing a server absolute path', async () => {
    api.listResearchArtifacts.mockResolvedValue([{
      id: 1, run_id: 'r', project_id: 'p1', scope: 'global', status: 'successful', trigger: 'manual_ui',
      summary: '摘要', file_manifest: { run_directory: 'blueprint/global/r' },
      sources: [{ url: 'https://archives.gov.cn/doc', title: '档案', credibility_score: 95, trust_tier: 'official_or_education', cross_source_count: 2 }],
    }])
    const wrapper = mount(ResearchCenterSection, { props: { projectId: 'p1' } })
    await flushPromises()
    expect(wrapper.text()).toContain('可信度 95')
    expect(wrapper.text()).toContain('官方/教育')
    expect(wrapper.text()).toContain('blueprint/global/r')
    expect(wrapper.text()).not.toContain('D:\\')
  })
})