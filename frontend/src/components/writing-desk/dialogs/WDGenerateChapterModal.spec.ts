import { describe, it, expect } from "vitest"

describe("WDGenerateChapterModal", () => {
  it("exists", async () => {
    const m = await import("@/components/writing-desk/dialogs/WDGenerateChapterModal.vue")
    expect(m.default).toBeDefined()
  })
})