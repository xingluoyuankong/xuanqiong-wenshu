import './shared/styles/tokens.css'
import './assets/main.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import { useAuthStore } from './stores/auth'

const bootstrap = async () => {
  const app = createApp(App)
  const pinia = createPinia()

  app.use(pinia)

  const authStore = useAuthStore(pinia)
  await authStore.bootstrapUser()

  app.use(router)
  app.mount('#app')
}

bootstrap().catch((err: unknown) => {
  console.error("Bootstrap failed:", err)
  const el = document.getElementById("app")
  if (el) {
    el.innerHTML = "<div style=padding:48px;text-align:center;font-family:sans-serif><h2>加载失败</h2><p>请检查后端服务是否启动，然后刷新页面重试。</p><p style=color:#94a3b8;font-size:13px>" + String(err).slice(0, 200) + "</p></div>"
  }
})
