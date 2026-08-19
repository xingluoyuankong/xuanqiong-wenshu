import { shallowMount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ChapterGenerating from './ChapterGenerating.vue'

const buildRuntime = () => ({
  progress_stage: 'generating',
  progress_message: '正在生成正文',
  estimated_remaining_seconds: 120,
  events: Array.from({ length: 10 }, (_, index) => ({
    at: `2026-04-21T08:00:${String(index).padStart(2, '0')}Z`,
    stage: index >= 8 ? 'generate_variants' : 'prepare_context',
    level: index === 8 ? 'warning' : 'info',
    message: `事件 ${index + 1}`,
    metadata: index === 8 ? { stable_retry_used: true, generation_mode: 'stable' } : undefined,
  })),
})

describe('ChapterGenerating', () => {
  it('长篇分段正文按段累积显示，而不是只显示最后一段', () => {
    const wrapper = shallowMount(ChapterGenerating, {
      props: {
        chapterNumber: 7,
        generationRuntime: {
          progress_stage: 'segment_generation',
          progress_message: '长篇分段生成 2/3',
          events: [
            {
              at: '2026-04-21T08:00:00Z',
              stage: 'segment_generation',
              kind: 'content',
              content_delta: '第一段正文内容。',
              content_preview: '第一段正文内容。',
              content_is_preview: false,
              segment_index: 0,
            },
            {
              at: '2026-04-21T08:01:00Z',
              stage: 'segment_generation',
              kind: 'status',
              message: '长篇分段生成 2/3',
            },
            {
              at: '2026-04-21T08:02:00Z',
              stage: 'segment_generation',
              kind: 'content',
              content_delta: '第二段正文内容。',
              content_preview: '第二段正文内容。',
              content_is_preview: false,
              segment_index: 1,
            },
          ],
        },
        progressStage: 'segment_generation',
        progressMessage: '长篇分段生成 2/3',
      },
    })

    const preview = wrapper.find('.cg-live-preview').text()
    expect(preview).toContain('第一段正文内容。')
    expect(preview).toContain('第二段正文内容。')
    expect(preview.indexOf('第一段正文内容。')).toBeLessThan(preview.indexOf('第二段正文内容。'))
    expect(wrapper.text()).toContain('正文实时流')
  })

  it('同一段重试重复推送时按段号去重，不重复拼接正文', () => {
    const wrapper = shallowMount(ChapterGenerating, {
      props: {
        chapterNumber: 8,
        generationRuntime: {
          progress_stage: 'segment_generation',
          events: [
            {
              at: '2026-04-21T08:00:00Z',
              kind: 'content',
              content_delta: '首版第一段。',
              content_is_preview: false,
              segment_index: 0,
            },
            {
              at: '2026-04-21T08:00:30Z',
              kind: 'content',
              content_delta: '重试后的第一段。',
              content_is_preview: false,
              segment_index: 0,
            },
          ],
        },
        progressStage: 'segment_generation',
      },
    })

    const preview = wrapper.find('.cg-live-preview').text()
    expect(preview).toBe('重试后的第一段。')
    expect(preview).not.toContain('首版第一段。')
  })

  it('预览分片不参与累积，仅在没有正式分段正文时兜底显示', () => {
    const wrapper = shallowMount(ChapterGenerating, {
      props: {
        chapterNumber: 9,
        generationRuntime: {
          progress_stage: 'generate_variants',
          events: [
            {
              at: '2026-04-21T08:00:00Z',
              kind: 'content',
              content_delta: '整章草稿预览片段。',
              content_preview: '整章草稿预览片段。',
              content_is_preview: true,
            },
          ],
        },
        progressStage: 'generate_variants',
      },
    })

    expect(wrapper.find('.cg-live-preview').text()).toContain('整章草稿预览片段。')
    expect(wrapper.text()).toContain('最新草稿片段')
    expect(wrapper.text()).not.toContain('正文实时流')
  })

  it('默认只展示最近 8 条日志，并可展开全部', async () => {
    const wrapper = shallowMount(ChapterGenerating, {
      props: {
        chapterNumber: 1,
        generationRuntime: buildRuntime(),
        progressStage: 'generating',
        progressMessage: '正在生成正文',
        allowedActions: ['refresh_status', 'cancel_generation'],
      },
    })

    expect(wrapper.findAll('.cg-log-item')).toHaveLength(8)
    expect(wrapper.text()).toContain('展开全部（+2）')

    await wrapper.find('.cg-log-toggle').trigger('click')

    expect(wrapper.findAll('.cg-log-item')).toHaveLength(10)
    expect(wrapper.text()).toContain('收起日志')
  })

  it('展示单次诊断后的分阶段优化与日志摘要', () => {
    const wrapper = shallowMount(ChapterGenerating, {
      props: {
        chapterNumber: 11,
        generationRuntime: {
          progress_stage: 'optimize_character',
          progress_message: '正在按人物问题批量优化正文',
          diagnosis_stage_label: '单次诊断',
          optimization_stage_label: '人物优化',
          optimization_dimensions: ['人物一致性', '关系推进'],
          self_critique_final_score: 81,
          optimization_logs: [
            { stage: 'structural', issue_count: 3, changed: true, dimensions: ['结构节奏'] },
            { stage: 'character', issue_count: 2, changed: false, dimensions: ['人物一致性', '关系推进'] },
          ],
        },
        progressStage: 'optimize_character',
        progressMessage: '正在按人物问题批量优化正文',
        allowedActions: ['refresh_status', 'cancel_generation'],
      },
    })

    expect(wrapper.text()).toContain('人物优化')
    expect(wrapper.text()).toContain('诊断阶段：单次诊断')
    expect(wrapper.text()).toContain('优化阶段：人物优化')
    expect(wrapper.text()).toContain('当前维度：人物一致性、关系推进')
    expect(wrapper.text()).toContain('批判摘要：评分 81 · 分批优化 2 段')
    expect(wrapper.text()).toContain('结构优化：问题 3 项 · 已输出修改 · 维度：结构节奏')
    expect(wrapper.text()).toContain('人物优化：问题 2 项 · 未改动正文 · 维度：人物一致性、关系推进')
  })

  it('展示前一章依据与关联上下文阶段信息', () => {
    const wrapper = shallowMount(ChapterGenerating, {
      props: {
        chapterNumber: 2,
        generationRuntime: {
          progress_stage: 'diagnose_context_bundle',
          progress_message: '正在整理关联上下文，汇总章节目标、长期记忆与剧情线索',
          diagnosis_stage_label: '关联上下文',
          diagnosis_dimensions: ['previous_summary', 'project_memory'],
        },
        progressStage: 'diagnose_context_bundle',
        progressMessage: '正在整理关联上下文，汇总章节目标、长期记忆与剧情线索',
        allowedActions: ['refresh_status', 'cancel_generation'],
      },
    })

    expect(wrapper.text()).toContain('关联上下文')
    expect(wrapper.text()).toContain('诊断阶段：关联上下文')
    expect(wrapper.text()).toContain('诊断维度：previous_summary、project_memory')
  })

  it('展示复用既有诊断提示', () => {
    const wrapper = shallowMount(ChapterGenerating, {
      props: {
        chapterNumber: 3,
        generationRuntime: {
          progress_stage: 'optimize_content',
          progress_message: '总览变更较小，已复用既有诊断结果并跳过重复诊断/优化',
          optimization_stage_label: '复用既有诊断',
          optimization_dimensions: ['previous_summary'],
        },
        progressStage: 'optimize_content',
        progressMessage: '总览变更较小，已复用既有诊断结果并跳过重复诊断/优化',
        allowedActions: ['refresh_status', 'cancel_generation'],
      },
    })

    expect(wrapper.text()).toContain('复用既有诊断')
    expect(wrapper.text()).toContain('当前维度：previous_summary')
    expect(wrapper.text()).toContain('总览变更较小，已复用既有诊断结果并跳过重复诊断/优化')
  })

  it('包含 metadata 的日志可展开查看附加信息', async () => {
    const wrapper = shallowMount(ChapterGenerating, {
      props: {
        chapterNumber: 1,
        generationRuntime: buildRuntime(),
        progressStage: 'generating',
        progressMessage: '正在生成正文',
        allowedActions: ['refresh_status', 'cancel_generation'],
      },
    })

    await wrapper.find('.cg-log-toggle').trigger('click')

    const metaBlocks = wrapper.findAll('.cg-log-item__meta')
    expect(metaBlocks.length).toBeGreaterThan(0)
    expect(metaBlocks[0].text()).toContain('开发者详情')
    expect(metaBlocks[0].text()).toContain('是否切换稳定模式：是')
    expect(metaBlocks[0].text()).toContain('生成模式：stable')
  })

  it('在日志消息中展示阶段耗时', () => {
    const wrapper = shallowMount(ChapterGenerating, {
      props: {
        chapterNumber: 1,
        generationRuntime: {
          progress_stage: 'generate_variants',
          progress_message: '正在生成正文',
          events: [
            {
              at: '2026-04-21T08:00:00Z',
              stage: 'generate_variants',
              level: 'info',
              message: '候选正文生成阶段完成',
              metadata: {
                stage_duration_ms: 2345,
                generation_phase_total_ms: 2000,
                guardrail_check_total_ms: 200,
                guardrail_rewrite_total_ms: 145,
              },
            },
          ],
        },
        progressStage: 'generate_variants',
        progressMessage: '正在生成正文',
        allowedActions: ['refresh_status', 'cancel_generation'],
      },
    })

    expect(wrapper.text()).toContain('候选正文生成阶段完成')
    expect(wrapper.text()).toContain('2.35秒')
    expect(wrapper.text()).toContain('正文生成耗时：2000')
    expect(wrapper.text()).toContain('护栏检查耗时：200')
    expect(wrapper.text()).toContain('自动修复耗时：145')
  })

  it('账本闭环分组展示伏笔和记忆层事件', async () => {
    const wrapper = shallowMount(ChapterGenerating, {
      props: {
        chapterNumber: 5,
        generationRuntime: {
          progress_stage: 'ledger_foreshadowing',
          progress_message: '伏笔回收和新伏笔抽取完成',
          events: [
            {
              at: '2026-04-21T08:00:00Z',
              stage: 'ledger_memory',
              kind: 'ledger',
              level: 'info',
              title: '记忆层更新完成',
              summary: '已从定稿正文抽取角色状态、时间线和因果信息。',
              metrics: {
                character_states_updated: 3,
                timeline_events_added: 2,
                dynamic_characters_created: 1,
                dynamic_character_names: ['林渡'],
              },
            },
            {
              at: '2026-04-21T08:00:01Z',
              stage: 'ledger_foreshadowing',
              kind: 'ledger',
              level: 'info',
              title: '伏笔闭环完成',
              summary: '回收 1 条，强化 2 条。',
              metrics: { resolved: 1, reinforced: 2 },
              artifact_refs: { resolution_ids: [7] },
            },
            {
              at: '2026-04-21T08:00:02Z',
              stage: 'generate_variants',
              kind: 'content',
              level: 'info',
              summary: '正文候选完成',
            },
          ],
        },
        progressStage: 'ledger_foreshadowing',
        progressMessage: '伏笔回收和新伏笔抽取完成',
        allowedActions: ['refresh_status'],
      },
    })

    const tabs = wrapper.findAll('.cg-log-tab')
    const ledgerTab = tabs.find((tab) => tab.text().includes('账本闭环'))
    expect(ledgerTab).toBeTruthy()
    await ledgerTab!.trigger('click')

    expect(wrapper.text()).toContain('记忆层更新完成')
    expect(wrapper.text()).toContain('伏笔闭环完成')
    expect(wrapper.text()).toContain('更新角色状态数：3')
    expect(wrapper.text()).toContain('动态角色入池数：1')
    expect(wrapper.text()).toContain('动态入池角色：林渡')
    expect(wrapper.text()).toContain('回收伏笔数：1')
    expect(wrapper.text()).not.toContain('正文候选完成')
  })

  it('shows local patch guidance when a stagewide candidate requires manual confirmation', () => {
    const wrapper = shallowMount(ChapterGenerating, {
      props: {
        chapterNumber: 9,
        generationRuntime: {
          progress_stage: 'optimize_structural',
          progress_message: 'Optimization guard is protecting continuity',
          events: [
            {
              at: '2026-04-21T08:00:00Z',
              stage: 'optimize_structural',
              kind: 'review',
              level: 'warning',
              title: 'Stagewide candidate deferred',
              summary: 'Whole-chapter candidate was not applied automatically',
              metadata: {
                manual_stagewide_confirmation_required: true,
                stagewide_deferred_count: 1,
                manual_patch_suggestions: [
                  {
                    stage: 'structural',
                    strategy: 'structure_guardrail',
                    location: 'mid-chapter turn',
                    problem: 'Need a stronger confrontation before reveal',
                    suggestion: 'Add a negotiation beat that changes the leverage.',
                    execution_requirement: 'Patch only the negotiation window and keep both anchors',
                  },
                ],
              },
            },
          ],
        },
        progressStage: 'optimize_structural',
        progressMessage: 'Optimization guard is protecting continuity',
        allowedActions: ['refresh_status'],
      },
    })

    expect(wrapper.find('.cg-log-item__notice').exists()).toBe(true)
    expect(wrapper.find('.cg-log-item__patches').text()).toContain('Need a stronger confrontation before reveal')
    expect(wrapper.find('.cg-log-item__patches').text()).toContain('Add a negotiation beat that changes the leverage.')
    expect(wrapper.find('.cg-log-item__patches').text()).toContain('Patch only the negotiation window and keep both anchors')
  })

  it('shows consistency local-repair diagnostics without hiding patch suggestions', () => {
    const wrapper = shallowMount(ChapterGenerating, {
      props: {
        chapterNumber: 10,
        generationRuntime: {
          progress_stage: 'consistency',
          progress_message: '一致性局部修复已完成，仍有问题需按局部补丁处理',
          events: [
            {
              at: '2026-04-21T08:00:00Z',
              stage: 'consistency',
              kind: 'continuity',
              level: 'warning',
              title: '一致性局部修复结果',
              summary: '局部修复尝试 1 次，未解决问题 1 项；整章候选需要人工确认。',
              metrics: {
                repair_attempt_count: 1,
                unresolved_consistency_issues: 1,
                auto_fix_accepted: false,
              },
              metadata: {
                manual_stagewide_confirmation_required: true,
                repair_attempts: [
                  {
                    attempt: 1,
                    mode: 'local_patch',
                    full_chapter_fallback_deferred: true,
                  },
                ],
                manual_patch_suggestions: [
                  {
                    dimension: 'continuity',
                    location: '第2段',
                    problem: '来源仍像两条并行事件链。',
                    suggestion: '统一来源，只保留一个正式版本。',
                  },
                ],
              },
            },
          ],
        },
        progressStage: 'consistency',
        progressMessage: '一致性局部修复已完成，仍有问题需按局部补丁处理',
        allowedActions: ['refresh_status'],
      },
    })

    expect(wrapper.text()).toContain('一致性局部修复结果')
    expect(wrapper.text()).toContain('局部修复尝试数：1')
    expect(wrapper.text()).toContain('未解决一致性问题数：1')
    expect(wrapper.text()).toContain('自动局部修复已采纳：否')
    expect(wrapper.find('.cg-log-item__notice').text()).toContain('整章候选没有自动套用')
    expect(wrapper.find('.cg-log-item__patches').text()).toContain('来源仍像两条并行事件链')
  })
})
