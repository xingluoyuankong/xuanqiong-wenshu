<template>
  <n-card :bordered="false" class="admin-card diagnostics-root">
    <template #header>
      <div class="card-header">
        <div>
          <div class="card-title">故障诊断</div>
          <p class="card-subtitle">直接聚焦最近的后端异常，给出中文根因、处理建议、关联请求信息和近期异常轨迹。</p>
        </div>
        <n-space align="center" :size="12">
          <n-switch v-model:value="autoRefresh" size="small">
            <template #checked>自动刷新</template>
            <template #unchecked>自动刷新</template>
          </n-switch>
          <n-button quaternary size="small" :loading="loading" @click="fetchDiagnostics">刷新</n-button>
        </n-space>
      </div>
    </template>

    <n-space vertical size="large">
      <n-alert v-if="error" type="error" closable @close="error = null">{{ error }}</n-alert>

      <n-spin :show="loading">
        <n-empty v-if="!diagnostics" description="暂无可用诊断结果" />

        <template v-else>
          <n-card :bordered="false" class="primary-card">
            <div class="primary-header">
              <div>
                <p class="primary-label">主要异常</p>
                <h3 class="primary-title">{{ translatedPrimaryErrorType }}</h3>
              </div>
              <n-tag :type="statusTagType" :bordered="false" round>{{ statusLabel }}</n-tag>
            </div>

            <p class="primary-message">{{ diagnostics.primary_error_message }}</p>

            <div class="diagnosis-blocks">
              <div class="diagnosis-block">
                <span class="meta-key">根因判断</span>
                <p>{{ diagnostics.root_cause || '当前日志未给出明确根因，需要结合堆栈和时间线继续排查。' }}</p>
              </div>
              <div class="diagnosis-block diagnosis-block--accent">
                <span class="meta-key">处理建议</span>
                <p>{{ diagnostics.hint || '建议先按时间线复盘，再结合请求 ID、接口路径和堆栈片段定位同批次错误。' }}</p>
              </div>
            </div>

            <n-grid :cols="24" :x-gap="12" :y-gap="12" class="meta-grid">
              <n-gi :span="8"><MetaItem label="请求 ID" :value="diagnostics.request_id || '-'" mono /></n-gi>
              <n-gi :span="8"><MetaItem label="接口路径" :value="diagnostics.path || '-'" mono /></n-gi>
              <n-gi :span="8"><MetaItem label="状态码" :value="diagnostics.status_code ?? '-'" /></n-gi>
              <n-gi :span="12"><MetaItem label="发生时间" :value="formatDateTime(diagnostics.occurred_at)" /></n-gi>
              <n-gi :span="12"><MetaItem label="来源日志" :value="diagnostics.source_log || '-'" mono /></n-gi>
            </n-grid>
          </n-card>

          <n-grid :cols="24" :x-gap="16" :y-gap="16">
            <n-gi :span="15">
              <n-card v-if="diagnostics.stack_excerpt" :bordered="false" class="stack-card">
                <template #header>
                  <div class="section-header">
                    <span>堆栈片段</span>
                    <n-button tertiary size="tiny" @click="copyStack">复制</n-button>
                  </div>
                </template>
                <n-scrollbar x-scrollable style="max-height: 360px">
                  <pre class="stack-block">{{ diagnostics.stack_excerpt }}</pre>
                </n-scrollbar>
              </n-card>
            </n-gi>
            <n-gi :span="9">
              <n-card :bordered="false" class="summary-card">
                <template #header>
                  <div class="section-header">
                    <span>诊断摘要</span>
                    <span class="small-note">中文解释</span>
                  </div>
                </template>
                <ul class="summary-list">
                  <li>
                    <strong>异常类型</strong>
                    <span>{{ translatedPrimaryErrorType }}</span>
                  </li>
                  <li>
                    <strong>日志覆盖</strong>
                    <span>已扫描 {{ diagnostics.scanned_logs.length }} 份日志</span>
                  </li>
                  <li>
                    <strong>最近刷新</strong>
                    <span>{{ formatDateTime(diagnostics.generated_at) }}</span>
                  </li>
                  <li>
                    <strong>近期异常数</strong>
                    <span>{{ diagnostics.incidents.length }} 条</span>
                  </li>
                </ul>
              </n-card>
            </n-gi>
          </n-grid>

          <n-card :bordered="false" class="timeline-card">
            <template #header>
              <div class="section-header">
                <span>近期异常时间线</span>
                <span class="small-note">共 {{ diagnostics.incidents.length }} 条</span>
              </div>
            </template>
            <n-space vertical size="small">
              <div v-for="incident in diagnostics.incidents" :key="incidentKey(incident)" class="incident-row">
                <div class="incident-top">
                  <div class="incident-title-row">
                    <n-tag :type="tagTypeByStatus(incident.status_code)" size="small" :bordered="false">
                      {{ translateErrorType(incident.error_type) }}
                    </n-tag>
                    <span class="incident-time">{{ formatDateTime(incident.occurred_at) }}</span>
                  </div>
                  <span v-if="incident.status_code" class="incident-status">HTTP {{ incident.status_code }}</span>
                </div>
                <p class="incident-message">{{ incident.error_message }}</p>
                <div class="incident-meta">
                  <span v-if="incident.path" class="mono">{{ incident.path }}</span>
                  <span v-if="incident.source_log" class="mono">{{ incident.source_log }}</span>
                  <span v-if="incident.request_id" class="mono">请求 ID {{ incident.request_id }}</span>
                </div>
                <p v-if="incident.root_cause" class="incident-extra"><strong>根因：</strong>{{ incident.root_cause }}</p>
                <p v-if="incident.hint" class="incident-extra"><strong>建议：</strong>{{ incident.hint }}</p>
              </div>
            </n-space>
          </n-card>
        </template>
      </n-spin>
    </n-space>
  </n-card>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { NAlert, NButton, NCard, NEmpty, NGi, NGrid, NScrollbar, NSpace, NSpin, NSwitch, NTag } from 'naive-ui'
