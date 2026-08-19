import { computed, ref } from 'vue'

/**
 * 全站双语基础设施（简体中文 / English）。
 *
 * 两种用法，按场景选择：
 * 1) pick(中文, English)   —— 就地二选一，适合一次性、强上下文的短文案（历史代码大量在用，长期保留）。
 * 2) t('common.cancel')    —— 走集中词表，适合跨组件复用的通用词条；key 缺失时原样返回 key，便于排查。
 *
 * ────────────────── 术语表（English 侧必须统一，禁止同义词漂移）──────────────────
 * 章节 Chapter            | 大纲 Outline           | 伏笔 Foreshadowing
 * 世界观 World setting    | 人物 Characters        | 版本 Version
 * 候选稿 Candidate        | 评审 Review            | 一致性 / 连续性 Continuity
 * 风格 Style              | 灵感 Inspiration       | 蓝图 Blueprint
 * 写作台 Writing desk     | 正文 Draft / Body      | 字数 Word count
 * 生成 Generate           | 优化 Optimize          | 终止 Stop
 * 重新生成 Regenerate     | 记忆 Memory            | 技能 Skill
 * 提示词 Prompt           | 令牌预算 Token budget  | 补丁 Patch
 * 差异对比 Diff           | 评分 Score             | 维度 Dimension
 * 场景 Scene              | 节奏 Pacing            | 情节 Plot
 * ──────────────────────────────────────────────────────────────────────────────
 */

export type LocaleCode = 'zh-CN' | 'en-US'

const STORAGE_KEY = 'xuanqiong_wenshu_locale'
const SUPPORTED_LOCALES: readonly LocaleCode[] = ['zh-CN', 'en-US']
/** <html lang> 取值：中文用 zh-CN，英文用更通用的 en */
const HTML_LANG: Record<LocaleCode, string> = { 'zh-CN': 'zh-CN', 'en-US': 'en' }
/** Intl 使用的区域标识 */
const INTL_LOCALE: Record<LocaleCode, string> = { 'zh-CN': 'zh-CN', 'en-US': 'en-US' }

/** 读取本地存储；非法值（含空串、旧版遗留值）一律回落中文 */
function readStoredLocale(): LocaleCode {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return SUPPORTED_LOCALES.includes(raw as LocaleCode) ? (raw as LocaleCode) : 'zh-CN'
  } catch {
    return 'zh-CN'
  }
}

/** 同步 <html lang>，让浏览器断词、朗读、拼写检查跟随界面语言 */
function syncDocumentLang(value: LocaleCode) {
  if (typeof document === 'undefined') return
  document.documentElement.lang = HTML_LANG[value]
}

const localeState = ref<LocaleCode>(readStoredLocale())
syncDocumentLang(localeState.value)

/** 中文词表即 key 的唯一真源；英文词表被类型强制补齐，漏译会直接编译报错 */
const zhMessages = {
  'locale.language': '中文',
  'locale.switch': '切换到英文',

  'common.confirm': '确定',
  'common.cancel': '取消',
  'common.close': '关闭',
  'common.save': '保存',
  'common.saving': '保存中…',
  'common.delete': '删除',
  'common.edit': '编辑',
  'common.apply': '应用',
  'common.reset': '重置',
  'common.retry': '重试',
  'common.refresh': '刷新',
  'common.loading': '加载中…',
  'common.empty': '暂无数据',
  'common.failed': '失败',
  'common.error': '错误',
  'common.success': '成功',
  'common.tip': '提示',
  'common.expand': '展开',
  'common.collapse': '收起',
  'common.more': '更多',
  'common.copy': '复制',
  'common.copied': '已复制',
  'common.copyFailed': '复制失败',
  'common.unknown': '未知',
  'common.processing': '处理中',
  'common.pending': '等待中',
  'common.done': '已完成',
  'common.stop': '终止',
  'common.generate': '生成',
  'common.generating': '生成中…',
  'common.regenerate': '重新生成',
  'common.optimize': '优化',
  'common.search': '搜索',
  'common.clear': '清空',
  'common.selectAll': '全选',
  'common.none': '无',
  'common.optional': '可选',
  'common.total': '合计',
  'common.enabled': '已启用',
  'common.disabled': '已停用',

  'term.chapter': '章节',
  'term.outline': '大纲',
  'term.foreshadowing': '伏笔',
  'term.worldSetting': '世界观',
  'term.characters': '人物',
  'term.version': '版本',
  'term.candidate': '候选稿',
  'term.review': '评审',
  'term.continuity': '连续性',
  'term.style': '风格',
  'term.inspiration': '灵感',
  'term.blueprint': '蓝图',
  'term.writingDesk': '写作台',
  'term.draft': '正文',
  'term.wordCount': '字数',
  'term.memory': '记忆',
  'term.skill': '技能',
  'term.prompt': '提示词',
  'term.tokenBudget': '令牌预算',
  'term.patch': '补丁',
  'term.diff': '差异对比',
  'term.score': '评分',
} as const

export type MessageKey = keyof typeof zhMessages

