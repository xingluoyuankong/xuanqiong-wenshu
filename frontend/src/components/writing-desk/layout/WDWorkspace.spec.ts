import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, it, expect } from 'vitest'

describe('WDWorkspace', () => {
  it('exists', async () => {
    const m = await import('@/components/writing-desk/layout/WDWorkspace.vue')
    expect(m.default).toBeDefined()
  })

  it('实际字数展示保留 0 值并使用空值判断', () => {
    const source = readFileSync(resolve(process.cwd(), 'src/components/writing-desk/layout/WDWorkspace.vue'), 'utf8')
    expect(source).toContain('resolveActualWordCount')
    expect(source).toContain('if (actual !== null)')
    expect(source).toContain('selectedChapter?.word_count != null')
    expect(source).not.toContain('if (actual) return pick(`实际 ${actual} 字`')
  })

  it('失败态恢复事件接回工作区刷新和候选版本入口', () => {
    const source = readFileSync(resolve(process.cwd(), 'src/components/writing-desk/layout/WDWorkspace.vue'), 'utf8')
    expect(source).toContain("@refreshStatus=\"$emit('fetchChapterStatus')\"")
    expect(source).toContain('@openVersionSelector="openVersionSelector"')
    expect(source).toContain("['failed', 'evaluation_failed'].includes")
    expect(source).toContain('allowedActions: resolveChapterActions(selectedChapter.value, chapterRuntime.value)')
  })

  it('无候选的评审失败不得打开空版本选择器', () => {
    const source = readFileSync(resolve(process.cwd(), 'src/components/writing-desk/layout/WDWorkspace.vue'), 'utf8')
    expect(source).toContain('if (!hasPreviewableVersions.value) return false')
    expect(source).toContain('评审未通过，请先处理根因或重试')
  })
})
