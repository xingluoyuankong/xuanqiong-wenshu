<!-- AIMETA P=聊天气泡_对话消息展示|R=消息气泡|NR=不含输入功能|E=component:ChatBubble|X=internal|A=气泡组件|D=vue|S=dom|RD=./README.ai -->
<template>
  <div :class="wrapperClass">
    <div :class="bubbleClass">
      <!-- AI 消息支持 markdown 渲染 -->
      <div 
        v-if="type === 'ai'" 
        class="prose prose-sm max-w-none prose-headings:mt-2 prose-headings:mb-1 prose-p:my-1 prose-ul:my-1 prose-ol:my-1 prose-li:my-0"
        v-html="renderedMessage"
      ></div>
      <!-- 用户消息保持原样 -->
      <div v-else>{{ message }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { renderSafeMarkdown } from '@/utils/safeMarkdown'

interface Props {
  message: string
  type: 'user' | 'ai'
}

const props = defineProps<Props>()

const renderedMessage = computed(() => {
  if (props.type === 'ai') {
    return renderSafeMarkdown(props.message)
  }
  return props.message
})

const wrapperClass = computed(() => {
  return `w-full flex ${props.type === 'ai' ? 'justify-start' : 'justify-end'}`
})

const bubbleClass = computed(() => {
  const baseClass = 'max-w-md lg:max-w-lg p-4 rounded-lg shadow-md fade-in'
  const typeClass = props.type === 'ai' ? 'chat-bubble-ai' : 'chat-bubble-user'
  return `${baseClass} ${typeClass}`
})
</script>