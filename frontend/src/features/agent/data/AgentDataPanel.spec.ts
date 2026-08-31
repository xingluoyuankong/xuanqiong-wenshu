import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import AgentDataPanel from './AgentDataPanel.vue'

const job = {
  id: 'job-1',
  run_id: 'run-1',
  user_id: 1,
  kind: 'visible_response',
  status: 'running',
  idempotency_key: 'job-key',
  payload_json: {},
  result_json: {},
  attempt_count: 1,
  max_attempts: 3,
  available_at: '2026-08-30T00:00:00Z',
  created_at: '2026-08-30T00:00:00Z',
}

const timeline = {
  id: 'event-1',
  run_id: 'run-1',
  sequence: 1,
  event_type: 'tool_call_completed',
  summary: '项目上下文已读取',
  created_at: '2026-08-30T00:00:00Z',
  session_id: 'session-1',
  run_status: 'completed',
  tool_name: 'project.context',
}

const audit = {
  event_id: 'audit-1',
  session_id: 'session-1',
  run_id: 'run-1',
  user_id: 1,
  run_status: 'completed',
  event_type: 'artifact_created',
  sequence: 2,
  summary: '候选已生成',
  artifact_id: 'artifact-1',
  data_json: {},
  created_at: '2026-08-30T00:00:00Z',
}

const mountPanel = (overrides: Record<string, unknown> = {}) =>
  mount(AgentDataPanel, {
    props: {
      isAdmin: true,
      providerHealth: {
        registry_status: 'healthy',
        provider_count: 1,
        providers: [
          {
            provider_id: 'project-read',
            status: 'loaded',
            source: 'builtin',
            tools: ['project.context'],
            provider_version: '1.0.0',
            capability_tags: ['project'],
          },
        ],
      },
      providerHealthLoading: false,
      providerHealthError: '',
      timeline: [timeline],
      timelineLoading: false,
      timelineEventType: '',
      timelineRunStatus: '',
      jobs: [job],
      jobsLoading: false,
      deadLetters: [{ ...job, id: 'dead-1', status: 'dead_letter', error_type: 'ProviderTimeout' }],
      deadLettersLoading: false,
      auditLedger: [audit],
      auditLoading: false,
      canListDeadLetters: true,
      ...overrides,
    },
  })

describe('AgentDataPanel', () => {
  it('管理员可查看 Provider、项目时间线、Job、死信和审计账本', () => {
    const wrapper = mountPanel()
    expect(wrapper.get('[data-testid="agent-data-panel"]').text()).toContain('Provider 健康状态')
    expect(wrapper.get('[data-testid="agent-provider-health-panel"]').text()).toContain('project-read')
    expect(wrapper.get('[data-testid="agent-timeline-panel"]').text()).toContain('项目上下文已读取')
    expect(wrapper.get('[data-testid="agent-job-panel"]').text()).toContain('visible_response · running')
    expect(wrapper.get('[data-testid="agent-dead-letter-panel"]').text()).toContain('ProviderTimeout')
    expect(wrapper.get('[data-testid="agent-audit-panel"]').text()).toContain('候选已生成')
  })

  it('筛选值和 Job 操作通过 typed emits 上送页面', async () => {
    const wrapper = mountPanel()
    const selects = wrapper.findAll('select')
    await selects[0].setValue('tool_call_failed')
    await selects[1].setValue('failed')
    const buttons = wrapper.findAll('button')
    await buttons.find((node) => node.text() === '请求取消')?.trigger('click')
    await buttons.find((node) => node.text() === '重新排队')?.trigger('click')

    expect(wrapper.emitted('update:timeline-event-type')?.[0]).toEqual(['tool_call_failed'])
    expect(wrapper.emitted('update:timeline-run-status')?.[0]).toEqual(['failed'])
    expect(wrapper.emitted('cancel-job')?.[0]).toEqual([job])
    expect(wrapper.emitted('replay-dead-letter')?.[0]).toEqual([{ ...job, id: 'dead-1', status: 'dead_letter', error_type: 'ProviderTimeout' }])
  })

  it('非管理员不渲染 Provider 和死信面板，但保留项目数据面板', () => {
    const wrapper = mountPanel({ isAdmin: false })
    expect(wrapper.findAll('[data-testid="agent-provider-health-panel"]').length).toBe(0)
    expect(wrapper.findAll('[data-testid="agent-dead-letter-panel"]').length).toBe(0)
    expect(wrapper.findAll('[data-testid="agent-timeline-panel"]').length).toBe(1)
    expect(wrapper.findAll('[data-testid="agent-audit-panel"]').length).toBe(1)
  })
})
