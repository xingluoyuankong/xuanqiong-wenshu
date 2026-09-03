# 前端重构共享规范（所有并行 agent 必读）

## 背景
项目：`D:\小说写作\xuanqiong-wenshu`，Vue 3 + TS + Vite + Pinia + naive-ui，小说生成工具「玄穹文枢」。
用户对生成界面的评价：**风格奇丑、颜色乱、排版留白乱、眼花缭乱、抓不住重点**。本轮做全面视觉与交互重构。

根因（已确认）：
1. 曾并存 3 套设计令牌（`--md-*` Material 淡蓝灰 + `--xq-*` 中式色名却填蓝值 + 组件内硬编码 hex），互相冲突。
2. 全局 body 字体是装饰性楷体 `ZCOOL XiaoWei`，圆角高达 26-32px，低对比度柔色，整体软塌无层次。
3. 历次改动只往文件尾部追加覆盖，`main.css` 里同一选择器重复定义 10-19 次，组件 `<style>` 里同一类定义 2-3 次、同名 `@keyframes` 定义 3 次、还用 `!important` 自我覆盖。

## 设计令牌（唯一真源，已就位）
`frontend/src/shared/styles/tokens.css` —— **动手前先完整读一遍**。`--md-*` 现已全部是指向 `--xq-*` 的兼容别名。

### 铁律
- `<style>` 内**禁止**任何硬编码颜色（hex / rgb / rgba / hsl / 颜色关键字）。一律 `var(--xq-…)`。
- 强调色全站唯一：`--xq-accent`（靛蓝 #4f46e5）。禁止引入第二品牌色。
- 语义色（success / warning / danger / info）只用于状态点、徽标文字、1px 细边框、3px 左侧条。**禁止大面积背景填充**。
- 字号只用 `--xq-text-*`：界面主体 13–15px，标题 17–24px。
- 间距只用 `--xq-space-*`（4pt 栅格）。禁止 7px / 9px / 10px 这类随手值。
- 圆角只用 `--xq-radius-*`（4 / 6 / 8 / 12 / 16 / pill）。
- 阴影只用 `--xq-shadow-*`。层次优先靠 1px `--xq-border` 描边，而非投影。
- 字体：界面 `var(--xq-font-sans)`；**仅**小说正文阅读区可用 `var(--xq-font-serif)`。绝不使用 ZCOOL XiaoWei / 楷体 / STKaiti。

## 视觉方向
现代、克制、留白充分、层次清晰（参照 Linear / Notion / Vercel 的信息密度控制）：
- **一屏只允许一个视觉焦点。** 次要信息降级为小字灰色，或收进可折叠区。
- 卡片：白底 + 1px 描边 + 12px 圆角 + 极轻阴影。**不要**渐变背景、不要 `backdrop-filter` 磨砂堆叠、不要多重径向渐变、不要纸纹网格。
- 按钮严格三级：主操作（accent 实心，**一屏最多 1 个**）/ 次操作（白底 + 描边）/ 弱操作（纯文字）。图标按钮统一 28 或 32px 见方。
- 同区块元素对齐同一栅格；卡片内边距统一 16px 或 20px，**不要 8 / 10 / 12px 混用**。
- 状态徽标统一形态：pill、11–12px、soft 背景 + 同色系文字 + 1px 同色系边框。
- 数字（百分比、字数、耗时）加 `font-variant-numeric: tabular-nums` 防抖动。
- 尊重 `prefers-reduced-motion`。

## 代码铁律
- **只改分配给你的文件**，绝不碰其他文件 —— 有多个 agent 正在并行改动，越界会造成冲突。
- `<style scoped>` 必须**重写而非追加**：一个选择器只出现一次，一个 `@keyframes` 只定义一次，禁止用 `!important` 覆盖自己写的规则。
- 所有面向用户的文案必须走 `useLocale` 的 `pick(中文, English)`，**不允许裸中文字符串**。容易漏的地方：`aria-label`、`placeholder`、`title`、alert / confirm 文案、`Record<string,string>` 标签表的值、`|| '处理中'` 这类兜底串、单位（"字" vs " chars"）、标点（"：" vs ": "、"、" vs ", "）。
- 注释用中文。
- 保持 `<script setup>` 现有 props / emits 契约不变，除非任务明确要求扩展。
- **不新增 npm 依赖。**
- 收工前自检：`cd frontend && npx vitest run <你改动涉及的 spec>`，并确认 `npx vue-tsc --build` 没有新增与你文件相关的类型错误。

## 跨 agent 共享契约（不可改签名）

### PixelMascot 组件
```vue
import PixelMascot from '@/components/shared/PixelMascot.vue'
<PixelMascot :mascot-id="mascotId" :color="color" :size="32" :moving="true" />
```
props：`mascotId?: PixelMascotId`（默认 `'cat'`）、`color?: string`、`size?: number`、`moving?: boolean`（默认 `true`）

### usePixelMascot composable
```ts
import { usePixelMascot, PIXEL_MASCOTS } from '@/composables/usePixelMascot'
const { mascot, mascotId, color, setMascot, setColor } = usePixelMascot()
```

### useLocale composable
```ts
import { useLocale } from '@/composables/useLocale'
const { pick, locale, isChinese, setLocale, toggleLocale } = useLocale()
```

## 交付要求
改完后用一段中文说明：改了哪些文件、每个文件的核心变化、测试结果、以及你发现但**不在你范围内**的问题（附文件与行号）。
