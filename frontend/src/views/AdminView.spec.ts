import { describe, it, expect } from "vitest"

describe("AdminView", () => {
  it("exists", async () => {
    const m = await import("@/views/AdminView.vue")
    expect(m.default).toBeDefined()
    // AdminView 的 defineAsyncComponent 依赖图较大，Windows 上 Vite transform
    // 常超过 vitest 默认 5s（与 WritingDesk.spec.ts 同一约定）
  }, 20000)
})