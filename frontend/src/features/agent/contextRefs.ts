import type { AgentContextRef, AgentEntityContextKind } from '@/api/agent'

export interface AgentManualEntityRef {
  kind: AgentEntityContextKind
  entityId?: number
}

export interface AgentManualQualityFindingRef {
  findingId?: string
}

export interface AgentContextSelection {
  projectId?: string
  chapterNumber?: number
  versionId?: number
  entityRefs?: AgentManualEntityRef[]
  qualityFindingRefs?: AgentManualQualityFindingRef[]
}

const projectId = (value: unknown): string | undefined => {
  if (typeof value !== 'string') return undefined
  const normalized = value.trim()
  return normalized && normalized.length <= 120 ? normalized : undefined
}

const positiveInteger = (value: unknown): number | undefined => {
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isInteger(parsed) && parsed >= 1 && parsed <= 1_000_000 ? parsed : undefined
}

const qualityFindingId = (value: unknown): string | undefined => {
  if (typeof value !== 'string') return undefined
  const normalized = value.trim()
  return normalized && normalized.length <= 36 ? normalized : undefined
}

const appendQualityFindingRefs = (refs: AgentContextRef[], projectId: string, selected: AgentManualQualityFindingRef[] | undefined) => {
  for (const finding of selected || []) {
    const findingId = qualityFindingId(finding.findingId)
    if (findingId) refs.push({ kind: 'quality_finding', project_id: projectId, finding_id: findingId })
  }
}

export function buildAgentContextRefs(selection: AgentContextSelection): AgentContextRef[] {
  const resolvedProjectId = projectId(selection.projectId)
  if (!resolvedProjectId) return []
  const chapterNumber = positiveInteger(selection.chapterNumber)
  const versionId = positiveInteger(selection.versionId)
  const refs: AgentContextRef[] = [{ kind: 'project', project_id: resolvedProjectId }]
  if (!chapterNumber) {
    for (const entity of selection.entityRefs || []) {
      const entityId = positiveInteger(entity.entityId)
      if (entityId) refs.push({ kind: entity.kind, project_id: resolvedProjectId, entity_id: entityId })
    }
    appendQualityFindingRefs(refs, resolvedProjectId, selection.qualityFindingRefs)
    return refs
  }
  if (versionId) {
    refs.push({
      kind: 'chapter_version',
      project_id: resolvedProjectId,
      chapter_number: chapterNumber,
      version_id: versionId,
      role: 'selected',
    })
    for (const entity of selection.entityRefs || []) {
      const entityId = positiveInteger(entity.entityId)
      if (entityId) refs.push({ kind: entity.kind, project_id: resolvedProjectId, entity_id: entityId })
    }
    appendQualityFindingRefs(refs, resolvedProjectId, selection.qualityFindingRefs)
    return refs
  }
  refs.push({ kind: 'chapter', project_id: resolvedProjectId, chapter_number: chapterNumber })
  for (const entity of selection.entityRefs || []) {
    const entityId = positiveInteger(entity.entityId)
    if (entityId) refs.push({ kind: entity.kind, project_id: resolvedProjectId, entity_id: entityId })
  }
  appendQualityFindingRefs(refs, resolvedProjectId, selection.qualityFindingRefs)
  return refs
}

export function contextRefKey(ref: AgentContextRef): string {
  if (ref.kind === 'project') return 'project:' + ref.project_id
  if (ref.kind === 'chapter') return 'chapter:' + ref.project_id + ':' + ref.chapter_number
  if (ref.kind === 'chapter_version')
    return (
      'chapter_version:' +
      ref.project_id +
      ':' +
      ref.chapter_number +
      ':' +
      ref.version_id +
      ':' +
      (ref.role || 'selected')
    )
  if (ref.kind === 'artifact') return 'artifact:' + ref.project_id + ':' + ref.artifact_id
  if (ref.kind === 'quality_finding') return 'quality_finding:' + ref.project_id + ':' + ref.finding_id
  return ref.kind + ':' + ref.project_id + ':' + ref.entity_id
}

export function contextRefLabel(
  ref: AgentContextRef,
  labels: { projectTitle?: string; chapterTitle?: string } = {},
): string {
  if (ref.kind === 'project') return '项目：' + (labels.projectTitle || ref.project_id)
  if (ref.kind === 'chapter')
    return (
      '第 ' + ref.chapter_number + ' 章' + (labels.chapterTitle ? ' · ' + labels.chapterTitle : '')
    )
  if (ref.kind === 'chapter_version')
    return '第 ' + ref.chapter_number + ' 章 · 版本 ' + ref.version_id
  if (ref.kind === 'artifact') return '候选 Artifact：' + ref.artifact_id.slice(0, 8)
  if (ref.kind === 'quality_finding') return '质量发现：' + ref.finding_id.slice(0, 8)
  const labelsByKind = {
    character: '人物', faction: '势力', foreshadowing: '伏笔', knowledge_node: '知识节点', research_artifact: '研究工件',
  }
  return labelsByKind[ref.kind] + ' #' + ref.entity_id
}
