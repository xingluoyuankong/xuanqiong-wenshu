import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import AgentArtifactWorkbench from './AgentArtifactWorkbench.vue'

const artifact = {
  id: 'artifact-1',
  run_id: 'run-1',
  correlation_id: 'correlation-1',
  user_id: 1,
  project_id: 'project-1',
  kind: 'chapter_candidate',
  uri: 'agent-artifact://candidate-1',
  sha256: 'a'.repeat(64),
  metadata_json: {
    status: 'candidate',
    quality_status: 'passed',
    quality_gate: { blockers: [] },
  },
  created_at: '2026-08-28T00:00:00Z',
}

const mountWorkbench = (overrides: Record<string, unknown> = {}) =>
  mount(AgentArtifactWorkbench, {
    props: {
      artifacts: [artifact],
      qualityFacts: {},
      qualityFactsLoading: {},
      qualityFactsErrors: {},
      lineageFacts: {},
      lineageFactsLoading: {},
      lineageFactsErrors: {},
      qualityBlockers: [],
      qualityBlockersArtifactId: null,
      qualityBlockersError: '',
      qualityBlockersLoadingByArtifact: {},
      qualityBlockersLoading: false,
      rewriteInstructions: {},
      artifactDiff: null,
      artifactDiffLoading: false,
      hasSelectedProject: true,
      canPreview: true,
      canDiff: true,
      canLocateBlockers: true,
      canLoadRewriteInstructions: true,
      canCompareWithVersion: true,
      canAccept: true,
      ...overrides,
    },
  })

describe('AgentArtifactWorkbench', () => {
  it('优先展示关系化 Gate 和 Finding，而不是 metadata 投影', () => {
    const wrapper = mountWorkbench({
      qualityFacts: {
        [artifact.id]: {
          artifact_id: artifact.id,
          quality_result: null,
          gate: {
            id: 'gate-row',
            gate_id: 'gate-id',
            quality_result_id: 'result-row',
            run_id: artifact.run_id,
            artifact_ref_id: artifact.id,
            correlation_id: artifact.correlation_id,
            transaction_id: null,
            gate_name: 'chapter_candidate_acceptance',
            gate_version: 'p1-b2',
            decision: 'blocked',
            blocker_count: 1,
            rationale: '关系化 Gate 阻断',
            policy_json: {},
            evaluated_at: artifact.created_at,
            created_at: artifact.created_at,
          },
          findings: [
            {
              id: 'finding-row',
              finding_id: 'finding-id',
              code: 'ending_pressure_missing',
              category: 'ending',
              severity: 'blocker',
              status: 'open',
              message: '结尾缺少压力',
              fingerprint: 'f'.repeat(64),
              location_json: {},
              evidence_json: {},
              remediation_json: {},
              created_at: artifact.created_at,
            },
          ],
        },
      },
    })

    expect(wrapper.text()).toContain('质量：blocked · 阻断项 1')
    expect(wrapper.text()).toContain('问题码：ending_pressure_missing')
    expect(wrapper.get('[data-testid="agent-accept-artifact-button"]').attributes('disabled')).toBeDefined()
  })

  it('emits only the selected relational quality finding identity for Chat context selection', async () => {
    const finding = {
      id: 'finding-row', finding_id: 'finding-id', code: 'ending_pressure_missing', category: 'ending',
      severity: 'blocker', status: 'open', message: '结尾缺少压力', fingerprint: 'f'.repeat(64),
      location_json: {}, evidence_json: { excerpt: 'DO_NOT_EXPOSE' }, remediation_json: {}, created_at: artifact.created_at,
    }
    const wrapper = mountWorkbench({
      qualityFacts: { [artifact.id]: { artifact_id: artifact.id, quality_result: null, gate: null, findings: [finding] } },
    })

    await wrapper.get('[data-testid="agent-quality-finding-finding-id"]').trigger('click')
    expect(wrapper.emitted('toggle-quality-finding')?.[0]).toEqual([finding])
    expect(wrapper.text()).not.toContain('DO_NOT_EXPOSE')
  })

  it('展示谱系摘要，并把操作意图上送页面级 orchestrator', async () => {
    const wrapper = mountWorkbench({
      lineageFacts: {
        [artifact.id]: {
          artifact_id: artifact.id,
          upstream_edges: [{ id: 'upstream' }],
          downstream_edges: [{ id: 'downstream-a' }, { id: 'downstream-b' }],
        },
      },
    })

    expect(wrapper.get('[data-testid="agent-artifact-lineage-summary"]').text()).toContain('谱系边：3（上游 1 / 下游 2）')
    const buttons = wrapper.findAll('button')
    await buttons.find((node) => node.text() === '查看候选正文')?.trigger('click')
    await buttons.find((node) => node.text() === '在写作台打开对应章节')?.trigger('click')
    expect(wrapper.emitted('preview')?.[0]).toEqual([artifact])
    expect(wrapper.emitted('open-writing-desk')?.[0]).toEqual([{ artifact, focus: 'version' }])
  })

  it('区分谱系事实读取中与读取失败状态', () => {
    const loading = mountWorkbench({ lineageFactsLoading: { [artifact.id]: true } })
    expect(loading.get('[data-testid="agent-artifact-lineage-loading"]').text()).toContain('正在读取谱系事实')

    const failed = mountWorkbench({ lineageFactsErrors: { [artifact.id]: 'lineage failed' } })
    expect(failed.get('[data-testid="agent-artifact-lineage-error"]').text()).toContain('lineage failed')
  })
  it('显示当前 Artifact 的阻断错误，并禁用其重复读取按钮', () => {
    const failed = mountWorkbench({
      qualityBlockersArtifactId: artifact.id,
      qualityBlockersError: '当前 Artifact 读取失败',
    })
    expect(failed.get('[data-testid="agent-quality-blockers"]').text()).toContain('当前 Artifact 读取失败')

    const loading = mountWorkbench({ qualityBlockersLoadingByArtifact: { [artifact.id]: true } })
    const button = loading.findAll('button').find((node) => node.text() === '定位质量阻断')
    expect(button?.attributes('disabled')).toBeDefined()
  })
  it('旧 Artifact 没有关系化事实时保留 metadata fallback', () => {
    const legacy = {
      ...artifact,
      id: 'legacy-artifact',
      metadata_json: {
        status: 'candidate',
        quality_status: 'blocked',
        quality_gate: {
          blockers: [{ code: 'legacy_blocker' }],
          quality_issue_codes: ['legacy_blocker'],
        },
      },
    }
    const wrapper = mountWorkbench({ artifacts: [legacy] })
    expect(wrapper.text()).toContain('质量：blocked · 阻断项 1')
    expect(wrapper.text()).toContain('问题码：legacy_blocker')
    expect(wrapper.find('[data-testid="agent-artifact-lineage-summary"]').exists()).toBe(false)
  })
})
