import { flushPromises, shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { pushMock, routeMock, novelStoreMock, alertMocks, localStorageState } = vi.hoisted(() => ({
  pushMock: vi.fn(),
  routeMock: { query: {} as Record<string, unknown> },
  novelStoreMock: {
    isLoading: false,
    currentProject: null as any,
    currentConversationState: { value: {} as Record<string, unknown> },
    setCurrentProject: vi.fn(),
    loadProject: vi.fn(),
    createProject: vi.fn(),
    sendConversation: vi.fn(),
    generateBlueprint: vi.fn(),
    startBlueprintGeneration: vi.fn(),
    getBlueprintGenerationStatus: vi.fn(),
    saveBlueprint: vi.fn(),
  },
  alertMocks: {
    showConfirm: vi.fn(),
    showError: vi.fn(),
    showSuccess: vi.fn(),
  },
  localStorageState: {} as Record<string, string>,
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: pushMock }),
  useRoute: () => routeMock,
}))

vi.mock('@/stores/novel', () => ({
  useNovelStore: () => novelStoreMock,
}))

vi.mock('@/composables/useAlert', () => ({
  globalAlert: alertMocks,
}))

vi.mock('@/components/ChatBubble.vue', () => ({
  default: {
    props: ['message', 'type'],
    template: '<div class="chat-bubble">{{ message }}</div>',
  },
}))

vi.mock('@/components/InspirationLoading.vue', () => ({
  default: {
    template: '<div class="loading">loading</div>',
  },
}))

vi.mock('@/components/ConversationInput.vue', () => ({
  default: {
    name: 'ConversationInput',
    props: ['uiControl', 'loading'],
    emits: ['submit'],
    template: '<button class="conversation-submit" @click="$emit(\'submit\', { value: \'补充设定\' })">submit</button>',
  },
}))

vi.mock('@/components/BlueprintConfirmation.vue', () => ({
  default: {
    props: ['aiMessage', 'forceStage'],
    template: '<div class="blueprint-confirmation">{{ aiMessage }}|{{ forceStage }}</div>',
  },
}))

vi.mock('@/components/BlueprintDisplay.vue', () => ({
  default: {
    props: ['blueprint', 'aiMessage'],
    template: '<div class="blueprint-display">{{ aiMessage }}</div>',
  },
}))

Object.defineProperty(window, 'localStorage', {
  value: {
    getItem: vi.fn((key: string) => localStorageState[key] ?? null),
    setItem: vi.fn((key: string, value: string) => {
      localStorageState[key] = value
    }),
    removeItem: vi.fn((key: string) => {
      delete localStorageState[key]
    }),
  },
  configurable: true,
})

import InspirationMode from './InspirationMode.vue'

const mountView = async () => {
  const wrapper = shallowMount(InspirationMode, {
    global: {
      stubs: {
        Teleport: true,
      },
    },
  })
  await flushPromises()
  return wrapper
}

