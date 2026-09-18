type StorageLike = Storage & {
  __xuanqiongPolyfill?: boolean
}

const ensureStorage = (name: 'localStorage' | 'sessionStorage') => {
  const current = window[name] as Partial<StorageLike> | undefined
  if (current && typeof current.clear === 'function' && typeof current.getItem === 'function' && typeof current.setItem === 'function') {
    return
  }

  const values = new Map<string, string>()
  const replacement: StorageLike = {
    __xuanqiongPolyfill: true,
    get length() { return values.size },
    clear: () => values.clear(),
    getItem: (key: string) => values.get(String(key)) ?? null,
    key: (index: number) => Array.from(values.keys())[index] ?? null,
    removeItem: (key: string) => { values.delete(String(key)) },
    setItem: (key: string, value: string) => { values.set(String(key), String(value)) },
  }

  Object.defineProperty(window, name, {
    configurable: true,
    value: replacement,
  })
}

ensureStorage('localStorage')
ensureStorage('sessionStorage')
