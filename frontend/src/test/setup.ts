type StorageLike = Storage & {
  __xuanqiongPolyfill?: boolean
}

const isStorageLike = (value: unknown): value is StorageLike => {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Partial<StorageLike>
  return (
    typeof candidate.clear === 'function' &&
    typeof candidate.getItem === 'function' &&
    typeof candidate.setItem === 'function'
  )
}

const createMemoryStorage = (): StorageLike => {
  const values = new Map<string, string>()
  return {
    __xuanqiongPolyfill: true,
    get length() { return values.size },
    clear: () => values.clear(),
    getItem: (key: string) => values.get(String(key)) ?? null,
    key: (index: number) => Array.from(values.keys())[index] ?? null,
    removeItem: (key: string) => { values.delete(String(key)) },
    setItem: (key: string, value: string) => { values.set(String(key), String(value)) },
  }
}

const ensureStorage = (name: 'localStorage' | 'sessionStorage') => {
  // Node 25 exposes a Web Storage getter that emits a warning when no
  // --localstorage-file is configured. Inspect descriptors instead of invoking
  // that getter; jsdom tests only need an isolated in-memory implementation.
  let owner: object | null = window
  let descriptor: PropertyDescriptor | undefined
  while (owner && !descriptor) {
    descriptor = Object.getOwnPropertyDescriptor(owner, name)
    owner = Object.getPrototypeOf(owner) as object | null
  }

  if (descriptor && 'value' in descriptor && isStorageLike(descriptor.value)) {
    return
  }

  Object.defineProperty(window, name, {
    configurable: true,
    value: createMemoryStorage(),
  })
}

ensureStorage('localStorage')
ensureStorage('sessionStorage')
