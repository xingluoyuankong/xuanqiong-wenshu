<template>
  <n-card :bordered="false">
    <template #header>
      <div class="card-header">
        <div>
          <span class="card-title">{{ pick('每日请求额度', 'Daily request quota') }}</span>
          <p class="card-subtitle">{{ pick(
            '控制“未配置个人 API Key 的用户”每天最多能发起多少次请求。',
            'Caps how many requests users without a personal API key can make per day.'
          ) }}</p>
        </div>
        <n-button quaternary size="small" :loading="loading" @click="$emit('refresh')">{{ pick('刷新', 'Refresh') }}</n-button>
      </div>
    </template>

    <n-spin :show="loading">
      <n-alert v-if="error" type="error" closable @close="$emit('clear-error')">{{ error }}</n-alert>
      <n-form label-placement="top" class="limit-form">
        <n-form-item :label="pick('每日请求上限', 'Daily request cap')">
          <n-input-number :value="limit" :min="0" :step="10" :placeholder="pick('请输入每日请求上限', 'Enter the daily request cap')" @update:value="$emit('update:limit', $event)" />
        </n-form-item>
        <p class="limit-hint">{{ pick(
          '说明：配置为 0 表示完全不允许未配置个人 API Key 的用户发起请求。',
          'Note: setting this to 0 blocks all requests from users without a personal API key.'
        ) }}</p>
        <n-space justify="end">
          <n-button type="primary" :loading="saving" @click="$emit('save')">{{ pick('保存设置', 'Save settings') }}</n-button>
        </n-space>
      </n-form>
    </n-spin>
  </n-card>
</template>

<script setup lang="ts">
import { useLocale } from '@/composables/useLocale'

const { pick } = useLocale()

defineProps<{ limit: number | null; loading: boolean; saving: boolean; error: string | null }>()
defineEmits<{ 'update:limit': [value: number | null]; refresh: []; save: []; 'clear-error': [] }>()
</script>

<style scoped>
.card-header { display:flex; align-items:center; justify-content:space-between; gap:16px; flex-wrap:wrap; }
.card-title { font-size:1.25rem; font-weight:700; color:#1f2937; }
.card-subtitle { margin:6px 0 0; color:#64748b; font-size:.9rem; }
.limit-form { max-width:420px; }
.limit-hint { margin:-4px 0 12px; color:#64748b; line-height:1.7; font-size:.9rem; }
@media (max-width: 767px) { .card-title { font-size:1.125rem; } }
</style>
