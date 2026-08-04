// AIMETA P=进度消息配置_有趣的等待提示|R=进度条消息_加载动画|NR=不含业务逻辑|E=progressMessages|X=internal|A=进度提示配置|D=none|S=none|RD=./README.ai
// 为小说生成过程中的各个阶段提供有趣、易懂的进度提示

/** 各阶段的有趣进度消息 */
export const PROGRESS_MESSAGES: Record<string, string[]> = {
  queued: [
    "📝 正在排队等待灵感降临...",
    "☕ 作家正在喝咖啡准备创作...",
    "🎭 角色们正在后台准备登场...",
    "🎪 故事舞台正在搭建中...",
  ],
  prepare_context: [
    "🧠 正在整理故事记忆...",
    "📚 回顾前文章节中...",
    "🔍 分析角色关系网...",
    "🗺️ 梳理故事时间线...",
  ],
  history_context: [
    "📖 重温前情提要...",
    "🧩 拼接故事碎片中...",
    "🔗 连接剧情线索...",
  ],
  generate_mission: [
    "🎯 正在制定本章创作目标...",
    "✨ 灵感火花正在碰撞...",
    "📋 规划故事走向中...",
    "🖊️ 构思章节大纲中...",
  ],
  generate_variants: [
    "✍️ 作家正在奋笔疾书...",
    "📖 故事正在流淌出来...",
    "🎨 文字正在编织成篇...",
    "💡 创意正在涌现...",
    "🌟 灵感如泉涌...",
    "📝 妙笔生花中...",
  ],
  ai_review: [
    "🔍 AI编辑正在审阅稿件...",
    "📝 正在评估故事质量...",
    "🎯 检查剧情逻辑中...",
    "⚖️ 衡量文字魅力中...",
  ],
  consistency: [
    "🔗 正在检查前后文一致性...",
    "🧩 拼接故事碎片中...",
    "📖 确保角色不OOC...",
    "🕸️ 维护剧情逻辑网...",
  ],
  continuity_gate: [
    "🚪 通过连续性检查站...",
    "✅ 验证前后呼应中...",
    "🎯 确保伏笔连贯...",
  ],
  finalize: [
    "📚 正在更新故事账本...",
    "💾 保存角色状态中...",
    "🎬 为下一章埋下伏笔...",
    "🏁 完成最终润色...",
  ],
  ledger_memory: [
    "🧠 更新角色记忆中...",
    "📖 记录故事轨迹...",
    "💎 沉淀故事精华...",
  ],
}

/** 加载动画帧 */
export const LOADING_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

/** 卡通小人动画帧 */
export const STICKMAN_FRAMES = ["🚶", "🏃", "🤸", "💪", "🎯"]

/** 等待时显示的小知识 */
export const WRITING_TIPS = [
  "💡 好的对话能让角色活起来",
  "🎭 冲突是故事的灵魂",
  "📖 每个章节都应该有转折",
  "✨ 细节决定成败",
  "🔥 悬念是抓住读者的利器",
  "🌟 角色要有成长弧线",
  "💎 好故事需要反复打磨",
  "🎪 意外是最好的礼物",
  "🎯 章末钩子是留住读者的关键",
  "💫 感官描写让场景更生动",
  "🎨 文风要与故事基调匹配",
  "⚡ 节奏张弛有度才精彩",
]

/**
 * 获取指定阶段的随机进度消息
 * @param stage 当前阶段标识
 * @returns 随机选择的进度消息
 */
export function getProgressMessage(stage: string): string {
  const messages = PROGRESS_MESSAGES[stage]
  if (!messages || messages.length === 0) {
    return "⏳ 正在处理中..."
  }
  return messages[Math.floor(Math.random() * messages.length)]
}

/**
 * 获取随机写作小知识
 * @returns 随机写作建议
 */
export function getRandomTip(): string {
  return WRITING_TIPS[Math.floor(Math.random() * WRITING_TIPS.length)]
}

/**
 * 获取加载动画帧
 * @param frameIndex 帧索引
 * @returns 动画字符
 */
export function getLoadingFrame(frameIndex: number): string {
  return LOADING_FRAMES[frameIndex % LOADING_FRAMES.length]
}

/**
 * 获取卡通小人帧
 * @param frameIndex 帧索引
 * @returns 小人动画字符
 */
export function getStickmanFrame(frameIndex: number): string {
  return STICKMAN_FRAMES[frameIndex % STICKMAN_FRAMES.length]
}

/**
 * 格式化等待时间
 * @param seconds 秒数
 * @returns 格式化的时间字符串
 */
export function formatWaitTime(seconds: number): string {
  if (seconds <= 0) return "即将完成"
  if (seconds < 60) return `${seconds}秒`
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = seconds % 60
  if (remainingSeconds === 0) return `${minutes}分钟`
  return `${minutes}分${remainingSeconds}秒`
}

/**
 * 生成进度条字符串
 * @param percent 进度百分比 (0-100)
 * @param length 进度条长度
 * @returns 进度条字符串
 */
export function generateProgressBar(percent: number, length = 20): string {
  const filled = Math.round((percent / 100) * length)
  const empty = length - filled
  return "█".repeat(filled) + "░".repeat(empty)
}
