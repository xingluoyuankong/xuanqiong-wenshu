<template>
  <n-modal :show="show" preset="card" :title="pick('新建提示词', 'New prompt')" class="prompt-modal" @update:show="$emit('update:show', $event)">
    <n-form label-placement="top" :model="form">
      <n-form-item :label="pick('内部标识（必填）', 'Internal identifier (required)')">
        <n-input v-model:value="form.name" :placeholder="pick('例如：chapter_plan / outline', 'For example: chapter_plan / outline')" />
      </n-form-item>
      <n-form-item :label="pick('中文标题', 'Display title')">
        <n-input v-model:value="form.title" :placeholder="pick('例如：章节规划提示词', 'For example: Chapter planning prompt')" />
      </n-form-item>
      <n-form-item :label="pick('标签', 'Tags')">
        <n-dynamic-tags v-model:value="form.tags" size="small" :placeholder="pick('输入标签后回车', 'Type a tag and press Enter')" />
      </n-form-item>
      <n-form-item :label="pick('提示词内容', 'Prompt body')">
        <n-input v-model:value="form.content" type="textarea" :autosize="{ minRows: 10, maxRows: 30 }" :placeholder="pick('输入提示词内容', 'Enter the prompt body')" />
      </n-form-item>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button quaternary @click="$emit('cancel')">{{ pick('取消', 'Cancel') }}</n-button>
        <n-button type="primary" :loading="creating" @click="$emit('create')">{{ pick('创建', 'Create') }}</n-button>
      </n-space>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type { PromptCreatePayload } from '@/api/admin'
import { useLocale } from '@/composables/useLocale'

const { pick } = useLocale()

defineProps<{
  show: boolean
  creating: boolean
  form: PromptCreatePayload
}>()

defineEmits<{
  'update:show': [value: boolean]
  cancel: []
  create: []
}>()
</script>

<style scoped>
.prompt-modal { max-width: min(720px, 90vw); }
</style>
