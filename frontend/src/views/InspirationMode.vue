<template>
  <div class="inspiration-shell xq-page-canvas min-h-screen text-slate-900">
    <header class="inspiration-topbar xq-topbar xq-topbar--inspiration sticky top-0 z-30">
      <div class="mx-auto flex w-full max-w-7xl items-center gap-4 px-4 py-4 sm:px-6 lg:px-8">
        <button class="inspiration-back-btn" type="button" @click="goBack">
          <span class="inspiration-back-icon">&larr;</span>
          <span>{{ pick('返回', 'Back') }}</span>
        </button>

        <div class="min-w-0 flex-1">
          <p class="inspiration-kicker">{{ pick('灵感模式', 'Inspiration mode') }}</p>
          <h1 class="mt-1 truncate text-xl font-semibold tracking-tight text-slate-900 sm:text-3xl">
            {{ pick('对话式创作工作台', 'Conversational writing workspace') }}
          </h1>
          <p class="mt-2 max-w-3xl text-sm leading-6 text-slate-600 sm:text-base">
            {{ pick(
              '先用聊天把灵感说出来，再逐轮收束成可落地的小说蓝图，减少一次性堆满表单的压迫感。',
              'Talk the idea out in chat first, then narrow it down round by round into a workable novel blueprint, instead of facing one crowded form.',
            ) }}
          </p>
        </div>

        <div class="hidden items-center gap-2 md:flex">
          <button class="inspiration-ghost-btn" type="button" :disabled="isInteractionLocked" @click="handleRestart">
            {{ pick('重启', 'Restart') }}
          </button>
          <button class="inspiration-ghost-btn" type="button" :disabled="isInteractionLocked" @click="exitConversation">
            {{ pick('退出', 'Exit') }}
          </button>
        </div>
      </div>
    </header>

    <main class="mx-auto flex min-h-[calc(100vh-88px)] w-full max-w-[1480px] flex-col gap-4 px-4 py-4 sm:px-5 lg:px-6 xl:px-8">
      <section class="inspiration-panel inspiration-stage-strip px-4 py-3 sm:px-4 sm:py-4">
        <div class="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p class="inspiration-kicker">{{ pick('当前阶段', 'Current stage') }}</p>
            <h2 class="mt-2 text-base font-semibold text-slate-950">{{ stageTitle }}</h2>
            <p class="mt-2 text-sm leading-6 text-slate-600">{{ stageDescription }}</p>
          </div>
          <div class="inspiration-stage-strip__actions">
            <button v-if="showReturnToConversation" class="inspiration-mini-btn" type="button" :disabled="isInteractionLocked" @click="backToConversation">
              {{ pick('返回对话', 'Back to conversation') }}
            </button>
            <button v-if="showSoftRestart" class="inspiration-mini-btn" type="button" :disabled="isInteractionLocked" @click="handleRestart">
              {{ pick('重启本轮', 'Restart this round') }}
            </button>
          </div>
        </div>
        <div v-if="inspirationProgressVisible" class="inspiration-progress-card mt-4">
          <div class="inspiration-progress-card__head">
            <strong>{{ inspirationProgressTitle }}</strong>
            <span>{{ inspirationProgressPercent }}%</span>
          </div>
          <p class="inspiration-progress-card__desc">{{ inspirationProgressDescription }}</p>
          <div class="inspiration-progress-track" aria-label="inspiration-progress">
            <div class="inspiration-progress-bar" :style="{ width: `${inspirationProgressPercent}%` }"></div>
          </div>
        </div>
        <div class="inspiration-stage-list mt-4">
          <div
            v-for="item in stageItems"
            :key="item.key"
            class="inspiration-stage-item"
            :class="{ 'inspiration-stage-item--active': item.key === currentStageKey, 'inspiration-stage-item--done': item.done }"
          >
            <span class="inspiration-stage-item__dot">{{ item.index }}</span>
            <div>
              <p class="inspiration-stage-item__title">{{ item.title }}</p>
              <p class="inspiration-stage-item__desc">{{ item.desc }}</p>
            </div>
          </div>
        </div>
      </section>

      <section
        v-if="!conversationStarted && !showBlueprintConfirmation && !showBlueprint"
        class="grid flex-1 min-h-0 gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(320px,380px)]"
      >
        <article class="inspiration-panel inspiration-landing-panel flex min-h-0 flex-col justify-between p-5 sm:p-6">
          <div>
            <div class="flex flex-wrap items-center gap-2">
              <span class="inspiration-pill inspiration-pill--blue">{{ pick('先说一个想法', 'Start with one idea') }}</span>
              <span class="inspiration-pill inspiration-pill--teal">{{ pick('逐轮收束', 'Narrow round by round') }}</span>
              <span class="inspiration-pill inspiration-pill--slate">{{ pick('不必一次定完', 'No need to settle it all at once') }}</span>
            </div>

            <h2 class="mt-6 max-w-3xl text-xl font-semibold tracking-tight text-slate-950 sm:text-4xl lg:text-5xl">
              {{ pick('把灵感先说出来，系统再帮你把它收成故事骨架。', 'Say the idea out loud first, then let the system shape it into a story skeleton.') }}
            </h2>

            <p class="mt-5 max-w-2xl text-base leading-8 text-slate-600 sm:text-lg">
              {{ pick(
                '这里不是“表单页”，而是一条对话式创作流水线。你只需要给出碎片化想法，AI 会逐轮收束成蓝图，再继续进入写作工作台。',
                'This is not a "form page" but a conversational writing pipeline. Just bring fragments of an idea; AI narrows them into a blueprint round by round before you move on to the writing workspace.',
              ) }}
            </p>
          </div>

          <div class="mt-8 grid gap-3 sm:grid-cols-3">
            <div class="inspiration-step">
              <span class="inspiration-step__index">1</span>
              <div>
                <p class="inspiration-step__title">{{ pick('开始对话', 'Start the conversation') }}</p>
                <p class="inspiration-step__desc">{{ pick('先让系统拿到你最初的想法。', 'Let the system capture your very first idea.') }}</p>
              </div>
            </div>
            <div class="inspiration-step">
              <span class="inspiration-step__index">2</span>
              <div>
                <p class="inspiration-step__title">{{ pick('逐轮收束', 'Narrow round by round') }}</p>
                <p class="inspiration-step__desc">{{ pick('每一轮只解决一个小问题。', 'Each round settles one small question.') }}</p>
              </div>
            </div>
            <div class="inspiration-step">
              <span class="inspiration-step__index">3</span>
              <div>
                <p class="inspiration-step__title">{{ pick('生成蓝图', 'Generate the blueprint') }}</p>
                <p class="inspiration-step__desc">{{ pick('确认后直接进入工作台。', 'Once confirmed, go straight to the workspace.') }}</p>
              </div>
            </div>
          </div>
        </article>

        <aside class="inspiration-panel flex min-h-0 flex-col gap-3 p-4 sm:p-5">
          <div class="rounded-[24px] border border-slate-200 bg-slate-950 px-5 py-5 text-white shadow-[0_20px_60px_-30px_rgba(15,23,42,0.55)]">
            <p class="text-xs uppercase tracking-[0.28em] text-slate-400">{{ pick('当前入口', 'Current entry') }}</p>
            <h3 class="mt-2 text-xl font-semibold">{{ pick('灵感工作流', 'Inspiration workflow') }}</h3>
            <p class="mt-3 text-sm leading-6 text-slate-300">
              {{ pick(
                '适合还没有大纲，或者只想先把一个模糊想法快速变成可写结构的时候。',
                'Best when there is no outline yet, or you just want to turn a vague idea into a writable structure fast.',
              ) }}
            </p>
          </div>

          <div class="rounded-[24px] border border-slate-200 bg-white/90 p-3.5 shadow-[0_18px_48px_-32px_rgba(15,23,42,0.35)]">
            <p class="text-sm font-semibold text-slate-900">{{ pick('这条线的顺序', 'How this flow runs') }}</p>
            <ol class="mt-4 space-y-3 text-sm leading-6 text-slate-600">
              <li class="flex items-start gap-3">
                <span class="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-xs font-semibold text-indigo-700">1</span>
                <span>{{ pick('创建一个临时灵感项目，保留上下文。', 'Create a temporary inspiration project to keep the context.') }}</span>
              </li>
              <li class="flex items-start gap-3">
                <span class="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-cyan-100 text-xs font-semibold text-cyan-700">2</span>
                <span>{{ pick('通过对话逐步澄清题材、人物和冲突。', 'Clarify genre, characters, and conflict through the conversation.') }}</span>
              </li>
              <li class="flex items-start gap-3">
                <span class="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-xs font-semibold text-emerald-700">3</span>
                <span>{{ pick('确认蓝图后进入章节写作工作台。', 'Confirm the blueprint, then enter the chapter writing workspace.') }}</span>
              </li>
            </ol>
          </div>

          <div class="mt-auto flex flex-col gap-3">
            <button
              v-if="hasResumeProject"
              type="button"
              class="inspiration-ghost-btn inspiration-ghost-btn--resume text-base"
              :disabled="novelStore.isLoading"
              @click="resumeLastConversation"
            >
              {{ pick('继续上次灵感', 'Resume last inspiration') }}
            </button>
            <button
              type="button"
              class="inspiration-primary-btn text-base"
              :disabled="novelStore.isLoading"
              @click="startConversation"
            >
              {{ novelStore.isLoading ? pick('正在准备...', 'Preparing...') : pick('开始灵感对话', 'Start the inspiration conversation') }}
            </button>
          </div>
        </aside>
      </section>

      <section
        v-else-if="showBlueprintConfirmation || showBlueprint"
        class="flex flex-1 min-h-0 flex-col overflow-hidden"
      >
        <div class="mb-4 flex items-center justify-between gap-3">
          <div>
            <p class="inspiration-kicker">{{ pick('蓝图阶段', 'Blueprint stage') }}</p>
            <h2 class="mt-1 text-xl font-semibold text-slate-950 sm:text-2xl">
              {{ showBlueprintConfirmation ? pick('确认蓝图', 'Confirm the blueprint') : pick('查看蓝图', 'View the blueprint') }}
            </h2>
          </div>
          <button
            v-if="showBlueprintConfirmation"
            class="inspiration-ghost-btn"
            type="button"
            :disabled="isInteractionLocked"
            @click="backToConversation"
          >
            {{ pick('返回对话', 'Back to conversation') }}
          </button>
        </div>

        <div class="inspiration-panel flex-1 min-h-0 overflow-y-auto p-4 sm:p-6">
          <div class="mx-auto flex min-h-full w-full max-w-7xl items-start justify-center py-2">
            <div class="w-full">
              <BlueprintConfirmation
                v-if="showBlueprintConfirmation"
                :ai-message="confirmationMessage"
                :force-stage="pendingBlueprintForceStage"
                @blueprint-generated="handleBlueprintGenerated"
                @back="backToConversation"
              />

              <BlueprintDisplay
                v-if="showBlueprint"
                :blueprint="completedBlueprint"
                :ai-message="blueprintMessage"
                :is-saving="isSavingBlueprint"
                @confirm="handleConfirmBlueprint"
                @regenerate="handleRegenerateBlueprint"
              />
            </div>
          </div>
        </div>
      </section>

      <section
        v-else
        class="inspiration-chat-layout grid flex-1 min-h-0 gap-3"
      >
        <div class="inspiration-panel inspiration-chat-panel flex min-h-0 flex-col overflow-hidden">
          <div class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200/80 px-4 py-4 sm:px-5">
            <div class="flex flex-wrap items-center gap-2">
              <span class="inspiration-pill inspiration-pill--blue">{{ conversationStateLabel }}</span>
              <span v-if="currentTurn > 0" class="inspiration-pill inspiration-pill--slate">
                {{ pick(`第 ${currentTurn} 轮`, `Round ${currentTurn}`) }}
              </span>
              <span class="inspiration-pill inspiration-pill--teal">
                {{ chatMessages.length }} {{ pick('条消息', 'messages') }}
              </span>
            </div>

            <div class="flex items-center gap-2">
              <button class="inspiration-mini-btn" type="button" @click="handleRestart">
                {{ pick('重启', 'Restart') }}
              </button>
              <button class="inspiration-mini-btn" type="button" @click="exitConversation">
                {{ pick('退出', 'Exit') }}
              </button>
            </div>
          </div>

          <div class="border-b border-slate-200/70 bg-slate-50/80 px-4 py-3 sm:px-5">
            <p class="text-sm font-medium text-slate-900">{{ currentControlTitle }}</p>
            <p class="mt-1 text-sm leading-6 text-slate-600">
              {{ currentControlHint }}
            </p>
          </div>

          <div ref="chatArea" class="inspiration-chat-area flex-1 min-h-[260px] space-y-3 overflow-y-auto px-4 py-4 sm:px-5 sm:py-4 lg:min-h-[320px]">
            <transition name="fade">
              <InspirationLoading v-if="isInitialLoading" />
            </transition>

            <ChatBubble
              v-for="(message, index) in chatMessages"
              :key="index"
              :message="message.content"
              :type="message.type"
            />
          </div>

          <div class="inspiration-input-shell border-t border-slate-200/80 bg-white/95 px-4 py-3 sm:px-5 sm:py-4">
            <div class="mb-3 flex items-center justify-between gap-3">
              <div>
                <p class="text-sm font-semibold text-slate-900">{{ pick('输入区', 'Input area') }}</p>
                <p class="mt-1 text-xs leading-5 text-slate-500">
                  {{ pick('先给出最小可用想法即可，后续再逐轮补充。', 'A minimal usable idea is enough; add more round by round.') }}
                </p>
              </div>
              <span class="inspiration-pill inspiration-pill--slate">{{ pick('支持单选和文本补充', 'Single choice and free text supported') }}</span>
            </div>

            <div class="inspiration-input-scroll">
              <ConversationInput
                :ui-control="currentUIControl"
                :loading="novelStore.isLoading"
                @submit="handleUserInput"
              />
            </div>
          </div>
        </div>

        <aside class="inspiration-rail flex min-h-0 flex-col gap-3 overflow-y-auto pr-1">
          <section class="inspiration-panel inspiration-rail-card p-5">
            <p class="inspiration-kicker">{{ pick('当前状态', 'Current state') }}</p>
            <h3 class="mt-2 text-xl font-semibold text-slate-950">{{ conversationStateLabel }}</h3>
            <p class="mt-3 text-sm leading-6 text-slate-600">
              {{ stateDescription }}
            </p>

            <div class="mt-5 grid grid-cols-2 gap-3">
              <div class="inspiration-metric">
                <span class="inspiration-metric__label">{{ pick('当前轮次', 'Current round') }}</span>
                <strong class="inspiration-metric__value">{{ currentTurn }}</strong>
              </div>
              <div class="inspiration-metric">
                <span class="inspiration-metric__label">{{ pick('控制类型', 'Control type') }}</span>
                <strong class="inspiration-metric__value">{{ controlModeLabel }}</strong>
              </div>
              <div class="inspiration-metric">
                <span class="inspiration-metric__label">{{ pick('消息数量', 'Messages') }}</span>
                <strong class="inspiration-metric__value">{{ chatMessages.length }}</strong>
              </div>
              <div class="inspiration-metric">
                <span class="inspiration-metric__label">{{ pick('选项数量', 'Options') }}</span>
                <strong class="inspiration-metric__value">{{ currentControlOptionCount }}</strong>
              </div>
            </div>
          </section>

          <section class="inspiration-panel inspiration-rail-card p-5">
            <p class="inspiration-kicker">{{ pick('操作建议', 'Tips') }}</p>
            <ul class="mt-4 space-y-3 text-sm leading-6 text-slate-600">
              <li class="flex gap-3">
                <span class="mt-1 h-2 w-2 rounded-full bg-indigo-500"></span>
                <span>{{ pick(
                  '先看 AI 这轮提示，再只做必要补充，不要一次性把整本书都写完。',
                  'Read the AI prompt for this round, add only what is needed, and do not try to write the whole book at once.',
                ) }}</span>
              </li>
              <li class="flex gap-3">
                <span class="mt-1 h-2 w-2 rounded-full bg-cyan-500"></span>
                <span>{{ pick(
                  '单选时直接选最接近的一项，再用文字把偏差补齐。',
                  'For single choice, take the closest option and close the gap in text.',
                ) }}</span>
              </li>
              <li class="flex gap-3">
                <span class="mt-1 h-2 w-2 rounded-full bg-emerald-500"></span>
                <span>{{ pick(
                  '输入区在底部固定分层，不用在一大坨选项里来回找入口。',
                  'The input area stays pinned at the bottom, so you never hunt for it inside a pile of options.',
                ) }}</span>
              </li>
            </ul>
          </section>

          <section class="inspiration-panel inspiration-rail-card p-5">
            <p class="inspiration-kicker">{{ pick('工作流摘要', 'Workflow summary') }}</p>
            <div class="mt-4 space-y-3 text-sm leading-6 text-slate-600">
              <p>{{ pick(
                '如果对话结束，会先进入蓝图确认，再保存到工作台。',
                'When the conversation ends, you confirm the blueprint first, then it is saved to the workspace.',
              ) }}</p>
              <p v-if="currentUIControl?.type === 'single_choice' || currentUIControl?.type === 'multi_choice'">
                {{ pick(`这一轮有 ${currentControlOptionCount} 个候选选项，`, `This round offers ${currentControlOptionCount} candidate options. `) }}{{ currentUIControl?.type === 'multi_choice' ? pick('可以组合多个方向一起推进。', 'You can combine several directions and push them forward together.') : pick('建议先点最接近的那个。', 'Start with the closest one.') }}
              </p>
              <p v-else-if="currentUIControl?.type === 'text_input'">
                {{ pick('这一轮是文本补充，直接说明你的想法即可。', 'This round takes free text, so just describe your idea.') }}
              </p>
              <p v-else>
                {{ pick('当前还在等待下一步指令，聊天区会继续给出引导。', 'Waiting for the next instruction; the chat area keeps guiding you.') }}
              </p>
            </div>
          </section>
        </aside>
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onMounted, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useNovelStore } from '@/stores/novel'
import type { UIControl, Blueprint } from '@/api/novel'
import ChatBubble from '@/components/ChatBubble.vue'
import ConversationInput from '@/components/ConversationInput.vue'
import InspirationLoading from '@/components/InspirationLoading.vue'

