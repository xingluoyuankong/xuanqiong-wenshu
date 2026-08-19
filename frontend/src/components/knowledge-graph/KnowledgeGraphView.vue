<template>
  <div class="knowledge-graph-page grid h-full gap-4 xl:grid-cols-[260px_minmax(0,1fr)]">
    <aside class="space-y-3 rounded-xl border border-slate-200 bg-white p-3.5 shadow-sm">
      <div>
        <h3 class="text-base font-semibold text-slate-900">{{ pick('知识图谱', 'Knowledge graph') }}</h3>
        <p class="mt-1 text-xs leading-5 text-slate-600">
          {{ pick(
            '自动从蓝图角色、记忆层状态和共同事件同步，重点是帮你看清“谁在推动哪条线”。',
            'Synced automatically from blueprint characters, memory-layer state, and shared events, so you can see who drives which thread.'
          ) }}
        </p>
      </div>
      <div class="grid gap-2 sm:grid-cols-3 xl:grid-cols-1">
        <article class="rounded-lg bg-slate-50 p-3">
          <div class="text-xs font-medium tracking-wide text-slate-500">{{ pick('角色节点', 'Character nodes') }}</div>
          <div class="mt-1.5 text-xl font-semibold text-slate-900">{{ graph.node_count || 0 }}</div>
        </article>
        <article class="rounded-lg bg-slate-50 p-3">
          <div class="text-xs font-medium tracking-wide text-slate-500">{{ pick('关系边', 'Relation edges') }}</div>
          <div class="mt-1.5 text-xl font-semibold text-slate-900">{{ graph.edge_count || 0 }}</div>
        </article>
        <article class="rounded-lg bg-slate-50 p-3">
          <div class="text-xs font-medium tracking-wide text-slate-500">{{ pick('剧情线', 'Plot threads') }}</div>
          <div class="mt-1.5 text-xl font-semibold text-slate-900">{{ plotThreads.length }}</div>
        </article>
      </div>
      <div class="rounded-lg border border-sky-100 bg-sky-50/80 px-3 py-2 text-xs leading-6 text-sky-800">
        {{ pick(
          '说明：图谱用于查关系与来源证据；角色“当前事实”仍以记忆层/故事账本为准。每次进入页面都会先同步角色状态、时间线和因果边。',
          'Note: the graph is for relations and source evidence; a character’s current facts still come from the memory layer / story ledger. Entering this page always syncs character state, timeline, and causal edges first.'
        ) }}
      </div>
      <div class="flex gap-2">
        <button class="flex-1 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:border-slate-300 hover:text-slate-900" :disabled="loading" @click="reload">{{ pick('刷新图谱', 'Refresh graph') }}</button>
        <button class="flex-1 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:border-slate-300 hover:text-slate-900" :disabled="loading" @click="reload">{{ pick('分析剧情线', 'Analyze plot threads') }}</button>
      </div>
      <div>
        <label class="mb-1.5 block text-sm font-medium text-slate-700">{{ pick('搜索角色', 'Search characters') }}</label>
        <input v-model="search" type="text" class="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none transition focus:border-slate-400" :placeholder="pick('输入角色名或角色类型', 'Enter a character name or type')" />
      </div>
      <div class="space-y-2 overflow-y-auto xl:max-h-[calc(100vh-28rem)]">
        <button
          v-for="node in filteredNodes"
          :key="node.id"
          class="w-full rounded-lg border px-4 py-3 text-left transition"
          :class="selectedNode?.id === node.id ? 'border-sky-200 bg-sky-50' : 'border-slate-200 bg-slate-50/70 hover:border-slate-300 hover:bg-white'"
          @click="selectNode(node)"
        >
          <div class="flex items-center justify-between gap-2">
            <div class="font-medium text-slate-900">{{ node.name }}</div>
            <span class="rounded-full bg-white px-2 py-1 text-[11px] text-slate-500">{{ node.role_type || pick('未分类', 'Uncategorized') }}</span>
          </div>
          <div class="mt-1.5 text-xs leading-5 text-slate-500 line-clamp-2">{{ node.description || pick('暂无角色描述', 'No character description yet') }}</div>
          <div class="mt-1.5 flex flex-wrap gap-1.5 text-[11px] text-slate-500">
            <span class="rounded-full bg-white px-2 py-0.5">{{ formatLifecycle(node.lifecycle) }}</span>
            <span class="rounded-full bg-white px-2 py-0.5">{{ formatNodeChapterLabel(node) }}</span>
            <span class="rounded-full bg-white px-2 py-0.5">{{ formatConfidence(node.confidence) }}</span>
          </div>
        </button>
        <div v-if="!filteredNodes.length" class="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-center text-sm text-slate-500">{{ pick('暂无可展示角色', 'No characters to show') }}</div>
      </div>
    </aside>

    <div class="space-y-5 overflow-y-auto">
      <section class="rounded-xl border border-slate-200 bg-white p-3.5 shadow-sm">
        <div class="flex items-center justify-between gap-2">
          <div>
            <h4 class="text-base font-semibold text-slate-900">{{ pick('当前焦点角色', 'Current focus character') }}</h4>
            <p class="mt-1 text-sm text-slate-500">{{ pick('选中一个角色后，右侧会展示其目标、特征与关键关系。', 'Select a character to see their goals, traits, and key relations here.') }}</p>
          </div>
          <span class="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600">{{ pick('自动同步数据', 'Auto-synced data') }}</span>
        </div>
        <div v-if="selectedNode" class="mt-3 grid gap-2 xl:grid-cols-[1.05fr_0.95fr]">
          <article class="rounded-lg bg-slate-50 p-3">
            <div class="text-xl font-semibold text-slate-900">{{ selectedNode.name }}</div>
            <div class="mt-1.5 flex flex-wrap gap-2 text-xs text-slate-500">
              <span class="rounded-full bg-white px-2 py-1">{{ selectedNode.role_type || pick('未分类角色', 'Uncategorized character') }}</span>
              <span class="rounded-full bg-white px-2 py-1">{{ pick('状态：', 'Status: ') }}{{ selectedNode.status || pick('未标记', 'Unmarked') }}</span>
              <span class="rounded-full bg-white px-2 py-1">{{ pick('来源：', 'Source: ') }}{{ formatFactSource(selectedNode) }}</span>
              <span class="rounded-full bg-white px-2 py-1">{{ formatConfidence(selectedNode.confidence) }}</span>
            </div>
            <p class="mt-3 text-xs leading-5 text-slate-700">{{ selectedNode.description || pick('暂无角色描述。', 'No character description yet.') }}</p>
            <div class="mt-3 grid gap-2 sm:grid-cols-2">
              <div v-for="item in selectedNodeFactRows" :key="item.label" class="rounded-lg border border-slate-200 bg-white px-3 py-2">
                <div class="text-[11px] uppercase tracking-wide text-slate-400">{{ item.label }}</div>
                <div class="mt-1 text-sm font-medium text-slate-700">{{ item.value }}</div>
              </div>
            </div>
            <div class="mt-3 grid gap-2 md:grid-cols-2">
              <div>
                <div class="text-sm font-medium text-slate-800">{{ pick('性格特征', 'Personality traits') }}</div>
                <div class="mt-1.5 flex flex-wrap gap-2">
                  <span v-for="trait in selectedNode.traits || []" :key="trait" class="rounded-full bg-white px-2.5 py-1 text-xs text-slate-600">{{ trait }}</span>
                  <span v-if="!(selectedNode.traits || []).length" class="text-sm text-slate-500">{{ pick('暂无', 'None') }}</span>
                </div>
              </div>
              <div>
                <div class="text-sm font-medium text-slate-800">{{ pick('目标 / 动机', 'Goals / motivation') }}</div>
                <div class="mt-1.5 flex flex-wrap gap-2">
                  <span v-for="goal in selectedNode.goals || []" :key="goal" class="rounded-full bg-white px-2.5 py-1 text-xs text-slate-600">{{ goal }}</span>
                  <span v-if="!(selectedNode.goals || []).length" class="text-sm text-slate-500">{{ pick('暂无', 'None') }}</span>
                </div>
              </div>
            </div>
          </article>
          <article class="rounded-lg bg-slate-50 p-3">
            <div class="text-sm font-medium text-slate-800">{{ pick('与其强关联的角色 / 事件', 'Strongly linked characters / events') }}</div>
            <div class="mt-3 space-y-3">
              <div v-for="edge in selectedNodeEdges" :key="edge.id" class="rounded-lg border border-slate-200 bg-white px-4 py-3">
                <div class="flex items-center justify-between gap-2">
                  <div class="text-sm font-medium text-slate-900">{{ edge.source_name }} → {{ edge.target_name }}</div>
                  <span class="rounded-full bg-slate-100 px-2 py-1 text-[11px] text-slate-500">{{ edge.event_type }}</span>
                </div>
                <div class="mt-1.5 text-xs leading-5 text-slate-600">{{ edge.description || pick('暂无事件描述', 'No event description yet') }}</div>
                <div class="mt-1.5 text-xs text-slate-500">{{ formatEdgeFactLine(edge) }} · {{ pick(`重要度 ${edge.importance || 0}/10`, `Importance ${edge.importance || 0}/10`) }}</div>
              </div>
              <div v-if="!selectedNodeEdges.length" class="rounded-lg border border-dashed border-slate-200 bg-white px-4 py-6 text-sm text-slate-500">{{ pick('当前没有与该角色绑定的关系边。', 'No relation edges are bound to this character yet.') }}</div>
            </div>
          </article>
        </div>
        <div v-else class="mt-3 rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-8 text-sm text-slate-500">{{ pick('左侧选一个角色，就能看见它在当前故事里的位置与关系网。', 'Pick a character on the left to see where they sit in the current story and who they connect to.') }}</div>
      </section>

      <section class="grid gap-2 xl:grid-cols-[1fr_1fr]">
        <article class="rounded-xl border border-slate-200 bg-white p-3.5 shadow-sm">
          <h4 class="text-base font-semibold text-slate-900">{{ pick('最强关系边', 'Strongest relation edges') }}</h4>
          <p class="mt-1 text-sm text-slate-500">{{ pick('按重要度排序，帮助快速定位谁在推动主线冲突。', 'Sorted by importance so you can quickly spot who drives the main conflict.') }}</p>
          <div class="mt-3 space-y-3">
            <div v-for="edge in topEdges" :key="edge.id" class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
              <div class="flex items-center justify-between gap-2">
                <div class="text-sm font-medium text-slate-900">{{ edge.source_name }} → {{ edge.target_name }}</div>
                <span class="rounded-full bg-white px-2 py-1 text-[11px] text-slate-500">{{ edge.event_type || pick('关系', 'Relation') }}</span>
              </div>
              <div class="mt-1.5 text-xs leading-5 text-slate-600 line-clamp-2">{{ edge.description || pick('暂无说明', 'No description yet') }}</div>
              <div class="mt-1.5 text-xs text-slate-500">{{ formatEdgeFactLine(edge) }}</div>
            </div>
            <div v-if="!topEdges.length" class="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-500">{{ pick('暂无关系边数据。', 'No relation edge data yet.') }}</div>
          </div>
        </article>

        <article class="rounded-xl border border-slate-200 bg-white p-3.5 shadow-sm">
          <h4 class="text-base font-semibold text-slate-900">{{ pick('剧情线索分组', 'Plot thread grouping') }}</h4>
          <p class="mt-1 text-sm text-slate-500">{{ pick('自动把同一批角色参与的关系边聚成“剧情线”，方便判断有哪些主线正在并行。', 'Relation edges sharing the same cast are grouped into plot threads, so you can tell which storylines run in parallel.') }}</p>
          <div class="mt-3 space-y-3">
            <div v-for="(thread, index) in plotThreads" :key="index" class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
              <div class="text-sm font-medium text-slate-900">{{ thread.title || pick(`剧情线 ${index + 1}`, `Plot thread ${index + 1}`) }}</div>
              <div class="mt-1.5 text-xs leading-5 text-slate-500">{{ pick('涉及角色：', 'Characters involved: ') }}{{ (thread.characters || []).join(pick('、', ', ')) || pick('暂无', 'None') }}</div>
              <div class="mt-1 text-xs leading-5 text-slate-500">{{ pick('关键事件：', 'Key events: ') }}{{ formatThreadEvents(thread.events) || pick('暂无', 'None') }}</div>
            </div>
            <div v-if="!plotThreads.length" class="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-500">{{ pick('尚未生成剧情线分析结果。', 'No plot thread analysis has been generated yet.') }}</div>
          </div>
        </article>
      </section>

      <section v-if="error" class="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">{{ error }}</section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { KnowledgeGraphAPI, type KnowledgeGraphEdge, type KnowledgeGraphNode, type KnowledgeGraphResponse, type PlotThread, type PlotThreadEvent } from '@/api/novel'
