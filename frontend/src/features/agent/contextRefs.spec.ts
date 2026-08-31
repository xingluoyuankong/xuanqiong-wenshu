import { describe, expect, it } from 'vitest'

import { buildAgentContextRefs, contextRefKey, contextRefLabel } from './contextRefs'

describe('Agent ContextRefs', () => {
  it('builds stable identifier-only refs without prose or metadata', () => {
    expect(buildAgentContextRefs({ projectId: 'project-a' })).toEqual([
      { kind: 'project', project_id: 'project-a' },
    ])
    const refs = buildAgentContextRefs({ projectId: 'project-a', chapterNumber: 7, versionId: 12 })
    expect(refs).toEqual([
      { kind: 'project', project_id: 'project-a' },
      {
        kind: 'chapter_version',
        project_id: 'project-a',
        chapter_number: 7,
        version_id: 12,
        role: 'selected',
      },
    ])
    expect(JSON.stringify(refs)).not.toContain('content')
    expect(JSON.stringify(refs)).not.toContain('summary')
  })

  it('drops invalid project, chapter, and detached version values', () => {
    expect(buildAgentContextRefs({ projectId: ' ', chapterNumber: 7, versionId: 12 })).toEqual([])
    expect(buildAgentContextRefs({ projectId: 'project-a', versionId: 12 })).toEqual([
      { kind: 'project', project_id: 'project-a' },
    ])
    expect(
      buildAgentContextRefs({ projectId: 'project-a', chapterNumber: 0, versionId: 12 }),
    ).toEqual([{ kind: 'project', project_id: 'project-a' }])
  })

  it('keeps project entities identifier-only and gives them stable context keys', () => {
    const refs = buildAgentContextRefs({
      projectId: 'project-a',
      entityRefs: [
        { kind: 'character', entityId: 17 },
        { kind: 'faction', entityId: 23 },
      ],
    })
    expect(refs).toEqual([
      { kind: 'project', project_id: 'project-a' },
      { kind: 'character', project_id: 'project-a', entity_id: 17 },
      { kind: 'faction', project_id: 'project-a', entity_id: 23 },
    ])
    expect(contextRefKey(refs[1])).toBe('character:project-a:17')
    expect(contextRefLabel(refs[2])).toBe('势力 #23')
    expect(JSON.stringify(refs)).not.toContain('name')
    expect(JSON.stringify(refs)).not.toContain('content')
  })

  it('keeps relational quality findings identifier-only and gives them a stable context key', () => {
    const refs = buildAgentContextRefs({
      projectId: 'project-a',
      qualityFindingRefs: [{ findingId: 'finding-17' }],
    })
    expect(refs).toEqual([
      { kind: 'project', project_id: 'project-a' },
      { kind: 'quality_finding', project_id: 'project-a', finding_id: 'finding-17' },
    ])
    expect(contextRefKey(refs[1])).toBe('quality_finding:project-a:finding-17')
    expect(contextRefLabel(refs[1])).toBe('质量发现：finding-')
    expect(JSON.stringify(refs)).not.toContain('message')
    expect(JSON.stringify(refs)).not.toContain('evidence')
  })

  it('has stable keys and user-facing labels', () => {
    const ref = {
      kind: 'chapter_version' as const,
      project_id: 'project-a',
      chapter_number: 7,
      version_id: 12,
      role: 'selected' as const,
    }
    expect(contextRefKey(ref)).toBe('chapter_version:project-a:7:12:selected')
    expect(contextRefLabel(ref)).toBe('第 7 章 · 版本 12')
    expect(
      contextRefLabel({ kind: 'project', project_id: 'project-a' }, { projectTitle: '星河旧梦' }),
    ).toBe('项目：星河旧梦')
  })
})
