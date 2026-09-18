import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import NovelOutlineSection from './NovelOutlineSection.vue'

describe('NovelOutlineSection', () => {
  it('展示正式详情页所需的总纲骨架信息', () => {
    const wrapper = mount(NovelOutlineSection, {
      props: {
        data: {
          world_setting: {
            era_background: '旧文明断裂后进入群岛争夺时代。',
            power_system: { core: '修炼需绑定潮汐反馈' },
            culture_system: { customs: '海祭与航名制度塑造身份认同' },
          },
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
              resource_and_operation_line: '围绕淡水、火种、补给点与残迹安全区展开。',
              emotional_core: '在恐惧中建立秩序感。',
              major_setpiece: '夜潮侵袭下的营地保卫战。',
              story_function: '把故事从单纯求生推进到文明主线入口。',
              key_events: ['找到潮汐残图', '守住首轮围攻'],
              turning_points: ['确认潮汐异常不是自然现象'],
              stage_tasks: ['建立营地制度'],
              stage_climax: '主角击退入侵者并守住岛屿',
              foreshadowing_and_payoff: '残图指向更深海域的文明断层',
              ending_hook: '新的海图坐标在夜潮中显现',
              expected_chapter_range: '1-60章',
            },
          ],
          story_arcs: [{ title: '遗迹权限线', summary: '围绕旧文明权限展开的主线争夺。' }],
          volume_plan: [{ title: '第一卷 孤岛起势', summary: '从求生转向聚落建设。' }],
          foreshadowing_system: [{ plant: '残图异动', payoff: '揭示外海入口' }],
        },
      },
    })

    const text = wrapper.text()
    expect(text).toContain('小说总大纲与世界骨架')
    expect(text).toContain('时代背景')
    expect(text).toContain('力量体系')
    expect(text).toContain('文化体系')
    expect(text).toContain('生存/生活推进')
    expect(text).toContain('文化/文明推进')
    expect(text).toContain('资源/运营线')
    expect(text).toContain('情绪核心')
    expect(text).toContain('场面支点')
    expect(text).toContain('阶段职责')
    expect(text).toContain('故事弧线')
    expect(text).toContain('卷规划')
    expect(text).toContain('伏笔系统')
    expect(text).toContain('孤岛立足')
  })
})
