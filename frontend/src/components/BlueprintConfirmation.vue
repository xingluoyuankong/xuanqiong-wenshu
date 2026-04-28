<!-- AIMETA P=蓝图确认_蓝图确认对话框|R=确认操作|NR=不含编辑功能|E=component:BlueprintConfirmation|X=internal|A=确认对话框|D=vue|S=dom|RD=./README.ai -->
<template>
  <section class="flex min-h-0 flex-col overflow-hidden rounded-[32px] border border-slate-200/80 bg-white/95 shadow-[0_24px_90px_-40px_rgba(15,23,42,0.34)] backdrop-blur-xl">
    <header class="shrink-0 border-b border-white/10 bg-[radial-gradient(circle_at_top_right,rgba(34,211,238,0.24),transparent_35%),linear-gradient(135deg,#0f172a_0%,#1e1b4b_55%,#155e75_100%)] px-5 py-5 text-white sm:px-6 lg:px-8">
      <div class="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
        <div class="min-w-0 space-y-4">
          <div class="flex flex-wrap items-center gap-2 text-xs font-medium">
            <span class="rounded-full border border-white/10 bg-white/12 px-3 py-1 text-white">蓝图确认台</span>
            <span
              class="rounded-full border px-3 py-1"
              :class="isGenerating ? 'border-cyan-300/30 bg-cyan-400/15 text-cyan-100' : 'border-emerald-300/30 bg-emerald-400/15 text-emerald-100'"
            >
              {{ isGenerating ? '生成中' : '待确认' }}
            </span>
            <span class="rounded-full border border-white/10 bg-white/10 px-3 py-1 text-slate-100">
              预计 {{ maxTime }} 秒内完成
            </span>
            <span v-if="isGenerating" class="rounded-full border border-white/10 bg-white/10 px-3 py-1 text-slate-100">
              剩余约 {{ timeRemaining }} 秒
            </span>
          </div>

          <div class="space-y-3">
            <h2 class="text-2xl font-semibold tracking-tight sm:text-3xl">把这段对话收成一份能直接开写的蓝图</h2>
            <p class="max-w-3xl text-sm leading-6 text-slate-200 sm:text-base">
              这里不继续编辑，只负责最后确认。确认后会进入蓝图生成，生成完成后直接切到蓝图展示页。
            </p>
          </div>
        </div>

        <div class="flex flex-wrap items-center gap-3 xl:justify-end">
          <button
            type="button"
            class="inline-flex items-center justify-center rounded-2xl border border-white/15 bg-white/10 px-4 py-3 text-sm font-semibold text-white transition-all hover:-translate-y-0.5 hover:bg-white/15 disabled:cursor-not-allowed disabled:opacity-70"
            :disabled="isGenerating"
            @click="emit('back')"
          >
            返回对话补充
          </button>
          <button
            v-if="isGenerating"
            type="button"
            class="inline-flex items-center justify-center rounded-2xl bg-white px-5 py-3 text-sm font-semibold text-slate-950 shadow-lg shadow-cyan-950/20"
            disabled
          >
            正在生成蓝图
          </button>
          <button
            v-else
            type="button"
            class="inline-flex items-center justify-center rounded-2xl bg-white px-5 py-3 text-sm font-semibold text-slate-950 shadow-lg shadow-cyan-950/20 transition-all hover:-translate-y-0.5 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-70"
            :disabled="!hasAiMessage"
            @click="generateBlueprint"
          >
            {{ hasAiMessage ? '确认方向并生成蓝图' : '等待可确认内容' }}
          </button>
        </div>
      </div>

      <div class="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div
          v-for="item in confirmationStats"
          :key="item.label"
          class="rounded-2xl border border-white/10 bg-white/10 px-4 py-3 backdrop-blur"
        >
          <p class="text-xs uppercase tracking-[0.24em] text-slate-300">{{ item.label }}</p>
          <p class="mt-1 text-lg font-semibold text-white">{{ item.value }}</p>
          <p class="mt-1 text-xs leading-5 text-slate-300">{{ item.hint }}</p>
        </div>
      </div>
    </header>

    <div class="min-h-0 flex-1 overflow-y-auto px-4 py-4 sm:px-6 lg:px-8">
      <div class="grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(320px,360px)]">
        <main class="space-y-4">
          <section class="rounded-[28px] border border-slate-200/80 bg-white/95 p-5 shadow-[0_12px_40px_-28px_rgba(15,23,42,0.24)]">
            <div class="flex flex-wrap items-center justify-between gap-3">
              <div class="min-w-0">
                <p class="text-xs font-medium uppercase tracking-[0.24em] text-indigo-600">收束结果</p>
                <h3 class="mt-2 text-lg font-semibold text-slate-950">当前对话已经整理出的关键方向</h3>
                <p class="mt-2 text-sm leading-6 text-slate-600">
                  确认后会直接进入蓝图生成，不再继续堆消息。先看这份总结是否已经足够清楚。
                </p>
              </div>
              <span class="inline-flex rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-600">
                {{ hasAiMessage ? '可直接生成' : '等待补充' }}
              </span>
            </div>

            <div class="mt-4 rounded-[24px] border border-slate-200/80 bg-slate-50/80 p-5">
              <div class="blueprint-markdown text-slate-700" v-html="renderedAiMessage"></div>
            </div>
          </section>

          <section
            v-if="isGenerating"
            class="rounded-[28px] border border-slate-200/80 bg-white p-5 shadow-[0_12px_40px_-28px_rgba(15,23,42,0.24)]"
          >
            <div class="flex flex-col gap-5 sm:flex-row sm:items-center">
              <div class="relative mx-auto h-24 w-24 shrink-0 sm:mx-0">
                <div class="absolute inset-0 rounded-full border-4 border-slate-100"></div>
                <div
                  class="absolute inset-0 rounded-full border-4 border-transparent border-t-indigo-500 border-r-cyan-400"
                  :class="progress < 100 ? 'animate-spin' : ''"
                ></div>
                <div
                  class="absolute inset-3 rounded-full transition-colors duration-500"
                  :class="progress >= 100 ? 'bg-emerald-500/15' : 'bg-indigo-500/10'"
                ></div>
                <div class="absolute inset-6 flex items-center justify-center rounded-full text-sm font-semibold text-slate-900">
                  {{ Math.round(progress) }}%
                </div>
              </div>

              <div class="min-w-0 flex-1 space-y-3">
                <div>
                  <h3 class="text-xl font-semibold text-slate-950">{{ loadingText }}</h3>
                  <p class="mt-1 text-sm leading-6 text-slate-600">{{ progressHint }}</p>
                </div>

                <div class="h-2 overflow-hidden rounded-full bg-slate-100">
                  <div
                    class="h-full rounded-full bg-gradient-to-r from-indigo-500 via-cyan-500 to-emerald-500 transition-all duration-500"
                    :style="{ width: `${progress}%` }"
                  ></div>
                </div>

                <div class="flex flex-wrap gap-2 text-xs font-medium text-slate-500">
                  <span class="rounded-full border border-slate-200 bg-slate-50 px-3 py-1">收束对话</span>
                  <span class="rounded-full border border-slate-200 bg-slate-50 px-3 py-1">整理蓝图骨架</span>
                  <span class="rounded-full border border-slate-200 bg-slate-50 px-3 py-1">准备切换展示</span>
                </div>
              </div>
            </div>
          </section>

          <section
            v-else
            class="rounded-[28px] border border-slate-200/80 bg-gradient-to-br from-indigo-50 via-white to-cyan-50 p-5 shadow-[0_12px_40px_-28px_rgba(15,23,42,0.24)]"
          >
            <div class="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
              <div class="space-y-2">
                <p class="text-sm font-semibold text-slate-950">确认后会发生什么</p>
                <p class="max-w-2xl text-sm leading-6 text-slate-600">
                  这一步只保留一个主动作：确认当前方向并生成蓝图。若还想补充内容，请回到对话区继续收束，再回来确认。
                </p>
              </div>
              <div class="rounded-2xl border border-white/70 bg-white/80 px-4 py-3 text-sm leading-6 text-slate-600 shadow-sm">
                <p class="font-semibold text-slate-900">生成完成后</p>
                <p class="mt-1">系统会自动切到蓝图展示页，再由你决定是否直接进入开写。</p>
              </div>
            </div>
          </section>
        </main>

        <aside class="space-y-4">
          <section class="rounded-[28px] border border-slate-200/80 bg-slate-950 p-5 text-white shadow-[0_16px_48px_-30px_rgba(15,23,42,0.55)]">
            <p class="text-xs uppercase tracking-[0.28em] text-slate-400">确认前再看一眼</p>
            <h3 class="mt-2 text-lg font-semibold">生成之前，先过这三件事</h3>
            <div class="mt-4 space-y-3 text-sm leading-6 text-slate-300">
              <p v-for="item in preflightItems" :key="item.title" class="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
                <span class="block font-semibold text-white">{{ item.title }}</span>
                <span class="mt-1 block">{{ item.desc }}</span>
              </p>
            </div>
          </section>

          <section class="rounded-[28px] border border-slate-200/80 bg-white p-5 shadow-[0_12px_40px_-28px_rgba(15,23,42,0.24)]">
            <p class="text-xs font-medium uppercase tracking-[0.24em] text-slate-400">生成流程</p>
            <div class="mt-4 space-y-3">
              <div
                v-for="(step, index) in flowSteps"
                :key="step.title"
                class="flex gap-3 rounded-2xl border border-slate-200 bg-slate-50/80 px-4 py-3"
              >
                <span class="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-xs font-semibold text-indigo-700">
                  {{ index + 1 }}
                </span>
                <div class="min-w-0">
                  <p class="text-sm font-semibold text-slate-900">{{ step.title }}</p>
                  <p class="mt-1 text-sm leading-6 text-slate-600">{{ step.desc }}</p>
                </div>
              </div>
            </div>
          </section>
        </aside>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { useNovelStore } from '@/stores/novel'
