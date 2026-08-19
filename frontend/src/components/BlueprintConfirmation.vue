<!-- AIMETA P=蓝图确认_后台生成任务|R=蓝图确认|NR=不含蓝图编辑|E=component:BlueprintConfirmation|X=internal|A=蓝图生成|D=vue|S=dom|RD=./README.ai -->
<template>
  <section class="blueprint-confirm xq-paper-grain">
    <header class="blueprint-confirm__hero">
      <div class="blueprint-confirm__copy">
        <div class="blueprint-confirm__badges">
          <span>{{ pick('蓝图确认', 'Blueprint confirmation') }}</span>
          <span :class="isGenerating ? 'is-running' : 'is-ready'">{{ isGenerating ? pick('后台生成中', 'Generating in background') : pick('准备就绪', 'Ready') }}</span>
          <span>{{ pick(`长等待提醒 ${Math.floor(longWaitNoticeSeconds / 60)} 分钟`, `Long-wait notice after ${Math.floor(longWaitNoticeSeconds / 60)} min`) }}</span>
          <span v-if="isGenerating">{{ pick(`已等待 ${elapsedSeconds} 秒`, `Waited ${elapsedSeconds}s`) }}</span>
        </div>
        <h2>{{ heroTitle }}</h2>
        <p>{{ heroDescription }}</p>
      </div>

      <div class="blueprint-confirm__actions">
        <XqButton variant="ghost" :disabled="isGenerating" @click="emit('back')">{{ pick('返回补充', 'Back to add more') }}</XqButton>
        <XqButton v-if="isGenerating" variant="secondary" @click="cancelBlueprint">{{ pick('取消生成', 'Cancel generation') }}</XqButton>
        <XqButton v-if="isGenerating" variant="secondary" loading disabled>{{ pick('正在生成', 'Generating') }}</XqButton>
        <XqButton v-else :disabled="!hasAiMessage" @click="generateBlueprint">
          {{ hasAiMessage ? pick('确认蓝图并生成大纲', 'Confirm the blueprint and generate the outline') : pick('等待可确认内容', 'Waiting for content to confirm') }}
        </XqButton>
      </div>
    </header>

    <div class="blueprint-confirm__stats">
      <XqStatCard
        v-for="(item, index) in confirmationStats"
        :key="item.label"
        :label="item.label"
        :value="item.value"
        :hint="item.hint"
        :tone="index === 0 ? 'ink' : index === 1 ? 'gold' : index === 2 ? 'jade' : 'paper'"
      />
    </div>

    <div class="blueprint-confirm__body">
      <main class="blueprint-confirm__main">
        <XqPanel
          :title="pick('即将用于生成蓝图的确认内容', 'Content that will be used to generate the blueprint')"
          :subtitle="pick(
            '请确认下面内容已经表达了你的故事方向；如有遗漏，先返回灵感对话补充。',
            'Check that the text below captures your story direction. If anything is missing, go back to the inspiration chat first.'
          )"
        >
          <template #kicker>{{ pick('确认材料', 'Confirmation material') }}</template>
          <template #actions>
            <span class="blueprint-confirm__state">{{ hasAiMessage ? pick('可生成', 'Ready to generate') : pick('待补充', 'Needs more input') }}</span>
          </template>
          <div class="blueprint-confirm__markdown-shell">
            <div class="blueprint-markdown" v-html="renderedAiMessage"></div>
          </div>
        </XqPanel>

        <XqPanel v-if="isGenerating" class="blueprint-confirm__progress" :title="loadingText" :subtitle="progressHint">
          <template #kicker>{{ pick('后台任务', 'Background task') }}</template>
          <div class="blueprint-confirm__progress-row">
            <div class="blueprint-confirm__ring" :class="{ 'is-complete': progress >= 100 }" :style="{ '--progress': progress }">
              <span>{{ Math.round(progress) }}%</span>
            </div>
            <div class="blueprint-confirm__progress-copy">
              <div class="blueprint-confirm__track">
                <div :style="{ width: `${progress}%` }"></div>
              </div>
              <p class="blueprint-confirm__task-log-current">{{ currentProgressText }}</p>
              <div class="blueprint-confirm__chips">
                <span>{{ pick('整理访谈', 'Digest interview') }}</span>
                <span>{{ pick('世界骨架', 'World skeleton') }}</span>
                <span>{{ pick('总纲骨架', 'Master outline skeleton') }}</span>
                <span>{{ pick('总纲细化', 'Master outline detailing') }}</span>
                <span>{{ pick('章节分批', 'Chapter batching') }}</span>
                <span>{{ pick('保存结果', 'Save result') }}</span>
              </div>
              <ul v-if="progressLogs.length" class="blueprint-confirm__task-log-list">
                <li v-for="(log, index) in progressLogs" :key="`${index}-${log}`">{{ log }}</li>
              </ul>
            </div>
          </div>
        </XqPanel>

        <XqPanel v-else tone="glass" :title="nextStepTitle" :subtitle="nextStepSubtitle">
          <div class="blueprint-confirm__next">
            <strong>{{ pick('生成完成后', 'After generation finishes') }}</strong>
            <span>{{ nextStepDescription }}</span>
          </div>
        </XqPanel>
      </main>

      <aside class="blueprint-confirm__side">
        <XqPanel tone="ink" :title="pick('生成前检查清单', 'Pre-generation checklist')">
          <template #kicker>{{ pick('质量闸门', 'Quality gate') }}</template>
          <div class="blueprint-confirm__checklist">
            <article v-for="item in preflightItems" :key="item.title">
              <strong>{{ item.title }}</strong>
              <span>{{ item.desc }}</span>
            </article>
          </div>
        </XqPanel>

        <XqPanel :title="pick('蓝图生成流程', 'Blueprint generation flow')">
          <template #kicker>{{ pick('流程', 'Flow') }}</template>
          <div class="blueprint-confirm__flow">
            <article v-for="(step, index) in flowSteps" :key="step.title">
              <span>{{ index + 1 }}</span>
              <div>
                <strong>{{ step.title }}</strong>
                <p>{{ step.desc }}</p>
              </div>
            </article>
          </div>
        </XqPanel>
      </aside>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { useNovelStore } from '@/stores/novel'
