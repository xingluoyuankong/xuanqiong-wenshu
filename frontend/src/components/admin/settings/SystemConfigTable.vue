<template>
  <n-card :bordered="false">
    <template #header>
      <div class="card-header">
        <div>
          <span class="card-title">{{ pick('系统配置', 'System configuration') }}</span>
          <p class="card-subtitle">{{ pick(
            '参数按分类显示。布尔值直接选 true / false，数字参数只允许输入数字。',
            'Parameters are grouped by category. Booleans are picked as true / false, and numeric parameters accept numbers only.'
          ) }}</p>
        </div>
      </div>
    </template>

    <n-spin :show="loading">
      <n-alert v-if="error" type="error" closable @close="$emit('clear-error')">{{ error }}</n-alert>
      <div class="config-table-shell">
        <n-data-table :columns="columns" :data="configs" :loading="loading" :bordered="false" :row-key="rowKey" class="config-table" />
      </div>
    </n-spin>
  </n-card>
</template>

<script setup lang="ts">
import { computed, h, reactive, watch } from 'vue'
import { NButton, NInputNumber, NSelect, NTag, type DataTableColumns, type SelectOption } from 'naive-ui'
import { useLocale } from '@/composables/useLocale'
import type { SystemConfigViewModel } from '@/composables/admin/useAdminSettings'

const { pick } = useLocale()

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
    title: pick('分类 / 参数', 'Category / parameter'),
    key: 'displayKey',
    minWidth: 240,
    render: row => h('div', { class: 'name-cell' }, [
      h(NTag, { size: 'small', round: true, type: 'info' }, { default: () => row.displayCategory }),
      h('strong', { class: 'name-cell__title' }, row.displayKey),
      h('small', { class: 'name-cell__key' }, row.key),
    ]),
  },
  {
    title: pick('当前值', 'Current value'),
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
  { title: pick('类型', 'Type'), key: 'valueType', width: 96, render: row => typeLabel(row.valueType) },
  { title: pick('功能说明', 'What it does'), key: 'displayDescription', minWidth: 320, ellipsis: { tooltip: true } },
  {
    title: pick('操作', 'Actions'),
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
          }, { default: () => pick('保存', 'Save') }),
          h(NButton, {
            size: 'small',
            quaternary: true,
            onClick: () => emit('edit', row),
          }, { default: () => pick('详情', 'Details') }),
        ])
      : h(NButton, { size: 'small', type: 'primary', tertiary: true, onClick: () => emit('edit', row) }, { default: () => pick('修改', 'Edit') }),
  },
])

function formatValue(row: SystemConfigViewModel) {
  if (!row.value) return pick('未设置', 'Not set')
  if (row.valueType === 'password') return pick('已设置（已隐藏）', 'Set (hidden)')
  if (row.valueType === 'boolean') return row.value === 'true' ? pick('开启 / true', 'On / true') : pick('关闭 / false', 'Off / false')
  return row.value
}

function typeLabel(type: SystemConfigViewModel['valueType']) {
  switch (type) {
    case 'boolean': return pick('布尔', 'Boolean')
    case 'number': return pick('数字', 'Number')
    case 'select': return pick('选项', 'Select')
    case 'password': return pick('密码', 'Password')
    case 'multiline': return pick('多行', 'Multiline')
    default: return pick('文本', 'Text')
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
.config-table-shell {
  width: 100%;
  overflow-x: auto;
  overflow-y: hidden;
}
.config-table-shell :deep(.n-data-table) {
  min-width: 920px;
}
@media (max-width: 720px) {
  .config-table-shell {
    margin-inline: -8px;
    padding-inline: 8px;
  }
}
</style>
