import { defineStore } from 'pinia'
import { API_BASE_URL, API_PREFIX } from '@/api/config'

export interface User {
  id: number
  username: string
  is_admin: boolean
  must_change_password: boolean
}

const AUTH_TOKEN_KEY = 'xuanqiong.auth.access_token'

export const getAccessToken = (): string | null => {
  try { return window.localStorage.getItem(AUTH_TOKEN_KEY) }
  catch { return null }
}

export const setAccessToken = (token: string | null): void => {
  try {
    if (token) window.localStorage.setItem(AUTH_TOKEN_KEY, token)
    else window.localStorage.removeItem(AUTH_TOKEN_KEY)
  } catch { /* storage may be unavailable in private/SSR contexts */ }
}

export const buildAuthHeaders = (headers?: HeadersInit): Headers => {
  const result = new Headers(headers || {})
  const token = getAccessToken()
  if (token) result.set('Authorization', `Bearer ${token}`)
  return result
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null as User | null,
    isBootstrapping: false,
    bootstrapError: '' as string,
  }),
  getters: {
    isAuthenticated: (state) => Boolean(state.user),
    isAdmin: (state) => Boolean(state.user?.is_admin),
  },
  actions: {
    setUser(user: User | null) {
      this.user = user
    },
    clearUser() {
      this.user = null
      setAccessToken(null)
    },
    async login(username: string, password: string): Promise<User> {
      const body = new URLSearchParams({ username, password })
      const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body,
      })
      if (!response.ok) throw new Error('用户名或密码错误')
      const payload = await response.json() as { access_token?: string }
      if (!payload.access_token) throw new Error('登录响应缺少访问令牌')
      setAccessToken(payload.access_token)
      await this.bootstrapUser()
      if (!this.user) throw new Error('登录后无法读取用户信息')
      return this.user
    },
    async bootstrapUser() {
      if (this.isBootstrapping) return
      this.isBootstrapping = true
      this.bootstrapError = ''
      try {
        const response = await fetch(`${API_BASE_URL}${API_PREFIX}/novels/current-user`, { headers: buildAuthHeaders() })
        if (!response.ok) {
          throw new Error(`status=${response.status}`)
        }
        const payload = await response.json() as User
        this.user = payload
      } catch (error) {
        this.user = null
        this.bootstrapError = error instanceof Error ? error.message : 'unknown-error'
      } finally {
        this.isBootstrapping = false
      }
    },
  },
})
