import { describe, it, expect } from "vitest"

describe("NovelWorkspace", () => {
  it("exists", async () => {
    const m = await import("@/views/NovelWorkspace.vue")
    expect(m.default).toBeDefined()
  })
})