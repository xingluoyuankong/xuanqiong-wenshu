import { ref } from 'vue'

import { pick } from '@/composables/useLocale'

type AlertType = 'success' | 'error' | 'info' | 'confirmation'

interface Alert {
  id: number
  visible: boolean
  type: AlertType
  title: string
  message: string
  showCancel: boolean
  confirmText: string
  cancelText: string
  onConfirm: (result: boolean) => void
}

const alerts = ref<Alert[]>([])
let alertId = 0

const closeAlert = (id: number, result: boolean) => {
  const index = alerts.value.findIndex((alert) => alert.id === id)
  if (index !== -1) {
    alerts.value[index].onConfirm(result)
    alerts.value.splice(index, 1)
  }
}

// 弹窗默认文案在调用时求值，切换语言后新弹出的弹窗即跟随当前语言
const defaultTitle = (type: AlertType) => {
  if (type === 'success') return pick('成功', 'Success')
  if (type === 'error') return pick('错误', 'Error')
  if (type === 'confirmation') return pick('请确认', 'Please confirm')
  return pick('提示', 'Notice')
}

const showAlert = (
  message: string,
  type: AlertType = 'info',
  title = '',
  options: Partial<Omit<Alert, 'id' | 'visible' | 'message' | 'type' | 'title'>> = {},
) => {
  return new Promise<boolean>((resolve) => {
    const id = alertId++
    const newAlert: Alert = {
      id,
      visible: true,
      type,
      title: title || defaultTitle(type),
      message,
      showCancel: options.showCancel || false,
      confirmText: options.confirmText || pick('确定', 'Confirm'),
      cancelText: options.cancelText || pick('取消', 'Cancel'),
      onConfirm: resolve,
    }
    alerts.value.push(newAlert)

    if ((type === 'success' || type === 'info') && !newAlert.showCancel) {
      setTimeout(() => closeAlert(id, false), 3000)
    }
  })
}

// title 留空即走 defaultTitle()，由它按当前语言给出标题
const showSuccess = (message: string, title = '') => showAlert(message, 'success', title)
const showError = (message: string, title = '') => showAlert(message, 'error', title)
const showInfo = (message: string, title = '') => showAlert(message, 'info', title)
const showConfirm = (message: string, title = '') => showAlert(message, 'confirmation', title, { showCancel: true })

export const globalAlert = {
  alerts,
  showAlert,
  closeAlert,
  showSuccess,
  showError,
  showInfo,
  showConfirm,
}

export function useAlert() {
  return {
    showAlert: globalAlert.showAlert,
  }
}