import { AdminAPI, type RootCauseDiagnosticsResponse, type RootCauseIncident } from '@/api/admin'
import { useAlert } from '@/composables/useAlert'
import { translateErrorType } from './adminI18n'

const MetaItem = defineComponent({
  props: {
    label: { type: String, required: true },
    value: { type: [String, Number], required: true },
    mono: { type: Boolean, default: false },
  },
  setup(props) {
    return () => h('div', { class: 'meta-item' }, [
      h('span', { class: 'meta-key' }, props.label),
      h('span', { class: ['meta-value', props.mono ? 'mono' : ''] }, String(props.value)),
    ])
  },
})

const { showAlert } = useAlert()

const diagnostics = ref<RootCauseDiagnosticsResponse | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const autoRefresh = ref(true)
let refreshTimer: number | undefined

const fetchDiagnostics = async () => {
  loading.value = true
  error.value = null
  try {
    diagnostics.value = await AdminAPI.getRootCauseDiagnostics()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '获取故障诊断失败'
  } finally {
    loading.value = false
  }
}

const tagTypeByStatus = (status?: number | null): 'default' | 'error' | 'warning' | 'success' | 'info' => {
  if (typeof status === 'number') {
    if (status >= 500) return 'error'
    if (status >= 400) return 'warning'
    if (status >= 200 && status < 300) return 'success'
  }
  return 'info'
}

const translatedPrimaryErrorType = computed(() => translateErrorType(diagnostics.value?.primary_error_type))
const statusTagType = computed(() => tagTypeByStatus(diagnostics.value?.status_code))
const statusLabel = computed(() => typeof diagnostics.value?.status_code === 'number' ? `HTTP ${diagnostics.value.status_code}` : '未标注状态码')

const formatDateTime = (value?: string | null) => {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false })
}

const incidentKey = (incident: RootCauseIncident) =>
  `${incident.occurred_at}-${incident.error_type}-${incident.source_log}-${incident.request_id || 'none'}`