import { globalAlert } from '@/composables/useAlert'
import { useLocale } from '@/composables/useLocale'
import { renderSafeMarkdown } from '@/utils/safeMarkdown'
import { XqButton, XqPanel, XqStatCard } from '@/shared/ui'
import type { BlueprintGenerationJobResponse } from '@/api/novel'

interface Props {
  aiMessage: string
  forceStage?: 'novel_outline' | 'chapter_outline'
}

const props = defineProps<Props>()
const isChapterOutlineStage = computed(() => props.forceStage === 'chapter_outline')

const emit = defineEmits<{
  blueprintGenerated: [response: any]
  back: []
}>()

const novelStore = useNovelStore()
const { pick } = useLocale()
const isGenerating = ref(false)
const progress = ref(0)
const timeElapsed = ref(0)
const currentProgressMessage = ref('')
const progressLogs = ref<string[]>([])
const longWaitNoticeSeconds = 900
let progressTimer: ReturnType<typeof setInterval> | null = null
let timeoutTimer: ReturnType<typeof setTimeout> | null = null
let cancelRequested = false
const longWaitNotified = ref(false)
const chapterOutlineBatchLabel = computed(() => pick('首批可执行章节大纲', 'the first batch of executable chapter outlines'))

// 首条后端进度日志到达前的占位文案；后端下发的 progress_message 是数据，不翻译
const currentProgressText = computed(() => currentProgressMessage.value || pick(
  '后台任务已启动，正在等待首条进度日志…',
  'The background task has started — waiting for the first progress log…'
))

const preflightItems = computed(() => [
  {
    title: pick('方向清楚', 'Clear direction'),
    desc: pick('核心卖点、主角欲望、冲突压力已经说清楚。', 'The core hook, the protagonist’s desire, and the conflict pressure are all stated.'),
  },
  {
    title: isChapterOutlineStage.value ? pick('继续拆章', 'Continue chapter breakdown') : pick('先看总纲', 'Master outline first'),
    desc: isChapterOutlineStage.value
      ? pick(
          `这一轮会基于已确认的小说总大纲，继续细化出${chapterOutlineBatchLabel.value}。`,
          `This round builds on the confirmed master outline to detail ${chapterOutlineBatchLabel.value}.`
        )
      : pick(
          '这一轮先产出全书级小说总大纲，不会直接跳到章节大纲。',
          'This round produces the book-level master outline first; it does not jump straight to chapter outlines.'
        ),
  },
  {
    title: pick('允许等待', 'Expect some waiting'),
    desc: pick('该任务已改为后台轮询；等待期间不要关闭服务。', 'This task now runs as a polled background job — keep the service running while you wait.'),
  },
])

