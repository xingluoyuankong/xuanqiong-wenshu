<template>
  <XqPanel
    :title="title"
    :subtitle="subtitle"
    data-testid="agent-tool-result-panel"
  >
    <p v-if="!views.length" class="tool-result-empty" data-testid="agent-tool-result-empty">
      {{ emptyText }}
    </p>

    <div v-else class="tool-result-list">
      <article
        v-for="view in views"
        :key="view.key"
        class="tool-result-card"
        :class="{ 'tool-result-card--selected': view.selected }"
        :data-testid="`agent-tool-result-${view.index}`"
      >
        <header class="tool-result-card__header">
          <strong>{{ view.toolName }}</strong>
          <span v-if="view.known" class="tool-result-card__badge">安全摘要</span>
          <span v-else class="tool-result-card__badge tool-result-card__badge--muted">未支持</span>
          <small v-if="view.resultRef" class="tool-result-card__ref" data-testid="agent-tool-result-ref">结果：{{ view.resultRef }}</small>
        </header>
        <p v-if="view.selected" class="tool-result-card__selection" data-testid="agent-tool-result-selection">已定位到当前结果</p>

        <p v-if="!view.known" class="tool-result-card__notice">
          此工具结果未纳入安全展示白名单，原始数据不会在界面中回显。
        </p>
        <dl v-else-if="view.fields.length" class="tool-result-fields">
          <div v-for="field in view.fields" :key="field.key" class="tool-result-field">
            <dt>{{ field.label }}</dt>
            <dd>{{ field.value }}</dd>
          </div>
        </dl>
        <p v-else class="tool-result-card__notice">
          工具已返回结果，但没有可安全展示的结构化字段。
        </p>

        <p v-if="view.notice" class="tool-result-card__notice">{{ view.notice }}</p>
      </article>

      <p v-if="hiddenResultCount" class="tool-result-card__notice" data-testid="agent-tool-result-truncated">
        还有 {{ hiddenResultCount }} 个工具结果未展示；为避免无界渲染，已按结果数量限制。
      </p>
      <p v-if="selectedResultRef && !views.some((view) => view.resultRef === selectedResultRef)" class="tool-result-card__notice" data-testid="agent-tool-result-selection">当前结果引用已失效，正在恢复执行事实。</p>
    </div>
  </XqPanel>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import type { AgentToolResult } from '@/api/agent'
import { XqPanel } from '@/shared/ui'

export interface AgentToolResultPanelProps {
  /** The structured results returned by the Agent runtime. */
  results: AgentToolResult[]
  /** Maximum number of result envelopes rendered at once. */
  maxResults?: number
  /** Maximum fields rendered for one result envelope. */
  maxFieldsPerResult?: number
  /** Maximum length of any rendered text value. */
  maxTextLength?: number
  /** Maximum item labels rendered from a list field. */
  maxListItems?: number
  title?: string
  subtitle?: string
  emptyText?: string
  /** Stable execution/step reference to highlight in the current Run. */
  selectedResultRef?: string | null
}

interface SafeField {
  key: string
  label: string
  value: string
}

interface SafeToolResultView {
  index: number
  key: string
  toolName: string
  known: boolean
  fields: SafeField[]
  resultRef?: string
  selected: boolean
  notice?: string
}

const props = withDefaults(defineProps<AgentToolResultPanelProps>(), {
  maxResults: 16,
  maxFieldsPerResult: 24,
  maxTextLength: 500,
  maxListItems: 20,
  title: '工具结果',
  subtitle: '仅展示按工具契约投影后的安全摘要，不回显原始 payload。',
  emptyText: '当前运行没有可展示的工具结果。',
  selectedResultRef: null,
})

const KNOWN_TOOLS = new Set([
  'project.list',
  'project.context',
  'chapter.inspect',
  'chapter.version.list',
  'chapter.version.diff',
  'outline.inspect',
  'quality.inspect',
  'quality.retest',
  'quality.rewrite_instructions',
  'research.inspect',
  'style.inspect',
  'statistics.project',
  'knowledge.inspect',
  'foreshadowing.inspect',
  'chapter.generate',
  'chapter.rewrite',
  'chapter.version.accept',
])

const SENSITIVE_KEY = /(?:content|source_text|prompt|reasoning|thought|secret|token|password|authorization|api[_-]?key|private|credential|raw_text|prose)/i
const SECRET_VALUE = /(?:bearer\s+[a-z0-9._~+/=-]{12,}|(?:sk|pk)-[a-z0-9_-]{12,}|(?:api[_-]?key|token|password|secret)\s*[:=]\s*[^\s,;]+)/gi

function objectOf(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
}

function listOf(value: unknown): unknown[] {
  return Array.isArray(value) ? value : []
}

