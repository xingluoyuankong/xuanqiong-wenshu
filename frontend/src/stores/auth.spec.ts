import { afterEach, describe, expect, it } from 'vitest'
import { buildAuthHeaders, getAccessToken, setAccessToken } from './auth'

describe('auth token helpers', () => {
  afterEach(() => { window.localStorage.clear() })
  it('persists a token and adds a Bearer header without overwriting caller headers', () => {
    setAccessToken('test-token')
    const headers = buildAuthHeaders({ 'X-Request-ID': 'req-1' })
    expect(getAccessToken()).toBe('test-token')
    expect(headers.get('Authorization')).toBe('Bearer test-token')
    expect(headers.get('X-Request-ID')).toBe('req-1')
  })
  it('removes the token when cleared', () => {
    setAccessToken('test-token')
    setAccessToken(null)
    expect(getAccessToken()).toBeNull()
    expect(buildAuthHeaders().has('Authorization')).toBe(false)
  })
})
