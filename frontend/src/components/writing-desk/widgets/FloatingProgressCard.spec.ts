import { describe, it, expect } from "vitest"

describe("FloatingProgressCard", () => {
  it("exists", async () => {
    const m = await import("@/components/writing-desk/widgets/FloatingProgressCard.vue")
    expect(m.default).toBeDefined()
  })
})