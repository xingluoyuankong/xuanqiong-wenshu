<template>
  <div class="space-y-5 overflow-y-auto">
    <section class="rounded-3xl border border-slate-200 bg-slate-50/80 p-5">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 class="text-lg font-semibold text-slate-900">伏笔管理工作台</h3>
          <p class="mt-1 text-sm leading-6 text-slate-600">
            这里不只是“记录伏笔”，而是把埋下、推进、提醒、回收整合到一张看板里，方便你判断下一章该处理哪些线索。
          </p>
        </div>
        <button
          class="inline-flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm transition hover:border-slate-300 hover:text-slate-900"
          :disabled="loading"
          @click="reload"
        >
          <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          刷新伏笔状态
        </button>
      </div>
    </section>

    <section class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <article v-for="item in summaryCards" :key="item.label" class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div class="text-xs font-medium tracking-wide text-slate-500">{{ item.label }}</div>
        <div class="mt-2 text-2xl font-semibold text-slate-900">{{ item.value }}</div>
        <div v-if="item.hint" class="mt-2 text-xs text-slate-500">{{ item.hint }}</div>
      </article>
    </section>

    <section class="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h4 class="text-base font-semibold text-slate-900">自动提醒与风险提示</h4>
          <p class="mt-1 text-sm text-slate-500">如果伏笔拖太久没处理，系统会在这里明确提醒你该在哪个方向推进。</p>
        </div>
        <span class="rounded-full bg-amber-50 px-3 py-1 text-xs font-medium text-amber-700">自动汇总</span>
      </div>
      <div v-if="recommendations.length || reminders.length" class="mt-4 grid gap-4 xl:grid-cols-2">
        <div class="space-y-3">
          <div class="text-sm font-medium text-slate-700">本轮建议</div>
          <div v-for="(item, index) in recommendations" :key="`recommend-${index}`" class="rounded-2xl border border-sky-100 bg-sky-50/70 px-4 py-3 text-sm leading-6 text-slate-700">
            {{ item }}
          </div>
          <div v-if="!recommendations.length" class="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-500">当前没有额外建议。</div>
        </div>
        <div class="space-y-3">
          <div class="text-sm font-medium text-slate-700">待处理提醒</div>
          <div v-for="item in reminders" :key="item.id" class="rounded-2xl border border-amber-100 bg-amber-50/80 px-4 py-3">
            <div class="text-sm font-medium text-slate-900">{{ item.message }}</div>
            <div class="mt-1 text-xs text-slate-500">{{ mapReminderType(item.reminder_type) }} · {{ formatDate(item.created_at) }}</div>
          </div>
          <div v-if="!reminders.length" class="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-500">当前没有待处理提醒，说明伏笔节奏暂时正常。</div>
        </div>
      </div>
      <div v-else class="mt-4 rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-500">还没有生成出足够的伏笔分析数据。</div>
    </section>

    <section class="grid gap-4 xl:grid-cols-4">
      <article v-for="column in boardColumns" :key="column.key" class="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
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
            class="rounded-2xl border px-3 py-3"
            :class="column.cardClass"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="text-sm font-medium leading-6 text-slate-900">{{ item.content }}</div>
              <span class="rounded-full bg-white/90 px-2 py-1 text-[11px] text-slate-500">第 {{ item.chapter_number }} 章</span>
            </div>
            <div class="mt-2 flex flex-wrap gap-2 text-xs text-slate-500">
              <span class="rounded-full bg-white/80 px-2 py-1">{{ mapForeshadowType(item.type) }}</span>
              <span v-if="item.resolved_chapter_number" class="rounded-full bg-white/80 px-2 py-1">已在第 {{ item.resolved_chapter_number }} 章回收</span>
              <span v-else-if="item.stageHint" class="rounded-full bg-white/80 px-2 py-1">{{ item.stageHint }}</span>
            </div>
            <div v-if="item.author_note" class="mt-2 text-xs leading-5 text-slate-500">作者备注：{{ item.author_note }}</div>
          </div>
          <div v-if="!column.items.length" class="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-3 py-6 text-center text-sm text-slate-500">暂无内容</div>
        </div>
      </article>
    </section>

    <section v-if="error" class="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
      {{ error }}
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ForeshadowingAPI, type ForeshadowingAnalysisResponse, type ForeshadowingItem, type ForeshadowingReminderItem } from '@/api/novel'

const props = defineProps<{ projectId?: string }>()

