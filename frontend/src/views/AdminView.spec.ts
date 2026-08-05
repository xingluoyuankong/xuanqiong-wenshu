import { describe, it, expect } from "vitest"

describe("AdminView", () => {
  it("exists", async () => {
    const m = await import("@/views/AdminView.vue")
    expect(m.default).toBeDefined()
  })
})