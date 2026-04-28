<template>
  <n-space vertical size="large" class="admin-settings">
    <n-alert type="info" :show-icon="false" class="settings-risk-alert">
      这里只做“修改参数”，不再提供前端删除入口。每个参数都给出中文名称、参数分类、当前值和用途说明。
    </n-alert>

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
import { onMounted } from 'vue'
import { NAlert, NSpace } from 'naive-ui'

import DailyLimitCard from './settings/DailyLimitCard.vue'
import SystemConfigModal from './settings/SystemConfigModal.vue'
import SystemConfigTable from './settings/SystemConfigTable.vue'
import { useAdminSettings } from '@/composables/admin/useAdminSettings'

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
.settings-risk-alert { border-radius: 16px; }
</style>
