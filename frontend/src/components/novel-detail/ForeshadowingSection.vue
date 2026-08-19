<template>
  <div class="space-y-3 overflow-y-auto">
    <section class="rounded-xl border border-slate-200 bg-slate-50/80 p-5">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 class="text-lg font-semibold text-slate-900">{{ pick('伏笔管理工作台', 'Foreshadowing workbench') }}</h3>
          <p class="mt-1 text-sm leading-6 text-slate-600">
            {{ pick(
              '这里不只是“记录伏笔”，而是把埋下、推进、提醒、回收整合到一张看板里，方便你判断下一章该处理哪些线索。',
              'This is more than a foreshadowing log: planting, progression, reminders, and payoff sit on one board so you can tell which threads the next chapter must handle.'
            ) }}
          </p>
        </div>
        <button
          class="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm transition hover:border-slate-300 hover:text-slate-900"
          :disabled="loading"
          @click="reload"
        >
          <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          {{ pick('刷新伏笔状态', 'Refresh foreshadowing state') }}
        </button>
      </div>
    </section>

    <section class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <article v-for="item in summaryCards" :key="item.label" class="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <div class="text-xs font-medium tracking-wide text-slate-500">{{ item.label }}</div>
        <div class="mt-2 text-xl font-semibold text-slate-900">{{ item.value }}</div>
        <div v-if="item.hint" class="mt-2 text-xs text-slate-500">{{ item.hint }}</div>
      </article>
    </section>

    <section class="rounded-xl border border-sky-100 bg-white p-3 shadow-sm">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h4 class="text-base font-semibold text-slate-900">{{ pick('下章必须处理', 'Must handle next chapter') }}</h4>
          <p class="mt-1 text-sm text-slate-500">{{ pick('根据目标回收章节、提醒、紧迫度和拖延距离，把最容易被遗忘的伏笔先挑出来。', 'Target payoff chapter, reminders, urgency, and delay distance surface the foreshadowing most likely to be forgotten.') }}</p>
        </div>
        <span class="rounded-full bg-sky-50 px-3 py-1 text-xs font-medium text-sky-700">{{ pick(`第 ${maxChapter + 1} 章任务建议`, `Suggested tasks for chapter ${maxChapter + 1}`) }}</span>
      </div>
      <div v-if="nextChapterTasks.length" class="mt-4 grid gap-3 lg:grid-cols-2">
        <article v-for="item in nextChapterTasks" :key="`next-${item.id}`" class="rounded-lg border border-sky-100 bg-sky-50/70 px-4 py-3">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="text-sm font-semibold leading-6 text-slate-900">{{ itemTitle(item) }}</div>
              <p class="mt-1 text-sm leading-6 text-slate-600">{{ item.content }}</p>
            </div>
            <span class="shrink-0 rounded-full bg-white px-2.5 py-1 text-[11px] font-medium text-sky-700">{{ item.priorityLabel }}</span>
          </div>
          <div class="mt-3 flex flex-wrap gap-2 text-xs text-slate-600">
            <span class="rounded-full bg-white/90 px-2 py-1">{{ pick(`第 ${item.chapter_number} 章埋下`, `Planted in chapter ${item.chapter_number}`) }}</span>
            <span v-if="item.targetHint" class="rounded-full bg-white/90 px-2 py-1">{{ item.targetHint }}</span>
            <span v-if="item.urgency" class="rounded-full bg-white/90 px-2 py-1">{{ pick(`紧迫度 ${item.urgency}/10`, `Urgency ${item.urgency}/10`) }}</span>
            <span v-if="item.related_characters?.length" class="rounded-full bg-white/90 px-2 py-1">{{ pick('角色：', 'Characters: ') }}{{ item.related_characters.slice(0, 3).join(pick('、', ', ')) }}</span>
          </div>
          <div v-if="item.reveal_method || item.reveal_impact" class="mt-3 grid gap-2 text-xs leading-5 text-slate-600 md:grid-cols-2">
            <div v-if="item.reveal_method" class="rounded-xl bg-white/80 px-3 py-2">{{ pick('回收方式：', 'Payoff method: ') }}{{ item.reveal_method }}</div>
            <div v-if="item.reveal_impact" class="rounded-xl bg-white/80 px-3 py-2">{{ pick('回收影响：', 'Payoff impact: ') }}{{ item.reveal_impact }}</div>
          </div>
          <div class="mt-3 rounded-xl bg-white/80 px-3 py-2 text-xs leading-5 text-slate-700">
            {{ pick('局部补丁建议：', 'Local patch suggestion: ') }}{{ patchSuggestion(item) }}
          </div>
        </article>
      </div>
      <div v-else class="mt-4 rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-500">{{ pick('当前没有必须压到下一章处理的伏笔。', 'No foreshadowing has to be handled in the next chapter right now.') }}</div>
    </section>

    <section class="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h4 class="text-base font-semibold text-slate-900">{{ pick('自动提醒与风险提示', 'Automatic reminders and risk alerts') }}</h4>
          <p class="mt-1 text-sm text-slate-500">{{ pick('如果伏笔拖太久没处理，系统会在这里明确提醒你该在哪个方向推进。', 'When foreshadowing sits unhandled too long, this panel spells out which direction to push it.') }}</p>
        </div>
        <span class="rounded-full bg-sky-50 px-3 py-1 text-xs font-medium text-sky-700">{{ pick('自动汇总', 'Auto summary') }}</span>
      </div>
      <div v-if="recommendations.length || reminders.length" class="mt-4 grid gap-4 xl:grid-cols-2">
        <div class="space-y-3">
          <div class="text-sm font-medium text-slate-700">{{ pick('本轮建议', 'Suggestions this round') }}</div>
          <div v-for="(item, index) in recommendations" :key="`recommend-${index}`" class="rounded-lg border border-sky-100 bg-sky-50/70 px-4 py-3 text-sm leading-6 text-slate-700">
            {{ item }}
          </div>
          <div v-if="!recommendations.length" class="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-500">{{ pick('当前没有额外建议。', 'No extra suggestions right now.') }}</div>
        </div>
        <div class="space-y-3">
          <div class="text-sm font-medium text-slate-700">{{ pick('待处理提醒', 'Pending reminders') }}</div>
          <div v-for="item in reminders" :key="item.id" class="rounded-lg border border-sky-100 bg-sky-50/80 px-4 py-3">
            <div class="text-sm font-medium text-slate-900">{{ item.message }}</div>
            <div class="mt-1 text-xs text-slate-500">{{ mapReminderType(item.reminder_type) }} · {{ formatDate(item.created_at) }}{{ reminderRangeLabel(item) }}</div>
          </div>
          <div v-if="!reminders.length" class="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-500">{{ pick('当前没有待处理提醒，说明伏笔节奏暂时正常。', 'No pending reminders, so the foreshadowing pacing looks fine for now.') }}</div>
        </div>
      </div>
      <div v-else class="mt-4 rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-500">{{ pick('还没有生成出足够的伏笔分析数据。', 'Not enough foreshadowing analysis data has been generated yet.') }}</div>
    </section>

    <section class="grid gap-4 xl:grid-cols-4">
      <article v-for="column in boardColumns" :key="column.key" class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div class="flex items-center justify-between gap-2">
          <div>
            <h4 class="text-sm font-semibold text-slate-900">{{ column.title }}</h4>
            <p class="mt-1 text-xs leading-5 text-slate-500">{{ column.description }}</p>
          </div>
          <span class="rounded-full px-2.5 py-1 text-xs font-medium" :class="column.badgeClass">{{ column.items.length }}</span>
        </div>
        <div class="mt-4 space-y-3">
          <div
            v-for="item in column.items"
            :key="item.id"
            class="rounded-lg border px-3 py-3"
            :class="column.cardClass"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="text-sm font-medium leading-6 text-slate-900">{{ itemTitle(item) }}</div>
              <span class="rounded-full bg-white/90 px-2 py-1 text-[11px] text-slate-500">{{ pick(`第 ${item.chapter_number} 章`, `Chapter ${item.chapter_number}`) }}</span>
            </div>
            <div v-if="item.name" class="mt-1 text-xs leading-5 text-slate-500 line-clamp-2">{{ item.content }}</div>
            <div class="mt-2 flex flex-wrap gap-2 text-xs text-slate-500">
              <span class="rounded-full bg-white/80 px-2 py-1">{{ mapForeshadowType(item.type) }}</span>
              <span v-if="item.resolved_chapter_number" class="rounded-full bg-white/80 px-2 py-1">{{ pick(`已在第 ${item.resolved_chapter_number} 章回收`, `Paid off in chapter ${item.resolved_chapter_number}`) }}</span>
              <span v-else-if="item.stageHint" class="rounded-full bg-white/80 px-2 py-1">{{ item.stageHint }}</span>
              <span v-if="item.targetHint && !item.resolved_chapter_number" class="rounded-full bg-white/80 px-2 py-1">{{ item.targetHint }}</span>
              <span v-if="item.urgency" class="rounded-full bg-white/80 px-2 py-1">{{ pick(`紧迫度 ${item.urgency}/10`, `Urgency ${item.urgency}/10`) }}</span>
            </div>
            <div v-if="item.reveal_method && !item.resolved_chapter_number" class="mt-2 text-xs leading-5 text-slate-500">{{ pick('建议回收：', 'Suggested payoff: ') }}{{ item.reveal_method }}</div>
            <div v-if="item.author_note" class="mt-2 text-xs leading-5 text-slate-500">{{ pick('作者备注：', 'Author note: ') }}{{ item.author_note }}</div>
          </div>
          <div v-if="!column.items.length" class="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-3 py-6 text-center text-sm text-slate-500">{{ pick('暂无内容', 'Nothing here yet') }}</div>
        </div>
      </article>
    </section>

    <section v-if="error" class="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
      {{ error }}
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ForeshadowingAPI, type ForeshadowingAnalysisResponse, type ForeshadowingItem, type ForeshadowingReminderItem } from '@/api/novel'
import { useLocale } from '@/composables/useLocale'