const BlueprintConfirmation = defineAsyncComponent(() => import('@/components/BlueprintConfirmation.vue'))
const BlueprintDisplay = defineAsyncComponent(() => import('@/components/BlueprintDisplay.vue'))
import { globalAlert } from '@/composables/useAlert'
import { useLocale } from '@/composables/useLocale'

interface ChatMessage {
  content: string
  type: 'user' | 'ai'
}

const router = useRouter()
const route = useRoute()
const novelStore = useNovelStore()
const { pick } = useLocale()
const ACTIVE_INSPIRATION_PROJECT_KEY = 'xuanqiong_wenshu_active_inspiration_project_id'

const conversationStarted = ref(false)
const isInitialLoading = ref(false)
const showBlueprintConfirmation = ref(false)
const showBlueprint = ref(false)
const chatMessages = ref<ChatMessage[]>([])
const currentUIControl = ref<UIControl | null>(null)
const currentTurn = ref(0)
const completedBlueprint = ref<Blueprint | null>(null)
const confirmationMessage = ref('')
const blueprintMessage = ref('')
const chatArea = ref<HTMLElement | null>(null)
const isSavingBlueprint = ref(false)
const pendingBlueprintForceStage = ref<'novel_outline' | 'chapter_outline' | undefined>(undefined)

