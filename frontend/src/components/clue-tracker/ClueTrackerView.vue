<template>
  <div class="grid h-full gap-5 xl:grid-cols-[320px_minmax(0,1fr)]">
    <aside class="space-y-4 rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
      <div>
        <h3 class="text-lg font-semibold text-slate-900">线索追踪</h3>
        <p class="mt-1 text-sm leading-6 text-slate-600">
          自动从伏笔系统同步到线索工作台，用来判断主线、误导线和待回收线索现在推进到了哪里。
        </p>
      </div>
      <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
        <article class="rounded-2xl bg-slate-50 p-4">
          <div class="text-xs font-medium tracking-wide text-slate-500">总线索数</div>
          <div class="mt-2 text-2xl font-semibold text-slate-900">{{ analysis.total_clues || clues.length }}</div>
        </article>
        <article class="rounded-2xl bg-slate-50 p-4">
          <div class="text-xs font-medium tracking-wide text-slate-500">待回收主线</div>
          <div class="mt-2 text-2xl font-semibold text-slate-900">{{ analysis.unresolved_count || 0 }}</div>
        </article>
        <article class="rounded-2xl bg-slate-50 p-4">
          <div class="text-xs font-medium tracking-wide text-slate-500">红鲱鱼</div>
          <div class="mt-2 text-2xl font-semibold text-slate-900">{{ analysis.red_herring_count || 0 }}</div>
        </article>
        <article class="rounded-2xl bg-slate-50 p-4">
          <div class="text-xs font-medium tracking-wide text-slate-500">已回收</div>
          <div class="mt-2 text-2xl font-semibold text-slate-900">{{ analysis.status_counts?.resolved || 0 }}</div>
        </article>
      </div>
      <div class="rounded-2xl border border-sky-100 bg-sky-50/80 px-4 py-3 text-sm leading-6 text-sky-800">
        说明：这里只保留真正会影响创作推进的线索。若伏笔状态变化，这里会随之同步，不需要手工重复维护。
      </div>
      <button class="w-full rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:border-slate-300 hover:text-slate-900" :disabled="loading" @click="reload">刷新线索</button>
      <div>
        <label class="mb-2 block text-sm font-medium text-slate-700">搜索</label>
        <input v-model="searchQuery" type="text" class="w-full rounded-2xl border border-slate-200 px-4 py-2.5 text-sm outline-none transition focus:border-slate-400" placeholder="按名称、描述或类型搜索" />
      </div>
      <div class="grid grid-cols-2 gap-2">
        <select v-model="filterType" class="rounded-2xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400">
          <option value="">全部类型</option>
          <option value="key_evidence">关键证物</option>
          <option value="mysterious_event">神秘事件</option>
          <option value="character_secret">人物秘密</option>
          <option value="timeline">时间线</option>
          <option value="red_herring">红鲱鱼</option>
          <option value="plot_hook">剧情钩子</option>
        </select>
        <select v-model="filterStatus" class="rounded-2xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400">
          <option value="">全部状态</option>
          <option value="active">推进中</option>
          <option value="resolved">已回收</option>
          <option value="red_herring">红鲱鱼</option>
          <option value="abandoned">已放弃</option>
        </select>
      </div>
      <div class="space-y-2 overflow-y-auto xl:max-h-[calc(100vh-30rem)]">
        <button
          v-for="clue in filteredClues"
          :key="clue.id"
          class="w-full rounded-2xl border px-4 py-3 text-left transition"
          :class="selectedClue?.id === clue.id ? 'border-sky-200 bg-sky-50' : 'border-slate-200 bg-slate-50/70 hover:border-slate-300 hover:bg-white'"
          @click="selectedClue = clue"
        >
          <div class="flex items-center justify-between gap-3">
            <div class="font-medium text-slate-900">{{ clue.name }}</div>
            <span class="rounded-full bg-white px-2 py-1 text-[11px] text-slate-500">{{ getStatusLabel(clue.status, clue.is_red_herring) }}</span>
          </div>
          <div class="mt-2 text-xs leading-5 text-slate-500 line-clamp-2">{{ clue.description || '暂无描述' }}</div>
        </button>
        <div v-if="!filteredClues.length" class="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-center text-sm text-slate-500">暂无符合条件的线索</div>
      </div>
    </aside>

    <div class="space-y-5 overflow-y-auto">
      <section class="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
        <div class="flex items-center justify-between gap-3">
          <div>
            <h4 class="text-base font-semibold text-slate-900">主线线程概览</h4>
            <p class="mt-1 text-sm text-slate-500">自动把同类线索聚成线程，方便你判断哪些线索还在推进，哪些该尽快回收。</p>
          </div>
          <span class="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600">{{ threads.length }} 条线程</span>
        </div>
        <div class="mt-4 grid gap-4 xl:grid-cols-2">
          <article v-for="(thread, index) in threads" :key="index" class="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4">
            <div class="text-sm font-semibold text-slate-900">{{ thread.thread_name || `线程 ${index + 1}` }}</div>
            <div class="mt-2 text-sm leading-6 text-slate-600">涉及线索：{{ (thread.clue_names || thread.clues || []).join('、') || '暂无' }}</div>
            <div class="mt-2 text-xs leading-5 text-slate-500">状态分布：{{ Object.entries(thread.status_counts || {}).map(([key, value]) => `${getStatusLabel(String(key), String(key) === 'red_herring')}:${value}`).join('，') || '暂无' }}</div>
          </article>
          <div v-if="!threads.length" class="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-8 text-sm text-slate-500">尚未生成线程分析结果。</div>
        </div>
      </section>

      <section class="grid gap-4 xl:grid-cols-[1.05fr_0.95fr]">
        <article class="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <h4 class="text-base font-semibold text-slate-900">当前焦点线索</h4>
          <div v-if="selectedClue" class="mt-4 space-y-4">
            <div>
              <div class="text-xl font-semibold text-slate-900">{{ selectedClue.name }}</div>
              <div class="mt-2 flex flex-wrap gap-2 text-xs text-slate-500">
                <span class="rounded-full bg-slate-100 px-2 py-1">{{ getTypeLabel(selectedClue.clue_type) }}</span>
                <span class="rounded-full bg-slate-100 px-2 py-1">{{ getStatusLabel(selectedClue.status, selectedClue.is_red_herring) }}</span>
                <span class="rounded-full bg-slate-100 px-2 py-1">重要度 {{ selectedClue.importance || 0 }}/5</span>
              </div>
            </div>
            <div class="rounded-2xl bg-slate-50 p-4 text-sm leading-6 text-slate-700">{{ selectedClue.description || '暂无描述。' }}</div>
            <div class="grid gap-3 md:grid-cols-2">
              <div class="rounded-2xl bg-slate-50 p-4 text-sm text-slate-700">
                <div class="font-medium text-slate-900">埋下章节</div>
                <div class="mt-2">第 {{ selectedClue.planted_chapter || '?' }} 章</div>
              </div>
              <div class="rounded-2xl bg-slate-50 p-4 text-sm text-slate-700">
                <div class="font-medium text-slate-900">回收章节</div>
                <div class="mt-2">{{ selectedClue.resolution_chapter ? `第 ${selectedClue.resolution_chapter} 章` : '尚未回收' }}</div>
              </div>
            </div>
            <div v-if="selectedClue.design_intent || selectedClue.clue_content" class="grid gap-3 md:grid-cols-2">
              <div class="rounded-2xl bg-slate-50 p-4 text-sm leading-6 text-slate-700">
                <div class="font-medium text-slate-900">设计意图</div>
                <div class="mt-2">{{ selectedClue.design_intent || '暂无' }}</div>
              </div>
              <div class="rounded-2xl bg-slate-50 p-4 text-sm leading-6 text-slate-700">
                <div class="font-medium text-slate-900">线索正文</div>
                <div class="mt-2">{{ selectedClue.clue_content || '暂无' }}</div>
              </div>
            </div>
          </div>
          <div v-else class="mt-4 rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-8 text-sm text-slate-500">左侧选一条线索，就能查看它的用途、状态和回收进度。</div>
        </article>

        <article class="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <h4 class="text-base font-semibold text-slate-900">本轮最值得盯住的线索</h4>
          <p class="mt-1 text-sm text-slate-500">按“未回收且重要”优先，减少主线丢失或红鲱鱼失控。</p>
          <div class="mt-4 space-y-3">
            <div v-for="clue in focusClues" :key="clue.id" class="rounded-2xl border border-amber-100 bg-amber-50/70 px-4 py-3">
              <div class="flex items-center justify-between gap-3">
                <div class="text-sm font-medium text-slate-900">{{ clue.name }}</div>
                <span class="rounded-full bg-white px-2 py-1 text-[11px] text-slate-500">第 {{ clue.planted_chapter || '?' }} 章埋下</span>
              </div>
              <div class="mt-2 text-sm leading-6 text-slate-600 line-clamp-2">{{ clue.description || '暂无描述' }}</div>
            </div>
            <div v-if="!focusClues.length" class="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-500">当前没有高风险线索。</div>
          </div>
        </article>
      </section>

      <section v-if="error" class="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{{ error }}</section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ClueTrackerAPI } from '@/api/novel'

