import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useLocale } from './useLocale'

const STORAGE_KEY = 'xuanqiong_wenshu_locale'

/** 重新加载模块，用于验证「模块初始化阶段」的读取与回落逻辑 */
async function loadFresh() {
  vi.resetModules()
  return await import('./useLocale')
}

describe('useLocale', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    // 模块级单例状态，测试之间必须复位，避免相互污染
    useLocale().setLocale('zh-CN')
    localStorage.clear()
  })

  describe('初始化', () => {
    it('无存储值时默认中文，并同步 <html lang>', async () => {
      const mod = await loadFresh()
      expect(mod.useLocale().locale.value).toBe('zh-CN')
      expect(document.documentElement.lang).toBe('zh-CN')
    })

    it('存储值合法时按存储恢复，英文的 lang 为 en', async () => {
      localStorage.setItem(STORAGE_KEY, 'en-US')
      const mod = await loadFresh()
      expect(mod.useLocale().locale.value).toBe('en-US')
      expect(mod.useLocale().isChinese.value).toBe(false)
      expect(document.documentElement.lang).toBe('en')
    })

    it.each(['fr-FR', 'zh', '', 'null', '{}'])('存储的非法值 %s 回落中文', async (bad) => {
      localStorage.setItem(STORAGE_KEY, bad)
      const mod = await loadFresh()
      expect(mod.useLocale().locale.value).toBe('zh-CN')
      expect(document.documentElement.lang).toBe('zh-CN')
    })
  })

  describe('切换语言', () => {
    it('setLocale 写入存储并同步 <html lang>', () => {
      const { setLocale, locale } = useLocale()

      setLocale('en-US')
      expect(locale.value).toBe('en-US')
      expect(localStorage.getItem(STORAGE_KEY)).toBe('en-US')
      expect(document.documentElement.lang).toBe('en')

      setLocale('zh-CN')
      expect(locale.value).toBe('zh-CN')
      expect(localStorage.getItem(STORAGE_KEY)).toBe('zh-CN')
      expect(document.documentElement.lang).toBe('zh-CN')
    })

    it('setLocale 传入非法值时回落中文', () => {
      const { setLocale, locale } = useLocale()
      setLocale('ja-JP' as 'zh-CN')
      expect(locale.value).toBe('zh-CN')
      expect(localStorage.getItem(STORAGE_KEY)).toBe('zh-CN')
    })

    it('toggleLocale 往返切换', () => {
      const { toggleLocale, locale } = useLocale()
      expect(locale.value).toBe('zh-CN')
      toggleLocale()
      expect(locale.value).toBe('en-US')
      toggleLocale()
      expect(locale.value).toBe('zh-CN')
    })

    it('语言标签与切换按钮文案随语言变化', () => {
      const { setLocale, languageLabel, switchLabel } = useLocale()
      expect(languageLabel.value).toBe('中文')
      expect(switchLabel.value).toBe('切换到英文')

      setLocale('en-US')
      expect(languageLabel.value).toBe('English')
      expect(switchLabel.value).toBe('Switch to Chinese')
    })
  })

  describe('pick', () => {
    it('按当前语言二选一，且支持非字符串值', () => {
      const { pick, setLocale } = useLocale()
      expect(pick('章节', 'Chapter')).toBe('章节')
      expect(pick(1, 2)).toBe(1)

      setLocale('en-US')
      expect(pick('章节', 'Chapter')).toBe('Chapter')
      expect(pick(1, 2)).toBe(2)
    })
  })

  describe('t', () => {
    it('命中词表并随语言切换', () => {
      const { t, setLocale } = useLocale()
      expect(t('common.cancel')).toBe('取消')
      expect(t('term.candidate')).toBe('候选稿')

      setLocale('en-US')
      expect(t('common.cancel')).toBe('Cancel')
      expect(t('term.candidate')).toBe('Candidate')
    })

    it('缺失 key 时原样返回 key，便于定位漏译', () => {
      const { t, setLocale } = useLocale()
      expect(t('nope.missing.key')).toBe('nope.missing.key')
      setLocale('en-US')
      expect(t('nope.missing.key')).toBe('nope.missing.key')
    })

    it('支持占位符插值，未提供的占位符保持原样', () => {
      const { t } = useLocale()
      // 词表里没有带参词条时，直接对 key 兜底串做插值验证行为
      expect(t('第 {index} 章', { index: 3 })).toBe('第 3 章')
      expect(t('第 {index} 章')).toBe('第 {index} 章')
      expect(t('{a}-{b}', { a: 'x' })).toBe('x-{b}')
    })
  })

  describe('本地化格式化', () => {
    it('formatNumber 输出千分位，非法值给 0', () => {
      const { formatNumber, setLocale } = useLocale()
      expect(formatNumber(1234567)).toBe('1,234,567')
      expect(formatNumber(Number.NaN)).toBe('0')

      setLocale('en-US')
      expect(formatNumber(1234567)).toBe('1,234,567')
    })

    it('formatWords 中文用「字」、英文用 word(s)', () => {
      const { formatWords, setLocale } = useLocale()
      expect(formatWords(1234)).toBe('1,234 字')
      expect(formatWords(1)).toBe('1 字')

      setLocale('en-US')
      expect(formatWords(1234)).toBe('1,234 words')
      expect(formatWords(1)).toBe('1 word')
      expect(formatWords(0)).toBe('0 words')
    })

    it('formatDate 两种语言排列不同，非法输入返回空串', () => {
      const { formatDate, formatDateTime, setLocale } = useLocale()
      const day = new Date(2026, 7, 14, 9, 5)

      const zh = formatDate(day)
      expect(zh).toMatch(/^2026\/08\/14$/)
      expect(formatDateTime(day)).toContain('2026')
      expect(formatDate('not-a-date')).toBe('')
      expect(formatDateTime('not-a-date')).toBe('')

      setLocale('en-US')
      const en = formatDate(day)
      expect(en).toMatch(/^08\/14\/2026$/)
      expect(en).not.toBe(zh)
      expect(formatDateTime(day)).toMatch(/AM|PM/)
    })

    it('punct 随语言给出中英标点', () => {
      const { punct, setLocale } = useLocale()
      expect(punct.colon).toBe('：')
      expect(punct.comma).toBe('、')
      expect(punct.paren('3')).toBe('（3）')

      setLocale('en-US')
      expect(punct.colon).toBe(': ')
      expect(punct.comma).toBe(', ')
      expect(punct.paren(3)).toBe(' (3)')
    })
  })

  it('保留历史导出，避免既有组件破坏', () => {
    const api = useLocale()
    for (const key of ['locale', 'isChinese', 'languageLabel', 'switchLabel', 'setLocale', 'toggleLocale', 'pick']) {
      expect(api).toHaveProperty(key)
    }
  })
})
