// 投影令牌化：层次优先靠 1px 描边，投影只保留极轻的三档。
// blur >= 24px 的"浮空大投影"是页面显脏的主因之一，一律降到 --xq-shadow-md/sm。
import fs from 'node:fs'

const FILE = 'src/assets/main.css'
let css = fs.readFileSync(FILE, 'utf8')
let count = 0

css = css.replace(/box-shadow\s*:\s*([^;{}]*?)(\s*!important)?;/g, (match, value, important) => {
  if (!/rgba\(/.test(value)) return match
  if (/^var\(--xq-shadow/.test(value.trim())) return match
  // 纯 inset 高光：直接删掉，白色内阴影在浅色界面上只增加毛边
  if (/^inset/i.test(value.trim()) && !/,\s*0/.test(value)) {
    count += 1
    return 'box-shadow: none' + (important || '') + ';'
  }
  const blurs = [...value.matchAll(/(\d+)px/g)].map((m) => Number(m[1]))
  const maxBlur = blurs.length ? Math.max(...blurs) : 0
  let token = 'var(--xq-shadow-sm)'
  if (maxBlur >= 24) token = 'var(--xq-shadow-md)'
  else if (maxBlur <= 8) token = 'var(--xq-shadow-xs)'
  count += 1
  return `box-shadow: ${token}${important || ''};`
})

fs.writeFileSync(FILE, css)
console.log('投影令牌化:', count)
console.log('残留非令牌投影:', (css.match(/box-shadow\s*:\s*[^;{}]*rgba/g) || []).length)

let depth = 0
const bad = []
css.split('\n').forEach((line, i) => {
  for (const ch of line) {
    if (ch === '{') depth += 1
    else if (ch === '}') {
      depth -= 1
      if (depth < 0) bad.push(i + 1)
    }
  }
})
console.log('括号深度:', depth, '| 异常闭合:', bad)
