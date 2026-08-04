<!-- AIMETA P=根组件_应用根节点|R=全局布局_RouterView|NR=不含页面逻辑|E=component:App|X=ui|A=RouterView|D=vue-router|S=dom|RD=./README.ai -->
<script setup lang="ts">
import { defineAsyncComponent, onErrorCaptured, ref } from 'vue'
import { NConfigProvider } from 'naive-ui'
import { RouterView } from 'vue-router'
import { globalAlert } from '@/composables/useAlert'

const CustomAlert = defineAsyncComponent(() => import('@/components/CustomAlert.vue'))
const GlobalNavBar = defineAsyncComponent(() => import('@/components/GlobalNavBar.vue'))
const GlobalNotification = defineAsyncComponent(() => import('@/components/shared/GlobalNotification.vue'))
const fatalError = ref<string|null>(null)
onErrorCaptured((err: unknown) => { console.error("Global error captured:", err); fatalError.value = String(err).slice(0, 300) || "未知错误"; return false })
</script>

<template>
  <NConfigProvider>
    <div class="xq-app-root min-h-screen">
      <!-- 全局导航栏 -->
      <GlobalNavBar />

      <RouterView />

      <!-- 全局提示框 -->
      <CustomAlert
        v-for="alert in globalAlert.alerts.value"
        :key="alert.id"
        :visible="alert.visible"
        :type="alert.type"
        :title="alert.title"
        :message="alert.message"
        :show-cancel="alert.showCancel"
        :confirm-text="alert.confirmText"
        :cancel-text="alert.cancelText"
        @confirm="globalAlert.closeAlert(alert.id, true)"
        @cancel="globalAlert.closeAlert(alert.id, false)"
        @close="globalAlert.closeAlert(alert.id, false)"
      />

      <!-- Toast 通知 -->
      <GlobalNotification />
    </div>
  </NConfigProvider>
</template>

<style scoped>
</style>
