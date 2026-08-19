<template>
  <div class="clue-tracker-page grid h-full gap-5 xl:grid-cols-[320px_minmax(0,1fr)]">
    <aside class="space-y-4 rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
      <div>
        <h3 class="text-lg font-semibold text-slate-900">{{ pick('线索追踪', 'Clue tracker') }}</h3>
        <p class="mt-1 text-sm leading-6 text-slate-600">
          {{ pick(
            '自动从伏笔系统同步到线索工作台，用来判断主线、误导线和待回收线索现在推进到了哪里。',
            'Synced automatically from the foreshadowing system so you can tell where the main threads, misdirections, and unresolved clues currently stand.'
          ) }}
        </p>
      </div>
      <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
        <article class="rounded-lg bg-slate-50 p-4">
          <div class="text-xs font-medium tracking-wide text-slate-500">{{ pick('总线索数', 'Total clues') }}</div>
          <div class="mt-2 text-xl font-semibold text-slate-900">{{ analysis.total_clues || clues.length }}</div>
        </article>
        <article class="rounded-lg bg-slate-50 p-4">
          <div class="text-xs font-medium tracking-wide text-slate-500">{{ pick('待回收主线', 'Unresolved threads') }}</div>
          <div class="mt-2 text-xl font-semibold text-slate-900">{{ analysis.unresolved_count || 0 }}</div>
        </article>
        <article class="rounded-lg bg-slate-50 p-4">
          <div class="text-xs font-medium tracking-wide text-slate-500">{{ pick('红鲱鱼', 'Red herrings') }}</div>
          <div class="mt-2 text-xl font-semibold text-slate-900">{{ analysis.red_herring_count || 0 }}</div>
        </article>
        <article class="rounded-lg bg-slate-50 p-4">
          <div class="text-xs font-medium tracking-wide text-slate-500">{{ pick('已回收', 'Resolved') }}</div>
          <div class="mt-2 text-xl font-semibold text-slate-900">{{ analysis.status_counts?.resolved || 0 }}</div>
        </article>
      </div>
      <div class="rounded-lg border border-sky-100 bg-sky-50/80 px-4 py-3 text-sm leading-6 text-sky-800">
        {{ pick(
          '说明：这里只保留真正会影响创作推进的线索。若伏笔状态变化，这里会随之同步，不需要手工重复维护。',
          'Note: only clues that actually affect writing progress are kept here. Foreshadowing status changes sync automatically, so no manual upkeep is needed.'
        ) }}
      </div>
      <button class="w-full rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:border-slate-300 hover:text-slate-900" :disabled="loading" @click="reload">{{ pick('刷新线索', 'Refresh clues') }}</button>
      <div>
        <label class="mb-2 block text-sm font-medium text-slate-700">{{ pick('搜索', 'Search') }}</label>
        <input v-model="searchQuery" type="text" class="w-full rounded-lg border border-slate-200 px-4 py-2.5 text-sm outline-none transition focus:border-slate-400" :placeholder="pick('按名称、描述或类型搜索', 'Search by name, description, or type')" />
      </div>
      <div class="grid grid-cols-2 gap-2">
        <select v-model="filterType" class="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400">
          <option value="">{{ pick('全部类型', 'All types') }}</option>
          <option value="key_evidence">{{ pick('关键证物', 'Key evidence') }}</option>
          <option value="mysterious_event">{{ pick('神秘事件', 'Mysterious event') }}</option>
          <option value="character_secret">{{ pick('人物秘密', 'Character secret') }}</option>
          <option value="timeline">{{ pick('时间线', 'Timeline') }}</option>
          <option value="red_herring">{{ pick('红鲱鱼', 'Red herring') }}</option>
          <option value="plot_hook">{{ pick('剧情钩子', 'Plot hook') }}</option>
        </select>
        <select v-model="filterStatus" class="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400">
          <option value="">{{ pick('全部状态', 'All statuses') }}</option>
          <option value="active">{{ pick('推进中', 'Active') }}</option>
          <option value="resolved">{{ pick('已回收', 'Resolved') }}</option>
          <option value="red_herring">{{ pick('红鲱鱼', 'Red herring') }}</option>
          <option value="abandoned">{{ pick('已放弃', 'Abandoned') }}</option>
        </select>
      </div>
      <div class="space-y-2 overflow-y-auto xl:max-h-[calc(100vh-30rem)]">
        <button
          v-for="clue in filteredClues"
          :key="clue.id"
          class="w-full rounded-lg border px-4 py-3 text-left transition"
          :class="selectedClue?.id === clue.id ? 'border-sky-200 bg-sky-50' : 'border-slate-200 bg-slate-50/70 hover:border-slate-300 hover:bg-white'"
          @click="selectedClue = clue"
        >
          <div class="flex items-center justify-between gap-3">
            <div class="font-medium text-slate-900">{{ clue.name }}</div>
            <span class="rounded-full bg-white px-2 py-1 text-[11px] text-slate-500">{{ getStatusLabel(clue.status, clue.is_red_herring) }}</span>
          </div>
          <div class="mt-2 text-xs leading-5 text-slate-500 line-clamp-2">{{ clue.description || pick('暂无描述', 'No description') }}</div>
        </button>
        <div v-if="!filteredClues.length" class="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-center text-sm text-slate-500">{{ pick('暂无符合条件的线索', 'No clues match the filters') }}</div>
      </div>
    </aside>

    <div class="space-y-3 overflow-y-auto">
      <section class="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
        <div class="flex items-center justify-between gap-3">
          <div>
            <h4 class="text-base font-semibold text-slate-900">{{ pick('主线线程概览', 'Thread overview') }}</h4>
            <p class="mt-1 text-sm text-slate-500">{{ pick('自动把同类线索聚成线程，方便你判断哪些线索还在推进，哪些该尽快回收。', 'Clues of the same kind are grouped into threads so you can see which are still active and which need resolving soon.') }}</p>
          </div>
          <span class="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600">{{ pick(`${threads.length} 条线程`, `${threads.length} threads`) }}</span>
        </div>
        <div class="mt-4 grid gap-4 xl:grid-cols-2">
          <article v-for="(thread, index) in threads" :key="index" class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-4">
            <div class="text-sm font-semibold text-slate-900">{{ getTypeLabel(thread.thread_type) || pick(`线程 ${index + 1}`, `Thread ${index + 1}`) }}</div>
            <div class="mt-2 text-sm leading-6 text-slate-600">{{ pick('涉及线索编号：', 'Clue ids: ') }}{{ formatClueIds(thread.clue_ids) }}</div>
            <div class="mt-2 text-xs leading-5 text-slate-500">{{ pick('线索数量：', 'Clue count: ') }}{{ thread.clue_count }}</div>
          </article>
          <div v-if="!threads.length" class="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-8 text-sm text-slate-500">{{ pick('尚未生成线程分析结果。', 'No thread analysis yet.') }}</div>
        </div>
      </section>

      <section class="grid gap-4 xl:grid-cols-[1.05fr_0.95fr]">
        <article class="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
          <h4 class="text-base font-semibold text-slate-900">{{ pick('当前焦点线索', 'Focused clue') }}</h4>
          <div v-if="selectedClue" class="mt-4 space-y-4">
            <div>
              <div class="text-xl font-semibold text-slate-900">{{ selectedClue.name }}</div>
              <div class="mt-2 flex flex-wrap gap-2 text-xs text-slate-500">
                <span class="rounded-full bg-slate-100 px-2 py-1">{{ getTypeLabel(selectedClue.clue_type) }}</span>
                <span class="rounded-full bg-slate-100 px-2 py-1">{{ getStatusLabel(selectedClue.status, selectedClue.is_red_herring) }}</span>
                <span class="rounded-full bg-slate-100 px-2 py-1">{{ pick(`重要度 ${selectedClue.importance || 0}/5`, `Importance ${selectedClue.importance || 0}/5`) }}</span>
              </div>
            </div>
            <div class="rounded-lg bg-slate-50 p-4 text-sm leading-6 text-slate-700">{{ selectedClue.description || pick('暂无描述。', 'No description.') }}</div>
            <div class="grid gap-3 md:grid-cols-2">
              <div class="rounded-lg bg-slate-50 p-4 text-sm text-slate-700">
                <div class="font-medium text-slate-900">{{ pick('埋下章节', 'Planted in') }}</div>
                <div class="mt-2">{{ pick(`第 ${selectedClue.planted_chapter || '?'} 章`, `Chapter ${selectedClue.planted_chapter || '?'}`) }}</div>
              </div>
              <div class="rounded-lg bg-slate-50 p-4 text-sm text-slate-700">
                <div class="font-medium text-slate-900">{{ pick('回收章节', 'Resolved in') }}</div>
                <div class="mt-2">{{ selectedClue.resolution_chapter ? pick(`第 ${selectedClue.resolution_chapter} 章`, `Chapter ${selectedClue.resolution_chapter}`) : pick('尚未回收', 'Not resolved yet') }}</div>
              </div>
            </div>
            <div v-if="selectedClue.design_intent || selectedClue.clue_content" class="grid gap-3 md:grid-cols-2">
              <div class="rounded-lg bg-slate-50 p-4 text-sm leading-6 text-slate-700">
                <div class="font-medium text-slate-900">{{ pick('设计意图', 'Design intent') }}</div>
                <div class="mt-2">{{ selectedClue.design_intent || pick('暂无', 'None') }}</div>
              </div>
              <div class="rounded-lg bg-slate-50 p-4 text-sm leading-6 text-slate-700">
                <div class="font-medium text-slate-900">{{ pick('线索正文', 'Clue text') }}</div>
                <div class="mt-2">{{ selectedClue.clue_content || pick('暂无', 'None') }}</div>
              </div>
            </div>
          </div>
          <div v-else class="mt-4 rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-8 text-sm text-slate-500">{{ pick('左侧选一条线索，就能查看它的用途、状态和回收进度。', 'Pick a clue on the left to see its purpose, status, and resolution progress.') }}</div>
        </article>

        <article class="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
          <h4 class="text-base font-semibold text-slate-900">{{ pick('本轮最值得盯住的线索', 'Clues to watch now') }}</h4>
          <p class="mt-1 text-sm text-slate-500">{{ pick('按“未回收且重要”优先，减少主线丢失或红鲱鱼失控。', 'Sorted by unresolved and important first, so main threads do not get lost and red herrings stay under control.') }}</p>
          <div class="mt-4 space-y-3">
            <div v-for="clue in focusClues" :key="clue.id" class="rounded-lg border border-sky-100 bg-sky-50/70 px-4 py-3">
              <div class="flex items-center justify-between gap-3">
                <div class="text-sm font-medium text-slate-900">{{ clue.name }}</div>
                <span class="rounded-full bg-white px-2 py-1 text-[11px] text-slate-500">{{ pick(`第 ${clue.planted_chapter || '?'} 章埋下`, `Planted in chapter ${clue.planted_chapter || '?'}`) }}</span>
              </div>
              <div class="mt-2 text-sm leading-6 text-slate-600 line-clamp-2">{{ clue.description || pick('暂无描述', 'No description') }}</div>
            </div>
            <div v-if="!focusClues.length" class="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-500">{{ pick('当前没有高风险线索。', 'No high-risk clues right now.') }}</div>
          </div>
        </article>
      </section>

      <section v-if="error" class="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{{ error }}</section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ClueTrackerAPI, type ClueItem, type ClueThreadAnalysisResponse } from '@/api/novel'
