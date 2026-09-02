import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AgentRunInspector from './AgentRunInspector.vue'
import source from './AgentRunInspector.vue?raw'

describe('AgentRunInspector', () => {
  it('locates a step and execution result from selected references', () => {
    const wrapper = mount(AgentRunInspector, {
      props: {
        run: { id: 'run-1', correlation_id: 'c1', session_id: 's1', user_id: 1, status: 'completed', current_phase: 'summary', current_step: 1, progress: 100, created_at: 'now' },
        state: null,
        selectedActionRef: 'step:step-1',
        selectedResultRef: 'execution:exec-1',
        executionFacts: [{ execution_id: 'exec-1', run_id: 'run-1', step_id: 'step-1', action_id: 'step:step-1', result_ref: 'execution:exec-1', tool_name: 'quality.inspect', status: 'completed', attempt: 1, has_output: true }],
        steps: [{
          id: 'step-1', run_id: 'run-1', user_id: 1, step_order: 1, tool_name: 'quality.inspect',
          idempotency_key: 'idem-1', status: 'completed', attempt_count: 1,
          output_json: { execution_id: 'exec-1', summary: '安全摘要' },
        }],
        toolResults: [{ tool_name: 'quality.inspect', result_ref: 'execution:exec-1', result: { summary: '安全摘要' } }],
        connectionState: 'terminal',
      },
      global: {
        stubs: { XqPanel: { template: '<section><slot /></section>' }, XqButton: { template: '<button><slot /></button>' } },
      },
    })

    expect(wrapper.get('[data-testid="agent-selected-location"]').text()).toContain('execution:exec-1')
    expect(wrapper.get('[data-testid="agent-step-step-1"]').classes()).toContain('step-list__item--selected')
    expect(wrapper.get('[data-testid="agent-tool-result-0"]').classes()).toContain('tool-result-card--selected')
    expect(wrapper.get('[data-testid="agent-execution-fact"]').text()).toContain('quality.inspect')
    expect(wrapper.get('[data-testid="agent-execution-fact"]').text()).toContain('第 1 次')
  })

  it('shows a readable state for a stale location reference', () => {
    const wrapper = mount(AgentRunInspector, {
      props: {
        run: { id: 'run-stale', correlation_id: 'c1', session_id: 's1', user_id: 1, status: 'completed', current_phase: 'summary', current_step: 0, progress: 100, created_at: 'now' },
        state: null, steps: [], toolResults: [], selectedResultRef: 'execution:gone', connectionState: 'terminal',
      },
      global: { stubs: { XqPanel: { template: '<section><slot /></section>' }, XqButton: { template: '<button><slot /></button>' } } },
    })
    expect(wrapper.get('[data-testid="agent-selected-location"]').text()).toContain('引用暂不可用')
    expect(wrapper.get('[data-testid="agent-selected-location"]').text()).toContain('execution:gone')
  })

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
    expect(source).toContain('.run-summary dd { min-width: 0;')
    expect(source).toContain('.provider-model-ref, .provider-attempt-summary { display: block;')
  })
})

