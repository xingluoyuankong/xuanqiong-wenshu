<template>
  <div class="inspiration-shell min-h-screen text-slate-900">
    <header class="inspiration-topbar sticky top-0 z-30">
      <div class="mx-auto flex w-full max-w-7xl items-center gap-4 px-4 py-4 sm:px-6 lg:px-8">
        <button class="inspiration-back-btn" type="button" @click="goBack">
          <span class="inspiration-back-icon">&larr;</span>
          <span>{{ '\u8fd4\u56de' }}</span>
        </button>

        <div class="min-w-0 flex-1">
          <p class="inspiration-kicker">{{ '\u7075\u611f\u6a21\u5f0f' }}</p>
          <h1 class="mt-1 truncate text-2xl font-semibold tracking-tight text-slate-900 sm:text-3xl">
            {{ '\u5bf9\u8bdd\u5f0f\u521b\u4f5c\u5de5\u4f5c\u53f0' }}
          </h1>
          <p class="mt-2 max-w-3xl text-sm leading-6 text-slate-600 sm:text-base">
            {{ '\u5148\u7528\u804a\u5929\u628a\u7075\u611f\u8bf4\u51fa\u6765\uff0c\u518d\u9010\u8f6e\u6536\u675f\u6210\u53ef\u843d\u5730\u7684\u5c0f\u8bf4\u84dd\u56fe\uff0c\u51cf\u5c11\u4e00\u6b21\u6027\u5806\u6ee1\u8868\u5355\u7684\u538b\u8feb\u611f\u3002' }}
          </p>
        </div>

        <div class="hidden items-center gap-2 md:flex">
          <button class="inspiration-ghost-btn" type="button" :disabled="isInteractionLocked" @click="handleRestart">
            {{ '\u91cd\u542f' }}
          </button>
          <button class="inspiration-ghost-btn" type="button" :disabled="isInteractionLocked" @click="exitConversation">
            {{ '\u9000\u51fa' }}
          </button>
        </div>
      </div>
    </header>

    <main class="mx-auto flex min-h-[calc(100vh-88px)] w-full max-w-[1480px] flex-col gap-4 px-4 py-4 sm:px-5 lg:px-6 xl:px-8">
      <section class="inspiration-panel inspiration-stage-strip px-4 py-3 sm:px-4 sm:py-4">
        <div class="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p class="inspiration-kicker">当前阶段</p>
            <h2 class="mt-2 text-lg font-semibold text-slate-950">{{ stageTitle }}</h2>
            <p class="mt-2 text-sm leading-6 text-slate-600">{{ stageDescription }}</p>
          </div>
          <div class="inspiration-stage-strip__actions">
            <button v-if="showReturnToConversation" class="inspiration-mini-btn" type="button" :disabled="isInteractionLocked" @click="backToConversation">
              返回对话
            </button>
            <button v-if="showSoftRestart" class="inspiration-mini-btn" type="button" :disabled="isInteractionLocked" @click="handleRestart">
              重启本轮
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
              <span class="inspiration-pill inspiration-pill--blue">先说一个想法</span>
              <span class="inspiration-pill inspiration-pill--teal">逐轮收束</span>
              <span class="inspiration-pill inspiration-pill--slate">不必一次定完</span>
            </div>

            <h2 class="mt-6 max-w-3xl text-3xl font-semibold tracking-tight text-slate-950 sm:text-4xl lg:text-5xl">
              把灵感先说出来，系统再帮你把它收成故事骨架。
            </h2>

            <p class="mt-5 max-w-2xl text-base leading-8 text-slate-600 sm:text-lg">
              这里不是“表单页”，而是一条对话式创作流水线。你只需要给出碎片化想法，AI 会逐轮收束成蓝图，再继续进入写作工作台。
            </p>
          </div>

          <div class="mt-8 grid gap-3 sm:grid-cols-3">
            <div class="inspiration-step">
              <span class="inspiration-step__index">1</span>
              <div>
                <p class="inspiration-step__title">开始对话</p>
                <p class="inspiration-step__desc">先让系统拿到你最初的想法。</p>
              </div>
            </div>
            <div class="inspiration-step">
              <span class="inspiration-step__index">2</span>
              <div>
                <p class="inspiration-step__title">逐轮收束</p>
                <p class="inspiration-step__desc">每一轮只解决一个小问题。</p>
              </div>
            </div>
            <div class="inspiration-step">
              <span class="inspiration-step__index">3</span>
              <div>
                <p class="inspiration-step__title">生成蓝图</p>
                <p class="inspiration-step__desc">确认后直接进入工作台。</p>
              </div>
            </div>
          </div>
        </article>

        <aside class="inspiration-panel flex min-h-0 flex-col gap-3 p-4 sm:p-5">
          <div class="rounded-[24px] border border-slate-200 bg-slate-950 px-5 py-5 text-white shadow-[0_20px_60px_-30px_rgba(15,23,42,0.55)]">
            <p class="text-xs uppercase tracking-[0.28em] text-slate-400">当前入口</p>
            <h3 class="mt-2 text-xl font-semibold">灵感工作流</h3>
            <p class="mt-3 text-sm leading-6 text-slate-300">
              适合还没有大纲，或者只想先把一个模糊想法快速变成可写结构的时候。
            </p>
          </div>

          <div class="rounded-[24px] border border-slate-200 bg-white/90 p-5 shadow-[0_18px_48px_-32px_rgba(15,23,42,0.35)]">
            <p class="text-sm font-semibold text-slate-900">这条线的顺序</p>
            <ol class="mt-4 space-y-3 text-sm leading-6 text-slate-600">
              <li class="flex items-start gap-3">
                <span class="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-xs font-semibold text-indigo-700">1</span>
                <span>创建一个临时灵感项目，保留上下文。</span>
              </li>
              <li class="flex items-start gap-3">
                <span class="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-cyan-100 text-xs font-semibold text-cyan-700">2</span>
                <span>通过对话逐步澄清题材、人物和冲突。</span>
              </li>
              <li class="flex items-start gap-3">
                <span class="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-xs font-semibold text-emerald-700">3</span>
                <span>确认蓝图后进入章节写作工作台。</span>
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
              继续上次灵感
            </button>
            <button
              type="button"
              class="inspiration-primary-btn text-base"
              :disabled="novelStore.isLoading"
              @click="startConversation"
            >
              {{ novelStore.isLoading ? '正在准备...' : '开始灵感对话' }}
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
            <p class="inspiration-kicker">蓝图阶段</p>
            <h2 class="mt-1 text-xl font-semibold text-slate-950 sm:text-2xl">
              {{ showBlueprintConfirmation ? '确认蓝图' : '查看蓝图' }}
            </h2>
          </div>
          <button
            v-if="showBlueprintConfirmation"
            class="inspiration-ghost-btn"
            type="button"
            :disabled="isInteractionLocked"
            @click="backToConversation"
          >
            返回对话
          </button>
        </div>

        <div class="inspiration-panel flex-1 min-h-0 overflow-y-auto p-4 sm:p-6">
          <div class="mx-auto flex min-h-full w-full max-w-7xl items-start justify-center py-2">
            <div class="w-full">
              <BlueprintConfirmation
                v-if="showBlueprintConfirmation"
                :ai-message="confirmationMessage"
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
        class="grid flex-1 min-h-0 gap-4 lg:grid-cols-[minmax(0,1.65fr)_minmax(300px,360px)] xl:grid-cols-[minmax(0,1.75fr)_minmax(320px,380px)]"
      >
        <div class="inspiration-panel inspiration-chat-panel flex min-h-0 flex-col overflow-hidden">
          <div class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200/80 px-4 py-4 sm:px-5">
            <div class="flex flex-wrap items-center gap-2">
              <span class="inspiration-pill inspiration-pill--blue">{{ conversationStateLabel }}</span>
              <span v-if="currentTurn > 0" class="inspiration-pill inspiration-pill--slate">
                第 {{ currentTurn }} 轮
              </span>
              <span class="inspiration-pill inspiration-pill--teal">
                {{ chatMessages.length }} 条消息
              </span>
            </div>

            <div class="flex items-center gap-2">
              <button class="inspiration-mini-btn" type="button" @click="handleRestart">
                重启
              </button>
              <button class="inspiration-mini-btn" type="button" @click="exitConversation">
                退出
              </button>
            </div>
          </div>

          <div class="border-b border-slate-200/70 bg-slate-50/80 px-4 py-3 sm:px-5">
            <p class="text-sm font-medium text-slate-900">{{ currentControlTitle }}</p>
            <p class="mt-1 text-sm leading-6 text-slate-600">
              {{ currentControlHint }}
            </p>
          </div>

          <div ref="chatArea" class="inspiration-chat-area flex-1 min-h-[360px] space-y-3 overflow-y-auto px-4 py-4 sm:px-5 sm:py-4 lg:min-h-[440px]">
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
                <p class="text-sm font-semibold text-slate-900">输入区</p>
                <p class="mt-1 text-xs leading-5 text-slate-500">
                  先给出最小可用想法即可，后续再逐轮补充。
                </p>
              </div>
              <span class="inspiration-pill inspiration-pill--slate">支持单选和文本补充</span>
            </div>

            <div class="max-h-[38vh] overflow-y-auto pr-1">
              <ConversationInput
                :ui-control="currentUIControl"
                :loading="novelStore.isLoading"
                @submit="handleUserInput"
              />
            </div>
          </div>
        </div>

        <aside class="flex min-h-0 flex-col gap-4 overflow-y-auto pr-1">
          <section class="inspiration-panel inspiration-rail-card p-5">
            <p class="inspiration-kicker">当前状态</p>
            <h3 class="mt-2 text-xl font-semibold text-slate-950">{{ conversationStateLabel }}</h3>
            <p class="mt-3 text-sm leading-6 text-slate-600">
              {{ stateDescription }}
            </p>

            <div class="mt-5 grid grid-cols-2 gap-3">
              <div class="inspiration-metric">
                <span class="inspiration-metric__label">当前轮次</span>
                <strong class="inspiration-metric__value">{{ currentTurn }}</strong>
              </div>
              <div class="inspiration-metric">
                <span class="inspiration-metric__label">控制类型</span>
                <strong class="inspiration-metric__value">{{ controlModeLabel }}</strong>
              </div>
              <div class="inspiration-metric">
                <span class="inspiration-metric__label">消息数量</span>
                <strong class="inspiration-metric__value">{{ chatMessages.length }}</strong>
              </div>
              <div class="inspiration-metric">
                <span class="inspiration-metric__label">选项数量</span>
                <strong class="inspiration-metric__value">{{ currentControlOptionCount }}</strong>
              </div>
            </div>
          </section>

          <section class="inspiration-panel inspiration-rail-card p-5">
            <p class="inspiration-kicker">操作建议</p>
            <ul class="mt-4 space-y-3 text-sm leading-6 text-slate-600">
              <li class="flex gap-3">
                <span class="mt-1 h-2 w-2 rounded-full bg-indigo-500"></span>
                <span>先看 AI 这轮提示，再只做必要补充，不要一次性把整本书都写完。</span>
              </li>
              <li class="flex gap-3">
                <span class="mt-1 h-2 w-2 rounded-full bg-cyan-500"></span>
                <span>单选时直接选最接近的一项，再用文字把偏差补齐。</span>
              </li>
              <li class="flex gap-3">
                <span class="mt-1 h-2 w-2 rounded-full bg-emerald-500"></span>
                <span>输入区在底部固定分层，不用在一大坨选项里来回找入口。</span>
              </li>
            </ul>
          </section>

          <section class="inspiration-panel inspiration-rail-card p-5">
            <p class="inspiration-kicker">工作流摘要</p>
            <div class="mt-4 space-y-3 text-sm leading-6 text-slate-600">
              <p>如果对话结束，会先进入蓝图确认，再保存到工作台。</p>
              <p v-if="currentUIControl?.type === 'single_choice'">
                这一轮有 {{ currentControlOptionCount }} 个候选选项，建议先点最接近的那个。
              </p>
              <p v-else-if="currentUIControl?.type === 'text_input'">
                这一轮是文本补充，直接说明你的想法即可。
              </p>
              <p v-else>
                当前还在等待下一步指令，聊天区会继续给出引导。
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