const props = defineProps<{ projectId?: string }>()

const { pick } = useLocale()

const loading = ref(false)
const error = ref('')
const list = ref<ForeshadowingItem[]>([])
const reminders = ref<ForeshadowingReminderItem[]>([])
const analysis = ref<ForeshadowingAnalysisResponse | null>(null)

const projectId = computed(() => props.projectId || '')
const maxChapter = computed(() => list.value.reduce((max, item) => Math.max(max, item.chapter_number, item.resolved_chapter_number || 0), 0))
const activeReminderIds = computed(() => new Set(reminders.value.filter(item => item.status !== 'resolved' && item.status !== 'dismissed').map(item => item.foreshadowing_id)))

const enrichItem = (item: ForeshadowingItem) => {
  const distance = maxChapter.value - item.chapter_number
  const targetReveal = typeof item.target_reveal_chapter === 'number' ? item.target_reveal_chapter : null
  const targetDistance = targetReveal == null ? null : targetReveal - maxChapter.value
  const hasReminder = activeReminderIds.value.has(item.id)
  const urgency = Number(item.urgency || 0)
  let stageHint = pick('刚埋下，后续可以继续铺陈', 'Just planted; keep layering it in later chapters')
  let targetHint = ''
  let priorityLabel = pick('保持可见', 'Keep visible')
  let priorityRank = 0
  if (item.resolved_chapter_number) {
    stageHint = pick(`回收跨度 ${Math.max(item.resolved_chapter_number - item.chapter_number, 0)} 章`, `Payoff span: ${Math.max(item.resolved_chapter_number - item.chapter_number, 0)} chapters`)
    priorityLabel = pick('已回收', 'Paid off')
  } else if (distance >= 4) {
    stageHint = pick('拖延较久，建议尽快安排回收或推进', 'Delayed for a while; schedule a payoff or push it forward soon')
    priorityLabel = pick('逾期风险', 'Overdue risk')
    priorityRank = 3
  } else if (distance >= 2) {
    stageHint = pick('已进入推进区，可在后续章节继续强化', 'In the progression zone; reinforce it in the coming chapters')
    priorityLabel = pick('近期强化', 'Reinforce soon')
    priorityRank = 1
  }
  if (targetReveal != null) {
    if (targetDistance == null) {
      targetHint = pick(`计划第 ${targetReveal} 章回收`, `Planned payoff in chapter ${targetReveal}`)
    } else if (targetDistance < 0) {
      targetHint = pick(`已超过计划回收 ${Math.abs(targetDistance)} 章`, `Overdue by ${Math.abs(targetDistance)} chapters past the plan`)
      priorityLabel = pick('计划逾期', 'Plan overdue')
      priorityRank = Math.max(priorityRank, 4)
    } else if (targetDistance <= 1) {
      targetHint = pick(`计划第 ${targetReveal} 章前后回收`, `Planned payoff around chapter ${targetReveal}`)
      priorityLabel = pick('下章处理', 'Handle next chapter')
      priorityRank = Math.max(priorityRank, 5)
    } else {
      targetHint = pick(`计划第 ${targetReveal} 章回收`, `Planned payoff in chapter ${targetReveal}`)
    }
  }
  if (hasReminder) {
    priorityLabel = pick('提醒待办', 'Reminder pending')
    priorityRank = Math.max(priorityRank, 6)
  }
  if (urgency >= 8 && !item.resolved_chapter_number) {
    priorityLabel = pick('高紧迫', 'High urgency')
    priorityRank = Math.max(priorityRank, 7)
  }
  return { ...item, stageHint, distance, targetHint, targetDistance, hasReminder, priorityLabel, priorityRank }
}

