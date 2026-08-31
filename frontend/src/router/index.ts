import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import { isRecoverableRouteImportError } from '@/utils/safeNavigation'

const ROUTE_RELOAD_GUARD_KEY = 'xqws-route-import-reload'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  scrollBehavior() {
    return { top: 0 }
  },
  routes: [
    {
      path: '/',
      name: 'workspace-entry',
      component: () => import('../views/WorkspaceEntry.vue'),
    },
    {
      path: '/workspace',
      name: 'novel-workspace',
      component: () => import('../views/NovelWorkspace.vue'),
    },
    {
      path: '/inspiration',
      name: 'inspiration-mode',
      component: () => import('../views/InspirationMode.vue'),
    },
    {
      path: '/agent',
      name: 'agent-workspace',
      component: () => import('../views/AgentWorkspace.vue'),
    },
    {
      path: '/detail/:id',
      name: 'novel-detail',
      component: () => import('../views/NovelDetail.vue'),
      props: true,
    },
    {
      path: '/novel/:id',
      name: 'writing-desk',
      component: () => import('../views/WritingDesk.vue'),
      props: true,
    },
    {
      path: '/novel/:id/read',
      name: 'novel-full-reader',
      component: () => import('../views/NovelFullReaderView.vue'),
      props: true,
    },
    {
      path: '/admin',
      name: 'admin',
      component: () => import('../views/AdminView.vue'),
      meta: { requiresAdmin: true },
    },
    {
      path: '/admin/novel/:id',
      name: 'admin-novel-detail',
      component: () => import('../views/AdminNovelDetail.vue'),
      props: true,
      meta: { requiresAdmin: true },
    },
    {
      path: '/style-center',
      name: 'style-center',
      component: () => import('../views/StyleCenterView.vue'),
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('../views/SystemSettingsView.vue'),
    },
    {
      path: '/llm-settings',
      name: 'llm-settings',
      component: () => import('../views/SettingsView.vue'),
    },
  ],
})

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
    query: {
      denied: 'admin',
    },
  }
})

router.afterEach((to) => {
  if (typeof window === 'undefined') {
    return
  }

  if (sessionStorage.getItem(ROUTE_RELOAD_GUARD_KEY) === to.fullPath) {
    sessionStorage.removeItem(ROUTE_RELOAD_GUARD_KEY)
  }
})

router.onError((error, to) => {
  if (typeof window === 'undefined' || !to || !isRecoverableRouteImportError(error)) {
    return
  }

  const pendingReloadPath = sessionStorage.getItem(ROUTE_RELOAD_GUARD_KEY)
  if (pendingReloadPath === to.fullPath) {
    sessionStorage.removeItem(ROUTE_RELOAD_GUARD_KEY)
    return
  }

  sessionStorage.setItem(ROUTE_RELOAD_GUARD_KEY, to.fullPath)
  window.location.replace(router.resolve(to).href)
})

export default router

