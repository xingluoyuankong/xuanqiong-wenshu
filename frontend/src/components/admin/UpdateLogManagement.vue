<!-- AIMETA P=更新日志管理_系统更新记录|R=日志CRUD|NR=不含系统更新|E=component:UpdateLogManagement|X=ui|A=日志组件|D=vue|S=dom,net|RD=./README.ai -->
<template>
  <n-card :bordered="false" class="admin-card">
    <template #header>
      <div class="card-header">
        <span class="card-title">{{ pick('更新日志管理', 'Update log management') }}</span>
        <n-button quaternary size="small" @click="fetchLogs" :loading="loading">
          {{ pick('刷新', 'Refresh') }}
        </n-button>
      </div>
    </template>

    <n-space vertical size="large">
      <n-alert v-if="error" type="error" closable @close="error = null">
        {{ error }}
      </n-alert>

      <n-card size="small" class="form-card">
        <n-form :model="form" label-placement="top">
          <div class="form-tip">{{ pick(
            '这里发布的是用户可见更新说明。若勾选置顶，会优先展示在日志列表顶部。',
            'What you publish here is the user-facing release note. Pinned entries show at the top of the list.'
          ) }}</div>
          <n-form-item :label="pick('更新内容', 'Release note')">
            <n-input
              v-model:value="form.content"
              type="textarea"
              :autosize="{ minRows: 3, maxRows: 10 }"
              :placeholder="pick('输入新的更新日志...', 'Write a new update log…')"
            />
          </n-form-item>
          <n-form-item :label="pick('置顶', 'Pin')">
            <n-switch v-model:value="form.isPinned" />
          </n-form-item>
          <n-space justify="end">
            <n-button type="primary" :loading="submitting" @click="addLog" :disabled="!form.content.trim()">
              {{ pick('发布日志', 'Publish') }}
            </n-button>
          </n-space>
        </n-form>
      </n-card>

      <n-spin :show="loading">
        <n-empty v-if="!logs.length && !loading" :description="pick('目前还没有更新记录', 'No update records yet')" />
        <n-space v-else vertical size="large">
          <n-card
            v-for="log in orderedLogs"
            :key="log.id"
            :bordered="false"
            size="small"
            class="log-card"
          >
            <div class="log-header">
              <n-space align="center" size="small">
                <n-tag v-if="log.is_pinned" type="warning" :bordered="false">{{ pick('置顶', 'Pinned') }}</n-tag>
                <span class="log-date">{{ formatDate(log.created_at) }}</span>
                <span v-if="log.created_by" class="log-author">by {{ log.created_by }}</span>
              </n-space>
              <n-space size="small">
                <n-switch
                  :value="log.is_pinned"
                  size="small"
                  :loading="togglingId === log.id"
                  @update:value="(value: boolean) => togglePin(log, value)"
                >
                  <template #checked>{{ pick('已置顶', 'Pinned') }}</template>
                  <template #unchecked>{{ pick('未置顶', 'Not pinned') }}</template>
                </n-switch>
                <n-popconfirm
                  placement="left"
                  :positive-text="pick('删除', 'Delete')"
                  :negative-text="pick('取消', 'Cancel')"
                  type="error"
                  @positive-click="() => deleteLog(log.id)"
                >
                  <template #trigger>
                    <n-button quaternary type="error" size="small" :loading="deletingId === log.id">
                      {{ pick('删除', 'Delete') }}
                    </n-button>
                  </template>
                  {{ pick(
                    `确认删除这条更新日志？“${logExcerpt(log.content)}” 删除后无法恢复。`,
                    `Delete this update log? “${logExcerpt(log.content)}” This cannot be undone.`
                  ) }}
                </n-popconfirm>
              </n-space>
            </div>
            <div class="log-content">
              {{ log.content }}
            </div>
          </n-card>
        </n-space>
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
  NEmpty,
  NForm,
  NFormItem,
  NInput,
  NPopconfirm,
  NSpace,
  NSpin,
  NSwitch,
  NTag
} from 'naive-ui'

