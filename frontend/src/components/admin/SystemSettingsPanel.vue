<template>
  <div class="admin-section-shell">
    <n-card :bordered="false" class="admin-section-card">
      <template #header>
        <div class="admin-section-head">
          <div>
            <h2>系统配置</h2>
            <p>和数据总览、故障诊断一样，直接作为管理台内部页面展示。按分类查看并就地修改布尔值、数字值和选项值。</p>
          </div>
        </div>
      </template>
      <SettingsManagement />
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { NCard } from 'naive-ui'
import SettingsManagement from './SettingsManagement.vue'
</script>

<style scoped>
.admin-section-card { border-radius: 20px; }
.admin-section-head h2 { margin: 0; font-size: 1.08rem; color: #0f172a; }
.admin-section-head p { margin: 6px 0 0; font-size: 0.84rem; line-height: 1.65; color: #64748b; }
:deep(.admin-settings) { gap: 16px !important; }
:deep(.settings-risk-alert) { margin-bottom: 4px; }
</style>
