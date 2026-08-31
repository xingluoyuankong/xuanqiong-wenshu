// 一次性清理 main.css 的装饰性视觉噪音：
// 1. 删除所有多层径向渐变光晕（保留同声明里的线性渐变/纯色层）
// 2. 删除磨砂 backdrop-filter（叠加后画面发灰、且拖累滚动性能）
// 3. 过大圆角（>=20px）收敛到令牌 --xq-radius-xl / lg
// 4. 超大扩散投影（blur >= 40px）收敛到 --xq-shadow-lg
import fs from 'node:fs'

const FILE = 'src/assets/main.css'
let css = fs.readFileSync(FILE, 'utf8')
const stat = { radial: 0, blank: 0, backdrop: 0, radius: 0, shadow: 0 }

/** 按顶层逗号切分渐变层，括号内的逗号不算分隔符 */
const splitLayers = (value) => {
  const parts = []
  let depth = 0
  let current = ''
  for (const ch of value) {
    if (ch === '(') depth += 1
    else if (ch === ')') depth -= 1
    if (ch === ',' && depth === 0) {
      parts.push(current)
      current = ''
    } else {
      current += ch
    }
  }
  parts.push(current)
  return parts.map((p) => p.trim()).filter(Boolean)
}

// ---- 1. background / background-image 去掉 radial-gradient 层 ----
css = css.replace(
  /(\n[ \t]*)(background(?:-image)?)\s*:\s*([^;{}]*?);/g,
  (match, indent, prop, rawValue) => {
    if (!/radial-gradient/i.test(rawValue)) return match
    let value = rawValue
    let important = ''
    if (/!important\s*$/i.test(value)) {
      important = ' !important'
      value = value.replace(/!important\s*$/i, '')
    }
    const kept = splitLayers(value).filter((layer) => !/^radial-gradient\s*\(/i.test(layer))
    stat.radial += splitLayers(value).length - kept.length
    if (kept.length === 0) {
      stat.blank += 1
      return `${indent}${prop}: var(--xq-surface)${important};`
    }
    if (kept.length === 1) return `${indent}${prop}: ${kept[0]}${important};`
    return `${indent}${prop}:${kept.map((l) => `${indent}  ${l}`).join(',')}${important};`
  },
)

// ---- 2. 整行删除磨砂滤镜 ----
css = css.replace(/\n[ \t]*(?:-webkit-)?backdrop-filter\s*:[^;{}]*;/g, () => {
  stat.backdrop += 1
  return ''
})

// ---- 3. 过大圆角收敛 ----
css = css.replace(/border-radius\s*:\s*(\d{2,})px/g, (match, px) => {
  const size = Number(px)
  if (size < 20) return match
  stat.radius += 1
  return `border-radius: var(--xq-radius-${size >= 24 ? 'xl' : 'lg'})`
})

// ---- 4. 超大扩散投影收敛 ----
css = css.replace(/box-shadow\s*:\s*([^;{}]*?);/g, (match, value) => {
  if (/inset|var\(--xq-shadow|var\(--xq-ring/.test(value)) return match
  const blurs = [...value.matchAll(/(\d{2,})px/g)].map((m) => Number(m[1]))
  if (!blurs.some((b) => b >= 40)) return match
  stat.shadow += 1
  return `box-shadow: var(--xq-shadow-lg);`
})

fs.writeFileSync(FILE, css)
console.log('删除径向渐变层:', stat.radial)
console.log('渐变清空后回落纯色:', stat.blank)
console.log('删除 backdrop-filter:', stat.backdrop)
console.log('圆角收敛:', stat.radius)
console.log('投影收敛:', stat.shadow)

// 括号平衡校验
let depth = 0
let bad = []
css.split('\n').forEach((line, i) => {
  for (const ch of line) {
    if (ch === '{') depth += 1
    else if (ch === '}') {
      depth -= 1
      if (depth < 0) bad.push(i + 1)
    }
  }
})
console.log('最终括号深度:', depth, '| 异常闭合行:', bad)
