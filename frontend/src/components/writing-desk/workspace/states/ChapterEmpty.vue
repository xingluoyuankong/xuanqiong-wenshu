<template>
  <div class="ce-shell">
    <section class="ce-panel">
      <div class="ce-header">
        <div class="ce-orbit" aria-hidden="true">
          <span></span>
          <strong>{{ chapterNumber }}</strong>
        </div>
        <div class="ce-copy">
          <p class="ce-kicker">{{ pick('章节待生成', 'Chapter not generated') }}</p>
          <h3>{{ pick(`第 ${chapterNumber} 章还没有正文`, `Chapter ${chapterNumber} has no text yet`) }}</h3>
        </div>
      </div>
      <p class="ce-desc">
        <template v-if="canGenerate">
          {{ pick(
            '已经轮到这一章进入正文生产。点击开始后，系统会在后台生成候选版本。',
            'This chapter is next in line for drafting. Once you start, candidate versions are generated in the background.'
          ) }}
        </template>
        <template v-else>
          {{ pick(
            '当前章节还被顺序锁保护。请先完成前置章节。',
            'This chapter is still held by the sequence lock — finish the earlier chapters first.'
          ) }}
        </template>
      </p>
      <div class="ce-path">
        <div :class="['ce-step', canGenerate ? 'ce-step--done' : '']">
          <span>1</span>
          <strong>{{ pick('确认前文', 'Confirm earlier text') }}</strong>
        </div>
        <div :class="['ce-step', canGenerate ? 'ce-step--active' : 'ce-step--locked']">
          <span>2</span>
          <strong>{{ pick('生成本章', 'Generate this chapter') }}</strong>
        </div>
        <div class="ce-step ce-step--future">
          <span>3</span>
          <strong>{{ pick('评审确认', 'Review and confirm') }}</strong>
        </div>
      </div>
      <div :class="['ce-hint', canGenerate ? 'ce-hint--ready' : 'ce-hint--locked']">
        {{ canGenerate
          ? pick('请使用顶部主命令栏开始生成', 'Use the command bar at the top to start generating')
          : pick('请按顺序推进章节', 'Work through the chapters in order') }}
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { useLocale } from '@/composables/useLocale'

const { pick } = useLocale()

defineProps<{
  chapterNumber: number
  generatingChapter: number | null
  canGenerate: boolean
}>()

defineEmits(['generateChapter'])
</script>

<style scoped>
.ce-shell {
  min-height: 240px;
  display: grid;
  place-items: center;
  padding: 12px;
}

.ce-panel {
  width: min(560px, 100%);
  display: grid;
  gap: 12px;
  padding: 20px;
  border-radius: 8px;
  border: 1px solid rgba(107, 155, 235, 0.15);
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.95), rgba(241, 247, 255, 0.9));
  box-shadow: 0 8px 24px rgba(37, 99, 235, 0.06);
}

.ce-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.ce-orbit {
  position: relative;
  width: 48px;
  height: 48px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: linear-gradient(135deg, #eef6ff, #ffffff);
  box-shadow: inset 0 0 0 1px rgba(107, 155, 235, 0.15);
  flex-shrink: 0;
}

.ce-orbit span {
  position: absolute;
  inset: 6px;
  border-radius: 6px;
  border: 1px dashed rgba(37, 99, 235, 0.3);
}

.ce-orbit strong {
  color: #2563eb;
  font-size: 16px;
  font-weight: 900;
}

.ce-copy {
  display: grid;
  gap: 2px;
}

.ce-kicker {
  margin: 0;
  color: #4f46e5;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.05em;
}

.ce-copy h3 {
  margin: 0;
  color: #0f172a;
  font-size: 16px;
  font-weight: 700;
}

.ce-desc {
  margin: 0;
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
}

.ce-path {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.ce-step {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  border-radius: 6px;
  border: 1px solid rgba(148, 163, 184, 0.15);
  background: rgba(255, 255, 255, 0.7);
}

.ce-step span {
  width: 22px;
  height: 22px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  color: #94a3b8;
  background: rgba(15, 23, 42, 0.05);
  font-size: 11px;
  font-weight: 700;
  flex-shrink: 0;
}

.ce-step strong {
  color: #0f172a;
  font-size: 11px;
  font-weight: 600;
}

.ce-step--done span,
.ce-step--active span {
  color: #fff;
  background: linear-gradient(135deg, #2563eb, #7c3aed);
}

.ce-step--active {
  border-color: rgba(37, 99, 235, 0.3);
}

.ce-step--locked {
  opacity: 0.6;
}

.ce-hint {
  width: fit-content;
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 10px;
  border-radius: 4px;
  color: #64748b;
  background: rgba(15, 23, 42, 0.04);
  font-size: 11px;
  font-weight: 600;
}

.ce-hint--ready {
  background: rgba(37, 99, 235, 0.08);
  color: #1d4ed8;
}

@media (max-width: 720px) {
  .ce-path {
    grid-template-columns: 1fr;
  }

  .ce-panel {
    padding: 16px;
  }
}
</style>
