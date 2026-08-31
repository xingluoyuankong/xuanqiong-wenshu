export interface AgentRouteState {
  projectId?: string
  sessionId?: string
  runId?: string
  artifactId?: string
  chapter?: number
  versionId?: number
  focus?: 'artifact' | 'quality-blocker' | 'version'
}

type QueryValue = string | null | Array<string | null> | undefined
type Query = Record<string, QueryValue>

const one = (value: QueryValue): string | undefined => {
  const candidate = Array.isArray(value) ? value[0] : value
  if (typeof candidate !== 'string') return undefined
  const normalized = candidate.trim()
  return normalized && normalized.length <= 120 ? normalized : undefined
}

const positiveInteger = (value: QueryValue): number | undefined => {
  const parsed = Number(one(value))
  return Number.isInteger(parsed) && parsed >= 1 && parsed <= 1_000_000 ? parsed : undefined
}

export function parseAgentRouteState(query: Query): AgentRouteState {
  const focus = one(query.focus)
  return {
    projectId: one(query.project_id),
    sessionId: one(query.session_id),
    runId: one(query.run_id),
    artifactId: one(query.artifact_id),
    chapter: positiveInteger(query.chapter),
    versionId: positiveInteger(query.version_id),
    focus: focus === 'artifact' || focus === 'quality-blocker' || focus === 'version' ? focus : undefined,
  }
}

export function writingDeskQueryFromAgent(state: Pick<AgentRouteState, 'chapter' | 'versionId' | 'focus' | 'artifactId'>): Record<string, string> {
  const query: Record<string, string> = {}
  if (state.chapter) query.chapter = String(state.chapter)
  if (state.versionId) query.version_id = String(state.versionId)
  if (state.focus === 'quality-blocker' || state.focus === 'version') query.focus = state.focus
  if (state.artifactId) query.artifact_id = state.artifactId
  return query
}