const enMessages: Record<MessageKey, string> = {
  'locale.language': 'English',
  'locale.switch': 'Switch to Chinese',

  'common.confirm': 'Confirm',
  'common.cancel': 'Cancel',
  'common.close': 'Close',
  'common.save': 'Save',
  'common.saving': 'Saving…',
  'common.delete': 'Delete',
  'common.edit': 'Edit',
  'common.apply': 'Apply',
  'common.reset': 'Reset',
  'common.retry': 'Retry',
  'common.refresh': 'Refresh',
  'common.loading': 'Loading…',
  'common.empty': 'Nothing here yet',
  'common.failed': 'Failed',
  'common.error': 'Error',
  'common.success': 'Success',
  'common.tip': 'Tip',
  'common.expand': 'Expand',
  'common.collapse': 'Collapse',
  'common.more': 'More',
  'common.copy': 'Copy',
  'common.copied': 'Copied',
  'common.copyFailed': 'Copy failed',
  'common.unknown': 'Unknown',
  'common.processing': 'In progress',
  'common.pending': 'Pending',
  'common.done': 'Done',
  'common.stop': 'Stop',
  'common.generate': 'Generate',
  'common.generating': 'Generating…',
  'common.regenerate': 'Regenerate',
  'common.optimize': 'Optimize',
  'common.search': 'Search',
  'common.clear': 'Clear',
  'common.selectAll': 'Select all',
  'common.none': 'None',
  'common.optional': 'Optional',
  'common.total': 'Total',
  'common.enabled': 'Enabled',
  'common.disabled': 'Disabled',

  'term.chapter': 'Chapter',
  'term.outline': 'Outline',
  'term.foreshadowing': 'Foreshadowing',
  'term.worldSetting': 'World setting',
  'term.characters': 'Characters',
  'term.version': 'Version',
  'term.candidate': 'Candidate',
  'term.review': 'Review',
  'term.continuity': 'Continuity',
  'term.style': 'Style',
  'term.inspiration': 'Inspiration',
  'term.blueprint': 'Blueprint',
  'term.writingDesk': 'Writing desk',
  'term.draft': 'Draft',
  'term.wordCount': 'Word count',
  'term.memory': 'Memory',
  'term.skill': 'Skill',
  'term.prompt': 'Prompt',
  'term.tokenBudget': 'Token budget',
  'term.patch': 'Patch',
  'term.diff': 'Diff',
  'term.score': 'Score',
}

const messages: Record<LocaleCode, Record<string, string>> = {
  'zh-CN': zhMessages,
  'en-US': enMessages,
}

export function setLocale(value: LocaleCode) {
  const next: LocaleCode = SUPPORTED_LOCALES.includes(value) ? value : 'zh-CN'
  localeState.value = next
  syncDocumentLang(next)
  try {
    localStorage.setItem(STORAGE_KEY, next)
  } catch {
    // 隐私模式下 localStorage 可能不可写，此时只保留内存状态
  }
}

export function toggleLocale() {
  setLocale(localeState.value === 'zh-CN' ? 'en-US' : 'zh-CN')
}

/** 就地二选一 */
export function pick<T>(zh: T, en: T): T {
  return localeState.value === 'zh-CN' ? zh : en
}

/** 查词表；当前语言缺失时退回中文，中文也没有则原样返回 key */
export function t(key: MessageKey | (string & {}), params?: Record<string, string | number>): string {
  const raw = messages[localeState.value][key] ?? messages['zh-CN'][key] ?? key
  if (!params) return raw
  return raw.replace(/\{(\w+)\}/g, (matched, name: string) =>
    Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : matched,
  )
}

/** 千分位数字 */
export function formatNumber(value: number): string {
  if (!Number.isFinite(value)) return '0'
  return value.toLocaleString(INTL_LOCALE[localeState.value])
}

function toDate(value: Date | string | number): Date | null {
  const date = value instanceof Date ? value : new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

/** 本地化日期；非法输入返回空串 */
export function formatDate(value: Date | string | number): string {
  const date = toDate(value)
  if (!date) return ''
  return date.toLocaleDateString(INTL_LOCALE[localeState.value], {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })
}

/** 本地化日期 + 时间（分钟精度）；非法输入返回空串 */
export function formatDateTime(value: Date | string | number): string {
  const date = toDate(value)
  if (!date) return ''
  return date.toLocaleString(INTL_LOCALE[localeState.value], {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** 字数单位：中文「1,234 字」/ 英文「1,234 words」 */
export function formatWords(value: number): string {
  const count = Number.isFinite(value) ? Math.round(value) : 0
  const text = formatNumber(count)
  if (localeState.value === 'zh-CN') return `${text} 字`
  return `${text} ${Math.abs(count) === 1 ? 'word' : 'words'}`
}

/** 中英标点差异；用 getter 保证语言切换后模板能重新求值 */
export const punct = {
  get colon() {
    return localeState.value === 'zh-CN' ? '：' : ': '
  },
  get comma() {
    return localeState.value === 'zh-CN' ? '、' : ', '
  },
  get period() {
    return localeState.value === 'zh-CN' ? '。' : '. '
  },
  /** 括号包裹：中文「（x）」/ 英文「 (x)」（英文自带前导空格，便于紧跟上文） */
  paren(text: string | number) {
    return localeState.value === 'zh-CN' ? `（${text}）` : ` (${text})`
  },
}

const localeRef = computed(() => localeState.value)
const isChineseRef = computed(() => localeState.value === 'zh-CN')
const languageLabelRef = computed(() => t('locale.language'))
const switchLabelRef = computed(() => t('locale.switch'))

export function useLocale() {
  return {
    locale: localeRef,
    isChinese: isChineseRef,
    languageLabel: languageLabelRef,
    switchLabel: switchLabelRef,
    setLocale,
    toggleLocale,
    pick,
    t,
    formatNumber,
    formatDate,
    formatDateTime,
    formatWords,
    punct,
  }
}
