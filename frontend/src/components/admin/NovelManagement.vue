<!-- AIMETA P=小说管理_管理员小说列表管理|R=小说列表_删除_统计|NR=不含普通用户功能|E=component:NovelManagement|X=ui|A=管理组件|D=vue|S=dom,net|RD=./README.ai -->
<template>
  <n-card class="novel-management-card" size="large" :bordered="false">
    <template #header>
      <div class="card-header">
        <span class="card-title">小说管理</span>
        <n-tag size="small" type="primary" round>共 {{ novels.length }} 项</n-tag>
      </div>
    </template>

    <n-space vertical size="large">
      <n-alert v-if="error" type="error" closable @close="error = null">
        {{ error }}
      </n-alert>

      <n-spin :show="loading">
        <template #default>
          <n-empty
            v-if="!novels.length && !loading"
            description="暂无小说项目"
            class="empty-state"
          />
          <div v-else>
            <NovelMobileList v-if="isMobile" :novels="novels" @view="viewDetails" />
            <n-data-table
              v-else
              :columns="columns"
              :data="novels"
              :pagination="pagination"
              :bordered="false"
              size="small"
              class="novel-table"
            />
          </div>
        </template>
      </n-spin>
    </n-space>
  </n-card>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { NAlert, NCard, NDataTable, NEmpty, NSpin, NTag, NSpace } from 'naive-ui'

import NovelMobileList from './novels/NovelMobileList.vue'
import { createNovelColumns } from './novels/createNovelColumns'
import { useNovelManagement } from '@/composables/admin/useNovelManagement'

const { novels, loading, error, isMobile, pagination, fetchNovels, viewDetails } = useNovelManagement()

const columns = computed(() => createNovelColumns(viewDetails))

onMounted(() => {
  fetchNovels()
})
</script>

<style scoped>
.novel-management-card {
  width: 100%;
  box-sizing: border-box;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.card-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: #1f2937;
}

.novel-table {
  width: 100%;
}

:deep(.table-title-cell) {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

:deep(.table-title) {
  font-weight: 600;
  color: #111827;
}

:deep(.table-subtitle) {
  font-size: 0.75rem;
  color: #6b7280;
  word-break: break-all;
}

:deep(.table-owner),
:deep(.table-progress),
:deep(.table-date) {
  color: #374151;
}

.empty-state {
  padding: 48px 0;
}

@media (max-width: 767px) {
  .card-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .card-title {
    font-size: 1.125rem;
  }
}
</style>