import { useLocale } from '@/composables/useLocale'

const props = defineProps<{ projectId?: string }>()

const { pick } = useLocale()

const loading = ref(false)
const error = ref('')
const graph = ref<KnowledgeGraphResponse>({ project_id: '', nodes: [], edges: [], node_count: 0, edge_count: 0 })
const plotThreads = ref<PlotThread[]>([])
const selectedNode = ref<KnowledgeGraphNode | null>(null)
const search = ref('')

const projectId = computed(() => props.projectId || '')
const nodes = computed(() => graph.value.nodes)
const edges = computed(() => graph.value.edges)

// 键是后端 fact_source 枚举保持原文；值在函数体内经 pick 求值，切换语言即刷新
const factSourceLabelMap = (): Record<string, string> => ({
  blueprint_character: pick('蓝图角色', 'Blueprint character'),
  dynamic_character: pick('动态角色入池', 'Dynamic character intake'),
  chapter_state: pick('章节状态', 'Chapter state'),
  timeline_event: pick('时间线事件', 'Timeline event'),
  blueprint_relationship: pick('蓝图关系', 'Blueprint relationship'),
  causal_chain: pick('因果链', 'Causal chain'),
  manual: pick('手工补充', 'Manually added'),
})

// 键是后端 lifecycle 枚举保持原文
const lifecycleLabelMap = (): Record<string, string> => ({
  active: pick('活跃追踪', 'Actively tracked'),
  dynamic: pick('动态入池', 'Dynamic intake'),
  ended: pick('已退场', 'Exited'),
  planned: pick('规划中', 'Planned'),
  tracked: pick('已追踪', 'Tracked'),
  manual: pick('手工补充', 'Manually added'),
})