import { useLocale } from '@/composables/useLocale'

const props = defineProps<{ projectId: string }>()

const { pick } = useLocale()

const loading = ref(false)
const error = ref('')
const clues = ref<ClueItem[]>([])
const analysis = ref<ClueThreadAnalysisResponse>({
  project_id: '',
  total_clues: 0,
  type_counts: {},
  status_counts: {},
  red_herring_count: 0,
  unresolved_count: 0,
  threads: [],
})
const searchQuery = ref('')
const filterType = ref('')
const filterStatus = ref('')
const selectedClue = ref<ClueItem | null>(null)

const threads = computed(() => analysis.value.threads)
const filteredClues = computed(() => {
  const keyword = searchQuery.value.trim().toLowerCase()
  return clues.value.filter((clue) => {
    const matchKeyword = !keyword || [clue.name, clue.description, clue.clue_type].some((value) => String(value || '').toLowerCase().includes(keyword))
    const matchType = !filterType.value || clue.clue_type === filterType.value
    const matchStatus = !filterStatus.value || clue.status === filterStatus.value || (filterStatus.value === 'red_herring' && clue.is_red_herring)
    return matchKeyword && matchType && matchStatus
  })
})
const focusClues = computed(() => clues.value.filter((clue) => !clue.resolution_chapter && !clue.is_red_herring).sort((a, b) => (b.importance || 0) - (a.importance || 0)).slice(0, 8))

