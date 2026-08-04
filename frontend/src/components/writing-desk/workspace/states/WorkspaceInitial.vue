<template>
  <div class="wi-shell">
    <div class="wi-panel">
      <div class="wi-kicker">✍️ 写作工作台</div>
      <h3>从左侧选择章节，或直接定位系统推荐的下一章</h3>
      <p>选择章节后，可以直接生成、评估、确认版本或继续优化正文。</p>
      <div class="wi-grid">
        <div>
          <strong>1</strong>
          <span>选择章节</span>
        </div>
        <div>
          <strong>2</strong>
          <span>生成正文</span>
        </div>
        <div>
          <strong>3</strong>
          <span>确认版本</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.wi-shell {
  display: grid;
  justify-items: center;
  padding: 8px 0;
}

.wi-panel {
  width: min(480px, 100%);
  padding: 20px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.85);
  border: 1px solid rgba(148, 163, 184, 0.12);
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
  display: grid;
  gap: 8px;
}

.wi-kicker {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.08);
  color: #1d4ed8;
  font-size: 11px;
  font-weight: 700;
  width: fit-content;
}

.wi-panel h3 {
  margin: 0;
  font-size: 15px;
  line-height: 1.4;
  color: #0f172a;
  font-weight: 700;
}

.wi-panel p {
  margin: 0;
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
}

.wi-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-top: 4px;
}

.wi-grid div {
  display: grid;
  gap: 4px;
  padding: 10px 12px;
  border-radius: 6px;
  background: rgba(248, 250, 252, 0.9);
  border: 1px solid rgba(148, 163, 184, 0.08);
}

.wi-grid strong {
  width: 24px;
  height: 24px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: #0f172a;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
}

.wi-grid span {
  color: #334155;
  font-size: 11px;
  line-height: 1.4;
}

@media (max-width: 768px) {
  .wi-panel {
    padding: 16px;
  }

  .wi-grid {
    grid-template-columns: 1fr;
  }
}
</style>
