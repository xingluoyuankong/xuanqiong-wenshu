// 审计：源码里 var(--xq-*/--md-*) 引用了但令牌真源与局部作用域都未定义的变量。
// 这类引用会让整条 CSS 声明失效（浏览器直接丢弃），是"颜色乱/背景没了"的隐性来源。
import fs from 'node:fs'
import path from 'node:path'

const tokens = fs.readFileSync('src/shared/styles/tokens.css', 'utf8')
const defined = new Set([...tokens.matchAll(/^\s*(--[a-z0-9-]+)\s*:/gim)].map((m) => m[1]))

const files = []
const walk = (dir) => {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      if (entry.name !== 'node_modules') walk(full)
    } else if (/\.(vue|css|ts)$/.test(entry.name)) {
      files.push(full)
    }
  }
}
walk('src')

const used = new Map()
for (const file of files) {
  const source = fs.readFileSync(file, 'utf8')
  for (const match of source.matchAll(/var\(\s*(--[a-z0-9-]+)/gi)) {
    const name = match[1]
    if (!used.has(name)) used.set(name, new Set())
    used.get(name).add(file.split(path.sep).join('/'))
  }
  // 组件内联定义的局部变量同样视为已定义
  for (const match of source.matchAll(/^\s*(--[a-z0-9-]+)\s*:/gim)) defined.add(match[1])
}

const missing = [...used.keys()]
  .filter((name) => !defined.has(name))
  .filter((name) => name.startsWith('--xq') || name.startsWith('--md'))
  .sort()

console.log('令牌真源 + 局部定义合计:', defined.size)
console.log('引用但未定义:', missing.length)
for (const name of missing) {
  console.log('  ' + name + '  <-  ' + [...used.get(name)].slice(0, 4).join(', '))
}
