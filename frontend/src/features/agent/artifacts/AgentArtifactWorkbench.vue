<template>
  <XqPanel
    v-if="artifacts.length"
    title="候选结果"
    subtitle="接受后才会保存为新的章节版本。"
    data-testid="agent-artifact-panel"
  >
    <article v-for="artifact in artifacts" :key="artifact.id" class="approval-card">
      <b>{{ artifact.kind }}</b>
      <span>{{ String(artifact.metadata_json.status || 'candidate') }}</span>
      <small>质量：{{ qualityStatus(artifact) }} · 阻断项 {{ qualityBlockerCount(artifact) }}</small>
      <small v-if="qualityFactsLoading[artifact.id]" class="muted" data-testid="agent-artifact-quality-loading">正在读取权威质量门禁…</small>
      <small v-else-if="qualityFactsErrors[artifact.id]" class="error" data-testid="agent-artifact-quality-error">质量门禁读取失败：{{ qualityFactsErrors[artifact.id] }}</small>
      <small v-else-if="!artifactQuality(artifact)" class="muted" data-testid="agent-artifact-quality-pending">尚未取得权威质量门禁，暂不能接受候选。</small>
      <small v-if="retestSide(artifact, 'before') && retestSide(artifact, 'after')">
        复测：before {{ retestSide(artifact, 'before')?.blocker_count ?? '?' }} → after
        {{ retestSide(artifact, 'after')?.blocker_count ?? '?' }}；阻断变化
        {{ retestDelta(artifact)?.blocker_count ?? '?' }}
      </small>
      <div
        v-if="rewriteInstructions[artifact.id]?.length"
        class="rewrite-instruction-list"
        data-testid="agent-rewrite-instructions"
      >
        <strong>结构化修复指令</strong>
        <article
          v-for="instruction in rewriteInstructions[artifact.id]"
          :key="instruction.code + instruction.instruction"
          class="rewrite-instruction"
        >
          <b>{{ instruction.code }} · {{ instruction.severity }}</b>
          <span>{{ instruction.instruction }}</span>
          <small>{{
            instruction.anchor_status === 'located'
              ? `定位：${instruction.snippet || '已定位'}`
              : '未安全定位原文，只提供规则级修复建议'
          }}</small>
        </article>
      </div>
      <div v-if="artifactQuality(artifact)?.findings.length" class="quality-finding-list" data-testid="agent-quality-finding-list">
        <strong>可选质量发现上下文</strong>
        <article v-for="finding in artifactQuality(artifact)?.findings" :key="finding.finding_id" class="quality-finding-row">
          <span>{{ finding.code }} · {{ finding.severity }} · {{ finding.status }}</span>
          <XqButton
            size="sm"
            variant="secondary"
            :data-testid="`agent-quality-finding-${finding.finding_id}`"
            @click="emit('toggle-quality-finding', finding)"
          >{{ selectedQualityFindingIds.includes(finding.finding_id) ? '移除上下文' : '加入上下文' }}</XqButton>
        </article>
      </div>
      <small v-if="qualityCodes(artifact).length">问题码：{{ qualityCodes(artifact).join('、') }}</small>
      <small v-if="artifactLineage(artifact)" data-testid="agent-artifact-lineage-summary">
        谱系边：{{ lineageEdgeCount(artifact) }}（上游 {{ artifactLineage(artifact)?.upstream_edges.length || 0 }} / 下游 {{ artifactLineage(artifact)?.downstream_edges.length || 0 }}）
      </small>
      <small>{{ artifact.uri }}</small>
      <XqButton v-if="canPreview" variant="secondary" size="sm" @click="emit('preview', artifact)">查看候选正文</XqButton>
      <XqButton v-if="artifacts.length > 1 && canDiff" variant="secondary" size="sm" @click="emit('compare', artifact)">查看与其他候选差异</XqButton>
      <XqButton v-if="canLocateBlockers" variant="secondary" size="sm" @click="emit('locate-blockers', artifact)">定位质量阻断</XqButton>
      <XqButton v-if="canLoadRewriteInstructions" variant="secondary" size="sm" data-testid="agent-load-rewrite-instructions-button" @click="emit('load-rewrite-instructions', artifact)">读取修复指令</XqButton>
      <XqButton v-if="canCompareWithVersion && hasVersionTarget(artifact)" variant="secondary" size="sm" data-testid="agent-compare-version-button" @click="emit('compare-with-version', artifact)">与正式版本比较</XqButton>
      <XqButton
        v-if="hasSelectedProject"
        variant="secondary"
        size="sm"
        @click="emit('open-writing-desk', { artifact, focus: qualityBlockerCount(artifact) ? 'quality-blocker' : 'version' })"
      >在写作台打开对应章节</XqButton>
      <div v-if="artifact.metadata_json.status === 'candidate' && canAccept" class="approval-actions">
        <XqButton
          size="sm"
          data-testid="agent-accept-artifact-button"
          :disabled="!canAcceptArtifact(artifact)"
          :title="acceptDisabledReason(artifact)"
          @click="emit('accept', artifact)"
        >接受并保存版本</XqButton>
      </div>
    </article>

    <XqPanel v-if="artifactDiffLoading || artifactDiff" title="候选差异" data-testid="agent-artifact-diff">
      <p v-if="artifactDiffLoading" class="muted">正在计算差异…</p>
      <template v-else-if="artifactDiff">
        <small v-if="isVersionDiff(artifactDiff)" data-testid="agent-artifact-version-diff-summary">对照第 {{ artifactDiff.chapter_number }} 章正式版本 {{ artifactDiff.version_id }}</small>
        <small>
          比较 {{ artifactDiff.artifact_id.slice(0, 8) }} 与 {{ artifactDiff.against_artifact_id.slice(0, 8) }} · 新增
          {{ artifactDiff.summary.added || 0 }} · 修改 {{ artifactDiff.summary.modified || 0 }} · 删除
          {{ artifactDiff.summary.deleted || 0 }}
        </small>
        <ol class="artifact-diff-list">
          <li v-for="line in artifactDiff.diff_lines" :key="line.line_number + line.change_type + (line.original_line || '')">
            <b>{{ line.line_number }}</b>
            <span :class="'diff-' + line.change_type">{{ line.patched_line ?? line.original_line }}</span>
          </li>
        </ol>
      </template>
    </XqPanel>

    <XqPanel v-if="qualityBlockersLoading || qualityBlockers.length" title="质量阻断定位" data-testid="agent-quality-blockers">
      <p v-if="qualityBlockersLoading" class="muted">正在读取质量阻断…</p>
      <ol v-else class="blocker-list">
        <li v-for="item in qualityBlockers" :key="item.artifact_id + item.code + String(item.start_char)">
          <strong>{{ item.code }}</strong>
          <span>{{ item.message }}</span>
          <small>
            {{ item.anchor_status === 'located' ? `已定位：${item.start_char}-${item.end_char}` : '尚未定位到具体文本' }}
            · {{ item.source }}
          </small>
          <small v-if="item.snippet">{{ item.snippet }}</small>
        </li>
      </ol>
    </XqPanel>
  </XqPanel>
