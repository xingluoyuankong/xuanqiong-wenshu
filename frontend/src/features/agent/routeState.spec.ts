import { describe, expect, it } from 'vitest'
import { parseAgentRouteState, writingDeskQueryFromAgent } from './routeState'

describe('Agent route state', () => {
  it('normalizes supported deep-link fields and rejects malformed focus/numbers', () => {
    expect(parseAgentRouteState({ project_id: 'p-1', session_id: ['s-1', 'ignored'], run_id: 'r-1', artifact_id: 'a-1', chapter: '7', version_id: '42', focus: 'quality-blocker' })).toEqual({ projectId: 'p-1', sessionId: 's-1', runId: 'r-1', artifactId: 'a-1', chapter: 7, versionId: 42, focus: 'quality-blocker' })
    expect(parseAgentRouteState({ chapter: '0', version_id: 'x', focus: 'raw-provider-data' })).toEqual({ projectId: undefined, sessionId: undefined, runId: undefined, artifactId: undefined, chapter: undefined, versionId: undefined, focus: undefined })
  })

  it('maps an Agent artifact to the WritingDesk deep-link contract without exposing run/session data', () => {
    expect(writingDeskQueryFromAgent({ artifactId: 'artifact-1', chapter: 7, versionId: 42, focus: 'quality-blocker' })).toEqual({ artifact_id: 'artifact-1', chapter: '7', version_id: '42', focus: 'quality-blocker' })
  })
})
