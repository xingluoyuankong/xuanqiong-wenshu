import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import RuntimeLogManagement from './RuntimeLogManagement.vue'

const { listRuntimeLogsMock, replaceMock } = vi.hoisted(() => ({
  listRuntimeLogsMock: vi.fn(),
  replaceMock: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {} }),
  useRouter: () => ({ replace: replaceMock }),
}))

vi.mock('@/api/admin', () => ({
  AdminAPI: {
    listRuntimeLogs: listRuntimeLogsMock,
  },
}))

const naiveStubs = {
  NAlert: { template: '<div><slot /></div>' },
  NButton: { emits: ['click'], template: '<button @click="$emit(\'click\')"><slot /></button>' },
  NCard: { template: '<section><slot name="header" /><slot /></section>' },
  NEmpty: { props: ['description'], template: '<div>{{ description }}</div>' },
  NSpace: { template: '<div><slot /></div>' },
  NSpin: { template: '<div><slot /></div>' },
  NTag: { template: '<span><slot /></span>' },
}

const runtimeProject = () => [{
  project_id: 'project-1',
  project_title: '潮雾测试',
  user_id: 1,
  chapter_count: 1,
  active_chapter: 1,
  updated_at: '2026-05-21T04:00:00Z',
  chapters: [{
    chapter_number: 1,
    chapter_title: '潮歌入局',
    generation_status: 'waiting_for_confirm',
    word_count: 4700,
    run_id: 'run-1',
    progress_stage: 'waiting_for_confirm',
    progress_message: '候选版本已准备完成',
    started_at: '2026-05-21T03:55:00Z',
    updated_at: '2026-05-21T04:00:00Z',
    summary_snapshot: {
      target_word_count: 5000,
      actual_word_count: 4700,
      review_status: 'ready',
    },
    runtime_snapshot: {
      target_word_count: 5000,
      actual_word_count: 4700,
      pipeline_total_duration_ms: 125000,
      provider_preflight: {
        checked: true,
        auto_switched: false,
        reason: 'current_profile_usable',
        active_profile_name: 'CPA Provider',
        recommended_profile_name: 'CPA Provider',
        has_usable_profile: true,
      },
      chapter_draft_contract: {
        tier: '标准高质量章',
      },
      chapter_generation_limits: {
        timeout_seconds: 240,
        max_tokens: 12000,
      },
      longform_context: {
        cast_plan: {
          planned_character_count: 12,
          target_character_count: 16,
          chapter_focus_names: ['沈文朝', '潮祠守灯人'],
        },
        foreshadowing_task: {
          must_resolve: [{ name: '第二遍潮歌', content: '解释潮歌为何只在退潮后出现' }],
          should_reinforce: [{ name: '祠门铜铃' }],
          avoid_forgetting: [{ name: '主角不能知道守灯人的真实身份' }],
          active_clues: [{ name: '盐痕脚印' }],
        },
      },
      token_budget_usage: {
        record_count: 2,
        total_tokens: 16800,
        estimated_cost: 0.1344,
        module: 'content',
        usage_ids: [7, 8],
      },
    },
    runtime_events: [{
      at: '2026-05-21T03:59:00Z',
      stage: 'draft_candidate',
      level: 'info',
      kind: 'content',
      title: '正文首稿候选完成',
      summary: '候选 1 已生成，进入质量门检查。',
      content_preview: '沈文朝在潮雾里听见第二遍潮歌，终于意识到对方不是救他，而是在引他入祠。',
      metrics: {
        target_word_count: 5000,
        actual_word_count: 4700,
      },
      artifact_refs: [{ type: 'chapter_version', id: 'v1' }],
      metadata: {
        manual_patch_suggestions: [{
          problem: '章末压力不足',
          suggestion: '补一段追兵逼近，让下一章必须闯祠。',
        }],
      },
    }],
  }],
}]

describe('RuntimeLogManagement', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listRuntimeLogsMock.mockResolvedValue(runtimeProject())
  })

  it('保留摘要中的 0 字数值，不显示为未记录', async () => {
    const project = runtimeProject()
    const chapter = project[0].chapters[0]
    chapter.word_count = 0
    chapter.summary_snapshot.target_word_count = 0
    chapter.summary_snapshot.actual_word_count = 0
    chapter.runtime_snapshot.longform_context.cast_plan.planned_character_count = 0
    listRuntimeLogsMock.mockResolvedValueOnce(project)

    const wrapper = mount(RuntimeLogManagement, {
      global: { stubs: naiveStubs },
    })

    await flushPromises()

    const summaryRows = wrapper.findAll('.summary-grid dt').map((label, index) => ({
      label: label.text(),
      value: wrapper.findAll('.summary-grid dd')[index]?.text(),
    }))
    expect(summaryRows.find(row => row.label === '目标字数')?.value).toBe('0')
    expect(summaryRows.find(row => row.label === '实际字数')?.value).toBe('0')
    expect(summaryRows.find(row => row.label === '角色上下文')?.value).toContain('0 人计划')

    wrapper.unmount()
  })

  it('将详细日志展示为生成状态而不是程序流水', async () => {
    const wrapper = mount(RuntimeLogManagement, {
      global: {
        stubs: naiveStubs,
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('详细生成状态日志')
    expect(wrapper.text()).toContain('正文首稿候选完成')
    expect(wrapper.text()).toContain('生成内容预览')
    expect(wrapper.text()).toContain('沈文朝在潮雾里听见第二遍潮歌')
    expect(wrapper.text()).toContain('局部补丁建议')
    expect(wrapper.text()).toContain('章末压力不足')
    expect(wrapper.text()).toContain('目标字数')
    expect(wrapper.text()).toContain('实际字数')
    expect(wrapper.text()).toContain('Provider 预检完成')
    expect(wrapper.text()).toContain('CPA Provider')
    expect(wrapper.text()).toContain('正文长度契约已生效')
    expect(wrapper.text()).toContain('长期上下文已装配')
    expect(wrapper.text()).toContain('本章关注角色：沈文朝、潮祠守灯人')
    expect(wrapper.text()).toContain('Token 预算已记录')
    expect(wrapper.text()).toContain('16,800 token')
    expect(wrapper.text()).toContain('开发者详情：metadata')
    expect(wrapper.text()).not.toContain('详细后台运行日志')

    wrapper.unmount()
  })
})