interface ChatMessage {
  content: string
  type: 'user' | 'ai'
}

const router = useRouter()
const route = useRoute()
const novelStore = useNovelStore()
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
  novelStore.setCurrentProject(null)
  novelStore.currentConversationState.value = {}
  if (!options?.preserveResumeProject) {
    syncActiveInspirationProject(null)
  }
}

const exitConversation = async () => {
  const confirmed = await globalAlert.showConfirm('确定要退出灵感模式吗？当前会保留，你之后可以继续接着聊。', '退出确认')
  if (confirmed) {
    resetInspirationMode({ preserveResumeProject: true })
    router.push('/')
  }
}

const handleRestart = async () => {
  const confirmed = await globalAlert.showConfirm('确定要重新开始吗？当前对话内容将会丢失。', '重新开始确认')
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
    { key: 'start', index: 1, title: '\u5f00\u59cb\u60f3\u6cd5', desc: '\u5148\u7ed9\u51fa\u4e00\u4e2a\u53ef\u4ee5\u7ee7\u7eed\u8ffd\u95ee\u7684\u6838\u5fc3\u7075\u611f\u3002', done: activeIndex > 0 },
    { key: 'conversation', index: 2, title: '\u9010\u8f6e\u6536\u675f', desc: '\u6309\u8f6e\u6b21\u6f84\u6e05\u9898\u6750\u3001\u4eba\u7269\u548c\u51b2\u7a81\u3002', done: activeIndex > 1 },
    { key: 'confirm', index: 3, title: '\u786e\u8ba4\u84dd\u56fe', desc: '\u786e\u8ba4\u5f53\u524d\u65b9\u5411\u662f\u5426\u5df2\u7ecf\u8db3\u591f\u7a33\u5b9a\u3002', done: activeIndex > 2 },
    { key: 'blueprint', index: 4, title: '\u8fdb\u5165\u5f00\u5199', desc: '\u84dd\u56fe\u751f\u6210\u540e\u76f4\u63a5\u5207\u5230\u5199\u4f5c\u53f0\u3002', done: false },
  ]
})

