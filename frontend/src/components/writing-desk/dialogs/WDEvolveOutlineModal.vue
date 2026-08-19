<!-- 剧情演进弹窗 - 让用户选择剧情分支 -->
<template>
  <div v-if="show" class="xq-dialog-overlay" @click.self="$emit('close')">
    <div class="xq-dialog-shell">
      <div class="xq-dialog-header">
        <div>
          <p class="xq-dialog-kicker">Plot Evolution</p>
          <h3 class="xq-dialog-title">{{ pick('剧情推演', 'Plot evolution') }}</h3>
          <p class="xq-dialog-subtitle">{{ pick('选择你感兴趣的方向，大纲将自动更新，并保留可回滚的演进意图。', 'Pick the direction that interests you. The outline updates automatically and keeps a revertible record of the evolution intent.') }}</p>
        </div>
        <button type="button" class="xq-dialog-close" @click="$emit('close')" :aria-label="t('common.close')">×</button>
      </div>

      <!-- 内容区 -->
      <div class="xq-dialog-body">
        <!-- 加载状态 -->
        <div v-if="loading" class="flex flex-col items-center justify-center py-12">
          <div class="animate-spin rounded-full h-12 w-12 border-4 border-indigo-500 border-t-transparent"></div>
          <p class="mt-4 text-slate-500">{{ pick('AI 正在生成剧情分支...', 'AI is generating plot branches...') }}</p>
        </div>

        <!-- 选项列表 -->
        <div v-else-if="alternatives.length" class="space-y-4">
          <div
            v-for="alt in alternatives"
            :key="alt.id"
            class="evolve-card"
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
                      'bg-sky-100 text-sky-700': alt.evolution_type === 'twist'
                    }"
                  >
                    {{ alt.evolution_type === 'branch' ? pick('分支剧情', 'Plot branch') : alt.evolution_type === 'extend' ? pick('延伸剧情', 'Plot extension') : pick('反转剧情', 'Plot twist') }}
                  </span>
                  <span class="text-xs text-slate-400">{{ pick('评分', 'Score') }}: {{ alt.score }}/100</span>
                </div>
              </div>
              <div class="ml-4 text-2xl">🎯</div>
            </div>
          </div>
        </div>

        <!-- 空状态 -->
        <div v-else class="text-center py-12 text-slate-500">
          {{ pick('暂无剧情选项，请先生成', 'No plot options yet. Generate them first.') }}
        </div>
      </div>

      <!-- 底部按钮 -->
      <div class="xq-dialog-footer justify-between">
        <button
          @click="$emit('close')"
          class="md-btn md-btn-outlined md-ripple"
        >
          {{ t('common.cancel') }}
        </button>
        <button
          v-if="!loading && alternatives.length"
          @click="regenerate"
          class="md-btn md-btn-filled md-ripple"
        >
          {{ t('common.regenerate') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { OptimizerAPI } from '@/api/novel'
import { useLocale } from '@/composables/useLocale'

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
const { pick, t } = useLocale()

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
    console.error(pick('加载剧情选项失败:', 'Failed to load plot options:'), e)
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
    console.error(pick('重新生成失败:', 'Regeneration failed:'), e)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.evolve-card {
  padding: 16px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 22px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(248, 250, 252, 0.92));
  cursor: pointer;
  transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
}

.evolve-card:hover {
  transform: translateY(-1px);
  border-color: rgba(99, 102, 241, 0.35);
  box-shadow: 0 18px 42px rgba(99, 102, 241, 0.12);
}
</style>
