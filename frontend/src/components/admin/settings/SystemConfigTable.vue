<template>
  <n-card :bordered="false">
    <template #header>
      <div class="card-header">
        <div>
          <span class="card-title">系统配置</span>
          <p class="card-subtitle">参数按分类显示。布尔值直接选 true / false，数字参数只允许输入数字。</p>
        </div>
      </div>
    </template>

    <n-spin :show="loading">
      <n-alert v-if="error" type="error" closable @close="$emit('clear-error')">{{ error }}</n-alert>
      <n-data-table :columns="columns" :data="configs" :loading="loading" :bordered="false" :row-key="rowKey" class="config-table" />
    </n-spin>
  </n-card>
</template>

<script setup lang="ts">
import { computed, h, reactive, watch } from 'vue'
import { NButton, NInputNumber, NSelect, NTag, type DataTableColumns, type SelectOption } from 'naive-ui'
import type { SystemConfigViewModel } from '@/composables/admin/useAdminSettings'

const props = defineProps<{ configs: SystemConfigViewModel[]; loading: boolean; error: string | null; saveInline: (config: SystemConfigViewModel, value: string) => Promise<unknown> }>()
const emit = defineEmits<{ edit: [config: SystemConfigViewModel]; 'clear-error': [] }>()

const rowKey = (row: SystemConfigViewModel) => row.key
const draftValues = reactive<Record<string, string>>({})
const savingMap = reactive<Record<string, boolean>>({})

watch(
  () => props.configs,
  configs => {
    for (const config of configs) {
      draftValues[config.key] = config.value ?? ''
    }
  },
  { immediate: true, deep: true }
)

const canInlineEdit = (row: SystemConfigViewModel) => ['boolean', 'number', 'select'].includes(row.valueType)

const saveInline = async (row: SystemConfigViewModel) => {
  savingMap[row.key] = true
  try {
    await props.saveInline(row, draftValues[row.key] ?? '')
  } finally {
    savingMap[row.key] = false
  }
}

const columns = computed<DataTableColumns<SystemConfigViewModel>>(() => [
  {
    title: '分类 / 参数',
    key: 'displayKey',
    minWidth: 240,
    render: row => h('div', { class: 'name-cell' }, [
      h(NTag, { size: 'small', round: true, type: 'info' }, { default: () => row.displayCategory }),
      h('strong', { class: 'name-cell__title' }, row.displayKey),
      h('small', { class: 'name-cell__key' }, row.key),
    ]),
  },
  {
    title: '当前值',
    key: 'value',
    minWidth: 260,
    render: row => {
      if (row.valueType === 'boolean' || row.valueType === 'select') {
        return h(NSelect, {
          value: draftValues[row.key],
          options: (row.options || []) as SelectOption[],
          consistentMenuWidth: false,
          onUpdateValue: (value: string) => {
            draftValues[row.key] = value
          },
        })
      }

      if (row.valueType === 'number') {
        return h(NInputNumber, {
          value: draftValues[row.key] === '' ? null : Number(draftValues[row.key]),
          min: 0,
          step: 1,
          style: 'width: 100%',
          onUpdateValue: (value: number | null) => {
            draftValues[row.key] = value === null ? '' : String(value)
          },
        })
      }

      return h('span', { class: 'static-value' }, formatValue(row))
    },
  },
  { title: '类型', key: 'valueType', width: 96, render: row => typeLabel(row.valueType) },
  { title: '功能说明', key: 'displayDescription', minWidth: 320, ellipsis: { tooltip: true } },
  {
    title: '操作',
    key: 'actions',
    width: 150,
    render: row => canInlineEdit(row)
      ? h('div', { class: 'action-cell' }, [
          h(NButton, {
            size: 'small',
            type: 'primary',
            tertiary: true,
            loading: Boolean(savingMap[row.key]),
            onClick: () => void saveInline(row),
          }, { default: () => '保存' }),
          h(NButton, {
            size: 'small',
            quaternary: true,
            onClick: () => emit('edit', row),
          }, { default: () => '详情' }),
        ])
      : h(NButton, { size: 'small', type: 'primary', tertiary: true, onClick: () => emit('edit', row) }, { default: () => '修改' }),
  },
])

function formatValue(row: SystemConfigViewModel) {
  if (!row.value) return '未设置'
  if (row.valueType === 'password') return '已设置（已隐藏）'
  if (row.valueType === 'boolean') return row.value === 'true' ? '开启 / true' : '关闭 / false'
  return row.value
}

function typeLabel(type: SystemConfigViewModel['valueType']) {
  switch (type) {
    case 'boolean': return '布尔'
    case 'number': return '数字'
    case 'select': return '选项'
    case 'password': return '密码'
    case 'multiline': return '多行'
    default: return '文本'
  }
}
</script>

<style scoped>
.card-header { display:flex; align-items:center; justify-content:space-between; gap:16px; flex-wrap:wrap; }
.card-title { font-size:1.25rem; font-weight:700; color:#1f2937; }
.card-subtitle { margin:6px 0 0; color:#64748b; font-size:.9rem; }
.name-cell { display:grid; gap:6px; }
.name-cell__title { color:#111827; }
.name-cell__key { color:#64748b; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
.static-value { color:#0f172a; }
.action-cell { display:flex; gap:8px; }
</style>