const stageTitle = computed(() => ({
  start: '\u5148\u628a\u7075\u611f\u8bf4\u51fa\u6765\uff0c\u518d\u8ba9\u7cfb\u7edf\u9010\u6b65\u6536\u675f',
  conversation: '\u5f53\u524d\u5904\u4e8e\u5bf9\u8bdd\u6536\u675f\u9636\u6bb5',
  confirm: '\u5f53\u524d\u5904\u4e8e\u84dd\u56fe\u786e\u8ba4\u9636\u6bb5',
  blueprint: '\u84dd\u56fe\u5df2\u751f\u6210\uff0c\u53ef\u4ee5\u51b3\u5b9a\u662f\u5426\u76f4\u63a5\u5f00\u5199',
}[currentStageKey.value]))

const stageDescription = computed(() => ({
  start: '\u8fd9\u4e00\u5c4f\u53ea\u8d1f\u8d23\u8d77\u6b65\u3002\u5148\u8bf4\u6700\u5c0f\u60f3\u6cd5\uff0c\u4e0d\u9700\u8981\u4e00\u6b21\u628a\u4e16\u754c\u89c2\u3001\u7ae0\u8282\u548c\u89d2\u8272\u5168\u586b\u5b8c\u3002',
  conversation: '\u804a\u5929\u533a\u4f1a\u6301\u7eed\u7ed9\u51fa\u5f53\u524d\u8f6e\u6b21\u7684\u5f15\u5bfc\u3002\u4f18\u5148\u5b8c\u6210\u5f53\u524d\u95ee\u9898\uff0c\u518d\u8fdb\u5165\u4e0b\u4e00\u8f6e\u3002',
  confirm: '\u5148\u786e\u8ba4\u65b9\u5411\uff0c\u518d\u51b3\u5b9a\u662f\u5426\u5f00\u59cb\u751f\u6210\u84dd\u56fe\u3002\u8fd9\u91cc\u4e0d\u5efa\u8bae\u7ee7\u7eed\u5806\u53e0\u65b0\u4fe1\u606f\u3002',
  blueprint: '\u84dd\u56fe\u5df2\u53ef\u9605\u8bfb\u3002\u786e\u8ba4\u540e\u4f1a\u76f4\u63a5\u8fdb\u5165\u5199\u4f5c\u53f0\uff0c\u91cd\u505a\u5219\u4f1a\u56de\u5230\u84dd\u56fe\u786e\u8ba4\u6d41\u7a0b\u3002',
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
  if (isSavingBlueprint.value) return '\u6b63\u5728\u4fdd\u5b58\u84dd\u56fe\u5e76\u51c6\u5907\u8fdb\u5165\u5199\u4f5c\u53f0'
  if (showBlueprint.value) return '\u84dd\u56fe\u5df2\u751f\u6210\uff0c\u7b49\u5f85\u786e\u8ba4'
  if (showBlueprintConfirmation.value) return '\u6b63\u5728\u6536\u675f\u84dd\u56fe\u65b9\u5411'
  if (isInitialLoading.value) return '\u6b63\u5728\u521d\u59cb\u5316\u7075\u611f\u5bf9\u8bdd'
  if (novelStore.isLoading) return `\u6b63\u5728\u5904\u7406\u7b2c ${Math.max(1, currentTurn.value)} \u8f6e\u7075\u611f\u8f93\u5165`
  return '\u7075\u611f\u5bf9\u8bdd\u8fdb\u884c\u4e2d'
})
const inspirationProgressDescription = computed(() => {
  if (isSavingBlueprint.value) return '\u84dd\u56fe\u5199\u5165\u9879\u76ee\u540e\u4f1a\u76f4\u63a5\u8df3\u8f6c\u5230\u5c0f\u8bf4\u5199\u4f5c\u754c\u9762\u3002'
  if (showBlueprint.value) return '\u53ef\u4ee5\u5148\u901a\u8bfb\u84dd\u56fe\uff0c\u518d\u51b3\u5b9a\u786e\u8ba4\u8fdb\u5165\u5199\u4f5c\u6216\u91cd\u65b0\u751f\u6210\u3002'
  if (showBlueprintConfirmation.value) return '\u5f53\u524d\u91cd\u70b9\u662f\u786e\u8ba4\u65b9\u5411\uff0c\u4e0d\u8981\u7ee7\u7eed\u5806\u53e0\u8fc7\u591a\u65b0\u4fe1\u606f\u3002'
  if (isInitialLoading.value) return '\u7cfb\u7edf\u6b63\u5728\u521b\u5efa\u7075\u611f\u9879\u76ee\u5e76\u51c6\u5907\u9996\u8f6e\u5f15\u5bfc\u3002'
  if (novelStore.isLoading) return '\u672c\u8f6e\u6d88\u606f\u5df2\u53d1\u51fa\uff0c\u6b63\u5728\u7b49\u5f85 AI \u8fd4\u56de\u4e0b\u4e00\u6b65\u5f15\u5bfc\u3002'
  return '\u4f60\u53ef\u4ee5\u7ee7\u7eed\u8865\u5145\u60f3\u6cd5\uff0c\u7cfb\u7edf\u4f1a\u9010\u6b65\u628a\u5b83\u6536\u675f\u6210\u84dd\u56fe\u3002'
})

const showReturnToConversation = computed(() => (showBlueprintConfirmation.value || showBlueprint.value) && !showBlueprint.value)
const showSoftRestart = computed(() => conversationStarted.value && !showBlueprint.value)

const controlModeLabel = computed(() => {
  if (!conversationStarted.value) return '\u51c6\u5907\u5f00\u59cb'
  if (showBlueprintConfirmation.value) return '\u84dd\u56fe\u786e\u8ba4'
  if (showBlueprint.value) return '\u84dd\u56fe\u5c55\u793a'
  if (isInitialLoading.value) return '\u542f\u52a8\u4e2d'
  if (currentUIControl.value?.type === 'single_choice') return '\u5355\u9009\u63a8\u8fdb'
  if (currentUIControl.value?.type === 'text_input') return '\u6587\u672c\u8865\u5145'
  return '\u7b49\u5f85\u4e0b\u4e00\u6b65'
})

const conversationStateLabel = computed(() => {
  if (!conversationStarted.value) return '\u672a\u5f00\u59cb'
  if (isInitialLoading.value) return '\u6b63\u5728\u521d\u59cb\u5316'
  if (showBlueprintConfirmation.value) return '\u5f85\u786e\u8ba4\u84dd\u56fe'
  if (showBlueprint.value) return '\u84dd\u56fe\u5df2\u751f\u6210'
  return '\u5bf9\u8bdd\u8fdb\u884c\u4e2d'
})

const currentControlTitle = computed(() => {
  if (!conversationStarted.value) return '\u5148\u5f00\u59cb\u5bf9\u8bdd\uff0c\u518d\u9010\u8f6e\u6536\u675f\u6210\u84dd\u56fe\u3002'
  if (!currentUIControl.value) return 'AI \u8fd8\u5728\u6574\u7406\u4e0b\u4e00\u6b65\u5f15\u5bfc\u3002'
  if (currentUIControl.value.type === 'single_choice') {
    return `\u5355\u9009\u6a21\u5f0f \u00b7 ${currentControlOptionCount.value} \u4e2a\u5019\u9009`
  }
  return '\u6587\u672c\u8865\u5145\u6a21\u5f0f \u00b7 \u76f4\u63a5\u8f93\u5165\u4f60\u7684\u60f3\u6cd5'
})

const currentControlHint = computed(() => {
  if (!conversationStarted.value) return '\u70b9\u51fb“\u5f00\u59cb\u7075\u611f\u5bf9\u8bdd”\u540e\uff0c\u7cfb\u7edf\u4f1a\u5148\u521b\u5efa\u4e00\u4e2a\u7075\u611f\u9879\u76ee\u5e76\u53d1\u8d77\u9996\u8f6e\u5bf9\u8bdd\u3002'
  if (currentUIControl.value?.type === 'single_choice') {
    return currentUIControl.value.placeholder || '\u53ef\u4ee5\u5148\u70b9\u6700\u63a5\u8fd1\u7684\u9009\u9879\uff0c\u518d\u8865\u4e00\u53e5\u8bf4\u660e\u3002'
  }
  if (currentUIControl.value?.type === 'text_input') {
    return currentUIControl.value.placeholder || '\u76f4\u63a5\u8865\u5145\u4f60\u7684\u60f3\u6cd5\uff0c\u8d8a\u77ed\u8d8a\u597d\u3002'
  }
  return '\u5f53\u524d\u56de\u5408\u4f1a\u7ee7\u7eed\u7ed9\u51fa\u4e0b\u4e00\u6b65\u5f15\u5bfc\u3002'
})

const stateDescription = computed(() => {
  if (!conversationStarted.value) return '\u5148\u4e0d\u8981\u8ffd\u6c42\u5b8c\u6574\u7ed3\u6784\uff0c\u628a\u6700\u60f3\u4fdd\u7559\u7684\u6838\u5fc3\u5370\u8c61\u8bf4\u51fa\u6765\u5373\u53ef\u3002'
  if (showBlueprintConfirmation.value) return '\u7cfb\u7edf\u5df2\u7ecf\u6536\u655b\u5230\u53ef\u4ee5\u751f\u6210\u84dd\u56fe\u7684\u7a0b\u5ea6\uff0c\u73b0\u5728\u5148\u786e\u8ba4\u5173\u952e\u65b9\u5411\u3002'
  if (showBlueprint.value) return '\u84dd\u56fe\u5df2\u7ecf\u751f\u6210\uff0c\u53ef\u4ee5\u786e\u8ba4\u540e\u8fdb\u5165\u5199\u4f5c\u5de5\u4f5c\u53f0\uff0c\u6216\u8005\u91cd\u65b0\u751f\u6210\u3002'
  if (isInitialLoading.value) return '\u7cfb\u7edf\u6b63\u5728\u521b\u5efa\u7075\u611f\u9879\u76ee\u5e76\u51c6\u5907\u9996\u8f6e\u5f15\u5bfc\u3002'
  return '\u6bcf\u4e00\u8f6e\u53ea\u89e3\u51b3\u4e00\u4e2a\u5c0f\u95ee\u9898\uff0c\u907f\u514d\u5728\u8fd9\u4e00\u5c4f\u91cc\u5806\u6ee1\u4e0d\u5fc5\u8981\u7684\u9009\u9879\u3002'
})

const parseAssistantPayload = (content: string) => {
  try {
    const parsed = JSON.parse(content)
    return {
      aiMessage: typeof parsed.ai_message === 'string' ? parsed.ai_message : content,
      isComplete: Boolean(parsed.is_complete),
      uiControl: parsed.ui_control as UIControl | null | undefined
    }
  } catch {
    return {
      aiMessage: content,
      isComplete: false,
      uiControl: null
    }
  }
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
    if (!project || !project.conversation_history) return

    conversationStarted.value = true
    chatMessages.value = project.conversation_history
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

    const lastAssistantMessage = project.conversation_history.filter((item) => item.role === 'assistant').pop()?.content
    if (lastAssistantMessage) {
      const payload = parseAssistantPayload(lastAssistantMessage)
      const hasPersistedBlueprint = Boolean(project.blueprint)

      if (hasPersistedBlueprint) {
        completedBlueprint.value = project.blueprint || null
        blueprintMessage.value = payload.aiMessage
        showBlueprintConfirmation.value = false
        showBlueprint.value = true
        currentUIControl.value = null
        syncActiveInspirationProject(null)
      } else if (payload.isComplete) {
        confirmationMessage.value = payload.aiMessage
        showBlueprintConfirmation.value = true
        showBlueprint.value = false
        currentUIControl.value = null
      } else {
        currentUIControl.value = payload.uiControl || null
      }
    }

    currentTurn.value = project.conversation_history.filter((item) => item.role === 'assistant').length
    await scrollToBottom()
  } catch (error) {
    console.error('恢复对话失败:', error)
    globalAlert.showError(`无法恢复对话: ${error instanceof Error ? error.message : '未知错误'}`, '加载失败')
    resetInspirationMode()
  }
}

