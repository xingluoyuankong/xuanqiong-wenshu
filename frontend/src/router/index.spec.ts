import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it } from 'vitest'

import { useAuthStore } from '@/stores/auth'

const buildRouter = () => createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/', name: 'workspace-entry', component: { template: '<div />' } },
    { path: '/workspace', name: 'novel-workspace', component: { template: '<div />' } },
    { path: '/admin', name: 'admin', component: { template: '<div />' }, meta: { requiresAdmin: true } },
  ],
})

describe('router admin guard', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('非管理员访问管理页时跳回工作台并带 denied 标记', async () => {
    const router = buildRouter()
    router.beforeEach((to) => {
      if (!to.meta.requiresAdmin) {
        return true
      }

      const authStore = useAuthStore()
      if (authStore.isAdmin) {
        return true
      }

      return {
        name: 'novel-workspace',
        query: { denied: 'admin' },
      }
    })

    await router.push('/admin')

    expect(router.currentRoute.value.name).toBe('novel-workspace')
    expect(router.currentRoute.value.query.denied).toBe('admin')
  })

  it('管理员可以访问管理页', async () => {
    const authStore = useAuthStore()
    authStore.setUser({
      id: 1,
      username: 'admin',
      is_admin: true,
      must_change_password: false,
    })

    const router = buildRouter()
    router.beforeEach((to) => {
      if (!to.meta.requiresAdmin) {
        return true
      }

      return useAuthStore().isAdmin ? true : { name: 'novel-workspace', query: { denied: 'admin' } }
    })

    await router.push('/admin')

    expect(router.currentRoute.value.name).toBe('admin')
  })
})
