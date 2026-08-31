// 把半透明背景改成实色令牌：半透明层层叠加是"画面发灰、颜色乱"的直接原因。
// 只处理 background / background-color，不动 border/shadow/overlay 的透明度语义。
import fs from 'node:fs'

const FILE = 'src/assets/main.css'
let css = fs.readFileSync(FILE, 'utf8')
let count = 0

const RULES = [
  // 半透明白 -> 纯白表面
  [/rgba\(\s*255\s*,\s*255\s*,\s*255\s*,\s*[\d.]+\s*\)/gi, 'var(--xq-surface)'],
  // 半透明表面色 -> 次级表面
  [/rgba\(\s*var\(--xq-surface-rgb\)\s*,\s*[\d.]+\s*\)/gi, 'var(--xq-surface-2)'],
  // 极淡墨 -> 下沉底色；中等墨 -> 遮罩令牌
  [/rgba\(\s*var\(--xq-ink-rgb\)\s*,\s*0?\.0[0-9]+\s*\)/gi, 'var(--xq-bg-sunken)'],
  [/rgba\(\s*var\(--xq-ink-rgb\)\s*,\s*0?\.[3-9][0-9]*\s*\)/gi, 'var(--xq-overlay)'],
  // 淡灰底 / 淡灰 hover
  [/rgba\(\s*var\(--xq-muted-rgb\)\s*,\s*0?\.0[0-9]+\s*\)/gi, 'var(--xq-surface-2)'],
  [/rgba\(\s*var\(--xq-muted-rgb\)\s*,\s*0?\.1[0-9]*\s*\)/gi, 'var(--xq-surface-3)'],
  // 淡强调底 -> 强调 soft
  [/rgba\(\s*var\(--xq-accent-rgb\)\s*,\s*0?\.[01][0-9]*\s*\)/gi, 'var(--xq-accent-soft)'],
]

css = css.replace(/(background(?:-color)?\s*:\s*)([^;{}]*?)(;)/g, (match, head, value, tail) => {
  let next = value
  for (const [pattern, replacement] of RULES) next = next.replace(pattern, replacement)
  if (next === value) return match
  count += 1
  return head + next + tail
})

fs.writeFileSync(FILE, css)
console.log('半透明背景改为实色:', count)
console.log('残留半透明背景:', (css.match(/background(?:-color)?\s*:\s*[^;{}]*rgba/g) || []).length)