const startConversation = async () => {
  resetInspirationMode()
  conversationStarted.value = true
  isInitialLoading.value = true

  try {
    const project = await novelStore.createProject('未命名灵感', '开始灵感模式')
    syncActiveInspirationProject(project?.id || novelStore.currentProject?.id || null)
    await handleUserInput(null)
  } catch (error) {
    console.error('启动灵感模式失败:', error)
    globalAlert.showError(`无法开始灵感模式: ${error instanceof Error ? error.message : '未知错误'}`, '启动失败')
    resetInspirationMode()
  }
}

const resumeLastConversation = async () => {
  const projectId = resolveResumeProjectId()
  if (!projectId) {
    globalAlert.showError('没有可继续的灵感会话，请先开始一轮新的灵感对话。', '无法继续')
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

    if (response.is_complete && response.ready_for_blueprint) {
      confirmationMessage.value = response.ai_message
      showBlueprintConfirmation.value = true
      showBlueprint.value = false
    } else if (response.is_complete) {
      await handleGenerateBlueprint()
    } else {
      currentUIControl.value = response.ui_control
    }
  } catch (error) {
    console.error('对话失败:', error)
    if (isInitialLoading.value) {
      isInitialLoading.value = false
    }
    globalAlert.showError(`抱歉，与 AI 连接时遇到问题：${error instanceof Error ? error.message : '未知错误'}`, '通信失败')

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

const handleGenerateBlueprint = async () => {
  try {
    const response = await novelStore.generateBlueprint()
    handleBlueprintGenerated(response)
  } catch (error) {
    console.error('生成蓝图失败:', error)
    globalAlert.showError(`生成蓝图失败: ${error instanceof Error ? error.message : '未知错误'}`, '生成失败')
  }
}

const handleBlueprintGenerated = (response: any) => {
  completedBlueprint.value = response.blueprint
  blueprintMessage.value = response.ai_message
  showBlueprintConfirmation.value = false
  showBlueprint.value = true
}

const handleRegenerateBlueprint = () => {
  showBlueprint.value = false
  showBlueprintConfirmation.value = true
}

const handleConfirmBlueprint = async () => {
  if (isSavingBlueprint.value) return

  if (!completedBlueprint.value) {
    globalAlert.showError('蓝图数据缺失，请重新生成后再试。', '保存失败')
    return
  }

  isSavingBlueprint.value = true
  try {
    await novelStore.saveBlueprint(completedBlueprint.value)
    syncActiveInspirationProject(null)
    if (novelStore.currentProject) {
      router.push(`/novel/${novelStore.currentProject.id}`)
    }
  } catch (error) {
    console.error('保存蓝图失败:', error)
    globalAlert.showError(`保存蓝图失败: ${error instanceof Error ? error.message : '未知错误'}`, '保存失败')
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
  min-height: 100vh;
  background:
    radial-gradient(900px 420px at 10% 0%, rgba(37, 99, 235, 0.16), transparent 56%),
    radial-gradient(700px 380px at 90% 12%, rgba(16, 185, 129, 0.14), transparent 52%),
    linear-gradient(180deg, #f8fafc 0%, #eef2ff 42%, #ecfeff 100%);
}

.inspiration-topbar {
  border-bottom: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(255, 255, 255, 0.78);
  backdrop-filter: blur(18px);
}

.inspiration-back-btn,
.inspiration-ghost-btn,
.inspiration-mini-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  background: rgba(255, 255, 255, 0.9);
  color: #0f172a;
  font-weight: 600;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease, background 0.18s ease;
}

.inspiration-back-btn {
  min-height: 48px;
  padding: 0 16px;
  border-radius: 16px;
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.06);
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
  gap: 8px;
  border-radius: 999px;
  background: rgba(15, 118, 110, 0.08);
  color: #0f766e;
  padding: 0.42rem 0.82rem;
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.inspiration-ghost-btn,
.inspiration-mini-btn {
  min-height: 40px;
  padding: 0 14px;
  border-radius: 12px;
  font-size: 0.92rem;
}

.inspiration-ghost-btn--resume {
  min-height: 48px;
  border-color: rgba(37, 99, 235, 0.22);
  background: rgba(239, 246, 255, 0.92);
  color: #1d4ed8;
}

.inspiration-primary-btn {
  display: inline-flex;
  min-height: 52px;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 16px;
  background: linear-gradient(135deg, #2563eb 0%, #14b8a6 100%);
  color: #fff;
  font-size: 1rem;
  font-weight: 700;
  box-shadow: 0 16px 34px rgba(37, 99, 235, 0.22);
  transition: transform 0.18s ease, box-shadow 0.18s ease, opacity 0.18s ease;
}

.inspiration-primary-btn:disabled {
  cursor: not-allowed;
  opacity: 0.6;
  box-shadow: none;
}

.inspiration-panel {
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 18px 52px -34px rgba(15, 23, 42, 0.26);
  backdrop-filter: blur(14px);
}

.inspiration-chat-panel {
  min-height: 0;
}

.inspiration-stage-strip {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.92), rgba(248, 250, 252, 0.9));
}

.inspiration-progress-card {
  display: grid;
  gap: 6px;
  padding: 12px 14px;
  border-radius: 16px;
  border: 1px solid rgba(37, 99, 235, 0.14);
  background: rgba(239, 246, 255, 0.88);
}

.inspiration-progress-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 0.86rem;
  font-weight: 700;
  color: #0f172a;
}

.inspiration-progress-card__desc {
  margin: 0;
  font-size: 0.8rem;
  line-height: 1.45;
  color: #475569;
}

.inspiration-progress-track {
  width: 100%;
  height: 7px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.22);
}

