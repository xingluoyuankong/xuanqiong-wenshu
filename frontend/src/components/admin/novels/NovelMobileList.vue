<template>
  <n-space vertical size="large">
    <n-card
      v-for="novel in novels"
      :key="novel.id"
      size="small"
      embedded
      class="novel-card"
    >
      <template #header>
        <div class="mobile-card-header">
          <span class="mobile-card-title">{{ novel.title }}</span>
          <n-tag size="small" type="info" round>{{ novel.genre || pick('未分类', 'Uncategorised') }}</n-tag>
        </div>
      </template>
      <div class="mobile-meta">
        <span class="mobile-label">{{ pick('编号', 'ID') }}</span>
        <span class="mobile-value">{{ novel.id }}</span>
      </div>
      <div class="mobile-meta">
        <span class="mobile-label">{{ pick('创作者', 'Author') }}</span>
        <span class="mobile-value">{{ novel.owner_username }}</span>
      </div>
      <div class="mobile-meta">
        <span class="mobile-label">{{ pick('进度', 'Progress') }}</span>
        <span class="mobile-value">{{ formatProgress(novel) }}</span>
      </div>
      <div class="mobile-meta">
        <span class="mobile-label">{{ pick('最近更新', 'Last updated') }}</span>
        <span class="mobile-value">{{ formatDate(novel.last_edited) }}</span>
      </div>
      <template #footer>
        <n-button type="primary" size="small" block @click="$emit('view', novel.id)">
          {{ pick('查看详情', 'View details') }}
        </n-button>
      </template>
    </n-card>
  </n-space>
</template>

<script setup lang="ts">
import type { AdminNovelSummary } from '@/api/admin'
import { useLocale } from '@/composables/useLocale'
import { formatAdminNovelDate, formatAdminNovelProgress } from '@/composables/admin/useNovelManagement'

const { pick } = useLocale()

const props = defineProps<{
  novels: AdminNovelSummary[]
}>()

defineEmits<{
  view: [novelId: string]
}>()

const formatDate = formatAdminNovelDate
const formatProgress = (novel: Pick<AdminNovelSummary, 'completed_chapters' | 'total_chapters'>) =>
  formatAdminNovelProgress(novel)
</script>

<style scoped>
.novel-card {
  border-radius: 16px;
}

.mobile-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.mobile-card-title {
  font-size: 1rem;
  font-weight: 600;
  color: #111827;
}

.mobile-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 10px;
  font-size: 0.875rem;
  color: #4b5563;
  word-break: break-word;
}

.mobile-label {
  color: #6b7280;
}

.mobile-value {
  color: #111827;
  font-weight: 500;
  text-align: right;
  margin-left: 12px;
}
</style>
