import { describe, it, expect } from "vitest"

describe("NovelDetailShell", () => {
  it("exists", async () => {
    const m = await import("@/components/shared/NovelDetailShell.vue")
    expect(m.default).toBeDefined()
  })
})