.inspiration-progress-bar {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #2563eb, #14b8a6);
  transition: width 0.25s ease;
}

.inspiration-stage-strip__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.inspiration-stage-list {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.inspiration-stage-item {
  display: flex;
  gap: 12px;
  padding: 13px;
  border-radius: 16px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  background: rgba(248, 250, 252, 0.9);
}

.inspiration-stage-item--active {
  border-color: rgba(37, 99, 235, 0.28);
  background: rgba(239, 246, 255, 0.9);
}

.inspiration-stage-item--done {
  border-color: rgba(16, 185, 129, 0.18);
}

.inspiration-stage-item__dot {
  display: inline-flex;
  width: 30px;
  height: 30px;
  flex: none;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: #e2e8f0;
  color: #334155;
  font-size: 0.8rem;
  font-weight: 700;
}

.inspiration-stage-item--active .inspiration-stage-item__dot {
  background: linear-gradient(135deg, #2563eb 0%, #14b8a6 100%);
  color: #fff;
}

.inspiration-stage-item--done .inspiration-stage-item__dot {
  background: rgba(16, 185, 129, 0.14);
  color: #047857;
}

.inspiration-stage-item__title {
  font-size: 0.95rem;
  font-weight: 700;
  color: #0f172a;
}

.inspiration-stage-item__desc {
  margin-top: 3px;
  font-size: 0.84rem;
  line-height: 1.5;
  color: #64748b;
}

.inspiration-landing-panel {
  background:
    radial-gradient(circle at top right, rgba(59, 130, 246, 0.08), transparent 28%),
    radial-gradient(circle at bottom left, rgba(20, 184, 166, 0.08), transparent 24%),
    rgba(255, 255, 255, 0.88);
}

.inspiration-step {
  display: flex;
  gap: 12px;
  border-radius: 18px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  background: rgba(248, 250, 252, 0.92);
  padding: 14px;
}

.inspiration-step__index {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: 999px;
  background: linear-gradient(135deg, #2563eb 0%, #14b8a6 100%);
  color: #fff;
  font-size: 0.9rem;
  font-weight: 700;
}

.inspiration-step__title {
  color: #0f172a;
  font-size: 0.94rem;
  font-weight: 700;
}

.inspiration-step__desc {
  margin-top: 3px;
  color: #64748b;
  font-size: 0.84rem;
  line-height: 1.5;
}

.inspiration-pill {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  border-radius: 999px;
  padding: 0 12px;
  font-size: 0.78rem;
  font-weight: 700;
}

.inspiration-pill--blue {
  background: rgba(37, 99, 235, 0.1);
  color: #1d4ed8;
}

.inspiration-pill--teal {
  background: rgba(20, 184, 166, 0.1);
  color: #0f766e;
}

.inspiration-pill--slate {
  background: rgba(15, 23, 42, 0.06);
  color: #334155;
}

.inspiration-chat-area {
  scrollbar-gutter: stable;
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.92), rgba(255, 255, 255, 0.96));
}

.inspiration-input-shell {
  position: sticky;
  bottom: 0;
}

.inspiration-rail-card {
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.94), rgba(255, 255, 255, 0.82)),
    rgba(255, 255, 255, 0.9);
}

.inspiration-metric {
  border-radius: 20px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  background: rgba(248, 250, 252, 0.9);
  padding: 14px;
}

.inspiration-metric__label {
  display: block;
  color: #64748b;
  font-size: 0.76rem;
  margin-bottom: 6px;
}

.inspiration-metric__value {
  display: block;
  color: #0f172a;
  font-size: 1.1rem;
  line-height: 1.1;
}

@media (max-width: 1024px) {
  .inspiration-panel {
    border-radius: 26px;
  }

  .inspiration-stage-list {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .inspiration-topbar .inspiration-back-btn {
    min-height: 44px;
  }

  .inspiration-step {
    padding: 14px;
  }

  .inspiration-stage-list {
    grid-template-columns: 1fr;
  }
}
</style>
