import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, it, expect } from "vitest"

describe("WDWorkspace", () => {
  it("exists", async () => {
    const m = await import("@/components/writing-desk/layout/WDWorkspace.vue")
    expect(m.default).toBeDefined()
  })

  it('实际字数展示保留 0 值并使用空值判断', () => {
    const source = readFileSync(resolve(process.cwd(), 'src/components/writing-desk/layout/WDWorkspace.vue'), 'utf8')
    expect(source).toContain('resolveActualWordCount')
    expect(source).toContain('if (actual !== null)')
    expect(source).toContain('selectedChapter?.word_count != null')
    expect(source).not.toContain('if (actual) return pick(`实际 ${actual} 字`')
  })
})