import { globalAlert } from '@/composables/useAlert'
import { renderSafeMarkdown } from '@/utils/safeMarkdown'

interface Props {
  aiMessage: string
}

const props = defineProps<Props>()

const emit = defineEmits<{
  blueprintGenerated: [response: any]
  back: []
}>()

const novelStore = useNovelStore()
const isGenerating = ref(false)
const progress = ref(0)
const timeElapsed = ref(0)
const maxTime = 180
let progressTimer: ReturnType<typeof setInterval> | null = null
let timeoutTimer: ReturnType<typeof setTimeout> | null = null

const preflightItems = [
  { title: '先确认方向', desc: '这一步只收束思路，不做编辑。方向一旦清楚，生成后的蓝图会更稳。' },
  { title: '再确认结构', desc: '蓝图会带着章节、角色和世界观一起进入后续写作流程。' },
  { title: '最后再开写', desc: '如果还有犹豫，先返回对话补一句，比生成后再反复改更省时间。' },
]

const flowSteps = [
  { title: '收束方向', desc: '把当前对话整理成蓝图可执行的信息骨架。' },
  { title: '生成蓝图', desc: '补齐世界、角色、章节和整体节奏。' },
  { title: '切换展示', desc: '完成后自动进入蓝图展示页，继续下一步创作。' },
]