const resolvedItems = computed(() => list.value.filter(item => item.resolved_chapter_number))
const unresolvedItems = computed(() => list.value.filter(item => !item.resolved_chapter_number))
const plantedItems = computed(() => unresolvedItems.value.map(enrichItem).filter(item => item.distance < 2))
const progressingItems = computed(() => unresolvedItems.value.map(enrichItem).filter(item => item.distance >= 2 && item.distance < 4))
const overdueItems = computed(() => unresolvedItems.value.map(enrichItem).filter(item => item.distance >= 4))
const nextChapterTasks = computed(() => unresolvedItems.value
  .map(enrichItem)
  .filter(item => item.priorityRank >= 5 || item.distance >= 5)
  .sort((a, b) => b.priorityRank - a.priorityRank || Number(b.urgency || 0) - Number(a.urgency || 0) || b.distance - a.distance)
  .slice(0, 8))

const summaryCards = computed(() => [
  { label: pick('总伏笔数', 'Total foreshadowing'), value: String(list.value.length) },
  { label: pick('待回收', 'Awaiting payoff'), value: String(overdueItems.value.length), hint: pick('拖延过久最容易削弱读者期待', 'Long delays are the fastest way to blunt reader anticipation') },
  { label: pick('已回收', 'Paid off'), value: String(resolvedItems.value.length), hint: analysis.value?.avg_resolution_distance != null ? pick(`平均回收跨度 ${analysis.value.avg_resolution_distance.toFixed(1)} 章`, `Average payoff span: ${analysis.value.avg_resolution_distance.toFixed(1)} chapters`) : undefined },
  { label: pick('下章任务', 'Next-chapter tasks'), value: String(nextChapterTasks.value.length), hint: pick('来自目标回收、提醒和紧迫度', 'Derived from target payoff, reminders, and urgency') },
  { label: pick('整体质量', 'Overall quality'), value: analysis.value?.overall_quality_score != null ? `${analysis.value.overall_quality_score.toFixed(1)} / 10` : '—', hint: analysis.value?.unresolved_ratio != null ? pick(`未回收占比 ${(analysis.value.unresolved_ratio * 100).toFixed(0)}%`, `Unresolved share: ${(analysis.value.unresolved_ratio * 100).toFixed(0)}%`) : undefined }
])