const props = defineProps<{ projectId: string }>()

const loading = ref(false)
const error = ref('')
const clues = ref<any[]>([])
const analysis = ref<any>({})
const searchQuery = ref('')
const filterType = ref('')
const filterStatus = ref('')
const selectedClue = ref<any | null>(null)

const threads = computed(() => Array.isArray(analysis.value?.threads) ? analysis.value.threads : [])
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

const getTypeLabel = (type: string) => ({ key_evidence: '关键证物', mysterious_event: '神秘事件', character_secret: '人物秘密', timeline: '时间线', red_herring: '红鲱鱼', plot_hook: '剧情钩子' } as Record<string, string>)[type] || type || '未分类'
const getStatusLabel = (status: string, isRedHerring = false) => isRedHerring ? '红鲱鱼' : ({ active: '推进中', resolved: '已回收', abandoned: '已放弃', red_herring: '红鲱鱼' } as Record<string, string>)[status] || status || '未标记'

const loadData = async () => {
  if (!props.projectId) return
  loading.value = true
  error.value = ''
  try {
    const [clueList, clueAnalysis] = await Promise.all([
      ClueTrackerAPI.getProjectClues(props.projectId),
      ClueTrackerAPI.analyzeClueThreads(props.projectId)
    ])
    clues.value = clueList || []
    analysis.value = clueAnalysis || {}
    selectedClue.value = selectedClue.value ? clues.value.find((item) => item.id === selectedClue.value.id) || clues.value[0] || null : clues.value[0] || null
  } catch (err: any) {
    error.value = err instanceof Error ? err.message : '加载线索追踪失败'
  } finally {
    loading.value = false
  }
}

const reload = () => { void loadData() }

onMounted(loadData)
watch(() => props.projectId, (value) => { if (value) void loadData() })
</script>
