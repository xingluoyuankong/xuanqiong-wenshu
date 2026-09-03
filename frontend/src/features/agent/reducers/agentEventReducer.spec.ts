import { describe, expect, it } from 'vitest'
import { reduceAgentRunEvent, createAgentRunEventProjection } from './agentEventReducer'

const event = (overrides: Record<string, unknown> = {}) => ({
  id: 'event-1',
  run_id: 'run-1',
  sequence: 1,
  event_type: 'progress_update',
  summary: '正在处理',
  data: {},
  ...overrides,
}) as any

describe('agentEventReducer', () => {
  it('deduplicates by durable run and sequence rather than event type', () => {
    const initial = createAgentRunEventProjection()
    const first = reduceAgentRunEvent(initial, event({ sequence: 4, event_type: 'assistant_delta', data: { content: '甲' } }))
    const duplicate = reduceAgentRunEvent(first.projection, event({ id: 'another-id', sequence: 4, event_type: 'assistant_delta', data: { content: '乙' } }))

    expect(first.accepted).toBe(true)
    expect(first.projection.assistantText).toBe('甲')
    expect(duplicate.accepted).toBe(false)
    expect(duplicate.projection.assistantText).toBe('甲')
    expect(duplicate.projection.events).toHaveLength(1)
  })

  it('orders out-of-order history and repairs an observed sequence gap', () => {
    const afterOne = reduceAgentRunEvent(createAgentRunEventProjection(), event({ sequence: 1 })).projection
    const afterThree = reduceAgentRunEvent(afterOne, event({ id: 'event-3', sequence: 3 })).projection
    const repaired = reduceAgentRunEvent(afterThree, event({ id: 'event-2', sequence: 2 })).projection

    expect(afterThree.hasSequenceGap).toBe(true)
    expect(afterThree.lastContiguousSequence).toBe(1)
    expect(repaired.events.map((item) => item.sequence)).toEqual([1, 2, 3])
    expect(repaired.lastContiguousSequence).toBe(3)
    expect(repaired.hasSequenceGap).toBe(false)
  })

  it('treats a first observed sequence above one as a prefix gap and replays from zero', () => {
    const projection = reduceAgentRunEvent(
      createAgentRunEventProjection(),
      event({ sequence: 3, event_type: 'progress_update' }),
    ).projection

    expect(projection.hasSequenceGap).toBe(true)
    expect(projection.lastContiguousSequence).toBe(0)
  })

  it('keeps progress action identity in the replayable display event', () => {
    const reduction = reduceAgentRunEvent(
      createAgentRunEventProjection(),
      event({
        event_type: 'progress_update',
        data: { phase: 'tool_execution', action_id: 'tool:chapter.inspect', progress: 42, progress_message: '正在检查章节' },
      }),
    )

    expect(reduction.projection.events[0]).toMatchObject({
      phase: 'tool_execution',
      actionId: 'tool:chapter.inspect',
      progress: 42,
    })
  })

  it('projects current progress metadata and ignores late older progress', () => {
    const first = reduceAgentRunEvent(
      createAgentRunEventProjection(),
      event({
        sequence: 4,
        event_type: 'progress_update',
        data: { phase: 'tool_execution', action_id: 'tool:quality.inspect', progress: 42, progress_message: '正在检查第三章质量' },
      }),
    ).projection

    expect(first).toMatchObject({
      latestProgressMessage: '正在检查第三章质量',
      latestProgressActionId: 'tool:quality.inspect',
      latestProgressPhase: 'tool_execution',
      latestProgress: 42,
    })

    const late = reduceAgentRunEvent(
      first,
      event({
        id: 'late-progress',
        sequence: 3,
        event_type: 'progress_update',
        data: { phase: 'planning', action_id: 'planner:old', progress: 5, progress_message: '旧进度' },
      }),
    ).projection

    expect(late).toMatchObject({
      latestProgressMessage: '正在检查第三章质量',
      latestProgressActionId: 'tool:quality.inspect',
      latestProgressPhase: 'tool_execution',
      latestProgress: 42,
    })
  })

  it('projects response stream action and result references without changing visible delta text', () => {
    const projection = reduceAgentRunEvent(
      createAgentRunEventProjection(),
      event({
        sequence: 2,
        event_type: 'assistant_delta',
        data: {
          content: '作者可见片段',
          phase: 'assistant_response',
          action_id: 'response:stream',
          result_ref: 'response:run-1',
          reasoning: 'HIDDEN_REASONING',
        },
      }),
    ).projection

    expect(projection.assistantText).toBe('作者可见片段')
    expect(projection.events[0]).toMatchObject({
      actionId: 'response:stream',
      resultRef: 'response:run-1',
    })
    expect(JSON.stringify(projection)).not.toContain('HIDDEN_REASONING')
  })

  it('projects action and result references for tool completion logs', () => {
    const projection = reduceAgentRunEvent(
      createAgentRunEventProjection(),
      event({
        sequence: 2,
        event_type: 'tool_call_completed',
        data: {
          phase: 'tool_execution',
          action_id: 'step:step-1',
          result_ref: 'execution:execution-1',
        },
      }),
    ).projection

    expect(projection.events[0]).toMatchObject({
      actionId: 'step:step-1',
      resultRef: 'execution:execution-1',
    })
  })

  it('only lets the newest durable event change current Run state', () => {
    const first = reduceAgentRunEvent(
      createAgentRunEventProjection(),
      event({ sequence: 8, data: { progress: 80, phase: 'tool_execution', step: 2 } }),
    )
    const late = reduceAgentRunEvent(
      first.projection,
      event({ id: 'late', sequence: 7, data: { progress: 10, phase: 'planning', step: 1 } }),
    )

    expect(first.runPatch).toEqual({ progress: 80, current_phase: 'tool_execution', current_step: 2 })
    expect(late.isLatest).toBe(false)
    expect(late.runPatch).toEqual({})
  })

  it('projects terminal events onto the current Run status without accepting unsafe data', () => {
    const result = reduceAgentRunEvent(
      createAgentRunEventProjection(),
      event({ sequence: 9, event_type: 'run_completed', data: { reasoning: 'hidden', progress: 22 } }),
    )

    expect(result.runPatch).toEqual({ status: 'completed', progress: 100 })
    expect(JSON.stringify(result.projection)).not.toContain('hidden')
  })


  it('keeps public work traces separate from assistant output and marks replay_required for a gap', () => {
    const first = reduceAgentRunEvent(
      createAgentRunEventProjection(),
      event({
        sequence: 1,
        event_type: 'assistant_delta',
        data: { content: '正文片段' },
      }),
    ).projection
    const traced = reduceAgentRunEvent(
      first,
      event({
        id: 'trace-3',
        sequence: 3,
        event_type: 'work_trace_delta',
        summary: '读取项目结构',
        data: {
          trace_id: 'trace-3',
          phase: 'observe',
          action_id: 'project:inspect',
          kind: 'tool',
          message: '读取项目结构',
          capability_id: 'project.context',
          progress: 25,
        },
      }),
    ).projection

    expect(traced.assistantText).toBe('正文片段')
    expect(traced.workTraceDeltas).toEqual([
      expect.objectContaining({
        sequence: 3,
        traceId: 'trace-3',
        phase: 'observe',
        kind: 'tool',
        message: '读取项目结构',
        capabilityId: 'project.context',
        progress: 25,
      }),
    ])
    expect(traced.latestWorkTrace?.message).toBe('读取项目结构')
    expect(traced.replayRequired).toBe(true)

    const repaired = reduceAgentRunEvent(
      traced,
      event({ id: 'event-2', sequence: 2, event_type: 'run_state', data: { status: 'running' } }),
    ).projection
    expect(repaired.replayRequired).toBe(false)
    expect(repaired.workTraceDeltas).toHaveLength(1)
    expect(repaired.assistantText).toBe('正文片段')
  })

  it('keeps an unknown durable sequence as a generic event without displaying its raw provider summary', () => {
    const result = reduceAgentRunEvent(
      createAgentRunEventProjection(),
      event({
        sequence: 3,
        event_type: 'unknown',
        summary: '收到未识别运行事件',
        data: {},
      }),
    )

    expect(result.accepted).toBe(true)
    expect(result.projection.events).toEqual([
      expect.objectContaining({ eventType: 'unknown', detail: '收到未识别运行事件' }),
    ])
    expect(JSON.stringify(result.projection)).not.toContain('HIDDEN')
  })
  it('将 Provider reasoning 分片独立投影，不污染 Assistant 正文并按 chunk_index 排序', () => {
    const started = reduceAgentRunEvent(createAgentRunEventProjection(), event({ sequence: 2, event_type: 'assistant_reasoning_started' })).projection
    const later = reduceAgentRunEvent(started, event({ id: 'reasoning-2', sequence: 4, event_type: 'assistant_reasoning_chunk', data: { chunk_index: 1, content: '后半段' } })).projection
    const first = reduceAgentRunEvent(later, event({ id: 'reasoning-1', sequence: 3, event_type: 'assistant_reasoning_chunk', data: { chunk_index: 0, content: '前半段\n' } })).projection
    const completed = reduceAgentRunEvent(first, event({ sequence: 5, event_type: 'assistant_reasoning_completed' })).projection

    expect(completed.reasoningText).toBe('前半段\n后半段')
    expect(completed.reasoningChunks.map((item) => item.chunkIndex)).toEqual([0, 1])
    expect(completed.assistantText).toBe('')
    expect(completed.reasoningStatus).toBe('completed')
  })

})