const confirmationStats = computed(() => [
  {
    label: '当前状态',
    value: isGenerating.value ? '生成中' : (hasAiMessage.value ? '待确认' : '待补充'),
    hint: isGenerating.value ? '请保持页面打开' : (hasAiMessage.value ? '确认后立刻开始生成' : '需要先补充可确认内容'),
  },
  {
    label: '当前动作',
    value: isGenerating.value ? '生成蓝图' : '确认方向',
    hint: '这一屏不再继续编辑蓝图内容',
  },
  {
    label: '剩余时间',
    value: isGenerating.value ? `${timeRemaining.value}s` : '—',
    hint: '超时后会提示重试',
  },
  {
    label: '下一步',
    value: '进入蓝图展示',
    hint: '完成后再决定是否直接开写',
  },
])

const hasAiMessage = computed(() => {
  return optionalText(props.aiMessage).length > 0
})

const renderedAiMessage = ref('<p class="text-sm leading-6 text-slate-500">暂无可确认内容，请返回对话补充后再试。</p>')

const renderAiMessage = (raw: string) => {
  if (!raw) {
    renderedAiMessage.value = '<p class="text-sm leading-6 text-slate-500">暂无可确认内容，请返回对话补充后再试。</p>'
    return
  }
  renderedAiMessage.value = renderSafeMarkdown(raw)
}

