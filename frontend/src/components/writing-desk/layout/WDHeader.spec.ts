import { describe, it, expect } from "vitest"

describe("WDHeader", () => {
  it("exists", async () => {
    const m = await import("@/components/writing-desk/layout/WDHeader.vue")
    expect(m.default).toBeDefined()
  })
})