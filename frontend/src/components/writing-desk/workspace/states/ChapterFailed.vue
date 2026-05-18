<!-- AIMETA P=生成失败_生成错误状态|R=错误提示_重试|NR=不含生成逻辑|E=component:ChapterFailed|X=internal|A=错误状态|D=vue|S=dom|RD=./README.ai -->
<template>
  <div class="cf-shell">
    <section class="cf-panel">
      <div class="cf-visual" aria-hidden="true">
        <span class="cf-visual__ring"></span>
        <span class="cf-visual__icon">!</span>
      </div>

      <div class="cf-copy">
        <p class="cf-kicker">章节异常恢复</p>
        <h3>第 {{ chapterNumber }} 章处理失败</h3>
        <p>
          当前章节没有形成可交付正文。系统不会再把空正文伪装成成功状态；
          刷新状态确认原因后，请用顶部主操作栏重新生成，避免这里再放一颗重复按钮。
        </p>
      </div>

      <div class="cf-checklist">
        <div>
          <strong>先确认</strong>
          <span>查看后台日志、错误摘要或最近一次运行记录。</span>
        </div>
        <div>
          <strong>再恢复</strong>
          <span>重新生成后会重新进入候选版本与评审流程。</span>
        </div>
        <div>
          <strong>导出保护</strong>
          <span>失败章节会阻断 TXT/DOCX 导出，避免交付半成品。</span>
        </div>
      </div>

      <section v-if="failureSummary || diagnosticRows.length || latestErrorEvent" class="cf-diagnostics">
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
        <details v-if="latestErrorEvent" class="cf-diagnostics__event">
          <summary>最近错误事件 metadata</summary>
          <pre>{{ latestErrorEvent }}</pre>
        </details>
      </section>

      <div class="cf-primary-hint" :class="generatingChapter === chapterNumber ? 'cf-primary-hint--busy' : ''">
        <div>
          <strong>{{ generatingChapter === chapterNumber ? '顶部主操作执行中' : '主操作已收口到顶部' }}</strong>
          <p>
            {{ generatingChapter === chapterNumber ? '当前章已经在重新生成，先等待顶部任务栏推进。' : '需要恢复时，请直接使用顶部命令栏里的“重新生成”。' }}
          </p>
        </div>
        <span>{{ generatingChapter === chapterNumber ? '处理中' : '去顶部操作' }}</span>
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
    diagnostics.value.retryable === true ? { label: '重试判断', value: '可重试' } : null,
    diagnostics.value.retryable === false ? { label: '重试判断', value: '先处理原因' } : null,
  ]
  return rows.filter(Boolean) as Array<{ label: string; value: string }>
})
const latestErrorEvent = computed(() => {
  const events = Array.isArray(runtime.value?.events) ? runtime.value.events : []
  const event = [...events].reverse().find((item) =>
    item && typeof item === 'object' && (item.level === 'error' || item.metadata)
  )
  if (!event) return ''
  return JSON.stringify(event.metadata || event, null, 2)
})
</script>

<style scoped>
.cf-shell {
  min-height: 360px;
  display: grid;
  place-items: center;
  padding: 18px;
}

.cf-panel {
  position: relative;
  width: min(760px, 100%);
  overflow: hidden;
  display: grid;
  gap: 18px;
  padding: clamp(24px, 4vw, 36px);
  border-radius: 34px;
  border: 1px solid rgba(248, 113, 113, 0.25);
  background:
    radial-gradient(circle at 12% 12%, rgba(248, 113, 113, 0.18), transparent 30%),
    linear-gradient(135deg, rgba(255, 247, 247, 0.98), rgba(255, 255, 255, 0.94));
  box-shadow: 0 26px 72px rgba(127, 29, 29, 0.12);
}

.cf-visual {
  position: relative;
  width: 74px;
  height: 74px;
  display: grid;
  place-items: center;
}