</template>

<script setup lang="ts">
import type {
  AgentArtifact,
  AgentArtifactDiff,
  AgentArtifactLineage,
  AgentArtifactQuality,
  AgentArtifactVersionDiff,
  AgentQualityBlocker,
  AgentQualityFinding,
  AgentRewriteInstruction,
} from '@/api/agent'
import { XqButton, XqPanel } from '@/shared/ui'

const props = withDefaults(defineProps<{
  artifacts: AgentArtifact[]
  qualityFacts: Record<string, AgentArtifactQuality>
  qualityFactsLoading: Record<string, boolean>
  qualityFactsErrors: Record<string, string>
  lineageFacts: Record<string, AgentArtifactLineage>
  qualityBlockers: AgentQualityBlocker[]
  qualityBlockersLoading: boolean
  rewriteInstructions: Record<string, AgentRewriteInstruction[]>
  artifactDiff: AgentArtifactDiff | null
  artifactDiffLoading: boolean
  hasSelectedProject: boolean
  canPreview: boolean
  canDiff: boolean
  canLocateBlockers: boolean
  canLoadRewriteInstructions: boolean
  canCompareWithVersion: boolean
  canAccept: boolean
  selectedQualityFindingIds?: string[]
}>(), {
  artifacts: () => [],
  qualityFacts: () => ({}),
  qualityFactsLoading: () => ({}),
  qualityFactsErrors: () => ({}),
  lineageFacts: () => ({}),
  qualityBlockers: () => [],
  qualityBlockersLoading: false,
  rewriteInstructions: () => ({}),
  artifactDiff: null,
  artifactDiffLoading: false,
  hasSelectedProject: false,
  canPreview: false,
  canDiff: false,
  canLocateBlockers: false,
  canLoadRewriteInstructions: false,
  canCompareWithVersion: false,
  canAccept: false,
  selectedQualityFindingIds: () => [],
})

