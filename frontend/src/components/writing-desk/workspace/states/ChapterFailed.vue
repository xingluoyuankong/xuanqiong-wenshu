<template>
  <div class="cf-shell">
    <section class="cf-panel">
      <div class="cf-header">
        <div class="cf-visual" aria-hidden="true">
          <span class="cf-visual__ring"></span>
          <span class="cf-visual__icon">!</span>
        </div>
        <div class="cf-copy">
          <p class="cf-kicker">章节异常恢复</p>
          <h3>第 {{ chapterNumber }} 章处理失败</h3>
        </div>
      </div>
      <p class="cf-desc">
        当前章节没有形成可交付正文。刷新状态确认原因后，请用顶部主操作栏重新生成。
      </p>

      <div v-if="failureSummary || diagnosticRows.length" class="cf-diagnostics">
        <div v-if="failureSummary" class="cf-diagnostics__summary">
          <strong>后端错误摘要</strong>
          <p>{{ failureSummary }}</p>
        </div>
        <div v-if="diagnosticRows.length" class="cf-diagnostics__grid">
          <div v-for="item in diagnosticRows" :key="item.label">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
          </div>
        </div>
      </div>

      <div class="cf-hint" :class="generatingChapter === chapterNumber ? 'cf-hint--busy' : ''">
        <strong>{{ generatingChapter === chapterNumber ? '顶部主操作执行中' : '主操作已收口到顶部' }}</strong>
        <span>{{ generatingChapter === chapterNumber ? '处理中...' : '去顶部操作' }}</span>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Chapter, GenerationRuntime } from '@/api/novel'

interface Props {
  chapterNumber: number
  generatingChapter: number | null
  chapter?: Chapter | null
  generationRuntime?: GenerationRuntime | null
  lastErrorSummary?: string | null
}

const props = defineProps<Props>()

const runtime = computed<Record<string, any>>(() =>
  (props.generationRuntime || props.chapter?.generation_runtime || {}) as Record<string, any>
)
const failureSummary = computed(() =>
  props.lastErrorSummary ||
  props.chapter?.last_error_summary ||
  runtime.value.last_error_summary ||
  runtime.value?.diagnostics?.message ||
  ''
)
const diagnostics = computed<Record<string, any>>(() => {
  const value = runtime.value?.diagnostics
  return value && typeof value === 'object' ? value as Record<string, any> : {}
})
const diagnosticRows = computed(() => {
  const rows = [
    diagnostics.value.code ? { label: '错误码', value: String(diagnostics.value.code) } : null,
    diagnostics.value.rootCause ? { label: '根因', value: String(diagnostics.value.rootCause) } : null,
    diagnostics.value.status ? { label: '状态码', value: String(diagnostics.value.status) } : null,
    diagnostics.value.requestId ? { label: '请求ID', value: String(diagnostics.value.requestId) } : null,
    diagnostics.value.hint ? { label: '建议', value: String(diagnostics.value.hint) } : null,
  ]
  return rows.filter(Boolean) as Array<{ label: string; value: string }>
})
</script>

<style scoped>
.cf-shell {
  min-height: 240px;
  display: grid;
  place-items: center;
  padding: 12px;
}

.cf-panel {
  width: min(520px, 100%);
  display: grid;
  gap: 12px;
  padding: 20px;
  border-radius: 8px;
  border: 1px solid rgba(248, 113, 113, 0.2);
  background: linear-gradient(135deg, rgba(255, 247, 247, 0.95), rgba(255, 255, 255, 0.9));
  box-shadow: 0 8px 24px rgba(127, 29, 29, 0.06);
}

.cf-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.cf-visual {
  position: relative;
  width: 44px;
  height: 44px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}

.cf-visual__ring {
  position: absolute;
  inset: 0;
  border-radius: 8px;
  background: linear-gradient(135deg, #ef4444, #f97316);
  opacity: 0.12;
}

.cf-visual__icon {
  position: relative;
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border-radius: 6px;
  color: #b91c1c;
  background: #fff;
  font-size: 14px;
  font-weight: 900;
  box-shadow: 0 4px 12px rgba(185, 28, 28, 0.12);
}

.cf-copy {
  display: grid;
  gap: 2px;
}

.cf-kicker {
  margin: 0;
  color: #dc2626;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.05em;
}

.cf-copy h3 {
  margin: 0;
  color: #111827;
  font-size: 16px;
  font-weight: 700;
}

.cf-desc {
  margin: 0;
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
}

.cf-diagnostics {
  display: grid;
  gap: 8px;
  padding: 12px;
  border-radius: 6px;
  border: 1px solid rgba(185, 28, 28, 0.15);
  background: rgba(255, 255, 255, 0.7);
}

.cf-diagnostics__summary strong {
  color: #991b1b;
  font-size: 11px;
  font-weight: 700;
}

.cf-diagnostics__summary p {
  margin: 4px 0 0;
  color: #4b5563;
  line-height: 1.5;
  font-size: 11px;
  white-space: pre-wrap;
}

.cf-diagnostics__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 6px;
}

.cf-diagnostics__grid div {
  display: grid;
  gap: 2px;
  padding: 6px 8px;
  border-radius: 4px;
  background: rgba(254, 242, 242, 0.7);
}

.cf-diagnostics__grid span {
  color: #991b1b;
  font-size: 10px;
  font-weight: 600;
}

.cf-diagnostics__grid strong {
  color: #374151;
  font-size: 11px;
  line-height: 1.4;
}

.cf-hint {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid rgba(248, 113, 113, 0.15);
  background: linear-gradient(135deg, rgba(254, 242, 242, 0.9), rgba(255, 255, 255, 0.85));
}

.cf-hint strong {
  color: #991b1b;
  font-size: 11px;
  font-weight: 700;
}

.cf-hint span {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  background: rgba(239, 68, 68, 0.1);
  color: #b91c1c;
  font-size: 10px;
  font-weight: 700;
  white-space: nowrap;
}

.cf-hint--busy {
  border-color: rgba(249, 115, 22, 0.2);
  background: linear-gradient(135deg, rgba(255, 247, 237, 0.9), rgba(255, 255, 255, 0.85));
}

.cf-hint--busy strong,
.cf-hint--busy span {
  color: #c2410c;
}

@media (max-width: 720px) {
  .cf-panel {
    padding: 16px;
  }

  .cf-hint {
    flex-direction: column;
    align-items: flex-start;
    gap: 4px;
  }
}
</style>
