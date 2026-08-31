import { spawn } from 'node:child_process'
import { existsSync, mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const backendRoot = resolve(scriptDir, '../../../backend')
const python = join(backendRoot, '.venv', 'Scripts', 'python.exe')
const port = String(process.env.XQ_AGENT_E2E_BACKEND_PORT || '18023')
const tempDir = mkdtempSync(join(tmpdir(), 'xq-agent-provider-e2e-'))
const dbPath = join(tempDir, 'agent-provider-browser-e2e.db')
const env = { ...process.env }

// Let Python Settings load backend/.env.  This provider-only E2E must not
// inherit the deliberately blank API-key overrides used by offline real E2E.
delete env.OPENAI_API_KEY
delete env.OPENAI_API_BASE_URL
delete env.OPENAI_API_BASE
delete env.OPENAI_MODEL_NAME
delete env.CPA_API_KEY
delete env.CODEX_AGENT_API_KEY

if (!existsSync(python)) {
  throw new Error('隔离 Provider E2E 未找到后端虚拟环境：' + python)
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
    ...env,
    DB_PROVIDER: 'sqlite',
    DATABASE_URL: '',
    SQLITE_DB_PATH: dbPath,
    ENVIRONMENT: 'development',
    DEBUG: 'false',
    ADMIN_DEFAULT_USERNAME: 'agent-provider-e2e-admin',
    ADMIN_DEFAULT_PASSWORD: 'AgentProviderE2E-Only-2026!',
    ADMIN_DEFAULT_EMAIL: 'agent-provider-e2e@example.invalid',
    ALLOW_USER_REGISTRATION: 'true',
    AGENT_INLINE_EXECUTION: 'true',
    AGENT_INLINE_VISIBLE_RESPONSE: 'true',
    AGENT_VISIBLE_RESPONSE_MAX_TOKENS: '96',
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