// 类型 / 状态映射表放在函数体内，切换语言时随调用重新求值；键名是后端枚举，不翻译
const getTypeLabel = (type: string) => ({
  key_evidence: pick('关键证物', 'Key evidence'),
  mysterious_event: pick('神秘事件', 'Mysterious event'),
  character_secret: pick('人物秘密', 'Character secret'),
  timeline: pick('时间线', 'Timeline'),
  red_herring: pick('红鲱鱼', 'Red herring'),
  plot_hook: pick('剧情钩子', 'Plot hook'),
} as Record<string, string>)[type] || type || pick('未分类', 'Uncategorized')
const formatClueIds = (ids: number[]) => ids.map((id: number) => `#${id}`).join(pick('、', ', ')) || pick('暂无', 'None')
const getStatusLabel = (status: string, isRedHerring = false) => isRedHerring ? pick('红鲱鱼', 'Red herring') : ({
  active: pick('推进中', 'Active'),
  resolved: pick('已回收', 'Resolved'),
  abandoned: pick('已放弃', 'Abandoned'),
  red_herring: pick('红鲱鱼', 'Red herring'),
} as Record<string, string>)[status] || status || pick('未标记', 'Unmarked')

const loadData = async () => {
  if (!props.projectId) return
  loading.value = true
  error.value = ''
  try {
    const snapshot = await ClueTrackerAPI.getOverview(props.projectId)
    const selectedClueId = selectedClue.value?.id
    clues.value = snapshot.clues
    analysis.value = snapshot.analysis
    selectedClue.value = selectedClueId == null
      ? clues.value[0] || null
      : clues.value.find((item) => item.id === selectedClueId) || clues.value[0] || null
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : pick('加载线索追踪失败', 'Failed to load the clue tracker')
  } finally {
    loading.value = false
  }
}

const reload = () => { void loadData() }

onMounted(loadData)
watch(() => props.projectId, (value) => { if (value) void loadData() })
</script>
