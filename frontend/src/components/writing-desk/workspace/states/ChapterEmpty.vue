<template>
  <div class="ce-shell">
    <div class="ce-panel">
      <div class="ce-icon">*</div>
      <h3>这一章还没有正文</h3>

      <div v-if="canGenerate" class="space-y-4">
        <p>可以直接开始生成这一章。建议先确认上一章已完成，再继续推进。</p>
        <button
          type="button"
          class="md-btn md-btn-filled md-ripple ce-primary"
          :disabled="generatingChapter === chapterNumber"
          @click="$emit('generateChapter', chapterNumber)"
        >
          {{ generatingChapter === chapterNumber ? '生成中...' : `开始生成第 ${chapterNumber} 章` }}
        </button>
      </div>

      <div v-else class="space-y-3">
        <p>当前还不能生成这一章，前面的章节需要先完成，避免上下文断裂。</p>
        <div class="ce-lock">请按顺序推进章节</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  chapterNumber: number
  generatingChapter: number | null
  canGenerate: boolean
}>()

defineEmits(['generateChapter'])
</script>

<style scoped>
.ce-shell {
  display: grid;
  justify-items: center;
  padding: 20px 0 8px;
}

.ce-panel {
  width: min(560px, 100%);
  padding: 28px;
  text-align: center;
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.88);
  border: 1px solid rgba(148, 163, 184, 0.18);
  box-shadow: 0 24px 48px rgba(15, 23, 42, 0.06);
}

.ce-icon {
  width: 60px;
  height: 60px;
  margin: 0 auto 18px;
  display: grid;
  place-items: center;
  border-radius: 18px;
  background: rgba(37, 99, 235, 0.08);
  color: #1d4ed8;
  font-size: 1.6rem;
  font-weight: 700;
}

.ce-panel h3 {
  color: #0f172a;
  font-size: 1.45rem;
  font-weight: 700;
}

.ce-panel p {
  color: #475569;
  margin-top: 12px;
  line-height: 1.8;
}

.ce-primary {
  min-width: 220px;
}

.ce-lock {
  display: inline-flex;
  align-items: center;
  min-height: 34px;
  padding: 0 14px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.06);
  color: #475569;
  font-size: 0.85rem;
  font-weight: 700;
}
</style>