import { AdminAPI, type UpdateLog } from '@/api/admin'
import { useAlert } from '@/composables/useAlert'
import { useLocale } from '@/composables/useLocale'

const { showAlert } = useAlert()
const { pick, formatDateTime } = useLocale()

const logs = ref<UpdateLog[]>([])
const loading = ref(false)
const submitting = ref(false)
const deletingId = ref<number | null>(null)
const togglingId = ref<number | null>(null)
const error = ref<string | null>(null)

const form = ref({
  content: '',
  isPinned: false
})

const orderedLogs = computed(() => {
  return [...logs.value].sort((a, b) => {
    if (a.is_pinned && !b.is_pinned) return -1
    if (!a.is_pinned && b.is_pinned) return 1
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  })
})

const fetchLogs = async () => {
  loading.value = true
  error.value = null
  try {
    logs.value = await AdminAPI.listUpdateLogs()
  } catch (err) {
    error.value = err instanceof Error ? err.message : pick('获取更新日志失败', 'Failed to load the update logs')
  } finally {
    loading.value = false
  }
}

const resetForm = () => {
  form.value.content = ''
  form.value.isPinned = false
}

const addLog = async () => {
  if (!form.value.content.trim()) return
  submitting.value = true
  try {
    const created = await AdminAPI.createUpdateLog({
      content: form.value.content.trim(),
      is_pinned: form.value.isPinned
    })
    logs.value.unshift(created)
    resetForm()
    showAlert(pick('更新日志发布成功', 'Update log published'), 'success')
  } catch (err) {
    showAlert(err instanceof Error ? err.message : pick('发布失败', 'Publish failed'), 'error')
  } finally {
    submitting.value = false
  }
}

const deleteLog = async (id: number) => {
  deletingId.value = id
  try {
    await AdminAPI.deleteUpdateLog(id)
    logs.value = logs.value.filter((item) => item.id !== id)
    showAlert(pick('删除成功', 'Deleted'), 'success')
  } catch (err) {
    showAlert(err instanceof Error ? err.message : pick('删除失败', 'Delete failed'), 'error')
  } finally {
    deletingId.value = null
  }
}

const togglePin = async (log: UpdateLog, value: boolean) => {
  togglingId.value = log.id
  try {
    const updated = await AdminAPI.updateUpdateLog(log.id, { is_pinned: value })
    const index = logs.value.findIndex((item) => item.id === log.id)
    if (index !== -1) {
      logs.value.splice(index, 1, updated)
    }
  } catch (err) {
    showAlert(err instanceof Error ? err.message : pick('更新失败', 'Update failed'), 'error')
  } finally {
    togglingId.value = null
  }
}

// 删除确认里的日志摘要，超长截断
const logExcerpt = (content: string) => `${content.slice(0, 30)}${content.length > 30 ? '…' : ''}`

const formatDate = (date: string) => formatDateTime(date) || date

onMounted(fetchLogs)
</script>

<style scoped>
.admin-card {
  width: 100%;
}

.form-tip {
  margin-bottom: 12px;
  font-size: 0.88rem;
  line-height: 1.6;
  color: #64748b;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.card-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: #1f2937;
}

.form-card {
  border-radius: 16px;
}

.log-card {
  border-radius: 16px;
  background: linear-gradient(135deg, rgba(15, 118, 110, 0.06), rgba(15, 118, 110, 0));
}

.log-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 10px;
}

.log-date {
  font-size: 0.85rem;
  color: #4b5563;
}

.log-author {
  font-size: 0.85rem;
  color: #6b7280;
}

.log-content {
  font-size: 0.95rem;
  color: #1f2937;
  line-height: 1.6;
  white-space: pre-wrap;
}

@media (max-width: 767px) {
  .card-title {
    font-size: 1.125rem;
  }
}
</style>
