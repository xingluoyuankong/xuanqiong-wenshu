import { createServer } from 'node:net'
import { spawn } from 'node:child_process'
import { mkdirSync, writeFileSync } from 'node:fs'
const server = createServer()
await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve) })
const port = server.address().port
await new Promise((resolve, reject) => server.close(e => e ? reject(e) : resolve()))
const tag = process.env.XQ_SSE_REPORT || `browser-${Date.now()}`
const dir = 'audit/sse-isolation-20260907'
mkdirSync(dir, { recursive: true })
const env = { ...process.env, XQ_SSE_PORT: String(port), XQ_SSE_REPORT: tag }
console.log(`SELECTED_PORT=${port}; existing 5174 untouched`)
writeFileSync(`${dir}/${tag}-launch.json`, JSON.stringify({ port, pid: process.pid, started: new Date().toISOString(), args: process.argv.slice(2) }, null, 2))
const child = spawn(process.execPath, ['node_modules/@playwright/test/cli.js', 'test', '-c', 'playwright.sse-audit.config.ts', ...process.argv.slice(2)], { env, stdio: 'inherit' })
child.on('exit', code => { process.exitCode = code ?? 1 })
