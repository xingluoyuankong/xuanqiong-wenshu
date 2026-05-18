import type { RouteLocationRaw, Router } from 'vue-router'

const DEFAULT_ORIGIN = 'http://localhost'
const ROUTE_IMPORT_ERROR_PATTERNS = [
  /Failed to fetch dynamically imported module/i,
  /Importing a module script failed/i,
  /ChunkLoadError/i,
  /Loading chunk [^\s]+ failed/i,
  /dynamically imported module/i,
]

const normalizeHistoryBackPath = (back: unknown, origin: string = DEFAULT_ORIGIN) => {
  if (typeof back !== 'string' || !back.trim()) return null

  if (back.startsWith('/')) {
    return back
  }

  try {
    const url = new URL(back, origin)
    const base = new URL(origin)
    if (url.origin !== base.origin) {
      return null
    }
    return `${url.pathname}${url.search}${url.hash}`
  } catch {
    return null
  }
}

export const hasSafeHistoryBack = (
  back: unknown,
  currentFullPath: string,
  origin?: string,
) => {
  const normalized = normalizeHistoryBackPath(back, origin)
  return Boolean(normalized && normalized !== currentFullPath)
}

export const navigateBackOrFallback = async (
  router: Router,
  currentFullPath: string,
  fallback: RouteLocationRaw,
  options: {
    historyState?: { back?: unknown } | null
    origin?: string
  } = {},
) => {
  const historyState = options.historyState ?? (typeof window !== 'undefined' ? window.history.state : null)
  const origin = options.origin ?? (typeof window !== 'undefined' ? window.location.origin : DEFAULT_ORIGIN)

  if (hasSafeHistoryBack(historyState?.back, currentFullPath, origin)) {
    router.back()
    return
  }

  await router.push(fallback)
}

export const isRecoverableRouteImportError = (error: unknown) => {
  const message = error instanceof Error
    ? `${error.name}: ${error.message}`
    : String(error)

  return ROUTE_IMPORT_ERROR_PATTERNS.some((pattern) => pattern.test(message))
}
