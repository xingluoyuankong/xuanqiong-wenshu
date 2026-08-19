<!-- AIMETA P=章节列表_章节目录展示|R=章节列表渲染|NR=不含章节编辑|E=component:ChapterList|X=internal|A=列表组件|D=vue|S=dom|RD=./README.ai -->
<template>
  <div class="bg-white rounded-lg shadow-sm p-6">
    <h3 class="text-lg font-semibold text-gray-800 mb-4">{{ pick('章节列表', 'Chapter list') }}</h3>

    <div v-if="chapterOutline.length === 0" class="text-gray-500 text-center py-8">
      {{ pick('暂无章节大纲', 'No chapter outline yet') }}
    </div>

    <div v-else class="space-y-3">
      <div
        v-for="outline in chapterOutline"
        :key="outline.chapter_number"
        class="border rounded-lg p-3 hover:bg-gray-50 transition-colors"
      >
        <div class="flex justify-between items-start">
          <div class="flex-1">
            <h4 class="font-medium text-gray-800">
              {{ pick(`第${outline.chapter_number}章: ${outline.title}`, `Chapter ${outline.chapter_number}: ${outline.title}`) }}
            </h4>
            <p class="text-sm text-gray-600 mt-1">{{ outline.summary }}</p>

            <!-- 章节状态 -->
            <div class="mt-2">
              <span
                :class="getChapterStatusClass(outline.chapter_number)"
                class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium"
              >
                {{ chapterStatusLabel(outline.chapter_number) }}
              </span>
            </div>
          </div>

          <div class="flex flex-col gap-2 ml-4">
            <!-- 查看按钮 -->
            <button
              v-if="isChapterCompleted(outline.chapter_number)"
              @click="$emit('selectChapter', outline.chapter_number)"
              class="px-3 py-1 bg-blue-100 text-blue-700 rounded hover:bg-blue-200 transition-colors text-sm"
            >
              {{ pick('查看', 'View') }}
            </button>

            <!-- 生成按钮 -->
            <button
              v-if="!isChapterCompleted(outline.chapter_number)"
              @click="$emit('generateChapter', outline.chapter_number)"
              class="px-3 py-1 bg-green-100 text-green-700 rounded hover:bg-green-200 transition-colors text-sm"
            >
              {{ pick('生成', 'Generate') }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useLocale } from '@/composables/useLocale'
import type { Chapter, ChapterOutline } from '@/api/novel'

const { pick } = useLocale()

interface Props {
  chapters: Chapter[]
  chapterOutline: ChapterOutline[]
}

const props = defineProps<Props>()

defineEmits<{
  selectChapter: [chapterNumber: number]
  generateChapter: [chapterNumber: number]
}>()

const isChapterCompleted = (chapterNumber: number) => {
  return props.chapters.some(ch => ch.chapter_number === chapterNumber && ch.content)
}

// 状态是内部枚举，展示文案与配色都从它派生，避免翻译后 switch 匹配失效
type ChapterStatus = 'not-started' | 'completed' | 'pending-selection'

const getChapterStatus = (chapterNumber: number): ChapterStatus => {
  const chapter = props.chapters.find(ch => ch.chapter_number === chapterNumber)
  if (!chapter) return 'not-started'
  if (chapter.content) return 'completed'
  if (chapter.versions && chapter.versions.length > 0) return 'pending-selection'
  return 'not-started'
}

const chapterStatusLabel = (chapterNumber: number) => {
  switch (getChapterStatus(chapterNumber)) {
    case 'completed':
      return pick('已完成', 'Completed')
    case 'pending-selection':
      return pick('待选择', 'Awaiting selection')
    default:
      return pick('未开始', 'Not started')
  }
}

const getChapterStatusClass = (chapterNumber: number) => {
  switch (getChapterStatus(chapterNumber)) {
    case 'completed':
      return 'bg-green-100 text-green-800'
    case 'pending-selection':
      return 'bg-sky-100 text-sky-800'
    default:
      return 'bg-gray-100 text-gray-800'
  }
}
</script>