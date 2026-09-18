// AIMETA P=Vite配置_构建和开发服务器配置|R=构建配置_代理配置|NR=不含业务逻辑|E=-|X=internal|A=Vite配置|D=vite|S=fs|RD=./README.ai
import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueJsx from '@vitejs/plugin-vue-jsx'
import vueDevTools from 'vite-plugin-vue-devtools'
import Components from 'unplugin-vue-components/vite'
import { NaiveUiResolver } from 'unplugin-vue-components/resolvers'

const getEnv = (...names: string[]) => {
  for (const name of names) {
    const value = process.env[name]
    if (value) {
      return value
    }
  }
  return undefined
}

const defaultBackendHost = getEnv('XUANQIONG_WENSHU_BACKEND_HOST') || '127.0.0.1'
const defaultBackendPort = getEnv('XUANQIONG_WENSHU_BACKEND_PORT') || '8013'
const defaultFrontendHost = getEnv('XUANQIONG_WENSHU_FRONTEND_HOST') || '127.0.0.1'
const defaultFrontendPort = Number(
  getEnv('XUANQIONG_WENSHU_FRONTEND_PORT') || '5174',
)

const apiProxyTarget =
  process.env.VITE_API_PROXY_TARGET ||
  process.env.VITE_API_BASE_URL ||
  getEnv('XUANQIONG_WENSHU_BACKEND_BASE_URL') ||
  `http://${defaultBackendHost}:${defaultBackendPort}`

// https://vitejs.dev/config/
const enableDevTools = process.env.VITE_ENABLE_DEVTOOLS === '1'

export default defineConfig(({ command }) => ({
  test: {
    environment: 'jsdom',
    globals: true,
    css: true,
  },
  plugins: [
    vue(),
    vueJsx(),
    command === 'serve' && enableDevTools ? vueDevTools() : null,
    // 自动导入 Naive UI 组件（按需加载，大幅减少打包体积）
    // @ts-ignore - NaiveUiResolver 在新版本中类型定义可能有变化
    Components({
      resolvers: [
        NaiveUiResolver()
      ],
    }),
  ].filter(Boolean),
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) {
            return undefined
          }
          if (id.includes('naive-ui')) {
            return 'naive-ui'
          }
          if (
            id.includes('@css-render') ||
            id.includes('vueuc') ||
            id.includes('vooks') ||
            id.includes('seemly') ||
            id.includes('async-validator') ||
            id.includes('evtd') ||
            id.includes('vdirs')
          ) {
            return 'naive-ui-runtime'
          }
          if (
            id.includes('/lodash/') ||
            id.includes('\\lodash\\') ||
            id.includes('/lodash-es/') ||
            id.includes('\\lodash-es\\')
          ) {
            return 'admin-vendor'
          }
          if (id.includes('@headlessui/vue')) {
            return 'headlessui'
          }
          if (id.includes('chart.js')) {
            return 'chart-vendor'
          }
          if (id.includes('marked') || id.includes('dompurify')) {
            return 'markdown-vendor'
          }
          if (id.includes('docx') || id.includes('file-saver')) {
            return 'export-vendor'
          }
          if (id.includes('vue-router')) {
            return 'vue-router'
          }
          if (id.includes('pinia')) {
            return 'pinia-vendor'
          }
          if (
            id.includes('/vue/') ||
            id.includes('\\vue\\') ||
            id.includes('@vue/')
          ) {
            return 'vue-vendor'
          }
          return 'vendor'
        },
      },
    },
  },
  resolve: {
    preserveSymlinks: true,
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    },
  },
  server: {
    host: defaultFrontendHost,
    port: defaultFrontendPort,
    strictPort: true,
    proxy: {
      '/api': {
        target: apiProxyTarget,
        changeOrigin: true,
      }
    }
  }
}))
