import { expect, test } from '@playwright/test'

// Real Vue/layout fixture: no API calls, provider settings, database or auth.
test('UI006 reasoning virtualization: variable heights, prepend anchor, tail and reclamation', async ({ page }) => {
  await page.goto('/e2e/reasoning-virtualization-fixture.html')
  const toggle = page.getByTestId('agent-reasoning-toggle')
  const body = page.getByTestId('agent-reasoning-body')
  const rows = body.locator('pre')
  const geometry = () => body.evaluate(element => {
    const bounds = element.getBoundingClientRect()
    const items = [...element.querySelectorAll('pre')]
    const first = items.find(row => row.getBoundingClientRect().bottom > bounds.top + element.clientTop)
    return {
      count: items.length, first: first?.textContent?.split('\n')[0],
      offset: first ? first.getBoundingClientRect().top - bounds.top : 0,
      top: element.scrollTop, remaining: element.scrollHeight - element.clientHeight - element.scrollTop,
      tail: items.at(-1)?.textContent?.split('\n')[0],
      gaps: items.slice(1).map((row, index) => row.getBoundingClientRect().top - items[index]!.getBoundingClientRect().bottom),
    }
  })
  await expect(rows).toHaveCount(0)
  await toggle.click()
  await expect.poll(async () => (await geometry()).first).toBe('row-100')
  await body.hover()
  await page.mouse.wheel(0, 3500)
  await expect.poll(async () => (await geometry()).top).toBeGreaterThan(3000)
  const before = await geometry()
  await page.getByRole('button', { name: '前插100段', exact: true }).click()
  await expect.poll(async () => (await geometry()).first).toBe(before.first)
  await expect.poll(async () => Math.abs((await geometry()).offset - before.offset)).toBeLessThan(2)
  await page.getByRole('button', { name: '切换宽度', exact: true }).click()
  await expect.poll(async () => (await geometry()).first).toBe(before.first)
  await expect.poll(async () => Math.abs((await geometry()).offset - before.offset)).toBeLessThan(2)
  await expect.poll(async () => (await geometry()).gaps.every(gap => Math.abs(gap - 9) < 1)).toBe(true)
  await body.press('Control+End')
  await expect.poll(async () => (await geometry()).tail).toBe('row-2099')
  await expect.poll(async () => (await geometry()).remaining).toBeLessThan(2)
  await page.getByRole('button', { name: '开始流式', exact: true }).click()
  await page.getByRole('button', { name: '增长尾段', exact: true }).click()
  await expect(rows.last()).toContainText('流式增长')
  await expect.poll(async () => (await geometry()).remaining).toBeLessThan(2)
  await body.press('Control+Home')
  await page.getByRole('button', { name: '增长尾段', exact: true }).click()
  await expect.poll(async () => (await geometry()).top).toBe(0)
  await expect.poll(async () => (await geometry()).first).toBe('row-0')
  expect((await geometry()).count).toBeLessThan(40)
  // Initially expanded manually: streaming completion preserves that choice.
  await page.getByRole('button', { name: '完成流式', exact: true }).click()
  await toggle.click()
  await expect(rows).toHaveCount(0)
  await toggle.click()
  await expect.poll(async () => (await geometry()).first).toBe('row-0')
})