const syncActiveInspirationProject = (projectId?: string | null) => {
  if (typeof window === 'undefined') return
  if (projectId) {
    window.localStorage.setItem(ACTIVE_INSPIRATION_PROJECT_KEY, projectId)
    return
  }
  window.localStorage.removeItem(ACTIVE_INSPIRATION_PROJECT_KEY)
}

const resolveResumeProjectId = () => {
  const queryProjectId = typeof route.query.project_id === 'string' ? route.query.project_id : ''
  if (queryProjectId) return queryProjectId
  if (typeof window === 'undefined') return ''
  return window.localStorage.getItem(ACTIVE_INSPIRATION_PROJECT_KEY) || ''
}

const hasResumeProject = computed(() => {
  if (typeof route.query.project_id === 'string' && route.query.project_id) return false
  if (typeof window === 'undefined') return false
  return Boolean(window.localStorage.getItem(ACTIVE_INSPIRATION_PROJECT_KEY))
})

const goBack = () => {
  router.push('/')
}

const resetInspirationMode = (options?: { preserveResumeProject?: boolean }) => {
  conversationStarted.value = false
  isInitialLoading.value = false
  showBlueprintConfirmation.value = false
  showBlueprint.value = false
  chatMessages.value = []
  currentUIControl.value = null
  currentTurn.value = 0
  completedBlueprint.value = null
  confirmationMessage.value = ''
  blueprintMessage.value = ''
  isSavingBlueprint.value = false
  pendingBlueprintForceStage.value = undefined
  novelStore.setCurrentProject(null)
  novelStore.currentConversationState.value = {}
  if (!options?.preserveResumeProject) {
    syncActiveInspirationProject(null)
  }
}

const exitConversation = async () => {
  const confirmed = await globalAlert.showConfirm(
    pick('确定要退出灵感模式吗？当前会保留，你之后可以继续接着聊。', 'Leave inspiration mode? The session is kept, so you can pick the conversation up later.'),
    pick('退出确认', 'Confirm exit'),
  )
  if (confirmed) {
    resetInspirationMode({ preserveResumeProject: true })
    router.push('/')
  }
}