const formatChapter = (value: unknown) => {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed > 0
    ? pick(`第 ${parsed} 章`, `Chapter ${parsed}`)
    : pick('未标记', 'Unmarked')
}

const formatConfidence = (value: unknown) => {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return pick('置信度未标记', 'Confidence unmarked')
  const percent = Math.max(0, Math.min(100, Math.round(parsed)))
  return pick(`置信度 ${percent}%`, `Confidence ${percent}%`)
}

const formatLifecycle = (value: unknown) => {
  const key = String(value || '').trim()
  return lifecycleLabelMap()[key] || key || pick('未标记生命周期', 'Lifecycle unmarked')
}

const formatFactSource = (item: Pick<KnowledgeGraphNode, 'fact_source' | 'fact_source_label'> | Pick<KnowledgeGraphEdge, 'fact_source' | 'fact_source_label'>) => {
  const key = String(item.fact_source || '').trim()
  return item.fact_source_label || factSourceLabelMap()[key] || key || pick('未标记来源', 'Source unmarked')
}

const formatNodeChapterLabel = (node: KnowledgeGraphNode) => {
  if (node?.first_chapter && node?.latest_chapter && node.first_chapter !== node.latest_chapter) {
    return pick(`第 ${node.first_chapter}-${node.latest_chapter} 章`, `Chapters ${node.first_chapter}-${node.latest_chapter}`)
  }
  if (node?.latest_chapter) return pick(`最新第 ${node.latest_chapter} 章`, `Latest chapter ${node.latest_chapter}`)
  if (node?.first_chapter) return pick(`首见第 ${node.first_chapter} 章`, `First seen in chapter ${node.first_chapter}`)
  return pick('章节未标记', 'Chapter unmarked')
}