const copyStack = async () => {
  const stack = diagnostics.value?.stack_excerpt
  if (!stack) {
    showAlert('没有可复制的堆栈内容', 'info')
    return
  }
  try {
    await navigator.clipboard.writeText(stack)
    showAlert('堆栈片段已复制', 'success')
  } catch {
    showAlert('复制失败，请手动复制', 'error')
  }
}

const clearTimer = () => {
  if (refreshTimer !== undefined) {
    window.clearInterval(refreshTimer)
    refreshTimer = undefined
  }
}

const setupTimer = () => {
  clearTimer()
  if (!autoRefresh.value) return
  refreshTimer = window.setInterval(() => {
    if (!loading.value) void fetchDiagnostics()
  }, 30000)
}

watch(autoRefresh, setupTimer)

onMounted(async () => {
  await fetchDiagnostics()
  setupTimer()
})

onBeforeUnmount(clearTimer)
</script>

<style scoped>
.diagnostics-root { width: 100%; }
.card-header,
.primary-header,
.section-header,
.incident-top,
.incident-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.card-title { font-size: 1.1rem; font-weight: 700; color: #0f172a; }
.card-subtitle { margin: 4px 0 0; font-size: 0.83rem; color: #64748b; }
.primary-card {
  background: linear-gradient(135deg, rgba(15,23,42,0.98), rgba(30,41,59,0.94));
  color: #e2e8f0;
  border-radius: 18px;
}
.primary-label { margin: 0; font-size: 0.72rem; letter-spacing: 0.15em; color: #94a3b8; text-transform: uppercase; }
.primary-title { margin: 4px 0 0; font-size: 1.18rem; font-weight: 700; color: #f8fafc; }
.primary-message { margin: 8px 0 14px; font-size: 0.88rem; line-height: 1.75; color: #cbd5e1; }
.diagnosis-blocks { display: grid; gap: 12px; grid-template-columns: repeat(2, minmax(0, 1fr)); margin-bottom: 14px; }
.diagnosis-block {
  border-radius: 14px;
  padding: 12px 14px;
  border: 1px solid rgba(148,163,184,0.22);
  background: rgba(15,23,42,0.35);
}
.diagnosis-block--accent { background: rgba(30,64,175,0.22); }
.diagnosis-block p { margin: 6px 0 0; line-height: 1.7; font-size: 0.84rem; color: #f8fafc; }
.meta-grid { margin-top: 10px; }
.meta-item { display: flex; flex-direction: column; gap: 6px; border: 1px solid rgba(148,163,184,0.28); background: rgba(15,23,42,0.35); border-radius: 12px; padding: 10px 12px; }
.meta-key { font-size: 0.68rem; letter-spacing: 0.12em; color: #94a3b8; text-transform: uppercase; }
.meta-value { font-size: 0.82rem; color: #f1f5f9; word-break: break-word; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
.stack-card, .timeline-card, .summary-card { border-radius: 18px; }
.stack-block { margin: 0; padding: 14px; border-radius: 14px; background: #0f172a; color: #e2e8f0; font-size: 0.78rem; line-height: 1.65; }
.small-note { color: #64748b; font-size: 0.78rem; }
.summary-list { display: grid; gap: 10px; margin: 0; padding: 0; list-style: none; }
.summary-list li { display: grid; gap: 4px; padding: 10px 12px; border-radius: 12px; background: #f8fafc; border: 1px solid #e2e8f0; }
.summary-list strong { font-size: 0.76rem; color: #475569; }
.summary-list span { font-size: 0.84rem; color: #0f172a; }
.incident-row { padding: 12px 14px; border-radius: 14px; border: 1px solid #e2e8f0; background: #f8fafc; }
.incident-time, .incident-meta, .incident-status { color: #64748b; font-size: 0.78rem; }
.incident-message { margin: 8px 0 8px; color: #0f172a; line-height: 1.65; font-size: 0.85rem; }
.incident-meta { display: flex; gap: 10px; flex-wrap: wrap; }
.incident-extra { margin: 8px 0 0; color: #334155; line-height: 1.6; font-size: 0.82rem; }
@media (max-width: 960px) {
  .diagnosis-blocks { grid-template-columns: 1fr; }
}
</style>
