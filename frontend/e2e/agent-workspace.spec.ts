import { expect, test } from '@playwright/test'
import { writeFile } from 'node:fs/promises'

const project = {
  id: 'e2e-project-1',
  title: 'E2E 星河旧梦',
  genre: '玄幻',
  last_edited: '2026-08-24T00:00:00Z',
  completed_chapters: 2,
  total_chapters: 8,
}

const session = {
  id: 'e2e-session-1',
  user_id: 1,
  project_id: project.id,
  title: 'E2E Agent 会话',
  status: 'active',
  created_at: '2026-08-24T00:00:00Z',
  updated_at: '2026-08-24T00:00:00Z',
}

const tools = {
  count: 1,
  tools: [
    {
      name: 'project.context',
      description: '读取当前小说项目的结构化上下文。',
      risk_level: 'read',
      requires_confirmation: false,
      supports_stream: false,
    },
  ],
}

const contentTree = {
  chapters: [
    {
      chapter_number: 1,
      title: 'E2E 第一章',
      summary: 'E2E 轻量章节摘要',
      generation_status: 'successful',
      word_count: 1280,
    },
  ],
  chapterOutline: [
    {
      chapter_number: 1,
      title: 'E2E 第一章',
      summary: 'E2E 大纲摘要',
      metadata: { volume_number: 1, volume_title: '星河卷' },
    },
  ],
  chapter: {
    chapter_number: 1,
    title: 'E2E 第一章',
    summary: 'E2E 轻量章节摘要',
    content: 'E2E 章节正文预览',
    selected_version_id: 11,
    versions: [{ id: 11, content: 'E2E 章节正文预览' }],
    evaluation: null,
    generation_status: 'successful',
  },
}

async function expandWorkspaceSection(
  page: import('@playwright/test').Page,
  testId: string,
) {
  const section = page.getByTestId(testId)
  await expect(section).toBeVisible()
  if (!(await section.evaluate((element) => (element as HTMLDetailsElement).open))) {
    await section.locator('summary').scrollIntoViewIfNeeded()
    await section.locator('summary').click()
  }
  await expect.poll(() => section.evaluate((element) => (element as HTMLDetailsElement).open)).toBe(true)
}

