// 把大面积线性渐变背景收敛为纯色：渐变本身是"颜色乱、画面脏"的主要来源。
// 规则：单层 linear-gradient 的 background 取其第一个颜色停靠点作为纯色；
// 多层声明留给人工判断（数量极少），此处跳过。
import fs from 'node:fs'

const FILE = 'src/assets/main.css'
let css = fs.readFileSync(FILE, 'utf8')
let flattened = 0
const skipped = []

/** 从渐变参数里取第一个颜色值（跳过角度/方向关键字） */
const firstColor = (args) => {
  const parts = []
  let depth = 0
  let current = ''
  for (const ch of args) {
    if (ch === '(') depth += 1
    else if (ch === ')') depth -= 1
    if (ch === ',' && depth === 0) {
      parts.push(current.trim())
      current = ''
    } else {
      current += ch
    }
  }
  parts.push(current.trim())
  for (const part of parts) {
    if (/^(-?\d+(\.\d+)?(deg|turn|rad)|to\s+|circle|ellipse|at\s+|closest|farthest)/i.test(part)) continue
    // 去掉尾部的位置百分比 / 长度
    return part.replace(/\s+(-?[\d.]+(%|px|rem|em)\s*)+$/i, '').trim()
  }
  return null
}

css = css.replace(/(\n[ \t]*)background\s*:\s*([^;{}]*?);/g, (match, indent, rawValue) => {
  if (!/linear-gradient/i.test(rawValue)) return match
  let value = rawValue.trim()
  let important = ''
  if (/!important$/i.test(value)) {
    important = ' !important'
    value = value.replace(/!important$/i, '').trim()
  }
  const single = value.match(/^(?:repeating-)?linear-gradient\s*\(([\s\S]*)\)$/i)
  if (!single) {
    skipped.push(value.slice(0, 70).replace(/\s+/g, ' '))
    return match
  }
  const color = firstColor(single[1])
  if (!color) {
    skipped.push(value.slice(0, 70).replace(/\s+/g, ' '))
    return match
  }
  flattened += 1
  return `${indent}background: ${color}${important};`
})

fs.writeFileSync(FILE, css)
console.log('渐变压平为纯色:', flattened)
console.log('需人工处理的多层声明:', skipped.length)
skipped.forEach((s) => console.log('  · ' + s))
