<template>
  <div class="grid h-full gap-5 xl:grid-cols-[300px_minmax(0,1fr)]">
    <aside class="space-y-4 rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
      <div>
        <h3 class="text-lg font-semibold text-slate-900">知识图谱</h3>
        <p class="mt-1 text-sm leading-6 text-slate-600">
          自动从蓝图角色、记忆层状态和共同事件同步，重点是帮你看清“谁在推动哪条线”。
        </p>
      </div>
      <div class="grid gap-3 sm:grid-cols-3 xl:grid-cols-1">
        <article class="rounded-2xl bg-slate-50 p-4">
          <div class="text-xs font-medium tracking-wide text-slate-500">角色节点</div>
          <div class="mt-2 text-2xl font-semibold text-slate-900">{{ graph.node_count || 0 }}</div>
        </article>
        <article class="rounded-2xl bg-slate-50 p-4">
          <div class="text-xs font-medium tracking-wide text-slate-500">关系边</div>
          <div class="mt-2 text-2xl font-semibold text-slate-900">{{ graph.edge_count || 0 }}</div>
        </article>
        <article class="rounded-2xl bg-slate-50 p-4">
          <div class="text-xs font-medium tracking-wide text-slate-500">剧情线</div>
          <div class="mt-2 text-2xl font-semibold text-slate-900">{{ plotThreads.length }}</div>
        </article>
      </div>
      <div class="rounded-2xl border border-sky-100 bg-sky-50/80 px-4 py-3 text-sm leading-6 text-sky-800">
        说明：这里不是静态图。每次进入页面都会先从角色状态与时间线自动同步，再展示关系图谱。
      </div>
      <div class="flex gap-2">
        <button class="flex-1 rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:border-slate-300 hover:text-slate-900" :disabled="loading" @click="reload">刷新图谱</button>
        <button class="flex-1 rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:border-slate-300 hover:text-slate-900" :disabled="loading" @click="loadThreads">分析剧情线</button>
      </div>
      <div>
        <label class="mb-2 block text-sm font-medium text-slate-700">搜索角色</label>
        <input v-model="search" type="text" class="w-full rounded-2xl border border-slate-200 px-4 py-2.5 text-sm outline-none transition focus:border-slate-400" placeholder="输入角色名或角色类型" />
      </div>
      <div class="space-y-2 overflow-y-auto xl:max-h-[calc(100vh-28rem)]">
        <button
          v-for="node in filteredNodes"
          :key="node.id"
          class="w-full rounded-2xl border px-4 py-3 text-left transition"
          :class="selectedNode?.id === node.id ? 'border-sky-200 bg-sky-50' : 'border-slate-200 bg-slate-50/70 hover:border-slate-300 hover:bg-white'"
          @click="selectNode(node)"
        >
          <div class="flex items-center justify-between gap-3">
            <div class="font-medium text-slate-900">{{ node.name }}</div>
            <span class="rounded-full bg-white px-2 py-1 text-[11px] text-slate-500">{{ node.role_type || '未分类' }}</span>
          </div>
          <div class="mt-2 text-xs leading-5 text-slate-500 line-clamp-2">{{ node.description || '暂无角色描述' }}</div>
        </button>
        <div v-if="!filteredNodes.length" class="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-center text-sm text-slate-500">暂无可展示角色</div>
      </div>
    </aside>

    <div class="space-y-5 overflow-y-auto">
      <section class="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
        <div class="flex items-center justify-between gap-3">
          <div>
            <h4 class="text-base font-semibold text-slate-900">当前焦点角色</h4>
            <p class="mt-1 text-sm text-slate-500">选中一个角色后，右侧会展示其目标、特征与关键关系。</p>
          </div>
          <span class="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600">自动同步数据</span>
        </div>
        <div v-if="selectedNode" class="mt-4 grid gap-4 xl:grid-cols-[1.05fr_0.95fr]">
          <article class="rounded-2xl bg-slate-50 p-4">
            <div class="text-xl font-semibold text-slate-900">{{ selectedNode.name }}</div>
            <div class="mt-2 flex flex-wrap gap-2 text-xs text-slate-500">
              <span class="rounded-full bg-white px-2 py-1">{{ selectedNode.role_type || '未分类角色' }}</span>
              <span class="rounded-full bg-white px-2 py-1">状态：{{ selectedNode.status || '未标记' }}</span>
            </div>
            <p class="mt-4 text-sm leading-6 text-slate-700">{{ selectedNode.description || '暂无角色描述。' }}</p>
            <div class="mt-4 grid gap-3 md:grid-cols-2">
              <div>
                <div class="text-sm font-medium text-slate-800">性格特征</div>
                <div class="mt-2 flex flex-wrap gap-2">
                  <span v-for="trait in selectedNode.traits || []" :key="trait" class="rounded-full bg-white px-2.5 py-1 text-xs text-slate-600">{{ trait }}</span>
                  <span v-if="!(selectedNode.traits || []).length" class="text-sm text-slate-500">暂无</span>
                </div>
              </div>
              <div>
                <div class="text-sm font-medium text-slate-800">目标 / 动机</div>
                <div class="mt-2 flex flex-wrap gap-2">
                  <span v-for="goal in selectedNode.goals || []" :key="goal" class="rounded-full bg-white px-2.5 py-1 text-xs text-slate-600">{{ goal }}</span>
                  <span v-if="!(selectedNode.goals || []).length" class="text-sm text-slate-500">暂无</span>
                </div>
              </div>
            </div>
          </article>
          <article class="rounded-2xl bg-slate-50 p-4">
            <div class="text-sm font-medium text-slate-800">与其强关联的角色 / 事件</div>
            <div class="mt-3 space-y-3">
              <div v-for="edge in selectedNodeEdges" :key="edge.id" class="rounded-2xl border border-slate-200 bg-white px-4 py-3">
                <div class="flex items-center justify-between gap-3">
                  <div class="text-sm font-medium text-slate-900">{{ edge.source_name }} → {{ edge.target_name }}</div>
                  <span class="rounded-full bg-slate-100 px-2 py-1 text-[11px] text-slate-500">{{ edge.event_type }}</span>
                </div>
                <div class="mt-2 text-sm leading-6 text-slate-600">{{ edge.description || '暂无事件描述' }}</div>
                <div class="mt-2 text-xs text-slate-500">第 {{ edge.chapter_number || '?' }} 章 · 重要度 {{ edge.importance || 0 }}/10</div>
              </div>
              <div v-if="!selectedNodeEdges.length" class="rounded-2xl border border-dashed border-slate-200 bg-white px-4 py-6 text-sm text-slate-500">当前没有与该角色绑定的关系边。</div>
            </div>
          </article>
        </div>
        <div v-else class="mt-4 rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-8 text-sm text-slate-500">左侧选一个角色，就能看见它在当前故事里的位置与关系网。</div>
      </section>

      <section class="grid gap-4 xl:grid-cols-[1fr_1fr]">
        <article class="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <h4 class="text-base font-semibold text-slate-900">最强关系边</h4>
          <p class="mt-1 text-sm text-slate-500">按重要度排序，帮助快速定位谁在推动主线冲突。</p>
          <div class="mt-4 space-y-3">
            <div v-for="edge in topEdges" :key="edge.id" class="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
              <div class="flex items-center justify-between gap-3">
                <div class="text-sm font-medium text-slate-900">{{ edge.source_name }} → {{ edge.target_name }}</div>
                <span class="rounded-full bg-white px-2 py-1 text-[11px] text-slate-500">{{ edge.event_type || '关系' }}</span>
              </div>
              <div class="mt-2 text-sm leading-6 text-slate-600 line-clamp-2">{{ edge.description || '暂无说明' }}</div>
            </div>
            <div v-if="!topEdges.length" class="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-500">暂无关系边数据。</div>
          </div>
        </article>

        <article class="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <h4 class="text-base font-semibold text-slate-900">剧情线索分组</h4>
          <p class="mt-1 text-sm text-slate-500">自动把同一批角色参与的关系边聚成“剧情线”，方便判断有哪些主线正在并行。</p>
          <div class="mt-4 space-y-3">
            <div v-for="(thread, index) in plotThreads" :key="index" class="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
              <div class="text-sm font-medium text-slate-900">{{ thread.thread_name || `剧情线 ${index + 1}` }}</div>
              <div class="mt-2 text-xs leading-5 text-slate-500">涉及角色：{{ (thread.characters || []).join('、') || '暂无' }}</div>
              <div class="mt-1 text-xs leading-5 text-slate-500">关键事件：{{ (thread.key_events || []).join('、') || '暂无' }}</div>
            </div>
            <div v-if="!plotThreads.length" class="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-500">尚未生成剧情线分析结果。</div>
          </div>
        </article>
      </section>

      <section v-if="error" class="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{{ error }}</section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { KnowledgeGraphAPI } from '@/api/novel'

