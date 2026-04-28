<template>
  <div class="wi-shell">
    <div class="wi-panel">
      <div class="wi-kicker">写作工作台</div>
      <h3>从左侧选择章节，或者直接定位系统推荐的下一章。</h3>
      <p>这里不再只是空白页，而是你的主工作区。选择章节后，可以直接生成、评估、确认版本或继续优化正文。</p>
      <div class="wi-grid">
        <div>
          <strong>1</strong>
          <span>选择目录中的章节</span>
        </div>
        <div>
          <strong>2</strong>
          <span>生成或继续当前章节</span>
        </div>
        <div>
          <strong>3</strong>
          <span>评估并确认最终版本</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.wi-shell {
  display: grid;
  justify-items: center;
  padding: 12px 0 8px;
}

.wi-panel {
  width: min(720px, 100%);
  padding: 28px;
  border-radius: 28px;
  background:
    radial-gradient(circle at top right, rgba(37, 99, 235, 0.12), transparent 28%),
    rgba(255, 255, 255, 0.86);
  border: 1px solid rgba(148, 163, 184, 0.18);
  box-shadow: 0 24px 48px rgba(15, 23, 42, 0.06);
}

.wi-kicker {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.1);
  color: #1d4ed8;
  font-size: 0.78rem;
  font-weight: 700;
}

.wi-panel h3 {
  margin-top: 14px;
  font-size: 1.5rem;
  line-height: 1.4;
  color: #0f172a;
  font-weight: 700;
}

.wi-panel p {
  margin-top: 12px;
  color: #475569;
  line-height: 1.8;
}

.wi-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 24px;
}

.wi-grid div {
  display: grid;
  gap: 10px;
  padding: 16px;
  border-radius: 20px;
  background: rgba(248, 250, 252, 0.96);
}

.wi-grid strong {
  width: 34px;
  height: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
  background: #0f172a;
  color: #fff;
}

.wi-grid span {
  color: #334155;
  line-height: 1.6;
}

@media (max-width: 768px) {
  .wi-panel {
    padding: 24px;
  }

  .wi-grid {
    grid-template-columns: 1fr;
  }
}
</style>
