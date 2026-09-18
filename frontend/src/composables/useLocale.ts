import { computed, ref } from 'vue'

const STORAGE_KEY = 'xuanqiong_wenshu_locale'
const localeState = ref<'zh-CN' | 'en-US'>((localStorage.getItem(STORAGE_KEY) as 'zh-CN' | 'en-US') || 'zh-CN')

const messages = {
  'zh-CN': {
    language: '中文',
    switchLabel: '切换到英文',
  },
  'en-US': {
    language: 'English',
    switchLabel: 'Switch to Chinese',
  },
} as const

export function useLocale() {
  const locale = computed(() => localeState.value)
  const isChinese = computed(() => localeState.value === 'zh-CN')

  function setLocale(value: 'zh-CN' | 'en-US') {
    localeState.value = value
    localStorage.setItem(STORAGE_KEY, value)
  }

  function toggleLocale() {
    setLocale(localeState.value === 'zh-CN' ? 'en-US' : 'zh-CN')
  }

  function pick<T>(zh: T, en: T) {
    return localeState.value === 'zh-CN' ? zh : en
  }

  return {
    locale,
    isChinese,
    languageLabel: computed(() => messages[localeState.value].language),
    switchLabel: computed(() => messages[localeState.value].switchLabel),
    setLocale,
    toggleLocale,
    pick,
  }
}