const recommendations = computed(() => analysis.value?.recommendations || [])

const boardColumns = computed(() => [
  {
    key: 'planted',
    title: pick('新埋下', 'Newly planted'),
    description: pick('刚埋下的伏笔，重点是别丢。', 'Freshly planted threads — the point is not to lose them.'),
    badgeClass: 'bg-sky-50 text-sky-700',
    cardClass: 'border-sky-100 bg-sky-50/70',
    items: plantedItems.value
  },
  {
    key: 'progressing',
    title: pick('推进中', 'In progress'),
    description: pick('已经进入承接区，可以继续强化存在感。', 'Already in the follow-through zone; keep strengthening their presence.'),
    badgeClass: 'bg-violet-50 text-violet-700',
    cardClass: 'border-violet-100 bg-violet-50/70',
    items: progressingItems.value
  },
  {
    key: 'overdue',
    title: pick('待回收', 'Awaiting payoff'),
    description: pick('拖太久没处理，最容易让读者忘掉或觉得空。', 'Left too long, readers either forget them or feel cheated.'),
    badgeClass: 'bg-sky-50 text-sky-700',
    cardClass: 'border-sky-100 bg-sky-50/80',
    items: overdueItems.value
  },
  {
    key: 'resolved',
    title: pick('已回收', 'Paid off'),
    description: pick('已经完成落地的伏笔，可用于回看回收节奏。', 'Threads already landed — useful for reviewing payoff pacing.'),
    badgeClass: 'bg-emerald-50 text-emerald-700',
    cardClass: 'border-emerald-100 bg-emerald-50/80',
    items: resolvedItems.value.map(enrichItem)
  }
])

