import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getChapters: vi.fn(),
  getProjectStyle: vi.fn(),
  listStyleSources: vi.fn(),
  listStyleProfiles: vi.fn(),
  getActiveStyleProfile: vi.fn(),
  extractStyle: vi.fn(),
  createStyleSource: vi.fn(),
  deleteStyleSource: vi.fn(),
  createStyleProfile: vi.fn(),
  activateStyleProfile: vi.fn(),
  clearActiveStyleProfile: vi.fn(),
}))

vi.mock('@/api/novel', () => ({
  NovelAPI: {
    getChapters: mocks.getChapters,
  },
  OptimizerAPI: {
    getProjectStyle: mocks.getProjectStyle,
    listStyleSources: mocks.listStyleSources,
    listStyleProfiles: mocks.listStyleProfiles,
    getActiveStyleProfile: mocks.getActiveStyleProfile,
    extractStyle: mocks.extractStyle,
    createStyleSource: mocks.createStyleSource,
    deleteStyleSource: mocks.deleteStyleSource,
    createStyleProfile: mocks.createStyleProfile,
    activateStyleProfile: mocks.activateStyleProfile,
    clearActiveStyleProfile: mocks.clearActiveStyleProfile,
  },
}))

import WDStyleExtractModal from './WDStyleExtractModal.vue'

const defaultChaptersResponse = {
  chapters: [
    { number: 1, title: '第一章', content: '甲'.repeat(800) },
    { number: 2, title: '第二章', content: '乙'.repeat(900) },
    { number: 3, title: '第三章', content: '丙'.repeat(1200) },
  ],
}

const mountModal = async () => {
  const wrapper = mount(WDStyleExtractModal, {
    props: {
      show: false,
      projectId: 'project-1',
    },
  })
  await wrapper.setProps({ show: true })
  await flushPromises()
  return wrapper
}