.cf-visual__ring {
  position: absolute;
  inset: 0;
  border-radius: 24px;
  background: linear-gradient(135deg, #ef4444, #f97316);
  opacity: 0.14;
}

.cf-visual__icon {
  position: relative;
  width: 52px;
  height: 52px;
  display: grid;
  place-items: center;
  border-radius: 18px;
  color: #b91c1c;
  background: #fff;
  font-size: 1.8rem;
  font-weight: 950;
  box-shadow: 0 12px 28px rgba(185, 28, 28, 0.16);
}

.cf-copy {
  display: grid;
  gap: 8px;
}

.cf-kicker {
  margin: 0;
  color: #dc2626;
  font-size: 0.76rem;
  font-weight: 900;
  letter-spacing: 0.12em;
}

.cf-copy h3 {
  margin: 0;
  color: #111827;
  font-size: clamp(1.35rem, 2.2vw, 2rem);
  font-weight: 900;
}

.cf-copy p {
  max-width: 62ch;
  margin: 0;
  color: #5b6472;
  line-height: 1.8;
}

.cf-checklist {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.cf-checklist div {
  display: grid;
  gap: 5px;
  padding: 14px;
  border-radius: 20px;
  border: 1px solid rgba(248, 113, 113, 0.18);
  background: rgba(255, 255, 255, 0.72);
}

.cf-checklist strong {
  color: #991b1b;
  font-size: 0.88rem;
}

.cf-checklist span {
  color: #64748b;
  font-size: 0.78rem;
  line-height: 1.6;
}

.cf-primary-hint {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 14px 16px;
  border-radius: 22px;
  border: 1px solid rgba(248, 113, 113, 0.2);
  background: linear-gradient(135deg, rgba(254, 242, 242, 0.96), rgba(255, 255, 255, 0.92));
}

.cf-diagnostics {
  display: grid;
  gap: 12px;
  padding: 16px;
  border-radius: 22px;
  border: 1px solid rgba(185, 28, 28, 0.18);
  background: rgba(255, 255, 255, 0.78);
}

.cf-diagnostics__summary strong {
  color: #991b1b;
  font-size: 0.9rem;
}

.cf-diagnostics__summary p {
  margin: 6px 0 0;
  color: #4b5563;
  line-height: 1.7;
  white-space: pre-wrap;
}

.cf-diagnostics__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 8px;
}

.cf-diagnostics__grid div {
  display: grid;
  gap: 4px;
  min-width: 0;
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(254, 242, 242, 0.72);
}

.cf-diagnostics__grid span {
  color: #991b1b;
  font-size: 0.76rem;
  font-weight: 800;
}

.cf-diagnostics__grid strong {
  overflow-wrap: anywhere;
  color: #374151;
  font-size: 0.82rem;
  line-height: 1.5;
}

.cf-diagnostics__event summary {
  cursor: pointer;
  color: #991b1b;
  font-size: 0.82rem;
  font-weight: 850;
}

.cf-diagnostics__event pre {
  overflow: auto;
  max-height: 220px;
  margin: 10px 0 0;
  padding: 12px;
  border-radius: 14px;
  background: #111827;
  color: #f9fafb;
  font-size: 0.76rem;
  line-height: 1.55;
}

.cf-primary-hint strong {
  display: block;
  color: #991b1b;
  font-size: 0.92rem;
}

.cf-primary-hint p {
  margin: 6px 0 0;
  color: #64748b;
  font-size: 0.82rem;
  line-height: 1.65;
}

.cf-primary-hint span {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  padding: 0 12px;
  border-radius: 999px;
  background: rgba(239, 68, 68, 0.12);
  color: #b91c1c;
  font-size: 0.78rem;
  font-weight: 850;
  white-space: nowrap;
}

.cf-primary-hint--busy {
  border-color: rgba(249, 115, 22, 0.22);
  background: linear-gradient(135deg, rgba(255, 247, 237, 0.98), rgba(255, 255, 255, 0.92));
}

.cf-primary-hint--busy strong,
.cf-primary-hint--busy span {
  color: #c2410c;
}

@media (max-width: 720px) {
  .cf-checklist {
    grid-template-columns: 1fr;
  }

  .cf-primary-hint {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