describe('InspirationMode', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    pushMock.mockReset()
    routeMock.query = {}
    Object.keys(localStorageState).forEach((key) => delete localStorageState[key])
    novelStoreMock.isLoading = false
    novelStoreMock.currentProject = null
    novelStoreMock.currentConversationState.value = {}
    novelStoreMock.createProject.mockResolvedValue({ id: 'proj-1' })
    novelStoreMock.sendConversation.mockResolvedValue({
      ai_message: '先确定主角和冲突。',
      is_complete: false,
      ready_for_blueprint: false,
      ui_control: {
        type: 'text_input',
        placeholder: '输入想法',
      },
      conversation_state: { turn: 1 },
    })
    novelStoreMock.generateBlueprint.mockResolvedValue({
      blueprint: { title: '蓝图' },
      ai_message: '蓝图已生成',
    })
    novelStoreMock.startBlueprintGeneration.mockResolvedValue({ status: 'queued' })
    novelStoreMock.getBlueprintGenerationStatus.mockResolvedValue({ status: 'successful', blueprint: { title: '蓝图', chapter_outline: [{ chapter_number: 1, title: '第1章', summary: '摘要' }] }, ai_message: '章节大纲已生成' })
    novelStoreMock.saveBlueprint.mockResolvedValue(undefined)
    alertMocks.showConfirm.mockResolvedValue(true)
  })

  it('首轮完成且 ready_for_blueprint 时进入蓝图确认态', async () => {
    novelStoreMock.sendConversation.mockResolvedValueOnce({
      ai_message: '已经可以生成蓝图。',
      is_complete: true,
      ready_for_blueprint: true,
      ui_control: null,
      conversation_state: { turn: 2 },
    })

    const wrapper = await mountView()
    const startButton = wrapper.findAll('button').find((btn) => btn.text().includes('开始灵感对话'))
    expect(startButton).toBeTruthy()
    await startButton!.trigger('click')
    await flushPromises()

    expect(novelStoreMock.createProject).toHaveBeenCalledWith('未命名灵感', '开始灵感模式')
    expect(novelStoreMock.sendConversation).toHaveBeenCalledWith(null)
    expect(wrapper.text()).toContain('确认蓝图')
    expect(wrapper.html()).toContain('blueprint-confirmation-stub')
  })

  it('非首轮通信失败时保留既有对话，不整页重置', async () => {
    const wrapper = await mountView()
    const startButton = wrapper.findAll('button').find((btn) => btn.text().includes('开始灵感对话'))
    await startButton!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('对话进行中')
    expect(wrapper.text()).toContain('第 1 轮')

    novelStoreMock.sendConversation.mockRejectedValueOnce(new Error('network down'))
    const inputStub = wrapper.findComponent({ name: 'ConversationInput' })
    expect(inputStub.exists()).toBe(true)
    inputStub.vm.$emit('submit', { value: '补充设定' })
    await flushPromises()

    expect(alertMocks.showError).toHaveBeenCalled()
    expect(wrapper.text()).toContain('对话进行中')
    expect(wrapper.text()).toContain('第 1 轮')
    expect(novelStoreMock.sendConversation).toHaveBeenCalledTimes(2)
  })

  it('退出后重新进入时会从本地记录恢复灵感项目', async () => {
    localStorageState.xuanqiong_wenshu_active_inspiration_project_id = 'resume-proj'
    routeMock.query = {}
    novelStoreMock.currentProject = {
      id: 'resume-proj',
      blueprint: null,
      conversation_history: [
        { role: 'assistant', content: JSON.stringify({ ai_message: '继续补充冲突。', is_complete: false, ui_control: { type: 'text_input', placeholder: '继续输入' } }) },
      ],
    }
    novelStoreMock.loadProject.mockResolvedValue(undefined)

    const wrapper = await mountView()

    expect(novelStoreMock.loadProject).toHaveBeenCalledWith('resume-proj')
    expect(wrapper.text()).toContain('对话进行中')
    expect(wrapper.text()).toContain('第 1 轮')
    expect(wrapper.text()).toContain('继续输入')
  })

  it('退出对话时保留续接项目标记', async () => {
    const wrapper = await mountView()
    const startButton = wrapper.findAll('button').find((btn) => btn.text().includes('开始灵感对话'))
    await startButton!.trigger('click')
    await flushPromises()

    const exitButton = wrapper.findAll('button').find((btn) => btn.text().includes('退出'))
    expect(exitButton).toBeTruthy()
    await exitButton!.trigger('click')
    await flushPromises()

    expect(localStorageState.xuanqiong_wenshu_active_inspiration_project_id).toBe('proj-1')
    expect(pushMock).toHaveBeenCalledWith('/')
  })

  it('auto restores previous inspiration project', async () => {
    localStorageState.xuanqiong_wenshu_active_inspiration_project_id = 'resume-proj'

    const wrapper = await mountView()

    expect(novelStoreMock.loadProject).toHaveBeenCalledWith('resume-proj')
  })

  it('存在 query 项目时不显示继续上次灵感按钮', async () => {
    localStorageState.xuanqiong_wenshu_active_inspiration_project_id = 'resume-proj'
    routeMock.query = { project_id: 'query-proj' }
    novelStoreMock.currentProject = {
      id: 'query-proj',
      blueprint: null,
      conversation_history: [
        { role: 'assistant', content: JSON.stringify({ ai_message: '从 query 恢复。', is_complete: false, ui_control: { type: 'text_input', placeholder: '继续输入' } }) },
      ],
    }
    novelStoreMock.loadProject.mockResolvedValue(undefined)

    const wrapper = await mountView()

    expect(wrapper.text()).not.toContain('继续上次灵感')
  })

  it('provides fallback text input when restored assistant has no ui_control', async () => {
    localStorageState.xuanqiong_wenshu_active_inspiration_project_id = 'resume-proj'
    novelStoreMock.currentProject = {
      id: 'resume-proj',
      blueprint: null,
      conversation_history: [
        { role: 'assistant', content: JSON.stringify({ ai_message: 'continue with fallback', is_complete: false, ui_control: null }) },
      ],
    }
    novelStoreMock.loadProject.mockResolvedValue(undefined)

    const wrapper = await mountView()
    const inputStub = wrapper.findComponent({ name: 'ConversationInput' })

    expect(inputStub.exists()).toBe(true)
    expect(inputStub.props('loading')).toBe(false)
    expect(inputStub.props('uiControl')).toMatchObject({ type: 'text_input' })
  })

  it('navigates to writing desk without saving blueprint again', async () => {
    novelStoreMock.currentProject = { id: 'proj-1', blueprint: null, conversation_history: [] }
    const wrapper = await mountView()

    ;(wrapper.vm as any).handleBlueprintGenerated({
      blueprint: {
        title: 'Blueprint',
        chapter_outline: Array.from({ length: 12 }, (_, index) => ({ chapter_number: index + 1, title: `第${index + 1}章`, summary: '摘要' })),
      },
      ai_message: 'blueprint generated',
    })
    await (wrapper.vm as any).handleConfirmBlueprint()

    expect(novelStoreMock.saveBlueprint).not.toHaveBeenCalled()
    expect(pushMock).toHaveBeenCalledWith('/novel/proj-1')
    expect(localStorageState.xuanqiong_wenshu_active_inspiration_project_id).toBeUndefined()
  })

  it('uses blueprint length contract instead of a fixed 12 chapter completion rule', async () => {
    novelStoreMock.currentProject = { id: 'proj-1', blueprint: null, conversation_history: [] }
    const wrapper = await mountView()

    ;(wrapper.vm as any).handleBlueprintGenerated({
      blueprint: {
        title: 'Blueprint',
        world_setting: {
          system_blueprint: {
            length_contract: {
              target_chapter_count: 80,
              chapter_outline_seed_count: 24,
            },
          },
        },
        chapter_outline: Array.from({ length: 60 }, (_, index) => ({ chapter_number: index + 1, title: `第${index + 1}章`, summary: '摘要' })),
      },
      ai_message: 'blueprint generated',
    })
    await (wrapper.vm as any).handleConfirmBlueprint()

    expect(novelStoreMock.saveBlueprint).not.toHaveBeenCalled()
    expect(pushMock).toHaveBeenCalledWith('/novel/proj-1')
  })

  it('keeps chapter outline generation pending when length contract expects more chapters', async () => {
    novelStoreMock.currentProject = { id: 'proj-1', blueprint: null, conversation_history: [] }
    const wrapper = await mountView()

    ;(wrapper.vm as any).handleBlueprintGenerated({
      blueprint: {
        title: 'Blueprint',
        world_setting: {
          system_blueprint: {
            length_contract: {
              target_chapter_count: 80,
              chapter_outline_seed_count: 24,
            },
          },
        },
        chapter_outline: Array.from({ length: 12 }, (_, index) => ({ chapter_number: index + 1, title: `第${index + 1}章`, summary: '摘要' })),
      },
      ai_message: 'blueprint generated',
    })
    await (wrapper.vm as any).handleConfirmBlueprint()
    await flushPromises()

    expect((wrapper.vm as any).pendingBlueprintForceStage).toBe('chapter_outline')
    expect(pushMock).not.toHaveBeenCalled()
  })

  it('novel outline only blueprint switches to forced chapter outline confirmation view', async () => {
    novelStoreMock.currentProject = { id: 'proj-1', blueprint: null, conversation_history: [] }
    const wrapper = await mountView()

    ;(wrapper.vm as any).handleBlueprintGenerated({
      blueprint: { title: 'Blueprint', novel_outline: [{ stage: 1, title: '第一阶段' }] },
      ai_message: 'blueprint generated',
    })
    await (wrapper.vm as any).handleConfirmBlueprint()
    await flushPromises()

    expect(novelStoreMock.startBlueprintGeneration).not.toHaveBeenCalled()
    expect((wrapper.vm as any).pendingBlueprintForceStage).toBe('chapter_outline')
    expect(wrapper.html()).toContain('blueprint-confirmation-stub')
    expect(pushMock).not.toHaveBeenCalled()
  })


  it('restores novel outline stage when blueprint has total outline but no chapter outline', async () => {
    localStorageState.xuanqiong_wenshu_active_inspiration_project_id = 'novel-outline-proj'
    novelStoreMock.currentProject = {
      id: 'novel-outline-proj',
      blueprint: { title: '异海开拓史', novel_outline: [{ stage: 1, title: '孤岛立足' }] },
      conversation_history: [
        { role: 'assistant', content: JSON.stringify({ ai_message: '总纲已生成', is_complete: false, ui_control: null, conversation_state: { stage: 'outline' } }) },
      ],
    }
    novelStoreMock.loadProject.mockResolvedValue(undefined)

    const wrapper = await mountView()

    expect(wrapper.html()).toContain('blueprint-display-stub')
  })

  it('regenerate blueprint marks next confirmation as forced novel outline regeneration', async () => {
    novelStoreMock.currentProject = { id: 'proj-1', blueprint: null, conversation_history: [] }
    const wrapper = await mountView()

    ;(wrapper.vm as any).handleBlueprintGenerated({
      blueprint: { title: 'Blueprint', novel_outline: [{ stage: 1, title: '第一阶段' }] },
      ai_message: 'blueprint generated',
    })
    ;(wrapper.vm as any).handleRegenerateBlueprint()
    await flushPromises()

    expect(wrapper.html()).toContain('blueprint-confirmation-stub')
    expect((wrapper.vm as any).pendingBlueprintForceStage).toBe('novel_outline')
  })

  it('does not treat empty blueprint as usable on resume', async () => {
    localStorageState.xuanqiong_wenshu_active_inspiration_project_id = 'empty-blueprint-proj'
    novelStoreMock.currentProject = {
      id: 'empty-blueprint-proj',
      blueprint: { title: '', chapter_outline: [] },
      conversation_history: [
        { role: 'assistant', content: JSON.stringify({ ai_message: 'continue conflict', is_complete: false, ui_control: null, conversation_state: { stage: 'conflict' } }) },
      ],
    }
    novelStoreMock.loadProject.mockResolvedValue(undefined)

    const wrapper = await mountView()

    expect(wrapper.html()).not.toContain('blueprint-display-stub')
    expect(wrapper.html()).toContain('blueprint-confirmation-stub')
    expect(novelStoreMock.currentConversationState.value).toMatchObject({ stage: 'conflict' })
  })

})