const flowSteps = computed(() => [
  {
    title: pick('启动任务', 'Start the task'),
    desc: pick('前端只负责启动并轮询，不再让请求长时间挂起。', 'The frontend only starts and polls the job instead of holding a long-running request.'),
  },
  {
    title: isChapterOutlineStage.value ? pick('生成章节大纲', 'Generate chapter outlines') : pick('生成总纲', 'Generate the master outline'),
    desc: isChapterOutlineStage.value
      ? pick(
          '后端会复用已确认的世界骨架与小说总大纲，按批次生成并润色章节大纲。',
          'The backend reuses the confirmed world skeleton and master outline, then generates and polishes chapter outlines in batches.'
        )
      : pick(
          '后端整理访谈、补齐蓝图结构，并先生成小说总大纲。',
          'The backend digests the interview, fills in the blueprint structure, and produces the master outline first.'
        ),
  },
  {
    title: pick('继续细化', 'Keep refining'),
    desc: isChapterOutlineStage.value
      ? pick(
          `成功后回到蓝图展示页，你可以直接检查${chapterOutlineBatchLabel.value}并进入写作台。`,
          `On success you return to the blueprint page, where you can review ${chapterOutlineBatchLabel.value} and move on to the writing desk.`
        )
      : pick(
          '成功后进入蓝图展示页；你确认总纲后，再继续生成章节大纲。',
          'On success you land on the blueprint page; once you confirm the master outline, chapter outlines come next.'
        ),
  },
])

const heroTitle = computed(() => (
  isChapterOutlineStage.value
    ? pick('确认当前总纲，继续生成章节大纲。', 'Confirm the current master outline and continue with chapter outlines.')
    : pick('确认故事方向，先生成小说总大纲。', 'Confirm the story direction and generate the master outline first.')
))

const heroDescription = computed(() => (
  isChapterOutlineStage.value
    ? pick(
        `系统会基于已确认的世界骨架与小说总大纲，按蓝图长度契约继续拆解${chapterOutlineBatchLabel.value}。生成过程仍采用后台任务，可取消、可轮询、可恢复失败态。`,
        `Using the confirmed world skeleton and master outline, the system breaks down ${chapterOutlineBatchLabel.value} according to the blueprint length contract. Generation still runs as a background task: cancellable, pollable, and recoverable from failure.`
      )
    : pick(
        '系统会先基于已确认的蓝图材料生成全书级小说总大纲；章节大纲会在你确认总大纲后再继续生成。生成过程已改为后台任务，可取消、可轮询、可恢复失败态。',
        'The system first generates the book-level master outline from the confirmed blueprint material; chapter outlines follow once you confirm it. Generation now runs as a background task: cancellable, pollable, and recoverable from failure.'
      )
))

const nextStepTitle = computed(() => pick('下一步会发生什么', 'What happens next'))
const nextStepSubtitle = computed(() => (
  isChapterOutlineStage.value
    ? pick(
        '系统会启动后台任务，直接基于当前小说总大纲继续生成章节大纲。',
        'The system starts a background task that continues straight from the current master outline into chapter outlines.'
      )
    : pick(
        '确认后系统会启动后台任务，先生成小说总大纲，再进入蓝图展示页。',
        'Once confirmed, the system starts a background task, generates the master outline, and then opens the blueprint page.'
      )
))
const nextStepDescription = computed(() => (
  isChapterOutlineStage.value
    ? pick(
        `你可以直接检查${chapterOutlineBatchLabel.value}；确认无误后就进入写作台。`,
        `You can review ${chapterOutlineBatchLabel.value} directly, then head to the writing desk once everything looks right.`
      )
    : pick(
        '你可以先检查世界观、人物关系和小说总大纲，确认无误后再继续生成章节大纲。',
        'Review the world setting, character relations, and master outline first; generate chapter outlines once everything looks right.'
      )
))

