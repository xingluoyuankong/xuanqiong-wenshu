import { defineConfig, devices } from '@playwright/test'
const port = process.env.XQ_SSE_PORT
if (!port) throw new Error('XQ_SSE_PORT must be supplied by the isolated runner')
const baseURL = `http://127.0.0.1:${port}`
export default defineConfig({
  testDir: './e2e', testMatch: ['agent-sse-isolation.spec.ts', 'agent-workspace.spec.ts'], workers: 1, retries: 0, timeout: 100000,
  outputDir: `./audit/sse-isolation-20260907/${process.env.XQ_SSE_REPORT || 'browser'}-artifacts`,
  reporter: [['list'], ['json', { outputFile: `./audit/sse-isolation-20260907/${process.env.XQ_SSE_REPORT || 'browser'}-results.json` }]],
  use: { baseURL, trace: 'on', screenshot: 'on', video: 'off' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: { command: 'node e2e/scripts/start-sse-audit-server.mjs', url: baseURL + '/e2e/fixtures/sse-audit.html', reuseExistingServer: false, timeout: 120000, env: { XQ_SSE_PORT: port } },
})
