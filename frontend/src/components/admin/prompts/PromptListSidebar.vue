<template>
  <div class="prompt-sidebar">
    <div class="prompt-sidebar__header">
      <strong>提示词索引</strong>
      <span>{{ prompts.length }} 项</span>
    </div>
    <n-scrollbar class="prompt-scroll">
      <n-empty v-if="!prompts.length && !loading" description="暂无提示词" />
      <n-space v-else vertical size="small">
        <n-button
          v-for="prompt in prompts"
          :key="prompt.id"
          type="primary"
          :ghost="selectedPromptId !== prompt.id"
          quaternary
          block
          @click="$emit('select', prompt)"
        >
          <div class="prompt-item">
            <span class="prompt-name">{{ prompt.title || translatePromptName(prompt.name) }}</span>
            <n-tag v-if="prompt.tags?.length" size="tiny" type="info">{{ prompt.tags.length }}</n-tag>
          </div>
        </n-button>
      </n-space>
    </n-scrollbar>
  </div>
</template>

<script setup lang="ts">
import type { PromptItem } from '@/api/admin'
import { translatePromptName } from '../adminI18n'

defineProps<{
  prompts: PromptItem[]
  selectedPromptId: number | null
  loading: boolean
}>()

defineEmits<{
  select: [prompt: PromptItem]
}>()
</script>

<style scoped>
.prompt-sidebar {
  width: 250px;
  flex-shrink: 0;
  display: grid;
  gap: 10px;
  border-right: 1px solid #e2e8f0;
  padding-right: 12px;
}
.prompt-sidebar__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 0.82rem;
  color: #64748b;
}
.prompt-scroll { max-height: 560px; }
.prompt-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  gap: 8px;
}
.prompt-name {
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  font-weight: 700;
  color: #1f2937;
  text-align: left;
}
@media (max-width: 1023px) {
  .prompt-sidebar { width: 100%; border-right: 0; padding-right: 0; }
}
</style>
