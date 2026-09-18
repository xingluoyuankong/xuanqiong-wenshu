<template>
  <div class="admin-section-shell llm-admin-shell">
    <n-card :bordered="false" class="admin-section-card">
      <template #header>
        <div class="admin-section-head">
          <div>
            <h2>LLM 配置</h2>
            <p>保持在管理台内部的同级页面，不再跳转到独立页面。保留真实配置能力，同时压缩多余的视觉包装。</p>
          </div>
        </div>
      </template>
      <LLMSettings />
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { NCard } from 'naive-ui'
import LLMSettings from '../LLMSettings.vue'
</script>

<style scoped>
.admin-section-card { border-radius: 20px; }
.admin-section-head h2 { margin: 0; font-size: 1.08rem; color: #0f172a; }
.admin-section-head p { margin: 6px 0 0; font-size: 0.84rem; line-height: 1.65; color: #64748b; }
:deep(.llm-admin-shell .admin-section-card .n-card__content) { padding-top: 0; }
:deep(.llm-settings-root),
:deep([ref='settingsRootRef']) {
  border-radius: 20px;
}
:deep(.llm-admin-shell #llm-summary) {
  background: #f8fafc !important;
  color: #0f172a !important;
  border-bottom: 1px solid #e2e8f0;
  padding: 18px 20px !important;
}
:deep(.llm-admin-shell #llm-summary .text-white),
:deep(.llm-admin-shell #llm-summary .text-slate-200),
:deep(.llm-admin-shell #llm-summary .text-slate-300),
:deep(.llm-admin-shell #llm-summary .text-slate-400) {
  color: #475569 !important;
}
:deep(.llm-admin-shell #llm-summary .bg-white\/10),
:deep(.llm-admin-shell #llm-summary .bg-white\/15) {
  background: #ffffff !important;
  border-color: #e2e8f0 !important;
}
</style>
