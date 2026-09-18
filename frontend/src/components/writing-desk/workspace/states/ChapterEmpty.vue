<template>
  <div class="ce-shell">
    <section class="ce-panel">
      <div class="ce-orbit" aria-hidden="true">
        <span></span>
        <strong>{{ chapterNumber }}</strong>
      </div>

      <div class="ce-copy">
        <p class="ce-kicker">章节待生成</p>
        <h3>第 {{ chapterNumber }} 章还没有正文</h3>
        <p v-if="canGenerate">
          已经轮到这一章进入正文生产。点击开始后，系统会在后台生成候选版本，
          并在完成后切换到评审/确认流程。
        </p>
        <p v-else>
          当前章节还被顺序锁保护。请先完成前置章节，避免上下文断裂、人物动机跳跃或伏笔遗漏。
        </p>
      </div>

      <div class="ce-path">
        <div :class="['ce-step', canGenerate ? 'ce-step--done' : '']">
          <span>1</span>
          <strong>确认前文</strong>
          <em>保证承接</em>
        </div>
        <div :class="['ce-step', canGenerate ? 'ce-step--active' : 'ce-step--locked']">
          <span>2</span>
          <strong>生成本章</strong>
          <em>{{ canGenerate ? '可执行' : '待解锁' }}</em>
        </div>
        <div class="ce-step ce-step--future">
          <span>3</span>
          <strong>评审确认</strong>
          <em>选择版本</em>
        </div>
      </div>

      <div :class="['ce-command-note', canGenerate ? 'ce-command-note--ready' : 'ce-command-note--locked']">
        {{ canGenerate ? '请使用顶部主命令栏开始生成，避免同一页面出现重复按钮。' : '请按顺序推进章节' }}
      </div>
    </section>
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
  min-height: 360px;
  display: grid;
  place-items: center;
  padding: 18px;
}

.ce-panel {
  width: min(820px, 100%);
  display: grid;
  gap: 20px;
  padding: clamp(24px, 4vw, 38px);
  border-radius: 8px;
  border: 1px solid rgba(107, 155, 235, 0.2);
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.98), rgba(241, 247, 255, 0.94));
  box-shadow: 0 26px 72px rgba(37, 99, 235, 0.12);
}

.ce-orbit {
  position: relative;
  width: 78px;
  height: 78px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: linear-gradient(135deg, #eef6ff, #ffffff);
  box-shadow: inset 0 0 0 1px rgba(107, 155, 235, 0.18), 0 18px 42px rgba(107, 155, 235, 0.16);
}

.ce-orbit span {
  position: absolute;
  inset: 10px;
  border-radius: 8px;
  border: 1px dashed rgba(37, 99, 235, 0.35);
}

.ce-orbit strong {
  color: #2563eb;
  font-size: 1.9rem;
  font-weight: 950;
}

.ce-copy {
  display: grid;
  gap: 8px;
}

.ce-kicker {
  margin: 0;
  color: #4f46e5;
  font-size: 0.76rem;
  font-weight: 900;
  letter-spacing: 0.12em;
}

.ce-copy h3 {
  margin: 0;
  color: #0f172a;
  font-size: clamp(1.35rem, 2.2vw, 2rem);
  font-weight: 900;
}

.ce-copy p {
  max-width: 66ch;
  margin: 0;
  color: #52627a;
  line-height: 1.8;
}

.ce-path {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.ce-step {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 3px 10px;
  align-items: center;
  min-height: 82px;
  padding: 14px;
  border-radius: 8px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  background: rgba(255, 255, 255, 0.72);
}

.ce-step span {
  grid-row: span 2;
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  color: #475569;
  background: rgba(15, 23, 42, 0.06);
  font-weight: 900;
}

.ce-step strong {
  color: #0f172a;
  font-size: 0.92rem;
}

.ce-step em {
  color: #64748b;
  font-size: 0.76rem;
  font-style: normal;
}

.ce-step--done span,
.ce-step--active span {
  color: #fff;
  background: linear-gradient(135deg, #2563eb, #7c3aed);
}

.ce-step--active {
  border-color: rgba(37, 99, 235, 0.35);
  box-shadow: 0 16px 36px rgba(37, 99, 235, 0.12);
}

.ce-step--locked {
  opacity: 0.72;
}

.ce-command-note {
  width: fit-content;
  display: inline-flex;
  align-items: center;
  min-height: 38px;
  padding: 0 16px;
  border-radius: 8px;
  color: #475569;
  background: rgba(15, 23, 42, 0.06);
  font-size: 0.86rem;
  font-weight: 850;
}

.ce-command-note--ready {
  background: rgba(37, 99, 235, 0.1);
  color: #1d4ed8;
}

@media (max-width: 720px) {
  .ce-path {
    grid-template-columns: 1fr;
  }
}
</style>