async function mockAgentApi(page: import('@playwright/test').Page) {
  const state: {
    run: Record<string, unknown> | null
    messages: Array<Record<string, unknown>>
    fullProjectRequests: number
  } = { run: null, messages: [], fullProjectRequests: 0 }
  await page.route('**/api/novels/current-user', async (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 1,
        username: 'e2e-admin',
        is_admin: true,
        is_active: true,
        must_change_password: false,
      }),
    }),
  )
  await page.route('**/api/task-runtime/tasks?limit=100', async (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) }),
  )
  await page.route('**/api/novels', async (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([project]),
    }),
  )
  await page.route('**/api/agent/tools', async (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(tools) }),
  )
  await page.route('**/api/agent/tools/health', async (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        registry_status: 'healthy',
        provider_count: 1,
        providers: [
          {
            provider_id: 'project-read',
            status: 'loaded',
            source: 'builtin',
            tools: ['project.context'],
            provider_version: '1.0.0',
          },
        ],
      }),
    }),
  )
  await page.route(`**/api/novels/${project.id}/sections/chapters`, async (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ section: 'chapters', data: { chapters: contentTree.chapters } }),
    }),
  )
  await page.route(`**/api/novels/${project.id}/sections/chapter_outline`, async (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        section: 'chapter_outline',
        data: { chapter_outline: contentTree.chapterOutline },
      }),
    }),
  )
  await page.route(`**/api/novels/${project.id}/chapters/1`, async (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(contentTree.chapter),
    }),
  )
  await page.route(`**/api/novels/${project.id}`, async (route) => {
    state.fullProjectRequests += 1
    await route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'content tree must not request the full project payload' }),
    })
  })
  await page.route('**/api/agent/sessions?project_id=*', async (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) }),
  )
  await page.route('**/api/agent/sessions', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify(session),
      })
      return
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
  })
  await page.route(`**/api/agent/sessions/${session.id}`, async (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ...session,
        messages: state.messages,
        runs: state.run ? [state.run] : [],
      }),
    }),
  )
  await page.route('**/api/agent/runs/*/approvals', async (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) }),
  )
  await page.route('**/api/agent/runs/*/plan', async (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        goal: '当前运行计划',
        project_id: project.id,
        mode: 'explore',
        provider_called: false,
        steps: [
          {
            order: 1,
            tool_name: 'project.context',
            description: '读取当前项目上下文',
            intent: '读取当前项目上下文',
            expected_result: '项目摘要',
            depends_on: [],
            planner_arguments: {},
            risk_level: 'read',
            requires_confirmation: false,
          },
        ],
        events: [],
      }),
    }),
  )
  await page.route('**/api/agent/runs/*/provider-provenance', async (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        planner_provider_called: false,
        planner_provider_fallback_reason: null,
        response_provider_called: null,
        response_provider_fallback_reason: null,
        candidate_writer_provider_called: null,
        candidate_writer_provider_fallback_reason: null,
        candidate_writer_model_ref: null,
      }),
    }),
  )
  await page.route('**/api/agent/runs/*/context-snapshot', async (route) => {
    const run = state.run || {}
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(
        typeof run.id === 'string'
          ? {
              id: `context-${run.id}`,
              snapshot_id: `snapshot-${run.id}`,
              run_id: run.id,
              session_id: session.id,
              user_id: 1,
              project_id: project.id,
              correlation_id: 'e2e-correlation',
              transaction_id: null,
              schema_version: 1,
              context_kind: 'run_initial',
              context_json: { project_id: project.id },
              digest: 'a'.repeat(64),
              created_at: session.created_at,
              refs: [],
            }
          : null,
      ),
    })
  })
  await page.route('**/api/agent/runs/*/plan-revision', async (route) => {
    const run = state.run || {}
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(
        typeof run.id === 'string'
          ? {
              id: `plan-${run.id}`,
              revision_id: `plan-revision-${run.id}`,
              run_id: run.id,
              session_id: session.id,
              context_snapshot_id: `context-${run.id}`,
              parent_revision_id: null,
              revision_number: 1,
              user_id: 1,
              project_id: project.id,
              correlation_id: 'e2e-correlation',
              transaction_id: null,
              planner_id: 'mock-planner',
              status: 'completed',
              rationale: 'mock plan revision',
              plan_json: { steps: [] },
              digest: 'b'.repeat(64),
              created_at: session.created_at,
            }
          : null,
      ),
    })
  })
  await page.route('**/api/agent/runs/*/conversation-summaries**', async (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) }),
  )
  await page.route('**/api/agent/runs/*/state', async (route) => {
    const run = state.run || {}
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        correlation_id: 'e2e-correlation',
        run_id: typeof run.id === 'string' ? run.id : null,
        user_id: 1,
        progress: typeof run.progress === 'number' ? run.progress : 0,
        phase: typeof run.current_phase === 'string' ? run.current_phase : 'planning',
        current_step: typeof run.current_step === 'number' ? run.current_step : 0,
        terminal_status: typeof run.status === 'string' ? run.status : null,
        recoverable: false,
        cancellation_requested: false,
        last_event_sequence: 0,
        steps: [],
        approvals: [],
        artifacts: [],
        accepted_version_ids: [],
        jobs: [],
        task_runtime_refs: [],
      }),
    })
  })
  await page.route('**/api/agent/runs/*/activity**', async (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) }),
  )
  await page.route('**/api/agent/runs/*/steps', async (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(
        state.run
          ? [
              {
                id: 'step-1',
                run_id: 'run-1',
                user_id: 1,
                step_order: 1,
                tool_name: 'project.context',
                idempotency_key: 'run-1:step:1:project.context',
                status: 'completed',
                attempt_count: 1,
                lease_owner: null,
                lease_expires_at: null,
                output_json: { project },
                error_type: null,
                started_at: session.created_at,
                finished_at: session.created_at,
              },
            ]
          : [],
      ),
    }),
  )
  await page.route('**/api/agent/artifacts/*/quality', async (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        artifact_id: route.request().url().split('/').at(-2),
        quality_result: null,
        findings: [],
        gate: null,
      }),
    }),
  )
  await page.route('**/api/agent/artifacts/*/lineage', async (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        artifact_id: route.request().url().split('/').at(-2),
        upstream_edges: [],
        downstream_edges: [],
      }),
    }),
  )
  await page.route('**/api/agent/runs/*/artifacts', async (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) }),
  )
  await page.route('**/api/agent/jobs*', async (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) }),
  )
  await page.route('**/api/agent/timeline*', async (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) }),
  )
  await page.route('**/api/agent/audit*', async (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) }),
  )
  await page.route('**/api/agent/dead-letters*', async (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) }),
  )
  return state
}