describe('WDStyleExtractModal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getChapters.mockResolvedValue(defaultChaptersResponse)
    mocks.getProjectStyle.mockResolvedValue({ has_style: false, summary: null, source: null })
    mocks.listStyleSources.mockResolvedValue({ sources: [] })
    mocks.listStyleProfiles.mockResolvedValue({ profiles: [] })
    mocks.getActiveStyleProfile.mockResolvedValue({ has_active_style: false, profile: null, scope: null })
    mocks.extractStyle.mockResolvedValue({
      success: true,
      style_summary: {
        summary: {
          narrative: '叙事沉稳',
          rhythm: '节奏克制',
          vocabulary: '词汇冷峻',
          dialogue: '对白含蓄',
        },
      },
    })
    mocks.createStyleSource.mockResolvedValue({
      success: true,
      source: { id: 'src-1', title: '外部参考 A', char_count: 3200, source_type: 'external_text' },
    })
    mocks.deleteStyleSource.mockResolvedValue({ success: true })
    mocks.createStyleProfile.mockResolvedValue({
      success: true,
      profile: {
        id: 'profile-1',
        name: '外部文风画像',
        source_ids: ['src-1'],
        summary: { narrative: '叙事沉稳' },
      },
    })
    mocks.activateStyleProfile.mockResolvedValue({
      success: true,
      scope: 'project',
      profile: {
        id: 'profile-1',
        name: '外部文风画像',
        source_ids: ['src-1'],
        summary: { narrative: '叙事沉稳' },
      },
    })
    mocks.clearActiveStyleProfile.mockResolvedValue({ success: true })
  })

  it('打开弹窗时加载章节和文风数据', async () => {
    await mountModal()

    expect(mocks.getChapters).toHaveBeenCalledWith('project-1')
    expect(mocks.getProjectStyle).toHaveBeenCalledWith('project-1')
    expect(mocks.listStyleSources).toHaveBeenCalledWith('project-1')
    expect(mocks.listStyleProfiles).toHaveBeenCalledWith('project-1')
    expect(mocks.getActiveStyleProfile).toHaveBeenCalledWith('project-1')
  })

  it('self 模式下选择章节后会提取项目章节文风并触发 extracted', async () => {
    const wrapper = await mountModal()

    const chapterCards = wrapper.findAll('div.cursor-pointer')
    expect(chapterCards.length).toBeGreaterThanOrEqual(2)
    await chapterCards[0].trigger('click')
    await chapterCards[1].trigger('click')
    const learnButton = wrapper.findAll('button').find((btn) => btn.text() === '学习我的文风')
    expect(learnButton).toBeTruthy()
    await learnButton!.trigger('click')
    await flushPromises()

    expect(mocks.extractStyle).toHaveBeenCalledWith('project-1', [1, 2])
    const extractedEvents = wrapper.emitted('extracted')
    expect(extractedEvents).toBeTruthy()
    expect(extractedEvents?.[0]?.[0]).toMatchObject({ narrative: '叙事沉稳' })
    expect(wrapper.text()).toContain('当前项目章节文风摘要')
  })

  it('external 模式下可保存参考文本、生成画像并自动激活', async () => {
    const wrapper = await mountModal()

    const externalTab = wrapper.findAll('button').find((btn) => btn.text() === '外部参考')
    expect(externalTab).toBeTruthy()
    await externalTab!.trigger('click')

    const titleInput = wrapper.find('input[type="text"]')
    expect(titleInput.exists()).toBe(true)
    await titleInput.setValue('雪中风格参考')
    await wrapper.get('textarea').setValue('风'.repeat(600))

    const buttons = wrapper.findAll('button')
    const saveButton = buttons.find((btn) => btn.text() === '保存为参考文本')
    expect(saveButton).toBeTruthy()
    await saveButton!.trigger('click')
    await flushPromises()

    expect(mocks.createStyleSource).toHaveBeenCalledWith('project-1', {
      title: '雪中风格参考',
      content_text: '风'.repeat(600),
      source_type: 'external_text',
    })

    const profileButton = wrapper.findAll('button').find((btn) => btn.text() === '生成文风画像')
    expect(profileButton).toBeTruthy()
    await profileButton!.trigger('click')
    await flushPromises()

    expect(mocks.createStyleProfile).toHaveBeenCalledWith('project-1', {
      source_ids: ['src-1'],
      name: '雪中风格参考',
    })
    expect(mocks.activateStyleProfile).toHaveBeenCalledWith('project-1', 'profile-1', 'project')

    const extractedEvents = wrapper.emitted('extracted')
    expect(extractedEvents?.length).toBeGreaterThan(0)
  })

  it('external 模式支持整本小说导入并以 external_novel 类型保存', async () => {
    const wrapper = await mountModal()

    const externalTab = wrapper.findAll('button').find((btn) => btn.text() === '外部参考')
    expect(externalTab).toBeTruthy()
    await externalTab!.trigger('click')

    const fullNovelButton = wrapper.findAll('button').find((btn) => btn.text() === '整本小说')
    expect(fullNovelButton).toBeTruthy()
    await fullNovelButton!.trigger('click')

    const titleInput = wrapper.find('input[type="text"]')
    await titleInput.setValue('雪中整书参考')
    await wrapper.get('textarea').setValue('雪'.repeat(5200))
    await flushPromises()

    const saveButton = wrapper.findAll('button').find((btn) => btn.text() === '保存为参考文本')
    expect(saveButton).toBeTruthy()
    await saveButton!.trigger('click')
    await flushPromises()

    expect(mocks.createStyleSource).toHaveBeenCalledWith('project-1', {
      title: '雪中整书参考',
      content_text: '雪'.repeat(5200),
      source_type: 'external_novel',
    })
  })

  it('self 模式遇到外部激活文风时给出明确提示，不误显示为章节文风', async () => {
    mocks.getProjectStyle.mockResolvedValue({
      has_style: true,
      summary: { narrative: '外部文风叙事' },
      source: { mode: 'external', profile_name: '外部参考文风' },
    })
    mocks.getActiveStyleProfile.mockResolvedValue({
      has_active_style: true,
      scope: 'global',
      profile: { id: 'profile-1', name: '外部参考文风', source_ids: ['src-1'] },
    })

    const wrapper = await mountModal()

    expect(wrapper.text()).toContain('当前启用的是外部参考文风')
    expect(wrapper.text()).not.toContain('当前项目章节文风摘要')
  })
})
