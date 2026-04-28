<!-- 剧情演进弹窗 - 让用户选择剧情分支 -->
<template>
  <div v-if="show" class="fixed inset-0 z-50 flex items-center justify-center p-4">
    <!-- 遮罩 -->
    <div class="absolute inset-0 bg-black/50" @click="$emit('close')"></div>

    <!-- 弹窗内容 -->
    <div class="relative bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[80vh] overflow-hidden">
      <!-- 标题 -->
      <div class="px-6 py-4 border-b border-slate-200">
        <h3 class="text-xl font-bold text-slate-900">剧情推演</h3>
        <p class="text-sm text-slate-500 mt-1">选择你感兴趣的方向，大纲将自动更新</p>
      </div>

      <!-- 内容区 -->
      <div class="px-6 py-4 overflow-y-auto max-h-[60vh]">
        <!-- 加载状态 -->
        <div v-if="loading" class="flex flex-col items-center justify-center py-12">
          <div class="animate-spin rounded-full h-12 w-12 border-4 border-indigo-500 border-t-transparent"></div>
          <p class="mt-4 text-slate-500">AI 正在生成剧情分支...</p>
        </div>

        <!-- 选项列表 -->
        <div v-else-if="alternatives.length" class="space-y-4">
          <div
            v-for="alt in alternatives"
            :key="alt.id"
            class="p-4 border-2 border-slate-200 rounded-xl cursor-pointer transition-all hover:border-indigo-400 hover:shadow-md"
            @click="selectOption(alt)"
          >
            <div class="flex items-start justify-between">
              <div class="flex-1">
                <h4 class="font-semibold text-slate-900">{{ alt.title }}</h4>
                <p class="mt-2 text-sm text-slate-600">{{ alt.description }}</p>
                <div class="mt-3 flex items-center gap-3">
                  <span
                    class="px-2 py-1 text-xs font-medium rounded-full"
                    :class="{
                      'bg-purple-100 text-purple-700': alt.evolution_type === 'branch',
                      'bg-blue-100 text-blue-700': alt.evolution_type === 'extend',
                      'bg-orange-100 text-orange-700': alt.evolution_type === 'twist'
                    }"
                  >
                    {{ alt.evolution_type === 'branch' ? '分支剧情' : alt.evolution_type === 'extend' ? '延伸剧情' : '反转剧情' }}
                  </span>
                  <span class="text-xs text-slate-400">评分: {{ alt.score }}/100</span>
                </div>
              </div>
              <div class="ml-4 text-2xl">🎯</div>
            </div>
          </div>
        </div>

        <!-- 空状态 -->
        <div v-else class="text-center py-12 text-slate-500">
          暂无剧情选项，请先生成
        </div>
      </div>

      <!-- 底部按钮 -->
      <div class="px-6 py-4 border-t border-slate-200 flex justify-between">
        <button
          @click="$emit('close')"
          class="px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-800"
        >
          取消
        </button>
        <button
          v-if="!loading && alternatives.length"
          @click="regenerate"
          class="px-4 py-2 text-sm font-medium text-indigo-600 hover:text-indigo-800"
        >
          重新生成
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { OptimizerAPI } from '@/api/novel'

interface Alternative {
  id: number
  title: string
  description: string
  evolution_type: string
  score: number
  new_outline: any
  changes: string
}

const props = defineProps<{
  show: boolean
  projectId: string
  chapterNumber: number
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'select', option: Alternative): void
}>()

const loading = ref(false)
const alternatives = ref<Alternative[]>([])

// 当弹窗显示时自动加载选项
watch(() => props.show, async (newVal) => {
  if (newVal && props.projectId && props.chapterNumber) {
    await loadAlternatives()
  }
})

async function loadAlternatives() {
  loading.value = true
  try {
    const res = await OptimizerAPI.getOutlineAlternatives(props.projectId, props.chapterNumber)
    alternatives.value = res.alternatives
  } catch (e) {
    console.error('加载剧情选项失败:', e)
    alternatives.value = []
  } finally {
    loading.value = false
  }
}

function selectOption(alt: Alternative) {
  emit('select', alt)
}

async function regenerate() {
  loading.value = true
  alternatives.value = []
  try {
    const res = await OptimizerAPI.evolveOutline(props.projectId, props.chapterNumber, 3)
    alternatives.value = res.alternatives
  } catch (e) {
    console.error('重新生成失败:', e)
  } finally {
    loading.value = false
  }
}
</script>