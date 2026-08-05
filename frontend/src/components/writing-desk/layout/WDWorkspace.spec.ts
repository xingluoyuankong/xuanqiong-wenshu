import { describe, it, expect } from "vitest"

describe("WDWorkspace", () => {
  it("exists", async () => {
    const m = await import("@/components/writing-desk/layout/WDWorkspace.vue")
    expect(m.default).toBeDefined()
  })
})