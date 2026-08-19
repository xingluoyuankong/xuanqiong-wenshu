<!-- AIMETA P=统计面板_系统使用统计|R=统计图表|NR=不含数据修改|E=component:Statistics|X=ui|A=统计组件|D=vue,chart.js|S=dom,net|RD=./README.ai -->
<template>
  <n-card :bordered="false" class="admin-card">
    <template #header>
      <div class="card-header">
        <div>
          <span class="card-title">{{ pick('数据总览', 'Data overview') }}</span>
          <p class="card-subtitle">{{ pick(
            '先看累计规模，再结合刷新时间判断当前后台数据是否可信。',
            'Read the cumulative totals first, then check the refresh time to judge how current this data is.'
          ) }}</p>
        </div>
        <n-button quaternary size="small" @click="fetchStats" :loading="loading">
          {{ pick('刷新', 'Refresh') }}
        </n-button>
      </div>
    </template>

    <n-space vertical size="large">
      <n-alert v-if="error" type="error" closable @close="error = null">
        {{ error }}
      </n-alert>

      <n-spin :show="loading">
        <div class="stats-meta-row">
          <span class="stats-meta-pill">{{ pick('口径：累计统计', 'Scope: cumulative') }}</span>
          <span class="stats-meta-pill">{{ pick(`最近刷新：${lastUpdatedAt}`, `Last refreshed: ${lastUpdatedAt}`) }}</span>
        </div>
        <n-grid :cols="gridCols" :x-gap="16" :y-gap="16">
          <n-gi>
            <n-card class="stat-card" :bordered="false">
              <div class="stat-icon">📚</div>
              <n-statistic :label="pick('小说总数', 'Novels')" :value="stats?.novel_count ?? 0" show-separator>
                <template #suffix>{{ pick('部', ' total') }}</template>
              </n-statistic>
            </n-card>
          </n-gi>
          <n-gi>
            <n-card class="stat-card" :bordered="false">
              <div class="stat-icon">⚡</div>
              <n-statistic :label="pick('API 请求总数', 'API requests')" :value="stats?.api_request_count ?? 0" show-separator>
                <template #suffix>{{ pick('次', ' calls') }}</template>
              </n-statistic>
            </n-card>
          </n-gi>
        </n-grid>
      </n-spin>
    </n-space>
  </n-card>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  NAlert,
  NButton,
  NCard,
  NGi,
  NGrid,
  NSpin,
  NStatistic,
  NSpace
} from 'naive-ui'

import { AdminAPI, type Statistics } from '@/api/admin'
import { useResponsiveFlag } from '@/composables/admin/useResponsiveFlag'
import { useLocale } from '@/composables/useLocale'

const { pick, formatDateTime } = useLocale()

const stats = ref<Statistics | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
// 存原始时间戳而不是格式化后的字符串，切换语言时才能重新格式化
const lastRefreshedAt = ref<string | null>(null)
const { matched: isMobile } = useResponsiveFlag(768)

const gridCols = computed(() => (isMobile.value ? 1 : 2))

const lastUpdatedAt = computed(() => {
  if (!lastRefreshedAt.value) return pick('尚未刷新', 'Not refreshed yet')
  return formatDateTime(lastRefreshedAt.value) || lastRefreshedAt.value
})

const fetchStats = async () => {
  loading.value = true
  error.value = null
  try {
    stats.value = await AdminAPI.getStatistics()
    lastRefreshedAt.value = new Date().toISOString()
  } catch (err) {
    error.value = err instanceof Error ? err.message : pick('获取统计数据失败', 'Failed to load the statistics')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchStats()
})
</script>

<style scoped>
.admin-card {
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

.card-subtitle {
  margin-top: 6px;
  font-size: 0.9rem;
  line-height: 1.6;
  color: #64748b;
}

.stats-meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 16px;
}

.stats-meta-pill {
  display: inline-flex;
  align-items: center;
  padding: 6px 12px;
  border-radius: 999px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  color: #475569;
  font-size: 0.82rem;
  font-weight: 600;
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px;
  border-radius: 18px;
  background: linear-gradient(135deg, rgba(79, 70, 229, 0.08), rgba(79, 70, 229, 0));
}

.stat-icon {
  font-size: 28px;
  line-height: 1;
}

@media (max-width: 767px) {
  .card-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .card-title {
    font-size: 1.125rem;
  }

  .stat-card {
    padding: 16px;
  }
}
</style>
