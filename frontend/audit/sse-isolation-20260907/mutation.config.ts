import { defineConfig, mergeConfig } from 'vitest/config'
import { readFileSync } from 'node:fs'
import base from '../../vite.config'
const mode = process.env.SSE_MUTATION || ''
const changes: Record<string, [string, string, string]> = {
  scope: ['useAgentRunStream.ts', "if ('run_id' in record && record.run_id !== options.runId) return null", "if (false) return null"],
  dedupe: ['useAgentRunStream.ts', 'if (wasSeen(event.sequence)) return false', 'if (false) return false'],
  generation: ['useAgentRunStream.ts', 'generation === runGeneration &&', 'true &&'],
  transport: ['sseStream.ts', 'callbacks.acceptEvent?.(eventType, parsed, pendingEventId) === false', 'false'],
  terminal: ['sseStream.ts', 'if (aborted && reader && typeof reader.cancel', 'if (false && reader && typeof reader.cancel'],
  control: ['useAgentRunStream.ts', "(!('run_id' in data) || data.run_id === options.runId)", 'true'],
}
export default defineConfig(env => mergeConfig(base(env), {
  plugins: [{ name: 'in-memory-sse-mutation', enforce: 'pre', transform(source, id) {
    const file = id.split('?')[0].replaceAll('\\', '/')
    if (mode === 'baseline') {
      if (file.endsWith('/useAgentRunStream.ts') || file.endsWith('/sseStream.ts')) {
        const name = file.slice(file.lastIndexOf('/') + 1).replace('.ts', '.before.txt')
        return { code: readFileSync(new URL(name, import.meta.url), 'utf8'), map: null }
      }
      return
    }
    const mutation = changes[mode]
    if (!mutation || !file.endsWith('/' + mutation[0])) return
    if (!source.includes(mutation[1])) throw new Error(`missing mutation anchor: ${mode}`)
    return { code: source.replace(mutation[1], mutation[2]), map: null }
  } }],
}))



