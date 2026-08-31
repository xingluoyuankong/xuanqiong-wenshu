/**
 * 审计「用户可见但未走 pick()/t() 的裸中文」。
 *
 * 判定逻辑（保守，宁可漏报不误报）：
 *  - 只看 <template> 与 <script> 段，跳过 <style> 与各类注释；
 *  - 跳过本行已出现 pick( / t( 的行；
 *  - 跳过多行 pick( 调用的续行（前一行以 pick( 结尾）；
 *  - 跳过纯 ASCII 行。
 * 输出按「模板命中数」排序，模板文案对用户最直接可见。
 */
import { readFileSync } from 'node:fs'
import { globSync } from 'node:fs'
import { execSync } from 'node:child_process'

const CJK = /[一-鿿]/
const SKIP_FILES = [
  'src/composables/useLocale.ts', // 词表真源，中文是数据不是硬编码
  'src/composables/useLocale.spec.ts',
]

const files = execSync('git ls-files "src/**/*.vue" "src/**/*.ts"', { encoding: 'utf8' })
  .split('\n')
  .map((line) => line.trim().replace(/^frontend\//, ''))
  .filter(Boolean)
  .filter((file) => !file.endsWith('.spec.ts'))
  .filter((file) => !file.includes('_deprecated/'))
  .filter((file) => !SKIP_FILES.includes(file))

const isCommentLine = (line) => {
  const text = line.trim()
  return (
    text.startsWith('//') ||
    text.startsWith('/*') ||
    text.startsWith('*') ||
    text.startsWith('<!--') ||
    text.startsWith('#')
  )
}

const report = []
const unzoned = []

for (const file of files) {
  let source
  try {
    // 仓库里有一批 .vue 带 UTF-8 BOM，不剥掉会让顶格块标签匹配失败，整段模板被判成 unknown。
    // 下面正则里行首那个不可见字符就是 BOM（U+FEFF），不要误删。
    source = readFileSync(file, 'utf8').replace(/^﻿/, '')
  } catch {
    continue
  }

  const lines = source.split('\n')
  // 标记每行所属区段：template / script / style
  // SFC 顶层块标签一定顶格书写；带缩进的 <template #slot> / </template> 是模板内部插槽，不能参与分区，
  // 否则第一个插槽闭合就会把后面整段模板误判成 unknown 而漏检。
  const zones = new Array(lines.length).fill(file.endsWith('.ts') ? 'script' : 'unknown')
  if (!file.endsWith('.ts')) {
    let zone = 'unknown'
    lines.forEach((line, index) => {
      if (/^<template[\s>]/.test(line)) zone = 'template'
      else if (/^<script[\s>]/.test(line)) zone = 'script'
      else if (/^<style[\s>]/.test(line)) zone = 'style'
      zones[index] = zone
      if (/^<\/(template|script|style)>/.test(line)) zone = 'unknown'
    })
    // 分区完全失效（一行都没落进 template/script）说明块标签写法超出预期，必须显式暴露而不是静默漏检
    if (!zones.some((zone) => zone === 'template' || zone === 'script')) unzoned.push(file)
  }

  const hits = { template: [], script: [] }
  let inBlockComment = false

  lines.forEach((line, index) => {
    const zone = zones[index]
    if (zone !== 'template' && zone !== 'script') return

    // 粗略跟踪块注释 / HTML 注释
    if (/\/\*/.test(line) && !/\*\//.test(line)) inBlockComment = true
    const wasInComment = inBlockComment
    if (/\*\//.test(line)) inBlockComment = false
    if (wasInComment) return
    if (isCommentLine(line)) return
    if (!CJK.test(line)) return
    if (/pick\(|[^\w.]t\(|\bt\(/.test(line)) return

    const prev = (lines[index - 1] || '').trim()
    // 多行 pick( 的续行
    if (/pick\($/.test(prev) || /pick\(\s*$/.test(prev)) return
    // HTML 注释单行
    if (/<!--[\s\S]*-->/.test(line) && !CJK.test(line.replace(/<!--[\s\S]*-->/g, ''))) return

    hits[zone].push({ line: index + 1, text: line.trim().slice(0, 96) })
  })

  const total = hits.template.length + hits.script.length
  if (total > 0) report.push({ file, total, ...hits })
}

report.sort((a, b) => b.template.length - a.template.length || b.total - a.total)

const templateTotal = report.reduce((sum, item) => sum + item.template.length, 0)
const scriptTotal = report.reduce((sum, item) => sum + item.script.length, 0)

console.log(`扫描文件: ${files.length}`)
console.log(`命中文件: ${report.length}`)
console.log(`模板裸中文: ${templateTotal} 行（用户直接可见）`)
console.log(`脚本裸中文: ${scriptTotal} 行`)
if (unzoned.length) {
  console.log('')
  console.log(`⚠ 分区失效（未扫描）: ${unzoned.length} 个文件`)
  for (const file of unzoned) console.log(`    ${file}`)
}
console.log('')

const detail = process.argv.includes('--detail')
const limit = detail ? report.length : 30

for (const item of report.slice(0, limit)) {
  console.log(`${String(item.template.length).padStart(4)} tpl / ${String(item.script.length).padStart(4)} js  ${item.file}`)
  if (detail) {
    for (const hit of [...item.template, ...item.script]) {
      console.log(`        ${hit.line}: ${hit.text}`)
    }
  }
}
