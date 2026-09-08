import { spawnSync } from 'node:child_process'
import { readFileSync, writeFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
const paths = ['src/utils/sseStream.ts', 'src/features/agent/composables/useAgentRunStream.ts']
const hashes = () => Object.fromEntries(paths.map(path => [path, createHash('sha256').update(readFileSync(path)).digest('hex')]))
const before = hashes(), results = []
for (const mode of ['scope', 'dedupe', 'generation', 'transport', 'terminal', 'control']) {
  const run = spawnSync(process.execPath, ['node_modules/vitest/vitest.mjs', 'run', '--config', 'audit/sse-isolation-20260907/mutation.config.ts', 'src/features/agent/composables/useAgentRunStream.isolation.spec.ts', 'src/features/agent/composables/useAgentRunStream.transport.spec.ts', '--reporter=json', `--outputFile=audit/sse-isolation-20260907/mutation-${mode}.json`], { env: { ...process.env, SSE_MUTATION: mode }, encoding: 'utf8' })
  writeFileSync(`audit/sse-isolation-20260907/mutation-${mode}.log`, run.stdout + run.stderr)
  const report = JSON.parse(readFileSync(`audit/sse-isolation-20260907/mutation-${mode}.json`, 'utf8'))
  results.push({ mode, exit_code: run.status, failed: report.numFailedTests, passed: report.numPassedTests, detected: run.status !== 0 && report.numFailedTests > 0 })
  console.log(results.at(-1))
}
const after = hashes()
const result = { results, before, after, source_hashes_unchanged: JSON.stringify(before) === JSON.stringify(after), all_detected: results.every(x => x.detected) }
writeFileSync('audit/sse-isolation-20260907/mutation-results.json', JSON.stringify(result, null, 2))
if (!result.source_hashes_unchanged || !result.all_detected) process.exitCode = 1