const props = defineProps<{ projectId?: string }>()

const loading = ref(false)
const error = ref('')
const graph = ref<any>({ nodes: [], edges: [], node_count: 0, edge_count: 0 })
const plotThreads = ref<any[]>([])
const selectedNode = ref<any | null>(null)
const search = ref('')

const projectId = computed(() => props.projectId || '')
const nodes = computed<any[]>(() => Array.isArray(graph.value.nodes) ? graph.value.nodes : [])
const edges = computed<any[]>(() => Array.isArray(graph.value.edges) ? graph.value.edges : [])

const filteredNodes = computed(() => {
  const keyword = search.value.trim().toLowerCase()
  if (!keyword) return nodes.value
  return nodes.value.filter((node) => [node.name, node.role_type, node.description].some((value) => String(value || '').toLowerCase().includes(keyword)))
})

const selectedNodeEdges = computed(() => {
  if (!selectedNode.value) return []
  return edges.value.filter((edge) => edge.source_id === selectedNode.value.id || edge.target_id === selectedNode.value.id)
    .sort((a, b) => (b.importance || 0) - (a.importance || 0))
    .slice(0, 8)
})

const topEdges = computed(() => edges.value.slice().sort((a, b) => (b.importance || 0) - (a.importance || 0)).slice(0, 8))

const selectNode = (node: any) => {
  selectedNode.value = node
}

const loadGraph = async () => {
  if (!projectId.value) return
  loading.value = true
  error.value = ''
  try {
    graph.value = await KnowledgeGraphAPI.getFullGraph(projectId.value)
    if (!selectedNode.value && nodes.value.length) {
      selectedNode.value = nodes.value[0]
    } else if (selectedNode.value) {
      selectedNode.value = nodes.value.find((node) => node.id === selectedNode.value.id) || nodes.value[0] || null
    }
  } catch (err: any) {
    error.value = err instanceof Error ? err.message : '加载知识图谱失败'
  } finally {
    loading.value = false
  }
}

const loadThreads = async () => {
  if (!projectId.value) return
  try {
    plotThreads.value = await KnowledgeGraphAPI.analyzePlotThreads(projectId.value)
  } catch (err: any) {
    error.value = err instanceof Error ? err.message : '分析剧情线失败'
  }
}

const reload = async () => {
  await loadGraph()
  await loadThreads()
}

onMounted(reload)
watch(projectId, (value) => { if (value) void reload() })
</script>
