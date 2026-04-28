import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
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

export default router

