// AIMETA P=日期工具_日期格式化函数|R=日期格式化_相对时间|NR=不含业务逻辑|E=formatDate|X=internal|A=formatDate函数|D=none|S=none|RD=./README.ai
/**
 * 日期时间格式化工具函数
 *
 * 具体的年月日排布交给 useLocale：中文走 zh-CN，英文走 en-US，
 * 这里只负责空值与非法输入的兜底。
 */
import {
  formatDate as formatLocaleDate,
  formatDateTime as formatLocaleDateTime,
  pick,
} from '@/composables/useLocale'

const EMPTY = '-'

/**
 * 将 ISO 8601 格式的时间字符串按当前界面语言格式化到分钟精度
 * @param isoString ISO 8601 格式的时间字符串，如 "2026-01-11T09:42:54.539359"
 * @returns 中文如 "2026/01/11 09:42"，英文如 "01/11/2026, 09:42 AM"
 */
export function formatDateTime(isoString: string | null | undefined): string {
  if (!isoString) return EMPTY
  return formatLocaleDateTime(isoString) || isoString
}

/**
 * 将 ISO 8601 格式的时间字符串按当前界面语言格式化为仅日期
 * @param isoString ISO 8601 格式的时间字符串
 */
export function formatDate(isoString: string | null | undefined): string {
  if (!isoString) return EMPTY
  return formatLocaleDate(isoString) || isoString
}

/**
 * 将 ISO 8601 格式的时间字符串转换为相对时间描述
 * @param isoString ISO 8601 格式的时间字符串
 * @returns 相对时间描述，如 "刚刚"、"5分钟前"、"2小时前"、"3天前"
 */
export function formatRelativeTime(isoString: string | null | undefined): string {
  if (!isoString) return EMPTY

  const date = new Date(isoString)
  if (Number.isNaN(date.getTime())) return isoString

  const diffMs = Date.now() - date.getTime()
  const diffSeconds = Math.floor(diffMs / 1000)
  const diffMinutes = Math.floor(diffSeconds / 60)
  const diffHours = Math.floor(diffMinutes / 60)
  const diffDays = Math.floor(diffHours / 24)

  if (diffSeconds < 60) return pick('刚刚', 'just now')
  if (diffMinutes < 60) return pick(`${diffMinutes}分钟前`, `${diffMinutes} min ago`)
  if (diffHours < 24) return pick(`${diffHours}小时前`, `${diffHours} h ago`)
  if (diffDays < 7) return pick(`${diffDays}天前`, `${diffDays} d ago`)
  return formatDateTime(isoString)
}
