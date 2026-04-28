<template>
  <n-modal :show="show" preset="card" title="新建提示词" class="prompt-modal" @update:show="$emit('update:show', $event)">
    <n-form label-placement="top" :model="form">
      <n-form-item label="内部标识（必填）">
        <n-input v-model:value="form.name" placeholder="例如：chapter_plan / outline" />
      </n-form-item>
      <n-form-item label="中文标题">
        <n-input v-model:value="form.title" placeholder="例如：章节规划提示词" />
      </n-form-item>
      <n-form-item label="标签">
        <n-dynamic-tags v-model:value="form.tags" size="small" placeholder="输入标签后回车" />
      </n-form-item>
      <n-form-item label="提示词内容">
        <n-input v-model:value="form.content" type="textarea" :autosize="{ minRows: 10, maxRows: 30 }" placeholder="输入提示词内容" />
      </n-form-item>
    </n-form>
    <template #footer>
      <n-space justify="end">
        <n-button quaternary @click="$emit('cancel')">取消</n-button>
        <n-button type="primary" :loading="creating" @click="$emit('create')">创建</n-button>
      </n-space>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import type { PromptCreatePayload } from '@/api/admin'

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
