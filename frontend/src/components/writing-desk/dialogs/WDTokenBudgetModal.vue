<!-- Token 预算管理弹窗 -->
<template>
  <div v-if="show" class="fixed inset-0 z-50 flex items-center justify-center p-4">
    <!-- 遮罩 -->
    <div class="absolute inset-0 bg-black/50" @click="$emit('close')"></div>

    <!-- 弹窗内容 -->
    <div class="relative bg-white rounded-2xl shadow-2xl w-full max-w-3xl max-h-[85vh] overflow-hidden">
      <!-- 标题 -->
      <div class="px-6 py-4 border-b border-slate-200 flex items-center justify-between">
        <div>
          <h3 class="text-xl font-bold text-slate-900">Token 预算管理</h3>
          <p class="text-sm text-slate-500 mt-1">控制 AI 生成成本，跟踪模块使用情况</p>
        </div>
        <button @click="$emit('close')" class="text-slate-400 hover:text-slate-600">
          <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
          </svg>
        </button>
      </div>

      <!-- 标签页 -->
      <div class="px-6 pt-4 border-b border-slate-200">
        <div class="flex gap-4">
          <button
            v-for="tab in tabs"
            :key="tab.key"
            @click="activeTab = tab.key"
            class="pb-3 text-sm font-medium transition-colors border-b-2"
            :class="activeTab === tab.key
              ? 'border-indigo-500 text-indigo-600'
              : 'border-transparent text-slate-500 hover:text-slate-700'"
          >
            {{ tab.label }}
          </button>
        </div>
      </div>

      <!-- 内容区 -->
      <div class="px-6 py-4 overflow-y-auto max-h-[60vh]">
        <!-- 加载状态 -->
        <div v-if="loading" class="flex flex-col items-center justify-center py-12">
          <div class="animate-spin rounded-full h-12 w-12 border-4 border-indigo-500 border-t-transparent"></div>
          <p class="mt-4 text-slate-500">加载中...</p>
        </div>

        <!-- 错误状态 -->
        <div v-else-if="error" class="text-center py-8">
          <div class="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mx-auto">
            <svg class="w-8 h-8 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
            </svg>
          </div>
          <p class="mt-4 text-red-600">{{ error }}</p>
          <button @click="loadData" class="mt-4 px-4 py-2 text-sm text-indigo-600 hover:text-indigo-800">
            重试
          </button>
        </div>

        <!-- 概览标签页 -->
        <div v-else-if="activeTab === 'overview'">
          <!-- 使用概览卡片 -->
          <div class="bg-gradient-to-r from-indigo-50 to-cyan-50 rounded-xl p-4 mb-6">
            <div class="flex items-center justify-between mb-4">
              <div>
                <p class="text-sm text-slate-600">总预算</p>
                <p class="text-2xl font-bold text-slate-900">¥{{ budgetConfig.total_budget?.toFixed(2) || '0.00' }}</p>
              </div>
              <div class="text-right">
                <p class="text-sm text-slate-600">已使用</p>
                <p class="text-2xl font-bold" :class="usagePercent >= 90 ? 'text-red-600' : 'text-indigo-600'">
                  ¥{{ usageStats.total_cost?.toFixed(2) || '0.00' }}
                </p>
              </div>
              <div class="text-right">
                <p class="text-sm text-slate-600">剩余</p>
                <p class="text-2xl font-bold text-green-600">¥{{ usageStats.budget_remaining?.toFixed(2) || '0.00' }}</p>
              </div>
            </div>

            <!-- 进度条 -->
            <div class="relative h-4 bg-slate-200 rounded-full overflow-hidden">
              <div
                class="absolute left-0 top-0 h-full transition-all duration-500"
                :class="usagePercent >= 90 ? 'bg-red-500' : usagePercent >= 70 ? 'bg-yellow-500' : 'bg-indigo-500'"
                :style="{ width: `${Math.min(usagePercent, 100)}%` }"
              ></div>
            </div>
            <p class="text-sm text-slate-500 mt-2 text-center">
              已使用 {{ usagePercent?.toFixed(1) || '0' }}%
              <span v-if="usagePercent >= budgetConfig.warning_threshold" class="text-red-600 font-medium">
                (已超过预警阈值 {{ budgetConfig.warning_threshold }}%)
              </span>
            </p>
          </div>

          <!-- 模块使用情况 -->
          <p class="text-sm font-medium text-slate-700 mb-3">各模块使用情况</p>
          <div class="grid grid-cols-2 gap-4">
            <div
              v-for="(data, module) in usageStats.module_stats"
              :key="module"
              class="p-4 border-2 border-slate-200 rounded-xl"
            >
              <div class="flex items-center justify-between mb-2">
                <span class="font-medium text-slate-900">{{ getModuleLabel(module) }}</span>
                <span class="text-sm text-slate-500">¥{{ data.cost?.toFixed(2) || '0' }}</span>
              </div>
              <div class="relative h-2 bg-slate-100 rounded-full overflow-hidden">
                <div
                  class="absolute left-0 top-0 h-full bg-indigo-500"
                  :style="{ width: `${getModulePercent(module)}%` }"
                ></div>
              </div>
              <p class="text-xs text-slate-500 mt-1">{{ data.tokens?.toLocaleString() || 0 }} tokens</p>
            </div>
          </div>

          <!-- 预警列表 -->
          <div v-if="alerts.length" class="mt-6">
            <p class="text-sm font-medium text-slate-700 mb-3">预算预警</p>
            <div class="space-y-2">
              <div
                v-for="alert in alerts"
                :key="alert.id"
                class="flex items-center gap-3 p-3 rounded-lg"
                :class="alert.alert_type === 'exceeded' ? 'bg-red-50 border border-red-200' : 'bg-yellow-50 border border-yellow-200'"
              >
                <svg class="w-5 h-5" :class="alert.alert_type === 'exceeded' ? 'text-red-600' : 'text-yellow-600'" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path>
                </svg>
                <div class="flex-1">
                  <p class="text-sm font-medium" :class="alert.alert_type === 'exceeded' ? 'text-red-800' : 'text-yellow-800'">
                    {{ alert.message }}
                  </p>
                  <p class="text-xs text-slate-500">{{ alert.created_at }}</p>
                </div>
                <button
                  v-if="!alert.is_resolved"
                  @click="resolveAlert(alert.id)"
                  class="px-2 py-1 text-xs text-indigo-600 hover:text-indigo-800"
                >
                  标记已处理
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- 配置标签页 -->
        <div v-else-if="activeTab === 'config'">
          <!-- 预算设置 -->
          <div class="space-y-4 mb-6">
            <div>
              <label class="block text-sm font-medium text-slate-700 mb-1">总预算 (人民币)</label>
              <input
                v-model.number="editConfig.total_budget"
                type="number"
                step="0.01"
                min="0"
                class="w-full px-3 py-2 border-2 border-slate-200 rounded-lg focus:border-indigo-500 focus:outline-none"
              />
            </div>
            <div>
              <label class="block text-sm font-medium text-slate-700 mb-1">单章节预算 (人民币)</label>
              <input
                v-model.number="editConfig.chapter_budget"
                type="number"
                step="0.01"
                min="0"
                class="w-full px-3 py-2 border-2 border-slate-200 rounded-lg focus:border-indigo-500 focus:outline-none"
              />
            </div>
            <div>
              <label class="block text-sm font-medium text-slate-700 mb-1">预警阈值 (%)</label>
              <input
                v-model.number="editConfig.warning_threshold"
                type="number"
                step="1"
                min="0"
                max="100"
                class="w-full px-3 py-2 border-2 border-slate-200 rounded-lg focus:border-indigo-500 focus:outline-none"
              />
              <p class="text-xs text-slate-500 mt-1">当使用量达到此百分比时触发预警</p>
            </div>
          </div>

          <!-- 模块分配 -->
          <p class="text-sm font-medium text-slate-700 mb-3">模块分配比例 (总和应为 100%)</p>
          <div class="space-y-3">
            <div v-for="module in budgetModules" :key="module" class="flex items-center gap-4">
              <span class="w-20 text-sm text-slate-600">{{ getModuleLabel(module) }}</span>
              <input
                v-model.number="editConfig.module_allocation[module]"
                type="range"
                min="0"
                max="100"
                class="flex-1"
              />
              <span class="w-12 text-sm text-slate-900 text-right">{{ editConfig.module_allocation[module] }}%</span>
            </div>
          </div>
          <p class="text-sm mt-2" :class="totalAllocation === 100 ? 'text-green-600' : 'text-red-600'">
            当前总和: {{ totalAllocation }}%
          </p>

          <button
            @click="saveConfig"
            :disabled="saving || totalAllocation !== 100"
            class="mt-4 w-full px-4 py-2 text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {{ saving ? '保存中...' : '保存配置' }}
          </button>
        </div>

        <!-- 记录标签页 -->
        <div v-else-if="activeTab === 'records'">
          <div class="text-center py-8 text-slate-500">
            <svg class="w-12 h-12 mx-auto mb-3 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"></path>
            </svg>
            <p>共 {{ usageStats.record_count || 0 }} 条使用记录</p>
            <p class="text-sm mt-1">总计 {{ usageStats.total_tokens?.toLocaleString() || 0 }} tokens</p>
          </div>
        </div>
      </div>

      <!-- 底部 -->
      <div class="px-6 py-4 border-t border-slate-200 flex justify-between">
        <button
          @click="$emit('close')"
          class="px-4 py-2 text-slate-600 hover:text-slate-800"
        >
          关闭
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { TokenBudgetAPI } from '@/api/novel'