const loading = ref(false)
const error = ref('')
const list = ref<ForeshadowingItem[]>([])
const reminders = ref<ForeshadowingReminderItem[]>([])
const analysis = ref<ForeshadowingAnalysisResponse | null>(null)

const projectId = computed(() => props.projectId || '')
const maxChapter = computed(() => list.value.reduce((max, item) => Math.max(max, item.chapter_number, item.resolved_chapter_number || 0), 0))

const enrichItem = (item: ForeshadowingItem) => {
  const distance = maxChapter.value - item.chapter_number
  let stageHint = '刚埋下，后续可以继续铺陈'
  if (item.resolved_chapter_number) {
    stageHint = `回收跨度 ${Math.max(item.resolved_chapter_number - item.chapter_number, 0)} 章`
  } else if (distance >= 4) {
    stageHint = '拖延较久，建议尽快安排回收或推进'
  } else if (distance >= 2) {
    stageHint = '已进入推进区，可在后续章节继续强化'
  }
  return { ...item, stageHint, distance }
}

const resolvedItems = computed(() => list.value.filter(item => item.resolved_chapter_number))
const unresolvedItems = computed(() => list.value.filter(item => !item.resolved_chapter_number))
const plantedItems = computed(() => unresolvedItems.value.map(enrichItem).filter(item => item.distance < 2))
const progressingItems = computed(() => unresolvedItems.value.map(enrichItem).filter(item => item.distance >= 2 && item.distance < 4))
const overdueItems = computed(() => unresolvedItems.value.map(enrichItem).filter(item => item.distance >= 4))

const summaryCards = computed(() => [
  { label: '总伏笔数', value: String(list.value.length) },
  { label: '待回收', value: String(overdueItems.value.length), hint: '拖延过久最容易削弱读者期待' },
  { label: '已回收', value: String(resolvedItems.value.length), hint: analysis.value?.avg_resolution_distance != null ? `平均回收跨度 ${analysis.value.avg_resolution_distance.toFixed(1)} 章` : undefined },
  { label: '整体质量', value: analysis.value?.overall_quality_score != null ? `${analysis.value.overall_quality_score.toFixed(1)} / 10` : '—', hint: analysis.value?.unresolved_ratio != null ? `未回收占比 ${(analysis.value.unresolved_ratio * 100).toFixed(0)}%` : undefined }
])

const recommendations = computed(() => analysis.value?.recommendations || [])

const boardColumns = computed(() => [
  {
    key: 'planted',
    title: '新埋下',
    description: '刚埋下的伏笔，重点是别丢。',
    badgeClass: 'bg-sky-50 text-sky-700',
    cardClass: 'border-sky-100 bg-sky-50/70',
    items: plantedItems.value
  },
  {
    key: 'progressing',
    title: '推进中',
    description: '已经进入承接区，可以继续强化存在感。',
    badgeClass: 'bg-violet-50 text-violet-700',
    cardClass: 'border-violet-100 bg-violet-50/70',
    items: progressingItems.value
  },
  {
    key: 'overdue',
    title: '待回收',
    description: '拖太久没处理，最容易让读者忘掉或觉得空。',
    badgeClass: 'bg-amber-50 text-amber-700',
    cardClass: 'border-amber-100 bg-amber-50/80',
    items: overdueItems.value
  },
  {
    key: 'resolved',
    title: '已回收',
    description: '已经完成落地的伏笔，可用于回看回收节奏。',
    badgeClass: 'bg-emerald-50 text-emerald-700',
    cardClass: 'border-emerald-100 bg-emerald-50/80',
    items: resolvedItems.value.map(enrichItem)
  }
])

const mapForeshadowType = (value: string) => {
  const normalized = String(value || '').toLowerCase()
  if (['main_plot', 'theme'].includes(normalized)) return '主线伏笔'
  if (['character', 'subplot'].includes(normalized)) return '人物 / 支线伏笔'
  if (['scene', 'short'].includes(normalized)) return '短线提示'
  return value || '未分类伏笔'
}

const mapReminderType = (value: string) => {
  const normalized = String(value || '').toLowerCase()
  if (normalized.includes('payoff')) return '回收提醒'
  if (normalized.includes('stale')) return '拖延预警'
  if (normalized.includes('consistency')) return '一致性提醒'
  return value || '系统提醒'
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
  } catch (err: any) {
    error.value = err instanceof Error ? err.message : '加载伏笔管理失败'
  } finally {
    loading.value = false
  }
}

const reload = () => { void load() }

onMounted(load)
watch(projectId, (value) => { if (value) void load() })
</script>
