import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import BlueprintDisplay from './BlueprintDisplay.vue'

const { alertMock } = vi.hoisted(() => ({
  alertMock: {
    showConfirm: vi.fn(),
  },
}))

vi.mock('@/composables/useAlert', () => ({
  globalAlert: alertMock,
}))

const buildBlueprint = (overrides: Record<string, unknown> = {}) => ({
  title: '异海开拓史',
  one_sentence_summary: '在异海求生并建立新文明',
  full_synopsis: '主角在断裂海域中扩张航路、势力与文明秩序。',
  genre: '航海冒险',
  style: '长篇升级',
  tone: '宏大',
  target_audience: '男频',
  world_setting: {
    core_rules: '海潮会周期性改写航路规则。',
    era_background: '旧文明断裂后进入群岛争夺时代。',
    power_system: { core: '修炼需绑定潮汐反馈' },
    culture_system: { customs: '海祭与航名制度塑造身份认同' },
    key_locations: [],
    factions: [],
  },
  characters: [],
  relationships: [],
  chapter_outline: [],
  novel_outline: [
    {
      stage: 1,
      title: '孤岛立足',
      core_theme: '生存与立足',
      goal: '建立首个安全据点',
      main_conflict: '资源匮乏与外敌试探',
      background: '孤岛海域规则混乱',
      character_progression: '主角从求生转向组织者',
      world_progression: '首次揭示异海航路规则',
      faction_progression: '海盗团开始注意主角',
      power_progression: '修炼体系初次成型',
      survival_and_life_progression: '从抢水搭棚走向稳定轮值与补给制度。',
      cultural_and_civilizational_progression: '幸存者开始形成共享规则与海祭雏形。',
      resource_and_operation_line: '围绕淡水、火种、补给点与残迹边缘安全区展开。',
      emotional_core: '在恐惧中建立秩序感。',
      major_setpiece: '夜潮侵袭下的营地保卫战。',
      turning_points: ['发现潮汐异常不是自然现象', '确认主角与遗迹存在呼应'],
      stage_tasks: ['建立营地制度', '锁定残迹线索'],
      story_function: '把故事从单纯求生推进到文明主线的入口。',
      key_events: ['找到潮汐残图', '守住首轮围攻', '收拢第一批追随者', '建立补给点', '发现旧文明遗迹'],
      stage_climax: '主角击退入侵者并守住岛屿',
      foreshadowing_and_payoff: '残图指向更深海域的文明断层',
      ending_hook: '新的海图坐标在夜潮中显现',
      expected_chapter_range: '1-60章',
    },
  ],
  ...overrides,
})

describe('BlueprintDisplay', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    alertMock.showConfirm.mockResolvedValue(true)
  })

  it('有小说总大纲时展示重新生成小说总大纲按钮', () => {
    const wrapper = mount(BlueprintDisplay, {
      props: {
        blueprint: buildBlueprint(),
      },
    })

    expect(wrapper.text()).toContain('重新生成小说总大纲')
  })

  it('点击重新生成小说总大纲后触发 regenerate 事件', async () => {
    const wrapper = mount(BlueprintDisplay, {
      props: {
        blueprint: buildBlueprint(),
      },
    })

    const button = wrapper.findAll('button').find((item) => item.text().includes('重新生成小说总大纲'))
    expect(button).toBeTruthy()
    await button!.trigger('click')

    expect(alertMock.showConfirm).toHaveBeenCalledWith(
      '重新生成小说总大纲会覆盖当前总纲及其下游章节大纲，确定继续吗？',
      '重新生成小说总大纲确认'
    )
    expect(wrapper.emitted('regenerate')).toBeTruthy()
  })

  it('章节大纲未满十二章时仍提示继续生成章节大纲', () => {
    const wrapper = mount(BlueprintDisplay, {
      props: {
        blueprint: buildBlueprint({
          chapter_outline: [{ chapter_number: 1, title: '第1章', summary: '摘要' }],
        }),
      },
    })

    expect(wrapper.text()).toContain('基于小说总大纲生成章节大纲')
    expect(wrapper.text()).not.toContain('确认蓝图并进入开写')
  })

  it('展示世界系统卡片与阶段扩展字段', () => {
    const wrapper = mount(BlueprintDisplay, {
      props: {
        blueprint: buildBlueprint(),
      },
    })

    const text = wrapper.text()
    expect(text).toContain('时代背景')
    expect(text).toContain('力量体系')
    expect(text).toContain('文化体系')
    expect(text).toContain('生存/生活推进')
    expect(text).toContain('文化/文明推进')
    expect(text).toContain('资源/运营线')
    expect(text).toContain('情绪核心')
    expect(text).toContain('场面支点')
    expect(text).toContain('阶段职责')
    expect(text).toContain('转折节点')
    expect(text).toContain('阶段任务')
  })
})
