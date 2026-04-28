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
    expect(metaBlocks[0].text()).toContain('查看附加信息')
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
})