const confirmationStats = computed(() => [
  {
    label: pick('当前状态', 'Current status'),
    value: isGenerating.value
      ? pick('生成中', 'Generating')
      : (hasAiMessage.value ? pick('待确认', 'Awaiting confirmation') : pick('待补充', 'Needs more input')),
    hint: isGenerating.value
      ? pick('后台任务轮询中', 'Polling the background task')
      : (hasAiMessage.value
          ? pick('确认后启动后台任务', 'Confirming starts the background task')
          : pick('先返回补充灵感内容', 'Go back and add more inspiration first')),
  },
  {
    label: pick('生成模式', 'Generation mode'),
    value: pick('后台轮询', 'Background polling'),
    hint: pick('支持取消、失败恢复和状态查询', 'Supports cancellation, failure recovery, and status queries'),
  },
  {
    label: pick('已等待', 'Waited'),
    value: isGenerating.value ? `${elapsedSeconds.value}s` : '—',
    hint: pick('长时间生成只提醒，不会自动取消后台任务', 'A long run only triggers a notice — the background task is never cancelled automatically'),
  },
  {
    label: pick('下一步', 'Next step'),
    value: pick('蓝图展示', 'Blueprint view'),
    hint: pick('检查蓝图后进入正文生成', 'Review the blueprint, then generate the draft'),
  },
])

const hasAiMessage = computed(() => optionalText(props.aiMessage).length > 0)
const emptyAiMessageHtml = () => `<p class="text-sm leading-6 text-slate-500">${pick(
  '暂无可确认内容，请返回对话补充后再试。',
  'There is nothing to confirm yet — go back to the chat, add more, and try again.'
)}</p>`
const renderedAiMessage = computed(() => {
  const raw = optionalText(props.aiMessage)
  return raw ? renderSafeMarkdown(raw) : emptyAiMessageHtml()
})

const loadingText = computed(() => {
  if (progress.value >= 100) return pick('小说总大纲已完成，正在准备切换页面', 'The master outline is done — preparing to switch pages')
  if (longWaitNotified.value) return pick('生成耗时较长，后台任务仍在继续执行', 'This is taking a while, but the background task is still running')
  if (currentProgressText.value) return currentProgressText.value
  if (progress.value >= 75) return pick('正在保存蓝图与总纲结构', 'Saving the blueprint and master outline structure')
  if (progress.value >= 40) return pick('正在生成蓝图结构与小说总大纲', 'Generating the blueprint structure and master outline')
  return pick('正在启动并整理蓝图核心信息', 'Starting up and organizing the blueprint essentials')
})

const progressHint = computed(() => {
  if (progress.value >= 100) return pick('生成完成后会自动切换到蓝图展示页。', 'You will be taken to the blueprint page automatically once generation finishes.')
  if (longWaitNotified.value) return pick('当前只是前端等待时间较长；后台任务没有被自动中断。', 'Only the frontend wait is long — the background task has not been interrupted.')
  if (progress.value >= 75) return pick(
    '系统正在写入项目蓝图和小说总大纲，并准备更新项目状态。',
    'The system is writing the project blueprint and master outline, and is about to update the project status.'
  )
  if (progress.value >= 40) return pick(
    '当前阶段会补齐世界设定、人物关系、故事弧，并生成全书级小说总大纲。',
    'This stage fills in the world setting, character relations, and story arcs, then produces the book-level master outline.'
  )
  return pick('任务已经后台化；页面会持续轮询任务状态。', 'The task runs in the background — this page keeps polling its status.')
})

const elapsedSeconds = computed(() => Math.ceil(timeElapsed.value))

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

function optionalText(value: unknown): string {
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return ''
}

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

const extractJobError = (status: BlueprintGenerationJobResponse): string => {
  const rawError = status.error
  const fallback = pick('蓝图生成失败，请稍后重试', 'Blueprint generation failed — please retry later')
  if (!rawError) return status.progress_message || fallback
  if (typeof rawError === 'string') return rawError
  return rawError.detail || rawError.message || status.progress_message || fallback
}

const pushProgressLog = (message: string) => {
  const normalized = optionalText(message)
  if (!normalized) return
  currentProgressMessage.value = normalized
  if (progressLogs.value[progressLogs.value.length - 1] === normalized) return
  progressLogs.value = [...progressLogs.value, normalized].slice(-6)
}