function boundedText(value: unknown): string | undefined {
  if (typeof value !== 'string') return undefined
  const normalized = value.replace(/[\u0000-\u001f\u007f]/g, ' ').trim()
  if (!normalized) return undefined
  return normalized.replace(SECRET_VALUE, '[已脱敏]').slice(0, Math.max(1, props.maxTextLength))
}

function displayScalar(value: unknown): string | undefined {
  if (typeof value === 'string') return boundedText(value)
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  if (typeof value === 'boolean') return value ? '是' : '否'
  return undefined
}

function addField(fields: SafeField[], key: string, label: string, value: unknown): void {
  if (SENSITIVE_KEY.test(key)) return
  const rendered = displayScalar(value)
  if (rendered === undefined) return
  fields.push({ key, label, value: rendered })
}

function addFields(
  fields: SafeField[],
  source: Record<string, unknown>,
  definitions: Array<[string, string]>,
): void {
  for (const [key, label] of definitions) addField(fields, key, label, source[key])
}

function firstSafeLabel(item: unknown, keys: string[]): string | undefined {
  const source = objectOf(item)
  for (const key of keys) {
    if (SENSITIVE_KEY.test(key)) continue
    const value = displayScalar(source[key])
    if (value !== undefined) return value
  }
  return undefined
}

function listSummary(value: unknown, keys: string[]): string | undefined {
  const items = listOf(value)
  if (!items.length) return '0 项'
  const visible = items.slice(0, Math.max(1, props.maxListItems)).map((item) => firstSafeLabel(item, keys) || '记录已隐藏')
  const suffix = items.length > props.maxListItems ? `；另有 ${items.length - props.maxListItems} 项未展示` : ''
  return `${visible.join('、')}${suffix}`
}

function addProjectSummary(fields: SafeField[], source: Record<string, unknown>): void {
  addFields(fields, source, [
    ['id', 'ID'],
    ['title', '标题'],
    ['status', '状态'],
    ['genre', '类型'],
    ['completed_chapters', '已完成章节'],
    ['total_chapters', '总章节'],
    ['updated_at', '更新时间'],
    ['last_edited', '最后编辑'],
  ])
}

function addChapterListSummary(fields: SafeField[], value: unknown): void {
  const summary = listSummary(value, ['title', 'chapter_title', 'chapter_number', 'status', 'id'])
  if (summary !== undefined) fields.push({ key: 'chapter_summary', label: '章节摘要', value: summary })
}

function addQualityGate(fields: SafeField[], value: unknown): void {
  const gate = objectOf(value)
  addFields(fields, gate, [
    ['passed', '质量门通过'],
    ['quality_score', '质量分数'],
    ['blocker_count', '阻断数量'],
    ['tone', '基调'],
  ])
  const blockers = listOf(gate.blockers)
  if (blockers.length) {
    const summary = blockers.slice(0, Math.max(1, props.maxListItems)).map((item) => {
      const blocker = objectOf(item)
      const code = displayScalar(blocker.code) || '质量阻断'
      const severity = displayScalar(blocker.severity)
      return severity ? `${code}（${severity}）` : code
    }).join('、')
    fields.push({ key: 'blockers', label: '阻断摘要', value: `${summary}${blockers.length > props.maxListItems ? '；其余已隐藏' : ''}` })
  }
}

