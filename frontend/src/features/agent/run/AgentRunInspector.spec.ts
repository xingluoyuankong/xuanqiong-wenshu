import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AgentRunInspector from './AgentRunInspector.vue'

describe('AgentRunInspector', () => {
  it('renders Planner, visible response, and candidate writer provenance as separate facts', () => {
    const wrapper = mount(AgentRunInspector, {
      props: {
        run: { id: 'run-1', correlation_id: 'correlation-1', session_id: 'session-1', user_id: 1, status: 'completed', current_phase: 'summary', current_step: 1, progress: 100, created_at: '2026-08-31T00:00:00Z' },
        state: null,
        steps: [],
        toolResults: [],
        connectionState: 'terminal',
        provenance: {
          planner_provider_called: true,
          planner_provider_fallback_reason: null,
          response_provider_called: false,
          response_provider_fallback_reason: 'empty_response',
          planner_provider_attempts: { provider_attempts: [{ status: 'succeeded' }, { status: 'succeeded' }], selected_provider_attempt: 2, fallback_used: false },
          response_provider_attempts: { provider_attempts: [{ status: 'failed', error_category: 'TIMEOUT' }], selected_provider_attempt: null, fallback_used: false },
          candidate_writer_provider_called: true,
          candidate_writer_provider_fallback_reason: null,
          candidate_writer_model_ref: 'fixture-model',
          candidate_writer_provider_attempts: { provider_attempts: [{ status: 'succeeded' }], selected_provider_attempt: 1, fallback_used: true },
        },
        hasSequenceGap: true,
        gapRepairState: 'repairing',
      },
      global: {
        stubs: { XqPanel: { template: '<section><slot /></section>' }, XqButton: { template: '<button><slot /></button>' } },
      },
    })

    expect(wrapper.get('[data-testid="agent-planner-provider-provenance"]').text()).toContain('已调用 Provider')
    expect(wrapper.get('[data-testid="agent-response-provider-provenance"]').text()).toContain('已降级：empty_response')
    expect(wrapper.get('[data-testid="agent-candidate-writer-provider-provenance"]').text()).toContain('fixture-model')
    expect(wrapper.get('[data-testid="agent-planner-provider-attempts"]').text()).toContain('2 次调用 · 已选 #2')
    expect(wrapper.get('[data-testid="agent-response-provider-attempts"]').text()).toContain('最后失败：TIMEOUT')
    expect(wrapper.get('[data-testid="agent-candidate-writer-provider-attempts"]').text()).toContain('1 次调用 · 已选 #1 · 含 fallback')
    expect(wrapper.get('[data-testid="agent-sequence-gap-status"]').text()).toContain('正在补齐事件账本')
  })
})