const resolveProgressFromMessage = (message: string, status: BlueprintGenerationJobResponse['status']) => {
  const text = optionalText(message)
  if (status === 'queued') return 8
  if (status === 'successful') return 100
  if (status === 'cancelled' || status === 'failed') return progress.value
  if (!text) return status === 'polishing' ? 72 : 24
  // 以下是对后端下发 progress_message 的中文匹配刻度表，属于数据比较值，不能翻译
  if (text.includes('整理灵感访谈')) return 16
  if (text.includes('锁定设定')) return 24
  if (text.includes('设定锁定包')) return 32
  if (text.includes('角色生命周期') || text.includes('伏笔回收窗口')) return 60
  if (text.includes('世界体系') || text.includes('世界骨架')) return 28
  if (text.includes('总大纲（阶段骨架首轮）')) return 42
  if (text.includes('解析小说总大纲骨架')) return 50
  if (text.includes('校验小说总大纲骨架连续性')) return 56
  if (text.includes('细化小说总大纲')) return 64
  if (text.includes('生成可执行章节大纲')) return 76
  if (text.includes('解析章节大纲批次')) return 82
  if (text.includes('润色章节大纲')) return 88
  if (text.includes('解析润色结果')) return 92
  if (text.includes('保存蓝图')) return 96
  if (status === 'polishing') return 72
  if (status === 'generating') return 38
  return progress.value
}

const updateProgressByStatus = (status: BlueprintGenerationJobResponse) => {
  const message = status.progress_message || ''
  pushProgressLog(message)
  progress.value = Math.max(progress.value, resolveProgressFromMessage(message, status.status))
}

const pollBlueprintJob = async (initialStatus: BlueprintGenerationJobResponse) => {
  let status = initialStatus
  updateProgressByStatus(status)

  while (!cancelRequested && ['queued', 'generating', 'polishing'].includes(status.status)) {
    await delay(2000)
    status = await novelStore.getBlueprintGenerationStatus()
    updateProgressByStatus(status)
  }

  if (cancelRequested || status.status === 'cancelled') {
    throw new Error(pick('蓝图生成已取消', 'Blueprint generation was cancelled'))
  }
  if (status.status === 'failed') {
    throw new Error(extractJobError(status))
  }
  if (status.status !== 'successful' || !status.blueprint) {
    throw new Error(status.progress_message || pick('蓝图任务未返回有效结果', 'The blueprint task returned no usable result'))
  }

  return {
    blueprint: status.blueprint,
    ai_message: status.ai_message || pick('蓝图已生成，请确认后进入写作阶段。', 'The blueprint is ready — confirm it to move on to writing.'),
  }
}

const generateBlueprint = async () => {
  if (isGenerating.value) return

  isGenerating.value = true
  cancelRequested = false
  longWaitNotified.value = false
  progress.value = 0
  timeElapsed.value = 0
  currentProgressMessage.value = ''
  progressLogs.value = []

  progressTimer = setInterval(() => {
    timeElapsed.value += 0.5
    const normalizedProgressBase = longWaitNoticeSeconds > 0 ? (timeElapsed.value / longWaitNoticeSeconds) * 95 : 0
    const timeProgress = Math.min(95, normalizedProgressBase)
    progress.value = Math.max(progress.value, timeProgress)
  }, 500)

  timeoutTimer = setTimeout(() => {
    longWaitNotified.value = true
    globalAlert.showInfo(
      pick(
        '蓝图生成耗时较长，但后台任务仍会继续执行，不会被前端自动取消。你可以继续等待，或手动点击“取消生成”。',
        'Blueprint generation is taking a while, but the background task keeps running and will not be cancelled automatically. Keep waiting, or click “Cancel generation” yourself.'
      ),
      pick('仍在生成', 'Still generating')
    )
  }, longWaitNoticeSeconds * 1000)

  try {
    const initialStatus = await novelStore.startBlueprintGeneration(
      props.forceStage ? { forceStage: props.forceStage } : {}
    )
    const response = await pollBlueprintJob(initialStatus)
    progress.value = 100
    await delay(600)
    clearTimers()
    isGenerating.value = false
    emit('blueprintGenerated', response)
  } catch (error) {
    console.error(pick('生成蓝图失败:', 'Failed to generate the blueprint:'), error)
    clearTimers()
    isGenerating.value = false
    const reason = error instanceof Error ? error.message : pick('未知错误', 'Unknown error')
    globalAlert.showError(
      pick(`生成蓝图失败：${reason}`, `Failed to generate the blueprint: ${reason}`),
      pick('生成失败', 'Generation failed'),
    )
  }
}

