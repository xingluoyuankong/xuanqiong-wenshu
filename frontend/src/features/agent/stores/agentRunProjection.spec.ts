import { describe, expect, it } from 'vitest'
import { useAgentRunProjection } from './agentRunProjection'

const run = (id: string, createdAt: string) => ({
  id,
  session_id: 'session-1',
  user_id: 1,
  project_id: 'project-1',
  status: 'running',
  current_step: 0,
  progress: 0,
  created_at: createdAt,
})

describe('useAgentRunProjection', () => {
  it('honors an explicitly selected historical Run instead of falling back to the last Run', () => {
    const projection = useAgentRunProjection()
    projection.replaceRuns([run('run-old', '2026-08-27T10:00:00Z'), run('run-new', '2026-08-27T10:01:00Z')], 'run-old')

    expect(projection.selectedRunId.value).toBe('run-old')
    expect(projection.activeRun.value?.id).toBe('run-old')

    projection.setRunSteps('run-old', [{ id: 'step-old', run_id: 'run-old', user_id: 1, step_order: 1, tool_name: 'outline.inspect', idempotency_key: 'old', status: 'completed', attempt_count: 1, output_json: {} }])
    projection.setRunSteps('run-new', [{ id: 'step-new', run_id: 'run-new', user_id: 1, step_order: 1, tool_name: 'quality.inspect', idempotency_key: 'new', status: 'completed', attempt_count: 1, output_json: {} }])

    expect(projection.activeRunSteps.value.map((item) => item.id)).toEqual(['step-old'])
    projection.selectRun('run-new')
    expect(projection.activeRunSteps.value.map((item) => item.id)).toEqual(['step-new'])
  })

  it('keeps stale Run events isolated from the selected Run projection', () => {
    const projection = useAgentRunProjection()
    projection.replaceRuns([run('run-a', '2026-08-27T10:00:00Z'), run('run-b', '2026-08-27T10:01:00Z')], 'run-b')

    projection.applyEvent({
      id: 'a-1',
      run_id: 'run-a',
      sequence: 1,
      event_type: 'assistant_delta',
      summary: 'A',
      data: { content: '旧运行内容' },
    } as any)
    projection.applyEvent({
      id: 'b-1',
      run_id: 'run-b',
      sequence: 1,
      event_type: 'assistant_delta',
      summary: 'B',
      data: { content: '当前运行内容' },
    } as any)

    expect(projection.activeEventProjection.value.assistantText).toBe('当前运行内容')
    projection.selectRun('run-a')
    expect(projection.activeEventProjection.value.assistantText).toBe('旧运行内容')
  })


  it('exposes the active public work trace and replay state without mixing assistant deltas', () => {
    const projection = useAgentRunProjection()
    projection.replaceRuns([run('run-trace', '2026-08-27T10:00:00Z')], 'run-trace')
    projection.applyEvent({
      id: 'assistant-1', run_id: 'run-trace', sequence: 1, event_type: 'assistant_delta', summary: '回复',
      data: { content: '回复内容' },
    } as any)
    projection.applyEvent({
      id: 'trace-3', run_id: 'run-trace', sequence: 3, event_type: 'work_trace_delta', summary: '检查项目',
      data: { trace_id: 'trace-3', phase: 'observe', kind: 'status', message: '检查项目' },
    } as any)

    expect(projection.activeEventProjection.value.assistantText).toBe('回复内容')
    expect(projection.activeWorkTraceDeltas.value).toHaveLength(1)
    expect(projection.latestWorkTrace.value?.message).toBe('检查项目')
    expect(projection.replayRequired.value).toBe(true)
  })

  it('isolates immutable Context/Plan/Summary facts by Run', () => {
    const projection = useAgentRunProjection()
    projection.replaceRuns([run('run-fact-a', '2026-08-27T10:00:00Z'), run('run-fact-b', '2026-08-27T10:01:00Z')], 'run-fact-a')
    projection.setRunContextSnapshot('run-fact-a', { snapshot_id: 'ctx-a', refs: [], context_kind: 'run_initial_context', digest: 'a'.repeat(64) } as any)
    projection.setRunPlanRevision('run-fact-a', { revision_id: 'plan-a', revision_number: 1, status: 'created', digest: 'b'.repeat(64) } as any)
    projection.setRunConversationSummaries('run-fact-a', [{ summary_id: 'summary-a', start_message_sequence: 1, end_message_sequence: 2 } as any])
    projection.setRunContextSnapshot('run-fact-b', { snapshot_id: 'ctx-b', refs: [], context_kind: 'run_initial_context', digest: 'c'.repeat(64) } as any)

    expect(projection.activeContextSnapshot.value?.snapshot_id).toBe('ctx-a')
    expect(projection.activePlanRevision.value?.revision_id).toBe('plan-a')
    expect(projection.activeConversationSummaries.value.map((item) => item.summary_id)).toEqual(['summary-a'])
    projection.selectRun('run-fact-b')
    expect(projection.activeContextSnapshot.value?.snapshot_id).toBe('ctx-b')
    expect(projection.activePlanRevision.value).toBeNull()
    expect(projection.activeConversationSummaries.value).toEqual([])
  })

  it('preserves selection while refreshes merge Run snapshots', () => {
    const projection = useAgentRunProjection()
    projection.replaceRuns([run('run-a', '2026-08-27T10:00:00Z'), run('run-b', '2026-08-27T10:01:00Z')], 'run-a')
    projection.replaceRuns([{ ...run('run-a', '2026-08-27T10:00:00Z'), progress: 72 }, run('run-b', '2026-08-27T10:01:00Z')])

    expect(projection.selectedRunId.value).toBe('run-a')
    expect(projection.activeRun.value?.progress).toBe(72)
  })
})