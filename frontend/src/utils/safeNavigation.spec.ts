import { describe, expect, it, vi } from 'vitest'
import type { Router } from 'vue-router'

import {
  hasSafeHistoryBack,
  isRecoverableRouteImportError,
  navigateBackOrFallback,
} from './safeNavigation'

describe('safeNavigation', () => {
  it('仅在上一条历史记录仍是应用内路径时允许 history back', () => {
    expect(hasSafeHistoryBack('/workspace', '/detail/1')).toBe(true)
    expect(hasSafeHistoryBack('/detail/1', '/detail/1')).toBe(false)
    expect(hasSafeHistoryBack('https://example.com/outside', '/detail/1', 'http://localhost:5173')).toBe(false)
    expect(hasSafeHistoryBack(null, '/detail/1')).toBe(false)
  })

  it('支持同源绝对地址的历史回退判断', () => {
    expect(
      hasSafeHistoryBack(
        'http://localhost:5173/workspace?tab=recent',
        '/detail/1',
        'http://localhost:5173',
      ),
    ).toBe(true)
  })

  it('在可安全回退时调用 router.back，否则走 fallback push', async () => {
    const router = {
      back: vi.fn(),
      push: vi.fn().mockResolvedValue(undefined),
    } as unknown as Router

    await navigateBackOrFallback(router, '/detail/1', { name: 'workspace-entry' }, {
      historyState: { back: '/workspace' },
      origin: 'http://localhost:5173',
    })

    expect(router.back).toHaveBeenCalledTimes(1)
    expect(router.push).not.toHaveBeenCalled()

    await navigateBackOrFallback(router, '/detail/1', { name: 'workspace-entry' }, {
      historyState: { back: 'about:blank' },
      origin: 'http://localhost:5173',
    })

    expect(router.push).toHaveBeenCalledWith({ name: 'workspace-entry' })
  })

  it('识别可通过硬刷新恢复的路由懒加载错误', () => {
    expect(isRecoverableRouteImportError(new Error('Failed to fetch dynamically imported module'))).toBe(true)
    expect(isRecoverableRouteImportError(new Error('ChunkLoadError: Loading chunk 42 failed.'))).toBe(true)
    expect(isRecoverableRouteImportError(new Error('network timeout'))).toBe(false)
  })
})
