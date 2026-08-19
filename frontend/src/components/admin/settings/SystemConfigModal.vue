<template>
  <n-modal :show="show" preset="card" :title="title" class="config-modal" :style="{ width: '720px', maxWidth: '94vw' }" @update:show="$emit('update:show', $event)">
    <div class="config-modal__intro">
      <div>
        <strong>{{ form.displayKey || form.key }}</strong>
        <p>{{ form.displayDescription }}</p>
      </div>
      <n-tag round>{{ form.displayCategory || pick('系统参数', 'System parameter') }}</n-tag>
    </div>

    <n-form label-placement="top" :model="form">
      <n-grid :cols="2" :x-gap="16" responsive="screen">
        <n-form-item-gi :label="pick('参数 Key', 'Parameter key')">
          <n-input :value="form.key" disabled />
        </n-form-item-gi>
        <n-form-item-gi :label="pick('参数类型', 'Value type')">
          <n-input :value="typeLabel" disabled />
        </n-form-item-gi>
      </n-grid>

      <n-form-item :label="pick('参数值', 'Value')">
        <n-select v-if="form.valueType === 'boolean' || form.valueType === 'select'" v-model:value="form.value" :options="normalizedOptions" />
        <n-input-number v-else-if="form.valueType === 'number'" :value="numericValue" class="w-full" @update:value="handleNumberChange" />
        <n-input v-else-if="form.valueType === 'multiline'" v-model:value="form.value" type="textarea" :rows="5" :placeholder="pick('请输入参数值', 'Enter the value')" />
        <n-input v-else v-model:value="form.value" :type="form.valueType === 'password' ? 'password' : 'text'" :placeholder="pick('请输入参数值', 'Enter the value')" show-password-on="click" />
      </n-form-item>

      <n-form-item :label="pick('中文说明', 'Description')">
        <n-input v-model:value="form.description" type="textarea" :rows="3" :placeholder="pick('请输入参数说明', 'Describe this parameter')" />
      </n-form-item>
    </n-form>

    <template #footer>
      <n-space justify="end">
        <n-button quaternary @click="$emit('cancel')">{{ pick('取消', 'Cancel') }}</n-button>
        <n-button type="primary" :loading="saving" @click="$emit('submit')">{{ pick('保存修改', 'Save changes') }}</n-button>
      </n-space>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { NButton, NForm, NFormItem, NFormItemGi, NGrid, NInput, NInputNumber, NModal, NSelect, NSpace, NTag } from 'naive-ui'
import { useLocale } from '@/composables/useLocale'
import type { SystemConfigViewModel } from '@/composables/admin/useAdminSettings'

const { pick } = useLocale()

const props = defineProps<{ show: boolean; title: string; saving: boolean; form: SystemConfigViewModel }>()
defineEmits<{ 'update:show': [value: boolean]; cancel: []; submit: [] }>()

const normalizedOptions = computed(() => props.form.options || [])
const numericValue = computed(() => Number(props.form.value || 0))
const typeLabel = computed(() => {
  switch (props.form.valueType) {
    case 'boolean': return pick('布尔值（true / false）', 'Boolean (true / false)')
    case 'number': return pick('数字', 'Number')
    case 'select': return pick('下拉选项', 'Select')
    case 'password': return pick('密码 / 密钥', 'Password / secret')
    case 'multiline': return pick('多行文本', 'Multiline text')
    default: return pick('文本', 'Text')
  }
})

function handleNumberChange(value: number | null) {
  props.form.value = value === null ? '' : String(value)
}
</script>

<style scoped>
.config-modal { max-width:min(760px, 94vw); }
.config-modal__intro { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; margin-bottom:16px; padding:14px; border-radius:16px; background:#f8fafc; border:1px solid #e2e8f0; }
.config-modal__intro p { margin:6px 0 0; color:#64748b; line-height:1.7; }
</style>
