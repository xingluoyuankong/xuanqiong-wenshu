import { defineStore } from 'pinia'
import { API_BASE_URL, API_PREFIX } from '@/api/config'

export interface User {
  id: number
  username: string
  is_admin: boolean
  must_change_password: boolean
}

export const buildAuthHeaders = (headers?: HeadersInit) => new Headers(headers || {})

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
    },
    async bootstrapUser() {
      if (this.isBootstrapping) return
      this.isBootstrapping = true
      this.bootstrapError = ''
      try {
        const response = await fetch(`${API_BASE_URL}${API_PREFIX}/novels/current-user`)
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