const handleRestart = async () => {
  const confirmed = await globalAlert.showConfirm(
    pick('确定要重新开始吗？当前对话内容将会丢失。', 'Start over? The current conversation will be lost.'),
    pick('重新开始确认', 'Confirm restart'),
  )
  if (confirmed) {
    syncActiveInspirationProject(null)
    await startConversation()
  }
}

const backToConversation = () => {
  showBlueprintConfirmation.value = false
  showBlueprint.value = false
}

const currentControlOptionCount = computed(() => currentUIControl.value?.options?.length || 0)

const currentStageKey = computed(() => {
  if (!conversationStarted.value) return 'start'
  if (isInitialLoading.value) return 'conversation'
  if (showBlueprintConfirmation.value) return 'confirm'
  if (showBlueprint.value) return 'blueprint'
  return 'conversation'
})

const stageItems = computed(() => {
  const order = ['start', 'conversation', 'confirm', 'blueprint']
  const activeIndex = order.indexOf(currentStageKey.value)
  return [
    { key: 'start', index: 1, title: pick('开始想法', 'Start an idea'), desc: pick('先给出一个可以继续追问的核心灵感。', 'Give one core idea worth digging into.'), done: activeIndex > 0 },
    { key: 'conversation', index: 2, title: pick('逐轮收束', 'Narrow it down'), desc: pick('按轮次澄清题材、人物和冲突。', 'Clarify genre, characters, and conflict turn by turn.'), done: activeIndex > 1 },
    { key: 'confirm', index: 3, title: pick('确认蓝图', 'Confirm the blueprint'), desc: pick('确认当前方向是否已经足够稳定。', 'Check whether the current direction is stable enough.'), done: activeIndex > 2 },
    { key: 'blueprint', index: 4, title: pick('进入开写', 'Start writing'), desc: pick('蓝图生成后直接切到写作台。', 'Jump straight to the writing desk once the blueprint is ready.'), done: false },
  ]
})

const stageTitle = computed(() => ({
  start: pick('先把灵感说出来，再让系统逐步收束', 'Say the idea out loud first, then let the system narrow it down'),
  conversation: pick('当前处于对话收束阶段', 'Currently narrowing things down through conversation'),
  confirm: pick('当前处于蓝图确认阶段', 'Currently confirming the blueprint'),
  blueprint: pick('蓝图已生成，可以决定是否直接开写', 'The blueprint is ready — decide whether to start writing'),
}[currentStageKey.value]))

const stageDescription = computed(() => ({
  start: pick(
    '这一屏只负责起步。先说最小想法，不需要一次把世界观、章节和角色全填完。',
    'This screen is only about getting started. Share the smallest idea — no need to fill in world, chapters, and cast at once.'
  ),
  conversation: pick(
    '聊天区会持续给出当前轮次的引导。优先完成当前问题，再进入下一轮。',
    'The chat keeps offering guidance for the current turn. Finish the current question before moving on.'
  ),
  confirm: pick(
    '先确认方向，再决定是否开始生成蓝图。这里不建议继续堆叠新信息。',
    'Confirm the direction before generating the blueprint. This is not the place to pile on new information.'
  ),
  blueprint: pick(
    '蓝图已可阅读。确认后会直接进入写作台，重做则会回到蓝图确认流程。',
    'The blueprint is readable. Confirming takes you to the writing desk; redoing returns you to the confirmation step.'
  ),
}[currentStageKey.value]))

const isInteractionLocked = computed(() => isSavingBlueprint.value)
const inspirationProgressVisible = computed(() => isInitialLoading.value || novelStore.isLoading || isSavingBlueprint.value)
const inspirationProgressPercent = computed(() => {
  if (isSavingBlueprint.value) return 92
  if (showBlueprint.value) return 86
  if (showBlueprintConfirmation.value) return 74
  if (isInitialLoading.value) return 24
  if (novelStore.isLoading) return Math.min(68, 34 + currentTurn.value * 8)
  if (conversationStarted.value) return Math.min(66, 28 + currentTurn.value * 10)
  return 0
})
const inspirationProgressTitle = computed(() => {
  if (isSavingBlueprint.value) {
    return hasCompleteChapterOutline(completedBlueprint.value)
      ? pick('正在保存蓝图并准备进入写作台', 'Saving the blueprint and preparing the writing desk')
      : pick('正在基于小说总大纲生成章节大纲', 'Generating the chapter outline from the novel outline')
  }
  if (showBlueprint.value) return pick('蓝图已生成，等待确认', 'The blueprint is ready and awaiting confirmation')
  if (showBlueprintConfirmation.value) return pick('正在收束蓝图方向', 'Narrowing down the blueprint direction')
  if (isInitialLoading.value) return pick('正在初始化灵感对话', 'Starting the inspiration conversation')
  if (novelStore.isLoading) return pick(
    `正在处理第 ${Math.max(1, currentTurn.value)} 轮灵感输入`,
    `Processing inspiration turn ${Math.max(1, currentTurn.value)}`
  )
  return pick('灵感对话进行中', 'Inspiration conversation in progress')
})
const inspirationProgressDescription = computed(() => {
  if (isSavingBlueprint.value) {
    return hasCompleteChapterOutline(completedBlueprint.value)
      ? pick(
          '蓝图写入项目后会直接跳转到小说写作界面。',
          'Once the blueprint is written to the project, you go straight to the writing view.'
        )
      : pick(
          '系统正在调用正式生成链，把小说总大纲细化成章节大纲。',
          'The full generation chain is running, expanding the novel outline into a chapter outline.'
        )
  }
  if (showBlueprint.value) return pick(
    '可以先通读蓝图，再决定确认进入写作或重新生成。',
    'Read the blueprint first, then decide whether to start writing or regenerate.'
  )
  if (showBlueprintConfirmation.value) return pick(
    '当前重点是确认方向，不要继续堆叠过多新信息。',
    'The focus right now is confirming the direction, not adding more information.'
  )
  if (isInitialLoading.value) return pick(
    '系统正在创建灵感项目并准备首轮引导。',
    'Creating the inspiration project and preparing the first prompt.'
  )
  if (novelStore.isLoading) return pick(
    '本轮消息已发出，正在等待 AI 返回下一步引导。',
    'This turn has been sent — waiting for the AI to return the next prompt.'
  )
  return pick(
    '你可以继续补充想法，系统会逐步把它收束成蓝图。',
    'Keep adding to the idea and the system will gradually narrow it into a blueprint.'
  )
})

const showReturnToConversation = computed(() => (showBlueprintConfirmation.value || showBlueprint.value) && !showBlueprint.value)
const showSoftRestart = computed(() => conversationStarted.value && !showBlueprint.value)

const controlModeLabel = computed(() => {
  if (!conversationStarted.value) return pick('准备开始', 'Ready to start')
  if (showBlueprintConfirmation.value) return pick('蓝图确认', 'Blueprint confirmation')
  if (showBlueprint.value) return pick('蓝图展示', 'Blueprint preview')
  if (isInitialLoading.value) return pick('启动中', 'Starting')
  if (currentUIControl.value?.type === 'single_choice') return pick('单选推进', 'Single choice')
  if (currentUIControl.value?.type === 'multi_choice') return pick('多选组合', 'Multiple choice')
  if (currentUIControl.value?.type === 'text_input') return pick('文本补充', 'Free text')
  return pick('等待下一步', 'Waiting for the next step')
})