const emit = defineEmits<{
  preview: [artifact: AgentArtifact]
  compare: [artifact: AgentArtifact]
  'locate-blockers': [artifact: AgentArtifact]
  'load-rewrite-instructions': [artifact: AgentArtifact]
  'compare-with-version': [artifact: AgentArtifact]
  accept: [artifact: AgentArtifact]
  'open-writing-desk': [payload: { artifact: AgentArtifact; focus: 'quality-blocker' | 'version' }]
  'toggle-quality-finding': [finding: AgentQualityFinding]
}>()

const artifactQuality = (artifact: AgentArtifact) => props.qualityFacts[artifact.id] || null
const artifactLineage = (artifact: AgentArtifact) => props.lineageFacts[artifact.id] || null
const qualityGateDecision = (artifact: AgentArtifact) => artifactQuality(artifact)?.gate?.decision || null
const hasVersionTarget = (artifact: AgentArtifact) => {
  const metadata = artifact.metadata_json || {}
  const chapter = Number(metadata.chapter_number)
  const versionId = Number(metadata.source_version_id)
  return Number.isInteger(chapter) && chapter >= 1 && Number.isInteger(versionId) && versionId >= 1
}
const canAcceptArtifact = (artifact: AgentArtifact) => {
  if (props.qualityFactsLoading[artifact.id] || props.qualityFactsErrors[artifact.id]) return false
  const decision = qualityGateDecision(artifact)
  return decision === 'passed' || decision === 'waived'
}
const acceptDisabledReason = (artifact: AgentArtifact) => {
  if (props.qualityFactsLoading[artifact.id]) return '正在读取权威质量门禁'
  if (props.qualityFactsErrors[artifact.id]) return '质量门禁读取失败，暂不能接受候选'
  const decision = qualityGateDecision(artifact)
  if (!decision) return '尚未取得权威质量门禁，暂不能接受候选'
  return decision === 'blocked' ? '质量门禁存在阻断项' : ''
}
const isVersionDiff = (diff: AgentArtifactDiff): diff is AgentArtifactVersionDiff =>
  'chapter_number' in diff && 'version_id' in diff
const qualityStatus = (artifact: AgentArtifact) =>
  qualityGateDecision(artifact) || String(artifact.metadata_json.quality_status || '未检查')
const qualityBlockerCount = (artifact: AgentArtifact) => {
  const facts = artifactQuality(artifact)
  if (facts) return facts.findings.filter((item) => item.severity === 'blocker').length
  const gate = artifact.metadata_json.quality_gate
  return gate && typeof gate === 'object' && gate !== null && Array.isArray((gate as Record<string, unknown>).blockers)
    ? ((gate as Record<string, unknown>).blockers as unknown[]).length
    : 0
}
const qualityCodes = (artifact: AgentArtifact) => {
  const facts = artifactQuality(artifact)
  if (facts) return facts.findings.map((item) => item.code).slice(0, 8)
  const gate = artifact.metadata_json.quality_gate
  if (!gate || typeof gate !== 'object' || gate === null) return []
  const codes = (gate as Record<string, unknown>).quality_issue_codes
  return Array.isArray(codes) ? codes.map(String).slice(0, 8) : []
}
const lineageEdgeCount = (artifact: AgentArtifact) => {
  const facts = artifactLineage(artifact)
  return facts ? facts.upstream_edges.length + facts.downstream_edges.length : 0
}
const qualityRetest = (artifact: AgentArtifact) => {
  const value = artifact.metadata_json.quality_retest
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}
const retestSide = (artifact: AgentArtifact, side: 'before' | 'after') => {
  const value = qualityRetest(artifact)?.[side]
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}
const retestDelta = (artifact: AgentArtifact) => {
  const value = qualityRetest(artifact)?.delta
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}
</script>


