import { createServer } from 'vite'
const port = Number(process.env.XQ_SSE_PORT)
if (!Number.isSafeInteger(port) || port < 1024) throw new Error('XQ_SSE_PORT required')
const calls = new Map(), evidence = []
const event = (seq, run = 'run-a', type = 'assistant_delta', legacy = false) => {
  const payload = { id: `event-${seq}`, sequence: seq, event_type: type, summary: '公开进度', data: { content: `片段${seq}|` }, created_at: null }
  if (!legacy) payload.run_id = run
  return `id: ${seq}\nevent: ${type}\ndata: ${JSON.stringify(payload)}\n\n`
}
const server = await createServer({
  server: { host: '127.0.0.1', port, strictPort: true },
  cacheDir: 'node_modules/.vite-sse-isolated',
  plugins: [{ name: 'sse-audit-http-fixture', configureServer(server) {
    server.middlewares.use((req, res, next) => {
      const url = new URL(req.url, `http://127.0.0.1:${port}`)
      if (url.pathname === '/__sse/evidence') { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(evidence)); return }
      if (url.pathname !== '/__sse/stream') return next()
      const key = url.searchParams.get('key'), run = url.searchParams.get('run') || 'run-a'
      const count = (calls.get(key) || 0) + 1; calls.set(key, count)
      const record = { key, run, count, query_cursor: url.searchParams.get('after_sequence'), header_cursor: req.headers['last-event-id'] || null, started: Date.now(), ended: null, frames: 0 }
      evidence.push(record)
      res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no' }); res.flushHeaders()
      const timers = []
      const later = (ms, fn) => timers.push(setTimeout(() => { if (!res.destroyed) fn() }, ms))
      const send = (...args) => { record.frames++; res.write(event(...args)) }
      if (key?.startsWith('switch')) {
        send(1, run)
        later(5000, () => { send(2, run, 'run_completed'); res.end() })
      } else if (count === 1) {
        send(1, run)
        later(250, () => send(999, 'run-foreign', 'run_completed'))
        later(500, () => send(1, run))
        later(800, () => send(2, run, 'assistant_delta', true))
        later(1200, () => res.end())
      } else {
        send(2, run)
        // A genuine 60 second TCP stream, not a route.fulfill body or fake clock.
        for (let seq = 3; seq <= 62; seq++) later((seq - 2) * 1000, () => { res.write(': heartbeat\n\n'); send(seq, run) })
        later(60500, () => { send(63, run, 'run_completed'); send(64, run); /* client must cancel the still-open response */ })
      }
      res.on('close', () => { timers.forEach(clearTimeout); record.ended = Date.now() })
    })
  } }],
})
await server.listen()
console.log(`ISOLATED_SSE_SERVER pid=${process.pid} port=${port}`)
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, async () => { await server.close(); process.exit(0) })