type BudgetModuleKey = 'world' | 'character' | 'outline' | 'content'

type ModuleAllocation = Record<BudgetModuleKey, number>

const props = defineProps<{
  show: boolean
  projectId: string
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'updated'): void
}>()

// 标签页
const tabs = [
  { key: 'overview', label: '使用概览' },
  { key: 'config', label: '预算配置' },
  { key: 'records', label: '使用记录' }
]

const budgetModules: BudgetModuleKey[] = ['world', 'character', 'outline', 'content']
const activeTab = ref('overview')

// 状态
const loading = ref(false)
const saving = ref(false)
const error = ref('')

// 数据
const budgetConfig = ref<{
  project_id?: string
  total_budget: number
  chapter_budget: number
  module_allocation: ModuleAllocation
  warning_threshold: number
}>({
  total_budget: 100,
  chapter_budget: 5,
  module_allocation: { world: 20, character: 15, outline: 10, content: 55 },
  warning_threshold: 80
})
const usageStats = ref<any>({
  total_cost: 0,
  budget_remaining: 100,
  usage_percent: 0,
  total_tokens: 0,
  module_stats: {}
})
const alerts = ref<any[]>([])

// 编辑配置
const editConfig = ref<{
  total_budget: number
  chapter_budget: number
  module_allocation: ModuleAllocation
  warning_threshold: number
}>({
  total_budget: 100,
  chapter_budget: 5,
  module_allocation: { world: 20, character: 15, outline: 10, content: 55 },
  warning_threshold: 80
})