const mapForeshadowType = (value: string) => {
  const normalized = String(value || '').toLowerCase()
  // 这些是后端 type 枚举取值，属于匹配规则，不随语言变化
  if (['main_plot', 'theme'].includes(normalized)) return pick('主线伏笔', 'Main-plot foreshadowing')
  if (['character', 'subplot'].includes(normalized)) return pick('人物 / 支线伏笔', 'Character / subplot foreshadowing')
  if (['scene', 'short'].includes(normalized)) return pick('短线提示', 'Short-range hint')
  return value || pick('未分类伏笔', 'Uncategorized foreshadowing')
}

const mapReminderType = (value: string) => {
  const normalized = String(value || '').toLowerCase()
  // payoff / stale / consistency 是后端 reminder_type 关键字，属于匹配规则，不随语言变化
  if (normalized.includes('payoff')) return pick('回收提醒', 'Payoff reminder')
  if (normalized.includes('stale')) return pick('拖延预警', 'Delay warning')
  if (normalized.includes('consistency')) return pick('一致性提醒', 'Continuity reminder')
  return value || pick('系统提醒', 'System reminder')
}

const itemTitle = (item: ForeshadowingItem) => item.name || item.content

const patchSuggestion = (item: ReturnType<typeof enrichItem>) => {
  if (item.reveal_method) return pick(
    `在不推翻原章节的前提下，新增一个局部场景或对话回合，让“${itemTitle(item)}”按计划回收：${item.reveal_method}`,
    `Without rewriting the chapter, add one local scene or dialogue beat so “${itemTitle(item)}” pays off as planned: ${item.reveal_method}`
  )
  if (item.target_reveal_chapter) return pick(
    `在第 ${maxChapter.value + 1} 章给“${itemTitle(item)}”安排可见动作、证据或角色反应，避免继续超过第 ${item.target_reveal_chapter} 章回收窗口。`,
    `In chapter ${maxChapter.value + 1}, give “${itemTitle(item)}” a visible action, piece of evidence, or character reaction so it does not slip further past the chapter ${item.target_reveal_chapter} payoff window.`
  )
  if (item.related_characters?.length) return pick(
    `让 ${item.related_characters.slice(0, 2).join('、')} 在下一章的行动或对话中触碰这条伏笔，不要整章重写，只补关键承接片段。`,
    `Have ${item.related_characters.slice(0, 2).join(', ')} touch this thread through action or dialogue next chapter — no full rewrite, just the key connective beat.`
  )
  return pick(
    `给“${itemTitle(item)}”补一个明确的发现、追问、代价或误导反转，让读者重新记住它。`,
    `Give “${itemTitle(item)}” a concrete discovery, follow-up question, cost, or misdirection reversal so readers remember it again.`
  )
}

const reminderRangeLabel = (item: ForeshadowingReminderItem) => {
  const range = item.suggested_chapter_range
  if (!range || (!range.start && !range.end)) return ''
  if (range.start && range.end) return pick(` · 建议第 ${range.start}-${range.end} 章处理`, ` · Suggested handling in chapters ${range.start}-${range.end}`)
  if (range.start) return pick(` · 建议第 ${range.start} 章后处理`, ` · Suggested handling after chapter ${range.start}`)
  return pick(` · 建议第 ${range.end} 章前处理`, ` · Suggested handling before chapter ${range.end}`)
}

const formatDate = (value: string) => {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

const load = async () => {
  if (!projectId.value) return
  loading.value = true
  error.value = ''
  try {
    const [foreshadowings, reminderData, analysisData] = await Promise.all([
      ForeshadowingAPI.getForeshadowings(projectId.value),
      ForeshadowingAPI.getReminders(projectId.value).catch(() => ({ total: 0, data: [] })),
      ForeshadowingAPI.getAnalysis(projectId.value).catch(() => null)
    ])
    list.value = foreshadowings.data || []
    reminders.value = reminderData?.data || []
    analysis.value = analysisData
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : pick('加载伏笔管理失败', 'Failed to load the foreshadowing workbench')
  } finally {
    loading.value = false
  }
}

const reload = () => { void load() }

onMounted(load)
watch(projectId, (value) => { if (value) void load() })
</script>