const formatEdgeFactLine = (edge: KnowledgeGraphEdge) => {
  const parts = [
    formatFactSource(edge),
    edge.source_chapter ? pick(`来源${formatChapter(edge.source_chapter)}`, `From ${formatChapter(edge.source_chapter)}`) : '',
    edge.latest_chapter ? pick(`最新${formatChapter(edge.latest_chapter)}`, `Latest ${formatChapter(edge.latest_chapter)}`) : '',
    formatConfidence(edge.confidence),
  ].filter(Boolean)
  return parts.join(' · ')
}

const filteredNodes = computed(() => {
  const keyword = search.value.trim().toLowerCase()
  if (!keyword) return nodes.value
  return nodes.value.filter((node) => [node.name, node.role_type, node.description].some((value) => String(value || '').toLowerCase().includes(keyword)))
})

const selectedNodeEdges = computed(() => {
  const node = selectedNode.value
  if (!node) return []
  return edges.value.filter((edge) => edge.source_id === node.id || edge.target_id === node.id)
    .sort((a, b) => (b.importance || 0) - (a.importance || 0))
    .slice(0, 8)
})

const topEdges = computed(() => edges.value.slice().sort((a, b) => (b.importance || 0) - (a.importance || 0)).slice(0, 8))

const selectedNodeFactRows = computed(() => {
  const node = selectedNode.value
  if (!node) return []
  return [
    { label: pick('来源', 'Source'), value: formatFactSource(node) },
    { label: pick('生命周期', 'Lifecycle'), value: formatLifecycle(node.lifecycle) },
    { label: pick('首次登场/引用', 'First appearance / mention'), value: formatChapter(node.first_chapter) },
    { label: pick('最新状态章节', 'Latest state chapter'), value: formatChapter(node.latest_chapter) },
    { label: pick('关系边数量', 'Relation edge count'), value: pick(`${Number(node.relationship_count || 0)} 条`, `${Number(node.relationship_count || 0)} edges`) },
    { label: pick('事实置信度', 'Fact confidence'), value: formatConfidence(node.confidence) },
  ]
})

const formatThreadEvents = (events?: PlotThreadEvent[]) => (events || [])
  .map(event => typeof event.description === 'string' ? event.description : '')
  .filter(Boolean)
  .join(pick('、', ', '))

const selectNode = (node: KnowledgeGraphNode) => {
  selectedNode.value = node
}

const loadSnapshot = async () => {
  if (!projectId.value) return
  loading.value = true
  error.value = ''
  try {
    const selectedNodeId = selectedNode.value?.id
    const snapshot = await KnowledgeGraphAPI.getOverview(projectId.value)
    graph.value = snapshot.graph
    plotThreads.value = snapshot.threads
    selectedNode.value = selectedNodeId == null
      ? nodes.value[0] || null
      : nodes.value.find((node) => node.id === selectedNodeId) || nodes.value[0] || null
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : pick('加载知识图谱失败', 'Failed to load the knowledge graph')
  } finally {
    loading.value = false
  }
}

const reload = () => { void loadSnapshot() }

onMounted(loadSnapshot)
watch(projectId, (value) => { if (value) void loadSnapshot() })
</script>