test.describe('Agent 创作工作台浏览器冒烟', () => {
  test('加载项目、工具注册表和持久化会话入口', async ({ page }) => {
    const state = await mockAgentApi(page)
    await page.goto('/agent')
    await expect(page.getByTestId('agent-workspace')).toBeVisible()
    await expect(page.getByTestId('agent-project-select')).toContainText('E2E 星河旧梦')
    await expect(page.getByTestId('agent-tool-list')).toContainText('project.context')
    await expandWorkspaceSection(page, 'agent-session-section')
    await expect(page.getByTestId('agent-session-panel')).toBeVisible()
    await expect(page.getByTestId('agent-project-content-tree')).toBeVisible()
    await expect(page.getByTestId('agent-content-chapter-1')).toContainText('E2E 第一章')
    expect(state.fullProjectRequests).toBe(0)

    await page.getByTestId('agent-content-chapter-1').click()
    await expect(page.getByTestId('agent-content-preview-text')).toContainText('E2E 章节正文预览')
    expect(state.fullProjectRequests).toBe(0)
  })

  test('深链历史 Run 并切换运行时，浏览器始终投影所选 Run 的状态和事件', async ({ page }) => {
    await mockAgentApi(page)
    const oldRun = {
      id: 'run-old',
      session_id: session.id,
      user_id: 1,
      project_id: project.id,
      status: 'completed',
      current_phase: 'completed',
      current_step: 1,
      progress: 21,
      created_at: '2026-08-24T00:00:00Z',
      started_at: '2026-08-24T00:00:00Z',
      finished_at: '2026-08-24T00:00:01Z',
    }
    const newestRun = {
      id: 'run-new',
      session_id: session.id,
      user_id: 1,
      project_id: project.id,
      status: 'completed',
      current_phase: 'completed',
      current_step: 2,
      progress: 88,
      created_at: '2026-08-24T00:01:00Z',
      started_at: '2026-08-24T00:01:00Z',
      finished_at: '2026-08-24T00:01:01Z',
    }

    await page.unroute('**/api/agent/sessions?project_id=*')
    await page.route('**/api/agent/sessions?project_id=*', async (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([session]) }),
    )
    await page.unroute(`**/api/agent/sessions/${session.id}`)
    await page.route(`**/api/agent/sessions/${session.id}`, async (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ...session, messages: [], runs: [oldRun, newestRun] }),
      }),
    )
    await page.unroute('**/api/agent/runs/*/approvals')
    await page.route('**/api/agent/runs/*/approvals', async (route) => {
      const runId = route.request().url().includes('run-old') ? oldRun.id : newestRun.id
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([{ id: `approval-${runId}`, run_id: runId, user_id: 1, tool_name: 'chapter.rewrite', status: 'pending' }]),
      })
    })
    await page.unroute('**/api/agent/runs/*/artifacts')
    await page.route('**/api/agent/runs/*/artifacts', async (route) => {
      const runId = route.request().url().includes('run-old') ? oldRun.id : newestRun.id
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([{ id: `artifact-${runId}`, run_id: runId, user_id: 1, project_id: project.id, kind: 'chapter_candidate', uri: `artifact://${runId}`, metadata_json: {}, created_at: session.created_at }]),
      })
    })
    await page.unroute('**/api/agent/runs/*/steps')
    await page.route('**/api/agent/runs/*/steps', async (route) => {
      const isOld = route.request().url().includes('run-old')
      const runId = isOld ? oldRun.id : newestRun.id
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([{ id: `step-${runId}`, run_id: runId, user_id: 1, step_order: 1, tool_name: isOld ? 'chapter.version.list' : 'quality.inspect', idempotency_key: `step-${runId}`, status: 'completed', attempt_count: 1, output_json: {} }]),
      })
    })
    await page.unroute('**/api/agent/runs/*/state')
    await page.route('**/api/agent/runs/*/state', async (route) => {
      const isOld = route.request().url().includes('run-old')
      const run = isOld ? oldRun : newestRun
      const latestPublicSummary = {
        action_id: `summary-${run.id}`,
        phase: 'tool_execution',
        current_action: isOld ? '历史 Run 正在整理章节版本。' : '最新 Run 正在汇总质量。',
        input_scope: [{ kind: 'chapter', chapter_number: isOld ? 3 : 8 }],
        selected_capability: isOld ? 'chapter.version.list' : 'quality.inspect',
        revision: 0,
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ correlation_id: `correlation-${run.id}`, run_id: run.id, user_id: 1, progress: run.progress, phase: run.current_phase, current_step: run.current_step, terminal_status: run.status, recoverable: false, cancellation_requested: false, last_event_sequence: 1, latest_public_summary: latestPublicSummary, latest_public_summary_sequence: 1, latest_public_summary_at: session.created_at, steps: [], approvals: [], artifacts: [], accepted_version_ids: [], jobs: [], task_runtime_refs: [] }),
      })
    })
    await page.unroute(`**/api/agent/sessions/${session.id}/runs/*/events**`)
    await page.route(`**/api/agent/sessions/${session.id}/runs/*/events**`, async (route) => {
      const isOld = route.request().url().includes('run-old')
      const run = isOld ? oldRun : newestRun
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([{ id: `event-${run.id}`, run_id: run.id, user_id: 1, sequence: 1, event_type: 'progress_update', summary: isOld ? '历史 Run 已载入' : '最新 Run 已载入', data: { progress: run.progress, progress_message: isOld ? '历史进度' : '最新进度' }, created_at: session.created_at }]),
      })
    })

    await page.goto(`/agent?project_id=${project.id}&session_id=${session.id}&run_id=${oldRun.id}`)
    await expect(page.getByTestId('agent-run-selector')).toHaveValue(oldRun.id)
    await expect(page.getByTestId('agent-selected-run-id')).toContainText('run-old')
    await expect(page.getByTestId('agent-run-progress')).toHaveText('21%')
    await expect(page.getByTestId('agent-step-panel')).toContainText('chapter.version.list')
    await expect(page.getByTestId('agent-public-work-summary')).toContainText('历史 Run 正在整理章节版本。')
    await expect(page.getByTestId('agent-process-stream')).toContainText('历史 Run 已载入')

    await page.getByTestId('agent-run-selector').selectOption(newestRun.id)
    await expect(page.getByTestId('agent-selected-run-id')).toContainText('run-new')
    await expect(page.getByTestId('agent-run-progress')).toHaveText('88%')
    await expect(page.getByTestId('agent-step-panel')).toContainText('quality.inspect')
    await expect(page.getByTestId('agent-public-work-summary')).toContainText('最新 Run 正在汇总质量。')
    await expect(page.getByTestId('agent-public-work-summary')).not.toContainText('历史 Run 正在整理章节版本。')
    await expect(page.getByTestId('agent-process-stream')).toContainText('最新 Run 已载入')
    await expect(page.getByTestId('agent-process-stream')).not.toContainText('历史 Run 已载入')
  })

  test('Artifact 质量发现通过最小 ContextRef 进入 Chat 发送请求', async ({ page }) => {
    const state = await mockAgentApi(page)
    const run = {
      id: 'quality-context-run',
      session_id: session.id,
      user_id: 1,
      project_id: project.id,
      status: 'completed',
      current_phase: 'quality',
      current_step: 1,
      progress: 100,
      created_at: session.created_at,
      started_at: session.created_at,
      finished_at: session.created_at,
    }
    const artifact = {
      id: 'quality-context-artifact',
      run_id: run.id,
      user_id: 1,
      project_id: project.id,
      kind: 'chapter_candidate',
      uri: 'artifact://quality-context',
      metadata_json: { status: 'candidate' },
      created_at: session.created_at,
    }
    state.run = run
    let messagePayload: Record<string, unknown> | undefined

    await page.unroute('**/api/agent/sessions?project_id=*')
    await page.route('**/api/agent/sessions?project_id=*', async (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([session]) }),
    )
    await page.unroute('**/api/agent/runs/*/artifacts')
    await page.route('**/api/agent/runs/*/artifacts', async (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([artifact]) }),
    )
    await page.unroute('**/api/agent/artifacts/*/quality')
    await page.route('**/api/agent/artifacts/*/quality', async (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          artifact_id: artifact.id,
          quality_result: null,
          gate: null,
          findings: [{
            id: 'quality-finding-row',
            finding_id: 'quality-finding-e2e',
            code: 'ending_pressure_missing',
            category: 'ending',
            severity: 'blocker',
            status: 'open',
            message: 'DO_NOT_SEND_MESSAGE',
            fingerprint: 'a'.repeat(64),
            location_json: { hidden: 'DO_NOT_SEND_LOCATION' },
            evidence_json: { hidden: 'DO_NOT_SEND_EVIDENCE' },
            remediation_json: { hidden: 'DO_NOT_SEND_REMEDIATION' },
            created_at: session.created_at,
          }],
        }),
      }),
    )
    await page.route(`**/api/agent/sessions/${session.id}/messages`, async (route) => {
      messagePayload = route.request().postDataJSON() as Record<string, unknown>
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          message: {
            id: 'quality-context-user-message',
            session_id: session.id,
            user_id: 1,
            role: 'user',
            content: '根据质量发现修订候选稿',
            sequence: 1,
            created_at: session.created_at,
          },
          assistant_message: null,
          run: null,
          plan: null,
          tool_results: [],
          approvals: [],
        }),
      })
    })

    await page.goto(`/agent?project_id=${project.id}&session_id=${session.id}&run_id=${run.id}`)
    await expandWorkspaceSection(page, 'agent-run-details-section')
    await expect(page.getByTestId('agent-quality-finding-quality-finding-e2e')).toHaveText('加入上下文')
    await page.getByTestId('agent-quality-finding-quality-finding-e2e').click()
    await expect(page.getByTestId('agent-quality-finding-quality-finding-e2e')).toHaveText('移除上下文')
    await expect(page.getByTestId('agent-context-chip-quality-finding')).toContainText('质量发现：quality-')

    await page.getByTestId('agent-message-input').fill('根据质量发现修订候选稿')
    await page.getByTestId('agent-plan-submit').click()

    expect(messagePayload).toEqual({
      content: '根据质量发现修订候选稿',
      context_refs: [
        { kind: 'project', project_id: project.id },
        { kind: 'quality_finding', project_id: project.id, finding_id: 'quality-finding-e2e' },
      ],
    })
    const serialized = JSON.stringify(messagePayload)
    expect(serialized).not.toContain('DO_NOT_SEND_MESSAGE')
    expect(serialized).not.toContain('DO_NOT_SEND_LOCATION')
    expect(serialized).not.toContain('DO_NOT_SEND_EVIDENCE')
    expect(serialized).not.toContain('DO_NOT_SEND_REMEDIATION')
  })

  test('消息发送后展示真实运行摘要和助手消息', async ({ page }) => {
    const state = await mockAgentApi(page)
    let messagePayload: Record<string, unknown> | undefined
    await page.route(`**/api/agent/sessions/${session.id}/messages`, async (route) => {
      messagePayload = route.request().postDataJSON() as Record<string, unknown>
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          message: {
            id: 'm-user',
            session_id: session.id,
            user_id: 1,
            role: 'user',
            content: '检查当前项目',
            sequence: 1,
            created_at: session.created_at,
          },
          assistant_message: null,
          run: (state.run = {
            id: 'run-1',
            session_id: session.id,
            user_id: 1,
            project_id: project.id,
            status: 'running',
            current_phase: 'assistant_response',
            current_step: 1,
            progress: 80,
            created_at: session.created_at,
            started_at: session.created_at,
            finished_at: null,
          }),
          plan: {
            goal: '检查当前项目',
            project_id: project.id,
            mode: 'explore',
            steps: [
              {
                order: 1,
                tool_name: 'project.context',
                description: '读取项目',
                risk_level: 'read',
                requires_confirmation: false,
              },
            ],
            events: [],
            provider_called: false,
          },
          tool_results: [{ tool_name: 'project.context', result: { project: project } }],
        }),
      })
    })
    await page.route(`**/api/agent/sessions/${session.id}/runs/run-1/events**`, async (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'event-1',
            run_id: 'run-1',
            user_id: 1,
            sequence: 1,
            event_type: 'plan_created',
            summary: '计划已创建',
            data: { phase: 'planning' },
            created_at: session.created_at,
          },
          {
            id: 'event-2',
            run_id: 'run-1',
            user_id: 1,
            sequence: 2,
            event_type: 'step_reused',
            summary: '已复用项目上下文结果',
            data: { tool_name: 'project.context', step: 1, phase: 'checkpoint_replay' },
            created_at: session.created_at,
          },
        ]),
      }),
    )
    await page.route(`**/api/agent/sessions/${session.id}/runs/run-1/stream**`, async (route) => {
      state.run = {
        ...state.run,
        status: 'completed',
        current_phase: 'summary',
        progress: 100,
        finished_at: session.created_at,
      }
      state.messages = [
        {
          id: 'm-user',
          session_id: session.id,
          user_id: 1,
          role: 'user',
          content: '检查当前项目',
          sequence: 1,
          created_at: session.created_at,
        },
        {
          id: 'm-assistant',
          session_id: session.id,
          user_id: 1,
          role: 'assistant',
          content: '已完成项目上下文检查。',
          sequence: 2,
          created_at: session.created_at,
        },
      ]
      const event = (
        sequence: number,
        eventType: string,
        summary: string,
        data: Record<string, unknown>,
      ) =>
        `id: ${sequence}\nevent: ${eventType}\ndata: ${JSON.stringify({ id: `event-${sequence}`, run_id: 'run-1', user_id: 1, sequence, event_type: eventType, summary, data, created_at: session.created_at })}\n\n`
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body:
          event(3, 'progress_update', '正在生成可见回复', {
            phase: 'assistant_response',
            progress: 90,
            step: 1,
            tool_name: 'project.context',
            progress_message: '工具已完成，正在生成可见回复。',
          }) +
          event(4, 'assistant_delta', 'Agent 输出第一段', { content: '已完成' }) +
          event(5, 'assistant_delta', 'Agent 输出第二段', { content: '项目上下文检查。' }) +
          event(6, 'run_completed', 'Agent 运行已完成', { phase: 'summary', progress: 100 }),
      })
    })
    await page.goto('/agent')
    await page.getByTestId('agent-content-chapter-1').click()
    await expect(page.getByTestId('agent-context-chip-chapter-version')).toContainText(
      '第 1 章 · 版本 11',
    )
    await page.getByTestId('agent-message-input').fill('检查当前项目')
    await page.getByTestId('agent-plan-submit').click()
    await expect(page.getByTestId('agent-message-list')).toContainText('已完成项目上下文检查。')
    await expect(page.getByTestId('agent-run-status')).toContainText('completed')
    await expect(page.getByTestId('agent-process-stream')).toContainText('Agent 已返回计划')
    await expect(page.getByTestId('agent-process-stream')).toContainText('已复用已完成步骤')
    await expect(page.getByTestId('agent-process-stream')).toContainText('运行进度')
    await expect(page.getByTestId('agent-run-progress-message')).toContainText(
      '工具已完成，正在生成可见回复。',
    )
    await expect(page.getByTestId('agent-process-stream')).toContainText('Agent 输出第一段')
    await expect(page.getByTestId('agent-process-stream')).toContainText('Agent 输出第二段')
    await expect(page.getByTestId('agent-process-stream')).toContainText('Agent 运行已完成')
    await expect(page.getByTestId('agent-step-panel')).toContainText('project.context')
    await expect(page.getByTestId('agent-step-panel')).toContainText('第 1 次')
    await expect(page.getByTestId('agent-step-panel')).toContainText('已完成')
    await expect(page.getByTestId('agent-step-panel')).toContainText('已复用/保存结果')
    expect(messagePayload).toEqual({
      content: '检查当前项目',
      context_refs: [
        { kind: 'project', project_id: project.id },
        {
          kind: 'chapter_version',
          project_id: project.id,
          chapter_number: 1,
          version_id: 11,
          role: 'selected',
        },
      ],
    })
    expect(JSON.stringify(messagePayload)).not.toContain('E2E 章节正文预览')
  })
})