function projectFields(toolName: string, payload: Record<string, unknown>): { fields: SafeField[]; notice?: string } {
  const fields: SafeField[] = []
  let notice: string | undefined

  switch (toolName) {
    case 'project.list': {
      const projects = listOf(payload.projects)
      addField(fields, 'count', '项目数量', projects.length)
      const summary = listSummary(projects, ['title', 'id', 'status'])
      if (summary !== undefined) fields.push({ key: 'projects', label: '项目摘要', value: summary })
      notice = '仅显示项目标识和状态摘要。'
      break
    }
    case 'project.context': {
      addProjectSummary(fields, objectOf(payload.project))
      notice = '项目上下文中的正文、提示词和敏感字段不会在此面板展开。'
      break
    }
    case 'chapter.inspect':
    case 'outline.inspect':
    case 'quality.inspect': {
      const result = objectOf(payload.result)
      addFields(fields, result, [
        ['chapter_count', '章节数量'],
        ['outline_count', '提纲数量'],
        ['status', '状态'],
        ['quality_status', '质量状态'],
      ])
      addChapterListSummary(fields, result.chapters || result.outlines || result.items)
      notice = '列表内容仅保留安全标识摘要，正文和原始长文本不展开。'
      break
    }
    case 'chapter.version.list': {
      addFields(fields, payload, [['count', '版本数量']])
      const versions = listOf(payload.versions)
      const summary = versions.slice(0, Math.max(1, props.maxListItems)).map((item) => {
        const version = objectOf(item)
        const chapter = displayScalar(version.chapter_number) || '?'
        const id = displayScalar(version.version_id) || '?'
        const status = displayScalar(version.status) || '未知状态'
        const words = displayScalar(version.word_count)
        return `第${chapter}章 v${id} · ${status}${words ? ` · ${words}字` : ''}`
      }).join('；')
      if (versions.length) fields.push({ key: 'versions', label: '版本摘要', value: `${summary}${versions.length > props.maxListItems ? '；其余已隐藏' : ''}` })
      notice = '版本正文不会在工具结果面板中渲染。'
      break
    }
    case 'chapter.version.diff': {
      addFields(fields, payload, [
        ['chapter_number', '章节号'],
        ['from_version_id', '来源版本'],
        ['to_version_id', '目标版本'],
      ])
      addFields(fields, objectOf(payload.summary), [
        ['added', '新增行'],
        ['modified', '修改行'],
        ['deleted', '删除行'],
        ['unchanged', '未变行'],
      ])
      addField(fields, 'diff_line_count', '差异行数', listOf(payload.diff_lines).length)
      notice = '差异中的 original_line/patched_line 属于正文内容，已全部隐藏。'
      break
    }
    case 'quality.retest': {
      addFields(fields, payload, [
        ['version_id', '版本ID'],
        ['content_hash', '内容哈希'],
        ['word_count', '字数'],
        ['quality_status', '质量状态'],
      ])
      addQualityGate(fields, payload.quality_gate)
      notice = '复测结果保留质量指标，不展示章节正文。'
      break
    }
    case 'quality.rewrite_instructions': {
      addFields(fields, payload, [
        ['artifact_id', 'Artifact ID'],
        ['chapter_number', '章节号'],
        ['source_version_id', '来源版本'],
        ['instruction_count', '指令数量'],
      ])
      const instructions = listOf(payload.instructions)
      const summary = instructions.slice(0, Math.max(1, props.maxListItems)).map((item) => {
        const instruction = objectOf(item)
        const code = displayScalar(instruction.code) || 'rewrite'
        const severity = displayScalar(instruction.severity)
        const text = boundedText(instruction.instruction)
        return `${code}${severity ? `（${severity}）` : ''}${text ? `：${text}` : ''}`
      }).join('；')
      if (instructions.length) fields.push({ key: 'instructions', label: '修复指令摘要', value: `${summary}${instructions.length > props.maxListItems ? '；其余已隐藏' : ''}` })
      notice = '不展示 snippet、候选正文、提示词或原始 payload。'
      break
    }
    case 'research.inspect': {
      addFields(fields, payload, [['count', '研究条目数量']])
      const artifacts = listOf(payload.artifacts)
      const summary = artifacts.slice(0, Math.max(1, props.maxListItems)).map((item) => {
        const artifact = objectOf(item)
        const scope = displayScalar(artifact.scope) || '未知范围'
        const status = displayScalar(artifact.status) || '未知状态'
        const text = boundedText(artifact.summary)
        return `${scope} · ${status}${text ? `：${text}` : ''}`
      }).join('；')
      if (artifacts.length) fields.push({ key: 'artifacts', label: '研究摘要', value: `${summary}${artifacts.length > props.maxListItems ? '；其余已隐藏' : ''}` })
      notice = '仅展示有界研究摘要，不启动联网研究。'
      break
    }
    case 'style.inspect': {
      addFields(fields, payload, [['profile_count', '文风档案数量'], ['applied_profile_id', '已应用档案']])
      const profiles = listOf(payload.profiles)
      const summary = profiles.slice(0, Math.max(1, props.maxListItems)).map((item) => {
        const profile = objectOf(item)
        const name = displayScalar(profile.name) || '未命名文风'
        const type = displayScalar(profile.profile_type)
        return `${name}${type ? ` · ${type}` : ''}`
      }).join('；')
      if (profiles.length) fields.push({ key: 'profiles', label: '文风摘要', value: `${summary}${profiles.length > props.maxListItems ? '；其余已隐藏' : ''}` })
      notice = '不展示 source、prompt_context 或原始文风文本。'
      break
    }
    case 'statistics.project': {
      addProjectSummary(fields, objectOf(payload.project))
      addFields(fields, objectOf(payload.chapters), [
        ['chapter_count', '章节数量'],
        ['outline_count', '提纲数量'],
        ['selected_version_count', '已选版本数量'],
        ['total_word_count', '总字数'],
        ['latest_chapter_number', '最新章节'],
      ])
      addFields(fields, objectOf(payload.quality), [
        ['evaluated_version_count', '已评估版本'],
        ['passed_count', '通过数量'],
        ['blocked_count', '阻断数量'],
        ['unknown_count', '未评估数量'],
      ])
      notice = '统计面板不读取或渲染章节正文。'
      break
    }
    case 'knowledge.inspect': {
      const result = objectOf(payload.result)
      const nodes = listOf(result.nodes)
      const edges = listOf(result.edges)
      addField(fields, 'node_count', '知识节点数量', nodes.length)
      addField(fields, 'edge_count', '关系数量', edges.length)
      const nodeSummary = listSummary(nodes, ['name', 'title', 'type', 'id'])
      if (nodeSummary !== undefined) fields.push({ key: 'nodes', label: '节点摘要', value: nodeSummary })
      notice = '知识图谱只展示有限标识摘要，不展开原始描述和正文。'
      break
    }
    case 'foreshadowing.inspect': {
      const result = objectOf(payload.result)
      addField(fields, 'total', '伏笔总数', result.total)
      const summary = listSummary(result.items, ['title', 'name', 'status', 'type', 'chapter_number', 'id'])
      if (summary !== undefined) fields.push({ key: 'items', label: '伏笔摘要', value: summary })
      notice = '仅展示伏笔标识、类型和状态摘要。'
      break
    }
    case 'chapter.generate':
    case 'chapter.rewrite':
    case 'chapter.version.accept': {
      const artifact = objectOf(payload.artifact)
      addFields(fields, artifact, [['id', 'Artifact ID'], ['kind', '类型'], ['created_at', '创建时间']])
      addFields(fields, objectOf(artifact.metadata_json), [
        ['status', '状态'],
        ['chapter_number', '章节号'],
        ['quality_status', '质量状态'],
        ['accepted_version_id', '已接受版本'],
      ])
      notice = '写入结果只展示 Artifact/版本元数据，不展示正文。'
      break
    }
  }

  return { fields: fields.slice(0, Math.max(0, props.maxFieldsPerResult)), notice }
}