watch(
  () => optionalText(props.aiMessage),
  (value) => {
    renderAiMessage(value)
  },
  { immediate: true }
)

const loadingText = computed(() => {
  if (progress.value >= 100) {
    return '蓝图已完成，正在准备切换页面'
  }

  if (progress.value >= 75) {
    return '正在整理蓝图结构'
  }

  if (progress.value >= 40) {
    return '正在压缩对话要点'
  }

  return '正在收集蓝图核心信息'
})

const progressHint = computed(() => {
  if (progress.value >= 100) return '生成完成后会自动切换到蓝图展示页。'
  if (progress.value >= 75) return '系统正在把对话信息整理成可写的蓝图结构。'
  if (progress.value >= 40) return '当前阶段会保留关键信息，同时去掉噪音内容。'
  return '先把最关键的方向收束起来，再进入蓝图生成。'
})

const timeRemaining = computed(() => Math.max(0, Math.ceil(maxTime - timeElapsed.value)))

const clearTimers = () => {
  if (progressTimer) {
    clearInterval(progressTimer)
    progressTimer = null
  }

  if (timeoutTimer) {
    clearTimeout(timeoutTimer)
    timeoutTimer = null
  }
}

const generateBlueprint = async () => {
  if (isGenerating.value) return

  isGenerating.value = true
  progress.value = 0
  timeElapsed.value = 0

  progressTimer = setInterval(() => {
    timeElapsed.value += 0.1

    const normalizedTime = timeElapsed.value / maxTime
    if (normalizedTime < 0.7) {
      progress.value = Math.min(80, (normalizedTime / 0.7) * 80)
    } else {
      const remainingProgress = (normalizedTime - 0.7) / 0.3
      progress.value = Math.min(95, 80 + remainingProgress * 15)
    }
  }, 100)

  timeoutTimer = setTimeout(() => {
    clearTimers()
    isGenerating.value = false
    globalAlert.showError('生成超时，请稍后重试。如果问题持续存在，请检查网络连接。', '生成超时')
  }, maxTime * 1000)

  try {
    const response = await novelStore.generateBlueprint()

    if (progressTimer) {
      clearInterval(progressTimer)
      progressTimer = null
    }

    progress.value = 100
    await new Promise((resolve) => setTimeout(resolve, 600))

    clearTimers()
    isGenerating.value = false
    emit('blueprintGenerated', response)
  } catch (error) {
    console.error('生成蓝图失败:', error)
    clearTimers()
    isGenerating.value = false
    globalAlert.showError(
      `生成蓝图失败: ${error instanceof Error ? error.message : '未知错误'}`,
      '生成失败',
    )
  }
}

const optionalText = (value: unknown): string => {
  if (typeof value === 'string') {
    return value.trim()
  }

  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }

  return ''
}

onUnmounted(() => {
  clearTimers()
})
</script>

<style scoped>
.blueprint-markdown :deep(p) {
  margin: 0 0 0.85rem;
  line-height: 1.85;
}

.blueprint-markdown :deep(p:last-child) {
  margin-bottom: 0;
}

.blueprint-markdown :deep(ul),
.blueprint-markdown :deep(ol) {
  margin: 0.85rem 0 0.85rem 1.25rem;
  padding: 0;
}

.blueprint-markdown :deep(li) {
  margin: 0.35rem 0;
  line-height: 1.75;
}

.blueprint-markdown :deep(strong) {
  color: rgb(15 23 42);
  font-weight: 700;
}

.blueprint-markdown :deep(a) {
  color: rgb(79 70 229);
  text-decoration: none;
}

.blueprint-markdown :deep(a:hover) {
  text-decoration: underline;
}
</style>
