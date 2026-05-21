import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import LLMSettings from './LLMSettings.vue'

const { getLLMConfigMock, getProviderHealthCheckMock } = vi.hoisted(() => ({
  getLLMConfigMock: vi.fn(),
  getProviderHealthCheckMock: vi.fn(),
}))

vi.mock('@/api/llm', () => ({
  getLLMConfig: getLLMConfigMock,
  createOrUpdateLLMConfig: vi.fn(),
  getAvailableModels: vi.fn(),
  getProviderHealthCheck: getProviderHealthCheckMock,
  autoSwitchProvider: vi.fn(),
}))

describe('LLMSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getLLMConfigMock.mockResolvedValue({
      user_id: 1,
      llm_provider_url: 'http://localhost:8317/v1',
      llm_provider_model: 'test-model',
      llm_provider_api_key_masked: 'sk-***',
      llm_provider_api_key_configured: true,
      llm_provider_profiles: [{
        id: 'cpa',
        name: 'CPA Provider',
        enabled: true,
        llm_provider_url: 'http://localhost:8317/v1',
        api_keys: [{ value: '', enabled: true, masked_value: 'sk-***', has_value: true, is_masked: true }],
        models: [{ value: 'test-model', enabled: true }],
      }],
    })
  })

  it('健康检查展示 key 级失败归因和重试建议', async () => {
    getProviderHealthCheckMock.mockResolvedValue({
      checked_at: '2026-05-21T08:00:00.000Z',
      overall_status: 'degraded',
      has_usable_profile: false,
      recommended_profile_id: null,
      recommended_profile_name: null,
      current_profile_id: 'cpa',
      current_profile_name: 'CPA Provider',
      current_profile_usable: false,
      recommended_action: '未发现可用 Provider，请先修复网络、API Key 或额度问题。',
      profiles: [{
        profile_id: 'cpa',
        profile_name: 'CPA Provider',
        enabled: true,
        llm_provider_url: 'http://localhost:8317/v1',
        status: 'degraded',
        summary: '可达但不可用（通常是 Key、配额或限流问题）',
        reachable: true,
        usable: false,
        model_count: 0,
        checked_key_count: 1,
        keys: [{
          key_index: 1,
          key_mask: 'sk-***',
          enabled: true,
          reachable: true,
          usable: false,
          model_count: 0,
          status_code: 429,
          latency_ms: 1280,
          detail: '请求被限流或额度不足',
        }],
      }],
    })

    const wrapper = mount(LLMSettings)
    await flushPromises()

    const button = wrapper.findAll('button').find(item => item.text() === '健康检查')
    expect(button).toBeTruthy()
    await button!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('CPA Provider')
    expect(wrapper.text()).toContain('请求被限流或额度不足')
    expect(wrapper.text()).toContain('HTTP 429')
    expect(wrapper.text()).toContain('1280 ms')
    expect(wrapper.text()).toContain('等待限流恢复')
    expect(wrapper.text()).toContain('http://localhost:8317/v1')
  })
})