const views = computed<SafeToolResultView[]>(() => props.results
  .slice(0, Math.max(0, props.maxResults))
  .map((item, index) => {
    const toolName = boundedText(item?.tool_name) || '未知工具'
    const known = KNOWN_TOOLS.has(item?.tool_name || '')
    const projection = known ? projectFields(item.tool_name, objectOf(item.result)) : { fields: [] }
    return {
      index,
      key: `${index}:${toolName}`,
      toolName,
      known,
      fields: projection.fields,
      resultRef: typeof item?.result_ref === 'string' ? item.result_ref : undefined,
      selected: typeof item?.result_ref === 'string' && item.result_ref === props.selectedResultRef,
      notice: projection.notice,
    }
  }))

const hiddenResultCount = computed(() => Math.max(0, props.results.length - Math.max(0, props.maxResults)))
</script>

<style scoped>
.tool-result-list {
  display: grid;
  gap: 0.75rem;
}

.tool-result-card {
  min-width: 0;
  transition: border-color 160ms ease, box-shadow 160ms ease, background 160ms ease;
  padding: 0.75rem;
  border: 1px solid var(--xq-border);
  border-radius: 0.65rem;
  background: rgba(255, 255, 255, 0.68);
}

.tool-result-card--selected {
  border-color: var(--xq-gold-deep);
  background: rgba(214, 169, 74, 0.12);
  box-shadow: 0 0 0 2px rgba(214, 169, 74, 0.2);
}

.tool-result-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.6rem;
  flex-wrap: wrap;
}

.tool-result-card__badge {
  padding: 0.12rem 0.45rem;
  border-radius: 999px;
  color: var(--xq-jade);
  background: rgba(61, 143, 125, 0.12);
  font-size: 0.72rem;
  font-weight: 800;
}

.tool-result-card__badge--muted {
  color: var(--xq-ink-muted);
  background: rgba(100, 116, 139, 0.12);
}

.tool-result-card__ref,
.tool-result-card__selection {
  color: var(--xq-ink-muted);
  font-size: 0.74rem;
  line-height: 1.4;
}

.tool-result-card__selection {
  margin: 0.45rem 0 0;
  color: var(--xq-gold-deep);
  font-weight: 800;
}

.tool-result-fields {
  display: grid;
  gap: 0.35rem;
  margin: 0.65rem 0 0;
}

.tool-result-field {
  display: grid;
  grid-template-columns: minmax(7rem, 0.35fr) minmax(0, 1fr);
  gap: 0.6rem;
  padding-bottom: 0.35rem;
  border-bottom: 1px dashed var(--xq-border);
}

.tool-result-field dt {
  color: var(--xq-ink-muted);
  font-size: 0.82rem;
}

.tool-result-field dd {
  min-width: 0;
  margin: 0;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
  line-height: 1.5;
}

.tool-result-card__notice,
.tool-result-empty {
  margin: 0.65rem 0 0;
  color: var(--xq-ink-muted);
  font-size: 0.82rem;
  line-height: 1.5;
}

.tool-result-empty {
  margin-top: 0;
}

@media (max-width: 520px) {
  .tool-result-field {
    grid-template-columns: 1fr;
    gap: 0.15rem;
  }
}
</style>