test.describe('Agent 恢复与 DLQ 浏览器交互', () => {
  test('恢复就绪运行显示恢复按钮并接收恢复后的可见事件', async ({ page }) => {
    const state = await mockAgentApi(page)
    let streamCalls = 0
    await page.route(`**/api/agent/sessions/${session.id}/messages`, async (route) =>
      route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          message: {
            id: 'm-recover-user',
            session_id: session.id,
            user_id: 1,
            role: 'user',
            content: '恢复运行',
            sequence: 1,
            created_at: session.created_at,
          },
          assistant_message: null,
          run: (state.run = {
            id: 'run-recover',
            session_id: session.id,
            user_id: 1,
            project_id: project.id,
            status: 'paused',
            current_phase: 'recovery_ready',
            current_step: 1,
            progress: 80,
            created_at: session.created_at,
            started_at: session.created_at,
            finished_at: null,
          }),
          plan: {
            goal: '恢复运行',
            project_id: project.id,
            mode: 'explore',
            steps: [
              {
                order: 1,
                tool_name: 'project.context',
                description: '读取项目',
                risk_level: 'read',
                requires_confirmation: false,
              },
            ],
            events: [],
            provider_called: false,
          },
          tool_results: [{ tool_name: 'project.context', result: { project } }],
        }),
      }),
    )
    await page.route(
      `**/api/agent/sessions/${session.id}/runs/run-recover/events**`,
      async (route) =>
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            {
              id: 'recover-event-1',
              run_id: 'run-recover',
              user_id: 1,
              sequence: 1,
              event_type: 'run_recovery_ready',
              summary: '运行已进入可恢复状态',
              data: { phase: 'recovery_ready' },
              created_at: session.created_at,
            },
          ]),
        }),
    )
    await page.route('**/api/agent/runs/run-recover/recover', async (route) => {
      state.run = { ...state.run, status: 'running', current_phase: 'recovered', progress: 85 }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(state.run),
      })
    })
    await page.route(
      `**/api/agent/sessions/${session.id}/runs/run-recover/stream**`,
      async (route) => {
        streamCalls += 1
        const event = (
          sequence: number,
          eventType: string,
          summary: string,
          data: Record<string, unknown>,
        ) =>
          `id: ${sequence}\nevent: ${eventType}\ndata: ${JSON.stringify({ id: `recover-event-${sequence}`, run_id: 'run-recover', user_id: 1, sequence, event_type: eventType, summary, data, created_at: session.created_at })}\n\n`
        if (streamCalls === 1) {
          // First connection closes before recovery; the UI must keep the
          // recovery-ready state and the SSE client must reconnect later.
          await route.fulfill({ status: 200, contentType: 'text/event-stream', body: '' })
          return
        }
        state.run = {
          ...state.run,
          status: 'completed',
          current_phase: 'summary',
          progress: 100,
          finished_at: session.created_at,
        }
        await route.fulfill({
          status: 200,
          contentType: 'text/event-stream',
          body:
            event(2, 'run_resumed', '运行已恢复', { phase: 'recovered' }) +
            event(3, 'assistant_delta', 'Agent 输出', { content: '恢复完成' }) +
            event(4, 'run_completed', '运行已完成', { phase: 'summary', progress: 100 }),
        })
      },
    )
    await page.goto('/agent')
    await page.getByTestId('agent-message-input').fill('恢复运行')
    await page.getByTestId('agent-plan-submit').click()
    await expect(page.getByTestId('agent-recover-run-button')).toBeVisible()
    await page.getByTestId('agent-recover-run-button').click()
    await expect(page.getByTestId('agent-process-stream')).toContainText('运行已恢复', {
      timeout: 10_000,
    })
    await expect(page.getByTestId('agent-run-status')).toHaveText('completed', { timeout: 10_000 })
    expect(streamCalls).toBeGreaterThan(0)
  })

  test('管理员可查看死信 Job 并重放，普通面板不泄露 Provider 私有字段', async ({ page }) => {
    const state = await mockAgentApi(page)
    let replayed = false
    await page.unroute('**/api/agent/dead-letters*')
    await page.route('**/api/agent/dead-letters/dlq-1/replay**', async (route) => {
      replayed = true
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'dlq-1',
          run_id: 'run-dlq',
          user_id: 1,
          project_id: project.id,
          kind: 'visible_response',
          status: 'queued',
          idempotency_key: 'dlq-key',
          payload_json: {},
          result_json: {},
          error_type: 'ProviderTimeout',
          error_detail: 'replayed_by=1; reason=Agent 工作台管理员重放',
          attempt_count: 1,
          max_attempts: 1,
          available_at: session.created_at,
          lease_owner: null,
          lease_expires_at: null,
          cancel_requested_at: null,
          cancel_reason: null,
          created_at: session.created_at,
          started_at: session.created_at,
          finished_at: null,
        }),
      })
    })
    await page.route('**/api/agent/dead-letters?limit=*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(
          replayed
            ? []
            : [
                {
                  id: 'dlq-1',
                  run_id: 'run-dlq',
                  user_id: 1,
                  project_id: project.id,
                  kind: 'visible_response',
                  status: 'dead_letter',
                  idempotency_key: 'dlq-key',
                  payload_json: {},
                  result_json: {},
                  error_type: 'ProviderTimeout',
                  error_detail: 'temporary provider failure',
                  attempt_count: 1,
                  max_attempts: 1,
                  available_at: session.created_at,
                  lease_owner: null,
                  lease_expires_at: null,
                  cancel_requested_at: null,
                  cancel_reason: null,
                  created_at: session.created_at,
                  started_at: session.created_at,
                  finished_at: session.created_at,
                },
              ],
        ),
      })
    })
    await page.goto('/agent')
    await expandWorkspaceSection(page, 'agent-data-section')
    await expect(page.getByTestId('agent-dead-letter-panel')).toContainText('ProviderTimeout')
    await expect(page.getByTestId('agent-dead-letter-panel')).toContainText(
      'temporary provider failure',
    )
    await page
      .getByTestId('agent-dead-letter-panel')
      .getByRole('button', { name: '重新排队' })
      .click()
    await expect(page.getByTestId('agent-process-stream')).toContainText('死信 Job 已重新排队')
    expect(replayed).toBe(true)
    expect(state).toBeTruthy()
  })

  test('CARD-071 五视口布局测量与日志/聊天滚动隔离', async ({ page }, testInfo) => {
    const state = await mockAgentApi(page)
    state.messages = Array.from({ length: 80 }, (_, index) => ({
      id: `layout-message-${index}`,
      session_id: session.id,
      role: index % 2 ? 'assistant' : 'user',
      content: `布局验收历史消息 ${index}`,
      created_at: session.created_at,
    }))
    await page.unroute('**/api/agent/sessions?project_id=*')
    await page.route('**/api/agent/sessions?project_id=*', async (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([session]) }),
    )
    const viewports = [
      { width: 1920, height: 1080 },
      { width: 1440, height: 900 },
      { width: 1280, height: 800 },
      { width: 960, height: 800 },
      { width: 650, height: 844 },
    ]
    const measurements: Array<Record<string, unknown>> = []

    for (const viewport of viewports) {
      await page.setViewportSize(viewport)
      await page.goto('/agent')
      await expect(page.getByTestId('agent-workspace')).toBeVisible()
      await expect(page.getByTestId('agent-project-select')).toContainText('E2E 星河旧梦')
      await expect(page.getByTestId('agent-message-list')).toBeVisible()

      const measurement = await page.evaluate(() => {
        const query = (selector: string) => document.querySelector(selector)
        const rect = (selector: string) => {
          const element = query(selector)
          if (!element) return null
          const value = element.getBoundingClientRect()
          return {
            x: Math.round(value.x),
            y: Math.round(value.y),
            width: Math.round(value.width),
            height: Math.round(value.height),
          }
        }
        const style = (selector: string) => {
          const element = query(selector)
          if (!element) return null
          const value = getComputedStyle(element)
          return {
            display: value.display,
            overflowY: value.overflowY,
            minWidth: value.minWidth,
            minHeight: value.minHeight,
            maxHeight: value.maxHeight,
            gridTemplateColumns: value.gridTemplateColumns,
          }
        }
        const logViewport = query('[data-testid="agent-runtime-log-viewport"]') as HTMLElement | null
        const chatMessages = query('[data-testid="agent-message-list"]') as HTMLElement | null
        if (logViewport) {
          const logList = logViewport.querySelector('[data-testid="agent-process-stream"]') as HTMLElement | null
          if (logList) {
            logList.innerHTML = Array.from({ length: 80 }, (_, index) => `<p>布局验收日志 ${index}</p>`).join('')
          }
        }
        const chatScrollTopBefore = chatMessages?.scrollTop || 0
        const logScrollHeight = logViewport?.scrollHeight || 0
        const logClientHeight = logViewport?.clientHeight || 0
        if (logViewport) logViewport.scrollTop = Math.max(0, logScrollHeight - logClientHeight)
        const logScrollTopAfter = logViewport?.scrollTop || 0
        const chatScrollTopAfterLog = chatMessages?.scrollTop || 0
        const logScrollTopBeforeChat = logViewport?.scrollTop || 0
        const chatScrollHeight = chatMessages?.scrollHeight || 0
        const chatClientHeight = chatMessages?.clientHeight || 0
        if (chatMessages) chatMessages.scrollTop = Math.max(0, chatScrollHeight - chatClientHeight)
        const chatScrollTopAfter = chatMessages?.scrollTop || 0
        const logScrollTopAfterChat = logViewport?.scrollTop || 0
        return {
          layout: rect('.agent-layout'),
          sidebar: rect('.agent-sidebar'),
          main: rect('.agent-main'),
          activity: rect('.agent-activity'),
          chat: rect('[data-testid="agent-chat-column"]'),
          logViewport: rect('[data-testid="agent-runtime-log-viewport"]'),
          layoutStyle: style('.agent-layout'),
          logStyle: style('[data-testid="agent-runtime-log-viewport"]'),
          logScrollHeight,
          logClientHeight,
          logScrollTopAfter,
          chatScrollTopBefore,
          chatScrollTopAfterLog,
          chatScrollHeight,
          chatClientHeight,
          chatScrollTopAfter,
          logScrollTopBeforeChat,
          logScrollTopAfterChat,
          horizontalOverflow: document.documentElement.scrollWidth > window.innerWidth,
        }
      })

      expect(measurement.layout).not.toBeNull()
      expect(measurement.main).not.toBeNull()
      expect(measurement.logViewport).not.toBeNull()
      expect((measurement.logStyle as { overflowY: string }).overflowY).toBe('auto')
      expect((measurement.logStyle as { minWidth: string }).minWidth).toBe('0px')
      expect(measurement.logScrollHeight).toBeGreaterThan(measurement.logClientHeight)
      expect(measurement.logScrollTopAfter).toBeGreaterThan(0)
      expect(measurement.chatScrollTopAfterLog).toBe(measurement.chatScrollTopBefore)
      expect(measurement.chatScrollHeight).toBeGreaterThan(measurement.chatClientHeight)
      expect(measurement.chatScrollTopAfter).toBeGreaterThan(0)
      expect(measurement.logScrollTopAfterChat).toBe(measurement.logScrollTopBeforeChat)
      expect(measurement.horizontalOverflow).toBe(false)

      const layoutColumns = String((measurement.layoutStyle as { gridTemplateColumns: string }).gridTemplateColumns)
        .trim()
        .split(/\s+/)
      if (viewport.width <= 960) {
        expect(layoutColumns).toHaveLength(1)
        expect((measurement.main as { y: number }).y).toBeLessThan((measurement.sidebar as { y: number }).y)
        expect((measurement.sidebar as { y: number }).y).toBeLessThan((measurement.activity as { y: number }).y)
      } else {
        expect(layoutColumns).toHaveLength(3)
        expect((measurement.sidebar as { width: number }).width).toBeGreaterThanOrEqual(160)
        expect((measurement.activity as { width: number }).width).toBeGreaterThanOrEqual(190)
        expect((measurement.main as { width: number }).width).toBeGreaterThan(700)
        expect((measurement.main as { width: number }).width).toBeGreaterThan((measurement.sidebar as { width: number }).width)
        expect((measurement.main as { width: number }).width).toBeGreaterThan((measurement.activity as { width: number }).width)
      }

      await page.screenshot({
        path: testInfo.outputPath(`card071-layout-${viewport.width}x${viewport.height}.png`),
        fullPage: true,
      })
      measurements.push({ viewport, ...measurement })
    }

    const measurementJson = JSON.stringify(measurements, null, 2)
    await writeFile(testInfo.outputPath('card071-layout-measurements.json'), measurementJson, 'utf8')
    await testInfo.attach('card071-layout-measurements.json', {
      body: measurementJson,
      contentType: 'application/json',
    })
  })

})