const conversationStateLabel = computed(() => {
  if (!conversationStarted.value) return pick('未开始', 'Not started')
  if (isInitialLoading.value) return pick('正在初始化', 'Initialising')
  if (showBlueprintConfirmation.value) return pick('待确认蓝图', 'Blueprint pending confirmation')
  if (showBlueprint.value) return pick('蓝图已生成', 'Blueprint ready')
  return pick('对话进行中', 'Conversation in progress')
})

const currentControlTitle = computed(() => {
  if (!conversationStarted.value) return pick(
    '先开始对话，再逐轮收束成蓝图。',
    'Start the conversation first, then narrow it into a blueprint turn by turn.'
  )
  if (!currentUIControl.value) return pick('AI 还在整理下一步引导。', 'The AI is still preparing the next prompt.')
  if (currentUIControl.value.type === 'single_choice') {
    return pick(
      `单选模式 · ${currentControlOptionCount.value} 个候选`,
      `Single choice · ${currentControlOptionCount.value} options`
    )
  }
  if (currentUIControl.value.type === 'multi_choice') {
    return pick(
      `多选模式 · ${currentControlOptionCount.value} 个候选`,
      `Multiple choice · ${currentControlOptionCount.value} options`
    )
  }
  return pick('文本补充模式 · 直接输入你的想法', 'Free text · type your idea directly')
})

const currentControlHint = computed(() => {
  if (!conversationStarted.value) return pick(
    '点击“开始灵感对话”后，系统会先创建一个灵感项目并发起首轮对话。',
    'Click “Start inspiration chat” and the system creates an inspiration project, then opens the first turn.'
  )
  if (currentUIControl.value?.type === 'single_choice') {
    return currentUIControl.value.placeholder || pick(
      '可以先点最接近的选项，再补一句说明。',
      'Pick the closest option first, then add a sentence of context.'
    )
  }
  if (currentUIControl.value?.type === 'multi_choice') {
    return currentUIControl.value.placeholder || pick(
      '可以先组合几个最接近的方向，再补一句你真正想保留的核心。',
      'Combine the closest directions first, then say which core you really want to keep.'
    )
  }
  if (currentUIControl.value?.type === 'text_input') {
    return currentUIControl.value.placeholder || pick(
      '直接补充你的想法，越短越好。',
      'Add to the idea directly — shorter is better.'
    )
  }
  return pick('当前回合会继续给出下一步引导。', 'This turn will keep offering the next prompt.')
})

const stateDescription = computed(() => {
  if (!conversationStarted.value) return pick(
    '先不要追求完整结构，把最想保留的核心印象说出来即可。',
    'Do not chase a complete structure yet — just name the core impression you want to keep.'
  )
  if (showBlueprintConfirmation.value) return pick(
    '系统已经收敛到可以生成蓝图的程度，现在先确认关键方向。',
    'Things have converged enough to generate a blueprint — confirm the key direction first.'
  )
  if (showBlueprint.value) return pick(
    '蓝图已经生成，可以确认后进入写作工作台，或者重新生成。',
    'The blueprint is ready: confirm it to enter the writing desk, or regenerate.'
  )
  if (isInitialLoading.value) return pick(
    '系统正在创建灵感项目并准备首轮引导。',
    'Creating the inspiration project and preparing the first prompt.'
  )
  return pick(
    '每一轮只解决一个小问题，避免在这一屏里堆满不必要的选项。',
    'Each turn solves one small question, so this screen never fills up with needless options.'
  )
})


const createFallbackTextControl = (placeholder = pick(
  '继续补充你的想法，或直接说明你想调整的方向。',
  'Keep adding to your idea, or say what you want to adjust.'
)): UIControl => ({
  type: 'text_input',
  placeholder,
})

const isVisibleConversationItem = (item: any) => {
  return (item.role === 'user' || item.role === 'assistant') && item.metadata?.type !== 'blueprint_generation_job'
}

const parseAssistantPayload = (content: string) => {
  try {
    const parsed = JSON.parse(content)
    return {
      aiMessage: typeof parsed.ai_message === 'string' ? parsed.ai_message : content,
      isComplete: Boolean(parsed.is_complete),
      uiControl: parsed.ui_control as UIControl | null | undefined,
      conversationState: parsed.conversation_state && typeof parsed.conversation_state === 'object'
        ? parsed.conversation_state
        : {},
    }
  } catch {
    return {
      aiMessage: content,
      isComplete: false,
      uiControl: null,
      conversationState: {},
    }
  }
}