const cancelBlueprint = async () => {
  if (!isGenerating.value) return
  cancelRequested = true
  try {
    const status = await novelStore.cancelBlueprintGeneration()
    progress.value = Math.max(progress.value, 5)
    globalAlert.showInfo(
      status.progress_message || pick('蓝图生成已取消', 'Blueprint generation was cancelled'),
      pick('已取消', 'Cancelled')
    )
  } catch (error) {
    const reason = error instanceof Error ? error.message : pick('未知错误', 'Unknown error')
    globalAlert.showError(
      pick(`取消蓝图生成失败：${reason}`, `Failed to cancel blueprint generation: ${reason}`),
      pick('取消失败', 'Cancellation failed')
    )
  } finally {
    clearTimers()
    isGenerating.value = false
  }
}

const autoStarted = ref(false)
watch(
  () => props.forceStage,
  (stage) => {
    if (stage !== 'chapter_outline' || autoStarted.value) return
    autoStarted.value = true
    void generateBlueprint()
  },
  { immediate: true },
)

onUnmounted(() => {
  cancelRequested = true
  clearTimers()
})
</script>
<style scoped>
.blueprint-confirm {
  display: flex;
  min-height: 0;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--xq-border);
  border-radius: var(--xq-radius-lg);
  background: rgba(255, 250, 240, 0.86);
  box-shadow: var(--xq-shadow-floating);
  backdrop-filter: blur(18px);
}

.blueprint-confirm__hero {
  display: flex;
  justify-content: space-between;
  gap: 1.5rem;
  padding: clamp(1.25rem, 3vw, 2rem);
  color: #fffaf0;
  background:
    radial-gradient(circle at 82% 0%, rgba(214, 169, 79, 0.28), transparent 18rem),
    radial-gradient(circle at 12% 12%, rgba(61, 143, 125, 0.2), transparent 14rem),
    linear-gradient(135deg, var(--xq-bg-ink), var(--xq-bg-midnight));
}

.blueprint-confirm__copy h2 {
  max-width: 760px;
  margin: 1rem 0 0;
  font-family: var(--xq-font-serif);
  font-size: clamp(1.65rem, 3vw, 2.4rem);
  line-height: 1.18;
}

.blueprint-confirm__copy p {
  max-width: 760px;
  margin: 0.75rem 0 0;
  color: rgba(255, 250, 240, 0.7);
  line-height: 1.8;
}

.blueprint-confirm__badges,
.blueprint-confirm__actions,
.blueprint-confirm__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.65rem;
}

.blueprint-confirm__badges span,
.blueprint-confirm__state,
.blueprint-confirm__chips span {
  display: inline-flex;
  align-items: center;
  border-radius: var(--xq-radius-pill);
  font-size: 0.78rem;
  font-weight: 800;
}

.blueprint-confirm__badges span {
  min-height: 1.9rem;
  padding: 0 0.75rem;
  border: 1px solid rgba(255, 250, 240, 0.14);
  background: rgba(255, 250, 240, 0.1);
  color: rgba(255, 250, 240, 0.86);
}

.blueprint-confirm__badges .is-running {
  border-color: rgba(214, 169, 79, 0.36);
  background: rgba(214, 169, 79, 0.18);
  color: #ffe7a8;
}

.blueprint-confirm__badges .is-ready {
  border-color: rgba(61, 143, 125, 0.36);
  background: rgba(61, 143, 125, 0.18);
  color: #c7fff3;
}

.blueprint-confirm__actions {
  align-content: flex-start;
  justify-content: flex-end;
}

.blueprint-confirm__stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.85rem;
  padding: 1rem clamp(1rem, 3vw, 1.5rem) 0;
}

.blueprint-confirm__body {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(320px, 360px);
  gap: 1rem;
  min-height: 0;
  overflow-y: auto;
  padding: 1rem clamp(1rem, 3vw, 1.5rem) 1.5rem;
}

.blueprint-confirm__main,
.blueprint-confirm__side {
  display: grid;
  align-content: start;
  gap: 1rem;
}

.blueprint-confirm__state {
  min-height: 1.9rem;
  padding: 0 0.75rem;
  border: 1px solid var(--xq-border);
  background: rgba(255, 250, 240, 0.72);
  color: var(--xq-ink-muted);
}

.blueprint-confirm__markdown-shell {
  border: 1px solid var(--xq-border);
  border-radius: var(--xq-radius-md);
  padding: 1.25rem;
  background: rgba(255, 250, 240, 0.58);
}

.blueprint-confirm__progress-row {
  display: flex;
  gap: 1.25rem;
  align-items: center;
}