// 计算属性
const usagePercent = computed(() => usageStats.value.usage_percent || 0)

const totalAllocation = computed(() => {
  const alloc = editConfig.value.module_allocation
  return (alloc.world || 0) + (alloc.character || 0) + (alloc.outline || 0) + (alloc.content || 0)
})

// 方法
const getModuleLabel = (module: string | number) => {
  const labels: Record<string, string> = {
    world: '世界观',
    character: '角色',
    outline: '大纲',
    content: '正文',
    other: '其他'
  }
  const moduleKey = String(module)
  return labels[moduleKey] || moduleKey
}

const getModulePercent = (module: string | number) => {
  const moduleKey = String(module)
  const moduleStats = usageStats.value.module_stats?.[moduleKey]
  const totalCost = usageStats.value.total_cost || 1
  return moduleStats ? (moduleStats.cost / totalCost * 100) : 0
}

const loadData = async () => {
  if (!props.projectId) return

  loading.value = true
  error.value = ''

  try {
    const [config, stats, alertData] = await Promise.all([
      TokenBudgetAPI.getBudgetConfig(props.projectId),
      TokenBudgetAPI.getUsageStats(props.projectId),
      TokenBudgetAPI.getAlerts(props.projectId, false)
    ])

    budgetConfig.value = {
      project_id: config.project_id,
      total_budget: config.total_budget,
      chapter_budget: config.chapter_budget,
      module_allocation: {
        world: config.module_allocation?.world ?? 20,
        character: config.module_allocation?.character ?? 15,
        outline: config.module_allocation?.outline ?? 10,
        content: config.module_allocation?.content ?? 55
      },
      warning_threshold: config.warning_threshold
    }
    usageStats.value = stats
    alerts.value = alertData

    // 更新编辑配置
    editConfig.value = {
      total_budget: config.total_budget,
      chapter_budget: config.chapter_budget,
      module_allocation: {
        world: config.module_allocation?.world ?? 20,
        character: config.module_allocation?.character ?? 15,
        outline: config.module_allocation?.outline ?? 10,
        content: config.module_allocation?.content ?? 55
      },
      warning_threshold: config.warning_threshold
    }
  } catch (e: any) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

const saveConfig = async () => {
  saving.value = true

  try {
    const result = await TokenBudgetAPI.updateBudgetConfig(props.projectId, editConfig.value)
    budgetConfig.value = {
      project_id: result.project_id,
      total_budget: result.total_budget,
      chapter_budget: result.chapter_budget,
      module_allocation: {
        world: result.module_allocation?.world ?? 20,
        character: result.module_allocation?.character ?? 15,
        outline: result.module_allocation?.outline ?? 10,
        content: result.module_allocation?.content ?? 55
      },
      warning_threshold: result.warning_threshold
    }
    emit('updated')
  } catch (e: any) {
    error.value = e.message || '保存失败'
  } finally {
    saving.value = false
  }
}

const resolveAlert = async (alertId: number) => {
  try {
    await TokenBudgetAPI.resolveAlert(props.projectId, alertId)
    alerts.value = alerts.value.filter(a => a.id !== alertId)
  } catch (e: any) {
    error.value = e.message || '操作失败'
  }
}

// 监听 show 变化
watch(() => props.show, (newVal) => {
  if (newVal) {
    loadData()
  }
})
</script>