const isRecord = (value: unknown): value is Record<string, unknown> => {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

const readPositiveInt = (value: unknown): number | null => {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : null
}

const resolveLengthContractSeedCount = (targetCount: number, seedCount?: number | null): number => {
  let defaultSeed = 60
  if (targetCount <= 60) defaultSeed = targetCount
  else if (targetCount <= 120) defaultSeed = 60
  else if (targetCount <= 300) defaultSeed = 80
  else if (targetCount <= 600) defaultSeed = 100
  else defaultSeed = 120
  return Math.min(targetCount, Math.max(defaultSeed, seedCount || 0))
}

const resolveChapterOutlineExpectedCount = (blueprint: Blueprint | null | undefined) => {
  if (!blueprint) return 0
  const worldSetting = isRecord(blueprint.world_setting) ? blueprint.world_setting : {}
  const systemBlueprint = isRecord(worldSetting.system_blueprint) ? worldSetting.system_blueprint : {}
  const candidates = [
    isRecord((blueprint as Record<string, unknown>).length_contract)
      ? (blueprint as Record<string, unknown>).length_contract
      : null,
    isRecord(worldSetting.length_contract) ? worldSetting.length_contract : null,
    isRecord(systemBlueprint.length_contract) ? systemBlueprint.length_contract : null,
  ].filter(isRecord)

  for (const candidate of candidates) {
    const seedCount = readPositiveInt(candidate.chapter_outline_seed_count)
    const targetCount = readPositiveInt(candidate.target_chapter_count)
    if (seedCount && targetCount) return resolveLengthContractSeedCount(targetCount, seedCount)
    if (seedCount) return seedCount
    if (targetCount) return resolveLengthContractSeedCount(targetCount)
  }

  return Array.isArray(blueprint.chapter_outline) ? blueprint.chapter_outline.length : 0
}

const hasNovelOutline = (blueprint: Blueprint | null | undefined) => {
  return Boolean(blueprint && Array.isArray(blueprint.novel_outline) && blueprint.novel_outline.length > 0)
}

const hasCompleteChapterOutline = (blueprint: Blueprint | null | undefined) => {
  const expectedCount = resolveChapterOutlineExpectedCount(blueprint)
  if (!blueprint || !Array.isArray(blueprint.chapter_outline) || expectedCount <= 0 || blueprint.chapter_outline.length < expectedCount) {
    return false
  }

  const chapterNumbers = blueprint.chapter_outline
    .map((chapter, index) => Number((chapter as { chapter_number?: unknown }).chapter_number) || index + 1)
    .sort((left, right) => left - right)

  return chapterNumbers.length >= expectedCount
    && chapterNumbers.slice(0, expectedCount).every((chapterNumber, index) => chapterNumber === index + 1)
}

const hasUsableBlueprint = (blueprint: Blueprint | null | undefined) => {
  if (!blueprint) return false
  const hasChapters = hasCompleteChapterOutline(blueprint)
  const hasTitle = typeof blueprint.title === 'string' && blueprint.title.trim().length > 0
  const summary = (blueprint.one_sentence_summary || blueprint.full_synopsis || (blueprint as any).summary || '').trim()
  return hasChapters && (hasTitle || summary.length > 0)
}

const scrollToBottom = async () => {
  await nextTick()
  if (chatArea.value) {
    chatArea.value.scrollTop = chatArea.value.scrollHeight
  }
}

const restoreConversation = async (projectId: string) => {
  try {
    syncActiveInspirationProject(projectId)
    await novelStore.loadProject(projectId)
    const project = novelStore.currentProject
    if (!project) {
      conversationStarted.value = true
      currentUIControl.value = createFallbackTextControl(pick(
        '旧灵感项目暂未加载到历史记录，可以继续输入补充或重新发起。',
        'This older inspiration project has no history loaded yet — keep typing or start a new run.'
      ))
      return
    }

    const visibleHistory = (project.conversation_history || []).filter(isVisibleConversationItem)
    conversationStarted.value = true
    chatMessages.value = visibleHistory
      .map((item): ChatMessage | null => {
        if (item.role === 'user') {
          try {
            const userInput = JSON.parse(item.content)
            return { content: userInput.value, type: 'user' }
          } catch {
            return { content: item.content, type: 'user' }
          }
        }

        const payload = parseAssistantPayload(item.content)
        return { content: payload.aiMessage, type: 'ai' }
      })
      .filter((msg): msg is ChatMessage => msg !== null && msg.content !== null)

    const visibleAssistantHistory = visibleHistory.filter((item) => item.role === 'assistant')
    const lastAssistantMessage = visibleAssistantHistory.at(-1)?.content
    if (lastAssistantMessage) {
      const payload = parseAssistantPayload(lastAssistantMessage)
      const hasPersistedBlueprint = hasUsableBlueprint(project.blueprint)
      const hasPersistedNovelOutline = hasNovelOutline(project.blueprint)

      if (hasPersistedBlueprint) {
        novelStore.currentConversationState.value = payload.conversationState || {}
        completedBlueprint.value = project.blueprint || null
        blueprintMessage.value = payload.aiMessage || pick(
          '章节大纲已恢复，你可以继续确认后进入写作。',
          'The chapter outline is restored — confirm it to move on to writing.'
        )
        showBlueprintConfirmation.value = false
        showBlueprint.value = true
        currentUIControl.value = null
      } else if (project.blueprint && hasPersistedNovelOutline) {
        novelStore.currentConversationState.value = payload.conversationState || {}
        completedBlueprint.value = project.blueprint || null
        blueprintMessage.value = pick(
          '已恢复到小说总大纲阶段。请先检查总纲，再使用软件功能继续生成章节大纲。',
          'Restored to the novel-outline stage. Review the outline first, then generate the chapter outline.'
        )
        showBlueprintConfirmation.value = false
        showBlueprint.value = true
        currentUIControl.value = null
      } else if (project.blueprint && !hasPersistedBlueprint) {
        novelStore.currentConversationState.value = payload.conversationState || {}
        completedBlueprint.value = null
        confirmationMessage.value = pick(
          '已恢复到蓝图确认阶段。请先生成小说总大纲，再继续正式生成章节大纲。',
          'Restored to the blueprint confirmation stage. Generate the novel outline first, then the chapter outline.'
        )
        showBlueprintConfirmation.value = true
        showBlueprint.value = false
        currentUIControl.value = null
      } else if (payload.isComplete) {
        novelStore.currentConversationState.value = payload.conversationState || {}
        confirmationMessage.value = payload.aiMessage
        showBlueprintConfirmation.value = true
        showBlueprint.value = false
        currentUIControl.value = null
      } else {
        novelStore.currentConversationState.value = payload.conversationState || {}
        currentUIControl.value = payload.uiControl || createFallbackTextControl(pick(
          '继续续写这个灵感：补充主角、冲突、世界规则或你想改掉的方向。',
          'Keep building on this idea: add the lead, the conflict, the world rules, or what you want to change.'
        ))
      }
    } else {
      currentUIControl.value = createFallbackTextControl(pick(
        '这个旧灵感还没有可恢复的 AI 引导，直接输入一句新想法继续推进。',
        'This older idea has no AI prompt to restore — type a fresh thought to keep going.'
      ))
    }

    currentTurn.value = visibleAssistantHistory.length
    await scrollToBottom()
  } catch (error) {
    console.error('恢复对话失败:', error)
    globalAlert.showError(
      pick(
        `无法恢复对话: ${error instanceof Error ? error.message : '未知错误'}`,
        `Could not restore the conversation: ${error instanceof Error ? error.message : 'unknown error'}`
      ),
      pick('加载失败', 'Load failed')
    )
    resetInspirationMode()
  }
}

const startConversation = async () => {
  resetInspirationMode()
  conversationStarted.value = true
  isInitialLoading.value = true

  try {
    // 标题与初始想法会持久化到后端，这里取创建时刻的界面语言，之后不随语言切换而变
    const project = await novelStore.createProject(
      pick('未命名灵感', 'Untitled idea'),
      pick('开始灵感模式', 'Start inspiration mode')
    )
    syncActiveInspirationProject(project?.id || novelStore.currentProject?.id || null)
    await handleUserInput(null)
  } catch (error) {
    console.error('启动灵感模式失败:', error)
    globalAlert.showError(
      pick(
        `无法开始灵感模式: ${error instanceof Error ? error.message : '未知错误'}`,
        `Could not start inspiration mode: ${error instanceof Error ? error.message : 'unknown error'}`
      ),
      pick('启动失败', 'Start failed')
    )
    resetInspirationMode()
  }
}

const resumeLastConversation = async () => {
  const projectId = resolveResumeProjectId()
  if (!projectId) {
    globalAlert.showError(
      pick(
        '没有可继续的灵感会话，请先开始一轮新的灵感对话。',
        'There is no inspiration session to resume — start a new round first.'
      ),
      pick('无法继续', 'Cannot resume')
    )
    return
  }

  resetInspirationMode({ preserveResumeProject: true })
  await restoreConversation(projectId)
}

const handleUserInput = async (userInput: any) => {
  const wasInitialLoading = isInitialLoading.value
  const previousMessages = [...chatMessages.value]
  const previousTurn = currentTurn.value
  const previousUIControl = currentUIControl.value
  const previousConversationState = { ...novelStore.currentConversationState.value }
  const previousConversationStarted = conversationStarted.value
  const previousBlueprintConfirmation = showBlueprintConfirmation.value
  const previousBlueprint = showBlueprint.value

  try {
    if (userInput && userInput.value) {
      chatMessages.value.push({ content: userInput.value, type: 'user' })
      await scrollToBottom()
    }

    const response = await novelStore.sendConversation(userInput)

    if (isInitialLoading.value) {
      isInitialLoading.value = false
    }

    chatMessages.value.push({
      content: response.ai_message,
      type: 'ai'
    })
    currentTurn.value += 1

    await scrollToBottom()

    if (response.is_complete) {
      confirmationMessage.value = response.ai_message
      showBlueprintConfirmation.value = true
      showBlueprint.value = false
    } else {
      currentUIControl.value = response.ui_control || createFallbackTextControl(pick(
        'AI 没有返回结构化按钮，你可以继续用文本补充设定或要求它换方向。',
        'The AI returned no structured buttons — keep adding details in text or ask it to change direction.'
      ))
    }
  } catch (error) {
    console.error('对话失败:', error)
    if (isInitialLoading.value) {
      isInitialLoading.value = false
    }
    globalAlert.showError(
      pick(
        `抱歉，与 AI 连接时遇到问题：${error instanceof Error ? error.message : '未知错误'}`,
        `Sorry, something went wrong talking to the AI: ${error instanceof Error ? error.message : 'unknown error'}`
      ),
      pick('通信失败', 'Connection failed')
    )

    if (wasInitialLoading) {
      resetInspirationMode()
      return
    }

    chatMessages.value = previousMessages
    currentTurn.value = previousTurn
    currentUIControl.value = previousUIControl
    conversationStarted.value = previousConversationStarted
    showBlueprintConfirmation.value = previousBlueprintConfirmation
    showBlueprint.value = previousBlueprint
    novelStore.currentConversationState.value = previousConversationState
  }
}

const handleBlueprintGenerated = (response: any) => {
  completedBlueprint.value = response.blueprint
  blueprintMessage.value = response.ai_message
  pendingBlueprintForceStage.value = undefined
  showBlueprintConfirmation.value = false
  showBlueprint.value = true
}

const waitForBlueprintGenerationResult = async () => {
  const readJobError = (error: unknown, fallback?: string) => {
    if (typeof error === 'string') return error
    if (error && typeof error === 'object') {
      const record = error as { message?: unknown; detail?: unknown }
      if (typeof record.message === 'string' && record.message.trim()) return record.message
      if (typeof record.detail === 'string' && record.detail.trim()) return record.detail
    }
    return fallback || pick('生成失败', 'Generation failed')
  }

  for (let attempt = 0; attempt < 450; attempt += 1) {
    const status = await novelStore.getBlueprintGenerationStatus()
    if (status.status === 'successful' && status.blueprint) {
      return {
        blueprint: status.blueprint,
        ai_message: status.ai_message || pick('生成完成，请继续下一步。', 'Generation finished — move on to the next step.'),
      }
    }
    if (status.status === 'failed') {
      throw new Error(readJobError(status.error, status.progress_message || pick('生成失败', 'Generation failed')))
    }
    if (status.status === 'cancelled') {
      throw new Error(status.progress_message || pick('生成已取消', 'Generation cancelled'))
    }
    await new Promise((resolve) => window.setTimeout(resolve, 2000))
  }
  throw new Error(pick('等待生成结果超时，请稍后重试。', 'Timed out waiting for the generation result — please retry shortly.'))
}

const handleRegenerateBlueprint = () => {
  pendingBlueprintForceStage.value = 'novel_outline'
  confirmationMessage.value = pick(
    '你正在重生小说总大纲。确认后会覆盖当前总纲与其下游章节大纲，并重新生成一版更完整的新结构。',
    'You are regenerating the novel outline. Confirming overwrites the current outline and its downstream chapter outline, then rebuilds a fuller structure.'
  )
  showBlueprint.value = false
  showBlueprintConfirmation.value = true
}

const handleConfirmBlueprint = async () => {
  if (isSavingBlueprint.value) return

  if (!completedBlueprint.value) {
    globalAlert.showError(
      pick('缺少蓝图数据，请先完成生成。', 'Blueprint data is missing — finish generating it first.'),
      pick('进入失败', 'Cannot continue')
    )
    return
  }

  const targetProjectId = novelStore.currentProject?.id || resolveResumeProjectId()
  if (!targetProjectId) {
    globalAlert.showError(
      pick('当前灵感项目不存在，请从工作区重新打开。', 'This inspiration project no longer exists — reopen it from the workspace.'),
      pick('进入失败', 'Cannot continue')
    )
    return
  }

  const readyForWriting = hasCompleteChapterOutline(completedBlueprint.value)

  isSavingBlueprint.value = true
  try {
    if (!readyForWriting) {
      pendingBlueprintForceStage.value = 'chapter_outline'
      confirmationMessage.value = pick(
        '正在基于当前小说总大纲继续生成章节大纲。页面会直接切换到后台任务视图，显示实时进度与日志。',
        'Generating the chapter outline from the current novel outline. The page switches to the background job view with live progress and logs.'
      )
      showBlueprint.value = false
      showBlueprintConfirmation.value = true
      return
    }

    syncActiveInspirationProject(null)
    await router.push(`/novel/${targetProjectId}`)
  } catch (error) {
    console.error(readyForWriting ? 'Enter writing desk failed:' : '生成章节大纲失败:', error)
    const reason = error instanceof Error ? error.message : pick('未知错误', 'unknown error')
    globalAlert.showError(
      readyForWriting
        ? pick(`进入写作台失败：${reason}`, `Could not open the writing desk: ${reason}`)
        : pick(`生成章节大纲失败：${reason}`, `Chapter outline generation failed: ${reason}`),
      readyForWriting ? pick('进入失败', 'Cannot continue') : pick('生成失败', 'Generation failed'),
    )
  } finally {
    isSavingBlueprint.value = false
  }
}

onMounted(() => {
  const projectId = resolveResumeProjectId()
  if (projectId) {
    restoreConversation(projectId)
  } else {
    resetInspirationMode()
  }
})
</script>

<style scoped>
.inspiration-shell {
  color: var(--xq-ink);
}

.inspiration-topbar {
  border-bottom: 1px solid var(--xq-border);
  background: rgba(255, 250, 240, 0.78);
  backdrop-filter: blur(18px);
}

.inspiration-back-btn,
.inspiration-ghost-btn,
.inspiration-mini-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  border: 1px solid var(--xq-border);
  background: rgba(255, 250, 240, 0.88);
  color: var(--xq-ink);
  font-family: var(--xq-font-sans);
  font-weight: 700;
  transition: transform var(--xq-fast), box-shadow var(--xq-fast), border-color var(--xq-fast), background var(--xq-fast);
}

