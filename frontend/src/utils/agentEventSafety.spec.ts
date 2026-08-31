import { describe, expect, it } from 'vitest'
import { toSafeAgentEvent } from './agentEventSafety'

describe('toSafeAgentEvent', () => {
  it('retains only the public assistant delta contract', () => {
    const event = toSafeAgentEvent({
      id: 'event-1',
      run_id: 'run-1',
      sequence: 2,
      event_type: 'assistant_delta',
      summary: 'safe summary',
      data: {
        content: '可见内容',
        phase: 'assistant_response',
        progress: 130,
        reasoning: 'hidden',
        system_prompt: 'hidden',
        provider_secret: 'hidden',
        arbitrary: 'drop',
      },
    } as any)
    expect(event.data).toEqual({ content: '可见内容', phase: 'assistant_response', progress: 100 })
    expect(JSON.stringify(event)).not.toContain('hidden')
    expect(JSON.stringify(event)).not.toContain('arbitrary')
  })

  it('normalizes unknown event type and summary so unreviewed provider text never reaches the browser process stream', () => {
    const event = toSafeAgentEvent({
      id: 'event-2',
      run_id: 'run-2',
      sequence: -1,
      event_type: 'unknown_provider_event',
      summary: 'reasoning=HIDDEN_UNKNOWN_PROMPT token=HIDDEN_UNKNOWN_TOKEN',
      data_json: { content: 'must not render', progress: -4, thought: 'must not render' },
    } as any)
    expect(event.sequence).toBe(0)
    expect(event.event_type).toBe('unknown')
    expect(event.summary).toBe('收到未识别运行事件')
    expect(event.data).toEqual({})
    expect(JSON.stringify(event)).not.toContain('HIDDEN_UNKNOWN')
    expect(JSON.stringify(event)).not.toContain('unknown_provider_event')
  })

  it('replaces a known event summary containing sensitive internal markers while retaining safe contract data', () => {
    const event = toSafeAgentEvent({
      id: 'event-sensitive-summary',
      run_id: 'run-sensitive-summary',
      sequence: 4,
      event_type: 'progress_update',
      summary: 'system_prompt=HIDDEN_SYSTEM_PROMPT',
      data: { progress: 40, phase: 'tool_execution', progress_message: '正在执行受控工具。' },
    } as any)
    expect(event.summary).toBe('收到运行事件')
    expect(event.data).toEqual({ progress: 40, phase: 'tool_execution', progress_message: '正在执行受控工具。' })
    expect(JSON.stringify(event)).not.toContain('HIDDEN_SYSTEM_PROMPT')
  })

  it('retains bounded progress_update fields while discarding private payload data', () => {
    const event = toSafeAgentEvent({
      id: 'event-progress',
      run_id: 'run-progress',
      sequence: 7,
      event_type: 'progress_update',
      summary: '正在执行章节检查。',
      data: {
        progress: 42.5,
        phase: 'tool_execution',
        step: 2,
        tool_name: 'chapter.inspect',
        progress_message: '正在执行章节检查。',
        reasoning: 'hidden',
        system_prompt: 'hidden',
        content: 'must not render',
      },
    } as any)
    expect(event.data).toEqual({
      progress: 42.5,
      phase: 'tool_execution',
      step: 2,
      tool_name: 'chapter.inspect',
      progress_message: '正在执行章节检查。',
    })
    expect(JSON.stringify(event)).not.toContain('hidden')
    expect(JSON.stringify(event)).not.toContain('must not render')
  })

  it('retains the bounded public plan_revised event while discarding replan internals', () => {
    const event = toSafeAgentEvent({
      id: 'event-revised',
      run_id: 'run-revised',
      sequence: 9,
      event_type: 'plan_revised',
      summary: '研究读取失败，改用统计工具。',
      data: {
        revision: 1,
        step_count: 1,
        phase: 'replanning',
        provider_called: true,
        fallback_reason: 'RuntimeError',
        completed_tool_results: [{ secret: 'drop' }],
        reasoning: 'hidden',
      },
    } as any)
    expect(event.data).toEqual({
      revision: 1,
      step_count: 1,
      phase: 'replanning',
      fallback_reason: 'RuntimeError',
      provider_called: true,
    })
    expect(JSON.stringify(event)).not.toContain('hidden')
    expect(JSON.stringify(event)).not.toContain('drop')
  })


  it('按事件阶段投影 Provider provenance，并丢弃跨阶段和隐藏字段', () => {
    const planner = toSafeAgentEvent({
      id: 'event-planner-provenance',
      run_id: 'run-provenance',
      sequence: 10,
      event_type: 'plan_created',
      summary: '已生成计划。',
      data: {
        planner_provider_called: true,
        planner_provider_fallback_reason: 'PlannerFallback',
        response_provider_called: true,
        candidate_writer_provider_called: true,
        reasoning: 'HIDDEN_PLANNER_REASONING',
        provider_secret: 'HIDDEN_PLANNER_SECRET',
      },
    } as any)
    expect(planner.data).toEqual({
      planner_provider_called: true,
      planner_provider_fallback_reason: 'PlannerFallback',
    })

    const response = toSafeAgentEvent({
      id: 'event-response-provenance',
      run_id: 'run-provenance',
      sequence: 11,
      event_type: 'run_completed',
      summary: '可见回复已完成。',
      data: {
        response_provider_called: true,
        response_provider_fallback_reason: 'ResponseTimeout',
        candidate_writer_provider_called: true,
        reasoning: 'HIDDEN_RESPONSE_REASONING',
      },
    } as any)
    expect(response.data).toEqual({
      response_provider_called: true,
      response_provider_fallback_reason: 'ResponseTimeout',
    })

    const writer = toSafeAgentEvent({
      id: 'event-writer-provenance',
      run_id: 'run-provenance',
      sequence: 12,
      event_type: 'artifact_created',
      summary: '候选正文已生成。',
      data: {
        candidate_writer_provider_called: true,
        candidate_writer_provider_fallback_reason: 'WriterRateLimit',
        candidate_writer_model_ref: 'fixture-writer-v1',
        response_provider_called: true,
        thought: 'HIDDEN_WRITER_THOUGHT',
        system_prompt: 'HIDDEN_WRITER_PROMPT',
      },
    } as any)
    expect(writer.data).toEqual({
      candidate_writer_provider_called: true,
      candidate_writer_provider_fallback_reason: 'WriterRateLimit',
      candidate_writer_model_ref: 'fixture-writer-v1',
    })
    expect(JSON.stringify([planner, response, writer])).not.toContain('HIDDEN_')
  })


  it('retains only bounded public work trace fields and rejects private trace messages', () => {
    const event = toSafeAgentEvent({
      id: 'trace-1',
      run_id: 'run-trace',
      sequence: 5,
      event_type: 'work_trace_delta',
      summary: '公开轨迹',
      data: {
        trace_id: 'trace-1',
        phase: 'act',
        action_id: 'tool:inspect',
        kind: 'tool',
        message: '调用项目能力读取结构。',
        capability_id: 'project.context',
        result_ref: 'artifact-1',
        progress: 37,
        content: 'must not enter trace',
        system_prompt: 'HIDDEN_PROMPT',
      },
    } as any)
    expect(event.event_type).toBe('work_trace_delta')
    expect(event.data).toEqual({
      trace_id: 'trace-1',
      phase: 'act',
      action_id: 'tool:inspect',
      kind: 'tool',
      message: '调用项目能力读取结构。',
      capability_id: 'project.context',
      result_ref: 'artifact-1',
      progress: 37,
    })

    const privateMessage = toSafeAgentEvent({
      id: 'trace-2', run_id: 'run-trace', sequence: 6, event_type: 'work_trace_delta', summary: '安全摘要',
      data: { message: 'chain_of_thought=HIDDEN', phase: 'decide' },
    } as any)
    expect(privateMessage.data).toEqual({ phase: 'decide' })
    expect(JSON.stringify(privateMessage)).not.toContain('HIDDEN')
  })

  it('保留 public_work_summary 的受控字段并丢弃 reasoning、正文和密钥', () => {
    const event = toSafeAgentEvent({
      id: 'event-public-summary',
      run_id: 'run-summary',
      sequence: 12,
      event_type: 'public_work_summary',
      summary: '正在读取项目上下文。',
      data_json: {
        action_id: 'context:started',
        phase: 'context',
        current_action: '正在读取项目上下文。',
        completed_action: '已确认项目范围。',
        selected_capability: 'project.context',
        decision_summary: '优先读取轻量项目数据。',
        next_action: '建立执行计划。',
        expected_output: '结构化项目上下文。',
        input_scope_count: 2,
        revision: 1,
        reasoning: 'HIDDEN_REASONING',
        system_prompt: 'HIDDEN_PROMPT',
        provider_secret: 'HIDDEN_SECRET',
        content: 'HIDDEN_PROSE',
        input_scope: [{ project_id: 'must-not-render' }],
      },
    } as any)

    expect(event.data).toEqual({
      action_id: 'context:started',
      phase: 'context',
      current_action: '正在读取项目上下文。',
      completed_action: '已确认项目范围。',
      selected_capability: 'project.context',
      decision_summary: '优先读取轻量项目数据。',
      next_action: '建立执行计划。',
      expected_output: '结构化项目上下文。',
      input_scope_count: 2,
      revision: 1,
    })
    expect(JSON.stringify(event)).not.toContain('HIDDEN_')
    expect(JSON.stringify(event)).not.toContain('must-not-render')
  })

})

it('规范化公开事件文本中的控制字符', () => {
  const event = toSafeAgentEvent({
    id: 'event-control',
    run_id: 'run-control',
    sequence: 13,
    event_type: 'public_work_summary',
    summary: '安全\u0000摘要\u001f',
    data: {
      current_action: '执行\u0000章节检查\u001f',
      next_action: '整理\u0000结果',
    },
  } as any)

  expect(event.summary).toBe('安全 摘要')
  expect(event.data).toEqual({
    current_action: '执行 章节检查',
    next_action: '整理 结果',
  })
})
