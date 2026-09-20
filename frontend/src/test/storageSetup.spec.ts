import { afterEach, describe, expect, it } from 'vitest'

describe('test storage setup', () => {
  afterEach(() => {
    window.localStorage.clear()
    window.sessionStorage.clear()
  })

  it('provides isolated local and session storage without invoking Node storage getters', () => {
    window.localStorage.setItem('local-key', 'local-value')
    window.sessionStorage.setItem('session-key', 'session-value')

    expect(window.localStorage.getItem('local-key')).toBe('local-value')
    expect(window.sessionStorage.getItem('session-key')).toBe('session-value')
    expect(window.localStorage.length).toBe(1)
    expect(window.sessionStorage.length).toBe(1)
  })
})