.inspiration-back-btn {
  min-height: 3rem;
  padding: 0 1rem;
  border-radius: var(--xq-radius-sm);
  box-shadow: 0 12px 28px rgba(80, 54, 24, 0.08);
}

.inspiration-back-btn:hover,
.inspiration-ghost-btn:hover,
.inspiration-mini-btn:hover,
.inspiration-primary-btn:hover {
  transform: translateY(-1px);
}

.inspiration-back-icon {
  font-size: 1.1rem;
  line-height: 1;
}

.inspiration-kicker {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  border-radius: var(--xq-radius-pill);
  background: rgba(214, 169, 79, 0.14);
  color: var(--xq-gold-deep);
  padding: 0.42rem 0.82rem;
  font-size: 0.78rem;
  font-weight: 900;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.inspiration-ghost-btn,
.inspiration-mini-btn {
  min-height: 2.5rem;
  padding: 0 0.9rem;
  border-radius: var(--xq-radius-sm);
  font-size: 0.92rem;
}

.inspiration-ghost-btn:disabled,
.inspiration-mini-btn:disabled,
.inspiration-primary-btn:disabled {
  cursor: not-allowed;
  opacity: 0.58;
  box-shadow: none;
}

.inspiration-ghost-btn--resume {
  min-height: 3rem;
  border-color: rgba(214, 169, 79, 0.28);
  background: rgba(255, 250, 240, 0.94);
  color: var(--xq-gold-deep);
}

.inspiration-primary-btn {
  display: inline-flex;
  min-height: 3.25rem;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: var(--xq-radius-sm);
  background: linear-gradient(135deg, var(--xq-gold-deep), var(--xq-gold));
  color: #fffaf0;
  font-size: 1rem;
  font-weight: 800;
  box-shadow: 0 16px 34px rgba(154, 106, 34, 0.22);
  transition: transform var(--xq-fast), box-shadow var(--xq-fast), opacity var(--xq-fast);
}

.inspiration-panel {
  border: 1px solid var(--xq-border);
  border-radius: var(--xq-radius-lg);
  background: rgba(255, 250, 240, 0.84);
  box-shadow: var(--xq-shadow-paper);
  backdrop-filter: blur(16px);
}

.inspiration-chat-panel {
  min-height: 0;
}


.inspiration-chat-layout {
  grid-template-columns: minmax(0, 1fr);
}

.inspiration-input-scroll {
  max-height: none;
  overflow: visible;
  padding-right: 0;
}

.inspiration-rail {
  max-height: calc(100vh - 11.5rem);
}

@media (min-width: 1180px) {
  .inspiration-chat-layout {
    grid-template-columns: minmax(0, 5.2fr) minmax(220px, 0.8fr);
  }
}

@media (min-width: 1440px) {
  .inspiration-chat-layout {
    grid-template-columns: minmax(0, 5.8fr) minmax(240px, 0.78fr);
  }
}

@media (max-width: 1179px) {
  .inspiration-rail {
    display: none;
  }
}

.inspiration-stage-strip,
.inspiration-rail-card {
  background:
    linear-gradient(145deg, rgba(255, 250, 240, 0.92), rgba(247, 239, 224, 0.82));
}

.inspiration-progress-card {
  display: grid;
  gap: 0.45rem;
  padding: 0.85rem 1rem;
  border-radius: var(--xq-radius-sm);
  border: 1px solid rgba(214, 169, 79, 0.22);
  background: rgba(255, 250, 240, 0.72);
}

.inspiration-progress-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  font-size: 0.86rem;
  font-weight: 800;
  color: var(--xq-ink);
}

