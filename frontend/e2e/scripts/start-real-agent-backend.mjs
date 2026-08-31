import { spawn } from 'node:child_process'
import { existsSync, mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const backendRoot = resolve(scriptDir, '../../../backend')
const python = join(backendRoot, '.venv', 'Scripts', 'python.exe')
const port = String(process.env.XQ_AGENT_E2E_BACKEND_PORT || '18013')
const tempDir = mkdtempSync(join(tmpdir(), 'xq-agent-e2e-'))
const dbPath = join(tempDir, 'agent-browser-e2e.db')

if (!existsSync(python)) {
  throw new Error('隔离 E2E 未找到后端虚拟环境：' + python)
}

const child = spawn(python, [
  '-m', 'uvicorn', 'app.main:app',
  '--host', '127.0.0.1',
  '--port', port,
  '--log-level', 'warning',
  '--no-access-log',
], {
  cwd: backendRoot,
  env: {
    ...process.env,
    DB_PROVIDER: 'sqlite',
    DATABASE_URL: '',
    SQLITE_DB_PATH: dbPath,
    ENVIRONMENT: 'development',
    DEBUG: 'false',
    ADMIN_DEFAULT_USERNAME: 'agent-e2e-admin',
    ADMIN_DEFAULT_PASSWORD: 'AgentE2E-Only-2026!',
    ADMIN_DEFAULT_EMAIL: 'agent-e2e@example.invalid',
    ALLOW_USER_REGISTRATION: 'true',
    OPENAI_API_KEY: '',
    CPA_API_KEY: '',
    CODEX_AGENT_API_KEY: '',
    XUANQIONG_TEST_LIGHT_IMPORTS: '1',
    PYTHONUNBUFFERED: '1',
    PYTHONUTF8: '1',
  },
  stdio: 'inherit',
})

let stopping = false
const stop = (signal) => {
  if (stopping) return
  stopping = true
  if (!child.killed) child.kill(signal)
}

process.on('SIGINT', () => stop('SIGINT'))
process.on('SIGTERM', () => stop('SIGTERM'))
child.once('exit', (code) => {
  rmSync(tempDir, { recursive: true, force: true })
  process.exitCode = code ?? 1
})