.blueprint-confirm__ring {
  display: grid;
  flex: none;
  width: 6rem;
  height: 6rem;
  place-items: center;
  border-radius: 999px;
  background:
    radial-gradient(circle at center, rgba(255, 250, 240, 0.96) 0 52%, transparent 54%),
    conic-gradient(var(--xq-gold) calc(var(--progress, 0) * 1%), rgba(93, 70, 43, 0.12) 0);
  box-shadow: inset 0 0 0 0.35rem rgba(214, 169, 79, 0.12);
  animation: xq-breathe 1.4s ease-in-out infinite;
}

.blueprint-confirm__ring.is-complete {
  animation: none;
}

.blueprint-confirm__ring span {
  font-weight: 900;
}

.blueprint-confirm__progress-copy {
  flex: 1;
  min-width: 0;
}

.blueprint-confirm__track {
  height: 0.6rem;
  overflow: hidden;
  border-radius: var(--xq-radius-pill);
  background: rgba(93, 70, 43, 0.12);
}

.blueprint-confirm__track div {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--xq-gold-deep), var(--xq-gold), var(--xq-jade));
  transition: width var(--xq-normal);
}

.blueprint-confirm__task-log-current {
  margin-top: 0.85rem;
  color: var(--xq-ink);
  font-size: 0.95rem;
  line-height: 1.7;
}

.blueprint-confirm__chips {
  margin-top: 0.9rem;
}

.blueprint-confirm__chips span {
  padding: 0.35rem 0.7rem;
  background: rgba(214, 169, 79, 0.12);
  color: var(--xq-gold-deep);
}

.blueprint-confirm__task-log-list {
  margin-top: 0.85rem;
  display: grid;
  gap: 0.45rem;
  padding-left: 1.1rem;
  color: var(--xq-ink-muted);
  font-size: 0.86rem;
  line-height: 1.65;
}

.blueprint-confirm__next {
  display: grid;
  gap: 0.4rem;
  border: 1px solid var(--xq-border);
  border-radius: var(--xq-radius-md);
  padding: 1rem;
  background: rgba(255, 250, 240, 0.66);
  color: var(--xq-ink-muted);
  line-height: 1.7;
}

.blueprint-confirm__next strong {
  color: var(--xq-ink);
}

.blueprint-confirm__checklist,
.blueprint-confirm__flow {
  display: grid;
  gap: 0.75rem;
}

.blueprint-confirm__checklist article,
.blueprint-confirm__flow article {
  border: 1px solid var(--xq-border);
  border-radius: var(--xq-radius-sm);
  padding: 0.9rem;
  background: rgba(255, 250, 240, 0.08);
}

.blueprint-confirm__checklist strong,
.blueprint-confirm__checklist span {
  display: block;
}

.blueprint-confirm__checklist span {
  margin-top: 0.35rem;
  color: rgba(255, 250, 240, 0.68);
  line-height: 1.65;
}

.blueprint-confirm__flow article {
  display: flex;
  gap: 0.75rem;
  background: rgba(255, 250, 240, 0.58);
}

.blueprint-confirm__flow article > span {
  display: inline-flex;
  width: 2rem;
  height: 2rem;
  flex: none;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: rgba(214, 169, 79, 0.16);
  color: var(--xq-gold-deep);
  font-weight: 900;
}

.blueprint-confirm__flow strong {
  display: block;
  color: var(--xq-ink);
}

.blueprint-confirm__flow p {
  margin: 0.3rem 0 0;
  color: var(--xq-ink-muted);
  line-height: 1.65;
}

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
  color: var(--xq-ink);
  font-weight: 800;
}

.blueprint-markdown :deep(a) {
  color: var(--xq-gold-deep);
  text-decoration: none;
}

.blueprint-markdown :deep(a:hover) {
  text-decoration: underline;
}

@keyframes xq-breathe {
  50% { transform: scale(1.035); }
}

@media (max-width: 1100px) {
  .blueprint-confirm__hero,
  .blueprint-confirm__body {
    grid-template-columns: 1fr;
  }

  .blueprint-confirm__hero {
    flex-direction: column;
  }

  .blueprint-confirm__actions {
    justify-content: flex-start;
  }

  .blueprint-confirm__stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .blueprint-confirm__stats {
    grid-template-columns: 1fr;
  }

  .blueprint-confirm__progress-row {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>