.inspiration-progress-card__desc {
  margin: 0;
  font-size: 0.82rem;
  line-height: 1.55;
  color: var(--xq-ink-muted);
}

.inspiration-progress-track {
  width: 100%;
  height: 0.45rem;
  overflow: hidden;
  border-radius: var(--xq-radius-pill);
  background: rgba(93, 70, 43, 0.12);
}

.inspiration-progress-bar {
  height: 100%;
  border-radius: var(--xq-radius-pill);
  background: linear-gradient(90deg, var(--xq-gold-deep), var(--xq-gold), var(--xq-jade));
  transition: width var(--xq-normal);
}

.inspiration-stage-strip__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.65rem;
}

.inspiration-stage-list {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.65rem;
}

.inspiration-stage-item,
.inspiration-step,
.inspiration-metric {
  border-radius: var(--xq-radius-sm);
  border: 1px solid var(--xq-border);
  background: rgba(255, 250, 240, 0.58);
}

.inspiration-stage-item {
  display: flex;
  gap: 0.75rem;
  padding: 0.8rem;
}

.inspiration-stage-item--active {
  border-color: rgba(214, 169, 79, 0.42);
  background: rgba(214, 169, 79, 0.12);
  box-shadow: 0 12px 28px rgba(154, 106, 34, 0.1);
}

.inspiration-stage-item--done {
  border-color: rgba(61, 143, 125, 0.24);
}

.inspiration-stage-item__dot,
.inspiration-step__index {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  border-radius: var(--xq-radius-pill);
  font-weight: 800;
}

.inspiration-stage-item__dot {
  width: 1.9rem;
  height: 1.9rem;
  background: rgba(93, 70, 43, 0.1);
  color: var(--xq-ink-muted);
  font-size: 0.8rem;
}

.inspiration-stage-item--active .inspiration-stage-item__dot {
  background: linear-gradient(135deg, var(--xq-gold-deep), var(--xq-gold));
  color: #fffaf0;
}

.inspiration-stage-item--done .inspiration-stage-item__dot {
  background: rgba(61, 143, 125, 0.14);
  color: var(--xq-jade);
}

.inspiration-stage-item__title,
.inspiration-step__title {
  color: var(--xq-ink);
  font-size: 0.95rem;
  font-weight: 800;
}

.inspiration-stage-item__desc,
.inspiration-step__desc {
  margin-top: 0.25rem;
  color: var(--xq-ink-muted);
  font-size: 0.84rem;
  line-height: 1.55;
}

.inspiration-landing-panel {
  background:
    radial-gradient(circle at top right, rgba(214, 169, 79, 0.14), transparent 28%),
    radial-gradient(circle at bottom left, rgba(61, 143, 125, 0.12), transparent 24%),
    rgba(255, 250, 240, 0.82);
}

.inspiration-step {
  display: flex;
  gap: 0.75rem;
  padding: 0.9rem;
}

.inspiration-step__index {
  width: 2.15rem;
  height: 2.15rem;
  background: linear-gradient(135deg, var(--xq-gold-deep), var(--xq-gold));
  color: #fffaf0;
  font-size: 0.9rem;
}

.inspiration-pill {
  display: inline-flex;
  align-items: center;
  min-height: 1.9rem;
  border-radius: var(--xq-radius-pill);
  padding: 0 0.75rem;
  font-size: 0.78rem;
  font-weight: 800;
}

.inspiration-pill--blue {
  background: rgba(107, 124, 255, 0.11);
  color: var(--xq-celestial);
}

.inspiration-pill--teal {
  background: rgba(61, 143, 125, 0.12);
  color: var(--xq-jade);
}

.inspiration-pill--slate {
  background: rgba(93, 70, 43, 0.08);
  color: var(--xq-ink-muted);
}

.inspiration-chat-area {
  scrollbar-gutter: stable;
  background:
    linear-gradient(180deg, rgba(247, 239, 224, 0.78), rgba(255, 250, 240, 0.9));
}

.inspiration-input-shell {
  position: sticky;
  bottom: 0;
}

.inspiration-metric {
  padding: 0.9rem;
}

.inspiration-metric__label {
  display: block;
  color: var(--xq-ink-muted);
  font-size: 0.76rem;
  margin-bottom: 0.35rem;
}

.inspiration-metric__value {
  display: block;
  color: var(--xq-ink);
  font-family: var(--xq-font-serif);
  font-size: 1.15rem;
  line-height: 1.1;
}

@media (max-width: 1024px) {
  .inspiration-panel {
    border-radius: var(--xq-radius-md);
  }

  .inspiration-stage-list {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .inspiration-topbar .inspiration-back-btn {
    min-height: 2.75rem;
  }

  .inspiration-stage-list {
    grid-template-columns: 1fr;
  }
}
</style>
