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

describe('durable current progress semantics', () => {
  const apply = (events: ReturnType<typeof event>[]) => events.reduce(
    (projection, item) => reduceAgentRunEvent(projection, item).projection,
    createAgentRunEventProjection(),
  )
  const waiting = event({ sequence: 15, data: {
    phase: 'awaiting_approval', action_id: 'approval:pending', progress: 60,
    progress_message: '等待审批，尚未执行',
  } })
  const started = event({ sequence: 20, event_type: 'write_execution_started',
    summary: '开始生成 chapter.generate 候选', data: { tool_name: 'chapter.generate' } })
  const summary = event({ sequence: 21, event_type: 'public_work_summary',
    summary: '候选摘要', data: { phase: 'artifact', action_id: 'artifact:a',
      current_action: '已创建候选 Artifact，等待作者查看。' } })
  const artifact = event({ sequence: 23, event_type: 'artifact_created',
    summary: '写入候选 artifact 已生成，等待用户接受', data: { artifact_id: 'a' } })
  const read = event({ sequence: 24, event_type: 'tool_call_completed',
    summary: '续跑读取项目统计已完成', data: { phase: 'tool_execution', action_id: 'tool:statistics.project' } })

  it('awaiting approval → write start → public summary → artifact → read completion replaces stale status and preserves history', () => {
    let projection = apply([waiting])
    expect(projection.latestProgress).toBe(60)
    for (const [item, message, phase] of [
      [started, started.summary, 'write_execution'],
      [summary, summary.data.current_action, 'artifact'],
      [artifact, artifact.summary, 'candidate_ready'],
      [read, read.summary, 'tool_execution'],
    ] as const) {
      projection = reduceAgentRunEvent(projection, item).projection
      expect(projection.latestProgressMessage).toBe(message)
      expect(projection.latestProgressPhase).toBe(phase)
      expect(projection.latestProgress).toBeUndefined()
      expect(projection.latestProgressActionId).not.toBe('approval:pending')
    }
    expect(projection.events.map((item: { sequence: number }) => item.sequence)).toEqual([15, 20, 21, 23, 24])
    expect(projection.events[0]).toMatchObject({ detail: '正在处理', phase: 'awaiting_approval', progress: 60 })
  })

  it('uses semantic sequence, not arrival order or the unrelated assistant high-water mark', () => {
    const unrelated = event({ sequence: 30, event_type: 'assistant_delta', data: { content: '正文' } })
    const expected = apply([waiting, started, summary, artifact, read, unrelated])
    for (const events of [
      [unrelated, read, artifact, summary, started, waiting],
      [waiting, unrelated, artifact, started, read, summary],
      [artifact, unrelated, waiting, read, summary, started],
    ]) {
      const actual = apply(events)
      expect(actual.latestProgressMessage).toBe(read.summary)
      expect(actual.latestProgressPhase).toBe(expected.latestProgressPhase)
      expect(actual.latestProgress).toBe(expected.latestProgress)
      expect(actual.events).toEqual(expected.events)
      expect(actual.lastSequence).toBe(30)
    }
  })

  it('retains valid progress across non-semantic events, including unrelated phase/action metadata', () => {
    const projection = apply([waiting,
      event({ sequence: 16, event_type: 'assistant_delta', data: { content: '正文', phase: 'assistant_response', action_id: 'response:stream' } }),
      event({ sequence: 17, event_type: 'assistant_reasoning_chunk', data: { content: '推理' } }),
      event({ sequence: 18, event_type: 'unknown', summary: '未知事件' }),
    ])
    expect(projection).toMatchObject({ latestProgressMessage: '等待审批，尚未执行',
      latestProgressPhase: 'awaiting_approval', latestProgressActionId: 'approval:pending', latestProgress: 60 })
  })

  it('accepts newer valid progress after artifact and rejects delayed older lifecycle/progress events', () => {
    const latest = event({ sequence: 26, data: { phase: 'quality', progress: 92, progress_message: '检查候选质量' } })
    const projection = apply([artifact, latest, waiting, started, summary, read])
    expect(projection).toMatchObject({ latestProgressMessage: '检查候选质量', latestProgress: 92, latestProgressPhase: 'quality' })
    expect(projection.events).toHaveLength(6)
  })

  it('isolates Run identity even when a foreign Run has a higher or identical sequence', () => {
    const original = apply([artifact])
    for (const sequence of [1, 23, 1000]) {
      const foreign = reduceAgentRunEvent(original, event({ run_id: 'run-other', sequence, data: { progress: 1, progress_message: '另一个运行' } }))
      expect(foreign.accepted).toBe(false)
      expect(foreign.runPatch).toEqual({})
      expect(foreign.projection).toBe(original)
    }
    const other = apply([event({ run_id: 'run-other', sequence: 1, data: { progress: 5, progress_message: '新运行' } })])
    expect(other.latestProgressMessage).toBe('新运行')
    expect(other.latestProgress).toBe(5)
  })

  it('orders work trace and progress in the same semantic stream without losing trace history', () => {
    const trace = event({ sequence: 22, event_type: 'work_trace_delta', data: {
      message: '候选写入中', phase: 'write_execution', progress: 80, action_id: 'write:1',
    } })
    const current = apply([waiting, trace])
    expect(current.latestProgressMessage).toBe('候选写入中')
    expect(current.latestProgress).toBe(80)
    const completed = reduceAgentRunEvent(current, artifact).projection
    expect(completed.latestProgressMessage).toBe(artifact.summary)
    expect(completed.latestWorkTrace?.message).toBe('候选写入中')
    expect(completed.workTraceDeltas).toHaveLength(1)
  })

  it('terminal completion replaces old progress and failure/cancellation do not retain a stale percentage', () => {
    expect(apply([waiting, event({ sequence: 25, event_type: 'run_completed', summary: '运行已完成', data: {} })]))
      .toMatchObject({ latestProgressMessage: '运行已完成', latestProgressPhase: 'completed', latestProgress: 100 })
    for (const event_type of ['run_failed', 'run_cancelled']) {
      const projection = apply([waiting, event({ sequence: 25, event_type, summary: '运行已结束', data: {} })])
      expect(projection.latestProgressMessage).toBe('运行已结束')
      expect(projection.latestProgress).toBeUndefined()
    }
  })
})
