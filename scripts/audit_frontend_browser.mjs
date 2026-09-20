import { writeFileSync } from 'node:fs'

const baseUrl = process.env.XQ_FRONTEND_URL || 'http://127.0.0.1:5174'
const routes = (process.env.XQ_FRONTEND_ROUTES || '/,/workspace,/admin').split(',').filter(Boolean)
const chromePort = Number(process.env.XQ_CHROME_PORT || '9222')
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

async function getJson(url) {
  const response = await fetch(url)
  if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`)
  return response.json()
}

async function send(ws, pending, method, params = {}) {
  const id = pending.nextId++
  const result = new Promise((resolve, reject) => pending.requests.set(id, { resolve, reject }))
  ws.send(JSON.stringify({ id, method, params }))
  const message = await result
  if (message.error) throw new Error(JSON.stringify(message.error))
  return message
}

const results = []
for (const route of routes) {
  const targets = await getJson(`http://127.0.0.1:${chromePort}/json/list`)
  const target = targets.find((item) => item.type === 'page' && item.webSocketDebuggerUrl)
  if (!target) throw new Error(`no page target for ${route}`)
  const ws = new WebSocket(target.webSocketDebuggerUrl)
  const pending = { nextId: 1, requests: new Map() }
  ws.onmessage = (event) => {
    const message = JSON.parse(event.data)
    const request = pending.requests.get(message.id)
    if (!request) return
    pending.requests.delete(message.id)
    request.resolve(message)
  }
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
  await send(ws, pending, 'Page.enable')
  await send(ws, pending, 'Runtime.enable')
  await send(ws, pending, 'Page.navigate', { url: `${baseUrl}${route}` })
  await sleep(4000)
  const expression = `JSON.stringify({
    route: ${JSON.stringify(route)},
    title: document.title,
    readyState: document.readyState,
    appRoot: !!document.querySelector('#app'),
    bodyTextLength: document.body?.innerText?.length ?? 0,
    navigation: performance.getEntriesByType('navigation').map((x) => ({
      domContentLoaded: x.domContentLoadedEventEnd,
      loadEventEnd: x.loadEventEnd,
      responseEnd: x.responseEnd,
      duration: x.duration
    })),
    resources: performance.getEntriesByType('resource').map((x) => ({
      name: x.name,
      initiatorType: x.initiatorType,
      startTime: x.startTime,
      responseEnd: x.responseEnd,
      duration: x.duration,
      transferSize: x.transferSize,
      encodedBodySize: x.encodedBodySize,
      decodedBodySize: x.decodedBodySize
    })).filter((x) => x.name.includes('/assets/') || x.name.includes('/api/')).sort((a,b) => a.startTime-b.startTime)
  })`
  const evaluated = await send(ws, pending, 'Runtime.evaluate', { expression, returnByValue: true })
  results.push(JSON.parse(evaluated.result.result.value))
  ws.close()
}

console.log(JSON.stringify({ audit_type: 'frontend_browser_route_baseline', base_url: baseUrl, results }, null, 2))