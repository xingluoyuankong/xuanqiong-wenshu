import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AgentPublicWorkSummary from './AgentPublicWorkSummary.vue'

const fullSummary = {
  action_id: 'tool:1:started',
  phase: 'tool_execution',
  current_action: '正在执行第 1 个项目能力：project.context。',
  completed_action: '已完成项目上下文定位。',
  input_scope: [
    { kind: 'project' as const, project_id: 'project-a' },
    { kind: 'chapter_version' as const, chapter_number: 3, version_id: 12 },
  ],
  selected_capability: 'project.context',
  decision_summary: '先读取项目元数据，再决定下一步。',
  next_action: '整理项目结构。',
  expected_output: '结构化项目上下文。',
  step_order: 0,
  revision: 0,
}

describe('AgentPublicWorkSummary', () => {
  it('显示 durable checkpoint 的当前动作、范围和零值步骤元数据', () => {
    const wrapper = mount(AgentPublicWorkSummary, { props: { summary: fullSummary } })

    expect(wrapper.get('[data-testid="agent-public-work-summary"]').text()).toContain(
      '正在执行第 1 个项目能力：project.context。',
    )
    expect(wrapper.text()).toContain('已完成项目上下文定位。')
    expect(wrapper.text()).toContain('project.context')
    expect(wrapper.text()).toContain('第 3 章 · 版本 12')
    expect(wrapper.text()).toContain('步骤 0')
    expect(wrapper.text()).toContain('修订 0')
  })


  it('默认折叠公开轨迹，并在展开后显示轨迹与 replay_required 缺口', async () => {
    const wrapper = mount(AgentPublicWorkSummary, {
      props: {
        summary: fullSummary,
        workTraceDeltas: [
          { sequence: 3, traceId: 'trace-3', phase: 'act', kind: 'tool', message: '读取项目结构', progress: 25 },
        ],
        latestWorkTrace: {
          sequence: 3, traceId: 'trace-3', phase: 'act', kind: 'tool', message: '读取项目结构', progress: 25,
        },
        replayRequired: true,
        hasSequenceGap: true,
        pendingSequences: [2],
      },
    })

    expect(wrapper.get('[data-testid="agent-replay-required"]').text()).toContain('2')
    const details = wrapper.get('.trace-details')
    expect((details.element as HTMLDetailsElement).open).toBe(false)
    await wrapper.get('[data-testid="agent-work-trace-toggle"]').trigger('click')
    expect((details.element as HTMLDetailsElement).open).toBe(true)
    expect(wrapper.get('[data-testid="agent-work-trace-list"]').text()).toContain('读取项目结构')
  })

  it('不渲染缺失的可选字段标签', () => {
    const wrapper = mount(AgentPublicWorkSummary, {
      props: {
        summary: {
          action_id: 'planner:started',
          phase: 'planning',
          current_action: '正在建立创作计划。',
          input_scope: [],
          revision: 0,
        },
      },
    })

    expect(wrapper.text()).toContain('正在建立创作计划。')
    expect(wrapper.text()).not.toContain('已完成')
    expect(wrapper.text()).not.toContain('能力')
    expect(wrapper.text()).not.toContain('判断')
    expect(wrapper.text()).not.toContain('下一步')
    expect(wrapper.text()).not.toContain('预期输出')
  })
})
