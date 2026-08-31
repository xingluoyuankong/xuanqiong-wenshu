import { defineConfig, devices } from '@playwright/test'

const backendPort = process.env.XQ_AGENT_E2E_BACKEND_PORT || '18013'
const frontendPort = process.env.XQ_AGENT_E2E_FRONTEND_PORT || '5176'
const backendBaseUrl = 'http://127.0.0.1:' + backendPort
const frontendBaseUrl = 'http://127.0.0.1:' + frontendPort

export default defineConfig({
  testDir: './e2e/real',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 90_000,
  reporter: 'list',
  use: {
    baseURL: frontendBaseUrl,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: 'node e2e/scripts/start-real-agent-backend.mjs',
      url: backendBaseUrl + '/health',
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        XQ_AGENT_E2E_BACKEND_PORT: backendPort,
      },
    },
    {
      command: 'npm run dev -- --host 127.0.0.1 --port ' + frontendPort,
      url: frontendBaseUrl + '/agent',
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        VITE_API_PROXY_TARGET: backendBaseUrl,
        XUANQIONG_WENSHU_FRONTEND_PORT: frontendPort,
      },
    },
  ],
})
