<template>
  <n-space vertical size="large" class="admin-settings">
    <n-alert type="info" :show-icon="false" class="settings-risk-alert">
      这里只做“修改参数”，不再提供前端删除入口。每个参数都给出中文名称、参数分类、当前值和用途说明。
    </n-alert>

    <n-card :bordered="false" class="embedding-health-card">
      <div class="embedding-health-card__head">
        <div>
          <strong>Embedding 能力检查</strong>
          <p>只读取当前能力状态，不显示密钥，也不会启动章节生成。</p>
        </div>
        <n-button size="small" :loading="embeddingHealthLoading" @click="checkEmbeddingHealth">
          检查
        </n-button>
      </div>
      <n-alert v-if="embeddingHealthError" type="error" :show-icon="false">
        {{ embeddingHealthError }}
      </n-alert>
      <div v-if="embeddingHealth" class="embedding-health-card__result">
        <n-tag :type="embeddingHealth.status.status === 'healthy' ? 'success' : 'warning'">
          {{ embeddingHealth.status.status === 'healthy' ? '可用' : '降级' }}
        </n-tag>
        <span>Provider：{{ embeddingHealth.status.provider || '未知' }}</span>
        <span>模型：{{ embeddingHealth.status.model || '未知' }}</span>
        <span>维度：{{ embeddingHealth.vector_dimension }}</span>
        <span>状态码：{{ embeddingHealth.status.code || '—' }}</span>
      </div>
    </n-card>

    <DailyLimitCard
      :limit="dailyLimit"
      :loading="dailyLimitLoading"
      :saving="dailyLimitSaving"
      :error="dailyLimitError"
      @refresh="fetchDailyLimit"
      @save="saveDailyLimit"
      @clear-error="dailyLimitError = null"
      @update:limit="dailyLimit = $event"
    />

    <SystemConfigTable
      :configs="configs"
      :loading="configLoading"
      :error="configError"
      :save-inline="saveConfigValue"
      @edit="openEditModal"
      @clear-error="configError = null"
    />
  </n-space>

  <SystemConfigModal
    :show="configModalVisible"
    :title="modalTitle"
    :saving="configSaving"
    :form="configForm"
    @update:show="configModalVisible = $event"
    @cancel="closeConfigModal"
    @submit="submitConfig"
  />
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { NAlert, NButton, NCard, NSpace, NTag } from 'naive-ui'

import DailyLimitCard from './settings/DailyLimitCard.vue'
import SystemConfigModal from './settings/SystemConfigModal.vue'
import SystemConfigTable from './settings/SystemConfigTable.vue'
import { useAdminSettings } from '@/composables/admin/useAdminSettings'
import { getEmbeddingHealthCheck, type EmbeddingHealthResponse } from '@/api/llm'

const embeddingHealth = ref<EmbeddingHealthResponse | null>(null)
const embeddingHealthLoading = ref(false)
const embeddingHealthError = ref<string | null>(null)

const checkEmbeddingHealth = async () => {
  embeddingHealthLoading.value = true
  embeddingHealthError.value = null
  try {
    embeddingHealth.value = await getEmbeddingHealthCheck()
  } catch (error) {
    embeddingHealthError.value = error instanceof Error ? error.message : 'Embedding 能力检查失败'
  } finally {
    embeddingHealthLoading.value = false
  }
}

const {
  dailyLimit,
  dailyLimitLoading,
  dailyLimitSaving,
  dailyLimitError,
  configs,
  configLoading,
  configSaving,
  configError,
  configModalVisible,
  configForm,
  modalTitle,
  fetchDailyLimit,
  saveDailyLimit,
  openEditModal,
  closeConfigModal,
  submitConfig,
  saveConfigValue,
  initialize,
} = useAdminSettings()

onMounted(() => {
  initialize()
})
</script>

<style scoped>
.admin-settings { width: 100%; }
.embedding-health-card { border-radius: 16px; }
.embedding-health-card__head { display:flex; align-items:center; justify-content:space-between; gap:16px; }
.embedding-health-card__head p { margin:4px 0 0; color:#64748b; font-size:.84rem; }
.embedding-health-card__result { display:flex; align-items:center; gap:14px; flex-wrap:wrap; margin-top:14px; color:#475569; font-size:.86rem; }
.settings-risk-alert { border-radius: 16px; }
</style>
