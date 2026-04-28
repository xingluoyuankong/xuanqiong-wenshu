<!-- 记忆管理弹窗 - 管理项目的记忆层 -->
<template>
  <div v-if="show" class="fixed inset-0 z-50 flex items-center justify-center p-4">
    <!-- 遮罩 -->
    <div class="absolute inset-0 bg-black/50" @click="$emit('close')"></div>

    <!-- 弹窗内容 -->
    <div class="relative bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[80vh] overflow-hidden">
      <!-- 标题 -->
      <div class="px-6 py-4 border-b border-slate-200 flex items-center justify-between">
        <div>
          <h3 class="text-xl font-bold text-slate-900">记忆管理</h3>
          <p class="text-sm text-slate-500 mt-1">管理项目的动态记忆层，支持增量更新、快照和回滚</p>
        </div>
        <button @click="$emit('close')" class="text-slate-400 hover:text-slate-600">
          <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
          </svg>
        </button>
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
          <button @click="loadSnapshots" class="mt-4 px-4 py-2 text-sm text-indigo-600 hover:text-indigo-800">
            重试
          </button>
        </div>

        <!-- 记忆信息 -->
        <div v-else>
          <!-- 当前状态卡片 -->
          <div class="bg-gradient-to-r from-indigo-50 to-purple-50 rounded-xl p-4 mb-4">
            <div class="flex items-center gap-3">
              <div class="w-12 h-12 bg-indigo-100 rounded-xl flex items-center justify-center">
                <svg class="w-6 h-6 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"></path>
                </svg>
              </div>
              <div class="flex-1">
                <p class="font-medium text-slate-900">记忆状态</p>
                <p class="text-sm text-slate-600">
                  共 {{ snapshots.length }} 个快照 | 当前版本: {{ currentVersion }}
                </p>
              </div>
              <button
                @click="triggerIncrementalUpdate"
                :disabled="actionLoading"
                class="px-3 py-1.5 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-50"
              >
                增量更新
              </button>
            </div>
          </div>

          <!-- 快照列表 -->
          <p class="text-sm font-medium text-slate-700 mb-3">记忆快照</p>

          <div v-if="snapshots.length" class="space-y-3">
            <div
              v-for="snapshot in snapshots"
              :key="snapshot.id"
              class="flex items-center gap-3 p-3 border-2 rounded-xl"
              :class="snapshot.id === currentSnapshotId
                ? 'border-green-500 bg-green-50'
                : 'border-slate-200'"
            >
              <div class="flex-1">
                <div class="flex items-center gap-2">
                  <p class="font-medium text-slate-900">{{ snapshot.summary }}</p>
                  <span
                    v-if="snapshot.id === currentSnapshotId"
                    class="px-2 py-0.5 text-xs font-medium bg-green-100 text-green-700 rounded-full"
                  >
                    当前
                  </span>
                </div>
                <p class="text-sm text-slate-500">{{ snapshot.created_at }}</p>
                <p class="text-xs text-slate-400 mt-1">
                  章节: {{ snapshot.chapter_number }}
                </p>
              </div>
              <div class="flex gap-2">
                <button
                  v-if="snapshot.id !== currentSnapshotId"
                  @click="rollbackToSnapshot(snapshot.id)"
                  :disabled="actionLoading"
                  class="px-3 py-1.5 text-sm font-medium text-orange-600 bg-orange-50 rounded-lg hover:bg-orange-100 disabled:opacity-50"
                >
                  回滚
                </button>
              </div>
            </div>
          </div>

          <!-- 空状态 -->
          <div v-else class="text-center py-8 text-slate-500">
            <p>暂无记忆快照</p>
            <p class="text-sm mt-1">点击"增量更新"开始构建记忆</p>
          </div>

          <!-- 操作反馈 -->
          <div v-if="actionMessage" class="mt-4 p-3 rounded-xl text-sm" :class="actionSuccess ? 'bg-green-50 border border-green-200 text-green-700' : 'bg-red-50 border border-red-200 text-red-700'">
            {{ actionMessage }}
          </div>
        </div>
      </div>

      <!-- 底部按钮 -->
      <div class="px-6 py-4 border-t border-slate-200 flex justify-between items-center">
        <button
          @click="compressMemory"
          :disabled="actionLoading || snapshots.length === 0"
          class="px-4 py-2 text-sm font-medium text-slate-600 bg-slate-100 rounded-lg hover:bg-slate-200 disabled:opacity-50"
        >
          压缩记忆
        </button>
        <button
          @click="$emit('close')"
          class="px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-800"
        >
          关闭
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { OptimizerAPI } from '@/api/novel'

interface Snapshot {
  id: number
  chapter_number: number
  summary: string
  created_at: string
}

const props = defineProps<{
  show: boolean
  projectId: string
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'updated'): void
}>()

const loading = ref(false)
const actionLoading = ref(false)
const error = ref('')
const actionMessage = ref('')
const actionSuccess = ref(false)
const snapshots = ref<Snapshot[]>([])
const currentVersion = ref('v1')
const currentSnapshotId = ref<number | null>(null)

async function loadSnapshots() {
  loading.value = true
  error.value = ''
  try {
    const res = await OptimizerAPI.getMemorySnapshots(props.projectId)
    snapshots.value = res.snapshots || []
    currentVersion.value = `v${res.current_memory_version || 0}`
    currentSnapshotId.value = res.current_snapshot_id ?? (snapshots.value.length > 0 ? snapshots.value[0].id : null)
  } catch (e: any) {
    error.value = e.message || '加载快照失败'
    console.error('加载记忆快照失败:', e)
  } finally {
    loading.value = false
  }
}

async function triggerIncrementalUpdate() {
  actionLoading.value = true
  actionMessage.value = ''
  try {
    await OptimizerAPI.updateMemoryIncremental(props.projectId, {
      chapter_number: 0
    })
    actionMessage.value = '增量更新成功'
    actionSuccess.value = true
    emit('updated')
    await loadSnapshots()
  } catch (e: any) {
    actionMessage.value = e.message || '增量更新失败'
    actionSuccess.value = false
    console.error('增量更新失败:', e)
  } finally {
    actionLoading.value = false
    setTimeout(() => { actionMessage.value = '' }, 3000)
  }
}

async function rollbackToSnapshot(snapshotId: number) {
  actionLoading.value = true
  actionMessage.value = ''
  try {
    const snapshotIndex = snapshots.value.findIndex(s => s.id === snapshotId)
    const targetVersion = snapshotIndex >= 0 ? snapshotIndex + 1 : snapshotId
    await OptimizerAPI.rollbackMemory(props.projectId, targetVersion)
    actionMessage.value = '回滚成功'
    actionSuccess.value = true
    emit('updated')
    await loadSnapshots()
  } catch (e: any) {
    actionMessage.value = e.message || '回滚失败'
    actionSuccess.value = false
    console.error('回滚失败:', e)
  } finally {
    actionLoading.value = false
    setTimeout(() => { actionMessage.value = '' }, 3000)
  }
}

async function compressMemory() {
  actionLoading.value = true
  actionMessage.value = ''
  try {
    await OptimizerAPI.compressMemory(props.projectId)
    actionMessage.value = '压缩成功'
    actionSuccess.value = true
    emit('updated')
    await loadSnapshots()
  } catch (e: any) {
    actionMessage.value = e.message || '压缩失败'
    actionSuccess.value = false
    console.error('压缩失败:', e)
  } finally {
    actionLoading.value = false
    setTimeout(() => { actionMessage.value = '' }, 3000)
  }
}

watch(() => props.show, (newVal) => {
  if (newVal) {
    loadSnapshots()
  }
})
</script>