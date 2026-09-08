import { defineConfig, mergeConfig } from 'vitest/config'
import base from '../../vite.config'
export default defineConfig(env => mergeConfig(base(env), {
 plugins: [{ name: 'stage13-command-order-negative-control', enforce: 'pre', transform(source, id) {
  if (id.includes('?') || !id.replaceAll('\\','/').endsWith('/AgentRunCommandHistory.vue')) return
  const anchor = 'return timeOrder'
  if (!source.includes(anchor)) throw new Error('missing mutation anchor')
  return { code: source.replace(anchor, 'return timeOrder || left.id.localeCompare(right.id)'), map: null }
 } }],
}))
